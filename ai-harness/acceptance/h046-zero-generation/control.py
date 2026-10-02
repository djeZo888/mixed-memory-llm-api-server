#!/usr/bin/env python3
"""Finite H046 HMAC source-bound driver; no GO is generated here."""
import argparse, hashlib, hmac, json, os, re, signal, stat, subprocess, time
from datetime import datetime
from pathlib import Path

class Denied(RuntimeError): pass
def need(value,message):
    if not value: raise Denied(message)
def canonical(value):
    if isinstance(value,dict):
        need(all(isinstance(k,str) for k in value),'nonstring key')
        return '{'+','.join(json.dumps(k,ensure_ascii=False)+':'+canonical(value[k]) for k in sorted(value,key=lambda s:s.encode('utf-16-be','surrogatepass'))) +'}'
    if isinstance(value,list):return '['+','.join(canonical(v) for v in value)+']'
    need(value is None or isinstance(value,(str,bool)) or type(value) is int and abs(value)<=9007199254740991,'unsafe signed JSON value')
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ident(path):
    s=Path(path).lstat();return dict(dev=s.st_dev,ino=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode),nlink=s.st_nlink)
def private(path,maxbytes,uid=None):
    p=Path(path);uid=os.getuid() if uid is None else uid
    need(p.is_absolute() and p.resolve()==p,'noncanonical private path')
    for parent in p.parents:
        s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022 and s.st_uid in (0,uid),'unsafe private ancestry')
    parent=p.parent.lstat();need(parent.st_uid==uid and stat.S_IMODE(parent.st_mode)==0o700,'private700 parent required')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==uid and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and 0<s.st_size<=maxbytes,'unsafe private600 file')
        raw=os.read(fd,maxbytes+1);after=os.fstat(fd);need(len(raw)==s.st_size and (s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns),'changing private file');return raw
    finally:os.close(fd)
def load(raw):
    def pairs(items):
        d={}
        for k,v in items:need(k not in d,'duplicate JSON key');d[k]=v
        return d
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
def timestamp(value):
    need(isinstance(value,str) and value.endswith('Z'),'UTC Z timestamp required')
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def check_go(raw,key,input_raw,now=None):
    now=time.time() if now is None else now;v=load(raw)
    need(set(v)=={'body','seal'} and isinstance(v['seal'],str) and re.fullmatch('[a-f0-9]{64}',v['seal']),'invalid HMAC envelope')
    b=v['body'];bodyraw=canonical(b).encode();need(hmac.compare_digest(v['seal'],hmac.new(key,bodyraw,hashlib.sha256).hexdigest()),'GO HMAC mismatch')
    need(len(key)==32,'protected32B root key required')
    need(set(b)=={'schema','status','approvedBy','authority','approvalId','issuedAt','notBefore','dispatchCutoff','expiresAt','inputSha256','invocations','cleanupReserveSeconds'},'unexpected GO fields')
    need(b['schema']=='h046-zero-generation-go-v1' and b['status']=='APPROVED' and b['approvedBy']=='root' and b['authority']=='H046','fresh root H046 GO required')
    need(re.fullmatch('[a-f0-9]{64}',b['approvalId']) is not None and b['inputSha256']==sha(input_raw),'GO input binding mismatch')
    issued,begin,cutoff,end=map(timestamp,[b['issuedAt'],b['notBefore'],b['dispatchCutoff'],b['expiresAt']])
    need(issued<=begin<=now<=cutoff<end and 0<end-issued<=600 and end<=timestamp('2026-10-02T16:59:03Z') and b['cleanupReserveSeconds']==130 and cutoff<=end-130,'finite GO expired/not current/reserve missing')
    need(type(b['cleanupReserveSeconds']) is int and isinstance(b['invocations'],dict) and all(type(v) is int for v in b['invocations'].values()),'literal integer bounds required')
    need(b['invocations']=={'nativeStart':1,'ownedShutdown':1,'initialize':1,'threadStart':1,'turnStart':0,'turnResume':0,'compact':0,'providerDispatch':0,'generation':0},'unsupported invocation bounds')
    return b

