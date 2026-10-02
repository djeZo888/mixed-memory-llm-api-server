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
"""One finite root-owned schedule; services overlap inference and every child is waited."""
import datetime,json,os,signal,subprocess,threading,time
from pathlib import Path
import control,lifecycle,observer

def epoch(go,action):return datetime.datetime.fromisoformat(go['actionDeadlines'][action]).timestamp()
def ticket_bytes(graph):return control.canonical({'graph':graph,'goRawHex':control.read_private(control.PHASE_ROOT+'/CURRENT-GO.json',0).hex(),'signatureHex':control.read_private(control.PHASE_ROOT+'/CURRENT-GO.json.sig',0,256).hex()})

class Children:
 def __init__(self,graph,go):self.graph,self.go=graph,go;self.children={};self.receipts=[]
 def launch(self,component):
  spec=self.graph['runtime'][component];argv=spec['argv'];uid=self.graph['runtime']['service']['uid']
  if os.geteuid()!=0 or uid!=1000:raise control.Refused('authentic_root_actual_UID1000_launch_boundary')
  payload=ticket_bytes(self.graph);prefix=Path(control.PHASE_ROOT)/(self.go['nonce']+'-'+component)
  control.exclusive(str(prefix)+'.intent.json',{'argv':argv,'uid':uid,'proofSHA256':control.sha(payload),'bootId':self.go['bootId'],'deadline':self.go['actionDeadlines']['inference'],'credentials':'UID1000_OWNED_LEAVES_NEVER_READ_BY_ROOT'})
  log=open(str(prefix)+'.raw','xb');os.chmod(str(prefix)+'.raw',0o600);p=None
  try:
   p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,user=1000,group=1000,extra_groups=[],env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
   # Store original Popen immediately, including failures before birth capture.
   item={'p':p,'birth':None,'log':log,'prefix':prefix,'component':component,'argv':argv,'cwd':os.getcwd(),'environment':{'PATH':'/usr/bin:/bin','LC_ALL':'C'},'startUtc':control.utc()};self.children[component]=item
   b=observer.birth(p.pid)
   if b.get('uid')!=1000 or b['pgid']!=p.pid:raise control.Refused('ACTUAL_CHILD_UID_GROUP_MISMATCH')
   item['birth']=b;control.exclusive(str(prefix)+'.identity.json',{'birth':b,'uid':1000,'pgid':p.pid,'bootId':self.go['bootId'],'workReleased':False})
   # Child blocks on stdin EOF until actual birth/intent are durable.
   p.stdin.write(payload);p.stdin.close();return item
  except BaseException:
   if p is None:log.close()
   raise
 def wait(self,name,deadline,abort=None):
  item=self.children[name];p=item['p']
  while p.poll() is None:
   if abort and abort():raise control.Refused('RESIDENCY_MONITOR_FAILURE')
   if time.time()>=deadline:raise TimeoutError('component_entire_wall_deadline')
   try:p.wait(timeout=min(.2,max(.001,deadline-time.time())))
   except subprocess.TimeoutExpired:pass
  return self.terminal(name,p.wait())
 def terminal(self,name,code):
  item=self.children[name]
  if item.get('receipt'):return item['receipt']
  # Original wait is authoritative and durable BEFORE optional stream/fsync,
  # inventory/digest/publication. Missing evidence never erases a genuine exit.
  actual=item['p'].wait()
  if type(actual) is not int or actual!=code:raise control.Refused('original_integer_wait_mismatch')
  b=item['birth'];r={'component':name,'argv':item['argv'],'cwd':item['cwd'],'environment':item['environment'],'startUtc':item['startUtc'],'endUtc':control.utc(),'actualPid':item['p'].pid,'birth':b,'actualExitCode':actual,'originalPopenWait':True,'bootId':self.go['bootId'],'originalBirthAbsent':None,'originalGroupAbsent':None,'descendantInventory':None,'rawSHA256':None,'rawBytes':None,'state':'QUARANTINE_PARTIAL_EVIDENCE','errors':[]}
  item['receipt']=r;self.receipts.append(r)
  def attempt(stage,operation):
   try:return operation()
   except BaseException as exc:r['errors'].append({'stage':stage,'type':type(exc).__name__,'message':str(exc)});return None
  attempt('durable_original_wait',lambda:control.exclusive(str(item['prefix'])+'.wait.json',dict(r)))
  if r['errors']:
   attempt('durable_original_wait_fallback',lambda:control.exclusive(str(item['prefix'])+'.wait-fallback.json',dict(r)))
  attempt('flush',item['log'].flush)
  attempt('fsync',lambda:os.fsync(item['log'].fileno()))
  attempt('stream_close',item['log'].close)
  if b is not None:
   r['originalBirthAbsent']=attempt('birth_absence',lambda:observer.pid_presence(b)['state'] in ('ORIGINAL_ABSENT_PROC_ROOT','ORIGINAL_ABSENT_PID_REUSED'))
   r['originalGroupAbsent']=attempt('group_absence',lambda:observer.group_absent(b['pgid']))
   r['descendantInventory']=attempt('descendant_inventory',lambda:__import__('receipt_recorder').inventory(b['pgid']))
  else:r['errors'].append({'stage':'birth','message':'MISSING_ORIGINAL_BIRTH_NO_INVENTED_ABSENCE'})
  raw=Path(str(item['prefix'])+'.raw')
  data=attempt('raw_read',raw.read_bytes)
  if data is not None:r['rawSHA256']=control.sha(data);r['rawBytes']=len(data)
  if not r['errors'] and r['originalBirthAbsent'] is True and r['originalGroupAbsent'] is True and r['rawBytes'] is not None and r['rawBytes']<=1048576:r['state']='WAITED_ABSENT'
  attempt('terminal_publication',lambda:control.exclusive(str(item['prefix'])+'.terminal.json',dict(r)))
  if r['errors']:
   r['state']='QUARANTINE_PARTIAL_EVIDENCE'
   attempt('terminal_fallback',lambda:control.exclusive(str(item['prefix'])+'.terminal-fallback.json',dict(r)))
  return r
 def close(self,deadline):
  failures=[]
  for name in reversed(list(self.children)):
   item=self.children[name];p=item['p']
   errors=[];code=None
   def signal_owned(kind):
    b=item['birth']
    try:same=b is not None and b['pgid']==p.pid and observer.birth(p.pid)==b and os.getpgid(p.pid)==p.pid
    except (OSError,ValueError,KeyError):same=False
    if same:os.killpg(p.pid,kind)
    elif p.returncode is None:
     p.kill() if kind==signal.SIGKILL else p.terminate()
   try:
    if p.poll() is None:
     signal_owned(signal.SIGTERM)
     try:code=p.wait(timeout=min(5,max(.001,deadline-time.time())))
     except subprocess.TimeoutExpired:
      signal_owned(signal.SIGKILL)
      code=p.wait(timeout=min(2,max(.001,deadline-time.time())))
    else:code=p.wait()
   except BaseException as exc:errors.append({'stage':'bounded_close','type':type(exc).__name__,'message':str(exc)})
   finally:
    # Never let an expired timer, birth lookup or receipt error skip the direct
    # wait. Only the still-owned original Popen is signalled on metadata failure.
    if p.returncode is None:
     try:p.kill()
     except ProcessLookupError:pass
    code=p.wait()
    r=self.terminal(name,code)
    r['errors'].extend(errors)
    if errors:r['state']='QUARANTINE_PARTIAL_EVIDENCE'
    if r['state']!='WAITED_ABSENT':failures.append(r)
    if p.stdin and not p.stdin.closed:
     try:p.stdin.close()
     except OSError as exc:failures.append({'component':name,'failure':str(exc),'stage':'stdin_close'})
  return {'receipts':self.receipts,'failures':failures,'state':'QUARANTINE' if failures else 'ALL_ORIGINAL_CHILDREN_WAITED_ABSENT'}


