#!/usr/bin/env python3
"""Offline image-only review packets. No transport, lifecycle or inference mode.

Plans are deliberately non-executable. No runtime/service module is imported.
Source fixtures, configured profiles and a registry UUID never qualify a GPU.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re

BASE_COMMIT = '9785456b351d5e5620367fee4919348a808f2c32'
GPU = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
READING_GPU = 'GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
SGLANG = '0cd8be351d0825488f4b81c8931167bbab618eca'
MANIFEST = 'sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef'
OCI_CONFIG = 'sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad'
PARENT = 'sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8'
BASE = '/data/services/image21-runtime-20260923'
RELEASE = '/data/services/releases/h037-image-placement-20260930'
MODEL = '/data/models-large/qwen-image-2.1-' + REVISION
OWNER = 'IMAGE21-RUNTIME-20260923'
UNIT = 'llm-image-backend.service'
CONTAINER = 'llm-image-backend'
NETWORK = 'llm-image-backend-private'
API_CONFIG = '/etc/llm-server/image-api.json'
CANDIDATE = 'configs/image/h044-external-ada-candidate.json'
ROOT = Path(__file__).resolve().parents[2]


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    require(type(raw) is bytes and len(raw) <= 262144, 'json_size')
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'json_duplicate')
            value[key] = item
        return value
    def constant(_):
        raise Refused('json_nonfinite')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json_invalid') from None
    def bound(item, depth=0):
        require(depth <= 12, 'json_depth')
        if type(item) in (dict, list):
            require(len(item) <= 256, 'json_count')
            for child in (item.values() if type(item) is dict else item):
                bound(child, depth + 1)
        elif type(item) is str:
            require(len(item) <= 16384, 'json_string')
    bound(value)
    return value


def fixed_paths(root=ROOT):
    declaration = strict_json((root / 'scripts/image_runtime/source-closure.json').read_bytes())
    require(declaration['runtime_root'] == BASE and declaration['release_root'] == RELEASE,
            'closure_roots')
    tree = ast.parse((root / 'scripts/image_runtime/service.py').read_text())
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('RUNTIME_SOURCE_FILES', 'RELEASE_SOURCE_FILES'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    require(list(constants['RUNTIME_SOURCE_FILES']) == declaration['runtime_files']
            and list(constants['RELEASE_SOURCE_FILES']) == declaration['release_files'], 'closure_lists')
    paths = {}
    for name in declaration['runtime_files']:
        paths[BASE + '/source/' + name] = 'scripts/image_runtime/' + name
    for name in declaration['release_files']:
        paths[RELEASE + '/' + name] = name
    for name in declaration['image_api_files']:
        paths[declaration['image_api_root'] + '/' + name] = 'scripts/image_api/' + name
    paths[declaration['fixed_recovery_installed']] = declaration['fixed_recovery_source']
    paths['/etc/systemd/system/' + UNIT] = 'scripts/image_runtime/llm-image-backend.service'
    paths['/etc/systemd/system/llm-image-api.service'] = 'scripts/image_api/llm-image-api.service.in'
    return paths


def source_graph(root=ROOT):
    return [{'installedPath': installed, 'candidateSource': source,
             'sha256': sha((root / source).read_bytes()),
             'comparison': 'installed_substitutions_required' if source.endswith('.in') else 'raw_bytes'}
            for installed, source in fixed_paths(root).items()]


def source_maps(graph):
    runtime = {row['installedPath'][len(BASE + '/source/'):]: row['sha256'] for row in graph
               if row['installedPath'].startswith(BASE + '/source/')}
    release = {row['installedPath'][len(RELEASE + '/'):]: row['sha256'] for row in graph
               if row['installedPath'].startswith(RELEASE + '/')}
    return runtime, release


def validate_candidate(value):
    require(value.get('schema') == 'h044-image-source-candidate-v1'
            and value.get('installable') is False and value.get('liveQualified') is False, 'candidate_authority')
    require(value['placement'] == {'gpu_uuid': GPU, 'ordinalFallback': False,
            'reading_gpu_excluded': READING_GPU}, 'candidate_placement')
    require(value['runtime'] == {'base': BASE, 'release': RELEASE, 'owner': OWNER,
            'unit': UNIT, 'container': CONTAINER, 'network': NETWORK,
            'modelPath': MODEL, 'modelRevision': REVISION, 'sglangRevision': SGLANG,
            'platformManifest': MANIFEST, 'configDigest': OCI_CONFIG, 'parentOnlyForbidden': PARENT},
            'candidate_runtime')
    require(value['resources'] == {'gpuReservePercent': 5, 'hostReservePercent': 15,
            'memoryBytes': 96 * 1024**3, 'memorySwapBytes': 96 * 1024**3,
            'cpusetCpus': '8-15', 'cpusetMems': '0', 'active': 1, 'outputs': 1,
            'steps': 40, 'cfg': 1, 'offload': False, 'quantization': False,
            'approximateCache': False, 'compile': False}, 'candidate_resources')
    require(all(type(value['resources'][name]) is int for name in ('gpuReservePercent',
            'hostReservePercent', 'memoryBytes', 'memorySwapBytes', 'active', 'outputs', 'steps', 'cfg'))
            and all(type(value['resources'][name]) is bool for name in
                    ('offload','quantization','approximateCache','compile')), 'candidate_resource_types')
    require(value['fullHD'] == {'public': '1920x1080', 'native': '1920x1088',
            'cropBottom': 8, 'rawArtifact': 'NOT_CAPTURED'}, 'candidate_geometry')
    return value


def plan_config_migration(runtime_raw, api_raw, expected_runtime_sha, expected_api_sha, graph):
    """CAS-bound in-memory successor, preserving every other field/profile.

    This does not validate authenticity, acquire a lease, write config or unlock
    qualification. Native platform identity already matches the runtime pin;
    the distinct config relationship needs actual cached-byte evidence.
    """
    require(re.fullmatch('[0-9a-f]{64}', expected_runtime_sha or '') is not None
            and re.fullmatch('[0-9a-f]{64}', expected_api_sha or '') is not None, 'cas_digest')
    require(sha(runtime_raw) == expected_runtime_sha and sha(api_raw) == expected_api_sha, 'cas_changed')
    runtime, api = strict_json(runtime_raw), strict_json(api_raw)
    require(runtime.get('schema_version') == 1 and runtime.get('owner') == OWNER
            and runtime.get('source_commit') == SGLANG and runtime.get('checkpoint_revision') == REVISION
            and runtime.get('checkpoint_path') == MODEL, 'runtime_identity')
    require(runtime.get('gpu_uuid') in (GPU, READING_GPU)
            and runtime.get('image_id') == MANIFEST, 'runtime_predecessor')
    require(re.fullmatch('[0-9a-f]{64}', runtime.get('network_id', '')) is not None
            and re.fullmatch('[0-9a-f]{64}', runtime.get('checkpoint_receipt_sha256', '')) is not None,
            'runtime_protected_receipts')
    require(graph == source_graph(), 'candidate_graph_changed')
    runtime_map, release_map = source_maps(graph)
    require(runtime.get('source_sha256') == runtime_map
            and runtime.get('release_source_sha256') == release_map, 'source_delivery_required')
    require(api.get('schema_version') == 1 and api.get('model_id') == 'Qwen/Qwen-Image-2.1'
            and api.get('runtime_revision') == SGLANG and api.get('model_revision') == REVISION
            and api.get('runtime_image_digest') in (PARENT, MANIFEST), 'api_identity')
    successor_runtime, successor_api = copy.deepcopy(runtime), copy.deepcopy(api)
    successor_runtime['gpu_uuid'] = GPU
    successor_api['runtime_image_digest'] = MANIFEST
    return {'executable': False, 'qualification': 'NOT_TESTED',
            'expectedRuntimeSha256': expected_runtime_sha, 'expectedApiSha256': expected_api_sha,
            'runtimeSuccessor': successor_runtime, 'apiSuccessor': successor_api,
            'blockers': ['root_privileged_current_raw_read', 'cached_manifest_config_relationship',
                         'root_owned_CAS_storage_lease_boot_hardware_owner_transition',
                         'generation_only_protected_qualification']}


def resource_guard(total_gpu, free_gpu, total_host, available_host, swap_bytes):
    values = (total_gpu, free_gpu, total_host, available_host, swap_bytes)
    require(all(type(v) is int and v >= 0 for v in values), 'resource_type')
    require(total_gpu > 0 and total_host > 0 and free_gpu <= total_gpu
            and available_host <= total_host, 'resource_range')
    require(free_gpu * 20 >= total_gpu, 'gpu_reserve')
    require(available_host * 100 >= total_host * 15, 'host_reserve')
    require(swap_bytes == 0, 'owned_swap')
    return True


def validate_generation(arguments, profiles):
    require(set(arguments) == {'prompt', 'size', 'seed'}, 'generation_fields')
    require(type(arguments['seed']) is int and 0 <= arguments['seed'] <= 2**53 - 1, 'generation_seed')
    require(type(arguments['prompt']) is str and 0 < len(arguments['prompt'].strip()) <= 16000
            and not any(ord(c) < 32 and c not in '\n\t' for c in arguments['prompt']), 'generation_prompt')
    require(arguments['size'] == '1920x1080', 'generation_size')
    require(any(p.get('operation') == 'generation' and p.get('size') == '1920x1080'
                and type(p.get('references')) is int and p['references'] == 0
                and p.get('transparent') is False and p.get('native_size') == '1920x1088'
                and type(p.get('crop_bottom')) is int and p['crop_bottom'] == 8
                and re.fullmatch('[0-9a-f]{64}', p.get('evidence_sha256', '')) is not None
                for p in profiles), 'generation_profile')
    return {'tool': 'image_generate', 'arguments': copy.deepcopy(arguments),
            'outputs': 1, 'active': 1, 'steps': 40, 'cfg': 1, 'references': 0}


def readonly_request(graph):
    # Command data only. Root must review and stage a separately sealed fixed
    # reader implementing the file contracts below before issuing transport GO.
    selected = '{"id":{{json .Id}},"name":{{json .Name}},"imageConfig":{{json .Image}},"configImageReference":{{json .Config.Image}},"pid":{{json .State.Pid}},"running":{{json .State.Running}},"status":{{json .State.Status}},"startedAt":{{json .State.StartedAt}},"oomKilled":{{json .State.OOMKilled}},"owner":{{json (index .Config.Labels "io.llm-image.owner")}},"invocation":{{json (index .Config.Labels "io.llm-image.invocation")}},"gpu":{{json (index .Config.Labels "io.llm-image.gpu")}},"user":{{json .Config.User}},"deviceRequests":{{json .HostConfig.DeviceRequests}},"memory":{{json .HostConfig.Memory}},"memorySwap":{{json .HostConfig.MemorySwap}},"cpus":{{json .HostConfig.CpusetCpus}},"mems":{{json .HostConfig.CpusetMems}},"networkMode":{{json .HostConfig.NetworkMode}},"ports":{{json .NetworkSettings.Ports}},"portBindings":{{json .HostConfig.PortBindings}},"networks":{{json .NetworkSettings.Networks}},"mounts":{{json .Mounts}},"privileged":{{json .HostConfig.Privileged}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"restart":{{json .HostConfig.RestartPolicy.Name}},"capDrop":{{json .HostConfig.CapDrop}},"securityOpt":{{json .HostConfig.SecurityOpt}},"devices":{{json .HostConfig.Devices}},"deviceRules":{{json .HostConfig.DeviceCgroupRules}},"pidMode":{{json .HostConfig.PidMode}},"cudaSelection":[{{range .Config.Env}}{{if or (eq . "CUDA_VISIBLE_DEVICES='+GPU+'") (eq . "NVIDIA_VISIBLE_DEVICES='+GPU+'")}}{{json .}},{{end}}{{end}}null]}'
    # Project only the two relevant environment keys as booleans, including
    # mismatches/duplicates. No complete environment or arbitrary value leaves
    # Docker. A missing or wrong UUID must not disappear from the projection.
    start = selected.index(',"cudaSelection"')
    selected = selected[:start] + ',"gpuEnvironment":[{{range .Config.Env}}{{if eq (index (split . "=") 0) "CUDA_VISIBLE_DEVICES"}}{"key":"CUDA_VISIBLE_DEVICES","exact":{{if eq . "CUDA_VISIBLE_DEVICES='+GPU+'"}}true{{else}}false{{end}}},{{end}}{{if eq (index (split . "=") 0) "NVIDIA_VISIBLE_DEVICES"}}{"key":"NVIDIA_VISIBLE_DEVICES","exact":{{if eq . "NVIDIA_VISIBLE_DEVICES='+GPU+'"}}true{{else}}false{{end}}},{{end}}{{end}}null]}'
    commands = [
        ['/usr/bin/systemctl', 'show', UNIT, '--property=Id,User,Group,ActiveState,SubState,MainPID,ControlPID,ExecMainPID,InvocationID,ControlGroup,Result,ExecMainStatus,FragmentPath,NeedDaemonReload'],
        ['/usr/bin/systemctl', 'show', 'llm-image-api.service', '--property=Id,User,Group,ActiveState,SubState,MainPID,InvocationID,ControlGroup,FragmentPath,NeedDaemonReload'],
        ['/usr/bin/docker', 'container', 'ls', '--all', '--no-trunc', '--format', '{"id":{{json .ID}},"name":{{json .Names}}}'],
        ['/usr/bin/docker', 'container', 'inspect', '--format', selected, CONTAINER],
        ['/usr/bin/docker', 'image', 'inspect', '--format', '{"daemonId":{{json .Id}},"repoDigests":{{json .RepoDigests}},"os":{{json .Os}},"architecture":{{json .Architecture}}}', MANIFEST],
        ['/usr/bin/docker', 'network', 'inspect', '--format', '{"id":{{json .Id}},"name":{{json .Name}},"owner":{{json (index .Labels "io.llm-image.owner")}},"driver":{{json .Driver}},"internal":{{json .Internal}},"scope":{{json .Scope}},"ingress":{{json .Ingress}},"containers":{{json .Containers}}}', NETWORK],
        ['/usr/bin/nvidia-smi', '--id='+GPU, '--query-gpu=uuid,pci.bus_id,memory.total,memory.free,temperature.gpu,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max', '--format=csv,noheader,nounits'],
        ['/usr/bin/nvidia-smi', '--id='+GPU, '--query-compute-apps=gpu_uuid,pid,used_memory', '--format=csv,noheader,nounits'],
        ['/usr/bin/ss', '-H', '-ltn', 'sport = :30006 or sport = :30007'],
    ]
    files = [{'path': p, 'projection': 'whole_file_sha256_stat_only'} for p in fixed_paths()]
    files += [{'path': BASE+'/'+p+'.json', 'projection': 'whole_file_sha256_stat_and_fixed_nonsecret_selectors'} for p in ('config','state','operation','recovery')]
    files += [{'path': p, 'projection': 'whole_file_sha256_stat_and_fixed_nonsecret_selectors'} for p in
              (API_CONFIG, MODEL+'/CHECKPOINT-RECEIPT.json')]
    files += [{'path': p, 'projection': 'bounded_metadata_text'} for p in ('/proc/sys/kernel/random/boot_id','/proc/meminfo')]
    files += [{'path': p, 'projection': 'stat_only_no_content_no_hash'} for p in
              ('/data/services/secrets/llm-api-key','/run/credentials/llm-image-api.service/inference-key')]
    return {'schema': 'h044-image-root-readonly-request-v1', 'authorization': 'REQUEST_ONLY_NO_GO',
            'effectiveUser': 'root (euid 0); no auth/membership repair or fallback',
            'transportArgv': ['/usr/bin/ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8',
                '-o','ConnectionAttempts=1','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1',
                'ai-vm','/usr/bin/sudo','-n','/usr/bin/python3','-I','-B','-'],
            'readerStatus': 'STAGED_PRIVATE_READER_REQUIRES_EXACT_HASH_REVIEW',
            'commands': commands, 'files': files, 'expectedSourceGraph': graph,
            'caps': {'transportInvocations':1,'transportSeconds':90,'remoteSeconds':75,
                'commands':len(commands),'commandSeconds':5,'stdoutBytes':65536,'stderrBytes':8192,
                'fileCount':len(files),'fileBytes':262144,'totalFileBytes':4194304,'processCount':3},
            'ownerProcessRead': 'Only positive image-unit/container PIDs joined to fixed owner; /proc/PID/stat,cgroup,exe; no cmdline/environ; bind boot/start_ticks/PGID before/after. PID0 does not prove absence.',
            'credentialRead': {'requestedNow':'metadata_only','laterAuthentication':'separate exact GO reads existing credential in-memory; no values/export/value hashes'},
            'overlayNamespace': 'Container filesystem only: native_server.py guard runs inside image21; no host overlay delivery or host-path dependency claim.',
            'prohibited': ['HTTP health/ready or Owner.probe','runtime/service imports','lifecycle locks or storage guard methods','lifecycle/inference','downloads/pulls/weight rehash','credential contents','peer process inspection'],
            'failClosed': 'Any permission, daemon, identity, birth, source or byte/time-cap failure remains unknown. Inventory success excluding exact name/CID is required for container absence.'}


def readonly_program(request):
    """Exact finite root-reader bytes for staging/review, never run here.

    This uses only fixed reads and selected metadata commands. Credential
    contents are never opened. There is no HTTP, runtime import or lock entry.
    An unsuccessful inspection remains unknown, even if a oneshot reports0.
    """
    constants = {key: request[key] for key in ('commands','files','caps')}
    body = r'''
import datetime, hashlib, json, os, pathlib, re, selectors, signal, stat, subprocess, time
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
class Refused(Exception): pass
def require(c):
    if not c: raise Refused()
def strict(b):
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d); d[k]=v
        return d
    def bad(_): raise Refused()
    v=json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
    def bound(x,n=0):
        require(n<=12)
        if type(x) in (dict,list):
            require(len(x)<=256)
            for c in (x.values() if type(x) is dict else x): bound(c,n+1)
        if type(x) is str: require(len(x)<=16384)
    bound(v); return v
def signature(s): return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def metadata(s): return dict(uid=s.st_uid,gid=s.st_gid,mode=oct(stat.S_IMODE(s.st_mode)),size=s.st_size,device=s.st_dev,inode=s.st_ino,nlink=s.st_nlink,mtimeNs=s.st_mtime_ns)
def protected(path,read):
    p=pathlib.Path(path); require(p.is_absolute() and '..' not in p.parts)
    d=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=d)
            os.close(d); d=child; s=os.fstat(d)
            require(s.st_uid==0 and not s.st_mode & 0o022)
        before=os.stat(p.name,dir_fd=d,follow_symlinks=False)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and not before.st_mode & 0o022)
        if not read: return metadata(before),None
        require(before.st_uid==0 and before.st_size<=REQUEST['caps']['fileBytes'])
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=d)
        try:
            require(signature(before)==signature(os.fstat(fd)))
            b=os.read(fd,REQUEST['caps']['fileBytes']+1)
            require(len(b)==before.st_size and signature(before)==signature(os.fstat(fd))
                    and signature(before)==signature(os.stat(p.name,dir_fd=d,follow_symlinks=False)))
            return metadata(before),b
        finally: os.close(fd)
    finally: os.close(d)
def safe_project(path,b):
    v=strict(b); require(type(v) is dict)
    # Strings copied below are fixed enums, UUIDs, digests, ISO times or fixed
    # paths. Unknown free-form strings, tokens and exception bodies are omitted.
    result={}
    exact={'owner':'IMAGE21-RUNTIME-20260923','source_commit':'0cd8be351d0825488f4b81c8931167bbab618eca',
           'checkpoint_revision':'790c92633540aa0cb11d9abf19eb46d861714758',
           'runtime_revision':'0cd8be351d0825488f4b81c8931167bbab618eca',
           'model_revision':'790c92633540aa0cb11d9abf19eb46d861714758','model_id':'Qwen/Qwen-Image-2.1',
           'revision':'790c92633540aa0cb11d9abf19eb46d861714758'}
    for k,x in v.items():
        if k in exact: require(x==exact[k]); result[k]=x
        elif k in ('schema_version','pid','file_count','total_bytes'):
            require(type(x) is int and 0<=x<2**63); result[k]=x
        elif k=='warm': require(type(x) is bool); result[k]=x
        elif k=='gpu_uuid': require(x in GPU_UUIDS); result[k]=x
        elif k in ('image_id','runtime_image_digest'): require(x in OCI_IDENTITIES); result[k]=x
        elif k in ('checkpoint_receipt_sha256','network_id','config_sha256','prior_state_sha256'):
            require(type(x) is str and re.fullmatch('[0-9a-f]{64}',x)); result[k]=x
        elif k in ('source_sha256','release_source_sha256'):
            require(type(x) is dict and len(x)<=64 and all(type(a) is str and len(a)<=200 and
                type(y) is str and re.fullmatch('[0-9a-f]{64}',y) for a,y in x.items())); result[k]=x
        elif k in ('status','phase','action'):
            allowed={'COMPLETE_VERIFIED','active','complete','failed','absent','stopped','creating','loading',
                     'warm','start','stop','recover','restart','settle','ready','closed','generation'}
            require(x in allowed); result[k]=x
        elif k in ('boot','boot_id'):
            require(type(x) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',x)); result[k]=x
        elif k in ('run_id','invocation_id','prior_invocation','child_start') and x is not None:
            require(type(x) is str and re.fullmatch('[0-9a-f]{32}',x)); result[k]=x
        elif k=='checkpoint_path': require(x==MODEL); result[k]=x
        elif k=='container':
            if x is None: result[k]=None
            else:
                require(type(x) is dict and re.fullmatch('[0-9a-f]{64}',x.get('id',''))
                        and x.get('image_id') in OCI_IDENTITIES)
                result[k]={'id':x['id'],'image_id':x['image_id']}
        elif k=='native_generation':
            require(type(x) is dict)
            y={n:x[n] for n in ('Pid','pid','start_ticks') if n in x}
            require(all(type(z) is int and z>0 for z in y.values()))
            if 'StartedAt' in x:
                require(type(x['StartedAt']) is str and len(x['StartedAt'])<=64 and
                        re.fullmatch(r'[0-9TZ:.+\-]+',x['StartedAt'])); y['StartedAt']=x['StartedAt']
            result[k]=y
        elif k=='profiles':
            require(type(x) is list and len(x)<=100)
            profiles=[]
            for p in x:
                require(type(p) is dict and p.get('operation') in ('generation','edit') and
                        type(p.get('references')) is int and p['references'] in (0,1,2) and
                        type(p.get('transparent')) is bool and re.fullmatch('[0-9a-f]{64}',p.get('evidence_sha256','')))
                y={n:p[n] for n in ('operation','references','transparent','evidence_sha256')}
                for n in ('size','native_size'):
                    if n in p: require(re.fullmatch('[1-9][0-9]{0,4}x[1-9][0-9]{0,4}',p[n])); y[n]=p[n]
                if 'crop_bottom' in p: require(type(p['crop_bottom']) is int and 0<=p['crop_bottom']<=8); y['crop_bottom']=p['crop_bottom']
                profiles.append(y)
            result[k]=profiles
    return result
def command(argv,end):
    started=utc(); child=None; buffers=[bytearray(),bytearray()]; overflow=False; timed=False
    child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
             start_new_session=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    birth=None
    try:
        try:
            raw=pathlib.Path('/proc',str(child.pid),'stat').read_text(); f=raw.rsplit(')',1)[1].split()
            birth={'pid':child.pid,'pgid':int(f[2]),'start_ticks':int(f[19])}
        except (OSError,ValueError,IndexError): pass
        limit=min(end,time.monotonic()+5)
        with selectors.DefaultSelector() as poll:
            for i,stream in enumerate((child.stdout,child.stderr)):
                os.set_blocking(stream.fileno(),False); poll.register(stream,selectors.EVENT_READ,i)
            while poll.get_map():
                if time.monotonic()>=limit: timed=True; break
                for key,_ in poll.select(min(.05,max(0,limit-time.monotonic()))):
                    b=os.read(key.fileobj.fileno(),8192)
                    if not b: poll.unregister(key.fileobj); continue
                    cap=65536 if key.data==0 else 8192
                    if len(buffers[key.data])+len(b)>cap: overflow=True; break
                    buffers[key.data].extend(b)
                if overflow: break
    finally:
        if child.poll() is None:
            if timed or overflow:
                try: os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError: pass
            try: child.wait(timeout=min(1,max(.05,end-time.monotonic())))
            except subprocess.TimeoutExpired:
                if child.poll() is None:
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                child.wait(timeout=2)
        terminal={'argv':argv,'cwd':'/','host':'ai-vm','startUtc':started,'endUtc':utc(),
            'exitCode':child.returncode,'timeoutSeconds':5,'timedOut':timed,'overflow':overflow,
            'pid':child.pid,'birth':birth,'reaped':True}
        # Original actual terminal precedes fallible parse/projection/postcheck.
        RECORDS.append({'terminal':terminal})
        child.stdout.close(); child.stderr.close()
    for name,b in zip(('stdout','stderr'),buffers):
        terminal[name]={'sha256':sha(b),'bytes':len(b),'text':b.decode('utf-8','replace')}
    terminal['outcome']='READBACK' if child.returncode==0 and not timed and not overflow else 'FAILED'
    return terminal
def process_stamp(pid):
    require(type(pid) is int and 0<pid<2**31)
    p=pathlib.Path('/proc',str(pid)); b=(p/'stat').read_bytes(); require(len(b)<=8192)
    f=b.decode().rsplit(')',1)[1].split(); require(f[0] not in ('Z','X'))
    cg=(p/'cgroup').read_text(); require(len(cg)<=8192)
    exe=os.readlink(p/'exe'); require(len(exe)<=1024 and exe.startswith('/'))
    return {'pid':pid,'ppid':int(f[1]),'pgid':int(f[2]),'start_ticks':int(f[19]),'cgroup':cg.strip(),'exe':exe}
def owner_processes(commands,end):
    targets=[]; records=[]
    for row in commands[:2]:
        if row['outcome']!='READBACK': continue
        fields=dict(line.split('=',1) for line in row['stdout']['text'].splitlines() if '=' in line)
        unit=fields.get('Id'); invocation=fields.get('InvocationID',''); cg=fields.get('ControlGroup','')
        if unit not in ('llm-image-backend.service','llm-image-api.service'): continue
        if not re.fullmatch('[0-9a-f]{32}',invocation): continue
        if cg!='/system.slice/'+unit: continue
        pid=fields.get('MainPID','')
        if pid.isascii() and pid.isdigit() and int(pid)>0:
            targets.append((int(pid),unit,cg))
    row=commands[3] if len(commands)>3 else None
    if row and row['outcome']=='READBACK':
        try:
            v=strict(row['stdout']['text'].encode())
            if (v.get('name')=='/llm-image-backend' and v.get('owner')=='IMAGE21-RUNTIME-20260923'
                and v.get('gpu')==GPU_UUIDS[0] and re.fullmatch('[0-9a-f]{64}',v.get('id',''))
                and re.fullmatch('[0-9a-f]{32}',v.get('invocation','')) and v.get('running') is True):
                targets.append((v['pid'],'llm-image-backend',v['id']))
        except (Refused,ValueError,TypeError): pass
    for pid,owner,anchor in targets[:3]:
        rec={'pid':pid,'owner':owner,'startUtc':utc()}
        try:
            require(time.monotonic()<end); before=process_stamp(pid)
            require(('0::'+anchor) in before['cgroup'].splitlines() if owner.endswith('.service')
                    else anchor in before['cgroup'])
            after=process_stamp(pid); require(before==after)
            rec.update(outcome='READBACK',identity=before,stable=True)
        except (OSError,Refused,ValueError,IndexError,TypeError):
            rec.update(outcome='FAILED',failure='joined_owner_process_unproven')
        rec['endUtc']=utc(); records.append(rec)
    return records
def main():
    require(os.geteuid()==0); os.chdir('/'); start=utc(); end=time.monotonic()+70
    before=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    commands=[]; files=[]; total=0
    for argv in REQUEST['commands']:
        if time.monotonic()>=end: break
        commands.append(command(argv,end))
    for spec in REQUEST['files']:
        if time.monotonic()>=end: break
        rec={'path':spec['path'],'startUtc':utc(),'projection':spec['projection']}
        try:
            p=spec['path']; read=spec['projection']!='stat_only_no_content_no_hash'
            if p in ('/proc/sys/kernel/random/boot_id','/proc/meminfo'):
                with open(p,'rb') as f: b=f.read(65537)
                require(len(b)<=65536); meta=None
            else: meta,b=protected(p,read)
            rec['metadata']=meta
            if b is not None:
                total+=len(b); require(total<=4194304); rec['sha256']=sha(b); rec['bytes']=len(b)
                if p=='/proc/sys/kernel/random/boot_id': rec['boot']=b.decode().strip()
                elif p=='/proc/meminfo':
                    rec['memory']={k:int(n)*1024 for k,n in re.findall(r'^(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+) kB$',b.decode(),re.M)}
                elif 'fixed_nonsecret_selectors' in spec['projection']: rec['selected']=safe_project(p,b)
            rec['outcome']='READBACK'
        except (OSError,ValueError,TypeError,KeyError,Refused) as e:
            rec['outcome']='FAILED'; rec['failure']='protected_read_or_schema_refused'; rec['errno']=getattr(e,'errno',None)
        rec['endUtc']=utc(); files.append(rec)
    processes=owner_processes(commands,end)
    after=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    print(json.dumps({'schema':'h044-image-root-passive-readback-v1','startUtc':start,'endUtc':utc(),
        'effectiveUid':os.geteuid(),'bootBefore':before,'bootAfter':after,'bootStable':before==after,
        'commands':commands,'files':files,'totalFileBytes':total,'admissionOrLifecycleInvoked':False,
        'ownerProcesses':processes,'ownerProcessLimit':'Only up to3 positive image-owner-joined PIDs. Empty/PID0 is not proof of native absence/readiness.',
        'readbackOutcome':'PARTIAL' if len(commands)!=len(REQUEST['commands']) or len(files)!=len(REQUEST['files'])
            or before!=after or any(r['outcome']!='READBACK' for r in commands+files) else 'PASS_PASSIVE_METADATA_ONLY',
        'readiness':'NOT_TESTED','nativeGeneration':'NOT_TESTED'},sort_keys=True))
RECORDS=[]
if __name__=='__main__': main()
'''
    return ('#!/usr/bin/env python3\nREQUEST='+repr(constants)+'\nGPU_UUIDS='+repr((GPU,READING_GPU))+
            '\nOCI_IDENTITIES='+repr((MANIFEST,OCI_CONFIG,PARENT))+'\nMODEL='+repr(MODEL)+'\n'+body).encode()


def runtime_proposal(graph):
    return {'schema':'h044-image-runtime-proposal-v1','authorizedEdits':False,
            'reason':'Retained source binds config.image_id to native platform manifest and compares container.Image to that same manifest. Root privileged read observed container.Image, Config.Image and image.Id all50a3; this does not show a validator failure and is not proof of config3f61. Exact engine source/manifest/config-domain diagnosis is required. Do not change a production guard to accept observed metadata.',
            'affectedReadOnlyFiles':['scripts/image_runtime/service.py','scripts/lifecycle/runtime_io.py'],
            'sourceBindings':{r['candidateSource']:r['sha256'] for r in graph if r['candidateSource'] in ('scripts/image_runtime/service.py','scripts/lifecycle/runtime_io.py','configs/runtimes/h005-runtime-binding.json')},
            'requestedSuccessor':'Only if current exact engine/OCI diagnosis establishes a genuine source mismatch, root assigns a distinct owner and separately reviews that concrete correction. Independently preserve immutable platform50a3 and config3f61 evidence. No OR parent fallback, guessed domain migration or weakening of label/GPU/network/mount/lease/source/hardware/CAS guards.',
            'overlayNamespace':'native_server.py runs inside image21; service.py mounts /runtime read-only and no host /opt overlay. Historical host ENOENT is wrong namespace, not established production defect.',
            'status':'CONTAINER_OVERLAY_AND_DISTINCT_CACHED_CONFIG_RELATIONSHIP_NOT_TESTED; no production mismatch established; no existing runtime edit made'}


def reconcile_plan(observation, original_sha256, graph):
    """Plan from selected root readback, never reconstruct protected raw state.

    The selected snapshot lacks operation capabilities/full native state. It can
    bind a future root CAS request, but cannot itself authenticate settlement.
    """
    require(re.fullmatch('[0-9a-f]{64}', original_sha256 or '') is not None, 'original_digest')
    require(observation.get('origin') == 'LIVE_PASSIVE_READBACK'
            and observation.get('bootStable') is True, 'live_read_origin')
    commands=observation['commands']
    require(len(commands)==7 and all(type(c.get('exitCode')) is int and c['exitCode']==0
            and c.get('capturedBytesComplete') is True for c in commands), 'current_commands')
    records=observation['records']; selected={}; hashes={}
    for key in ('config','state','operation','recovery','api_config','checkpoint'):
        rec=records[key]; receipt=rec['receipt']; require(receipt.get('outcome')=='READBACK', 'current_file_read')
        digest=receipt.get('sha256'); require(re.fullmatch('[0-9a-f]{64}',digest or '') is not None, 'current_file_hash')
        hashes[receipt['path']]=digest; selected[key]=rec['fields']
    config=selected['config']; runtime_map, release_map=source_maps(graph)
    require(config['owner']==OWNER and config['gpu_uuid']==READING_GPU and config['image_id']==MANIFEST
            and config['source_commit']==SGLANG and config['checkpoint_revision']==REVISION
            and config.get('checkpointPathMatchesFixed') is True, 'observed_config_identity')
    require(config['source_sha256']==runtime_map and config['release_source_sha256']==release_map,
            'observed_source_maps')
    protected=[r for r in observation['sourceGraph'] if r['scope'] in ('source_sha256','release_source_sha256')]
    require(len(protected)==37, 'observed_closure_count')
    expected={BASE+'/source/'+k:v for k,v in runtime_map.items()}
    expected.update({RELEASE+'/'+k:v for k,v in release_map.items()})
    require({r['path']:r['receipt'].get('sha256') for r in protected}==expected
            and all(r['receipt'].get('outcome')=='READBACK' for r in protected), 'observed_closure_hashes')
    native=next(c for c in commands if c['name']=='native_container')
    container=strict_json(native['stdoutLog'].encode())
    state=selected['state']; operation=selected['operation']; recovery=selected['recovery']
    require(container['name']=='/'+CONTAINER and container['owner']==OWNER
            and container['id']==state['container']['id'] and container['invocation']==state['run_id']
            and container['gpu']==READING_GPU and container['image']==container['configImage']==MANIFEST,
            'observed_container_join')
    require(container['running'] is False and type(container['pid']) is int and container['pid']==0
            and container['status']=='exited', 'observed_container_stopped')
    require(operation['status']==recovery['status']=='active'
            and operation['boot']==recovery['boot'] and operation['boot']!=observation['bootId'],
            'observed_prior_boot_records')
    checkpoint=selected['checkpoint']
    require(checkpoint=={'file_count':26,'revision':REVISION,'status':'COMPLETE_VERIFIED',
            'total_bytes':33131614782}
            and records['checkpoint']['receipt']['sha256']==config['checkpoint_receipt_sha256'],
            'observed_checkpoint')
    require(selected['api_config']['runtime_image_digest']==PARENT, 'observed_api_parent')
    image=strict_json(next(c for c in commands if c['name']=='native_image')['stdoutLog'].encode())
    require(image['id']==MANIFEST and image['os']=='linux' and image['architecture']=='amd64', 'observed_daemon_image')
    return {'schema':'h044-image-current-reconcile-plan-v1','executable':False,
        'rootOriginalReadbackSha256':original_sha256,'observedBoot':observation['bootId'],
        'observedUtc':observation['finishedUtc'],'criticalFileCAS':hashes,
        'protectedClosure':{'count':37,'hashesMatch':True,'externalDeliveryReviewed':False},
        'daemonIdentity':{'observedId':image['id'],'observedContainerImage':container['image'],
            'requiredManifest':MANIFEST,'requiredConfig':OCI_CONFIG,'configDomainProven':False},
        'ownedContainerCandidate':{'id':container['id'],'invocation':container['invocation'],
            'gpu_uuid':READING_GPU,'running':False,'pid':0,'exitCode':container['exitCode'],
            'authenticCurrentSettlement':'NOT_PROVEN'},
        'staleRecords':{'priorBoot':operation['boot'],'operationStatus':'active','recoveryStatus':'active',
            'currentProcessOwnership':'NOT_PROVEN; prior-boot PID numbers must not authorize signals'},
        'deltas':{'runtime':{'gpu_uuid':GPU},'api':{'runtime_image_digest':MANIFEST}},
        'preserve':'Every other raw field/profile/evidence. Selected fields are not complete raw bytes; do not build replacement files from this snapshot.',
        'phases':[
            {'name':'identity_and_current_settlement_read','authorization':'NEW_EXACT_ROOT_GO_REQUIRED',
             'maximumInvocations':1,'seconds':90,'prerequisites':'Exact /usr/bin/docker realpath/source and local daemon native platform/config evidence; exact external graph/overlay requirements; current image service/container/network/native descendant absence. No speculative source rewrite, health/ready or old GO retry.'},
            {'name':'container_overlay_preflight','authorization':'DISTINCT_NEW_EXACT_ROOT_GO_REQUIRED',
             'maximumInvocations':1,'seconds':120,'hostDeliveryProposed':False,
             'prerequisites':'GPU-free cached-platform50a3 owned temporary container; hash exact in-container verifier and selected receipt, invoke exact pinned verify_installed. No runtime/model/key mount. Host overlay ENOENT cannot establish container absence.'},
            {'name':'reviewed_guarded_reconcile_source','authorization':'SOURCE_OWNER_ASSIGNMENT_REQUIRED',
             'prerequisites':'Current selected read is insufficient for an executable rollback/helper graph. Root assigns exact separately owned helper; no edit to existing lifecycle/runtime files by I. Bind full protected current state/native_actions/native_generation/operation/recovery without exposing tokens.'},
            {'name':'archive_and_settle_prior_boot_image_owner','authorization':'NEW_EXACT_ROOT_GO_REQUIRED',
             'maximumInvocations':1,'seconds':120,'prerequisites':'Canonical lease, registered storage/root disk/boot/hardware, all6 original-file CAS, refreshed exact image container/native descendants and network. Copy original bytes to new protected registered evidence location before any writes. No generic reset/latch clear or name-only adoption.',
             'transition':'Only after current authentic owner/absence proof may a reviewed helper settle/reconcile old image records and remove the exact stopped owned container. Preserve originals and all peer/uncertain owners.'},
            {'name':'critical_config_CAS','authorization':'NEW_EXACT_ROOT_GO_REQUIRED','maximumInvocations':1,
             'seconds':120,'prerequisites':'Settled image owner, same boot, current refreshed6file CAS/source closure, immutable saved image/model receipt and exact resource guards. No source closure hash changes without reviewed source delivery.',
             'transition':'Read full config privately; change runtime.gpu_uuid14c→5d and API.runtime_image_digest parent→platform. Retain all other fields and profiles. Record whole before/after FILE hashes and rollback CAS. Registry source already declares external5d.'},
            {'name':'detached_owned_activation','authorization':'DISTINCT_NEW_EXACT_ROOT_GO_REQUIRED',
             'maximumInvocations':1,'seconds':840,'prerequisites':'Root-reviewed full helper/unit/current-source/config graph, source closure37+external requirements, boot/storage/lease/native owner/hardware/memory guards; prerequisite service recovery may itself start/warm and is an active operation.',
             'transition':'Load existing saved image weights through one reviewed existing owned service only. Service start includes deterministic warm generation; include that explicitly in GO. Detach model load; close paid session during load. Ordinary residency is left usable only after qualification.'},
            {'name':'normal_Sova_generation','authorization':'DISTINCT_NEW_EXACT_ROOT_GO_REQUIRED',
             'maximumInvocations':1,'outputs':1,'active':1,'steps':40,'cfg':1,
             'prerequisites':'Fresh actual native/runtime/auth/profile readiness, generation-only protected ticket from R owner, saved canonical same-chat IDs and resource sampling. No edit/multi-reference/child operation.'}],
        'rollback':'A separately reviewed exact finite owned rollback restores archived raw config by successor CAS only after new image owner is settled; it does not restart the old stable-Ada placement. No rollback may occupy the reading GPU, replay a historical helper or change fan policy.',
        'remaining':['distinct cached platform/config relationship','actual in-container overlay verification','current raw schema/owner/descendant/storage/lease/hardware settlement','generation-only protected ticket','actual concurrent six-model operation'],
        'qualification':'NOT_TESTED'}


def packet(root=ROOT):
    candidate = validate_candidate(strict_json((root/CANDIDATE).read_bytes()))
    graph = source_graph(root)
    args = {'prompt':'Create one clear landscape illustration of a red sailboat on a calm alpine lake at sunrise, with mountains reflected in the water.','size':'1920x1080','seed':43001}
    read_request=readonly_request(graph)
    program=readonly_program(read_request)
    read_request['readerSha256']=sha(program)
    read_request['readerBytes']=len(program)
    read_request['readerPrivateFilename']='ROOT-READONLY-CANDIDATE-FINAL.py'
    normal_files=('ai-harness/server/src/image-broker.ts','ai-harness/server/src/image-upstream.ts',
        'ai-harness/server/src/image-contracts.ts','ai-harness/server/src/image-files.ts',
        'ai-harness/server/src/image-codec.ts','ai-harness/server/src/image-status-consumption.ts',
        'ai-harness/server/src/codex-specialist-qualification.ts','ai-harness/server/src/codex-launcher.ts',
        'ai-harness/tools/image/image-mcp.mjs','ai-harness/tools/image/image.mjs')
    bindings={'sourceBase':BASE_COMMIT,'preparationSourceSha256':sha((root/'scripts/h044/image_backend_preparation.py').read_bytes()),
        'candidateConfigSha256':sha((root/CANDIDATE).read_bytes()),
        'registrySha256':sha((root/'ai-harness/config/system-registry.json').read_bytes()),
        'normalPathSourceSha256':{name:sha((root/name).read_bytes()) for name in normal_files},
        'runtimeSourceGraphSha256':sha(json.dumps(graph,sort_keys=True,separators=(',',':')).encode()),
        'currentRuntimeConfigSha256':candidate['currentReadback']['currentRuntimeConfigSha256'],
        'currentApiConfigSha256':candidate['currentReadback']['currentApiConfigSha256'],
        'rootReadbackOriginalSha256':candidate['currentReadback']['originalStdoutSha256'],
        'integrationRequirement':'Frozen base normal-path hashes only. Root must bind the actual reviewed successor routing/native source and fresh config/owner/boot immediately before any finite GO; no concurrent active source is imported.'}
    return {'schema':'h044-image-preparation-v1','sourceOnly':True,'baseCommit':BASE_COMMIT,
            'candidate':candidate,'candidateSha256':sha((root/CANDIDATE).read_bytes()),
            'sourceGraph':graph,'readonlyRequest':read_request,'runtimeProposal':runtime_proposal(graph),
            'generation':{'executable':False,'authorization':'REQUEST_ONLY_NO_GO','reviewBindings':bindings,'tool':'image_generate','arguments':args,
                'path':'normal Sova saved chat → pinned native Codex → authenticated image MCP → owned image broker/job → upstream image API → exact external-Ada backend → decoded durable public PNG → same-chat result',
                'invocations':1,'outputs':1,'active':1,'steps':40,'cfg':1,'references':0,
                'operationSeconds':900,'scopedTicketSeconds':1800,'mcpTimeoutSeconds':3300,
                'publicSize':'1920x1080','nativeSize':'1920x1088','cropBottom':8,'rawPrecropArtifact':'NOT_CAPTURED',
                'prerequisites':['genuine minimal Codex startup/owned shutdown','current root-reviewed source/config/boot/owner/container/native OCI/model checkpoint','CAS migration and source closure settled','canonical storage/lease/hardware guards','current protected API authentication','authentic generation-only scoped task ticket from R owner; old global guard remains closed','exact qualified zero-reference opaque FullHD profile','fresh before/during/after external GPU temperature/link/ownership/memory and host/cgroup no-swap samples'],
                'evidence':['actual app/native session/run/request/job IDs','exact operation/container/GPU/boot/source/config/OCI/model binding','normal tool and durable app result','actual decoded public PNG SHA256 and1920x1080 dimensions','native protocol geometry/crop evidence without invented raw hash','sample gaps/peaks >=5%GPU/>=15%host reserves','one same-chat noncreative follow-up using saved image; no additional generation'],
                'gate':'Retained codex-specialist-qualification.ts requires generation + followup_edit + child live records; this packet cannot open it from one generation. R owns separately reviewed generation-only qualification. No fake evidence or guard bypass.',
                'rollback':'Separate exact finite GO with authentic current image owner/boot/container/invocation/PID-birth/config/source/helper/storage/lease/hardware. Retain old bytes and original failures; no name-only stop/recover, historical H032 latch clear, peer/fan action.',
                'coResidency':'Two Qwens + MiMo + Qwen3.5-9B + PaddleOCR-VL1.6 + Qwen-Image must be observed resident/operating together by separate bounded root owner. Configured placement is not observed concurrency.'},
            'notTested':['Linux privileged readback','config migration/install','owned model activation/shutdown','normal native generation','protected generation-only ticket','co-residency/concurrent operation','external USB4 sustained workload stability'],
            'postponed':['image editing','multiple references','creative child acceptance','persistent raw pre-crop capture']}



PREFLIGHT_BODY = '"""Finite diagnostic only. Imported by synthetic tests; Linux execution needs GO."""\nimport datetime, hashlib, json, os, pathlib, selectors, signal, stat, subprocess, time\n\nclass Refused(Exception): pass\ndef require(ok, code):\n    if not ok: raise Refused(code)\ndef sha(raw): return hashlib.sha256(raw).hexdigest()\ndef utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()\ndef strict(raw):\n    require(type(raw) is bytes and len(raw) <= 262144, \'json_size\')\n    def pairs(items):\n        d={}\n        for k,v in items:\n            require(k not in d, \'duplicate_key\'); d[k]=v\n        return d\n    def bad(_): raise Refused(\'nonfinite\')\n    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)\ndef signature(s): return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)\ndef read_protected(path, cap=262144):\n    p=pathlib.Path(path); require(p.is_absolute() and \'..\' not in p.parts,\'path\')\n    directory=os.open(\'/\',os.O_RDONLY|os.O_DIRECTORY)\n    try:\n        for part in p.parts[1:-1]:\n            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)\n            s=os.fstat(child); require(s.st_uid==0 and not s.st_mode&0o022,\'ancestry\')\n            os.close(directory); directory=child\n        before=os.stat(p.name,dir_fd=directory,follow_symlinks=False)\n        require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1\n                and not before.st_mode&0o022 and before.st_size<=cap,\'file\')\n        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)\n        try:\n            require(signature(before)==signature(os.fstat(fd)),\'fd\')\n            raw=os.read(fd,cap+1)\n            require(len(raw)==before.st_size and signature(before)==signature(os.fstat(fd))\n                    and signature(before)==signature(os.stat(p.name,dir_fd=directory,follow_symlinks=False)),\'file_cas\')\n            return raw\n        finally: os.close(fd)\n    finally: os.close(directory)\ndef verify_image(v):\n    require(type(v) is dict and v.get(\'id\')==PIN[\'platform\'] and v.get(\'os\')==\'linux\'\n            and v.get(\'architecture\')==\'amd64\',\'image_identity\')\n    desc=v.get(\'descriptor\')\n    require(type(desc) is dict and desc.get(\'digest\')==PIN[\'platform\']\n            and desc.get(\'mediaType\')==\'application/vnd.oci.image.manifest.v1+json\'\n            and type(desc.get(\'size\')) is int and 0<desc[\'size\']<=262144,\'image_descriptor\')\n    require(v.get(\'overlay\')==PIN[\'overlay\'],\'image_overlay_label\')\n    return {\'imageId\':v[\'id\'],\'imageIdDomain\':\'oci_platform_manifest\',\'descriptor\':desc,\n            \'platform\':\'linux/amd64\',\'configDigest\':PIN[\'config\'],\n            \'configRelationship\':\'BLOCKED_EXACT_CACHE_FD_PATH_NOT_AVAILABLE\'}\ndef labels():\n    return {\'io.llm-image.owner\':PIN[\'owner\'],\'io.llm-image.invocation\':PIN[\'invocation\'],\n            \'io.llm-image.go\':PIN[\'goId\'],\'io.llm-image.boot\':PIN[\'boot\'],\n            \'io.llm-image.source-sha256\':PIN[\'sourceSha256\'],\n            \'io.llm-image.revision\':PIN[\'revision\']}\ndef verify_container(v,cid=None):\n    require(type(v) is dict and type(v.get(\'Id\')) is str and len(v[\'Id\'])==64\n            and all(c in \'0123456789abcdef\' for c in v[\'Id\']) and (cid is None or v[\'Id\']==cid),\'container_id\')\n    c,h,s=v.get(\'Config\',{}),v.get(\'HostConfig\',{}),v.get(\'State\',{})\n    require(v.get(\'Name\')==\'/\'+PIN[\'name\'] and v.get(\'Image\')==PIN[\'platform\']\n            and c.get(\'Image\')==PIN[\'platform\'] and type(c.get(\'Labels\')) is dict\n            and all(c[\'Labels\'].get(k)==v for k,v in labels().items())\n            and c[\'Labels\'].get(\'io.llmctl.adaptive-idle.overlay-sha256\')==PIN[\'overlay\'],\'container_owner\')\n    require(c.get(\'User\')==\'1000:1001\' and c.get(\'Entrypoint\')==[\'/opt/image-venv/bin/python\']\n            and c.get(\'Cmd\')==[\'-I\',\'-B\',\'-c\',PIN[\'containerProgram\']],\'container_command\')\n    selected=[e for e in c.get(\'Env\',[]) if e.split(\'=\',1)[0] in (\'NVIDIA_VISIBLE_DEVICES\',\'CUDA_VISIBLE_DEVICES\')]\n    require(sorted(selected)==[\'CUDA_VISIBLE_DEVICES=\',\'NVIDIA_VISIBLE_DEVICES=void\'],\'gpu_environment\')\n    require(h.get(\'Runtime\')==\'runc\' and h.get(\'NetworkMode\')==\'none\' and h.get(\'ReadonlyRootfs\') is True\n            and h.get(\'Privileged\') is False and h.get(\'DeviceRequests\') in (None,[])\n            and h.get(\'Devices\') in (None,[]) and h.get(\'DeviceCgroupRules\') in (None,[])\n            and v.get(\'Mounts\')==[] and h.get(\'Binds\') in (None,[]) and h.get(\'Tmpfs\') in (None,{})\n            and h.get(\'PortBindings\') in (None,{}) and h.get(\'PidMode\')==\'\'\n            and h.get(\'CapDrop\')==[\'ALL\'] and h.get(\'CapAdd\') in (None,[])\n            and h.get(\'SecurityOpt\')==[\'no-new-privileges\'] and h.get(\'RestartPolicy\',{}).get(\'Name\')==\'no\'\n            and h.get(\'LogConfig\',{}).get(\'Type\')==\'none\' and h.get(\'Memory\')==536870912\n            and h.get(\'MemorySwap\')==536870912 and h.get(\'NanoCpus\')==1000000000\n            and h.get(\'PidsLimit\')==32,\'container_isolation\')\n    require(type(s.get(\'Running\')) is bool and type(s.get(\'Pid\')) is int,\'container_state\')\n    return v[\'Id\']\ndef create_argv():\n    argv=[\'/usr/bin/docker\',\'create\',\'--pull\',\'never\',\'--runtime\',\'runc\',\'--name\',PIN[\'name\']]\n    for k,v in labels().items(): argv+=[\'--label\',k+\'=\'+v]\n    return argv+[\'--network\',\'none\',\'--read-only\',\'--user\',\'1000:1001\',\'--env\',\'NVIDIA_VISIBLE_DEVICES=void\',\n        \'--env\',\'CUDA_VISIBLE_DEVICES=\',\'--env\',\'PYTHONDONTWRITEBYTECODE=1\',\'--cap-drop\',\'ALL\',\n        \'--security-opt\',\'no-new-privileges\',\'--cpus\',\'1\',\'--memory\',\'512m\',\'--memory-swap\',\'512m\',\n        \'--pids-limit\',\'32\',\'--restart\',\'no\',\'--log-driver\',\'none\',\'--entrypoint\',\'/opt/image-venv/bin/python\',\n        PIN[\'platform\'],\'-I\',\'-B\',\'-c\',PIN[\'containerProgram\']]\ndef proc_stamp(pid):\n    raw=pathlib.Path(\'/proc/\'+str(pid)+\'/stat\').read_text(); tail=raw[raw.rfind(\')\')+2:].split()\n    return {\'pid\':pid,\'pgid\':int(tail[2]),\'startTicks\':int(tail[19])}\ndef journal(value):\n    data=(json.dumps(value,sort_keys=True)+\'\\n\').encode(); os.write(AUDIT,data); os.fsync(AUDIT)\nCOMMANDS=[]\ndef command(argv,deadline,seconds=8,check=True):\n    require(time.monotonic()<deadline,\'budget\')\n    start=utc(); buffers=[bytearray(),bytearray()]; streams=None; birth=\'UNKNOWN\'\n    timed=False; overflow=False; failure=None; child=None; reaped=False\n    local_end=min(deadline,time.monotonic()+seconds)\n    try:\n        child=subprocess.Popen(argv,cwd=\'/\',env={\'PATH\':\'/usr/bin:/bin\',\'HOME\':\'/nonexistent\'},\n            stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,start_new_session=True)\n        # Every operation after Popen is inside this try/finally.\n        birth=proc_stamp(child.pid)\n        streams=selectors.DefaultSelector()\n        for i,pipe in enumerate((child.stdout,child.stderr)):\n            os.set_blocking(pipe.fileno(),False); streams.register(pipe,selectors.EVENT_READ,i)\n        while streams.get_map():\n            if time.monotonic()>=local_end: timed=True; break\n            for key,_ in streams.select(min(.1,max(0,local_end-time.monotonic()))):\n                data=os.read(key.fileobj.fileno(),8192)\n                if not data: streams.unregister(key.fileobj)\n                else:\n                    buffers[key.data].extend(data)\n                    if len(buffers[key.data])>65536: overflow=True; break\n            if overflow: break\n        if not timed and not overflow:\n            try: child.wait(timeout=max(.001,min(local_end-time.monotonic(),deadline-time.monotonic())))\n            except subprocess.TimeoutExpired: timed=True\n    except BaseException as error:\n        failure=\'interrupted\' if isinstance(error,Refused) and str(error)==\'interrupted\' else \'metadata_selector_or_command_failed\'\n    finally:\n        # Repeated interrupts cannot prevent mandatory direct-child settlement.\n        previous={sig:signal.signal(sig,signal.SIG_IGN) for sig in (signal.SIGTERM,signal.SIGINT)}\n        if child is not None:\n            for sig,grace in ((signal.SIGTERM,.5),(signal.SIGKILL,1.5)):\n                if child.poll() is not None: break\n                try: os.killpg(child.pid,sig)\n                except ProcessLookupError: pass\n                remaining=min(grace,max(.001,deadline-time.monotonic()))\n                try: child.wait(timeout=remaining)\n                except subprocess.TimeoutExpired: pass\n            reaped=child.poll() is not None\n            if reaped:\n                # returncode is actual Popen terminal; no prospective exit.\n                child.wait(timeout=.001)\n            for i,pipe in enumerate((child.stdout,child.stderr)):\n                try:\n                    os.set_blocking(pipe.fileno(),False)\n                    while len(buffers[i])<=65536:\n                        data=os.read(pipe.fileno(),min(8192,65537-len(buffers[i])))\n                        if not data: break\n                        buffers[i].extend(data)\n                except (OSError,ValueError): pass\n            overflow=overflow or any(len(buf)>65536 for buf in buffers)\n        terminal={\'argv\':argv,\'cwd\':\'/\',\'host\':\'ai-vm\',\'startUtc\':start,\'endUtc\':utc(),\n            \'pid\':child.pid if child else None,\'pgid\':child.pid if child else None,\'birth\':birth,\n            \'exitCode\':child.returncode if child and reaped else None,\'reaped\':reaped,\n            \'timeoutSeconds\':seconds,\'timedOut\':timed,\'overflow\':overflow,\'failure\':failure,\n            \'stdout\':bytes(buffers[0]).decode(\'utf-8\',\'replace\'),\'stderr\':bytes(buffers[1]).decode(\'utf-8\',\'replace\'),\n            \'stdoutSha256\':sha(bytes(buffers[0])),\'stderrSha256\':sha(bytes(buffers[1]))}\n        COMMANDS.append(terminal) # persist actual terminal before any postcheck\n        try: journal(terminal)\n        except (OSError,ValueError): failure=\'journal_failed\'\n        if streams is not None: streams.close()\n        if child is not None:\n            child.stdout.close(); child.stderr.close()\n        for sig,handler in previous.items(): signal.signal(sig,handler)\n    require(child is not None and reaped and failure is None and not timed and not overflow\n            and (not check or child.returncode==0),\'command_failed\')\n    return child.returncode,bytes(buffers[0])\n\ndef inspect(name,deadline):\n    # Full diagnostic config has no credentials; no production container is inspected.\n    code,raw=command([\'/usr/bin/docker\',\'container\',\'inspect\',name],deadline,check=False)\n    if code: return None\n    value=strict(raw); require(type(value) is list and len(value)==1,\'inspect_count\'); return value[0]\ndef validate_go(go,self_sha,now):\n    require(type(go) is dict and go.get(\'status\')==\'GO\' and go.get(\'issuedBy\')==\'root\'\n        and go.get(\'goId\')==PIN[\'goId\'] and go.get(\'bootId\')==PIN[\'boot\']\n        and go.get(\'helperSha256\')==self_sha and go.get(\'sourceSha256\')==PIN[\'sourceSha256\']\n        and go.get(\'containerName\')==PIN[\'name\'] and type(go.get(\'maximumInvocations\')) is int and go[\'maximumInvocations\']==1\n        and go.get(\'actions\')==[\'cached_image_inspect\',\'owned_gpu_free_create_start_attach_wait_inspect_remove\'], \'root_go\')\n    a=datetime.datetime.fromisoformat(go[\'notBeforeUtc\']); b=datetime.datetime.fromisoformat(go[\'expiresUtc\'])\n    require(a.tzinfo is not None and b.tzinfo is not None and a<=now<b\n            and (b-a).total_seconds()<=150 and (b-now).total_seconds()>=120,\'go_budget\')\ndef main():\n    global AUDIT\n    require(os.geteuid()==0,\'root\'); os.chdir(\'/\')\n    helper=PIN[\'stageRoot\']+\'/image21-preflight.py\'; go_path=PIN[\'stageRoot\']+\'/ROOT-GO.json\'\n    raw=read_protected(helper); go=strict(read_protected(go_path))\n    validate_go(go,sha(raw),datetime.datetime.now(datetime.timezone.utc))\n    require(pathlib.Path(\'/proc/sys/kernel/random/boot_id\').read_text().strip()==PIN[\'boot\'],\'boot\')\n    directory=os.open(PIN[\'stageRoot\'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\n    s=os.fstat(directory); require(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,\'stage_root\')\n    AUDIT=os.open(\'PREFLIGHT-JOURNAL.jsonl\',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)\n    os.close(directory)\n    beginning=time.monotonic(); work_end=beginning+65; cleanup_end=beginning+110\n    def interrupted(signum,frame): raise Refused(\'interrupted\')\n    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)\n    cid=None; created_attempted=False; creator_complete=False; result={\'status\':\'FAILED\',\'nativeGeneration\':\'NOT_TESTED\',\'configRelationship\':\'BLOCKED_EXACT_CACHE_FD_PATH_NOT_AVAILABLE\'}\n    try:\n        fmt=\'{"id":{{json .Id}},"descriptor":{{json .Descriptor}},"os":{{json .Os}},"architecture":{{json .Architecture}},"overlay":{{json (index .Config.Labels "io.llmctl.adaptive-idle.overlay-sha256")}}}\'\n        _,raw=command([\'/usr/bin/docker\',\'image\',\'inspect\',\'--format\',fmt,PIN[\'platform\']],work_end)\n        result[\'image\']=verify_image(strict(raw))\n        _,raw=command([\'/usr/bin/docker\',\'container\',\'ls\',\'--all\',\'--no-trunc\',\'--filter\',\'name=^/\'+PIN[\'name\']+\'$\',\'--format\',\'{{.Names}}\'],work_end)\n        require(PIN[\'name\'] not in raw.decode().splitlines(),\'name_collision\')\n        journal({\'createIntent\':create_argv(),\'name\':PIN[\'name\'],\'boot\':PIN[\'boot\'],\'goId\':PIN[\'goId\']})\n        created_attempted=True\n        _,raw=command(create_argv(),work_end); cid=raw.decode().strip()\n        require(len(cid)==64 and all(c in \'0123456789abcdef\' for c in cid),\'creator_cid\')\n        creator_complete=True\n        verify_container(inspect(cid,work_end),cid)\n        _,raw=command([\'/usr/bin/docker\',\'start\',\'--attach\',\'--sig-proxy=false\',cid],work_end,seconds=15)\n        result[\'overlay\']=strict(raw)\n        require(result[\'overlay\'].get(\'verifierRawSha256\')==PIN[\'verifier\']\n                and type(result[\'overlay\'].get(\'receiptRawSha256\')) is str\n                and len(result[\'overlay\'][\'receiptRawSha256\'])==64\n                and result[\'overlay\'].get(\'verification\',{}).get(\'overlay_sha256\')==PIN[\'overlay\']\n                and result[\'overlay\'][\'verification\'].get(\'target\')==\'image\',\'overlay_result\')\n        _,raw=command([\'/usr/bin/docker\',\'wait\',cid],work_end)\n        require(raw.strip()==b\'0\',\'container_exit\')\n        value=inspect(cid,work_end); verify_container(value,cid)\n        require(value[\'State\'][\'Running\'] is False and value[\'State\'][\'Pid\']==0\n                and type(value[\'State\'][\'ExitCode\']) is int and value[\'State\'][\'ExitCode\']==0,\'container_terminal\')\n        result[\'status\']=\'PASS_CONTAINER_OVERLAY_ONLY\'\n    except (OSError,ValueError,KeyError,TypeError,Refused):\n        result[\'status\']=\'FAILED_DIAGNOSTIC\'\n    finally:\n        signal.signal(signal.SIGTERM,signal.SIG_IGN); signal.signal(signal.SIGINT,signal.SIG_IGN)\n        try:\n            if created_attempted:\n                value=inspect(PIN[\'name\'],cleanup_end)\n                if value is not None:\n                    owned=verify_container(value,cid)\n                    command([\'/usr/bin/docker\',\'rm\',\'--force\',owned],cleanup_end)\n                _,raw=command([\'/usr/bin/docker\',\'container\',\'ls\',\'--all\',\'--no-trunc\',\'--filter\',\'name=^/\'+PIN[\'name\']+\'$\',\'--format\',\'{{.Names}}\'],cleanup_end)\n                require(PIN[\'name\'] not in raw.decode().splitlines(),\'cleanup_absence\')\n                result[\'ownedContainerAbsent\']=True if creator_complete else \'NOT_PROVEN_CREATOR_DAEMON_DISPOSITION_UNRESOLVED\'\n                if not creator_complete: result[\'status\']=\'FAILED_UNRESOLVED_CREATE\'\n            else: result[\'ownedContainerAbsent\']=\'NO_CREATE_ATTEMPT\'\n            require(pathlib.Path(\'/proc/sys/kernel/random/boot_id\').read_text().strip()==PIN[\'boot\'],\'boot_after\')\n        except (OSError,ValueError,KeyError,TypeError,Refused):\n            result[\'ownedContainerAbsent\']=\'NOT_PROVEN\'; result[\'status\']=\'FAILED_CLEANUP\'\n        result[\'elapsedSeconds\']=time.monotonic()-beginning; result[\'commands\']=COMMANDS\n        try: journal({\'result\':result})\n        except (OSError,ValueError): result[\'journalComplete\']=False; result[\'status\']=\'FAILED_JOURNAL\'\n        os.close(AUDIT)\n    print(json.dumps(result,sort_keys=True))\n    return 0 if result[\'status\']==\'PASS_CONTAINER_OVERLAY_ONLY\' and result[\'ownedContainerAbsent\'] is True else 1\nif __name__==\'__main__\': raise SystemExit(main())\n'


def container_program():
    # Exact reviewed verifier executes in the container namespace. No package,
    # torch, runtime, model, HTTP or credential imports are performed.
    return r"""import hashlib, json, os, stat
