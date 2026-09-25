#!/usr/bin/env python3
"""Read-only UID1000 fixture for the exact H005 image permissions repair.

Run in the actual derivative with python -I -B, --user 1000:1001, no extra
groups, read-only root, no network/model mount/ports/GPU devices, private /tmp,
8 GiB/2 CPU/pids128 bounds and an external timeout. Deliver this file and the
reviewed native_server.py over stdin into private /tmp; no host bind mounts.
NVIDIA_VISIBLE_DEVICES=none may expose driver libraries; it must not expose
devices. CUDA_VISIBLE_DEVICES must be empty. This is not native readiness.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time

PACKAGE = Path('/opt/image-venv/lib/python3.12/site-packages/sglang')
MANIFEST = Path('/opt/llmctl/adaptive-idle/image.json')
VERIFIER = Path('/opt/llmctl/adaptive-idle/verify.py')
OVERLAY_SHA256 = 'dda84e200adcc6a1ee8915e0e993627695477a346c5848fc27f9251c34d04b3b'
VERIFIER_SHA256 = '554c6ffc6c76fef28a3c778cd25ee1160a21a771906f95a7fea3418682ece00d'
NATIVE = 'sglang.multimodal_gen.runtime.'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_metadata(path, *, directory=False):
    """Never open for writing; mode checks also catch read-only mount masking."""
    st = path.lstat()
    require(not stat.S_ISLNK(st.st_mode), 'symlink:' + str(path))
    require(stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode),
            'wrong_file_type:' + str(path))
    require(st.st_uid == 0, 'not_root_owned:' + str(path))
    require(not st.st_mode & 0o022, 'group_or_other_writable:' + str(path))
    wanted = os.R_OK | (os.X_OK if directory else 0)
    require(os.access(path, wanted, effective_ids=True), 'not_accessible:' + str(path))
    require(not os.access(path, os.W_OK, effective_ids=True), 'uid_can_write:' + str(path))
    return {'path': str(path), 'mode': oct(stat.S_IMODE(st.st_mode)),
            'uid': st.st_uid, 'gid': st.st_gid, 'readable': True,
            'traversable': directory, 'writable': False}


def check_devices():
    devices = sorted(str(p) for pattern in ('nvidia*', 'dri/render*')
                     for p in Path('/dev').glob(pattern))
    require(not devices, 'gpu_device_present')
    require(os.environ.get('NVIDIA_VISIBLE_DEVICES') == 'none',
            'nvidia_visible_devices_must_be_none')
    require(os.environ.get('CUDA_VISIBLE_DEVICES') == '',
            'cuda_visible_devices_must_be_empty')
    return devices


def load_native_server(path, expected_sha256):
    require(len(expected_sha256) == 64 and all(c in '0123456789abcdef' for c in expected_sha256),
            'invalid_native_server_expected_sha256')
    require(not path.is_symlink() and sha256(path) == expected_sha256,
            'native_server_source_mismatch')
    spec = importlib.util.spec_from_file_location('_h005_production_native_server', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.ADAPTIVE_OVERLAY_SHA256 == OVERLAY_SHA256,
            'native_server_overlay_pin_mismatch')
    require(module.ADAPTIVE_VERIFIER_SHA256 == VERIFIER_SHA256,
            'native_server_verifier_pin_mismatch')
    result = module.verify_adaptive_overlay()
    require(result == {'target': 'image', 'overlay_sha256': OVERLAY_SHA256,
                       'verified_files': 15}, 'production_verifier_closure_mismatch')
    return result


def check_payload():
    receipt = json.loads(MANIFEST.read_text())
    require(receipt['native_package_root'] == str(PACKAGE), 'native_package_root_mismatch')
    final = dict(receipt['input_raw_sha256'])
    final.update(receipt['output_raw_sha256'])
    checks = dict(receipt['installed_preconditions'])
    for name, digest in final.items():
        require(name.startswith('python/sglang/') and '..' not in Path(name).parts,
                'invalid_payload_path')
        checks[str(PACKAGE / name[len('python/sglang/'):])] = digest
    require(len(checks) == 15, 'unexpected_payload_closure_count')
    require(len(receipt['output_raw_sha256']) == 6, 'unexpected_overlay_file_count')
    paths = {Path(name): digest for name, digest in checks.items()}
    paths[VERIFIER] = VERIFIER_SHA256
    paths[MANIFEST] = None  # The unchanged verifier authenticates its canonical core.
    files, directories = [], set()
    for path, expected in sorted(paths.items()):
        require(path.is_absolute() and '..' not in path.parts, 'invalid_payload_path')
        entry = checked_metadata(path)
        entry['sha256'] = sha256(path)  # Actual successful open/read by UID1000.
        if expected is not None:
            require(entry['sha256'] == expected, 'payload_sha256_mismatch:' + str(path))
        files.append(entry)
        directories.update(path.parents)
    return {'files': files, 'directories': [checked_metadata(p, directory=True)
                                           for p in sorted(directories)]}


def native_imports(report):
    # Install failure traps before importing native packages. The fixture never
    # calls device_count/is_available, launches a kernel, or instantiates a model.
    import torch
    require(not torch.cuda.is_initialized(), 'cuda_initialized_during_torch_import')
    attempts = report.setdefault('cuda_initialization_attempts', [])

    def forbidden_cuda_init(*args, **kwargs):
        attempts.append('blocked')
        raise RuntimeError('cpu_fixture_forbids_cuda_initialization')

    torch.cuda.init = forbidden_cuda_init
    torch.cuda._lazy_init = forbidden_cuda_init
    if hasattr(torch._C, '_cuda_init'):
        torch._C._cuda_init = forbidden_cuda_init
    report['cuda_init_traps'] = 'INSTALLED_BEFORE_NATIVE_IMPORTS'
    # Real package imports, no synthetic sys.modules package or dependency stubs.
    imported = report.setdefault('native_imports', [])
    modules = {}
    for suffix in ('managers.adaptive_idle', 'managers.adaptive_diffusion',
                   'managers.adaptive_diffusion_drain', 'entrypoints.control_requests'):
        module = importlib.import_module(NATIVE + suffix)
        require(Path(module.__file__).resolve().is_relative_to(PACKAGE),
                'native_import_outside_package')
        modules[suffix] = module
        imported.append({'module': module.__name__, 'path': module.__file__, 'status': 'PASS'})
    drain = modules['managers.adaptive_diffusion_drain']
    require(callable(modules['managers.adaptive_idle'].AdaptiveIdle), 'policy_import_invalid')
    require(callable(modules['managers.adaptive_diffusion'].DiffusionIdleBinding),
            'binding_import_invalid')
    # Image scheduler traffic uses pickle; msgspec defines native control types.
    import msgspec
    control_type = modules['entrypoints.control_requests'].ReleaseRealtimeSessionReq
    control = control_type(session_id='h005-cpu-fixture-no-session')
    decoded = msgspec.msgpack.decode(msgspec.msgpack.encode(control), type=control_type)
    require(type(decoded) is control_type and decoded.session_id == control.session_id,
            'native_control_msgspec_roundtrip_failed')
    report['native_control_msgspec_roundtrip'] = 'PASS_NO_REQUEST_SENT'
    import pickle
    for event in ('begin', 'end'):
        signal = drain._signal(event, 'a' * 32, False)
        require(pickle.loads(pickle.dumps(signal)) == signal, 'image_drain_pickle_roundtrip_failed')
    report['image_drain_pickle_roundtrip'] = 'PASS_LOCAL_VALUES_ONLY'

    async def exercise_wrapper():
        observed = []

        async def app(scope, receive, send):
            observed.append(drain._SCOPE.get())
            await send({'type': 'http.response.start', 'status': 204, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        sent = []

        async def send(message):
            sent.append(message)

        wrapper = drain.DiffusionDrainMiddleware(app)
        require(wrapper.app is app, 'native_wrapper_identity_failed')
        await wrapper({'type': 'http', 'method': 'POST', 'path': '/v1/images/generations'},
                      receive, send)
        require(len(observed) == 1 and observed[0]['response_closed'] is True
                and observed[0]['pending'] == {} and drain._SCOPE.get() is None
                and len(sent) == 2, 'native_wrapper_scope_failed')
    asyncio.run(exercise_wrapper())
    report['native_diffusion_drain_wrapper'] = 'PASS_ASGI_FIXTURE_NO_GENERATION'
    # Parse (never execute) the pinned launch function to bind the actual imported
    # wrapper to the native launch call. Full server imports may initialize CUDA.
    source = PACKAGE / 'multimodal_gen/runtime/launch_server.py'
    tree = ast.parse(source.read_text())
    launch = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'launch_http_server_only')
    calls = [node for node in ast.walk(launch) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'run'
             and isinstance(node.func.value, ast.Name) and node.func.value.id == 'uvicorn']
    require(len(calls) == 1 and calls[0].args
            and isinstance(calls[0].args[0], ast.Call)
            and isinstance(calls[0].args[0].func, ast.Name)
            and calls[0].args[0].func.id == 'DiffusionDrainMiddleware',
            'native_launch_wrapper_hook_mismatch')
    report['native_launch_wrapper_hook'] = 'PASS_PINNED_AST_ONLY'
    report['full_server_scheduler_imports'] = 'NOT_TESTED_NO_MODEL_OR_CUDA_INITIALIZATION'
    report['torch_imported'] = 'torch' in sys.modules
    require(not attempts, 'native_import_attempted_cuda_initialization')
    require(not torch.cuda.is_initialized(), 'cuda_initialized')
    report['cuda_initialized'] = False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-server', type=Path, required=True)
    parser.add_argument('--native-server-sha256', required=True)
    args = parser.parse_args(argv)
    started = time.monotonic()
    report = {'schema_version': 1, 'scope': 'actual_image_uid1000_cpu_fixture',
              'status': 'FAIL', 'native_gpu_warmup': 'NOT_TESTED',
              'native_readiness': 'NOT_TESTED', 'generation': 'NOT_TESTED',
              'model_load': 'NOT_EXECUTED', 'production_state_changed': False}
    try:
        require(sys.flags.isolated and sys.dont_write_bytecode, 'requires_python_I_B')
        require(os.getuid() == os.geteuid() == 1000 and os.getgid() == os.getegid() == 1001,
                'requires_configured_uid1000_gid1001')
        require(set(os.getgroups()) <= {1001}, 'unexpected_supplementary_groups')
        report['identity'] = {'uid': os.geteuid(), 'gid': os.getegid(),
                              'supplementary_groups': os.getgroups()}
        report['gpu_devices'] = check_devices()
        report['production_verifier'] = load_native_server(args.native_server,
                                                          args.native_server_sha256)
        report['native_server_sha256'] = args.native_server_sha256
        report['payload'] = check_payload()
        native_imports(report)
        check_devices()
        report['status'] = 'PASS'
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        report['error'] = str(exc)
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
