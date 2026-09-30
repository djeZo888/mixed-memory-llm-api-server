#!/usr/bin/env python3
"""Task-only exact-content reverse migration. Default is read-only dry-run."""
import argparse, hashlib, json, os, pathlib, stat, tempfile
OLD='ac773137a850439b9109bc22080071d46d60b8758ad9660d15981f7a7c761dfe'
# Complete candidate digest; keep explicit identity rather than accepting any 1M text.
NEW='49b3b110242cd89741855b33653c9596f31a23cc064fafa61035b6afaee06dd5'
def migration(root, apply=False):
 root=pathlib.Path(root)
 assert root.is_absolute() and root.resolve()==root
 def directory(p):
  s=p.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode&0o022 and not p.is_symlink(), 'unsafe profile directory'
 directory(root)
 planned=[];already=0
 for current, dirs, files in os.walk(root,followlinks=False):
  current=pathlib.Path(current);directory(current)
  for d in dirs:directory(current/d)
  if current.name!='frontier' or current.parent.name!='agents' or current.parent.parent.name!='state':continue
  assert 'agent.md' in files,'missing managed agent'
  p=current/'agent.md';s=p.lstat()
  assert stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and not s.st_mode&0o077,'unsafe managed file'
  raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest()
  if sha==OLD:already+=1;continue
  assert sha==NEW,'custom frontier content preserved; stop for review'
  old=raw.replace(b'contextWindow: 1048576',b'contextWindow: 480000')
  assert hashlib.sha256(old).hexdigest()==OLD
  planned.append((p,raw,old,s.st_ino,s.st_dev))
 # Validate every profile before the first write; recheck each exact target.
 if apply:
  for p,raw,old,ino,dev in planned:
   directory(p.parent);s=p.lstat()
   assert s.st_ino==ino and s.st_dev==dev and s.st_nlink==1 and s.st_uid==os.getuid() and not s.st_mode&0o077 and p.read_bytes()==raw,'profile changed; stop'
   fd,name=tempfile.mkstemp(prefix='.h013-rollback-',dir=p.parent)
   try:
    with os.fdopen(fd,'wb') as f:f.write(old);f.flush();os.fsync(f.fileno())
    os.replace(name,p)
   finally:
    if os.path.exists(name):os.unlink(name)
 return {'mode':'apply' if apply else 'dry-run','exact_1m_to_480k':len(planned),'already_480k':already,'data_restore':False}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('profiles_root');p.add_argument('--apply',action='store_true');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
 if a.apply and a.dry_run:p.error('choose --apply or --dry-run')
 print(json.dumps(migration(a.profiles_root,a.apply)))
