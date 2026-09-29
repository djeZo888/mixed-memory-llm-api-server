#!/usr/bin/env python3
"""H032 DEPLOY-FLOW02 exact reviewed app deployment, adapted from the reviewed FLOW01 helper.
Remote operator runs stage, reviews its exact receipt, then activate ROOT-GO.json.
No inference, model control, status restart, policy mutation, or implicit retry.
"""
import datetime, hashlib, json, os, pathlib, re, shutil, sqlite3, stat, subprocess, sys, tarfile, time, urllib.request
P = pathlib.Path('/home/user/.cache/h032-count-update-release')
OLD = pathlib.Path('/opt/ai-harness/releases/h032-deploy-flow02-e9e4f71c53b2caade69c345aadb231f788323a3d/ai-harness')
UNIT = pathlib.Path('/home/user/.config/systemd/user/ai-harness.service')
OLD_UNIT_SHA = 'a9c5bd26ea83867ef706af48d9ac643e6f7e19398cf3258abe43049a961fdc6f'
DATA = pathlib.Path('/home/user/.local/share/ai-harness/harness.sqlite')
POLICY = pathlib.Path('/home/user/.config/ai-harness/h024-owned-acceptance/policy.json')
BACKUP = P / 'backup'
STAGED = P / 'STAGED-READBACK.json'
ACTIVATION = P / 'ACTIVATION.json'
HIST = {'bd71984f-2f90-4375-bca4-6c76730ba224', 'bed0fc3c-910c-4598-bfa6-11cabf637e3f'}
HIST_WORK = {'275de12a-3d63-4aba-be14-5d6dc5a496aa', '0db2129f-f6bd-4ed4-b16b-5d6370ea662d'}
# Normal application close/recovery can update these non-history lane snapshots.
# They are separately checked below; user rows, failures, ownership and events are exact.
VOLATILE = {'h003_image_lane', 'h005_image_ownership', 'gateway_lanes'}
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def call(*a, timeout=60): return subprocess.check_output(a, text=True, timeout=timeout).strip()
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p, v): p.write_text(json.dumps(v, indent=2) + '\n'); p.chmod(0o600)
def db(p=DATA):
    c = sqlite3.connect('file:' + str(p) + '?mode=ro', uri=True); c.row_factory = sqlite3.Row; return c
def rows(c, table):
    assert re.fullmatch(r'[A-Za-z0-9_]+', table)
    return [dict(r) for r in c.execute('select * from ' + table)]
def tables(c): return sorted(r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'") if r[0] not in VOLATILE)
def hashes():
    with db() as c:
        c.execute('BEGIN')
        return {t: hashlib.sha256(json.dumps(sorted(rows(c,t),key=repr),sort_keys=True,separators=(',',':')).encode()).hexdigest() for t in tables(c)}
def tree(p): return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}
def service(name, user=False):
    return call('systemctl', *(['--user'] if user else []), 'show', name, '-p','MainPID','-p','ActiveState','-p','UnitFileState','-p','WorkingDirectory','-p','FragmentPath')
def status_files():
    paths = list(pathlib.Path('/etc/systemd/system/ai-harness-status.service.d').glob('*.conf')) + [pathlib.Path('/etc/systemd/system/ai-harness-status.service')]
    return {str(p):sha(p) for p in paths}
def holds():
    with sqlite3.connect('file:/var/lib/ai-harness-dispatch/state.sqlite?mode=ro',uri=True) as c:
        return sorted([list(r) for r in c.execute('select * from dispatch_holds')],key=repr)
def image(): return call('podman','image','inspect','--format','{{.Id}}|{{index .Labels "org.opencontainers.image.ai-harness.patchset"}}','localhost/sova-codex:0.158.0-h024-release02')
def validate_handoffs(c):
    assert 'h030_handoff_targets' in tables(c), 'existing handoff table missing'
    for target in rows(c,'h030_handoff_targets'):
        run=c.execute('select session_id,status from runs where id=?',(target['run_id'],)).fetchone()
        assert run and run['status'] in ('completed','failed','cancelled','interrupted'), 'handoff target not terminal'
        owner=c.execute('select ownership,active_turn_id from h021_session_engines where session_id=?',(run['session_id'],)).fetchone()
        assert owner and owner['ownership']=='idle' and owner['active_turn_id'] is None, 'handoff target owner not idle'

