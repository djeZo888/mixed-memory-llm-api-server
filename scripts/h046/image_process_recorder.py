"""H046 finite process recorder; source-only successor of bounded_wrapper.py.

The gated child has an observed birth before dispatch. Only the original direct
child's vanished observation may be resolved by its actual wait/reap. Its durable
terminal receipt precedes fresh independent all-UID birth/group absence checks.
A successful later command never repairs an earlier failed receipt. Detached
native/systemd/Podman resources still require independent owned cleanup.
"""
import os,signal,time,select,json,pathlib,datetime,hashlib,socket,subprocess,uuid,math
P=pathlib.Path
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def identity(pid):
    p=P('/proc')/str(pid);a=(p/'stat').read_text().rsplit(')',1)[1].split();cg=(p/'cgroup').read_text().strip();uid=[x.split()[1:] for x in (p/'status').read_text().splitlines() if x.startswith('Uid:')]
    boot=P('/proc/sys/kernel/random/boot_id').read_text().strip();b=(p/'stat').read_text().rsplit(')',1)[1].split()
    if a[19]!=b[19] or uid!=[[str(os.getuid())]*4] or not cg.startswith('0::/') or '\n' in cg:raise ValueError('process identity race')
    return {'pid':pid,'ppid':int(a[1]),'startTicks':a[19],'bootId':boot,'uid':os.getuid(),'pgid':int(a[2]),'sid':int(a[3]),'cgroupPath':cg[3:]}
def put(path,raw,check=lambda:None):
    check();fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        v=memoryview(raw)
        while v:
            check();n=os.write(fd,v);check()
            if n<=0:raise OSError("short exclusive receipt write")
            v=v[n:]
        check();os.fsync(fd);check()
    finally:os.close(fd)

import sys, stat
GATE_SHA = '9c3d787d4480f671f504ca39504c44c7f3e76e9f70d117f3aadc5fcb79880dd3'
def birth_key(v):return (v['pid'],v['startTicks'],v['bootId'])
class ProcessSamplingError(ValueError):
    """An ambiguous inventory never proves absence or authorizes a signal."""

class DirectChildReaped(Exception):
    """Actual direct wait resolved a vanished observation; absence is not claimed.

    The caller must persist its actual terminal before a new independent scan.
    No other birth, UID, boot, executable change or stale relation is excused.
    """
    def __init__(self, observation):
        super().__init__('original direct child actually reaped after observation')
        self.observation = observation


def current_boot():return P('/proc/sys/kernel/random/boot_id').read_text().strip()

def _stat(pid):
    raw=(P('/proc')/str(pid)/'stat').read_text()
    fields=raw.rsplit(')',1)[1].split()
    if int(raw.split(' ',1)[0])!=pid or len(fields)<20:raise ProcessSamplingError('invalid stat observation')
    return {'pid':pid,'ppid':int(fields[1]),'pgid':int(fields[2]),'sid':int(fields[3]),'startTicks':fields[19]},fields[0]

class Inventory(list):
    """Observed all-UID rows plus unresolved basic observations, never absences."""
    def __init__(self,rows=(),ambiguities=()):
        super().__init__(rows);self.ambiguities=list(ambiguities)

class BirthRegistry(dict):
    """Per-invocation current strict births and immutable relationship history."""
    def __init__(self):
        super().__init__();self.basicHistory={};self.relatedHistory={};self.ambiguities=[]

def _same_birth(a,b):
    return a['pid']==b['pid'] and a['startTicks']==b['startTicks']

def _observations(v):return v.get('basicObservations',[v])

def basic_identity(pid,boot=None):
    # Every UID participates. PPID/PGID/SID may legitimately change between
    # reads; retain both relationships, bound to the same current kernel birth.
    supplied=boot is not None;boot=current_boot() if boot is None else boot
    a,_=_stat(pid)
    try:b,_=_stat(pid)
    except (OSError,ValueError) as e:
        error=ProcessSamplingError('incomplete basic observation');error.observations=[{**a,'bootId':boot}]
        error.vanished=isinstance(e,(FileNotFoundError,ProcessLookupError));raise error from e
    if not _same_birth(a,b) or (not supplied and current_boot()!=boot):
        error=ProcessSamplingError('basic birth race');error.observations=[{**a,'bootId':boot},{**b,'bootId':boot}];error.vanished=False;raise error
    v={**b,'bootId':boot}
    if a!=b:v['basicObservations']=[{**a,'bootId':boot},{**b,'bootId':boot}]
    return v

