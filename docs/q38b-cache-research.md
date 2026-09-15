# Q38B cache resolver and no-GPU image gate

Status: **source review and controlled worker tests PASS; actual pinned-image
execution, GPU/model execution, compilation and live acceptance NOT_TESTED**.
This source task accessed public source only. Worker1 owns later actual execution.

## Reviewed correction

SGLang commit `0bcd822377da7b5718e674eaf9c870d349424dd1` directly derives
`SGLANG_CACHE_DIR` from the user's home, independently of `XDG_CACHE_HOME`.
Its DeepGEMM default follows this base lazily. Set `SGLANG_CACHE_DIR=/cache/sglang`;
no separate DeepGEMM override is needed. SGLang's third-party redirect uses
`setdefault`, preserving the launcher's existing fixed overrides. Its package
initializer invokes that redirect before heavy imports.
([registry](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/environ.py),
[initialization](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/__init__.py))

The JIT build resolver has a separate hard-coded home fallback. Set
`SGLANG_JIT_CACHE_DIR=/cache/sglang/jit`. Native architecture detection catches
missing devices and produces `sm00`; the probe calls the actual build-path
resolver using that fallback, without mocking it or compiling a kernel.
([build path](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/kernels/jit/utils/compile/cache.py),
[architecture fallback](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/kernels/jit/utils/arch.py))

Only these two environment variables are added. `HOME` is retained and checked
for changes. `SGLANG_DG_CACHE_DIR`, arbitrary SGLang switches and unreviewed cache
overrides remain unavailable through this launcher.

## Native resolver coverage

| Resolver | Required effective path |
| --- | --- |
| SGLang base / DeepGEMM default | `/cache/sglang` / `/cache/sglang/deep_gemm` |
| SGLang JIT sample build path | `/cache/sglang/jit/sm00/q38b_resolver_probe/build-0000000000000000` |
| Hugging Face home / hub / assets | `/cache/huggingface`, with `hub` / `assets` children |
| Transformers module cache | `/cache/huggingface/modules` |
| Triton FileCacheManager sample | `/cache/triton/q38b_resolver_probe` |
| PyTorch Inductor / extension root | `/cache/torchinductor` / `/cache/torch_extensions` |
| FlashInfer cache | `/cache/flashinfer/.cache/flashinfer` |
| FlashInfer no-device workspace | cache root + `/0.6.18`, with `cached_ops` / `generated` children |
| CUDA driver JIT configuration | `/cache/cuda`; actual driver cache use **NOT_TESTED** |

