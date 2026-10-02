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
"""Root-only offline finite issuer. Source-only worker installs no authority; only the authentic root signer can issue."""
import argparse,datetime,json,os,re,subprocess
from pathlib import Path
import control

def issue(graph,request,private_key,output):
 if os.geteuid()!=0:raise control.Refused('ROOT_SIGNER_REQUIRED')
 anchor_sha=control.trusted_anchor()
 control.validate_graph(graph)
 if set(request)!={'nonce','notBefore','expires','bootId','actions','actionDeadlines','counts'}:raise control.Refused('exact_issuer_input')
 if any(graph['gates'][x]!='PASS' for x in control.GATES):raise control.Refused('current_gates_missing')
 if not re.fullmatch('[0-9a-f]{64}',request['nonce']):raise control.Refused('nonce')
 start=datetime.datetime.fromisoformat(request['notBefore']).timestamp();end=datetime.datetime.fromisoformat(request['expires']).timestamp()
 if not 0<end-start<=1200 or request['bootId']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise control.Refused('window_boot')
 if set(request['actions'])!=set(request['counts']) or set(request['actions'])!=set(request['actionDeadlines']) or any(type(v) is not int or v!=1 for v in request['counts'].values()):raise control.Refused('counts')
 if set(request['actions'])-set(graph['actions']) or not request['actions']:raise control.Refused('exact_actions')
 # Pull is a separate carrier, never bundled with load/inference.
 if 'pull' in request['actions'] and request['actions']!=['pull']:raise control.Refused('separate_pull_authority')
 control.read_private(private_key,0,4096)
 go={'schema':'h044-finite-root-go-v1',**request,'graphSHA256':control.sha(control.canonical(graph)),'ownedTupleSHA256':control.sha(control.canonical(graph['rootOwnerEvidence'])),'issuer':'ROOT_AUTHENTIC_SIGNER','rootCarrierSHA256':anchor_sha}
 control.exclusive(output,go);sig=output+'.sig'
 with open(sig,'xb') as f:
  os.chmod(sig,0o600);c=subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',private_key,'-in',output],stdout=f,stderr=subprocess.DEVNULL,timeout=5)
 if c.returncode!=0:raise control.Refused('signing_failed_no_retry')
 return {'carrierSHA256':control.sha(Path(output).read_bytes()),'signatureSHA256':control.sha(Path(sig).read_bytes()),'workerIdentityIsRootProof':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('graph');p.add_argument('request');p.add_argument('key');p.add_argument('output');a=p.parse_args()
 print(json.dumps(issue(json.loads(Path(a.graph).read_text()),json.loads(Path(a.request).read_text()),a.key,a.output),indent=2))
if __name__=='__main__':main()
