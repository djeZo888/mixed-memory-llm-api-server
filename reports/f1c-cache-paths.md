# F1C — fixed pinned-SGLang cache paths

Status: **PASS_SOURCE; actual-image cache/auth fixtures NOT_TESTED**.
Base: `516e4cb52aa2672cf140b687d237b8fa832f6899`.
Branch: `milestone/f1c-sglang-cache-paths`.

## Change and scope

The reviewed runtime now explicitly sets the five source-verified paths below.
The launcher requires all nine fixed cache values, including the four existing
HF/XDG/Triton/TorchInductor values. Missing, empty or altered values fail before
native SGLang imports and key access. Validation never supplies missing values.

| Variable | Required value |
| --- | --- |
| `SGLANG_DG_CACHE_DIR` | `/cache/deep_gemm` |
| `SGLANG_CACHE_DIR` | `/cache/sglang` |
| `FLASHINFER_WORKSPACE_BASE` | `/cache/flashinfer` |
| `CUDA_CACHE_PATH` | `/cache/cuda` |
| `TORCH_EXTENSIONS_DIR` | `/cache/torch_extensions` |
| `HF_HOME` | `/cache/huggingface` |
| `XDG_CACHE_HOME` | `/cache` |
| `TRITON_CACHE_DIR` | `/cache/triton` |
| `TORCHINDUCTOR_CACHE_DIR` | `/cache/torchinductor` |

The runtime also retains `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and
`DISABLE_OPENAPI_DOC=1`. HOME is neither added nor changed. Only the two named
SGLang cache settings join the exact-name/exact-value allowlist; unknown or
altered SGLang controls/plugins remain rejected. Exact optional public build
metadata retains F1E's absent/subset/full semantics and byte-for-byte checks.

The standalone launcher cannot depend on the repository at deployment, so its
cache literal is checked against an independent expected contract, runtime JSON
and `qwen_next.ENVIRONMENT`. Production edits to qwen_next are limited to that
literal; runtime JSON edits are limited to its environment map. Manager, path
bindings, leases, installers, deployment instances and `run_pinned_image.py`
are unchanged. Existing auth tests received only explicit valid cache setup;
their assertions remain intact. F1E2 owns the actual-auth helper/caller seam.

The exact required environment and frozen helper CLI were published early in
task sibling `../cache-env-handshake.md`. The actual-auth **caller must pass the
reviewed runtime environment**; the helper must still reject misconfiguration.
F1C does not repair missing actual-auth caller values by injecting defaults.

## Source provenance and limits

[Machine-readable evidence](f1c-cache-source-evidence.json) records versions,
paths, line references and SHA256s. Image identity remains
`sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`.
F1A actual-image evidence records SGLang `0.5.14`, Torch `2.11.0+cu130`,
FlashInfer `0.6.12`, Transformers `5.8.1` and the three non-SGLang names in its
tiny-kernel command. F1D's retained report records the unresolved cache concern;
F1E supplies the current build-metadata validator. Their historical runtime
results do not prove this revision.

- Retained installed `/sgl-workspace/sglang/python/sglang/srt/environ.py` has
  SHA256 `f8a56f1f4b56332b54bee2aaaa81237018e09e208ecd49dc0f59e15f95cdb743`,
  reverified against F1A. Lines 557/894 declare the two SGLang paths; native
  `envs.<name>.get()` reads their exact names. No HOME redirection is needed.
- [FlashInfer's pinned resolver](https://github.com/flashinfer-ai/flashinfer/blob/d768c14e7cf5dd5df45a8a1de78ae815879f108a/flashinfer/jit/env.py#L51)
  appends `.cache/flashinfer` to the configured base, then version/architecture
  workspace children and `cached_ops`/`generated`. These stay beneath
  `/cache/flashinfer`; AOT/CUBIN installed package resources are separate.
  `jit/env.py` SHA256:
  `09d2e6d6d03770d765acb8d89db2b58cd9600babacf6fbaad9dde0002a7d2cb9`.
- [PyTorch's pinned resolver](https://github.com/pytorch/pytorch/blob/70d99e998b4955e0049d13a98d77ae1b14db1f45/torch/utils/cpp_extension.py#L2670)
  reads `TORCH_EXTENSIONS_DIR` and creates its named build-directory child.
  `utils/cpp_extension.py` SHA256:
  `1517eb2ac276065210d7c861becc5bf3a5404796da16d35af9b9466667fef904`.
- [CUDA 13.0's environment reference](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-c-programming-guide/index.html#cuda-environment-variables)
  documents `CUDA_CACHE_PATH` as the JIT binary cache folder. No Python resolver
  or filesystem-only check proves the CUDA driver's use of it.

FlashInfer/PyTorch sources were retrieved on the worker from their exact release
tags and verified against immutable commit URLs. They were not present in the
retained F1A source set. **Installed-image byte agreement is NOT_TESTED**; the
deferred helper fails if these source hashes differ. No SSH/container inspection
was necessary, and no ephemeral source-inspection container was created.

## Deferred actual-image helper

[check_cache_paths.py](../tests/lifecycle/sglang_fixture/check_cache_paths.py)
has one actual-mode interface:

```text
python3 /fixture/tests/lifecycle/sglang_fixture/check_cache_paths.py --actual-image --repo /fixture
```

It checks read-only root/checkout, empty private cache/tmp mounts, no GPU device,
reviewed environment, launcher hash, installed package versions and resolver
source bytes before real resolver imports. No AST or framework fallback exists.
It checks native module paths/versions and every returned writable cache path,
then performs bounded create/fsync/read/remove using directory descriptors and
no-follow/exclusive file creation. It removes only its own matching file inode;
it performs no recursive or global cleanup. Created cache directories and native
FlashInfer log files live only in the private tmpfs until container removal.

FlashInfer import itself creates its workspace/log; Torch's directory resolver
also creates a child. Preflight therefore precedes imports. Helper-written
probe files remain inside validated resolved directories. Existing HF/XDG/
Triton/Inductor paths and CUDA are configured-directory filesystem checks;
SGLang/FlashInfer/Torch extension paths use native resolvers. Successful output
is deliberately named `PASS_RESOLVERS_AND_FILESYSTEM_ONLY`. No kernel,
compilation, model, server, key or actual-auth execution is part of this helper.

### Exact deferred operator command — NOT EXECUTED

Root must review/merge first and coordinate execution with D3. Use a verified
checkout of the merged revision at the exact path below, already staged by its
owner. This command reads the reviewed runtime JSON for every production env
entry; it adds only Python/tmp fixture settings. It does not override HOME.
No source preparation, service mutation or key/model mount is implicit here.

```bash
set -euo pipefail
reviewed_repo=/data/build/f1c-cache-20260915/reviewed-source
"$reviewed_repo/scripts/common/require-data-mounted.sh"
"$reviewed_repo/scripts/common/root-disk-guard.sh" --report /data/logs/f1c-cache-pre.md
python3 - <<'PY'
import json
from pathlib import Path
import subprocess

