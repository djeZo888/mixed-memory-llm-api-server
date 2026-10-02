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
"""Separate selected privileged reader/control graph; disabled, never grants lifecycle."""
import datetime,hashlib,importlib.util,json,os,re,subprocess,signal,time
from pathlib import Path
import control
SCHEMA='h043-selected-readonly-graph-v1'
ROOT='/data/logs/h044-vision-v03/read-only'

def materialize(g,source_root,helper_root):
 if set(g)!={'schema','execute','privateRoot','uid','directoryMode','fileMode','readerSHA256','readerPath','helperManifest','bootId','owner','action','count','commandCount','fileCount','wallSeconds','outputBytes','outputProjection','rootCarrier','notBefore','expires'}:raise control.Refused('reader_template_fields')
 if (g['schema'],g['execute'],g['privateRoot'],g['uid'],g['directoryMode'],g['fileMode'],g['readerPath'],g['action'],g['count'])!=(SCHEMA,False,ROOT,0,'0700','0600','scripts/h043/vision_runtime_probe.py','selected_privileged_read_only',1):raise control.Refused('fixed_reader_controls')
 if g['wallSeconds']!=90 or g['outputBytes']!=1048576 or g['commandCount']!=16 or g['fileCount']!=33:raise control.Refused('reader_exact_caps')
 if control.sha((Path(source_root)/g['readerPath']).read_bytes())!=g['readerSHA256']:raise control.Refused('reader_source_hash')
 for rel,digest in g['helperManifest'].items():
  if rel not in ('control.py','read_only_control.py') or control.sha((Path(helper_root)/rel).read_bytes())!=digest:raise control.Refused('reader_helper_hash')
 if g['rootCarrier']!='MISSING_AUTHENTIC_ROOT_SIGNATURE' or g['notBefore'] is not None or g['expires'] is not None:raise control.Refused('disabled_not_current_go')
 return {'graph':g,'materializedSHA256':control.sha(control.canonical(g)),'execute':False,'missing':['authentic root carrier','new finite absolute 90s window','current root-owned node/owner tuple']}

def execute(g,go_path=None,sig_path=None):
 # Separate read-only carrier: it can never authorize model/lifecycle/health actions.
 if os.geteuid()!=0:raise control.Refused('ROOT_READER_UID_REQUIRED')
 anchor_sha=control.trusted_anchor()
 key=Path(control.TRUST_ANCHOR);st=key.lstat()
 if st.st_uid!=0 or st.st_mode&0o022 or control.sha(key.read_bytes())!=anchor_sha:raise control.Refused('read_only_root_anchor')
 raw=control.read_private(go_path,0);control.read_private(sig_path,0,256)
 check=subprocess.run(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-inkey',control.TRUST_ANCHOR,'-rawin','-in',go_path,'-sigfile',sig_path],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
 if check.returncode!=0:raise control.Refused('read_only_signature')
 go=json.loads(raw)
 if set(go)!={'schema','nonce','graphSHA256','bootId','ownerSHA256','action','count','notBefore','expires','rootCarrierSHA256'} or go['schema']!='h043-finite-root-read-only-v1':raise control.Refused('read_only_carrier_fields')
 if go['action']!='selected_privileged_read_only' or type(go['count']) is not int or go['count']!=1 or not re.fullmatch('[a-f0-9]{64}',go['nonce']):raise control.Refused('read_only_action')
 now=time.time();start=datetime.datetime.fromisoformat(go['notBefore']).timestamp();end=datetime.datetime.fromisoformat(go['expires']).timestamp()
 if not start<=now<end or not 0<end-start<=90:raise control.Refused('read_only_finite_window')
 if go['rootCarrierSHA256']!=anchor_sha or go['graphSHA256']!=control.sha(control.canonical(g)) or go['bootId']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip() or go['ownerSHA256']!=control.sha(control.canonical(g['owner'])):raise control.Refused('read_only_current_binding')
 materialize(g,control.SOURCE_ROOT,control.SOURCE_ROOT+'/scripts/h044/vision_runtime')
 control.exclusive(ROOT+'/spent-'+go['nonce']+'.json',{'carrierSHA256':control.sha(raw),'action':go['action'],'count':1})
 spec=importlib.util.spec_from_file_location('h043_selected_reader',Path(control.SOURCE_ROOT)/g['readerPath']);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

 def expired(*_):raise TimeoutError('read_only_deadline')
 old=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,end-time.time())
 try:result=module.selected_inventory(authorized_go=go)
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 control.exclusive(ROOT+'/readback-'+go['nonce']+'.json',result);return result

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
 if not a.execute:raise SystemExit('DEFAULT_CLOSED_NO_CURRENT_ROOT_READ_ONLY_GO')
 graph=json.loads(control.read_private(ROOT+'/READ-ONLY-TEMPLATE.json',0))
 print(json.dumps(execute(graph,ROOT+'/CURRENT-READ-ONLY-GO.json',ROOT+'/CURRENT-READ-ONLY-GO.json.sig'),indent=2))
