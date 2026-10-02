# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[3]
 _loader = _root/'scripts/h044/vision_runtime/trusted_imports.py'
 _manifest = (_root/'SOURCE-MANIFEST.json') if str(_root).startswith('/opt/') else (_root.parent/'output/SOURCE-MANIFEST.json')
 _uid = 0 if str(_root).startswith('/opt/') else _o.geteuid()
 def _protected(p):
  if str(p)!=_o.path.realpath(p):raise ValueError('bootstrap_symlink')
  for a in [p,*p.parents]:
   z=a.lstat()
   if z.st_uid not in (0,_uid) or z.st_mode&0o022:raise ValueError('bootstrap_owner_mode')
  fd=_o.open(p,_o.O_RDONLY|_o.O_NOFOLLOW)
  try:
   z=_o.fstat(fd)
   if not _s.S_ISREG(z.st_mode) or z.st_uid!=_uid or z.st_nlink!=1 or z.st_size>1048576:raise ValueError('bootstrap_source')
   raw=_o.read(fd,1048577);q=_o.fstat(fd)
   if (z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)!=(q.st_dev,q.st_ino,q.st_size,q.st_mtime_ns,q.st_ctime_ns):raise ValueError('bootstrap_changed')
   return raw
  finally:_o.close(fd)
 _m=_j.loads(_protected(_manifest));_b=_protected(_loader);_record=_m['modules']['trusted_imports']
 if _record['path']!='scripts/h044/vision_runtime/trusted_imports.py' or _h.sha256(_b).hexdigest()!=_record['sha256'] or len(_b)!=_record['bytes']:raise ValueError('bootstrap_hash')
 _spec=_iu.spec_from_file_location('trusted_imports',_loader);_module=_iu.module_from_spec(_spec)
 import sys as _sys
 _sys.modules['trusted_imports']=_module;exec(compile(_b,str(_loader),'exec'),_module.__dict__)
 _module.install(_root,_m,_uid)

#!/usr/bin/env python3
"""Private sealed control primitives. No approval is installed by this source phase."""
import datetime,hashlib,json,os,re,stat,subprocess,time
from pathlib import Path
EXECUTION_ENABLED=False
TRUST_ANCHOR='/etc/llm-server/h043-vision-root-ed25519.pub'
TRUST_SHA=None  # authentic root carrier must be installed/bound by separately reviewed successor
PHASE_ROOT='/data/logs/h044-vision-v03'
SOURCE_ROOT='/opt/llm-technical-vision/h044-v03'
GATES=('root_owner_tuple','lease_freeze_admission','hardware_thermal','model_receipt_inode','exact_oci_support','credential_actual_uid','authenticated_ingress','full_source_seal','host_headroom','gpu_peak_measurement_plan')
class Refused(ValueError):pass
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read_private(path,owner=None,cap=1048576):
 p=Path(path);owner=os.geteuid() if owner is None else owner
 if not p.is_absolute() or str(p)!=os.path.realpath(p):raise Refused('canonical_private_path')
 for a in p.parents:
  s=os.lstat(a)
  if s.st_uid not in (0,owner) or not stat.S_ISDIR(s.st_mode) or s.st_mode&0o022:raise Refused('unsafe_parent')
 f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  s=os.fstat(f)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=owner or stat.S_IMODE(s.st_mode) not in (0o400,0o600) or s.st_size>cap:raise Refused('private_regular_required')
  b=os.read(f,cap+1);z=os.fstat(f)
  if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns):raise Refused('changed')
 finally:os.close(f)
 if len(b)>cap:raise Refused('cap')
 return b

def exclusive(path,value):
 # Durable one-time claim/export; never overwrite original receipts.
 p=Path(path);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
 d=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(d)
 finally:os.close(d)

