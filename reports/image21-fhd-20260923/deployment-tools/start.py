"""Start reviewed API owner once; only readiness GETs follow normal warm."""
import hashlib,json,stat,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,'/data/services/image21-runtime-20260923/source')
from service import Runtime,acquire_lease,require,storage_io,protected_file
r=Runtime();base=Path('/data/services/image21-fhd-20260923')
with acquire_lease(blocking=False):
 r.guards();r.verify_resident(r.state());r.check_network(r.state())
 installed=r.binding.read_json('services',str(base/'installed.json'))
 for p,digest in installed['files'].items():require(hashlib.sha256(protected_file(Path(p))).hexdigest()==digest,'installed_source_mismatch')
# API child is sole recovery owner; release canonical lease before systemd call.
p=subprocess.run(['systemctl','start','llm-image-api.service'],capture_output=True,timeout=30)
require(p.returncode==0,'api_start_failed')
key=protected_file(Path('/data/services/secrets/llm-api-key'),maximum=257).strip().decode('ascii')
def get(route):
 req=urllib.request.Request('http://127.0.0.1:30006'+route,headers={'Authorization':'Bearer '+key})
 with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
for _ in range(100):
 try:
  ready=get('/health/ready')
  if ready['ready'] and ready['admitting'] and not ready['busy']:break
 except Exception:pass
 time.sleep(2)
else:raise RuntimeError('readiness_not_observed_no_retry')
with acquire_lease(blocking=False):
 r.guards();s=r.state();resident=r.verify_resident(s);r.check_network(s)
 cap=get('/v1/image-capabilities')
 require(cap['limits']['max_width']==1920 and cap['limits']['max_height']==1080 and cap['limits']['native_max_pixels']==2088960,'capability_limits_mismatch')
 ck=Path('/run/credentials/llm-image-api.service/inference-key').stat()
 require((ck.st_uid,ck.st_gid,stat.S_IMODE(ck.st_mode))==(0,0,0o440),'credential_metadata_changed')
 receipt={'status':'READY_AFTER_ONE_NORMAL_RECONCILIATION','source_commit':installed['source_commit'],'readiness':ready,'capabilities':cap,'backend_container':s['container'],'backend_run_id':s['run_id'],'runtime_config_sha256':hashlib.sha256(protected_file(Path('/data/services/image21-runtime-20260923/config.json'))).hexdigest(),'credential':{'uid':ck.st_uid,'gid':ck.st_gid,'mode':'0440'},'normal_warm':{k:s.get(k) for k in ['warm','phase','start_utc','completed_utc','generation','tmp_new_entries_after_generation']},'before_acceptance_tmp':r.tmp_snapshot(s['run_id']),'source_files':installed['files']}
 with r.binding.mounted_guard(storage_io) as g:
  with storage_io.AnchoredRoot(str(base),g) as a:a.atomic_json('ready.json',receipt)
 r.guards()
print(json.dumps({'status':receipt['status'],'readiness':ready,'backend_run_id':s['run_id'],'backend_container':s['container'],'lease':'released'}))
