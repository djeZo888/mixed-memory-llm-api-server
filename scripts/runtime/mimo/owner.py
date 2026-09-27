#!/usr/bin/env python3
"""Single supervised MiMo production owner. Import is inert; deployment is separate."""
import contextlib
import http.client
import math
import uuid
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

BASE = Path('/data/services/mimo-h016-20260927')
OWNER = 'H016-MIMO-PERSISTENT-20260927'
MODEL = 'mimo-v2.6-pro-rl'
GPU = 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
IMAGE = 'sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e'
REVISION = 'ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d'
UNIT = 'llm-frontier-mimo.service'
GLM = 'glm-5.3-flash'
GLM_UNIT = 'llm-frontier-flash.service'
GLM_BASE = Path('/data/services/flash-h008-20260926')
RUNTIME_REVISION = '7ac59a6e3ad851cd41af00f678effab0598ba9a8'
TEMPLATE = '16b2dac352c6cf1aef8b0a976618c76deb28c5bf3aba4c8b788fb846aa3769a4'
RAW_TEMPLATE = '11ea52e156de38a458e6b7720ad45915d65b97d4ec979a09f55e3c9bd1b4d059'
NUMACTL_SHA = 'f3944bcd7848d64424f8daf27f350b03d7f3281b2fb9be5eaaba0ddd0e72efb8'
LIBNUMA_SHA = '02d7582c5d391e460e56aa67a414360e3183b968206645b9123f9dc7bff5d009'
MODEL_PATH = '/models/MXFP4/MiMo-V2.6-Pro-RL-MXFP4-00001-of-00013.gguf'
PREP = Path('/data/build/h014-pro-7ac59a6-20260927/prep.py')
PREP_SHA = '03c0933c194c79a6aca5e98e26bd1682f99927c0f9dbfe53f25d9938caf3724c'
HEX = re.compile(r'[0-9a-f]{64}\Z')
BOOT = Path('/proc/sys/kernel/random/boot_id')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def protected(path):
    """Bounded protected read, also used before importing the pinned guard adapter."""
    path = Path(path)
    for parent in path.parents:
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022, 'protected_parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and not before.st_mode & 0o022 and before.st_size <= 2 * 1024 * 1024, 'protected_file')
        raw = os.read(fd, before.st_size + 1)
        sig = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and sig(before) == sig(os.fstat(fd)) == sig(path.lstat()), 'protected_file_changed')
        return raw
    finally:
        os.close(fd)


def read(path):
    return json.loads(protected(path))


def run(argv, timeout=10):
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        raw, _ = child.communicate(timeout=timeout)
        require(child.returncode == 0, 'command_failed')
        require(len(raw) <= 2 * 1024 * 1024, 'command_output_bound')
        return raw.decode()
    except BaseException:
        if child.poll() is None:
            child.kill()
            try:
                child.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                pass  # No unbounded reap on mandatory safety path; caller stops owner.
        raise
    finally:
        child.stdout.close()


@contextlib.contextmanager
def bounded(seconds=5):
    """Whole mandatory sample deadline, not a timeout per mapping/file."""
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise TimeoutError('mandatory_guard_timeout')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def ticks(pid):
    return Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()[19]


def unit_identity():
    values = dict(x.split('=', 1) for x in run(['systemctl', 'show', UNIT, '-p', 'MainPID,InvocationID,ActiveState,ControlGroup'], 2).splitlines())
    require(values['ActiveState'] in ('active', 'activating') and int(values['MainPID']) == os.getpid(), 'supervisor_not_current')
    cg = Path('/proc', str(os.getpid()), 'cgroup').read_text().split('::', 1)[1].strip()
    require(cg == values['ControlGroup'] and cg.startswith('/system.slice/'), 'supervisor_cgroup_changed')
    return {'unit': UNIT, 'pid': os.getpid(), 'invocation_id': values['InvocationID']}


def native_identity(c):
    pid = c['State']['Pid']
    require(c['State']['Running'] and type(pid) is int and pid > 0, 'native_not_running')
    return {'container_id': c['Id'], 'name': c['Name'].lstrip('/'), 'pid': pid,
            'pid_start_ticks': ticks(pid), 'started_at': c['State']['StartedAt'], 'image_id': c['Image']}


