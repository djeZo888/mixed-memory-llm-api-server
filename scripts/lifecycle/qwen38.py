"""Q38 source adapter; Manager owns leases, storage registration and transitions.

Only the two reviewed declarations are accepted. This module never installs,
downloads, executes Docker, reads an inference key or changes active state.
Manager dispatch was composed after the explicit frozen L1B handoff. Installation
and runtime proof remain separate gates. See docs/qwen38-runtime.md.
"""
from __future__ import annotations

import copy
from functools import wraps
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

from .runtime_io import LifecycleError, probe_sglang, validate_container_network
from runtime import qwen38_oci as oci

ROOT = Path(__file__).resolve().parents[2]
MODEL = 'qwen38-27b-fp8'
RUNTIME = 'sglang-qwen38-0.5.19'
BACKEND = 'sglang_qwen38'
REVISION = '017b9c7af6b5689d5dd426a76e0bc077eb5ca20a'
SOURCE_REVISION = '0bcd822377da7b5718e674eaf9c870d349424dd1'
MANIFEST_DIGEST = 'sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262'
IMAGE_REFERENCE = 'lmsysorg/sglang@' + MANIFEST_DIGEST
IMAGE_ID = 'sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813'
VARIANTS = {'qwen38-27b-128k': 131072, 'qwen38-27b-256k': 262144}
LAUNCHER_TARGET = '/opt/llmctl/sglang38_file_auth.py'
LAUNCHER_SUFFIX = 'services/llm-manager/adapters/sglang38_file_auth.py'
COMPLETION_SUFFIX = 'services/llm-manager/acquisition/' + MODEL + '.complete.json'
PROOF_SUFFIX = 'services/llm-manager/evidence/' + RUNTIME + '.auth.json'
# Whole-file pins are intentionally explicit: adding a context/flag/path/profile
# is a source review, never an operator-supplied command or plugin extension.
PROFILE_HASHES = {'reports/q38s-acquisition-manifest.json': '726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2',
 'configs/models/qwen38-27b-fp8.json': 'fb62b2689a4c57aa1265b1262830c8d0e3983061c9674640ec9704ce603a44be',
 'configs/runtimes/sglang-qwen38-0.5.19.json': '17bb735a7e13affc11d90b1f7174243c81a5f848d87c8780f1f8d0d0cf67eb11',
 'configs/deployments/qwen38-27b-128k.json': 'cee5253c28bd8ff36f33630f27642cc9cdd3857eaa108bd177488efd6a0d133f',
 'configs/deployments/qwen38-27b-256k.json': '462ed5792940890eaa410c3c6dd4996c6723157eee5fb7021ee210ed2f78523a',
 'tests/lifecycle/sglang38_fixture/provenance.json': '4f8ac18cab3ea1fb58ec625c7a0cb77f22105bac1761ce196a3eb05f91b3809e'}
Q38R_SHA256 = '3df6f2a0a46a33b2b48f62609235ff209e50403d679bd8ee120b941445a87ed0'
AUTH_CHECKS = (
    'native_routes_and_final_chain', 'native_prepare_and_normalization',
    'health_starting_503_up_200', 'sentinel_absence', 'injection_failure_child_cleanup',
    'spawn_import', 'unsupported_modes', 'raw_resolved_workerargs_sentinel_absence',
    'native_sse_disconnect', 'ordinary_http_auth', 'server_info_sentinel_absence',
    'websocket_denial', 'native_freeze_gc_has_no_key', 'warmup_failure_and_timeout_cleanup',
    'native_false_warmup_not_ready', 'native_parser_template_synthetic',
    'actual_cache_resolvers', 'no_gpu_driver_libraries',
)


def require(condition, code):
    if not condition:
        raise LifecycleError(code)


def safe_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except LifecycleError:
            raise
        except Exception:
            # Do not relay malformed evidence, file contents or native exceptions.
            raise LifecycleError('qwen38_contract_invalid') from None
    return wrapped


def same(actual, expected):
    """Type-sensitive JSON identity (True must not satisfy integer 1)."""
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


def _pinned_json(relative):
    raw = (ROOT / relative).read_bytes()
    require(relative in PROFILE_HASHES and hashlib.sha256(raw).hexdigest() == PROFILE_HASHES[relative],
            'qwen38_source_profile_pin_mismatch')
    return json.loads(raw)


