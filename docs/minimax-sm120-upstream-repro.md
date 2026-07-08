# MiniMax-M3 SM120 Upstream Reproduction

- Timestamp: `2026-07-08T21:35:35Z`
- Repo branch: `milestone/m9e-r2-sm120-minimax-remediation`
- Result: STOP. MiniMax-M3-MXFP8 did not reach API proof-of-life on RTX PRO 6000 Blackwell Workstation / SM120.

## Hardware

- Hostname: `llmserver`
- GPU: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition
- Compute capability: `12.0` / SM120
- VRAM: `97887 MiB` per GPU
- Driver: `595.71.05`
- Host CUDA Toolkit: not installed
- Docker GPU runtime: NVIDIA Container Toolkit verified

## Model And Runtime

- Model: `MiniMaxAI/MiniMax-M3-MXFP8`
- Model path: `/data/models/minimax-m3-mxfp8`
- Model size on disk: `414G`
- Fallback model: not downloaded
- Initial image: `local/minimax-m3-ktransformers:0.6.3-post1`
- R1 image: `local/minimax-m3-ktransformers:0.6.3-post1-r1`
- R2 image: not built; R2 stopped before build because no clean SM120-compatible path was identified
- Runtime path: SGLang-KT plus KT-Kernel, isolated in Docker
- Active service after STOP: restored/existing 30B Qwen backend at `http://127.0.0.1:30001/v1`, localhost-only

## Package Versions In R1 Image

- Python: `3.12.3`
- Torch: `2.9.1+cu128`
- Torch CUDA runtime: `12.8`
- `sglang-kt`: `0.6.3.post1`
- `sgl-kernel`: `0.3.21`
- `kt-kernel`: `0.6.3.post1`
- `flashinfer-python`: `0.6.3`
- `flashinfer-cubin`: `0.6.3`
- `transformers`: `5.13.0`

## Launch Command Shape

The failed R1 MiniMax proof used localhost-only Docker publishing (`127.0.0.1:30002:30000`) and launched SGLang inside the container with this command shape:

```text
python3 -m sglang.launch_server
  --model-path /data/models/minimax-m3-mxfp8
  --kt-weight-path /data/models/minimax-m3-mxfp8
  --kt-method MXFP8
  --kt-cpuinfer 64
  --kt-threadpool-count 7
  --kt-num-gpu-experts 8
  --kt-gpu-prefill-token-threshold 500
  --tp-size 2
  --quantization mxfp8
  --moe-runner-backend triton
  --trust-remote-code
  --host 0.0.0.0
  --port 30000
  --served-model-name minimax-m3-mxfp8-poc
  --context-length 8192
  --mem-fraction-static 0.55
  --chunked-prefill-size 4096
  --cuda-graph-max-bs 1
  --tool-call-parser minimax-m3
  --reasoning-parser minimax-m3
  --max-running-requests 1
```

SGLang-KT overrode `--moe-runner-backend triton` for this CUDA MXFP8 branch:

```text
mxfp8 quantization forces --moe-runner-backend=cutlass. Overriding 'triton'.
```

## Exact Assertion

R1 traceback excerpt from `/data/logs/minimax-m3-poc/m9e-r1-failure-20260708T203230Z/docker.log`:

```text
File "/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/models/minimax_m3.py", line 344, in __init__
  self.experts = get_moe_impl_class(quant_config)(...)
File "/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/moe/fused_moe_triton/layer.py", line 280, in __init__
  gpu_method = quant_config.get_quant_method(self, prefix)
File "/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/quantization/fp8.py", line 213, in get_quant_method
  fp8_method = Fp8MoEMethod(self)
File "/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/quantization/fp8.py", line 788, in __init__
  assert is_sm100_supported() or is_sm90_supported()
AssertionError
```

Related source paths in the installed image:

- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/quantization/fp8.py:788`: `assert is_sm100_supported() or is_sm90_supported()`
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/moe/cutlass_moe.py:147`: `assert is_sm100_supported(), "MXFP8 requires SM100"`
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/server_args.py:2538`: SGLang-KT forces CUDA MXFP8 to Cutlass for this path
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/utils/common.py:253`: `is_sm120_supported()` exists and returns true on this host
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/utils/common.py:3606`: `mxfp8_block_convert_required()` returns false for compute capability major >= 10, including SM120

## common_ops Coverage

Files present in R1 image:

```text
/opt/minimax-m3-runtime/lib/python3.12/site-packages/sgl_kernel/sm90/common_ops.abi3.so
/opt/minimax-m3-runtime/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so
```

No native SM120 directory or `common_ops` file was present.

On SM120, `sgl_kernel.load_utils` selected the `sm100` common_ops path for compatibility/fallback loading. Import succeeded after R1 fixed NUMA:

```text
loaded common_ops /opt/minimax-m3-runtime/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so
```

With runtime library paths set to the image's torch/NVIDIA wheel libraries, ldd resolved `sm90` and `sm100` common ops, including `libnuma.so.1`. The R1 image did not include `file`, `strings`, `cuobjdump`, or `nvdisasm`, so deeper fatbin/PTX inspection was not available inside the image.

## What R1 Fixed

R1 added the missing NUMA dependency inside the isolated Docker image only:

- `libnuma1`
- `libnuma-dev`
- `numactl`

After R1, `libnuma.so.1`, `sgl_kernel`, and common_ops import/loading were no longer the immediate blocker. The remaining blocker is SM120 support in the MiniMax-M3-MXFP8 SGLang-KT / `sgl-kernel` path.

## Upstream Evidence Summary

- KTransformers MiniMax tutorial: `https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/MiniMax-M3-Tutorial.md`
  - Lists SM90 Hopper as supported and says upstream SGLang targets SM100 datacenter Blackwell so far.
- KTransformers issue #2058: `https://github.com/kvcache-ai/ktransformers/issues/2058`
  - Same MiniMax-M3-MXFP8 RTX PRO 6000 / SM120 assertion; maintainer response says SM120 is not supported.
- KTransformers issue #2081: `https://github.com/kvcache-ai/ktransformers/issues/2081`
  - New same-boundary report on RTX PRO 4500 / SM120.
- SGLang issue #29900 and PR #29902: `https://github.com/sgl-project/sglang/issues/29900`, `https://github.com/sgl-project/sglang/pull/29902`
  - SM120 test sweep records expected-unsupported failures in related kernel families.
- SGLang PR #28125: `https://github.com/sgl-project/sglang/pull/28125`
  - Open/unreleased SM120/SM121 dispatch for `fp8_blockwise_scaled_grouped_mm`; relevant but not sufficient to prove MiniMax-M3-MXFP8 end-to-end.
- NVIDIA CUDA GPU table: `https://developer.nvidia.com/cuda/gpus`
  - RTX PRO 6000 Blackwell Workstation Edition is compute capability 12.0.
- NVIDIA Blackwell Compatibility Guide: `https://docs.nvidia.com/cuda/blackwell-compatibility-guide/index.html`
  - CUDA apps require compatible native cubin or forward-compatible PTX; missing both causes launch failure.

## Reproduction Boundary

R2 did not patch installed files in place and did not build an R2 image. The observed state points to an upstream/release-level gap, not a local dependency-only failure:

- Python guard rejects SM120 before MiniMax reaches model serving.
- The forced Cutlass MXFP8 path requires SM100.
- The installed `sgl-kernel` wheel has SM90/SM100 common ops only.
- Current upstream issues/PRs show SM120 support work is still incomplete or unreleased for relevant kernel paths.

## Scope Confirmations

- No fallback model was downloaded.
- No model files were deleted.
- No Docker image was deleted.
- No Docker prune was run.
- No Docker/containerd daemon configuration was changed.
- No Docker/containerd daemon was restarted.
- No host CUDA Toolkit was installed.
- No host SGLang/KTransformers/system Python package was installed.
- No public API exposure, firewall change, Caddy, reverse proxy, API auth/front-door, systemd service, or Docker restart policy was created.
- No secrets are included in this document.
