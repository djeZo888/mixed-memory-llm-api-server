import os,sys,json,time,hashlib,pathlib,subprocess,contextlib,datetime
P=pathlib.Path
ROOT='/usr/local/lib/llm-server/control-api'
GUARDS={'scripts/common/registered-storage.py':'21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d','scripts/install/storage.py':'4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505','scripts/install/storage_io.py':'5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a','scripts/common/lifecycle_lease.py':'483ba038c62a8b4633449cef9c0f9a6664c00276662498abc748b58c8be644e0'}
for n,h in GUARDS.items():assert hashlib.sha256(P(ROOT,n).read_bytes()).hexdigest()==h,'installed_guard_mismatch'
sys.path.insert(0,ROOT+'/scripts')
from install.storage import Storage
from install.storage_io import MountedStorageGuard,AnchoredRoot
from common.lifecycle_lease import acquire_lease,LeaseBusy
class Runner:
 def run(self,argv,*,timeout=30,env=None):return subprocess.check_output(argv,timeout=timeout,text=True,env=env)
r=Storage({},Runner()).read_registration()
s=Storage({'data_dir':r['data']['path'],'data_uuid':r['data']['uuid'],'model_dir':r['models']['path'],'model_uuid':r['models']['uuid'],'storage_mode':r['storage_mode']},Runner())
@contextlib.contextmanager
def transaction():
 deadline=time.monotonic()+90
 while True:
  try:
   ctx=acquire_lease(blocking=False);lease=ctx.__enter__();break
  except LeaseBusy:
   if time.monotonic()>deadline:raise
   time.sleep(.25)
 try:
  with MountedStorageGuard(s) as guard:yield lease,guard
 finally:ctx.__exit__(None,None,None)
def write_new(path,raw,guard):
 path=P(path)
 with AnchoredRoot(str(path.parent),guard) as a:
  with a.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as f:
   for i in range(0,len(raw),1024*1024):f.write(raw[i:i+1024*1024])
   f.fsync()
def status(path,value,guard):
 with AnchoredRoot(str(P(path).parent),guard) as a:a.atomic_json(P(path).name,value)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
