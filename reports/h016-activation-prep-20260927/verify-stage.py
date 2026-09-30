#!/usr/bin/env python3
"""H016 bounded artifact/stage verification; no service or backend requests.
Usage: verify-stage.py inputs|staged|preservation (or --help).
Private unit copies and data identities stay under the remote task, outside Git.
"""
import hashlib, json, os, pathlib, shlex, stat, subprocess, sys, tarfile
B = pathlib.Path('/home/user/ai-harness-build/H016-MIMO-BUILD-20260927')
P = pathlib.Path('/home/user/ai-harness-build/H016-ACTIVATION-PREP-20260927')
OLD = pathlib.Path('/opt/ai-harness/releases/7143c17d73173db9364b77956679c86d7026a4ae/ai-harness')
NEW = pathlib.Path('/opt/ai-harness/releases/928b3b470058241f089a839367d4b30d5887a6e3-h016/ai-harness')
SOURCE = '928b3b470058241f089a839367d4b30d5887a6e3'
BASE = '9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c'
IMAGE = '6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022'
TAG = 'localhost/ai-harness-engine:0.0.2-ae65651df5f9'
UNITS = {'ai-harness.service': pathlib.Path('/home/user/.config/systemd/user/ai-harness.service'),
         '30-h008-registry.conf': pathlib.Path('/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf')}
