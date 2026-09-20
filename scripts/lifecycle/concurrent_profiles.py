"""Closed G1/Q1 production declarations; never manufacture live acceptance.

Manager owns storage guards, the single lease, identities and all Docker calls.
These two candidate declarations are UNVALIDATED until root publishes a protected
receipt at ACCEPTANCE_SUFFIX and binds its canonical SHA256 in the instance.
Changing any capacity, resource, default, source or runtime pin is source review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time

from .runtime_io import LifecycleError

ROOT = Path(__file__).resolve().parents[2]
GLM_PROFILE = 'glm-5.3-ud-q4-k-xl-g1-480000'
QWEN_PROFILE = 'qwen38-27b-q1-700160-yarn4-bf16kv'
SLOTS = {'glm': GLM_PROFILE, 'qwen': QWEN_PROFILE}
GPU_UUIDS = ('GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237',
            'GPU-69acfa26-8b60-61b5-702d-aee252c163cc')
ACCEPTANCE_SUFFIX = 'services/llm-manager/evidence/concurrent-g1q1.accepted.json'
HOST_HEADROOM_POLICY_15 = {
    'version': 'sampled-required-working-set-15pct-v1',
    'numerator': 23, 'denominator': 20,
    'basis': 'sampled_required_working_set_estimate_bytes',
}
PINS = {
    'configs/deployments/glm-5.3-ud-q4-k-xl-g1-480000.json': '5c3864ad2f32c0eda4ca642daba66509af2b4cdfd7b97ac822846dffaf0920d1',
    'configs/deployments/qwen38-27b-q1-700160-yarn4-bf16kv.json': '7650e6ba3cc089ce3955c465a76bd0d97b832c5e1ef1d1ee37dfc56f13a1d401',
    'configs/models/glm-5.3-ud-q4-k-xl.json': '857924551fa83c546bb99f7b524b35c8d79d0cb9ba0a666e0c139bbace0e7e0d',
    'configs/models/qwen38-27b-fp8.json': 'fb62b2689a4c57aa1265b1262830c8d0e3983061c9674640ec9704ce603a44be',
    'configs/runtimes/llama-cpp-v0.4.1-d3br.json': 'd073105a70540df73cef325df7fdcfa32651f5a6aa8387b584708fb51b802d50',
    'configs/runtimes/sglang-qwen38-0.5.19.json': '17bb735a7e13affc11d90b1f7174243c81a5f848d87c8780f1f8d0d0cf67eb11',
    'scripts/runtime/sglang38_file_auth.py': 'e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4',
    'scripts/runtime/sglang38_pair_file_auth.py': '0f0f774ac39ef81b89b85f86bd9a898a0ba7099804763e396aa33a9c30a1c9b5',
}


def require(condition, code):
    if not condition:
        raise LifecycleError(code)


def safe(function):
    from functools import wraps
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except LifecycleError:
            raise
        except Exception:
            raise LifecycleError('concurrent_profile_contract_invalid') from None
    return wrapped


def same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def slot_for_deployment(identifier):
    """Fixed model slot for both candidate and preserved singleton alternatives."""
    if not isinstance(identifier, str):
        return None
    if identifier in {GLM_PROFILE, 'glm-5.3-ud-q4-k-xl-8k', 'glm-5.3-ud-q4-k-xl-32k',
                      'glm-5.3-ud-q4-k-xl-n76-32k', 'glm-5.3-ud-q4-k-xl-n76-native1m'}:
        return 'glm'
    if identifier in {QWEN_PROFILE, 'qwen38-27b-128k', 'qwen38-27b-256k',
                      'qwen38-27b-1000000-yarn4-tp2-bf16kv'}:
        return 'qwen'
    return None


def is_pair(d):
    return isinstance(d, dict) and d.get('id') in SLOTS.values()


def _pinned(relative):
    raw = (ROOT / relative).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PINS[relative], 'concurrent_source_pin_mismatch')
    return raw


@safe
def declared_profile(identifier):
    require(identifier in SLOTS.values(), 'concurrent_profile_unreviewed')
    d = json.loads(_pinned('configs/deployments/' + identifier + '.json'))
    d['_model'] = json.loads(_pinned('configs/models/' + d['model'] + '.json'))
    d['_runtime'] = json.loads(_pinned('configs/runtimes/' + d['runtime'] + '.json'))
    for name in PINS:
        _pinned(name)
    return d


@safe
def validate(d):
    from . import qwen38
    expected, refs = qwen38._bound_expected(declared_profile(d['id']), qwen38._binding(d))
    require(same({key: value for key, value in d.items() if key != '_storage_binding'}, expected),
            'concurrent_profile_contract_mismatch')
    binding = d['_storage_binding']
    binding.verify(roles=('data', 'models'))
    for role, path in refs:
        binding.validate_path(role, path)


def resource_args(d):
    validate(d)
    resources = d['concurrent_pair']
    return ['--cpuset-cpus', resources['guest_cpuset'], '--memory', str(resources['memory_bytes']),
            '--memory-swap', str(resources['memory_swap_bytes'])]


def launch_environment(d):
    validate(d)
    return dict(d['launch_environment'])


def glm_command(d, e):
    """Full native argv, including fixed measured benchmark allocation settings."""
    validate(d)
    require(d['id'] == GLM_PROFILE and e.get('image_id') == d['_runtime']['validation']['image_id']
            and e.get('load_mode') == 'none', 'concurrent_glm_runtime_mismatch')
    launch = d['launch']
    return ['--model', '/models/' + d['_model']['load_entry'], '--host', d['container_host'],
            '--port', str(d['container_port']), '--alias', d['endpoint']['served_model'],
            '--api-key-file', d['auth']['container_key_file'], '--ctx-size', str(launch['context_size']),
            '--parallel', '1', '--n-cpu-moe', '76', '--n-gpu-layers', '999',
            '--split-mode', 'none', '--tensor-split', '1', '--main-gpu', '0', '--device', 'CUDA0',
            '--load-mode', 'none', '--cache-type-k', 'f16', '--cache-type-v', 'f16', '--fit', 'off',
            '--batch-size', '2048', '--ubatch-size', '512', '--threads', '96', '--threads-batch', '96',
            '--jinja', '--no-webui', '--no-cache-prompt', '--chat-template-kwargs',
            json.dumps(launch['chat_template_kwargs'], sort_keys=True, separators=(',', ':'))]


@safe
def validate_pair(d, peer):
    """No unknown peers, alternatives or second copy can share pair admission."""
    validate(d)
    validate(peer)
    require({d['id'], peer['id']} == set(SLOTS.values()), 'concurrent_peer_conflict')
    require(d['endpoint']['port'] != peer['endpoint']['port']
            and d['endpoint']['served_model'] != peer['endpoint']['served_model']
            and not set(d['launch']['gpus']) & set(peer['launch']['gpus']), 'concurrent_peer_conflict')


@safe
def validate_gpu_inventory(rows):
    """Current host nvidia-smi index,uuid output; no saved intent substitutes."""
    if isinstance(rows, str):
        rows = [tuple(part.strip() for part in line.split(',')) for line in rows.splitlines() if line.strip()]
    require(isinstance(rows, (list, tuple)) and len(rows) == 2
            and all(isinstance(row, (list, tuple)) and len(row) == 2 for row in rows),
            'concurrent_gpu_inventory_mismatch')
    require([(str(index), uuid) for index, uuid in rows] == list(zip(('0', '1'), GPU_UUIDS)),
            'concurrent_gpu_inventory_mismatch')


@safe
def validate_reuse(c, d):
    """Add exact pair resource checks to Manager's full identity/network contract."""
    validate(d)
    host, config, resources = c.get('HostConfig', {}), c.get('Config', {}), d['concurrent_pair']
    requests = host.get('DeviceRequests')
    require(isinstance(requests, list) and len(requests) == 1 and same(requests[0].get('DeviceIDs'), d['launch']['gpus'])
            and requests[0].get('Driver', '') in ('', 'nvidia') and same(requests[0].get('Count'), 0)
            and requests[0].get('Capabilities') == [['gpu']] and not requests[0].get('Options')
            and not host.get('Devices') and not host.get('DeviceCgroupRules'), 'concurrent_gpu_reuse_mismatch')
    require(host.get('CpusetCpus') == resources['guest_cpuset']
            and same(host.get('Memory'), resources['memory_bytes'])
            and same(host.get('MemorySwap'), resources['memory_swap_bytes'])
            and all(same(host.get(name, 0), 0) for name in
                    ('NanoCpus', 'CpuQuota', 'CpuPeriod', 'CpuShares', 'MemoryReservation'))
            and host.get('CpusetMems', '') == '' and host.get('OomKillDisable', False) in (None, False)
            and host.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0},
            'concurrent_resource_reuse_mismatch')
    entries = config.get('Env', [])
    require(isinstance(entries, list) and all(isinstance(item, str) and '=' in item for item in entries),
            'concurrent_cuda_remapping_mismatch')
    env = dict(item.split('=', 1) for item in entries)
    require(len(env) == len(entries) and env.get('CUDA_VISIBLE_DEVICES') == d['launch']['gpus'][0]
            and ('NVIDIA_VISIBLE_DEVICES' not in env or env['NVIDIA_VISIBLE_DEVICES'] in ('all', d['launch']['gpus'][0])),
            'concurrent_cuda_remapping_mismatch')


