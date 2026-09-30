# H037 — Codex default and internal Ada image service

Authorized 30 September 2026. Execution began 10:37:52 UTC; hard stop is
13:37:52 UTC (15:37:52 Europe/Ljubljana). App updates were completed before
implementation. Root coordinates, reviews and publishes. Both Mac workers use
fresh bounded native Codex sessions with `gpt-6.1-sol` and `ultra`, isolated
copies, retained session IDs and actual exit receipts.

## Required outcome

- Repair worker1's stale CLI launcher and check the desktop SSH connection.
- Retire the internal Ada's 200K Qwen instance and bind the existing image model
  to that Ada by UUID. Preserve the image recipe, Full HD maximum, guarded
  editing and 5% VRAM reserve.
- Keep MiMo at 480K on RAM plus its fast Blackwell and both 480K Qwen instances
  on their existing fast and Gen3 x4 Blackwells.
- Make Codex the default for new chats while preserving existing chat engines,
  histories, files and MiniMax as an available choice.
- Review Status and Status-Admin against central configuration and observed
  runtime. Hardware absence must affect only its dependent service.
- Inspect current official Codex upstream and Sova's integration changes.
  Upgrade only if the delta is manageable; report a substantial merge rather
  than expanding this task into an unbounded upgrade.

The latest user decision keeps the existing 400,000-token compaction threshold,
480,000-token context and 65,536-token output allowance. This leaves 14,464
additional tokens of headroom. Retain the existing admission rules and policy
hashes; no adaptive output-budget feature is needed.

## Bounded allocation

1. Worker1: launcher repair; read-only placement/ownership inventory; reviewed
   image relocation; short generation/edit and memory/readiness verification.
2. Worker2: fresh source audit (maximum 30 minutes), then a separate bounded
   application task for default/config/status and coordinated deployment.
3. Workers: focused acceptance of changed paths, short new chats/follow-ups,
   image tool delivery and status pages. Root reviews exact source and receipts,
   synchronizes results and publishes.

Shared deployments require one named owner and root coordination. Do not keep
paid sessions open waiting for another owner or model loading. Record completed
work incrementally and finish exports before the deadline.

## Preserve and exclude

Preserve credentials outside Git, chats/uploads/generated files, original
failed/interrupted outcomes, unrelated uncertain owners and quarantines, model
weights and runtime recipes. Use current lifecycle/storage ownership guards.
No new models, Proxmox changes, drivers, fan changes, long benchmarks, repeated
950K tests or repeated large compaction pastes. No recurring automatic updates;
manual maintenance policy remains. Label retained evidence separately from
fresh live acceptance and report incomplete items at the hard stop.
