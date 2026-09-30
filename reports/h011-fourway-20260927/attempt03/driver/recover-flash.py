from pathlib import Path
import json,subprocess
common=Path('../tools/vm-common.py').read_text();expected=json.loads(Path('../evidence/FINAL-IDENTITY.json').read_text())['source_matches']
remote=common+'\nEXPECTED='+repr(expected)+r'''
import importlib.util
base='/data/services/flash-h008-20260926';log='/data/logs/flash-h008-20260926'
name='llm-frontier-flash';gpu='GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
others=['llmctl-qwen38-27b-q0-480000-yarn4-bf16kv','llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv','llm-image-backend']
def inspect(n):return json.loads(subprocess.check_output(['docker','inspect',n],text=True))[0]
def identity(v):return {'Id':v['Id'],'Image':v['Image'],'State':v['State']}
receipt={'utc':now(),'action':'original_owner_resume','halt_performed':False,'inference':False,'profile_change':False}
with transaction() as (lease,g):
 s.root_payload_guard()
 for p,h in EXPECTED.items():assert hashlib.sha256(P(p).read_bytes()).hexdigest()==h,'source_drift:'+p
 g.check_path(base);g.check_path(log)
 before=inspect(name);receipt['before']=identity(before)
 latch=json.loads(P('/data/services/llm-manager/hardware-latch.json').read_text());receipt['hardware_latch']=latch;assert not latch.get('targets'),'hardware_latch_present_no_clear'
 gpu_idle=subprocess.check_output(['nvidia-smi','--id=GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528','--query-gpu=uuid,temperature.gpu,utilization.gpu,fan.speed','--format=csv,noheader,nounits'],text=True);receipt['server_idle_before']=gpu_idle
 values=[v.strip()for v in gpu_idle.strip().split(',')];assert float(values[1])<60 and float(values[2])==0,'server_not_cooled_idle'
 assert before['Id']=='2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab'
 assert not before['State']['Running'] and before['State']['Pid']==0,'do_not_recycle_running_service'
 processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True)
 receipt['gpu_compute_processes_before']=processes
 assert not any(line.split(',')[0].strip()==gpu for line in processes.splitlines()),'flash_gpu_processes_remain'
 receipt['others_before']={n:identity(inspect(n)) for n in others}
 assert all(v['State']['Running'] for v in receipt['others_before'].values())
 spec=importlib.util.spec_from_file_location('h011_original_owner',base+'/source/owner.py');owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
 state=json.loads(P(base+'/state.json').read_text());config=json.loads(P(base+'/config.json').read_text());owner.validate_container(before,config,state)
 assert state['desired']=='running'
 receipt.update(status='OWNED_BEFORE_RESUME',resume_start_utc=now());status(log+'/H011-RECOVERY03.json',receipt,g)
 owner.operate('resume',borrowed=lease)
 after=inspect(name);receipt['after_start']=identity(after)
 assert after['Id']==before['Id'] and after['Image']==before['Image'] and after['State']['Running']
 receipt['others_after']={n:identity(inspect(n)) for n in others}
 assert receipt['others_before']==receipt['others_after'],'other_service_changed'
 receipt.update(status='STARTED_LOADING',resume_end_utc=now(),same_container_resumed=True,container_recreated=False)
 status(log+'/H011-RECOVERY03.json',receipt,g);s.root_payload_guard()
print(json.dumps(receipt))
'''
Path('../tools/recover-flash03-remote.py').write_text(remote)
r=subprocess.run(['ssh','-T','ai-vm','sudo -n python3 -I -B -'],input=remote.encode(),capture_output=True,timeout=120);Path('../evidence/RECOVERY03.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr.decode()[-1500:]
Path('../evidence/RECOVERY03.json').write_bytes(r.stdout);x=json.loads(r.stdout);print({k:x[k] for k in ['status','resume_start_utc','resume_end_utc','same_container_resumed','container_recreated']})
