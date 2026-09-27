#!/usr/bin/env python3
"""Independent-systemd-owned H016 supervisor. Never replay or clear quarantine."""
import argparse, datetime, json, os, pathlib, signal, subprocess, sys, time
ENTRY_MONO = time.monotonic()
ENTRY_WALL = time.time()
P = pathlib.Path(__file__).resolve().parent
RUN = pathlib.Path('/home/user/ai-harness-build/H016-FINAL-ACTIVATION-PREP-20260927/live-acceptance-01')
SETTLE = datetime.datetime(2026, 9, 27, 17, 44, 30, tzinfo=datetime.timezone.utc).timestamp()
SUPERVISOR_SECONDS, WORK_SECONDS, CLEANUP_SECONDS = 1380, 1200, 180
MIN_WORK_SECONDS = 720  # root-selected attempt budget, never predicted PASS
ADMIT = SETTLE - CLEANUP_SECONDS - MIN_WORK_SECONDS  # theoretical inference bound only
HARD_SETTLE = SETTLE + 30

def remaining(entry_wall, entry_mono, now_wall, now_mono):
    return max(0, min(SUPERVISOR_SECONDS - (now_mono-entry_mono), SETTLE-now_wall))

def work_budget(entry_wall, entry_mono, now_wall, now_mono):
    budget = max(0, min(WORK_SECONDS, remaining(entry_wall,entry_mono,now_wall,now_mono)-CLEANUP_SECONDS))
    if budget < MIN_WORK_SECONDS:
        raise ValueError('insufficient full-acceptance startup budget; inference refused')
    return budget

class Cancelled(Exception):
    pass

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate',required=True);parser.add_argument('--gate-sha256',required=True)
    parser.add_argument('--activation-manifest',required=True);parser.add_argument('--receipt',required=True)
    args=parser.parse_args()
    assert sys.platform=='linux' and os.getuid()==1000
    assert os.environ.get('INVOCATION_ID'), 'independent Linux systemd owner required'
    os.umask(0o077)
    receipt=pathlib.Path(args.receipt);assert receipt.is_absolute() and not receipt.exists()
    assert receipt.parent.resolve()==P and not RUN.exists()
    now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
    left=lambda:remaining(ENTRY_WALL,ENTRY_MONO,time.time(),time.monotonic())
    state={'startedUtc':datetime.datetime.fromtimestamp(ENTRY_WALL,datetime.timezone.utc).isoformat(),
           'supervisorPid':os.getpid(),'invocationId':os.environ['INVOCATION_ID'],
           'wallBudgetSeconds':SUPERVISOR_SECONDS,
           'absoluteSettlementUtc':'2026-09-27T17:45:00Z','status':'PREFLIGHT',
           'nativeSettlement':'NOT_PROVEN','replayAllowed':False}
    def save():
        temp=receipt.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(receipt)
    def cancel(signum,frame):
        state['signal']=signum
        raise Cancelled()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,cancel)
    child=None
    env={'HOME':'/home/user','PATH':'/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin','XDG_RUNTIME_DIR':'/run/user/1000','LANG':'C.UTF-8','INVOCATION_ID':os.environ['INVOCATION_ID']}
    common=['--gate',args.gate,'--gate-sha256',args.gate_sha256,'--activation-manifest',args.activation_manifest]
    node='/home/user/.local/opt/ai-harness/node-v24.21.0/bin/node'
    def pod(*a):
        seconds=min(25,left())
        if seconds<=0:raise TimeoutError('settlement deadline')
        return subprocess.check_output(['/usr/bin/podman','--remote=false',*a],env=env,text=True,timeout=seconds).strip()
    def owned():
        found=[]
        for cid in filter(None,pod('ps','--all','--quiet','--no-trunc').splitlines()):
            mounts=json.loads(pod('inspect','--format','{{json .Mounts}}',cid))
            profiles=[m['Source'] for m in mounts if m.get('Source','').startswith(str(RUN/'data/profiles')+'/')]
            workspaces=[m['Source'] for m in mounts if m.get('Source','').startswith(str(RUN/'data/workspaces')+'/')]
            if profiles and workspaces:found.append({'id':cid,'profile':profiles,'workspace':workspaces})
        return found
    try:
        save()
        work_budget(ENTRY_WALL,ENTRY_MONO,time.time(),time.monotonic())
        with open(P/'preflight.log','x') as log:
            child=subprocess.Popen([node,str(P/'preflight-cli.mjs'),*common],env=env,stdout=log,stderr=log,start_new_session=True)
            state['preflightPid']=child.pid;save()
            code=child.wait(timeout=min(120,left()-CLEANUP_SECONDS))
        child=None
        if code:
            state.update(status='PREFLIGHT_REFUSED',exitCode=code)
            return 1
        work=work_budget(ENTRY_WALL,ENTRY_MONO,time.time(),time.monotonic())
        assert work>0,'no remaining work budget'
        deadline_ms=int((time.time()+work)*1000)
        command=[node,str(P/'live.mjs'),*common,'--work-deadline-ms',str(deadline_ms)]
        state.update(workBudgetSeconds=work,workDeadlineMs=deadline_ms,command=command)
        with open(P/'live-process.log','x') as log:
            child=subprocess.Popen(command,cwd=P,env=env,stdout=log,stderr=log,start_new_session=True)
            state.update(childPid=child.pid,status='RUNNING');save()
            state['exitCode']=child.wait(timeout=min(work+90,left()-60))
        child=None
        result=RUN/'RESULT.json'
        terminal=json.loads(result.read_text()) if result.exists() else {}
        if state['exitCode']==0 and terminal.get('status')=='COMPLETED_PENDING_ROOT_REVIEW':
            state.update(status='COMPLETED_REVIEW_REQUIRED',nativeSettlement='CLIENT_TERMINAL_REVIEW_REQUIRED')
        else:state['status']='SETTLEMENT_UNKNOWN'
    except ValueError as e:
        state.update(status='LATE_ENTRY_REFUSED',reason=str(e))
    except BaseException as e:
        state.update(status='SETTLEMENT_UNKNOWN',errorType=type(e).__name__)
    finally:
        # Cancellation is evidence of uncertainty, not proof the native request stopped.
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,signal.SIG_IGN)
        save()
        try:
            if child and child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=min(20,max(0,left())))
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=min(5,max(0,left())))
            if RUN.exists():
                found=owned();state['ownedContainersAfter']=found
                if found:
                    state['status']='SETTLEMENT_UNKNOWN';save()
                    for item in found:
                        assert item in owned(),'exact owner changed'
                        pod('stop','--time','10',item['id'])
                    state['ownedContainersAfterEmergencyStop']=owned()
        except Exception as e:
            # Includes late entry: no host contact is needed when RUN does not exist.
            state.update(status='SETTLEMENT_UNKNOWN',cleanupErrorType=type(e).__name__)
        state['endedUtc']=now();state['elapsedSeconds']=time.monotonic()-ENTRY_MONO;save()
    return 0 if state['status']=='COMPLETED_REVIEW_REQUIRED' else 1

if __name__=='__main__':sys.exit(main())