def settled(allow_known_idle=False):
    with db() as c:
        assert not c.execute("select 1 from runs where status in ('queued','running','cancelling')").fetchone(), 'active run'
        validate_handoffs(c)
        owners = rows(c,'h021_session_engines')
        unsafe = [r for r in owners if r['ownership']!='idle' or r['active_turn_id'] is not None]
        assert len(unsafe)==2 and {r['session_id'] for r in unsafe}==HIST and all(r['ownership']=='uncertain' for r in unsafe), 'new/changed unsettled native owner'
        assert not c.execute("select 1 from h021_gateway_requests where state!='settled'").fetchone(), 'unsettled gateway request'
        assert not c.execute("select 1 from h003_image_jobs where json_extract(data,'$.job.state') not in ('completed','failed','cancelled') or json_extract(data,'$.job.error.code') in ('image_completion_unknown','server_stopped','server_restarted')").fetchone(), 'unsettled/uncertain image job'
        assert tuple(c.execute('select uncertain from h005_image_ownership where id=1').fetchone())==(0,), 'image uncertainty'
        assert c.execute('select state from h003_image_lane where id=1').fetchone()[0] in ('idle','quarantined'), 'active image lane'
    names = call('podman','ps','--all','--format','{{.Names}}').splitlines()
    tasks=[n for n in names if n.startswith('ai-harness-') and n!='ai-harness-searxng']
    if tasks and allow_known_idle:
        assert tasks==['ai-harness-b3061d26150044a0bee427e57934890d'], 'unknown remaining task container'
        info=json.loads(call('podman','inspect',tasks[0]))[0]
        assert info['Id'].startswith('e4f4d659cb63')
        mounts={m['Source'] for m in info['Mounts']}
        assert mounts=={'/home/user/.local/share/ai-harness/workspaces/1467b8f4-342c-45e6-96df-4a6f6c59a41e','/home/user/.local/share/ai-harness/profiles/76db5b44-722c-473e-9b81-c6c89e4bdd02'}
        with db() as c:
            owner=c.execute('select ownership,active_turn_id,workspace_id,engine_kind from h021_session_engines where session_id=?',('76db5b44-722c-473e-9b81-c6c89e4bdd02',)).fetchone()
            assert tuple(owner)==('idle',None,'1467b8f4-342c-45e6-96df-4a6f6c59a41e','minimax'), 'cached owner not idle'
        # Normal application stop closes this exact settled cached engine.
    else:
        assert not tasks, 'remaining task container'

def invariants(base):
    assert sha('/etc/nginx/sites-available/ai-harness.conf')=='0cf275f63b34b42dff6b42258e5b2b04e51401ba92d2ad7b26ca022ae14c54c6', 'maintenance gate changed'
    assert service('ai-harness-status.service')==base['status'], 'status PID/state/release changed'
    assert status_files()==base['statusFiles'], 'status configuration changed'
    assert sha(POLICY)==base['policySha256'], 'acceptance policy/tickets changed'
    assert tree(OLD/'config')==base['config'], 'old live configuration changed'
    assert holds()==base['holds'], 'dispatch holds changed'
    assert image()==base['image'], 'resident image/policy changed'
    for name, expected in base['support'].items():
        assert service(name,name=='ai-harness-searxng.service')==expected, 'support service changed: '+name
def config_changes():
    assert R['configReplacements']==[]
    assert sha(OLD/'config/mimo-candidate.json')=='45b9a590c9b9802408024ca60836b07b37a371a4b23b6cc2ef8cfd4977561c5e'
    assert sha(OLD/'config/active-frontier.json')=='6fac2925b81e0c40154635643a327f8f3149f7211cf8b78a4f321f6d5b09dc22'
    assert sha('/etc/sova-qualification/mimo.json')=='05ad0301dc7b7d614f0400747812079a02c7f4163c506d774d8c7b944d61e83a'
    return []
