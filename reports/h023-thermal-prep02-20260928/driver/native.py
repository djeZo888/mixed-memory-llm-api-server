"""Fixed W1-only Linux adapter. Import is inert; construction requires exact reviewed GO.

No arbitrary commands/owner modules from configuration. H013 concrete guard,
Qwen manager, image owner and H016/H019 MiMo identity/stop primitives retained.
"""
import contextlib
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import types
from urllib.parse import urlsplit
from contract import LANES, TEXT, canonical, digest, require

ROOT=Path('/usr/local/lib/llm-server/control-api')
MIMO=Path('/data/services/mimo-h016-20260927/source/owner.py')
IMAGE=Path('/data/services/image21-runtime-20260923/source/service.py')
KEY=Path('/data/services/secrets/llm-api-key')

def clock():return {'utc':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic()}
def run(argv,timeout=5):return subprocess.check_output(argv,text=True,stderr=subprocess.PIPE,timeout=timeout)
def pairs(path):return {s.split()[0]:int(s.split()[1]) for s in Path(path).read_text().splitlines()}
def protected(path):
    path=Path(path)
    for item in (path,*path.parents):
        st=item.lstat();require(st.st_uid==0 and not st.st_mode & 0o022 and not stat.S_ISLNK(st.st_mode),'protected source/path required')
    return path.read_bytes()
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def container_identity(c):
    pid=c['State']['Pid'];require(c['State']['Running'] and pid>0 and not c['State']['OOMKilled'],'exact native running required')
    cg=Path('/proc',str(pid),'cgroup').read_text().split('::',1)[1].strip()
    return {'Id':c['Id'],'Image':c['Image'],'StartedAt':c['State']['StartedAt'],'Pid':pid,'cgroup':cg,
            'pid_start_ticks':Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]}

@contextlib.contextmanager
def initial_lease(acquire, busy_type, expected_boot):
    """One bounded pre-dispatch admission; never retries a request/body/phase."""
    path='/run/llmctl/lifecycle.lock'
    info=os.stat(path,follow_symlinks=False);identity=(info.st_dev,info.st_ino)
    deadline=time.monotonic()+10
    def unchanged():
        info=os.stat(path,follow_symlinks=False)
        require((info.st_dev,info.st_ino)==identity and
                Path('/proc/sys/kernel/random/boot_id').read_text().strip()==expected_boot,
                'initial canonical lease or boot changed')
    while True:
        unchanged()
        context=acquire(blocking=False)
        try:
            lease=context.__enter__()
            break
        except busy_type:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise
            time.sleep(min(.1,remaining))
    try:
        unchanged()
        yield lease
    finally:
        context.__exit__(*sys.exc_info())

class Wire:
    def __init__(self,spec,key,seconds):
        url=urlsplit(spec['endpoint']);cls=http.client.HTTPSConnection if url.scheme=='https' else http.client.HTTPConnection
        self.c=cls(url.hostname,url.port,timeout=min(5,seconds));self.c.connect();self.c.auto_open=0
        self.spec,self.key,self.seconds=spec,key,seconds
    def send(self,raw,request_id):
        self.c.request('POST',self.spec['request_path'],raw,{'Authorization':'Bearer '+self.key,'Content-Type':'application/json','X-Request-ID':request_id})
        if self.c.sock:self.c.sock.settimeout(self.seconds)
    def response(self):return self.c.getresponse()
    def close(self):self.c.close()