def source_identity():
    """Current critical shipped bytes that a reviewed acceptance must bind."""
    files = set(PINS) | {'scripts/lifecycle/concurrent_profiles.py', 'scripts/lifecycle/qwen38.py',
            'scripts/lifecycle/manager.py', 'scripts/lifecycle/boot_unit.py', 'scripts/lifecycle/slot_state.py',
            'scripts/lifecycle/runtime_io.py',
            'scripts/control/core.py', 'scripts/control/adapter.py', 'scripts/control/catalog.py',
            'scripts/control/journal.py', 'scripts/control/protocol.py', 'scripts/control/discovery.py',
            'scripts/control/installation.py', 'scripts/control/source-closure.json'}
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(files)}


def receipt_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@safe
def check_acceptance(d, instance):
    """Read, never create, root's protected reviewed capacity/allocation receipt.

    A receipt is operator evidence, not a synthetic test result. The instance
    supplies {path, sha256, reviewed_source_commit}; SHA256 is canonical JSON.
    Both slots, source hashes and resource margins are required for either start.
    Largest occupied context is independent of accepted configured allocation.
    """
    validate(d)
    binding = d['_storage_binding']
    path = binding.path('data', ACCEPTANCE_SUFFIX)
    reference = instance.get('concurrent_pair_acceptance', {})
    require(isinstance(reference, dict) and set(reference) == {'path', 'sha256', 'reviewed_source_commit'}
            and reference.get('path') == path and re.fullmatch(r'[0-9a-f]{64}', str(reference.get('sha256', '')))
            and re.fullmatch(r'[0-9a-f]{40}', str(reference.get('reviewed_source_commit', ''))),
            'concurrent_reviewed_acceptance_required')
    receipt = binding.read_json('data', path, maximum=1024 * 1024)
    require(receipt_sha256(receipt) == reference['sha256'], 'concurrent_acceptance_digest_mismatch')
    require(receipt.get('schema_version') == 1 and type(receipt.get('schema_version')) is int
            and receipt.get('kind') == 'root-reviewed-concurrent-g1q1'
            and receipt.get('status') == 'ACCEPTED_FOR_ACTIVATION'
            and isinstance(instance.get('id'), str) and bool(instance['id'])
            and receipt.get('instance_id') == instance['id']
            and receipt.get('storage_identity') == binding.identity
            and receipt.get('reviewed_source_commit') == reference['reviewed_source_commit']
            and same(receipt.get('source_sha256'), source_identity())
            and receipt.get('concurrency_performance_review') == 'ACCEPTED'
            and isinstance(receipt.get('evidence'), list) and receipt['evidence']
            and all(isinstance(item, str) and item.strip() for item in receipt['evidence']),
            'concurrent_acceptance_identity_mismatch')
    validate_gpu_inventory(receipt.get('gpu_inventory'))
    slots = receipt.get('slots')
    require(isinstance(slots, dict) and set(slots) == set(SLOTS), 'concurrent_acceptance_slots_mismatch')
    # An explicit root-reviewed policy selects the new estimate margin. Absent
    # metadata retains the legacy 25% field semantics without reinterpretation.
    estimate_policy = 'host_headroom_policy' in receipt
    if estimate_policy:
        require(same(receipt['host_headroom_policy'], HOST_HEADROOM_POLICY_15),
                'concurrent_host_headroom_policy_unaccepted')
    total_caps = 0
    for slot, identifier in SLOTS.items():
        expected = declared_profile(identifier)
        proof, resource = slots[slot], expected['concurrent_pair']
        capacity = expected['launch']['context_size']
        require(isinstance(proof, dict) and proof.get('deployment') == identifier
                and same(proof.get('configured_context'), capacity)
                and proof.get('profile_sha256') == PINS['configs/deployments/' + identifier + '.json']
                and proof.get('runtime_image_id') == (expected['_runtime']['validation']['image_id'] if slot == 'glm'
                    else expected['_runtime']['image_id'])
                and proof.get('model_revision') == expected['_model']['revision']
                and proof.get('visible_cuda_devices') == {'CUDA0': expected['launch']['gpus'][0]}
                and same(proof.get('guest_cpu_count'), resource['guest_cpu_count'])
                and proof.get('guest_cpuset') == resource['guest_cpuset']
                and same(proof.get('memory_bytes'), resource['memory_bytes'])
                and same(proof.get('memory_swap_bytes'), resource['memory_swap_bytes'])
                and proof.get('allocation') == 'PASS' and proof.get('short_inference') == 'PASS'
                and proof.get('correctness') == 'PASS'
                and type(proof.get('largest_occupied_context')) is int and 0 < proof['largest_occupied_context'] <= capacity,
                'concurrent_capacity_evidence_mismatch')
        peak, free, total = (proof.get(key) for key in ('host_peak_bytes', 'minimum_free_gpu_bytes', 'gpu_total_bytes'))
        if estimate_policy:
            estimate = proof.get(HOST_HEADROOM_POLICY_15['basis'])
            require(type(estimate) is int and estimate > 0
                    and estimate * 23 <= resource['memory_bytes'] * 20,
                    'concurrent_resource_margin_unaccepted')
            # Raw cache/current/peak evidence remains separate. The hard cap
            # still applies to raw peak; it is not the working-set estimate.
            host_margin = type(peak) is int and 0 < peak <= resource['memory_bytes']
        else:
            host_margin = type(peak) is int and peak * 125 <= resource['memory_bytes'] * 100
        require(all(type(value) is int and value > 0 for value in (peak, free, total))
                and host_margin and free <= total
                and free >= resource['minimum_free_gpu_bytes']
                and (slot != 'qwen' or free * 10 >= total), 'concurrent_resource_margin_unaccepted')
        if slot == 'qwen':
            from . import qwen38
            require(proof.get('pair_launcher_sha256') == PINS['scripts/runtime/sglang38_pair_file_auth.py']
                    and proof.get('native_auth_checks') == {name: 'PASS' for name in qwen38.AUTH_CHECKS},
                    'concurrent_qwen_actual_auth_evidence_required')
        total_caps += resource['memory_bytes']
    require(type(receipt.get('host_usable_bytes')) is int and receipt['host_usable_bytes'] >= total_caps,
            'concurrent_aggregate_host_margin_unaccepted')
    binding.verify(roles=('data', 'models'))
    return receipt