def process_identity(pid):
    p=P('/proc')/str(pid);boot=current_boot();a,state=_stat(pid)
    status=(p/'status').read_text()
    uids=[x.split()[1:] for x in status.splitlines() if x.startswith('Uid:')]
    cg=(p/'cgroup').read_text().strip()
    if len(uids)!=1 or len(uids[0])!=4 or len(set(uids[0]))!=1 or not cg.startswith('0::/') or '\n' in cg:raise ProcessSamplingError('strict four-UID/cgroup refusal')
    executable=None
    if state!='Z':
        try:
            path=os.readlink(p/'exe');s=(p/'exe').stat()
            executable={'path':path,'device':s.st_dev,'inode':s.st_ino}
        except FileNotFoundError as e:
            ended,ended_state=_stat(pid)
            if not _same_birth(ended,a):
                raise ProcessSamplingError('executable disappearance birth changed') from e
            if ended_state!='Z':raise
    again=[x.split()[1:] for x in (p/'status').read_text().splitlines() if x.startswith('Uid:')]
    b,last_state=_stat(pid)
    if not _same_birth(a,b) or uids!=again or (p/'cgroup').read_text().strip()!=cg or current_boot()!=boot:raise ProcessSamplingError('strict identity race')
    if executable is not None:
        try:
            s=(p/'exe').stat()
            if os.readlink(p/'exe')!=executable['path'] or (s.st_dev,s.st_ino)!=(executable['device'],executable['inode']):raise ProcessSamplingError('executable identity race')
        except FileNotFoundError as e:
            ended,ended_state=_stat(pid)
            if not _same_birth(ended,b):
                raise ProcessSamplingError('executable disappearance birth changed') from e
            if ended_state!='Z':raise
            executable=None
            if [x.split()[1:] for x in (p/'status').read_text().splitlines() if x.startswith('Uid:')]!=uids or (p/'cgroup').read_text().strip()!=cg or current_boot()!=boot:raise ProcessSamplingError('zombie owner race')
    elif last_state!='Z':raise ProcessSamplingError('zombie identity race')
    v={**b,'bootId':boot,'uid':int(uids[0][0]),'uidTuple':[int(x) for x in uids[0]],'cgroupPath':cg[3:],'executable':executable}
    if a!=b:v['basicObservations']=[{**a,'bootId':boot},{**b,'bootId':boot}]
    return v

def snapshot(owner, allowed):
    rows=Inventory();boot=current_boot()
    if boot!=owner['bootId']:raise ProcessSamplingError('current boot changed')
    pids=sorted((int(p.name) for p in P('/proc').iterdir() if p.name.isdigit()),reverse=True)
    if len(pids)>20000:raise ProcessSamplingError('finite process inventory')
    for pid in pids:
        try:v=basic_identity(pid,boot)
        except (OSError,ValueError) as e:
            # Do not invent a basic row or kernel absence. Capture resolves only
            # ordinary ENOENT against the retained ownership/relation registry.
            rows.ambiguities.append({'pid':pid,'observations':getattr(e,'observations',[]),'vanished':getattr(e,'vanished',isinstance(e,(FileNotFoundError,ProcessLookupError))),'error':type(e).__name__,'message':str(e)})
            continue
        if v['bootId']!=boot:raise ProcessSamplingError('inventory boot race')
        rows.append(v)
    if current_boot()!=boot:raise ProcessSamplingError('inventory boot changed')
    return rows

def _related_set(rows,owner,known,historical=False):
    history=[v for values in getattr(known,'relatedHistory',{}).values() for v in values]
    anchors=list(known.values())+history if historical else [v for row in rows for v in _observations(row) if birth_key(v) in known]
    owned={v['pid'] for v in anchors}
    sessions={v['sid'] for v in anchors};groups={(v['pgid'],v['sid']) for v in anchors}
    selected=set()
    while True:
        more={v['pid'] for row in rows for v in _observations(row) if birth_key(v) in known or v['ppid'] in owned or ((v['sid'] in sessions or (v['pgid'],v['sid']) in groups) and int(v['startTicks'])>=int(owner['startTicks']))}
        if more<=selected:break
        selected|=more;owned|=more
        for row in rows:
            if row['pid'] in selected:
                for v in _observations(row):sessions.add(v['sid']);groups.add((v['pgid'],v['sid']))
    return selected

