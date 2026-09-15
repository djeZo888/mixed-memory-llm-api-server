# D3BR — checked build-source corrections

Status: PASS_SOURCE_AND_FOCUSED_WORKER_CHECKS; actual Linux build NOT_TESTED.
Base: `ec747134615f4f1d86cf455016aadc166d44be50`.
Source-only mac-worker1 task. Installer PAUSED. No VM access, Docker recipe
build, CUDA/native compile, image, model load, request, service action or restart.

## Historical failure retained

The supplied [D3B build contract](d3br-evidence/d3b-build-contract.md) and
[ownership release](d3br-evidence/d3b-ownership-release.md) are preserved verbatim.
The authorized build ran 2026-09-15 02:58:39–02:58:50Z and failed before compile
in the Docker COPY context. `git apply --check --index` reported index mismatch
for `src/llama-context.cpp` and `tools/server/server.cpp`. Host clean pin/tree and
raw-byte checks had passed. No new IID was produced. There is no retry here.

A copied index stat cache is a candidate explanation for that measured failure.
D3BR reproduces this mechanism locally with a fixture Git repository; it does
not establish the actual cause inside the failed Docker layer.

## Helper correction and reproduction

The sole production helper change adds explicit `git update-index --refresh`
inside APPLY only, after clean pin/tree/status, ordinary index flags, cached
index/HEAD agreement, raw blob/executable-mode checks, patch SHA256, and the
scratch-index prospective derived-tree check. `GIT_OPTIONAL_LOCKS=0` stays in
force. The existing `apply --check --index`, `apply --index`, final tree,
raw-byte/mode and unexpected-file gates remain. No repair by reset/checkout,
patch rewrite, index-check bypass, model or native-source change was added.

The focused regression copies a complete real fixture checkout, including
`.git`, with `shutil.copytree(..., copy_function=shutil.copy2)`. It asserts the
copied index bytes are identical and the tracked file inode differs. Check-only
passes without changing any checkout/index/object file bytes or modes. The
original first APPLY subprocess then fails with the exact observed error form:
`sample.txt: does not match index`. Corrected full APPLY succeeds and matches the
fixture's exact derived tree, while HEAD remains the pinned base commit.
A second regression alters only tracked-file mtime by two seconds and proves
the same failure and corrected success. These use real Git calls, not mocked
Git failures. Both new regressions also failed against the unmodified helper
before the production edit and passed afterward.

The [baseline reproduction transcript](d3br-evidence/baseline-reproduction.txt)
also reruns both current regressions against the unmodified integration helper
(SHA256 `e465b44113a097502c7cffb763c251095986a10fdcd5f130c2d362c2a8c03664`).
To reproduce that expected failing baseline on the worker:

```sh
d3br_repro=$(mktemp -d)
git show ec747134615f4f1d86cf455016aadc166d44be50:containers/llama-cpp/prepare-d3p-source.py > "$d3br_repro/prepare-d3p-source.py"
cp containers/llama-cpp/test_d3p_source.py "$d3br_repro/test_d3p_source.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$d3br_repro/test_d3p_source.py" \
  SourceTests.test_copied_checkout_reproduces_original_index_failure_then_applies \
  SourceTests.test_stat_invalidated_checkout_reproduces_original_index_failure_then_applies
# Expected: exit 1, two real Git index-mismatch errors. No Docker invocation.
```

Same-size raw-content tampering is deliberately hidden from status by retaining
mtime/size and minimizing stat checks; the independent raw-blob check still
refuses before refresh. Copied mode, index, patch SHA, hidden-entry and wrong
prospective-tree cases likewise refuse before refresh and preserve their
pre-attempt byte/mode snapshots. Check-only still uses only scratch index and
objects. No timestamp-invariance claim is made for Git reads.

## Existing registered-host runner seam

The [early runner contract](d3br-evidence/runner-contract.md) names exact source
ownership, reviewed protected closure hashes, the actual loader and writer,
report placement, and later operator prerequisites. It was also published at
`../runner-contract.md` before runner edits for L2VM coordination.