@safe_errors
def expected_manifest():
    raw = (ROOT / 'reports/q38r-source-weight-manifest.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == Q38R_SHA256, 'qwen38_research_manifest_pin_mismatch')
    return _pinned_json('reports/q38s-acquisition-manifest.json')


@safe_errors
def declared_profile(identifier):
    """Return a fresh, unbound declaration for source review/catalog metadata."""
    require(identifier in VARIANTS, 'qwen38_deployment_identity_mismatch')
    d = _pinned_json('configs/deployments/' + identifier + '.json')
    d['_model'] = _pinned_json('configs/models/' + MODEL + '.json')
    d['_runtime'] = _pinned_json('configs/runtimes/' + RUNTIME + '.json')
    expected_manifest()
    return d


def _binding(d):
    binding = d.get('_storage_binding')
    require(binding is not None and all(callable(getattr(binding, name, None))
            for name in ('path', 'verify', 'validate_path', 'read_json')),
            'qwen38_registered_storage_binding_required')
    return binding


def _bound_expected(d, binding):
    """Consume L1's trusted in-process binding; never synthesize a registry."""
    result = copy.deepcopy(d)
    refs = []

    def resolve(ref):
        require(set(ref) == {'role', 'suffix'} and ref['role'] in {'data', 'models'},
                'qwen38_invalid_path_reference')
        path = binding.path(ref['role'], ref['suffix'])
        require(isinstance(path, str) and Path(path).is_absolute(), 'qwen38_invalid_bound_path')
        refs.append((ref['role'], path))
        return path

    result['paths'] = {name: resolve(ref) for name, ref in d['paths'].items()}
    result['auth']['key_file'] = resolve(d['auth']['key_file'])
    result['_model']['model_root'] = resolve(d['_model']['model_root'])
    for mount in result['mounts']:
        mount['source'] = resolve(mount['source'])
    return result, refs


@safe_errors
def validate(d):
    """Validate fixed settings and all L1-bound paths before any backend switch.

    Binding authentication/creation and role filesystem validation belong to L1.
    This function must run inside Manager's existing guarded lease transaction;
    passing an object here does not authorize a lifecycle operation.
    """
    binding = _binding(d)
    expected, refs = _bound_expected(declared_profile(d['id']), binding)
    supplied = {key: value for key, value in d.items() if key != '_storage_binding'}
    require(same(supplied, expected), 'qwen38_profile_contract_mismatch')
    binding.verify(roles=('data', 'models'))
    for role, path in refs:
        binding.validate_path(role, path)


def launcher_hash():
    return hashlib.sha256((ROOT / 'scripts/runtime/sglang38_file_auth.py').read_bytes()).hexdigest()


@safe_errors
def command(d):
    validate(d)
    # Namespace import is safe: launcher main is guarded, imports stdlib only,
    # and neither reads a key nor imports SGLang at module import time.
    from runtime.sglang38_file_auth import backend_argv
    return [LAUNCHER_TARGET, '--key-file', '/run/secrets/llm-api-key',
            '--warmup-timeout', '600', *backend_argv(d['launch']['context_size'])]


def _protected_bytes(path, maximum=1024 * 1024):
    """Read a root-owned reviewed launcher without path or content diagnostics."""
    fd = None
    try:
        path = Path(path)
        require(path.is_absolute() and path.resolve() == path, 'qwen38_protected_path_invalid')
        for parent in path.parents:
            info = parent.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022, 'qwen38_protected_parent_invalid')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and stat.S_IMODE(before.st_mode) == 0o644 and 0 < before.st_size <= maximum,
                'qwen38_protected_file_invalid')
        raw = os.read(fd, maximum + 1)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and signature(before) == signature(os.fstat(fd))
                == signature(path.stat(follow_symlinks=False)), 'qwen38_protected_file_changed')
        return raw
    finally:
        if fd is not None:
            os.close(fd)


@safe_errors
def validate_launcher(d, e):
    validate(d)
    binding = _binding(d)
    source = binding.path('data', LAUNCHER_SUFFIX)
    local = binding.validate_path('data', source)
    raw = _protected_bytes(local)
    require(hashlib.sha256(raw).hexdigest() == e['launcher_sha256'] == launcher_hash(),
            'qwen38_installed_launcher_mismatch')
    binding.verify(roles=('data', 'models'))


