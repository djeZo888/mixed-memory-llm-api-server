#!/usr/bin/env python3
"""H016 read-only ai-harness build/quiet guard. Usage: guard.py [--help]."""
import datetime, hashlib, json, os, pathlib, sqlite3, stat, subprocess, sys
if '--help' in sys.argv: print(__doc__); sys.exit(0)
def run(*args): return subprocess.check_output(args,text=True,timeout=30).strip()
def safe(p,parents=True):
 p=pathlib.Path(p)
 for x in ([p,*p.parents] if parents else [p]):
  s=x.lstat(); assert stat.S_ISDIR(s.st_mode) and s.st_uid in (0,1000) and not s.st_mode&0o022 and x.resolve()==x,str(x)
root=pathlib.Path('/home/user/ai-harness-build')
rel=pathlib.Path('/opt/ai-harness/releases/7143c17d73173db9364b77956679c86d7026a4ae/ai-harness')
assert os.getuid()==1000
safe(root);safe(rel);safe('/home/user/.local/share/containers/storage',False)
assert run('podman','info','--format','{{.Host.Security.Rootless}}')=='true'
assert run('podman','info','--format','{{.Store.GraphRoot}}')=='/home/user/.local/share/containers/storage'
free=os.statvfs(root).f_bavail*os.statvfs(root).f_frsize;assert free>21474836480
base='9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c'
assert run('podman','image','inspect',base,'--format','{{.Id}}')==base
units={}
for n,user in [('ai-harness.service',True),('ai-harness-searxng.service',True),('ai-harness-status.service',False),('ai-harness-admin.service',False)]:
 units[n]=dict(x.split('=',1) for x in run('systemctl',*(['--user'] if user else []),'show',n,'-p','ActiveState','-p','MainPID','-p','WorkingDirectory').splitlines())
assert units['ai-harness.service']['ActiveState']=='inactive' and units['ai-harness.service']['MainPID']=='0'
cs=json.loads(run('podman','ps','--format','json'));assert all(x['Names']==['ai-harness-searxng'] for x in cs),'owned engine/build container still running'
c=sqlite3.connect('file:/home/user/.local/share/ai-harness/harness.sqlite?mode=ro',uri=True);c.execute('BEGIN');states={};data={}
for table,col,allowed in [('runs','status',['completed','cancelled','interrupted','failed']),('sessions','status',['idle','interrupted','error']),('frontier_requests','state',['completed','cancelled','failed','rejected']),('gateway_lanes','state',['idle']),('h005_image_ownership','uncertain',[0])]:
 states[table]=c.execute('SELECT '+col+',count(*) FROM '+table+' GROUP BY '+col).fetchall();assert all(x[0] in allowed for x in states[table]),table
for table in ['sessions','messages','files','gateway_lanes','frontier_requests']:
 rows=c.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall();data[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()}
c.close()
print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base_image':base,'units':units,'containers':[{'id':x['Id'],'image':x['Image'],'names':x['Names']} for x in cs],'states':states,'data':data,'free_bytes':free,'guard':'current harness protected build/release paths; canonical rootless graphroot; >20GiB; paused idle app'},indent=2))
