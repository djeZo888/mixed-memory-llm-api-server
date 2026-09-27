import pathlib,json,base64,hashlib,subprocess
T=pathlib.Path(__file__).resolve().parents[1];plan=json.load(open(T/'LAST-INACTIVE-STAGE.json'));files=[]
for f in plan['files']:
 if f['action']=='STAGE_INACTIVE_ONLY_NO_UNIT_INSTALL':
  raw=pathlib.Path(f['source']).read_bytes();assert hashlib.sha256(raw).hexdigest()==f['sha256'];files.append({**f,'bytes':base64.b64encode(raw).decode()})
code='import pathlib,json,base64,hashlib,os,importlib.util,datetime\nfiles='+repr(files)+'\nretained='+repr([f for f in plan['files'] if f['action'].startswith('RETAIN')])+'\n'+'''
p='/data/services/mimo-h016-20260927/source/owner.py';s=importlib.util.spec_from_file_location('ordinary',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);h=o.setup();P=pathlib.Path;B=P('/data/build/H016-20260927/worker1-final13-long')
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();proof={};differences=[]
 for f in retained:
  actual=hashlib.sha256(o.protected(f['destination'])).hexdigest();proof[f['destination']]=actual
  if actual!=f['sha256']:differences.append({'path':f['destination'],'expected':f['sha256'],'actual':actual})
 if differences:
  print(json.dumps({'status':'INACTIVE_STAGE_REFUSED_RETAINED_SOURCE_DIFFERENCE','differences':differences,'mutations':False}));raise SystemExit(0)
 if B.exists():
  present=sorted(p.name for p in B.iterdir());o.require(all(p in {P(f['destination']).name for f in files} for p in present),'unexpected_inactive_namespace')
  for f in files:
   p=P(f['destination'])
   if p.exists():o.require(hashlib.sha256(o.protected(p)).hexdigest()==f['sha256'],'existing_stage_changed')
 else:
  with h.AnchoredRoot('/data/build',g) as a:a.mkdir('H016-20260927/worker1-final13-long')
 with h.AnchoredRoot(str(B),g) as a:
  for f in files:
   p=P(f['destination'])
   if not p.exists():
    with a.open(p.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as out:out.write(base64.b64decode(f['bytes']))
   proof[str(p)]=hashlib.sha256(o.protected(p)).hexdigest()
 h.s.root_payload_guard();print(json.dumps({'status':'STAGED_INACTIVE_NO_GO_NO_UNIT_INSTALL_NO_DISPATCH','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_pins':proof,'stage':str(B),'source_closure':'retained dependencies verified;4 staged reviewed files','root_go_created':False,'unit_installed':False,'dispatched':False},indent=2))
'''
(T/'private/last-stage-remote.py').write_text(code);r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=20)
(T/'private/last-stage-readback.json').write_text(r.stdout);(T/'private/last-stage.stderr').write_text(r.stderr);print(r.stdout);print(r.stderr)
