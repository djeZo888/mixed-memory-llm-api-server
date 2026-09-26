#!/usr/bin/env python3
"""Read-only finalization of H010 recovery after HTML status parsing correction."""
import pathlib,json,hashlib,importlib.util,urllib.request,datetime,os
TASK=pathlib.Path('/home/user/ai-harness-build/H010-WORKER2-20260927')
def sha(b):return hashlib.sha256(b).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 os.umask(0o077)
 receipt=TASK/'RECOVERY-02.json';raw=receipt.read_bytes();original=TASK/'RECOVERY-RAW-02.json'
 assert not original.exists(),'preserve first finalization attempt';original.write_bytes(raw)
 r=json.loads(raw);r['original_recorder_receipt_sha256']=sha(raw)
 r['original_recovery_script_sha256']=sha((TASK/'recover-harness-02.py').read_bytes())
 spec=importlib.util.spec_from_file_location('prior',TASK/'recover-harness-02.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 routes={}
 for path in ['/api/health','/status','/api/status/v1/system']:
  with urllib.request.urlopen('http://10.156.100.61'+path,timeout=15) as response:
   body=response.read();routes[path]={'http_status':response.status,'content_type':response.headers.get_content_type(),'body_bytes':len(body)}
   if path=='/api/health':r['health']=json.loads(body)
 assert all(x['http_status']==200 for x in routes.values())
 r['final_http']=routes;r['health_http']=r['status_http']=r['canonical_status_http']=200
 r['final_units']=m.units();assert r['final_units']==r['after_units'],'unexpected owner/unit change'
 fresh=json.loads(json.dumps(m.summary()));assert fresh==r['after_data'],'data changed after original check'
 m.require_idle(m.summary());assert fresh['h003_image_lane']['states']==[['idle',1]]
 assert all(r['history_preserved'].values()) and r['regular_files_preserved'] and r['other_services_unchanged']
 assert r['metadata']==r['after_metadata']
 r['canonical_availability']=json.loads((TASK/'CANONICAL-AVAILABILITY-02.json').read_text());assert r['canonical_availability']['status']=='PASS'
 r['worker1_release']={'path':str(TASK/'WORKER1-FINAL-RELEASE.md'),'sha256':sha((TASK/'WORKER1-FINAL-RELEASE.md').read_bytes()),'abort_receipt':json.loads((TASK/'WORKER1-OVERLAP-ABORT.json').read_text())}
 r['recorder_warning']='Ordinary app start succeeded. Initial recorder treated HTML /status as JSON and left status_http unset. Original failed receipt/log preserved. Read-only HTTP/content-type finalization passed; no second start or data restore.'
 r['status']='PASS';r['finalized_utc']=now();r['finalizer_pid']=os.getpid();r['four_instance_overlap']='NOT_TESTED';r['worker2_three_request_smoke']='PASS'
 receipt.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'utc':r['finalized_utc'],'app_pid':r['final_units']['ai-harness.service']['MainPID'],'history_preserved':True,'regular_files':r['after_files']['regular_non_database_files'],'all_four_available':True}))
if __name__=='__main__':main()
