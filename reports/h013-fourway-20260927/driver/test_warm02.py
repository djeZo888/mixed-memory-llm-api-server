"""Offline WARM02 bounds, ordering and unchanged main gate checks. No VM contact."""
import ast,copy,datetime,hashlib,json,pathlib,threading,types,unittest
from unittest.mock import Mock
D=pathlib.Path(__file__).resolve().parent
T=D.parents[3]
B=T/'private/prior-driver-999d202a'
class Warm02(unittest.TestCase):
 def test_main_is_identical_except_warm_namespace(self):
  self.assertEqual((D/'job-body.py').read_text(),(B/'job-body.py').read_text().replace('H013-WARM01.json','H013-WARM02.json'))
  for n in ('vm-common.py','fan-readings.py','settle-body.py','prepare.py','preflight-body.py'):
   self.assertEqual((D/n).read_bytes(),(B/n).read_bytes())
 def test_assembled_warm_bounds_and_main_bounds(self):
  source=(D/'job-body.py').read_text();tree=ast.parse(source)
  tree.body=[n for n in tree.body if not isinstance(n,ast.If)]
  warm=ast.unparse(tree).replace('timeout=540','timeout=900').replace('threading.Timer(540,','threading.Timer(900,')
  def caps(raw):
   t=ast.parse(raw)
   return [(ast.unparse(n.func),[x.value for x in n.args if isinstance(x,ast.Constant) and isinstance(x.value,int)],{k.arg:k.value.value for k in n.keywords if isinstance(k.value,ast.Constant)}) for n in ast.walk(t) if isinstance(n,ast.Call) and ast.unparse(n.func) in ('http.client.HTTPConnection','threading.Timer')]
  self.assertIn(('threading.Timer',[900],{}),caps(warm));self.assertIn(('threading.Timer',[540],{}),caps(source))
  self.assertEqual([k['timeout'] for f,a,k in caps(warm) if f=='http.client.HTTPConnection'],[20,900])
  self.assertEqual(hashlib.sha256((T/'private/H011-WARM03-warm8192-FIXTURE.jsonl').read_bytes()).hexdigest(),'9a3d1c486008de6b8fd50a09c71498d86245d892428c60d6997e82cdb09a5297')
 def test_flash_first_failure_stops_before_qwen(self):
  tree=ast.parse((D/'warm-tail.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef))
  block=next(n for n in fn.body if isinstance(n,ast.Try)).body
  start=next(i for i,n in enumerate(block) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ok' for t in n.targets))
  seq=block[start:start+2]
  for failed in (False,True):
   stop=threading.Event();seen=[]
   def request(lane,index,payload,expected_tokens):
    seen.append((lane,expected_tokens,payload['max_tokens']))
    if failed:stop.set()
    return not failed
   ns=dict(request=request,payload={'max_tokens':128},stop=stop,PARAMETERS={'capacities':{l:{'served_model_name':l} for l in ('qwen0','qwen1')}},control=lambda *a:{'count':4096})
   exec(compile(ast.Module(body=seq,type_ignores=[]),'order','exec'),ns)
   self.assertEqual(seen,[('flash',8192,128)] if failed else [('flash',8192,128),('qwen0',4096,16),('qwen1',4096,16)])
 def test_existing_main_gate_rejects_stale_wrong_ids_missing_counts_cancel(self):
  fn=next(n for n in ast.parse((D/'job-body.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
  block=next(n for n in fn.body if isinstance(n,ast.Try)).body
  i=next(i for i,n in enumerate(block) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='warm' for t in n.targets))
  gate=compile(ast.Module(body=block[i+1:i+5],type_ignores=[]),'gate','exec')
  good={'status':'COMPLETE','client_threads_settled':True,'cancel_reason':None,'owner':{'boot':'b','containers':{'flash':'id'}},'end_utc':datetime.datetime.fromtimestamp(1000,datetime.timezone.utc).isoformat(),'requests':{l:[{'status':'COMPLETE','usage':{'prompt_tokens':c}}] for l,c in [('flash',8192),('qwen0',4096),('qwen1',4096)]}}
  def run(w):exec(gate,dict(warm=w,PARAMETERS=good['owner'],time=types.SimpleNamespace(time=lambda:1100),datetime=datetime))
  run(good)
  for case in ('stale','ids','count','cancel','failed'):
   w=copy.deepcopy(good)
   if case=='stale':w['end_utc']=datetime.datetime.fromtimestamp(799,datetime.timezone.utc).isoformat()
   if case=='ids':w['owner']['containers']['flash']='other'
   if case=='count':w['requests']['qwen1'][0]['usage']['prompt_tokens']=1
   if case=='cancel':w['cancel_reason']='cap'
   if case=='failed':w['status']='FAILED'
   with self.assertRaises(AssertionError):run(w)
if __name__=='__main__':unittest.main()