def _validated_related(row,owner,known,allowed):
    try:v=process_identity(row['pid'])
    except (OSError,ValueError) as e:
        error = ProcessSamplingError('related birth unreadable/unstable')
        error.related_pid = row['pid']
        error.direct_exit_candidate = isinstance(e, (FileNotFoundError, ProcessLookupError))
        error.observations = _observations(row)
        raise error from e
    # Relationship transitions do not change ownership. Exact current birth,
    # four UIDs, cgroup and stable executable still validate before any signal.
    if birth_key(v)!=birth_key(row):raise ProcessSamplingError('related birth changed after basic sample')
    if v['uid'] not in allowed or v['bootId']!=owner['bootId']:raise ProcessSamplingError('unapproved related UID/boot')
    original=known.get(birth_key(v))
    if original and (v['cgroupPath']!=original['cgroupPath'] or v['uid']!=original['uid']):raise ProcessSamplingError('recorded UID/cgroup changed')
    return v

def _direct_vanished_observation(ambiguity, owner):
    return (ambiguity['pid'] == owner['pid'] and ambiguity.get('vanished') is True
            and all(birth_key(v) == birth_key(owner)
                    for v in ambiguity.get('observations', [])))

def capture(owner, known, allowed, reap_direct=None):
    rows=snapshot(owner,allowed);by_pid={v['pid']:v for v in rows}
    # Historical basic rows supplement an incomplete *current* observation for
    # relationship detection only, never as live rows or absence proof.
    history=getattr(known,'basicHistory',{})
    ambiguous=getattr(rows,'ambiguities',[])
    candidates=list(rows)
    for a in ambiguous:
        candidates.extend(a['observations']);candidates.extend(history.get(a['pid'],[]))
    for original in known.values():
        replacement=by_pid.get(original['pid'])
        if replacement and birth_key(replacement)!=birth_key(original):
            if isinstance(known,BirthRegistry):known.ambiguities.append({'pid':original['pid'],'observations':[replacement],'error':'RECORDED_PID_REUSED'})
            raise ProcessSamplingError('recorded PID reused')
    selected=_related_set(candidates,owner,known)
    possible=_related_set(candidates,owner,known,historical=True)
    stale=possible-selected
    if stale:
        if isinstance(known,BirthRegistry):known.ambiguities.extend({'pid':pid,'error':'STALE_RECORDED_GROUP_SESSION_RELATION'} for pid in stale)
        raise ProcessSamplingError('stale recorded group/session/parent ambiguity')
    relevant=[]
    for a in ambiguous:
        if a['pid'] in selected or any(v['pid']==a['pid'] for v in known.values()) or (not a['vanished'] and len(a['observations'])<2):
            relevant.append(a)
    direct_pending = None
    if relevant:
        # These observations are *not* absence. A genuinely owned direct child
        # cannot be PID-reused while unreaped; only an actual wait may resolve
        # its disappearing /proc row. The terminal must precede any new scan.
        if (reap_direct is not None
                and all(_direct_vanished_observation(a, owner) for a in relevant)):
            direct_pending = {'phase': 'basic', 'observations': relevant}
        else:
            if isinstance(known,BirthRegistry):known.ambiguities.extend(relevant)
            raise ProcessSamplingError('ambiguous owned/possibly related basic PID '+','.join(str(a['pid']) for a in relevant))
    pending={};relations={}
    for row in rows:
        if row['pid'] in selected:
            try:checked=_validated_related(row,owner,known,allowed)
            except (OSError,ValueError) as e:
                if (row['pid'] == owner['pid']
                        and birth_key(row) == birth_key(owner)
                        and getattr(e, 'direct_exit_candidate', False)
                        and reap_direct is not None):
                    direct_pending = {'phase': 'strict', 'pid': row['pid'],
                                      'observations': _observations(row),
                                      'error': type(e.__cause__).__name__}
                    continue
                if isinstance(known,BirthRegistry):
                    for possible_row in rows:
                        if possible_row['pid'] in selected:known.relatedHistory.setdefault(birth_key(possible_row),[]).extend(_observations(possible_row))
                    known.ambiguities.append({'pid':row['pid'],'observations':_observations(row),'error':'RELATED_STRICT_REFUSAL'})
                    known.relatedHistory.setdefault(birth_key(row),[]).extend(_observations(row))
                raise
            k=birth_key(checked)
            pending[k]=checked;relations[k]=_observations(row)+_observations(checked)
    # Validate all related siblings before resolving even the direct-child race.
    # No partial approved set may hide an unapproved related sibling.
    known.update(pending)
    if isinstance(known,BirthRegistry):
        for k,values in relations.items():
            dest=known.relatedHistory.setdefault(k,[])
            for v in values:
                r={x:v[x] for x in ['pid','ppid','pgid','sid','startTicks','bootId']}
                if r not in dest:dest.append(r)
        for row in rows:
            dest=known.basicHistory.setdefault(row['pid'],[])
            for v in _observations(row):
                r={x:v[x] for x in ['pid','ppid','pgid','sid','startTicks','bootId']}
                if r not in dest:dest.append(r)
        if sum(map(len,known.basicHistory.values()))>20000:raise ProcessSamplingError('finite basic history')
    if direct_pending is not None:
        if reap_direct() is True:
            raise DirectChildReaped(direct_pending)
        if isinstance(known, BirthRegistry):
            known.ambiguities.append({'pid': owner['pid'],
                                     'error': 'DIRECT_OBSERVATION_NOT_REAPED',
                                     'observations': direct_pending['observations']})
        raise ProcessSamplingError('direct observation unresolved by actual wait')
    return rows

