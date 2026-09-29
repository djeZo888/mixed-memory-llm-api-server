#!/usr/bin/env python3
"""H031 exact one-shot activation helper; private staged inputs are never in Git.

Each phase is invoked once by W1 after inspecting the preceding receipt.
No implicit retries, repeated MiMo stop, direct native stop, baseline restore or inference.
"""
import base64, datetime, hashlib, importlib.util, json, os, stat, subprocess, sys, time
from pathlib import Path
STAGE=Path('/data/build/h031-source02-20260929')
M=Path('/data/services/mimo-h016-20260927')
I=Path('/data/services/image21-runtime-20260923')
OLD='1cc1ee45eca7c578d9b84411d75c1cfd37c914edd7b5097389ee2f19fae23098'
NEW='687aa9e57f59103b39f6c4aefcf51d5ffc0bb9cf697fb443747d3757c332b090'
PROPOSAL='482f1b3051275f0f7b9c9e3530b1ff051c0df9b3c4b9330e7c5ec7199f164d06'
END=datetime.datetime(2026,9,29,10,0,tzinfo=datetime.timezone.utc).timestamp()
sha=lambda b:hashlib.sha256(b).hexdigest()
def need(ok,why):
    if not ok: raise RuntimeError(why)
def load(path,pin):
    for p in (path,*path.parents):
        s=p.lstat();need(s.st_uid==0 and not s.st_mode&0o022 and not stat.S_ISLNK(s.st_mode),'unprotected_source')
    need(sha(path.read_bytes())==pin,'owner_pin_changed')
    spec=importlib.util.spec_from_file_location('activation_owner',path)
    o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o);return o

def create(path,raw,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def js(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def receipt(name,value):
    value={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**value}
    create(STAGE/(name+'.json'),js(value));print(json.dumps(value),flush=True);return value

def unit(name):
    r=subprocess.run(['systemctl','show',name,'-p','MainPID,ActiveState,SubState,InvocationID,Result,ExecMainStatus,Job'],capture_output=True,text=True,check=True,timeout=3)
    return dict(x.split('=',1) for x in r.stdout.splitlines())
def command(*args,timeout=30):
    r=subprocess.run(args,capture_output=True,timeout=timeout)
    need(r.returncode==0,'command_failed_'+args[0]+'_'+str(r.returncode));return r.stdout

def atomic(o,path,raw,mode=0o600):
    for p in path.parents:
        s=p.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'unprotected_target_parent')
    tmp=path.with_name(path.name+'.h031-new');create(tmp,raw,mode);os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    need(o.protected(path)==raw,'atomic_readback_failed')

def stage():
    o=load(M/'source/owner.py',OLD);h=o.setup()
    data=json.load(sys.stdin);entries={n:base64.b64decode(v) for n,v in data.items()}
    need(sha(entries['proposal.json'])==PROPOSAL,'proposal_pin')
    p=json.loads(entries['proposal.json']);mapping=json.loads(entries['mapping.json'])
    need(o.BOOT.read_text().strip()==p['boot'],'boot_changed')
    for dest,row in p['leaves'].items():
        need(sha(o.protected(dest))==row['old'],'old_pin_changed_'+dest)
        need(sha(entries[mapping[dest]])==row['new'],'new_pin_changed_'+dest)
    need(sha(o.protected(M/'state.json'))==p['mimo']['stoppedStateRawSha256'],'running_state_changed')
    need(sha(entries['source-successor-corrected-delta.json'])==p['mimo']['exactDeltaRawSha256'],'delta_changed')
    # Protected candidate content has a separately pinned proposal; stage mapping
    # is kept outside that proposal to preserve its reviewed raw hash.
    with h.MountedStorageGuard(h.s) as g:
        o.storage_paths(h,g);h.s.root_payload_guard();g.check_path('/data/build')
        STAGE.mkdir(mode=0o700)
        for d in ('reviewed-source','private','predecessor','prior-inputs','backup'): (STAGE/d).mkdir(mode=0o700)
        for name,raw in entries.items():
            need(name in ALLOWED,'stage_path_not_allowed')
            (STAGE/name).parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            create(STAGE/name,raw)
        subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=STAGE,check=True,stdout=subprocess.DEVNULL)
        for name,src in [('manifest.json',M/'manifest.json'),('owner.py',M/'source/owner.py')]:create(STAGE/'predecessor'/name,o.protected(src),0o400)
        for name in ('source-successor-prior-manifest.json','source-successor-prior-owner.py','source-successor-delta.json'):
            if os.path.lexists(M/name):create(STAGE/'prior-inputs'/name,o.protected(M/name),0o400)
        backup={}
        for dest in list(p['leaves'])+[str(M/n) for n in ('state.json','selection.json','proxy-state.json','guard.json')]+[str(I/'state.json')]:
            raw=o.protected(dest);name=sha(dest.encode())+'.bin';create(STAGE/'backup'/name,raw,0o400)
            backup[dest]={'file':name,'sha256':sha(raw),'mode':stat.S_IMODE(Path(dest).stat().st_mode)}
        create(STAGE/'backup/index.json',js(backup),0o400)
        need(sha(o.protected(M/'source-successor-delta.json'))==p['mimo']['originalDeltaRawSha256'],'original_delta_changed')
        create(M/'source-successor-corrected-delta.json',entries['source-successor-corrected-delta.json'],0o400)
        create(M/'source-successor-corrected-manifest.json',entries['private/source-successor-corrected-manifest.json'],0o400)
        h.s.root_payload_guard()
    receipt('02-staged',{'status':'STAGED_OLD_INSTALLED_PINS_UNCHANGED','stage':str(STAGE),'installedDelta':p['mimo']['exactDeltaRawSha256'],'sixOldPinsMatch':True})

