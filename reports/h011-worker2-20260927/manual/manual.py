#!/usr/bin/env python3
"""H011 one-attempt, SSH-independent Flash 1M candidate owner.

Only explicit start acknowledges CURRENT stopped harness and settled clients.
Production files/container stay unchanged. Verified PASS retains the candidate;
all other paths confirm candidate stop before original-owner restoration. Unknown
identity/stop is quarantined. No retries, promotion, remote harness control or
secret argv/env. Import, --help and plan are offline.
"""
import argparse
import contextlib
import copy
import datetime
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid

STAGE = '/data/services/h011-manual1m-20260927'
BASE = '/data/services/flash-h008-20260926'
LOG = '/data/logs/flash-h008-20260926'
PREFIX = 'H011-MANUAL1M'
UNIT = 'h011-manual1m'
NAME = 'llm-frontier-flash-h011-manual1m'
OWNER = 'H011-MANUAL1M-20260927'
IMAGE = 'sha256:51791e17c0149019e2ddc032d8c1b2f60b86c3a6c293daff639e20053baa858a'
OWNER_HASH = 'd4a628876b8643a01277039ab744e87a2218e3b87e2c6207e2d67816b570a4b1'
GPU = 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
BUDGET = {'startup':1800,'short':300,'fixture':600,'main':7200,'restore':1800}
TOTAL = sum(BUDGET.values())
RETAINED = 'PASSED_RETAINED_PENDING_PRODUCTION_PROMOTION'
TERMINAL = {RETAINED,'FAILED_CANDIDATE_STOPPED_480K_RESTORED','QUARANTINED_REQUIRES_OWNER_REVIEW'}
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def require(ok, code):
    if not ok: raise ValueError(code)

def protected(path, modes=(0o600,0o644), maximum=16*1024*1024):
    path=Path(path)
    for parent in reversed(path.parents):
        s=parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'unprotected_ancestry')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode) in modes,'unprotected_file')
        raw=b''
        while len(raw)<=maximum:
            block=os.read(fd,min(1024*1024,maximum+1-len(raw)))
            if not block:break
            raw+=block
        require(len(raw)<=maximum,'protected_file_too_large')
        return raw
    finally:os.close(fd)

def run(argv, timeout=30):
    return subprocess.check_output(argv,text=True,timeout=timeout,stderr=subprocess.PIPE).strip()

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

def inspect(ident):
    return json.loads(run(['docker','inspect',ident]))[0]

def stopped(c):
    s=c.get('State',{})
    return s.get('Running') is False and s.get('Pid')==0 and not s.get('Restarting') and not s.get('Paused')

def retainable(request, resource_failure, identity_valid):
    usage=request.get('usage') or {}
    return (request.get('status')=='TRANSPORT_PASS' and request.get('semantic_status')=='PASS'
            and request.get('sse_done') is True and request.get('body_drained') is True
            and request.get('finish_reason')=='stop' and usage.get('prompt_tokens')==1000000
            and type(usage.get('completion_tokens')) is int and 0<usage['completion_tokens']<=1024
            and usage.get('total_tokens')==1000000+usage['completion_tokens']
            and not resource_failure and identity_valid)

def cleanup_decision(candidate_present, identity_valid, stop_confirmed):
    if candidate_present and (not identity_valid or not stop_confirmed):return 'QUARANTINE'
    return 'RESTORE_ORIGINAL'

def canonical_mounts(mounts):
    require(type(mounts) is list,'mounts_invalid')
    require(all(type(m) is dict and type(m.get('Destination')) is str for m in mounts),'mount_destination_invalid')
    require(len({m['Destination'] for m in mounts})==len(mounts),'duplicate_mount_destination')
    return sorted(mounts,key=lambda m:m['Destination'])

