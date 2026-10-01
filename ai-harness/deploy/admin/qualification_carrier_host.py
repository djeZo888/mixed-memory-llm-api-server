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

def _retained_digest(value):
 # Include the SQLite value type: BLOB and text must never share a digest.
 if isinstance(value,bytes):raw=b'blob\0'+value
 else:raw=(type(value).__name__+'\0'+json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)).encode()
 return hashlib.sha256(raw).hexdigest()

def _retained_keys(value):
 # JSON.parse/stringify enumerate array-index keys first, in numeric order.
 integer=lambda k:k.isascii() and k.isdigit() and str(int(k))==k and int(k)<4294967295
 return sorted((k for k in value if integer(k)),key=int)+[k for k in value if not integer(k)]

def _retained_tree(value):
 """Ordered JSON structure with hashed keys/scalars, never chat/body text."""
 if isinstance(value,dict):return ['object',[[_retained_digest(k),_retained_tree(value[k])] for k in _retained_keys(value)]]
 if isinstance(value,list):return ['array',[_retained_tree(v) for v in value]]
 if isinstance(value,float) and value.is_integer():value=int(value)
 return ['scalar',_retained_digest(value)]

def _retained_set(tree,key,value):
 import copy
 result=copy.deepcopy(tree)
 if result[0]!='object':raise CarrierError('recovery_json_object_required')
 for pair in result[1]:
  if pair[0]==_retained_digest(key):pair[1]=_retained_tree(value);break
 else:result[1].append([_retained_digest(key),_retained_tree(value)])
 return result

def _retained_json(raw):
 def unique(pairs):
  result={}
  for key,value in pairs:
   if key in result:raise ValueError('duplicate_json_key')
   result[key]=value
  return result
 try:return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
 except (TypeError,ValueError):raise CarrierError('retained_json_invalid')

def _retained_source_json(value):
 """JSON.stringify encoding for preserved JSON data; unsupported data fails closed."""
 import math,decimal
 if isinstance(value,dict):
  keys=_retained_keys(value)
  return '{'+','.join(_retained_source_json(k)+':'+_retained_source_json(value[k]) for k in keys)+'}'
 if isinstance(value,list):return '['+','.join(_retained_source_json(v) for v in value)+']'
 if value is None:return 'null'
 if isinstance(value,bool):return 'true' if value else 'false'
 if isinstance(value,str):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
 if isinstance(value,int):
  if abs(value)>9007199254740991:raise CarrierError('unsafe_json_integer_evidence')
  return str(value)
 if isinstance(value,float):
  if not math.isfinite(value):raise CarrierError('nonfinite_json_evidence')
  if value==0:return '0'
  text=repr(value).lower()
  if 1e-6<=abs(value)<1e21:return format(decimal.Decimal(text),'f').rstrip('0').rstrip('.') if '.' in format(decimal.Decimal(text),'f') else format(decimal.Decimal(text),'f')
  mantissa,exponent=text.split('e') if 'e' in text else (text,'0')
  return mantissa.removesuffix('.0')+'e'+('+' if int(exponent)>=0 else '-')+str(abs(int(exponent)))
 raise CarrierError('unsupported_json_evidence')

def _retained_engine_readable(db,values):
 # Store.getSession's post-ownership-update checks, without exposing native IDs.
 import re
 required={'session_id','engine_kind','workspace_id','event_cursor','ownership','active_turn_id'}
 if not required<=set(values):return False
 session=db.execute('SELECT workspace_id FROM sessions WHERE id=?',(values['session_id'],)).fetchone()
 cursor=values['event_cursor'];turn=values['active_turn_id'];ownership=values['ownership']
 return bool(session and values['engine_kind'] in ['minimax','codex'] and session[0]==values['workspace_id'] and type(cursor) is int and 0<=cursor<=9007199254740991 and ownership in ['idle','active','uncertain'] and (turn is None or isinstance(turn,str) and turn and not re.search(r'[\x00-\x20\x7f]',turn)) and (ownership!='idle' or turn is None))

