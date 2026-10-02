# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[2]
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

import importlib.util,os,sys,tempfile,unittest
from pathlib import Path
import vision_runtime_probe as p
class ProbeTests(unittest.TestCase):
 def test_fixed_passive_commands(self):
  self.assertEqual(p.SSH[-4:],['/usr/bin/python3','-I','-B','-','--remote'][-4:])
  for argv in p.COMMANDS.values():
   self.assertFalse(set(argv)&{'run','start','stop','pull','exec','restart','status','sudo'})
   self.assertFalse(any(x.startswith('--env') for x in argv))
  with self.assertRaises(ValueError):p.bounded(['/bin/echo','unapproved'])
 def test_small_metadata_stable_hash_only(self):
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'metadata.json';f.write_text('{"architectures":["A"],"secret":"NOT_EXPORTED"}')
   r=p.small_file(f,('architectures',));self.assertEqual(r['selected'],{'architectures':['A']});self.assertNotIn('secret',str(r))
   link=Path(t)/'link';link.symlink_to(f);self.assertEqual(p.small_file(link)['state'],'UNKNOWN')
 def test_missing_is_unknown_not_absent(self):
  self.assertEqual(p.small_file('/this/file/does/not/exist')['state'],'UNKNOWN')
 def test_exact_adoption(self):
  self.assertEqual(len(p.RECEIPT_SHA),64);self.assertEqual(len(p.MODELS),2);self.assertEqual(p.GPU,'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf')
if __name__=='__main__':unittest.main()