def _host_available(text):
    require(isinstance(text, str) and len(text) <= 65536, 'concurrent_current_host_memory_unavailable')
    values = {}
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] in ('MemAvailable:', 'MemTotal:'):
            require(len(fields) == 3 and fields[2] == 'kB' and fields[1].isdigit()
                    and fields[0] not in values, 'concurrent_current_host_memory_unavailable')
            values[fields[0]] = int(fields[1]) * 1024
    require(set(values) == {'MemAvailable:', 'MemTotal:'}
            and 0 < values['MemAvailable:'] <= values['MemTotal:'], 'concurrent_current_host_memory_unavailable')
    return values['MemAvailable:']


def _resident_nonreclaimable(slot, container, instance, read):
    """Credit disjoint resident anon and no-swap shmem, never total file cache.

    Manager supplies an already-trusted running identity and rechecks it around
    this sample. PID/cgroup membership is independently tied to its exact ID.
    Cgroup shmem is included in file, not anon. With zero swap it is already
    resident nonreclaimable RAM; credit it once, without adding file or THP
    subsets. MemAvailable can already include other reclaimable file pages,
    so crediting RSS, memory.current or the full file counter is unsafe.
    """
    require(isinstance(container, dict), 'concurrent_resident_identity_invalid')
    cid, state = container.get('Id'), container.get('State', {})
    labels = container.get('Config', {}).get('Labels', {})
    pid = state.get('Pid')
    require(isinstance(cid, str) and re.fullmatch(r'[0-9a-f]{64}', cid)
            and state.get('Running') is True and type(pid) is int and pid > 0
            and labels.get('io.llmctl.owner') == 'mixed-memory-llm-api-server'
            and labels.get('io.llmctl.instance') == instance['id']
            and labels.get('io.llmctl.deployment') == SLOTS[slot], 'concurrent_resident_identity_invalid')
    membership = read(['/usr/bin/cat', f'/proc/{pid}/cgroup'])
    lines = membership.splitlines()
    require(len(lines) == 1 and lines[0] in ('0::/system.slice/docker-' + cid + '.scope',
            '0::/docker/' + cid), 'concurrent_resident_cgroup_unavailable')
    root = '/sys/fs/cgroup' + lines[0][3:]
    members = read(['/usr/bin/cat', root + '/cgroup.procs']).split()
    require(all(member.isdigit() for member in members) and str(pid) in members,
            'concurrent_resident_cgroup_unavailable')
    text = read(['/usr/bin/cat', root + '/memory.stat'])
    require(len(text) <= 65536, 'concurrent_resident_memory_unavailable')
    values = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) == 2 and fields[1].isdigit() and fields[0] not in values,
                'concurrent_resident_memory_unavailable')
        values[fields[0]] = int(fields[1])
    require({'anon', 'file', 'shmem'} <= set(values) and values['shmem'] <= values['file'],
            'concurrent_resident_memory_unavailable')
    require(read(['/usr/bin/cat', root + '/memory.swap.current']).strip() == '0',
            'concurrent_resident_swap_detected')
    require(read(['/usr/bin/cat', f'/proc/{pid}/cgroup']) == membership,
            'concurrent_resident_cgroup_changed')
    return values['anon'] + values['shmem']


