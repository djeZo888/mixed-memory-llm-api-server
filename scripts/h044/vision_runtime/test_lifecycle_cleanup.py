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

import copy,json,tempfile,unittest
from pathlib import Path
from unittest import mock
import control,lifecycle as l
ROOT=Path(__file__).absolute().parents[3];OUT=ROOT.parent/'output';CID='a'*64;NID='b'*64;NONCE='c'*64
class CleanupTests(unittest.TestCase):
 def run_case(self,kind,changed=False):
  with tempfile.TemporaryDirectory(dir=OUT) as directory:
   p=Path(directory);created={'id':CID,'role':'ocr','nonce':NONCE,'bootId':'fixture','receipt':{'fixture':'SOURCE_ONLY_CREATED_ID'},'expectedImageId':'image'}
   value={'id':CID,'nonce':NONCE,'owner':l.OWNER,'running':kind=='started','pid':123 if kind=='started' else 0,'started':'time' if kind=='started' else '0001-01-01T00:00:00Z','image':'image','devices':[{'DeviceIDs':[l.observer.GPU],'Count':0,'Driver':''}],'exit':0}
   birth={'pid':123,'pgid':123,'startTicks':1};owner=dict(created,birth=birth,image='image',devices=value['devices'],startedAt='time');calls=[];removed=[False]
   if kind!='network-only':
    (p/('container-'+NONCE+'-ocr.json')).write_text(json.dumps(created))
    if kind=='started':(p/('birth-'+NONCE+'-ocr.json')).write_text(json.dumps(owner))
    if kind=='unrecorded-start':value.update(running=True,pid=123,started='time')
   (p/('network-'+NONCE+'.json')).write_text(json.dumps({'id':NID,'nonce':NONCE,'bootId':'fixture'}))
   if changed:value['owner']='UNRELATED_OWNER'
   def exact(_):return {'state':'ABSENT_PROVEN','id':CID} if removed[0] else {'state':'READBACK','value':value,'birth':birth if value['running'] else None}
   def docker(argv,*_):
    calls.append(argv)
    if argv[0]=='stop':value['running']=False
    if argv[0]=='rm':removed[0]=True
    if argv[0]=='wait':return {'fixture':'ORIGINAL_WAIT_SOURCE_ONLY'},b'0'
    if argv[:2]==['network','inspect']:return {},json.dumps({'id':NID,'owner':l.OWNER,'nonce':NONCE,'containers':{CID:{}} if not removed[0] and kind!='network-only' else {}}).encode()
    return {},b''
   original=Path.read_text
   def read(path,*a,**k):return 'fixture' if str(path)=='/proc/sys/kernel/random/boot_id' else original(path,*a,**k)
   with mock.patch.object(l.control,'PHASE_ROOT',directory),mock.patch.object(l,'check_enabled'),mock.patch.object(l.control,'read_private',side_effect=lambda path,*_:Path(path).read_bytes()),mock.patch.object(l,'docker',side_effect=docker),mock.patch.object(l.observer,'exact_container',side_effect=exact),mock.patch.object(l.observer,'pid_presence',return_value={'state':'ORIGINAL_ABSENT_PROC_ROOT'}),mock.patch.object(l.observer,'group_absent',return_value=True),mock.patch.object(l.observer,'snapshot',return_value={'ports':[],'gpuProcesses':[]}),mock.patch.object(Path,'read_text',read):
    r=l.stop({'runtime':{'containers':[{'role':'ocr'}]}},NONCE,1e12)
   return r,calls
 def test_exact_created_never_started_removed_without_invented_wait(self):
  r,c=self.run_case('created');self.assertEqual(r['state'],'OWNED_RESOURCE_SETTLEMENT_PROVEN');self.assertTrue(r['containers'][0]['createdNeverStarted']);self.assertFalse(any(a[0] in ('stop','wait') for a in c));self.assertIn(['rm',CID],c)
 def test_network_only_settled_and_full_id_absence(self):
  r,c=self.run_case('network-only');self.assertEqual(r['state'],'OWNED_RESOURCE_SETTLEMENT_PROVEN');self.assertEqual(r['containers'],[]);self.assertTrue(r['networkAbsence']['absent'])
 def test_started_uses_original_wait_and_full_id_remove(self):
  r,c=self.run_case('started');self.assertEqual(r['state'],'OWNED_RESOURCE_SETTLEMENT_PROVEN');self.assertIn(['wait',CID],c);self.assertIs(type(r['containers'][0]['exitCode']),int)
 def test_missing_birth_or_unrelated_owner_remains_untouched(self):
  for kind,changed in [('unrecorded-start',False),('created',True)]:
   r,c=self.run_case(kind,changed);self.assertEqual(r['state'],'QUARANTINE');self.assertFalse(any(a[0] in ('stop','wait','rm') for a in c));self.assertNotIn(['network','rm',NID],c)
 def test_preflight_exceptions_have_stop_finally(self):
  graph={'image':'exact','rootOwnerEvidence':{'imageId':'image'}};go={'actionDeadlines':{'stop':'2099-01-01T00:00:00+00:00'}}
  for boundary in ('create','start','wait'):
   with mock.patch.object(l,'check_enabled',return_value=(graph,go)),mock.patch.object(l,'record_created',side_effect=RuntimeError('create') if boundary=='create' else None,return_value={'id':CID}),mock.patch.object(l,'start_created',side_effect=RuntimeError('start') if boundary=='start' else None),mock.patch.object(l,'docker',side_effect=RuntimeError('wait') if boundary=='wait' else None),mock.patch.object(l,'stop',return_value={'state':'fixture-settled'}) as stop:
    r=l.preflight(graph,NONCE,1e12);self.assertIsNotNone(r['failure']);stop.assert_called_once()
if __name__=='__main__':unittest.main()
