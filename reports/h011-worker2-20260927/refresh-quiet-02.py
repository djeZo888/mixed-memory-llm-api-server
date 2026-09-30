#!/usr/bin/env python3
"""H010 ordinary app recovery; state functions reused from native01 quiet helper."""
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
 assert s['h003_image_lane']['states'] in [[('idle',1)],[('quarantined',1)]],'unexpected image lane'
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
 with urllib.request.urlopen('http://10.156.100.61'+path,timeout=15) as r:
  body=r.read()
  return r.status,json.loads(body) if r.headers.get_content_type()=='application/json' else {'body_bytes':len(body)}

def main():
 baseline=json.loads((TASK/'HARNESS-QUIET-01.json').read_text())
 r={'utc':now(),'pid':os.getpid(),'scope':'READ_ONLY_APP_QUIET_PRESERVATION_NOT_NATIVE_DRAIN','no_service_action':True,'inference':False,'ai_vm_contact':False,'native_backend_settlement':'Worker1-owned, not established by this receipt'}
 r['units']=units();r['containers']=container_summary();current=summary();require_idle(current)
 r['data']=json.loads(json.dumps(current));r['files']=inventory()
 assert r['units']['ai-harness.service']['ActiveState']=='inactive' and r['units']['ai-harness.service']['MainPID']=='0' and r['units']['ai-harness.service']['UnitFileState']=='enabled'
 protected_tables=['sessions','messages','files','runs','events','quarantined_workspaces','h003_image_jobs','h005_image_ownership','frontier_requests']
 r['history_preserved']={t:r['data'][t]==baseline['before_data'][t] for t in protected_tables}
 r['regular_files_preserved']=all(r['files'][k]==baseline['before_files'][k] for k in ['regular_non_database_files','sha256'])
 r['other_services_unchanged']=all(r['units'][n]==baseline['after_units'][n] for n in ['ai-harness-searxng.service','ai-harness-status.service','ai-harness-admin.service'])
 r['release_metadata_sha256']={name:sha(pathlib.Path(name).read_bytes()) for name in baseline['release_metadata_sha256']}
 assert r['release_metadata_sha256']==baseline['release_metadata_sha256']
 credentials={}
 for name,expected in baseline['credentials_metadata'].items():
  p=pathlib.Path('/home/user/.config/ai-harness')/name;s=p.lstat()
  for parent in p.parents:
   st=parent.lstat();assert stat.S_ISDIR(st.st_mode) and st.st_uid in (0,1000) and not st.st_mode&0o022
  assert stat.S_ISREG(s.st_mode)
  credentials[name]={'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'size':s.st_size,'nlink':s.st_nlink,'protected_ancestry':True,'contents_read':False}
  assert credentials[name]==expected
 r['credentials_metadata']=credentials
 r['canonical_status_http'],status=http('/api/status/v1/system')
 services=[]
 def walk(x):
  if isinstance(x,dict):
   if 'service_id' in x:services.append({k:v for k,v in x.items() if k in ['service_id','model_alias','state','ready','availability','freshness','configured_context_tokens','max_output_tokens','activity','active_requests','queue_depth','admitting']})
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(status);r['canonical_services']=services
 r['status_http'],_=http('/status')
 r['frontier_config']={k:json.loads((REL/'config/frontier.json').read_text()).get(k) for k in ['model','qualified','contextWindow','maxOutputTokens','tokenizerRevision','templateRevision']}
 assert all(r['history_preserved'].values()) and r['regular_files_preserved'] and r['other_services_unchanged']
 assert r['canonical_status_http']==r['status_http']==200
 r['status']='PASS_APP_REMAINS_PAUSED_DATA_PRESERVED'
 path=TASK/'HARNESS-QUIET-REFRESH-02.json';assert not path.exists()
 path.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'utc':r['utc'],'pid':r['pid'],'app_pid':r['units']['ai-harness.service']['MainPID']}))
if __name__=='__main__':main()