def read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_nlink!=1 or s.st_mode&0o022 or s.st_size>262144:
            raise ValueError('protected_container_file')
        raw=os.read(fd,262145)
        after=os.fstat(fd); named=os.stat(path,follow_symlinks=False)
        signature=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_gid,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if len(raw)!=s.st_size or signature(s)!=signature(after) or signature(s)!=signature(named):
            raise ValueError('container_file_changed')
        return raw
    finally: os.close(fd)
verifier=read('/opt/llmctl/adaptive-idle/verify.py')
digest=hashlib.sha256(verifier).hexdigest()
if digest!='554c6ffc6c76fef28a3c778cd25ee1160a21a771906f95a7fea3418682ece00d':
    raise ValueError('reviewed_verifier_mismatch')
receipt=read('/opt/llmctl/adaptive-idle/image.json')
scope={'__name__':'image_adaptive_verifier','__file__':'/opt/llmctl/adaptive-idle/verify.py'}
exec(compile(verifier,scope['__file__'],'exec'),scope)
verified=scope['verify_installed']('/opt/llmctl/adaptive-idle/image.json','dda84e200adcc6a1ee8915e0e993627695477a346c5848fc27f9251c34d04b3b','image')
if receipt!=read('/opt/llmctl/adaptive-idle/image.json') or verifier!=read('/opt/llmctl/adaptive-idle/verify.py'):
    raise ValueError('container_overlay_changed')