@safe_errors
def check_completion(d, instance):
    """Validate the protected acquisition receipt, never download or invent it.

    Manager must additionally stat all immutable artifacts inside its guarded
    transaction. A receipt attests acquired-byte hashing, not live inference.
    """
    validate(d)
    binding = _binding(d)
    expected = expected_manifest()
    item = instance.get('model_integrity', {}).get(MODEL, {})
    path = binding.path('data', COMPLETION_SUFFIX)
    manifest_hash = PROFILE_HASHES['reports/q38s-acquisition-manifest.json']
    require(item.get('verified') is True and item.get('revision') == REVISION
            and item.get('manifest_sha256') == manifest_hash and item.get('completion_manifest') == path
            and isinstance(item.get('evidence'), str) and bool(item['evidence'].strip()),
            'qwen38_acquisition_incomplete')
    complete = binding.read_json('data', path, maximum=1024 * 1024)
    header = {'schema_version': 1, 'complete': True, 'repo_id': expected['repo_id'],
              'revision': REVISION, 'model_root': d['_model']['model_root'],
              'manifest_sha256': manifest_hash, 'artifact_count': 81, 'total_bytes': 30890049597}
    require(set(complete) == set(header) | {'artifacts'}
            and all(same(complete.get(k), v) for k, v in header.items()), 'qwen38_acquisition_incomplete')
    files = complete['artifacts']
    require(isinstance(files, list) and len(files) == 81, 'qwen38_completion_artifacts_mismatch')
    wanted = {a['path']: {'path': a['path'], 'size_bytes': a['size_bytes'],
                        'sha256': a['sha256'], 'verified': True} for a in expected['artifacts']}
    require(len(wanted) == 81 and len({a['path'] for a in files}) == 81
            and all(same(a, wanted.get(a['path'])) for a in files), 'qwen38_completion_artifacts_mismatch')
    binding.verify(roles=('data', 'models'))


@safe_errors
def evidence(d, instance):
    """Require actual-image proof bound to source, OCI identities and launcher.

    Source/mock passes cannot mint this protected runtime receipt. L2 publishes
    it only after worker1 runs the exact shipped actual-image fixture.
    """
    validate(d)
    e = instance.get('runtime_evidence', {}).get(RUNTIME, {})
    identity = {'image_id': IMAGE_ID, 'image_reference': IMAGE_REFERENCE,
                'source_revision': SOURCE_REVISION, 'launcher_sha256': launcher_hash()}
    require(all(e.get(k) == v for k, v in identity.items()), 'qwen38_runtime_identity_evidence_required')
    require(e.get('flags_verified') is True and e.get('auth_gate_passed') is True
            and same(e.get('supported_flags'), d['_runtime']['required_cli_flags'])
            and isinstance(e.get('evidence'), str) and bool(e['evidence'].strip()),
            'qwen38_actual_image_auth_gate_required')
    binding = _binding(d)
    path = binding.path('data', PROOF_SUFFIX)
    require(e.get('auth_gate_evidence') == path, 'qwen38_auth_evidence_path_invalid')
    proof = binding.read_json('data', path, maximum=1024 * 1024)
    _validate_auth_proof(proof, identity)
    require(same(e.get('docker_inspect'), proof['docker_inspect']),
            'qwen38_installer_observed_identity_mismatch')
    binding.verify(roles=('data', 'models'))
    return e


