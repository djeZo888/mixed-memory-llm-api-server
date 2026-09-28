#!/usr/bin/env python3
"""H026 one-shot sequential caps; existing native streaming parser; no retries."""
import datetime,hashlib,http.client,json,os,pathlib,signal,subprocess,sys,threading,time,types,secrets
P=pathlib.Path
ROOT=P('/usr/local/lib/llm-server/control-api')
OUT=P('/data/logs/H026-CAP01-20260928')
CUT=datetime.datetime.fromisoformat('2026-09-28T21:23:00+00:00').timestamp()
GPUS={'qwen0':'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237','qwen1':'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'}
SLOTS={'qwen0':'glm','qwen1':'qwen'}
EXPECTED={'qwen0':(41,2511660),'qwen1':(37,1844069)}
sys.path.insert(0,str(OUT/'source/scripts'))
from benchmark.client import run_request,http_transport
from benchmark.fixtures import canonical,digest
sys.path.insert(0,str(ROOT/'scripts'))
from lifecycle.manager import load_manager
from common.lifecycle_lease import acquire_lease
sys.path.insert(0,str(OUT/'source'))
from fans import FanReader
stop=threading.Event();done=threading.Event();latest=0.;faults=[];samples=[];active=None
R={'task':'H026-CAP01','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requests':[],'faults':faults}
def run(a,t=8):return subprocess.check_output(a,timeout=t,text=True,stderr=subprocess.PIPE)
def save(name,v):
 b=json.dumps(v,indent=2).encode();p=OUT/(name+'.json');tmp=OUT/(name+'.tmp');tmp.write_bytes(b);os.chmod(tmp,0o600);tmp.replace(p)
def persist():save('RESULTS',R)
def limits():
 fields='uuid,power.limit,enforced.power.limit,power.min_limit,power.max_limit'
 return {s[0]:list(map(float,s[1:])) for line in run(['nvidia-smi','--query-gpu='+fields,'--format=csv,noheader,nounits']).splitlines() if (s:=[v.strip() for v in line.split(',')])[0] in GPUS.values()}
def cap(uid,w):
 assert uid in GPUS.values() and w in (500,550,600)
 run(['nvidia-smi','-i',uid,'-pl',str(w)])
 v=limits()[uid];assert v[:2]==[float(w),float(w)] and v[2]<=w<=v[3]
 return v
def restore():
 receipts={}
 for uid in GPUS.values():
  try:receipts[uid]={'readback':cap(uid,600)}
  except BaseException as e:receipts[uid]={'error':type(e).__name__}
 save('RESTORE',receipts);return receipts
