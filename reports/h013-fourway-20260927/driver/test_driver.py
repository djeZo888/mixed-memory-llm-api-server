"""Scoped offline H013 guard and retained-workload verification. No VM contact."""
import ast,copy,hashlib,json,pathlib,unittest,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent;TASK=HERE.parents[3];REPO=TASK/'repo'
class DriverTests(unittest.TestCase):
 def setUp(self):
  self.tree=ast.parse((HERE/'job-body.py').read_text());self.ns={}
  functions=[x for x in self.tree.body if isinstance(x,ast.FunctionDef) and x.name in ('numeric','safety')]
  exec(compile(ast.Module(body=functions,type_ignores=[]),'safety','exec'),self.ns)
  self.ns.update(GPUS={'flash':'f','qwen0':'q','qwen1':'r','image':'i'},limits={x:85 for x in ('flash','qwen0','qwen1','image')},samples=[],PARAMETERS={'power_limits':dict.fromkeys('fqri',600)})
  self.row={'ram':{'MemTotal':100,'MemAvailable':50},'gpu':{x:{'temperature.gpu':40,'memory.total':100000,'memory.free':20000,'power.limit':600,'ecc.mode.current':'Disabled','ecc.mode.pending':'Disabled','clocks_event_reasons.sw_power_cap':'Active'} for x in 'fqri'},'cgroups':{x:{'memory.swap.current':0,'events':{'oom':0,'max':0,'oom_kill':0}} for x in self.ns['GPUS']},'swap':{'pswpin':10,'pswpout':20}}
 def test_all_thermal_and_memory_floors(self):
  safety=self.ns['safety'];self.assertIsNone(safety(self.row))
  for lane,gpu in self.ns['GPUS'].items():
   for field,value,reason in [('temperature.gpu',85,lane+'_thermal_limit'),('memory.free',0,lane+'_gpu_reserve'),('ecc.mode.current','Enabled',lane+'_ecc_changed'),('power.limit',500,lane+'_power_limit_changed')]:
    bad=copy.deepcopy(self.row);bad['gpu'][gpu][field]=value;self.assertEqual(safety(bad),reason)
   bad=copy.deepcopy(self.row);bad['cgroups'][lane]['memory.swap.current']=1;self.assertEqual(safety(bad),lane+'_owned_swap')
  bad=copy.deepcopy(self.row);bad['ram']['MemAvailable']=14;self.assertEqual(safety(bad),'host_reserve_below_15pct')
 def test_fault_counters_and_historical_swap(self):
  self.ns['samples']=[copy.deepcopy(self.row) for _ in range(5)];self.assertIsNone(self.ns['safety'](self.row))
  for i,row in enumerate(self.ns['samples']):row['swap']['pswpout']=i
  self.assertEqual(self.ns['safety'](self.row),'sustained_swap_io_5_intervals')
  self.ns['samples']=[copy.deepcopy(self.row)];bad=copy.deepcopy(self.row);bad['cgroups']['flash']['events']['oom']=1;self.assertEqual(self.ns['safety'](bad),'flash_cgroup_oom_or_limit')
 def test_retained_fixture_bytes_and_counts(self):
  raw=(TASK/'private/FIXTURES03.json').read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),'135f2bbbea8deda81576feb667fbbd2411810a04150da9a76e6f0b730b467dec')
  fixture=json.loads(raw)
  for lane,rows in fixture.items():
   self.assertEqual(len(rows),1 if lane=='flash' else 12)
   for row in rows:
    self.assertEqual(row['native_count']['count'],65536 if lane=='flash' else 262144)
    self.assertEqual(row['payload']['max_tokens'],768 if lane=='flash' else 128)
  old=ast.parse((REPO/'reports/h011-fourway-20260927/attempt03/driver/job-body.py').read_text())
  def image_assignment(tree):return next(ast.dump(n) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript) and ast.unparse(t)=="FIXTURES['image']" for t in n.targets))
  self.assertEqual(image_assignment(old),image_assignment(self.tree))
 def test_stream_has_no_guard_or_fsync_per_delta(self):
  request=next(n for n in self.tree.body if isinstance(n,ast.FunctionDef) and n.name=='request')
  loop=next(n for n in ast.walk(request) if isinstance(n,ast.While))
  text=ast.unparse(loop)
  for word in ('fsync','transaction','boundary_guard','persist('):self.assertNotIn(word,text)
 def test_missing_image_refuses_dispatch_before_ssh(self):
  tree=ast.parse((HERE/'dispatch.py').read_text());ns={}
  function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='require_full_preflight')
  exec(compile(ast.Module(body=[function],type_ignores=[]),'dispatch-gate','exec'),ns)
  with self.assertRaisesRegex(AssertionError,'image_recovery_and_full_preflight_required'):ns['require_full_preflight']({'status':'BLOCKED_IMAGE_RECOVERY'})
  ns['require_full_preflight']({'status':'FULL_PREFLIGHT_PASS'})
if __name__=='__main__':unittest.main()
