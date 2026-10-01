
import os,sys,json,hashlib,hmac,base64,pathlib,stat,datetime,time,subprocess,signal
P=pathlib.Path;v=json.load(sys.stdin);packet=v['packet'];host=P(packet['hostRoot']);uid=os.getuid();assert uid==1000
sha=lambda b:hashlib.sha256(b).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc)
def stamp():return now().isoformat()
def ident(pid):return {'pid':pid,'startTicks':(P('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19],'bootId':P('/proc/sys/kernel/random/boot_id').read_text().strip()}
def ancestry(p):
 for q in [p,*p.parents]:
  s=q.lstat();assert q.resolve()==q and stat.S_ISDIR(s.st_mode) and s.st_uid in [0,uid] and not s.st_mode&0o022

def guarded(path,bound=16*1024*1024):
 p=P(path);ancestry(p.parent);s=p.lstat();assert p.resolve()==p and stat.S_ISREG(s.st_mode) and s.st_uid in [0,uid] and s.st_nlink==1 and not s.st_mode&0o022 and s.st_size<=bound
 f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  old=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns);raw=b''
  while True:
   b=os.read(f,1024*1024)
   if not b:break
   raw+=b
  a=os.fstat(f);n=p.lstat();assert old==(a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(n.st_dev,n.st_ino,n.st_size,n.st_mtime_ns,n.st_ctime_ns) and len(raw)==s.st_size
  return raw
 finally:os.close(f)

def put(p,raw):
 f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  os.fchmod(f,0o600);view=memoryview(raw)
  while view:view=view[os.write(f,view):]
  os.fsync(f)
 finally:os.close(f)

approval=base64.b64decode(v['approval']);key=base64.b64decode(v['key']);assert sha(approval)=='43b9fddb07cef73faebcb35e85c1b19186aa1774096157231d27b6a6731e3020';a=json.loads(approval);body=a['body'];assert hmac.compare_digest(a['seal'],hmac.new(key,json.dumps(body,separators=(',',':'),ensure_ascii=False).encode(),hashlib.sha256).hexdigest())
cutoff=datetime.datetime.fromisoformat(body['dispatchBeforeUtc']);end=datetime.datetime.fromisoformat(body['endBeforeUtc']);assert now()<cutoff and body['maximumCommandSeconds']==300 and body['candidateCommit']==packet['candidateCommit'] and body['repositoryRoot']==packet['input']['repositoryRoot']
script=host/'no-turn-transport09d.mjs';inputp=host/'input.json';node=P(packet['input']['nodePath']);assert sha(guarded(inputp))==body['inputSHA256'] and sha(guarded(script))==body['scriptSHA256'] and sha(guarded(node,128*1024*1024))==packet['input']['nodeSHA256']
for name,digest in body['helpers'].items():assert sha(guarded(host/name))==digest
for p in [host,host/'result',P(packet['taskRoot']),P(packet['input']['launchInput']['profileDir']),P(packet['input']['launchInput']['workspace'])]:
 ancestry(p);s=p.lstat();assert s.st_uid==uid and stat.S_IMODE(s.st_mode)==0o700
for p in [host/'result',P(packet['input']['launchInput']['profileDir']),P(packet['input']['launchInput']['workspace'])]:assert not list(p.iterdir())
input=json.loads(guarded(inputp));repo=P(input['repositoryRoot']);roots={'build':repo/'ai-harness/server/dist','source':repo/'ai-harness/server/src','deploy':repo/'ai-harness/deploy','tools':repo/'ai-harness/tools','skills':repo/'ai-harness/skills','config':repo/'ai-harness/config','dependencies':P(input['dependencyRoot'])}
def closure():
 for kind,root in roots.items():
  ancestry(root);actual={}
  for p in sorted(root.rglob('*')):
   s=p.lstat();name=str(p.relative_to(root))
   if p.is_symlink():
    target=p.resolve();assert target.is_relative_to(root);actual[name]={'type':'link','target':str(target.relative_to(root))}
   elif p.is_file():actual[name]={'sha256':sha(guarded(p,128*1024*1024)),'bytes':s.st_size}
   elif p.is_dir():ancestry(p)
   else:raise ValueError('source_object')
  assert actual==input['closure'][kind]
 for n,d in input['closure']['packages'].items():assert sha(guarded(repo/'ai-harness/server'/n))==d
 for n,d in input['receiptPolicy']['sourceSha256'].items():assert sha(guarded(repo/'ai-harness/deploy'/n))==d
 assert (repo/'ai-harness/server/node_modules').resolve()==P(input['dependencyRoot'])
closure();env={'PATH':'/usr/bin:/bin','LANG':'C','HOME':'/home/user','XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
def observe(name):
 argv=['/usr/bin/python3','-I','-S','-B',str(host/'legacy-gateway-observer06.py'),str(inputp),str(host/'result')];r=subprocess.run(argv,env=env,capture_output=True,timeout=20);put(host/(name+'.original.json'),r.stdout);assert r.returncode==0;return json.loads(r.stdout)
def equal(before,after):return all(before[k]==after[k] for k in ['identity','requestIds','retainedRecords','counts','nativeOwners'])
before=observe('wrapper-before');assert equal(packet['observation'],before) and time.time()*1000-before['observedAtMs']<60000 and now()<cutoff
approvalp=host/'root-issued-go09d.approval.json';keyp=host/'root-issued-go09d.key.bin';put(approvalp,approval);put(keyp,key)
argv=[str(node),str(script),str(inputp),str(approvalp),str(keyp),str(host/'result')];assert not any(k in env for k in ['NODE_OPTIONS','NODE_PATH','LD_PRELOAD','LD_LIBRARY_PATH'])
stdout=host/'native-command.stdout.private';stderr=host/'native-command.stderr.private';outfd=os.open(stdout,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);errfd=os.open(stderr,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);gate_r,gate_w=os.pipe();ready_r,ready_w=os.pipe();started=stamp();pid=os.fork()
if pid==0:
 try:
  os.close(gate_w);os.close(ready_r);os.setsid();os.write(ready_w,b'R');os.close(ready_w)
  if os.read(gate_r,1)!=b'G':os._exit(125)
  os.close(gate_r);os.dup2(outfd,1);os.dup2(errfd,2);null=os.open('/dev/null',os.O_RDONLY);os.dup2(null,0);os.execve(str(node),argv,env)
 except BaseException:os._exit(126)
os.close(gate_r);os.close(ready_w);assert os.read(ready_r,1)==b'R';os.close(ready_r);owner=ident(pid)
try:
 assert now()<cutoff and time.time()*1000-before['observedAtMs']<60000
 claim={'schema':'h041-single-no-turn-invocation09d-v1','argv':argv,'startedUtc':started,'actualProcess':owner,'inputSHA256':body['inputSHA256'],'callerSHA256':body['scriptSHA256'],'approvalSHA256':sha(approval),'dispatchBeforeUtc':body['dispatchBeforeUtc'],'endBeforeUtc':body['endBeforeUtc'],'maximumCommandSeconds':300};put(P(body['exclusiveClaimPath']),json.dumps(claim).encode());os.write(gate_w,b'G')
finally:os.close(gate_w);os.close(outfd);os.close(errfd)
startmono=time.monotonic();status=None;timed=False
while status is None:
 got,raw=os.waitpid(pid,os.WNOHANG)
 if got:status=raw;break
 if time.monotonic()-startmono>=300 or now()>=end:
  timed=True
  if ident(pid)==owner:os.killpg(pid,signal.SIGTERM)
  got,status=os.waitpid(pid,0);break
 time.sleep(.05)
code=os.waitstatus_to_exitcode(status);after=observe('wrapper-after');closure();assert sha(guarded(script))==body['scriptSHA256'] and sha(guarded(inputp))==body['inputSHA256']
for n,d in body['helpers'].items():assert sha(guarded(host/n))==d
result={'schema':'actual-no-turn09d-command-v1','argv':argv,'startedUtc':started,'finishedUtc':stamp(),'actualProcess':owner,'exit':code,'deadlineTermination':timed,'normalRetainedStateEqual':equal(before,after),'beforeObservedAtMs':before['observedAtMs'],'afterObservedAtMs':after['observedAtMs'],'stdoutSHA256':sha(guarded(stdout)),'stderrSHA256':sha(guarded(stderr)),'finalWholeSourceClosureRechecked':True,'nativeAcceptance':'NOT_TESTED','scope':'single initialize/readOnly thread/start/owned close; no generation/service lifecycle'};put(host/'actual-command-receipt09d.json',json.dumps(result,indent=2).encode());print(json.dumps(result));sys.exit(0 if code==0 and result['normalRetainedStateEqual'] and not timed else 1)
