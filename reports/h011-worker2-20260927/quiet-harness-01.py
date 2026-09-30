import os, stat, json, sqlite3, hashlib, pathlib, subprocess, urllib.request, datetime
os.umask(0o077)
ROOT=pathlib.Path('/home/user/.local/share/ai-harness')
TASK=pathlib.Path('/home/user/ai-harness-build/H011-WORKER2-20260927')
REL=pathlib.Path('/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness')
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def serialized(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def run(*a): return subprocess.check_output(a,text=True,timeout=30).strip()
def unit(name,user=False):
 a=['systemctl']+(['--user'] if user else [])+['show',name,'-p','Id','-p','MainPID','-p','ActiveState','-p','SubState','-p','UnitFileState','-p','WorkingDirectory']
 return dict(x.split('=',1) for x in run(*a).splitlines())
def units():return {n:unit(n,u) for n,u in [('ai-harness.service',True),('ai-harness-searxng.service',True),('ai-harness-status.service',False),('ai-harness-admin.service',False)]}
def containers():return json.loads(run('/usr/bin/podman','--remote=false','ps','--format','json'))
def container_summary():return [{'id':x['Id'],'image':x['Image'],'names':x['Names'],'state':x['State']} for x in containers()]
def db():return sqlite3.connect('file:'+str(ROOT/'harness.sqlite')+'?mode=ro',uri=True)
def summary():
 c=db();c.execute('BEGIN'); out={}
 for t in ['sessions','messages','files','runs','events','quarantined_workspaces','h003_image_jobs','h003_image_lane','h005_image_ownership','gateway_lanes','frontier_requests']:
  rows=c.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall();out[t]={'count':len(rows),'sha256':sha(serialized(rows))}
 for t,k in [('runs','status'),('sessions','status'),('frontier_requests','state'),('h003_image_jobs',"json_extract(data,'$.job.state')"),('gateway_lanes','state'),('h003_image_lane','state'),('h005_image_ownership','uncertain')]:
  out[t]['states']=c.execute('SELECT '+k+',count(*) FROM '+t+' GROUP BY '+k).fetchall()
 c.close();return out

def require_idle(s):
 assert all(x[0] in ['completed','cancelled','interrupted','failed'] for x in s['runs']['states']), 'active run'
 assert all(x[0] in ['idle','interrupted','error'] for x in s['sessions']['states']), 'active session'
 assert all(x[0] in ['completed','cancelled','failed','rejected'] for x in s['frontier_requests']['states']), 'active/uncertain Flash request'
 assert all(x[0] in ['completed','cancelled','failed'] for x in s['h003_image_jobs']['states']), 'active image job'
 assert s['h003_image_lane']['states']==[('idle',1)],'image lane not idle'
 assert s['h005_image_ownership']['states']==[(0,1)],'image uncertain'
 assert s['gateway_lanes']['states']==[('idle',3)],'text lane not idle'
 assert all(x['names']==['ai-harness-searxng'] for x in container_summary()),'native container running'
def inventory():
 rows=[];excluded=0
 for p in sorted(ROOT.rglob('*')):
  if p.is_symlink() or not p.is_file():continue
  if p.name.endswith(('.sqlite','.sqlite-wal','.sqlite-shm','.sqlite-journal')):excluded+=1;continue
  rows.append((str(p.relative_to(ROOT)),p.stat().st_size,sha(p.read_bytes())))
 return {'regular_non_database_files':len(rows),'sha256':sha(serialized(rows)),'excluded_database_and_transient_files':excluded}
def http(path):
 with urllib.request.urlopen('http://10.156.100.61'+path,timeout=15) as r:return r.status,json.load(r)
before=summary();require_idle(before)
initial_units=units(); initial_containers=container_summary()
assert initial_units['ai-harness.service']['ActiveState']=='active' and initial_units['ai-harness.service']['MainPID']!='0'
health_code,health=http('/api/health');status_code,status=http('/api/status/v1/system')
services=[]
def walk(x):
 if isinstance(x,dict):
  if 'service_id' in x or ('id' in x and 'current_state' in x):services.append({k:v for k,v in x.items() if k in ['id','service_id','state','current_state','health','ready','availability','configured_context_tokens','max_output_tokens','activity','active_requests','queue_depth','freshness','admitting','model_alias']})
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(status)
credentials={}
for p in sorted(pathlib.Path('/home/user/.config/ai-harness').iterdir()):
 s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==1000 and s.st_nlink==1 and not s.st_mode&0o077
 for q in p.parents:
  t=q.lstat();assert stat.S_ISDIR(t.st_mode) and t.st_uid in (0,1000) and not t.st_mode&0o022
 credentials[p.name]={'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'size':s.st_size,'nlink':s.st_nlink,'protected_ancestry':True,'contents_read':False}
config=json.loads((REL/'config/frontier.json').read_text());assert config['qualified'] and config['contextWindow']==480000 and config['maxOutputTokens']==65536
image=json.loads(run('/usr/bin/podman','--remote=false','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9'))[0]
assert image['Id'].removeprefix('sha256:')=='c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20'
assert os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize>20*1024**3
TASK.mkdir(mode=0o700,exist_ok=True)
assert TASK.resolve()==TASK and TASK.stat().st_uid==1000 and not TASK.stat().st_mode&0o077
snapshot=TASK/'harness-before-stop-01.sqlite';assert not snapshot.exists()
src=db();dst=sqlite3.connect(snapshot);src.backup(dst);assert dst.execute('pragma integrity_check').fetchall()==[('ok',)];dst.close();src.close()
files_before=inventory()
fresh=summary();require_idle(fresh);assert before==fresh,'data changed during snapshot'
receipt={'schema_version':1,'before_utc':now(),'production_release':str(REL),'native_image_id':image['Id'],'frontier_config':{k:config.get(k) for k in ['model','qualified','contextWindow','maxOutputTokens','tokenizerRevision','templateRevision']},'credentials_metadata':credentials,'before_units':initial_units,'before_containers':initial_containers,'before_data':before,'before_files':files_before,'health_http':health_code,'health':health,'canonical_status_http':status_code,'canonical_services':services,'snapshot':{'path':str(snapshot),'sha256':sha(snapshot.read_bytes()),'integrity':'ok','method':'SQLite backup API','mode':oct(stat.S_IMODE(snapshot.stat().st_mode))},'atomic_drain_claim':False,'stop_reason':'H011 user/root authorized idle app-only quiet benchmark window','restore_command':'systemctl --user start ai-harness.service','restore_authority':'ordinary start after explicit actual Worker1 settled handback within session deadline'}
receipt['release_metadata_sha256']={'/home/user/.config/systemd/user/ai-harness.service': '7e339dc3e44e566f5eb8c5206cf37b7123047502564465fda6afaea5a0321b57', '/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness/config/frontier.json': '5c10ef1e1eae12ac297b7eabd07ba8023d799b25edc01626162a26e9c18f2261', '/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness/deploy/run-engine.sh': 'f3385648fdb2fd41efca41509b6c2a11ad5b6098fa5ad761e98dd5b2f2d5c722', '/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness/deploy/run-server.sh': '1e70596f578db2c5af5dd5400575f9a47607f9a16e2f820d44175169cb19309f'}
for name,digest in receipt['release_metadata_sha256'].items():assert sha(pathlib.Path(name).read_bytes())==digest,'release metadata changed'
receipt['pid']=os.getpid()
(TASK/'before-01.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Recheck ownership directly before the existing service stop. This is not an atomic drain.
last=summary();require_idle(last);assert last==before
receipt['immediate_owner_check_utc']=now()
(TASK/'before-01.json').write_text(json.dumps(receipt,indent=2)+'\n')
subprocess.run(['systemctl','--user','stop','ai-harness.service'],check=True,timeout=100)
receipt['stopped_utc']=now();receipt['after_units']=units();receipt['after_containers']=container_summary();receipt['after_data']=summary();receipt['after_files']=inventory()
assert receipt['after_units']['ai-harness.service']['MainPID']=='0' and receipt['after_units']['ai-harness.service']['ActiveState']=='inactive'
for n in ['ai-harness-searxng.service','ai-harness-status.service','ai-harness-admin.service']:
 assert receipt['after_units'][n]==initial_units[n],n+' changed'
assert receipt['after_units']['ai-harness.service']['UnitFileState']==initial_units['ai-harness.service']['UnitFileState']=='enabled'
assert all(x['names']==['ai-harness-searxng'] for x in receipt['after_containers'])
for t in before:
 if t not in ['gateway_lanes','h003_image_lane']:assert before[t]==receipt['after_data'][t],t+' changed'
assert all(files_before[k]==receipt['after_files'][k] for k in ['regular_non_database_files','sha256'])
receipt['status']='QUIET_APP_STOPPED_SEARCH_STATUS_ADMIN_PRESERVED';receipt['after_status_http']=http('/api/status/v1/system')[0];receipt['after_storage_free_bytes']=os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize
receipt['changed_tables']=[t for t in before if before[t]!=receipt['after_data'][t]]
(TASK/'HARNESS-QUIET-01.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['status','pid','stopped_utc','changed_tables']}))