repo = Path('/data/build/f1c-cache-20260915/reviewed-source')
runtime = json.loads((repo / 'configs/runtimes/sglang-qwen-next-0.5.14.json').read_text())
image = 'sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3'
assert runtime['image_id'] == image
observed = subprocess.check_output(
    ['sudo', '-n', 'docker', 'image', 'inspect', '--format', '{{.Id}}', image], text=True).strip()
assert observed == image
args = ['sudo', '-n', 'timeout', '--signal=TERM', '--kill-after=10s', '180s',
        'docker', 'run', '--rm', '--name', 'f1c-reviewed-cache-proof',
        '--pull', 'never', '--runtime', 'runc', '--network', 'none', '--read-only',
        '--user', '0:0', '--log-driver', 'none', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--pids-limit', '128',
        '--memory', '4g', '--cpus', '2', '--stop-timeout', '5',
        '--mount', f'type=bind,src={repo},dst=/fixture,readonly',
        '--tmpfs', '/cache:rw,nosuid,nodev,noexec,size=128m,mode=0700',
        '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m,mode=0700',
        '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'TMPDIR=/tmp']
for name, value in sorted(runtime['environment'].items()):
    args += ['--env', name + '=' + value]
args += ['--entrypoint', 'python3', image,
         '/fixture/tests/lifecycle/sglang_fixture/check_cache_paths.py',
         '--actual-image', '--repo', '/fixture']
result = subprocess.run(args, check=False)
# Run post-guards even if the fixture refuses imports/resolvers or times out.
subprocess.run([str(repo / 'scripts/common/require-data-mounted.sh')], check=True)
subprocess.run([str(repo / 'scripts/common/root-disk-guard.sh'), '--report',
                '/data/logs/f1c-cache-post.md'], check=True)
raise SystemExit(result.returncode)
PY
```

Record the reviewed commit, helper/launcher hashes, exact image ID, stdout and
exit status. A timeout or failure remains FAIL; inspect only the named fixture
container under D3/root ownership if cleanup is needed. Do not remove unrelated
containers or clear caches. Source mismatch needs source review, not a bypass.
This command supplies no inference/auth approval.

## Worker checks, warnings and next action

Final check counts and hashes are in
[worker validation](f1c-worker-validation.json) and
[helper provenance](f1c-cache-helper-provenance.json).

```bash
python3 -m unittest discover -s tests/lifecycle -p 'test_sglang_cache*.py' -q
python3 -m unittest discover -s tests/lifecycle -p 'test_sglang_file_auth.py' -q
python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -q
bash tests/shell/test-llmctl-lifecycle-static.sh
bash tests/shell/test-llmctl-lifecycle-fixtures.sh
python3 tests/lifecycle/sglang_fixture/check_cache_paths.py --help
git diff --check
```

All cache/auth/GPU/model actual-image results for this revision remain
**NOT_TESTED**. Root reviews this source and merges the independent F1E2 caller
and auth coverage before any actual cache/auth fixture. D3 continues independently;
F1C performed no VM work and imposes no GLM hold. The bundle, commit attribution,
secret scan and final handoff are recorded in task sibling `../handoff.md`.
