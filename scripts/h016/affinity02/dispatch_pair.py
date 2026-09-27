#!/usr/bin/env python3
"""Consume exact root GO once; all inference clients belong to Linux systemd."""
import datetime,hashlib,json,pathlib,subprocess
T=pathlib.Path(__file__).resolve().parents[4];S=T/'repo/scripts/h016/affinity02'

def main():
 go=json.loads((T/'ROOT-AFFINITY02-GO.json').read_text())
 assert go['authorized'] is True and datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'].replace('Z','+00:00'))
 for n,d in go['source_sha256'].items():assert hashlib.sha256((S/n).read_bytes()).hexdigest()==d
 intent=T/'AFFINITY02-DISPATCH-INTENT.json'
 with intent.open('x') as f:json.dump({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'ONE_DISPATCH_INTENT','root_go':go},f,indent=2)
 code="""import json,sys,pathlib
sys.path.insert(0,'/data/build/H016-20260927/worker1-affinity02')
from authority import validate
actual,plan=validate()
assert actual==PAYLOAD_GO,'remote_go_differs'
from launch_pair import main
main(run=True)
""".replace('PAYLOAD_GO',repr(go))
 r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=30)
 for n,v in [('stdout',r.stdout),('stderr',r.stderr)]:(T/'private/affinity02'/('DISPATCH.'+n)).write_text(v)
 assert r.returncode==0,'dispatch uncertain: inspect actual owner; never replay: '+r.stderr[-1000:]
 out=json.loads(r.stdout);(T/'AFFINITY02-DISPATCH.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
if __name__=='__main__':main()
