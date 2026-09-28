# Sova project execution — H019

## Current user authorization

The user authorized another two-hour foreground window, September 28 2026
02:10:29–04:10:29 UTC (04:10–06:10 Ljubljana). Finish MiMo integration using
both Mac workers. Root plans, coordinates, reviews and publishes; workers do
implementation, builds, tests and VM operations through fresh bounded native
Codex CLI sessions over SSH in isolated working copies. Preserve session IDs,
compact checkpoints and reusable artifacts. Avoid paid sessions waiting idle.

The user explicitly changed two earlier requirements:
- Keep MiMo selected/resident at the deadline; do NOT swap it back to GLM.
  Sova may remain down. A real hardware/resource fault still requires stopping
  affected work safely; do not keep a failing GPU workload alive or load GLM.
- Skip the unrun optimized 64K benchmark. The final independent test goes
  directly to near-950K input in the 950,000-token window.

Read docs/h018-mimo-integration-results.md and docs/h019-mimo-finalization-plan.md.
H018 records and client clocks are historical. Do not repeat completed model
hashing/downloads, native builds, 4K/16K benchmarks, thread tuning, or the passed
GLM million-token benchmark. Retain the verified MiMo Pro-RL MXFP4/BF16/F32
checkpoint/runtime, eight decode threads, 64 batch threads, F16 KV, 950K context,
GOMP_SPINCOUNT=0 and all-node memory interleave.

## Execution and acceptance

Deploy the reviewed periodic health-write fix; repair the demonstrated nested
lease issue narrowly. First measure health-proof freshness and canonical-lock
hold time before another expensive model load. Stage independent test clients
before loading. No full filesystem scans in periodic health writes. Preserve
heavy storage checks at lifecycle boundaries and lightweight exact mount/path/
registration checks during use. Do not widen proof TTL or erase positive faults.

Worker1 owns ai-vm. Worker2 owns ai-harness preparation and independent review.
Coordinate shared deployment; workers must not change each other's live host.
Sova downtime is authorized and nobody is using it. Preserve chats, uploads,
artifacts, credentials and historical failure evidence. Keep the two Qwens and
image resident where practical; do not spend time restoring front-end availability.

After actual native tools/result and Sova delegation acceptance, launch one
independent near-950K test with the existing eight-hour background limit. Count
actual input tokens and reserve output/template space. Verify real startup and
then close paid CLI sessions; user will nudge for results. Do not stay active to
poll a multi-hour request, and leave the existing automation paused.

Use current failure evidence to make narrow fixes, not blanket timeouts or
safety bypasses. Preserve request ownership, complete SSE/HTTP drain and native
settlement checks. Never automatically replay ambiguous requests. A parent
waiting on a child does not hold an inference slot. Do not hold lifecycle locks
across inference or expensive periodic work. Do not invent new approval steps
for work already authorized here; root review of an exact changed artifact is
sufficient for coordinated deployment.

## Resource and data boundaries

Use registered storage and the existing canonical /run/llmctl/lifecycle.lock;
never replace/unlink it. Nested operations borrow and validate the existing
lease. Preserve MiMo's dedicated 704 GiB zero-swap slice, zero owned swap/OOM,
15% host available-memory reserve and 7% frontier GPU free-memory reserve.
Keep existing Qwen and Ada guards. Stop on 85C or lower hardware limit.
No four-way stress, driver/ECC/BMC/fan changes, host/VM reboot, Proxmox changes,
new model/runtime builds, installer work or model precision changes in H019.
Credentials stay private outside Git and task containers; do not print them.

## Publication and handoff

Use feature/glm53-flash and draft PR10. Root synchronizes reviewed worker commits,
scans changed files for credentials and pushes GitHub. Distinguish tested source,
live deployment, allocation, native qualification and application acceptance.
No main merge until appropriate acceptance. Record actual unavailable subsystems
and unfinished work. At the deadline keep MiMo selected; no automatic GLM rollback.
Historical instructions: docs/orchestration/AGENTS-H018-archive.md, not current
execution authority. Latest explicit user directions override older plans.
