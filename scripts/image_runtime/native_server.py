#!/usr/bin/env python3
"""Fixed native launch; only the root-owned unit supplies an invocation ID."""
import os
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

GPU_UUID = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
ADAPTIVE_OVERLAY_SHA256 = 'a2d2eb892e600ff710e60145f64c2d65a6e62b45e5cf549fb9eb214e1772b0d2'
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

def main():
    if len(sys.argv) != 2 or not re.fullmatch('[0-9a-f]{32}', sys.argv[1]):
        raise SystemExit('invalid_owned_invocation')
    if os.environ.get('CUDA_VISIBLE_DEVICES') != GPU_UUID:
        raise SystemExit('unexpected_cuda_visibility')
    verify_adaptive_overlay()
    path = Path('/work/evidence') / sys.argv[1] / 'backend.log'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    argv = launch_argv()
    os.execvp(argv[0], argv)

if __name__ == '__main__':
    main()
