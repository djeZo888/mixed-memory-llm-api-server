#!/usr/bin/env python3
"""Fixed native launch; only the root-owned unit supplies an invocation ID."""
import os
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import sys

ADAPTIVE_OVERLAY_SHA256 = 'dda84e200adcc6a1ee8915e0e993627695477a346c5848fc27f9251c34d04b3b'
ADAPTIVE_VERIFIER_SHA256 = '554c6ffc6c76fef28a3c778cd25ee1160a21a771906f95a7fea3418682ece00d'


def verify_adaptive_overlay():
    # A new derived image must carry the reviewed overlay. Historical parent
    # identity alone is insufficient; canonical owner admission is additional.
    verifier = Path('/opt/llmctl/adaptive-idle/verify.py')
    if (verifier.is_symlink()
            or hashlib.sha256(verifier.read_bytes()).hexdigest() != ADAPTIVE_VERIFIER_SHA256):
        raise RuntimeError('adaptive_overlay_verifier_mismatch')
    spec = importlib.util.spec_from_file_location('image_adaptive_verifier', verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_installed('/opt/llmctl/adaptive-idle/image.json',
                                   ADAPTIVE_OVERLAY_SHA256, 'image')


def launch_argv():
    return ['sglang', 'serve', '--model-type', 'diffusion',
            '--model-path', '/models', '--model-id', 'Qwen-Image-2.1',
            '--served-model-name', 'qwen-image-2.1', '--backend', 'sglang',
            # Only host127.0.0.1:30007 is published by the private namespace.
            '--host', '0.0.0.0', '--port', '30007', '--strict-ports', 'true',
            '--master-port', '30009', '--scheduler-port', '30010',
            '--num-gpus', '1', '--performance-mode', 'speed',
            '--component-residency', 'all=resident',
            '--dit-cpu-offload', 'false', '--dit-layerwise-offload', 'false',
            '--text-encoder-cpu-offload', 'false', '--image-encoder-cpu-offload', 'false',
            '--vae-cpu-offload', 'false', '--use-fsdp-inference', 'false',
            '--attention-backend', 'torch_sdpa', '--enable-torch-compile', 'false',
            '--enable-breakable-cuda-graph', 'false', '--warmup-mode', 'off',
            '--vae-tiling', 'false', '--vae-sp', 'false',
            '--batching-max-size', '1', '--batching-delay-ms', '0',
            '--output-path', '', '--input-save-path', '']

def selected_gpu(argv, environ):
    # The protected owner forwards its selected full UUID in fixed launch argv.
    # Container containment separately binds DeviceRequests and the GPU label.
    if (len(argv) != 3 or not re.fullmatch(r'GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', argv[2])
            or environ.get('CUDA_VISIBLE_DEVICES') != argv[2]
            or environ.get('NVIDIA_VISIBLE_DEVICES') != argv[2]):
        raise RuntimeError('unexpected_gpu_visibility')
    return argv[2]


def evidence_directory(invocation):
    # Only the supervisor creates these directories. Never repair or fall back.
    if (not re.fullmatch('[0-9a-f]{32}', invocation)
            or (os.geteuid(), os.getegid()) != (1000, 1001)):
        raise RuntimeError('unsafe_startup_evidence')
    fd = None
    device = None
    try:
        for name in ('/work', 'evidence', invocation):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            if fd is not None:
                os.close(fd)
            fd = child
            meta = os.fstat(fd)
            if (not stat.S_ISDIR(meta.st_mode) or meta.st_mode & 0o022
                    or device is not None and meta.st_dev != device
                    or (name != invocation and meta.st_uid != 0)
                    or (name == invocation and ((meta.st_uid, meta.st_gid) != (1000, 1001)
                                                or stat.S_IMODE(meta.st_mode) != 0o700))):
                raise RuntimeError('unsafe_startup_evidence')
            device = meta.st_dev
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


EXCEPTION_CLASSES = (RuntimeError, PermissionError, FileNotFoundError, FileExistsError,
                     NotADirectoryError, IsADirectoryError, OSError, ImportError,
                     ValueError, TypeError, KeyError)
GUARD_CODES = frozenset({
    'unexpected_gpu_visibility', 'adaptive_overlay_verifier_mismatch',
    'adaptive_overlay_expected_digest_invalid', 'adaptive_overlay_target_invalid',
    'adaptive_overlay_receipt_invalid', 'adaptive_overlay_digest_mismatch',
    'adaptive_overlay_target_mismatch', 'adaptive_overlay_path_invalid',
    'adaptive_overlay_installed_source_mismatch',
})


def startup_record(fd, stage, error=None):
    # Four entries and at most one failure; no arbitrary text or type names.
    if stage not in ('visibility', 'overlay', 'log_open', 'exec'):
        raise RuntimeError('invalid_startup_stage')
    classify = lambda value: ('none' if value is None else
                              type(value).__name__ if type(value) in EXCEPTION_CLASSES else 'Exception')
    cause = None if error is None else error.__cause__
    if error is not None and cause is None and not error.__suppress_context__:
        cause = error.__context__
    code = 'entered' if error is None else stage + '_failed'
    if (error is not None and error.args and type(error.args[0]) is str
            and error.args[0] in GUARD_CODES):
        code = error.args[0]
    raw = (json.dumps({'stage': stage, 'code': code, 'exceptionClass': classify(error),
                       'causeClass': classify(cause)}, separators=(',', ':')) + '\n').encode()
    if len(raw) > 256 or os.write(fd, raw) != len(raw):
        raise RuntimeError('startup_receipt_write_failed')
    os.fsync(fd)


def launch_owned(args, environ):
    if len(args) != 3 or not re.fullmatch('[0-9a-f]{32}', args[1]):
        raise RuntimeError('invalid_owned_invocation')
    directory = evidence_directory(args[1])
    receipt = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        receipt = os.open('startup.jsonl', flags, 0o600, dir_fd=directory)
        stage = 'visibility'
        try:
            startup_record(receipt, stage)
            selected_gpu(args, environ)
            stage = 'overlay'
            startup_record(receipt, stage)
            verify_adaptive_overlay()
            stage = 'log_open'
            startup_record(receipt, stage)
            fd = os.open('backend.log', flags, 0o600, dir_fd=directory)
            try:
                os.dup2(fd, 1)
                os.dup2(fd, 2)
            finally:
                os.close(fd)
            stage = 'exec'
            startup_record(receipt, stage)
            argv = launch_argv()
            os.execvp(argv[0], argv)
            raise RuntimeError('native_exec_returned')
        except Exception as error:
            try:
                startup_record(receipt, stage, error)
            except Exception:
                pass  # Preserve the original failure; no fallback or raw output.
            raise
    finally:
        if receipt is not None:
            os.close(receipt)
        os.close(directory)


def main():
    launch_owned(sys.argv, os.environ)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Docker logging is intentionally absent. Receipt absence stays truthful;
        # the original supervisor failure remains authoritative for unsafe paths.
        raise SystemExit(1) from None
