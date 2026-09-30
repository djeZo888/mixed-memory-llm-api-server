#!/usr/bin/env python3
"""Guarded exact GO staging only; no inference, source overwrite, or replay."""
import base64,datetime,hashlib,json,pathlib,subprocess
T=pathlib.Path(__file__).resolve().parents[4];S=T/'repo/scripts/h016/affinity14'

def main():
 go=json.loads((T/'ROOT-AFFINITY14-GO.json').read_text())
 assert go['authorized'] is True and datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'].replace('Z','+00:00'))
 files={n:base64.b64encode((S/n).read_bytes()).decode() for n in go['source_sha256']}
 assert {n:hashlib.sha256(base64.b64decode(b)).hexdigest() for n,b in files.items()}==go['source_sha256']
 code='''import base64,datetime,hashlib,json,os,pathlib,sys
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from verify_retained import dependency
h=dependency();files=PAYLOAD_FILES;go=PAYLOAD_GO
assert go.get('authorized') is True and go.get('profiles')==['r12-spread4','r13-spread2'],'root_scope'
assert go['expires_utc']=='2026-09-27T17:35:00Z','fixed_go_expiry'
for n,raw in files.items():
 parts=pathlib.Path(n).parts
 assert not pathlib.Path(n).is_absolute() and '..' not in parts
 assert len(parts)==1 or (len(parts)==2 and parts[0] in go['profiles'])
 assert hashlib.sha256(base64.b64decode(raw)).hexdigest()==go['source_sha256'][n]
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'].replace('Z','+00:00'))
names=['affinity14','r12-spread4','r13-spread2']
for n in names:
 unit='h016-affinity14-20260927.service' if n=='affinity14' else 'h016-mimo-profile-20260927-'+n+'.service'
 import subprocess
 assert subprocess.check_output(['systemctl','show',unit,'-p','LoadState','--value'],text=True).strip()=='not-found','unit_exists_inspect_no_replay'
 if n!='affinity14':
  assert not subprocess.check_output(['docker','ps','-aq','--filter','name=^/llm-h016-mimo-pro-'+n+'$'],text=True).strip(),'candidate_exists_no_replay'
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
  subset={n.split('/')[-1]:base64.b64decode(v) for n,v in files.items() if (n.startswith(namespace+'/') if namespace!='affinity14' else '/' not in n)}
  if namespace!='affinity14':subset.update(retained)
  with h.AnchoredRoot(b,g) as a:
   for n,raw in subset.items():
    with a.open(n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o700 if n=='numactl' else 0o600) as f:f.write(raw)
   a.atomic_json('SOURCE-SHA256.json',go['source_sha256'] if namespace=='affinity14' else {n:hashlib.sha256(v).hexdigest() for n,v in subset.items()})
   a.atomic_json('ROOT-AFFINITY14-GO.json',go)
 h.s.root_payload_guard()
print(json.dumps({'status':'EXACT_AFFINITY_PAIR_STAGED_NO_DISPATCH','utc':h.now(),'source_sha256':go['source_sha256']}))
'''.replace('PAYLOAD_FILES',repr(files)).replace('PAYLOAD_GO',repr(go))
 compile(code,'remote-stage','exec')
 r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=50)
 (T/'private/affinity14').mkdir(parents=True,exist_ok=True)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')
 for name,value in [('stdout',r.stdout),('stderr',r.stderr)]:(T/'private/affinity14'/('STAGE-'+stamp+'.'+name)).write_text(value)
 assert r.returncode==0, 'stage_failure_inspect_no_replay: '+r.stderr[-1000:]
 out=json.loads(r.stdout);(T/'AFFINITY14-STAGED.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
if __name__=='__main__':main()
