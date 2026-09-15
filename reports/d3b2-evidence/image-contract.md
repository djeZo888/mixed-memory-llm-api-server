# D3B2 measured image contract — frozen for D3RD

Status: PASS_BUILD_CLI_ENUMERATION_ONLY

## Exact binding fields

```json
{
  "runtime_id": "llama-cpp-v0.4.1-d3br",
  "image_tag": "local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d",
  "image_id": "sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9",
  "repo_digests": [
    "local/llama-cpp@sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9"
  ],
  "image_config_sha256": "89a1ea2575d8a5ea2c2debd618d420ac03194b1c2d54b85972a8ebff850f3938",
  "platform_manifest_sha256": "384a22a0b15b9668b89e4ec46ed7363f2bb02e91d3344db102411288551ef62b",
  "source_revision": "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4",
  "binary_sha256": "c81262fd063e9d2fc098d9e116d0ae742ca7ea37344ee3f4b56eb5d088206e0a",
  "source_kind": "upstream-plus-checked-patch",
  "upstream_tree": "950999fe62b7fe55f44ab5b7394e3c8542f37f12",
  "patch_sha256": "43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b",
  "derived_tree": "0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e",
  "derived_commit": null,
  "oci_revision_kind": "git-tree",
  "build_recipe_manifest_sha256": "87b03d3c2ebd3b4369c6014ccd1ca7fcfb502747f7bee0b81036f7f99c9409bb",
  "runtime_proof_path": "reports/d3b2-evidence/runtime-proof.json",
  "runtime_proof_sha256": "1d500eae56d6e777b944b2492071c8b3dd28ea350b04f5c72da5b7bd70d052c9",
  "supported_flags": [
    "--model",
    "--host",
    "--port",
    "--alias",
    "--api-key-file",
    "--ctx-size",
    "--parallel",
    "--cpu-moe",
    "--jinja",
    "--no-webui",
    "--n-gpu-layers",
    "--split-mode",
    "--tensor-split",
    "--load-mode",
    "--device",
    "--chat-template-kwargs",
    "--n-cpu-moe"
  ],
  "supported_load_modes": [
    "auto",
    "none",
    "mmap",
    "mlock",
    "mmap+mlock",
    "dio"
  ],
  "devices": [
    "CUDA0",
    "CUDA1"
  ],
  "validation_status": "PASS_BUILD_CLI_ENUMERATION_ONLY",
  "active_binding_edited": false,
  "rollback_runtime_id": "llama-cpp-v0.4.1-d1",
  "rollback_image_id": "sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62"
}
```

## Exact image identity and labels

```json
{
  "image_id": "sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9",
  "image_tag": "local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d",
  "image_index_sha256": "86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9",
  "platform_manifest_sha256": "384a22a0b15b9668b89e4ec46ed7363f2bb02e91d3344db102411288551ef62b",
  "image_config_sha256": "89a1ea2575d8a5ea2c2debd618d420ac03194b1c2d54b85972a8ebff850f3938",
  "repo_digests": [
    "local/llama-cpp@sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9"
  ],
  "platform": "linux/amd64",
  "entrypoint": [
    "/opt/llama/llama-server"
  ],
  "oci_labels": {
    "local.d1.cuda.architectures": "120a-real",
    "local.d3p.source.derived-tree": "0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e",
    "local.d3p.source.kind": "upstream-plus-checked-patch",
    "local.d3p.source.patch-sha256": "43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b",
    "local.d3p.source.revision-kind": "git-tree",
    "local.d3p.source.upstream-commit": "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4",
    "maintainer": "NVIDIA CORPORATION <cudatools@nvidia.com>",
    "org.opencontainers.image.revision": "0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e",
    "org.opencontainers.image.source": "https://github.com/ggml-org/llama.cpp",
    "org.opencontainers.image.version": "v0.4.1+d3p"
  }
}
```

## Revised recipe SHA256

- `Dockerfile.d3p`: `704fe3dcbcddd4497147b2b12b09ac674cb1b7c2ce2b049197620691b6acd92a`.
- `Dockerfile.d3p.dockerignore`: `875afccc85a373f21e7fc8197b2c91ffd6a8ae321aef56767a5099c7fe7d4761`.
- `prepare-d3p-source.py`: `47be70ebc01f7f5ff6d790c510bc9bf1ef9cf604ed725449ec3e52548798138a`.
- `build-d3p-runtime.sh`: `67c5124ff21ec4a0e56e8678b6e888300c11aa0aa33b2e05ffb80627e6bf3a9f`.
- `d3p-source.json`: `a073747a339995e3dc6f1b509c7d977765d46f1959340ee4b2895230bf7c13c7`.
- `strict-model-chat.patch`: `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b`.

Host AND in-image recipe manifest SHA256: `87b03d3c2ebd3b4369c6014ccd1ca7fcfb502747f7bee0b81036f7f99c9409bb`. Revised helper/runner are bound; historical D3PD hashes are not final proof.

Build source owner `c7155099e4d8d096b0e946352fbf01e3a9072ab9`; build 2026-09-15T03:27:14Z to 2026-09-15T03:30:27Z, one actual attempt, build.exit=job.exit=0. Source revision remains upstream; derived tree is separate, derived commit null, source_state verified-patched.

## Measured CLI and device enumeration

Both runc version/help containers exited0; all16 baseline flags plus --n-cpu-moe verified. Load modes listed above are exact help modes.

- CUDA0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (97249 MiB, 79836 MiB free)
- CUDA1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition (97249 MiB, 83724 MiB free)

ONE separately authorized enumeration used NVIDIA runtime/device0,1, compute/utility, 30s timeout; no network, ports or model/key mounts. It exited0. All3 verification containers were quiescent and removed by exact ID; independent absence checks passed.

GPU before/after memory samples (MiB):

```json
[
  {
    "index": "0",
    "name": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
    "before": 16856,
    "after": 16856,
    "delta": 0
  },
  {
    "index": "1",
    "name": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
    "before": 12968,
    "after": 12968,
    "delta": 0
  }
]
```

Compute-process rows unchanged: True. Samples do not exclude transient CUDA contexts or initialization. Original GLM identity/image/start unchanged.

## Evidence and acceptance boundary

VM evidence: `/data/build/d3p-d3b2-20260915/evidence`; proof `runtime-proof.json` SHA256 `1d500eae56d6e777b944b2492071c8b3dd28ea350b04f5c72da5b7bd70d052c9`. Local evidence is copied verbatim to `repo/reports/d3b2-evidence/`. Exact help/version/list-devices outputs and source/recipe/CMake/nvcc/package evidence retained.

Build/CLI/enumeration PASS only. Model/context/kernel/protocol/fusion/allocated-workspace acceptance remains NOT_TESTED. Installer STOPPED; old D1 retained as rollback. No runtime/deployment/instance/control binding edited. Root/D3RD/D3T own later source binding and live acceptance.