def _retained_run_projection(db,run,tables):
 """The read-only relational projection used by Store.runSnapshot/emitRun.

 Cross-run image status consumption needs a separate image qualification proof;
 this verifier fails closed for that shape rather than trusting opaque additions.
 """
 sid=run['session_id'];rid=run['id']
 needed={'files','messages','h002_file_refs','h002_message_meta','h002_subagents','h036_image_status_refs'}
 if not needed<=tables:raise CarrierError('source_run_projection_schema_required')
 if db.execute('SELECT 1 FROM h036_image_status_refs WHERE session_id=? AND run_id=?',(sid,rid)).fetchone():
  raise CarrierError('cross_run_image_projection_unqualified')
 artifacts=[r[0] for r in db.execute("SELECT f.id FROM files f JOIN h002_file_refs r ON r.file_id=f.id WHERE f.session_id=? AND f.kind='artifact' AND r.run_id=? ORDER BY f.rowid",(sid,rid))]
 requested=_retained_json(run['attachment_ids'])
 if not isinstance(requested,list) or any(not isinstance(x,str) for x in requested):raise CarrierError('source_attachment_ids_invalid')
 attachments=[]
 for aid in dict.fromkeys(requested):
  if db.execute("SELECT id FROM files WHERE id=? AND session_id=? AND kind='attachment'",(aid,sid)).fetchone():attachments.append(aid)
 final=None
 for mid,meta in db.execute('SELECT m.id,p.data FROM messages m LEFT JOIN h002_message_meta p ON p.message_id=m.id WHERE m.session_id=? AND m.run_id=? ORDER BY m.rowid',(sid,rid)):
  if meta is not None and _retained_json(meta).get('phase')=='final':final=mid
 summary=db.execute('SELECT data FROM h002_subagents WHERE run_id=?',(rid,)).fetchone()
 result={'id':rid,'kind':run['kind'],'status':'interrupted','createdAt':run['created_at'],'updatedAt':run['updated_at'],'finalMessageId':final,'artifactIds':artifacts,'attachmentIds':attachments}
 if len(artifacts)+len(attachments)>1 and len(attachments)==len(set(requested)):result['filesZipUrl']=f'/api/sessions/{sid}/runs/{rid}/files.zip'
 if len(artifacts)>1:result['zipUrl']=f'/api/sessions/{sid}/runs/{rid}/artifacts.zip'
 result['subagents']=_retained_json(summary[0]) if summary else {'known':False,'active':None,'completed':None,'failed':None,'cancelled':None}
 return _retained_tree(result)