class Ops:
    def __init__(self):
        require(os.getuid()==0,'root_owner_required')
        require(str(Path(__file__).resolve())==STAGE+'/manual.py','exact_staged_path_required')
        require(sha(protected(BASE+'/source/owner.py',(0o644,)))==OWNER_HASH,'installed_owner_drift')
        self.owner=load_module('h011_original_owner',BASE+'/source/owner.py')
        self.storage=self.owner.storage()
        from common.lifecycle_lease import acquire_lease
        from install.storage_io import MountedStorageGuard,AnchoredRoot
        self.acquire,self.Guard,self.Anchor=acquire_lease,MountedStorageGuard,AnchoredRoot
        self.lease=None;self.write_lock=threading.RLock()
        self.verify_sources()
        self.key=protected('/data/services/secrets/llm-api-key',(0o600,),4096)
        require(0<len(self.key)<=4096 and all(33<=x<=126 for x in self.key),'invalid_protected_key')

    def verify_sources(self):
        manifest_raw=protected(STAGE+'/candidate-sha256.json',(0o644,))
        if hasattr(self,'stage_hash'):require(sha(manifest_raw)==self.stage_hash,'stage_manifest_changed')
        else:self.stage_hash=sha(manifest_raw)
        manifest=json.loads(manifest_raw)
        require(type(manifest) is dict and 'manual.py' in manifest and 'context_profile.py' in manifest,'candidate_manifest_invalid')
        for name,digest in manifest.items():
            require(type(name) is str and '/' not in name and name not in ('.','..'),'manifest_path_invalid')
            require(sha(protected(STAGE+'/'+name,(0o644,)))==digest,'candidate_source_drift')
        config=json.loads(protected(BASE+'/config.json',(0o600,)))
        baseline=json.loads(protected(STAGE+'/baseline-sha256.json',(0o644,)))
        expected_names={'file_auth.py','idle.py','tokenize_adapter.py','tool_runtime.py','owner.py','native-source-pins.json','numa-seccomp.json'}
        require(set(config['source_sha256'])==expected_names,'production_manifest_set_changed')
        require(config['source_sha256']=={k:baseline[k] for k in expected_names},'production_manifest_changed')
        for name,digest in config['source_sha256'].items():
            require('/' not in name and sha(protected(BASE+'/source/'+name,(0o644,)))==digest,'production_source_drift')
        return manifest,config

    @contextlib.contextmanager
    def transaction(self):
        # One canonical lease spans the durable job; periodic writes borrow it.
        # The reader never enters this function. No alternate lifecycle lock.
        with self.write_lock:
            with (contextlib.nullcontext(self.lease) if self.lease else self.acquire(blocking=False)) as lease:
                lease.validate()
                with self.Guard(self.storage) as guard:
                    for path in (STAGE,BASE,LOG,self.owner.MODEL,'/data/docker','/data/containerd','/data/services/secrets/llm-api-key'):guard.check_path(path)
                    self.storage.root_payload_guard()
                    yield lease,guard
                    self.storage.root_payload_guard()

    def save(self,name,value,exclusive=False):
        with self.transaction() as (_,guard):
            with self.Anchor(LOG,guard) as a:
                if exclusive:
                    with a.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600) as f:
                        f.write((json.dumps(value,sort_keys=True)+'\n').encode());f.fsync()
                else:a.atomic_json(name,value)

    def read(self,name):return json.loads(protected(LOG+'/'+name,(0o600,)))

    def call(self,port,path,body=None,timeout=10):
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
        try:
            c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),
                      {'Authorization':'Bearer '+self.key.decode(),'Content-Type':'application/json'})
            r=c.getresponse();raw=r.read(8*1024*1024)
            require(r.status==200 and len(raw)<8*1024*1024,'native_control_response_invalid')
            return json.loads(raw)
        finally:c.close()

    def original(self):
        _,config=self.verify_sources();state=json.loads(protected(BASE+'/state.json',(0o600,)))
        require(state.get('desired')=='running','original_desired_not_running')
        c=inspect(state['container']['id']);self.owner.validate_container(c,config,state)
        return config,state,c

    def others(self):
        rows=[json.loads(line) for line in run(['docker','ps','--no-trunc','--format','json']).splitlines()]
        selected=[r for r in rows if r.get('Names','').startswith('llmctl-qwen38-27b-') or r.get('Names')=='llm-image-backend']
        require(len(selected)==3,'other_three_models_missing')
        result={}
        for row in selected:
            c=inspect(row['ID']);require(c['State']['Running'],'other_model_not_running')
            identity={k:c[k] for k in ('Id','Image','HostConfig','Config','Mounts')}
            identity['Mounts']=canonical_mounts(identity['Mounts'])
            result[c['Name']]={'id':c['Id'],'image':c['Image'],'started_at':c['State']['StartedAt'],
                               'identity_sha256':sha(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())}
        return result

    def ecc(self):
        raw=run(['nvidia-smi','--query-gpu=uuid,ecc.mode.current,ecc.mode.pending','--format=csv,noheader,nounits'])
        rows={p[0].strip():[x.strip() for x in p[1:]] for p in (line.split(',') for line in raw.splitlines())}
        expected={self.owner.GPU:['Enabled','Enabled'],
          'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237':['Enabled','Enabled'],
          'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528':['Enabled','Enabled'],
          'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23':['Disabled','Disabled']}
        require(rows==expected,'exact_device_or_ecc_changed');return rows

    def idle_precondition(self):
        # Root-approved explicit human prerequisite supplies ownership settlement;
        # these are supplemental live observations, not an atomic native drain.
        require(self.call(30010,'/v1/readiness').get('ready') is True,'original_not_ready')
        require(not run(['ss','-H','-nt4','state','established','( sport = :30010 or dport = :30010 )']), 'native_connection_observed')
        units=run(['systemctl','list-units','--all','--plain','--no-legend','--no-pager','h010-*','h011-*'])
        for line in units.splitlines():
            parts=line.split()
            if len(parts)>3 and parts[0]!=UNIT+'.service':
                require(parts[2] not in ('active','activating','deactivating') or parts[3]=='exited','other_benchmark_owner_active')
        for port in (30011,):
            with socket.socket() as s:s.bind(('127.0.0.1',port))
        require(not run(['docker','ps','-aq','--filter','name=^/'+NAME+'$']),'candidate_already_exists')

    def validate_candidate(self,c,job):
        require(c['Id']==job.get('candidate_id') and c['Name']=='/'+NAME and c['Image']==IMAGE,'candidate_identity_changed')
        n=c['Config'];require(n['Cmd']==['-I','-B','/runtime/file_auth.py','--profile','manual1m'],'candidate_command_changed')
        require(n.get('Labels',{}).get('io.llm-frontier.owner')==OWNER and n['Labels'].get('io.h011.job')==job['nonce'],'candidate_owner_changed')
        mounts=[m for m in c['Mounts'] if m['Destination']=='/runtime']
        require(len(mounts)==1 and mounts[0]['Source']==STAGE and mounts[0]['RW'] is False,'candidate_source_mount_changed')
        projected=copy.deepcopy(c)
        projected['Name']='/'+self.owner.NAME
        projected['Config']['Cmd']=['-I','-B','/runtime/file_auth.py']
        projected['Config']['Labels']['io.llm-frontier.owner']=self.owner.OWNER
        for m in projected['Mounts']:
            if m['Destination']=='/runtime':m['Source']=BASE+'/source'
        _,config=self.verify_sources()
        state={'schema_version':1,'owner':self.owner.OWNER,'container':{'id':c['Id'],'name':self.owner.NAME,'image_id':IMAGE}}
        self.owner.validate_container(projected,config,state)

    def admission(self,lease):
        from lifecycle.storage_binding import RegisteredStorageBinding
        from lifecycle.manager import StorageRunner
        from lifecycle.hardware_policy import HardwarePolicy,RegisteredLatchStore
        from control.node_collectors import boot_identity
        binding=RegisteredStorageBinding.read_registered(StorageRunner())
        def boot():
            b=boot_identity();return {'boot_id':b['boot_id'],'uptime_seconds':b['boot_age_seconds']}
        HardwarePolicy(RegisteredLatchStore(binding,lease=lease),lease=lease,
                       run=lambda argv,timeout=2:subprocess.check_output(argv,timeout=timeout,text=True),boot=boot).require_start([GPU])
        mem={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()}
        require(mem['MemAvailable']>=self.owner.MEMORY+int(mem['MemTotal']*.15),'host_start_reserve')
        g=[x.strip() for x in run(['nvidia-smi','--id='+GPU,'--query-gpu=uuid,memory.total,memory.free,temperature.gpu','--format=csv,noheader,nounits']).split(',')]
        require(g[0]==GPU and float(g[2])>=float(g[1])*.93 and float(g[3])<85,'gpu_start_reserve')
        require(not run(['docker','ps','-q','--filter','name=^/llmctl-glm-']),'historical_glm_running')
        self.ecc()

    def create_candidate(self,job):
        with self.transaction() as (lease,guard):
            self.admission(lease)
            _,config=self.verify_sources()
            receipt=protected('/data/logs/h008-flash-phase1-20260926/DOWNLOAD-STATUS.json',(0o600,),1024*1024)
            weights=json.loads(receipt)
            require(sha(receipt)==config['download_receipt_sha256'] and weights.get('status')=='VERIFIED_COMPLETE' and weights.get('revision')=='eb9eb208eb0d988989d07a6a12d0fdeb5f52574a','weights_receipt_changed')
            require(config.get('numa_seccomp_sha256')==self.owner.NUMA_SECCOMP_SHA256,'numa_seccomp_mismatch')
            args=['docker','create','--name',NAME,'--network','host','--read-only','--cap-drop','ALL',
                  '--security-opt','no-new-privileges','--security-opt','seccomp='+BASE+'/source/numa-seccomp.json',
                  '--log-driver','local','--log-opt','max-size=64m','--log-opt','max-file=2','--restart','no',
                  '--cpuset-cpus','0-71','--memory',str(self.owner.MEMORY),'--memory-swap',str(self.owner.MEMORY),
                  '--shm-size','16g','--gpus','device='+GPU,'--label','io.llm-frontier.owner='+OWNER,
                  '--label','io.llm-frontier.gpu='+GPU,'--label','io.h011.job='+job['nonce'],
                  '--entrypoint','/opt/conda/bin/python']
            for k,v in self.owner.environment().items():args+=['--env',k+'='+v]
            for target,(source,writable) in self.owner.mounts().items():
                if target=='/runtime':source=STAGE
                args+=['--mount','type=bind,src='+source+',dst='+target+('' if writable else ',readonly')]
            args += [IMAGE,'-I','-B','/runtime/file_auth.py','--profile','manual1m']
            # Persist create intent before the side effect. Unknown create outcome
            # is never rediscovered by name and silently adopted or removed.
            job['status']='CREATING_CANDIDATE';self.save(PREFIX+'-OWNER.json',job)
            job['candidate_id']=run(args,60)
            self.validate_candidate(inspect(job['candidate_id']),job)
            job['status']='CANDIDATE_CREATED';self.save(PREFIX+'-OWNER.json',job)
            run(['docker','start',job['candidate_id']],60)

    def verify_capacity(self,port,context):
        data=self.call(port,'/get_server_info')
        def field(key):return next((i[key] for i in [data,*data.get('internal_states',[])] if key in i),None)
        expected={'context_length':context,'max_total_tokens':context,'max_total_num_tokens':context,
                  'max_req_input_len':context-6,'max_running_requests':1,'kv_cache_dtype':'fp8_e4m3',
                  'kt_cpuinfer':64,'kt_threadpool_count':8,'kt_numa_nodes':list(range(8)),
                  'disable_radix_cache':True,'chunked_prefill_size':2048,'kt_gpu_prefill_token_threshold':2048}
        got={k:field(k) for k in expected};require(got==expected,'actual_native_allocation_or_settings_mismatch')
        return got

    def stop_candidate(self,job):
        if not job.get('candidate_id'):
            require(not run(['docker','ps','-aq','--filter','name=^/'+NAME+'$']),'unknown_created_candidate')
            return
        with self.transaction():
            c=inspect(job['candidate_id']);self.validate_candidate(c,job)
            if not stopped(c):run(['docker','stop','--time','30',job['candidate_id']],45)
            c=inspect(job['candidate_id']);self.validate_candidate(c,job)
            require(stopped(c),'candidate_stop_unconfirmed')
            # Confirm captured cgroup has no remaining process before rollback.
            if job.get('candidate_cgroup'):
                procs=Path(job['candidate_cgroup'],'cgroup.procs')
                require(not procs.exists() or not procs.read_text().strip(),'candidate_cgroup_unsettled')
            job['candidate_stop_confirmed_utc']=now();job['status']='CANDIDATE_STOP_CONFIRMED'
            self.save(PREFIX+'-OWNER.json',job)
            # Retain stopped exact container/evidence; no destructive removal.

    def restore(self,job,before,deadline):
        with self.transaction() as (lease,_):
            self.stop_candidate(job)
            config,state,c=self.original()
            require(sha(protected(BASE+'/state.json',(0o600,)))==before['state_sha256'],'original_state_changed')
            require(c['Id']==before['container_id'],'original_container_changed')
            self.owner.operate('resume',borrowed=lease)
        while time.monotonic()<deadline:
            try:
                require(self.call(30010,'/v1/readiness').get('ready') is True,'restored_not_ready')
                job['restored_capacity']=self.verify_capacity(30010,480000)
                require(self.others()==before['other_three'],'other_models_changed')
                self.ecc();job['status']='FAILED_CANDIDATE_STOPPED_480K_RESTORED';job['restored_utc']=now()
                self.save(PREFIX+'-OWNER.json',job);return
            except (OSError,ValueError,http.client.HTTPException):time.sleep(2)
        raise ValueError('restoration_deadline')