ALLOWED={'initial-private.json', 'SOURCE-MANIFEST.json', 'SHA256SUMS', 'mapping.json', 'private/exact/guard.json', 'private/image-config.json', 'private/exact/state.json', 'SOURCE.patch', 'REPORT.md', 'private/original-proposed-manifest.json', 'private/exact/source-stop-992bf979-efae-495b-9ab2-26e75ed5c5d0-fbfd46357f0d4e3482aa1c7da14f5147.json', 'reviewed-source/node.py', 'reviewed-source/service.py', 'reviewed-source/node_collectors.py', 'private/exact/source-successor-delta.json', 'private/exact/source/owner.py', 'TESTS.log', 'TESTS-clean-initial.log', 'PACKET-CHECKS.json', 'private/exact/selection.json', 'TESTS-timeout-second.log', 'SOURCE.bundle', 'TESTS.md', 'reviewed-source/owner.py', 'private/exact/manifest.json', 'activate.py', 'source-successor-delta.original.json', 'TESTS-timeout-initial.log', 'proposal.json', 'private/source-successor-corrected-manifest.json', 'source-successor-corrected-delta.json', 'private/exact/proxy-state.json', 'TESTS-timeout-actual.log', 'PROTOCOL.md'}

def context():
    o=load(STAGE/'reviewed-source/owner.py',NEW);h=o.setup()
    raw=o.protected(STAGE/'proposal.json');need(sha(raw)==PROPOSAL,'proposal_pin')
    p=json.loads(raw);mapping=o.read(STAGE/'mapping.json')
    need(o.BOOT.read_text().strip()==p['boot'],'boot_changed')
    return o,h,p,mapping

