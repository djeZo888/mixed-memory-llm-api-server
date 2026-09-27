import json,pathlib,subprocess,hashlib
T=pathlib.Path(__file__).resolve().parents[1]
owner=(T/'repo/scripts/runtime/mimo/owner.py').read_text()
code='import types,sys,json,pathlib,hashlib,subprocess,os\no=types.ModuleType("approved_owner");exec('+repr(owner)+',o.__dict__)\nh=o.setup()\n'+'''
def emit(k,v):print(json.dumps({'key':k,'value':v}),flush=True)
def show(unit):
 return dict(x.split('=',1) for x in o.run(['systemctl','show',unit,'-p','MainPID,ControlPID,InvocationID,ActiveState,SubState,Result,ExecMainStatus,ControlGroup,ExecMainStartTimestamp,ExecMainExitTimestamp'],4).splitlines())
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard()
 pair=o.read('/data/logs/H016-20260927/worker1-affinity14/PAIR.json');own=o.read('/data/logs/H016-20260927/worker1-r12-spread4/OWNER.json')
 emit('controller',show('h016-affinity14-20260927.service'));emit('first_unit',show('h016-mimo-profile-20260927-r12-spread4.service'));emit('pair',pair);emit('owner',own)
 emit('glm_unit',show(o.GLM_UNIT));emit('glm_config',o.read(o.GLM_BASE/'config.json'));emit('glm_state',o.read(o.GLM_BASE/'state.json'))
 emit('glm_pins',{n:hashlib.sha256(o.protected(o.GLM_BASE/n)).hexdigest() for n in ('config.json','source/owner.py')})
 emit('hardware_latch',o.latch(h,o.BOOT.read_text().strip()))
 emit('control_closure',{str(pathlib.Path(v.__file__).with_suffix('.py') if v.__file__.endswith('.pyc') else pathlib.Path(v.__file__)):hashlib.sha256(o.protected(pathlib.Path(v.__file__).with_suffix('.py') if v.__file__.endswith('.pyc') else pathlib.Path(v.__file__))).hexdigest() for v in list(sys.modules.values()) if getattr(v,'__file__',None) and '/usr/local/lib/llm-server/control-api/' in v.__file__})
 emit('guard_registration',h.s.read_registration());emit('boot',o.BOOT.read_text().strip());emit('memory',o.memory())
 emit('gpu',o.run(['nvidia-smi','--query-gpu=uuid,name,memory.total,memory.used,memory.free,temperature.gpu','--format=csv,noheader,nounits'],3));emit('gpu_apps',o.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader,nounits'],3))
 emit('services',o.run(['systemctl','list-units','--all','--no-pager','--plain','h016*','llm*'],4))
 emit('existing_mimo',{'exists':o.BASE.exists(),'files':sorted(str(x.relative_to(o.BASE)) for x in o.BASE.rglob('*')) if o.BASE.exists() else []})
 emit('containers',o.run(['docker','ps','-a','--no-trunc','--format','{{.ID}} {{.Names}} {{.Status}}'],4))
 h.s.root_payload_guard()
'''
p=(T/'repo/reports/h016-production-prep16-20260927/STAGE-MAP.json');mapping=json.loads(p.read_text())
code+='\n'+"emit('node_comparison', [{**f,'actual_sha256':hashlib.sha256(o.protected(f['destination'])).hexdigest() if pathlib.Path(f['destination']).exists() else None} for f in "+repr(mapping['files'])+"])\n"
(T/'private/preflight-remote.py').write_text(code)
r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=45)
(T/'private/preflight.raw.jsonl').write_text(r.stdout);(T/'private/preflight.stderr').write_text(r.stderr)
v={j['key']:j['value'] for j in map(json.loads,r.stdout.splitlines())};(T/'private/preflight.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({'returncode':r.returncode,'stderr':r.stderr[-1000:],**{k:v.get(k) for k in ['controller','first_unit','pair','glm_unit','glm_pins','existing_mimo','services','gpu','memory']},'owner_status':v.get('owner',{}).get('status'),'node_differences':[f for f in v.get('node_comparison',[]) if f['sha256']!=f['actual_sha256']]},indent=2))
