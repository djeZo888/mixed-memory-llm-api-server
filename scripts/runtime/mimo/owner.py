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
LEASE_PATH = Path('/run/llmctl/lifecycle.lock')
SETTLEMENT_LEASE_SECONDS = 10
MEMORY_SLICE = 'llmmimo.slice'
MEMORY_SLICE_PATH = Path('/sys/fs/cgroup') / MEMORY_SLICE
MEMORY_SLICE_UNIT = Path('/etc/systemd/system') / MEMORY_SLICE
OWNER_FAILURE_CODES = frozenset({
    'added_host_swap', 'artifact_manifest_changed', 'boot_changed',
    'command_failed', 'command_output_bound', 'container_not_settled',
    'created_container_changed', 'created_id_invalid', 'deployed_source_closure_required',
    'exact_owned_container_required', 'frontier_compute_present', 'frontier_compute_remains',
    'glm_must_be_settled_before_selection', 'glm_original_changed', 'guard_adapter_changed', 'guard_write_integrity',
    'host_reserve', 'host_swap_configuration_changed', 'interleave_file_changed', 'interleave_pins_required',
    'key_invalid', 'launch_source_changed', 'native_bind_changed',
    'native_cgroup_not_empty', 'native_configuration_changed', 'native_generation_changed',
    'native_identity_or_capacity_changed', 'native_load_timeout', 'native_memory_oom_or_swap',
    'native_memory_policy_changed',
    'native_not_running', 'native_pins_required', 'native_process_changed',
    'native_response_limit', 'no_double_launch', 'not_selected',
    'numa_seccomp_changed', 'old_native_pid_remains', 'owned_container_missing_requires_review',
    'owned_gpu_latch_unproven', 'owned_gpu_missing', 'owned_gpu_reserve_or_temperature',
    'owned_gpu_sample_invalid', 'owner_interrupted', 'preserved_glm_pins_required',
    'prior_owner_or_request_unsettled', 'production_container_name_required', 'protected_file',
    'protected_file_changed', 'protected_parent', 'proxy_child_died',
    'proxy_child_identity_or_disposition', 'proxy_final_identity_unknown', 'proxy_not_settled',
    'proxy_start_failed', 'recovery_invocation_changed', 'registered_mount_changed',
    'reviewed_1m_request_required', 'reviewed_capacity_required', 'reviewed_file_changed',
    'reviewed_launch_required', 'reviewed_memory_exceeds_fresh_reserve', 'reviewed_memory_peak_and_cache_required',
    'reviewed_native_argv_changed', 'reviewed_no_host_required', 'reviewed_qualified_manifest_required',
    'rollback_cgroup_present', 'rollback_compute_present', 'rollback_native_not_settled',
    'rollback_requires_exact_settlement', 'runtime_image_changed', 'selection_changed_during_rollback',
    'selection_changed_or_not_mimo', 'selection_invalid', 'selection_manifest_required',
    'service_required', 'settlement_deadline_invalid', 'settlement_lease_deadline',
    'settlement_lock_changed', 'source_and_qualification_pins_required', 'supervisor_cgroup_changed',
    'supervisor_not_current', 'tool_template_pin_invalid', 'unrecorded_container_exists',
    'verified_artifact_required', 'verified_shard_changed',
    'new_boot_recovery_invalid', 'new_boot_owner_present', 'new_boot_archive_changed',
    'new_boot_recovery_consumed', 'source_only_amendment_required',
})


class OwnerRefusal(RuntimeError):
    """Owner-generated diagnostic code; never arbitrary command/request text."""


def failure(exc, phase, operation=None, elapsed=None):
    code = 'unexpected_error'
    if type(exc) is OwnerRefusal and str(exc) in OWNER_FAILURE_CODES:
        code = str(exc)
    elif isinstance(exc, MandatoryGuardTimeout):
        code = 'mandatory_guard_timeout'
    elif isinstance(exc, TimeoutError):
        code = 'timeout'
    elif isinstance(exc, OSError):
        code = 'os_error'
    elif isinstance(exc, http.client.HTTPException):
        code = 'http_error'
    elif isinstance(exc, subprocess.TimeoutExpired):
        code = 'command_timeout'
    elif type(exc).__name__ == 'LeaseBusy':
        code = 'lifecycle_busy'
    elif type(exc).__name__ == 'LeaseError':
        code = 'lifecycle_invalid'
    result = {'phase': phase if phase in ('CREATING', 'LOADING', 'STARTING_PROXY', 'RUNNING',
            'SETTLING', 'SETTLED', 'HELD', 'CLI') else 'UNKNOWN', 'code': code,
            'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if operation in ('launch', 'key_read', 'selection_read', 'boot_read', 'docker_inspect',
                     'resource_sample', 'nvml_sample', 'host_memory', 'cgroup_memory',
                     'resource_validate', 'hardware_latch', 'native_readiness', 'http_props',
                     'http_slots', 'native_identity', 'state_write', 'proxy_start',
                     'proxy_snapshot', 'guard_write', 'cycle_sleep', 'settlement'):
        result['operation'] = operation
    if type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0:
        result['cycle_elapsed_s'] = round(elapsed, 6)
    if code == 'unexpected_error':
        safe_types = (KeyError, ValueError, RuntimeError, TypeError, AttributeError,
                      IndexError, AssertionError, OverflowError, ZeroDivisionError)
        result['exception_class'] = (type(exc).__name__ if type(exc) in safe_types
                                     else 'OtherException')
        trace = exc.__traceback__
        while trace is not None:
            if trace.tb_frame.f_code.co_filename == __file__:
                result['owner_source_line'] = trace.tb_lineno
            trace = trace.tb_next
    if hasattr(exc, 'resource_memory'):
        result['resource_memory'] = exc.resource_memory
    if hasattr(exc, 'hardware_evidence'):
        result['hardware_evidence'] = exc.hardware_evidence
    return result


