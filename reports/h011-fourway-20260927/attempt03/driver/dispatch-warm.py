from pathlib import Path
import json,base64,subprocess,hashlib
root=Path('reports/h010-flash64k-20260927/driver')
common=(root/'vm-common.py').read_text();body=(root/'qualify-body.py').read_text()
body=body.replace('datetime.datetime(2026,9,27,0,58','datetime.datetime(2026,9,27,1,43').replace("PREFIX = 'H010-FLASH64K'","PREFIX = 'H011-WARM03'").replace('remaining() > 1500','remaining() > 240').replace("'hardstop_utc':'2026-09-27T00:58:00Z'","'hardstop_utc':'2026-09-27T01:43:00Z'")
a=body.index("        for mode,target,seed,output,cap in [");b=body.index('            MODE=mode;',a)
body=body[:a]+"        for mode,target,seed,output,cap in [('warm8192',8192,'H011-fan03-warm-varied-20260927',128,180)]:\n"+body[b:]
body=body.replace('remaining() > (600 if target==65536 else 300)','remaining() > 200')
expected=json.loads(Path('../evidence/FINAL-IDENTITY.json').read_text())['source_matches']
full=common+'\nFIXTURE_SOURCE='+repr((root/'fixture_native.py').read_text())+'\nEXPECTED_IDENTITIES='+repr(expected)+'\n'+body
compile(full,'warm02','exec');Path('../tools/warm03-job.py').write_text(full)
remote=common+'\nRAW='+repr(base64.b64encode(full.encode()).decode())+r'''
import base64
path='/data/logs/flash-h008-20260926/H011-WARM03-job.py'
with transaction() as (_,g):
 s.root_payload_guard();write_new(path,base64.b64decode(RAW),g)
 receipt={'utc':now(),'status':'OWNED_BEFORE_DISPATCH','unit':'h011-warm03','source_sha256':hashlib.sha256(base64.b64decode(RAW)).hexdigest(),'input':8192,'max_output':128,'request_cap_s':180,'retry':False}
 status('/data/logs/flash-h008-20260926/H011-WARM03-OWNER.json',receipt,g)
 subprocess.run(['systemd-run','--unit=h011-warm03','--property=Type=exec','--property=RuntimeMaxSec=300','--property=TimeoutStopSec=20','--property=Restart=no','--property=StandardOutput=null','--property=StandardError=null','--property=UMask=0077','/usr/bin/python3','-I','-B',path],check=True,capture_output=True)
 receipt['status']='DISPATCHED';receipt['dispatch_utc']=now();status('/data/logs/flash-h008-20260926/H011-WARM03-OWNER.json',receipt,g);s.root_payload_guard()
print(json.dumps(receipt))
'''
r=subprocess.run(['ssh','-T','ai-vm','sudo -n python3 -I -B -'],input=remote.encode(),capture_output=True,timeout=60);assert r.returncode==0,r.stderr.decode()[-1500:]
Path('../evidence/WARM03-OWNER.json').write_bytes(r.stdout);print(r.stdout.decode())
