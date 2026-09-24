"""Bounded activation helpers; never invoke upstream APIs or print user content."""
import datetime, hashlib, json, os, pathlib, sqlite3, stat, subprocess, time, urllib.request

TASK = pathlib.Path('/home/user/.local/share/ai-harness-deploy/H003-HARNESS-ENGINE-ACTIVATE-20260923')
DATA = pathlib.Path('/home/user/.local/share/ai-harness')
OLD_HEAD = 'b5717d03416252c8640c47d37baf892a0c4e532a'
HEAD = '9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27'
RELEASES = pathlib.Path('/home/user/.local/share/ai-harness-app/releases')
OLD = RELEASES / OLD_HEAD
NEW = RELEASES / HEAD
UNIT = pathlib.Path('/home/user/.config/systemd/user/ai-harness.service')
CONFIG = pathlib.Path('/home/user/.config/ai-harness')
TAG = 'localhost/ai-harness-engine:0.0.2-ae65651df5f9'
CANDIDATE_TAG = 'localhost/ai-harness-engine:h003-worker-mcp-20260923'
OLD_ID = '31b7a4d0aba256266e55a4aa510b0b7af484bef3502e9ffa2b333cf6c48b1428'
IMAGE_ID = '11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87'
DIGEST = 'sha256:d60f138286d755fb9857f08f0f981c88084e8a82f763abe354f8c421f2102d64'
PATCHSET = '69d7fe14ed8b1e394fe7315e04724e3ef89c2efbd21118a42fa1842f5ed48eff'
NATIVE = '3df245464c0d58eab6e71d808e6741b11472f459'
BASE = 'ae65651df5f97ae1085ab4e19964f4b78c769a4e'
RECEIPT_SHA = '5b6407f96dd779b29a3f103facda67441231184f603b3c4058834bb7cb9308b1'
os.umask(0o077)

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def run(args, timeout=45): return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()
def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()
def hash_json(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()
def write(path, value): pathlib.Path(path).write_text(json.dumps(value, indent=2)+'\n')
def guard():
    s=os.statvfs(TASK); free=s.f_bavail*s.f_frsize
    assert os.getuid()==1000 and TASK.resolve()==TASK and free>20*1024**3, 'host storage/identity gate failed'
    return {'path':str(TASK), 'freeBytes':free, 'minimumBytes':20*1024**3}
def service(system=False):
    args=['systemctl']+([] if system else ['--user'])+['show','nginx.service' if system else 'ai-harness.service']
    for k in ['MainPID','ActiveState','SubState','NRestarts','ExecMainStartTimestamp','ExecMainStartTimestampMonotonic','ExecMainExitTimestamp','ExecMainCode','ExecMainStatus','Result']:
        args += ['-p', k]
    return dict(line.split('=',1) for line in run(args).splitlines())
def image(ref):
    v=json.loads(run(['podman','image','inspect',ref]))[0]
    return {k:v.get(k) for k in ['Id','Digest','RepoTags','RepoDigests','Created','Labels']}
def candidate():
    v=image(CANDIDATE_TAG)
    assert v['Id']==IMAGE_ID and v['Digest']==DIGEST
    assert v['Labels']['org.opencontainers.image.ai-harness.patchset']==PATCHSET
    assert v['Labels']['org.opencontainers.image.revision']==BASE
    return v
def health():
    with urllib.request.urlopen('http://10.156.100.61/api/health',timeout=5) as r:
        return {'httpStatus':r.status,'body':json.load(r),'url':'http://10.156.100.61/api/health'}
def db_open():
    d=sqlite3.connect(f'file:{DATA}/harness.sqlite?mode=ro',uri=True,timeout=5)
    d.row_factory=sqlite3.Row
    return d
def state():
    with db_open() as d:
        d.execute('BEGIN')
        tables=sorted(r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        counts={}; hashes={}
        for t in tables:
            assert t.replace('_','').isalnum()
            rows=[list(r) for r in d.execute('SELECT * FROM "'+t+'"')]
            counts[t]=len(rows); hashes[t]=hash_json(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True)))
        sessions=[dict(r) for r in d.execute('SELECT id,workspace_id,native_session_id,deleted,status FROM sessions ORDER BY id')]
        jobs=[{'id':r['id'],'sessionId':r['session_id'],'state':json.loads(r['data'])['job']['state']} for r in d.execute('SELECT id,session_id,data FROM h003_image_jobs ORDER BY id')]
        result={'atUtc':utc(),'counts':counts,'tableContentSha256':hashes,'sessions':sessions,
          'visibleChats':sum(not s['deleted'] for s in sessions),'imageJobs':jobs,
          'activeRuns':[dict(r) for r in d.execute("SELECT id,session_id,status FROM runs WHERE status NOT IN ('completed','cancelled','failed','interrupted')")],
          'nonIdleSessions':[dict(r) for r in d.execute("SELECT id,status FROM sessions WHERE status NOT IN ('idle','interrupted','failed') OR (deleted=0 AND delete_requested!=0)")],
          'textLanes':[dict(r) for r in d.execute('SELECT alias,state FROM gateway_lanes ORDER BY alias')],
          'imageLane':[dict(r) for r in d.execute('SELECT id,state FROM h003_image_lane')]}
    for name in ['profiles','workspaces','uploads','artifacts','image-jobs']:
        result[name+'DirectoryIds']=sorted(p.name for p in (DATA/name).iterdir() if p.is_dir())
    return result
