"""Bounded read-only inventory of one approved release's Linux dependencies."""
import hashlib, json, os
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(release):
 release=Path(release)
 if not release.is_absolute() or release.resolve()!=release or release.parent!=Path('/opt/ai-harness/releases'):raise ValueError('canonical immutable release required')
 result={}
 for part in ['server','web']:
  package=release/'ai-harness'/part;deps=package/'node_modules';target=deps.resolve()
  if not target.is_dir() or not target.is_relative_to('/opt/ai-harness/releases'):raise ValueError('unapproved dependency cache')
  graph={}
  for p in sorted(target.rglob('*')):
   if p.is_symlink():
    if not p.resolve().is_relative_to(target):raise ValueError('dependency symlink escapes tree')
    graph[str(p.relative_to(target))]={'symlink':os.readlink(p)}
   elif p.is_file():
    st=p.stat()
    if st.st_mode&0o022 or st.st_uid not in (0,1000):raise ValueError('mutable dependency bytes')
    graph[str(p.relative_to(target))]={'sha256':sha(p),'mode':st.st_mode&0o777,'uid':st.st_uid}
  result[part]={'requestedPath':str(deps),'canonicalPath':str(target),'packageSha256':sha(package/'package.json'),'packageLockSha256':sha(package/'package-lock.json'),'treeSha256':hashlib.sha256(json.dumps(graph,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'entries':len(graph),'files':graph}
 return result
if __name__=='__main__':
 import sys
 print(json.dumps(inventory(sys.argv[1]),sort_keys=True,indent=2))
