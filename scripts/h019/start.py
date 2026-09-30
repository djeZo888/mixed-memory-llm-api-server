#!/usr/bin/env python3
"""One reviewed ordinary GLM release and MiMo start; no rollback or inference."""
import base64
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import time

B = Path('/data/build/H019-20260928')
OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OWNER_SHA = 'e5fda2057168c29b1fe6e53da727b337beaf5634ddbc7dbb3d4f2c46602bcd53'
MANIFEST = 'd8bd9326118458774ac2b585e6029faa2a607d195001d85e14c5d238f6c05be4'
QUIET = '9bb5404c976ce26d6addf64ec32f38a1b63db4c5a714409edbfc515f1c52bea4'
END = 1790568629
NAMES = ('llmctl-qwen38-27b-q0-480000-yarn4-bf16kv', 'llmctl-qwen38-27b-q1-server-480000-yarn4-bf16kv', 'llm-image-backend')

def require(ok, why):
    if not ok: raise RuntimeError(why)

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value

def main():
    require(time.time() < END, 'foreground_closed')
    for p in (OWNER, *OWNER.parents):
        st = p.lstat(); require(st.st_uid == 0 and not st.st_mode & 0o022 and not stat.S_ISLNK(st.st_mode), 'protected_owner')
    require(hashlib.sha256(OWNER.read_bytes()).hexdigest() == OWNER_SHA, 'owner_pin')
    o = module('h019_start_owner', OWNER); h = o.setup()
    def save(name, value):
        with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(B), g) as a:
            a.atomic_json(name, value); a.check()
    def show(unit):
        return dict(x.split('=',1) for x in o.run(['systemctl','show',unit,'-p','MainPID,ActiveState,InvocationID'],3).splitlines())
    def residents():
        rows=[]
        for name in NAMES:
            c=o.inspect(name); require(c['State']['Running'],'resident_stopped'); cg=o.cgpath(c['State']['Pid'])
            rows.append({'name':name,'id':c['Id'],'pid':c['State']['Pid'],'started_at':c['State']['StartedAt'],
                'cgroup':str(cg),'limits':{n:(cg/n).read_text().strip() for n in ('memory.max','memory.swap.max')},
                'swap_current':(cg/'memory.swap.current').read_text().strip()})
        return rows
    raw=o.protected(B/'package/QUIET.json'); require(hashlib.sha256(raw).hexdigest()==QUIET,'quiet_pin')
    q=json.loads(raw); require(q['status']=='QUIET_ORIGINAL_APP_PAUSED' and q['app']['MainPID']=='0','app_not_paused')
    require(all(q[k]==0 for k in ('activeOwnedRuns','activeFrontierRequests','activeImageJobs','uncertainImageJobs')),'app_not_idle')
    m=o.read(o.BASE/'manifest.json'); require(o.digest(m)==MANIFEST,'manifest_pin'); o.source_preflight(h,m)
    for path,pin in o.read(B/'client-closure.json').items():
        require(hashlib.sha256(o.protected(path)).hexdigest()==pin,'client_closure_changed')
    require(not (B/'START-ATTEMPT.json').exists(),'one_start_no_replay')
    selected=o.selection(); require(selected=={'schema_version':1,'generation':11,'selected_frontier':o.GLM},'selection_changed')
    previous=o.read(o.BASE/'state.json')
    require(previous['status']=='SETTLED' and previous['request_hold'] is False and
        previous['settlement']=={'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True},'old_mimo_not_settled')
    for pid in (previous['native']['pid'],previous['proxy']['pid']): require(not Path('/proc',str(pid)).exists(),'old_pid_present')
    require(not Path(previous['native_cgroup']).exists() and show(o.UNIT)['MainPID']=='0','old_owner_present')
    backup=o.read(B/'BACKUP.json'); old=json.loads(base64.b64decode(backup[str(o.BASE/'manifest.json')]['base64']))
    prior=o.exact_container(o.inspect(previous['native']['container_id']),old,previous)
    require(not prior['State']['Running'] and prior['State']['Pid']==0,'old_container_active')
    glmconfig=o.read(o.GLM_BASE/'config.json'); glmstate=o.read(o.GLM_BASE/'state.json')
    for name,pin in glmconfig['source_sha256'].items():
        require(hashlib.sha256(o.protected(o.GLM_BASE/'source'/name)).hexdigest()==pin,'glm_source_changed')
    f=module('h019_glm_owner',o.GLM_BASE/'source/owner.py')
    glm=o.inspect('llm-frontier-flash'); f.validate_container(glm,glmconfig,glmstate)
    require(glm['State']['Running'] and glm['State']['Pid']==3099917 and
        glm['Id']=='2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab','glm_identity_changed')
    glmrow={'id':glm['Id'],'pid':glm['State']['Pid'],'started_at':glm['State']['StartedAt'],'cgroup':str(o.cgpath(glm['State']['Pid']))}
    before=residents(); identity=[o.LEASE_PATH.stat().st_dev,o.LEASE_PATH.stat().st_ino]
    with h.MountedStorageGuard(h.s) as g:
        o.storage_paths(h,g); h.s.root_payload_guard()
    save('START-ATTEMPT.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'ONE_TRANSITION_INTENT',
        'selection':selected,'manifest_sha256':MANIFEST,'glm':glmrow,'residents':before,'previous_mimo':previous,'lock_identity':identity})
    # Normal GLM owner takes its own lease; never wrap systemctl in a lease.
    o.run(['systemctl','stop',o.GLM_UNIT],55)
    c=o.inspect(glmrow['id'])
    require(not c['State']['Running'] and c['State']['Pid']==0 and show(o.GLM_UNIT)['MainPID']=='0','glm_not_stopped')
    require(not Path('/proc',str(glmrow['pid'])).exists() and not Path(glmrow['cgroup']).exists(),'glm_physical_not_released')
    require(not o.run(['nvidia-smi','--id='+o.GPU,'--query-compute-apps=pid','--format=csv,noheader,nounits'],3).strip(),'frontier_compute_present')
    after=residents(); require([{k:v for k,v in r.items() if k!='swap_current'} for r in after]==
        [{k:v for k,v in r.items() if k!='swap_current'} for r in before],'residents_changed')
    save('GLM-RELEASE.json',{'status':'EXACT_GLM_RELEASED','glm':glmrow,'pid_released':True,'cgroup_released':True,'gpu_released':True,'residents':after})
    # Verify existing GPU guards before changing selection, without broadening them.
    for line in o.run(['nvidia-smi','--query-gpu=uuid,memory.total,memory.free,temperature.gpu','--format=csv,noheader,nounits'],3).splitlines():
        uid,total,free,temp=[x.strip() for x in line.split(',')];total,free,temp=map(float,(total,free,temp))
        require(temp<85,'thermal'); floor=total*.07 if uid==o.GPU else total*.05 if uid=='GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23' else 16384
        require(free>=floor,'gpu_reserve')
    baseline=o.memory();require(m['memory']['limit_bytes']<=baseline['MemAvailable']-.15*baseline['MemTotal'],'host_reserve')
    # Full lifecycle scans are outside the canonical section. State is archived above.
    with h.MountedStorageGuard(h.s) as g:
        o.storage_paths(h,g);h.s.root_payload_guard()
        with h.acquire_lease(blocking=False) as lease:
            require(o.selection()==selected and o.read(o.BASE/'state.json')==previous,'state_changed')
            require([o.LEASE_PATH.stat().st_dev,o.LEASE_PATH.stat().st_ino]==identity,'canonical_changed')
            cycle=time.monotonic();boot=o.BOOT.read_text().strip()
            with o.bounded(5):
                limit=o.temperature_limit(o.run(['nvidia-smi','--id='+o.GPU,'-q','-x'],2))
                sample=o.sample_guard(m,baseline,limit,proof_boot=boot)
                hardware=o.latch(h,boot,lease=lease,evidence=sample['hardware_validation'],deadline=cycle+5)
                policy=o.memory_policy(m)
            # Ordinary restart removes only this exact stopped historical container.
            prior=o.exact_container(o.inspect(prior['Id']),old,previous)
            require(not prior['State']['Running'] and prior['State']['Pid']==0,'old_container_changed')
            o.run(['docker','rm',prior['Id']],5)
            new={'schema_version':1,'selected_frontier':o.MODEL,'generation':12,'manifest_sha256':MANIFEST}
            o.write(h,'selection.json',new);lease.validate()
        h.s.root_payload_guard()
    require(time.time()<END,'foreground_closed_before_start')
    o.run(['systemctl','start',o.UNIT],10)
    current=o.read(o.BASE/'state.json')
    for _ in range(40):
        if current.get('launch_id')!=previous['launch_id'] and current.get('native'):break
        if show(o.UNIT)['ActiveState']=='failed':break
        time.sleep(.25);current=o.read(o.BASE/'state.json')
    unit=show(o.UNIT)
    out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selection':o.selection(),'state':current,
        'unit':unit,'lock_identity':[o.LEASE_PATH.stat().st_dev,o.LEASE_PATH.stat().st_ino],
        'lifecycle_lease_released_before_start':True,'hardware':hardware,'residents':residents()}
    if current.get('launch_id')!=previous['launch_id'] and current.get('native'):
        out['memory_policy']=o.memory_policy(m,current['native'])
        out['sample']=o.sample_guard(m,current['baseline'],limit,current['native'])
    save('START-RESULT.json',out);print(json.dumps(out),flush=True)
    require(current.get('launch_id')!=previous['launch_id'] and current['status'] in ('LOADING','RUNNING') and
        unit['ActiveState']=='active' and out['lock_identity']==identity,'independent_loading_unproven_no_retry')

if __name__ == '__main__': main()