def rpc(lane,path,payload=None):
 c=http.client.HTTPConnection('127.0.0.1',30002 if lane=='qwen0' else 30004,timeout=15)
 try:
  c.request('GET' if payload is None else 'POST',path,None if payload is None else canonical(payload),{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  r=c.getresponse();b=r.read(4*1024*1024);assert r.status==200 and r.read(1)==b''
  return json.loads(b)
 finally:c.close()
def identity(lane):
 slot=manager.read_state(offline=True)['slots'][SLOTS[lane]]
 c=manager.trusted_container(slot['container']);pid=c['State']['Pid']
 assert c['State']['Running'] and not c['State']['OOMKilled']
 return {'generation':slot['generation'],'profile':slot['container'],'Id':c['Id'],'Image':c['Image'],'StartedAt':c['State']['StartedAt'],'Pid':pid,'start_ticks':P('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19],'cgroup':P('/proc',str(pid),'cgroup').read_text().split('::')[1].strip()}
def ready(lane):
 assert identity(lane)==R['identities'][lane]
 assert rpc(lane,'/v1/readiness')['ready'] is True
 info=rpc(lane,'/get_server_info');read={k:next((x[k] for x in [info,*info.get('internal_states',[])] if k in x),None) for k in specs[lane]['capacity_readback']}
 assert read==specs[lane]['capacity_readback'];return read

def stop_owned(lane):
 # Only potentially dispatched uncertain work reaches here, never an unsent row.
 expected=R['identities'][lane];assert identity(lane)==expected
 before=manager.read_state(offline=True)['slots'][SLOTS[lane]]
 save('STOP-INTENT',{'lane':lane,'identity':expected,'utc':time.time()})
 run(['docker','stop','--time','3',expected['Id']],12)
 c=json.loads(run(['docker','inspect',expected['Id']]))[0]
 assert c['Id']==expected['Id'] and not c['State']['Running'] and c['State']['Pid']==0 and not c['State']['Restarting']
 cg=P('/sys/fs/cgroup'+expected['cgroup']);assert not cg.exists() or not (cg/'cgroup.procs').read_text().strip()
 assert not P('/proc',str(expected['Pid'])).exists()
 with acquire_lease(blocking=False) as lease:
  assert manager.read_state(offline=True)['slots'][SLOTS[lane]]==before
  manager.dispatch('boot-stop',lease=lease,target=SLOTS[lane],expected_generation=before['generation'])
  if before['failure'] is not None:
   with manager.slot_context(SLOTS[lane]):manager.state['failure']=before['failure'];manager.save(emergency=True)
  after=manager.read_state(offline=True)['slots'][SLOTS[lane]]
  assert all(after[k]==before[k] for k in ('selected','desired','boot_policy','failure'))
 R['fault_stop']={'lane':lane,'physical_stop_proven':True};persist()

def sample():
 global latest
 fields=['uuid','power.draw','temperature.gpu','utilization.gpu','clocks.current.graphics','clocks.current.sm','clocks.current.memory']
 flags=['sw_power_cap','hw_thermal_slowdown','sw_thermal_slowdown','hw_power_brake_slowdown','hw_slowdown'];fields+=['clocks_event_reasons.'+x for x in flags]
 begin=time.monotonic();rows={}
 for line in run(['nvidia-smi','--query-gpu='+','.join(fields),'--format=csv,noheader,nounits'],3).splitlines():
  v=[s.strip() for s in line.split(',')]
  if v[0] in GPUS.values():rows[v[0]]={**dict(zip(fields[1:7],map(float,v[1:7]))),**dict(zip(flags,v[7:]))}
 assert set(rows)==set(GPUS.values())
 for row in rows.values():
  assert row['temperature.gpu']<85,'thermal_85C'
  assert all(row[f]=='Not Active' for f in flags[1:4]),'thermal_or_power_brake'
 mirror=json.loads((OUT/'fan.json').read_text());fan=mirror['controller']
 assert time.time()-mirror['received_epoch']<5 and time.time()-datetime.datetime.fromisoformat(fan['updated_at']).timestamp()<15,'fan_stale'
 assert fan['gpu_uuid']==GPUS['qwen1'] and fan['source_bits']==[0,0,0] and fan['mode']==4,'fan_identity'
 assert fan['state']=='healthy' and not fan['errors'] and fan['readback_duty']==fan['desired_duty'] and fan['actual_tach']>0,'fan_unhealthy'
 assert run(['systemctl','is-active','local-ai-fan-boost.service']).strip()=='active'
 row={'monotonic':time.monotonic(),'epoch':time.time(),'gpu':rows,'fans':fans.sample(GPUS),'external_fan':fan}
 assert row['monotonic']-begin<5,'telemetry_slow'
 latest=row['monotonic'];samples.append(row)
 with (OUT/'telemetry.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
def monitor():
 while not done.is_set():
  t=time.monotonic()
  try:sample()
  except BaseException as e:faults.append({'kind':'telemetry','reason':str(e),'epoch':time.time()});stop.set();return
  done.wait(max(0,1-(time.monotonic()-t)))
def freshness_watch():
 while not done.wait(.2):
  if time.monotonic()-latest>=5:
   faults.append({'kind':'telemetry_stale_watchdog','epoch':time.time()});stop.set();return
def guard():
 assert not stop.is_set() and time.monotonic()-latest<5,'safety_guard'
 assert time.time()<CUT,'admission_cutoff'
 assert P('/proc/sys/kernel/random/boot_id').read_text().strip()==R['boot_id']

def fixture(lane,nonce,units):
 # Fixed familiar neutral corpus, leading nonce ahead of every repeated byte.
 content=nonce+'\n'+' amber cedar river stone meadow cloud'*units+'\nWrite an extensive numbered list of 100 distinct practical observations about the above landscape words. Each item must be a full sentence. Begin immediately with item 1 and continue until the output limit. Do not summarize or conclude.'
 return {'model':specs[lane]['model'],'messages':[{'role':'user','content':content}],'max_tokens':512,'temperature':0,'chat_template_kwargs':{'enable_thinking':False},'stream':True,'stream_options':{'include_usage':True}}
def count(lane,body):
 cb={k:v for k,v in body.items() if k not in ('stream','stream_options')};v=rpc(lane,'/v1/tokenize',cb)
 assert type(v['count']) is int and v['count']==len(v['tokens']) and all(type(t) is int for t in v['tokens'])
 return {'input_tokens':v['count'],'count_body_sha256':digest(canonical(cb)),'token_ids_sha256':digest(canonical(v['tokens'])),'template_sha256':specs[lane]['template_sha256'],'removed_fields':['stream','stream_options']}
def main():
 global manager,key,specs,fans,active
 with (OUT/'LAUNCHED').open('x') as f:f.write(str(os.getpid()))
 manager=load_manager(types.SimpleNamespace(instance=None),ROOT/'configs');key=P('/data/services/secrets/llm-api-key').read_text().strip()
 specs=json.loads(P('/data/logs/H025-EXEC05-20260928/manifest.json').read_text())['lanes']
 R['boot_id']=P('/proc/sys/kernel/random/boot_id').read_text().strip();R['original_caps']=limits();save('ORIGINAL-CAPS',R['original_caps'])
 assert all(v[:2]==[600.,600.] for v in R['original_caps'].values())
 R['identities']={l:identity(l) for l in GPUS}
 for l,i in R['identities'].items():assert (i['generation'],i['Pid'])==EXPECTED[l];ready(l)
 R['source_pins']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('scripts/runtime/adaptive_text_drain.py','scripts/lifecycle/hardware_policy.py')}
 assert R['source_pins']['scripts/runtime/adaptive_text_drain.py']=='517357bd0aa6fb17ea23f8041884c7d7557fa1a95410174aea5a6d5fed313a36'
 assert R['source_pins']['scripts/lifecycle/hardware_policy.py']=='cf5581289148f419f7056165e244ade8d696542cbb24c045b7d3533f873c46d1'
 fans=FanReader();sample();threading.Thread(target=freshness_watch,daemon=True).start();thread=threading.Thread(target=monitor,daemon=True);thread.start();persist()
 try:
  units=9125
  for lane in GPUS:
   for index,watts in enumerate((600,600,550,500,600)):
    guard();ready(lane);readback=cap(GPUS[lane],watts);time.sleep(2);guard()
    body=fixture(lane,secrets.token_hex(24),units);native=count(lane,body)
    assert 63000<=native['input_tokens']<=66000,'fixture_not_64K'
    guard();sid=lane+'-'+str(index)+'-'+str(watts);row={'sample_id':sid,'lane':lane,'watts':watts,'warmup':index==0,'native_count':native,'cap_readback':readback,'status':'INTENT'};R['requests'].append(row);persist()
    transport=http_transport(specs[lane]['endpoint'],key,cancel_event=stop,admission_deadline_epoch=CUT)
    active=lane
    result=run_request(canonical(body),transport,sample_id=sid,private_dir=str(OUT/'raw'),summary_path=str(OUT/'client.jsonl'),timeout=180,capture_events=True)
    row.update(summary=result['summary'],transport_clock=getattr(transport,'request_clock',{}))
    summary=result['summary'];assert summary['status'] in ('COMPLETE','OUTPUT_LIMIT') and summary['response_retained_complete'] and summary['client_timing']['done_observed'] and row['transport_clock']['terminal_reason']=='DRAINED','incomplete_response'
    # Valid terminal SSE + EOF settles this accepted request before postprocessing.
    active=None;row['native_response_complete']=True
    assert type(summary['counters'].get('completion_tokens')) is int and 0<summary['counters']['completion_tokens']<=512,'invalid_completion_tokens'
    assert summary['counters']['prompt_tokens']==native['input_tokens'],'native_count_mismatch'
    row.update(finish_reason=result['parsed']['finish_reason'],capacity=ready(lane),status='SETTLED_FULL_RESPONSE_SAME_OWNER',settlement='PINNED_ADAPTIVE_DRAIN_FULL_RESPONSE_EXCLUSIVE_OWNER');active=None
    persist();print(sid,summary['counters'],summary['client_elapsed_seconds'],flush=True)
   cap(GPUS[lane],600)
  assert not stop.is_set() and not faults,'post_drain_guard_fault'
  R['status']='COMPLETE'
 except BaseException as e:
  R['status']='FAILED';R['failure']={'class':type(e).__name__,'reason':str(e)};stop.set();persist()
  if active:
   dispatched=locals().get('transport');clock=getattr(dispatched,'request_clock',{})
   if clock.get('http_dispatched'):stop_owned(active)
 finally:
  R['restored_caps']=restore();done.set();thread.join(6);fans.close();R['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();persist()
if __name__=='__main__':
 os.umask(0o077)
 if '--restore' in sys.argv:restore()
 else:
  signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
  try:main()
  finally:restore()
