# Sova project execution

## Current authorization: H017, 27 September 2026

The user resumed MiMo integration with a **two-hour foreground limit**:
19:07:11–21:07:11UTC (21:07–23:07 Ljubljana). This supersedes the closed H016
window and old holds. Read `docs/h017-mimo-final-integration.md` and local
`orchestration/tasks/H017-20260927/STATUS.md`.

Use eight decode threads,64 batch threads and the already-verified MiMo Pro-RL
checkpoint/runtime. Root selects950,000 usable context under the user's explicit
permission to reduce1M slightly. Keep F16 cache, GOMP_SPINCOUNT=0, ordinary
CPU-expert allocation, external eight-node interleave and the selected GPU.
No new model download, runtime/dependency rebuild or thread sweep.

The last task is a finite independent Linuxsystemd job: optimized64K first,
then near950K only if64K passes. Reserve output/template space within the actual
usable slot. Launch only after real persistent-service and Sova delegation
acceptance. Verify startup, close paid worker sessions, keep automation paused
and wait for the user's later nudge. No paid polling of the long test. The
existing eight-hour background-test cap is separate from the two-hour foreground
window; neither may silently extend.

## Roles and execution

Mac-Orchestrator plans, coordinates, reviews and publishes. Implementation,
builds, tests and VM operations run through mac-worker1/mac-worker2 in fresh
bounded native Codex CLI sessions and isolated copies. Retain session IDs and
compact durable records. Worker1 owns ai-vm, Worker2 owns ai-harness and
independent acceptance. Coordinate shared mutations and model inference.
Root may edit planning/reports and synchronize reviewed Git artifacts.

Sova downtime is authorized during integration. Preserve chats, files, job
records, quarantines and rollback artifacts. Two Qwen480K instances plus the
image model remain on their GPUs. GLM1,048,576 is the working rollback.

## Starting state and evidence

H016 ended with GLM and original Sova7143/9ef885 restored and all four instances
ready. MiMo is exactly settled. No optimized64K or near1M job started.
Eight threads measured9.20988outputtokens/s; four6.76392, so two was skipped.
Native4K/16K and genuine tool continuation passed at1,000,000 usable context.
R9 sampled VRAM89,770MiB/free7,481MiB and cgroup573.37GiB including file cache.
These are historical measured results, not proof of current availability.

The ordinary MiMo supervisor failed before its proxy started. Cleanup's
LeaseBusy/TimeoutExpired may have masked the primary error; cause is UNKNOWN.
A later node lock holder is not proof of that historical cause. Start with
retained evidence, offline readiness validation and narrow primary-error/
settlement corrections. Reuse qualified artifacts; avoid replaying completed
benchmarks. Never adopt an unknown running owner or hotpatch its deadlines.

## Runtime and request ownership

Distinguish configured capacity, actual occupied tokens, allocation, native
acceptance and application acceptance. Preserve exact model/runtime/tokenizer/
quantization identity. No aliases that disguise model changes. Qwen remains
the coordinator and usual coding worker; MiMo becomes the selective frontier
after actual acceptance. Keep logical models separate from model instances.

Use independent Linuxsystemd jobs for live clients. Never interrupt a CLI that
owns a foreground request. Preserve terminal SSE, usage, DONE, full HTTP drain
and native settlement; socket closure alone is not GPU cancellation. No
automatic replay of uncertain requests. Positive local busy rejection must be
distinguished from upstream errors. A later caller cannot become our request.

Avoid per-token lifecycle locks, full storage scans, receipt rewrites or fsync.
Heavy checks belong at boundaries; periodic telemetry must stay bounded.
Report input processing, output generation and total latency separately.

## Storage, hardware and recovery

Use installed registered-storage/root-disk guards and protected
`/etc/local-ai-server/storage.json` authority. Verify registered UUIDs, mounts,
roots and operation paths before/after authorized data writes. Keep models,
cache, builds, container storage and logs under registered /data roots. No
stale-checkout guard fallback or environment identity override.

Reuse canonical `/run/llmctl/lifecycle.lock`; nested operations borrow the
validated lease. Never replace/unlink the lock or bypass ownership. Exact
settlement must prove native PID/cgroup/GPU release before changing selection.
Preserve primary and cleanup failures separately and retain genuine request
ambiguity. Cleanup failure without a request is not proof of an active request.

Retain7% free frontier VRAM,15% available host memory, Qwen16GiB and Ada5%
reserves; stop on owned swap/OOM or85C/the lower hardware limit. Aggregate host
swap changes are not proof that MiMo swapped: the H017 load stopped on that
comparison despite owned swap0 and about652GiB host available. Diagnose the
actual delta; a reviewed narrow correction may retain host swap as telemetry
while keeping zero owned swap, zero OOM and the15% available-memory floor.
No four-way
stress before improved physical cooling and separate user authorization. No
BMC/fan/ECC/driver/reboot/Proxmox work in H017. Existing manual server-GPU fans
remain unchanged. Installer work remains paused.

## Publication and continuity

Use scoped branches and reviewable commits; no direct main push. Run a scoped
secret scan and diff/whitespace review before publication. Never commit tokens,
credentials, private keys, model weights or bulky traces. Protected credential
files remain outside repositories and task containers. Preserve exact user data
and previous releases; no global prune, unrelated cleanup or token regeneration.

Current root review branch is feature/glm53-flash; PR10 remains draft until
its scope is genuinely accepted. Keep results/status/next steps in project files.
Record missing tests honestly at the time limit and recover the last working
service if the new one is not qualified. Do not infer permission extensions.

Historical instructions are archived in `docs/orchestration/AGENTS-H016-archive.md`
and Git. They are evidence, not competing instructions for this window.
