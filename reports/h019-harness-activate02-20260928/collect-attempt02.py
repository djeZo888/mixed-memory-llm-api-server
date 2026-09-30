"""Read-only compact collection of the distinct independent attempt; never dispatch."""
import datetime, hashlib, json, pathlib, subprocess

p=pathlib.Path('/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928')
d=p/'driver-attempt02'; run=p/'live-acceptance-01'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def unit(n):
    return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','--user','show',n,'-p','ActiveState','-p','SubState','-p','MainPID','-p','InvocationID','-p','ExecMainStartTimestamp','-p','ExecMainStatus'],text=True).splitlines())
supervisor=json.loads((d/'supervisor-result.json').read_text())
r={'status':'INDEPENDENT_ATTEMPT02_STARTUP_OBSERVED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'attempt':2,'unit':unit('h019-prep01-app-acceptance-02.service'),'hardstop':unit('h019-prep01-app-hardstop-02.timer'),
   'supervisor':supervisor,'evidencePaths':{n:str(f) for n,f in {'dispatchIntent':d/'dispatch-intent.json','supervisor':d/'supervisor-result.json','preflight':d/'preflight.log','hardstop':d/'hardstop-readback.txt','liveLog':d/'live-process.log','owner':run/'OWNER.json','events':run/'events.jsonl','result':run/'RESULT.json','childToolProof':run/'child-tool-proof.json','nativeIds':run/'code-native-ids.json'}.items()},
   'replayAllowed':False,'appAcceptance':'NOT_YET_PROVEN'}
events=[]
if (run/'events.jsonl').exists():
    for line in (run/'events.jsonl').read_text().splitlines():
        try:e=json.loads(line)
        except json.JSONDecodeError:continue
        if e.get('event') in ['run','payload-captured','pre-count','native-session','owned-container','frontier-state','payload-binding','qwen-usage','failed','container-settlement','deadline-stop']:
            events.append({k:e[k] for k in ['at','event','phase','sessionId','runId','requestId','route','mode','seq','state','id','promptTokens','reservedOutput','code','present'] if k in e})
r['observedEvents']=events
r['preflightPassed']='H016_PREFLIGHT_PASS' in (d/'preflight.log').read_text() if (d/'preflight.log').exists() else False
r['realParentRequestObserved']=any(e.get('mode')=='qwen' and e.get('event')=='payload-captured' for e in events)
r['realFrontierActiveObserved']=any(e.get('event')=='frontier-state' and e.get('state')=='active' for e in events)
r['firstParentRequestUtc']=next((e['at'] for e in events if e.get('mode')=='qwen' and e.get('event')=='payload-captured'),None)
r['firstFrontierActiveUtc']=next((e['at'] for e in events if e.get('event')=='frontier-state' and e.get('state')=='active'),None)
r['currentPhase']=events[-1] if events else 'preflight'
r['sha256']={n:sha(f) for n,f in [('dispatchIntent',d/'dispatch-intent.json'),('gate',p/'private/ROOT-LIVE-GATE-02.json'),('activation',p/'private/ACTIVATION-MANIFEST.json'),('preflight',d/'preflight.log'),('supervisorSnapshot',d/'supervisor-result.json')] if f.exists()}
if (run/'RESULT.json').exists():
    r['terminalResult']=json.loads((run/'RESULT.json').read_text())
    r['terminalRawSha256']={n:sha(run/n) for n in ['RESULT.json','child-tool-proof.json','code-native-ids.json','events.jsonl'] if (run/n).exists()}
if (run/'OWNER.json').exists():r['owner']=json.loads((run/'OWNER.json').read_text())
print(json.dumps(r,indent=2))
