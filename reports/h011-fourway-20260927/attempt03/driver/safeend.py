from pathlib import Path
import subprocess,json
common=Path('../tools/vm-common.py').read_text();expected=json.loads(Path('../evidence/FINAL-IDENTITY.json').read_text())['source_matches']
remote=common+'\nEXPECTED='+repr(expected)+r'''
import importlib.util
base='/data/services/flash-h008-20260926';log='/data/logs/flash-h008-20260926';name='llm-frontier-flash';gpu='GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
receipt={'utc':now(),'scope':'Direct phase03 safe-end recovery only; no subsequent stress','status':'PREPARING'}
def inspect(n):return json.loads(subprocess.check_output(['docker','inspect',n],text=True))[0]
def identity(v):return {'Id':v['Id'],'Image':v['Image'],'State':v['State']}
with transaction() as (lease,g):
 s.root_payload_guard();g.check_path(base);g.check_path(log)
 for p,h in EXPECTED.items():assert hashlib.sha256(P(p).read_bytes()).hexdigest()==h,'source_changed:'+p
 job=json.loads(P(log+'/H011-FOURWAY03.json').read_text());assert job['cancel_reason'] or job['status'] in ['FAILED','PARTIAL_OR_CANCELLED'],'safeend_only_on_failed_test'
 receipt['test_status']={k:job.get(k)for k in ['status','cancel_reason','cancel_utc','end_utc']}
 receipt['pre_action_gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,power.draw,utilization.gpu,temperature.gpu,fan.speed,memory.free,clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.hw_power_brake_slowdown','--format=csv,noheader,nounits'],text=True)
 receipt['pre_action_gpu_processes']=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True)
 p=subprocess.run(['docker','logs','--timestamps','--since','2026-09-27T01:34:35Z',name],capture_output=True,text=True);receipt['pre_action_native_logs']=p.stdout+p.stderr
 receipt['pre_action_kernel']=subprocess.check_output(['journalctl','-k','--since','2026-09-27T01:34:35Z','--no-pager','-o','short-iso'],text=True)
 before=inspect(name);assert before['Id']=='2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab';receipt['before']=identity(before)
 others=['llmctl-qwen38-27b-q0-480000-yarn4-bf16kv','llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv','llm-image-backend'];receipt['others_before']={n:identity(inspect(n))for n in others}
 spec=importlib.util.spec_from_file_location('original_owner',base+'/source/owner.py');owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
 owner.validate_container(before,json.loads(P(base+'/config.json').read_text()),json.loads(P(base+'/state.json').read_text()))
 receipt['halt_needed']=before['State']['Running'];receipt['halt_start_utc']=now();status(log+'/H011-SAFEEND03.json',receipt,g)
 if receipt['halt_needed']:owner.operate('halt',borrowed=lease)
 receipt['halt_end_utc']=now();stopped=inspect(name);receipt['stopped']=identity(stopped);assert not stopped['State']['Running'] and stopped['State']['Pid']==0
 processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True);receipt['gpu_processes_stopped']=processes;assert not any(l.split(',')[0].strip()==gpu for l in processes.splitlines()),'flash_gpu_not_released'
 latch=json.loads(P('/data/services/llm-manager/hardware-latch.json').read_text());receipt['hardware_latch']=latch # Original owner's HardwarePolicy validates this Flash target; never clear any latch.
 receipt['resume_start_utc']=now();status(log+'/H011-SAFEEND03.json',receipt,g);owner.operate('resume',borrowed=lease);receipt['resume_end_utc']=now()
 after=inspect(name);receipt['after_start']=identity(after);assert after['Id']==before['Id'] and after['State']['Running']
 receipt['others_after']={n:identity(inspect(n))for n in others};assert receipt['others_after']==receipt['others_before'],'other_service_changed'
 receipt['status']='STARTED_LOADING_NO_MORE_INFERENCE';status(log+'/H011-SAFEEND03.json',receipt,g);s.root_payload_guard()
print(json.dumps(receipt))
'''
Path('../tools/safeend03-remote.py').write_text(remote)
r=subprocess.run(['ssh','-T','ai-vm','sudo -n python3 -I -B -'],input=remote.encode(),capture_output=True,timeout=150);Path('../evidence/SAFEEND03.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr.decode()[-1000:];Path('../evidence/SAFEEND03.json').write_bytes(r.stdout);x=json.loads(r.stdout);print({k:x[k]for k in ['status','halt_needed','halt_start_utc','halt_end_utc','resume_start_utc','resume_end_utc']})
