# Reused HOSTRECOVER operations, task-pinned; overrides follow in finalops-boot.py.
import os, sys, stat, json, hashlib, subprocess, datetime, time, fcntl
from pathlib import Path
SRC=Path('/usr/local/lib/llm-server/control-api')
REPORT=Path('/data/logs/finalops-20260917')
TARGET='qwen38-27b-1000000-yarn4-tp2-bf16kv'
CID=None
IMAGE=None
def emit(phase, **kw):
    print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'phase':phase,**kw},sort_keys=True),flush=True)
def run(args,timeout=60):
    return subprocess.check_output(args,stderr=subprocess.DEVNULL,text=True,timeout=timeout)
def protected(path):
    p=Path(path)
    for a in (p,*p.parents):
        st=a.lstat(); assert not a.is_symlink() and st.st_uid==0 and not st.st_mode&0o022, 'unprotected_path'
    return p
def guard_identity():
    for row in (CFG['registered_host']['guard'],CFG['registered_host']['dependency']):
        p=protected(row['path']); st=p.stat()
        assert st.st_nlink==1 and stat.S_IMODE(st.st_mode)==int(row['expected_mode'],8), 'guard_metadata'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],'guard_hash'
    protected('/etc/local-ai-server/storage.json')
def guard():
    guard_identity()
    return json.loads(run(['/usr/bin/python3','-I','-B',CFG['registered_host']['guard']['path'],'--root-guard','--json']))
def bind():
    sys.path.insert(0,str(SRC/'scripts'))
    from lifecycle.storage_binding import RegisteredStorageBinding
    from lifecycle.manager import StorageRunner
    return RegisteredStorageBinding.load(StorageRunner())
from contextlib import contextmanager
@contextmanager
def writer(binding):
    from install import storage_io
    with binding.mounted_guard(storage_io) as mounted:
        with storage_io.AnchoredRoot('/data/logs',mounted) as anchor:
            yield anchor
def quiet():
    rows=run(['ss','-tnH','state','established']).splitlines()
    assert not [x for x in rows if any(':'+str(p) in x for p in (30000,30002,30004))], 'api_connections_present'
def manager():
    b=bind()
    from lifecycle.manager import Manager
    return Manager(SRC/'configs',b.read_json('data',b.path('data','services/llm-manager/deployment-instance.json')),binding=b)
def preservation():
    names=['/etc/local-ai-server/storage.json','/etc/llm-server/control.json','/etc/llm-server/network.json','/data/services/llm-manager/deployment-instance.json','/usr/local/lib/llm-server/control-api.manifest.json','/data/services/secrets/llm-api-key','/etc/llm-server/control-api-key']
    data={}
    for n in names:
        p=protected(n);data[n]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'metadata':snap(p.stat())}
    manifest=json.loads(protected('/usr/local/lib/llm-server/control-api.manifest.json').read_bytes())
    for n,r in manifest['files'].items():
        p=protected(SRC/n);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],'installed_source_hash_mismatch'
        assert stat.S_IMODE(p.stat().st_mode)==int(r['mode'],8),'installed_source_mode_mismatch'
    return {'files':data,'installed_source_files':len(manifest['files']),'source_commit':manifest['source_commit']}
def cinfo(cid=CID):
    fmt='{"Id":{{json .Id}},"Image":{{json .Image}},"State":{{json .State}},"RestartPolicy":{{json .HostConfig.RestartPolicy}},"Ports":{{json .NetworkSettings.Ports}}}'
    return json.loads(run(['docker','inspect','--format',fmt,cid],10))
def snap(st):
    return {k:getattr(st,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns','blocks')}
def nonuse(paths):
    ids={(Path(p).stat().st_dev,Path(p).stat().st_ino) for p in paths}
    opened=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid(): continue
        try:
            for f in (proc/'fd').iterdir():
                try:
                    s=f.stat()
                    if (s.st_dev,s.st_ino) in ids: opened.append((proc.name,f.name))
                except FileNotFoundError: pass
            for line in (proc/'maps').read_text().splitlines():
                fields=line.split(None,5)
                if len(fields)>5 and fields[5] in paths: opened.append((proc.name,'mmap'))
        except (FileNotFoundError,ProcessLookupError): pass
    assert not opened,'candidate_in_use'
def no_package_writer():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            comm=(proc/'comm').read_text().strip()
            if comm.startswith(('apt','dpkg')): raise AssertionError('package_writer_present')
            if comm.startswith('unattended'):
                args=(proc/'cmdline').read_bytes().split(b'\0')
                assert b'/usr/share/unattended-upgrades/unattended-upgrade-shutdown' in args, 'unattended_writer_present'
        except (FileNotFoundError,ProcessLookupError): pass
def expected(row):
    p=Path(row['path'])
    if str(p).startswith('/var/log/journal/'):
        # Ubuntu /var/log is root:syslog 0775. It is outside registered storage;
        # pin its observed identity and anchor the exact authorized journal path.
        for a in (p,*p.parents):
            st=a.lstat(); assert not a.is_symlink() and st.st_uid==0,'journal_source_ancestry'
            if str(a)=='/var/log':
                assert (st.st_ino,st.st_gid,stat.S_IMODE(st.st_mode))==(263743,104,0o775),'journal_log_parent_changed'
            else: assert not st.st_mode&0o022,'journal_source_writable'
    else: protected(p)
    s=p.stat()
    assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_ino==row['inode'] and s.st_uid==row['uid'] and stat.S_IMODE(s.st_mode)==int(row['mode'],8) and s.st_size==row['bytes'] and s.st_blocks*512==row['allocated_bytes'],'candidate_identity_changed'
    if 'mtime_utc' in row: assert abs(s.st_mtime-datetime.datetime.fromisoformat(row['mtime_utc']).timestamp())<.000002,'candidate_mtime_changed'
    return snap(s)
