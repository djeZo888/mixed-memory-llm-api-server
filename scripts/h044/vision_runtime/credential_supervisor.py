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
"""Exact in-container key-to-env exec; no secret in Docker config, argv or logs."""
import os,sys
from pathlib import Path
from vision_service_entrypoint import protected_read
KEYS={'interpretation':'/run/secrets/vision-interpretation.key','ocr':'/run/secrets/vision-ocr.key'}

def main():
 if len(sys.argv)!=2 or sys.argv[1] not in KEYS:raise SystemExit(78)
 role=sys.argv[1]
 from trusted_imports import protected_bytes
 # The isolated bootstrap verified root-owned SOURCE-MANIFEST inputs and all code.
 argv=__import__('json').loads(protected_bytes(Path('/opt/vision/runtime-argv-'+role+'.json'),0))
 # argv is separately source-hashed sealed material, not user-controlled input.
 if not argv or argv[0]!='/usr/local/bin/vllm' or any(x in argv for x in ('--api-key','--trust-remote-code')):raise SystemExit(78)
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/runtime','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','VLLM_NO_USAGE_STATS':'1','DO_NOT_TRACK':'1','HF_DATASETS_OFFLINE':'1','HF_HOME':'/tmp/hf','VLLM_CACHE_ROOT':'/tmp/vllm','VLLM_API_KEY':protected_read(KEYS[role]),'NVIDIA_VISIBLE_DEVICES':'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf','NVIDIA_DRIVER_CAPABILITIES':'compute,utility'}
 env.update({k:'1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
 os.execvpe(argv[0],argv,env)
if __name__=='__main__':main()
