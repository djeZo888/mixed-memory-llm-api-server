"""One-off reviewed FHD deployment. Stdin payload contains source, never secrets."""
import hashlib,json,os,pwd,stat,subprocess,sys,urllib.request
from pathlib import Path
sys.path.insert(0,'/data/services/image21-runtime-20260923/source')
from service import Runtime,acquire_lease,storage_io,require,protected_file
BASE=Path('/data/services/image21-fhd-20260923')
SOURCE=Path('/usr/local/lib/llm-server/image-api/scripts/image_api')
CONFIG=Path('/etc/llm-server/image-api.json')
HELPER=Path('/usr/local/lib/llm-server/image-api/examples/generate.py')
OLD_CONFIG='d8d38a8212bb2f040b979f899e74564af541b36a83832b21122f280792b3ec7b'
RUNTIME_CONFIG='4ded6e9261b512d952c5033b0634d4eaba79fa115685635c6307defe78c11d76'
TEXT_IDS=['a2afad49380a592739944f2766f5547687a5cf302badd375bda14fffdb09f75c','a71924b9e7fa4f72c6eeefc243731f59bdc0d951b817de1d32f32dbfd67f450e']
def sha(raw):return hashlib.sha256(raw).hexdigest()
def cmd(args,timeout=30):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 require(p.returncode==0,'deployment_command_failed')
 return p.stdout
def get(route):
 key=protected_file(Path('/data/services/secrets/llm-api-key'),maximum=257).strip().decode('ascii')
 req=urllib.request.Request('http://127.0.0.1:30006'+route,headers={'Authorization':'Bearer '+key})
 with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
def text_state():
 result=[]
 for cid in TEXT_IDS:
  c=json.loads(cmd(['docker','inspect',cid]))[0]
  require(c['Id']==cid and c['State']['Running'],'original_text_not_running')
  result.append({'id':cid,'started_at':c['State']['StartedAt'],'pid':c['State']['Pid']})
 return result
def atomic(path,raw,mode):
 # Protected parents, exclusive same-filesystem temp + fsync + atomic replace.
 for parent in path.parents:
  st=parent.lstat();require(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022,'unprotected_target_parent')
 if path.exists():protected_file(path,maximum=1048576)
 temp=path.with_name('.fhd-'+path.name)
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 try:
  os.fchown(fd,0,0);os.fchmod(fd,mode)
  with os.fdopen(fd,'wb',closefd=False) as out:out.write(raw);out.flush();os.fsync(fd)
 finally:os.close(fd)
 os.replace(temp,path)
 fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 require(protected_file(path,modes={mode},maximum=1048576)==raw,'installed_bytes_mismatch')
