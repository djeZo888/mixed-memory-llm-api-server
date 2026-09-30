#!/usr/bin/env python3
"""One bounded normal-owner recovery after H013. Never clear hardware latches."""
import argparse,datetime,hashlib,json,os,pathlib,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).parent));import prep
P=pathlib.Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');args=p.parse_args()
if not args.run:p.error('--run required')
prep.setup();gate=prep.gate();deadline=time.monotonic()+880
pins=json.loads(P(prep.RUN,'RECOVERY-PINS.json').read_text())
for name,want in pins.items():prep.require(hashlib.sha256(P(name).read_bytes()).hexdigest()==want,'preserved_source_changed')
state={'status':'NORMAL_RECOVERY_STARTED','utc':prep.now(),'pid':os.getpid(),'session':prep.SESSION,'gate':gate,'actions':[],'no_benchmark':True,'no_latch_clear':True}
active=json.loads(P('/data/services/llm-manager/active/active.json').read_text())
for slot,selected in [('glm','qwen38-27b-q0-480000-yarn4-bf16kv'),('qwen','qwen38-27b-q1-server-480000-yarn4-bf16kv')]:
 v=active['slots'][slot];prep.require(v['desired']=='running' and v['selected']==selected,'qwen_intent_changed')
flash=json.loads(P('/data/services/flash-h008-20260926/state.json').read_text());prep.require(flash['desired']=='running','flash_intent_changed')
settlement=gate['H013-FOURWAY01']['native_settlement']
for lane,row in settlement['lanes'].items():
 r=subprocess.run(['docker','inspect',row['container_id']],capture_output=True,text=True)
 if r.returncode:
  prep.require(lane=='image' and 'no such object' in r.stderr.lower() and json.loads(P('/data/services/image21-runtime-20260923/state.json').read_text()).get('container') is None,'owned_container_ambiguously_absent')
  prep.require(not prep.output(['docker','ps','-aq','--filter','name=^/llm-image-backend$']).strip(),'image_replaced_owner')
 else:
  c=json.loads(r.stdout)[0];prep.require(not c['State']['Running'] and c['State']['Pid']==0 and not c['State']['Restarting'],'owned_state_changed')
commands=[('qwen0','GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237',['/usr/bin/python3','-I','-B','/data/services/releases/h009-flash-r1-20260926/scripts/llmctl','start','--target','glm','--yes','--instance','/data/services/llm-manager/deployment-instance.json']),('qwen1','GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528',['/usr/bin/python3','-I','-B','/data/services/releases/h009-flash-r1-20260926/scripts/llmctl','start','--target','qwen','--yes','--instance','/data/services/llm-manager/deployment-instance.json']),('flash','GPU-69acfa26-8b60-61b5-702d-aee252c163cc',['/usr/bin/python3','-I','-B','/data/services/flash-h008-20260926/source/owner.py','resume']),('image','GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23',['systemctl','restart','llm-image-backend.service'])]
prep.put('recovery-STATUS.json',state)
for lane,gpu,cmd in commands:
 row={'lane':lane,'start_utc':prep.now(),'command':cmd};state['actions'].append(row)
 try:
  temp=int(prep.output(['nvidia-smi','--id='+gpu,'--query-gpu=temperature.gpu','--format=csv,noheader,nounits']).strip());row['admission_temp_c']=temp
  prep.require(temp<65,'temperature_not_recovered')
  prep.require(time.monotonic()<deadline,'recovery_deadline')
  prep.put('recovery-STATUS.json',state)
  with prep.MountedStorageGuard(prep.s) as g,prep.AnchoredRoot(prep.LOG,g) as a:
   prep.s.root_payload_guard()
   with a.open('recovery-'+lane+'.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as f:
    q=subprocess.Popen(cmd,stdout=f.fileno(),stderr=subprocess.STDOUT)
    row['child_pid']=q.pid
    while q.poll() is None:
     prep.require(time.monotonic()<deadline,'recovery_deadline');a.check();time.sleep(2)
    row['exit_code']=q.returncode;row['status']='OWNER_RETURNED' if q.returncode==0 else 'OWNER_REFUSED_OR_FAILED'
   prep.s.root_payload_guard()
 except Exception as e:
  row.update(status='STOP_COMPONENT',error_type=type(e).__name__,reason=str(e) if isinstance(e,RuntimeError) else type(e).__name__)
 row['end_utc']=prep.now();prep.put('recovery-STATUS.json',state)
state.update(status='NORMAL_OWNER_ACTIONS_FINISHED_READINESS_REQUIRES_READBACK',end_utc=prep.now())
# A concurrent job may own a short checkpoint lease; final receipt must not be skipped.
until=time.monotonic()+30
while not prep.put('recovery-STATUS.json',state):
 if time.monotonic()>until:raise RuntimeError('final_receipt_lease_timeout')
 time.sleep(.25)
