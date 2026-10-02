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
import datetime,json,os,sys
from pathlib import Path
import control,lifecycle,observer,service_supervisor

def main():
 if len(sys.argv)!=2 or sys.argv[1] not in ('preflight','load','inference','stop'):raise control.Refused('fixed_action')
 action=sys.argv[1];g,go=control.current_authority(action)
 claim=json.loads(control.read_private(control.PHASE_ROOT+'/spent-'+go['nonce']+'-'+action+'.json',0))
 if claim['carrierSHA256']!=control.sha(control.read_private(control.PHASE_ROOT+'/CURRENT-GO.json',0)) or type(claim['count']) is not int or claim['count']!=1:raise control.Refused('issuer_executor_claim_mismatch')
 deadline=datetime.datetime.fromisoformat(go['actionDeadlines'][action]).timestamp()
 if action=='load':
  for a in ('inference','stop'):
   c=json.loads(control.read_private(control.PHASE_ROOT+'/spent-'+go['nonce']+'-'+a+'.json',0))
   if c.get('scheduleEntry')!='load' or c.get('carrierSHA256')!=claim['carrierSHA256']:raise control.Refused('schedule_claim_missing')
  result=service_supervisor.schedule(g,go)
 elif action=='preflight':result=lifecycle.preflight(g,go['nonce'],deadline)
 elif action=='stop':result=lifecycle.stop(g,go['nonce'],deadline)
 else:raise control.Refused('INFERENCE_ONLY_WITHIN_CONCURRENT_OWNED_SCHEDULE_NO_BACKEND_BYPASS')
 control.exclusive(control.PHASE_ROOT+'/action-'+go['nonce']+'-'+action+'.json',{'result':result,'producer':observer.birth(os.getpid()),'rootProof':'REVIEWED_SIGNED_CURRENT_CARRIER'})
 if result.get('state') in ('QUARANTINE','QUARANTINE_OR_FAILED') or result.get('cleanup',{}).get('state')=='QUARANTINE' or result.get('failure'):raise SystemExit(75)
if __name__=='__main__':main()