def verify_release(base):
    for name,h in R['files'].items():
        assert (name.startswith('server/dist/') or name.startswith('web/dist/')) and '..' not in pathlib.PurePosixPath(name).parts
        assert sha(NEW/name)==h, 'compiled file mismatch: '+name
    expected=dict(base['config'])
    for item in config_changes():expected[item['path'][len('config/'):]]=item['sha256']
    assert tree(NEW/'config')==expected, 'new runtime config mismatch'
    expected_deploy=tree(OLD/'deploy')
    for item in R['deployReplacements']:expected_deploy[item['path'][len('deploy/'):]]=item['sha256']
    assert tree(NEW/'deploy')==expected_deploy, 'unexpected native launch policy change'
    policy_names=['config.toml','config-image-jobs.toml','requirements.toml','models.json','browser-mcp.mjs','skills/sova-local-tools/SKILL.md']
    assert hashlib.sha256(b''.join((NEW/'deploy/codex'/n).read_bytes() for n in policy_names)).hexdigest()==R['hostPolicySha256']
    assert sha(NEW/'deploy/codex/models.json')=='75f39aa38c42d99265101686c15e0f3154aacecc325a3fb6c598e0a185a51823'
    assert tree(NEW/'web')==tree(OLD/'web'), 'web changed'
    assert tree(NEW/'server/node_modules')==tree(OLD/'server/node_modules'), 'Linux dependencies changed'
    assert image()==R['image']['imageId']+'|'+R['image']['policySha256']
def preservation(after):
    with db() as current, db(BACKUP/'harness-before.sqlite') as old:
        current.execute('BEGIN'); old.execute('BEGIN')
        before_tables=tables(old); current_tables=tables(current)
        assert 'h030_handoff_targets' in before_tables, 'existing handoff target table missing'
        assert current_tables==before_tables, 'unexpected table set change; no migration authorized'
        assert rows(old,'h030_handoff_targets')==rows(current,'h030_handoff_targets'), 'retained handoff target changed'
        for table in tables(old):
            before=rows(old,table); actual=rows(current,table)
            if after and table=='sessions':
                for row in before:
                    if row['id'] in HIST:
                        found=next(r for r in actual if r['id']==row['id']); assert found['updated_at']>=row['updated_at']
                        row['updated_at']=found['updated_at'];row['status']='interrupted'; context=json.loads(row['context']);context['stale']=True
                        assert json.loads(found['context'])==context;row['context']=found['context']
            if after and table=='quarantined_workspaces':
                for row in before:
                    if row['id'] in HIST_WORK:row['reason']='restart_during_run'
            if table=='events':
                original={(r['session_id'],r['id']):r for r in before}; observed={(r['session_id'],r['id']):r for r in actual}
                assert all(observed.get(k)==v for k,v in original.items()), 'original event changed'
                added=[v for k,v in observed.items() if k not in original]
                if after:
                    assert len(added)==6 and all(v['session_id'] in HIST and v['run_id'] is None for v in added)
                    for sid in HIST: assert sorted(v['type'] for v in added if v['session_id']==sid)==['context','error','state']
                else: assert not added
            else: assert sorted(before,key=repr)==sorted(actual,key=repr), 'retained rows changed: '+table
    return {'allOriginalApplicationRowsAndEventsPreserved':True,'historicalUncertaintyPreserved':True,'normalStartupEvents':6 if after else 0,'volatileLaneTablesSeparatelyChecked':sorted(VOLATILE)}