print(json.dumps({'verifierRawSha256':digest,'receiptRawSha256':hashlib.sha256(receipt).hexdigest(),'verification':verified},sort_keys=True))
"""


def container_preflight_request(root=ROOT):
    name='h044-i03-image21-preflight-f7c7a4d8'
    pin={'platform':MANIFEST,'config':OCI_CONFIG,'parentForbidden':PARENT,
         'boot':'424b2823-b27c-4b3c-88b3-0ae9f4e7106d',
         'owner':'H044-I03-IMAGE21-PREFLIGHT-f7c7a4d8',
         'invocation':'f7c7a4d8979f4e089d340c7976f8e9c1','name':name,
         'goId':'H044-I03-IMAGE21-PREFLIGHT-01','revision':SGLANG,
         'sourceSha256':sha((root/'scripts/h044/image_backend_preparation.py').read_bytes()),
         'overlay':'dda84e200adcc6a1ee8915e0e993627695477a346c5848fc27f9251c34d04b3b',
         'verifier':'554c6ffc6c76fef28a3c778cd25ee1160a21a771906f95a7fea3418682ece00d',
         'stageRoot':'/run/llmctl/'+name,'containerProgram':container_program()}
    program=('#!/usr/bin/env python3\nPIN='+repr(pin)+'\n'+PREFLIGHT_BODY).encode()
    scope={'__name__':'source_packet'}
    exec(compile(program,'<offline-preflight>','exec'),scope)
    return {'schema':'h044-image21-container-preflight-request-v1',
        'authorization':'REQUEST_ONLY_NO_GO','pin':pin,'helperSha256':sha(program),
        'helperBytes':len(program),'helperFilename':'image21-preflight.py',
        'createArgv':scope['create_argv'](),
        'transportArgv':['/usr/bin/ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8',
            '-o','ConnectionAttempts=1','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1',
            'ai-vm','/usr/bin/sudo','-n','/usr/bin/python3','-I','-B',pin['stageRoot']+'/image21-preflight.py'],
        'transportProposal':{'staging':'Root alone stages these exact bytes plus a NEW ROOT-GO.json under the exact root-owned0700 stage directory; exclusive0600 files, protected ancestry/FD/hash validation. Separate finite source-bound staging/diagnostic approval required. No transport executed by I03.',
            'stdout':'protected original Mac stdout/stderr files and actual child terminal; remote exclusive0600 PREFLIGHT-JOURNAL.jsonl stores original command logs before parsing',
            'outerDeadlineSeconds':145,'remoteSeconds':120,'workSeconds':65,'cleanupReserveSeconds':45,
            'transportInvocations':1,'createCount':1,'startAttachCount':1,'waitCount':1,
            'allPathCleanup':'Reinspect exact unique name/CID, full diagnostic ownership/isolation/image/program labels before force removal; successful inventory absence required. Ambiguous owner refuses removal and reports NOT_PROVEN.',
            'GOFields':{'status':'GO','issuedBy':'root','goId':pin['goId'],'bootId':pin['boot'],
                'helperSha256':sha(program),'sourceSha256':pin['sourceSha256'],'containerName':name,
                'maximumInvocations':1,'notBeforeUtc':'ROOT_MUST_SET_EXACT_CURRENT_UTC',
                'expiresUtc':'ROOT_MUST_SET_FINITE_UTC_WITH_120_SECONDS_REMAINING',
                'actions':['cached_image_inspect','owned_gpu_free_create_start_attach_wait_inspect_remove']}},
        'cacheRelationship':{'status':'BLOCKED_EXACT_CACHE_FD_PATH_NOT_AVAILABLE',
            'platformManifest':MANIFEST,'configDigest':OCI_CONFIG,
            'requirement':'Separate exact known root-owned no-follow cache blob paths/FDs; raw platform/config hash and descriptor relationship. No store discovery, inference, image export/save, layers or network in this packet.'},
        'qualification':'NOT_TESTED; overlay-only PASS cannot qualify OCI config relationship, lifecycle, GPU, model, generation or native Sova admission'}, program

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(packet(), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