def inspect(name):
    return json.loads(run(['docker', 'inspect', name], 2))[0]


def cgpath(pid):
    return Path('/sys/fs/cgroup' + Path('/proc', str(pid), 'cgroup').read_text().split('::', 1)[1].strip())


def memory():
    return {x.split(':')[0]: int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines()}


def selection():
    value = read(BASE / 'selection.json')
    require(value.get('schema_version') == 1 and value.get('selected_frontier') in (MODEL, GLM)
            and type(value.get('generation')) is int and value['generation'] > 0, 'selection_invalid')
    if value['selected_frontier'] == MODEL:
        require(isinstance(value.get('manifest_sha256'), str) and HEX.fullmatch(value['manifest_sha256']), 'selection_manifest_required')
    return value


def require_selected(manifest, expected=None):
    value = selection()
    require(value['selected_frontier'] == MODEL and value['manifest_sha256'] == digest(manifest)
            and (expected is None or value == expected), 'selection_changed_or_not_mimo')
    return value


def launch_args(manifest):
    raw = protected(BASE / 'source/launch.json')
    require(hashlib.sha256(raw).hexdigest() == manifest['source_sha256'][str(BASE / 'source/launch.json')], 'launch_source_changed')
    argv = json.loads(raw)['native_argv']
    for name in ('--ctx-size', '--kv-unified-per-slot'):
        argv[argv.index(name) + 1] = str(manifest['context'])
    require(type(manifest.get('no_host')) is bool, 'reviewed_no_host_required')
    if manifest['no_host']:
        argv.append('--no-host')
    require(argv == manifest.get('native_argv'), 'reviewed_native_argv_changed')
    return argv


def validate_manifest(m):
    require(m.get('schema_version') == 2 and m.get('owner') == OWNER
            and m.get('service_id') == MODEL and m.get('qualified') is True, 'reviewed_qualified_manifest_required')
    require(type(m.get('context')) is int and 65536 < m['context'] <= 1048576
            and m.get('parallel') == 1 and m.get('slot_id') == 0 and m.get('max_output_tokens') == 65536,
            'reviewed_capacity_required')
    require(m.get('image_id') == IMAGE and m.get('model_revision') == REVISION
            and m.get('runtime_revision') == RUNTIME_REVISION and m.get('required_gpu_uuids') == [GPU]
            and m.get('template_sha256') == TEMPLATE and m.get('raw_template_sha256') == RAW_TEMPLATE
            and m.get('raw_template_bytes') == 3867 and m.get('template_bytes') == 3866
            and m.get('model_path') == MODEL_PATH and m.get('build_info') == 'b1-7ac59a6', 'native_pins_required')
    require(m.get('tool_template_sha256') is None or (isinstance(m.get('tool_template_sha256'), str)
            and HEX.fullmatch(m['tool_template_sha256'])), 'tool_template_pin_invalid')
    require(isinstance(m.get('container_name'), str) and re.fullmatch(r'llm-frontier-mimo-[a-z0-9-]{1,64}', m['container_name']), 'production_container_name_required')
    budget = m.get('memory', {})
    require(all(type(budget.get(k)) is int and budget[k] > 0 for k in
                ('limit_bytes', 'qualified_peak_bytes', 'startup_cache_bytes'))
            and budget['limit_bytes'] >= budget['qualified_peak_bytes'] + budget['startup_cache_bytes'],
            'reviewed_memory_peak_and_cache_required')
    artifact = m.get('artifact', {})
    require(artifact.get('verified_shards') == 13 and artifact.get('verified_bytes') == 577669438240
            and artifact.get('tensor_counts') == {'MXFP4': 207, 'BF16': 163, 'F32': 357}
            and len(artifact.get('files', [])) == 13, 'verified_artifact_required')
    require(isinstance(m.get('source_sha256'), dict) and isinstance(m.get('qualification_sha256'), dict)
            and m['qualification_sha256'], 'source_and_qualification_pins_required')
    require(type(m.get('no_host')) is bool and isinstance(m.get('native_argv'), list), 'reviewed_launch_required')
    require(m.get('numactl_sha256') == NUMACTL_SHA and m.get('libnuma_sha256') == LIBNUMA_SHA,
            'interleave_pins_required')
    require(isinstance(m.get('glm_preserved_sha256'), dict) and set(m['glm_preserved_sha256']) ==
            {'config.json', 'source/owner.py'}, 'preserved_glm_pins_required')


