#!/usr/bin/env python3
"""Check nginx boundaries; source checks never read the protected secret include."""
import argparse
import pathlib
import re
import subprocess
import sys
import unittest

SECRET = '/etc/ai-harness/image-approval-proxy.conf'
VISION = r'^/api/sessions/[a-zA-Z0-9_-]{1,80}/technical-vision-jobs/[a-zA-Z0-9_-]{1,80}/(status|lookup|cancel)$'
IMAGE = r'^/api/sessions/[a-zA-Z0-9_-]+/image-jobs/[a-zA-Z0-9_-]+/approval-token$'
MEMORY = r'^/api/sessions/[a-zA-Z0-9_-]+/memory/(accept|recovery/[a-zA-Z0-9_-]+/(acknowledge|recover))$'


def parse(text):
    text = '\n'.join(line.split('#', 1)[0] for line in text.splitlines())
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s;]+|;', text)
    position = 0
    def block(nested=False):
        nonlocal position
        nodes = []; head = []
        while position < len(tokens):
            token = tokens[position]; position += 1
            if token == '}':
                if not nested or head: raise ValueError('invalid block')
                return nodes
            if token == ';':
                if not head: raise ValueError('empty directive')
                nodes.append((head, None)); head = []
            elif token == '{':
                if not head: raise ValueError('empty block')
                if head[:2]==['location','~']: head[2]=head[2].strip('"')
                nodes.append((head, block(True))); head = []
            else: head.append(token)
        if nested or head: raise ValueError('unclosed directive')
        return nodes
    return block()


def validate(text, includes=None, source=False):
    # Historical source fixtures concatenate public templates. Preserve that API
    # as source-only; actual -T validation always passes its complete file map.
    if includes is None:
        includes = source_inputs(pathlib.Path(__file__).resolve().parent.parent/'nginx')[1]
        source = True
    def expand(nodes, seen=()):
        result = []
        for head, child in nodes:
            if head[0] == 'include':
                target = head[1]
                if target == SECRET:
                    if not source:
                        if target not in includes: raise ValueError('protected include absent')
                        secret = parse(includes[target])
                        if len(secret)!=1 or len(secret[0][0])!=3 or secret[0][0][:2]!=['proxy_set_header','X-AI-Harness-Approval-Proxy'] or '$' in secret[0][0][2] or secret[0][0][2] in ('""',"''"): raise ValueError('invalid protected setter')
                    result.append((['protected_auth'],None))
                else:
                    if target not in includes or target in seen: raise ValueError('unresolved include')
                    result.extend(expand(parse(includes[target]),seen+(target,)))
            else: result.append((head,expand(child,seen) if child is not None else None))
        return result
    tree = expand(parse(text))
    def walk(nodes):
        for head,child in nodes:
            yield head
            if child is not None: yield from walk(child)
    heads=list(walk(tree))
    if any(h[0] in ('real_ip_header','set_real_ip_from','real_ip_recursive') for h in heads): raise ValueError('actual peer rewritten')
    if any(h[0]=='proxy_set_header' and h[1]=='X-AI-Harness-Approval-Proxy' and h[2]!='""' for h in heads): raise ValueError('spoofable capability')
    if any(h[0]=='proxy_set_header' and h[1] in ('X-Real-IP','X-Forwarded-For') and h[2]!='$remote_addr' for h in heads): raise ValueError('spoofable peer')
    servers=[c for h,c in tree if h==['server']]
    main=[s for s in servers if (['server_name','10.156.100.61'],None) in s]
    status=[s for s in servers if (['server_name','status.ai-harness'],None) in s]
    if len(main)!=1 or len(status)!=1: raise ValueError('server boundary absent')
    main=main[0]
    protected=[(h,c) for h,c in main if c is not None and any(x[0]=='protected_auth' for x in walk(c))]
    if len(protected)!=3 or sum(h[0]=='protected_auth' for h in heads)!=3 or {tuple(h) for h,c in protected}!={('location','~',VISION),('location','~',IMAGE),('location','~',MEMORY)}: raise ValueError('capability path scope changed')
    for head,child in protected:
        method='GET' if head[2]==IMAGE else 'POST'
        methods=[(h,c) for h,c in child if h[0]=='limit_except']
        if methods!=[(['limit_except',method],[(['deny','all'],None)])]: raise ValueError('protected method changed')
        access=[h for h,c in child if h[0] in ('deny','allow')]
        if access[:3]!=[['deny','127.0.0.0/8'],['deny','::1'],['deny','10.156.100.61']] or ['allow','all'] not in access: raise ValueError('peer inventory changed')
        if head[2]==VISION:
            for h in (['client_max_body_size','1k'],['client_body_timeout','5s'],['proxy_pass','http://127.0.0.1:8080'],['proxy_read_timeout','15s'],['proxy_send_timeout','15s']):
                if (h,None) not in child: raise ValueError('technical bounds changed')
    generic=[c for h,c in main if h==['location','/']]
    if len(generic)!=1 or (['proxy_set_header','X-AI-Harness-Approval-Proxy','""'],None) not in generic[0]: raise ValueError('other paths retain capability')
    if any(h[0]=='protected_auth' for h in walk(generic[0])): raise ValueError('generic capability grant')
    for h,c in main:
        if h in (['location','=','/admin'],['location','^~','/api/admin/']) and (['deny','127.0.0.0/8'],None) not in c: raise ValueError('admin peer inventory absent')
    if not {('location','=','/admin'),('location','^~','/api/admin/')} <= {tuple(h) for h,c in main}: raise ValueError('admin routes absent')
    if not any(h==['proxy_pass','http://unix:/run/ai-harness-status/http.sock'] for h in heads): raise ValueError('status UDS absent')
    if any(h[0]=='protected_auth' for h in walk(status[0])): raise ValueError('status grants capability')
    for action in ('status','lookup','cancel'):
        if not re.fullmatch(VISION,f'/api/sessions/session_1/technical-vision-jobs/vision-1/{action}'): raise ValueError('valid route absent')
    for path in ('/api/sessions/a/technical-vision-jobs/b/status/extra','/api/sessions/a/technical-vision-jobs/b/list','/api/sessions/a/technical-vision-jobs','/api/technical-vision-capabilities','/api/sessions/a.b/technical-vision-jobs/b/cancel','/api/sessions/'+('a'*81)+'/technical-vision-jobs/b/status'):
        if re.fullmatch(VISION,path): raise ValueError('route too broad')


