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
"""Finite private executor. This phase cannot execute any runtime action."""
import argparse,datetime,json,os,re,signal,subprocess,time,selectors
from pathlib import Path
import control,observer

def run(argv,deadline,output,label):
 import receipt_recorder
 if not re.fullmatch('[a-zA-Z0-9_-]{1,120}',label):raise control.Refused('fixed_label')
 if deadline<=time.time():raise control.Refused('action_deadline_expired')
 control.exclusive(Path(output)/(label+'.intent.json'),{'argv':argv,'deadlineEpoch':deadline,'requestedUtc':control.utc(),'scope':'NEW_EXCLUSIVE_PROCESS_GROUP'})
 original=receipt_recorder.record(argv,output,cwd=str(Path(__file__).absolute().parents[3]),
  environment={'PATH':'/usr/local/bin:/usr/bin:/bin','LC_ALL':'C'},
  timeout=deadline-time.time(),output_cap=1048576,label=label)
 raw=Path(original['stdout']['path']).read_bytes() if original.get('stdout') else b''
 with (Path(output)/(label+'.raw')).open('xb') as f:f.write(raw)
 result={'argv':argv,'producer':original['birth'],'actualPopenPid':original['pid'],
  'scope':{'pgid':original['pgid']},'exitCode':original['actualExitCode'],
  'state':'EXITED' if original['status']=='COMPLETE' else 'QUARANTINE',
  'failure':original['errors'],'workReleased':bool(original['birth'] and original['pgid'] and original['status']=='COMPLETE'),'originalReceipt':original['receiptPath'],
  'originalPopenWait':original['waited'],'rawSHA256':control.sha(raw),
  'descendantSettlement':original.get('absence'),'rootCarrierProof':'SEPARATE_SIGNED_CURRENT_CAPABILITY'}
 control.exclusive(Path(output)/(label+'.receipt.json'),result)
 return result

def execute(graph,go_path,sig_path,action):
 # This check precedes every socket, model, daemon and filesystem live operation.
 control.trusted_anchor()
 control.validate_graph(graph);go=control.carrier(go_path,sig_path,graph)
 if action not in go['actions']:raise control.Refused('action_not_enabled')
 if any(graph['gates'][g]!='PASS' for g in control.GATES):raise control.Refused('gates_not_current')
 control.verify_source(graph,control.SOURCE_ROOT,control.SOURCE_ROOT+'/scripts/h044/vision_runtime')
 deadline=datetime.datetime.fromisoformat(go['actionDeadlines'][action]).timestamp()
 # Root current owner/lease/freeze/route/admission/hardware receipt is separate from us.
 # Its byte hash is in signed graph. Never acquire or repair an unknown old owner.
 owner=graph['rootOwnerEvidence']
 if owner.get('bootId')!=go['bootId'] or owner.get('lease')!='FROZEN_EXCLUSIVE_VISION' or owner.get('admission')!='CLOSED' or owner.get('hardware')!='PASS':raise control.Refused('root_current_owner_not_proven')
 current=json.loads(control.read_private(control.PHASE_ROOT+'/current-owner.json',0))
 if current!=owner:raise control.Refused('current_owner_tuple_changed')
 claims=('load','inference','stop') if action=='load' else ('preflight','stop') if action=='preflight' else (action,)
 if not set(claims)<=set(go['actions']):raise control.Refused('schedule_or_preflight_requires_owned_stop_capability')
 for claim in claims:
  control.exclusive(control.PHASE_ROOT+'/spent-'+go['nonce']+'-'+claim+'.json',{'carrierSHA256':control.sha(Path(go_path).read_bytes()),'action':claim,'count':1,'claimedUtc':control.utc(),'scheduleEntry':action})
 if action in ('load','preflight'):deadline=datetime.datetime.fromisoformat(go['actionDeadlines']['stop']).timestamp()
 # Exact candidate argv is fully signed; no CLI overrides, shell or arbitrary parameters.
 commands=graph['actions'][action]['argv']
 if not isinstance(commands,list) or len(commands)>12:raise control.Refused('finite_command_count')
 if action=='pull' and commands!=[['/usr/bin/docker','pull','--platform','linux/amd64',graph['image']]]:raise control.Refused('exact_separate_pull')
 before=observer.snapshot();control.exclusive(control.PHASE_ROOT+'/before-'+go['nonce']+'-'+action+'.json',before)
 results=[]
 for index,argv in enumerate(commands):
  if not isinstance(argv,list) or any(not isinstance(x,str) for x in argv) or argv[0] not in ('/usr/bin/docker','/usr/bin/python3','/usr/bin/ss','/usr/bin/nvidia-smi'):raise control.Refused('fixed_binary_required')
  # Root sealed lifecycle script handles actual cidfiles; no inferred names/kill/stop-all.
  r=run(argv,deadline,control.PHASE_ROOT,f'{go["nonce"]}-{action}-{index}')
  results.append(r)
  if r['exitCode']!=0 or r['state']!='EXITED':break
 after=observer.snapshot();control.exclusive(control.PHASE_ROOT+'/after-'+go['nonce']+'-'+action+'.json',after)
 result={'rootCarrierSHA256':control.sha(Path(go_path).read_bytes()),'workerProducer':observer.birth(os.getpid()),'action':action,'results':results,'admission':'CLOSED','runtimeQualification':'NOT_PROVEN','cleanup':'REQUIRES_AUTHENTIC_OWNED_LEDGER_OBSERVER_SETTLEMENT'}
 control.exclusive(control.PHASE_ROOT+'/result-'+go['nonce']+'-'+action+'.json',result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('graph');p.add_argument('carrier');p.add_argument('signature');p.add_argument('action',choices=('preflight','load','inference','stop','pull'));a=p.parse_args()
 print(json.dumps(execute(json.loads(Path(a.graph).read_text()),a.carrier,a.signature,a.action),indent=2))
if __name__=='__main__':main()
