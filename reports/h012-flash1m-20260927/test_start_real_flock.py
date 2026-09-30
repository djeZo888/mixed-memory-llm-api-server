"""Focused start regression: real canonical flock and real receipt filesystem.

Only unrelated storage/root identity and systemd operations use local seams.
Exercises the actual start(), Ops.transaction() and Ops.save() methods.
"""
import contextlib, importlib.util, json, os, sys, tempfile, threading, types
from pathlib import Path
from unittest import mock
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts'))
from common.lifecycle_lease import acquire_lease, LeaseBusy

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Guard:
 def __init__(self,*args):pass
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def check_path(self,*args):pass
class Anchor:
 def __init__(self,path,guard):self.path=Path(path)
 def __enter__(self):return self
 def __exit__(self,*args):pass
 @contextlib.contextmanager
 def open(self,name,flags,mode):
  fd=os.open(self.path/name,flags,mode)
  with os.fdopen(fd,'wb') as f:
   yield types.SimpleNamespace(write=f.write,fsync=lambda:(f.flush(),os.fsync(f.fileno())))
 def atomic_json(self,name,value):
  tmp=self.path/(name+'.tmp');tmp.write_text(json.dumps(value));os.replace(tmp,self.path/name)

def exercise(path,mode):
 m=load(path,'manual_'+mode)
 with tempfile.TemporaryDirectory() as d:
  root=Path(d).resolve();os.chmod(root,0o700);log=root/'log';log.mkdir();stage=root/'stage';stage.mkdir();(stage/'candidate-sha256.json').write_text('{}');boot=root/'boot';boot.write_text('fixture-boot')
  acquire=lambda **kw:acquire_lease(system_root=root,trusted_uid=os.getuid(),**kw)
  o=object.__new__(m.Ops);o.lease=None;o.write_lock=threading.RLock();o.acquire=acquire;o.Guard=Guard;o.Anchor=Anchor;o.storage=types.SimpleNamespace(root_payload_guard=lambda:None);o.owner=types.SimpleNamespace(MODEL=str(root/'model'));o.stage_hash='fixture';o.idle_precondition=lambda:None;o.original=lambda:({},{},{})
  calls=[]
  def dispatch(argv,timeout):
   calls.append(argv);o.lease.validate()
   try:
    with acquire(blocking=False):raise AssertionError('canonical lease released during dispatch')
   except LeaseBusy:pass
   if mode=='dispatch_error':raise RuntimeError('controlled_systemd_failure')
   return ''
  def mapped_path(*args):return boot if args==('/proc/sys/kernel/random/boot_id',) else Path(*args)
  ownerpath=log/(m.PREFIX+'-OWNER.json')
  if mode=='existing_owner':ownerpath.write_text('{"preserved":true}')
  with mock.patch.object(m,'Ops',return_value=o),mock.patch.object(m,'LOG',str(log)),mock.patch.object(m,'STAGE',str(stage)),mock.patch.object(m,'Path',side_effect=mapped_path),mock.patch.object(m,'protected',side_effect=lambda p,*args:Path(p).read_bytes()),mock.patch.object(m,'run',side_effect=dispatch):
   try:result=m.start(True)
   except Exception as exc:
    expected={'original':LeaseBusy,'dispatch_error':RuntimeError,'existing_owner':ValueError}.get(mode)
    assert expected and isinstance(exc,expected),(mode,type(exc));result={'exception':type(exc).__name__}
   else:assert mode=='corrected' and result['status']=='DISPATCHED'
  assert o.lease is None,'borrowed lease not reset'
  with acquire(blocking=False) as lease:lease.validate()
  if mode=='original':assert not ownerpath.exists() and not calls
  if mode=='corrected':assert len(calls)==1 and json.loads(ownerpath.read_text())['status']=='DISPATCHED'
  if mode=='dispatch_error':assert len(calls)==1 and json.loads(ownerpath.read_text())['status']=='OWNED_BEFORE_DISPATCH'
  if mode=='existing_owner':assert not calls and ownerpath.read_text()=='{"preserved":true}'
  return {'case':mode,'status':'PASS','real_canonical_flock':True,'real_receipt_files':True,'result':result.get('status',result.get('exception'))}
if __name__=='__main__':
 old=Path(sys.argv[1]);new=Path(sys.argv[2]);print(json.dumps([exercise(old,'original')]+[exercise(new,x) for x in ['corrected','dispatch_error','existing_owner']],indent=2))
