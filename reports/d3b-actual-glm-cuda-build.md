# D3B — one actual reviewed GLM CUDA build

**FAILED_PRECOMPILE_SOURCE_INDEX_CHECK. One authorized build attempted; no retry.**
The unchanged reviewed Docker recipe reached its checked source helper, then
indexed patch validation failed. Compilation never started. No image IID,
binary, CUDA SM120 proof, version/help result or supported-flags proof exists.
Installer remains stopped; no source, runtime/profile or Manager files changed.

## Exact source and run

| Item | Identity |
| --- | --- |
| Owner base | `48a982420561ad6d0189a710a228beb1e2838de7` |
| Clean upstream commit | `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Clean upstream tree | `950999fe62b7fe55f44ab5b7394e3c8542f37f12` |
| Combined patch SHA256 | `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b` |
| Verified prospective tree | `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e` |
| New VM run | `/data/build/d3p-d3b-20260915` |
| Run owner/mode/inode at creation | user:ai / 2770 / 44302940 |
| Transient unit | `d3b-glm-cuda-build-20260915.service` |
| Historical observed PIDs | main 202062; runner 202064; Docker 202548; buildx 202651 |
| Unit launch / exit (UTC) | 2026-09-15 02:58:36 / 02:58:50 |
| Docker build start / finish (UTC) | 2026-09-15 02:58:39 / 02:58:50 |
| Final state | unit failed; MainPID=0; runner exit=1; outer exit=1 |

The self-contained owner repository came from a verified complete-history
bundle. Clean upstream was cloned with `--no-hardlinks --no-checkout` from the
existing D1 source object store into this run, then checked out at the exact
upstream commit. Existing source was never changed. Before and after the attempt,
the fixed helper's check-only mode verified raw tracked bytes/modes, clean status
including ignored files, clean tree, ancestry, patch hash and prospective tree.
Patch application was attempted only inside the single Docker build; the host
source remains clean upstream. The successful temporary-index prospective-tree
checks are not claims that an image was built.

Exact reviewed invocation:

```sh
/data/build/d3p-d3b-20260915/repo/containers/llama-cpp/build-d3p-runtime.sh /data/build/d3p-d3b-20260915
```

The existing transient systemd launch pattern ran the invocation as user:ai,
with working directory at the run, stdout/stderr appended to `build.log`,
`TMPDIR=run/tmp`, bytecode disabled, Nice=10, TimeoutStopSec=120,
RuntimeMaxSec=12h and Restart=no. The detached job survived its launching SSH
session. The runner used its unchanged named context, pinned base digests,
Ubuntu snapshot `20260914T000000Z`, `120a-real`, and jobs8. No no-cache or prune
option was used. HOME was checked against its original value and unchanged.

All new VM source, temporary files, client cache and evidence remain in the run;
Docker and containerd used their existing `/data/docker` and
`/data/containerd/root` stores. The sole metadata correction was `job.pid`:
systemd transformed inline `$$` into a literal `$`; after completion this file
was corrected to historical MainPID 202062 from durable unit-launch evidence.
No process or recipe was restarted or edited.

## Guards and shared ownership

The mandatory canonical JSON is copied in `d3b-evidence/canonical-guards.json`.
Both exact protected D3 paths resolved without symlinks; files were root:root,
mode 0700, under protected root-owned ancestors. Both SHA256 values matched.
The supporting `require-data-mounted.sh` was checked separately. No historical
dirty checkout guard was used. Real canonical guards passed before run creation,
again with a report in the new run, and after the attempt. The unchanged runner
also passed its own before/after guards from its clean exact owner checkout.

Strict exact-mount checks passed for two distinct writable ext4 devices:

- `/data`: `8daf56f1-5649-4163-9d87-919c2d271875`.
- `/data/models-large`: `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`.
- Root free bytes: 5,210,423,296 before; 5,210,308,608 at post-build dual-mount
  check; 5,210,214,400 at closing guard. The unrounded STOP threshold was 4 GiB.
- Warnings: root below the 6 GiB warning threshold; existing small bootstrap
  checkout and pre-mount backup. No guard STOP or cleanup occurred.

`/etc/local-ai-server` was absent immediately before launch. The actual Docker
child was observed after the entry refusal check. The build failed within
seconds during the early ownership handoff; the terminal handoff superseded
the short-lived active status. `../ownership-release.md` releases all further
direct-child creation under `/data/build`, `/data/hf-cache`, `/data/backups`,
and `/data/logs`. Root acknowledged relaying this release to L2VM. D3B requires
only its existing run now. L2VM may make its approved nonrecursive owner changes,
preserving gids/setgid/content/inodes, and create its registration parent.
D3B did not mutate registry state or those roots' ownership.

## Failure evidence and narrow diagnosis

Docker completed COPY of the clean source and named recipe context. Build stage
7/7 failed in the helper's indexed-apply phase for `src/llama-context.cpp` and
`tools/server/server.cpp`, classified by Git as worktree/index mismatch.
The existing log records this at lines 191-192. Full log stays on `/data`; its
SHA256 is `5d4d1867c1d40b5d1964d89832fd700f543f8c31b91fd910e32d4a71604f0616`.
Committed evidence contains safe metadata/hashes, not raw build-log bodies.

Exact helper observations at the owner base:

- Line 33 forces `GIT_OPTIONAL_LOCKS=0`; lines 37-38 disable fsmonitor and
  untracked cache.
- Lines 117-123 check clean status, ordinary index entries, cached diff and all
  raw tracked bytes/modes.
- Lines 138-142 prove the prospective patched tree in a temporary index.
- Lines 146-147 perform `apply --check --index` and `apply --index`. The emitted
  error does not distinguish those two calls. There is no explicit stat-cache
  refresh between verification and indexed apply.
- By source control flow, reaching indexed apply implies the preceding
  in-container verification passed. This is an inference from the checked code
  and failure position, not an exported measurement of failed-layer stat tuples.
- Post-failure host measurements show clean status and identical worktree/index
  bytes for both files; file hashes, modes and host stat tuples are recorded in
  `d3b-evidence/host-source.metadata.json`. Failed-layer stat tuples were not
  extracted, and no extra Docker build/container was created for diagnosis.

A bounded worker-only Git fixture independently reproduced the suspected
mechanism using Apple Git 2.54.0 and the helper's Git options/environment:

| Check | Exit/result |
| --- | --- |
| Copied identical bytes, clean status and cached diff | 0 / clean |
| Indexed patch check before explicit refresh | 1 |
| Explicit `git update-index --refresh` | 0 |
| Same indexed patch check after refresh | 0 |
| Tree/content before and after refresh | unchanged |
| Actually changed-file control: refresh / apply check | 1 / 1 |

Safe command/exit/output-hash metadata is in `git-stat-reproduction.metadata.json`
and `git-stat-refresh.metadata.json`. This supports the hypothesis that Docker
COPY invalidated cached file metadata and optional-lock suppression prevented
status from persisting a refresh. It does not establish the exact Linux
failed-layer cause. No general audit, native patch edit or VM retry was done.

## Result and next reviewed seam

The original GLM container
`bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`
was observed running after the attempt on original image
`sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`,
with start time 2026-09-15T00:48:45.235739944Z. D3B did not restart, load,
generate, call inference endpoints, request GPU access, change networks/services,
use a real key, or modify any existing container. V3's generation lease remains
outside this task. D1 recipe/image/rollback were untouched; caches/partials remain.

Root's smallest source follow-up to review is an explicit stat-cache refresh
after existing raw-byte/mode/clean checks and before real indexed apply, confined
to apply mode. Preserve check-only immutability, every source/hash/tree check,
and rejection of genuinely changed bytes/modes. A copied-stat reproduction plus
negative controls must qualify that correction. It is proposed, not implemented.

Before another build, root must also resolve the registered-host runner contract:
the current exact runner must refuse at ENTRY if the registration parent exists.
Do not remove it, bypass it, reuse this failed run as an automatic retry, or invoke
an installer. A new reviewed source/guard integration and explicit build
authorization are required. This task's one-build authorization is consumed.

Proposed future image/proof fields, with no active binding made:

- Tag: `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d`.
- `image_id`: **null** (tag and IID file measured absent).
- `source_kind`: `upstream-plus-checked-patch`; `revision_kind`: `git-tree`.
- `upstream_commit`, `patch_sha256`, `derived_tree`: exact table values above.
- Future OCI revision must be the derived **tree**, not an invented commit.
- Required future measured fields: IID, labels, image/binary hashes, exported
  source/recipe proof, CMakeCache `120a-real`/CUDA flags, nvcc version, packages,
  actual `--version`, `--help` and supported flags. Use only owned no-model,
  no-network containers with no ports or GPU request for help/version.
- Runtime/profile binding remains a separate source review. Model protocol gate,
  actual diagnostic graph allocation and GPU/kernel qualification remain live
  work later; a build/help result alone cannot prove them.

## Verification and handoff

Checks run: exact Git/base and source pins; clean/raw-byte pre/post helper checks;
canonical guard path/owner/hash checks; real before/after guards; strict dual UUID
and root-byte checks; actual single durable Docker attempt; final unit/exit/log
metadata; absent new tag/IID; original container identity/state; bounded worker
stat fixture including changed-byte control. Build FAIL; storage and bounded
diagnostic checks PASS. No installer tests or implementation changes.

For read-only continuation, inspect the existing unit with `systemctl show` and
the run's `build.state`, `build.exit`, `job.exit`, `evidence/result.metadata.json`
and `build.log` through the `ai-vm` SSH alias. Do not rerun the build command.
Local report/evidence verification uses `git diff --cached --check`, JSON parsing,
recipe SHA256 comparison to the unchanged files, a credential-pattern scan,
author/committer inspection and `git bundle verify ../D3B.bundle`.
Root coordination acknowledged the terminal release and then launched D3BR as a
separate source-only correction task; this report does not duplicate that work.
The final external handoff records the report commit and bundle hash. No push.
