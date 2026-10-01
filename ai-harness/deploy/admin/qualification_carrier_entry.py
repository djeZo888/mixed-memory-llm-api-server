#!/usr/bin/env python3
"""Fixed root signed carrier entry. No action at import; no public HTTP switch."""
import sys,os,json,hashlib,stat,runpy,hmac
from pathlib import Path

def main(argv):
 if os.geteuid()!=0 or len(argv)!=3 or os.environ.get('PYTHONPATH') or os.environ.get('PYTHONHOME'):raise SystemExit('isolated_root_entry_required')
 # Bootstrap builtin-only protected source check BEFORE executing helper imports.
 here=Path(__file__).resolve().parent
 for name in ['qualification_carrier_host.py','qualification_carrier.py','qualification_guardian.py','local_helper.py','resource_observer.py']:
  p=here/name;s=p.lstat()
  if p.resolve()!=p or s.st_uid!=0 or s.st_mode&0o022 or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:raise SystemExit('protected_root_source_required')
 def private(path,bound):
  p=Path(path);s=p.lstat()
  if p.resolve()!=p or s.st_uid!=0 or not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or s.st_size>bound:raise SystemExit('root_private_input_required')
  return p.read_bytes()
 raw=private(argv[0],4*1024*1024);approval=json.loads(private(argv[1],8192));key=private(argv[2],32)
 if len(key)!=32 or set(approval)!={'inputSHA256','mac'} or approval['inputSHA256']!=hashlib.sha256(raw).hexdigest() or not hmac.compare_digest(approval['mac'],hmac.new(key,raw,hashlib.sha256).hexdigest()):raise SystemExit('root_exact_hmac_required')
 reviewed=json.loads(raw)
 for name in ['qualification_carrier_host.py','qualification_carrier.py','qualification_guardian.py','local_helper.py','resource_observer.py']:
  p=str(here/name)
  if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=reviewed['privilegedSourceHashes'].get(p):raise SystemExit('source_hash_before_import_required')
 sys.path.insert(0,str(here))
 from qualification_carrier_host import signed_packet,LinuxCarrierHost
 packet=signed_packet(*argv)
 for name in ['qualification_carrier_host.py','qualification_carrier.py','qualification_guardian.py','local_helper.py','resource_observer.py']:
  p=str(here/name)
  if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=packet['privilegedSourceHashes'].get(p):raise SystemExit('reviewed_privileged_source_hash_required')
 from qualification_carrier import CarrierPlan,QualificationCarrier
 import local_helper as helper
 user=packet['user'];identity=helper.Identity(user['uid'],user['gid'],user['name'],user['home']);owner=helper.CommandOwner(identity);freeze=helper.ProtectedFreeze(user['uid']);ops=helper.Operations(Path(helper.STATE_PATH),owner.boot_id,owner.observe_service,owner.execute,freeze)
 host=LinuxCarrierHost(packet,owner,freeze,helper._lease_module)
 plan=CarrierPlan(packet['transactionId'],packet['bootId'],packet['stopRequest'],packet['startRequest'],packet['issuedAtMs']/1000,packet['expiresAtMs']/1000,packet['dispatchCutoffMs']/1000,120,tuple(Path(p) for p in packet['sourceRoots']),Path(packet['backupRoot']),Path(packet['journal']))
 try:return QualificationCarrier(ops,host).run(plan)
 finally:ops.db.close()
if __name__=='__main__':
 try:main(sys.argv[1:])
 except Exception:raise SystemExit('carrier_failed_inspect_private_receipts_no_replay')
