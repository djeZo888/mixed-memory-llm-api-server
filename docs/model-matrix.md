# Model Matrix

Do not download large models before `/data`, Docker storage, cache paths, root-disk guard, GPU driver, and API smoke tests are complete.

## GPU Compatibility Gate

Before selecting GPU acceleration for any model, M5A must pass and the human must approve the NVIDIA driver, CUDA Toolkit, PyTorch CUDA wheel, KTransformers/kt-kernel, ik_llama, and NVIDIA Container Toolkit matrix. This is especially important for RTX PRO 6000 Blackwell class GPUs, where backend support must be proven from official NVIDIA sources and upstream project sources before installation or benchmarking.

If M5A concludes that KTransformers or ik_llama support is not yet proven for the installed GPU architecture, keep the affected model/backend combination in `Blocked` status and do not run GPU benchmarks for it.

| Priority | Model | Role | First backend | Status |
| --- | --- | --- | --- | --- |
| 0 | Small smoke-test model | API/auth/logging validation | To be selected | Planned |
| 1 | Qwen/Qwen3.6-35B-A3B | Fast technical/coding | KTransformers | Planned |
| 2 | Qwen/Qwen3.5-122B-A10B | Larger fast/quality | KTransformers | Planned |
| 3 | Qwen/Qwen3.5-397B-A17B | Big quality | KTransformers | Planned |
| 4 | zai-org/GLM-5.2 | Big quality | KTransformers | Planned |
