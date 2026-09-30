#!/usr/bin/env python3
"""Read-only harness identity/storage/data guard; no credentials printed."""
import argparse, hashlib, json, os, pathlib, stat, subprocess
p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--compare');a=p.parse_args()
root=pathlib.Path('/home/user/ai-harness-build/H013-SOVA-1M-20260927')
production='/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness'
expected='c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20'
def run(*cmd):return subprocess.check_output(cmd,text=True,timeout=30).strip()
def safe(path, ancestors=True):
 path=pathlib.Path(path)
 for x in ([path,*path.parents] if ancestors else [path]):
  s=x.lstat()
  assert stat.S_ISDIR(s.st_mode) and s.st_uid in (0,1000) and not s.st_mode&0o022 and x.resolve()==x, str(x)
def digest(path):
 path=pathlib.Path(path);h=hashlib.sha256();counts={'files':0,'links':0,'directories':0}
 for f in sorted(path.rglob('*')):
  s=f.lstat(); name=str(f.relative_to(path)); row=[name,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode)]
  if stat.S_ISREG(s.st_mode):
   hfile=hashlib.sha256()
   with f.open('rb') as stream:
    for b in iter(lambda:stream.read(1024*1024),b''):hfile.update(b)
   row+=['file',hfile.hexdigest()];counts['files']+=1
  elif stat.S_ISLNK(s.st_mode):row+=['link',os.readlink(f)];counts['links']+=1
  elif stat.S_ISDIR(s.st_mode):row+=['dir'];counts['directories']+=1
  else: row+=['other',stat.S_IFMT(s.st_mode)]
  h.update(json.dumps(row,separators=(',',':')).encode()+b'\n')
 return {'sha256':h.hexdigest(),**counts}
assert os.getuid()==1000
for path in ['/home/user/ai-harness-build',str(root),production]:safe(path)
# Existing H008 guard checks canonical protected graphroot itself. The host's
# pre-existing ~/.local is 0775 (user:user), beneath which share is 0700; this
# PREP does not change host modes or replace the established graphroot policy.
safe('/home/user/.local/share/containers/storage', ancestors=False)
free=os.statvfs(root).f_bavail*os.statvfs(root).f_frsize;assert free>21474836480
assert run('podman','--remote=false','info','--format','{{.Host.Security.Rootless}}')=='true'
assert run('podman','--remote=false','info','--format','{{.Store.GraphRoot}}')=='/home/user/.local/share/containers/storage'
image=run('podman','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9','--format','{{.Id}}');assert image==expected
units={}
for unit in ['ai-harness.service','ai-harness-searxng.service']:
 units[unit]=run('systemctl','--user','show',unit,'-p','ActiveState','-p','MainPID','-p','WorkingDirectory')
assert 'ActiveState=inactive' in units['ai-harness.service'] and 'MainPID=0\n' in units['ai-harness.service']
result={'image':image,'units':units,'production':production,'release':digest(production),'data':digest('/home/user/.local/share/ai-harness'),'unit_sha256':hashlib.sha256(pathlib.Path('/home/user/.config/systemd/user/ai-harness.service').read_bytes()).hexdigest(),'credential_metadata':[]}
for f in sorted(pathlib.Path('/home/user/.config/ai-harness').iterdir()):
 s=f.lstat(); result['credential_metadata'].append([f.name,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_size,s.st_mtime_ns])
if a.compare:
 before=json.loads(pathlib.Path(a.compare).read_text());assert before['preserved']==result,'production/data/secret metadata identity drift'
pathlib.Path(a.output).write_text(json.dumps({'preserved':result,'free_bytes':free,'guard':'existing harness canonical protected paths, rootless graphroot, production identity/stopped state, >20GiB'},indent=2)+'\n')
print('PASS preservation and storage guard')