EXPECTED_UNITS = {'ai-harness.service':'eee8e1d7a3f370e3fcdbf5783f1b03df8672296abcf27726cdaca73c62b71b9c',
                  '30-h008-registry.conf':'e033a07a50b8c5f9f535909e1405c87f99f932a3c1506aa36c30a4647462ac16'}
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def run(*args): return subprocess.check_output(args, text=True, timeout=60).strip()
def inspect(image): return json.loads(run('podman','image','inspect',image))[0]
def tree(root):
    rows=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): rows.append((str(p.relative_to(root)), 'link', os.readlink(p)))
        elif p.is_file(): rows.append((str(p.relative_to(root)), 'file', sha(p)))
    return {'entries':len(rows),'sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()}
def content_identity():
    root=pathlib.Path('/home/user/.local/share/ai-harness')
    rows=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or not p.is_file() or p.name.endswith(('.sqlite','.sqlite-wal','.sqlite-shm','.sqlite-journal')): continue
        rows.append((str(p.relative_to(root)),p.stat().st_size,sha(p)))
    return {'files':len(rows),'sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()}
def credentials():
    result={}
    for n in ['browser-approval-key','inference-key','node-control-key']:
        s=pathlib.Path('/home/user/.config/ai-harness',n).lstat()
        assert stat.S_ISREG(s.st_mode) and s.st_uid==1000 and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1
        result[n]={'dev':s.st_dev,'ino':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns,'mode':stat.S_IMODE(s.st_mode)}
    return result
def artifacts(root):
    assert sha(B/'artifacts.SHA256SUMS')=='622fe7cbf38b9f9adc0bf6467035430bc6f559b821c8d75a978db705cd2f2296'
    for line in (B/'artifacts.SHA256SUMS').read_text().splitlines():
        expected,rel=line.split(None,1); assert sha(root/rel)==expected,rel
    with tarfile.open(B/'server-web-artifacts.tar.gz') as archive:
        for m in archive.getmembers():
            if m.isfile():
                p=root/m.name
                assert p.is_file() and not p.is_symlink() and hashlib.sha256(archive.extractfile(m).read()).hexdigest()==sha(p),m.name
    with tarfile.open(B/'source.tar') as archive:
        for m in archive.getmembers():
            if m.isfile():
                rel=pathlib.PurePosixPath(m.name).relative_to('ai-harness')
                p=root/str(rel)
                assert p.is_file() and not p.is_symlink() and hashlib.sha256(archive.extractfile(m).read()).hexdigest()==sha(p),str(rel)
def main(mode):
    assert inspect(TAG)['Id'].removeprefix('sha256:')==BASE
    if mode=='inputs':
        assert (B/'source.commit').read_text().strip()==SOURCE
        for f,h in [('release/minimax-code-0.5.1.tar.gz','041918b54b6ae9de236de915334d87987a3e29e9d0c800bf4936c512a15fc172'),
                    ('server-web-artifacts.tar.gz','db9c89f3e8b49a72c07b8167a9e109c654ead52f2e646f1cac032036bda5072a'),
                    ('source.tar','9bd1cd1088e2f78d87a63981932db4fc4a7bbcd0d1690b389190ca1cac0f4286')]: assert sha(B/f)==h,f
        base,image=inspect(BASE),inspect(IMAGE)
        layers=base['RootFS']['Layers']; assert len(layers)==30 and image['RootFS']['Layers'][:30]==layers and len(image['RootFS']['Layers'])==31
        labels=image['Labels']; assert labels['org.opencontainers.image.ai-harness.source']==SOURCE
        assert labels['org.opencontainers.image.ai-harness.patchset']=='a6dd7df37313edc4ea2f6bc742ffb6ff431a37abacb2facdbbf422a4c9f9d4bd'
        root=B/'source/ai-harness'; artifacts(root); deps={}
        donor=pathlib.Path('/home/user/ai-harness-build/H013-SOVA-1M-20260927/source/ai-harness')
        for part in ['server','web']:
            for f in ['package.json','package-lock.json']:
                assert (root/part/f).read_bytes()==(donor/part/f).read_bytes()
            deps[part]=tree(root/part/'node_modules'); assert deps[part]==tree(donor/part/'node_modules')
        (P/'private/dependencies.json').write_text(json.dumps(deps))
        for f in ['deploy/run-server.sh','config/system-registry.json','config/frontier.json']:
            assert (root/f).read_bytes()==(OLD/f).read_bytes()
        # Accepted engine launcher changes only the reviewed patchset pin.
        before=(OLD/'deploy/run-engine.sh').read_text()
        assert (root/'deploy/run-engine.sh').read_text()==before.replace('e487935b3d6efce51216b8755cbd712912c30c7d45f6a9e5e293f0f998f89a65','a6dd7df37313edc4ea2f6bc742ffb6ff431a37abacb2facdbbf422a4c9f9d4bd')
        for name,p in UNITS.items():
            assert sha(p)==EXPECTED_UNITS[name]; (P/'private'/name).write_bytes(p.read_bytes())
        (P/'private/content-before.json').write_text(json.dumps(content_identity()))
        (P/'private/credential-metadata-before.json').write_text(json.dumps(credentials()))
        return {'result':'PASS','image':IMAGE,'base':BASE,'base_layers':30,'new_layers':1,'source':SOURCE,'dependencies':deps,'source_archive_and_dist_hashes':'PASS','production_unit_hashes':EXPECTED_UNITS}
    if mode=='staged':
        artifacts(NEW)
        deps=json.loads((P/'private/dependencies.json').read_text())
        for part in ['server','web']: assert tree(NEW/part/'node_modules')==deps[part]
        units={}
        for name,p in UNITS.items():
            assert sha(p)==EXPECTED_UNITS[name]
            old=p.read_text(); assert str(OLD) in old
            proposed=old.replace(str(OLD),str(NEW)); target=P/'proposed'/name
            target.write_text(proposed); assert proposed.replace(str(NEW),str(OLD))==old
            for line in proposed.splitlines():
                if line.startswith('WorkingDirectory='): assert pathlib.Path(line.split('=',1)[1]).is_dir()
                if line.startswith('ExecStart=') and line!='ExecStart=':
                    args=shlex.split(line.split('=',1)[1]); assert pathlib.Path(args[0]).is_file() and os.access(args[0],os.X_OK)
                    for arg in args:
                        if arg.startswith(str(NEW)): assert pathlib.Path(arg).exists()
            units[name]=sha(target)
        return {'result':'PASS','staged_release':str(NEW),'source_archive_dist_dependencies':'PASS','unit_path_only_replacement':True,'unit_hashes':units,'active_config_sha256':sha(NEW/'config/active-frontier.json'),'status_entrypoint_exists':(NEW/'server/dist/status-main.js').is_file(),'qualified':False,'activated':False}
    if mode=='preservation':
        a=json.loads((P/'private/before.json').read_text()); b=json.loads((P/'private/after.json').read_text())
        for k in ['units','containers','states','data','base_image']: assert a[k]==b[k],k
        after=content_identity(); (P/'private/content-after.json').write_text(json.dumps(after))
        assert after==json.loads((P/'private/content-before.json').read_text())
        assert credentials()==json.loads((P/'private/credential-metadata-before.json').read_text())
        for name,p in UNITS.items(): assert sha(p)==EXPECTED_UNITS[name]
        present=subprocess.run(['sudo','-n','test','-e','/etc/ai-harness/mimo-qualification.json'],timeout=10).returncode
        assert present in [0,1], 'privileged qualification metadata check failed'
        return {'result':'PASS','units_containers_queues_data_unchanged':True,'non_database_files':after['files'],'credentials_metadata_unchanged_contents_unread':True,'production_tag':BASE,'activation':False,'qualification_present':present==0}
    raise ValueError('unknown mode')
if __name__=='__main__':
    if '--help' in sys.argv: print(__doc__)
    else: print(json.dumps(main(sys.argv[1]),indent=2))
