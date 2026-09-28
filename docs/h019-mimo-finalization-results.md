# H019 — MiMo finalization checkpoint

Foreground window: September 28, 2026, 02:10:29–04:10:29 UTC.

## Decisions

- Keep MiMo selected at the end of the window; do not restore GLM.
- Skip the unrun 64K benchmark. The final test submits approximately 948,975
  input tokens, reserving up to 1,024 output tokens in a 950,000-token window.
- The final test runs independently with an eight-hour limit. Paid worker
  sessions close after confirmed startup; the user requests the later result.
- Sova downtime is allowed. If application integration alone remains incomplete,
  a qualified native MiMo service may run the private-API benchmark.

## Completed preparation

Sova was stopped normally at 02:17:56 UTC. All 26 conversations, 133 messages,
62 file records and 17,597 workspace files were preserved. Search, status and
administration services remained running. No active Sova task or owned engine
remained. The existing compiled MiniMax and server payload were retained; only
the current qualification/configuration overlay remains to be built and applied.

Worker1 repaired a nested lifecycle-lock acquisition by validating and borrowing
the existing lock. Startup now supplies the same-boot hardware sample to the
health-policy check. Worker2 independently checked the changed ownership path.
Periodic hardware proofs and MiMo guard writes no longer need recursive
filesystem scans; full scans remain at lifecycle boundaries, alongside exact
mount/path validation and atomic writes. Current source checks passed; live
deployment and model acceptance are recorded separately below.

Before deployment, a 45-second observer recorded the node service holding the
canonical lifecycle lock. The longest sampled continuous hold was 1.878 seconds;
the oldest proof was 10.022 seconds. Sampling was every 100 milliseconds, so this
is not an exact trace of every hold. It does not identify the holder at the
historical H018 failure instant.

## Live results

The exact 13-file backend package deployed at 02:43:55 UTC. Control and node
services restarted normally; the canonical lock identity and existing model
processes were preserved.

A comparable 45-second observation after deployment passed: longest sampled
lock hold fell from 1.878 to 0.784 seconds, and maximum proof age was 9.309 seconds,
below the unchanged 15-second limit. Proofs belonged to the current boot and had
no positive hardware faults. This supports proceeding with a model load; it does
not yet establish stability during inference or 950K correctness.

MiMo became the selected frontier (generation 12) and started loading independently
at 02:46:14 UTC. The prior GLM process, cgroup and GPU allocation were released.
The startup receipt confirmed the 704 GiB memory limit, zero owned swap/OOM and
36 C frontier GPU temperature. Both Qwens and the image process were preserved.
Model/application acceptance and the long-context test are pending.

## Benchmark baseline

The checkpoint, native runtime and selected eight-decode/64-batch configuration
are unchanged. Historical optimized results were:

| Input size | Input tokens/s | Output tokens/s |
|---|---:|---:|
| Approximately 4K | 71.49 | 9.58 |
| Approximately 16K | 69.56 | 9.41 |

These short results do not predict long-context speed. Earlier 950K allocation
used 85.74 GiB of GPU memory, with 9.85 GiB free, and 625.47 GiB of container memory
including reclaimable file cache. That is allocation evidence, not a completed
950K inference test.

## Durable execution records

- Worker1 preparation: native session `01a0e5cb-c39b-7e72-a9b1-a52a13b0fe82`,
  exit 0 at 02:36:21 UTC; no live mutation.
- Worker2 preparation/review: `01a0e5cb-2069-7661-b178-7c7ac500a191`,
  exit 0 at 02:26:20 UTC.
- Worker1 deployment: `01a0e5df-3b5f-7b03-b5c9-38f548533ee3`, started
  02:36:47 UTC, exit 0 at 02:49:35 UTC. It closed while the model loaded.

Credentials, detailed host traces and user conversations remain outside Git.
The existing follow-up automation stays paused.