class SteadyChildren(Children):
 """Original root supervisor directly owns each Docker attach from START."""
 def launch_attach(self,created):
  import receipt_recorder
  component='attach-'+created['role'];argv=['/usr/bin/docker','start','--attach',created['id']]
  prefix=Path(control.PHASE_ROOT)/(self.go['nonce']+'-'+component)
  env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
  control.exclusive(str(prefix)+'.intent.json',{'argv':argv,'createdOriginalId':created['id'],'actualWaitParent':observer.birth(os.getpid()),'startUtc':control.utc()})
  log=open(str(prefix)+'.raw','xb');os.chmod(str(prefix)+'.raw',0o600);p=None;r,w=os.pipe()
  try:
   p=subprocess.Popen(['/usr/bin/python3','-I','-c',receipt_recorder._GATE,str(r),*argv],pass_fds=(r,),stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,env=env)
   item={'p':p,'birth':None,'log':log,'prefix':prefix,'component':component,'argv':argv,'cwd':os.getcwd(),'environment':env,'startUtc':control.utc()};self.children[component]=item
   item['birth']=observer.birth(p.pid)
   if item['birth']['ppid']!=os.getpid() or item['birth']['pgid']!=p.pid:raise control.Refused('ORIGINAL_ATTACH_DIRECT_PARENT')
   control.exclusive(str(prefix)+'.identity.json',{'birth':item['birth'],'actualOriginalWaitParent':observer.birth(os.getpid())})
   os.write(w,b'G')
   # Gate's birth is captured before release; exec changes executable metadata,
   # never the kernel birth. Record actual Docker identity after that real exec.
   while time.time()<epoch(self.go,'load'):
    current=observer.birth(p.pid)
    if current['startTicks']!=item['birth']['startTicks']:raise control.Refused('ATTACH_ORIGINAL_KERNEL_BIRTH_CHANGED')
    if current['exe']=='/usr/bin/docker':break
    if p.poll() is not None:raise control.Refused('ATTACH_EXEC_FAILED')
    time.sleep(.01)
   else:raise TimeoutError('ATTACH_EXEC_DEADLINE')
   item['birth']=current;control.exclusive(str(prefix)+'.docker-exec-identity.json',{'birth':current})
   return item
  except BaseException:
   if p is None:log.close()
   raise
  finally:os.close(r);os.close(w)
 def check_output_and_liveness(self):
  for name,item in self.children.items():
   if item.get('receipt'):continue
   if item['p'].poll() is not None:raise control.Refused('STEADY_ORIGINAL_CHILD_EXITED:'+name)
   if Path(str(item['prefix'])+'.raw').stat().st_size>1048576:raise control.Refused('STEADY_ORIGINAL_OUTPUT_CAP:'+name)


