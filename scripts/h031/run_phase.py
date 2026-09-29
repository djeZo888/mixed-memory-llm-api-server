#!/usr/bin/env python3
"""Local W1 bounded SSH wrapper; captures all remote output privately."""
import datetime,hashlib,json,os,shlex,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];out=root.parent/'output'
phase=sys.argv[1]
if phase=='stage':
    import base64
    inp=root.parent/'input';w2=inp/'W2-SOURCE01';w1=inp/'W1-IMAGELOCK01'
    mapping={
      '/data/services/image21-runtime-20260923/config.json':'private/image-config.json',
      '/data/services/image21-runtime-20260923/source/service.py':'reviewed-source/service.py',
      '/data/services/mimo-h016-20260927/manifest.json':'private/successor-manifest.json',
      '/data/services/mimo-h016-20260927/source/owner.py':'reviewed-source/owner.py',
      '/usr/local/lib/llm-server/node-api/scripts/control/node.py':'reviewed-source/node.py',
      '/usr/local/lib/llm-server/node-api/scripts/control/node_collectors.py':'reviewed-source/node_collectors.py'}
    paths={'proposal.json':w1/'COMBINED-ACTIVATION-PROPOSAL.json','activate.py':root/'scripts/h031/activate.py','reviewed-source/service.py':root/'scripts/image_runtime/service.py','private/image-config.json':w1/'image-config.proposed.private.json','private/successor-manifest.json':w2/'private/successor-manifest.json','source-successor-delta.json':w2/'source-successor-delta.json','initial-private.json':out/'01-current.private.json',**{'reviewed-source/'+n:w2/'reviewed-source'/n for n in ('owner.py','node.py','node_collectors.py')}}
    raw={n:p.read_bytes() for n,p in paths.items()};raw['mapping.json']=json.dumps(mapping).encode()
    p=json.loads(raw['proposal.json'])
    for dest,row in p['leaves'].items():assert hashlib.sha256(raw[mapping[dest]]).hexdigest()==row['new']
    data=json.dumps({n:base64.b64encode(v).decode() for n,v in raw.items()}).encode()
    cmd=['sudo','-n','/usr/bin/python3','-I','-B','-c',raw['activate.py'].decode(),'stage']
else:
    data=None;cmd=['sudo','-n','/usr/bin/python3','-I','-B','/data/build/h031-activate01-20260929/activate.py',phase]
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
r=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=5','ai-vm',shlex.join(cmd)],input=data,capture_output=True,timeout=180)
for suffix,raw in [('stdout',r.stdout),('stderr',r.stderr)]:
    p=out/(phase+'.'+suffix);p.write_bytes(raw);os.chmod(p,0o600)
print(json.dumps({'phase':phase,'startedUtc':start,'finishedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exitCode':r.returncode,'stdoutBytes':len(r.stdout),'stderrBytes':len(r.stderr)}))
if r.returncode==0:
    v=json.loads(r.stdout);print(json.dumps(v,indent=2) if phase not in ('reconcile',) else json.dumps({k:v.get(k) for k in ('status','utc','transition','selection','consumed_name','archive_name')}))
else:
    print(r.stderr.decode()[-3000:]);print(r.stdout.decode()[-2000:])
sys.exit(r.returncode)
