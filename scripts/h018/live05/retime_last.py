#!/usr/bin/env python3
"""Stage only the approved inactive LAST admission ceiling; never dispatch."""
import datetime,hashlib,importlib.util,json,os
from pathlib import Path
P=Path
B=P('/data/build/H018-20260928/worker1-last950k')
L=P('/data/logs/H018-20260928/worker1-last950k')
OWNER=P('/data/services/mimo-h016-20260927/source/owner.py')
def require(ok,why):
 if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 require(sha(OWNER.read_bytes())==CONFIG['source_sha256'][str(OWNER)],'owner_pin_changed')
 spec=importlib.util.spec_from_file_location('last_retime_owner',OWNER);o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o);h=o.setup()
 with o.settlement_lease(h) as lease,h.MountedStorageGuard(h.s) as g:
  h.s.root_payload_guard();o.storage_paths(h,g);g.check_path(str(B));g.check_path(str(L))
  state=o.read(o.BASE/'state.json');require({k:state.get(k) for k in CONFIG['production_identity']}==CONFIG['production_identity'],'owner_changed');require(o.selection()==CONFIG['selection'],'selection_changed')
  before=dict(x.split('=',1) for x in o.run(['systemctl','show','h018-last950k.service','-p','MainPID,ActiveState,SubState,InvocationID,UnitFileState'],3).splitlines())
  require(before['MainPID']=='0' and before['ActiveState']=='inactive' and before['UnitFileState']=='static','LAST_not_inactive')
  absent=[B/'ROOT-GO.json',B/'LAST-GO.json',B/'AUTHORITY.json',L/'DISPATCH-ATTEMPT.json',L/'DISPATCH.json',L/'CLIENT.json',L/'LAST-64K-REQUEST.json',L/'LAST-near950K-REQUEST.json']
  require(all(not p.exists() for p in absent),'LAST_authority_or_attempt_present')
  for path,pin in OLD_PINS.items():require(sha(o.protected(path))==pin,'reviewed_LAST_source_changed')
  old=o.protected(B/'client.py');new=old.replace(b'1790558700',b'1790559000')
  require(old.count(b'1790558700')==2 and new==NEW_SOURCE.encode(),'not_exact_two_clock_substitutions')
  require(str(B/'client.py') not in CONFIG['source_sha256'],'short_source_overlap')
  with h.AnchoredRoot(str(B),g) as a:
   with a.open('client.pre-LIVE05-0130.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400) as f:f.write(old)
   lease.validate()
   with a.open('client.py',os.O_WRONLY|os.O_TRUNC) as f:f.write(new)
  require(sha(o.protected(B/'client.py'))==sha(new),'client_readback_failed')
  h.s.root_payload_guard();require(o.selection()==CONFIG['selection'],'selection_changed_after')
  state=o.read(o.BASE/'state.json');require({k:state.get(k) for k in CONFIG['production_identity']}==CONFIG['production_identity'],'owner_changed_after')
  require(all(not p.exists() for p in absent),'LAST_authority_or_attempt_after')
  pins=dict(OLD_PINS);pins[str(B/'client.py')]=sha(new)
  for path,pin in pins.items():require(sha(o.protected(path))==pin,'LAST_readback_pin')
  lease.validate()
  print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'INACTIVE_LAST_RETIMED_SOURCE_ONLY','old_client_sha256':sha(old),'new_client_sha256':sha(new),'source_sha256':pins,'exact_two_clock_substitutions':True,'latest_admission_utc':'2026-09-28T01:30:00Z','active_cap_seconds':28800,'unit_before':before,'authority_and_attempt_absent':[str(p) for p in absent],'production_identity':CONFIG['production_identity'],'selection':CONFIG['selection'],'manager_reload':False,'dispatched':False}))
if __name__=='__main__':main()