def schedule(graph,go,*,manager_factory=Children,load=lifecycle.load,stop=lifecycle.stop,sample=observer.residency_sample,adopt=None):
 """Explicit boundaries allow meaningful source failure/concurrency fixtures."""
 if set(('load','inference','stop'))-set(go['actions']):raise control.Refused('FINITE_FULL_SCHEDULE_GO_REQUIRED')
 if not time.time()<epoch(go,'load')<epoch(go,'inference')<epoch(go,'stop'):raise control.Refused('ORDERED_PHASE_DEADLINES_REQUIRED')
 manager=manager_factory(graph,go);owners=[];samples=[];faults=[];event=threading.Event();monitor=None;failure=None;outcome=None;normal=None;baseline=observer.snapshot();protected=observer.protected_instances(graph,baseline)
 def monitor_residence():
  while not event.is_set():
   try:samples.append(sample(graph,owners))
   except BaseException as e:faults.append(str(e));return
   event.wait(.2)
 try:
  owners=load(graph,go['nonce'],epoch(go,'load'))
  if len(owners)!=2 or {o['role'] for o in owners}!={'interpretation','ocr'}:raise control.Refused('BOTH_MODEL_OWNERS_REQUIRED')
  samples.append(sample(graph,owners));monitor=threading.Thread(target=monitor_residence,name='owned-residency-monitor',daemon=False);monitor.start()
  # Both are released before any inference/health wait; neither blocks the other.
  manager.launch('service');manager.launch('ingress');manager.launch('health')
  health=manager.wait('health',epoch(go,'load'),lambda:bool(faults))
  if health['actualExitCode']!=0 or health['state']!='WAITED_ABSENT':raise control.Refused('AUTHENTICATED_HEALTH_FAILED')
  for name in ('service','ingress'):
   if manager.children[name]['p'].poll() is not None:raise control.Refused('SERVICE_OR_INGRESS_NOT_RESIDENT')
  manager.launch('workload');outcome=manager.wait('workload',epoch(go,'inference'),lambda:bool(faults))
  if outcome['actualExitCode']!=0 or outcome['state']!='WAITED_ABSENT':raise control.Refused('WORKLOAD_EXPECTED_LITERAL_OR_DEADLINE_FAILED')
  for name in ('service','ingress'):
   if manager.children[name]['p'].poll() is not None:raise control.Refused('SERVICE_OR_INGRESS_EXITED_DURING_JOB')
  samples.append(sample(graph,owners))
  if adopt:
   # Actual terminal bytes and model/service identities precede root adoption.
   # The returned owner must be a real NormalOwner with signed current ledger.
   import normal_service
   normal=adopt(graph,go,manager,owners,outcome,samples)
   if not isinstance(normal,normal_service.NormalOwner):raise control.Refused('NORMAL_OWNER_ADAPTER_REQUIRED')
   normal.adopt()
   normal.govern(stop_requested=normal.callbacks['stop_requested'])
 except BaseException as e:failure=str(e)
 finally:
  event.set()
  if monitor:monitor.join(timeout=2)
  if monitor and monitor.is_alive():faults.append('MONITOR_UNJOINED_QUARANTINE')
  # Closed admission + exact original waits precede engine/network settlement.
  policy='CLOSE_EXACT_FINITE_OWNED_RESOURCES'
  if normal and failure:
   import normal_handoff
   try:policy=normal_handoff.cleanup_policy(normal.ledger.read(),normal.cap['oldOwner'],normal.resources)
   except BaseException:policy='QUARANTINE_UNKNOWN_HANDOFF_NO_SIGNAL'
  if policy!='CLOSE_EXACT_FINITE_OWNED_RESOURCES' and failure:
   children={'state':'QUARANTINE_HANDOFF_OR_NORMAL_OWNER','policy':policy}
   cleanup={'state':'NORMAL_OWNER_RETAINS_RESOURCES' if policy=='NORMAL_OWNER_ONLY_NO_FINITE_STOP' else 'QUARANTINE_UNKNOWN_OWNER_UNTOUCHED'}
  elif normal and not failure:
   # Normal authority needs its own cleanup callback; finite GO is not replayed.
   children,cleanup=normal.callbacks['normal_cleanup'](normal)
  else:
   children=manager.close(epoch(go,'stop'))
   try:cleanup=stop(graph,go['nonce'],epoch(go,'stop'))
   except BaseException as e:cleanup={'state':'QUARANTINE','failure':str(e)}
  final=observer.snapshot()
  try:
   if observer.protected_instances(graph,final)!=protected:raise control.Refused('OTHER_FOUR_INSTANCE_IDENTITY_CHANGED')
  except BaseException as e:faults.append(str(e))
 state='FINITE_SCHEDULE_COMPLETE' if not failure and not faults and children['state']=='ALL_ORIGINAL_CHILDREN_WAITED_ABSENT' and cleanup['state']=='OWNED_RESOURCE_SETTLEMENT_PROVEN' else 'QUARANTINE_OR_FAILED'
 result={'state':state,'failure':failure,'residencyFailures':faults,'models':owners,'samples':samples,'peakFreeFraction':min((x['minimumFreeFraction'] for x in samples),default=None),'workload':outcome,'children':children,'cleanup':cleanup,'otherFourBefore':protected,'baseline':baseline,'final':final,'normalFactory':'NOT_TESTED_R_EXCLUSIVE','status':'SOURCE_ONLY_UNTIL_GENUINE_EXECUTION'}
 control.exclusive(Path(control.PHASE_ROOT)/('schedule-'+go['nonce']+'.json'),result);return result

def start():
 graph,go=control.current_authority('load');return schedule(graph,go)
if __name__=='__main__':start()
