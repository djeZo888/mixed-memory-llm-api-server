#!/usr/bin/env python3
"""Separate H008 frontier lifecycle; fixed UUID, canonical lease, registered paths.

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

BASE='/data/services/flash-h008-20260926'
LOG='/data/logs/flash-h008-20260926'
MODEL='/data/models-large/glm-5.3-flash-eb9eb208'
NAME='llm-frontier-flash'
OWNER='H008-FLASH-20260926'
GPU='GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
IMAGE='sha256:51791e17c0149019e2ddc032d8c1b2f60b86c3a6c293daff639e20053baa858a'
MEMORY=650*1024**3
GUARDS={'scripts/common/registered-storage.py':'21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d',
'scripts/install/storage.py':'4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505',
'scripts/install/storage_io.py':'5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a',
'scripts/common/lifecycle_lease.py':'483ba038c62a8b4633449cef9c0f9a6664c00276662498abc748b58c8be644e0'}


def require(ok, code):
    if not ok: raise ValueError(code)


def mounts():
    return {'/models':(MODEL,False), '/runtime':(BASE+'/source',False),
            '/cache':(BASE+'/cache',True), '/tmp':(BASE+'/tmp',True),
            '/run/secrets/llm-api-key':('/data/services/secrets/llm-api-key',False)}


def environment():
    return {'CUDA_VISIBLE_DEVICES':GPU,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                         'HF_HOME':'/cache/huggingface','XDG_CACHE_HOME':'/cache','SGLANG_CACHE_DIR':'/cache/sglang',
                         'SGLANG_JIT_CACHE_DIR':'/cache/sglang/jit','TRITON_CACHE_DIR':'/cache/triton',
                         'TORCHINDUCTOR_CACHE_DIR':'/cache/torchinductor','FLASHINFER_WORKSPACE_BASE':'/cache/flashinfer',
                         'CUDA_CACHE_PATH':'/cache/cuda','TMPDIR':'/tmp','OMP_NUM_THREADS':'1',
                         'DISABLE_OPENAPI_DOC':'1','SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN':'1'}

def validate_container(c, config, state):
    """Pure admission proof reused by Qwen and passive node observation."""
    require(config.get('owner')==OWNER and config.get('image_id')==IMAGE
            and state.get('owner')==OWNER and state.get('schema_version')==1, 'frontier_config_invalid')
    identity=state.get('container') or {}
    require(c.get('Id')==identity.get('id') and c.get('Image')==IMAGE
            and c.get('Name')=='/'+NAME and identity.get('name')==NAME
            and identity.get('image_id')==IMAGE, 'frontier_identity_invalid')
    host=c.get('HostConfig',{});native=c.get('Config',{})
    req=host.get('DeviceRequests')
    require(isinstance(req,list) and len(req)==1 and req[0].get('DeviceIDs')==[GPU]
            and req[0].get('Capabilities')==[['gpu']] and req[0].get('Count')==0
            and not host.get('Privileged') and not host.get('Devices')
            and host.get('ReadonlyRootfs') is True and host.get('NetworkMode')=='host'
            and host.get('RestartPolicy')=={'Name':'no','MaximumRetryCount':0}
            and host.get('Memory')==host.get('MemorySwap')==MEMORY
            and host.get('CpusetCpus')=='0-71' and host.get('CapDrop')==['ALL']
            and host.get('SecurityOpt')==['no-new-privileges']
            and host.get('LogConfig',{}).get('Type')=='local', 'frontier_containment_invalid')
    expected=mounts();actual=c.get('Mounts',[])
    require(len(actual)==len(expected) and {x.get('Destination') for x in actual}==set(expected)
            and all(x.get('Type')=='bind' and (x.get('Source'),x.get('RW'))==expected[x['Destination']] for x in actual),
            'frontier_mounts_invalid')
    require(native.get('Entrypoint')==['/opt/conda/bin/python']
            and native.get('Cmd')==['-I','-B','/runtime/file_auth.py']
            and native.get('Labels',{}).get('io.llm-frontier.owner')==OWNER
            and native.get('Labels',{}).get('io.llm-frontier.gpu')==GPU, 'frontier_launch_invalid')
    env=dict(x.split('=',1) for x in native.get('Env',[]) if '=' in x)
    base_env=dict(x.split('=',1) for x in config.get('image_env',[]) if '=' in x)
    require(env == {**base_env, **environment()} and len(native.get('Env',[]))==len(env), 'frontier_environment_invalid')


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


def operate(action, *, borrowed=None):
    s=storage()
    from common.lifecycle_lease import acquire_lease
    from install.storage_io import MountedStorageGuard,AnchoredRoot
    from control.installation import protected_file
    with (contextlib.nullcontext(borrowed) if borrowed is not None else acquire_lease(blocking=False)) as lease:
        lease.validate()
        with MountedStorageGuard(s) as g:
            for path in [BASE,LOG,MODEL,'/data/docker','/data/containerd','/data/services/secrets/llm-api-key']: g.check_path(path)
            s.root_payload_guard()
            config=json.loads(protected_file(Path(BASE+'/config.json'),modes={0o600}))
            for n,h in config['source_sha256'].items():
                require('/' not in n and hashlib.sha256(protected_file(Path(BASE+'/source/'+n),modes={0o644})).hexdigest()==h,'frontier_source_drift')
            with AnchoredRoot(BASE,g) as a:
                state=json.loads(protected_file(Path(BASE+'/state.json'),modes={0o600}))
                if action=='resume' and state.get('desired') != 'running': return
                found=subprocess.check_output(['docker','ps','-aq','--no-trunc','--filter','name=^/'+NAME+'$'],text=True).strip()
                if found:
                    c=json.loads(subprocess.check_output(['docker','inspect',found],text=True))[0]
                    validate_container(c,config,state)
                    if action in ('stop','halt'):
                        subprocess.run(['docker','stop','--time','30',found],check=True,stdout=subprocess.DEVNULL)
                        if action=='stop': state['desired']='stopped'
                        a.atomic_json('state.json',state);s.root_payload_guard();return
                    if c['State']['Running']: s.root_payload_guard();return
                elif state.get('container') is not None:
                    raise ValueError('frontier_saved_container_missing')
                if action in ('stop','halt'):
                    if action=='stop': state['desired']='stopped'
                    a.atomic_json('state.json',state);s.root_payload_guard();return
                receipt=json.loads(protected_file(Path('/data/logs/h008-flash-phase1-20260926/DOWNLOAD-STATUS.json'),modes={0o600},maximum=1024*1024))
                require(receipt.get('status')=='VERIFIED_COMPLETE' and receipt.get('revision')=='eb9eb208eb0d988989d07a6a12d0fdeb5f52574a','flash_weights_not_verified')
                require(hashlib.sha256(Path('/data/logs/h008-flash-phase1-20260926/DOWNLOAD-STATUS.json').read_bytes()).hexdigest()==config['download_receipt_sha256'],'flash_weights_receipt_changed')
                from lifecycle.storage_binding import RegisteredStorageBinding
                from lifecycle.manager import StorageRunner
                from lifecycle.hardware_policy import HardwarePolicy,RegisteredLatchStore
                from control.node_collectors import boot_identity
                binding=RegisteredStorageBinding.read_registered(StorageRunner())
                def boot():
                    value=boot_identity();return {'boot_id':value['boot_id'],'uptime_seconds':value['boot_age_seconds']}
                HardwarePolicy(RegisteredLatchStore(binding,lease=lease),lease=lease,
                    run=lambda argv,timeout=2:subprocess.check_output(argv,timeout=timeout,text=True),boot=boot).require_start([GPU],boot_restore=action=='resume')
                mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()}
                require(mem['MemAvailable'] >= MEMORY + int(mem['MemTotal']*.15), 'flash_host_reserve_insufficient')
                gpu=subprocess.check_output(['nvidia-smi','--id='+GPU,'--query-gpu=uuid,memory.total,memory.free,temperature.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',')
                require(gpu[0].strip()==GPU and int(gpu[2])>=int(gpu[1])*.93 and int(gpu[3])<85,'flash_gpu_admission_failed')
                # Keep historical full GLM stopped before admitting Flash.
                require(not subprocess.check_output(['docker','ps','-q','--filter','name=^/llmctl-glm-'],text=True).strip(),'historical_glm_running')
                if not found:
                    argv=['docker','create','--name',NAME,'--network','host','--read-only','--cap-drop','ALL',
                          '--security-opt','no-new-privileges','--log-driver','local','--log-opt','max-size=64m','--log-opt','max-file=2','--restart','no',
                          '--cpuset-cpus','0-71','--memory',str(MEMORY),'--memory-swap',str(MEMORY),
                          '--shm-size','16g','--gpus','device='+GPU,'--label','io.llm-frontier.owner='+OWNER,
                          '--label','io.llm-frontier.gpu='+GPU,'--entrypoint','/opt/conda/bin/python']
                    env=environment()
                    for k,v in env.items(): argv+=['--env',k+'='+v]
                    for target,(source,writable) in mounts().items():
                        argv+=['--mount','type=bind,src='+source+',dst='+target+('' if writable else ',readonly')]
                    argv += [IMAGE,'-I','-B','/runtime/file_auth.py']
                    found=subprocess.check_output(argv,text=True).strip()
                    state['container']={'id':found,'name':NAME,'image_id':IMAGE}
                state['desired']='running';a.atomic_json('state.json',state)
                validate_container(json.loads(subprocess.check_output(['docker','inspect',found],text=True))[0],config,state)
                subprocess.run(['docker','start',found],check=True,stdout=subprocess.DEVNULL)
                s.root_payload_guard()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','stop','resume','halt']);a=p.parse_args()
    operate(a.action)

if __name__=='__main__': main()
