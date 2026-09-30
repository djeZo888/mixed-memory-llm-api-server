"""Actual interprocess canonical flock contention; fixture-only status I/O."""
import ast,contextlib,json,os,pathlib,subprocess,sys,tempfile,unittest
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from common.lifecycle_lease import acquire_lease,LeaseBusy
HERE=pathlib.Path(__file__).parent

def function(path,name,namespace):
 tree=ast.parse(path.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
 return namespace[name]

class ContentionTest(unittest.TestCase):
 def test_status_writes_do_not_take_child_lifecycle_lease(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td); log=root/'logs';log.mkdir();uid=os.getuid()
   childcode="import sys,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from common.lifecycle_lease import acquire_lease\nwith acquire_lease(system_root=Path(sys.argv[2]),trusted_uid=int(sys.argv[3])):\n print('HELD',flush=True);sys.stdin.read(1)"
   child=subprocess.Popen([sys.executable,'-c',childcode,str(ROOT),str(root),str(uid)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
   try:
    self.assertEqual(child.stdout.readline().strip(),'HELD');events=[]
    @contextlib.contextmanager
    def guard(_):
     events.append('guard_enter');yield None;events.append('guard_exit')
    class Anchor:
     def __init__(self,path,g):self.path=pathlib.Path(path);self.path.mkdir(exist_ok=True)
     def __enter__(self):events.append('anchor_enter');return self
     def __exit__(self,*a):events.append('anchor_exit')
     def atomic_json(self,name,value):
      tmp=self.path/(name+'.tmp');tmp.write_text(json.dumps(value));tmp.replace(self.path/name)
    @contextlib.contextmanager
    def transaction():
     with acquire_lease(blocking=False,system_root=root,trusted_uid=uid):yield None
    h=SimpleNamespace(s=SimpleNamespace(root_payload_guard=lambda:events.append('root_guard')),MountedStorageGuard=guard,AnchoredRoot=Anchor,transaction=transaction)
    # The old status pattern really contends with the other process.
    with self.assertRaises(LeaseBusy):
     with h.transaction():pass
    ns={'LOG':log,'utc':lambda:'fixture'}
    function(HERE/'controller.py','save',ns)(h,{'status':'fixture'})
    for profile in ['r10-spread02','r11-local02']:
     function(HERE/profile/'launch_profile.py','save_status',{'LOG':log})(h,profile+'.json',{'status':'fixture'})
    self.assertEqual(len(list(log.glob('*.json'))),3)
    self.assertEqual(events.count('root_guard'),6)
    # Status writes did not release/bypass the actual child-owned canonical lock.
    with self.assertRaises(LeaseBusy):
     with acquire_lease(blocking=False,system_root=root,trusted_uid=uid):pass
   finally:
    child.stdin.write('x');child.stdin.flush();child.wait(timeout=5);child.stdin.close();child.stdout.close()
   with acquire_lease(blocking=False,system_root=root,trusted_uid=uid):pass
if __name__=='__main__':unittest.main()
