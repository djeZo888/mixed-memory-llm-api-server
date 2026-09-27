# H011 task-only driver. Prepend pinned vm-common and PARAMETERS; no model lifecycle.
import http.client, threading, socket, signal, copy, base64, struct, re
import xml.etree.ElementTree as ET
LOG='/data/logs/flash-h008-20260926'
PREFIX='H011-FOURWAY02'
NAMES={'flash':'llm-frontier-flash','qwen0':'llmctl-qwen38-27b-q0-480000-yarn4-bf16kv','qwen1':'llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv','image':'llm-image-backend'}
PORTS={'flash':30010,'qwen0':30002,'qwen1':30004,'image':30006}
GPUS={'flash':'GPU-69acfa26-8b60-61b5-702d-aee252c163cc','qwen0':'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237','qwen1':'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528','image':'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'}
FIELDS=['uuid','power.draw','power.draw.average','power.draw.instant','power.limit','utilization.gpu','memory.total','memory.used','memory.free','temperature.gpu','clocks_event_reasons.active','ecc.errors.uncorrected.volatile.total','pcie.replay_counter']+[
 'clocks_event_reasons.'+x for x in ('sw_power_cap','hw_slowdown','hw_thermal_slowdown','hw_power_brake_slowdown','sw_thermal_slowdown')]
key=P('/data/services/secrets/llm-api-key').read_text().strip()
stop=threading.Event();done=threading.Event();barrier=threading.Barrier(5)
lock=threading.Lock();persist_lock=threading.Lock();active={};buffers={};cursors={};samples=[];cgroups={};limits={}
result={'status':'PREPARING','utc':now(),'owner':PARAMETERS,'requests':{k:[] for k in NAMES},'cancel_reason':None,'no_automatic_retries':True,'model_lifecycle_mutations':False}
def run(args,timeout=10):
 return subprocess.check_output(args,text=True,stderr=subprocess.PIPE,timeout=timeout)
