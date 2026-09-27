import pathlib,json,hashlib,base64,subprocess
T=pathlib.Path(__file__).resolve().parents[1];R=T/'repo';sha=lambda b:hashlib.sha256(b).hexdigest()
pre=json.load(open(T/'private/preflight.json'));mp=json.load(open(R/'reports/h016-production-prep16-20260927/STAGE-MAP.json'));m=json.load(open(R/'reports/h016-production-prep16-20260927/ORDINARY-MANIFEST.template.json'))
assert sha((R/'reports/h016-production-prep16-20260927/STAGE-MAP.json').read_bytes()).startswith('30c4a551')
assert sha((R/'reports/h016-production-prep16-20260927/ORDINARY-MANIFEST.template.json').read_bytes()).startswith('214cb798')
m['glm_preserved_sha256']=pre['glm_pins'];m['source_sha256'].update(pre['control_closure'])
files=[];before={f['destination']:f['actual_sha256'] for f in pre['node_comparison']}
for f in mp['files']+mp['unit_installation']:
 b=(R/f['source']).read_bytes();assert sha(b)==f['sha256'];files.append({**f,'bytes':base64.b64encode(b).decode(),'before_sha256':before.get(f['destination'])})
r9=json.load(open(T.parent/'H016-R9-TERMINAL-15-20260927/private/r9-checkpoint/R9-READ-ONCE.json'))
receipts={}
for dest,d in m['qualification_sha256'].items():
 b=r9['files'][pathlib.Path(dest).name]['text'].encode();assert sha(b)==d;receipts[dest]=base64.b64encode(b).decode()
cutoff='''import importlib.util,json,datetime,pathlib,subprocess
p='/data/services/mimo-h016-20260927/source/owner.py'
s=importlib.util.spec_from_file_location('ordinary',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
h=o.setup();m=o.read(o.BASE/'manifest.json');state=o.read(o.BASE/'state.json')
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before':state,'action':'READY_NO_STOP'}
if state.get('status')!='RUNNING':
 r['action']='NORMAL_STOP_AT_READINESS_CUTOFF';r['stop_rc']=subprocess.run(['systemctl','stop',o.UNIT],timeout=50).returncode;r['after']=o.read(o.BASE/'state.json')
with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot('/data/build/H016-20260927/worker1-deploy17',g) as a:
 h.s.root_payload_guard();a.atomic_json('CUTOFF.json',r);h.s.root_payload_guard()
'''
header='import types,sys,json,pathlib,hashlib,subprocess,os,stat,time,datetime,base64\no=types.ModuleType("approved_owner");exec('+repr((R/'scripts/runtime/mimo/owner.py').read_text())+',o.__dict__)\nh=o.setup()\n'
for k,v in [('m',m),('files',files),('receipts',receipts),('guardpins',pre['control_closure']),('cutoff_source',cutoff)]:header+=k+'='+repr(v)+'\n'
code=header+(T/'private/deploy_remote_body.py').read_text();compile(code,'deploy17','exec');(T/'private/deploy-remote.py').write_text(code)
(T/'private/manifest-final.json').write_text(json.dumps(m,indent=2)+'\n')
r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=120)
(T/'private/deploy.raw.jsonl').write_text(r.stdout);(T/'private/deploy.stderr').write_text(r.stderr)
print(json.dumps({'rc':r.returncode,'stderr':r.stderr[-1500:],'events':[json.loads(l) for l in r.stdout.splitlines()]},indent=2))
