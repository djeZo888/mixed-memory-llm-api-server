"""Read-only service verification plus guarded task receipt; no inference."""
import sys
sys.path.insert(0,'/data/services/image21-reference-20260923/source')
from remote_common import *
r.guards()
with m.acquire_lease(blocking=False):
 prior=json.loads((BASE/'trial.json').read_text())
 assert qwens()==prior['before_qwens']
 state=r.state();assert state['phase']=='warm' and state['warm'] is True
 resident=r.verify_resident(state)
 trial=json.loads(m.run(['docker','inspect',prior['container_id']]).stdout)[0]
 assert not trial['State']['Running'] and trial['State']['Pid']==0
 assert trial['Config']['Labels']['io.llm-reference.session']==SESSION
 receipt={'utc':m.now(),'session_id':SESSION,'status':'REFERENCE_BLOCKED_SGLANG_RESTORED_WARM','qwens_unchanged':True,'qwens':qwens(),'sglang':resident,'sglang_image_id':r.config['image_id'],'sglang_run_id':state['run_id'],'sglang_unit':m.run(['systemctl','show',m.UNIT,'-p','ActiveState','-p','SubState','-p','UnitFileState']).stdout,'reference_container':{'id':trial['Id'],'state':trial['State']},'reference_gpu_context_released':True,'recovery_generation_count':1,'additional_reference_attempts':0,'retained_reference_image_id':prior['image_id'],'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'source').iterdir() if p.is_file()},'gpu_processes':m.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits']).stdout}
 r.guards()
receipt['canonical_lease_released']=True
with anchor(BASE) as a:a.atomic_json('final-verification.json',receipt)
r.guards();print(json.dumps(receipt),flush=True)
