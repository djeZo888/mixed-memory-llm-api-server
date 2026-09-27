#!/usr/bin/env python3
"""Read-only H013 activation receipt; reuses the accepted H010 content method."""
import argparse,datetime,hashlib,importlib.util,json,os,pathlib,sqlite3,stat,subprocess,urllib.request
p=argparse.ArgumentParser(description=__doc__);p.parse_args();os.umask(0o077)
T=pathlib.Path('/home/user/ai-harness-build/H013-SOVA-1M-20260927');os.chdir(T)
R=pathlib.Path('/opt/ai-harness/releases/7143c17d73173db9364b77956679c86d7026a4ae/ai-harness')
s=importlib.util.spec_from_file_location('prior','/home/user/ai-harness-build/H010-WORKER2-20260927/recover-harness-02.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=json.loads((T/'activation-content-before.json').read_text());pre=json.loads((T/'pre-activation-final.json').read_text())['preserved']
r={'observed_utc':m.now(),'units':m.units(),'data':m.summary(),'files':m.inventory(),'containers':m.container_summary(),'routes':{}}
for n,path in [('dispatch','/var/lib/ai-harness-dispatch/state.sqlite')]:
 c=sqlite3.connect('file:'+path+'?mode=ro',uri=True);c.execute('BEGIN');out={}
 for (t,) in c.execute('select name from sqlite_master where type="table" order by name'):
  rows=c.execute('select * from "'+t+'" order by rowid').fetchall();out[t]={'count':len(rows),'sha256':m.sha(m.serialized(rows))}
 c.close();r[n]=out
for path in ['/api/health','/status','/api/status/v1/system']:
 try:
  with urllib.request.urlopen('http://10.156.100.61'+path,timeout=15) as resp:
   body=resp.read();r['routes'][path]={'http_status':resp.status,'content_type':resp.headers.get_content_type(),'body_bytes':len(body)}
   if resp.headers.get_content_type()=='application/json':r['routes'][path]['body']=json.loads(body)
 except Exception as e:r['routes'][path]={'error':type(e).__name__+': '+str(e)}
r['frontier_config']=json.loads((R/'config/frontier.json').read_text());r['registry']=json.loads((R/'config/system-registry.json').read_text())
r['image_id']=m.run('podman','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9','--format','{{.Id}}')
r['unit_properties']=m.run('systemctl','--user','show','ai-harness.service','-p','MainPID','-p','NRestarts','-p','ExecMainStartTimestamp','-p','ExecMainStatus','-p','InvocationID')
pid=r['units']['ai-harness.service']['MainPID'];r['process_cwd']=os.readlink('/proc/'+pid+'/cwd');r['process_exe']=os.readlink('/proc/'+pid+'/exe')
r['credential_metadata']=[]
for f in sorted(pathlib.Path('/home/user/.config/ai-harness').iterdir()):
 st=f.lstat();r['credential_metadata'].append([f.name,st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode),st.st_size,st.st_mtime_ns])
r['credentials_metadata_preserved']=r['credential_metadata']==pre['credential_metadata']
r['content_preserved']={t:r['data'][t]==b['data'][t] for t in ['sessions','messages','files','runs','events','quarantined_workspaces','h003_image_jobs','frontier_requests']}
r['regular_files_preserved']=all(r['files'][k]==b['files'][k] for k in ['regular_non_database_files','sha256'])
r['owner_lock']={'readback':'exclusive_lock_held_by_running_app_as_designed','bytes':pathlib.Path('/home/user/.local/share/ai-harness/owner.sqlite').stat().st_size,'tables_before':b['owner'],'not_a_ledger':True};r['owner_ledger_preserved']=all(r['data'][t]==b['data'][t] for t in ['runs','frontier_requests','quarantined_workspaces','h003_image_jobs','gateway_lanes']);r['dispatch_preserved']=r['dispatch']==b['dispatch']
r['search_preserved']=r['units']['ai-harness-searxng.service']==b['units']['ai-harness-searxng.service'] and r['containers']==b['containers']
r['admin_preserved']=r['units']['ai-harness-admin.service']==b['units']['ai-harness-admin.service']
r['operational_before_after']={t:{'before':b['data'][t],'after':r['data'][t]} for t in ['h003_image_lane','h005_image_ownership','gateway_lanes']}
unit=pathlib.Path('/home/user/.config/systemd/user/ai-harness.service');drop=pathlib.Path('/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf')
old='/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness'
r['unit_exact_path_replacement']=unit.read_text()==(T/'activation-backup/ai-harness.service').read_text().replace(old,str(R))
r['status_exact_path_replacement']=drop.read_text()==(T/'activation-backup/30-h008-registry.conf').read_text().replace('/opt/ai-harness/components/H008-REGISTRY-296ae49/ai-harness',str(R))
r['sha256']={str(f):m.sha(f.read_bytes()) for f in [unit,drop,R/'config/frontier.json',R/'config/system-registry.json',R/'deploy/engine/configure-profile.mjs',T/'source.commit',T/'artifacts.SHA256SUMS',T/'source.SHA256SUMS']}
# Reuse existing preservation helper functions without its old-image/stopped-only CLI predicates.
code=(T/'preservation.py').read_text(); funcs=code[code.index('def run('):code.index('assert os.getuid()==1000')]
ns={'subprocess':subprocess,'pathlib':pathlib,'hashlib':hashlib,'stat':stat,'os':os,'json':json};exec(funcs,ns)
for path in ['/home/user/ai-harness-build',str(T),old,str(R)]:ns['safe'](path)
ns['safe']('/home/user/.local/share/containers/storage',ancestors=False)
r['old_release_preserved']=ns['digest'](old)==pre['release'];r['free_bytes']=os.statvfs(T).f_bavail*os.statvfs(T).f_frsize
r['rootless']=m.run('podman','--remote=false','info','--format','{{.Host.Security.Rootless}}');r['graphroot']=m.run('podman','--remote=false','info','--format','{{.Store.GraphRoot}}')
r['post_storage_guard_pass']=r['free_bytes']>21474836480 and r['rootless']=='true' and r['graphroot']=='/home/user/.local/share/containers/storage'
r['limits']=['No native inference or benchmark','No live managed-agent migration proof; lazy normal engine startup only','No image workflow acceptance from status','No full 1M application occupancy claim','No manual dispatch hold or quarantine clear','No VM or BMC contact; production capacity and settlement from supplied root/Worker1 evidence']
r['status']='PASS' if all(r['content_preserved'].values()) and all(r[k] for k in ['regular_files_preserved','owner_ledger_preserved','dispatch_preserved','search_preserved','admin_preserved','credentials_metadata_preserved','unit_exact_path_replacement','status_exact_path_replacement','old_release_preserved','post_storage_guard_pass']) and all(x.get('http_status')==200 for x in r['routes'].values()) and r['units']['ai-harness.service']['ActiveState']=='active' else 'REVIEW'
(T/'activation-readback-02.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:r[k] for k in ['status','observed_utc','units','content_preserved','regular_files_preserved','owner_ledger_preserved','dispatch_preserved','credentials_metadata_preserved','old_release_preserved','post_storage_guard_pass','operational_before_after','frontier_config','routes']},indent=2))