@safe
def preflight_current(d, instance, run_fn, *, residents=None):
    """Bounded current admission after any predecessor stop, before start/create.

    ``residents`` is exactly the caller's trusted RUNNING glm/qwen inspect map.
    Saved desired/observed fields must never populate it. We reserve each target
    or resident peer's full reviewed cap, less current anon plus no-swap shmem,
    and retain the existing 16-GiB host headroom. Thus resident allocations are
    not counted twice, reclaimable cache is not double-credited, and remaining
    room up to each cap is retained even for an idle peer. This is a current
    bounded sample, not an allocator reservation or benchmark recertification.
    """
    receipt = check_acceptance(d, instance)
    residents = {} if residents is None else residents
    require(type(residents) is dict and set(residents) <= set(SLOTS), 'concurrent_resident_identity_invalid')
    target = slot_for_deployment(d['id'])
    deadline = time.monotonic() + 10

    def read(argv):
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'concurrent_memory_admission_timeout')
        result = run_fn(argv, timeout=min(5, remaining))
        require(time.monotonic() < deadline and isinstance(result, str), 'concurrent_memory_admission_timeout')
        return result

    before = _host_available(read(['/usr/bin/cat', '/proc/meminfo']))
    credit = {slot: _resident_nonreclaimable(slot, container, instance, read)
              for slot, container in residents.items()}
    host_available = min(before, _host_available(read(['/usr/bin/cat', '/proc/meminfo'])))
    required = 16 * 1024**3
    for slot in set(residents) | {target}:
        required += max(0, receipt['slots'][slot]['memory_bytes'] - credit.get(slot, 0))
    require(host_available >= required, 'concurrent_current_host_memory_insufficient')
    text = read(['nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.free', '--format=csv,noheader,nounits'])
    require(len(text) <= 4096, 'concurrent_current_gpu_memory_unavailable')
    rows = [tuple(value.strip() for value in line.split(',')) for line in text.splitlines() if line.strip()]
    require(len(rows) == 2 and all(len(row) == 4 and row[2].isdigit() and row[3].isdigit() for row in rows),
            'concurrent_current_gpu_memory_unavailable')
    validate_gpu_inventory([(row[0], row[1]) for row in rows])
    gpu_required = {}
    for slot in set(residents) | {target}:
        proof = receipt['slots'][slot]
        index = 0 if slot == 'glm' else 1
        total, free = (int(value) * 1024**2 for value in rows[index][2:])
        require(total == proof['gpu_total_bytes'] and 0 <= free <= total,
                'concurrent_current_gpu_memory_unavailable')
        reserve = max(16 * 1024**3, (total + 9) // 10 if slot == 'qwen' else 0)
        # Accepted measured occupied GPU bytes include model, allocated cache
        # and workspace. A resident target has already paid that allocation.
        needed = reserve + (0 if slot in residents else total - proof['minimum_free_gpu_bytes'])
        require(free >= needed, 'concurrent_current_gpu_memory_insufficient')
        gpu_required[slot] = needed
    return {'host_available_bytes': host_available, 'required_host_available_bytes': required,
            'resident_slots': sorted(residents), 'gpu_required_free_bytes': gpu_required}


@safe
def native_capacity(d, *, timeout=3):
    """Actual resolved native capacity, independently of argv and saved receipt.

    Caller must bind this response to the same trusted container/start identity
    before and after the read, and retain ordinary auth/alias/health probing.
    Native Qwen pool fields are read only from runtime top-level/internal state,
    never ``server_args``. The known scheduler reserve is one request token plus
    five input tokens, so native max_req_input_len must be configured minus six.
    """
    validate(d)
    from .runtime_io import native_capacity_metadata
    info = native_capacity_metadata(f"http://127.0.0.1:{d['endpoint']['port']}/v1",
                                    d['auth']['key_file'], timeout=timeout)
    expected = d['launch']['context_size']
    if d['id'] == GLM_PROFILE:
        actual = info.get('default_generation_settings', {}).get('n_ctx')
        require(same(actual, expected) and same(info.get('total_slots'), 1)
                and info.get('is_sleeping') is False and info.get('model_alias') == d['endpoint']['served_model'],
                'concurrent_native_capacity_mismatch')
        return {'configured_context': actual, 'native_pool_tokens': actual, 'native_request_limit': actual}
    args = info.get('server_args', info)
    require(isinstance(args, dict) and same(args.get('context_length'), expected)
            and same(args.get('tp_size'), 1), 'concurrent_native_capacity_mismatch')
    states = info.get('internal_states', [])
    require(isinstance(states, list) and len(states) <= 1 and all(isinstance(item, dict) for item in states),
            'concurrent_native_capacity_mismatch')

    def actual_value(name, *, optional=False):
        values = [mapping[name] for mapping in [info, *states] if name in mapping]
        if not values and optional:
            return None
        require(values and all(type(value) is int and value > 0 and value == values[0] for value in values),
                'concurrent_native_capacity_unavailable')
        return values[0]

    pool = actual_value('max_total_num_tokens')
    request = actual_value('max_req_len', optional=True)
    input_limit = actual_value('max_req_input_len')
    require(pool == expected and input_limit == expected - 6
            and (request is None or request == expected - 1), 'concurrent_native_capacity_mismatch')
    return {'configured_context': expected, 'native_pool_tokens': pool,
            'native_request_limit': request, 'native_input_limit': input_limit}
