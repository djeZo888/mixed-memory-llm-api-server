"""Executable fixed Linux carrier producers. SOURCE ONLY until root exact GO.

Root signed packets, protected sources and one canonical lease are mandatory.
No caller-selected shell, model start, hold deletion or original Store opening.
"""
import hashlib,hmac,json,os,stat,socket,struct,subprocess,threading,time,signal
from pathlib import Path
from qualification_carrier import CarrierError,tree_manifest

def checked_bytes(path,uid=0,mode=None,bound=4*1024*1024):
 p=Path(path);s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=uid or s.st_nlink!=1 or s.st_mode&0o022 or (mode is not None and stat.S_IMODE(s.st_mode)!=mode) or s.st_size>bound or p.resolve()!=p:raise CarrierError('protected_input_identity')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  before=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns);raw=os.read(fd,bound+1);after=os.fstat(fd);current=p.lstat()
  if len(raw)!=s.st_size or before!=tuple(getattr(after,k) for k in ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns']) or before!=tuple(getattr(current,k) for k in ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns']):raise CarrierError('changing_protected_input')
  return raw
 finally:os.close(fd)

def signed_packet(input_path,approval_path,key_path):
 raw=checked_bytes(input_path,mode=0o600);approval=json.loads(checked_bytes(approval_path,mode=0o600));key=checked_bytes(key_path,mode=0o600,bound=32)
 if len(key)!=32 or set(approval)!={'inputSHA256','mac'} or approval['inputSHA256']!=hashlib.sha256(raw).hexdigest() or not hmac.compare_digest(approval['mac'],hmac.new(key,raw,hashlib.sha256).hexdigest()):raise CarrierError('root_approval_invalid')
 value=json.loads(raw)
 if value.get('schema')!='h041-qualification-carrier-v1' or value.get('actor')!='worker1' or value.get('phase') not in ['stage','full'] or value.get('nativeActionLimit')!=(9 if value['phase']=='stage' else 39) or value.get('settlementReserveMs')!=120000:raise CarrierError('fixed_carrier_scope')
 return value