FlashInfer appends its own cache subdirectory to the configured base; with zero
devices its architecture component is empty. Installed AOT/cubin package assets
remain read-only image assets and are not presented as writable caches.
([FlashInfer cache source](https://github.com/flashinfer-ai/flashinfer/blob/69ff11fc4954396d98326656dc85debd2223f637/flashinfer/jit/env.py),
[compilation context](https://github.com/flashinfer-ai/flashinfer/blob/69ff11fc4954396d98326656dc85debd2223f637/flashinfer/compilation_context.py))

PyTorch's Inductor resolver uses its explicit override; the extension default
uses the XDG cache directory. Transformers derives its module directory from
Hugging Face home.
([Inductor](https://github.com/pytorch/pytorch/blob/v2.13.0/torch/_inductor/runtime/cache_dir_utils.py),
[extensions](https://github.com/pytorch/pytorch/blob/v2.13.0/torch/utils/cpp_extension.py),
[XDG resolver](https://github.com/pytorch/pytorch/blob/v2.13.0/torch/_appdirs.py),
[Transformers](https://github.com/huggingface/transformers/blob/v5.12.1/src/transformers/utils/hub.py))

The probe pins exact public source bytes for SGLang, FlashInfer, PyTorch's two
resolver modules and Transformers in `SOURCE_PINS`. Hugging Face Hub and Triton
are transitive dependencies whose installed versions have **not** been observed
in this source session. Their imported native APIs must produce the exact paths
above in the independently verified immutable image. The receipt labels their
scope `IMAGE_BOUND_NATIVE_API_PATH_CHECK`; it does not claim independently pinned
upstream dependency source. No new environment override is inferred from their
current public source.
([Hub constants](https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/constants.py),
[Triton cache API](https://github.com/triton-lang/triton/blob/main/python/triton/runtime/cache.py))

## NVIDIA 1.19.1 contract and boundaries

The existing installer lock selects NVIDIA Container Toolkit/libnvidia-container
`1.19.1-1`. Its versioned upstream contract distinguishes `none` (driver
capabilities enabled, no selected GPUs) from `void` (runc behavior). The bounded
fixture uses `--runtime nvidia`, `NVIDIA_VISIBLE_DEVICES=none`,
`NVIDIA_DRIVER_CAPABILITIES=compute,utility`, and empty `CUDA_VISIBLE_DEVICES`.
It must pass no `--gpus` or device requests.
([versioned runtime contract](https://github.com/NVIDIA/nvidia-container-toolkit/blob/v1.19.1/cmd/nvidia-container-runtime/README.md))

The driver mount implementation can still mount global control/UVM nodes for
compute capability. The probe permits only `/dev/nvidiactl`, `/dev/nvidia-uvm`,
and `/dev/nvidia-uvm-tools`, records those observed, rejects GPU/render/MIG nodes
and other unreviewed NVIDIA nodes, loads `libcuda.so.1` and `libnvidia-ml.so.1`,
and requires unmodified PyTorch to report zero devices and unavailable CUDA.
This proves library loading and absence of GPU access at the fixture boundary;
it does not prove a CUDA kernel ran.
([versioned mount implementation](https://github.com/NVIDIA/libnvidia-container/blob/v1.19.1/src/nvc_mount.c))

The reported 0.5.14 F1DX runc/void import failure remains a separate pending
diagnosis. The 0.5.19 gate does not copy that no-library execution or infer that
its installed dependencies will import successfully. Any missing library,
source drift, import failure or resolver mismatch fails closed.

## Worker1 call and integration contract

The outer `run_fixture.py` must first verify the image/OCI relationship, runtime
configuration, absence of device requests, unique container identity and all
fixture hashes. Its pinned-image child invokes the cache probe in a separate
bounded Python subprocess
**before** creating synthetic model/key files and before installing CUDA stubs.
`/models` and `/run/secrets` must be empty private tmpfs mounts; `/cache` must be
private writable tmpfs; the container root must be read-only. No host model or
real secret may be mounted. The probe's directory-FD writes reject symlink
traversal and remove only their own exclusive probe files.

The separate interpreter matters: native SGLang imports cache its platform
singleton, and JIT/FlashInfer cache architecture discovery. No-device discovery
must not contaminate the auth fixture's later explicitly stubbed hardware setup.
The parent validates the child's exact result through the pure validator before
importing the native auth stack. A child failure/timeout fails the whole gate;
outer verified-container cleanup also terminates container descendants.

The same in-container probe is callable directly within that verified isolation:

```text
python3 -B /fixture/tests/lifecycle/sglang38_fixture/cache_probe.py --actual-image --repo /fixture
```

Its JSON has `schema_version: 1`, `kind: q38b_cache_resolvers`, and
`status: PASS_ACTUAL_CACHE_RESOLVERS`. Host/lifecycle consumers must call the pure
`validate_result(result)` function, require the enclosing receipt's verified
container/image binding, and bind the fixture/support hashes. The probe itself
reports `HOST_DOCKER_INSPECT_REQUIRED` and cannot establish OCI identity.
The enclosing native gate records `actual_cache_resolvers` and
`no_gpu_driver_libraries` as PASS only after this complete check. CUDA driver
cache use remains `CONFIG_ONLY_NO_KERNEL`; no actual-image success is asserted
by this source report.

## Verification

```text
python3 -B -m unittest discover -s tests/lifecycle -p test_qwen38_cache_probe.py -v
python3 -B tests/lifecycle/sglang38_fixture/cache_probe.py --help
```

The controlled worker suite verifies read-only/tmpfs boundaries, runtime-env
refusal, GPU-node refusal, path drift, exact/pure receipt validation, operation
ordering, private file cleanup, symlink refusal, an unrelated file sentinel,
missing-library/import failure disclosure control and retained HOME policy.
Actual pinned-image checks remain Worker1's next action.