def main():
    need(os.geteuid()==0 and time.time()<END,'execution_window_closed')
    action=sys.argv[1]
    if action=='stage':return stage()
    o,h,p,mapping=context(); mi=p['mimo']
    if action=='prepare':
        for dest,row in p['leaves'].items():need(sha(o.protected(dest))==row['old'],'old_pin_changed')
        v=o.prepare_source_stop_timeout(mi['stoppedStateRawSha256'],p['boot'],mi['oldManifestCanonical'],mi['originalDeltaRawSha256'],mi['originalIntentRawSha256'],mi['exactDeltaRawSha256'],mi['newManifestCanonical'])
        name=o.source_supplement_name(o.read(M/'state.json'));raw=o.protected(M/name)
        create(STAGE/'supplement.json',raw,0o400)
        receipt('03-prepared',{'status':v['status'],'supplementName':name,'supplement_sha256':sha(raw),'physical':v['physical_absence'],'hardware':v['hardware_proof']})
        for n in ('state.json','guard.json','proxy-state.json','selection.json',o.source_stop_name(o.read(M/'state.json'))):create(STAGE/'predecessor'/n,o.protected(M/n),0o400)
        receipt('04-mimo-stopped',{'stateRawSha256':sha(o.protected(M/'state.json')),'status':o.read(M/'state.json')['status'],'retainedFailures':{k:o.read(M/'state.json')[k] for k in ('primary_failure','settlement_failure')},'unit':unit(o.UNIT)})
    elif action=='stop-image':
        need((STAGE/'04-mimo-stopped.json').exists(),'mimo_stop_unproved')
        # Read API owner status without invoking readiness/recovery or generation.
        import http.client
        conn=http.client.HTTPConnection('127.0.0.1',30006,timeout=4)
        try:
            conn.request('GET','/v1/image-capabilities',headers={'Authorization':'Bearer '+Path('/data/services/secrets/llm-api-key').read_text().strip()})
            r=conn.getresponse();status=json.loads(r.read(65536));need(r.status==200 and status.get('busy') is False,'image_work_not_idle')
        finally:conn.close()
        create(STAGE/'image-api-before.json',js({k:status[k] for k in ('ready','busy','admitting','state')}))
        initial=o.read(STAGE/'initial-private.json');old=initial['files'][str(I/'state.json')]['value']
        need(o.read(I/'state.json')==old,'image_state_changed')
        command('systemctl','stop','llm-image-api.service',timeout=30)
        need(unit('llm-image-api.service')['MainPID']=='0','image_api_not_stopped')
        command('systemctl','stop','llm-image-backend.service',timeout=130)
        state=o.read(I/'state.json');need(state['phase']=='stopped','image_not_stopped')
        ids=command('docker','ps','-aq','--no-trunc',timeout=5).decode().split()
        need(old['container']['id'] not in ids,'old_image_container_present')
        need(not Path('/proc',str(initial['native'][0]['State']['Pid'])).exists(),'old_image_pid_present')
        command('systemctl','stop','llm-node.service',timeout=25)
        need(unit('llm-node.service')['MainPID']=='0','node_not_stopped')
        create(STAGE/'image-stopped-state.json',o.protected(I/'state.json'),0o400)
        receipt('05-image-stopped',{'status':'IMAGE_REMOVED_NODE_STOPPED','oldContainerId':old['container']['id'],'stateRawSha256':sha(o.protected(I/'state.json')),'units':{u:unit(u) for u in ('llm-image-api.service','llm-image-backend.service','llm-node.service')}})
    elif action=='install':
        need((STAGE/'05-image-stopped.json').exists(),'stops_unproved')
        stopped=o.read(STAGE/'04-mimo-stopped.json')
        need(sha(o.protected(M/'state.json'))==stopped['stateRawSha256'],'stopped_state_changed')
        for u in ('llm-frontier-mimo.service','llm-image-api.service','llm-image-backend.service','llm-node.service'):need(unit(u)['MainPID']=='0','unit_live')
        content={dest:o.protected(STAGE/mapping[dest]) for dest in p['leaves']}
        for dest,row in p['leaves'].items():need(sha(content[dest])==row['new'] and sha(o.protected(dest))==row['old'],'install_pin_mismatch')
        with h.MountedStorageGuard(h.s) as g:
            o.storage_paths(h,g);h.s.root_payload_guard()
            with h.acquire_lease(blocking=False) as lease:
                need(o.selection()==mi['selection'],'selection_changed')
                for name,src in [('source-successor-prior-manifest.json','manifest.json'),('source-successor-prior-owner.py','owner.py')]:atomic(o,M/name,o.protected(STAGE/'predecessor'/src),0o400)
                for dest,raw in content.items():
                    need(sha(o.protected(dest))==p['leaves'][dest]['old'],'old_pin_cas_changed')
                    if dest.startswith('/data/'):g.check_path(dest)
                    atomic(o,Path(dest),raw)
                    create(STAGE/('installed-'+sha(dest.encode())+'.json'),js({'path':dest,**p['leaves'][dest]}))
                lease.validate()
            h.s.root_payload_guard()
        receipt('06-installed',{'status':'SIX_EXACT_PATHS_INSTALLED','files':{d:{'old':r['old'],'new':sha(o.protected(d))} for d,r in p['leaves'].items()},'stateUnchanged':sha(o.protected(M/'state.json'))==stopped['stateRawSha256']})
    elif action=='node-start':
        need((STAGE/'06-installed.json').exists(),'install_unproved')
        command('systemctl','start','llm-node.service',timeout=15)
        receipt('07-node-started',{'unit':unit('llm-node.service')})
    elif action=='reconcile':
        stopped=o.read(STAGE/'04-mimo-stopped.json')
        v=o.reconcile_settled_source(stopped['stateRawSha256'],p['boot'],mi['newManifestCanonical'],mi['exactDeltaRawSha256'],same_boot=True,stop_timeout=True,expected_supplement_sha256=o.read(STAGE/'03-prepared.json')['supplement_sha256'])
        receipt('08-reconciled',v)
    elif action=='start':
        need((STAGE/'08-reconciled.json').exists(),'reconcile_missing')
        command('systemctl','start','--no-block','llm-frontier-mimo.service',timeout=5)
        command('systemctl','start','--no-block','llm-image-api.service',timeout=5)
        receipt('09-started',{'status':'ONE_NORMAL_START_EACH_SUBMITTED','units':{u:unit(u) for u in ('llm-frontier-mimo.service','llm-image-api.service')}})
    else:raise RuntimeError('unknown_phase')
if __name__=='__main__':main()
