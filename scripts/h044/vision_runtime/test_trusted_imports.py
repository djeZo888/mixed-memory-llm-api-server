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

import copy,hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import trusted_imports as ti
ROOT=Path(__file__).absolute().parents[3];OUT=ROOT.parent/'output'
def recorded_command(argv,*,input=None,cwd=None,timeout=10):
 import receipt_recorder
 environment={k:os.environ[k] for k in ('PATH','TMPDIR','LANG','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE') if k in os.environ}
 r=receipt_recorder.record(argv,OUT/'nested-checks',cwd=cwd,environment=environment,timeout=timeout,label='fixture-command',stdin_data=input)
 if r['status']!='COMPLETE':raise RuntimeError('Original source command recorder partial: '+json.dumps(r['errors']))
 return subprocess.CompletedProcess(argv,r['actualExitCode'],Path(r['stdout']['path']).read_bytes(),Path(r['stderr']['path']).read_bytes())

class TrustedTests(unittest.TestCase):
 def test_isolated_real_entrypoints_and_no_cwd_hijack(self):
  for name,args,wanted in [('scripts/h043/vision_service_entrypoint.py',['--describe'],0),('scripts/h044/vision_runtime/runtime_action.py',['load'],1),('scripts/h044/vision_runtime/executor.py',['--help'],0),('scripts/h044/vision_runtime/credential_supervisor.py',['bad'],78)]:
   p=recorded_command([sys.executable,'-I','-B',str(ROOT/name),*args],cwd='/private/tmp',timeout=10)
   self.assertEqual(p.returncode,wanted,(name,p.stderr.decode()))
   self.assertNotIn(b'ModuleNotFoundError',p.stderr)
  p=recorded_command([sys.executable,'-I','-B',str(ROOT/'scripts/h043/vision_service_entrypoint.py'),'--serve'],input=b'{}',timeout=5)
  self.assertEqual(p.returncode,78);self.assertIn(b'exact_service_uid',p.stderr)
 def test_protected_loader_positive_negative_graph(self):
  with tempfile.TemporaryDirectory(dir=OUT) as d:
   root=Path(d);p=root/'leaf.py';p.write_text('VALUE=42\n');os.chmod(p,0o600)
   m={'schema':'h044-protected-imports-v1','modules':{'fixture_leaf':{'path':'leaf.py','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}}}
   finder=ti.TrustedFinder(root,m,os.geteuid());self.assertEqual(finder.source('fixture_leaf')[1],b'VALUE=42\n')
   for changed in ({},dict(m,schema='bad'),{'schema':m['schema'],'modules':{'fixture_leaf':dict(m['modules']['fixture_leaf'],path='../leaf.py')}},{'schema':m['schema'],'modules':{'fixture_leaf':dict(m['modules']['fixture_leaf'],sha256='0'*64)}}):
    with self.assertRaises(ti.TrustError):ti.TrustedFinder(root,changed,os.geteuid())
   with self.assertRaises(ti.TrustError):ti.TrustedFinder(root,m,os.geteuid()+1)
   os.chmod(p,0o666)
   with self.assertRaises(ti.TrustError):ti.TrustedFinder(root,m,os.geteuid())
   os.chmod(p,0o600);p.unlink();(root/'target.py').write_text('VALUE=42\n');p.symlink_to(root/'target.py')
   with self.assertRaises(ti.TrustError):ti.TrustedFinder(root,m,os.geteuid())
 def test_foreign_loaded_and_mutated_source_denied(self):
  with tempfile.TemporaryDirectory(dir=OUT) as d:
   root=Path(d);p=root/'leaf.py';p.write_text('VALUE=42\n');m={'schema':'h044-protected-imports-v1','modules':{'fixture_leaf':{'path':'leaf.py','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}}};f=ti.TrustedFinder(root,m,os.geteuid());p.write_text('VALUE=43\n')
   with self.assertRaises(ti.TrustError):f.find_spec('fixture_leaf')
if __name__=='__main__':unittest.main()
