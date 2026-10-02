"""Isolated-mode imports of exact protected, hashed source bytes; never sys.path."""
import hashlib,importlib.abc,importlib.util,json,os,re,stat,sys
from pathlib import Path
class TrustError(ValueError):pass

def protected_bytes(path,uid,cap=1048576):
 p=Path(path)
 if not p.is_absolute() or '..' in p.parts or str(p)!=os.path.realpath(p):raise TrustError('canonical_source_path')
 descriptors=[];fd=None
 try:
  d=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);descriptors.append(d)
  for part in p.parts[1:-1]:
   d=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=d);descriptors.append(d);s=os.fstat(d)
   if s.st_uid not in (0,uid) or s.st_mode&0o022:raise TrustError('protected_source_parent')
  fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=d);a=os.fstat(fd)
  if not stat.S_ISREG(a.st_mode) or a.st_uid!=uid or a.st_nlink!=1 or a.st_mode&0o022 or a.st_size>cap:raise TrustError('protected_source_uid_mode')
  raw=os.read(fd,cap+1);z=os.fstat(fd);q=os.stat(p.name,dir_fd=d,follow_symlinks=False)
  fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  if fields(a)!=fields(z) or (q.st_dev,q.st_ino)!=(a.st_dev,a.st_ino) or len(raw)>cap:raise TrustError('source_changed')
  return raw
 finally:
  if fd is not None:os.close(fd)
  for d in reversed(descriptors):os.close(d)

class SourceLoader(importlib.abc.Loader):
 def __init__(self,path,raw):self.path,self.raw=path,raw
 def create_module(self,spec):return None
 def exec_module(self,module):
  module.__file__=str(self.path);exec(compile(self.raw,str(self.path),'exec'),module.__dict__)
class TrustedFinder(importlib.abc.MetaPathFinder):
 def __init__(self,root,manifest,uid):
  self.root=Path(root);self.uid=uid;self.mapping={}
  if not isinstance(manifest,dict) or set(manifest) not in ({'schema','modules'},{'schema','modules','inputs'}) or manifest['schema']!='h044-protected-imports-v1' or not isinstance(manifest['modules'],dict):raise TrustError('manifest_schema')
  for name,s in manifest['modules'].items():
   if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name) or not isinstance(s,dict) or set(s)!={'path','sha256','bytes'}:raise TrustError('module_record')
   rel=Path(s['path'])
   if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.suffix!='.py' or not re.fullmatch('[a-f0-9]{64}',s['sha256']) or type(s['bytes']) is not int:raise TrustError('module_path_hash')
   self.mapping[name]=s
  self.inputs=manifest.get('inputs',{})
  if not isinstance(self.inputs,dict):raise TrustError('input_manifest')
  for name,s in self.inputs.items():
   if name not in ('runtime-argv-interpretation.json','runtime-argv-ocr.json') or set(s)!={'path','sha256','bytes'} or s['path']!=name:raise TrustError('input_path')
   base=self.root if str(self.root).startswith('/opt/') else self.root.parent/'output'
   raw=protected_bytes(base/name,self.uid)
   if len(raw)!=s['bytes'] or hashlib.sha256(raw).hexdigest()!=s['sha256']:raise TrustError('input_hash')
  # Validate the whole graph before installing even one finder/module.
  for name in self.mapping:self.source(name)
 def source(self,name):
  s=self.mapping[name];path=self.root/s['path'];raw=protected_bytes(path,self.uid)
  if len(raw)!=s['bytes'] or hashlib.sha256(raw).hexdigest()!=s['sha256']:raise TrustError('source_hash')
  return path,raw
 def find_spec(self,fullname,path=None,target=None):
  if fullname not in self.mapping:return None
  source,raw=self.source(fullname)
  return importlib.util.spec_from_loader(fullname,SourceLoader(source,raw),origin=str(source))

def install(root,manifest,uid):
 finder=TrustedFinder(root,manifest,uid)
 for name in finder.mapping:
  loaded=sys.modules.get(name)
  if loaded is not None and Path(getattr(loaded,'__file__',''))!=finder.root/finder.mapping[name]['path']:raise TrustError('foreign_loaded_module')
 sys.meta_path.insert(0,finder);return finder
