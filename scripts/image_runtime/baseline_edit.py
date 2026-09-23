"""One worker-only edit after parent has visually accepted generated reference."""
import importlib.util,json,os,pathlib,subprocess,time
BASE=pathlib.Path('/data/services/image21-runtime-20260923')
spec=importlib.util.spec_from_file_location('runtime',BASE/'source/service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.OPERATION_DEADLINE=time.monotonic()+840
r=m.Runtime();sampler=None
with m.acquire_lease(blocking=False):
 r.guards();s=r.state();assert s['phase']=='warm' and s['warm'] is True
 assert m.run(['systemctl','show','llm-image-api.service','-p','LoadState','--value']).stdout.strip()=='not-found'
 before=r.verify_resident(s);cid=s['container']['id'];rid=s['run_id'];tmp_before=r.tmp_snapshot(rid)
 rel='receipts/'+rid+'-edit-telemetry.jsonl';start=time.monotonic()
 try:
  with r.anchor() as a:
   with a.open(rel,os.O_WRONLY|os.O_CREAT|os.O_EXCL) as output:
    sampler=subprocess.Popen(['/usr/bin/python3','-I','-B',str(BASE/'source/telemetry.py'),'--output-fd',str(output.fileno()),'--output-path',str(BASE/rel),'--cgroup','/sys/fs/cgroup/system.slice/docker-'+cid+'.scope'],pass_fds=(output.fileno(),),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
     time.sleep(.4);m.require(sampler.poll() is None,'edit_telemetry_failed')
     r.guards();r.verify_resident(s)
     reply=m.run(['docker','exec',cid,'/opt/image-venv/bin/python','-I','-B','/runtime/native_request.py','--mode','edit','--run-id',rid],timeout=820)
     summary=json.loads(reply.stdout);m.require(summary['status']=='pass','native_edit_failed');after=r.verify_resident(s)
    finally:
     sampler_result=m.settle_sampler(sampler);output.fsync()
    m.require(sampler_result==0,'edit_telemetry_failed');a.check()
  records=[json.loads(line) for line in (BASE/rel).read_text().splitlines()];end=records[-1]
  m.require(end['sampled_min_free_bytes']*20>=before['device_current']['total_bytes'],'edit_device_peak_margin_below_5_percent')
  host=[x['host']['meminfo_bytes']['value']['values'] for x in records if x.get('host',{}).get('meminfo_bytes',{}).get('status')=='ok']
  swap=[x['host']['cgroup_bytes']['memory.swap.current']['value'] for x in records if x.get('host',{}).get('cgroup_bytes',{}).get('memory.swap.current',{}).get('status')=='ok']
  m.require(host and all(v['MemAvailable']*100>=v['MemTotal']*15 for v in host),'edit_host_margin_below_15_percent')
  m.require(swap and max(swap)==0,'edit_swap_unavailable_or_observed')
  receipt={'status':'TRANSPORT_DECODE_AND_SAMPLED_MARGINS_PASS_VISUAL_PENDING','run_id':rid,'elapsed_seconds':time.monotonic()-start,'summary':summary,'telemetry_path':str(BASE/rel),'telemetry_summary':end,'before':before,'after':after,'sampled_min_host_available_bytes':min(v['MemAvailable'] for v in host),'sampled_max_swap_bytes':max(swap),'tmp_before':tmp_before,'tmp_after':r.tmp_snapshot(rid),'utc':m.now()}
  with r.anchor() as a:a.atomic_json('receipts/'+rid+'-edit.json',receipt)
  s.update(edit=receipt);r.save(s);r.guards();print(json.dumps(receipt),flush=True)
 except BaseException as error:
  m.OPERATION_DEADLINE=time.monotonic()+55
  m.settle_sampler(sampler)
  d=r.inspect_owned(s,missing_ok=True)
  if d and d['State']['Running']:m.run(['docker','stop','--time','30',cid],timeout=40)
  s.update(phase='failed',warm=False,edit_failure={'type':type(error).__name__,'code':str(error) if type(error) is RuntimeError else 'edit_failed','utc':m.now(),'telemetry_path':str(BASE/rel)})
  r.save(s);r.guards();raise
