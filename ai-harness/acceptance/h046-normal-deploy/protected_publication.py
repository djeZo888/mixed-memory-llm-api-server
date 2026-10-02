#!/usr/bin/env python3
"""Prepare/review and publish protected packets. No key creation, inference or restart.

Publication is a separate root operation; a signed packet proposal is NOT a GO.
Only the existing ordinary key is used. Failed claimed operations remain spent.
"""
import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

BASE = ('run-codex.sh','engine/task-egress.py','engine/redact-acp.py',
        'engine/codex_receipts.py','engine/codex_native_trace.py',
        'security/chromium-seccomp.json','codex/config.toml','codex/models.json')
TECH = ('../tools/technical-vision/technical-vision-mcp.mjs','../tools/technical-vision/technical-vision.mjs')
GEN = ('codex/config-generation-only.toml','../tools/image/image-mcp.mjs',
       '../tools/image/image.mjs','codex/skills/sova-local-tools/SKILL.md')
PROFILES = ('ordinary','technical','generation','technical-generation')
UUID = re.compile(r'^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$')
HEX40 = re.compile(r'^[a-f0-9]{40}$')
HEX64 = re.compile(r'^[a-f0-9]{64}$')
RELEASES_ROOT = Path('/opt/ai-harness/releases')

class Refused(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Refused(reason)

def canonical(v):
    # All signed numbers are bounded integers. This matches codex-canonical.ts.
    def safe(x):
        require(not isinstance(x, float), 'Signed floating point values are forbidden')
        if isinstance(x, int):
            require(abs(x) <= 9007199254740991, 'Unsafe signed integer')
        elif isinstance(x, dict):
            require(all(isinstance(k, str) for k in x), 'Non-string JSON key')
            for value in x.values(): safe(value)
        elif isinstance(x, list):
            for value in x: safe(value)
    safe(v)
    def encode(x):
        if isinstance(x,dict):
            return '{'+','.join(json.dumps(k,ensure_ascii=False)+':'+encode(x[k]) for k in sorted(x,key=lambda k:k.encode('utf-16-be'))) + '}'
        if isinstance(x,list): return '['+','.join(encode(a) for a in x)+']'
        return json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return encode(v).encode('utf-8')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def exact(v, keys):
    return isinstance(v, dict) and set(v) == set(keys)

def ancestry(path, uid, private=False):
    p = Path(path)
    require(p.is_absolute() and str(p.resolve()) == str(p), 'Noncanonical path')
    for parent in [p, *p.parents]:
        s = parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and not stat.S_ISLNK(s.st_mode)
                and s.st_uid in (0, uid) and not s.st_mode & 0o022, 'Unsafe path ancestry')
    if private:
        s = p.lstat()
        require(s.st_uid == uid and s.st_mode & 0o077 == 0, 'Directory is not private app-owned')
    return p

def read_bytes(path, private=False, maximum=512 * 1024 * 1024, uid=None):
    uid = os.getuid() if uid is None else uid
    p = Path(path)
    ancestry(p.parent, uid, private)
    require(p.is_absolute() and str(p.resolve()) == str(p), 'File alias is forbidden')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid in ((uid,) if private else (0, uid))
                and (before.st_mode & 0o777 == 0o600 if private else not before.st_mode & 0o022)
                and 0 < before.st_size <= maximum, 'Unsafe protected/source file')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            raw = f.read(maximum + 1)
        after = os.fstat(fd)
        require(len(raw) == before.st_size and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'File changed during read')
        return raw
    finally:
        os.close(fd)

def load_json(path, **kwargs):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'Duplicate JSON key')
            out[k] = v
        return out
    return json.loads(read_bytes(path, **kwargs).decode('utf-8'), object_pairs_hook=pairs)

def verify_envelope(v, key):
    require(len(key) == 32 and exact(v, ('body','seal')) and isinstance(v['seal'], str)
            and HEX64.fullmatch(v['seal']) is not None, 'Malformed signed envelope')
    require(hmac.compare_digest(v['seal'], hmac.new(key, canonical(v['body']), hashlib.sha256).hexdigest()),
            'Untrusted HMAC envelope')
    return v['body']

def seal(body, key):
    return {'body': body, 'seal': hmac.new(key, canonical(body), hashlib.sha256).hexdigest()}