def protected_directory(path):
    p=Path(path);need(p.is_absolute() and p.resolve()==p,'directory alias')
    for parent in (p,*p.parents):
        s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022 and s.st_uid in (0,os.getuid()),'unsafe directory ancestry')
    s=p.lstat();need(s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'private700 directory required')
def source_graph(input):
    files=input['fileGraph'];need(isinstance(files,dict) and 8<=len(files)<=4096,'incomplete file graph')
    for name,digest in files.items():
        p=Path(name);need(p.is_absolute() and p.resolve()==p and re.fullmatch('[a-f0-9]{64}',digest),'invalid graph path/hash')
        s=p.lstat();need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and not s.st_mode&0o022 and s.st_uid in (0,os.getuid()),'unsafe graph file')
        for parent in p.parents:
            ps=parent.lstat();need(stat.S_ISDIR(ps.st_mode) and not ps.st_mode&0o022 and ps.st_uid in (0,os.getuid()),'unsafe graph ancestry')
        need(sha(p.read_bytes())==digest,'source/build/helper changed: '+name)
    need(sha(canonical(files).encode())==input['fileGraphSha256'],'graph join mismatch')
    required=[Path(__file__).resolve(),Path(input['helperDir'])/'carrier.mjs',Path(input['helperDir'])/'metadata.py',Path(input['node']),Path(input['python']),Path(input['unitFile']),Path(input['configPath'])]
    need(all(str(p) in files for p in required),'omitted executor/config/helper')
    need(input['configSha256']==files[input['configPath']],'config join mismatch')
    commit=Path(input['serverDir']).parent/'source-commit.txt';need(str(commit) in files and commit.read_text().strip()==input['appSourceCommit']=='1f3d4ec9efb3a704639c496b5507d6d203f107df','sealed app source mismatch')
    # Enumerate every statically imported JS edge of the exact carrier modules.
    reached=set()
    def walk(p):
        p=p.resolve();need(str(p) in files,'omitted imported module: '+str(p))
        if p in reached:return
        reached.add(p);raw=p.read_text()
        for rel in re.findall(r'(?:from\s*|import\s*\()[\"\x27](\.\.?/[^\"\x27]+\.js)[\"\x27]',raw):walk(p.parent/rel)
    for name in ('codex-launcher','codex-connection','codex-receipts','codex-ordinary-entry'):walk(Path(input['serverDir'])/'dist'/(name+'.js'))
    for name,digest in input['receiptSources'].items():need(files.get(str((Path(input['deploymentDir'])/name).resolve()))==digest,'receipt source join mismatch')
    return sorted(str(p) for p in reached)
def birth(pid):
    p=Path('/proc')/str(pid);fields=(p/'stat').read_text().rsplit(')',1)[1].split();status=(p/'status').read_text();cg=(p/'cgroup').read_text().strip()
    need(cg.startswith('0::/') and '\n' not in cg,'unexpected cgroup')
    return dict(pid=pid,ppid=int(fields[1]),pgid=int(fields[2]),startTicks=fields[19],uid=int(status.split('Uid:',1)[1].split()[0]),bootId=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cgroupPath=cg[3:])
def present(expected):
    try:actual=birth(expected['pid']);return all(actual[k]==expected[k] for k in ('pid','startTicks','uid','bootId'))
    except FileNotFoundError:return False

