#!/usr/bin/env python3
"""Finite H025 Mac SSH status bridge; sink uses existing anchored storage only.

No credentials forwarded. No requests, model/fan actions, new service or keys.
If this child exits, independent VM driver's <=5s mirror gate stops owned work.
"""
import argparse,datetime,hashlib,json,os,re,shlex,subprocess,sys,time
from pathlib import Path
from contract import canonical,digest,require,utc_seconds,validate_manifest
FAN_PATH='/var/lib/sova-cha-fan3/status.json'

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=('run','sink'));p.add_argument('--manifest',required=True);p.add_argument('--go',required=True);p.add_argument('--remote-source');p.add_argument('--intent');a=p.parse_args()
 m=json.loads(Path(a.manifest).read_bytes());g=json.loads(Path(a.go).read_bytes());validate_manifest(m)
 require(g['task_id']==m['task_id'] and g['deployment_sha256']==digest(m) and g['action']=='ROOT GO H025 PHASE B','bridge exact GO binding')
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 require(utc_seconds(g['not_before_utc'])<=utc_seconds(now)<utc_seconds(g['settlement_deadline_utc']),'bridge outside finite grant')
 if a.action=='sink':
  from native import ROOT,protected
  sys.path.insert(0,str(ROOT/'scripts'))
  from install.storage import Storage
  from install.storage_io import MountedStorageGuard,AnchoredRoot
  # Re-read protected exact inputs; no periodic canonical lease/root payload scan.
  require(json.loads(protected(a.manifest))==m and json.loads(protected(a.go))==g,'bridge protected inputs drift')
  raw=sys.stdin.buffer.read(65537);require(len(raw)<=65536,'fan source exceeds64KiB')
  value=json.loads(raw);require(value.get('schema_version')==1,'fan source schema')
  boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();require(boot==m['boot_id'],'bridge VM boot changed')
  class Command:
   def run(self,argv,*,timeout=30,env=None):return subprocess.check_output(argv,text=True,timeout=timeout,env=env)
  r=Storage({},Command()).read_registration();s=Storage({'data_dir':r['data']['path'],'data_uuid':r['data']['uuid'],'model_dir':r['models']['path'],'model_uuid':r['models']['uuid'],'storage_mode':r['storage_mode']},Command())
  target=Path(m['fan_status_path'])
  with MountedStorageGuard(s) as guard,AnchoredRoot(str(target.parent),guard) as root:
   root.atomic_json(target.name,{'task_id':m['task_id'],'vm_boot_id':boot,'received_utc':now,'received_monotonic':time.monotonic(),'controller':value})
  return
 require(a.intent and a.remote_source,'bridge source and unique durable intent required')
 require(re.fullmatch(r'/data/logs/H025-[A-Za-z0-9_-]+/driver/bridge.py',a.remote_source),'exact task bridge path')
 # Intent is local private evidence, deliberately O_EXCL/no replay.
 fd=os.open(a.intent,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:
  f.write(canonical({'task_id':m['task_id'],'pid':os.getpid(),'started_utc':now,'deadline':g['settlement_deadline_utc'],'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'go_sha256':digest(g)})+b'\n');f.flush();os.fsync(f.fileno())
 remote=['sudo','-n','python3','-B',a.remote_source,'sink','--manifest',str(Path(a.remote_source).parent.parent/'manifest.json'),'--go',str(Path(a.remote_source).parent.parent/'go.json')]
 # Existing user owns0600 status. Python caps bytes and rejects symlink/odd owner.
 reader="import os,stat,pathlib,sys;p=pathlib.Path('/var/lib/sova-cha-fan3/status.json');s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and s.st_size<=65536;sys.stdout.buffer.write(p.read_bytes())"
 while time.time()<utc_seconds(g['settlement_deadline_utc']):
  raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=3','ai-harness','python3 -c '+shlex.quote(reader)],timeout=4)
  require(len(raw)<=65536,'bridge source bound')
  subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=3','ai-vm',' '.join(map(shlex.quote,remote))],input=raw,check=True,timeout=4,stdout=subprocess.DEVNULL)
  time.sleep(1)

if __name__=='__main__':main()
