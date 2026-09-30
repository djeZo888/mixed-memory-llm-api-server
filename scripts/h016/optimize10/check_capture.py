#!/usr/bin/env python3
"""One short read of durable Linux capture progress; no request or waiting."""
import argparse,base64,hashlib,json,pathlib,subprocess
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--collect',action='store_true');args=ap.parse_args()
T=pathlib.Path(__file__).resolve().parents[4]
code='''import sys,json,subprocess,hashlib,base64
sys.path.insert(0,'/data/build/H016-20260927/worker1-r7')
from candidate_owner import dependency
h=dependency();out={}
with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot('/data/logs/H016-20260927/worker1-optimize10',g) as a:
 if a.stat('PROGRESS.jsonl',missing_ok=True):
  with a.open('PROGRESS.jsonl') as f:raw=f.read(100000)
  out['events']=[json.loads(x) for x in raw.splitlines() if x]
 if COLLECT and a.stat('HOST-UMC512-REPLACEMENT.json',missing_ok=True):
  with a.open('HOST-UMC512-REPLACEMENT.json') as f:
   pieces=[]
   while True:
    piece=f.read(65536)
    if not piece:break
    pieces.append(piece)
   raw=b''.join(pieces)
  out['receipt']={'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}
out['unit']=subprocess.check_output(['systemctl','show','h016-host-umc512-replacement-20260927-r10.service','-p','MainPID,ControlPID,InvocationID,ExecMainStartTimestamp,ActiveState,SubState,Result,ExecMainStatus'],text=True)
print(json.dumps(out))
'''.replace('COLLECT',repr(args.collect))
r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=15)
if r.returncode:raise RuntimeError('short_receiver_failed: '+r.stderr[-500:])
out=json.loads(r.stdout);events=out.get('events',[])
if events:
 p=T/'UMC512-PROGRESS.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(events[-1],indent=2)+'\n');tmp.replace(p)
 for e in events:
  if e['event']=='FIRST_OUTPUT':
   p=T/'UMC512-FIRST_OUTPUT.json'
   if not p.exists():
    p.write_text(json.dumps(e,indent=2)+'\n')
    with (T/'ROOT-NOTICE.md').open('a') as f:f.write('\n## FIRST_OUTPUT\n'+json.dumps(e,indent=2)+'\n')
 if 'receipt' in out:
  raw=base64.b64decode(out['receipt']['base64']);assert hashlib.sha256(raw).hexdigest()==out['receipt']['sha256']
  (T/'private/optimize10/HOST-UMC512-REPLACEMENT.json').write_bytes(raw)
  out['receipt']={'sha256':out['receipt']['sha256'],'saved':True}
(T/'private/optimize10/CAPTURE-CHECK.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'latest_event':events[-1] if events else None,'unit':out['unit'],'receipt':out.get('receipt')}))
