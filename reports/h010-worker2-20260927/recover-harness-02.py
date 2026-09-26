#!/usr/bin/env python3
"""H010 ordinary app recovery; state functions reused from native01 quiet helper."""
import os, stat, json, sqlite3, hashlib, pathlib, subprocess, urllib.request, datetime
os.umask(0o077)
ROOT=pathlib.Path('/home/user/.local/share/ai-harness')
TASK=pathlib.Path('/home/user/ai-harness-build/H010-WORKER2-20260927')
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
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inspect',action='store_true');p.add_argument('--recover',action='store_true');p.add_argument('--release-note');a=p.parse_args()
 assert a.inspect != a.recover,'choose inspect or recover'
 assert os.getuid()==1000
 baseline=json.loads((TASK/'HARNESS-QUIET-01.json').read_text())
 def check_metadata():
  out={}
  for name,digest in baseline['release_metadata_sha256'].items():
   out[name]=sha(pathlib.Path(name).read_bytes());assert out[name]==digest,'installed metadata changed'
  for name,expected in baseline['credentials_metadata'].items():
   f=pathlib.Path('/home/user/.config/ai-harness')/name;s=f.lstat()
   for parent in f.parents:
    st=parent.lstat();assert stat.S_ISDIR(st.st_mode) and st.st_uid in (0,1000) and not st.st_mode&0o022
   current={'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'size':s.st_size,'nlink':s.st_nlink,'protected_ancestry':True,'contents_read':False}
   assert stat.S_ISREG(s.st_mode) and current==expected,'protected credential metadata changed'
  image=json.loads(run('/usr/bin/podman','--remote=false','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9'))[0]
  assert image['Id'].removeprefix('sha256:')==baseline['native_image_id'].removeprefix('sha256:')
  assert os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize>20*1024**3
  return {'release_metadata_sha256':out,'credentials_metadata':baseline['credentials_metadata'],'native_image_id':image['Id']}
 before=summary();require_idle(before)
 before=json.loads(json.dumps(before));u=units();assert u['ai-harness.service']['ActiveState']=='inactive' and u['ai-harness.service']['MainPID']=='0'
 metadata=check_metadata()
 protected=['sessions','messages','files','runs','events','quarantined_workspaces','h003_image_jobs','h005_image_ownership','frontier_requests']
 assert all(before[t]==baseline['before_data'][t] for t in protected),'history changed; review without restore'
 assert all(u[n]==baseline['after_units'][n] for n in ['ai-harness-searxng.service','ai-harness-status.service','ai-harness-admin.service'])
 r={'utc':now(),'pid':os.getpid(),'mode':'inspect' if a.inspect else 'recover','before_units':u,'before_data':before,'metadata':metadata,'atomic_drain_claim':False,'no_old_database_restore':True,'manual_image_clear':False}
 if a.inspect:
  (TASK/'OWNERS-BEFORE-SMOKE-02.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':'PASS_APP_INACTIVE_OWNERS_TERMINAL','utc':r['utc'],'pid':r['pid']}));return
 assert a.release_note,'actual root Worker1 settled release note required'
 note=pathlib.Path(a.release_note);assert note.is_file();r['release_note']={'path':str(note),'sha256':sha(note.read_bytes())}
 smoke=TASK/'overlap-02/SMOKE-02.json'
 if smoke.exists():
  sm=json.loads(smoke.read_text());assert sm.get('allOwnedRequestsSettled') is True,'owned smoke settlement unproven; coordinate, never clear'
  r['smoke_receipt_sha256']=sha(smoke.read_bytes())
 files=inventory();assert files['regular_non_database_files']==baseline['after_files']['included_regular_files'] and files['sha256']==baseline['after_files']['sha256']
 r['before_files']=files;r['start_command_utc']=now();r['status']='RECOVERY_STARTED'
 receipt=TASK/'RECOVERY-02.json';assert not receipt.exists(),'preserve previous recovery evidence'
 receipt.write_text(json.dumps(r,indent=2)+'\n')
 subprocess.run(['systemctl','--user','start','ai-harness.service'],check=True,timeout=90)
 r['start_returned_utc']=now()
 import time
 for _ in range(20):
  try:
   r['health_http'],r['health']=http('/api/health');r['status_http'],_=http('/status');r['canonical_status_http'],_=http('/api/status/v1/system');break
  except Exception:time.sleep(1)
 try:
  r['after_units']=units();r['after_data']=json.loads(json.dumps(summary()));r['after_files']=inventory();r['after_metadata']=check_metadata()
  r['history_preserved']={t:r['after_data'][t]==baseline['before_data'][t] for t in protected}
  r['regular_files_preserved']=r['after_files']['regular_non_database_files']==files['regular_non_database_files'] and r['after_files']['sha256']==files['sha256']
  r['other_services_unchanged']=all(r['after_units'][n]==u[n] for n in ['ai-harness-searxng.service','ai-harness-status.service','ai-harness-admin.service'])
  r['after_containers']=container_summary()
  config=json.loads((REL/'config/frontier.json').read_text());r['frontier_config']={k:config.get(k) for k in ['model','qualified','contextWindow','maxOutputTokens','tokenizerRevision','templateRevision']}
  assert r['health_http']==r['status_http']==r['canonical_status_http']==200
  assert r['after_units']['ai-harness.service']['ActiveState']=='active' and r['after_units']['ai-harness.service']['UnitFileState']=='enabled'
  assert r['other_services_unchanged'] and all(r['history_preserved'].values()) and r['regular_files_preserved']
  assert config['qualified'] and config['contextWindow']==480000 and config['maxOutputTokens']==65536
  assert r['after_data']['h003_image_lane']['states']==[['idle',1]] and r['after_data']['h005_image_ownership']['states']==[[0,1]]
  require_idle(summary());r['status']='PASS_AWAITING_CANONICAL_AVAILABILITY'
 except Exception:
  r['status']='FAIL_REVIEW_PRESERVED_EVIDENCE';raise
 finally:
  r['finished_utc']=now();receipt.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'receipt':str(receipt),'utc':r['finished_utc']}))
if __name__=='__main__':main()
