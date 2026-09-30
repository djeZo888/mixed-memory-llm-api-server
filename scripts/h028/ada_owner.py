#!/usr/bin/env python3
"""Separate H028 Ada Qwen lifecycle; fixed UUID, canonical lease, registered paths.

Import is inert. CLI start/stop is operator-only; passive node integration grants
no service action API authority. Existing Qwen/image owners remain independent.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys

BASE='/data/services/qwen-ada200k-h028-20260929'
LOG='/data/logs/qwen-ada200k-h028-20260929'
MODEL='/data/models-large/qwen38-27b-fp8'
NAME='llm-qwen-ada200k-h028'
OWNER='H028-ADA200K-20260929'
GPU='GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
IMAGE='sha256:0aa2afe62c04fdd4f06a38229e6941cb1e47f6b7c0863698b708f299d4f15ddf'
MEMORY=64*1024**3
NUMA_SECCOMP_SHA256='5eebab079391a29eecdaa2cd8483b4cd76ce38e9baa4ade238494c0a71cf481f'
GUARDS={'scripts/common/registered-storage.py':'21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d',
'scripts/install/storage.py':'4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505',
'scripts/install/storage_io.py':'5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a',
'scripts/common/lifecycle_lease.py':'483ba038c62a8b4633449cef9c0f9a6664c00276662498abc748b58c8be644e0'}


def require(ok, code):
    if not ok: raise ValueError(code)


def mounts():
    return {'/models':(MODEL,False), '/runtime':(BASE+'/source',False),
            '/opt/llmctl/sglang38_file_auth.py':('/data/services/llm-manager/adapters/sglang38_file_auth.py',False),
            '/cache':(BASE+'/cache',True), '/tmp':(BASE+'/tmp',True),
            '/run/secrets/llm-api-key':('/data/services/secrets/llm-api-key',False)}


def environment():
    return {'CUDA_VISIBLE_DEVICES':GPU,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                         'HF_HOME':'/cache/huggingface','XDG_CACHE_HOME':'/cache','SGLANG_CACHE_DIR':'/cache/sglang',
                         'SGLANG_JIT_CACHE_DIR':'/cache/sglang/jit','TRITON_CACHE_DIR':'/cache/triton',
                         'TORCHINDUCTOR_CACHE_DIR':'/cache/torchinductor','FLASHINFER_WORKSPACE_BASE':'/cache/flashinfer',
                         'CUDA_CACHE_PATH':'/cache/cuda','TMPDIR':'/tmp','OMP_NUM_THREADS':'1',
                         'DISABLE_OPENAPI_DOC':'1','SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN':'1'}


def security_options_valid(options, config):
    """Accept only the configured exact Docker profile plus three NUMA calls."""
    if config.get('numa_seccomp_sha256') is None:
        return options == ['no-new-privileges']
    if config['numa_seccomp_sha256'] != NUMA_SECCOMP_SHA256 or not isinstance(options, list):
        return False
    if len(options) != 2 or options[0] != 'no-new-privileges' or not options[1].startswith('seccomp='):
        return False
    try:
        profile = json.loads(options[1].split('=', 1)[1])
        return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == NUMA_SECCOMP_SHA256
    except (ValueError, TypeError):
        return False

def validate_container(c, config, state):
    """Pure admission proof reused by Qwen and passive node observation."""
    require(config.get('owner')==OWNER and config.get('image_id')==IMAGE
            and state.get('owner')==OWNER and state.get('schema_version')==1, 'ada_config_invalid')
    identity=state.get('container') or {}
    require(c.get('Id')==identity.get('id') and c.get('Image')==IMAGE
            and c.get('Name')=='/'+NAME and identity.get('name')==NAME
            and identity.get('image_id')==IMAGE, 'ada_identity_invalid')
    host=c.get('HostConfig',{});native=c.get('Config',{})
    req=host.get('DeviceRequests')
    require(isinstance(req,list) and len(req)==1 and req[0].get('DeviceIDs')==[GPU]
            and req[0].get('Capabilities')==[['gpu']] and req[0].get('Count')==0
            and not host.get('Privileged') and not host.get('Devices')
            and host.get('ReadonlyRootfs') is True and host.get('NetworkMode')=='bridge'
            and host.get('PortBindings')=={'30014/tcp':[{'HostIp':'127.0.0.1','HostPort':'30014'}]}
            and host.get('RestartPolicy')=={'Name':'no','MaximumRetryCount':0}
            and host.get('Memory')==host.get('MemorySwap')==MEMORY
            and host.get('CpusetCpus')=='0-71' and host.get('CapDrop')==['ALL']
            and security_options_valid(host.get('SecurityOpt'),config)
            and host.get('LogConfig',{}).get('Type')=='local', 'ada_containment_invalid')
    expected=mounts();actual=c.get('Mounts',[])
    require(len(actual)==len(expected) and {x.get('Destination') for x in actual}==set(expected)
            and all(x.get('Type')=='bind' and (x.get('Source'),x.get('RW'))==expected[x['Destination']] for x in actual),
            'ada_mounts_invalid')
    require(native.get('Entrypoint')==['/opt/sglang/bin/python']
            and native.get('Cmd')==['-I','-B','/runtime/ada_launcher.py','--slot','ada200k']
            and native.get('Labels',{}).get('io.llm-ada200k.owner')==OWNER
            and native.get('Labels',{}).get('io.llm-ada200k.gpu')==GPU, 'ada_launch_invalid')
    env=dict(x.split('=',1) for x in native.get('Env',[]) if '=' in x)
    base_env=dict(x.split('=',1) for x in config.get('image_env',[]) if '=' in x)
    require(env == {**base_env, **environment()} and len(native.get('Env',[]))==len(env), 'ada_environment_invalid')


def storage():
    root=Path('/usr/local/lib/llm-server/control-api')
    for n,h in GUARDS.items(): require(hashlib.sha256((root/n).read_bytes()).hexdigest()==h,'installed_guard_mismatch')
    sys.path.insert(0,str(root/'scripts'))
    from install.storage import Storage
    class Runner:
        def run(self,argv,*,timeout=30,env=None): return subprocess.check_output(argv,timeout=timeout,text=True,env=env)
    r=Storage({},Runner()).read_registration()
    require(r['data']['uuid']=='8daf56f1-5649-4163-9d87-919c2d271875'
            and r['models']['uuid']=='a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
            and r['data']['path']=='/data' and r['models']['path']=='/data/models-large', 'registered_identity_changed')
    return Storage({'data_dir':r['data']['path'],'data_uuid':r['data']['uuid'],
        'model_dir':r['models']['path'],'model_uuid':r['models']['uuid'],'storage_mode':r['storage_mode']},Runner())


def require_port_available(port=30014):
    # Reuse permits a recently closed TCP connection in TIME_WAIT, never an
    # active listener. Docker still performs the authoritative bind on start.
    import socket
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind(('127.0.0.1',port))


def operate(action):
    s=storage()
    from common.lifecycle_lease import acquire_lease
    from install.storage_io import MountedStorageGuard, AnchoredRoot
    from control.installation import protected_file
    with acquire_lease(blocking=False) as lease:
        lease.validate()
        with MountedStorageGuard(s) as guard:
            for path in [BASE,LOG,MODEL,'/data/docker','/data/containerd','/data/services/secrets/llm-api-key']:
                guard.check_path(path)
            s.root_payload_guard()
            config=json.loads(protected_file(Path(BASE+'/config.json'),modes={0o600}))
            for name,sha in config['source_sha256'].items():
                require('/' not in name and hashlib.sha256(protected_file(Path(BASE+'/source/'+name),modes={0o644})).hexdigest()==sha,'ada_source_drift')
            require(hashlib.sha256(protected_file(Path('/data/services/llm-manager/adapters/sglang38_file_auth.py'),modes={0o644})).hexdigest()=='e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4','ada_auth_drift')
            with AnchoredRoot(BASE,guard) as anchored:
                state=json.loads(protected_file(Path(BASE+'/state.json'),modes={0o600}))
                found=subprocess.check_output(['docker','ps','-aq','--no-trunc','--filter','name=^/'+NAME+'$'],text=True).strip()
                if found:
                    c=json.loads(subprocess.check_output(['docker','inspect',found],text=True))[0]
                    validate_container(c,config,state)
                    if action=='stop':
                        subprocess.run(['docker','stop','--time','30',found],check=True,timeout=40,stdout=subprocess.DEVNULL)
                        state['desired']='stopped';anchored.atomic_json('state.json',state);return
                    require(not c['State']['Running'],'ada_already_running')
                else:
                    require(state.get('container') is None,'ada_saved_container_missing')
                    if action=='stop':return
                require(action=='start','ada_action_invalid')
                from lifecycle.storage_binding import RegisteredStorageBinding
                from lifecycle.manager import StorageRunner
                from lifecycle.hardware_policy import HardwarePolicy,RegisteredLatchStore
                from control.node_collectors import boot_identity
                binding=RegisteredStorageBinding.read_registered(StorageRunner())
                def boot():
                    value=boot_identity();return {'boot_id':value['boot_id'],'uptime_seconds':value['boot_age_seconds']}
                HardwarePolicy(RegisteredLatchStore(binding,lease=lease),lease=lease,
                    run=lambda argv,timeout=2:subprocess.check_output(argv,timeout=timeout,text=True),boot=boot).require_start([GPU],boot_restore=False)
                require_port_available()
                gpu=subprocess.check_output(['nvidia-smi','--id='+GPU,'--query-gpu=uuid,memory.total,memory.free,temperature.gpu','--format=csv,noheader,nounits'],text=True,timeout=5).strip().split(',')
                require(gpu[0].strip()==GPU and int(gpu[2])>=int(gpu[1])*.93 and int(gpu[3])<70,'ada_gpu_admission_failed')
                apps=subprocess.check_output(['nvidia-smi','--id='+GPU,'--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True,timeout=5)
                require(not apps.strip(),'ada_gpu_has_process')
                require(subprocess.check_output(['systemctl','is-active','local-ai-fan-boost.service'],text=True).strip()=='active','ada_fan_not_active')
                for name,sha in config['model_metadata_sha256'].items():
                    require('/' not in name and hashlib.sha256(Path(MODEL,name).read_bytes()).hexdigest()==sha,'ada_model_metadata_drift')
                if not found:
                    argv=['docker','create','--name',NAME,'--network','bridge','--publish','127.0.0.1:30014:30014','--read-only','--cap-drop','ALL',
                          '--security-opt','no-new-privileges','--log-driver','local','--log-opt','max-size=64m','--log-opt','max-file=2','--restart','no',
                          '--cpuset-cpus','0-71','--memory',str(MEMORY),'--memory-swap',str(MEMORY),'--shm-size','16g','--gpus','device='+GPU,
                          '--label','io.llm-ada200k.owner='+OWNER,'--label','io.llm-ada200k.gpu='+GPU,'--entrypoint','/opt/sglang/bin/python']
                    for k,v in environment().items():argv+=['--env',k+'='+v]
                    for target,(source,writable) in mounts().items():argv+=['--mount','type=bind,src='+source+',dst='+target+('' if writable else ',readonly')]
                    argv += [IMAGE,'-I','-B','/runtime/ada_launcher.py','--slot','ada200k']
                    state['pending_create']={'name':NAME,'image':IMAGE};anchored.atomic_json('state.json',state)
                    found=subprocess.check_output(argv,text=True,timeout=30).strip()
                    state['container']={'id':found,'name':NAME,'image_id':IMAGE}
                state['desired']='running';state.pop('pending_create',None);anchored.atomic_json('state.json',state)
                validate_container(json.loads(subprocess.check_output(['docker','inspect',found],text=True))[0],config,state)
                subprocess.run(['docker','start',found],check=True,timeout=30,stdout=subprocess.DEVNULL)
                s.root_payload_guard()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop']);a=p.parse_args();operate(a.action)

if __name__=='__main__':main()
