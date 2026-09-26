#!/usr/bin/env python3
"""Bounded foreground supervisor; only task-owned launcher/container settlement.
No unit/tag/release/registry mutation. No inference without live.mjs gate.
"""
import argparse, datetime, json, os, pathlib, signal, subprocess, sys, time
P=pathlib.Path(__file__).resolve().parent
RUN=pathlib.Path('/home/user/ai-harness-build/H009-FRONTIER-20260926/live-acceptance-01')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gate',required=True);parser.add_argument('--gate-sha256',required=True)
parser.add_argument('--activation-manifest',required=True)
parser.add_argument('--receipt',required=True)
args=parser.parse_args()
assert sys.platform=='linux' and os.getuid()==1000
os.umask(0o077)
receipt=pathlib.Path(args.receipt);assert receipt.is_absolute() and not receipt.exists()
assert receipt.parent.resolve()==P and not RUN.exists()
# Full metadata, artifacts and host state preflight BEFORE job reservation/Popen.
preflight_env={'HOME':'/home/user','PATH':'/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin','XDG_RUNTIME_DIR':'/run/user/1000','LANG':'C.UTF-8'}
subprocess.run(['/home/user/.local/opt/ai-harness/node-v24.21.0/bin/node',str(P/'preflight-cli.mjs'),'--gate',args.gate,'--gate-sha256',args.gate_sha256,'--activation-manifest',args.activation_manifest],env=preflight_env,check=True,timeout=120)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
gate_expiry=datetime.datetime.fromisoformat(json.loads(pathlib.Path(args.gate).read_text())['expiresUtc'].replace('Z','+00:00')).timestamp()
wall_budget=min(1200,int(gate_expiry-time.time()))
assert wall_budget>60, 'insufficient root-authorized remaining window'
state={'startedUtc':now(),'supervisorPid':os.getpid(),'wallBudgetSeconds':wall_budget,'absoluteRootDeadlineUtc':datetime.datetime.fromtimestamp(gate_expiry,datetime.timezone.utc).isoformat(),'status':'STARTING','command':['/home/user/.local/opt/ai-harness/node-v24.21.0/bin/node',str(P/'live.mjs'),'--gate',args.gate,'--gate-sha256',args.gate_sha256,'--activation-manifest',args.activation_manifest]}
def save():
    temp=receipt.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(receipt)
save()
def owned():
    env={'HOME':'/home/user','PATH':'/usr/bin:/bin','XDG_RUNTIME_DIR':'/run/user/1000'}
    def pod(*a):return subprocess.check_output(['/usr/bin/podman','--remote=false',*a],env=env,text=True,timeout=25).strip()
    found=[]
    for cid in filter(None,pod('ps','--all','--quiet','--no-trunc').splitlines()):
        mounts=json.loads(pod('inspect','--format','{{json .Mounts}}',cid))
        profiles=[m['Source'] for m in mounts if m.get('Source','').startswith(str(RUN/'data/profiles')+'/')]
        workspaces=[m['Source'] for m in mounts if m.get('Source','').startswith(str(RUN/'data/workspaces')+'/')]
        if profiles and workspaces:found.append({'id':cid,'profile':profiles,'workspace':workspaces})
    return found,pod
child=None
try:
    # Sanitized environment: no credential value, key path, proxies or SSH agent.
    env={'HOME':'/home/user','PATH':'/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin','XDG_RUNTIME_DIR':'/run/user/1000','LANG':'C.UTF-8'}
    with open(P/'live-process.log','x') as log:
        child=subprocess.Popen(state['command'],cwd=P,env=env,stdout=log,stderr=log,start_new_session=True)
        state.update(childPid=child.pid,status='RUNNING',deadlineUtc=datetime.datetime.fromtimestamp(time.time()+wall_budget,datetime.timezone.utc).isoformat());save()
        try:state['exitCode']=child.wait(timeout=wall_budget-60)
        except subprocess.TimeoutExpired:
            state['status']='DEADLINE';save();os.killpg(child.pid,signal.SIGTERM)
            try:state['exitCode']=child.wait(timeout=20)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);state['exitCode']=child.wait(timeout=5)
    if state['status']=='RUNNING':state['status']='COMPLETED_REVIEW_REQUIRED' if state['exitCode']==0 else 'FAILED'
except BaseException as e:
    state['status']='SUPERVISOR_FAILED';state['errorType']=type(e).__name__
    if child and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=15)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
finally:
    try:
        remaining,pod=owned();state['ownedContainersAfter']=remaining
        # Emergency exact-owner teardown only; never clear durable quarantine.
        if remaining:
            state['status']='SETTLEMENT_UNKNOWN';save()
            for item in remaining:
                fresh,_=owned();assert item in fresh
                pod('stop','--time','10',item['id'])
            state['ownedContainersAfterEmergencyStop']=owned()[0]
    except Exception:state['status']='SETTLEMENT_UNKNOWN'
    state['endedUtc']=now();save()
sys.exit(0 if state['status']=='COMPLETED_REVIEW_REQUIRED' else 1)