payload=json.load(sys.stdin)
r=Runtime()
require(sha(protected_file(Path('/data/services/image21-runtime-20260923/config.json')))==RUNTIME_CONFIG,'runtime_config_changed')
require(set(payload['source'])=={'__init__.py','app.py','backend.py','protocol.py','protection.py','serve.py','uploads.py'},'api_source_set_mismatch')
new_config=payload['qualification'].encode();q=json.loads(new_config)
require(q['limits']=={'max_width':1920,'max_height':1080,'max_pixels':2073600,'native_max_pixels':2088960},'fhd_limits_mismatch')
require([p['size'] for p in q['profiles']]==['1024x1024','1024x576','1216x704','1472x832','1760x992','1920x1080'],'profile_set_mismatch')
require(all(p['operation']=='generation' and p['references']==0 and p['transparent'] is False for p in q['profiles']),'generation_only_required')
require(q['runtime_image_digest']==r.config['image_id'] and q['runtime_revision']==r.config['source_commit'] and q['model_revision']==r.config['checkpoint_revision'],'manifest_pins_mismatch')
files={SOURCE/name:raw.encode() for name,raw in payload['source'].items()}
files[CONFIG]=new_config;files[HELPER]=payload['helper'].encode()
previous={};metadata={}
with acquire_lease(blocking=False):
 r.guards();state=r.state();r.verify_resident(state);r.check_network(state)
 ready=get('/health/ready');require(ready['ready'] and ready['admitting'] and not ready['busy'],'api_not_idle')
 texts=text_state()
 old=protected_file(CONFIG,modes={0o644});require(sha(old)==OLD_CONFIG,'prior_manifest_changed')
 require(json.loads(old)['profiles'][:5]==q['profiles'][:5],'smaller_profiles_changed')
 require(sha(payload['crop_evidence'].encode())==q['profiles'][-1]['evidence_sha256'],'crop_evidence_hash_mismatch')
 for path in files:
  if path.exists():
   previous[path]=protected_file(path,maximum=1048576);st=path.lstat()
   metadata[str(path)]={'sha256':sha(previous[path]),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
  else:
   require(path==HELPER and not path.is_symlink(),'unexpected_missing_source');previous[path]=None
 for name,digest in payload['previous_source_sha256'].items():
  require(sha(previous[SOURCE/name])==digest,'prior_source_changed')
 with r.binding.mounted_guard(storage_io) as guard:
  with storage_io.AnchoredRoot(r.binding.path('services'),guard) as a:a.mkdir(BASE.name,mode=0o700)
  with storage_io.AnchoredRoot(str(BASE),guard) as a:
   a.mkdir('rollback',mode=0o700);a.mkdir('source',mode=0o700)
   for path,raw in previous.items():
    if raw is not None:
     name='config.json' if path==CONFIG else 'example-generate.py' if path==HELPER else path.name
     with a.open('rollback/'+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL) as f:f.write(raw);f.fsync()
   for path,raw in files.items():
    name='config.json' if path==CONFIG else 'example-generate.py' if path==HELPER else path.name
    with a.open('source/'+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL) as f:f.write(raw);f.fsync()
   for name in ['crop_evidence','root_go','root_helper_review']:
    with a.open('crop-evidence.json' if name=='crop_evidence' else name+'.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as f:f.write(payload[name].encode());f.fsync()
   a.atomic_json('rollback/metadata.json',metadata)
   a.atomic_json('preflight.json',{'source_commit':payload['source_commit'],'ready':ready,'text_containers':texts,'runtime_config_sha256':RUNTIME_CONFIG,'backend_container':state['container'],'backend_run_id':state['run_id']})
 r.guards()
# Systemd is never called while the lifecycle lease is held.
cmd(['systemctl','stop','llm-image-api.service'])
with acquire_lease(blocking=False):
 r.guards();r.verify_resident(r.state());r.check_network(r.state())
 require(r.state()['container']==state['container'],'backend_changed_during_stop')
 stopped=cmd(['systemctl','show','llm-image-api.service','-p','ActiveState','-p','MainPID'])
 require('ActiveState=inactive' in stopped and 'MainPID=0' in stopped,'api_not_stopped')
 require(text_state()==texts,'text_identity_changed')
 HELPER.parent.mkdir(mode=0o755,exist_ok=True)
 installed=[]
 try:
  for path,raw in files.items():
   if previous[path] is not None:require(protected_file(path,maximum=1048576)==previous[path],'source_changed_after_snapshot')
   atomic(path,raw,0o755 if path==HELPER else 0o644);installed.append(path)
  cmd(['/data/services/image-api/venv/bin/python','-I','-B','-c',"import sys;sys.path.insert(0,'/usr/local/lib/llm-server/image-api/scripts');from image_api.protocol import qualification,strict_json;from image_api.protection import protected,CONFIG;qualification(strict_json(protected(CONFIG,modes={0o644},maximum=131072)))"])
  account=pwd.getpwnam('user')
  with r.binding.mounted_guard(storage_io) as guard:
   with storage_io.AnchoredRoot(r.binding.path('services'),guard) as a:
    a.mkdir('image-api/examples',mode=0o755)
    a.mkdir('image-api/examples/output',mode=0o700)
   output=Path(r.binding.path('services','image-api/examples/output'))
   require(not output.is_symlink(),'unsafe_output_dir');os.chown(output,account.pw_uid,account.pw_gid);os.chmod(output,0o700)
   with storage_io.AnchoredRoot(str(BASE),guard) as a:
    a.atomic_json('installed.json',{'source_commit':payload['source_commit'],'files':{str(p):sha(raw) for p,raw in files.items()},'limits':q['limits'],'helper_output_owner':{'uid':account.pw_uid,'gid':account.pw_gid},'text_containers':texts,'status':'INSTALLED_API_STOPPED'})
  r.guards()
 except BaseException:
  for path in reversed(installed):
   if previous[path] is None:path.unlink()
   else:atomic(path,previous[path],metadata[str(path)]['mode'])
  raise
print(json.dumps({'status':'INSTALLED_API_STOPPED','source_commit':payload['source_commit'],'manifest_sha256':sha(new_config),'lease':'released','rollback':str(BASE/'rollback')}))