def _signal_identity(v,current,allowed):
    if birth_key(current)!=birth_key(v) or current['bootId']!=current_boot():raise ValueError('reused/changed recorded birth refusal')
    if current['uid'] not in allowed or current['uid']!=v['uid'] or current['uidTuple']!=[current['uid']]*4 or current['cgroupPath']!=v['cgroupPath']:raise ValueError('recorded owner changed refusal')
    if current['executable'] is not None and current['executable']!=v.get('executable'):raise ValueError('recorded executable changed refusal')

def send_birth(v,sig,allowed):
    if v['uid'] not in allowed:raise ValueError('exact owned UID')
    try:
        before=process_identity(v['pid']);_signal_identity(v,before,allowed)
        if before['executable'] is None:return False # zombie waits; no invented absence
        fd=os.pidfd_open(v['pid'],0)
        try:
            after=process_identity(v['pid']);_signal_identity(v,after,allowed)
            if after['executable'] is None:return False
            signal.pidfd_send_signal(fd,sig,None,0)
        finally:os.close(fd)
        return True
    except (ProcessLookupError,FileNotFoundError):return False
def settle_births(owner,known,allowed,events):
    # Direct wait is handled separately and unconditionally by the caller.
    faults=[]
    def fault(e,where):
        v={'settlementFailure':type(e).__name__,'phase':where,'message':str(e)}
        faults.append(v);events.append(v)
    def sample():
        try:return capture(owner,known,allowed)
        except BaseException as e:fault(e,'capture');return None
    for sig,grace in [(signal.SIGTERM,.5),(signal.SIGKILL,1)]:
        sample()
        for v in list(known.values()):
            if v['pid']==owner['pid']:continue
            try:
                if send_birth(v,sig,allowed):events.append({'identity':v,'signal':int(sig)})
            except BaseException as e:fault(e,'recorded_signal')
        end=time.monotonic()+grace
        while time.monotonic()<end:
            for v in list(known.values()):
                if v['pid']==owner['pid']:continue
                # Reap only a recorded birth adopted by this finite subreaper.
                try:
                    current=process_identity(v['pid'])
                    if birth_key(current)!=birth_key(v):raise ValueError('reused adopted birth refusal')
                    if current['uid'] not in allowed or current['uid']!=v['uid'] or current['cgroupPath']!=v['cgroupPath'] or current['bootId']!=owner['bootId']:raise ValueError('adopted recorded owner refusal')
                    if current['ppid']==os.getpid():
                        got,status=os.waitpid(v['pid'],os.WNOHANG)
                        if got:events.append({'adoptedRecordedIdentity':v,'actualWaitExitCode':os.waitstatus_to_exitcode(status)})
                except (FileNotFoundError,ProcessLookupError,ChildProcessError):pass
                except BaseException as e:fault(e,'recorded_adoption_wait')
            rows=sample()
            if rows is not None and not any(birth_key(v) in known and v['pid']!=owner['pid'] for v in rows):break
            time.sleep(.01)
    rows=sample()
    history=[v for values in getattr(known,'relatedHistory',{}).values() for v in values]
    recorded_groups={(v['pgid'],v['sid']) for v in list(known.values())+history}
    recorded_sessions={v['sid'] for v in list(known.values())+history}
    remaining=[v for v in rows if birth_key(v) in known or (v['pgid'],v['sid']) in recorded_groups or v['sid'] in recorded_sessions] if rows is not None else 'UNKNOWN'
    return {'knownIdentities':list(known.values()),'remainingKnownBirthsOrGroups':remaining,'settlementFailures':faults,'relatedHistory':list(getattr(known,'relatedHistory',{}).values()),'basicAmbiguities':getattr(known,'ambiguities',[]),'independentBirthGroupAbsence':'UNKNOWN' if faults or rows is None or getattr(known,'ambiguities',[]) else not remaining}
