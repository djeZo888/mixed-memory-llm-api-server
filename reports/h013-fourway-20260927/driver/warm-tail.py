# Uses identical H011 fan03 retained 8192-token Flash warm fixture and collector functions.
# Assembled with definitions only, replacing the two fixed request bounds for warm mode.
PREFIX='H013-WARM02'
result.update(status='PREPARING',warmup='exact_retained_H011_fan03_Flash8192_output128',qwen_warmup='each_actual4096_output16',image_warmup='existing_image_owner_only')
def warm_main():
 global LOGGABLE,ENERGY_PATHS,FAN_READER,FIELDS
 background=[]
 try:
  assert not P(LOG,PREFIX+'.json').exists(),'warm_owner_no_retry'
  result['before']=capture_identity()
  FIELDS=PARAMETERS['query_fields']
  raw=P(LOG,PREFIX+'-FIXTURE.jsonl').read_bytes()
  assert hashlib.sha256(raw).hexdigest()==PARAMETERS['warm_fixture_sha256'],'warm_fixture_changed'
  fixture=json.loads(raw);payload=fixture['payload'];assert payload['max_tokens']==128
  tokenized=control('flash','/v1/tokenize',payload);assert tokenized['count']==8192
  xml=ET.fromstring(run(['nvidia-smi','-q','-x']));LOGGABLE=[]
  for lane,name in NAMES.items():
   v=json.loads(run(['docker','inspect',name]))[0];cg=P('/proc',str(v['State']['Pid']),'cgroup').read_text().split('::')[1].strip();cgroups[lane]=P('/sys/fs/cgroup'+cg)
   if v['HostConfig']['LogConfig']['Type']!='none':
    run(['docker','logs','--tail','1',name]);LOGGABLE.append(lane)
   gpu=next(g for g in xml.findall('gpu') if g.findtext('uuid')==GPUS[lane]);match=re.search(r'\d+',gpu.findtext('temperature/gpu_temp_slow_threshold') or '');limits[lane]=min(85,int(match.group())) if match else 85
  FAN_READER=FanReader();ENERGY_PATHS=list(P('/sys/class/powercap').glob('*/energy_uj'))
  row=sample();assert safety(row) is None,safety(row);samples.append(row);put('telemetry',row)
  collect_logs(result['utc'],now());assert not result['cancel_reason'],'complete_telemetry_preflight_failed'
  result.update(status='RUNNING',full_idle_telemetry_preflight_utc=now(),submission_deadline_monotonic=time.monotonic()+1100)
  persist()
  for fn in (telemetry,writer,native_logs):
   t=threading.Thread(target=fn,daemon=True);t.start();background.append(t)
  ok=request('flash',0,payload,expected_tokens=8192)
  for lane in ('qwen0','qwen1'):
   if stop.is_set():break
   # Bounded native count construction; main fixture bytes never change.
   model=PARAMETERS['capacities'][lane]['served_model_name']
   warm={'model':model,'messages':[{'role':'user','content':''}],'max_tokens':16,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
   count=4096
   for attempt in range(8):
    warm['messages'][0]['content']=' x'*count
    actual=control(lane,'/v1/tokenize',warm)['count']
    if actual==4096:break
    count+=4096-actual
    assert 1<=count<=8192,'warm_count_out_of_bounds'
   assert actual==4096,'warm_exact_count_failed'
   ok=request(lane,0,warm,expected_tokens=4096) and ok
  if not stop.is_set():result['after']=capture_identity()
  result['client_threads_settled']=True
  result['status']='COMPLETE' if ok and not stop.is_set() else 'FAILED'
 finally:
  if stop.is_set():await_settlement()
  done.set()
  for t in background:t.join(10)
  result.update(end_utc=now(),native_settlement='TERMINAL_RESPONSE_CAPTURED' if result['status']=='COMPLETE' else result.get('native_settlement','UNPROVEN'))
  if 'FAN_READER' in globals():
   try:FAN_READER.close()
   except BaseException:result['fan_shutdown_error']=True
  persist()
if __name__=='__main__':
 signal.signal(signal.SIGTERM,lambda *_:cancel('signal_termination'))
 warm_main()
