"""Focused offline controller acceptance; no dispatch, SSH or model contact."""
import copy,datetime,hashlib,importlib.util,json,pathlib,tempfile,time,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('controller',D/'controller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def snapshot(complete=False):
 params={'boot':'boot','containers':{l:{'Id':l,'Image':'image','StartedAt':'utc'} for l in ('flash','qwen0','qwen1','image')}}
 records={p+s:None for p in (m.WARM,m.MAIN) for s in ('.json','-OWNER.json','-CANCEL.json','-SETTLEMENT.json')}
 if complete:
  records[m.WARM+'.json']={'status':'COMPLETE','client_threads_settled':True,'cancel_reason':None,'owner':dict(params,review_package_sha256=m.PACKAGE),'end_utc':m.NOW(),'requests':{'image':[],**{l:[{'status':'COMPLETE','done':True,'finish_reason':'length','http_status':200,'body_sent_utc':'sent','usage':{'prompt_tokens':n,'completion_tokens':c,'total_tokens':n+c}}] for l,n,c in [('flash',8192,128),('qwen0',4096,16),('qwen1',4096,16)]}}}
 return params,{'utc':'utc','boot':'boot','containers':{l:dict(v,Running=True,OOMKilled=False) for l,v in params['containers'].items()},'records':records,'units':''}
class Tests(unittest.TestCase):
 def test_qualification_refuses_stale_wrong_id_cancel_and_usage(self):
  p,s=snapshot(True);m.qualify(s,p)
  for reason in ('stale','id','cancel','usage'):
   bad=copy.deepcopy(s);w=bad['records'][m.WARM+'.json']
   if reason=='stale':w['end_utc']=datetime.datetime.fromtimestamp(time.time()-301,datetime.timezone.utc).isoformat()
   if reason=='id':bad['containers']['flash']['Id']='wrong'
   if reason=='cancel':bad['records'][m.WARM+'-CANCEL.json']={}
   if reason=='usage':w['requests']['qwen0'][0]['usage']['completion_tokens']=17
   with self.assertRaises(AssertionError):m.qualify(bad,p)
 def simulate(self,mode):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'TASK',pathlib.Path(d)):
   private=pathlib.Path(d,'private');private.mkdir();p,empty=snapshot();_,full=snapshot(True)
   (private/'PREFLIGHT.json').write_text(json.dumps({'status':'FULL_PREFLIGHT_PASS','parameters':p}))
   main=copy.deepcopy(full);main['records'][m.MAIN+'.json']={'status':'RUNNING','cancel_reason':None,'barrier_released_utc':'barrier','requests':{l:[{'body_sent_utc':'sent'}] for l in p['containers']}}
   if mode=='failure':full['records'][m.WARM+'.json']['status']='FAILED'
   reads=iter([empty,full,full,main]);events=[]
   c=m.Controller(1500);c.check=lambda:('go','controller');c.read=lambda:next(reads);c.pause=lambda:None
   def invoke(label,argv,cap):
    self.assertTrue((c.home/'INTENT.json').exists());c.save(label+'_INTENT');events.append(label)
    if mode=='ambiguous':raise TimeoutError('uncertain')
    c.save(label+'_RETURNED')
   c.invoke=invoke
   if mode=='success':c.run();self.assertEqual(c.state['stage'],'MAIN_STARTED_EXIT');self.assertEqual(events,['WARM_DISPATCH','MAIN_PREFLIGHT','MAIN_DISPATCH'])
   else:
    with self.assertRaises((RuntimeError,TimeoutError)):c.run()
    self.assertEqual(events,['WARM_DISPATCH']);self.assertEqual(c.state['stage'],'STOP_NO_RETRY')
   with self.assertRaises(FileExistsError):c.run()
   self.assertEqual(events.count('WARM_DISPATCH'),1)
 def test_success_dispatches_each_once_and_exits_after_four_body_proof(self):self.simulate('success')
 def test_failed_warm_no_main_and_exclusive_intent_no_replay(self):self.simulate('failure')
 def test_ambiguous_dispatch_never_replayed(self):self.simulate('ambiguous')
 def test_exact_GO_and_expiry(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'TASK',pathlib.Path(d)):
   go={'review_package_sha256':m.PACKAGE,'controller_sha256':hashlib.sha256((D/'controller.py').read_bytes()).hexdigest(),'modes':['warm','main'],'quiet_confirmed':True,'quiet_evidence':'root','expires_utc':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=60)).isoformat()}
   p=pathlib.Path(d,'ROOT-GO.json');p.write_text(json.dumps(go));m.Controller(1500).check()
   for field,value in [('controller_sha256','wrong'),('review_package_sha256','wrong'),('expires_utc','2000-01-01T00:00:00+00:00')]:
    bad=dict(go);bad[field]=value;p.write_text(json.dumps(bad))
    with self.assertRaises(AssertionError):m.Controller(1500).check()
if __name__=='__main__':unittest.main()