def process_identity(pid):
 root=Path('/proc')/str(pid);raw=(root/'stat').read_text();return {'pid':pid,'startTicks':raw.rsplit(')',1)[1].split()[19],'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}

def previous_worker_gone(previous):
 try:return process_identity(previous['pid'])!=previous
 except (FileNotFoundError,ProcessLookupError):return True


def object_scope(roots):
 """STAT-only actual original objects plus canonical ancestor identities."""
 result={'roots':[],'objects':set(),'ancestors':set()}
 for raw in roots:
  root=Path(raw)
  if root.resolve()!=root or not root.is_dir():raise CarrierError('physical_root_not_canonical')
  st=root.lstat();result['roots'].append({'path':str(root),'dev':st.st_dev,'ino':st.st_ino})
  for p in [root,*root.rglob('*')]:
   st=p.lstat()
   if p.is_symlink():raise CarrierError('physical_original_alias')
   result['objects'].add((st.st_dev,st.st_ino))
   if len(result['objects'])>250000:raise CarrierError('physical_scope_bound')
  for parent in [root,*root.parents]:
   st=parent.stat();result['ancestors'].add((st.st_dev,st.st_ino))
 return result

def mount_overlaps(source,scope):
 p=Path(source)
 if not p.is_absolute() or p.resolve()!=p:raise CarrierError('mount_source_unknown_alias')
 st=p.stat();key=(st.st_dev,st.st_ino)
 # Parent binds expose original subroots; child/alias binds share an object.
 if key in scope['ancestors'] or key in scope['objects']:return True
 return any(p==Path(r['path']) or p in Path(r['path']).parents or Path(r['path']) in p.parents for r in scope['roots'])

def physical_scope(roots,uid,ports=(8080,8081,18081)):
 """Kernel FD dev/inode + namespace + bidirectional mount closure; unknown aborts."""
 scope=object_scope(roots);targets=[Path(r['path']) for r in scope['roots']];writers=[];listeners=[];inodes={};observed=0
 for table in ['/proc/net/tcp','/proc/net/tcp6']:
  for line in Path(table).read_text().splitlines()[1:]:
   parts=line.split()
   if int(parts[1].split(':')[1],16) in ports and parts[3]=='0A':inodes[parts[9]]=int(parts[1].split(':')[1],16)
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   identity=process_identity(int(proc.name));namespace=(proc/'ns/mnt').stat().st_ino;mountsha=hashlib.sha256((proc/'mountinfo').read_bytes()).hexdigest()
   for fd in (proc/'fd').iterdir():
    try:link=os.readlink(fd);st=fd.stat()
    except FileNotFoundError:continue
    observed+=1
    if observed>1000000:raise CarrierError('kernel_fd_bound')
    if link.startswith('socket:[') and link[8:-1] in inodes:listeners.append({**identity,'socketInode':link[8:-1],'port':inodes[link[8:-1]],'mountNamespace':namespace})
    clean=link.removesuffix(' (deleted)')
    if (st.st_dev,st.st_ino) in scope['objects'] or any(clean==str(p) or clean.startswith(str(p)+'/') for p in targets):writers.append({**identity,'fd':fd.name,'objectDev':st.st_dev,'objectIno':st.st_ino,'mountNamespace':namespace,'mountInfoSHA256':mountsha})
   if process_identity(int(proc.name))!=identity:raise CarrierError('kernel_process_changed')
  except (FileNotFoundError,ProcessLookupError):continue
  except PermissionError:raise CarrierError('incomplete_kernel_fd_observation')
 command=['/usr/sbin/runuser','--user',uid['name'],'--','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+uid['home'],'XDG_RUNTIME_DIR=/run/user/'+str(uid['uid']),'/usr/bin/podman','--remote=false'];containers=[]
 result=subprocess.run(command+['ps','-a','--format','json'],capture_output=True,timeout=8,check=True)
 for row in json.loads(result.stdout):
  cid=row.get('Id',row.get('ID'));result=subprocess.run(command+['inspect',cid],capture_output=True,timeout=8,check=True);v=json.loads(result.stdout)[0];matches=[]
  for m in v.get('Mounts',[]):
   source=m.get('Source')
   if source and mount_overlaps(source,scope):matches.append({'sourceDev':Path(source).stat().st_dev,'sourceIno':Path(source).stat().st_ino,'type':m.get('Type'),'rw':m.get('RW'),'destination':m.get('Destination')})
  if matches:containers.append({'id':cid,'running':v['State']['Running'],'pid':v['State']['Pid'],'overlappingMounts':matches})
 return {'roots':scope['roots'],'objectCount':len(scope['objects']),'observedFDCount':observed,'writers':writers,'listeners':listeners,'containers':containers}

class LinuxCarrierHost:
 def __init__(self,packet,owner,freeze,lease_module):
  self.packet,self.owner,self.freeze,self.lease_module=packet,owner,freeze,lease_module;self.task=None;self.task_identity=None;self.server=None;self.channel=None;self.guardian=None;self.original_records=None;self.guardian_identity=None;self.key=os.urandom(32);self.dead=False
 def sources(self):
  for p,digest in self.packet['privilegedSourceHashes'].items():
   if hashlib.sha256(checked_bytes(p)).hexdigest()!=digest:raise CarrierError('privileged_source_changed')
  for p,digest in self.packet['taskSourceHashes'].items():
   if hashlib.sha256(checked_bytes(p,uid=self.packet['user']['uid'],bound=512*1024*1024)).hexdigest()!=digest:raise CarrierError('task_source_changed')
 def begin_guardian(self,plan,lease):
  lease.validate();self.sources();self._start_guardian(plan,lease)
 def _guardian_current(self):
  if not self.guardian or self.guardian.poll() is not None or process_identity(self.guardian.pid)!=self.guardian_identity:raise CarrierError('spanning_guardian_lost')
 def release_unmutated_guardian(self,plan,lease):
  lease.validate()
  if self.task is not None or self.owner.observe_service('harness')!=self.packet['normalService']:raise CarrierError('unmutated_guardian_release_unproved')
  if self.guardian:self._release_guardian(plan)
 def _release_guardian(self,plan):
  self._guardian_current();p=Path(self.packet['evidenceRoot'])/'guardian.release';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  try:os.write(fd,json.dumps({'carrier':process_identity(os.getpid()),'transactionId':plan.transaction_id}).encode());os.fsync(fd)
  finally:os.close(fd)
  self.guardian.wait(timeout=3)
  if self.guardian.returncode:raise CarrierError('guardian_release_unproved')
 def assert_current(self,plan,lease,stage):
  lease.validate();self.sources();self._guardian_current()
  if process_identity(os.getpid())['bootId']!=plan.boot_id:raise CarrierError('boot_changed')
  self.freeze(plan.stop_request)
  observed=self.owner.observe_service('harness')
  if stage=='before-stop':
   if observed!=self.packet['normalService']:raise CarrierError('normal_owner_changed')
   verify_normal_tuple(self.packet['normalTuple'],observe_normal_tuple(self.packet,observed['main_pid']))
  if stage!='before-stop' and (observed['active']!='inactive' or observed['sub']!='dead' or observed['main_pid'] or observed['control_pid'] or observed['job_pending']):raise CarrierError('normal_service_not_stopped')
  if stage=='before-task' and time.time()>=plan.dispatch_cutoff:raise CarrierError('carrier_dispatch_expired')
 def assert_stopped_writers(self,plan,lease):
  self.assert_current(plan,lease,'stopped');v=physical_scope(plan.source_roots,self.packet['user'])
  if v['writers'] or v['listeners'] or any(c['running'] for c in v['containers']):raise CarrierError('original_writer_or_listener_present')
  if self.original_records is None:self.original_records=retained_record_snapshot(self.packet['normalDatabase'])
 def _foreign_holds(self):
  import sqlite3
  db=sqlite3.connect('file:/var/lib/ai-harness-dispatch/state.sqlite?mode=ro',uri=True,timeout=.2)
  try:rows=db.execute('SELECT key,scope FROM dispatch_holds').fetchall()
  finally:db.close()
  own=self.packet['ownHoldKey'];service='qwen-gpu1'
  if not any(k==own for k,_ in rows):raise CarrierError('own_stop_hold_missing')
  if any(k!=own and ('harness' in json.loads(s) or service in json.loads(s)) for k,s in rows):raise CarrierError('unrelated_hold_wins')
 def _admission(self,plan,lease):
  directory=Path('/run/ai-harness-qualification')/plan.transaction_id
  directory.mkdir(mode=0o710,parents=False);os.chown(directory,0,self.packet['user']['gid']);path=directory/'admission.sock';server=socket.socket(socket.AF_UNIX);server.bind(str(path));os.chmod(path,0o660);os.chown(path,0,self.packet['user']['gid']);server.listen(4);server.settimeout(.2);self.server=server;self.channel=directory
  packet={'schema':'qualification-task-admission-v1','transactionId':plan.transaction_id,'carrier':process_identity(os.getpid()),'socketPath':str(path),'key':self.key.hex(),'sessionId':self.packet['sessionId'],'lane':'qwen3.8-27b','maxOwnedSessions':64,'ownHoldKey':self.packet['ownHoldKey'],'dispatchCutoffMs':int(plan.dispatch_cutoff*1000),'expiresAtMs':int(plan.expires_at*1000)}
  fd=os.open(directory/'admission.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
  try:os.write(fd,json.dumps(packet).encode());os.fchown(fd,0,self.packet['user']['gid']);os.fchmod(fd,0o640);os.fsync(fd)
  finally:os.close(fd)
  sessions={self.packet['sessionId']:{'role':'carrier'}}
  def serve():
   while not self.dead:
    try:c,_=server.accept()
    except socket.timeout:continue
    except OSError:return
    try:
     c.settimeout(1);peer,uid,_=struct.unpack('3i',c.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
     if uid!=self.packet['user']['uid']:raise CarrierError('foreign_task_peer')
     if self.task is None:raise CarrierError('task_not_registered')
     ancestor=peer
     for _ in range(32):
      if ancestor==self.task.pid:break
      ancestor=int((Path('/proc')/str(ancestor)/'stat').read_text().rsplit(')',1)[1].split()[1])
     if ancestor!=self.task.pid:raise CarrierError('peer_not_owned_task_descendant')
     raw=b''
     while not raw.endswith(b'\n') and len(raw)<8192:
      chunk=c.recv(8192-len(raw))
      if not chunk:raise CarrierError('incomplete_task_challenge')
      raw+=chunk
     request=json.loads(raw);body=request['body'];v=json.loads(body)
     operation=v.get('operation');allowed={'challenge','transactionId','sessionId','requestId','lane','operation'}
     if operation=='register':allowed|={'role','parentSessionId'} if 'parentSessionId' in v else {'role'}
     if operation=='adopt':allowed|={'role','previousWorker'}
     if not hmac.compare_digest(request['mac'],hmac.new(self.key,body.encode(),hashlib.sha256).hexdigest()) or set(v)!=allowed or v['transactionId']!=plan.transaction_id or v['lane']!='qwen3.8-27b' or time.time()>=plan.dispatch_cutoff or operation not in ['register','admit','adopt']:raise CarrierError('foreign_expired_task_challenge')
     if operation=='register':
      import re
      if not re.fullmatch('[A-Za-z0-9._:-]{1,128}',v['sessionId']) or v['role'] not in ['parent','probe','child'] or v['sessionId'] in sessions or len(sessions)>=65 or (v['role']!='parent' and v.get('parentSessionId') not in sessions):raise CarrierError('unowned_session_registration')
     elif operation=='adopt':
      prior=sessions.get(v['sessionId'])
      if not prior or prior.get('role')!='parent' or v['role']!='parent' or v['previousWorker']!=prior.get('worker') or peer==v['previousWorker']['pid']:raise CarrierError('foreign_parent_readoption')
      if not previous_worker_gone(v['previousWorker']):raise CarrierError('prior_worker_exit_unproved')
     elif v['sessionId'] not in sessions:raise CarrierError('unregistered_task_session')
     # Same-process capability cannot be borrowed by another thread. Its owner
     # is the carrier main thread/process; validate is PID-based, no FD minting.
     lease.validate();self.sources();self.freeze(plan.stop_request);self._foreign_holds()
     if self.task is None or self.task.poll() is not None:raise CarrierError('task_owner_lost')
     if operation=='register':sessions[v['sessionId']]={'role':v['role'],'parentSessionId':v.get('parentSessionId'),'worker':process_identity(peer)}
     if operation=='adopt':sessions[v['sessionId']]={**sessions[v['sessionId']],'worker':process_identity(peer)}
     response=json.dumps({**v,'status':'registered' if operation=='register' else 'adopted' if operation=='adopt' else 'admit','worker':process_identity(peer),'observedAtMs':int(time.time()*1000),'ownerStartTicks':packet['carrier']['startTicks'],'ownHoldKey':self.packet['ownHoldKey']},separators=(',',':'));c.sendall(json.dumps({'body':response,'mac':hmac.new(self.key,response.encode(),hashlib.sha256).hexdigest()}).encode()+b'\n')
    except Exception:
     try:c.sendall(b'{"status":"reject"}\n')
     except OSError:pass
    finally:c.close()
  threading.Thread(target=serve,daemon=True).start();return directory/'admission.json'
 def run_owned_task(self,plan,lease):
  self.assert_current(plan,lease,'before-task');self.assert_stopped_writers(plan,lease);self._foreign_holds();admission=self._admission(plan,lease);self.sources();user=self.packet['user'];node=self.packet['nodePath'];entry=self.packet['taskEntry']
  if not entry.endswith('/ai-harness/deploy/engine/qualification-task.mjs') or not node.endswith('/bin/node') or entry not in self.packet['taskSourceHashes'] or node not in self.packet['taskSourceHashes']:raise CarrierError('fixed_task_entry_required')
  argv=['/usr/sbin/runuser','--user',user['name'],'--','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+user['home'],'USER='+user['name'],'LOGNAME='+user['name'],'XDG_RUNTIME_DIR=/run/user/'+str(user['uid']),'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(user['uid'])+'/bus',node,entry,self.packet['taskConfigPath'],str(admission)]
  out=Path(self.packet['evidenceRoot']);stdout=open(out/'task.stdout.private','xb');stderr=open(out/'task.stderr.private','xb');os.chmod(stdout.name,0o600);os.chmod(stderr.name,0o600)
  barrier=Path(__file__).with_name('qualification_task_barrier.py')
  if str(barrier) not in self.packet['privilegedSourceHashes']:raise CarrierError('reviewed_preexec_barrier_required')
  config=out/'task-preexec.json';fd=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  try:os.write(fd,json.dumps({'transactionId':plan.transaction_id,'carrier':process_identity(os.getpid()),'user':user['name'],'argv':argv,'ack':str(out/'guardian.task-ready')}).encode());os.fsync(fd)
  finally:os.close(fd)
  try:self.task=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(barrier),str(config)],stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True);self.task_identity=process_identity(self.task.pid);self._register_task(plan);code=self.task.wait(timeout=max(.1,plan.dispatch_cutoff-time.time()))
  finally:stdout.close();stderr.close()
  if code:raise CarrierError('task_actual_exit_nonzero')
  return {'exit':code,'identity':self.task_identity,'argv':argv}
 def _start_guardian(self,plan,lease):
  import local_helper
  fd=local_helper._lease_module._export_package_watcher_fd(lease)
  try:
   config=Path(self.packet['evidenceRoot'])/'guardian.json';value={'transactionId':plan.transaction_id,'carrier':process_identity(os.getpid()),'taskRecordPath':str(Path(self.packet['evidenceRoot'])/'guardian.task-owner.json'),'roots':[str(p) for p in plan.source_roots]+self.packet['taskRoots'],'user':self.packet['user'],'leaseFD':fd,'leaseStat':{'dev':os.fstat(fd).st_dev,'ino':os.fstat(fd).st_ino},'evidenceRoot':self.packet['evidenceRoot']};config.write_text(json.dumps(value));config.chmod(0o600)
   guardian=Path(__file__).with_name('qualification_guardian.py');self.guardian=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(guardian),str(config)],pass_fds=(fd,),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   self.guardian_identity=process_identity(self.guardian.pid)
   until=time.monotonic()+3
   while not (Path(self.packet['evidenceRoot'])/'guardian.ready').exists():
    if self.guardian.poll() is not None or time.monotonic()>until:raise CarrierError('guardian_readiness_unproved')
    time.sleep(.02)
  finally:os.close(fd)
 def _register_task(self,plan):
  self._guardian_current();root=Path(self.packet['evidenceRoot']);p=root/'guardian.task-owner.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  try:os.write(fd,json.dumps({'transactionId':plan.transaction_id,'task':self.task_identity}).encode());os.fsync(fd)
  finally:os.close(fd)
  until=time.monotonic()+3
  while not (root/'guardian.task-ready').exists():
   self._guardian_current()
   if time.monotonic()>until:raise CarrierError('task_guardian_registration_unproved')
   time.sleep(.01)
 def settle_owned_task(self,plan,lease):
  lease.validate()
  if self.task and self.task.poll() is None:
   if process_identity(self.task.pid)!=self.task_identity:raise CarrierError('task_process_identity_changed')
   os.killpg(self.task.pid,signal.SIGTERM)
   try:self.task.wait(timeout=65)
   except subprocess.TimeoutExpired:raise CarrierError('owned_task_close_unproved')
  self.dead=True
  if self.server:self.server.close()
 def assert_task_closed(self,plan,lease):
  lease.validate()
  if self.task and self.task.poll() is None:raise CarrierError('task_still_active')
  v=physical_scope(self.packet['taskRoots'],self.packet['user'])
  if v['writers'] or v['listeners'] or any(c['running'] for c in v['containers']):raise CarrierError('task_physical_scope_not_closed')
 def assert_restored(self,plan,lease,before):
  lease.validate();self.sources();current=self.owner.observe_service('harness')
  if current['active']!='active' or current['sub']!='running' or current['main_pid']==0 or current['invocation']==self.packet['normalService']['invocation']:raise CarrierError('normal_restoration_identity_unproved')
  roots=[str(p) for p in plan.source_roots];v=physical_scope(roots,self.packet['user']);pid=current['main_pid']
  if {x['port'] for x in v['listeners']}!={8080,8081} or any(x['pid']!=pid for x in v['listeners']):raise CarrierError('restored_listener_owner_unproved')
  actual_tuple=observe_normal_tuple(self.packet,pid);verify_normal_tuple(self.packet['normalTuple'],actual_tuple)
  if not any(x['pid']==pid and (x['objectDev'],x['objectIno'])==(actual_tuple['database']['dev'],actual_tuple['database']['ino']) for x in v['writers']):raise CarrierError('restored_exact_db_fd_unproved')
  # Never claim restored bytes identical after genuine original-release recovery.
  result={'normalService':current,'normalTuple':actual_tuple,'physical':v,'recoveryDelta':verify_retained_records(self.original_records,retained_record_snapshot(self.packet['normalDatabase'])),'oldOwnersReconciled':False}
  self._release_guardian(plan)
  return result
 def retain_restore_needed(self,plan,reason):
  p=Path(self.packet['evidenceRoot'])/'RESTORE-NEEDED.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  try:os.write(fd,json.dumps({'transactionId':plan.transaction_id,'reason':reason,'noReplay':True,'identity':process_identity(os.getpid())}).encode());os.fsync(fd)
  finally:os.close(fd)

def observe_normal_tuple(packet,pid):
 """Actual process/source/data/readiness, no environment/config/log bodies."""
 import http.client
 proc=Path('/proc')/str(pid);owner=process_identity(pid);expected=packet['normalTuple'];files={}
 for path,pin in expected['files'].items():
  raw=checked_bytes(path,uid=pin['uid'],bound=512*1024*1024);st=Path(path).lstat();files[path]={'sha256':hashlib.sha256(raw).hexdigest(),'uid':st.st_uid,'mode':oct(stat.S_IMODE(st.st_mode)),'nlink':st.st_nlink,'resolved':str(Path(path).resolve())}
 db=Path(packet['normalDatabase']);st=db.lstat()
 if db.resolve()!=db or not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise CarrierError('normal_database_alias')
 fds=[]
 for fd in (proc/'fd').iterdir():
  try:f=fd.stat()
  except FileNotFoundError:continue
  if (f.st_dev,f.st_ino)==(st.st_dev,st.st_ino):fds.append(fd.name)
 safe={};raw=(proc/'environ').read_bytes()
 for item in raw.split(b'\0'):
  if b'=' not in item:continue
  key,value=item.split(b'=',1)
  if key.decode() in ['NODE_OPTIONS','NODE_PATH','LD_PRELOAD','LD_LIBRARY_PATH'] and value:raise CarrierError('normal_process_preload')
  if key.decode() in expected['paths']:safe[key.decode()]=value.decode('utf8')
 # Fixed read-only application health; frozen Host is source-reviewed, no URL oracle.
 host=expected['health'].get('host')
 if host not in ['localhost:8080','sova.lan','sova.local']:raise CarrierError('frozen_normal_health_host_required')
 connection=http.client.HTTPConnection('127.0.0.1',8080,timeout=3)
 try:
  connection.request('GET','/api/health',headers={'Host':host});response=connection.getresponse();raw=response.read(4097)
  if len(raw)>4096:raise CarrierError('health_bound')
  body=json.loads(raw);health={'http':response.status,'status':body.get('status'),'version':body.get('version'),'host':host}
 finally:connection.close()
 result={'process':{**owner,'cmdlineSHA256':hashlib.sha256((proc/'cmdline').read_bytes()).hexdigest(),'exe':str((proc/'exe').resolve()),'cwd':str((proc/'cwd').resolve()),'cgroup':(proc/'cgroup').read_text().strip(),'mountNamespace':(proc/'ns/mnt').stat().st_ino},'paths':safe,'files':files,'database':{'path':str(db),'dev':st.st_dev,'ino':st.st_ino,'ownedFDs':fds},'health':health}
 if process_identity(pid)!=owner:raise CarrierError('normal_process_changed')
 return result

def verify_normal_tuple(expected,actual):
 for key in ['cmdlineSHA256','exe','cwd','cgroup','mountNamespace','bootId']:
  if actual['process'][key]!=expected['process'][key]:raise CarrierError('normal_release_process_tuple_changed')
 if actual['paths']!=expected['paths']:raise CarrierError('normal_paths_or_config_changed')
 if set(actual['files'])!=set(expected['files']):raise CarrierError('normal_source_closure_changed')
 for path,old in expected['files'].items():
  if any(actual['files'][path].get(k)!=old.get(k) for k in ['sha256','uid','mode','nlink','resolved']):raise CarrierError('normal_source_or_credential_changed')
 if any(actual['database'].get(k)!=expected['database'].get(k) for k in ['path','dev','ino']) or not actual['database']['ownedFDs']:raise CarrierError('normal_data_fd_changed')
 if expected['health'].get('http')!=200 or expected['health'].get('status')!='ok' or any(actual['health'].get(k)!=expected['health'].get(k) for k in ['http','status','version','host']):raise CarrierError('normal_readiness_unproved')
 return True

def retained_record_snapshot(database):
 """Read-only SQLite snapshot; hash every original field without exporting chats.

 The read transaction includes WAL state. It never constructs Store/migrates.
 """
 import sqlite3
 from urllib.parse import quote
 db=sqlite3.connect('file:'+quote(str(database))+'?mode=ro',uri=True,timeout=.5)
 try:
  db.execute('BEGIN');result={}
  for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
   identifier='"'+table.replace('"','""')+'"';info=db.execute('PRAGMA table_info('+identifier+')').fetchall();columns=[r[1] for r in info];keys=[r[1] for r in sorted(info,key=lambda r:r[5]) if r[5]]
   rows={}
   for row in db.execute('SELECT * FROM '+identifier):
    def digest(value):return hashlib.sha256((value if isinstance(value,bytes) else json.dumps(value,sort_keys=True,separators=(',',':')).encode())).hexdigest()
    fields={k:digest(v) for k,v in zip(columns,row)};key=hashlib.sha256(json.dumps([fields[k] for k in keys] if keys else list(fields.values())).encode()).hexdigest()
    if key in rows:raise CarrierError('ambiguous_original_record_identity')
    rows[key]={'fields':fields,'status':{k:v for k,v in zip(columns,row) if k in ['status','ownership','updated_at']}}
   result[table]={'columns':columns,'primaryKey':keys,'rows':rows}
  return result
 finally:db.close()

def verify_retained_records(before,after):
 if set(before)!=set(after):raise CarrierError('original_table_set_changed')
 delta=[]
 for table,old in before.items():
  new=after[table]
  if old['columns']!=new['columns'] or old['primaryKey']!=new['primaryKey'] or set(old['rows'])!=set(new['rows']):raise CarrierError('original_record_identity_changed')
  for key,row in old['rows'].items():
   nextrow=new['rows'][key]
   for field,digest in row['fields'].items():
    if nextrow['fields'][field]==digest:continue
    permitted=(field=='status' and row['status'].get(field) in ['queued','running','cancelling'] and nextrow['status'].get(field) in ['error','failed','cancelled']) or (field=='ownership' and nextrow['status'].get(field)=='uncertain') or (field in ['error','updated_at'] and row['status'].get('status') in ['queued','running','cancelling'])
    if field in old['primaryKey'] or not permitted:raise CarrierError('original_nonrecovery_field_changed')
    delta.append({'table':table,'recordIdentitySHA256':key,'field':field,'beforeSHA256':digest,'afterSHA256':nextrow['fields'][field]})
 return delta