def _validate_auth_proof(proof, identity):
    provenance = _pinned_json('tests/lifecycle/sglang38_fixture/provenance.json')
    require(provenance['launcher_sha256'] == launcher_hash(), 'qwen38_auth_fixture_launcher_changed')
    fixtures = provenance['fixture_sha256']
    require(set(fixtures) == {'run_fixture.py', 'run_pinned_image.py', 'auth_native.py', 'chat_template.jinja', 'cache_probe.py'},
            'qwen38_auth_fixture_invalid')
    for name, digest in fixtures.items():
        require(hashlib.sha256((ROOT / 'tests/lifecycle/sglang38_fixture' / name).read_bytes()).hexdigest() == digest,
                'qwen38_auth_fixture_changed')
    support = provenance['support_sha256']
    require(set(support) == {'scripts/runtime/qwen38_oci.py'}, 'qwen38_support_manifest_invalid')
    for name, digest in support.items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest,
                'qwen38_support_source_changed')
    inspected = oci.validate_evidence(proof.get('docker_inspect'))
    source_hashes = {name: item['sha256'] for name, item in provenance['sources'].items()}
    expected = dict(identity, schema_version=2, kind='q38b_actual_image_auth', status='PASS',
                    fixture_sha256=fixtures, support_sha256=support, source_hashes=source_hashes,
                    checks={name: 'PASS' for name in AUTH_CHECKS}, contexts=[131072, 262144],
                    image_identity_verification='HOST_DOCKER_INSPECT_AND_PINNED_RUN',
                    docker_inspect=inspected,
                    model_execution='NOT_TESTED', native_lifespan='NOT_TESTED',
                    live_inference_and_agent_acceptance='NOT_TESTED')
    require(set(proof) == set(expected) | {'native_results', 'container_lifetimes'}
            and all(same(proof.get(k), v) for k, v in expected.items()),
            'qwen38_actual_image_auth_proof_mismatch')
    results = proof['native_results']
    cache_spec = importlib.util.spec_from_file_location('q38b_receipt_cache',
        ROOT / 'tests/lifecycle/sglang38_fixture/cache_probe.py')
    cache = importlib.util.module_from_spec(cache_spec)
    cache_spec.loader.exec_module(cache)
    require(isinstance(results, list) and len(results) == 2, 'qwen38_actual_image_context_proof_missing')
    for context, result in zip((131072, 262144), results):
        native = {
            'status': 'PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE',
            'image_identity_verification': 'HOST_DOCKER_INSPECT_REQUIRED',
            'configured_context': context, 'image_id_pin': IMAGE_ID,
            'image_reference': IMAGE_REFERENCE, 'source_revision': SOURCE_REVISION,
            'launcher_sha256': launcher_hash(), 'fixture_sha256': fixtures, 'source_hashes': source_hashes,
            'support_sha256': support,
            'model_loading': 'STUBBED_NOT_TESTED', 'gpu_execution': 'NOT_TESTED',
            'native_lifespan_model_serving_initialization': 'NOT_TESTED',
            'live_inference_and_agent_acceptance': 'NOT_TESTED',
            **{name: 'PASS' for name in AUTH_CHECKS},
        }
        require(isinstance(result, dict) and all(same(result.get(k), v) for k, v in native.items()),
                'qwen38_actual_image_context_proof_mismatch')
        cache.validate_result(result.get('cache_probe'))
    lifetimes = proof['container_lifetimes']
    require(isinstance(lifetimes, list) and len(lifetimes) == 2, 'qwen38_container_lifetime_proof_missing')
    ids, names = set(), set()
    for context, lifetime in zip((131072, 262144), lifetimes):
        require(isinstance(lifetime, dict) and set(lifetime) == {
            'container_name', 'container_id', 'outcome', 'cleanup', 'runtime_inspect'},
            'qwen38_container_lifetime_proof_invalid')
        name, identity = lifetime['container_name'], lifetime['container_id']
        require(isinstance(name, str) and re.fullmatch(r'q38b-fixture-[a-f0-9]{32}', name)
                and isinstance(identity, str) and re.fullmatch(r'[a-f0-9]{64}', identity)
                and name not in names and identity not in ids
                and lifetime['outcome'] == 'FIXTURE_EXITED'
                and lifetime['cleanup'] == 'QUIESCENT_REMOVAL_VERIFIED',
                'qwen38_container_cleanup_unverified')
        names.add(name); ids.add(identity)
        require(same(lifetime['runtime_inspect'], {
            'runtime': 'nvidia', 'visible_devices': 'none', 'driver_capabilities': 'compute,utility',
            'device_requests': [], 'host_devices': [], 'network': 'none',
            'root_readonly': True, 'model_and_secret_mounts': 'EMPTY_PRIVATE_TMPFS',
            'entrypoint': ['python3'], 'context': context, 'status': 'PASS_HOST_INSPECT'}),
            'qwen38_fixture_runtime_inspect_mismatch')


