# Sova project execution

## Current authorization: H018, 28 September 2026

The user resumed MiMo integration and authorized **up to two hours**. The new
foreground window is 23:38:03UTC27September–01:38:03UTC28September
(01:38–03:38 Ljubljana). This supersedes closed H017 execution holds, but does
not renew its expired client clocks. Read `docs/h018-mimo-integration-plan.md`,
the H017 results and local `orchestration/tasks/H018-20260928/STATUS.md`.

Use eight decode threads,64 batch threads and the already-verified MiMo Pro-RL
checkpoint/runtime. Root selects950,000 usable context under the user's explicit
permission to reduce1M slightly. Keep F16 cache, GOMP_SPINCOUNT=0, ordinary
CPU-expert allocation, external eight-node interleave and the selected GPU.
No new model download, runtime/dependency rebuild or thread sweep.

No optimized64K or near950K job has yet run. First reproduce and repair the swap
limit lifecycle defect with a small disposable no-GPU container. Review the
repair before paying for another model load. Preserve enforced zero owned swap;
do not treat Linux's `max` value as zero. Preinstall independent test units before
loading. Avoid system daemon-reload during model inference.

After genuine950K native tool and Sova delegation acceptance, the final task is
one independent systemd job: optimized64K followed by near950K only if64K passes.
Renew its dispatch authority once for H018; retain the eight-hour total background
cap. Aim application acceptance complete by01:15UTC, final dispatch by01:25UTC,
and reserve recovery/publication time before01:38:03. Close paid worker CLI
sessions after actual startup verification, keep automation paused, and wait
for the user's nudge. No paid polling while the long test runs.

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

H017 restored original GLM1,048,576 at20:45:14 and original Sova7143/9ef885 at
20:48:10. Existing observer reported all four instances ready at20:49:08.
MiMo is exactly settled. No optimized64K or near950K job started.
Eight threads measured9.20988outputtokens/s; four6.76392, so two was skipped.
Native4K/16K and genuine tool continuation passed at1,000,000 usable context.
R9 sampled VRAM89,770MiB/free7,481MiB and cgroup573.37GiB including file cache.
These are historical measured results, not proof of current availability.

H017 twice achieved actual950000 capacity and tiny text, then supervisorfailure.
The diagnostic attempt located ValueError at int(cg['memory.swap.max']), owner
line455. Exact nonnumeric value was omitted by numeric-only diagnostics. Owned
swap/OOM were zero; exact PID/cgroup/GPU/proxy settlement passed. Test dispatch
called systemctl daemon-reload immediately before failure. Moby issue51446
documents a possible zero-to-max reset; local causality remains unproven.
Next window: reproduce with a small disposable container, preserve swap limits
across reload, handle nonnumeric values without weakening zero-swap enforcement,
and preinstall test units before another model load. Reuse qualified artifacts;
do not replay historical benchmarks or change precision/runtime/threads. Never
adopt an unknown running owner or hotpatch its deadlines.

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
BMC/fan/ECC/driver/reboot/Proxmox work in H018. Existing manual server-GPU fans
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
