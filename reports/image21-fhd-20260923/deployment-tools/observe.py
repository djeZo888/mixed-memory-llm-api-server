"""Lightweight post-acceptance receipt; no generation or memory sampling loop."""
import hashlib,json,stat,subprocess,sys,urllib.request
from pathlib import Path
from PIL import Image
sys.path.insert(0,'/data/services/image21-runtime-20260923/source')
from service import Runtime,acquire_lease,require,storage_io,protected_file
r=Runtime();base=Path('/data/services/image21-fhd-20260923')
output=Path('/data/services/image-api/examples/output/fhd-acceptance-lake-bled.png')
key=protected_file(Path('/data/services/secrets/llm-api-key'),maximum=257).strip().decode('ascii')
def get(route):
 req=urllib.request.Request('http://127.0.0.1:30006'+route,headers={'Authorization':'Bearer '+key})
 with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
with acquire_lease(blocking=False):
 r.guards();s=r.state();r.verify_resident(s);r.check_network(s)
 before=r.binding.read_json('services',str(base/'ready.json'))
 require(s['container']==before['backend_container'] and s['run_id']==before['backend_run_id'],'backend_changed_during_acceptance')
 after=r.tmp_snapshot(s['run_id']);names=lambda d:{x['path'] for x in d['entries']}
 ready=get('/health/ready');cap=get('/v1/image-capabilities')
 require(ready['ready'] and ready['admitting'] and not ready['busy'],'post_acceptance_not_settled')
 texts=[]
 prior=r.binding.read_json('services',str(base/'preflight.json'))
 for item in prior['text_containers']:
  proc=subprocess.run(['docker','inspect',item['id']],text=True,capture_output=True,check=True)
  c=json.loads(proc.stdout)[0]
  observed={'id':c['Id'],'started_at':c['State']['StartedAt'],'pid':c['State']['Pid']}
  require(c['State']['Running'] and observed==item,'original_text_changed')
  texts.append(observed)
 st=output.lstat();require(stat.S_ISREG(st.st_mode) and st.st_uid==1000 and st.st_nlink==1,'unsafe_acceptance_output')
 with Image.open(output) as image:
  image.load();decoded={'width':image.width,'height':image.height,'mode':image.mode,'format':image.format,'fully_decoded':True}
 require(decoded=={'width':1920,'height':1080,'mode':'RGB','format':'PNG','fully_decoded':True},'unexpected_delivered_png')
 decoded.update(sha256=hashlib.sha256(output.read_bytes()).hexdigest(),bytes=st.st_size,path=str(output),uid=st.st_uid,gid=st.st_gid)
 receipt={'status':'ONE_PUBLIC_FHD_ACCEPTANCE_SETTLED','source_commit':before['source_commit'],'public_calls':1,'output':decoded,'readiness':ready,'capabilities':cap,'backend_container':s['container'],'backend_run_id':s['run_id'],'text_containers':texts,'tmp_before':before['before_acceptance_tmp'],'tmp_after':after,'tmp_new_entries':sorted(names(after)-names(before['before_acceptance_tmp'])),'runtime_config_sha256':hashlib.sha256(protected_file(Path('/data/services/image21-runtime-20260923/config.json'))).hexdigest(),'native_elapsed_seconds':None,'native_elapsed_scope':'not returned by public API; no extra instrumentation','memory_benchmark':'NOT_RUN; unchanged qualified native1920x1088 workload','guards':'registered storage and root-disk guards passed before and after','lease':'released at script exit'}
 require(not receipt['tmp_new_entries'],'new_owned_tmp_entries_after_acceptance')
 with r.binding.mounted_guard(storage_io) as g:
  with storage_io.AnchoredRoot(str(base),g) as a:a.atomic_json('acceptance-observation.json',receipt)
 r.guards()
print(json.dumps({'status':receipt['status'],'output':decoded,'readiness':ready,'tmp_new_entries':receipt['tmp_new_entries'],'text_containers_unchanged':True,'lease':'released'}))
