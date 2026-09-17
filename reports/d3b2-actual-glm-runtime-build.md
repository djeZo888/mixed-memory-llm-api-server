# D3B2 — one reviewed actual GLM CUDA build retry

**PASS_BUILD_CLI_ENUMERATION_ONLY.** The one authorized build from reviewed
`c7155099e4d8d096b0e946352fbf01e3a9072ab9` completed successfully. Both version/help checks and the
separately authorized single GPU enumeration passed. No model, context, protocol,
model-kernel, fusion or allocated-workspace acceptance is claimed.

The immutable image contract was published before packaging at `../image-contract.md`;
its committed copy is [image-contract.md](d3b2-evidence/image-contract.md).
Final source binding belongs to D3RD under runtime ID `llama-cpp-v0.4.1-d3br`.
No runtime/deployment/instance/control files changed here. Installer stays STOPPED.

## Exact build and provenance

| Item | Measured identity |
| --- | --- |
| Run | `/data/build/d3p-d3b2-20260915` |
| Owner source commit | `c7155099e4d8d096b0e946352fbf01e3a9072ab9` |
| Upstream commit / source_revision | `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Clean upstream tree | `950999fe62b7fe55f44ab5b7394e3c8542f37f12` |
| Combined patch SHA256 | `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b` |
| Derived tree | `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e` |
| Derived commit | null; the derived identity is a tree |
| Image IID / OCI index | `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9` |
| Linux/amd64 manifest | `sha256:384a22a0b15b9668b89e4ec46ed7363f2bb02e91d3344db102411288551ef62b` |
| Image config | `sha256:89a1ea2575d8a5ea2c2debd618d420ac03194b1c2d54b85972a8ebff850f3938` |
| Tag | `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d` |
| RepoDigests | `["local/llama-cpp@sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9"]` |
| llama-server binary SHA256 | `c81262fd063e9d2fc098d9e116d0ae742ca7ea37344ee3f4b56eb5d088206e0a` |
| Host AND in-image recipe manifest SHA256 | `87b03d3c2ebd3b4369c6014ccd1ca7fcfb502747f7bee0b81036f7f99c9409bb` |
| Runtime proof SHA256 | `1d500eae56d6e777b944b2492071c8b3dd28ea350b04f5c72da5b7bd70d052c9` |

The IID is an OCI index digest, distinct from the platform manifest and image
config. All three were independently hashed from `docker image save` streamed
on the VM; no image archive/layers were copied to the orchestrator. Config bytes
remain at `evidence/image-config.json` on the VM; published identity is sanitized.
Both host and image six-file recipe manifests match the revised D3BR hashes.
The image reports `source_state:verified-patched`, the exact upstream commit,
patch and derived tree. OCI revision/revision-kind are derived tree/git-tree;
`source_revision` remains the upstream commit.

The owner repo came from a complete-history verified bundle, checked out at the
exact reviewed commit. The upstream context was cloned `--no-hardlinks
--no-checkout` from the existing D1 object store, then checked out only in the
new run. It has ordinary self-contained `.git`, no alternates, clean raw bytes,
index/modes and exact clean tree. Reviewed check-only helper checks passed before
and after build. The patch was applied once inside Docker to this clean context.
No failed source tree was reused or mutated. The unchanged recipe used jobs8,
`120a-real`, pinned CUDA13.2.1 bases and Ubuntu snapshot20260914T000000Z.

## Durable job and guards

- Unit: `d3b2-glm-cuda-build-20260915.service`; wrapper and independent launch MainPID both214914.
- Build started `2026-09-15T03:27:14Z`; finished `2026-09-15T03:30:27Z`.
- Ninja completed592/592; build.exit=0, job.exit=0; Restart=no and 12h bound.
- Final unit MainPID0/inactive/dead; successful transient unit was garbage-collected
  (`LoadState=not-found`). Synthetic defaults after collection do not replace
  the recorded launch properties in `unit-launch.txt`.
- Wrapper SHA256 `5017341a2cfd1efcc5fc7dcefe638a55438c2c686b33d41d8b05146a17d56f24`.
  Ordinary script `$$` fixed the old inline-systemd escaping issue. It passed
  VM `bash -n`, `--help` and independent read-only contract review.
- Full build log stays at `/data/build/d3p-d3b2-20260915/build.log`;
  final SHA256 `84bfcab71ee0a472770ba3b2f7409d57b90eaf4f7f77c4fb6877675d158d3118`.
- Runner statuses, PID, lock, recipe/source proof, temporary files and caches stay
  under this run. Docker/containerd roots remained `/data/docker` and
  `/data/containerd/root`; HOME remained `/home/user`.

Mandatory original D3 paths, file hashes, single-link files, root ownership and
protected nonsymlink ancestors passed before invocation and at close. Both actual
canonical guards passed preflight/postflight; the historical dirty checkout guard
was never called. The fixed registered guard and exact storage.py dependency
passed their source/protection checks, actual --root-guard, both UUIDs and the
unrounded root STOP threshold. Registered selection never fell back to legacy.

Exact UUIDs: data `8daf56f1-5649-4163-9d87-919c2d271875`; models
`a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Initial free root bytes5209165824;
final after enumeration/cleanup `5209092096`,
above4294967296. Existing warnings: root below6GiB, small historical bootstrap
checkout and pre-mount backup; no STOP or cleanup action.