def receipt_names(profile):
    require(profile in PROFILES, 'Unknown source profile')
    return BASE + (GEN if 'generation' in profile else ()) + (TECH if 'technical' in profile else ())

def validate_release_paths(server_dir,deployment_dir,commit):
    require(HEX40.fullmatch(commit),'Final sealed source commit required')
    server=Path(server_dir);deployment=Path(deployment_dir)
    require(server.name=='server' and deployment.name=='deploy' and server.parent==deployment.parent
            and server.parent.name=='ai-harness' and server.parent.parent.parent==RELEASES_ROOT
            and re.fullmatch(re.escape(commit)+r'-[A-Za-z0-9][A-Za-z0-9._-]{0,63}',server.parent.parent.name),
            'Final immutable release sibling paths do not bind the sealed commit')
    ancestry(server,os.getuid());ancestry(deployment,os.getuid())
    metadata=read_bytes(server.parent/'source-commit.txt',maximum=128)
    require(metadata in (commit.encode(),commit.encode()+b'\n'),'Immutable release source-commit.txt mismatch')
    return server,deployment

def current_graph(server_dir, deployment_dir, profile):
    server = ancestry(server_dir, os.getuid())
    deployment = ancestry(deployment_dir, os.getuid())
    required = set()
    imports = re.compile(r'''(?:from\s*|import\s*\()?["'](\.\.?/[^"']+\.js)["']''')
    def walk(p):
        require(str(p).startswith(str(server) + os.sep), 'Executable import escapes release')
        if p in required: return
        raw = read_bytes(p)
        required.add(p)
        for name in imports.findall(raw.decode('utf-8')):
            # resolve lexical .. without silently following an alias.
            walk(Path(os.path.normpath(str(p.parent / name))))
    walk(server / 'dist/main.js')
    walk(server / 'dist/codex-preview-main.js')
    for p in list(required):
        required.add(Path(str(p).replace(os.sep + 'dist' + os.sep, os.sep + 'src' + os.sep,1)).with_suffix('.ts'))
    required.add(server / 'package-lock.json')
    sources = {}
    for name in receipt_names(profile):
        p = Path(os.path.normpath(str(deployment / name)))
        required.add(p)
        sources[name] = sha(read_bytes(p))
    required.add(deployment / 'engine/validate-image-overlays.py')
    files = {str(p): sha(read_bytes(p)) for p in sorted(required)}
    require(8 <= len(files) <= 512, 'Incomplete source graph')
    return files, sources

# This bridge validates ORIGINAL retained evidence with the actual compiled
# validators, not synthetic validation receipts. It prints no evidence content.
BASELINE_BRIDGE = r'''
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
let raw='';for await(const c of process.stdin)raw+=c;const x=JSON.parse(raw);
const r=await import(pathToFileURL(x.serverDir+'/dist/codex-receipts.js'));
const o=await import(pathToFileURL(x.serverDir+'/dist/codex-ordinary-entry.js'));
const q=x.body.qualification;
const launch=r.validateCodexLaunchReceipt(JSON.parse(readFileSync(q.launchPath,'utf8')),q.binding,q.observedProducer,q.validatedAtMs);
const s=JSON.parse(readFileSync(q.settlementPath,'utf8'));
const settlement=r.validateCodexSettlementReceipt(s,q.binding,launch,s.checkedAtMs);
const a=JSON.parse(readFileSync(q.protocolAckPath,'utf8'));
if(!settlement.cleanupOk||a.schema!=='codex-zero-generation-acks-v1'||a.launchNonce!==launch.nonce||a.initialize?.codexHome!==q.binding.profileDir+'/codex-home'||a.initialize?.platformOs!=='linux'||typeof a.initialize?.userAgent!=='string'||!a.initialize.userAgent.includes('0.158.0')||typeof a.threadStart?.thread?.id!=='string'||a.threadStart?.model!=='qwen3.8-27b'||a.threadStart?.modelProvider!=='sova'||a.threadStart?.cwd!==q.binding.workspace)throw Error('Missing actual no-generation protocol proof');
if(a.providerRequests!==0){if(!q.legacyTransportPath||!q.rawProtocolPath)throw Error('Missing original legacy evidence');o.assertOrdinaryNoGenerationObservation(a,JSON.parse(readFileSync(q.legacyTransportPath,'utf8')),{launchSha256:q.launchSha256,settlementSha256:q.settlementSha256,rawProtocolSha256:q.rawProtocolSha256});}
o.assertOrdinaryProtectedPaths(launch,x.protectedPaths);
process.stdout.write(JSON.stringify({originalEvidenceValidated:true,nativePassClaim:false}));
'''

