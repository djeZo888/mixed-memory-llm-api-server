import datetime,os,subprocess,sys,time
sys.path.insert(0,'/data/services/image21-reference-20260923/source')
from remote_common import *
r.guards();start=time.monotonic()
with anchor(BASE) as a:
 with m.acquire_lease(blocking=False):
  before=qwens();resident=r.verify_resident(r.state())
  a.atomic_json('build-start.json',{'utc':m.now(),'session_id':SESSION,'qwens':before,'sglang':resident})
 with anchor(BUILD) as b:
  with b.open('build.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as log:
   deadline=datetime.datetime.fromisoformat('2026-09-23T03:55:56.581908+00:00')
   remaining=(deadline-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
   assert remaining>0
   # GPU-free build; canonical lease deliberately released during independent build.
   result=subprocess.run(['docker','build','--pull=false','--cpuset-cpus','8-15','--memory','96g','--memory-swap','96g','--label','io.llm-reference.owner='+TASK,'--iidfile',str(BUILD/'image-id.txt'),'-t','local/qwen-image21-reference:8b3c707-20260923',str(BUILD)],stdout=log.fileno(),stderr=subprocess.STDOUT,timeout=remaining,env={**os.environ,'DOCKER_BUILDKIT':'0'})
   log.fsync()
  b.check()
 with m.acquire_lease(blocking=False):
  r.guards();assert qwens()==before;r.verify_resident(r.state())
  receipt={'status':'built' if result.returncode==0 else 'build_failed','returncode':result.returncode,'elapsed_seconds':time.monotonic()-start,'utc':m.now(),'qwens_unchanged':True,'sglang_still_warm':True}
  if result.returncode==0:receipt['image_id']=(BUILD/'image-id.txt').read_text().strip()
  a.atomic_json('build-result.json',receipt);print(json.dumps(receipt),flush=True)
  r.guards()
 sys.exit(result.returncode)
