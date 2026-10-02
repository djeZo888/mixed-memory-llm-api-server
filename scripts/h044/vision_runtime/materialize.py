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

#!/usr/bin/env python3
"""Validate a secret-free disabled graph; no installation or lifecycle side effects."""
import argparse,json
from pathlib import Path
from control import validate_graph,verify_source,sha,canonical

def materialize(graph,source_root,helper_root):
 validate_graph(graph);verify_source(graph,source_root,helper_root)
 # No keys or input values are accepted by this materializer.
 return {'schema':'h043-materialized-review-v1','execute':False,'graphSHA256':sha(canonical(graph)),'graph':graph,'runtimeAdmission':'CLOSED','rootProof':'MISSING','liveActions':'NONE'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--read-only',action='store_true');p.add_argument('graph');p.add_argument('source_root');p.add_argument('helper_root');a=p.parse_args()
 review=materialize
 if a.read_only:
  from read_only_control import materialize as review
 print(json.dumps(review(json.loads(Path(a.graph).read_text()),a.source_root,a.helper_root),indent=2))
if __name__=='__main__':main()
