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
"""Exact candidate image support inspection; no model load/download. Disabled."""
import hashlib,importlib.metadata,json,os,sys
from pathlib import Path
import control

def inspect_image():
 # Called only in an exact newly owned preflight container by authenticated runtime_action.
 # No independent model/weight or lifecycle calls exist in this inspection leaf.
 import torch,vllm
 from vllm.model_executor.models import ModelRegistry
 architectures=sorted(ModelRegistry.get_supported_archs());wanted=['Qwen3_5ForConditionalGeneration','PaddleOCRVLForConditionalGeneration']
 root=Path(vllm.__file__).parent
 files=('model_executor/models/registry.py','model_executor/models/qwen3_5.py','model_executor/models/paddleocr_vl.py','envs.py','entrypoints/openai/api_server.py')
 bindings={f:control.sha((root/f).read_bytes()) if (root/f).is_file() else 'UNKNOWN' for f in files}
 return {'vllmVersion':importlib.metadata.version('vllm'),'torchVersion':torch.__version__,'cudaVersion':torch.version.cuda,'compiledArchList':torch.cuda.get_arch_list(),'deviceCapability':list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,'architectureSupport':{a:a in architectures for a in wanted},'actualImageSourceHashes':bindings,'processorTemplateAPIAuthSupport':'REQUIRES_EXACT_SOURCE_REVIEW_NO_VERSION_INFERENCE','modelsLoaded':False,'weightResidency':'NOT_PROVEN'}
if __name__=='__main__':print(json.dumps(inspect_image(),indent=2))