assert os.getuid()==1000, 'ordinary service user required'
assert len(sys.argv)>=2 and sys.argv[1] in ('stage','activate','readback')
mode=sys.argv[1];R=json.loads((P/'BUILD-RECEIPT.json').read_text());SOURCE=R['sourceHead']
assert SOURCE=='c863d4984f4a75c237b6de97b7ce40b8570fca81'
NEW=pathlib.Path('/opt/ai-harness/releases/h032-count-update-'+SOURCE+'/ai-harness')
BUILD_SHA=sha(P/'BUILD-RECEIPT.json')
if mode=='stage':
    assert len(sys.argv)==2 and not STAGED.exists() and not NEW.parent.exists(), 'existing stage; inspect, do not replay'
    assert sha(UNIT)==OLD_UNIT_SHA and not UNIT.is_symlink()
    app=dict(x.split('=',1) for x in service('ai-harness.service',True).splitlines())
    assert app['ActiveState']=='active' and app['WorkingDirectory']==str(OLD/'server') and app['UnitFileState']=='enabled'
    settled(True); changes=config_changes()
    base={'status':service('ai-harness-status.service'),'statusFiles':status_files(),'policySha256':sha(POLICY),'config':tree(OLD/'config'),'holds':holds(),'image':image(),'dataHashes':hashes(),'support':{n:service(n,n=='ai-harness-searxng.service') for n in ('nginx.service','ai-harness-admin.service','ai-harness-egress.service','ai-harness-searxng.service')}}
    status_state=dict(x.split('=',1) for x in base['status'].splitlines())
    assert status_state['ActiveState']=='active' and int(status_state['MainPID'])>0 and status_state['WorkingDirectory']=='/opt/ai-harness/components/h028-accept01-fc7c121/ai-harness/server' and status_state['UnitFileState']=='enabled'
    archive=P/'app-release.tar.gz';assert sha(archive)==R['archiveSha256']
    call('sudo','-n','mkdir',str(NEW.parent));call('sudo','-n','chown','1000:1000',str(NEW.parent));call('cp','-a',str(OLD),str(NEW))
    assert tree(NEW/'config')==base['config']
    shutil.rmtree(NEW/'server/dist')
    with tarfile.open(archive) as tar:
        names=[]
        for m in tar.getmembers():
            assert m.name.startswith('ai-harness/');m.name=m.name[len('ai-harness/'):]
            assert m.isfile() and (m.name.startswith('server/dist/') or m.name.startswith('web/dist/')) and '..' not in pathlib.PurePosixPath(m.name).parts and m.name in R['files']
            names.append(m.name)
        assert len(names)==len(set(names)) and set(names)==set(R['files']), 'archive/receipt set mismatch'
        tar.extractall(NEW,members=tar.getmembers(),filter='data')
    for item in changes+R['deployReplacements']:
        assert sha(P/item['inputFile'])==item['sha256'];shutil.copy2(P/item['inputFile'],NEW/item['path'])
    save(NEW/'H032-SOURCE-MANIFEST.json',{'source':SOURCE,'sourceHashes':R['sourceHashes'],'buildReceiptSha256':BUILD_SHA})
    candidate=UNIT.read_text().replace(str(OLD),str(NEW));assert str(NEW) in candidate and '--codex-image-jobs-reviewed' not in candidate
    candidate_path=P/'candidate-app.service';candidate_path.write_text(candidate);candidate_path.chmod(0o600)
    verify_release(base);invariants(base);settled(True);assert hashes()==base['dataHashes'] and sha(UNIT)==OLD_UNIT_SHA
    result={'state':'STAGED_ONLY','source':SOURCE,'release':str(NEW),'oldRelease':str(OLD),'buildReceiptSha256':BUILD_SHA,'appUnitSha256':sha(candidate_path),'oldAppUnitSha256':OLD_UNIT_SHA,'configReplacements':changes,'baseline':base,'utc':utc()}
    save(STAGED,result);print(json.dumps({k:v for k,v in result.items() if k!='baseline'}));sys.exit(0)

