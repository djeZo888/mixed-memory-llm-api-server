# Large Model Proof Of Life

M9E attempted the first approved large-model proof-of-life target: `MiniMaxAI/MiniMax-M3-MXFP8` through KTransformers / KT-Kernel plus SGLang-KT heterogeneous CPU/GPU serving.

## M9E Result

- Result: STOP.
- Branch: `milestone/m9e-large-model-poc`.
- Report: `reports/m9e-large-model-poc.md`.
- Selected model: `MiniMaxAI/MiniMax-M3-MXFP8`.
- Local model path: `/data/models/minimax-m3-mxfp8`.
- Model size: `414G`.
- Initial runtime image: `local/minimax-m3-ktransformers:0.6.3-post1`.
- R1 runtime image: `local/minimax-m3-ktransformers:0.6.3-post1-r1`.
- Runtime compose path used for launch attempts: `/data/services/llm-manager/compose/minimax-m3-poc.compose.yml`.
- Repo compose template: `configs/compose/compose.minimax-m3-poc.template.yml`.
- Latest R1 diagnostics: `/data/logs/minimax-m3-poc/m9e-r1-failure-20260708T203230Z`.
- Current active backend is restored 30B at `http://127.0.0.1:30001/v1`, bound to `127.0.0.1` only.

## What Passed

- MiniMax model download completed and fallback model download did not occur.
- Initial M9E runtime build/import preflight passed before download.
- M9E-R1 added `libnuma1`, `libnuma-dev`, and `numactl` inside the isolated Docker image only.
- R1 verification proved `libnuma.so.1` is present, `sgl_kernel` imports, `common_ops` loads, ldd resolves dependencies, and required KT/SGLang launch flags are present.
- Root-disk guard, Docker storage verification, GPU container verification, and 30B restore verification passed.
- No public API exposure, Docker daemon change, restart policy, systemd service, model deletion, image deletion, or Docker prune occurred.

## Current Failure Boundary

The original M9E blocker was missing `libnuma.so.1`, which prevented `sgl_kernel` common ops from loading. R1 fixed that dependency.

The current blocker is SM120 support in the SGLang MXFP8 path. The R1 launch reached container startup and `127.0.0.1:30002` listened, but `/v1/models` never passed. Logs show:

```text
assert is_sm100_supported() or is_sm90_supported()
AssertionError
```

The runtime package contains `sm90` and `sm100` common ops, not native `sm120` common ops. `sgl_kernel` imports through the SM100 compatibility/fallback path, but MiniMax MXFP8 serving still stops before readiness on RTX PRO 6000 Blackwell Workstation / SM120.

## Current Boundary

MiniMax did not achieve `/v1/models` or chat proof. The current active service is the restored 30B SGLang backend:

- Model: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1` only.
- Model files preserved at `/data/models/qwen3-30b-a3b-instruct-2507`.

## Next Step

Next task: SM120-specific MiniMax runtime remediation planning. Determine whether current SGLang-KT/MXFP8 can support SM120 through an upstream wheel/source build or whether a different approved runtime, quantization path, or model path is required. Do not download fallback models without separate human approval.