def initialize_driver(ops,job):
    driver=load_module('h011_request_driver',STAGE+'/request_driver.py')
    from install.storage_io import AnchoredRoot
    driver.LOG,driver.GPU,driver.NAME,driver.MODEL=LOG,GPU,NAME,'glm-5.3-flash'
    driver.PREFIX=PREFIX;driver.MODE='startup';driver.REQUEST_CAP=300
    driver.GLOBAL_END=job['hard_end_epoch']-BUDGET['restore']
    driver.key=ops.key.decode();driver.transaction=ops.transaction;driver.s=ops.storage;driver.AnchoredRoot=AnchoredRoot
    def status(path,value,guard):
        with AnchoredRoot(str(Path(path).parent),guard) as a:a.atomic_json(Path(path).name,value)
    driver.status=status;driver.stop_event=threading.Event();driver.persist_lock=threading.Lock()
    driver.samples=[];driver.raw_batches={};driver.raw_cursors={};driver.raw_bytes=0
    driver.active_connection=driver.active_response=driver.cancel_reason=None
    driver.result={'status':'STARTING','start_utc':now(),'nonce':job['nonce'],'requests':{},'active_request':None,
                   'automatic_retry':False,'native_active_counter':'UNAVAILABLE; fresh human settlement acknowledgement plus supplemental live observations, no atomic drain claim',
                   'source_manifest_sha256':job['source_manifest_sha256']}
    driver.thermal_limit=85;driver.baseline_events={}
    return driver