def write_once(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:os.write(fd,canonical(value).encode());os.fsync(fd)
    finally:os.close(fd)
def run_snapshot(input,input_path,outpath):
    command=[input['python'],str(Path(input['helperDir'])/'metadata.py'),'--input',str(input_path),'--output',str(outpath)]
    p=subprocess.run(command,env=safe_env(),capture_output=True,timeout=12)
    need(p.returncode==0,'fresh actual owner/preflight unavailable');return load(private(outpath,8*1024*1024))
def safe_env():return {k:os.environ[k] for k in ('HOME','USER','LOGNAME','XDG_RUNTIME_DIR') if k in os.environ}|{'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def scan_tree(process,observed):
    candidates={}
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal():continue
        try:candidates[int(p.name)]=birth(int(p.name))
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:continue  # unrelated inaccessible host processes are never acquired
    roots={process.pid}|{b['pid'] for b in observed.values() if present(b)};changed=True
    while changed:
        new={pid for pid,v in candidates.items() if v['ppid'] in roots};changed=not new<=roots;roots|=new
    for pid in roots:
        if pid in candidates:
            b=candidates[pid];observed[(pid,b['startTicks'])]=b
    return candidates

def signal_owned(observed,number):
    """Fresh same-birth group leader or exact recorded PID only; no bare retired PGID."""
    signaled=set()
    for expected in list(observed.values()):
        if not present(expected):continue
        actual=birth(expected['pid'])
        need(all(actual[k]==expected[k] for k in ('bootId','uid','pid','startTicks','pgid','cgroupPath')),'cleanup birth changed')
        if actual['pid']==actual['pgid']:
            try:os.killpg(actual['pgid'],number);signaled.add(actual['pgid'])
            except ProcessLookupError:pass
    for expected in list(observed.values()):
        if expected['pgid'] in signaled or not present(expected):continue
        actual=birth(expected['pid'])
        need(all(actual[k]==expected[k] for k in ('bootId','uid','pid','startTicks','pgid','cgroupPath')),'cleanup birth changed')
        try:os.kill(actual['pid'],number)
        except ProcessLookupError:pass

def closure_observation(observed,groups,scopes):
    live=[b for b in observed.values() if present(b)];group_live=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal():continue
        try:b=birth(int(p.name))
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:continue
        if b['pgid'] in groups:group_live.append(b)
    cgroups=[];directories=[]
    for path,identity in scopes.items():
        cp=Path('/sys/fs/cgroup')/path.lstrip('/')
        try:s=cp.stat()
        except FileNotFoundError:continue
        if {'dev':s.st_dev,'ino':s.st_ino}!=identity:continue
        directories.append(path)
        try:
            if any(p.read_text().strip() for p in cp.rglob('cgroup.procs')):cgroups.append(path)
        except FileNotFoundError:pass  # collected between observed inode and read; next full observation verifies absence
    return live,group_live,cgroups,directories

def preserve_channel(output):
    descriptor=output/'channel.json'
    if not descriptor.exists():return
    channel=Path(load(private(descriptor,65536))['directory'])
    need(str(channel).startswith('/run/user/'+str(os.getuid())+'/ai-harness-codex-receipts/run-'),'unowned channel path')
    protected_directory(channel)
    for original in channel.iterdir():
        if not re.fullmatch(r'[a-z-]+\.(json|ready)',original.name):continue
        target=output/('channel-'+original.name)
        if target.exists():continue
        s=original.lstat();need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and s.st_size<=65536,'unsafe original channel file')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:os.write(fd,original.read_bytes());os.fsync(fd)
        finally:os.close(fd)

def monitor(process,input,output,end):
    """Independent OS birth/group/cgroup observer and bounded failure cleanup."""
    observed={};groups=set();scopes={};stopped=False;fallback=False;failure=None
    # Record the direct parent's independently observed birth before any fallible scan.
    try:b=birth(process.pid);observed[(b['pid'],b['startTicks'])]=b
    except (FileNotFoundError,ProcessLookupError):pass
    try:
        while True:
            scan_tree(process,observed)
            for b in list(observed.values()):
                groups.add(b['pgid'])
                if '/ai-harness-codex-' in b['cgroupPath']:
                    cp=Path('/sys/fs/cgroup')/b['cgroupPath'].lstrip('/')
                    try:s=cp.stat();scopes[b['cgroupPath']]={'dev':s.st_dev,'ino':s.st_ino}
                    except FileNotFoundError:pass
            if process.poll() is not None:break
            if time.time()>=end-130 and not stopped:
                original=next((b for b in observed.values() if b['pid']==process.pid),None)
                need(original and present(original),'driver child changed before stop');process.send_signal(signal.SIGTERM);stopped=True
            if time.time()>=end-8:
                fallback=True;signal_owned(observed,signal.SIGKILL);break
            time.sleep(.05)
    except Exception as error:
        failure=type(error).__name__;fallback=True
    finally:
        if process.poll() is None:
            # A monitor error must close the exact owned carrier even when scanning failed.
            fallback=True
            direct=next((b for b in observed.values() if b['pid']==process.pid),None)
            if direct and present(direct):process.send_signal(signal.SIGTERM)
            # Preserve the existing launcher's 45s owned scope escalation within reserve.
            grace=min(end-8,time.time()+50)
            while time.time()<grace and process.poll() is None:
                try:scan_tree(process,observed)
                except Exception:pass
                time.sleep(.05)
            if process.poll() is None:
                signal_owned(observed,signal.SIGKILL)
                if direct and present(direct):process.kill()
        actual=process.wait(timeout=3)
    need(type(actual) is int,'missing actual parent wait')
    for b in observed.values():groups.add(b['pgid'])
    live=list(observed.values());group_live=[{'state':'NOT_OBSERVED'}];cgroups=list(scopes);directories=list(scopes)
    while time.time()<end-1:
        try:live,group_live,cgroups,directories=closure_observation(observed,groups,scopes)
        except Exception as error:failure=type(error).__name__;fallback=True;break
        if not live and not group_live and not cgroups and not directories:break
        # Abnormal carrier exit leaves no native PASS. Cleanup targets only acquired same births.
        if (actual!=0 or fallback) and live:
            fallback=True;signal_owned(observed,signal.SIGTERM)
            time.sleep(min(.1,max(0,end-time.time()-2)))
            signal_owned(observed,signal.SIGKILL)
        time.sleep(.05)
    closure={'schema':'h046-independent-parent-closure-v1','actualWaitExit':actual,'forcedStop':stopped,'fallbackCleanup':fallback,'monitorFailureClass':failure,'observedBirths':list(observed.values()),'observedGroups':sorted(groups),'observedNativeCgroups':scopes,'birthAbsence':not live,'groupAbsence':not group_live,'cgroupProcessAbsence':not cgroups,'cgroupDirectoryAbsence':not directories,'scopeAcquisitionObserved':bool(scopes),'remainingBirths':live,'remainingGroups':group_live,'remainingCgroups':cgroups,'remainingCgroupDirectories':directories}
    write_once(output/'parent-closure.json',closure)
    preserve_channel(output)
    return closure

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);ap.add_argument('--input',required=True);ap.add_argument('--root-key',required=True);ap.add_argument('--trusted-key-sha256',required=True);a=ap.parse_args()
    input_raw=private(a.input,2*1024*1024);input=load(input_raw);key=private(a.root_key,32);need(len(key)==32 and sha(key)==a.trusted_key_sha256,'independent existing root key anchor mismatch');go=check_go(private(a.go,2*1024*1024),key,input_raw)
    need(os.uname().sysname=='Linux' and os.getuid()>0,'rootless Linux only')
    need(len(input['receiptSources'])==8,'ordinary receipt profile only');need(ident(a.root_key)==input['rootKeyIdentity'] and a.root_key==input['rootKeyPath'],'protected root key inode changed')
    need(set(input['runtime'])=={'version','upstream','context','auto','output'} and input['runtime']=={'version':'0.158.0','upstream':'064c6b8c737f5b41d171fdda80bd9ef10ad06eb3','context':480000,'auto':400000,'output':65536},'runtime pins changed')
    need(input['nativeThreadId']=='UNALLOCATED' and type(input['workBudgetMs']) is int and 1<=input['workBudgetMs']<=45000,'fresh finite protocol only');need(input['gatewayTokenPath'] in {v['path'] for v in input['metadata']['protectedFiles']},'gateway credential inode omitted');need(a.root_key in {v['path'] for v in input['metadata']['protectedFiles']},'ordinary key inode omitted');need(input['rootKeyPath']==a.root_key,'ordinary key path mismatch')
    need(Path(input['helperDir']).resolve()==Path(__file__).parent.resolve(),'helper directory mismatch');need(input['unitFile']==input['metadata']['application']['unitFile'],'unit join mismatch');need(Path(input['cwd']).resolve()==Path(input['cwd']),'cwd alias')
    output=Path(input['output']);state=Path(input['stateDirectory']);protected_directory(output);protected_directory(state);need(not list(output.iterdir()),'output must be fresh empty700')
    for mount in [input['profileDir'],input['workspace']]:
        p=Path(mount);need(p.is_absolute() and p.resolve()==p,'native mount alias')
        for protected in [a.root_key,a.input,a.go,input['gatewayTokenPath'],str(output),str(state),input['helperDir'],input['serverDir'],input['deploymentDir']]:
            q=Path(protected);need(q!=p and p not in q.parents and q not in p.parents,'protected control/source path overlaps native mount')
    graph=source_graph(input);snapshot=run_snapshot(input,a.input,output/'driver-preflight.json');need(sha(canonical(snapshot).encode())==input['preflightSha256'],'stale owner/store/unit/credentials packet')
    need(time.time()<=timestamp(go['dispatchCutoff']),'GO expired before claim');write_once(state/('claim-'+go['approvalId']),{'approvalId':go['approvalId'],'inputSha256':sha(input_raw),'claimedAtNs':time.time_ns(),'status':'SPENT_BEFORE_START'})
    # A claim remains spent on every failure; no retries, no signing, no service action.
    argv=[input['node'],str(Path(input['helperDir'])/'carrier.mjs'),a.input,str(output)]
    need(argv==input['argv'] and sha(canonical(argv).encode())==input['argvSha256'],'startup argv mismatch')
    source_graph(input)
    outfd=os.open(output/'carrier.stdout.original',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);errfd=os.open(output/'carrier.stderr.original',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    process=None
    try:
        process=subprocess.Popen(argv,cwd=input['cwd'],env=safe_env(),stdout=outfd,stderr=errfd,start_new_session=True)
        closure=monitor(process,input,output,timestamp(go['expiresAt']))
    except Exception as error:
        # Direct child handle is owned even if the independent monitor itself fails.
        actual=None
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:actual=process.wait(timeout=max(1,min(125,timestamp(go['expiresAt'])-time.time()-3)))
                except subprocess.TimeoutExpired:process.kill();actual=process.wait(timeout=3)
            else:actual=process.wait(timeout=3)
        write_once(output/'parent-monitor-failure.json',{'schema':'h046-parent-monitor-failure-v1','errorClass':type(error).__name__,'actualWaitExit':actual,'nativeAcceptance':'FAIL','independentAbsence':'UNKNOWN'})
        try:preserve_channel(output)
        except Exception:pass
        raise
    finally:os.close(outfd);os.close(errfd)
    write_once(output/'driver-outcome-before-review.json',{'status':'REVIEW_PENDING' if closure['actualWaitExit']==0 else 'FAIL','actualWaitExit':closure['actualWaitExit'],'fallbackCleanup':closure['fallbackCleanup']})
    final_snapshot=run_snapshot(input,a.input,output/'driver-postflight.json');need(canonical(snapshot)==canonical(final_snapshot),'ordinary owner/gateway/retained originals changed');source_graph(input)
    result=load(private(output/'carrier-result.json',2*1024*1024))
    scope_terminal=load(private(output/'channel-scope-terminal.json',65536));need(type(scope_terminal.get('creatorExit')) is int and scope_terminal.get('creatorReaped') is True,'missing actual original scope wait/reap')
    need(closure['actualWaitExit']==0 and not closure['fallbackCleanup'] and not closure['monitorFailureClass'] and closure['birthAbsence'] and closure['groupAbsence'] and closure['cgroupProcessAbsence'] and closure['cgroupDirectoryAbsence'] and closure['scopeAcquisitionObserved'] and result['status']=='CARRIER_PROTOCOL_VALID','independent closure/native protocol failed')
    write_once(output/'driver-result.json',{'schema':'h046-zero-generation-driver-result-v1','status':'ACTUAL_NO_GENERATION_PROOF_ROOT_REVIEW_REQUIRED','inputSha256':sha(input_raw),'goSha256':sha(private(a.go,2*1024*1024)),'actualWaitExit':closure['actualWaitExit'],'sourceGraphSha256':input['fileGraphSha256'],'importedModules':graph,'ordinaryBaseline':'NOT_CREATED','rootReviewRequired':True})
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (Denied,FileExistsError,FileNotFoundError) as e:print('DENIED: '+str(e));raise SystemExit(64)