S=json.loads(STAGED.read_text());assert S['source']==SOURCE and S['release']==str(NEW) and S['buildReceiptSha256']==BUILD_SHA
base=S['baseline'];invariants(base);verify_release(base)
if mode=='activate':
    assert len(sys.argv)==3 and not BACKUP.exists() and not ACTIVATION.exists(), 'one attempt already exists; readback only'
    go=pathlib.Path(sys.argv[2]);st=go.lstat();assert stat.S_ISREG(st.st_mode) and st.st_uid in (0,1000) and not st.st_mode&0o022
    expected={'exactSource':SOURCE,'exactHelperSha256':sha(__file__),'buildReceiptSha256':BUILD_SHA,'stagedReceiptSha256':sha(STAGED),'candidateUnitSha256':S['appUnitSha256'],'configReplacements':S['configReplacements'],'rootUpgradeGo':True,'appOnly':True,'ownersSettled':True,'preserveHistoricalUncertainty':True}
    assert json.loads(go.read_text())==expected, 'exact final root GO required'
    assert sha(UNIT)==OLD_UNIT_SHA and hashes()==base['dataHashes'];settled(True)
    assert call('systemctl','--user','show','ai-harness.service','-p','ActiveState','--value')=='active'
    assert call('systemctl','--user','show','ai-harness.service','-p','WorkingDirectory','--value')==str(OLD/'server')
    BACKUP.mkdir(mode=0o700);shutil.copy2(UNIT,BACKUP/'original.service');shutil.copy2(POLICY,BACKUP/'acceptance-policy.json');shutil.copytree(OLD/'config',BACKUP/'config');shutil.copytree(OLD/'deploy',BACKUP/'deploy')
    with db() as c:
        with sqlite3.connect(BACKUP/'harness-before.sqlite') as target:c.backup(target)
    (BACKUP/'harness-before.sqlite').chmod(0o600)
    receipt={'state':'PRE_STOP','source':SOURCE,'release':str(NEW),'oldRelease':str(OLD),'utc':utc(),'buildReceiptSha256':BUILD_SHA,'helperSha256':sha(__file__),'rootGoSha256':sha(go),'appUnitSha256':S['appUnitSha256'],'configReplacements':S['configReplacements'],'statusUnchanged':True,'imageId':R['image']['imageId'],'codexPolicySha256':R['image']['policySha256']}
    save(ACTIVATION,receipt);preservation(False)
    receipt['state']='STOP_REQUESTED';save(ACTIVATION,receipt);call('systemctl','--user','stop','ai-harness.service')
    state=dict(x.split('=',1) for x in call('systemctl','--user','show','ai-harness.service','-p','ActiveState','-p','Result','-p','ExecMainStatus').splitlines())
    receipt['stopReadback']=state;save(ACTIVATION,receipt);assert state=={'ActiveState':'inactive','Result':'success','ExecMainStatus':'0'}, 'normal stop unconfirmed'
    settled();preservation(False);invariants(base)
    assert not call('ss','-ltnH','sport = :8081') and not call('ss','-ltnH','sport = :8080'), 'app/gateway listener remains'
    assert sha(P/'candidate-app.service')==S['appUnitSha256']
    tmp=UNIT.with_name('ai-harness.service.h032');shutil.copy2(P/'candidate-app.service',tmp);os.replace(tmp,UNIT)
    receipt['state']='UNIT_INSTALLED';save(ACTIVATION,receipt);call('systemctl','--user','daemon-reload')
    receipt['state']='START_REQUESTED';save(ACTIVATION,receipt);call('systemctl','--user','start','ai-harness.service');receipt['state']='HEALTH_UNCONFIRMED';save(ACTIVATION,receipt)
else:
    assert len(sys.argv)==2
    receipt=json.loads(ACTIVATION.read_text());assert receipt['source']==SOURCE and receipt['state'] in ('START_REQUESTED','HEALTH_UNCONFIRMED','APP_STATUS_HEALTH_PASS'), 'no valid readback checkpoint'
assert sha(UNIT)==S['appUnitSha256'];verify_release(base);invariants(base)
app=dict(x.split('=',1) for x in service('ai-harness.service',True).splitlines())
assert app['ActiveState']=='active' and app['WorkingDirectory']==str(NEW/'server') and app['UnitFileState']=='enabled' and int(app['MainPID'])>0
health=None
for attempt in range(12):
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080/api/health',headers={'Host':'10.156.100.61','Origin':'http://10.156.100.61'}),timeout=2) as response:health=json.load(response)
        if health.get('status')=='ok':break
    except Exception:health=None
    time.sleep(1)
assert health and health['status']=='ok' and health['engines']['default']=='minimax'
assert health['engines']['codex']['available'] is True and health['engines']['codex']['imageToolEnabled'] is False
assert health['engines']['codex']['capabilities']['media'] is False and health['engines']['codex']['capabilities']['frontier'] is False
with urllib.request.urlopen('http://10.156.100.61/status',timeout=3) as response:assert response.status==200
for route in ('/','/api/health','/api/sessions/00000000-0000-0000-0000-000000000000/image-jobs/00000000-0000-0000-0000-000000000000/approval-token'):
    try:
        with urllib.request.urlopen('http://10.156.100.61'+route,timeout=3) as response:raise AssertionError('ordinary access unexpectedly open')
    except urllib.error.HTTPError as error:assert error.code==503
settled();receipt['preservation']=preservation(True);invariants(base)
receipt.update(state='APP_STATUS_HEALTH_PASS',completedUtc=utc(),health=health,services={'ai-harness.service':service('ai-harness.service',True),'ai-harness-status.service':service('ai-harness-status.service')},policySha256=sha(POLICY),holdsPreserved=True,acceptanceNotStarted=True)
save(ACTIVATION,receipt);print(json.dumps(receipt))