def persist_terminal(path,terminal,writer):
    raw=json.dumps(terminal,indent=2).encode()+b'\n'
    try:writer(path,raw);return None
    except BaseException as e:
        terminal['terminalWriteFailure']=type(e).__name__;raw=json.dumps(terminal,indent=2).encode()+b'\n'
        try:put(str(path)+'.fallback',raw)
        except BaseException:
            try:sys.stderr.write(json.dumps({'originalActualChildTerminal':terminal})+'\n');sys.stderr.flush()
            except BaseException:pass
        return type(e).__name__
def verify_gate(gate,allowed):
    p=P(gate);s=p.lstat()
    if p.resolve()!=p or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid not in allowed or s.st_mode&0o022:raise ValueError('protected gate source')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd);raw=os.read(fd,65537);after=os.fstat(fd)
        ident=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
        if ident(s)!=ident(before) or ident(before)!=ident(after) or ident(after)!=ident(p.lstat()) or len(raw)!=s.st_size or hashlib.sha256(raw).hexdigest()!=GATE_SHA:raise ValueError('exact gate byte pin')
    finally:os.close(fd)

def actual_child_wait(child, receipts, timeout=None):
    """Wait only the original direct child and retain its actual kernel status.

    Popen.wait/poll treats ECHILD as success with a synthesized zero on some
    Python versions. An external reaper or SIGCHLD policy is real ambiguity.
    Reusing our own already recorded status is allowed, synthesizing one is not.
    """
    if child.returncode is not None:
        if (type(child.returncode) is int and receipts
                and receipts[-1]['pid'] == child.pid
                and receipts[-1]['actualExitCode'] == child.returncode):
            return child.returncode
        raise ProcessSamplingError('cached child returncode has no actual wait receipt')
    end = None if timeout is None else time.monotonic() + timeout
    while True:
        try:
            got, status = os.waitpid(child.pid, 0 if timeout is None else os.WNOHANG)
        except InterruptedError:
            continue
        if got:
            if got != child.pid or not (os.WIFEXITED(status) or os.WIFSIGNALED(status)):
                raise ProcessSamplingError('actual direct wait PID/status mismatch')
            result = os.waitstatus_to_exitcode(status)
            child.returncode = result
            receipts.append({'method': 'os.waitpid', 'pid': got,
                             'actualWaitStatus': status, 'actualExitCode': result,
                             'observedUtc': utc()})
            return result
        if end is None:
            raise ProcessSamplingError('blocking direct wait returned no child')
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(child.args, timeout)
        time.sleep(min(.002, remaining))

