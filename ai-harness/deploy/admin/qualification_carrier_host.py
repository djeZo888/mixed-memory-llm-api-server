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

def physical_scope(roots,uid,ports=(8080,8081,18081)):
 """Complete root FD census, model mount census and listener proof; unknown aborts."""
 targets=[Path(p) for p in roots];writers=[];listeners=[];inodes=set()
 for table in ['/proc/net/tcp','/proc/net/tcp6']:
  for line in Path(table).read_text().splitlines()[1:]:
   parts=line.split()
   if int(parts[1].split(':')[1],16) in ports and parts[3]=='0A':inodes.add(parts[9])
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   for fd in (proc/'fd').iterdir():
    try:link=os.readlink(fd)
    except FileNotFoundError:continue
    if link.startswith('socket:[') and link[8:-1] in inodes:listeners.append({'pid':int(proc.name),'socketInode':link[8:-1]})
    clean=link.removesuffix(' (deleted)')
    if any(clean==str(p) or clean.startswith(str(p)+'/') for p in targets):writers.append({'pid':int(proc.name),'fd':fd.name,'path':clean})
  except FileNotFoundError:continue
  except PermissionError:raise CarrierError('incomplete_kernel_fd_observation')
 command=['/usr/sbin/runuser','--user',uid['name'],'--','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+uid['home'],'XDG_RUNTIME_DIR=/run/user/'+str(uid['uid']),'/usr/bin/podman','--remote=false']
 containers=[]
 result=subprocess.run(command+['ps','-a','--format','json'],capture_output=True,timeout=8,check=True)
 for row in json.loads(result.stdout):
  cid=row.get('Id',row.get('ID'));result=subprocess.run(command+['inspect',cid],capture_output=True,timeout=8,check=True);v=json.loads(result.stdout)[0]
  if any(any(m.get('Source')==str(p) or str(m.get('Source','')).startswith(str(p)+'/') for p in targets) for m in v.get('Mounts',[])):containers.append({'id':cid,'running':v['State']['Running'],'pid':v['State']['Pid']})
 return {'writers':writers,'listeners':listeners,'containers':containers}

class LinuxCarrierHost:
 def __init__(self,packet,owner,freeze,lease_module):
  self.packet,self.owner,self.freeze,self.lease_module=packet,owner,freeze,lease_module;self.task=None;self.task_identity=None;self.server=None;self.channel=None;self.guardian=None;self.original_records=None;self.key=os.urandom(32);self.dead=False
 def sources(self):
  for p,digest in self.packet['privilegedSourceHashes'].items():
   if hashlib.sha256(checked_bytes(p)).hexdigest()!=digest:raise CarrierError('privileged_source_changed')
  for p,digest in self.packet['taskSourceHashes'].items():
   if hashlib.sha256(checked_bytes(p,uid=self.packet['user']['uid'],bound=512*1024*1024)).hexdigest()!=digest:raise CarrierError('task_source_changed')
 def assert_current(self,plan,lease,stage):
  lease.validate();self.sources()
  if process_identity(os.getpid())['bootId']!=plan.boot_id:raise CarrierError('boot_changed')
  self.freeze(plan.stop_request)
  observed=self.owner.observe_service('harness')
  if stage=='before-stop' and observed!=self.packet['normalService']:raise CarrierError('normal_owner_changed')
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
  packet={'schema':'qualification-task-admission-v1','transactionId':plan.transaction_id,'carrier':process_identity(os.getpid()),'socketPath':str(path),'key':self.key.hex(),'sessionId':self.packet['sessionId'],'lane':'qwen3.8-27b','ownHoldKey':self.packet['ownHoldKey'],'dispatchCutoffMs':int(plan.dispatch_cutoff*1000),'expiresAtMs':int(plan.expires_at*1000)}
  fd=os.open(directory/'admission.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
  try:os.write(fd,json.dumps(packet).encode());os.fchown(fd,0,self.packet['user']['gid']);os.fchmod(fd,0o640);os.fsync(fd)
  finally:os.close(fd)
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
     if not hmac.compare_digest(request['mac'],hmac.new(self.key,body.encode(),hashlib.sha256).hexdigest()) or set(v)!={'challenge','transactionId','sessionId','requestId','lane'} or v['transactionId']!=plan.transaction_id or v['sessionId']!=self.packet['sessionId'] or v['lane']!='qwen3.8-27b' or time.time()>=plan.dispatch_cutoff:raise CarrierError('foreign_expired_task_challenge')
     # Same-process capability cannot be borrowed by another thread. Its owner
     # is the carrier main thread/process; validate is PID-based, no FD minting.
     lease.validate();self.sources();self._foreign_holds()
     if self.task is None or self.task.poll() is not None:raise CarrierError('task_owner_lost')
     response=json.dumps({**v,'status':'admit','observedAtMs':int(time.time()*1000),'ownerStartTicks':packet['carrier']['startTicks'],'ownHoldKey':self.packet['ownHoldKey']},separators=(',',':'));c.sendall(json.dumps({'body':response,'mac':hmac.new(self.key,response.encode(),hashlib.sha256).hexdigest()}).encode()+b'\n')
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
  try:self.task=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True);self.task_identity=process_identity(self.task.pid);self._start_guardian(plan,lease);code=self.task.wait(timeout=max(.1,plan.dispatch_cutoff-time.time()))
  finally:stdout.close();stderr.close()
  if code:raise CarrierError('task_actual_exit_nonzero')
  return {'exit':code,'identity':self.task_identity,'argv':argv}
 def _start_guardian(self,plan,lease):
  import local_helper
  fd=local_helper._lease_module._export_package_watcher_fd(lease)
  try:
   config=Path(self.packet['evidenceRoot'])/'guardian.json';value={'transactionId':plan.transaction_id,'carrier':process_identity(os.getpid()),'task':self.task_identity,'roots':[str(p) for p in plan.source_roots]+self.packet['taskRoots'],'user':self.packet['user'],'leaseFD':fd,'leaseStat':{'dev':os.fstat(fd).st_dev,'ino':os.fstat(fd).st_ino},'evidenceRoot':self.packet['evidenceRoot']};config.write_text(json.dumps(value));config.chmod(0o600)
   guardian=Path(__file__).with_name('qualification_guardian.py');self.guardian=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(guardian),str(config)],pass_fds=(fd,),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   until=time.monotonic()+3
   while not (Path(self.packet['evidenceRoot'])/'guardian.ready').exists():
    if self.guardian.poll() is not None or time.monotonic()>until:raise CarrierError('guardian_readiness_unproved')
    time.sleep(.02)
  finally:os.close(fd)
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
  if not v['listeners'] or any(x['pid']!=pid for x in v['listeners']) or not any(x['pid']==pid for x in v['writers']):raise CarrierError('restored_listener_db_owner_unproved')
  # Never claim restored bytes identical after genuine original-release recovery.
  result={'normalService':current,'physical':v,'recoveryDelta':verify_retained_records(self.original_records,retained_record_snapshot(self.packet['normalDatabase'])),'oldOwnersReconciled':False}
  if self.guardian:
   Path(self.packet['evidenceRoot'],'guardian.release').write_text(json.dumps({'carrier':process_identity(os.getpid()),'transactionId':plan.transaction_id}));self.guardian.wait(timeout=3)
   if self.guardian.returncode:raise CarrierError('guardian_release_unproved')
  return result
 def retain_restore_needed(self,plan,reason):
  p=Path(self.packet['evidenceRoot'])/'RESTORE-NEEDED.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  try:os.write(fd,json.dumps({'transactionId':plan.transaction_id,'reason':reason,'noReplay':True,'identity':process_identity(os.getpid())}).encode());os.fsync(fd)
  finally:os.close(fd)

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
