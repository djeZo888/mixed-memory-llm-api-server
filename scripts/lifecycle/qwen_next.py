"""Bounded SGLang adapter contract; lifecycle state/ownership remains in Manager.

The only reviewed SGLang launch path is the separately mounted file-auth launcher.
No acquisition, installation, real credentials, or model execution lives here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from .runtime_io import LifecycleError
from .storage_binding import BindingError

IMAGE = 'sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3'
MANIFEST_SHA256 = '022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e'
MODEL = 'qwen3-coder-next-fp8'
RUNTIME = 'sglang-qwen-next-0.5.14'
LAUNCHER_TARGET = '/opt/llmctl/sglang_file_auth.py'
LAUNCHER_SUFFIX = 'services/llm-manager/adapters/sglang_file_auth.py'
FLAGS = ['--model-path', '--served-model-name', '--host', '--port', '--context-length',
         '--tp-size', '--tokenizer-worker-num', '--tool-call-parser',
         '--mem-fraction-static', '--max-running-requests', '--load-format']
ENVIRONMENT = {
    'DISABLE_OPENAPI_DOC': '1',
    'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HOME': '/cache/huggingface',
    'XDG_CACHE_HOME': '/cache', 'TRITON_CACHE_DIR': '/cache/triton',
    'TORCHINDUCTOR_CACHE_DIR': '/cache/torchinductor',
    'SGLANG_DG_CACHE_DIR': '/cache/deep_gemm', 'SGLANG_CACHE_DIR': '/cache/sglang',
    'FLASHINFER_WORKSPACE_BASE': '/cache/flashinfer', 'CUDA_CACHE_PATH': '/cache/cuda',
    'TORCH_EXTENSIONS_DIR': '/cache/torch_extensions',
}


def require(condition, code):
    if not condition:
        raise LifecycleError(code)


def expected_manifest():
    path = Path(__file__).resolve().parents[2] / 'reports/f1s-contract-evidence/f1a-qwen-manifest.json'
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256, 'f1a_manifest_pin_mismatch')
    return json.loads(raw)


def validate(d):
    rt, model, launch = d['_runtime'], d['_model'], d['launch']
    binding = d['_storage_binding']
    require(d['runtime'] == RUNTIME and d['model'] == MODEL and d['id'] == 'qwen3-coder-next', 'sglang_profile_identity_mismatch')
    require(rt.get('image_id') == IMAGE and rt.get('image_tag') == 'lmsysorg/sglang:v0.5.14-cu130'
            and rt.get('entrypoint') == ['python3'], 'sglang_image_contract_mismatch')
    require(rt.get('required_cli_flags') == FLAGS, 'sglang_flag_contract_mismatch')
    require(rt.get('environment') == ENVIRONMENT, 'unsafe_runtime_environment')
    require(d['endpoint'] == {'host': '127.0.0.1', 'port': 30003, 'api_prefix': '/v1', 'served_model': 'qwen3-coder-next'}
            and d['container_port'] == 30003, 'sglang_endpoint_mismatch')
    require(d['container_name'] == 'llmctl-qwen3-coder-next', 'sglang_container_identity_mismatch')
    expected = expected_manifest()
    require(all(model.get(k) == v for k, v in expected.items()), 'sglang_artifact_profile_mismatch')
    require(model.get('manifest_sha256') == MANIFEST_SHA256
            and model['model_root'] == str(binding.path('models', MODEL)), 'sglang_manifest_identity_mismatch')
    exact = {'context_size': 32768, 'gpus': ['0', '1'], 'tp_size': 2,
             'tokenizer_worker_num': 1, 'tool_call_parser': 'qwen3_coder',
             'max_running_requests': 1, 'mem_fraction_static': 0.75,
             'load_format': 'safetensors', 'warmup_timeout_seconds': 600}
    require(set(launch) == set(exact) | {'timeout_seconds', 'poll_seconds', 'request_timeout_seconds', 'stop_timeout_seconds'}, 'sglang_unknown_launch_option')
    require(all(launch.get(k) == v and type(launch.get(k)) is type(v) for k, v in exact.items()), 'sglang_launch_contract_mismatch')
    require(launch['timeout_seconds'] == 7200, 'sglang_startup_deadline_mismatch')
    by_target = {m['target']: m for m in d['mounts']}
    adapter = by_target.get(LAUNCHER_TARGET, {})
    require(adapter == {'source': str(binding.path('data', LAUNCHER_SUFFIX)), 'target': LAUNCHER_TARGET,
                        'read_only': True, 'required_role': 'data'}, 'sglang_launcher_mount_mismatch')
    require(d['paths']['cache'] == str(binding.path('models', 'runtime-cache/sglang-qwen-next'))
            and d['paths']['logs'] == str(binding.path('data', 'logs/llmctl/qwen3-coder-next'))
            and d['paths']['service'] == str(binding.path('data', 'services/llm-manager/qwen3-coder-next')), 'sglang_paths_mismatch')
    # Do not accept arbitrary argv/config/plugin extensions even if ignored by rendering.
    require(not any(k in d or k in rt for k in ('legacy', 'args', 'command', 'extra_args', 'config', 'plugins', 'tool_server', 'env')),
            'sglang_unsupported_extension')


def launcher_hash():
    return hashlib.sha256(Path(__file__).with_name('sglang_file_auth.py').read_bytes()).hexdigest()


def evidence(d, instance):
    e = instance.get('runtime_evidence', {}).get(d['runtime'], {})
    require(isinstance(e, dict), 'sglang_image_evidence_required')
    supported = e.get('supported_flags')
    require(isinstance(supported, list) and all(isinstance(flag, str) for flag in supported), 'sglang_flag_evidence_required')
    require(e.get('image_id') == IMAGE, 'sglang_image_evidence_required')
    require(e.get('flags_verified') is True and bool(e.get('evidence'))
            and set(FLAGS).issubset(supported), 'sglang_flag_evidence_required')
    require(e.get('launcher_sha256') == launcher_hash(), 'sglang_launcher_evidence_required')
    require(e.get('auth_gate_passed') is True and bool(e.get('auth_gate_evidence')), 'sglang_pinned_image_auth_gate_required')
    return e


def protected_bytes(path, limit=1024 * 1024):
    """Read nonsecret protected source/evidence, refusing symlink parents and races."""
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p, 'sglang_protected_path_invalid')
    fd = None
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0
                and not meta.st_mode & 0o022 and 0 < meta.st_size <= limit,
                'sglang_protected_file_invalid')
        for parent in p.parents:
            pm = parent.stat()
            require(pm.st_uid == 0 and not pm.st_mode & 0o022,
                    'sglang_protected_parent_invalid')
        raw = os.read(fd, limit + 1)
        require(len(raw) == meta.st_size and len(raw) <= limit, 'sglang_protected_file_changed')
        return raw
    except (OSError, ValueError, TypeError):
        raise LifecycleError('sglang_protected_file_invalid') from None
    finally:
        if fd is not None:
            os.close(fd)


def validate_launcher(d, e):
    source = next(m['source'] for m in d['mounts'] if m['target'] == LAUNCHER_TARGET)
    validate_host_path(d, 'data', source)
    raw = protected_bytes(source)
    require(stat.S_IMODE(Path(source).stat().st_mode) == 0o644, 'sglang_launcher_mode_invalid')
    validate_host_path(d, 'data', source)
    require(hashlib.sha256(raw).hexdigest() == e['launcher_sha256'] == launcher_hash(), 'sglang_installed_launcher_mismatch')


def validate_host_path(d, role, path):
    """Small protected evidence files must remain on their registered filesystem."""
    try:
        d['_storage_binding'].validate_path(role, str(path))
    except BindingError:
        raise LifecycleError('sglang_storage_path_invalid') from None


def check_completion(d, instance):
    item = instance.get('model_integrity', {}).get(d['model'], {})
    require(isinstance(item, dict), 'sglang_acquisition_incomplete')
    require(item.get('verified') is True and item.get('revision') == d['_model']['revision']
            and item.get('manifest_sha256') == MANIFEST_SHA256 and bool(item.get('evidence')),
            'sglang_acquisition_incomplete')
    require(isinstance(item.get('completion_manifest'), str), 'sglang_completion_path_invalid')
    path = Path(item['completion_manifest'])
    completion_root = d['_storage_binding'].path('data', 'services/llm-manager/acquisition')
    require(path.is_absolute() and '..' not in path.parts and path.parent == Path(completion_root),
            'sglang_completion_path_invalid')
    try:
        validate_host_path(d, 'data', path)
        raw = protected_bytes(path)
        validate_host_path(d, 'data', path)
        complete = json.loads(raw)
        require(isinstance(complete, dict), 'sglang_acquisition_incomplete')
        for k, v in {'schema_version': 1, 'complete': True, 'repo_id': d['_model']['repo_id'],
                     'revision': d['_model']['revision'], 'model_root': d['_model']['model_root'],
                     'manifest_sha256': MANIFEST_SHA256, 'artifact_count': 48, 'total_bytes': 80407722953}.items():
            require(complete.get(k) == v and type(complete.get(k)) is type(v), 'sglang_acquisition_incomplete')
        files = complete.get('artifacts', [])
        require(len(files) == 48 and all(a.get('verified') is True for a in files), 'sglang_acquisition_incomplete')
        actual = {(a['path'], a['size_bytes'], a['sha256']) for a in files}
        expected = {(a['path'], a['size_bytes'], a['sha256']) for a in d['_model']['artifacts']}
        require(actual == expected and len(actual) == 48, 'sglang_completion_artifacts_mismatch')
    except (ValueError, KeyError, TypeError, AttributeError):
        raise LifecycleError('sglang_acquisition_incomplete') from None


def command(d):
    launch = d['launch']
    return [LAUNCHER_TARGET, '--key-file', d['auth']['container_key_file'],
            '--warmup-timeout', str(launch['warmup_timeout_seconds']),
            '--model-path', '/models', '--served-model-name', d['endpoint']['served_model'],
            '--host', d['container_host'], '--port', str(d['container_port']),
            '--context-length', str(launch['context_size']), '--tp-size', str(launch['tp_size']),
            '--tokenizer-worker-num', str(launch['tokenizer_worker_num']),
            '--tool-call-parser', launch['tool_call_parser'],
            '--mem-fraction-static', str(launch['mem_fraction_static']),
            '--max-running-requests', str(launch['max_running_requests']), '--load-format', launch['load_format']]


def image_environment(image, d):
    """Exact inherited image environment plus nonsecret reviewed overrides."""
    entries = image.get('Config', {}).get('Env') or []
    require(isinstance(entries, list) and all(isinstance(x, str) and '=' in x for x in entries), 'sglang_image_environment_invalid')
    env = dict(x.split('=', 1) for x in entries)
    env.update(d['_runtime']['environment'])
    return env


def validate_reused(c, d, e, image):
    validate_launcher(d, e)
    config, host = c.get('Config', {}), c.get('HostConfig', {})
    entries = config.get('Env', [])
    require(isinstance(entries, list) and all(isinstance(x, str) and '=' in x for x in entries), 'container_environment_mismatch')
    env = dict(x.split('=', 1) for x in entries)
    require(len(env) == len(entries) and env == image_environment(image, d), 'container_environment_mismatch')
    require(config.get('WorkingDir') == '/service' and config.get('User', '') in ('', '0', 'root'), 'sglang_container_process_mismatch')
    require(host.get('ReadonlyRootfs') is True and host.get('ShmSize') == 8 * 1024**3
            and host.get('Tmpfs') == {'/tmp': 'rw,nosuid,nodev,size=1g'}, 'sglang_container_storage_mismatch')
    require(set(host.get('CapDrop') or []) == {'ALL'} and not host.get('CapAdd')
            and set(host.get('SecurityOpt') or []) == {'no-new-privileges:true'}, 'sglang_container_security_mismatch')
    require(not config.get('Healthcheck') or config['Healthcheck'].get('Test') == ['NONE'], 'sglang_container_healthcheck_mismatch')
    require(not any(host.get(field) for field in ('Devices', 'DeviceCgroupRules', 'VolumesFrom', 'Binds'))
            and host.get('PidMode', '') == '' and host.get('IpcMode', 'private') == 'private'
            and host.get('UTSMode', '') == '', 'sglang_container_namespace_mismatch')
    requests = host.get('DeviceRequests', [])
    require(len(requests) == 1 and requests[0].get('Driver', '') in ('', 'nvidia')
            and requests[0].get('Count', 0) == 0 and requests[0].get('Capabilities') == [['gpu']]
            and not requests[0].get('Options'), 'container_gpu_contract_mismatch')
    require(all(m.get('Type') == 'bind' for m in c.get('Mounts', [])), 'container_mount_contract_mismatch')