CURRENT_BRIDGE = r'''
import {pathToFileURL} from 'node:url';
let raw='';for await(const c of process.stdin)raw+=c;const x=JSON.parse(raw);
const o=await import(pathToFileURL(x.serverDir+'/dist/codex-ordinary-entry.js'));
const entry=o.loadCodexOrdinaryEntry(x.baseline,x.key,{serverDir:x.serverDir,deploymentDir:x.deploymentDir});
entry.assertSourcesCurrent();
process.stdout.write(JSON.stringify({approvalId:entry.approvalId,generationAuthority:entry.generationAuthority??null,nativePassClaim:false}));
'''

def actual_current_loader(baseline,key,body):
    result=subprocess.run(['node','--input-type=module','-e',CURRENT_BRIDGE],
        input=json.dumps({'baseline':str(baseline),'key':str(key),'serverDir':body['serverDir'],
                          'deploymentDir':body['deploymentDir']}).encode(),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
    if result.returncode:
        sys.stderr.buffer.write(result.stderr)
        raise Refused('Actual ordinary current loader failed; exit='+str(result.returncode))
    return json.loads(result.stdout)

def validate_baseline(baseline_path, key_path, server_dir):
    raw = read_bytes(baseline_path, private=True, maximum=262144)
    key = read_bytes(key_path, private=True, maximum=32)
    b = verify_envelope(json.loads(raw), key)
    q = b.get('qualification', {})
    require(b.get('schema') == 'codex-ordinary-entry-v1' and HEX40.fullmatch(b.get('sourceCommit',''))
            and re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', b.get('approvalId',''))
            and q.get('binaryVersion') == '0.158.0'
            and q.get('upstream') == '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'
            and set(b.get('receiptSources', {})) == set(BASE), 'Missing genuine pinned ordinary baseline')
    require(8 <= len(b.get('files',{})) <= 512, 'Incomplete retained baseline source')
    for path, digest in b['files'].items():
        require(HEX64.fullmatch(digest) and sha(read_bytes(path)) == digest, 'Retained baseline source changed')
    require(q.get('binding',{}).get('sources') == b['receiptSources'], 'Retained baseline receipt closure changed')
    protected = [str(baseline_path), str(key_path)]
    for name, maximum in [('launch',32768),('settlement',32768),('protocolAck',65536),
                          ('binary',512*1024*1024),('legacyTransport',8*1024*1024),('rawProtocol',2*1024*1024)]:
        path = q.get(name+'Path')
        if name in ('legacyTransport','rawProtocol') and path is None: continue
        require(isinstance(path,str) and HEX64.fullmatch(q.get(name+'Sha256',''))
                and sha(read_bytes(path, private=True, maximum=maximum)) == q[name+'Sha256'],
                'Missing/changed genuine baseline ' + name + ' evidence')
        protected.append(path)
    # Preserve original subprocess exit/stderr for operator capture. Never print keys.
    result = subprocess.run(['node','--input-type=module','-e',BASELINE_BRIDGE],
        input=json.dumps({'body':b,'serverDir':str(server_dir),'protectedPaths':protected}).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode:
        sys.stderr.buffer.write(result.stderr)
        raise Refused('Actual retained baseline consumer validation failed; exit=' + str(result.returncode))
    require(json.loads(result.stdout).get('originalEvidenceValidated') is True, 'Missing baseline validator result')
    return raw, b, key

def prepare_ordinary(baseline, key, server, deployment, commit, profile, reviewed_at):
    validate_release_paths(server,deployment,commit)
    at = int(dt.datetime.fromisoformat(reviewed_at.replace('Z','+00:00')).timestamp()*1000)
    require(at <= int(time.time()*1000), 'Future review timestamp')
    raw, b, _ = validate_baseline(baseline, key, server)
    files, sources = current_graph(server, deployment, profile)
    return {'schema':'codex-ordinary-current-sources-v1','reviewedBy':'root','reviewedAt':reviewed_at,
            'baselineApprovalSha256':sha(raw),'baselineApprovalId':b['approvalId'],'sourceCommit':commit,
            'serverDir':str(server),'deploymentDir':str(deployment),'profile':profile,'files':files,'receiptSources':sources}

def identity(v):
    require(exact(v, ('pid','startTicks','uid','bootId','cgroupPath')) and type(v['pid']) is int
            and v['pid'] > 0 and type(v['uid']) is int and v['uid'] > 0
            and re.fullmatch(r'\d+',v['startTicks']) and UUID.fullmatch(v['bootId'])
            and isinstance(v['cgroupPath'],str) and v['cgroupPath'].startswith('/'), 'Invalid current app owner')
    return v

def observe_owner(pid, proc_root=Path('/proc')):
    require(type(pid) is int and pid > 0, 'Positive app PID required')
    def ticks():
        raw = (proc_root / str(pid) / 'stat').read_text()
        return raw[raw.rfind(')')+2:].split()[19]
    start = ticks()
    status = (proc_root / str(pid) / 'status').read_text()
    ids = re.search(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',status,re.M)
    require(ids and len(set(ids.groups())) == 1, 'App uid is changing')
    cg = (proc_root / str(pid) / 'cgroup').read_text().strip()
    require(cg.startswith('0::/') and '\n' not in cg and ticks() == start, 'App birth/cgroup changed')
    return identity({'pid':pid,'startTicks':start,'uid':int(ids[1]),
                     'bootId':(proc_root/'sys/kernel/random/boot_id').read_text().strip(),'cgroupPath':cg[3:]})

def observe_unit(unit,uid):
    # env -i intentionally removes inherited INVOCATION_ID from the app.
    # Read systemd's actual identity instead; this is not a lifecycle command.
    require(unit=='ai-harness.service','Publication is limited to the reviewed normal unit')
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','XDG_RUNTIME_DIR':'/run/user/'+str(uid),
         'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/'+str(uid)+'/bus'}
    r=subprocess.run(['/usr/bin/systemctl','--user','show',unit,'--no-pager',
                      '--property=MainPID','--property=InvocationID','--property=ControlGroup'],
                     env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
    if r.returncode:
        sys.stderr.buffer.write(r.stderr)
        raise Refused('Current unit read failed; exit='+str(r.returncode))
    fields={}
    for line in r.stdout.decode('utf-8').splitlines():
        key,value=line.split('=',1)
        require(key not in fields,'Duplicate current unit property')
        fields[key]=value
    require(set(fields)=={'MainPID','InvocationID','ControlGroup'},'Incomplete current unit identity')
    return fields

def validate_sidecar(path, baseline, key_path, now):
    b = verify_envelope(load_json(path,private=True,maximum=262144),read_bytes(key_path,private=True,maximum=32))
    require(exact(b, ('schema','reviewedBy','reviewedAt','baselineApprovalSha256','baselineApprovalId',
                    'sourceCommit','serverDir','deploymentDir','profile','files','receiptSources')),
            'Invalid current sidecar keys')
    expected = prepare_ordinary(baseline,key_path,b['serverDir'],b['deploymentDir'],b['sourceCommit'],b['profile'],b['reviewedAt'])
    require(canonical(b) == canonical(expected), 'Current signed source graph changed')
    return b

def prepare_generation(sidecar, baseline, key, ticket_id, session_id, pid, issued, expires):
    require(UUID.fullmatch(ticket_id) and UUID.fullmatch(session_id) and type(issued) is int
            and type(expires) is int and issued <= int(time.time()*1000) < expires
            and 0 < expires-issued <= 1800000, 'Invalid finite generation ticket identifiers/deadline')
    b = validate_sidecar(sidecar,baseline,key,int(time.time()*1000))
    require(str(sidecar) == str(baseline)+'.sources.json' and b['profile'] in ('generation','technical-generation'),
            'Generation requires the exact protected current sidecar')
    loaded=actual_current_loader(baseline,key,b)
    expected_authority={'sourceCommit':b['sourceCommit'],'profile':b['profile'],
                        'currentSourceSha256':sha(canonical(b)),
                        'receiptSourcesSha256':sha(canonical(b['receiptSources']))}
    require(loaded.get('generationAuthority')==expected_authority,'Actual consumer source authority mismatch')
    return {'schema':'codex-normal-generation-acceptance-v1','reviewedBy':'root','id':ticket_id,
        'sessionId':session_id,'issuedAtMs':issued,'expiresAtMs':expires,'maxNativeRuns':1,'maxImageJobs':1,
        'operation':'generation','size':'1920x1080','authority':{'sourceCommit':b['sourceCommit'],
        'profile':b['profile'],'currentSourceSha256':sha(canonical(b)),
        'receiptSourcesSha256':sha(canonical(b['receiptSources']))},'owner':observe_owner(pid)}

GO_KEYS = ('schema','reviewedBy','id','operation','issuedAtMs','expiresAtMs','maxInvocations','sourceCommit',
           'bodySha256','receiptSourcesSha256','helperSha256','baselinePath','keyPath','targetPath',
           'claimsDir','owner','ownerObservationPath','ownerObservationSha256','configFiles')

def validate_go(go, key, body, operation, baseline, key_path, target, claims, now):
    g = verify_envelope(go,key)
    require(exact(g,GO_KEYS) and g['schema']=='h046-protected-publication-go-v1' and g['reviewedBy']=='root'
            and UUID.fullmatch(g['id']) and g['operation']==operation and type(g['maxInvocations']) is int and g['maxInvocations']==1
            and type(g['issuedAtMs']) is int and type(g['expiresAtMs']) is int
            and g['issuedAtMs'] <= now < g['expiresAtMs'] and 0 < g['expiresAtMs']-g['issuedAtMs'] <= 1800000,
            'Missing fresh finite root publication GO')
    authority = body.get('authority', body)
    sources_hash = authority.get('receiptSourcesSha256',sha(canonical(body.get('receiptSources',{}))))
    require(g['sourceCommit']==authority['sourceCommit'] and g['bodySha256']==sha(canonical(body))
            and g['receiptSourcesSha256']==sources_hash and g['helperSha256']==sha(read_bytes(Path(__file__).absolute()))
            and g['baselinePath']==str(baseline) and g['keyPath']==str(key_path)
            and g['targetPath']==str(target) and g['claimsDir']==str(claims), 'GO source/config/helper/path mismatch')
    require(identity(g['owner']) == observe_owner(g['owner']['pid']) and g['owner']['uid']==os.getuid(), 'Current app owner mismatch')
    observation = load_json(g['ownerObservationPath'],private=True,maximum=65536)
    require(sha(read_bytes(g['ownerObservationPath'],private=True,maximum=65536))==g['ownerObservationSha256']
            and exact(observation,('schema','owner','observedAtMs','unit','invocationId','sourceCommit',
                                  'configSha256','activeRuns','activeImageJobs','activeVisionJobs','originalLogSha256'))
            and observation['schema']=='h046-root-app-observation-v1' and observation['owner']==g['owner']
            and type(observation['observedAtMs']) is int and 0 <= now-observation['observedAtMs'] <= 15000
            and all(type(observation[n]) is int and observation[n]==0 for n in ('activeRuns','activeImageJobs','activeVisionJobs'))
            and isinstance(observation['unit'],str) and observation['unit'].endswith('.service')
            and re.fullmatch(r'[a-f0-9]{32}',observation['invocationId'])
            and HEX40.fullmatch(observation['sourceCommit']) and HEX64.fullmatch(observation['originalLogSha256']),
            'Missing current genuine idle/owner/unit observation')
    unit=observe_unit(observation['unit'],g['owner']['uid'])
    require(unit['MainPID']==str(g['owner']['pid']) and unit['InvocationID']==observation['invocationId']
            and unit['ControlGroup']==g['owner']['cgroupPath'], 'Current unit invocation/owner/cgroup mismatch')
    require(isinstance(g['configFiles'],dict) and g['configFiles']
            and sha(canonical(g['configFiles']))==observation['configSha256'], 'GO config closure mismatch')
    for path,digest in g['configFiles'].items():
        require(HEX64.fullmatch(digest) and sha(read_bytes(path))==digest,'Current config bytes changed')
    if operation=='generation-ticket': require(body['owner']==g['owner'],'Ticket app owner mismatch')
    ancestry(claims,os.getuid(),True)
    ancestry(Path(target).parent,os.getuid(),True)
    require(not Path(target).exists() and not Path(target).is_symlink(), 'Publication is exclusive; replacement requires another reviewed helper')
    return g

def exclusive(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(raw); f.flush(); os.fsync(fd)
    finally: os.close(fd)

def publish(body, go_path, baseline, key_path, target, claims):
    key=read_bytes(key_path,private=True,maximum=32)
    operation = 'ordinary-current-sources' if body.get('schema')=='codex-ordinary-current-sources-v1' else 'generation-ticket'
    if operation=='ordinary-current-sources':
        require(str(target)==str(baseline)+'.sources.json','Ordinary sidecar target must be fixed beside baseline')
        current=prepare_ordinary(baseline,key_path,body['serverDir'],body['deploymentDir'],body['sourceCommit'],body['profile'],body['reviewedAt'])
    else:
        current=prepare_generation(str(baseline)+'.sources.json',baseline,key_path,body['id'],body['sessionId'],body['owner']['pid'],body['issuedAtMs'],body['expiresAtMs'])
    require(canonical(current)==canonical(body),'Publication body/source/owner drift')
    go=load_json(go_path,private=True,maximum=65536)
    g=validate_go(go,key,body,operation,baseline,key_path,target,claims,int(time.time()*1000))
    claim=Path(claims)/(g['id']+'.claim.json')
    exclusive(claim,canonical({'schema':'h046-publication-claim-v1','goSha256':sha(canonical(go)),
                              'claimedAtMs':int(time.time()*1000),'settlementClaim':False})+b'\n')
    # A claim is never removed, including a failed operation. No retry or refund.
    require(int(time.time()*1000)<g['expiresAtMs'] and observe_owner(g['owner']['pid'])==g['owner'],'GO expired or owner changed after claim')
    validate_go(go,key,body,operation,baseline,key_path,target,claims,int(time.time()*1000))
    if operation=='ordinary-current-sources':
        files,sources=current_graph(body['serverDir'],body['deploymentDir'],body['profile'])
        require(files==body['files'] and sources==body['receiptSources'],'Source graph changed after GO claim')
    else:
        b=validate_sidecar(str(baseline)+'.sources.json',baseline,key_path,int(time.time()*1000))
        require(sha(canonical(b))==body['authority']['currentSourceSha256'],'Generation source changed after GO claim')
    if operation=='generation-ticket':
        child=Path(target).parent/body['id']
        os.mkdir(child,0o700)  # consumer's exclusive claims live in this private UUID directory
        ancestry(child,os.getuid(),True)
    envelope=seal(body,key)
    exclusive(target,canonical(envelope)+b'\n')
    if operation=='ordinary-current-sources': actual_current_loader(baseline,key_path,body)
    return {'schema':'h046-publication-result-v1','goId':g['id'],'operation':operation,
            'path':str(target),'packetSha256':sha(read_bytes(target,private=True,maximum=262144)),
            'bodySha256':sha(canonical(body)),'settlementClaim':False,'nativePassClaim':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    ordinary=sub.add_parser('prepare-ordinary')
    for name in ('baseline','key','server-dir','deployment-dir','source-commit','profile','reviewed-at'): ordinary.add_argument('--'+name,required=True)
    generation=sub.add_parser('prepare-generation')
    for name in ('baseline','key','sidecar','ticket-id','session-id'): generation.add_argument('--'+name,required=True)
    for name in ('app-pid','issued-at-ms','expires-at-ms'): generation.add_argument('--'+name,type=int,required=True)
    pub=sub.add_parser('publish')
    for name in ('body-file','go','baseline','key','target','claims-dir'): pub.add_argument('--'+name,required=True)
    a=p.parse_args()
    try:
        if a.command=='prepare-ordinary': result=prepare_ordinary(a.baseline,a.key,a.server_dir,a.deployment_dir,a.source_commit,a.profile,a.reviewed_at)
        elif a.command=='prepare-generation': result=prepare_generation(a.sidecar,a.baseline,a.key,a.ticket_id,a.session_id,a.app_pid,a.issued_at_ms,a.expires_at_ms)
        else: result=publish(load_json(a.body_file,private=True,maximum=262144),a.go,a.baseline,a.key,a.target,a.claims_dir)
        sys.stdout.buffer.write(canonical(result)+b'\n')
    except (Refused,OSError,KeyError,TypeError,ValueError,subprocess.TimeoutExpired) as e:
        print('REFUSED: '+str(e),file=sys.stderr)
        return 2
    return 0

if __name__=='__main__': sys.exit(main())