class NativeAdapter:
    def __init__(self,m,go,journal_path):
        self.m,self.go=m,go
        self.owner_id=m['task_id']+'-'+go['phase']+'-'+go['go_id']
        self.started_utc=clock()['utc'];self.physically_stopped=set();self.stopping={};self.stopped={};self.cg={};self.latest_identity={}
        required={str(MIMO),str(IMAGE),str(ROOT/'scripts/lifecycle/manager.py'),
                  str(ROOT/'scripts/common/lifecycle_lease.py'),str(ROOT/'scripts/install/storage.py'),str(ROOT/'scripts/install/storage_io.py')}
        require(required <= set(m['source_sha256']),'fixed owner/guard source closure required')
        for path,pin in m['source_sha256'].items():require(hashlib.sha256(protected(path)).hexdigest()==pin,'current source pin changed')
        self.source_stats={path:(Path(path).stat().st_ino,Path(path).stat().st_mtime_ns,Path(path).stat().st_size) for path in m['source_sha256']}
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==m['boot_id'],'current boot changed')
        require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==m['owner_adapter_sha256'],'fixed adapter hash changed')
        sys.path.insert(0,str(ROOT/'scripts'))
        from install.storage import Storage
        from install.storage_io import MountedStorageGuard, AnchoredRoot
        from common.lifecycle_lease import acquire_lease, LeaseBusy
        from lifecycle.manager import load_manager
        class Command:
            def run(self,argv,*,timeout=30,env=None):return subprocess.check_output(argv,text=True,timeout=timeout,env=env)
        registration=Storage({},Command()).read_registration()
        self.storage=Storage({'data_dir':registration['data']['path'],'data_uuid':registration['data']['uuid'],
            'model_dir':registration['models']['path'],'model_uuid':registration['models']['uuid'],'storage_mode':registration['storage_mode']},Command())
        self.guard_cls,self.root_cls,self.acquire=MountedStorageGuard,AnchoredRoot,acquire_lease
        self.manager=load_manager(types.SimpleNamespace(instance=None),ROOT/'configs')
        self.o=module(MIMO,'h023_current_mimo');self.image_module=module(IMAGE,'h023_current_image')
        self.image=self.image_module.Runtime()
        self.key=protected(KEY).strip().decode()  # only live construction, never logged
        require(all(m['lanes'][l]['auth_ref']==str(KEY) for l in LANES),'only existing protected inference key transport')
        from fans import FanReader
        self.fans=FanReader();self.spool_baseline=None
        self.journal_path=Path(journal_path)
        require(str(self.journal_path).startswith('/data/logs/H023-') and '..' not in self.journal_path.parts,'registered H023 journal required')
        # One full registration/root/lease boundary; retain guard for lightweight
        # mountinfo/path/FD checks throughout telemetry and all journal writes.
        with initial_lease(self.acquire,LeaseBusy,m['boot_id']):
            self.storage.root_payload_guard()
            self.guard=self.guard_cls(self.storage)
            self.guard.check_path(str(self.journal_path.parent))
        own=dict(s.split('=',1) for s in run(['systemctl','show',go['unit'],'-p','MainPID,InvocationID,ActiveState,ControlGroup']).splitlines())
        require(int(own['MainPID'])==os.getpid() and own['InvocationID']==os.environ.get('INVOCATION_ID')
                and own['ActiveState'] in ('active','activating') and
                Path('/proc/self/cgroup').read_text().split('::',1)[1].strip()==own['ControlGroup'],'independent current systemd owner required')
    @contextlib.contextmanager
    def boundary(self,full_scan=False):
        with self.acquire(blocking=False) as lease:
            guard=self.guard
            if full_scan:self.storage.root_payload_guard()
            guard.check_path(str(self.journal_path.parent))
            yield lease
            if full_scan:self.storage.root_payload_guard()
    @contextlib.contextmanager
    def read_boundary(self):
        # Read-only request/telemetry checks: no lifecycle lease, no recursive scan.
        self.guard.check_path(str(self.journal_path.parent))
        yield
    def intent(self):return self.read_boundary()
    def rpc(self,lane,path,raw=None):
        spec=self.m['lanes'][lane];url=urlsplit(spec['endpoint'])
        allowed={'/v1/readiness','/get_server_info','/props','/slots','/health/ready','/v1/image-capabilities',spec.get('count_path')}
        require(path in allowed,'fixed read/count route required')
        cls=http.client.HTTPSConnection if url.scheme=='https' else http.client.HTTPConnection
        c=cls(url.hostname,url.port,timeout=5)
        try:
            c.connect();c.auto_open=0
            c.request('POST' if raw is not None else 'GET',path,raw,{'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            response=c.getresponse();body=response.read(2*1024*1024+1)
            require(response.status==200 and len(body)<=2*1024*1024 and response.read(1)==b'','authenticated complete native read required')
            return json.loads(body)
        finally:c.close()
    def identity(self,lane,lifecycle_boundary=False):
        spec=self.m['lanes'][lane]
        with self.boundary() if lifecycle_boundary else self.read_boundary():
            if lane=='mimo':
                o=self.o;state=o.read(o.BASE/'state.json');manifest=o.read(o.BASE/'manifest.json')
                o.validate_manifest(manifest);o.require_selected(manifest)
                require(state['status']=='RUNNING' and state['request_hold'] is False,'MiMo not running/held')
                c=o.inspect(state['native']['container_id']);o.exact_container(c,manifest,state)
                proxy=o.read(o.BASE/'proxy-state.json')
                require(proxy['pid_start_ticks']==o.ticks(proxy['pid']) and proxy['parent_pid']==state['supervisor']['pid']
                        and proxy['launch_id']==state['launch_id'] and proxy['native']==state['native']
                        and proxy['boot_id']==self.m['boot_id'],'proxy actual generation drift')
                unit=dict(s.split('=',1) for s in run(['systemctl','show',o.UNIT,'-p','MainPID,InvocationID,ActiveState']).splitlines())
                require(int(unit['MainPID'])==state['supervisor']['pid'] and unit['InvocationID']==state['supervisor']['invocation_id']
                        and unit['ActiveState']=='active','MiMo supervisor drift')
                guard=o.read(o.BASE/'guard.json')
                require(guard['status']=='ok' and guard['native']==state['native'] and guard['boot_id']==self.m['boot_id']
                        and guard['manifest_sha256']==o.digest(manifest) and not guard['hardware_latched']
                        and 0<=time.monotonic()-guard['observed_monotonic_s']<=15,'MiMo guard freshness')
                identity={'native':o.native_identity(c),'supervisor':state['supervisor'],'proxy':{k:proxy[k] for k in ('pid','pid_start_ticks','parent_pid')},
                          'launch':state['launch_id'],'container':container_identity(c),'policy':o.digest(manifest)}
            elif lane.startswith('qwen'):
                target='glm' if lane=='qwen0' else 'qwen';slot=self.manager.read_state(offline=True)['slots'][target]
                c=self.manager.trusted_container(slot['container'])
                identity={'container':container_identity(c),'generation':slot['generation'],'runtime_profile':slot['container']}
            else:
                with self.root_cls(str(self.image_module.BASE),self.guard) as root:st=root.read_json('state.json')
                require(st['schema_version']==1 and st['owner']==self.image_module.OWNER,'image state identity mismatch')
                c=self.image.inspect_owned(st)
                identity={'container':container_identity(c),'run_id':st['run_id']}
            require(identity==spec['identity'],'current lane native identity changed')
            self.cg[lane]=Path('/sys/fs/cgroup'+identity['container']['cgroup'])
            self.latest_identity[lane]=identity
            return identity
    def preflight(self,lane):
        identity=self.identity(lane)
        r={'lane':lane,'owner_id':self.owner_id,'boot_id':self.m['boot_id'],'deployment_sha256':digest(self.m),
           'identity':identity,'gpu_uuid':self.m['lanes'][lane]['gpu_uuid'],'observed':clock(),
           'ready':True,'guard_ok':True,'global_admission_receipt':self.go['global_admission_receipt'],
           'authenticated':True,'evidence_ref':'current owned native HTTP and exact container/source contract'}
        if lane=='mimo':
            p=self.o.read(self.o.BASE/'proxy-state.json');slots=self.rpc(lane,'/slots');props=self.rpc(lane,'/props')
            require(p['active_requests']==0 and p['quarantined'] is False and len(slots)==1 and
                    slots[0]['is_processing'] is False and slots[0]['n_ctx']==950000 and
                    props['default_generation_settings']['n_ctx']==950000,'MiMo actual native idle required')
            r.update(proxy_active_requests=0,proxy_quarantined=False,native_slots=slots,native_idle=True)
        elif lane.startswith('qwen'):
            ready=self.rpc(lane,'/v1/readiness');info=self.rpc(lane,'/get_server_info')
            require(ready.get('ready') is True,'Qwen readiness')
            require(self.m['lanes'][lane]['capacity_readback']=={k:next((x[k] for x in [info,*info.get('internal_states',[])] if k in x),None)
                    for k in self.m['lanes'][lane]['capacity_readback']},'Qwen capacity/config drift')
            # Root-authorized successful full-drain contract, never queue/util inference.
            require(self.m['lanes'][lane]['completion_contract']=='PINNED_ADAPTIVE_DRAIN_FULL_RESPONSE_EXCLUSIVE_OWNER','Qwen source drain qualification missing')
            r['request_disposition']='EXCLUSIVE_QUIET_PREFLIGHT';r['evidence_ref']='exclusive task + quiet root grant + pinned adaptive drain; subsequent requests require prior full response'
        else:
            ready=self.rpc(lane,'/health/ready')
            require(ready.get('ready') is True and ready.get('busy') is False and ready.get('admitting') is True,'image owner not released')
            require(self.m['lanes'][lane]['completion_contract']=='PINNED_IMAGE_OWNER_NATIVE_EOF_PUBLIC_OUTPUT_CLEANUP','image source cleanup qualification missing')
            spool=self.image.tmp_snapshot(identity['run_id'])
            if self.spool_baseline is None:self.spool_baseline=spool
            require(spool==self.spool_baseline,'new image spool remains owned; no arbitrary cleanup')
            r.update(native_idle=True,owned_job_idle=True,spool_ready=True,spool_evidence=spool)
        r['observed']=clock();return r
    def count(self,lane,raw,row):
        body=json.loads(raw);count_body=body if lane=='mimo' else {k:v for k,v in body.items() if k not in ('stream','stream_options')}
        count_raw=canonical(count_body)
        result=self.rpc(lane,self.m['lanes'][lane]['count_path'],count_raw)
        if lane.startswith('qwen'):
            tokens=result.get('tokens');require(isinstance(tokens,list) and type(result.get('count')) is int and result['count']==len(tokens)
                and all(type(t) is int and 0<=t<2**31 for t in tokens),'Qwen native count/token mismatch')
        return {'body_sha256':hashlib.sha256(raw).hexdigest(),'native':True,'http_status':200,
                'endpoint':self.m['lanes'][lane]['count_path'],'response':{k:v for k,v in result.items() if k!='tokens'},
                'count_body_sha256':hashlib.sha256(count_raw).hexdigest(),'removed_fields':[] if lane=='mimo' else ['stream','stream_options'],
                'token_ids_sha256':digest(result['tokens']) if lane.startswith('qwen') else None,'template_sha256':self.m['lanes'][lane].get('template_sha256'), 'observed':clock(),
                'owner_id':self.owner_id,'identity':row['identity']}
    def connect(self,lane):return Wire(self.m['lanes'][lane],self.key,self.m['bounds']['request_seconds'])
    def corpus(self,lane):
        source=self.m['lanes'][lane]['corpus'];raw=protected(source['path'])
        require(len(raw)<=2*1024*1024 and hashlib.sha256(raw).hexdigest()==source['sha256'],'reviewed corpus changed')
        return raw.decode()
    def settlement(self,lane,row):
        if lane in self.stopped:return self.stopped[lane]
        if row.get('state') not in ('HTTP_COMPLETE','SETTLED') and not row.get('response_complete'):return None
        r=self.preflight(lane);r.update(request_id=row['request_id'],ownership_released=True,resident=True,disposition='COMPLETED')
        if lane.startswith('qwen'):r['request_disposition']='REQUEST_SETTLED'
        if lane=='image':r.update(job_released=True,spool_cleanup='OWNED_SPOOL_UNCHANGED',cleanup_receipt=digest(r['spool_evidence']),native_owner_run_id=r['identity']['run_id'])
        return r
    def stop_exact(self,lane,intent):
        self.identity(lane)  # never a healthy peer
        if lane=='mimo':
            # Normal existing owner unit stop OUTSIDE parent lifecycle lease.
            run(['systemctl','stop',self.o.UNIT],55)
            st=self.o.read(self.o.BASE/'state.json')
            require(st.get('status')=='SETTLED' and st.get('settlement')=={'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True},'MiMo stop settlement unproven')
        else:
            cid=self.m['lanes'][lane]['identity']['container']['Id']
            expected=self.m['lanes'][lane]['identity']
            if lane.startswith('qwen'):
                target='glm' if lane=='qwen0' else 'qwen'
                before=self.manager.read_state(offline=True)['slots'][target]
                require(before['generation']==expected['generation'] and before['container']==expected['runtime_profile'],'stop slot drift')
                intent_before={k:before[k] for k in ('selected','desired','boot_policy','failure')}
            else:
                with self.root_cls(str(self.image_module.BASE),self.guard) as root:before=root.read_json('state.json')
                require(before['run_id']==expected['run_id'],'image stop run drift')
            # STOP intent is already durable. Do not hold the canonical lease
            # over a physical wait: the healthy MiMo owner checks it nonblocking.
            self.stopping[lane]={'intent':intent,'state':before,'stage':'PHYSICAL_STOPPING'}
            c=json.loads(run(['docker','inspect',cid]))[0]
            require(container_identity(c)==expected['container'],'stop immediate native drift')
            run(['docker','stop','--time','3' if lane.startswith('qwen') else '30',cid],12 if lane.startswith('qwen') else 45)
            c=json.loads(run(['docker','inspect',cid]))[0]
            require(c['Id']==cid and c['Image']==expected['container']['Image'] and not c['State']['Running']
                    and c['State']['Pid']==0 and not c['State']['Restarting'],'physical stop failed')
            require(not self.cg[lane].exists() or not (self.cg[lane]/'cgroup.procs').read_text().strip(),'owned cgroup still populated')
            require(not Path('/proc',str(expected['container']['Pid'])).exists(),'owned native PID not released')
            self.stopping[lane]['stage']='STOPPED_BOOKKEEPING_PENDING'
            if lane.startswith('qwen'):
                with self.boundary() as lease:
                    slot=self.manager.read_state(offline=True)['slots'][target]
                    require(slot==before,'stop slot changed during physical wait')
                    self.manager.dispatch('boot-stop',lease=lease,target=target,expected_generation=before['generation'])
                    # Existing boot-stop intentionally preserves desired/selected/
                    # boot policy but clears failure. Retain pre-existing failure.
                    if intent_before['failure'] is not None:
                        with self.manager.slot_context(target):
                            self.manager.state['failure']=intent_before['failure'];self.manager.save(emergency=True)
                    after=self.manager.read_state(offline=True)['slots'][target]
                    require({k:after[k] for k in intent_before}==intent_before,'Qwen intent/failure drift')
            else:
                self.image_module.OPERATION_DEADLINE=time.monotonic()+60
                # Same reset_owned physical removal + owned spool/state primitives,
                # with physical wait/removal outside the borrowed bookkeeping lease.
                self.stopping[lane]['stage']='REMOVING_EXACT_STOPPED_CONTAINER'
                self.image_module.run(['docker','rm',cid])
                require(self.image.inspect_owned(before,missing_ok=True) is None,'image exact removal unproven')
                self.stopping[lane]['stage']='REMOVED_BOOKKEEPING_PENDING'
                with self.boundary() as lease:
                    self.image.lease=lease
                    with self.root_cls(str(self.image_module.BASE),self.guard) as root:current=root.read_json('state.json')
                    require(current==before,'image state changed during physical wait')
                    if before.get('run_id'):before['last_tmp_cleanup']=self.image.cleanup_tmp(before['run_id'])
                    before.update(phase='stopped',container=None,warm=False)
                    self.image.save(before)
        # Stopped identities cannot be represented as running preflight receipts.
        # Keep exact stop evidence durably separate; runner retains UNKNOWN ownership
        # until root inspects it. Never fabricate native-idle running proxy proof.
        proof={'intent':intent,'physical_stop_proven':True,'observed':clock(),'no_replay':True}
        self.journal.write('NATIVE-STOP-'+lane,proof,exclusive=True)
        self.physically_stopped.add(lane)
        self.stopping.pop(lane,None)
        return proof
    def stopping_identity(self,lane):
        """Retain the exact STOPPING identity while physical wait/bookkeeping runs."""
        expected=self.m['lanes'][lane]['identity'];item=self.stopping[lane]
        if lane.startswith('qwen'):c=self.manager.trusted_container(expected['runtime_profile'])
        else:c=self.image.inspect_owned(item['state'],missing_ok=True)
        if c is None:
            require(lane=='image' and item['stage'] in ('REMOVING_EXACT_STOPPED_CONTAINER','REMOVED_BOOKKEEPING_PENDING'), 'unexpected stopped container absence')
        elif c['State']['Running']:
            require(container_identity(c)==expected['container'],'stopping live identity drift')
        else:
            require(c['Id']==expected['container']['Id'] and c['Image']==expected['container']['Image']
                    and c['State']['Pid']==0 and not c['State']['Restarting'],'stopping identity drift')
        return expected
    def sample(self,due):
        return sample(self,due)

def sample(a,due):
    for path,identity in a.source_stats.items():
        st=Path(path).stat();require((st.st_ino,st.st_mtime_ns,st.st_size)==identity,'source identity drift')
    start=clock();fields=['uuid','name','temperature.gpu','power.draw','power.limit','utilization.gpu','memory.total','memory.used','memory.free',
        'clocks.current.graphics','clocks.current.sm','clocks.current.memory','ecc.mode.current','ecc.mode.pending','ecc.errors.uncorrected.volatile.total']
    reasons=['hw_thermal_slowdown','sw_thermal_slowdown','hw_power_brake_slowdown','sw_power_cap','hw_slowdown']
    fields += ['clocks_event_reasons.'+x for x in reasons]
    raw=run(['nvidia-smi','--query-gpu='+','.join(fields),'--format=csv,noheader,nounits'],3)
    rows={}
    for line in raw.splitlines():
        v=dict(zip(fields,[p.strip() for p in line.split(',')]))
        # Installed nvidia-smi rejects this field; retain explicit unavailability.
        v['pcie.replay_counter']='N/A'
        rows[v['uuid']]=v
    gpu={};cgroups={};identities={}
    fans=a.fans.sample({l:a.m['lanes'][l]['gpu_uuid'] for l in LANES})
    for lane in LANES:
        spec=a.m['lanes'][lane];v=rows[spec['gpu_uuid']]
        # No lease or recursive root scan in periodic telemetry.
        identities[lane]=(a.m['lanes'][lane]['identity'] if lane in a.physically_stopped else a.stopping_identity(lane) if lane in a.stopping else a.identity(lane,lifecycle_boundary=False))
        g={'type':v['name'],'family':spec['gpu_family'],
           'clocks':{k:float(v['clocks.current.'+k]) for k in ('graphics','sm','memory')},
           'throttle':{k:v['clocks_event_reasons.'+k]=='Active' for k in reasons},
           'power_brake':v['clocks_event_reasons.hw_power_brake_slowdown']=='Active',
           'ecc_current':v['ecc.mode.current'],'ecc_pending':v['ecc.mode.pending']}
        for name,field in [('temperature_c','temperature.gpu'),('power_draw_w','power.draw'),('power_limit_w','power.limit'),
                ('utilization_pct','utilization.gpu'),('memory_total_mib','memory.total'),('memory_used_mib','memory.used'),('memory_free_mib','memory.free')]:g[name]=float(v[field])
        for name,field in [('ecc_uncorrected','ecc.errors.uncorrected.volatile.total'),('pcie_replay','pcie.replay_counter')]:
            g[name]=int(v[field]) if v[field].isdigit() else None
        g['counter_unavailable_reason']='installed nvidia-smi rejects pcie.replay_counter; unsupported counters remain unavailable' if any(g[k] is None for k in ('ecc_uncorrected','pcie_replay')) else None
        allfans=fans[spec['gpu_uuid']].get('fans',[])
        g['integrated_fan']={'target_pct':min(x['intended_percent'] for x in allfans) if allfans else None,
                            'current_pct':min(x['reported_percent'] for x in allfans) if allfans else None,
                            'rpm':min(x['rpm'] for x in allfans) if allfans else None,
                            'unavailable_reason':None if allfans else 'external server cooling; integrated fan unavailable','individual':allfans}
        gpu[spec['gpu_uuid']]=g
        cg=a.cg[lane]
        if (lane in a.physically_stopped or lane in a.stopping) and not cg.exists():
            cgroups[lane]={'memory_current':0,'swap_current':0,'events':{'oom':0,'oom_kill':0,'max':0},'cpu':{'usage_usec':0},'cgroup_absent':True,'ownership_state':'STOPPED' if lane in a.physically_stopped else 'STOPPING'}
            continue
        cgroups[lane]={'memory_current':int((cg/'memory.current').read_text()),'swap_current':int((cg/'memory.swap.current').read_text()),
                                   'events':pairs(cg/'memory.events'),'cpu':pairs(cg/'cpu.stat')}
    ram={s.split(':')[0]:int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith(('MemTotal:','MemAvailable:'))}
    swap=pairs('/proc/vmstat')
    kernel=run(['journalctl','-k','--since',a.started_utc,'--no-pager','-o','short-iso'],3)
    events=[]
    for line in kernel.splitlines():
        if re.search(r'NVRM.*Xid|out of memory|oom-kill|AER:.*(?:fatal|uncorrected)',line,re.I):
            events.append({'kind':'Xid' if 'Xid' in line else 'AER' if 'AER' in line else 'OOM','lane':None,'sha256':hashlib.sha256(line.encode()).hexdigest()})
    return {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'deployment_sha256':digest(a.m),'identities':identities,
            'guard_ok':True,'stopping_lanes':{l:v['stage'] for l,v in list(a.stopping.items())},'physically_settled_lanes':sorted(a.physically_stopped),'utc':start['utc'],'start_monotonic':start['monotonic'],'due_monotonic':min(due,start['monotonic']),
            'end_monotonic':time.monotonic(),'gpu':gpu,'cgroups':cgroups,'guest':{'ram_total_bytes':ram['MemTotal'],
            'ram_available_bytes':ram['MemAvailable'],'swap_in':swap['pswpin'],'swap_out':swap['pswpout'],
            'cpu_ticks':list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))},
            'kernel':{'read_ok':True,'events':events},'external_fan':a.m['external_fan_readback']}
