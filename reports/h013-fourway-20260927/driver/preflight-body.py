# Exact candidate definitions already loaded, no main() call and no file writes on VM.
out={'utc':now(),'status':'PREPARING','no_inference':True,'blockers':[],'native':{},'collector_status':{}}
assert r['data']['uuid']=='8daf56f1-5649-4163-9d87-919c2d271875'
assert r['models']['uuid']=='a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
s.root_payload_guard()
with MountedStorageGuard(s) as g:
 for path in [LOG,'/data/services/image21-runtime-20260923','/data/models-large/glm-5.3-flash-eb9eb208','/data/docker','/data/containerd']:g.check_path(path)
 for path,digest in PARAMETERS['source_matches'].items():assert hashlib.sha256(P(path).read_bytes()).hexdigest()==digest,'source_changed:'+path
out['guard']='PASS';out['sources_verified']=len(PARAMETERS['source_matches']);out['boot']=P('/proc/sys/kernel/random/boot_id').read_text().strip();assert out['boot']==PARAMETERS['boot']
LOGGABLE=[]
xml=ET.fromstring(run(['nvidia-smi','-q','-x']));out['gpu_xml']=ET.tostring(xml,encoding='unicode')
for lane,name in NAMES.items():
 proc=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=10)
 if proc.returncode:
  out['blockers'].append(lane+'_container_absent');out['native'][lane]={'container':'ABSENT'};continue
 v=json.loads(proc.stdout)[0];assert v['State']['Running'] and not v['State']['OOMKilled']
 PARAMETERS['containers'][lane]={k:v[k] for k in ['Id','Image']};PARAMETERS['containers'][lane]['StartedAt']=v['State']['StartedAt']
 PARAMETERS['container_policy'][lane]={k:v['HostConfig'][k] for k in ('CpusetCpus','CpusetMems','Memory','MemorySwap','RestartPolicy','DeviceRequests','NetworkMode')}
 cg=P('/proc',str(v['State']['Pid']),'cgroup').read_text().split('::')[1].strip();cgroups[lane]=P('/sys/fs/cgroup'+cg)
 logging=v['HostConfig']['LogConfig']['Type']
 if logging!='none':
  probe=subprocess.run(['docker','logs','--tail','1',name],capture_output=True,text=True,timeout=5);assert probe.returncode==0,'native_log_probe_failed';LOGGABLE.append(lane)
 gpu=next(g for g in xml.findall('gpu') if g.findtext('uuid')==GPUS[lane]);match=re.search(r'\d+',gpu.findtext('temperature/gpu_temp_slow_threshold') or '');limits[lane]=min(85,int(match.group())) if match else 85
 if lane!='image':
  ready=control(lane,'/v1/readiness');assert ready['ready']
  info=control(lane,'/get_server_info');cap={k:next((x[k] for x in [info,*info.get('internal_states',[])] if k in x),None) for k in PARAMETERS['capacities'][lane]};assert cap==PARAMETERS['capacities'][lane],'native_capacity_mismatch:'+lane
  out['native'][lane]={'ready':ready,'capacity':cap,'log_driver':logging}
 else:out['native'][lane]={'ready':control(lane,'/health/ready'),'log_driver':logging}
out['image_capabilities']=control('image','/v1/image-capabilities')
if not out['image_capabilities']['ready']:out['blockers'].append('image_API_not_ready')
assert len(out['image_capabilities']['profiles'])==9
supported=[];unsupported=[]
for field in FIELDS:
 p=subprocess.run(['nvidia-smi','--query-gpu='+field,'--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
 (supported if p.returncode==0 else unsupported).append(field)
FIELDS=supported;out['query_fields']=FIELDS;out['unsupported_fields']=unsupported;PARAMETERS['query_fields']=FIELDS
FAN_READER=FanReader();ENERGY_PATHS=list(P('/sys/class/powercap').glob('*/energy_uj'))
try:
 for index in range(3):
  row=sample();samples.append(row)
  if index<2:time.sleep(1)
 out['samples']=samples
 for uid,v in samples[-1]['gpu'].items():
  assert v['ecc.mode.current']=='Disabled' and v['ecc.mode.pending']=='Disabled';PARAMETERS['power_limits'][uid]=float(v['power.limit'])
 if not out['blockers']:
  for row in samples:assert safety(row) is None,safety(row)
 else:
  out['collector_status']['image_native_cgroup']='BLOCKED_ABSENT_BACKEND'
  assert all(cg['memory.swap.current']==0 for row in samples for cg in row['cgroups'].values())
 collect_logs(out['utc'],now());assert not result['cancel_reason'],result['cancel_reason']
 out['collector_buffers']=buffers
 out['collector_status'].update(gpu_clock_power_ECC='PASS_ALL4',NVML_five_integrated_fans_RPM_intended='PASS',text_native_logs='PASS',image_supported_API_journal='PASS',kernel='PASS',host_cpu_ram_pressure='PASS',text_cgroups='PASS',Ada_docker_logs='SKIPPED_NONE_SUPPORTED_PATH_ONLY')
finally:FAN_READER.close()
# Exact owner modules/config imports are preflighted before warm or main.
import importlib.util,types
from lifecycle.manager import load_manager
manager=load_manager(types.SimpleNamespace(instance=None),P(ROOT)/'configs')
state=manager.read_state()
for lane,target in [('qwen0','glm'),('qwen1','qwen')]:
 assert state['slots'][target]['container']['id']==PARAMETERS['containers'][lane]['Id']
 manager.trusted_container(state['slots'][target]['container'])
for name,path in [('image','/data/services/image21-runtime-20260923/source/service.py'),('flash','/data/services/flash-h008-20260926/source/owner.py')]:
 spec=importlib.util.spec_from_file_location('h013_preflight_'+name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 if name=='image' and not out['blockers']:
  owner=module.Runtime();owner.inspect_owned(owner.state())
 if name=='flash':
  cfg=json.loads(P(module.BASE+'/config.json').read_text());st=json.loads(P(module.BASE+'/state.json').read_text())
  module.validate_container(json.loads(run(['docker','inspect',PARAMETERS['containers']['flash']['Id']]))[0],cfg,st)
out['collector_status']['exact_owner_imports_and_readonly_validation']='PASS'
out['parameters']=PARAMETERS
out['status']='BLOCKED_IMAGE_RECOVERY' if out['blockers'] else 'FULL_PREFLIGHT_PASS'
s.root_payload_guard();print(json.dumps(out,indent=2))