def retained_record_snapshot(database):
 """One consistent read-only SQLite/WAL transaction; no Store or body export.

 PK identities and genuine rowids bind every prior row and its order, including
 duplicate keyless history. JSON evidence exports structure and scalar hashes.
 """
 import sqlite3,datetime
 from urllib.parse import quote
 started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 db=sqlite3.connect('file:'+quote(str(database))+'?mode=ro',uri=True,timeout=.5)
 try:
  db.execute('BEGIN');result={}
  schema=db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
  tables={r[1] for r in schema if r[0]=='table'}
  json_fields={'sessions':['context'],'events':['data'],'h041_session_checkpoints':['body'],'h041_checkpoint_transitions':['body']}
  linkage={'runs':['id','session_id','workspace_id','status','created_at','updated_at'], 'sessions':['id','workspace_id','status','updated_at'], 'h021_session_engines':['session_id','engine_kind','ownership'], 'events':['session_id','id','type','run_id','created_at'], 'quarantined_workspaces':['id','reason'], 'h041_session_checkpoints':['id','session_id','run_id','status'], 'h041_checkpoint_transitions':['session_id','run_id']}
  for table in sorted(tables):
   identifier='"'+table.replace('"','""')+'"'
   info=db.execute('PRAGMA table_xinfo('+identifier+')').fetchall();columns=[r[1] for r in info];keys=[r[1] for r in sorted(info,key=lambda r:r[5]) if r[5]]
   sql=next(r[3] for r in schema if r[0]=='table' and r[1]==table)
   without_rowid='WITHOUT ROWID' in sql.upper()
   if any(c.lower() in ['rowid','_rowid_','oid'] for c in columns):raise CarrierError('shadowed_sqlite_row_identity')
   if without_rowid and not keys:raise CarrierError('genuine_row_identity_required')
   order_sql=','.join('"'+k.replace('"','""')+'"' for k in keys) if without_rowid else '_rowid_'
   select='SELECT '+('' if without_rowid else '_rowid_,')+'* FROM '+identifier+' ORDER BY '+order_sql
   rows={};order=[]
   for raw in db.execute(select):
    rowid=None if without_rowid else raw[0];values=dict(zip(columns,raw if without_rowid else raw[1:]))
    key=_retained_digest([values[k] for k in keys]) if keys else 'rowid:'+str(rowid)
    if key in rows:raise CarrierError('ambiguous_original_record_identity')
    row={'rowid':rowid,'fields':{k:_retained_digest(v) for k,v in values.items()},'meta':{k:values[k] for k in linkage.get(table,[]) if k in values},'json':{k:_retained_tree(_retained_json(values[k])) for k in json_fields.get(table,[]) if k in values},'sourceJSON':{k:values[k]==_retained_source_json(_retained_json(values[k])) for k in json_fields.get(table,[]) if k in values}}
    if table=='h021_session_engines' and 'sessions' in tables:row['sourceEngineReadable']=_retained_engine_readable(db,values)
    if table=='runs' and values.get('status') in ['queued','running','cancelling'] and {'session_id','kind','attachment_ids','created_at','updated_at'}<=set(values):row['runProjection']=_retained_run_projection(db,values,tables)
    rows[key]=row;order.append(key)
   result[table]={'columns':columns,'primaryKey':keys,'schema':info,'sqlSHA256':_retained_digest(sql),'rows':rows,'order':order}
  result['_snapshot']={'schemaSHA256':_retained_digest(schema),'startedAt':started,'finishedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  return result
 finally:db.close()

def verify_retained_records(before,after):
 """Accept only the complete source-derived normal Store constructor repair."""
 import datetime,re
 def fail(reason):raise CarrierError(reason)
 oldtables=set(before)-{'_snapshot'};newtables=set(after)-{'_snapshot'}
 if oldtables!=newtables:fail('original_table_set_changed')
 if before['_snapshot']['schemaSHA256']!=after['_snapshot']['schemaSHA256']:fail('original_schema_changed')
 for table in oldtables:
  for k in ['columns','primaryKey','schema','sqlSHA256']:
   if before[table][k]!=after[table][k]:fail('original_schema_changed')
 def rows(snapshot,table):return snapshot.get(table,{}).get('rows',{})
 def indexed(snapshot,table,key):
  result={}
  for identity,row in rows(snapshot,table).items():
   if key not in row['meta']:fail('source_recovery_schema_required')
   value=row['meta'][key]
   if value in result:fail('source_recovery_link_ambiguous')
   result[value]=(identity,row)
  return result
 runs=indexed(before,'runs','id');sessions=indexed(before,'sessions','id');engines=indexed(before,'h021_session_engines','session_id')
 affected_runs={rid:pair for rid,pair in runs.items() if pair[1]['meta'].get('status') in ['queued','running','cancelling']}
 affected_sessions={r['meta'].get('session_id') for _,r in affected_runs.values()}|{sid for sid,(_,r) in engines.items() if r['meta'].get('engine_kind')=='codex' and r['meta'].get('ownership')!='idle'}
 if affected_sessions-set(sessions):fail('source_affected_session_missing')
 workspaces={sessions[sid][1]['meta'].get('workspace_id') for sid in affected_sessions}
 checkpoints={key:rows(before,'h041_session_checkpoints')[key] for key in before.get('h041_session_checkpoints',{}).get('order',[]) if rows(before,'h041_session_checkpoints')[key]['meta'].get('status') in ['prepared','replacement_observed']}
 if None in affected_sessions or None in workspaces:fail('source_recovery_schema_required')
 delta=[];changes={};expected_events=[];expected_transitions=[]
 lower=datetime.datetime.fromisoformat(before['_snapshot']['startedAt']);upper=datetime.datetime.fromisoformat(after['_snapshot']['finishedAt'])
 def timestamp(value):
  if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z',value):fail('source_recovery_timestamp_required')
  try:time=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
  except ValueError:fail('source_recovery_timestamp_required')
  if not lower<=time<=upper:fail('source_recovery_timestamp_outside_snapshot')
  return time
 def successor(table,key):
  if key not in rows(after,table):fail('original_record_identity_changed')
  return rows(after,table)[key]
 def allow(table,key,expected):changes[(table,key)]=expected
 run_times=set()
 # SQLite SELECT without ORDER BY scans these source run rows in rowid order.
 for key in before.get('runs',{}).get('order',[]):
  old=rows(before,'runs')[key];rid=old['meta'].get('id')
  if rid not in affected_runs:continue
  new=successor('runs',key);time=new['meta'].get('updated_at');timestamp(time);run_times.add(time)
  if 'runProjection' not in old:fail('source_run_projection_required')
  allow('runs',key,{'status':_retained_digest('interrupted'),'updated_at':_retained_digest(time)})
  projection=_retained_set(old['runProjection'],'updatedAt',time)
  expected_events.append((old['meta']['session_id'],'run',rid,['object',[[_retained_digest('run'),projection]]]))
 if len(run_times)>1:fail('source_run_update_timestamp_mismatch')
 for sid in sorted(affected_sessions):
  key,old=sessions[sid];new=successor('sessions',key);time=new['meta'].get('updated_at');timestamp(time)
  if 'context' not in old['json']:fail('source_context_required')
  context=_retained_set(old['json']['context'],'stale',True)
  if not new['sourceJSON'].get('context') or new['json'].get('context')!=context:fail('original_context_evidence_changed')
  allow('sessions',key,{'status':_retained_digest('interrupted'),'updated_at':_retained_digest(time),'context':new['fields']['context']})
  if sid not in engines:fail('source_engine_identity_required')
  enginekey,engine=engines[sid]
  if not successor('h021_session_engines',enginekey).get('sourceEngineReadable'):fail('source_engine_identity_unreadable')
  if engine['meta']['engine_kind']=='codex':allow('h021_session_engines',enginekey,{'ownership':_retained_digest('uncertain')})
  expected_events.extend([(sid,'state',None,_retained_tree({'status':'interrupted'})),(sid,'context',None,['object',[[_retained_digest('context'),context]]]),(sid,'error',None,_retained_tree({'code':'interrupted','message':'Server restarted; the run was interrupted and was not replayed'}))])
 for key,old in checkpoints.items():
  new=successor('h041_session_checkpoints',key)
  if 'body' not in old['json']:fail('source_checkpoint_body_required')
  body=_retained_set(_retained_set(old['json']['body'],'outcome','process_restart'),'status','recovery_required')
  if not new['sourceJSON'].get('body') or new['json'].get('body')!=body:fail('original_checkpoint_evidence_changed')
  allow('h041_session_checkpoints',key,{'status':_retained_digest('recovery_required'),'body':new['fields']['body']})
  expected_transitions.append((old['meta']['session_id'],old['meta']['run_id'],body))
 # Every preexisting row survives with its exact identity/order/multiplicity.
 # Only source quarantine INSERT OR REPLACE may change rowid/order.
 for table in oldtables:
  old=before[table];new=after[table]
  if table=='quarantined_workspaces':continue
  if set(old['rows'])-set(new['rows']):fail('original_record_identity_changed')
  if table in ['events','h041_checkpoint_transitions'] and new['order'][:len(old['order'])]!=old['order']:fail('source_history_append_order_required')
  if [k for k in new['order'] if k in old['rows']]!=old['order']:fail('original_record_order_changed')
  for key,row in old['rows'].items():
   nextrow=new['rows'][key]
   if row['rowid']!=nextrow['rowid']:fail('original_rowid_changed')
   permitted=changes.get((table,key),{})
   if set(row['fields'])!=set(nextrow['fields']):fail('original_schema_changed')
   for field,digest in row['fields'].items():
    expected=permitted.get(field,digest)
    if nextrow['fields'][field]!=expected:fail('original_nonrecovery_field_changed')
    if digest!=expected:delta.append({'table':table,'recordIdentitySHA256':key,'field':field,'beforeSHA256':digest,'afterSHA256':expected})
  if table not in ['events','h041_checkpoint_transitions'] and set(new['rows'])!=set(old['rows']):fail('unexpected_original_record_added')
 # New quarantine rows are exact source reason writes for the derived workspace set.
 oldq=indexed(before,'quarantined_workspaces','id');newq=indexed(after,'quarantined_workspaces','id')
 if affected_sessions and before.get('quarantined_workspaces',{}).get('columns')!=['id','reason']:fail('source_quarantine_schema_required')
 if set(newq)!=set(oldq)|workspaces:fail('unrelated_quarantine_changed')
 for wid,(key,row) in newq.items():
  if wid in workspaces:
   if row['fields']!={'id':_retained_digest(wid),'reason':_retained_digest('restart_during_run')}:fail('source_quarantine_reason_required')
   delta.append({'table':'quarantined_workspaces','recordIdentitySHA256':key,'field':'reason','operation':'source_restart_quarantine'})
  elif row!=oldq[wid][1]:fail('unrelated_quarantine_changed')
 # Simulate each exact INSERT OR REPLACE, including duplicate workspace owners.
 expected_q={wid:row['rowid'] for wid,(_,row) in oldq.items()}
 for sid in sorted(affected_sessions):
  wid=sessions[sid][1]['meta']['workspace_id'];nextid=max(expected_q.values(),default=0)+1;expected_q[wid]=nextid
 if any(newq[wid][1]['rowid']!=rid for wid,rid in expected_q.items()):fail('source_quarantine_rowid_required')
 if [rows(after,'quarantined_workspaces')[k]['meta']['id'] for k in after.get('quarantined_workspaces',{}).get('order',[])]!=sorted(expected_q,key=expected_q.get):fail('source_quarantine_order_required')
 def appended(table):
  added=[(k,rows(after,table)[k]) for k in after.get(table,{}).get('order',[]) if k not in rows(before,table)]
  last=max((r['rowid'] for r in rows(before,table).values()),default=0)
  for _,row in added:
   last+=1
   if row['rowid']!=last:fail('source_history_append_rowid_required')
  return added
 additions=appended('events')
 if len(additions)!=len(expected_events):fail('source_recovery_event_count_mismatch')
 cursors={};previous_time=None;session_event_times={}
 for row in rows(before,'events').values():
  meta=row['meta'];sid=meta['session_id'];cursors[sid]=max(cursors.get(sid,0),meta['id'])
 for (key,event),(sid,kind,rid,data) in zip(additions,expected_events):
  meta=event['meta'];created=meta.get('created_at');time=timestamp(created)
  if previous_time is not None and time<previous_time:fail('source_recovery_event_time_order')
  previous_time=time;cursors[sid]=cursors.get(sid,0)+1
  if not event['sourceJSON'].get('data'):fail('source_event_json_encoding_required')
  if meta!={'session_id':sid,'id':cursors[sid],'type':kind,'run_id':rid,'created_at':created} or event['json'].get('data')!=data:fail('source_recovery_event_payload_mismatch')
  if set(event['fields'])!={'session_id','id','type','run_id','created_at','data'}:fail('source_event_schema_required')
  if run_times and time<timestamp(next(iter(run_times))):fail('source_event_before_run_update')
  session_event_times.setdefault(sid,{})[kind]=time
  delta.append({'table':'events','recordIdentitySHA256':key,'operation':'source_recovery_append','type':kind})
 for sid in affected_sessions:
  times=session_event_times[sid];updated=timestamp(successor('sessions',sessions[sid][0])['meta']['updated_at'])
  if not times['state']<=updated<=times['context']:fail('source_session_update_event_timestamp_mismatch')
 transitions=appended('h041_checkpoint_transitions')
 if len(transitions)!=len(expected_transitions):fail('source_checkpoint_transition_count_mismatch')
 for (key,row),(sid,rid,body) in zip(transitions,expected_transitions):
  if not row['sourceJSON'].get('body') or row['meta']!={'session_id':sid,'run_id':rid} or row['json'].get('body')!=body or set(row['fields'])!={'session_id','run_id','body'}:fail('source_checkpoint_transition_payload_mismatch')
  delta.append({'table':'h041_checkpoint_transitions','recordIdentitySHA256':key,'operation':'source_checkpoint_append'})
 return delta