def record_failure(h, state, field, exc, phase, operation=None, elapsed=None):
    """Best-effort guarded receipt plus sanitized durable systemd journal record.

    Neither a failed receipt nor a failed journal write may prevent settlement.
    """
    state[field] = failure(exc, phase, operation, elapsed)
    try:
        write(h, 'state.json', state)
    except BaseException as receipt_error:
        state['receipt_failure'] = failure(receipt_error, phase)
    try:
        print(json.dumps({'status': 'OWNER_FAILURE', 'launch_id': state['launch_id'],
                          **{k: state[k] for k in ('primary_failure', 'settlement_failure',
                             'settlement_recheck_failure', 'receipt_failure') if k in state}}), flush=True)
    except BaseException:
        pass


def require(value, reason):
    if not value:
        raise OwnerRefusal(reason)


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


class MandatoryGuardTimeout(TimeoutError):
    """The whole mandatory sample expired; never a pending readiness probe."""


@contextlib.contextmanager
def bounded(seconds=5):
    """Whole mandatory sample deadline, not a timeout per mapping/file."""
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise MandatoryGuardTimeout('mandatory_guard_timeout')
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
    context_flags = ('--ctx-size', '--kv-unified-per-slot')
    if manifest['context'] in (1000000, 1000192):
        # The reviewed 1M request may expose allocator-rounded usable capacity.
        # Preserve the source request; native_ready still requires exact actual
        # props/slots agreement with manifest.context, never invented equality.
        require(all(argv.count(name) == 1 and argv[argv.index(name) + 1] == '1000000'
                    for name in context_flags), 'reviewed_1m_request_required')
    else:
        for name in context_flags:
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
    # The measured cgroup peak already includes charged file cache. Only a
    # separately justified incremental startup allowance belongs in the sum.
    require(all(type(budget.get(k)) is int and budget[k] > 0 for k in
                ('limit_bytes', 'qualified_peak_bytes'))
            and type(budget.get('startup_cache_bytes')) is int and budget['startup_cache_bytes'] >= 0
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
    # Only periodic guard persistence omits recursive root-payload scans.
    # MountedStorageGuard and anchored I/O still verify registration, mount,
    # protected ancestry and the exact path. Lifecycle/state writes scan fully.
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(str(BASE), g) as a:
        if filename == 'guard.json':
            g.check_path(str(BASE / filename))
            a.atomic_json(filename, value)
            with a.open(filename) as stream:
                require(json.loads(stream.read()) == value, 'guard_write_integrity')
            a.check()
            return
        h.s.root_payload_guard()
        a.atomic_json(filename, value)
        h.s.root_payload_guard()


def source_preflight(h, m):
    validate_manifest(m)
    required = {str(BASE / 'source' / n) for n in ('owner.py', 'private_proxy.py', 'launch.json')}
    required.update((str(MEMORY_SLICE_UNIT), '/etc/systemd/system/' + UNIT))
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


def native_ready(m, key, *, progress=lambda _: None):
    progress('http_props')
    code, props = get('/props', key)
    progress('http_slots')
    slot_code, slots = get('/slots', key)
    if code == 503 or slot_code == 503:
        return False  # Loading only; malformed successful identity remains fatal.
    progress('native_identity')
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


def limit_value(raw):
    """Bounded kernel-value classification, never turn unlimited into zero."""
    if type(raw) is str and len(raw) <= 32:
        if raw == 'max':
            return {'class': 'max', 'raw': raw}
        if raw == '':
            return {'class': 'empty', 'raw': raw}
        if raw.isascii() and raw.isdecimal():
            return {'class': 'zero' if int(raw) == 0 else 'finite', 'raw': raw}
    # Arbitrary invalid bytes are not safe log content; retain classification.
    return {'class': 'invalid'}


def memory_policy(m, native=None):
    """The dedicated persistent parent supplies the effective zero-swap cap."""
    expected = ('[Unit]\nDescription=MiMo dedicated zero-swap boundary\n'
                '[Slice]\nMemoryAccounting=yes\nMemoryMax=' + str(m['memory']['limit_bytes']) +
                '\nMemorySwapMax=0\n')
    require(protected(MEMORY_SLICE_UNIT).decode() == expected, 'native_memory_policy_changed')
    children = []
    with os.scandir(MEMORY_SLICE_PATH) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                children.append(entry.name)
                require(len(children) <= 1, 'native_memory_policy_changed')
    require(children == ([] if native is None else ['docker-' + native['container_id'] + '.scope'])
            and not (MEMORY_SLICE_PATH / 'cgroup.procs').read_text().strip(), 'native_memory_policy_changed')
    values = {n: (MEMORY_SLICE_PATH / n).read_text().strip() for n in
              ('memory.max', 'memory.swap.max', 'memory.swap.current')}
    try:
        require(values == {'memory.max': str(m['memory']['limit_bytes']),
                           'memory.swap.max': '0', 'memory.swap.current': '0'}, 'native_memory_policy_changed')
    except OwnerRefusal as exc:
        # This boundary also runs before sample_guard's validation catch. Preserve
        # safe raw literals/classification here, without arbitrary malformed text.
        exc.resource_memory = {'memory_policy': {k: limit_value(v) for k, v in values.items()}}
        raise
    return values


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
    require(mem['SwapTotal'] == baseline['SwapTotal'], 'host_swap_configuration_changed')
    # Aggregate swap belongs to the whole host. Own swap remains forbidden below;
    # unrelated host variation is retained as evidence, not attributed to MiMo.
    sample['host_swap_diagnostic'] = {
        'baseline_used_bytes': baseline['SwapTotal'] - baseline['SwapFree'],
        'used_bytes': mem['SwapTotal'] - mem['SwapFree'],
        'delta_bytes': (mem['SwapTotal'] - mem['SwapFree']) - (baseline['SwapTotal'] - baseline['SwapFree'])}
    cg = sample.get('cgroup')
    if cg is not None:
        require(all(limit_value(cg.get(k))['class'] in ('zero', 'finite') for k in
                    ('memory.max', 'memory.current', 'memory.swap.current'))
                and all(limit_value(cg.get('memory.events', {}).get(k, '0'))['class'] in ('zero', 'finite')
                        for k in ('oom', 'oom_kill'))
                and int(cg['memory.max']) == m['memory']['limit_bytes']
                and int(cg['memory.current']) <= m['memory']['limit_bytes']
                and int(cg['memory.swap.current']) == 0
                and cg['memory.swap.max'] in ('0', 'max')
                and sample.get('memory_policy') == {'memory.max': str(m['memory']['limit_bytes']),
                    'memory.swap.max': '0', 'memory.swap.current': '0'}
                and all(int(cg['memory.events'].get(k, 0)) == 0 for k in ('oom', 'oom_kill')), 'native_memory_oom_or_swap')
    return row


def sample_guard(m, baseline, limit, native=None, *, progress=lambda _: None, proof_boot=None):
    # R4 cheap guard behavior: one own-GPU query <=2s, host and cgroup only.
    progress('nvml_sample')
    if proof_boot is not None:
        require(BOOT.read_text().strip() == proof_boot, 'boot_changed')
    raw = run(['nvidia-smi', '--id=' + GPU, '--query-gpu=uuid,memory.total,memory.free,temperature.gpu', '--format=csv,noheader,nounits'], 2)
    observed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if proof_boot is not None:
        require(BOOT.read_text().strip() == proof_boot, 'boot_changed')
    rows = []
    for line in raw.splitlines():
        fields = [x.strip() for x in line.split(',')]
        require(len(fields) == 4, 'owned_gpu_sample_invalid')
        rows.append(dict(zip(('uuid', 'total_mib', 'free_mib', 'temp_c'), [fields[0]] + [float(v) for v in fields[1:]])))
    progress('host_memory')
    sample = {'gpus': rows, 'host': memory()}
    if native is not None:
        progress('cgroup_memory')
        cg = cgpath(native['pid'])
        require(cg == MEMORY_SLICE_PATH / ('docker-' + native['container_id'] + '.scope'),
                'native_memory_policy_changed')
        sample['memory_policy'] = memory_policy(m, native)
        sample['cgroup'] = {n: (cg / n).read_text().strip() for n in
                           ('memory.current', 'memory.max', 'memory.swap.current', 'memory.swap.max')}
        sample['cgroup']['memory.events'] = dict(x.split() for x in (cg / 'memory.events').read_text().splitlines())
    progress('resource_validate')
    try:
        validate_sample(m, sample, baseline, limit)
        if proof_boot is not None:
            require(len(rows) == 1, 'owned_gpu_sample_invalid')
            # validate_sample requires one exact UUID and all existing reserves.
            sample['hardware_validation'] = {'gpu_uuid': GPU, 'boot_id': proof_boot,
                'observed_at': observed_at, 'observation_id': uuid.uuid4().hex}
    except Exception as exc:
        # Preserve the actual cheap failing sample, before the last-good receipt
        # can obscure it. No extra sampling, process scan or per-token work.
        # Diagnostic failure must never replace the original guard failure.
        # Keep only bounded numeric fields; no exception messages or locals.
        try:
            def numeric_fields(value, keys):
                value = value if type(value) is dict else {}
                return {k: v for k in keys if
                        (type(v := value.get(k)) is int or
                         (type(v) is str and len(v) <= 32 and v.isascii() and v.isdecimal()))}
            keys = ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')
            cg = sample.get('cgroup')
            safe_cg = None
            if type(cg) is dict:
                safe_cg = numeric_fields(cg, ('memory.current', 'memory.max',
                                             'memory.swap.current', 'memory.swap.max'))
                safe_cg['limit_classification'] = {k: limit_value(cg.get(k)) for k in ('memory.max', 'memory.swap.max')}
                safe_cg['memory.events'] = numeric_fields(cg.get('memory.events'),
                    ('low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill'))
            exc.resource_memory = {'host': numeric_fields(sample.get('host'), keys),
                                   'baseline': numeric_fields(baseline, keys),
                                   'cgroup': safe_cg}
        except Exception:
            pass
        raise
    return sample


def latch(h, boot, *, evidence=None, deadline=None, lease=None):
    from lifecycle.storage_binding import RegisteredStorageBinding
    from lifecycle.manager import StorageRunner
    from lifecycle.hardware_policy import read_latch_status, RegisteredLatchStore, HardwarePolicy
    from control.hardware_latch import HardwareLatch, _timestamp, MAX_AGE_MS
    diagnostic = {'stage': 'registered_read', 'refresh_attempted': False}
    def check_deadline():
        if lease is not None:
            from common.lifecycle_lease import _validate_borrowed_lease
            _validate_borrowed_lease(lease)
        # read_latch_status intentionally maps read exceptions to unknown; an
        # outer alarm swallowed there must still leave the whole cycle closed.
        if deadline is not None and time.monotonic() >= deadline:
            raise MandatoryGuardTimeout('mandatory_guard_timeout')
    try:
        check_deadline()
        binding = RegisteredStorageBinding.read_registered(StorageRunner())
        result = read_latch_status(binding, [GPU], current_boot_id=boot)
        diagnostic['pre'] = result
        check_deadline()
        if result.get('hardware_latched') is False:
            return result
        require(result.get('hardware_latched') is not True, 'owned_gpu_latch_unproven')
        diagnostic['stage'] = 'canonical_lease'
        # No waiting/retry or nested deadline: supervise's existing bounded(5)
        # covers the prior <=2s GPU sample and this entire refresh transaction.
        with (h.acquire_lease(blocking=False) if lease is None else contextlib.nullcontext(lease)) as active:
            active.validate()
            result = read_latch_status(binding, [GPU], current_boot_id=boot)
            diagnostic['under_lease'] = result
            check_deadline()
            if result.get('hardware_latched') is False:
                return result  # The scheduled producer refreshed before entry.
            diagnostic['stage'] = 'protected_state'
            store = RegisteredLatchStore(binding, lease=active)
            state = HardwareLatch(store.read()).export_state()
            check_deadline()
            record = state['targets'].get(GPU, {})
            proof = state.get('validated', {}).get(GPU, {})
            observed = _timestamp(proof.get('observed_at'))
            age = None if observed is None else (time.time() - observed) * 1000
            diagnostic['protected_proof'] = {'boot_id': proof.get('boot_id'),
                'observed_at': proof.get('observed_at'), 'age_ms': age,
                'positive_latch': record.get('hardware_latched') is True}
            require(record.get('hardware_latched') is not True, 'owned_gpu_latch_unproven')
            diagnostic['stage'] = 'stale_same_boot_required'
            require(proof.get('boot_id') == boot and age is not None and age > MAX_AGE_MS,
                    'owned_gpu_latch_unproven')
            diagnostic['stage'] = 'fresh_sample_required'
            require(isinstance(evidence, dict)
                    and set(evidence) == {'gpu_uuid', 'boot_id', 'observed_at', 'observation_id'}
                    and _timestamp(evidence.get('observed_at')) is not None
                    and re.fullmatch('[0-9a-f]{32}', str(evidence.get('observation_id')))
                    and evidence.get('gpu_uuid') == GPU
                    and evidence.get('boot_id') == boot and BOOT.read_text().strip() == boot,
                    'owned_gpu_latch_unproven')
            diagnostic['refresh_attempted'] = True
            diagnostic['sample'] = evidence
            diagnostic['stage'] = 'validate_required'
            check_deadline()
            HardwarePolicy(store, lease=active).validate_required(GPU, current_boot_id=boot,
                observed_at=evidence['observed_at'], observation_id=evidence['observation_id'])
            check_deadline()
            diagnostic['stage'] = 'post_projection'
            result = read_latch_status(binding, [GPU], current_boot_id=boot)
            diagnostic['post'] = result
            check_deadline()
            require(result.get('hardware_latched') is False, 'owned_gpu_latch_unproven')
            active.validate()
        return {**result, 'owner_refresh': diagnostic}
    except BaseException as exc:
        # Only policy projections, validated timestamps/UUIDs and fixed stages;
        # never exception text, command output, credentials or request contents.
        exc.hardware_evidence = diagnostic
        raise


def create_argv(h, m, launch_id):
    limit = str(m['memory']['limit_bytes'])
    return ['docker', 'create', '--name', m['container_name'], '--network', 'host', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--security-opt', 'seccomp=' + str(GLM_BASE / 'source/numa-seccomp.json'),
            '--log-driver', 'local', '--log-opt', 'max-size=64m', '--log-opt', 'max-file=2', '--restart', 'no',
            '--cgroup-parent', MEMORY_SLICE, '--cpuset-cpus', '0-7,16-71', '--cpuset-mems', '0-7', '--memory', limit, '--memory-swap', limit,
            '--gpus', 'device=' + GPU, '--label', 'io.h016.owner=' + OWNER,
            '--label', 'io.h016.manifest=' + digest(m), '--label', 'io.h016.launch=' + launch_id,
            '--mount', 'type=bind,src=' + h.MODEL + ',dst=/models,readonly',
            '--mount', 'type=bind,src=/data/services/secrets/llm-api-key,dst=/run/secrets/llm-api-key,readonly',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=1g', '--env', 'CUDA_CACHE_DISABLE=1', '--env', 'OMP_NUM_THREADS=1', '--env', 'GOMP_SPINCOUNT=0',
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
                and host['CgroupParent'] == MEMORY_SLICE
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


@contextlib.contextmanager
def settlement_lease(h, *, lease=None, deadline=None):
    """Only exact settlement retries contention; all trust errors fail closed."""
    if lease is not None:
        from common.lifecycle_lease import _validate_borrowed_lease
        _validate_borrowed_lease(lease)
        yield lease
        _validate_borrowed_lease(lease)
        return
    end = time.monotonic() + SETTLEMENT_LEASE_SECONDS
    if deadline is not None:
        require(type(deadline) in (int, float) and math.isfinite(deadline), 'settlement_deadline_invalid')
        end = min(end, deadline)
    def identity():
        info = LEASE_PATH.lstat()
        return info.st_dev, info.st_ino
    original = identity()
    with contextlib.ExitStack() as stack:
        while True:
            require(identity() == original, 'settlement_lock_changed')
            require(time.monotonic() < end, 'settlement_lease_deadline')
            try:
                active = stack.enter_context(h.acquire_lease(blocking=False))
            except h.LeaseBusy:
                time.sleep(min(.1, max(0, end - time.monotonic())))
                continue
            require(identity() == original, 'settlement_lock_changed')
            require(time.monotonic() < end, 'settlement_lease_deadline')
            active.validate()
            break
        yield active
        active.validate()


def stop_exact(h, m, state, *, lease=None, deadline=None):
    """Recovery uses exact protected launch labels, including create/start gaps."""
    with settlement_lease(h, lease=lease, deadline=deadline), h.MountedStorageGuard(h.s) as g:
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


def proxy_released(state, proxy):
    """Read final disposition only after the exact child can no longer admit.

    begin() persists active=1 before native I/O; finish() persists terminal
    release. An earlier idle snapshot is never evidence of final release.
    """
    try:
        if not state.get('proxy_started'):
            p = read(BASE / 'proxy-state.json')
            return isinstance(p, dict) and p.get('launch_id') != state['launch_id']
        expected = state.get('proxy', {})
        require(type(expected.get('pid')) is int and expected['pid'] > 0
                and isinstance(expected.get('pid_start_ticks'), str)
                and expected.get('parent_pid') == state['supervisor']['pid']
                and BOOT.read_text().strip() == state['boot_id'], 'proxy_final_identity_unknown')
        if proxy is not None:
            require(proxy.pid == expected['pid'] and proxy.poll() is not None, 'proxy_not_settled')
        else:
            require(not Path('/proc', str(expected['pid'])).exists()
                    or ticks(expected['pid']) != expected['pid_start_ticks'], 'proxy_not_settled')
        p = read(BASE / 'proxy-state.json')
        return (p.get('schema_version') == 2 and p.get('launch_id') == state['launch_id']
                and p.get('native') == state['native'] and p.get('boot_id') == state['boot_id']
                and all(p.get(k) == expected[k] for k in ('pid', 'pid_start_ticks', 'parent_pid'))
                and type(p.get('active_requests')) is int and p['active_requests'] == 0
                and p.get('quarantined') is False)
    except FileNotFoundError:
        return not state.get('proxy_started')
    except (OSError, ValueError, RuntimeError, KeyError, AttributeError, TypeError):
        return False


def settle_state(h, m, state, proxy=None, *, lease=None, deadline=None):
    # ExecStopPost can repeat this same protected, invocation-checked launch.
    # Preserve its earlier proof only for contention before any new physical
    # observation; the failed recheck is not fresh proof. rollback_glm always
    # rechecks exact container/cgroup/GPU/source under its own canonical lease.
    prior = dict(state) if (state.get('schema_version') == 2 and state.get('status') == 'SETTLED'
            and state.get('manifest_sha256') == digest(m)
            and state.get('proxy_started') is False and state.get('request_hold') is False
            and state.get('settlement') == {'pid_released': True, 'cgroup_empty': True,
                                          'gpu_compute_empty': True}) else None
    state['status'] = 'SETTLING'
    state.setdefault('request_hold', False)
    try:
        try:
            stop_proxy(proxy)
            state['request_hold'] = state['request_hold'] or not proxy_released(state, proxy)
        except BaseException:
            state['request_hold'] = state['request_hold'] or bool(state.get('proxy_started'))
            raise
        finally:
            # Failed status writes must never skip physical settlement.
            if lease is None and deadline is None:
                state['settlement'] = stop_exact(h, m, state)
            else:
                state['settlement'] = stop_exact(h, m, state, lease=lease, deadline=deadline)
    except BaseException as exc:
        if (prior is not None and state.get('request_hold') is False
                and type(exc) is OwnerRefusal and str(exc) == 'settlement_lease_deadline'):
            state.clear()
            state.update(prior)
            record_failure(h, state, 'settlement_recheck_failure', exc, 'SETTLING', 'settlement')
            raise
        # Physical failure is not evidence of an admitted/unknown request.
        # Preserve historical holds and every actual proxy ambiguity above.
        state.update(status='HELD', settlement=None)
        record_failure(h, state, 'settlement_failure', exc, 'SETTLING', 'settlement')
        raise
    state['status'] = 'SETTLED'
    write(h, 'state.json', state)
    return state


def recovery_names(boot):
    require(isinstance(boot, str) and re.fullmatch(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', boot),
        'new_boot_recovery_invalid')
    return ('new-boot-archive-' + boot + '.json', 'new-boot-consumed-' + boot + '.json')


def recovery_receipt_name(boot):
    recovery_names(boot)
    return 'new-boot-recovery-' + boot + '.json'


def source_only_amendment(old, new):
    """The reviewed owner source pin is the ONLY permitted manifest amendment."""
    path = str(BASE / 'source/owner.py')
    a, b = json.loads(json.dumps(old)), json.loads(json.dumps(new))
    prior, current = a['source_sha256'].pop(path), b['source_sha256'].pop(path)
    require(a == b and HEX.fullmatch(prior) and HEX.fullmatch(current) and prior != current
            and hashlib.sha256(protected(BASE / 'source/owner.py')).hexdigest() == current,
            'source_only_amendment_required')


def old_boot_absence(old, state, boot, *, successor=None):
    """Physical absence only; never turns an uncertain request into success."""
    recovery_names(boot)
    recovery_names(state['boot_id'])
    require(state['boot_id'] != boot and BOOT.read_text().strip() == boot
            and state.get('schema_version') == 2 and state.get('status') == 'HELD'
            and state.get('request_hold') is True and state.get('manifest_sha256') == digest(old),
            'new_boot_recovery_invalid')
    for field in ('native', 'supervisor', 'proxy'):
        value = state.get(field)
        require(isinstance(value, dict) and type(value.get('pid')) is int and value['pid'] > 0
                and not Path('/proc', str(value['pid'])).exists(), 'new_boot_owner_present')
    unit = dict(x.split('=', 1) for x in run(['systemctl', 'show', UNIT, '-p',
                'MainPID,ActiveState,SubState,InvocationID,Job'], 2).splitlines())
    if successor is None:
        require(unit['MainPID'] == '0' and unit['ActiveState'] in ('inactive', 'failed')
                and unit.get('Job') in ('', '0'), 'new_boot_owner_present')
    else:
        require(unit['MainPID'] == str(os.getpid()) == str(successor['pid'])
                and unit['InvocationID'] == successor['invocation_id']
                and unit['ActiveState'] in ('activating', 'active'), 'new_boot_owner_present')
    c = exact_container(inspect(state['native']['container_id']), old, state)
    require(c['State']['Running'] is False and c['State']['Pid'] == 0
            and c['State']['Status'] == 'exited', 'new_boot_owner_present')
    cg = Path(state['native_cgroup'])
    require(str(cg) == '/sys/fs/cgroup/' + MEMORY_SLICE + '/docker-' + c['Id'] + '.scope'
            and (not cg.exists() or not (cg / 'cgroup.procs').read_text().strip()),
            'new_boot_owner_present')
    require(not run(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid',
                     '--format=csv,noheader,nounits'], 2).strip(), 'new_boot_owner_present')
    # MiMo proxy binds private IPv4:30012; native binds loopback:30012.
    # The unrelated legacy GLM private socket on :30010 is not MiMo ownership.
    require(not run(['ss', '-H', '-lnt', 'sport = :30012'], 2).strip(), 'new_boot_owner_present')
    require(BOOT.read_text().strip() == boot, 'boot_changed')
    return {'old_boot_id': state['boot_id'], 'current_boot_id': boot,
            'container_id': c['Id'], 'native_pid_absent': True, 'cgroup_empty': True,
            'gpu_compute_empty': True, 'owner_absent': True,
            'physical_release': 'REBOOT', 'prior_request_outcome': 'FAILED_OR_UNKNOWN'}


def exclusive_recovery_write(h, guard, name, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    with h.AnchoredRoot(str(BASE), guard) as root:
        with root.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400) as stream:
            stream.write(raw)
            stream.fsync()
        os.fsync(root.fileno())
        root.check()
    require(protected(BASE / name) == raw, 'new_boot_archive_changed')


def reconcile_new_boot(expected_state_sha256, expected_boot_id, expected_manifest_sha256):
    """Explicit source-bound action; archives history, never edits the old owner."""
    require(all(isinstance(x, str) and HEX.fullmatch(x) for x in
                (expected_state_sha256, expected_manifest_sha256)), 'new_boot_recovery_invalid')
    recovery_names(expected_boot_id)
    h = setup()
    m = read(BASE / 'manifest.json')
    require(digest(m) == expected_manifest_sha256, 'new_boot_recovery_invalid')
    source_preflight(h, m)
    with h.acquire_lease(blocking=False) as lease, h.MountedStorageGuard(h.s) as guard:
        storage_paths(h, guard)
        h.s.root_payload_guard()
        lease.validate()
        names = ['state.json', 'proxy-state.json', 'guard.json', 'selection.json',
                 'new-boot-prior-manifest.json', 'new-boot-prior-owner.py']
        def input_name(name):
            if name.startswith('new-boot-prior-'):
                stem, suffix = name.rsplit('.', 1)
                return stem + '-' + expected_boot_id + '.' + suffix
            return name
        files = {name: protected(BASE / input_name(name)).decode() for name in names}
        require(hashlib.sha256(files['state.json'].encode()).hexdigest() == expected_state_sha256
                and digest(read(BASE / 'manifest.json')) == digest(m), 'new_boot_recovery_invalid')
        state = json.loads(files['state.json'])
        old = json.loads(files['new-boot-prior-manifest.json'])
        proxy, prior_guard = json.loads(files['proxy-state.json']), json.loads(files['guard.json'])
        require(all(proxy.get(k) == state.get(k) for k in ('boot_id', 'launch_id', 'native'))
                and prior_guard.get('boot_id') == state['boot_id']
                and prior_guard.get('manifest_sha256') == digest(old), 'new_boot_recovery_invalid')
        source_only_amendment(old, m)
        require(hashlib.sha256(files['new-boot-prior-owner.py'].encode()).hexdigest()
                == old['source_sha256'][str(BASE / 'source/owner.py')], 'new_boot_archive_changed')
        selected = require_selected(old, state['selection'])
        physical = old_boot_absence(old, state, expected_boot_id)
        archive_name, consumed_name = recovery_names(expected_boot_id)
        receipt_name = recovery_receipt_name(expected_boot_id)
        require(not (BASE / consumed_name).exists() and not (BASE / receipt_name).exists(),
                'new_boot_recovery_consumed')
        archive = {'schema_version': 1, 'files': files,
                   'sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()},
                   'physical_absence': physical, 'prior_request_outcome': 'FAILED_OR_UNKNOWN'}
        exclusive_recovery_write(h, guard, archive_name, archive)
        amended = {**selected, 'manifest_sha256': digest(m)}
        receipt = {'schema_version': 1, 'status': 'NEW_BOOT_RECONCILED',
                   'current_boot_id': expected_boot_id, 'prior_state_digest': digest(state),
                   'prior_manifest_sha256': digest(old), 'manifest_sha256': digest(m),
                   'selection': amended, 'archive_name': archive_name,
                   'archive_sha256': hashlib.sha256(protected(BASE / archive_name)).hexdigest(),
                   'physical_absence': physical, 'prior_request_outcome': 'FAILED_OR_UNKNOWN',
                   'preserved_container_name': old['container_name'] + '-prior-' + state['launch_id']}
        exclusive_recovery_write(h, guard, receipt_name, receipt)
        require(read(BASE / 'state.json') == state and selection() == selected
                and BOOT.read_text().strip() == expected_boot_id, 'new_boot_recovery_invalid')
        # Source-only CAS amendment, after durable archive/receipt; no model/generation change.
        write(h, 'selection.json', amended)
        h.s.root_payload_guard()
        lease.validate()
    return receipt


def recovery_for_start(m, selected, previous):
    boot = BOOT.read_text().strip()
    receipt = read(BASE / recovery_receipt_name(boot))
    archive_name, consumed_name = recovery_names(boot)
    require(not (BASE / consumed_name).exists(), 'new_boot_recovery_consumed')
    require(receipt.get('schema_version') == 1 and receipt.get('status') == 'NEW_BOOT_RECONCILED'
            and receipt.get('current_boot_id') == boot and receipt.get('archive_name') == archive_name
            and receipt.get('manifest_sha256') == digest(m) and receipt.get('selection') == selected
            and receipt.get('prior_state_digest') == digest(previous)
            and receipt.get('prior_request_outcome') == 'FAILED_OR_UNKNOWN', 'new_boot_recovery_invalid')
    raw = protected(BASE / archive_name)
    require(hashlib.sha256(raw).hexdigest() == receipt['archive_sha256'], 'new_boot_archive_changed')
    archive = json.loads(raw)
    require(all(hashlib.sha256(v.encode()).hexdigest() == archive['sha256'][k]
                for k, v in archive['files'].items()), 'new_boot_archive_changed')
    old = json.loads(archive['files']['new-boot-prior-manifest.json'])
    require(json.loads(archive['files']['state.json']) == previous
            and digest(old) == receipt['prior_manifest_sha256']
            and receipt['preserved_container_name'] == old['container_name'] + '-prior-' + previous['launch_id'],
            'new_boot_archive_changed')
    source_only_amendment(old, m)
    return receipt, old


def assert_launch_admission(m, selected, previous, recovery=None):
    require(selected['selected_frontier'] == MODEL and selected.get('manifest_sha256') == digest(m), 'not_selected')
    if previous is not None:
        if recovery is not None:
            require(recovery.get('status') == 'NEW_BOOT_RECONCILED'
                    and recovery.get('prior_state_digest') == digest(previous)
                    and recovery.get('manifest_sha256') == digest(m)
                    and recovery.get('selection') == selected, 'new_boot_recovery_invalid')
            return
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
    recovery, prior_manifest = None, m
    if previous is not None and previous.get('status') == 'HELD':
        recovery, prior_manifest = recovery_for_start(m, selected, previous)
    assert_launch_admission(m, selected, previous, recovery)
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
    primary_error = None
    cycle = None
    operation = 'launch'
    def progress(value):
        nonlocal operation
        operation = value
    try:
        with h.acquire_lease(blocking=False) as lease, h.MountedStorageGuard(h.s) as g:
            storage_paths(h, g)
            h.s.root_payload_guard()
            require_selected(m, selected)
            if recovery is not None:
                require(read(BASE / 'state.json') == previous
                        and digest(read(BASE / 'manifest.json')) == digest(m), 'new_boot_recovery_invalid')
                recovery, prior_manifest = recovery_for_start(m, selected, previous)
                old_boot_absence(prior_manifest, previous, boot, successor=supervisor)
                lease.validate()
                state['predecessor_recovery'] = recovery
            # Competing boot intent is gated by GLM's reviewed ExecCondition.
            glm = dict(x.split('=', 1) for x in run(['systemctl', 'show', GLM_UNIT, '-p', 'MainPID,ActiveState'], 2).splitlines())
            require(glm['MainPID'] == '0' and glm['ActiveState'] in ('inactive', 'failed'), 'glm_must_be_settled_before_selection')
            require(not run(['nvidia-smi', '--id=' + GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits'], 2).strip(), 'frontier_compute_present')
            launch_guard_started = time.monotonic()
            with bounded():
                baseline = memory()
                require(m['memory']['limit_bytes'] <= baseline['MemAvailable'] - .15 * baseline['MemTotal'], 'reviewed_memory_exceeds_fresh_reserve')
                limit = temperature_limit(run(['nvidia-smi', '--id=' + GPU, '-q', '-x'], 2))
                sample = sample_guard(m, baseline, limit, proof_boot=boot)
                memory_policy(m)
                latch(h, boot, evidence=sample.get('hardware_validation'),
                      deadline=launch_guard_started + 5, lease=lease)
            found = run(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + m['container_name'] + '$'], 2).strip()
            require(recovery is None or bool(found), 'owned_container_missing_requires_review')
            if found:
                require(previous is not None and previous.get('manifest_sha256') == digest(prior_manifest), 'unrecorded_container_exists')
                c = exact_container(inspect(found), prior_manifest, previous)
                require(not c['State']['Running'] and c['State']['Pid'] == 0, 'no_double_launch')
                if recovery is not None:
                    # All read-only launch checks passed. Persist successor ownership
                    # before consuming its intent or changing the predecessor name.
                    state['baseline'] = baseline
                    write(h, 'state.json', state)
                    admitted = True
                    exclusive_recovery_write(h, g, recovery_names(boot)[1],
                        {'schema_version': 1, 'recovery_sha256': digest(recovery),
                         'successor_launch_id': state['launch_id'], 'supervisor': supervisor})
                    # Keep stopped predecessor and all Docker logs; no history deletion.
                    run(['docker', 'rename', c['Id'], recovery['preserved_container_name']], 5)
                else:
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
        operation = 'key_read'
        key = read_key(h)
        load_end = time.monotonic() + 1800
        while True:
            cycle = time.monotonic()
            with bounded():
                operation = 'selection_read'
                require_selected(m, selected)
                operation = 'boot_read'
                require(BOOT.read_text().strip() == boot, 'boot_changed')
                operation = 'docker_inspect'
                exact_container(inspect(state['native']['container_id']), m, state)
                operation = 'resource_sample'
                sample = sample_guard(m, baseline, limit, state['native'], progress=progress, proof_boot=boot)
                operation = 'hardware_latch'
                hardware = latch(h, boot, evidence=sample.get('hardware_validation'), deadline=cycle + 5)
                if state['status'] == 'LOADING':
                    require(time.monotonic() < load_end, 'native_load_timeout')
                    ready = False
                    try:
                        operation = 'native_readiness'
                        ready = native_ready(m, key, progress=progress)
                    except MandatoryGuardTimeout:
                        raise
                    except (ConnectionError, OSError, http.client.HTTPException):
                        pass  # Loading may not yet bind or answer within the HTTP timeout.
                    if ready is True:
                        state['status'] = 'STARTING_PROXY'
                        # Persist possible admission before creating the child;
                        # an interruption in Popen must not claim no proxy.
                        state['proxy_started'] = True
                        operation = 'state_write'
                        write(h, 'state.json', state)
                        operation = 'proxy_start'
                        proxy = subprocess.Popen(['/usr/bin/python3', '-I', '-B', str(BASE / 'source/private_proxy.py')],
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        proxy_deadline = time.monotonic() + 5
                        state['proxy'] = {'pid': proxy.pid, 'pid_start_ticks': ticks(proxy.pid),
                                          'parent_pid': os.getpid()}
                        operation = 'state_write'
                        write(h, 'state.json', state)
                disposition = None
                if proxy is not None:
                    operation = 'proxy_snapshot'
                    require(proxy.poll() is None, 'proxy_child_died')
                    try:
                        disposition = proxy_snapshot(state, proxy)
                    except FileNotFoundError:
                        require(state['status'] == 'STARTING_PROXY' and time.monotonic() < proxy_deadline, 'proxy_start_failed')
                    if disposition is not None:
                        state['proxy'] = {k: disposition[k] for k in ('pid', 'pid_start_ticks', 'parent_pid')}
                        if state['status'] != 'RUNNING':
                            state['status'] = 'RUNNING'
                            operation = 'state_write'
                            write(h, 'state.json', state)
                guard = {'schema_version': 2, 'status': 'ok', 'boot_id': boot, 'manifest_sha256': digest(m),
                         'selection': selected, 'supervisor': supervisor, 'native': state['native'],
                         'proxy': state.get('proxy'), 'proxy_disposition': disposition,
                         'observed_monotonic_s': time.monotonic(),
                         'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         'hardware_latched': hardware['hardware_latched'], 'hardware_proof': hardware, 'sample': sample}
                operation = 'guard_write'
                write(h, 'guard.json', guard)
            operation = 'cycle_sleep'
            time.sleep(max(0, 5 - (time.monotonic() - cycle)))
    except BaseException as exc:
        primary_error = exc
        if admitted:
            record_failure(h, state, 'primary_failure', exc, state['status'], operation,
                           None if cycle is None else max(0, time.monotonic() - cycle))
        raise
    finally:
        if admitted:
            try:
                settle_state(h, m, state, proxy)
            except BaseException as exc:
                record_failure(h, state, 'settlement_failure', exc, 'SETTLING', 'settlement')
                if primary_error is None:
                    raise


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
    p.add_argument('action', choices=['supervise', 'settle', 'check-selected', 'rollback-glm', 'reconcile-new-boot'])
    p.add_argument('--service', choices=[MODEL, GLM])
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--expected-state-sha256')
    p.add_argument('--expected-boot-id')
    p.add_argument('--expected-manifest-sha256')
    args = p.parse_args()
    if args.action == 'reconcile-new-boot':
        require(not args.dry_run, 'new_boot_recovery_invalid')
        result = reconcile_new_boot(args.expected_state_sha256, args.expected_boot_id, args.expected_manifest_sha256)
        print(json.dumps({'status': result['status'], 'archive_sha256': result['archive_sha256']}))
        return 0
    if args.action == 'check-selected':
        require(args.service is not None, 'service_required')
        return 0 if selection()['selected_frontier'] == args.service else 1
    if args.action == 'supervise':
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(OwnerRefusal('owner_interrupted')))
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
        print(json.dumps({'status': 'REFUSED', **failure(exc, 'CLI')}))
        raise SystemExit(255)