def validate_graph(g):
 if set(g)!={'schema','execute','phase','sourceRoot','privateRoot','sourceManifest','helperManifest','controlManifest','image','modelReceipt','configSHA256','rootOwnerEvidence','runtime','actions','gates','rootCarrier','workload'}:raise Refused('graph_fields')
 if g['schema']!='h044-private-runtime-graph-v1' or g['execute'] is not False or g['phase'] not in ('V-runtime04','V-runtime05','V-live06','H045-vision'):raise Refused('disabled_exact_graph')
 if (g['sourceRoot'],g['privateRoot'])!=(SOURCE_ROOT,PHASE_ROOT):raise Refused('fixed_roots')
 if g['image']!='vllm/vllm-openai@sha256:5f5e535216848d0c52159c8c13a0af04be5f6fe1a84e79914300610796f76d40':raise Refused('image')
 if set(g['gates'])!=set(GATES):raise Refused('gates')
 c=g['rootCarrier']
 if set(c)!={'publicKeyPath','publicKeySHA256','authenticRootProof','workerProducerIsRootProof'} or c['publicKeyPath']!=TRUST_ANCHOR or c['workerProducerIsRootProof'] is not False:raise Refused('root_carrier')
 if c['publicKeySHA256'] is not None and not re.fullmatch('[a-f0-9]{64}',c['publicKeySHA256']):raise Refused('root_anchor_hash')
 for table in ('sourceManifest','helperManifest','controlManifest'):
  for name,value in g[table].items():
   if not re.fullmatch(r'[A-Za-z0-9_./-]{1,180}',name) or '..' in name.split('/') or not re.fullmatch(r'[0-9a-f]{64}',value):raise Refused('manifest')
 if set(g['actions'])!={'preflight','load','inference','stop','pull'} or any(v['enabled'] is not False for v in g['actions'].values()):raise Refused('all_actions_disabled')
 enabled_roster(g)
 return g

def enabled_roster(graph):
 """Explicit signed capacity plan; absence preserves the historical contract."""
 roster=graph.get('runtime',{}).get('enabledServices')
 if 'enabledServices' not in graph.get('runtime',{}):return None
 expected={'general':['qwen0','qwen1','mimo'],'vision':['interpretation','ocr'],'generation':False}
 if roster!=expected or not isinstance(roster,dict) or roster.get('generation') is not False:raise Refused('enabled_service_roster')
 return roster

def protected_roster(graph):
 roster=enabled_roster(graph)
 if roster is None:
  expected=graph['rootOwnerEvidence'].get('otherFourInstances')
  if not isinstance(expected,list) or len(expected)!=4:raise Refused('other_four_current_identity_missing')
  return expected
 expected=graph['rootOwnerEvidence'].get('protectedInstances')
 if not isinstance(expected,list) or len(expected)!=len(roster['general']):raise Refused('enabled_general_current_identity_missing')
 if any(not isinstance(x,dict) for x in expected):raise Refused('enabled_general_identity')
 if {x.get('serviceId') for x in expected}!=set(roster['general']):raise Refused('enabled_general_roles')
 ids=[x.get('id') for x in expected]
 if any(not isinstance(x,str) or not re.fullmatch('[a-f0-9]{64}',x) for x in ids) or len(set(ids))!=len(ids):raise Refused('enabled_general_unique_container_ids')
 if any(not x.get('birth') or not x.get('image') or not x.get('devices') for x in expected):raise Refused('enabled_general_exact_identity_required')
 return expected

def verify_source(g,source_root,helper_root):
 from trusted_imports import protected_bytes
 root=Path(source_root);uid=0 if str(root).startswith('/opt/') else os.geteuid()
 for table,base in (('sourceManifest',root),('helperManifest',Path(helper_root)),('controlManifest',root if str(root).startswith('/opt/') else root.parent/'output')):
  for rel,digest in g[table].items():
   if sha(protected_bytes(base/rel,uid))!=digest:raise Refused('source_hash_mismatch')
 if g['configSHA256']!=g['sourceManifest'].get('configs/vision/h043-candidate.json'):raise Refused('config_binding')


def parse_proof(raw):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d:raise Refused('duplicate_proof_field')
   d[k]=v
  return d
 try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Refused('nonfinite_proof')))
 except (ValueError,TypeError,UnicodeError,RecursionError) as e:raise Refused('malformed_proof') from e