def source_inputs(directory):
    directory=pathlib.Path(directory)
    files=('status-proxy.inc','technical-vision-proxy.inc','admin-peer-deny.inc')
    return (directory/'ai-harness.conf').read_text(),{'/etc/ai-harness/'+n:(directory/n).read_text() for n in files}


def self_test(directory):
    text,includes=source_inputs(directory)
    class BoundaryTests(unittest.TestCase):
        def test_current_source(self): validate(text,includes,True)
        def test_negative_mutations(self):
            mutations=[(text.replace(VISION,VISION[:-1]),includes),(text+'\nreal_ip_header X-Forwarded-For;\n',includes),(text.replace('X-AI-Harness-Approval-Proxy ""','X-AI-Harness-Approval-Proxy $http_x_ai_harness_approval_proxy'),includes),(text.replace('X-Forwarded-For $remote_addr','X-Forwarded-For $http_x_forwarded_for'),includes)]
            for old,new in [('limit_except POST','limit_except GET'),('client_max_body_size 1k','client_max_body_size 50m'),(SECRET,'/etc/ai-harness/attacker.conf'),('admin-peer-deny.inc','missing-peer.inc')]:
                changed=dict(includes);key='/etc/ai-harness/technical-vision-proxy.inc';changed[key]=changed[key].replace(old,new);mutations.append((text,changed))
            changed=dict(includes);key='/etc/ai-harness/admin-peer-deny.inc';changed[key]=changed[key].replace('deny 127.0.0.0/8;','allow 127.0.0.0/8;');mutations.append((text,changed))
            for i,(bad,inc) in enumerate(mutations):
                with self.subTest(mutation=i),self.assertRaises(ValueError):validate(bad,inc,True)
        def test_actual_secret_setter(self):
            inc=dict(includes);inc[SECRET]='proxy_set_header X-AI-Harness-Approval-Proxy "synthetic-unit-value";';validate(text,inc,False)
            for value in ('$http_x_ai_harness_approval_proxy','""'):
                inc[SECRET]='proxy_set_header X-AI-Harness-Approval-Proxy '+value+';'
                with self.subTest(value=value),self.assertRaises(ValueError):validate(text,inc,False)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    if not result.wasSuccessful(): raise ValueError('boundary tests failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');parser.add_argument('--source-dir');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.source_dir:
        if args.check: raise ValueError('separate source and actual modes')
        if args.self_test:self_test(args.source_dir)
        else:validate(*source_inputs(args.source_dir),source=True)
        print('SOURCE_ONLY nginx boundary PASS; installed peer inventory and live access NOT_TESTED')
    elif args.check and not args.self_test:
        result=subprocess.run(['/usr/sbin/nginx','-T'],capture_output=True,text=True,timeout=5)
        if result.returncode:raise ValueError('nginx configuration invalid')
        sections=re.split(r'^# configuration file ([^\n:]+):\n',result.stdout,flags=re.M);includes=dict(zip(sections[1::2],sections[2::2]))
        main=includes.get('/etc/ai-harness/ai-harness.conf') or includes.get('/etc/nginx/conf.d/ai-harness.conf')
        if main is None:raise ValueError('exact server configuration absent')
        validate(main,includes);print('nginx actual-peer/UDS preflight PASS; live access acceptance still required')
    else:parser.error('choose --source-dir [--self-test] or --check')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(f'nginx-boundary: refused ({type(error).__name__})',file=sys.stderr);sys.exit(1)
