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

import copy,hashlib,importlib.util,json,os,sys,tempfile,unittest
from unittest import mock
from pathlib import Path
import control,executor,issuer,materialize,observer,read_only_control,workload,ingress,lifecycle
ROOT=Path(__file__).absolute().parents[3];OUT=ROOT.parent/'output'
class ControlTests(unittest.TestCase):
 def graph(self):return json.loads((OUT/'RUNTIME-GRAPH.json').read_text())
 def test_full_hash_bound_graph(self):
  g=self.graph();r=materialize.materialize(g,ROOT,ROOT/'scripts/h044/vision_runtime');self.assertFalse(r['execute']);self.assertEqual(r['rootProof'],'MISSING')
  changed=copy.deepcopy(g);changed['sourceManifest']['scripts/vision/service.py']='0'*64
  with self.assertRaises(control.Refused):materialize.materialize(changed,ROOT,ROOT/'scripts/h044/vision_runtime')
 def test_all_runtime_calls_disabled_before_side_effects(self):
  g=self.graph()
  for fn in (lambda:executor.execute(g,'missing','missing','load'),lambda:issuer.issue(g,{},'missing','missing'),lambda:control.carrier('missing','missing',g),lambda:read_only_control.execute({}),lambda:lifecycle.load(g,'0'*64,0),lambda:ingress.Server('fake-key-00000000','10.156.100.1','PASS_ROOT_REVIEWED_AUTHENTICATED_PRIVATE_LINK',0),lambda:workload.request('GET','/v1/models',b'','fake',0)):
   with self.assertRaises(control.Refused):fn()
 def test_no_profile_or_image_fallback_and_pull_separate(self):
  g=self.graph();self.assertTrue(g['image'].endswith('5f5e535216848d0c52159c8c13a0af04be5f6fe1a84e79914300610796f76d40'))
  for c in g['runtime']['containers']:
   self.assertIn('--pull=never',c['createArgv']);self.assertNotIn('--api-key',c['runtimeArgv']);self.assertNotIn('--trust-remote-code',c['runtimeArgv']);self.assertEqual(c['maxOutputTokens'],4096)
  self.assertEqual(g['workload']['jobCount'],1);self.assertEqual(g['runtime']['peakMeasurements']['minimumFreeFraction'],.07)
 def test_readonly_exact_template(self):
  g=json.loads((OUT/'READ-ONLY-TEMPLATE.json').read_text());self.assertFalse(read_only_control.materialize(g,ROOT,ROOT/'scripts/h044/vision_runtime')['execute'])
  for k,v in [('count',2),('privateRoot','/tmp'),('readerPath','../../x'),('uid',1000)]:
   x=copy.deepcopy(g);x[k]=v
   with self.assertRaises(control.Refused):read_only_control.materialize(x,ROOT,ROOT/'scripts/h044/vision_runtime')
 def test_original_corpus_pixels_not_prediction(self):
  png,c=workload.fixture();self.assertEqual(c['expectedLiteral'],'R1 10K 5V');self.assertEqual(c['pngSha256'],control.sha(png));self.assertEqual(c['predictionStatus'],'NOT_RUN')
  from service import decode_png
  w,h,channels,color,rows=decode_png(png);self.assertEqual((w,h),(c['width'],c['height']));self.assertEqual(control.sha(b''.join(rows)),c['pixelSha256'])
 def test_unknown_cleanup_quarantines(self):
  before={'bootId':'same','gpuProcesses':[],'gpus':[],'ports':[],'containers':[]};after=copy.deepcopy(before);after['ports']=None
  r=observer.cleanup_proof(before,after,[],{}, {},{});self.assertEqual(r['state'],'QUARANTINE');self.assertFalse(r['authenticSettlement'])
  r=observer.cleanup_proof(before,before,[],{}, {'config':'a'},{'config':'b'});self.assertEqual(r['state'],'QUARANTINE')
 def test_nested_missing_file_does_not_prove_pid_absence(self):
  original={'pid':1234,'startTicks':100}
  with mock.patch('pathlib.Path.read_text',side_effect=FileNotFoundError()),mock.patch('observer.os.stat',return_value=object()):
   self.assertEqual(observer.pid_presence(original)['state'],'UNKNOWN_PROC_ROOT_STILL_PRESENT')
 def test_postfork_capture_error_has_original_wait_receipt(self):
  # Real Mac-only blocked guard child; injected Linux birth failure, no workload released.
  with tempfile.TemporaryDirectory() as t:
   with mock.patch('receipt_recorder.birth',side_effect=OSError('explicit injected source fixture')):
    r=executor.run(['/usr/bin/python3','-c','raise SystemExit(0)'],__import__('time').time()+5,t,'postfork-fixture')
   self.assertFalse(r['workReleased']);self.assertIs(type(r['exitCode']),int);self.assertEqual(r['state'],'QUARANTINE')
   self.assertTrue((Path(t)/'postfork-fixture.intent.json').exists());self.assertTrue((Path(t)/'postfork-fixture.receipt.json').exists())
   # Original injected-child receipts must outlive this temporary test directory.
   import shutil,secrets
   kept=OUT/'control-fault-originals'/secrets.token_hex(12);kept.parent.mkdir(mode=0o700,exist_ok=True);shutil.copytree(t,kept)
   control.exclusive(kept/'SOURCE-FIXTURE.json',{'evidence':'SOURCE_ONLY_INJECTED_BIRTH_FAILURE','originalTemporaryRoot':t,'retainedOriginals':True,'result':r})
if __name__=='__main__':unittest.main()
