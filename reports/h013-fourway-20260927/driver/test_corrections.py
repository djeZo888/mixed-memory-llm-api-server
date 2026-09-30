"""Offline exact-owner, cancellation and warmup regression checks; no VM actions."""
import ast,contextlib,copy,json,pathlib,socket,tempfile,threading,types,unittest
from unittest.mock import Mock,patch
HERE=pathlib.Path(__file__).resolve().parent

def functions(filename,names,ns):
 tree=ast.parse((HERE/filename).read_text())
 body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 exec(compile(ast.Module(body=body,type_ignores=[]),filename,'exec'),ns)
 return ns

class Corrections(unittest.TestCase):
 def test_await_terminal_once_success_and_failure(self):
  for terminal in ('SETTLED','FAILED_NATIVE_SETTLEMENT_UNPROVEN'):
   with self.subTest(terminal=terminal),tempfile.TemporaryDirectory() as d:
    event=threading.Event();event.set();path=pathlib.Path(d,'T-SETTLEMENT.json')
    value={'status':terminal,'end_utc':'terminal'};path.write_text(json.dumps(value))
    clock=types.SimpleNamespace(monotonic=Mock(return_value=0),sleep=Mock(side_effect=AssertionError('must not wait terminal')))
    ns=functions('job-body.py',['await_settlement'],dict(settlement_started=event,result={},P=pathlib.Path,LOG=d,PREFIX='T',time=clock,json=json))
    ns['await_settlement']();path.unlink();ns['await_settlement']()
    self.assertEqual(ns['result']['native_settlement'],value);clock.sleep.assert_not_called()
 def test_nonterminal_failure_keeps_monitor_until_owner_concludes(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d,'T-SETTLEMENT.json');p.write_text(json.dumps({'status':'FAILED_NATIVE_SETTLEMENT_UNPROVEN'}))
   event=threading.Event();event.set()
   def advance(_):p.write_text(json.dumps({'status':'FAILED_NATIVE_SETTLEMENT_UNPROVEN','end_utc':'done'}))
   clock=types.SimpleNamespace(monotonic=lambda:0,sleep=Mock(side_effect=advance))
   ns=functions('job-body.py',['await_settlement'],dict(settlement_started=event,result={},P=pathlib.Path,LOG=d,PREFIX='T',time=clock,json=json))
   ns['await_settlement']();self.assertEqual(clock.sleep.call_count,1)
 def test_cancel_socket_first_exact_inflight_targets_once(self):
  events=[];rows={'qwen1':[{'request_id':'T-qwen1-0','status':'SUBMITTED'}],'flash':[{'request_id':'T-flash-0','status':'COMPLETE'}]}
  sock=types.SimpleNamespace(shutdown=lambda _:events.append('socket'))
  @contextlib.contextmanager
  def transaction():yield None,None
  def status(path,value,g):events.append(('receipt',value['targets']))
  runner=Mock(side_effect=lambda *a,**k:(events.append('dispatch') or types.SimpleNamespace(returncode=0)))
  ns=functions('job-body.py',['cancel'],dict(lock=threading.Lock(),result={'cancel_reason':None,'requests':rows},stop=threading.Event(),active={'qwen1':(types.SimpleNamespace(sock=sock),None)},now=lambda:'utc',socket=socket,settlement_launch_lock=threading.Lock(),settlement_started=threading.Event(),transaction=transaction,s=types.SimpleNamespace(root_payload_guard=lambda:None),status=status,LOG='/log',PREFIX='T',PARAMETERS={'boot':'b','containers':{}},subprocess=types.SimpleNamespace(run=runner)))
  ns['cancel']('thermal');ns['cancel']('again')
  self.assertEqual(events[:3],['socket',('receipt',{'qwen1':['T-qwen1-0']}),'dispatch']);self.assertEqual(runner.call_count,1)
  self.assertIn('--property=RuntimeMaxSec=420',runner.call_args.args[0])
 def exact(self):
  value={'Id':'a'*64,'Image':'sha256:i','State':{'StartedAt':'boot','Running':True,'Pid':42,'Restarting':False},'HostConfig':{'RestartPolicy':{'Name':'no'}}}
  params={'containers':{'qwen1':{'Id':value['Id'],'Image':value['Image'],'StartedAt':'boot'}}}
  return value,params
 def test_exact_identity_and_restart_refusals(self):
  value,params=self.exact();ns=functions('settle-body.py',['validate_exact'],{'PARAMETERS':params})
  self.assertEqual(ns['validate_exact']('qwen1',value),value)
  for field in ('Id','Image','StartedAt','restart'):
   bad=copy.deepcopy(value)
   if field=='StartedAt':bad['State'][field]='changed'
   elif field=='restart':bad['HostConfig']['RestartPolicy']['Name']='always'
   else:bad[field]='changed'
   with self.assertRaises(AssertionError):ns['validate_exact']('qwen1',bad)
 def test_short_stop_checks_receipt_before_exact_id_and_bookkeeping_after(self):
  value,params=self.exact();events=[];state=copy.deepcopy(value)
  def inspect(lane):events.append('inspect');return copy.deepcopy(state)
  def run(argv,**kwargs):
   self.assertEqual(argv,['docker','stop','--time','3','a'*64]);self.assertEqual(kwargs['timeout'],12)
   events.append('short_stop');state['State'].update(Running=False,Pid=0)
  def owner(lane,lease):events.append('receipt');return lambda:events.append('bookkeeping')
  ns=functions('settle-body.py',['validate_exact','short_stop'],dict(PARAMETERS=params,owner_action=owner,inspect_exact=inspect,subprocess=types.SimpleNamespace(run=run)))
  ns['short_stop']('qwen1',value,None,types.SimpleNamespace(validate=lambda:events.append('lease')))
  self.assertLess(events.index('receipt'),events.index('short_stop'));self.assertGreater(events.index('bookkeeping'),events.index('short_stop'))
 def test_short_stop_failure_never_bookkeeps_or_retries(self):
  value,params=self.exact();finish=Mock();runner=Mock(side_effect=TimeoutError())
  ns=functions('settle-body.py',['validate_exact','short_stop'],dict(PARAMETERS=params,owner_action=lambda *a:finish,inspect_exact=lambda _:value,subprocess=types.SimpleNamespace(run=runner)))
  with self.assertRaises(TimeoutError):ns['short_stop']('qwen1',value,None,types.SimpleNamespace(validate=lambda:None))
  finish.assert_not_called();self.assertEqual(runner.call_count,1)
 def test_nonempty_cgroup_refuses_bookkeeping(self):
  value,params=self.exact();stopped=copy.deepcopy(value);stopped['State'].update(Running=False,Pid=0);finish=Mock()
  with tempfile.TemporaryDirectory() as d:
   cg=pathlib.Path(d);(cg/'cgroup.procs').write_text('44\n')
   ns=functions('settle-body.py',['validate_exact','short_stop'],dict(PARAMETERS=params,owner_action=lambda *a:finish,inspect_exact=lambda _:stopped,subprocess=types.SimpleNamespace(run=Mock())))
   with self.assertRaisesRegex(AssertionError,'owned_cgroup_not_empty'):ns['short_stop']('qwen1',value,cg,types.SimpleNamespace(validate=lambda:None))
   finish.assert_not_called()
 def test_qwen_bookkeeping_exact_slot_borrowed_lease_retains_intent(self):
  value,params=self.exact();lease=object();slot={'container':{'id':'a'*64},'selected':'qwen','desired':'running','boot_policy':'resume','generation':31}
  manager=types.SimpleNamespace(read_state=lambda:{'slots':{'qwen':copy.deepcopy(slot)}},trusted_container=Mock(),dispatch=Mock())
  module=types.ModuleType('lifecycle.manager');module.load_manager=lambda *a:manager
  with patch.dict('sys.modules',{'lifecycle':types.ModuleType('lifecycle'),'lifecycle.manager':module}):
   ns=functions('settle-body.py',['owner_action'],dict(PARAMETERS=params,types=types,P=pathlib.Path,ROOT='/installed'))
   finish=ns['owner_action']('qwen1',lease);manager.dispatch.assert_not_called();finish()
  manager.dispatch.assert_called_once_with('boot-stop',lease=lease,target='qwen',expected_generation=31)
 def test_flash_string_base_halt_borrowed_lease(self):
  with tempfile.TemporaryDirectory() as d:
   pathlib.Path(d,'state.json').write_text(json.dumps({'container':{'id':'x'},'desired':'running'}));pathlib.Path(d,'config.json').write_text('{}')
   m=types.SimpleNamespace(BASE=d,validate_container=Mock(),operate=Mock());lease=object()
   ns=functions('settle-body.py',['owner_action'],dict(PARAMETERS={'containers':{'flash':{'Id':'x'}}},load_owner=lambda *a:m,P=pathlib.Path,json=json,inspect_exact=lambda _:{}))
   ns['owner_action']('flash',lease)();m.operate.assert_called_once_with('halt',borrowed=lease)
 def test_warm_counts_and_main_identity_unchanged(self):
  tree=ast.parse((HERE/'warm-tail.py').read_text());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='request']
  self.assertEqual({k.value.value for n in calls for k in n.keywords if k.arg=='expected_tokens'},{4096,8192})
  warm=(HERE/'warm-tail.py').read_text();self.assertIn("'max_tokens':16",warm);self.assertIn("actual==4096",warm)
  main=(HERE/'job-body.py').read_text();self.assertIn("('flash',8192),('qwen0',4096),('qwen1',4096)",main)
  self.assertIn("c.auto_open=0",main)
if __name__=='__main__':unittest.main()
