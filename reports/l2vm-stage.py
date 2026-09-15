"""One-use ai-vm L2VM procedure, not an installer or migration entrypoint.

Worker supplies frozen PAYLOAD in memory and explicit --apply after preapply review.
Without --apply: read-only exact-current preflight. --help prints this text.
Verification: syntax compile, independent review, dry-run, actual source/stat/binding QA.
No subprocess output containing secret bytes is requested or recorded.
"""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys

if '--help' in sys.argv:
    print(__doc__); raise SystemExit(0)
assert set(sys.argv[1:]) <= {'--apply'}, 'unsupported option'
P = PAYLOAD
assert {'files','manifest','before','guards','proposals','historical_readonly','inverse',
        'coordination_release_sha256','d3b_release_sha256'} <= set(P), 'incomplete frozen payload'
TX = Path('/data/services/llm-manager/adoption/l2vm-existing-host-20260915')
SRC = Path('/usr/local/lib/llm-server/control-api')
INSTANCE = Path('/data/services/llm-manager/deployment-instance.json')
DELTA = {'/data/build':(1000,1001,0o2775), '/data/hf-cache':(1000,1001,0o2775),
         '/data/backups':(1000,1001,0o2775), '/data/logs':(1000,1000,0o2755)}
ENV = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'PYTHONDONTWRITEBYTECODE':'1'}
BINDING = None
def sha(b): return hashlib.sha256(b).hexdigest()
def raw(p):
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME)
    try:
        s=os.fstat(fd); assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
        b=os.read(fd,s.st_size+1); assert len(b)==s.st_size and signature(s)==signature(os.fstat(fd))
        return b
    finally: os.close(fd)
def signature(s):
    return (s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def recorded(p, secret=False):
    s=Path(p).lstat();v={k:getattr(s,'st_'+k) for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns')}
    v['mode']=format(stat.S_IMODE(s.st_mode),'04o')
    if not secret:v['sha256']=sha(raw(p))
    return v
def run(args): return subprocess.check_output(args,text=True,env=ENV,stderr=subprocess.DEVNULL)
def proposal(name): return base64.b64decode(P['proposals'][name])
def mounts():
    rows=json.loads(run(['findmnt','--json','--list','--output','TARGET,SOURCE,UUID,FSTYPE,FSROOT,OPTIONS,MAJ:MIN']))['filesystems']
    for role in ('data','models'):
        e=json.loads(proposal('storage.proposed.json'))[role]
        m=[r for r in rows if r['target']==e['path']]
        assert len(m)==1 and all(m[0][k]==e[v] for k,v in [('source','source'),('uuid','uuid'),('fstype','fstype'),('maj:min','device')])
        assert m[0]['fsroot']=='/' and 'rw' in m[0]['options'].split(',')
        assert [r['target'] for r in rows if r['maj:min']==e['device'] and r['fsroot']=='/']==[e['mount']]
    v=os.statvfs('/'); assert v.f_bavail*v.f_frsize>=4*1024**3, 'root below 4GiB'
def blocks():
    observed=json.loads(run(['lsblk','--json','--bytes','--paths','--output','NAME,PATH,TYPE,PKNAME,MOUNTPOINTS,FSTYPE,UUID,RO,MAJ:MIN']))
    assert observed==P['before']['blocks'], 'block UUID/ancestry/layout drift'
def guard():
    mounts()
    for name,row in P['guards']['guards'].items():
        path=Path(row['path']);assert sha(raw(path))==row['sha256']
        for q in [path,*path.parents]:
            s=q.lstat();assert s.st_uid==0 and not s.st_mode&0o022 and not stat.S_ISLNK(s.st_mode)
        if name=='require-data-mounted.sh':run(['/bin/bash',str(path)])
        else:
            # FD3 avoids the guard's command-substitution stdout/report collision.
            report=run(['/bin/bash','-c','exec 3>&1; /bin/bash "$1" --report /proc/self/fd/3','l2vm',str(path)])
            assert '## Conclusion\n\nPASS' in report and 'PASS: root disk guard passed' in report
    return report.encode()
@contextlib.contextmanager
def directory(path):
    """Retain every no-follow directory FD; refuse changed ancestry before write."""
    path=Path(path);assert path.is_absolute() and '..' not in path.parts
    fds=[os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)]; paths=[Path('/')]
    try:
        for part in path.parts[1:]:
            fds.append(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fds[-1]));paths.append(paths[-1]/part)
        for fd,p in zip(fds,paths):
            s=os.fstat(fd);assert s.st_uid==0 and not s.st_mode&0o022 and (s.st_dev,s.st_ino)==(p.lstat().st_dev,p.lstat().st_ino)
            expected = os.makedev(8,33) if p.is_relative_to('/data/models-large') else os.makedev(8,17) if p.is_relative_to('/data') else P['before']['directories']['/']['dev']
            assert s.st_dev==expected, 'anchored filesystem mismatch'
        mounts()
        yield fds[-1]
        for fd,p in zip(fds,paths):
            s=os.fstat(fd);assert (s.st_dev,s.st_ino)==(p.lstat().st_dev,p.lstat().st_ino)
        mounts()
    finally:
        for fd in reversed(fds): os.close(fd)