def idle():
    s=state()
    assert not s['activeRuns'] and not s['nonIdleSessions'], 'user work active; wait, never stop it'
    assert all(x['state']=='idle' for x in s['textLanes']), 'text lane busy'
    assert all(x['state'] in ['completed','failed','cancelled','interrupted'] for x in s['imageJobs']), 'image job unfinished'
    # ImageAPI is intentionally stopped; image-lane quarantine is not a fault.
    return s
def snapshot_db(dest):
    with db_open() as src, sqlite3.connect(dest) as dst:
        deadline=time.monotonic()+20
        def progress(*args):
            if time.monotonic()>deadline: raise TimeoutError('SQLite backup deadline')
        src.backup(dst,pages=256,progress=progress,sleep=.05)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    return {'path':str(dest),'sha256':sha(dest),'integrity':'ok','method':'SQLite backup API'}
def tree(path):
    path=pathlib.Path(path); entries={}
    for base,dirs,files in os.walk(path,followlinks=False):
        for name in sorted(dirs+files):
            p=pathlib.Path(base)/name; s=p.lstat(); row={'mode':stat.S_IMODE(s.st_mode)}
            if p.is_symlink(): row.update(type='symlink',target=os.readlink(p))
            elif p.is_dir(): row.update(type='directory')
            elif p.is_file(): row.update(type='file',size=s.st_size,sha256=sha(p))
            else: row.update(type='special',kind=stat.S_IFMT(s.st_mode))
            entries[str(p.relative_to(path))]=row
    return entries
def verify_source(root,manifest):
    for name, expected in manifest['files'].items():
        p=root/name
        assert p.is_file() and not p.is_symlink() and sha(p)==expected['sha256'], 'source mismatch: '+name
        actual=stat.S_IMODE(p.stat().st_mode)
        assert actual & 0o700 == expected['mode'] & 0o700 and not actual & ~expected['mode'], 'source mode mismatch: '+name
def key_metadata():
    result=[]
    for name in ['inference-key','browser-approval-key']:
        p=CONFIG/name;s=p.lstat()
        assert stat.S_ISREG(s.st_mode) and s.st_uid==1000 and stat.S_IMODE(s.st_mode) in [0o400,0o600]
        result.append({'path':str(p),'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'size':s.st_size,'mtimeNs':s.st_mtime_ns,'ctimeNs':s.st_ctime_ns})
    return result
def copy(source,dest): run(['cp','-a','--reflink=auto',str(source),str(dest)],timeout=60)
