#!/usr/bin/env python3
"""Guarded exact GO staging only; no inference, source overwrite, or replay."""
import base64,datetime,hashlib,json,pathlib,subprocess
T=pathlib.Path(__file__).resolve().parents[4];S=T/'repo/scripts/h016/affinity02'

def main():
 go=json.loads((T/'ROOT-AFFINITY02-GO.json').read_text())
 assert go['authorized'] is True and datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'].replace('Z','+00:00'))
 files={n:base64.b64encode((S/n).read_bytes()).decode() for n in go['source_sha256']}
 assert {n:hashlib.sha256(base64.b64decode(b)).hexdigest() for n,b in files.items()}==go['source_sha256']
 code='''import base64,datetime,hashlib,json,os,pathlib,sys
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from verify_retained import dependency
h=dependency();files=PAYLOAD_FILES;go=PAYLOAD_GO
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'].replace('Z','+00:00'))
names=['affinity02','r10-spread02','r11-local02']
for n in names:
 for root in ['/data/build','/data/logs']:
  assert not pathlib.Path(root,'H016-20260927','worker1-'+n).exists(),'namespace_exists_no_overwrite'
expected={'numactl':'f3944bcd7848d64424f8daf27f350b03d7f3281b2fb9be5eaaba0ddd0e72efb8','libnuma.so.1.0.0':'02d7582c5d391e460e56aa67a414360e3183b968206645b9123f9dc7bff5d009','HARNESS-QUIET-01.json':'2858831152358589f305a70aab6f1bcb39a6206ccd522889188dfc0bc2112200'}
with h.transaction() as g:
 h.s.root_payload_guard()
 retained={}
 with h.AnchoredRoot('/data/build/H016-20260927/worker1-r8',g) as a:
  for n,d in expected.items():
   with a.open(n) as f:
    chunks=[]
    while True:
     raw=f.read(65536)
     if not raw:break
     chunks.append(raw)
   raw=b''.join(chunks);assert hashlib.sha256(raw).hexdigest()==d;retained[n]=raw
 for namespace in names:
  for root in ['/data/build','/data/logs']:
   with h.AnchoredRoot(root,g) as a:a.mkdir('H016-20260927/worker1-'+namespace)
  b='/data/build/H016-20260927/worker1-'+namespace
  subset={n.split('/')[-1]:base64.b64decode(v) for n,v in files.items() if (n.startswith(namespace+'/') if namespace!='affinity02' else '/' not in n)}
  if namespace!='affinity02':subset.update(retained)
  with h.AnchoredRoot(b,g) as a:
   for n,raw in subset.items():
    with a.open(n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o700 if n=='numactl' else 0o600) as f:f.write(raw)
   a.atomic_json('SOURCE-SHA256.json',go['source_sha256'] if namespace=='affinity02' else {n:hashlib.sha256(v).hexdigest() for n,v in subset.items()})
   a.atomic_json('ROOT-AFFINITY02-GO.json',go)
 h.s.root_payload_guard()
print(json.dumps({'status':'EXACT_AFFINITY_PAIR_STAGED_NO_DISPATCH','utc':h.now(),'source_sha256':go['source_sha256']}))
'''.replace('PAYLOAD_FILES',repr(files)).replace('PAYLOAD_GO',repr(go))
 compile(code,'remote-stage','exec')
 r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=50)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')
 for name,value in [('stdout',r.stdout),('stderr',r.stderr)]:(T/'private/affinity02'/('STAGE-'+stamp+'.'+name)).write_text(value)
 assert r.returncode==0, 'stage_failure_inspect_no_replay: '+r.stderr[-1000:]
 out=json.loads(r.stdout);(T/'AFFINITY02-STAGED.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
if __name__=='__main__':main()
