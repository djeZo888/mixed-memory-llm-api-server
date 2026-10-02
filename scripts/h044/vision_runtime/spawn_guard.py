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
"""New owned producer stays blocked until parent durably records actual identity."""
import json,os,sys
from pathlib import Path
if len(sys.argv)!=3:raise SystemExit(78)
import control
if os.geteuid()!=0:raise SystemExit(78)
fd=int(sys.argv[1]);intent=Path(sys.argv[2])
if str(intent.parent)!=control.PHASE_ROOT:raise SystemExit(78)
raw=control.read_private(intent,0)
g=control.parse_proof(control.read_private(control.PHASE_ROOT+'/RUNTIME-GRAPH.json',0));control.validate_graph(g)
go=control.carrier(control.PHASE_ROOT+'/CURRENT-GO.json',control.PHASE_ROOT+'/CURRENT-GO.json.sig',g);control.verify_source(g,control.SOURCE_ROOT,control.SOURCE_ROOT+'/scripts/h044/vision_runtime')
v=control.parse_proof(raw)
if not v.get('label','').startswith(go['nonce']+'-') or v.get('deadlineEpoch',0)>__import__('datetime').datetime.fromisoformat(go['expires']).timestamp():raise SystemExit(78)
if os.read(fd,1)!=b'G':raise SystemExit(125)
os.close(fd);v=json.loads(raw);argv=v['argv']
if not isinstance(argv,list) or not argv or argv[0] not in ('/usr/bin/docker','/usr/bin/python3','/usr/bin/ss','/usr/bin/nvidia-smi'):raise SystemExit(78)
os.execve(argv[0],argv,{'PATH':'/usr/local/bin:/usr/bin:/bin','LC_ALL':'C'})