def mkdir(path,mode):
    mounts();path=Path(path)
    with directory(path.parent) as fd:
        os.mkdir(path.name,mode,dir_fd=fd)
        child=os.open(path.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        try:os.fchown(child,0,0);os.fchmod(child,mode);os.fsync(child)
        finally:os.close(child)
        os.fsync(fd)
def new(path,b,mode=0o600):
    mounts();path=Path(path)
    if BINDING is not None and path.is_relative_to('/data'):
        assert mode==0o600, 'private transaction files only'
        with BINDING.mounted_guard(storage_io,roles=('data',)) as guard:
            with storage_io.AnchoredRoot('/data',guard) as anchor:
                rel=str(path.relative_to('/data')); assert anchor.stat(rel,missing_ok=True) is None
                with anchor.open(rel,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as stream:
                    stream.write(b);stream.fsync()
                anchor.check()
        assert raw(path)==b
        return
    with directory(path.parent) as fd:
        # Exclusive fixed transaction temp, then atomic no-overwrite hardlink publish.
        tmp='.'+path.name+'.l2vm-new'
        f=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            os.fchown(f,0,0);os.fchmod(f,mode)
            view=memoryview(b)
            while view:view=view[os.write(f,view):]
            os.fsync(f)
        finally:os.close(f)
        os.link(tmp,path.name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
        os.unlink(tmp,dir_fd=fd);os.fsync(fd)
    if 'key' not in path.name:assert raw(path)==b
def container():
    c=json.loads(run(['docker','inspect','llmctl-glm-5.3-32k']))[0]
    return {k:c[k] for k in ('Id','Image','Name','RestartCount','State','Path','Args','Mounts','Config','HostConfig')}
def stopped():
    assert run(['systemctl','show','llm-control.service','--property=ActiveState','--value']).strip()=='inactive'
    assert run(['systemctl','show','llm-control.service','--property=UnitFileState','--value']).strip() in ('','disabled')
    assert not Path('/etc/systemd/system/multi-user.target.wants/llm-control.service').exists()
    sockets=run(['ss','-ltnH'])
    assert not any(':'+str(p) in line for line in sockets.splitlines() for p in (30000,30004))

assert os.geteuid()==0
before_guard=guard(); blocks(); stopped()
for p,(u,g,m) in DELTA.items():
    s=Path(p).lstat();e=P['before']['directories'][p]
    assert stat.S_ISDIR(s.st_mode) and (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_ino,s.st_dev)==(u,g,m,e['ino'],e['dev']), 'metadata drift: '+p
assert 'MainPID=0' in run(['systemctl','show','d3b-glm-cuda-build-20260915.service','--property=MainPID'])
assert run(['systemctl','show','d3b-glm-cuda-build-20260915.service','--property=ActiveState','--value']).strip()=='failed'
for p in ('/etc/local-ai-server',str(SRC),str(TX),'/data/services/installer','/data/services/llm-control','/etc/llm-server/control.json','/etc/systemd/system/llm-control.service','/usr/local/lib/llm-server/control-api.manifest.json'):
    assert not os.path.lexists(p), 'unexpected existing target: '+p
for p,e in P['before']['files'].items():
    if not e.get('absent'):
        assert sha(raw(p))==e['sha256'], 'original changed: '+p
        s=Path(p).lstat()
        assert all(getattr(s,'st_'+k)==e[k] for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns')), 'original metadata changed: '+p
        assert format(stat.S_IMODE(s.st_mode),'04o')==e['mode']
native=Path('/data/services/secrets/llm-api-key');native_stat=signature(native.lstat());native_bytes=raw(native)
e=P['before']['private_metadata_only'][str(native)];s=native.lstat()
assert all(getattr(s,'st_'+k)==e[k] for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns')) and stat.S_IMODE(s.st_mode)==0o600
e=P['before']['private_metadata_only']['/run/llmctl/lifecycle.lock'];s=Path('/run/llmctl/lifecycle.lock').lstat()
assert all(getattr(s,'st_'+k)==e[k] for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns')) and stat.S_IMODE(s.st_mode)==0o600
originals={p:raw(p) for p,e in P['before']['files'].items() if not e.get('absent')}
state_paths=['/data/services/llm-manager/active/active.json','/run/llmctl/recovery.json']
state_stats={p:signature(Path(p).lstat()) for p in state_paths}
old_container=container()
assert old_container['Id']==P['before']['container']['Id'] and old_container['State']['Running']
assert old_container['State']['Pid']==P['before']['container']['State']['Pid']
helper=Path('/usr/local/lib/llm-server/private-network/private_network.py')
assert sha(raw(helper))==P['manifest']['files']['scripts/control/private_network.py']['sha256']
for p in ('/etc/llm-server','/usr/local/lib/llm-server'):
    s=Path(p).lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022
shared_meta={p:signature(Path(p).lstat()) for p in ('/etc/llm-server','/usr/local/lib/llm-server')}
print('PREFLIGHT_PASS exact mounts, originals, metadata, D3B release state, control stopped',flush=True)
if '--apply' not in sys.argv:raise SystemExit(0)
assert P['coordination_release_sha256'] and P['d3b_release_sha256']
if not TX.parent.exists():mkdir(TX.parent,0o700)
mkdir(TX,0o700)
new(TX/'pre-root-guard.md',before_guard)
new(TX/'before.json',(json.dumps(P['before'],sort_keys=True,indent=2)+'\n').encode())
new(TX/'source-manifest.json',(json.dumps(P['manifest'],sort_keys=True,indent=2)+'\n').encode())
new(TX/'inverse.json',(json.dumps(P['inverse'],sort_keys=True,indent=2)+'\n').encode())
mkdir(TX/'originals',0o700)
for n,(p,b) in enumerate(originals.items()):new(TX/'originals'/f'{n:02d}.raw',b)
new(TX/'originals/index.json',(json.dumps({p:f'{n:02d}.raw' for n,p in enumerate(originals)},sort_keys=True,indent=2)+'\n').encode())
mkdir(SRC,0o755)
for relative in sorted(P['files']):
    p=SRC/relative
    for parent in reversed(p.parents):
        if parent.is_relative_to(SRC) and not parent.exists():mkdir(parent,0o755)
    b=base64.b64decode(P['files'][relative]);assert sha(b)==P['manifest']['files'][relative]['sha256']
    new(p,b,int(P['manifest']['files'][relative]['mode'],8))
new(SRC.parent/'control-api.manifest.json',(json.dumps(P['manifest'],sort_keys=True,indent=2)+'\n').encode(),0o644)
sys.path.insert(0,str(SRC/'scripts'))
from common.lifecycle_lease import acquire_lease
from lifecycle.instance_binding import import_historical_instance
from lifecycle.storage_binding import RegisteredStorageBinding
from lifecycle.manager import Manager, StorageRunner
from install import storage_io
from control import installation
with acquire_lease(blocking=False) as lease:
    blocks()
    for p,b in originals.items():
        assert raw(p)==b, 'changed before lease: '+p
        e=P['before']['files'][p];s=Path(p).lstat()
        assert all(getattr(s,'st_'+k)==e[k] for k in ('uid','gid','ino','dev','nlink','size','mtime_ns','ctime_ns'))
    for p,(u,g,m) in DELTA.items():
        mounts();lease.validate()
        with directory('/data') as parent:
            fd=os.open(Path(p).name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            try:
                s=os.fstat(fd);e=P['before']['directories'][p]
                assert (s.st_ino,s.st_dev,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(e['ino'],e['dev'],u,g,m)
                os.fchown(fd,0,g);os.fchmod(fd,0o2755);os.fsync(fd)
            finally:os.close(fd)
    mkdir('/data/services/installer',0o700);mkdir('/data/services/llm-control',0o700)
    lease.validate();mkdir('/etc/local-ai-server',0o700)
    new('/etc/local-ai-server/storage.json',proposal('storage.proposed.json'))
    binding=RegisteredStorageBinding.load(StorageRunner(),roles=('data','models'))
    BINDING=binding
    assert binding.identity==json.loads(proposal('storage-identity.proposed.json'))
    old=json.loads(originals[str(INSTANCE)])
    new(TX/'instance-immediate-preimport.raw',raw(INSTANCE))
    adopted=import_historical_instance(binding,lease=lease,storage_io=storage_io)
    assert adopted==dict(old,storage_identity=binding.identity,historical_import=True)
    # Runtime-free old-container contract comparison uses reviewed JSON in memory only.
    m=Manager(SRC/'configs',adopted,binding=binding)
    state=m.read_state();m.validate_identity(state['container']);c=m.trusted_container(state['container'])
    d=json.loads(base64.b64decode(P['historical_readonly']['configs/deployments/glm-5.3-ud-q4-k-xl-32k.json']))
    d['_runtime']=json.loads(base64.b64decode(P['historical_readonly']['configs/runtimes/llama-cpp-v0.4.1-d1.json']))
    d['_model']=json.loads(raw(SRC/'configs/models/glm-5.3-ud-q4-k-xl.json'))
    m.bind_deployment(d);m.validate_reused_contract(c,d)
    new(TX/'binding-check.json',b'{"historical_import":true,"registered_both_roles":true,"readonly_old_container_contract":"PASS","catalog_compatibility_installed":false}\n')
    lease.validate();new('/etc/llm-server/control.json',proposal('control.proposed.json'))
    key=Path('/etc/llm-server/control-api-key')
    if key.exists():
        installation._key(installation.protected_file(key,modes={0o600},maximum=257,root_device=Path('/').stat().st_dev));key_action='reused'
    else:
        new(key,secrets.token_hex(32).encode(),0o600);key_action='created'
    new(TX/'control-key-action.json',(json.dumps({'action':key_action,'metadata':recorded(key,secret=True),'inverse':'remove only if action=created and exact recorded inode/metadata unchanged; never hash key'},sort_keys=True,indent=2)+'\n').encode())
    installation._key(installation.protected_file(key,modes={0o600},maximum=257,root_device=Path('/').stat().st_dev))
    installation._control_config(Path('/').stat().st_dev)
    new('/etc/systemd/system/llm-control.service',proposal('llm-control.service.proposed'),0o644)
    # No daemon-reload, enable, start, credentials injection, or control GET.
    verify=subprocess.run(['systemd-analyze','verify','/etc/systemd/system/llm-control.service'],env=ENV,capture_output=True,text=True)
    new(TX/'systemd-verify.txt',('exit='+str(verify.returncode)+'\n'+verify.stdout+verify.stderr).encode())
    assert verify.returncode==0, 'systemd verify failed'
    for p in state_paths:assert raw(p)==originals[p] and signature(Path(p).lstat())==state_stats[p]
    assert raw(native)==native_bytes and signature(native.lstat())==native_stat
    assert container()==old_container, 'container contract changed'
    for p in ('/etc/llm-server/network.json',str(helper),'/etc/fstab'):
        assert raw(p)==originals[p]
    for p,(u,g,m0) in DELTA.items():
        s=Path(p).lstat();e=P['before']['directories'][p]
        assert (s.st_ino,s.st_dev,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(e['ino'],e['dev'],0,g,0o2755)
    installed={str(p.relative_to(SRC)) for p in SRC.rglob('*') if p.is_file()}
    assert installed==set(P['manifest']['files'])
    for relative,e in P['manifest']['files'].items():
        p=SRC/relative;s=p.lstat()
        assert sha(installation.protected_file(p,root_device=Path('/').stat().st_dev))==e['sha256']
        assert s.st_gid==0 and stat.S_IMODE(s.st_mode)==int(e['mode'],8)
    binding.verify();stopped()
    registered_report=run(['/usr/bin/python3','-I','-B',str(SRC/'scripts/common/registered-storage.py'),'--root-guard'])
    new(TX/'registered-root-guard.json',registered_report.encode())
    after_guard=guard();new(TX/'post-root-guard.md',after_guard)
    post_paths=[str(INSTANCE),'/etc/local-ai-server/storage.json','/etc/llm-server/control.json','/etc/systemd/system/llm-control.service',str(SRC.parent/'control-api.manifest.json')]
    new(TX/'post-files.json',(json.dumps({p:recorded(p) for p in post_paths},sort_keys=True,indent=2)+'\n').encode())
    new(TX/'stage-result.json',b'{"status":"PASS_STAGED_ONLY","control":"STOPPED_UNENABLED","native_key_exactbytes_unchanged":true,"state_bytes_timestamps_unchanged":true,"container_exact_inspect_contract_unchanged":true,"q38_receipt":"SEPARATE_VALIDATION_PENDING","runtime_auth":"NOT_PUBLISHED"}\n')
print('STAGE_PASS control STOPPED_UNENABLED; state/container/native key unchanged',flush=True)
