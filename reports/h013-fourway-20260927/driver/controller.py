#!/usr/bin/env python3
"""One bounded WARM02 -> conditional main dispatch. Plain Mac process, no retries.
Requires exact root GO for this controller and the frozen existing driver.
Exclusive intent is never removed or resumed. No inference without --run.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, subprocess, sys, time
HERE=Path(__file__).resolve().parent
TASK=HERE.parents[3]
PACKAGE='ff31aca7a201b29226a844c0047545f8fe79aa240b7ad915802dcf59c1bcebee'
WARM='H013-WARM02';MAIN='H013-FOURWAY01'
NOW=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda raw:hashlib.sha256(raw).hexdigest()
READ=r'''
from pathlib import Path
import json,subprocess,datetime
p=Path('/data/logs/flash-h008-20260926')
result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'records':{},'containers':{}}
for prefix in ('H013-WARM02','H013-FOURWAY01'):
 for suffix in ('.json','-OWNER.json','-CANCEL.json','-SETTLEMENT.json'):
  f=p/(prefix+suffix)
  result['records'][f.name]=json.loads(f.read_text()) if f.exists() else None
for lane,name in {'flash':'llm-frontier-flash','qwen0':'llmctl-qwen38-27b-q0-480000-yarn4-bf16kv','qwen1':'llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv','image':'llm-image-backend'}.items():
 v=json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=5))[0]
 result['containers'][lane]={'Id':v['Id'],'Image':v['Image'],'StartedAt':v['State']['StartedAt'],'Running':v['State']['Running'],'OOMKilled':v['State']['OOMKilled']}
result['units']=subprocess.check_output(['systemctl','show','h013-warm02','h013-fourway01','--property=Id,ActiveState,SubState,MainPID,Result'],text=True,timeout=5)
print(json.dumps(result))
'''
def write(path,value,exclusive=False):
 raw=(json.dumps(value,indent=2)+'\n').encode()
 target=path if exclusive else path.with_suffix(path.suffix+'.tmp')
 fd=os.open(target,os.O_WRONLY|os.O_CREAT|(os.O_EXCL if exclusive else os.O_TRUNC),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 if not exclusive:os.replace(target,path)
 fd=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def identity(snapshot,params):
 assert snapshot['boot']==params['boot'],'boot_changed'
 assert set(snapshot['containers'])==set(params['containers']),'container_set_changed'
 for lane,v in snapshot['containers'].items():
  assert v['Running'] and not v['OOMKilled'],'container_not_running:'+lane
  assert {k:v[k] for k in ('Id','Image','StartedAt')}==params['containers'][lane],'container_changed:'+lane

def qualify(snapshot,params,wall=None):
 identity(snapshot,params)
 records=snapshot['records'];warm=records[WARM+'.json'];assert warm,'warm_receipt_missing'
 assert warm['status']=='COMPLETE' and warm['client_threads_settled'] and not warm['cancel_reason'],'warm_not_complete_clean'
 assert records[WARM+'-CANCEL.json'] is None,'warm_cancel_exists'
 assert warm['owner']['boot']==params['boot'] and warm['owner']['containers']==params['containers'],'warm_identity_changed'
 assert warm['owner']['review_package_sha256']==PACKAGE,'warm_package_changed'
 age=(time.time() if wall is None else wall)-datetime.datetime.fromisoformat(warm['end_utc']).timestamp()
 assert 0<=age<=300,'warm_stale'
 for lane,count,cap in (('flash',8192,128),('qwen0',4096,16),('qwen1',4096,16)):
  rows=warm['requests'][lane];assert len(rows)==1,'warm_request_count'
  row=rows[0];usage=row['usage']
  assert row['status']=='COMPLETE' and row['done'] and row['finish_reason'] and row['http_status']==200,'warm_lane_incomplete'
  assert usage['prompt_tokens']==count and 0<usage['completion_tokens']<=cap and usage['total_tokens']==count+usage['completion_tokens'],'warm_native_usage_mismatch'
 assert not warm['requests']['image'],'unexpected_image_warm'
 assert records[MAIN+'-OWNER.json'] is None and records[MAIN+'.json'] is None,'main_already_owned'
 return {'end_utc':warm['end_utc'],'age_seconds':age,'native_usage':{l:warm['requests'][l][0]['usage'] for l in ('flash','qwen0','qwen1')}}

def proof(snapshot,prefix):
 value=snapshot['records'][prefix+'.json']
 if not value:return None
 if value.get('cancel_reason') or value.get('status') in ('FAILED','PARTIAL_OR_CANCELLED'):
  raise RuntimeError(prefix+'_failed_no_retry')
 lanes=('flash',) if prefix==WARM else ('flash','qwen0','qwen1','image')
 rows={lane:next((r for r in value['requests'][lane] if r.get('body_sent_utc')),None) for lane in lanes}
 if all(rows.values()) and (prefix==WARM or value.get('barrier_released_utc')):
  return {'observed_utc':snapshot['utc'],'barrier_released_utc':value.get('barrier_released_utc'),'body_sent_utc':{lane:r['body_sent_utc'] for lane,r in rows.items()}}
 return None

class Controller:
 def __init__(self,seconds):
  self.deadline=time.monotonic()+seconds;self.seconds=seconds
  self.home=TASK/'private/WARM02-CONTROLLER';self.state={}
 def remaining(self,cap):
  left=self.deadline-time.monotonic()
  if left<=0:raise TimeoutError('controller_dispatch_phase_deadline')
  return min(cap,left)
 def save(self,stage,**values):
  self.state.update(stage=stage,updated_utc=NOW(),**values);write(self.home/'STATUS.json',self.state)
 def check(self):
  manifest=json.loads((HERE.parent/'WARM02-REVIEW.json').read_text())
  hashes={n:sha((HERE/n).read_bytes()) for n in manifest['files']}
  assert hashes==manifest['files'] and sha(json.dumps(hashes,sort_keys=True).encode())==PACKAGE,'driver_package_changed'
  controller=sha(Path(__file__).read_bytes());go_raw=(TASK/'ROOT-GO.json').read_bytes();go=json.loads(go_raw)
  assert go['review_package_sha256']==PACKAGE and go['controller_sha256']==controller,'exact_root_GO_required'
  assert {'warm','main'}.issubset(go['modes']) and go.get('quiet_confirmed') is True and go.get('quiet_evidence'),'root_scope_or_quiet_missing'
  assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc']),'root_GO_expired'
  if self.state:assert sha(go_raw)==self.state['root_GO_sha256'],'root_GO_changed_during_controller'
  return sha(go_raw),controller
 def read(self):
  r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','-T','ai-vm','sudo -n python3 -I -B -'],input=READ,text=True,capture_output=True,timeout=self.remaining(40))
  assert r.returncode==0,'receipt_read_failed_no_replay'
  snapshot=json.loads(r.stdout);write(self.home/'LATEST-REMOTE.json',snapshot);return snapshot
 def invoke(self,label,argv,cap):
  self.check();self.save(label+'_INTENT',command=argv)
  # Timeout/nonzero is ambiguous for dispatch: terminal controller failure, never replay.
  with (self.home/(label+'.stdout')).open('wb') as out,(self.home/(label+'.stderr')).open('wb') as err:
   r=subprocess.run(argv,stdout=out,stderr=err,timeout=self.remaining(cap))
  self.save(label+'_RETURNED',returncode=r.returncode)
  assert r.returncode==0,label+'_failed_or_uncertain_no_replay'
 def pause(self):time.sleep(self.remaining(15))
 def run(self):
  go_hash,controller_hash=self.check()
  self.home.mkdir(mode=0o700) # exclusive, any previous attempt refuses
  parent_fd=os.open(self.home.parent,os.O_RDONLY)
  try:os.fsync(parent_fd)
  finally:os.close(parent_fd)
  self.state={'pid':os.getpid(),'started_utc':NOW(),'max_seconds':self.seconds,'deadline_utc':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=self.remaining(self.seconds))).isoformat(),'package_sha256':PACKAGE,'controller_sha256':controller_hash,'root_GO_sha256':go_hash,'no_automatic_retry':True}
  write(self.home/'INTENT.json',self.state,exclusive=True);self.save('OWNED_BEFORE_ANY_DISPATCH')
  try:
   report=json.loads((TASK/'private/PREFLIGHT.json').read_text());assert report['status']=='FULL_PREFLIGHT_PASS';params=report['parameters']
   snapshot=self.read();identity(snapshot,params)
   for prefix in (WARM,MAIN):
    assert all(snapshot['records'][prefix+s] is None for s in ('.json','-OWNER.json','-CANCEL.json','-SETTLEMENT.json')),'existing_namespace_no_replay'
   self.invoke('WARM_DISPATCH',[sys.executable,'-I','-B',str(HERE/'dispatch.py'),'--mode','warm'],125)
   while True:
    snapshot=self.read();warm=snapshot['records'][WARM+'.json']
    if not self.state.get('warm_start_proof'):
     start=proof(snapshot,WARM)
     if start:self.save('WARM_RUNNING',warm_start_proof=start)
    if snapshot['records'][WARM+'-CANCEL.json'] or (warm and warm.get('cancel_reason')):
     raise RuntimeError('warm_cancelled_native_settlement_owned_no_retry')
    if warm and warm.get('status')=='COMPLETE':
     qualification=qualify(snapshot,params);self.save('WARM_QUALIFIED',qualification=qualification);break
    if warm and warm.get('status') in ('FAILED','PARTIAL_OR_CANCELLED'):raise RuntimeError('warm_failed_no_retry')
    unit=next((b for b in snapshot['units'].split('\n\n') if 'Id=h013-warm02.service' in b),'')
    if any(x in unit.splitlines() for x in ('ActiveState=failed','ActiveState=inactive')):raise RuntimeError('warm_unit_terminal_without_success_no_retry')
    self.pause()
   self.invoke('MAIN_PREFLIGHT',[sys.executable,'-I','-B',str(HERE/'prepare.py')],155)
   fresh=json.loads((TASK/'private/PREFLIGHT.json').read_text());assert fresh['status']=='FULL_PREFLIGHT_PASS'
   assert fresh['parameters']['boot']==params['boot'] and fresh['parameters']['containers']==params['containers'],'postwarm_identity_changed'
   qualification=qualify(self.read(),fresh['parameters']);self.save('MAIN_QUALIFIED',qualification=qualification)
   self.invoke('MAIN_DISPATCH',[sys.executable,'-I','-B',str(HERE/'dispatch.py'),'--mode','main'],125)
   proof_deadline=min(self.deadline,time.monotonic()+120)
   while time.monotonic()<proof_deadline:
    snapshot=self.read();identity(snapshot,params);start=proof(snapshot,MAIN)
    if start:self.save('MAIN_STARTED_EXIT',main_start_proof=start);return
    self.pause()
   raise TimeoutError('main_start_proof_unproven_no_replay')
  except BaseException as e:
   self.save('STOP_NO_RETRY',error_type=type(e).__name__,error=str(e));raise

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true',required=True);parser.add_argument('--max-seconds',type=int,default=1500);args=parser.parse_args()
 assert 1<=args.max_seconds<=1500,'controller_bound_invalid'
 os.umask(0o077)
 Controller(args.max_seconds).run()
if __name__=='__main__':main()
