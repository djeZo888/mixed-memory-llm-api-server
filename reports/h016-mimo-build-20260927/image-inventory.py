#!/usr/bin/env python3
"""Hash immutable packaged engine, tools and dependency files; no execution."""
import hashlib,json,os,pathlib,stat,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
roots=['/opt/minimax','/opt/ai-harness','/opt/ai-harness-python','/usr/lib/chromium','/usr/local/bin','/usr/local/lib','/usr/bin','/usr/local/share/ai-harness-patches']
rows={}
for root in roots:
 p=pathlib.Path(root)
 if not p.exists():continue
 for f in sorted([p,*p.rglob('*')]):
  s=f.lstat()
  if stat.S_ISLNK(s.st_mode):row=['link',os.readlink(f)]
  elif stat.S_ISREG(s.st_mode):
   h=hashlib.sha256()
   with f.open('rb') as stream:
    for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
   row=['file',h.hexdigest(),s.st_size]
  else:continue
  rows[str(f)]=row+[stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid]
print(json.dumps(rows,sort_keys=True,separators=(',',':')))