def validate_carrier(raw,graph,anchor_sha,now,boot):
 g=parse_proof(raw)
 if not isinstance(g,dict) or set(g)!={'schema','nonce','notBefore','expires','bootId','graphSHA256','ownedTupleSHA256','actions','actionDeadlines','counts','issuer','rootCarrierSHA256'}:raise Refused('carrier_fields')
 if g['schema']!='h044-finite-root-go-v1' or g['issuer']!='ROOT_AUTHENTIC_SIGNER' or g['rootCarrierSHA256']!=anchor_sha:raise Refused('issuer_identity')
 if not isinstance(g['nonce'],str) or not re.fullmatch('[0-9a-f]{64}',g['nonce']):raise Refused('finite_nonce')
 try:start=datetime.datetime.fromisoformat(g['notBefore']).timestamp();end=datetime.datetime.fromisoformat(g['expires']).timestamp()
 except (ValueError,TypeError):raise Refused('malformed_window')
 if not start<=now<end or not 0<end-start<=1200:raise Refused('finite_window')
 if g['graphSHA256']!=sha(canonical(graph)) or g['bootId']!=boot:raise Refused('current_graph_boot')
 if g['ownedTupleSHA256']!=sha(canonical(graph['rootOwnerEvidence'])):raise Refused('owned_tuple')
 if not isinstance(g['actions'],list) or not g['actions'] or len(set(g['actions']))!=len(g['actions']) or set(g['actions'])-{'preflight','load','inference','stop','pull'}:raise Refused('finite_actions')
 if set(g['actions'])!=set(g['counts']) or set(g['actions'])!=set(g['actionDeadlines']) or any(type(n) is not int or n!=1 for n in g['counts'].values()):raise Refused('one_action_count')
 for deadline in g['actionDeadlines'].values():
  try:t=datetime.datetime.fromisoformat(deadline).timestamp()
  except (ValueError,TypeError):raise Refused('malformed_action_deadline')
  if not start<t<=end:raise Refused('action_deadline')
 return g

def carrier(go_path,sig_path,graph):
 anchor_sha=trusted_anchor()
 key=Path(TRUST_ANCHOR);s=key.lstat()
 if s.st_uid!=0 or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_mode&0o022 or sha(key.read_bytes())!=anchor_sha:raise Refused('untrusted_root_anchor')
 raw=read_private(go_path,0);sig=read_private(sig_path,0,256)
 import receipt_recorder
 c=receipt_recorder.record(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-inkey',TRUST_ANCHOR,'-rawin','-in',go_path,'-sigfile',sig_path],PHASE_ROOT,environment={'PATH':'/usr/bin:/bin','LC_ALL':'C'},timeout=5,label='finite-root-signature')
 if c['status']!='COMPLETE' or c['actualExitCode']!=0:raise Refused('invalid_root_signature')
 return validate_carrier(raw,graph,anchor_sha,time.time(),Path('/proc/sys/kernel/random/boot_id').read_text().strip())

def trusted_anchor():
 # Pre-existing authentic root trust anchor only. Never installs keys or changes auth.
 p=Path(TRUST_ANCHOR);q=Path(TRUST_ANCHOR+'.sha256')
 try:
  for f in (p,q):
   s=f.lstat()
   if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_nlink!=1 or s.st_mode&0o022 or str(f)!=os.path.realpath(f):raise Refused('root_anchor_unsafe')
  expected=q.read_text().strip()
  if not re.fullmatch('[a-f0-9]{64}',expected) or sha(p.read_bytes())!=expected:raise Refused('root_anchor_hash')
  return expected
 except OSError:raise Refused('DEFAULT_CLOSED_AUTHENTIC_ROOT_ANCHOR_MISSING')

def current_authority(action):
 trusted_anchor()
 graph=json.loads(read_private(PHASE_ROOT+'/RUNTIME-GRAPH.json',0));validate_graph(graph)
 go=carrier(PHASE_ROOT+'/CURRENT-GO.json',PHASE_ROOT+'/CURRENT-GO.json.sig',graph)
 if os.geteuid()!=0:raise Refused('actual_root_control_context')
 if action in ('load','preflight') and not re.fullmatch(r'sha256:[a-f0-9]{64}',graph['rootOwnerEvidence'].get('imageId') or ''):raise Refused('current_exact_OCI_image_ID_missing')
 if action=='load':
  protected_roster(graph)
  if not graph['rootOwnerEvidence'].get('credentialDescriptorProof'):raise Refused('current_UID_descriptor_proof_missing')
 if action not in go['actions'] or datetime.datetime.fromisoformat(go['actionDeadlines'][action]).timestamp()<=time.time():raise Refused('finite_current_action_missing')
 if any(graph['gates'][x]!='PASS' for x in GATES):raise Refused('current_root_gates_missing')
 verify_source(graph,SOURCE_ROOT,SOURCE_ROOT+'/scripts/h044/vision_runtime')
 return graph,go