def control(lane,path,payload=None):
 c=http.client.HTTPConnection('127.0.0.1',PORTS[lane],timeout=20)
 try:
  c.request('POST' if payload is not None else 'GET',path,json.dumps(payload) if payload is not None else None,{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  q=c.getresponse();raw=q.read(16*1024*1024);assert q.status==200,(lane,path,q.status)
  return json.loads(raw)
 finally:c.close()
def put(name,row):
 # Bounded memory only on hot stream paths.
 rows=buffers.setdefault(name,[])
 assert len(rows)<16000,'buffer_count_bound'
 rows.append(row)
def persist():
 with persist_lock:
  snapshot=copy.deepcopy(result);snapshot.update(checkpoint_utc=now(),sample_count=len(samples),latest_sample=samples[-1] if samples else None)
  pending={n:(len(rows),rows[cursors.get(n,0):]) for n,rows in list(buffers.items())}
  with transaction() as (_,g):
   s.root_payload_guard()
   with AnchoredRoot(LOG,g) as a:
    for n,(end,rows) in pending.items():
     if not rows:continue
     with a.open(PREFIX+'-'+n+'.jsonl',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600) as f:
      f.write((''.join(json.dumps(x,separators=(',',':'))+'\n' for x in rows)).encode());f.fsync()
     cursors[n]=end
   status(LOG+'/'+PREFIX+'.json',snapshot,g);s.root_payload_guard()
def cancel(reason):
 with lock:
  if not result['cancel_reason']:result.update(cancel_reason=reason,cancel_utc=now())
  stop.set();current=list(active.values())
 for c,response in current:
  sock=getattr(c,'sock',None)
  if sock is None and response is not None:sock=getattr(getattr(getattr(response,'fp',None),'raw',None),'_sock',None)
  if sock:
   try:sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass

def capture_identity():
 s.root_payload_guard()
 with MountedStorageGuard(s) as g:
  g.check_path(LOG)
  for p,h in PARAMETERS['source_matches'].items():assert hashlib.sha256(P(p).read_bytes()).hexdigest()==h,'source_changed:'+p
 out={'utc':now(),'boot':P('/proc/sys/kernel/random/boot_id').read_text().strip(),'containers':{},'capacity':{},'ready':{}}
 assert out['boot']==PARAMETERS['boot']
 for lane,name in NAMES.items():
  v=json.loads(run(['docker','inspect',name]))[0]
  assert v['State']['Running'] and not v['State']['OOMKilled']
  out['containers'][lane]={k:v[k] for k in ['Id','Image']};out['containers'][lane]['StartedAt']=v['State']['StartedAt']
  assert out['containers'][lane]==PARAMETERS['containers'][lane],'container_changed'
  if lane!='image':
   out['ready'][lane]=control(lane,'/v1/readiness');assert out['ready'][lane]['ready']
   info=control(lane,'/get_server_info')
   cap={k:next((x[k] for x in [info,*info.get('internal_states',[])] if k in x),None) for k in PARAMETERS['capacities'][lane]}
   assert cap==PARAMETERS['capacities'][lane],'capacity_changed';out['capacity'][lane]=cap
  else:
   out['ready'][lane]=control(lane,'/health/ready');assert out['ready'][lane]['ready'] and not out['ready'][lane]['busy']
   out['image_profiles']=control(lane,'/v1/image-capabilities');assert len(out['image_profiles']['profiles'])==9
 return out

def read_pairs(p):return {l.split()[0]:int(l.split()[1]) for l in p.read_text().splitlines()}
def numeric(v):
 try:return float(v)
 except (ValueError,TypeError):return None

def sample():
 t=time.monotonic();out={'utc':now(),'monotonic':t,'gpu':{},'cgroups':{}}
 raw=run(['nvidia-smi','--query-gpu='+','.join(FIELDS),'--format=csv,noheader,nounits'],5)
 for line in raw.splitlines():
  vals=[v.strip() for v in line.split(',')];row=dict(zip(FIELDS,vals));uid=row.pop('uuid');out['gpu'][uid]=row
 assert set(out['gpu'])==set(GPUS.values()),'gpu_identity_set_changed'
 out['gpu_query_end_monotonic']=time.monotonic()
 out['ram']={l.split(':')[0]:int(l.split()[1])*1024 for l in P('/proc/meminfo').read_text().splitlines() if l.split(':')[0] in {'MemTotal','MemAvailable','SwapTotal','SwapFree'}}
 out['swap']={k:v for k,v in read_pairs(P('/proc/vmstat')).items() if k in ('pswpin','pswpout')}
 out['cpu_ticks']=list(map(int,P('/proc/stat').read_text().splitlines()[0].split()[1:]))
 out['pressure']={n:P('/proc/pressure',n).read_text() for n in ('memory','io','cpu')}
 for lane,cg in cgroups.items():
  out['cgroups'][lane]={n:int((cg/n).read_text()) for n in ('memory.current','memory.swap.current')}
  out['cgroups'][lane]['events']=read_pairs(cg/'memory.events');out['cgroups'][lane]['cpu']=read_pairs(cg/'cpu.stat')
  out['cgroups'][lane]['memory_stat']={k:v for k,v in read_pairs(cg/'memory.stat').items() if k in ('anon','file','pgmajfault','workingset_refault_anon','workingset_refault_file')}
 out['cpu_energy_uj']={str(p):int(p.read_text()) for p in ENERGY_PATHS}
 out['three_blackwell_w']=sum(float(out['gpu'][GPUS[l]]['power.draw']) for l in ('flash','qwen0','qwen1'))
 out['ada_external_w']=float(out['gpu'][GPUS['image']]['power.draw'])
 out['all_four_diagnostic_w']=out['three_blackwell_w']+out['ada_external_w']
 return out

def safety(row):
 if row['ram']['MemAvailable']<row['ram']['MemTotal']*.15:return 'host_reserve_below_15pct'
 for lane,uid in GPUS.items():
  g=row['gpu'][uid]
  if float(g['temperature.gpu'])>=limits[lane]:return lane+'_thermal_limit'
  if any(g.get('clocks_event_reasons.'+k)=='Active' for k in ('hw_thermal_slowdown','hw_power_brake_slowdown','sw_thermal_slowdown')):return lane+'_thermal_or_power_brake'
  floor=float(g['memory.total'])*(.07 if lane=='flash' else .05 if lane=='image' else 0)
  if lane.startswith('qwen'):floor=16*1024
  if float(g['memory.free'])<floor:return lane+'_gpu_reserve'
  cg=row['cgroups'][lane]
  if cg['memory.swap.current']>0:return lane+'_owned_swap'
  if samples:
   old=samples[0]['cgroups'][lane]['events']
   if any(cg['events'].get(k,0)>old.get(k,0) for k in ('oom','oom_kill','max')):return lane+'_cgroup_oom_or_limit'
   initial=samples[0]['gpu'][uid]
   for field in ('ecc.errors.uncorrected.volatile.total','pcie.replay_counter'):
    a=numeric(g.get(field));b=numeric(initial.get(field))
    if a is not None and b is not None and a>b:return lane+'_'+field+'_increase'
 if len(samples)>=5:
  recent=samples[-5:]+[row]
  if all(any(b['swap'][k]>a['swap'][k] for k in ('pswpin','pswpout')) for a,b in zip(recent,recent[1:])):return 'sustained_swap_io_5_intervals'
 return None

def telemetry():
 try:
  while not done.is_set():
   start=time.monotonic();row=sample();reason=safety(row);samples.append(row);put('telemetry',row)
   if reason:cancel(reason)
   done.wait(max(.01,1-(time.monotonic()-start)))
 except BaseException as e:result['telemetry_error']=type(e).__name__;cancel('telemetry_failed')

def writer():
 while not done.wait(10):
  try:persist()
  except BaseException as e:result['writer_error']=type(e).__name__;cancel('checkpoint_failed');return

def collect_logs(start,end):
 for lane,name in NAMES.items():
  if lane not in LOGGABLE:continue
  p=subprocess.run(['docker','logs','--timestamps','--since',start,'--until',end,'--tail','500',name],capture_output=True,text=True,timeout=5)
  assert p.returncode==0,'native_log_read_failed:'+lane
  put('native-'+lane,{'poll_utc':end,'text':p.stdout+p.stderr})
 # Ada Docker logging is none. Existing owner unit journal may be empty; retain that fact.
 p=subprocess.run(['journalctl','-u','llm-image-api','--since',start,'--until',end,'--no-pager','-o','short-iso'],capture_output=True,text=True,timeout=5)
 assert p.returncode==0,'image_owner_journal_read_failed'
 put('native-image-owner',{'poll_utc':end,'text':p.stdout,'native_gpu_phase_available':False})
 p=subprocess.run(['journalctl','-k','--since',start,'--until',end,'--no-pager','-o','short-iso'],capture_output=True,text=True,timeout=5)
 assert p.returncode==0,'kernel_journal_read_failed'
 lines=[l for l in p.stdout.splitlines() if re.search(r'NVRM.*Xid|out of memory|oom-kill|PCIe.*(?:fatal|error)|AER:.*(?:fatal|uncorrected)',l,re.I)]
 put('kernel-window',{'utc':end,'text':p.stdout})
 if lines:put('kernel-errors',{'utc':end,'lines':lines});cancel('kernel_hardware_or_oom_error')

def native_logs():
 start=result['utc']
 while not done.wait(5):
  end=now()
  try:collect_logs(start,end);start=end
  except BaseException as e:result['native_log_error']=type(e).__name__;cancel('native_error_monitor_failed');return

def boundary_guard():
 with transaction() as (_,g):s.root_payload_guard();g.check_path(LOG)

def request(lane,index,payload):
 boundary_guard()
 if stop.is_set() or time.monotonic()>=result['submission_deadline_monotonic']:return False
 row={'index':index,'status':'OWNED_BEFORE_REQUEST','payload_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'owner_utc':now(),'max_tokens':payload.get('max_tokens')}
 result['requests'][lane].append(row)
 # Durable ownership for each submission, at request boundary only.
 with transaction() as (_,g):status(LOG+'/'+PREFIX+'-'+lane+'-'+str(index)+'-OWNER.json',row,g)
 if stop.is_set() or time.monotonic()>=result['submission_deadline_monotonic']:
  row['status']='NOT_SUBMITTED_DEADLINE';return False
 c=http.client.HTTPConnection('127.0.0.1',PORTS[lane],timeout=900);response=None
 timer=threading.Timer(900,lambda:cancel(lane+'_request_cap'));timer.daemon=True
 try:
  if lane!='image':payload={**payload,'stream':True,'stream_options':{'include_usage':True}}
  raw=json.dumps(payload).encode();row.update(start_utc=now(),start_monotonic=time.monotonic(),status='SUBMITTED',bytes=len(raw))
  active[lane]=(c,None);timer.start()
  c.request('POST','/v1/images/generations' if lane=='image' else '/v1/chat/completions',raw,{'Authorization':'Bearer '+key,'Content-Type':'application/json','X-Request-ID':PREFIX+'-'+lane+'-'+str(index)})
  row['body_sent_utc']=now();response=c.getresponse();active[lane]=(c,response)
  row.update(http_status=response.status,headers_utc=now());assert response.status==200,'http_status_'+str(response.status)
  if lane=='image':
   body=response.read(40*1024*1024+1);assert len(body)<=40*1024*1024,'image_response_bound'
   parsed=json.loads(body);encoded=parsed['data'][0]['b64_json'];png=base64.b64decode(encoded,validate=True)
   assert png[:8]==b'\x89PNG\r\n\x1a\n';w,h=struct.unpack('>II',png[16:24]);assert (w,h)==(1920,1080),'image_dimensions'
   row.update(response_end_utc=now(),response_end_monotonic=time.monotonic(),width=w,height=h,png_color_type=png[25],png_bit_depth=png[24],png_bytes=len(png),png_sha256=hashlib.sha256(png).hexdigest(),response_metadata={k:v for k,v in parsed.items() if k!='data'})
   with transaction() as (_,g):write_new(LOG+'/'+PREFIX+'-image-'+str(index)+'.png',png,g)
  else:
   row.update(content='',reasoning='',usage=None,finish_reason=None,done=False,first_delta_monotonic=None)
   total=0
   while True:
    line=response.readline(1024*1024+1);t=time.monotonic();utc=now();total+=len(line)
    assert len(line)<=1024*1024 and total<=16*1024*1024,'stream_bound'
    if not line:break
    put(lane+'-'+str(index)+'-sse',{'utc':utc,'monotonic':t,'line':line.decode('utf-8')})
    if not line.startswith(b'data:'):continue
    data=line[5:].strip()
    if data==b'[DONE]':row['done']=True;break
    obj=json.loads(data)
    if obj.get('usage'):row['usage']=obj['usage']
    for choice in obj.get('choices',[]):
     if choice.get('finish_reason') is not None:row['finish_reason']=choice['finish_reason']
     d=choice.get('delta',{});content=d.get('content') or '';reason=d.get('reasoning_content') or d.get('reasoning') or ''
     row['content']+=content;row['reasoning']+=reason
     if content or reason:
      if row['first_delta_monotonic'] is None:row.update(first_delta_monotonic=t,first_delta_utc=utc)
      row.update(last_delta_monotonic=t,last_delta_utc=utc)
   assert row['done'] and row['usage'] and row['finish_reason'],'incomplete_stream'
   expected=65536 if lane=='flash' else 262144
   assert row['usage']['prompt_tokens']==expected,'native_usage_count_mismatch'
   row['output_cap_reached']=row['finish_reason']=='length'
   row['correctness']='UNPROVEN_OUTPUT_CAP' if row['output_cap_reached'] else 'NOT_SCORED_LOAD_TEST'
  row['status']='COMPLETE'
 except BaseException as e:
  row.update(status='PARTIAL_OR_ERROR',error_type=type(e).__name__,error=str(e) if isinstance(e,AssertionError) else 'transport_or_capture_error');cancel(lane+'_request_failed_no_replay')
 finally:
  timer.cancel();c.close()
  if response:response.close()
  active.pop(lane,None);row.update(end_utc=now(),end_monotonic=time.monotonic())
  boundary_guard()
 return row['status']=='COMPLETE'

def lane_work(lane):
 try:
  prepared=FIXTURES[lane]
  barrier.wait(30)
  for index,item in enumerate(prepared):
   if stop.is_set() or time.monotonic()>=result['submission_deadline_monotonic']:break
   if not request(lane,index,item['payload']):break
 except BaseException as e:result.setdefault('lane_errors',{})[lane]=type(e).__name__;cancel(lane+'_lane_failed')

def main():
 global FIELDS,ENERGY_PATHS,FIXTURES,LOGGABLE
 tasks=[];background=[]
 try:
  assert not P(LOG,PREFIX+'.json').exists(),'existing_task_no_retry'
  result['before']=capture_identity()
  FIXTURES=json.loads(P(LOG,PREFIX+'-FIXTURES.json').read_text())
  result['fixtures']={lane:[{k:v for k,v in f.items() if k not in ('payload',)} for f in fs] for lane,fs in FIXTURES.items()}
  FIXTURES['image']=[{'payload':{'model':'qwen-image-2.1','prompt':f'A photorealistic wide landscape of a Slovenian alpine lake, island church, distant castle and mountains, natural autumn colors, crisp daylight, no lettering. Viewpoint variation {i}, with distinct natural reflections and shoreline trees.','size':'1920x1080','n':1,'background':'opaque','response_format':'b64_json','seed':202609270+i}} for i in range(8)]
  x=ET.fromstring(run(['nvidia-smi','-q','-x']))
  result['nvidia_before_xml']=ET.tostring(x,encoding='unicode')
  LOGGABLE=[];result['native_log_capability']={}
  for lane,name in NAMES.items():
   v=json.loads(run(['docker','inspect',name]))[0];cg=P('/proc',str(v['State']['Pid']),'cgroup').read_text().split('::')[1].strip();cgroups[lane]=P('/sys/fs/cgroup'+cg)
   assert int((cgroups[lane]/'memory.swap.current').read_text())==0
   result['native_log_capability'][lane]=v['HostConfig']['LogConfig']['Type']
   if v['HostConfig']['LogConfig']['Type']!='none':
    probe=subprocess.run(['docker','logs','--tail','1',name],capture_output=True,text=True,timeout=5)
    assert probe.returncode==0,'native_log_probe_failed'
    LOGGABLE.append(lane)
   gpu=next(g for g in x.findall('gpu') if g.findtext('uuid')==GPUS[lane])
   temp=gpu.findtext('temperature/gpu_temp_slow_threshold') or ''
   match=re.search(r'\d+',temp);limits[lane]=min(85,int(match.group())) if match else 85
  supported=[];unsupported=[]
  for field in FIELDS:
   p=subprocess.run(['nvidia-smi','--query-gpu='+field,'--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
   (supported if p.returncode==0 else unsupported).append(field)
  FIELDS=supported;result.update(query_fields=FIELDS,unsupported_fields=unsupported,thermal_limits_c=limits)
  ENERGY_PATHS=list(P('/sys/class/powercap').glob('*/energy_uj'))
  result['bmc_devices_exposed']=[str(p) for p in P('/dev').glob('ipmi*')]
  result['cpu_package_power']='exposed energy counters' if ENERGY_PATHS else 'UNAVAILABLE: guest powercap and hwmon empty; no BMC device exposed'
  result['baseline']=sample();assert safety(result['baseline']) is None,'baseline_resource_failure';samples.append(result['baseline'])
  result['kernel_before']=run(['journalctl','-k','--since','-10min','--no-pager','-o','short-iso'])
  collect_logs(result['utc'],now())
  assert not result['cancel_reason'],'idle_full_telemetry_preflight_failed'
  result['full_idle_telemetry_preflight_utc']=now()
  persist()
  for fn in (telemetry,writer,native_logs):
   t=threading.Thread(target=fn,daemon=True);t.start();background.append(t)
  for lane in NAMES:
   t=threading.Thread(target=lane_work,args=(lane,),daemon=True);t.start();tasks.append(t)
  result.update(status='RUNNING',barrier_utc=now(),barrier_monotonic=time.monotonic())
  result['submission_deadline_monotonic']=result['barrier_monotonic']+300
  barrier.wait(30)
  hard=result['barrier_monotonic']+1170
  while any(t.is_alive() for t in tasks):
   if time.monotonic()>=hard:cancel('hard_job_cap');break
   time.sleep(.25)
  for t in tasks:t.join(5)
  result['client_threads_settled']=not any(t.is_alive() for t in tasks)
  time.sleep(3)
  result['after']=capture_identity()
  result['connections_after']=run(['ss','-H','-nt4','state','established','( sport = :30010 or sport = :30002 or sport = :30004 or sport = :30006 )'])
  result['nvidia_after_xml']=run(['nvidia-smi','-q','-x'])
  result['status']='COMPLETE' if not result['cancel_reason'] and result['client_threads_settled'] else 'PARTIAL_OR_CANCELLED'
 except BaseException as e:
  result.update(status='FAILED',error_type=type(e).__name__,error=str(e) if isinstance(e,AssertionError) else 'task_error');cancel('job_exception')
 finally:
  done.set()
  for t in background:t.join(15)
  result['end_utc']=now();result['end_monotonic']=time.monotonic()
  try:persist()
  except BaseException:pass
if __name__=='__main__':
 signal.signal(signal.SIGTERM,lambda *_:cancel('signal_termination'))
 main()
