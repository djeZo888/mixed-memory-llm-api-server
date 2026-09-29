#!/usr/bin/env python3
"""H031 exact one-shot activation helper; private staged inputs are never in Git.

Each phase is invoked once by W1 after inspecting the preceding receipt.
No retries, source redesign, direct native stop, baseline restore or inference.
"""
import base64, datetime, hashlib, importlib.util, json, os, stat, subprocess, sys, time
from pathlib import Path
STAGE=Path('/data/build/h031-activate01-20260929')
M=Path('/data/services/mimo-h016-20260927')
I=Path('/data/services/image21-runtime-20260923')
OLD='1cc1ee45eca7c578d9b84411d75c1cfd37c914edd7b5097389ee2f19fae23098'
NEW='206ccfe397d3b855836f28a05170ac1d5af56c7d93cb85e1bd1cb4ff6c84f5bc'
PROPOSAL='39739da1364518880a6971abcb1305618d609e32227822f89062fc7382b7aab1'
END=datetime.datetime(2026,9,29,9,35,tzinfo=datetime.timezone.utc).timestamp()
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
    need(sha(o.protected(M/'state.json'))==p['mimo']['runningStateRawSha256'],'running_state_changed')
    need(sha(entries['source-successor-delta.json'])==p['mimo']['exactDeltaRawSha256'],'delta_changed')
    # Protected candidate content has a separately pinned proposal; stage mapping
    # is kept outside that proposal to preserve its reviewed raw hash.
    with h.MountedStorageGuard(h.s) as g:
        o.storage_paths(h,g);h.s.root_payload_guard();g.check_path('/data/build')
        STAGE.mkdir(mode=0o700)
        for d in ('reviewed-source','private','predecessor','prior-inputs','backup'): (STAGE/d).mkdir(mode=0o700)
        for name,raw in entries.items():
            need(name in ALLOWED,'stage_path_not_allowed');create(STAGE/name,raw)
        for name,src in [('manifest.json',M/'manifest.json'),('owner.py',M/'source/owner.py')]:create(STAGE/'predecessor'/name,o.protected(src),0o400)
        for name in ('source-successor-prior-manifest.json','source-successor-prior-owner.py','source-successor-delta.json'):
            if os.path.lexists(M/name):create(STAGE/'prior-inputs'/name,o.protected(M/name),0o400)
        backup={}
        for dest in list(p['leaves'])+[str(M/n) for n in ('state.json','selection.json','proxy-state.json','guard.json')]+[str(I/'state.json')]:
            raw=o.protected(dest);name=sha(dest.encode())+'.bin';create(STAGE/'backup'/name,raw,0o400)
            backup[dest]={'file':name,'sha256':sha(raw),'mode':stat.S_IMODE(Path(dest).stat().st_mode)}
        create(STAGE/'backup/index.json',js(backup),0o400)
        atomic(o,M/'source-successor-delta.json',entries['source-successor-delta.json'])
        h.s.root_payload_guard()
    receipt('02-staged',{'status':'STAGED_OLD_INSTALLED_PINS_UNCHANGED','stage':str(STAGE),'installedDelta':p['mimo']['exactDeltaRawSha256'],'sixOldPinsMatch':True})

ALLOWED={'proposal.json','mapping.json','activate.py','reviewed-source/owner.py','reviewed-source/node.py','reviewed-source/node_collectors.py','reviewed-source/service.py','private/successor-manifest.json','private/image-config.json','source-successor-delta.json','initial-private.json'}

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
        v=o.prepare_source_stop(mi['runningStateRawSha256'],p['boot'],mi['oldManifestCanonical'],mi['exactDeltaRawSha256'])
        receipt('03-prepared',{'status':v['status'],'intent':o.source_stop_name(o.read(M/'state.json')),'launch_id':v['launch_id'],'intentSha256':sha(o.protected(M/o.source_stop_name(o.read(M/'state.json'))))})
    elif action=='stop-mimo':
        need((STAGE/'03-prepared.json').exists(),'intent_missing')
        for dest,row in p['leaves'].items():need(sha(o.protected(dest))==row['old'],'old_pin_changed')
        command('systemctl','stop','llm-frontier-mimo.service',timeout=140)
        old=o.read(M/'manifest.json');o.source_preflight(h,old)
        with h.acquire_lease(blocking=False) as lease,h.MountedStorageGuard(h.s) as g:
            o.storage_paths(h,g);h.s.root_payload_guard()
            files={n:o.protected(M/n).decode() for n in ('state.json','proxy-state.json','guard.json')}
            state=json.loads(files['state.json']);name=o.source_stop_name(state);files[name]=o.protected(M/name).decode()
            o.intentional_source_stop(old,state,p['boot'],files,mi['exactDeltaRawSha256'])
            physical=o.settled_source_absence(old,state,p['boot'],same_boot=True)
            hardware=o.source_hardware(h,p['boot'],lease)
            need(all(o.protected(M/n).decode()==raw for n,raw in files.items()),'stopped_state_changed');lease.validate();h.s.root_payload_guard()
        for n,raw in files.items():create(STAGE/'predecessor'/n,raw.encode(),0o400)
        receipt('04-mimo-stopped',{'stateRawSha256':sha(files['state.json'].encode()),'status':state['status'],'failure':state['primary_failure'],'physical':physical,'hardware':hardware,'unit':unit(o.UNIT)})
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
        v=o.reconcile_settled_source(stopped['stateRawSha256'],p['boot'],mi['newManifestCanonical'],mi['exactDeltaRawSha256'],same_boot=True)
        receipt('08-reconciled',v)
    elif action=='start':
        need((STAGE/'08-reconciled.json').exists(),'reconcile_missing')
        command('systemctl','start','--no-block','llm-frontier-mimo.service',timeout=5)
        command('systemctl','start','--no-block','llm-image-api.service',timeout=5)
        receipt('09-started',{'status':'ONE_NORMAL_START_EACH_SUBMITTED','units':{u:unit(u) for u in ('llm-frontier-mimo.service','llm-image-api.service')}})
    else:raise RuntimeError('unknown_phase')
if __name__=='__main__':main()
