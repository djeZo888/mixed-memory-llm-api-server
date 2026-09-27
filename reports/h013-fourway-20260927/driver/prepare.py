#!/usr/bin/env python3
"""Read-only H013 identity/collector preflight. Never dispatches inference.
Run from the isolated repository. A missing image owner stays BLOCKED.
"""
from pathlib import Path
import argparse, subprocess, json, hashlib, ast
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2];TASK=REPO.parent
BASE=REPO/'reports/h011-fourway-20260927/attempt03/EXECUTION-IDENTITY.json'
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
 old=json.loads(BASE.read_text());expected=dict(old['source_matches'])
 production='/data/services/flash-h008-20260926/'
 for name,digest in {'file_auth.py':'5cad2c509e5c82cd7162f7a10ded2d08c4af768a20dbb9d8ddafb9a49fa5ecbb','idle.py':'3fd14b64793b79d97da179c98606c1f9b58a05420fe3eb01096d0301e63086e4','tokenize_adapter.py':'f5f863fd41732a7e56cb73e883471572819ac4554b687befd8e6205006509386'}.items():expected[production+'source/'+name]=digest
 expected[production+'config.json']='4a5ea3904fba96480884b91414524617683b50e6f79fef96261e2b92183e6b71'
 expected.update({'/usr/local/lib/llm-server/node-api/scripts/control/node_observation.py':'18b4f2d4c8e34a3b23e0e87a90c1b68821bd7becc02349196a598a86ad5b8666','/data/services/image21-runtime-20260923/source/service.py':'748b94a5b17e6c2cb4229d69f4dd142dc9cf099b05206f0f97e6c04173cab052','/data/services/image21-runtime-20260923/config.json':'439751ac672fc183799e65a434449aadd60d5b421d1f4887e47c35d3cb9088f7'})
 expected.update(json.loads((REPO/'reports/h013-integrated-fan-live-20260927/FAN-RESULT.json').read_text())['installation']['sha256'])
 expected.update({'/usr/local/lib/llm-server/control-api/scripts/lifecycle/manager.py': 'b0f1ef12151757cd8432d84a03406efdb35089abaf5bac78066c887de43c2a6f', '/usr/local/lib/llm-server/control-api/scripts/lifecycle/runtime_io.py': 'a85f7126cde008c0c5a03fba64b6ba051df508f058efd6871c7c868ed9b42b52', '/usr/local/lib/llm-server/control-api/scripts/lifecycle/storage_binding.py': '69e61ce6685c310ce83449de75d45b209e63c6454c175f03d42bdad3daea7fbf', '/usr/local/lib/llm-server/control-api/scripts/lifecycle/slot_state.py': 'fd88954ee77521dc0e3f87454315e89a25508383ffa19b84115d76930fff8c79', '/data/services/flash-h008-20260926/source/owner.py': 'd4a628876b8643a01277039ab744e87a2218e3b87e2c6207e2d67816b570a4b1', '/data/services/image21-runtime-20260923/source/service.py': '748b94a5b17e6c2cb4229d69f4dd142dc9cf099b05206f0f97e6c04173cab052'})
 cap=old['capacities'];cap['flash'].update(context_length=1048576,max_total_tokens=1048576,max_total_num_tokens=1048576)
 common=(HERE/'vm-common.py').read_text();fans=(HERE/'fan-readings.py').read_text();body=(HERE/'job-body.py').read_text()
 # Load definitions without invoking main. All telemetry functions are exactly the candidate's.
 tree=ast.parse(body);tree.body=[n for n in tree.body if not (isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__')]
 definitions=ast.unparse(tree)
 params={'source_base':'cb4cdf87b692b3b81b124b54b7c848cfc225175a','session_id':json.loads((TASK/'SESSION.json').read_text())['thread_id'],'boot':'6535a867-8e27-49d9-8a04-4ecc1adb1e32','source_matches':expected,'capacities':cap,'containers':{},'container_policy':{},'power_limits':{},'preflight_only':True}
 script=common+'\nPARAMETERS='+repr(params)+'\n'+fans+'\n'+definitions+'\n'+(HERE/'preflight-body.py').read_text()
 compile(script,'h013-readonly-preflight','exec')
 (TASK/'private/preflight-remote.py').write_text(script)
 r=subprocess.run(['ssh','-o','ConnectTimeout=5','-T','ai-vm','sudo -n python3 -I -B -'],input=script.encode(),capture_output=True,timeout=150)
 (TASK/'private/PREFLIGHT.stderr').write_bytes(r.stderr);(TASK/'private/PREFLIGHT.json').write_bytes(r.stdout)
 assert r.returncode==0,r.stderr.decode()[-1500:]
 out=json.loads(r.stdout);(HERE.parent/'PREFLIGHT-SUMMARY.json').write_text(json.dumps({k:v for k,v in out.items() if k in ('utc','status','blockers','sources_verified','native','collector_status','boot','no_inference','guard','parameters')},indent=2)+'\n')
 (TASK/'private/PARAMETERS.json').write_text(json.dumps(out['parameters'],indent=2)+'\n')
 print(json.dumps({k:out[k] for k in ['utc','status','blockers','collector_status','sources_verified']}))
if __name__=='__main__':main()