def setup():
    require(hashlib.sha256(protected(PREP)).hexdigest() == PREP_SHA, 'guard_adapter_changed')
    spec = importlib.util.spec_from_file_location('mimo_guard_adapter', PREP)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    h.setup()  # Only installed pinned guards/registered UUIDs, never H014 gate().
    registration = h.s.read_registration()
    require(registration['data']['path'] == '/data' and registration['models']['path'] == '/data/models-large', 'registered_mount_changed')
    return h


def storage_paths(h, guard):
    for path in (BASE, h.MODEL, '/data/docker', '/data/containerd', GLM_BASE,
                 '/data/services/secrets/llm-api-key'):
        guard.check_path(str(path))


def write(h, filename, value):
    # Status writes do not acquire the lifecycle lease. Anchored registered I/O
    # and root-disk guards remain mandatory before/after every write boundary.
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(BASE), g) as a:
        h.s.root_payload_guard()
        a.atomic_json(filename, value)
        h.s.root_payload_guard()


def source_preflight(h, m):
    validate_manifest(m)
    required = {str(BASE / 'source' / n) for n in ('owner.py', 'private_proxy.py', 'launch.json')}
    required |= {'/usr/local/lib/llm-server/node-api/scripts/control/' + n
                 for n in ('node.py', 'node_observation.py', 'node_collectors.py', 'passive.py')}
    require(required <= set(m['source_sha256']), 'deployed_source_closure_required')
    with h.MountedStorageGuard(h.s) as g:
        storage_paths(h, g)
        h.s.root_payload_guard()
        for filename, sha in {**m['source_sha256'], **m['qualification_sha256']}.items():
            require(Path(filename).is_absolute() and HEX.fullmatch(sha)
                    and hashlib.sha256(protected(filename)).hexdigest() == sha, 'reviewed_file_changed')
        for name, sha in m['glm_preserved_sha256'].items():
            require(HEX.fullmatch(sha) and hashlib.sha256(protected(GLM_BASE / name)).hexdigest() == sha, 'glm_original_changed')
        for name, sha in [('numactl', NUMACTL_SHA), ('libnuma.so.1.0.0', LIBNUMA_SHA)]:
            require(hashlib.sha256(protected(BASE / 'source' / name)).hexdigest() == sha, 'interleave_file_changed')
        require(hashlib.sha256(protected(GLM_BASE / 'source/numa-seccomp.json')).hexdigest() == '835759ce29944318d0a8de36cc62940e79125a15eedec3448fde1edd3fa320bf', 'numa_seccomp_changed')
        launch_args(m)
        expected = h.manifest()['files']
        for file, pin in zip(m['artifact']['files'], expected):
            require(file['name'] == pin['rfilename'] and file['sha256'] == pin['lfs']['sha256']
                    and file['size'] == pin['size'], 'artifact_manifest_changed')
            path = Path(h.MODEL, file['name'])
            g.check_path(str(path))
            st = path.lstat()
            require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022
                    and {k: getattr(st, 'st_' + k) for k in ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns')} == file['stat'], 'verified_shard_changed')
        require(inspect(IMAGE)['Id'] == IMAGE, 'runtime_image_changed')
        h.s.root_payload_guard()


def read_key(h):
    with h.MountedStorageGuard(h.s) as g:
        g.check_path('/data/services/secrets/llm-api-key')
        raw = protected('/data/services/secrets/llm-api-key').rstrip()
        require(1 <= len(raw) <= 4096 and all(33 <= x <= 126 for x in raw), 'key_invalid')
        return raw


def get(path, key, timeout=1):
    c = http.client.HTTPConnection('127.0.0.1', 30012, timeout=timeout)
    try:
        c.request('GET', path, headers={'Authorization': 'Bearer ' + key.decode()})
        r = c.getresponse()
        raw = r.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'native_response_limit')
        return r.status, json.loads(raw)
    finally:
        c.close()


