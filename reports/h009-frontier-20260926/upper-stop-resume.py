#!/usr/bin/env python3
"""H009 exact upper stop after ROOT-STOP-GO; no backend operation or data restore."""
import argparse,datetime,hashlib,json,os,pathlib,shutil,sqlite3,stat,subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--resume-old',action='store_true');a=p.parse_args()
assert sum([a.execute,a.dry_run,a.resume_old])==1, 'select --dry-run, --execute or --resume-old'
assert os.getuid()==1000
os.umask(0o077)
TASK=pathlib.Path('/home/user/ai-harness-build/H009-FRONTIER-20260926');DATA=pathlib.Path('/home/user/.local/share/ai-harness')
for path in [pathlib.Path('/home/user'),TASK.parent,TASK,DATA]:
 s=path.lstat();assert path.resolve()==path and stat.S_ISDIR(s.st_mode) and s.st_uid==1000 and not s.st_mode&0o022
space=os.statvfs(TASK);assert space.f_bavail*space.f_frsize>21474836480
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def unit(name,system=False):
 args=['systemctl']+([] if system else ['--user'])+['show',name,'-p','MainPID','-p','ActiveState','-p','WorkingDirectory'];return dict(l.split('=',1) for l in subprocess.check_output(args,text=True).splitlines() if '=' in l)
def data_state(path):
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as c:
  out={}
  for table in ['sessions','messages','files','quarantined_workspaces','h003_image_jobs','h003_image_lane','h005_image_ownership','runs']:
   rows=c.execute('SELECT * FROM '+table).fetchall();out[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
   if table in ['h003_image_lane','h005_image_ownership']:out[table]['rows']=rows
  out['activeRuns']=c.execute("SELECT count(*) FROM runs WHERE status IN ('queued','running','cancelling')").fetchone()[0]
  out['activeImageJobs']=sum(json.loads(r[0])['job']['state'] in ['queued','running','saving','awaiting_approval'] for r in c.execute('SELECT data FROM h003_image_jobs'))
  return out
if a.resume_old:
 assert hashlib.sha256(pathlib.Path('/home/user/.config/systemd/user/ai-harness.service').read_bytes()).hexdigest()=='a2555938623fbde672152b4e7b552f21faae8f208fb7acf90c0ec9a7c4c8b6a7'
 assert subprocess.check_output(['podman','--remote=false','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9','--format','{{.Id}}'],text=True).strip()=='f957fd7149295c3cca031814bcd1c13add31dfd651ac219520998ffe31b81c29'
 old_state=data_state(DATA/'harness.sqlite')
 subprocess.run(['systemctl','--user','start','ai-harness-searxng.service','ai-harness.service'],check=True,timeout=90)
 units={u:unit(u) for u in ['ai-harness.service','ai-harness-searxng.service']};assert all(v['ActiveState']=='active' for v in units.values())
 for route in ['/api/health','/status']:subprocess.run(['curl','--fail','--silent','--show-error','--max-time','10','--output','/dev/null','http://10.156.100.61'+route],check=True)
 result={'status':'OLD_UPPERS_RESUMED','utc':now(),'before':old_state,'after':data_state(DATA/'harness.sqlite'),'units':units,'noOldDataRestore':True}
 (TASK/'UPPER-RESUME-01.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit
before={'utc':now(),'data':data_state(DATA/'harness.sqlite'),'units':{u:unit(u) for u in ['ai-harness.service','ai-harness-searxng.service']},'components':{u:unit(u,True) for u in ['ai-harness-status.service','ai-harness-admin.service']}}
assert before['data']['activeRuns']==0 and before['data']['activeImageJobs']==0,'active user work: do not interrupt'
containers=json.loads(subprocess.check_output(['podman','--remote=false','ps','--format','json'],text=True));assert all(c.get('Names')==['ai-harness-searxng'] for c in containers),'unexpected active native owner'
before['nativeEngineContainers']=0
if a.dry_run:print(json.dumps({'mode':'DRY_RUN','before':before,'actions':['SQLite-consistent private backup','stop exactly two upper user units','verify settled; preserve other components/data']},indent=2));raise SystemExit
backup=TASK/'before-upper-stop-01.private';assert not backup.exists();backup.mkdir(mode=0o700)
# All SQLite databases use backup API. SHM/WAL are transient, never raw-copied or
# treated as stable backup identities. Preserve other files and symlinks as-is.
count=0
for source in DATA.rglob('*'):
 rel=source.relative_to(DATA);dest=backup/'data'/rel
 if source.is_symlink():dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(os.readlink(source));continue
 if source.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
 if source.name.endswith(('-shm','-wal')):continue
 dest.parent.mkdir(parents=True,exist_ok=True)
 with source.open('rb') as stream:sqlite_header=stream.read(16)==b'SQLite format 3\0'
 if sqlite_header:
  with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src,sqlite3.connect(dest) as dst:
   src.backup(dst);assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  count+=1
 else:shutil.copy2(source,dest,follow_symlinks=False)
shutil.copy2('/home/user/.config/systemd/user/ai-harness.service',backup/'ai-harness.service')
(backup/'before.json').write_text(json.dumps(before,indent=2)+'\n')
# Refuse rather than interrupt a newer user request/change during backup.
assert data_state(DATA/'harness.sqlite')==before['data'],'user state changed during backup; preserve and refresh later'
subprocess.run(['systemctl','--user','stop','ai-harness.service','ai-harness-searxng.service'],check=True,timeout=90)
after={u:unit(u) for u in ['ai-harness.service','ai-harness-searxng.service']};assert all(v['ActiveState']=='inactive' and v['MainPID']=='0' for v in after.values())
components={u:unit(u,True) for u in before['components']};assert components==before['components'],'status/admin changed'
assert not json.loads(subprocess.check_output(['podman','--remote=false','ps','--format','json'],text=True)),'remaining owner after stop'
result={'status':'UPPERS_STOPPED','utc':now(),'before':before,'after':after,'components':components,'dataAfter':data_state(DATA/'harness.sqlite'),'backup':str(backup),'consistentSQLiteSnapshots':count,'noOldDataRestore':True,'noAiVmContact':True}
(TASK/'UPPER-STOP-01.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
