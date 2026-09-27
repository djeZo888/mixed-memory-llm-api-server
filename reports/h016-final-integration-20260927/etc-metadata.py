#!/usr/bin/env python3
"""Private metadata-only snapshot of protected credential tree; no content reads."""
import json,pathlib,stat,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
p=pathlib.Path('/etc/ai-harness');s=p.lstat()
assert stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o700
rows=[]
for q in [p,*sorted(p.rglob('*'))]:
 s=q.lstat();rows.append([str(q),s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns])
print(json.dumps(rows,separators=(',',':')))
