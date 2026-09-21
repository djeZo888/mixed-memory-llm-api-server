# ai-vm operations

**Live production acceptance PASS — 2026-09-21, 03:21 UTC**, installed source
`04143b18cca7aca724d9a4a4bcf943fe86c040db`. The [saved receipt summary](../reports/dualq-480k-20260921.md#dated-production-acceptance--2026-09-21)
records dual Qwen warm/ready, native 480,000 each and persisted running/resume
intent on the 72-vCPU guest. Private API, GPU0 mode switching, preserved Q1,
control restart and warm replay passed. This is a dated snapshot, not a new
live observation by CLOSE.

## Modes and normal control

Default `dual-qwen` runs Qwen on GPU0 and GPU1; optional `glm-qwen` replaces
GPU0 with GLM and retains GPU1 Qwen. Return explicitly to GPU0 Qwen. All three
profiles configure 480,000 tokens on 72 guest CPUs. Both Qwen masks are 0–7;
GLM uses 0–71, sharing Qwen's eight CPUs. Masks do not prove exclusive cores,
physical host pinning or minimum core needs. Exact IDs/aliases/ports are in the
[model matrix](model-matrix.md) and [API guide](ai-vm-api-operations.md).

Use authenticated catalog/status, a targeted mutation with fresh target-slot
identity/generation, then poll the returned operation and rediscover. Every
running-target switch/restart requires `allow_interrupt:true`. `mutation_busy`
is independent of unknown inference activity. Ready does not mean idle. The
future harness owns dispatch, backlog and drain; the server cannot atomically
fence direct requests. A target transition must preserve the peer's identity;
partial failure retains recovery ownership rather than silently replacing it.

## Durable service ownership

The source uses ai-vm's protected `llm-control.service`, existing private TCP
transport services and the single `llmctl-boot.service` lifecycle owner.
Production has no Worker1, SSH or benchmark-keeper process dependency. Docker
restart stays `no`; operators must not use it as a second boot owner.

Canonical boot-start replays only selected slots with desired running and
`boot_policy:"resume"`, GPU1 (`qwen`) first, then GPU0 (`glm`). Boot-stop
preserves desired intent. Explicit API stop persists stopped intent; switching
preserves the target's saved boot policy. Final evidence records both installed
policies as `resume`, all five units enabled/active, and control restart plus
idempotent replay on the already-ready pair without container identity changes.
Activation SSH exited before fresh clients received correct Q0/Q1 answers.
**Hardware boot, cold-boot replay and live full rollback remain NOT_TESTED.**

## Storage and recovery

The protected `/etc/local-ai-server/storage.json` is storage authority. Verify
registered UUIDs, mounts, roots, protected ancestry and operation paths with the
current root-reviewed installed registered-storage/root-disk guards before and
after authorized writes. Directory existence and historical checkout helpers
are insufficient. Models and caches remain on registered model storage; Docker,
containerd, logs and service data remain in their registered `/data` roots.

All lifecycle mutations borrow the canonical `/run/llmctl/lifecycle.lock` lease.
Preserve per-slot identities, protected credentials, desired intent, pending
creates, emergency journal and the immutable pre-migration source/state/boot
backup. A create marked uncertain is not cleared by an empty inventory.
Failed/partial stops retain ownership until exact absence is proven.

Use the [reviewed migration and rollback contract](concurrent-api.md) for an
explicitly authorized recovery. `rollback-check` is a prerequisite observation,
not rollback or deletion authority. No automatic rollback, global prune,
unrelated cleanup or benchmark-container adoption is allowed. Preserve the D1
rollback runtime/image and recovery evidence.

## Evidence boundary

GPU0 switch operations took 255.585590 s to GLM / 120.568066 s back to Qwen,
excluding pre-admission/status overhead. Final status/catalog latency was
20.994856 / 25.000605 s; these administrative reads inform polling cadence.
The 60/60 s production budgets, generic 10 s defaults, HTTP 130 s and client
140 s bounds remain as documented in the [API guide](ai-vm-api-operations.md).
Routine exact stopped-container and writable-directory corrections plus the
reviewed control-budget fix are retained in the activation receipt. No further
VM changes or retests were needed for this closeout.

The [dual-Q benchmark](../reports/dualq-480k-20260921.md) restored its captured
STOPPED/manual state; this does not describe current production. Its singleton
restoration owner refuses migrated schema 3 even if both slots are stopped.
Do not rerun it against pair production without separate reviewed ownership.

Historical [stage-one status](../reports/stage1-ai-vm-status.md),
[cleanup](../reports/finalops-reboot-cleanup.md) and
[installer records](installation.md) are retained evidence, not instructions to
resume old installer commands. Frontend work is separate; **all installer work
and tests remain paused**.
