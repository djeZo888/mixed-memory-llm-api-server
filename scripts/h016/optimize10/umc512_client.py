#!/usr/bin/env python3
"""One authorized R7 UMC512 request; systemd-owned durable receiver. No retry."""
import argparse,base64,datetime,hashlib,http.client,json,os,pathlib,signal,sys,time
P=pathlib.Path
B='/data/build/H016-20260927/worker1-r7'
L='/data/logs/H016-20260927/worker1-r7'
CID='b0c319cce5c8fcececc28acb01ec92f68693588ba843c8136107927aa7ffbac1'
UNIT='h016-mimo-profile-20260927-r7.service'
INV='2034e3b8f6004f6da8ebf7a92a389690'
TEXT=('Scientific technical fixture HOST-UMC-R7-512-270927-R10. Explain how a successive-approximation ADC samples a sensor signal. '
      'Write at least 1600 words covering sample-and-hold, binary search, quantization error, reference voltage, source impedance, '
      'settling time, aliasing, and anti-alias filtering. Continue in detailed numbered paragraphs without an introduction or early conclusion until the response limit.')
def stamp():return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic_seconds':time.monotonic()}
OUT='/data/logs/H016-20260927/worker1-optimize10'
EVENTS=None
RAW=None
ANCHOR=None
LAST_FLUSH=0

def emit(event,**values):
 row={'event':event,**stamp(),**values}
 if event=='RECEIPT':
  ANCHOR.atomic_json('HOST-UMC512-REPLACEMENT.json',values['receipt'])
 else:
  os.write(EVENTS.fileno(),(json.dumps(row,separators=(',',':'))+'\n').encode())
 # Evidence is local and independent of stdout/SSH. No stdout notification.

