# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[3]
 _loader = _root/'scripts/h044/vision_runtime/trusted_imports.py'
 _manifest = (_root/'SOURCE-MANIFEST.json') if str(_root).startswith('/opt/') else (_root.parent/'output/SOURCE-MANIFEST.json')
 _uid = 0 if str(_root).startswith('/opt/') else _o.geteuid()
 def _protected(p):
  if str(p)!=_o.path.realpath(p):raise ValueError('bootstrap_symlink')
  for a in [p,*p.parents]:
   z=a.lstat()
   if z.st_uid not in (0,_uid) or z.st_mode&0o022:raise ValueError('bootstrap_owner_mode')
  fd=_o.open(p,_o.O_RDONLY|_o.O_NOFOLLOW)
  try:
   z=_o.fstat(fd)
   if not _s.S_ISREG(z.st_mode) or z.st_uid!=_uid or z.st_nlink!=1 or z.st_size>1048576:raise ValueError('bootstrap_source')
   raw=_o.read(fd,1048577);q=_o.fstat(fd)
   if (z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)!=(q.st_dev,q.st_ino,q.st_size,q.st_mtime_ns,q.st_ctime_ns):raise ValueError('bootstrap_changed')
   return raw
  finally:_o.close(fd)
 _m=_j.loads(_protected(_manifest));_b=_protected(_loader);_record=_m['modules']['trusted_imports']
 if _record['path']!='scripts/h044/vision_runtime/trusted_imports.py' or _h.sha256(_b).hexdigest()!=_record['sha256'] or len(_b)!=_record['bytes']:raise ValueError('bootstrap_hash')
 _spec=_iu.spec_from_file_location('trusted_imports',_loader);_module=_iu.module_from_spec(_spec)
 import sys as _sys
 _sys.modules['trusted_imports']=_module;exec(compile(_b,str(_loader),'exec'),_module.__dict__)
 _module.install(_root,_m,_uid)

import json,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import control,service_supervisor as s
ROOT=Path(__file__).absolute().parents[3];OUT=ROOT.parent/'output'
class ScheduleTests(unittest.TestCase):
 def run_case(self,fail=None):
  graph=json.loads((OUT/'RUNTIME-GRAPH.json').read_text());now=time.time();go={'nonce':'1'*64,'bootId':'fixture','actions':['load','inference','stop'],'actionDeadlines':{k:__import__('datetime').datetime.fromtimestamp(now+n,__import__('datetime').timezone.utc).isoformat() for k,n in [('load',20),('inference',40),('stop',60)]}}
  actions=[];owners=[{'role':'interpretation'},{'role':'ocr'}]
  def load(*_):
   actions.append('load-both')
   if fail=='load':raise RuntimeError('fixture network/post-create/post-start failure')
   return owners
  def stop(*_):actions.append('stop-resources');return {'state':'OWNED_RESOURCE_SETTLEMENT_PROVEN'}
  def sample(*_):
   if fail=='sample':raise RuntimeError('fixture residency failure')
   return {'minimumFreeFraction':.12}
  class Manager:
   def __init__(self,*_):self.children={}
   def launch(self,name):
    actions.append('launch-'+name)
    if fail=='launch-'+name:raise RuntimeError('injected boundary '+name)
    if name=='workload':
     assert all(self.children[k]['p'].poll() is None for k in ('service','ingress'))
     assert actions.index('launch-service')<actions.index('wait-health') and actions.index('launch-ingress')<actions.index('wait-health')
    self.children[name]={'p':SimpleNamespace(poll=lambda:None)}
   def wait(self,name,*_):
    actions.append('wait-'+name)
    return {'actualExitCode':75 if fail=='wait-'+name else 0,'state':'WAITED_ABSENT','fixture':'SOURCE_ONLY'}
   def close(self,*_):actions.append('wait-close-all');return {'state':'ALL_ORIGINAL_CHILDREN_WAITED_ABSENT','fixture':'SOURCE_ONLY'}
  with mock.patch.object(s.observer,'snapshot',return_value={}),mock.patch.object(s.observer,'protected_instances',return_value=['four']),mock.patch.object(s.control,'exclusive'):
   result=s.schedule(graph,go,manager_factory=Manager,load=load,stop=stop,sample=sample)
  return result,actions
 def test_concurrent_residence_order_and_success(self):
  r,a=self.run_case();self.assertEqual(r['state'],'FINITE_SCHEDULE_COMPLETE');self.assertLess(a.index('launch-ingress'),a.index('launch-workload'));self.assertLess(a.index('wait-workload'),a.index('wait-close-all'));self.assertLess(a.index('wait-close-all'),a.index('stop-resources'));self.assertEqual(r['status'],'SOURCE_ONLY_UNTIL_GENUINE_EXECUTION')
 def test_each_boundary_always_owned_wait_then_resource_settlement(self):
  for failure in ('load','sample','launch-service','launch-ingress','launch-health','wait-health','launch-workload','wait-workload'):
   with self.subTest(boundary=failure):
    r,a=self.run_case(failure);self.assertEqual(r['state'],'QUARANTINE_OR_FAILED');self.assertIn('wait-close-all',a);self.assertEqual(a[-1],'stop-resources')
 def test_single_load_capability_cannot_start_schedule(self):
  with self.assertRaises(control.Refused):s.schedule({}, {'actions':['load']})