def job_run():
    ops=Ops();job=ops.read(PREFIX+'-OWNER.json')
    require(job['status'] in ('OWNED_BEFORE_DISPATCH','DISPATCHED'),'job_not_dispatchable')
    require(job['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'dispatch_boot_changed')
    require(job['source_manifest_sha256']==ops.stage_hash,'dispatch_source_changed')
    # Parent start owns the same lease briefly while systemd acknowledges exec.
    end=time.monotonic()+30
    while True:
        try:ctx=ops.acquire(blocking=False);ops.lease=ctx.__enter__();break
        except Exception:
            if time.monotonic()>=end:raise
            time.sleep(.25)
    driver=None;sampler=writer=None;before=None;claimed=False;success_decided=False
    try:
        job=ops.read(PREFIX+'-OWNER.json')
        require(job['status'] in ('OWNED_BEFORE_DISPATCH','DISPATCHED'),'duplicate_or_stale_job_no_replay')
        ops.save(PREFIX+'-CLAIM.json',{'nonce':job['nonce'],'pid':os.getpid(),'utc':now()},exclusive=True)
        claimed=True
        def early_signal(signum,frame):
            if driver:driver.cancel('signal_'+str(signum))
            raise InterruptedError('owned_job_aborted')
        signal.signal(signal.SIGTERM,early_signal);signal.signal(signal.SIGINT,early_signal)
        job['status']='JOB_RUNNING';ops.save(PREFIX+'-OWNER.json',job)
        require(time.time()<job['hard_end_epoch']-BUDGET['main']-BUDGET['restore'],'dispatch_too_late')
        with ops.transaction():
            config,state,c=ops.original();require(c['State']['Running'],'original_not_running')
            ops.idle_precondition();ops.verify_capacity(30010,480000)
            before={'container_id':c['Id'],'state':state,'source_sha256':config['source_sha256'],'state_sha256':sha(protected(BASE+'/state.json',(0o600,))),
                    'config_sha256':sha(protected(BASE+'/config.json',(0o600,))),'other_three':ops.others(),'ecc':ops.ecc()}
            job['before']=before;job['status']='BEFORE_STATE_DURABLE';ops.save(PREFIX+'-OWNER.json',job)
            job['status']='HALTING_ORIGINAL';ops.save(PREFIX+'-OWNER.json',job)
            ops.owner.operate('halt',borrowed=ops.lease)
            require(stopped(inspect(before['container_id'])),'original_halt_unconfirmed')
            require(sha(protected(BASE+'/state.json',(0o600,)))==before['state_sha256'],'halt_changed_original_intent')
        startup_end=min(time.monotonic()+BUDGET['startup'],time.monotonic()+job['hard_end_epoch']-time.time()-BUDGET['restore'])
        ops.create_candidate(job)
        driver=initialize_driver(ops,job)
        c=inspect(job['candidate_id']);ops.validate_candidate(c,job)
        require(c['State']['Running'] and c['State']['Pid']>0,'candidate_start_failed')
        rel=Path('/proc',str(c['State']['Pid']),'cgroup').read_text().strip().split(':',2)[2]
        driver.cgroup_root=Path('/sys/fs/cgroup'+rel)
        job['candidate_cgroup']=str(driver.cgroup_root);ops.save(PREFIX+'-OWNER.json',job)
        require(int((driver.cgroup_root/'memory.max').read_text())==ops.owner.MEMORY and int((driver.cgroup_root/'memory.swap.max').read_text())==0,'candidate_cgroup_changed')
        driver.result['baseline']=driver.sample();driver.baseline_events=driver.result['baseline']['memory.events']
        driver.samples.append(driver.result['baseline']);require(not driver.resource_reason(driver.result['baseline']),'baseline_resource_guard')
        sampler=threading.Thread(target=driver.sampling,daemon=True);sampler.start()
        writer=threading.Thread(target=driver.periodic_writer,daemon=True);writer.start()
        def on_signal(signum,frame):
            driver.cancel('signal_'+str(signum));raise InterruptedError('owned_job_aborted')
        signal.signal(signal.SIGTERM,on_signal);signal.signal(signal.SIGINT,on_signal)
        while True:
            require(not driver.cancel_reason,'startup_resource_abort')
            require(time.monotonic()<startup_end,'startup_allocation_deadline')
            c=inspect(job['candidate_id']);ops.validate_candidate(c,job);require(c['State']['Running'],'candidate_exited')
            try:
                if ops.call(30011,'/v1/readiness',timeout=5).get('ready'):break
            except (OSError,ValueError,http.client.HTTPException):pass
            time.sleep(2)
        driver.result['native_capacity']=ops.verify_capacity(30011,1048576)
        # Allocation assertion inside pinned candidate idle.py additionally checks
        # max_req_len=context-1 and runs the unchanged SM120 execution check.
        sys.path.insert(0,STAGE)
        fixture=load_module('h011_fixture_1m',STAGE+'/fixture_1m.py')
        from context_profile import verify_count
        driver.MODE='short';driver.REQUEST_CAP=BUDGET['short']
        short=fixture.short_payload();count=ops.call(30011,'/v1/tokenize',short)
        require(type(count.get('count')) is int and 1<=count['count']<=128 and count['context_limit']==1048576,'short_native_count_invalid')
        verify_count(count,target=count['count'],output=32)
        driver.result['short_count']=count
        row=driver.stream(short);driver.result['requests']['short']=row
        require(row['status']=='TRANSPORT_PASS' and row['input_tokens']==count['count'] and row['output_tokens']<=32,'short_qualification_failed')
        ops.verify_capacity(30011,1048576)
        driver.MODE='exact1m';driver.REQUEST_CAP=BUDGET['main']
        require(not driver.cancel_reason,'resource_abort_before_fixture')
        # Inside exact candidate with same pinned native tokenizer/template.
        fixture_end=time.monotonic()+BUDGET['fixture']
        built=json.loads(run(['docker','exec',job['candidate_id'],'/opt/conda/bin/python','-I','-B','/runtime/fixture_1m.py','--seed',job['nonce']],BUDGET['fixture']))
        payload=built.pop('payload');built.pop('content')
        require(payload['max_tokens']==1024,'main_output_reserve_invalid')
        require(time.monotonic()<fixture_end,'fixture_count_deadline')
        native_count=ops.call(30011,'/v1/tokenize',payload,timeout=min(120,fixture_end-time.monotonic()))
        require(time.monotonic()<fixture_end,'fixture_count_deadline')
        verify_count(native_count)
        driver.result['fixtures']={'exact1m':built|{'native_tokenize':native_count}}
        driver.buffer({'payload':payload,'fixture':built},'-FIXTURE.jsonl');driver.persist()
        with ops.transaction():
            ops.verify_sources();ops.validate_candidate(inspect(job['candidate_id']),job)
            require(stopped(inspect(before['container_id'])),'original_restarted_during_candidate')
            require(ops.others()==before['other_three'],'other_models_changed');ops.ecc()
            require(not driver.cancel_reason,'resource_abort_before_main')
        row=driver.stream(payload);driver.qualify(row,1000000);driver.result['requests']['exact1m']=row
        # Quiesce periodic writers before the final durable retention decision.
        driver.stop_event.set()
        sampler.join(15);writer.join(120)
        require(not sampler.is_alive() and not writer.is_alive(),'telemetry_writer_not_settled')
        final=driver.sample();driver.samples.append(final)
        resource=driver.resource_reason(final) or driver.cancel_reason
        with ops.transaction():
            ops.verify_sources();ops.validate_candidate(inspect(job['candidate_id']),job)
            require(inspect(job['candidate_id'])['State']['Running'],'candidate_not_retained_running')
            require(ops.others()==before['other_three'],'other_models_changed');ops.ecc()
            require(stopped(inspect(before['container_id'])),'original_restarted')
            require(sha(protected(BASE+'/state.json',(0o600,)))==before['state_sha256'] and sha(protected(BASE+'/config.json',(0o600,)))==before['config_sha256'],'original_files_changed')
            ops.verify_capacity(30011,1048576)
            final=driver.sample();driver.samples.append(final)
            resource=driver.resource_reason(final) or driver.cancel_reason
            require(retainable(row,resource,True),'main_acceptance_failed')
            success_decided=True
            job.update(status=RETAINED,finished_utc=now(),candidate_port=30011,context=1048576,
                       input_tokens=1000000,output_tokens=row['output_tokens'],candidate_restart='no',
                       reboot_behavior='Original desired=running 480K resumes; retained candidate is not production-promoted',
                       harness='MUST_REMAIN_PAUSED',final_resource_sample=final)
        # Monitor threads are settled; never invert persist_lock/write_lock.
        driver.result['status']=RETAINED;driver.result['finished_utc']=now();driver.persist()
        # Durable terminal owner is the retention authority. No ExecStopPost.
        ops.save(PREFIX+'-OWNER.json',job)
    except BaseException as exc:
        if not claimed:raise  # Never overwrite an existing/retained owner on replay.
        if success_decided:
            # All terminal gates passed; a late evidence write error cannot cause
            # destructive cleanup of a valid retained success. Preserve/quarantine.
            job['evidence_error_type']=type(exc).__name__
            job['status']='QUARANTINED_RETAINED_SUCCESS_EVIDENCE_WRITE_FAILED'
            ops.save(PREFIX+'-RETAINED-WARNING.json',job)
            return
        job['failure']={'type':type(exc).__name__,'code':str(exc) if isinstance(exc,(ValueError,AssertionError)) else 'owned_job_failed','utc':now()}
        # SIGTERM during cleanup must not interrupt exact-stop confirmation.
        signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGINT,signal.SIG_IGN)
        if driver:
            driver.cancel('cleanup_after_failure');driver.result['failure']=job['failure']
            if sampler:sampler.join(15)
            if writer:writer.join(120)
        try:
            # Confirm only the exact candidate stopped before original restart.
            # No socket-close inference and no name-only adoption on lost create.
            if before:
                ops.restore(job,before,time.monotonic()+BUDGET['restore'])
            else:
                job['status']='FAILED_BEFORE_MUTATION';ops.save(PREFIX+'-OWNER.json',job)
        except BaseException as cleanup:
            job['status']='QUARANTINED_REQUIRES_OWNER_REVIEW'
            job['cleanup_error_type']=type(cleanup).__name__;job['automatic_restore_blocked']=True
            ops.save(PREFIX+'-OWNER.json',job)
        if driver:
            driver.result['status']=job['status'];driver.result['finished_utc']=now();driver.persist()
    finally:
        if driver:
            driver.stop_event.set()
            if sampler:sampler.join(12)
            if writer:writer.join(20)
        ops.lease=None;ctx.__exit__(None,None,None)

def start(acknowledged):
    require(acknowledged,'fresh_harness_stopped_and_all_clients_settled_ack_required')
    ops=Ops()
    with ops.transaction() as (lease,_):
        ops.lease=lease
        try:
            require(not Path(LOG,PREFIX+'-OWNER.json').exists() and not Path(LOG,PREFIX+'.json').exists(),'duplicate_or_stale_job_no_replay')
            ops.idle_precondition();config,state,c=ops.original()
            manifest=protected(STAGE+'/candidate-sha256.json',(0o644,))
            job={'schema_version':1,'owner':OWNER,'nonce':uuid.uuid4().hex,'status':'OWNED_BEFORE_DISPATCH',
                 'started_utc':now(),'hard_end_epoch':time.time()+TOTAL,'phase_budgets_seconds':BUDGET,
                 'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 'source_manifest_sha256':sha(manifest),'image':IMAGE,'unit':UNIT,
                 'fresh_manual_prerequisite_acknowledged':True,'atomic_native_drain_claim':False,
                 'candidate_id':None,'automatic_retry':False,'success_policy':RETAINED}
            ops.save(PREFIX+'-OWNER.json',job,exclusive=True)
            # systemd owns the independent process. No ExecStop/Post removes models.
            run(['systemd-run','--unit='+UNIT,'--property=Type=exec','--property=RuntimeMaxSec='+str(TOTAL),
                 '--property=TimeoutStopSec=1830','--property=KillMode=control-group','--property=Restart=no',
                 '--property=UMask=0077','--property=StandardOutput=null','--property=StandardError=null',
                 '/usr/bin/python3','-I','-B',STAGE+'/manual.py','_run'],30)
            job['status']='DISPATCHED';job['dispatch_utc']=now();ops.save(PREFIX+'-OWNER.json',job)
        finally:
            ops.lease=None
    return {k:job[k] for k in ('status','unit','nonce','started_utc','phase_budgets_seconds','success_policy')}

def status_result(detail=False):
    ops=Ops();job=ops.read(PREFIX+'-OWNER.json')
    state=dict(line.split('=',1) for line in run(['systemctl','show',UNIT,'-p','ActiveState','-p','SubState','-p','MainPID','-p','Result']).splitlines())
    value={'owner':job,'unit':state}
    if Path(LOG,PREFIX+'.json').exists():value['result']=ops.read(PREFIX+'.json')
    if job['status'] not in TERMINAL and state['ActiveState'] in ('inactive','failed'):
        value['observation']='STALE_OR_UNCERTAIN_NO_REPLAY_REQUIRES_OWNER_REVIEW'
        value['effective_status']='QUARANTINED_REQUIRES_OWNER_REVIEW'
    if job['status']==RETAINED:
        c=inspect(job['candidate_id']);ops.validate_candidate(c,job)
        value['retained_currently_running']=c['State']['Running']
        value['retained_same_boot']=job['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if detail:return value
    result=value.get('result',{});request=result.get('request') or {};sample=result.get('latest_telemetry') or {}
    return {'status':job['status'],'effective_status':value.get('effective_status',job['status']),
            'unit':state,'candidate_id':job.get('candidate_id'),'request_phase':request.get('phase'),
            'native_usage':request.get('usage'),'ttft_seconds':request.get('ttft_seconds'),
            'request_kind':result.get('active_request'),'request_body_sent_utc':request.get('request_body_sent_utc'),
            'request_deadline_utc':request.get('request_deadline_utc'),
            'job_hard_end_utc':datetime.datetime.fromtimestamp(job['hard_end_epoch'],datetime.timezone.utc).isoformat(),
            'latest_sample_utc':sample.get('utc'),'gpu':sample.get('gpu'),'ram':sample.get('ram'),
            'retained_currently_running':value.get('retained_currently_running'),
            'retained_same_boot':value.get('retained_same_boot'),
            'owner_receipt':LOG+'/'+PREFIX+'-OWNER.json','result_receipt':LOG+'/'+PREFIX+'.json'}

def plan():
    return {'status':'PREPARED_OFFLINE_NOT_EXECUTED','main_input_tokens':1000000,'main_output_tokens_including_reasoning':1024,
            'configured_capacity':1048576,'production_default':480000,'phase_budgets_seconds':BUDGET,
            'normal_total_budget_seconds':TOTAL,'systemd_final_stop_grace_seconds':1830,
            'absolute_supervisor_max_seconds':TOTAL+1830,'success':RETAINED,
            'failure':'Confirm exact candidate stop then original owner 480K restore; quarantine uncertainty',
            'main_http_request_hard_limit_seconds':7200,
            'owned_candidate_stop_grace_seconds':30,'owned_stop_command_timeout_seconds':45,
            'native_socket_close_is_drain_proof':False,
            'retained_after_job_exit':True,'reboot_restores_original_480k':True,
            'native_active_counter':'Unavailable; explicit fresh prerequisite, no atomic drain claim',
            'linear_planning_minutes':{'input1m':246.468*1000000/65536/60,'positions1048576':246.468*16/60}}

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('action',choices=['plan','start','status','result','_run'])
    p.add_argument('--ack-harness-stopped-and-clients-settled',action='store_true')
    p.add_argument('--dry-run',action='store_true',help='Print the offline plan; no host contact or mutation')
    a=p.parse_args()
    try:
        if a.action=='plan' or a.dry_run:value=plan()
        elif a.action=='start':value=start(a.ack_harness_stopped_and_clients_settled)
        elif a.action=='_run':job_run();return 0
        else:value=status_result(detail=a.action=='result')
        print(json.dumps(value,indent=2));return 0
    except Exception as exc:
        print(json.dumps({'status':'REFUSED_OR_BLOCKED','type':type(exc).__name__,
                          'code':str(exc) if isinstance(exc,(ValueError,AssertionError)) else 'protected_operation_failed'}));return 2

if __name__=='__main__':raise SystemExit(main())
