"""Read-only normal service owner/config/database observation. No key contents."""
import hashlib, json, os
from pathlib import Path
import sqlite3, subprocess

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def proc(pid):
 p=Path('/proc')/str(pid);stat=(p/'stat').read_text().rsplit(')',1)[1].split()
 uid=[int(x) for x in (p/'status').read_text().split('Uid:',1)[1].splitlines()[0].split()]
 return {'pid':pid,'startTicks':stat[19],'pgid':int(stat[2]),'uid':uid[0],'uids':uid,'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cgroupPath':(p/'cgroup').read_text().strip().split('::',1)[-1],'cgroup':(p/'cgroup').read_text().strip(),'gid':int((p/'status').read_text().split('Gid:',1)[1].splitlines()[0].split()[0]),'cmdlineSha256':digest(p/'cmdline'),'exe':os.readlink(p/'exe'),'cwd':os.readlink(p/'cwd'),'cmdline':(p/'cmdline').read_bytes().decode().split('\0')[:-1]}
def observe():
 result=subprocess.run(['systemctl','--user','show','ai-harness.service','--property=MainPID,InvocationID,ActiveState,SubState,FragmentPath,ControlGroup'],capture_output=True,timeout=8)
 if result.returncode!=0:raise RuntimeError('systemctl read failed')
 fields=dict(line.split('=',1) for line in result.stdout.decode().splitlines());pid=int(fields['MainPID']);owner=proc(pid)
 env=dict(x.split(b'=',1) for x in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0') if b'=' in x)
 names=['AI_HARNESS_DATA_DIR','AI_HARNESS_ENGINE_LAUNCHER','AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE','AI_HARNESS_CODEX_ORDINARY_ENTRY_KEY_FILE','AI_HARNESS_CODEX_GENERATION_ACCEPTANCE_FILE','AI_HARNESS_CODEX_GENERATION_ONLY_FILE','AI_HARNESS_CODEX_CURRENT_FRONTIER_FILE','AI_HARNESS_WEB_DIST']
 selected={n:env.get(n.encode(),b'').decode() for n in names}
 unit=Path(fields['FragmentPath']);paths=[unit,Path(owner['exe'])]
 launcher=selected['AI_HARNESS_ENGINE_LAUNCHER'];paths.extend([Path(launcher),Path(launcher).with_name('run-server.sh')])
 ordinary=selected['AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE'];baseline={'present':False}
 if ordinary:
  path=Path(ordinary);baseline={'path':ordinary,'present':path.is_file()}
  if path.is_file():
   envelope=json.loads(path.read_text());body=envelope.get('body',{});q=body.get('qualification',{})
   baseline.update({'approvalSha256':digest(path),'approvalId':body.get('approvalId'),'sourceCommit':body.get('sourceCommit'),'qualificationFiles':{n:{'path':q[n],'present':Path(q[n]).is_file(),'sha256':digest(q[n]) if Path(q[n]).is_file() else None} for n in ['launchPath','settlementPath','protocolAckPath','binaryPath','legacyTransportPath','rawProtocolPath'] if n in q},'binaryVersion':q.get('binaryVersion'),'upstream':q.get('upstream')})
 data=selected['AI_HARNESS_DATA_DIR'];db=Path(data)/'harness.sqlite';connection=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=3)
 try:
  connection.execute('PRAGMA query_only=ON')
  active=connection.execute("SELECT id,session_id,status FROM runs WHERE status IN ('queued','running','cancelling') ORDER BY id").fetchall()
  owners=connection.execute("SELECT e.session_id,e.ownership,e.active_turn_id,s.status FROM h021_session_engines e JOIN sessions s ON s.id=e.session_id WHERE e.active_turn_id IS NOT NULL OR e.ownership!='idle' ORDER BY e.session_id").fetchall()
  retained=connection.execute("SELECT id,status FROM sessions WHERE id LIKE '50d3d298%' ORDER BY id").fetchall()
  projection={}
  if len(retained)==1:
   for table,column in [('sessions','id'),('messages','session_id'),('runs','session_id'),('events','session_id'),('h021_session_engines','session_id')]:
    cursor=connection.execute('SELECT * FROM '+table+' WHERE '+column+'=? ORDER BY rowid',(retained[0][0],));projection[table]={'columns':[v[0] for v in cursor.description],'rows':cursor.fetchall()}
  preserved_sha=hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest() if projection else None
 finally:connection.close()
 assert proc(pid)==owner,'owner changed during observation'
 return {'schema':'h046-read-only-observation-v1','mutation':False,'unit':fields,'owner':owner,'selectedEnvironment':selected,'files':{str(p):{'sha256':digest(p),'uid':p.stat().st_uid,'mode':oct(p.stat().st_mode&0o777)} for p in paths if p.is_file()},'baselineOrdinary':baseline,'database':{'path':str(db),'activeRuns':active,'retainedNonIdleOwners':owners,'originalUser50d3d298':retained,'preservedSessionSha256':preserved_sha,'databaseIdentity':{k:v for k,v in zip(['dev','ino','uid','gid','mode','nlink'],[db.stat().st_dev,db.stat().st_ino,db.stat().st_uid,db.stat().st_gid,db.stat().st_mode&0o777,db.stat().st_nlink])}}}
if __name__=='__main__': print(json.dumps(observe(),sort_keys=True,indent=2))