def run_gated(argv,cwd,env,out,err,launch,terminal_path,seconds,deadline,claim=lambda _:None,writer=put,identity_reader=process_identity,allowed=None,monitor=None,on_dispatch_cutoff=None,dispatch_reserve=0,gate=None,python=None,python_sha=None):
    allowed={os.geteuid()} if allowed is None else set(allowed)
    if not allowed or any(type(uid)is not int or uid<0 for uid in allowed):raise ValueError('explicit approved gate owners')
    if type(seconds) not in [int,float] or not math.isfinite(seconds) or seconds<=0:raise ValueError('numeric finite command timeout')
    deadline.check(dispatch_reserve+3);gate=P(gate or P(__file__).with_name('image_command_gate.py'));verify_gate(gate,allowed)
    python=python or sys.executable
    if python_sha is not None and hashlib.sha256(P(python).read_bytes()).hexdigest()!=python_sha:raise ValueError('exact interpreter byte pin')
    c=None;owner=None;known=BirthRegistry();rc=None;failure=None;released=False;events=[];absence={'independentBirthGroupAbsence':'UNKNOWN'};gr=gw=direct_fd=None
    direct_waits=[]
    start=utc();mono=time.monotonic();previous={n:signal.getsignal(n) for n in [signal.SIGTERM,signal.SIGINT,signal.SIGALRM]};libc=None;subreaper=None
    def stop(n,_):raise InterruptedError('finite owned command interrupted')
    for n in previous:signal.signal(n,stop)
    def remember(e,where):
        nonlocal failure
        detail={'class':type(e).__name__,'phase':where,'message':str(e),'cause':str(e.__cause__) if e.__cause__ else None}
        if failure is None:failure=detail
        else:events.append({'cleanupFailure':type(e).__name__,**detail})
    def wait_direct(timeout=None):
        nonlocal rc
        rc = actual_child_wait(c, direct_waits, timeout=timeout)
        return rc
    def reap_direct_race():
        try:
            wait_direct(timeout=.05)
            return True
        except subprocess.TimeoutExpired:
            return False
    def signal_direct(sig):
        if direct_fd is None:
            raise ProcessSamplingError('no pidfd for original direct child')
        # An unexpected external reaper cannot turn a stale numeric PID into
        # authority to signal a replacement process.
        signal.pidfd_send_signal(direct_fd, sig, None, 0)
    try:
        if sys.platform=='linux':
            import ctypes
            libc=ctypes.CDLL(None,use_errno=True);v=ctypes.c_int()
            if libc.prctl(37,ctypes.byref(v),0,0,0)!=0:raise OSError(ctypes.get_errno(),'get finite subreaper')
            subreaper=v.value
            if libc.prctl(36,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),'set finite subreaper')
        with P(out).open('xb') as so,P(err).open('xb') as se:
            gr,gw=os.pipe()
            c=subprocess.Popen([python,'-I','-S','-B',str(gate),str(gr),*argv],cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True,pass_fds=(gr,))
            direct_fd=os.pidfd_open(c.pid,0)
            os.close(gr);gr=None
            owner=identity_reader(c.pid)
            if owner['pid']!=c.pid or owner.get('ppid')!=os.getpid() or owner['pgid']!=c.pid or owner['sid']!=c.pid or owner['uid'] not in allowed:raise ValueError('actual gate owner identity')
            strict=process_identity(c.pid)
            if any(strict[k]!=owner[k] for k in ['pid','ppid','pgid','sid','startTicks','bootId','uid','cgroupPath']) or strict['bootId']!=current_boot():raise ValueError('strict prerelease gate owner join')
            known[birth_key(owner)]=owner
            # Exclusive fsynced original receipt and claim BOTH precede release.
            writer(launch,json.dumps({'argv':argv,'gateArgv':c.args,'cwd':cwd,'startUtc':start,'owner':owner,'timeoutSeconds':seconds,'gateReleased':False},indent=2).encode()+b'\n')
            claim(owner);deadline.check(dispatch_reserve+2)
            os.write(gw,b'G');released=True;os.close(gw);gw=None
            cutoff=time.monotonic()+min(seconds,max(.001,deadline.remaining()-dispatch_reserve-2))
            while True:
                try:
                    capture(owner,known,allowed,reap_direct=reap_direct_race)
                except DirectChildReaped as reaped:
                    events.append({'directExitObservationResolvedByActualWait': reaped.observation,
                                   'independentAbsenceStillRequired': True})
                    break
                if monitor:monitor()
                try:rc=wait_direct(timeout=min(.02,max(.001,cutoff-time.monotonic())));break
                except subprocess.TimeoutExpired:
                    if time.monotonic()>=cutoff:
                        if on_dispatch_cutoff:
                            on_dispatch_cutoff();cutoff=time.monotonic()+max(.001,deadline.remaining()-30);on_dispatch_cutoff=None
                            remember(TimeoutError('dispatch cutoff'),'dispatch_cutoff');continue
                        raise
    except BaseException as e:remember(e,'execution')
    finally:
        for n in previous:signal.signal(n,signal.SIG_IGN)
        try:
            for fd in [gr,gw]:
                if fd is not None:
                    try:os.close(fd)
                    except BaseException as e:remember(e,'gate_close')
            if c is not None:
                try:
                    try:
                        if owner is not None and c.returncode is None:
                            try:capture(owner,known,allowed,reap_direct=reap_direct_race)
                            except DirectChildReaped as reaped:
                                events.append({'directExitObservationResolvedByActualWait': reaped.observation, 'independentAbsenceStillRequired': True})
                        if c.returncode is None:
                            # Direct unreaped child cannot be a recycled PID.
                            signal_direct(signal.SIGTERM)
                            try:wait_direct(timeout=.5)
                            except subprocess.TimeoutExpired:
                                signal_direct(signal.SIGKILL);wait_direct(timeout=.5)
                    except BaseException as e:remember(e,'finite_wait')
                finally:
                    # Neither first/second timeout nor signal/identity faults skip this.
                    try:
                        if c.returncode is None:signal_direct(signal.SIGKILL)
                    except BaseException as e:remember(e,'final_kill')
                    finally:
                        while True:
                            try:rc=wait_direct();break
                            except InterruptedError:continue
                            except BaseException as e:
                                remember(e,'direct_wait')
                                # ECHILD is incomplete proof, never a fabricated zero.
                                rc=None
                                break
        finally:
            terminal={'argv':argv,'cwd':cwd,'startUtc':start,'endUtc':utc(),'actualExitCode':rc,'reaped':c is not None and type(rc) is int and bool(direct_waits),'directWait':c is not None and type(rc) is int and bool(direct_waits),'directWaitEvidence':direct_waits,'owner':owner,'pid':c.pid if c else None,'pgid':owner['pgid'] if owner else None,'birthSampling':'OBSERVED' if owner else 'UNKNOWN','timeoutSeconds':seconds,'gateReleased':released,'failure':failure,'elapsedMonotonicSeconds':time.monotonic()-mono}
            # Durable actual terminal precedes even descendant readback/settlement.
            wf=persist_terminal(terminal_path,terminal,writer)
            if wf:remember(OSError(wf),'terminal_write')
            try:
                if owner is not None:absence=settle_births(owner,known,allowed,events)
                if absence.get('independentBirthGroupAbsence') is not True:remember(RuntimeError('unproved birth/group absence'),'independent_absence')
            except BaseException as e:remember(e,'descendant_settlement')
            finally:
                try:
                    if libc is not None and subreaper is not None and libc.prctl(36,subreaper,0,0,0)!=0:remember(OSError('restore finite subreaper'),'subreaper_restore')
                except BaseException as e:remember(e,'subreaper_restore')
                closure={'actualExitCode':rc,'directReaped':terminal['reaped'],'failure':failure,'signals':events,'knownIdentities':list(known.values()),**absence}
                cf=persist_terminal(str(terminal_path)+'.closure',closure,writer)
                if cf:remember(OSError(cf),'closure_write')
                if direct_fd is not None:
                    try:os.close(direct_fd)
                    except BaseException as e:remember(e,'direct_pidfd_close')
                for n,h in previous.items():signal.signal(n,h)
    return {**terminal,'failure':failure,'closure':closure}
