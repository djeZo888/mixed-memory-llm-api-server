"""Exact source-successor staging only. Requires coordinator's exact reviewed GO and idle gap."""
import datetime,hashlib,importlib.util,json,os,pathlib,sys
P=pathlib.Path
BASE=P('/data/services/mimo-h016-20260927')
STAGE=P('/data/backups/H030-SPECIAL01-stage')
BOOT='992bf979-efae-495b-9ab2-26e75ed5c5d0'
def require(ok,reason):
 if not ok: raise RuntimeError(reason)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 require(os.geteuid()==0 and sys.argv[1:]==['apply'],'explicit_root_apply_required')
 require(datetime.datetime.now(datetime.timezone.utc)<datetime.datetime(2026,9,29,7,43,tzinfo=datetime.timezone.utc),'deadline')
 proposal=json.loads((STAGE/'MIMO-DEPLOY-PROPOSAL.json').read_bytes())
 for name,pin in proposal['stageHashes'].items():require(sha((STAGE/name).read_bytes())==pin,'stage_hash_changed_'+name)
 o=module(BASE/'source/owner.py','old_mimo_owner');candidate=module(STAGE/'owner.py','candidate_mimo_owner')
 h=o.setup();old=o.read(BASE/'manifest.json');new=json.loads((STAGE/'successor-manifest.json').read_bytes());delta=json.loads((STAGE/'source-successor-delta.json').read_bytes())
 a,b=json.loads(json.dumps(old)),json.loads(json.dumps(new));before,after=a.pop('source_sha256'),b.pop('source_sha256')
 require(a==b and set(before)==set(after),'non_source_change')
 require({p:{'old':before[p],'new':after[p]} for p in before if before[p]!=after[p]}==delta,'delta_mismatch')
 require(o.digest(old)==proposal['oldManifestCanonicalSha256'] and o.digest(new)==proposal['newManifestCanonicalSha256'],'manifest_digest_changed')
 require(len(delta)==13,'exact_13_leaf_delta_required')
 with h.acquire_lease(blocking=False) as lease,h.MountedStorageGuard(h.s) as guard:
  o.storage_paths(h,guard);h.s.root_payload_guard();lease.validate()
  require(o.BOOT.read_text().strip()==BOOT,'boot_changed')
  original={n:o.protected(BASE/n) for n in proposal['predecessorHashes']}
  require(all(sha(raw)==proposal['predecessorHashes'][n] for n,raw in original.items()),'predecessor_changed')
  state=json.loads(original['state.json']);selection=o.require_selected(old,state['selection'])
  for path,pin in {**new['source_sha256'],**new['qualification_sha256']}.items():
   expected=before[path] if path==str(BASE/'source/owner.py') else pin
   require(sha(o.protected(path))==expected,'current_source_changed_'+path)
  for pin in proposal['qwenIdentities']:
   c=o.inspect(pin['id']);require(c['Id']==pin['id'] and c['State']['Running'] is True and c['State']['Pid']==pin['pid'] and c['Image']==pin['image'] and c['State']['StartedAt']==pin['startedAt'],'qwen_identity_changed')
  physical=candidate.settled_source_absence(old,state,BOOT)
  from lifecycle.storage_binding import RegisteredStorageBinding
  from lifecycle.manager import StorageRunner
  from lifecycle.hardware_policy import read_latch_status
  hardware=read_latch_status(RegisteredStorageBinding.load(StorageRunner()),[o.GPU],current_boot_id=BOOT)
  require(hardware['hardware_latched'] is False,'hardware_not_current')
  frozen={'schema_version':1,'task':'H030-SPECIAL01','files':{n:raw.decode() for n,raw in original.items()},'sha256':proposal['predecessorHashes'],'prior_request_outcome':'FAILED_OR_UNKNOWN','physical_absence':physical}
  o.exclusive_recovery_write(h,guard,'h030-special01-source-predecessor.json',frozen)
  with h.AnchoredRoot(str(BASE),guard) as root:
   for name,raw in [('source-successor-prior-manifest.json',original['manifest.json']),('source-successor-prior-owner.py',original['source/owner.py']),('source-successor-delta.json',(STAGE/'source-successor-delta.json').read_bytes())]:
    with root.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400) as out:out.write(raw);out.fsync()
    os.fsync(root.fileno());require(o.protected(BASE/name)==raw,'backup_readback')
   def replace_source(raw,tag):
    temp='source/.h030-special01-'+tag
    with root.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644) as out:out.write(raw);out.fsync()
    root.replace(temp,'source/owner.py');root.check()
   try:
    replace_source((STAGE/'owner.py').read_bytes(),'new')
    root.atomic_json('manifest.json',new)
    candidate.reviewed_source_amendment(old,new,delta)
    candidate.source_preflight(h,new)
    require(o.read(BASE/'selection.json')==selection,'selection_changed')
    require(all(o.protected(BASE/n)==raw for n,raw in original.items() if n not in ['manifest.json','source/owner.py']),'history_changed')
   except BaseException:
    # Stage owns no runtime or selection. Restore only its two source-binding writes.
    require(o.read(BASE/'selection.json')==selection,'partial_stage_selection_changed')
    replace_source(original['source/owner.py'],'rollback')
    temp='h030-special01-manifest-rollback.tmp'
    with root.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as out:out.write(original['manifest.json']);out.fsync()
    root.replace(temp,'manifest.json');root.check()
    raise
  h.s.root_payload_guard();lease.validate()
  result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'SOURCE_STAGED_SELECTION_OLD','oldManifestSha256':o.digest(old),'newManifestSha256':o.digest(new),'ownerSha256':sha(o.protected(BASE/'source/owner.py')),'delta':delta,'oldStateSha256':sha(o.protected(BASE/'state.json')),'physicalAbsence':physical,'selectionUnchanged':True,'historyUnchanged':True,'inferenceSubmitted':0}
  o.exclusive_recovery_write(h,guard,'h030-special01-source-stage.json',result)
 print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'status':'FAIL','type':type(e).__name__,'code':str(e) if type(e) in (RuntimeError,) else None}));raise SystemExit(1)
