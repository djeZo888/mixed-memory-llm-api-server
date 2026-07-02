# Model Matrix

Do not download large models before `/data`, Docker storage, cache paths, root-disk guard, GPU driver, and API smoke tests are complete.

## GPU Compatibility Gate

M5A execution produced `reports/m5a-cuda-nvidia-compatibility.md` with a `STOP` conclusion for installation until human review. Host-driver-only M5B may proceed only after the human approves the recommended matrix. KTransformers Blackwell GPU support is not proven by current prebuilt kt-kernel wheels because the published GPU matrix lists SM 80, 86, 89, and 90, not SM 120.

Until M5B/M6/M7 pass, keep all GPU-backed model work blocked. CPU-only smoke work may proceed later only when it stays within `/data` storage rules and does not download large model weights before approval.

| Priority | Model | Role | First backend | Status | Gate |
| --- | --- | --- | --- | --- | --- |
| 0 | Small smoke-test model | API/auth/logging validation | To be selected | Planned | Wait for M8 storage/API approval; CPU-only remains acceptable if GPU is blocked. |
| 1 | Qwen/Qwen3.6-35B-A3B | Fast technical/coding | KTransformers first, ik_llama fallback if GGUF path is better | Blocked for GPU | Requires human review of M5A, M5B driver pass, M6 toolkit pass if containers are used, and M7 backend smoke. |
| 2 | Qwen/Qwen3.5-122B-A10B | Larger fast/quality | KTransformers | Blocked for GPU | Requires proven KTransformers/kt-kernel SM_120 support or approved CPU/GGUF fallback. |
| 3 | Qwen/Qwen3.5-397B-A17B | Big quality | KTransformers | Blocked for GPU | Requires storage sizing, model download approval, and proven backend support. |
| 4 | zai-org/GLM-5.2 | Big quality | KTransformers | Blocked for GPU | Requires proven backend support and model-specific memory plan. |

## Current Backend Notes

- Recommended PyTorch wheel family after approval: `cu128` first.
- Host CUDA Toolkit approach: do not install for M5B; use driver-only validation first.
- KTransformers: do not rely on prebuilt wheels for Blackwell; require source-build proof for SM_120.
- ik_llama: appears plausible for Blackwell through CUDA, but remains unverified until source build and smoke test.
