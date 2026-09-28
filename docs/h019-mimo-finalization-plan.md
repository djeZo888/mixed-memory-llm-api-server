# H019 — finish MiMo integration, then direct 950K test

## Window and changed decisions

September 28, 2026, 02:10:29–04:10:29 UTC. The user permits Sova downtime and
requires leaving MiMo selected/resident if integration is unfinished. Do not
restore GLM at the deadline. Skip the unrun 64K benchmark and proceed directly
to the near-950K test after short integration checks pass.

## Starting point

Original GLM-backed Sova was restored in H018. MiMo weights/runtime and optimized
8-decode/64-batch configuration are already verified. The 950K allocation and
tiny text worked; supervisor lock contention interrupted native tool tests.
The reviewed periodic-write correction removes redundant filesystem scans and
passed 59 focused tests, but is not deployed. A separate nested lease path
needs correction. Do not repeat downloads, builds or completed benchmarks.

## Parallel bounded work

1. Worker1: inspect current state, repair nested lease borrowing, stage a fresh
   deployment with the reviewed periodic-write fix and all required hash bindings.
   Measure observer lock/freshness behavior before loading. Stage current short
   and direct-950K clients, then ordinary GLM stop/MiMo start after root review.
2. Worker2: independently review the exact backend changes while preparing the
   existing compiled Sova artifacts, preserving histories and files. Pause the
   app normally and stage matching MiMo routing and current acceptance clocks.
3. Worker1: real native tool/result continuation with 17 offered tool schemas;
   retain exact model and token usage. Worker2: real Qwen-parent -> MiMo-child
   with a tool/result -> Qwen-verification. Fix concrete failures within scope.
4. Worker1: final independent near-950K test (approximately 948,975 actual input
   tokens with up to 1,024 output), eight-hour total cap, explicit correctness
   markers and normal resource/stream/settlement evidence. No 64K precondition.
   Verify running and close paid sessions. User requests the later result check.

## Time and completion discipline

Aim backend changes/review by 02:45, load and native acceptance by 03:15, Sova
acceptance by 03:40, background dispatch by 03:55. These are planning targets,
not additional approval gates. Hard foreground end remains 04:10:29 UTC.
Use fresh bounded native sessions and independent jobs for loading/inference.
No paid CLI should wait for a long test. No rollback to GLM. If a real resource
fault requires a stop, report it and leave MiMo selected but unavailable.

Root records reviewed code, exact live state, evidence and pending work, and
publishes to draft PR10. Preserve all historical receipts; do not rewrite old
qualification or reuse expired dispatch clocks. Automatic follow-up stays paused.