Once the registration parent exists, the runner selects and latches the actual
protected registered guard, failing closed if registration is missing, invalid
or disappears between guard invocations. It verifies both required installed source files and their
root-owned protected ancestors before isolated Python invocation under sudo.
The guard owns registry/mount verification and its existing constrained report
writer. The runner accepts only the current-host verified `/data`, separate
`/data/models-large`, and `/data/logs` layout. It adds no override flags, new
loader, storage policy, writer, job, supervisor or receipt framework.

Registered reports use `/data/logs/<run basename>/root-build-{before,after}.json`.
The later VM task must create this one approved directory root-owned mode 0700;
this runner does not create it. Reports use the existing guard writer after
verified storage. Legacy parent-absent guards and report paths stay valid.
Root's supplied [canonical D3 guards](d3br-evidence/canonical-external-guards.json)
remain required external preflight and postflight; registered verification is
additional. A missing protected dependency stops instead of importing a dirty
checkout or triggering a reinstall.

Review identified one inherited guard limit: `registered-storage.py` requires
registration on bootstrap, while the subsequent `Storage.verify` reread permits
absence for its general full-role API. Removal by a concurrent root operation
inside that one guard invocation is therefore not an atomic-registration
guarantee. The runner adds no legacy fallback and refuses disappearance on its
next invocation. This externally owned guard behavior is recorded for root/L2
review; no guard, loader, writer or installer source was changed to address it.

The exact model-free Docker build command, source/run guards, no-existing-IID
check, build pins, 8 jobs, `120a-real`, named context, CUDA bases/snapshot,
Docker/containerd data roots, source helper/hash/tree verification and HOME
behavior are preserved. Build files stay under the existing `/data/build/d3p-*`
run. No L2/L2VM-owned source or installer files were modified.

## Provenance and acceptance boundary

The combined patch remains SHA256
`43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b`;
its declared derived tree remains
`0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`.
D3P/D3PD reports and recipe hashes remain historical evidence, unchanged.
D3BR provenance records the revised helper/runner hashes separately. A later
build must bind these revised files in both host recipe evidence and the image's
`/opt/llama/build-recipe-sha256.txt`; old D3PD hashes are not new build proof.

Actual Linux registered guard/runtime integration and the Docker recipe build
are **NOT_TESTED** here. No new IID, binary or runtime proof is claimed. Root
must review this source, test evidence, protected closure and task report path
before authorizing ONE later actual build retry. Preserve the failed D3B run,
its partials/caches and the existing D1/GLM runtime.

## Focused verification

Worker: Darwin arm64, Git 2.54.0 (Apple Git-157), Python 3.14.7.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 containers/llama-cpp/test_d3p_source.py
PYTHONDONTWRITEBYTECODE=1 python3 containers/llama-cpp/test_d3p_runner.py
bash -n containers/llama-cpp/build-d3p-runtime.sh
git diff --check
```

| Check | Result / evidence |
| --- | --- |
| Original helper copied/stat-invalidated regressions | PASS: two expected original index-mismatch failures; `d3br-evidence/baseline-reproduction.txt` |
| Corrected helper and recipe | PASS: 26 tests; `d3br-evidence/helper-tests.txt` |
| Runner fixture and writer-interface checks | PASS: 22 shell fixtures + 4 mock-interface tests; `d3br-evidence/runner-tests.txt` |
| Exact Docker command, recipe/pins, native patch and manifest preservation | PASS: `d3br-evidence/preservation.txt` |
| Protected guard source dependency hashes | PASS against reviewed L2 source; installed files NOT_TESTED |
| Shell syntax / CLI help | PASS in helper/recipe suite |
| Author/committer, scope, local secret scan, diff check | PASS: `d3br-evidence/repository-checks.txt` |
| Actual Linux registered runtime and Docker recipe build | NOT_TESTED; later authorized task only |

The runner suite uses a temporary translated source copy and fake commands for
Linux metadata, sudo, Docker, Git preflight and registered-guard responses.
Its simplified fixture registry tests shell branch selection and failure
propagation, not the real mount/schema verifier. Real shell source checks,
closure file hashes/modes/links, fixed build arguments and report placement are
exercised. Four direct calls to the existing guard's report function use a mock
Storage interface; no Storage operation, installation flow, privileged write or
installer suite is executed. HOME remains unchanged in the runner subprocesses.