if __name__=='__main__':unittest.main()

class ProductionWaitTests(unittest.TestCase):
 """Actual LOCAL Popen children; production settlement, no Linux/UID claim.

 The test process creates and directly waits every child itself. Linux observer
 seams use genuine Darwin kernel births/groups, never constructed current facts.
 """
 def test_actual_direct_wait_durable_before_stream_and_metadata_faults(self):
  import contextlib,os,sys,signal,subprocess,uuid
  import receipt_recorder as r,normal_service as n
  for fault in ('none','missing-birth','flush','fsync','digest','inventory','wait-publication','terminal-publication','wait-timeout'):
   with self.subTest(fault=fault):
    directory=OUT/('production-wait-'+fault+'-'+uuid.uuid4().hex);directory.mkdir(mode=0o700)
    prefix=directory/'actual-child';env={'PATH':'/usr/bin:/bin','LC_ALL':'C','TMPDIR':os.environ['TMPDIR']}
    argv=[sys.executable,'-I','-c','import time;print("actual-owned-child",flush=True);time.sleep(20)']
    log=open(str(prefix)+'.raw','xb');gate_r,gate_w=os.pipe();p=None
    manager=s.Children({}, {'nonce':'a'*64,'bootId':'SOURCE_ONLY_LOCAL_NO_LINUX_BOOT'})
    try:
     p=subprocess.Popen([sys.executable,'-I','-c',r._GATE,str(gate_r),*argv],pass_fds=(gate_r,),stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL,env=env)
     born=r.birth(p.pid);identity=n.process_identity(p.pid)
     control.exclusive(directory/'original-before-release.json',{'evidence':'SOURCE_ONLY_ACTUAL_LOCAL_PRODUCTION_SETTLEMENT','argv':argv,'cwd':os.getcwd(),'environment':env,'pid':p.pid,'pgid':os.getpgid(p.pid),'kernelBirth':born,'identity':identity,'startUtc':control.utc(),'injectedFault':fault})
     item={'p':p,'birth':identity if fault!='missing-birth' else None,'log':log,'prefix':prefix,'component':'local','argv':argv,'cwd':os.getcwd(),'environment':env,'startUtc':control.utc()};manager.children['local']=item
     os.write(gate_w,b'G');os.close(gate_w);gate_w=None
     output_end=time.monotonic()+2
     while Path(str(prefix)+'.raw').stat().st_size==0 and time.monotonic()<output_end:time.sleep(.005)
     self.assertIn(b'actual-owned-child',Path(str(prefix)+'.raw').read_bytes())
     original_exclusive=control.exclusive;original_fsync=os.fsync;original_read=Path.read_bytes;original_wait=p.wait
     with contextlib.ExitStack() as stack:
      stack.enter_context(mock.patch.object(s.observer,'birth',side_effect=n.process_identity))
      stack.enter_context(mock.patch.object(s.observer,'pid_presence',side_effect=lambda b:{'state':'ORIGINAL_ABSENT_PROC_ROOT' if r.birth(b['pid'])!=born else 'ORIGINAL_PRESENT'}))
      stack.enter_context(mock.patch.object(s.observer,'group_absent',side_effect=lambda group:not r.inventory(group)['rows']))
      if fault=='flush':
       class BadFlush:
        def flush(self):raise OSError('SOURCE_ONLY_INJECTED_FLUSH')
        def fileno(self):return log.fileno()
        def close(self):return log.close()
       item['log']=BadFlush()
      if fault=='fsync':stack.enter_context(mock.patch.object(os,'fsync',side_effect=lambda fd:(_ for _ in ()).throw(OSError('SOURCE_ONLY_INJECTED_FSYNC')) if fd==log.fileno() else original_fsync(fd)))
      if fault=='digest':stack.enter_context(mock.patch.object(Path,'read_bytes',side_effect=lambda path:(_ for _ in ()).throw(OSError('SOURCE_ONLY_INJECTED_DIGEST')) if path==Path(str(prefix)+'.raw') else original_read(path),autospec=True))
      if fault=='inventory':stack.enter_context(mock.patch.object(r,'inventory',side_effect=OSError('SOURCE_ONLY_INJECTED_INVENTORY')))
      if fault in ('wait-publication','terminal-publication'):
       suffix='.wait.json' if fault=='wait-publication' else '.terminal.json'
       stack.enter_context(mock.patch.object(control,'exclusive',side_effect=lambda path,value:(_ for _ in ()).throw(OSError('SOURCE_ONLY_INJECTED_PUBLICATION')) if str(path).endswith(suffix) else original_exclusive(path,value)))
      if fault=='wait-timeout':
       calls=[0]
       def wait(*args,**kw):
        if kw.get('timeout') is not None:calls[0]+=1;raise subprocess.TimeoutExpired(argv,kw['timeout'])
        return original_wait(*args,**kw)
       stack.enter_context(mock.patch.object(p,'wait',side_effect=wait))
      result=manager.close(time.time()-.01)
     self.assertIs(type(p.returncode),int);receipt=item['receipt'];self.assertEqual(receipt['actualExitCode'],p.returncode);self.assertTrue(receipt['originalPopenWait'])
     durable=Path(str(prefix)+('.wait-fallback.json' if fault=='wait-publication' else '.wait.json'))
     self.assertEqual(json.loads(durable.read_text())['actualExitCode'],p.returncode)
     self.assertNotEqual(r.birth(p.pid),born);absence=r.inventory(p.pid);self.assertEqual(absence['rows'],[])
     control.exclusive(directory/'independent-after-direct-wait.json',{'actualExitCode':p.returncode,'directOriginalPopenWait':True,'originalBirthAbsent':r.birth(p.pid)!=born,'originalGroupAbsent':not absence['rows'],'groupInventory':absence,'managerResult':result,'rawStream':r.digest(str(prefix)+'.raw'),'endUtc':control.utc()})
     if fault=='none':self.assertEqual(receipt['state'],'WAITED_ABSENT')
     else:self.assertEqual(receipt['state'],'QUARANTINE_PARTIAL_EVIDENCE');self.assertTrue(receipt['errors'])
    finally:
     if p is not None:
      if p.returncode is None:p.kill()
      p.wait()
     if not log.closed:log.close()
     os.close(gate_r)
     if gate_w is not None:os.close(gate_w)