def supervise(argv,cwd,env,evidence,deadline,claim,dispatch_reserve=120,monitor=None,identity_reader=identity,on_dispatch_cutoff=None):
    d=P(evidence)
    return run_gated(argv,cwd,env,d/'child.stdout.private',d/'child.stderr.private',d/'child-launch.json',d/'actual-child-terminal.json',max(.001,deadline.remaining()-dispatch_reserve-2),deadline,claim=claim,identity_reader=identity_reader,dispatch_reserve=dispatch_reserve,monitor=monitor,on_dispatch_cutoff=on_dispatch_cutoff)
def bounded_command(argv,cwd,env,evidence,seconds,deadline,identity_reader=identity):
    if not 0<seconds<=5:raise ValueError('fixed short helper timeout')
    d=P(evidence)/('helper-'+uuid.uuid4().hex);d.mkdir(mode=0o700)
    t=run_gated(argv,cwd,env,d/'stdout',d/'stderr',d/'launch.json',d/'actual-terminal.json',seconds,deadline,identity_reader=identity_reader)
    raw={}
    for n in ['stdout','stderr']:
        q=d/n
        if q.stat().st_size>1048576:raise ValueError('helper original output bound')
        raw[n]=q.read_bytes()
    put(d/'original-hashes.json',json.dumps({k:{'path':str(d/k),'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in raw.items()},indent=2).encode()+b'\n')
    return {**raw,'actualExitCode':t['actualExitCode'],'failure':t['failure'],'processClosure':'REAPED' if t['reaped'] else 'UNKNOWN','evidenceDirectory':str(d),'terminal':t}