def native_ready(m, key):
    code, props = get('/props', key)
    slot_code, slots = get('/slots', key)
    if code == 503 or slot_code == 503:
        return False  # Loading only; malformed successful identity remains fatal.
    template = props.get('chat_template')
    tool = props.get('chat_template_tool_use')
    require(code == slot_code == 200 and props.get('model_alias') == MODEL
            and props.get('build_info') == m['build_info'] and props.get('model_path') == m['model_path']
            and props.get('is_sleeping') is False and type(props.get('total_slots')) is int and props['total_slots'] == 1
            and props.get('default_generation_settings', {}).get('n_ctx') == m['context']
            and isinstance(template, str) and len(template.encode()) == 3866
            and hashlib.sha256(template.encode()).hexdigest() == TEMPLATE
            and (None if 'chat_template_tool_use' not in props else
                 hashlib.sha256(tool.encode()).hexdigest() if isinstance(tool, str) else 'invalid') == m.get('tool_template_sha256')
            and all(props.get('modalities', {}).get(k) is False for k in ('vision', 'video', 'audio'))
            and isinstance(slots, list) and len(slots) == 1 and slots[0].get('id') == 0
            and slots[0].get('n_ctx') == m['context'] and slots[0].get('speculative') is False
            and type(slots[0].get('is_processing')) is bool
            and 'prompt' not in slots[0] and 'generated' not in slots[0], 'native_identity_or_capacity_changed')
    return True


def temperature_limit(xml):
    rows = [g for g in ET.fromstring(xml).findall('gpu') if g.findtext('uuid') == GPU]
    require(len(rows) == 1, 'owned_gpu_missing')
    limits = [85.0]
    for name in ('gpu_temp_slow_threshold', 'gpu_temp_shutdown_threshold'):
        raw = rows[0].findtext('temperature/' + name, '')
        try:
            value = float(raw.split()[0])
            if 'C' in raw and 0 < value < 150:
                limits.append(value)
        except (ValueError, IndexError):
            pass
    return min(limits)


def validate_sample(m, sample, baseline, limit):
    """Own frontier GPU only; other owners enforce their own GPU reserves."""
    rows, mem = sample['gpus'], sample['host']
    own = [r for r in rows if r['uuid'] == GPU]
    require(len(own) == 1, 'owned_gpu_missing')
    row = own[0]
    require(all(type(row.get(k)) in (int, float) and math.isfinite(row[k]) for k in ('total_mib', 'free_mib', 'temp_c'))
            and row['total_mib'] > 0 and 0 <= row['temp_c'] < limit
            and row['free_mib'] * 100 >= 7 * row['total_mib'], 'owned_gpu_reserve_or_temperature')
    require(mem['MemTotal'] == baseline['MemTotal'] and mem['MemAvailable'] >= .15 * mem['MemTotal'], 'host_reserve')
    require(mem['SwapTotal'] == baseline['SwapTotal']
            and mem['SwapTotal'] - mem['SwapFree'] <= baseline['SwapTotal'] - baseline['SwapFree'], 'added_host_swap')
    cg = sample.get('cgroup')
    if cg is not None:
        require(int(cg['memory.max']) == m['memory']['limit_bytes']
                and int(cg['memory.current']) <= m['memory']['limit_bytes']
                and int(cg['memory.swap.current']) == 0
                and int(cg['memory.swap.max']) == 0
                and all(int(cg['memory.events'].get(k, 0)) == 0 for k in ('oom', 'oom_kill')), 'native_memory_oom_or_swap')
    return row


