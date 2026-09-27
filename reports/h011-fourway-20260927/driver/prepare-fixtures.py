from pathlib import Path
import subprocess,json,hashlib
source=Path('reports/h011-fourway-20260927/driver/fixture_native.py').read_text()
common=Path('../tools/vm-common.py').read_text()
script=common+'\nSOURCE='+repr(source)+r'''
import http.client
key=P('/data/services/secrets/llm-api-key').read_text().strip()
names={'flash':('llm-frontier-flash',30010),'qwen0':('llmctl-qwen38-27b-q0-480000-yarn4-bf16kv',30002),'qwen1':('llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv',30004)}
s.root_payload_guard()
all_fixtures={}
with MountedStorageGuard(s) as guard:
 guard.check_path('/data/models-large/glm-5.3-flash-eb9eb208')
 for lane,(name,port) in names.items():
  proc=subprocess.run(['docker','exec','-i',name,'python3','-I','-B','-',lane],input=SOURCE,capture_output=True,text=True,timeout=240)
  assert proc.returncode==0,(lane,proc.returncode,proc.stdout[-1000:],proc.stderr[-1000:])
  built=json.loads(proc.stdout)
  for f in built:
   c=http.client.HTTPConnection('127.0.0.1',port,timeout=30)
   c.request('POST','/v1/tokenize',json.dumps(f['payload']),{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   response=c.getresponse();out=json.loads(response.read(16*1024*1024));c.close()
   assert response.status==200,(lane,response.status,out)
   assert out['count']==f['rendered_tokens'],(lane,out['count'],f['rendered_tokens'])
   if 'tokens' in out:
    assert hashlib.sha256(json.dumps(out['tokens'],separators=(',',':')).encode()).hexdigest()==f['rendered_token_ids_sha256'],'native_token_ids_mismatch'
    out={k:v for k,v in out.items() if k!='tokens'}
   f['native_count']=out
  all_fixtures[lane]=built
 s.root_payload_guard()
print(json.dumps(all_fixtures))
'''
Path('../tools/fixtures-remote.py').write_text(script)
r=subprocess.run(['ssh','-o','ConnectTimeout=5','-T','ai-vm','sudo -n python3 -I -B -'],input=script.encode(),capture_output=True,timeout=720)
Path('../evidence/FIXTURES02.stderr').write_bytes(r.stderr)
assert r.returncode==0,r.stderr.decode()[-1800:]
Path('../evidence/FIXTURES02.json').write_bytes(r.stdout)
x=json.loads(r.stdout);print({lane:[{'tokens':f['rendered_tokens'],'sha256':f['payload_sha256']} for f in rows] for lane,rows in x.items()})