def capture_chunk(row):
 global LAST_FLUSH
 RAW.write((json.dumps(row,separators=(',',':'))+'\n').encode())
 if time.monotonic()-LAST_FLUSH>=1:
  RAW.flush();LAST_FLUSH=time.monotonic()

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run-authorized',action='store_true');args=ap.parse_args()
 if not args.run_authorized:ap.error('Explicit --run-authorized required; no default dispatch')
 sys.path.insert(0,B)
 assert hashlib.sha256(P(B,'candidate_owner.py').read_bytes()).hexdigest()=='4e2c9e98503d4e7ce7a2bb18cd589f5767d53cf7fdca2cd04b397173aa258c71'
 from candidate_owner import dependency,inspect,get,read_key,run_cmd
 assert hashlib.sha256(P(B,'telemetry.py').read_bytes()).hexdigest()=='2c0e7483845530cf9b669d699c67b574e0f4a8cbba21dd6c511bc7ddf7f817aa'
 from benchmark import body,count
 h=dependency();key=read_key(h)
 def identity():
  u=run_cmd(['systemctl','show',UNIT,'-p','MainPID,InvocationID,ActiveState']);assert 'MainPID=229308\n' in u and 'InvocationID='+INV in u and 'ActiveState=active' in u
  c=inspect(CID);assert c['State']['Running'] and c['State']['Pid']==232672 and c['State']['StartedAt']=='2026-09-27T14:28:05.871420053Z' and c['Image']=='sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e'
  return c
 identity()
 # Prior native completion was retained by PROFILE09; authenticated idle below is the current boundary.
 with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot(L,g) as a:
  def jread(n):
   with a.open(n) as f:
    parts=[]
    while True:
     b=f.read(65536)
     if not b:break
     parts.append(b)
    return json.loads(b''.join(parts))
  owner=jread('OWNER.json');assert owner['status']=='PROFILE_BASELINE_COMPLETE_WARM_AWAIT_ROOT' and owner['pid']==229308
  for label in ['BASELINE128','PROFILE128']:
   r=jread(label+'.json');assert r['done'] and r['full_http_drain'] and r['status']=='TRANSPORT_COMPLETE'
  with a.open('TELEMETRY.jsonl') as f:
   f.seek(max(0,a.stat('TELEMETRY.jsonl').st_size-30000));guard=json.loads(f.read(40000).decode().splitlines()[-1])
 assert time.time()-datetime.datetime.fromisoformat(guard['utc']).timestamp()<12
 assert int(guard['cgroup']['memory.swap.current'])==0 and guard['host']['MemAvailable']>=.15*guard['host']['MemTotal']
 assert len(guard['gpus'])==4
 assert all(g['temp_c']<guard['temperature_limits_c'][g['uuid']] for g in guard['gpus'])
 for g in guard['gpus']:
  floor=g['total_mib']*(.07 if g['uuid']=='GPU-69acfa26-8b60-61b5-702d-aee252c163cc' else .05) if g['uuid'] in ['GPU-69acfa26-8b60-61b5-702d-aee252c163cc','GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'] else 16*1024
  assert g['free_mib']>=floor
 events=dict(line.split() for line in guard['cgroup']['memory.events'].splitlines())
 assert int(events.get('oom',0))==0 and int(events.get('oom_kill',0))==0
 code,slots=get(30012,'/slots',key);assert code==200 and len(slots)==1 and slots[0]['is_processing'] is False
 with h.transaction():h.s.root_payload_guard()
 payload=body(TEXT,thinking=False,output=512);payload['seed']=270927
 expected,raw=count(key,payload)
 # Existing proxy reserializes normalize(body) with default json.dumps.
 upstream=json.dumps(payload).encode()
 deadline=min(time.time()+240,datetime.datetime(2026,9,27,15,15,tzinfo=datetime.timezone.utc).timestamp())
 assert deadline-time.time()>=180 and expected+512<=131071
 emit('PREPARED',fixture=TEXT,payload=payload,payload_sha256=hashlib.sha256(raw).hexdigest(),upstream_payload_sha256=hashlib.sha256(upstream).hexdigest(),input_tokens=expected,deadline_utc=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).isoformat(),owner_pid=229308,native_pid=232672,guard_utc=guard['utc'])
 start=time.monotonic();row={'label':'HOST-UMC512-REPLACEMENT','started':stamp(),'expected_input_tokens':expected,'request_sha256':hashlib.sha256(raw).hexdigest(),'upstream_request_sha256':hashlib.sha256(upstream).hexdigest(),'payload':payload,'raw_chunks':[],'status':'SUBMITTED','client_deadline_epoch':deadline}
 c=http.client.HTTPConnection('10.156.100.60',30012,timeout=max(.1,deadline-time.time()));dispatched=False;terminal=False
 def expired(*_):raise TimeoutError('absolute_client_deadline')
 signal.signal(signal.SIGTERM,expired);signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,deadline-time.time())
 try:
  emit('DISPATCHING',output_ceiling=512,request_sha256=row['request_sha256']);dispatched=True;c.request('POST','/v1/chat/completions',raw,{'Authorization':'Bearer '+key.decode(),'Content-Type':'application/json'})
  row['body_sent']=stamp();emit('BODY_SENT',body_sent=row['body_sent'],input_tokens=expected,output_ceiling=512)
  response=c.getresponse();assert response.status==200
  done=False;usage=None;finish=None;pending=b'';content='';reasoning='';calls={};output_events=0
  while True:
   assert time.time()<deadline
   if c.sock:c.sock.settimeout(max(.1,deadline-time.time()))
   chunk=response.read1(65536)
   if not chunk:break
   at=stamp();piece={**at,'bytes':len(chunk),'base64':base64.b64encode(chunk).decode()};row['raw_chunks'].append(piece);capture_chunk(piece);pending+=chunk
   while b'\n' in pending:
    line,pending=pending.split(b'\n',1)
    if not line.startswith(b'data: '):continue
    data=line[6:].strip()
    if data==b'[DONE]':done=True;row['done_at']=at;continue
    event=json.loads(data)
    if event.get('usage'):usage=event['usage'];row['usage_at']=at
    if event.get('timings'):row['native_timings']=event['timings']
    for choice in event.get('choices',[]):
     d=choice.get('delta',{})
     if d.get('content') or d.get('reasoning_content') or d.get('tool_calls'):
      output_events+=1
      if 'first_output' not in row:row['first_output']=at;emit('FIRST_OUTPUT',first_output=at,body_sent=row['body_sent'],output_events=output_events,output_ceiling=512,request_sha256=row['request_sha256'])
      row['last_output']=at
     content+=d.get('content') or '';reasoning+=d.get('reasoning_content') or ''
     for call in d.get('tool_calls',[]):
      item=calls.setdefault(call['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
      if call.get('id'):item['id']=call['id']
      for k,v in call.get('function',{}).items():item['function'][k]+=v
     finish=choice.get('finish_reason') or finish
     if choice.get('finish_reason'):row['finish_at']=at
   assert len(pending)<16*1024*1024
  row['drained']=stamp();assert done and usage and finish and not pending.strip()
  assert usage['prompt_tokens']==expected and usage['completion_tokens']<=512
  code,slots=get(30012,'/slots',key);assert code==200 and len(slots)==1 and slots[0]['is_processing'] is False
  terminal=True;row.update(status='TRANSPORT_COMPLETE',done=done,full_http_drain=True,usage=usage,finish_reason=finish,content=content,reasoning_content=reasoning,tool_calls=list(calls.values()),output_events=output_events,slot_idle_after=True,total_seconds=time.monotonic()-start,correctness='UNSCORED_LENGTH_THROUGHPUT')
  emit('TERMINAL',usage=usage,finish_reason=finish,body_sent=row['body_sent'],first_output=row.get('first_output'),last_output=row.get('last_output'),done_at=row.get('done_at'),drained=row['drained'],native_timings=row.get('native_timings'),slot_idle_after=True)
 except BaseException as exc:
  row.update(status='FAILED_NO_RETRY',error_type=type(exc).__name__)
  emit('FAILURE',error_type=type(exc).__name__,exact_owner_settlement_required=dispatched)
  if dispatched:
   identity()
   with h.transaction():h.s.root_payload_guard()
   os.kill(229308,signal.SIGTERM);row['owner_settlement_requested']=stamp();emit('OWNER_SETTLEMENT_REQUESTED',owner_pid=229308)
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);c.close();RAW.flush();row['finished']=stamp()
  with h.transaction():emit('RECEIPT',receipt=row);h.s.root_payload_guard()
 if not terminal:raise SystemExit(1)
def entry():
 global EVENTS,RAW,ANCHOR
 sys.path.insert(0,B)
 from candidate_owner import dependency,inspect,run_cmd
 h=dependency()
 if '--settle-if-needed' in sys.argv:
  with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot(OUT,g) as a:
   receipt=a.read_json('HOST-UMC512-REPLACEMENT.json') if a.stat('HOST-UMC512-REPLACEMENT.json',missing_ok=True) else {}
   if receipt.get('status')=='TRANSPORT_COMPLETE' and receipt.get('slot_idle_after'):return
   if not a.stat('PROGRESS.jsonl',missing_ok=True):return
   with a.open('PROGRESS.jsonl') as f: events=f.read(100000).decode()
  if 'DISPATCHING' not in events and 'BODY_SENT' not in events:return
  c=inspect(CID)
  if not c['State']['Running']:return
  assert c['State']['Pid']==232672 and c['State']['StartedAt']=='2026-09-27T14:28:05.871420053Z'
  u=run_cmd(['systemctl','show',UNIT,'-p','MainPID,InvocationID'])
  assert 'MainPID=229308\n' in u and 'InvocationID='+INV in u
  with h.transaction():h.s.root_payload_guard()
  os.kill(229308,signal.SIGTERM)
  return
 with h.transaction():h.s.root_payload_guard()
 with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot(OUT,g) as a, a.open('PROGRESS.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as e, a.open('RAW-CHUNKS.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as r:
  ANCHOR=a;EVENTS=e
  with os.fdopen(os.dup(r.fileno()),'wb',buffering=65536) as stream:
   RAW=stream
   try:main()
   except BaseException as exc:
    emit('CLIENT_EXIT_FAILURE',error_type=type(exc).__name__)
    if not a.stat('HOST-UMC512-REPLACEMENT.json',missing_ok=True):
     with h.transaction():emit('RECEIPT',receipt={'status':'FAILED_NO_RETRY','error_type':type(exc).__name__,'finished':stamp()})
    raise

if __name__=='__main__':entry()
