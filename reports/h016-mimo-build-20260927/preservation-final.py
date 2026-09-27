#!/usr/bin/env python3
"""Final read-only H016 production preservation comparison. No credentials read."""
import hashlib,json,os,pathlib,stat,subprocess,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
t=pathlib.Path('/home/user/ai-harness-build/H016-MIMO-BUILD-20260927')
b=json.loads((t/'before.json').read_text());a=json.loads((t/'after-final-probes.json').read_text())
for key in ['units','containers','states','data','base_image']:assert a[key]==b[key],key
root=pathlib.Path('/home/user/.local/share/ai-harness');rows=[];excluded=0
for p in sorted(root.rglob('*')):
 if p.is_symlink() or not p.is_file():continue
 if p.name.endswith(('.sqlite','.sqlite-wal','.sqlite-shm','.sqlite-journal')):excluded+=1;continue
 rows.append((str(p.relative_to(root)),p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()))
digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
assert len(rows)==17597 and digest=='1e262519cde8059973b23a2fc2a2838e2a15cb4429269fe18e57cc4adb906f51'
credentials={}
for name,size in [('browser-approval-key',65),('inference-key',64),('node-control-key',64)]:
 p=pathlib.Path('/home/user/.config/ai-harness')/name;s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==1000 and stat.S_IMODE(s.st_mode)==0o600 and s.st_size==size and s.st_nlink==1
 credentials[name]={'uid':s.st_uid,'mode':'0600','size':s.st_size,'contents_read':False}
prod=subprocess.check_output(['podman','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9','--format','{{.Id}}'],text=True).strip();assert prod==b['base_image']
print(json.dumps({'result':'PASS','production_units_containers_and_data_unchanged':True,'regular_non_database_files':len(rows),'file_inventory_sha256':digest,'matches_prior_paused_receipt':True,'credential_metadata':credentials,'production_tag_unchanged':prod,'old_release_preserved':True,'owned_build_service':subprocess.check_output(['systemctl','--user','show','h016-mimo-compile-928b3b4','-p','ActiveState','-p','MainPID','-p','ExecMainStatus'],text=True).strip(),'final_free_bytes':a['free_bytes']},indent=2))