def sample_guard(m, baseline, limit, native=None):
    # R4 cheap guard behavior: one own-GPU query <=2s, host and cgroup only.
    raw = run(['nvidia-smi', '--id=' + GPU, '--query-gpu=uuid,memory.total,memory.free,temperature.gpu', '--format=csv,noheader,nounits'], 2)
    rows = []
    for line in raw.splitlines():
        fields = [x.strip() for x in line.split(',')]
        require(len(fields) == 4, 'owned_gpu_sample_invalid')
        rows.append(dict(zip(('uuid', 'total_mib', 'free_mib', 'temp_c'), [fields[0]] + [float(v) for v in fields[1:]])))
    sample = {'gpus': rows, 'host': memory()}
    if native is not None:
        cg = cgpath(native['pid'])
        sample['cgroup'] = {n: (cg / n).read_text().strip() for n in
                           ('memory.current', 'memory.max', 'memory.swap.current', 'memory.swap.max')}
        sample['cgroup']['memory.events'] = dict(x.split() for x in (cg / 'memory.events').read_text().splitlines())
    validate_sample(m, sample, baseline, limit)
    return sample


def latch(h, boot):
    from lifecycle.storage_binding import RegisteredStorageBinding
    from lifecycle.manager import StorageRunner
    from lifecycle.hardware_policy import read_latch_status
    result = read_latch_status(RegisteredStorageBinding.read_registered(StorageRunner()), [GPU], current_boot_id=boot)
    require(result.get('hardware_latched') is False, 'owned_gpu_latch_unproven')
    return result


def create_argv(h, m, launch_id):
    limit = str(m['memory']['limit_bytes'])
    return ['docker', 'create', '--name', m['container_name'], '--network', 'host', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--security-opt', 'seccomp=' + str(GLM_BASE / 'source/numa-seccomp.json'),
            '--log-driver', 'local', '--log-opt', 'max-size=64m', '--log-opt', 'max-file=2', '--restart', 'no',
            '--cpuset-cpus', '0-7,16-71', '--cpuset-mems', '0-7', '--memory', limit, '--memory-swap', limit,
            '--gpus', 'device=' + GPU, '--label', 'io.h016.owner=' + OWNER,
            '--label', 'io.h016.manifest=' + digest(m), '--label', 'io.h016.launch=' + launch_id,
            '--mount', 'type=bind,src=' + h.MODEL + ',dst=/models,readonly',
            '--mount', 'type=bind,src=/data/services/secrets/llm-api-key,dst=/run/secrets/llm-api-key,readonly',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=1g', '--env', 'CUDA_CACHE_DISABLE=1', '--env', 'OMP_NUM_THREADS=1',
            '--mount', 'type=bind,src=' + str(BASE / 'source/numactl') + ',dst=/usr/bin/numactl,readonly',
            '--mount', 'type=bind,src=' + str(BASE / 'source/libnuma.so.1.0.0') + ',dst=/usr/lib/x86_64-linux-gnu/libnuma.so.1,readonly',
            '--entrypoint', '/usr/bin/numactl', IMAGE, '--interleave=0-7', '/opt/llama/llama-server'] + launch_args(m)


def exact_container(c, m, state, *, configuration=True):
    labels = c['Config'].get('Labels', {})
    if configuration:
        host = c['HostConfig']
        require(c['Config']['Entrypoint'] == ['/usr/bin/numactl']
                and c['Config']['Cmd'] == ['--interleave=0-7', '/opt/llama/llama-server'] + m['native_argv']
                and host['Memory'] == host['MemorySwap'] == m['memory']['limit_bytes']
                and host['ReadonlyRootfs'] is True and host['NetworkMode'] == 'host'
                and host['RestartPolicy']['Name'] == 'no' and not host['Privileged']
                and host['CpusetCpus'] == '0-7,16-71' and host['CpusetMems'] == '0-7'
                and host['CapDrop'] == ['ALL'] and len(host['DeviceRequests']) == 1
                and host['DeviceRequests'][0]['DeviceIDs'] == [GPU], 'native_configuration_changed')
        mounts = {x['Destination']: (x['Source'], x['RW']) for x in c['Mounts'] if x['Type'] == 'bind'}
        require(mounts == {'/models': ('/data/models-large/mimo-v2.6-pro-rl-ba4eabb7', False),
                '/run/secrets/llm-api-key': ('/data/services/secrets/llm-api-key', False),
                '/usr/bin/numactl': (str(BASE / 'source/numactl'), False),
                '/usr/lib/x86_64-linux-gnu/libnuma.so.1': (str(BASE / 'source/libnuma.so.1.0.0'), False)}, 'native_bind_changed')
    require(c['Name'] == '/' + m['container_name'] and c['Image'] == IMAGE
            and labels.get('io.h016.owner') == OWNER and labels.get('io.h016.manifest') == digest(m)
            and labels.get('io.h016.launch') == state['launch_id'], 'exact_owned_container_required')
    if state.get('native'):
        require(c['Id'] == state['native']['container_id'] and c['State']['StartedAt'] == state['native']['started_at'], 'native_generation_changed')
        if c['State']['Running']:
            require(native_identity(c) == state['native'], 'native_process_changed')
    elif state.get('container_id'):
        require(c['Id'] == state['container_id'], 'created_container_changed')
    return c


