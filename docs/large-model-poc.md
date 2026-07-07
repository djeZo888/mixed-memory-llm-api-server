# Large Model Proof Of Life

M9E attempted the first approved large-model proof-of-life target: `MiniMaxAI/MiniMax-M3-MXFP8` through KTransformers / KT-Kernel plus SGLang-KT heterogeneous CPU/GPU serving.

## M9E Result

- Result: STOP.
- Branch: `milestone/m9e-large-model-poc`.
- Report: `reports/m9e-large-model-poc.md`.
- Selected model: `MiniMaxAI/MiniMax-M3-MXFP8`.
- Local model path: `/data/models/minimax-m3-mxfp8`.
- Model size: `414G`.
- Runtime image built: `local/minimax-m3-ktransformers:0.6.3-post1`.
- Runtime compose path used for the failed launch: `/data/services/llm-manager/compose/minimax-m3-poc.compose.yml`.
- Repo compose template: `configs/compose/compose.minimax-m3-poc.template.yml`.
- Failed container: `minimax-m3-mxfp8-poc`, exited with status 1.
- Failure diagnostics: `/data/logs/minimax-m3-poc/m9e-failure-20260707T030539Z`.
- Prior 30B backend was restored and is active at `http://127.0.0.1:30001/v1`, bound to `127.0.0.1` only.

## What Passed

- Context-sync gate passed on `llmserver` in `/data/services/mixed-memory-llm-api-server`.
- Runtime build/import preflight passed before model download.
- Required SGLang-KT MiniMax/KTransformers launch flags were present in `python3 -m sglang.launch_server --help`.
- `MiniMaxAI/MiniMax-M3-MXFP8` downloaded successfully to `/data/models/minimax-m3-mxfp8`.
- Required model files were present: `config.json`, tokenizer/chat template files, and 31 safetensors shards.
- Root-disk guard, Docker storage verification, and GPU container verification passed.
- No fallback model was downloaded.
- No public API exposure was configured.
- No Docker/containerd daemon configuration was changed.

## Failure Boundary

The MiniMax container exited before readiness. The log shows `sgl_kernel` failed to load common ops on the SM120 GPUs, with `libnuma.so.1` missing in the runtime image:

```text
[sgl_kernel] CRITICAL: Could not load any common_ops library!
GPU Info:
- Compute capability: 120
- Expected variant: SM120 (precise math for compatibility)
Error details from previous import attempts:
- ImportError: libnuma.so.1: cannot open shared object file: No such file or directory
- ModuleNotFoundError: No module named 'common_ops'
```

The container also printed:

```text
Triton is not supported on current platform, roll back to CPU.
```

## Current Boundary

M9E did not achieve `/v1/models` or chat proof for MiniMax. The current active service is the restored 30B SGLang backend:

- Model: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1` only.
- Model files preserved at `/data/models/qwen3-30b-a3b-instruct-2507`.

## Next Step

Next task: M9E remediation planning, not M9F benchmarking. Remediation should update and rebuild only the isolated MiniMax runtime image, verify `libnuma.so.1` and `sgl_kernel` common ops loading inside the image, account for SM120 support limits, and then relaunch MiniMax only after the preflight proves those imports cleanly.
