#!/usr/bin/env python3
"""Stage exact root-authorized R9 sources and reuse three retained dependencies."""
import base64,datetime,hashlib,json,pathlib,subprocess
T=pathlib.Path(__file__).resolve().parents[4];R=T/'repo';S=R/'scripts/h016/r9'
go=json.loads((T/'ROOT-R9-GO.json').read_text())
assert go['authorized'] is True
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'])
from importlib.machinery import SourceFileLoader
# Names are fixed in the reviewed owner, independently of the GO contents.
import sys
sys.path.insert(0,str(S))
from candidate_owner import SOURCE_NAMES, FIXTURE_SHA
files={n:base64.b64encode((S/n).read_bytes()).decode() for n in SOURCE_NAMES}
winner_raw=(T/'ROOT-WINNER.json').read_bytes()
assert go['winner_sha256']==hashlib.sha256(winner_raw).hexdigest()
winner=json.loads(winner_raw)
assert winner['authorized'] is True and winner['threads'] in (16,64) and winner['context']==1000000
fixture=(T.parent/'H016-BACKEND-02-20260927/private/mimo-production-fixture-65536.json').read_bytes()
assert hashlib.sha256(fixture).hexdigest()==go['fixture_sha256']==FIXTURE_SHA
assert {n:hashlib.sha256(base64.b64decode(b)).hexdigest() for n,b in files.items()}==go['source_sha256']
files['mimo-production-fixture-65536.json']=base64.b64encode(fixture).decode()
files['ROOT-WINNER.json']=base64.b64encode(winner_raw).decode()
code='''import base64,datetime,hashlib,json,os,pathlib,sys
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from candidate_owner import dependency
h=dependency();files=PAYLOAD_FILES;go=PAYLOAD_AUTHORITY
assert go['authorized'] is True
assert hashlib.sha256(base64.b64decode(files['ROOT-WINNER.json'])).hexdigest()==go['winner_sha256']
assert hashlib.sha256(base64.b64decode(files['mimo-production-fixture-65536.json'])).hexdigest()==go['fixture_sha256']
assert set(files)==set(go['source_sha256'])|{'ROOT-WINNER.json','mimo-production-fixture-65536.json'}
for n,d in go['source_sha256'].items():assert hashlib.sha256(base64.b64decode(files[n])).hexdigest()==d
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'])
B='/data/build/H016-20260927/worker1-r9';L='/data/logs/H016-20260927/worker1-r9'
for destination in [B,L]:
 if pathlib.Path(destination).exists():assert not list(pathlib.Path(destination).iterdir()),'r9_namespace_nonempty_inspect_no_overwrite'
old='/data/build/H016-20260927/worker1-r8'
expected={'numactl':'f3944bcd7848d64424f8daf27f350b03d7f3281b2fb9be5eaaba0ddd0e72efb8','libnuma.so.1.0.0':'02d7582c5d391e460e56aa67a414360e3183b968206645b9123f9dc7bff5d009','HARNESS-QUIET-01.json':'2858831152358589f305a70aab6f1bcb39a6206ccd522889188dfc0bc2112200'}
with h.transaction() as g:
 h.s.root_payload_guard()
 with h.AnchoredRoot('/data/build',g) as a:a.mkdir('H016-20260927/worker1-r9')
 with h.AnchoredRoot('/data/logs',g) as a:a.mkdir('H016-20260927/worker1-r9')
 with h.AnchoredRoot(old,g) as a:
  for n,digest in expected.items():
   with a.open(n) as f:
    parts=[]
    while True:
     part=f.read(65536)
     if not part:break
     parts.append(part)
    raw=b''.join(parts)
   assert hashlib.sha256(raw).hexdigest()==digest
   files[n]=base64.b64encode(raw).decode()
 hashes={}
 with h.AnchoredRoot(B,g) as a:
  for n,b in files.items():
   raw=base64.b64decode(b);hashes[n]=hashlib.sha256(raw).hexdigest()
   with a.open(n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o700 if n=='numactl' else 0o600) as f:f.write(raw)
  a.atomic_json('SOURCE-SHA256.json',hashes)
  a.atomic_json('ROOT-R9-GO.json',go)
 h.s.root_payload_guard()
print(json.dumps({'status':'EXACT_R9_STAGED_NO_DISPATCH','utc':h.now(),'base':B,'log':L,'source_hashes':hashes}))
'''.replace('PAYLOAD_FILES',repr(files)).replace('PAYLOAD_AUTHORITY',repr(go))
r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=40)
(T/('private/finalprep11/R9-STAGING-'+datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')+'.stderr')).write_text(r.stderr)
if r.returncode:raise RuntimeError('staging failed '+r.stderr[-1000:])
out=json.loads(r.stdout);(T/'R9-STAGED.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
