import hashlib,json,pathlib
from PIL import Image
root=pathlib.Path('.')
pre=json.loads((root/'artifacts/resume-preflight.json').read_text());post=json.loads((root/'artifacts/post-d06-preflight.json').read_text())
assert post['ready']=={'status':200,'body':{'ready':True,'busy':False,'admitting':True,'state':'ready'}}
for key in ('runtime_config_sha256','phase','warm','run_id','container','containers','tmp','units'):
 assert pre[key]==post[key],key
assert pre['capabilities']==post['capabilities'];assert post['guards']=='pass'
assert [p[:2] for p in pre['resident']['gpu_processes']]==[p[:2] for p in post['resident']['gpu_processes']]
assert all(p['operation']=='generation' for p in post['capabilities']['body']['profiles'])
assert len(post['capabilities']['body']['profiles'])==6
ledger=json.loads((root/'DIAGNOSTIC-LEDGER.json').read_text());assert ledger['actual_gpu_requests']==5 and ledger['remaining']==1
pixels=[]
for prefix in ('d05','d06'):
 raw=Image.open(root/('artifacts/'+prefix+'-raw-output.png'));rgb=Image.open(root/('artifacts/'+prefix+'-delivered-rgb.png'))
 assert raw.size==rgb.size==(1024,1024) and rgb.mode=='RGB' and rgb.format=='PNG' and raw.convert('RGB').tobytes()==rgb.tobytes()
 pixels.append({'case':prefix,'opaque_rgb':True,'native_rgb_pixels_identical':True,'size':[1024,1024]})
assert (root/'artifacts/d06-input.png').read_bytes()==(root/'artifacts/d04-delivered-rgb.png').read_bytes()
result={'status':'PASS','scope':'Read-only readiness receipt comparison and CPU artifact integrity; no additional model call or source test suite.','utc':post['utc'],'generation_ready':post['ready'],'six_generation_profiles_unchanged':True,'public_edit_profiles':0,'runtime_config_sha256':post['runtime_config_sha256'],'container_id':post['container']['id'],'native_gpu_uuid_pid':[p[:2] for p in post['resident']['gpu_processes']],'api_and_text_identities_unchanged':True,'containers':post['containers'],'units':post['units'],'runtime_spool_unchanged':True,'guards':post['guards'],'canonical_lease':post['canonical_lease'],'pixel_delivery':pixels,'d06_exact_d04_input_bytes':True,'actual_gpu_requests':5,'remaining_reserved':1}
(root/'artifacts/final-readiness-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