Only the two approved top-level task directories were created:
run user:ai2770/inode44308488; registered report parent
`/data/logs/d3p-d3b2-20260915` root:root0700/inode47972510. Parents and failed D3B
owner/gid/mode/inodes were verified unchanged; `/data/build` remains
root:gid1001 mode2755/inode21757953 and `/data/logs` root:gid1000
mode2755/inode47972353. Runner root-build-before/after.json are root-owned0600
under the approved protected report parent.

## Measured CLI and GPU enumeration

Version output: `0.4.1-dev (build62, commit b29c606)`, GNU13.3.0/Linux x86_64.
CMake evidence verifies CUDA enabled, `120a-real`, Release, dynamic backends,
all CPU variants, and web UI/tests/examples/app disabled. nvcc/package outputs
and binary/source/recipe hashes are retained in the evidence.

Both uniquely named runc containers ran only --version or --help, with network
none, no ports, mounts or GPU exposure, and exited0. All16 baseline flags plus
`--n-cpu-moe` were measured. Load modes: auto, none, mmap, mlock, mmap+mlock, dio.
See `cli-provenance.json` and exact retained help/version outputs.

The direct orchestrator follow-up explicitly superseded the original no-GPU
restriction for ONE --list-devices probe. It used only the exact new image,
NVIDIA runtime visible devices0,1, compute/utility, no network/ports/model/key
mounts, and a30s timeout with5s termination escalation. It exited0 and reported:

- CUDA0: NVIDIA RTX PRO6000 Blackwell Workstation Edition.
- CUDA1: NVIDIA RTX PRO6000 Blackwell Workstation Edition.

GPU memory samples before/after were16856/16856MiB on GPU0 and12968/12968MiB on
GPU1; both deltas0MiB. Compute-process rows were unchanged. These are sampled
before/after observations, not continuous context tracking. CUDA initialization
and transient contexts are not excluded; no inference/model/kernel acceptance
is inferred. All3 verification containers were independently observed exited0,
removed by exact ID without force, and independently confirmed absent.

Original GLM container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`
remains running on `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`,
start `2026-09-15T00:48:45.235739944Z`, unchanged through final checks. No endpoint,
model request, load/restart, key/service/network/instance or control mutation.
No lifecycle/model lease was acquired. Failed D3B log/hash and caches preserved.

## Checks, warnings and next action

PASS: exact source/recipe/raw-byte gates; actual build; guard pre/post checks;
wrapper syntax/help; image digest chain; source/patch/tree and host/image recipe
agreement; binary/CMake/nvcc/package provenance; CLI16+N-CPU-MoE; one enumeration;
quiescent cleanup; original GLM and failed-run preservation. Verification commands
are in `verification-commands.md`. No local implementation/build/tests and no
installer suite were run. Local work is evidence/report/Git packaging only.

Metadata extraction caught and corrected three assumptions: helper emits
`verified-patched`; this Docker IID identifies an OCI index rather than config;
the help window also includes later options, so load modes were limited to the
six measured model-loading entries. No build or verification probe was replayed.
VM rg was unavailable; Python reads provided the bounded metadata inspection.

Root/D3RD should consume `proposed-runtime-fields.json` and `runtime-proof.json`
to bind the new sibling runtime while retaining D1 rollback. Root/D3T own later
model/context/kernel/protocol/fusion/workspace acceptance. No rebuild is needed
or authorized. Final author/committer, quiet secret scan, diff check and bundle
verification are recorded by the local packaging handoff. No push.

Raw evidence is preserved byte-for-byte. The measured help contains five
whitespace-only lines and CMakeCache has a final blank line; default Git
whitespace checking reports those original bytes. Authored files pass the
default check, and the two raw files pass with only those whitespace categories
disabled. Their provenance hashes remain unchanged. Inherited M3/next-M4 and
no-Docker-changes boilerplate in canonical guard output describes that guard
invocation, not this build milestone.