def stop_exact(h, m, state):
    """Recovery uses exact protected launch labels, including create/start gaps."""
    with h.acquire_lease(blocking=False), h.MountedStorageGuard(h.s) as g:
        storage_paths(h, g)
        h.s.root_payload_guard()
        found = run(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + m['container_name'] + '$'], 2).strip()
        if found:
            c = exact_container(inspect(found), m, state, configuration=False)
            native = state.get('native')
            pid = native['pid'] if native else c['State']['Pid']
            cg = Path(state['native_cgroup']) if state.get('native_cgroup') else (cgpath(pid) if pid else None)
            if c['State']['Running']:
                run(['docker', 'stop', '--time', '3', c['Id']], 7)
            after = exact_container(inspect(c['Id']), m, state, configuration=False)
            require(not after['State']['Running'] and after['State']['Pid'] == 0, 'container_not_settled')
            if native and Path('/proc', str(pid)).exists():
                require(ticks(pid) != native['pid_start_ticks'], 'old_native_pid_remains')
            require(cg is None or not cg.exists() or not (cg / 'cgroup.procs').read_text().strip(), 'native_cgroup_not_empty')
        else:
            require(not state.get('container_id') and not state.get('native'), 'owned_container_missing_requires_review')
        require(not run(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits'], 2).strip(), 'frontier_compute_remains')
        h.s.root_payload_guard()
    return {'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True}


def stop_proxy(proxy):
    if proxy is not None and proxy.poll() is None:
        proxy.terminate()
        try:
            proxy.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proxy.kill()
            proxy.wait(timeout=2)


def proxy_snapshot(state, proxy):
    require(proxy.poll() is None, 'proxy_child_died')
    value = read(BASE / 'proxy-state.json')
    if value.get('launch_id') != state['launch_id'] and state['status'] == 'STARTING_PROXY':
        raise FileNotFoundError('proxy_receipt_not_yet_published')
    require(value.get('schema_version') == 2 and value.get('launch_id') == state['launch_id']
            and value.get('native') == state['native'] and value.get('boot_id') == state['boot_id']
            and value.get('pid') == proxy.pid and value.get('pid_start_ticks') == ticks(proxy.pid)
            and value.get('parent_pid') == os.getpid()
            and type(value.get('active_requests')) is int and value['active_requests'] in (0, 1)
            and type(value.get('quarantined')) is bool, 'proxy_child_identity_or_disposition')
    return value


def settle_state(h, m, state, proxy=None):
    state['status'] = 'SETTLING'
    # Preserve ambiguous active requests even if the child dies before its final write.
    try:
        p = read(BASE / 'proxy-state.json')
        if p.get('launch_id') == state['launch_id']:
            state['request_hold'] = state.get('request_hold', False) or p.get('quarantined') is not False or p.get('active_requests') != 0
    except (OSError, ValueError, RuntimeError):
        state['request_hold'] = bool(state.get('proxy_started')) or state.get('request_hold', False)
    try:
        try:
            stop_proxy(proxy)
        finally:
            # Failed status writes must never skip physical settlement.
            state['settlement'] = stop_exact(h, m, state)
    except BaseException:
        state.update(status='HELD', request_hold=True, settlement=None)
        try:
            write(h, 'state.json', state)
        except Exception:
            pass  # Guard proof ages out; no successful settlement is published.
        raise
    state['status'] = 'SETTLED'
    write(h, 'state.json', state)
    return state


def assert_launch_admission(m, selected, previous):
    require(selected['selected_frontier'] == MODEL and selected.get('manifest_sha256') == digest(m), 'not_selected')
    if previous is not None:
        require(previous.get('schema_version') == 2 and previous.get('status') == 'SETTLED'
                and previous.get('settlement') == {'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True}
                and previous.get('request_hold') is False, 'prior_owner_or_request_unsettled')


def supervise(dry_run=False):
    m = read(BASE / 'manifest.json')
    h = setup()
    source_preflight(h, m)
    selected = require_selected(m)
    try:
        previous = read(BASE / 'state.json')
    except FileNotFoundError:
        previous = None
    assert_launch_admission(m, selected, previous)
    if dry_run:
        return {'status': 'SOURCE_PREFLIGHT_ONLY', 'manifest_sha256': digest(m)}
    supervisor = unit_identity()
    boot = BOOT.read_text().strip()
    state = {'schema_version': 2, 'status': 'CREATING', 'boot_id': boot, 'manifest_sha256': digest(m),
             'selection': selected, 'supervisor': supervisor, 'launch_id': uuid.uuid4().hex,
             'native': None, 'request_hold': False, 'proxy_started': False}
    proxy = None
    proxy_deadline = None
    admitted = False
    try:
        with h.acquire_lease(blocking=False) as lease, h.MountedStorageGuard(h.s) as g:
            storage_paths(h, g)
            h.s.root_payload_guard()
            require_selected(m, selected)
            # Competing boot intent is gated by GLM's reviewed ExecCondition.
            glm = dict(x.split('=', 1) for x in run(['systemctl', 'show', GLM_UNIT, '-p', 'MainPID,ActiveState'], 2).splitlines())
            require(glm['MainPID'] == '0' and glm['ActiveState'] in ('inactive', 'failed'), 'glm_must_be_settled_before_selection')
            require(not run(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits'], 2).strip(), 'frontier_compute_present')
            with bounded():
                baseline = memory()
                require(m['memory']['limit_bytes'] <= baseline['MemAvailable'] - .15 * baseline['MemTotal'], 'reviewed_memory_exceeds_fresh_reserve')
                limit = temperature_limit(run(['nvidia-smi', '--id=' + GPU, '-q', '-x'], 2))
                sample_guard(m, baseline, limit)
                latch(h, boot)
            found = run(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + m['container_name'] + '$'], 2).strip()
            if found:
                require(previous is not None and previous.get('manifest_sha256') == digest(m), 'unrecorded_container_exists')
                c = exact_container(inspect(found), m, previous)
                require(not c['State']['Running'] and c['State']['Pid'] == 0, 'no_double_launch')
                run(['docker', 'rm', c['Id']], 5)  # Only exact previously settled owner.
            state['baseline'] = baseline
            write(h, 'state.json', state)
            admitted = True
            state['container_id'] = run(create_argv(h, m, state['launch_id']), 10).strip()
            require(HEX.fullmatch(state['container_id']), 'created_id_invalid')
            write(h, 'state.json', state)
            with bounded():
                run(['docker', 'start', state['container_id']], 2)
                c = exact_container(inspect(state['container_id']), m, state)
                state.update(native=native_identity(c), native_cgroup=str(cgpath(c['State']['Pid'])), status='LOADING')
                write(h, 'state.json', state)
                h.s.root_payload_guard()
        key = read_key(h)
        load_end = time.monotonic() + 1800
        while True:
            cycle = time.monotonic()
            with bounded():
                require_selected(m, selected)
                require(BOOT.read_text().strip() == boot, 'boot_changed')
                exact_container(inspect(state['native']['container_id']), m, state)
                sample = sample_guard(m, baseline, limit, state['native'])
                hardware = latch(h, boot)
                if state['status'] == 'LOADING':
                    require(time.monotonic() < load_end, 'native_load_timeout')
                    ready = False
                    try:
                        ready = native_ready(m, key)
                    except TimeoutError:
                        raise
                    except (ConnectionError, OSError, http.client.HTTPException):
                        pass  # Loading may not have bound the native endpoint yet.
                    if ready is True:
                        state['status'] = 'STARTING_PROXY'
                        write(h, 'state.json', state)
                        proxy = subprocess.Popen(['/usr/bin/python3', '-I', '-B', str(BASE / 'source/private_proxy.py')],
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        proxy_deadline = time.monotonic() + 5
                        state['proxy_started'] = True
                        write(h, 'state.json', state)
                disposition = None
                if proxy is not None:
                    require(proxy.poll() is None, 'proxy_child_died')
                    try:
                        disposition = proxy_snapshot(state, proxy)
                    except FileNotFoundError:
                        require(state['status'] == 'STARTING_PROXY' and time.monotonic() < proxy_deadline, 'proxy_start_failed')
                    if disposition is not None:
                        state['proxy'] = {k: disposition[k] for k in ('pid', 'pid_start_ticks', 'parent_pid')}
                        if state['status'] != 'RUNNING':
                            state['status'] = 'RUNNING'
                            write(h, 'state.json', state)
                guard = {'schema_version': 2, 'status': 'ok', 'boot_id': boot, 'manifest_sha256': digest(m),
                         'selection': selected, 'supervisor': supervisor, 'native': state['native'],
                         'proxy': state.get('proxy'), 'proxy_disposition': disposition,
                         'observed_monotonic_s': time.monotonic(),
                         'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         'hardware_latched': hardware['hardware_latched'], 'hardware_proof': hardware, 'sample': sample}
                write(h, 'guard.json', guard)
            time.sleep(max(0, 5 - (time.monotonic() - cycle)))
    finally:
        if admitted:
            settle_state(h, m, state, proxy)


def rollback_glm(h, m, expected, *, dry_run=False):
    """Explicit operator rollback; never called automatically by guard failure."""
    with h.acquire_lease(blocking=False), h.MountedStorageGuard(h.s) as g:
        storage_paths(h, g)
        h.s.root_payload_guard()
        require(selection() == expected, 'selection_changed_during_rollback')
        state = read(BASE / 'state.json')
        require(state.get('status') == 'SETTLED' and state.get('request_hold') is False
                and state.get('settlement') == {'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True}, 'rollback_requires_exact_settlement')
        # Recheck physical release in caller before admission, and immutable GLM bytes.
        c = exact_container(inspect(state['native']['container_id']), m, state)
        require(not c['State']['Running'] and c['State']['Pid'] == 0, 'rollback_native_not_settled')
        require(not Path(state['native_cgroup']).exists() or not (Path(state['native_cgroup']) / 'cgroup.procs').read_text().strip(), 'rollback_cgroup_present')
        require(not run(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits'], 2).strip(), 'rollback_compute_present')
        for name, sha in m['glm_preserved_sha256'].items():
            require(hashlib.sha256(protected(GLM_BASE / name)).hexdigest() == sha, 'glm_original_changed')
        new = {'schema_version': 1, 'selected_frontier': GLM, 'generation': expected['generation'] + 1}
        if not dry_run:
            write(h, 'selection.json', new)
        h.s.root_payload_guard()
    # No canonical lease around systemctl: original GLM owner acquires its own.
    if not dry_run:
        run(['systemctl', 'start', GLM_UNIT], 190)
    return new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['supervise', 'settle', 'check-selected', 'rollback-glm'])
    p.add_argument('--service', choices=[MODEL, GLM])
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if args.action == 'check-selected':
        require(args.service is not None, 'service_required')
        return 0 if selection()['selected_frontier'] == args.service else 1
    if args.action == 'supervise':
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError('owner_interrupted')))
        supervise(args.dry_run)
        return 0
    m, h = read(BASE / 'manifest.json'), setup()
    validate_manifest(m)
    if args.action == 'settle':
        if not args.dry_run:
            state = read(BASE / 'state.json')
            require(state.get('supervisor', {}).get('invocation_id') == os.environ.get('INVOCATION_ID'), 'recovery_invocation_changed')
            settle_state(h, m, state)
    else:
        rollback_glm(h, m, selection(), dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'REFUSED', 'reason': str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__}))
        raise SystemExit(255)