@safe_errors
def image_environment(image, d):
    validate(d)
    oci.verify_image(image)
    entries = image.get('Config', {}).get('Env', [])
    require(isinstance(entries, list) and all(isinstance(s, str) and '=' in s for s in entries),
            'qwen38_image_environment_invalid')
    env = dict(s.split('=', 1) for s in entries)
    require(len(env) == len(entries) and same(env, d['_runtime']['image_environment']),
            'qwen38_image_environment_mismatch')
    require(image.get('Config', {}).get('Labels', {}).get('org.opencontainers.image.revision') == SOURCE_REVISION,
            'qwen38_image_source_mismatch')
    env.update(d['_runtime']['environment'])
    return env


@safe_errors
def verify_runtime_image(image, d, e):
    """Bind runtime/auth proof to this host's exact observed OCI domain."""
    image_environment(image, d)
    observed = oci.verify_image(image)
    require(same(e.get('docker_inspect'), observed), 'qwen38_runtime_observed_identity_mismatch')
    return observed['image_id']


@safe_errors
def validate_reused(c, d, e, image):
    """Exact launch identity, including context, GPU, parsers, cache and paths."""
    validate_launcher(d, e)
    config, host = c.get('Config', {}), c.get('HostConfig', {})
    verify_runtime_image(image, d, e)
    oci.validate_container_image(c, e['docker_inspect'])
    require(config.get('Entrypoint') == ['python3'] and config.get('Cmd') == command(d),
            'qwen38_reused_command_mismatch')
    expected_env = image_environment(image, d)
    entries = config.get('Env', [])
    require(isinstance(entries, list) and all(isinstance(s, str) and '=' in s for s in entries),
            'qwen38_reused_environment_mismatch')
    env = dict(s.split('=', 1) for s in entries)
    require(len(env) == len(entries) and same(env, expected_env), 'qwen38_reused_environment_mismatch')
    require(config.get('WorkingDir') == '/service' and config.get('User') == '0',
            'qwen38_reused_process_mismatch')
    require(config.get('Healthcheck') == {'Test': ['NONE']}, 'qwen38_reused_healthcheck_mismatch')
    mounts = c.get('Mounts', [])
    wanted = {(m['source'], m['target'], not m['read_only']) for m in d['mounts']}
    require(isinstance(mounts, list) and len(mounts) == 6
            and all(m.get('Type') == 'bind' and type(m.get('RW')) is bool
                    and m.get('Propagation') in ('rprivate', '') for m in mounts)
            and {(m.get('Source'), m.get('Destination'), m.get('RW')) for m in mounts} == wanted,
            'qwen38_reused_mount_mismatch')
    require(host.get('ReadonlyRootfs') is True and host.get('ShmSize') == 8 * 1024**3
            and host.get('Tmpfs') == {'/tmp': 'rw,nosuid,nodev,size=1g'}, 'qwen38_reused_storage_mismatch')
    require(host.get('CapDrop') == ['ALL'] and not host.get('CapAdd') and not host.get('Privileged')
            and host.get('SecurityOpt') == ['no-new-privileges:true'], 'qwen38_reused_security_mismatch')
    require(host.get('LogConfig') == {'Type': 'json-file', 'Config': {'max-size': '20m', 'max-file': '3'}},
            'qwen38_reused_logging_mismatch')
    requests = host.get('DeviceRequests', [])
    require(isinstance(requests, list) and len(requests) == 1 and requests[0].get('Driver', '') in ('', 'nvidia')
            and type(requests[0].get('Count')) is int and requests[0].get('Count') == 0 and requests[0].get('DeviceIDs') == ['0']
            and requests[0].get('Capabilities') == [['gpu']] and not requests[0].get('Options'),
            'qwen38_reused_gpu_mismatch')
    require(not any(host.get(k) for k in ('Devices', 'DeviceCgroupRules', 'VolumesFrom', 'Binds', 'PidMode', 'UTSMode'))
            and host.get('IpcMode', 'private') == 'private' and host.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0},
            'qwen38_reused_namespace_mismatch')
    validate_container_network(c, 30004, 30004)


def probe(endpoint, expected_model, key_file, require_auth=True, timeout=3):
    """Existing health-Up + exact alias + missing/wrong-key denial observation."""
    require(endpoint == 'http://127.0.0.1:30004/v1' and expected_model == 'qwen3.8-27b',
            'qwen38_probe_identity_mismatch')
    return probe_sglang(endpoint, expected_model, key_file, require_auth=require_auth, timeout=timeout)
