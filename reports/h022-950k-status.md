# H022 — MiMo near-950K test result and Codex follow-up

Read-only collection: September 28, 2026, 11:02–11:07 UTC, through a bounded
native mac-worker1 session. No request was replayed and no VM configuration,
service, model, hold or hardware setting was changed.

## Result: FAILED; MiMo is currently not resident

The existing `h019-final950k.service` exited with status 1 at **07:40:01 UTC /
09:40:01 Ljubljana**, before its 11:36:11 UTC eight-hour deadline. The request
was sent once at 03:36:16 UTC with **948,975 input tokens and a 1,024-token
output allowance**, using the configured 950,000-token window. It lasted about
**4 hours 4 minutes** before failure.

### Recorded failure chain

1. At **07:40:00.423857 UTC**, the owner recorded `lifecycle_busy` while checking
   `hardware_latch`, at the `canonical_lease` stage. The recorded cycle lasted
   0.110690 seconds; a hardware refresh was not attempted.
2. The client recorded `FAILED_QUARANTINE_NO_RETRY` / `RuntimeError`. Its original
   ownership disposition remains `UNKNOWN_POSSIBLY_SUBMITTED`.
3. At **07:40:09.535037 UTC**, settlement recorded `command_timeout`. Owner state
   remains `HELD`, with `request_hold=true` and no successful settlement receipt.

This identifies the supervision failure trigger. The client did not persist its
exact exception message, so the complete causal chain from that supervisor
event to the client's RuntimeError is not independently proved. The identity
of the lock holder and the complete contention/root-cause chain are not
established by this collection. It is not a demonstrated context-memory failure or model-quality
failure. A future repair must distinguish temporary control-plane contention
from positive hardware faults while retaining bounded freshness/fault handling.

### Current state versus stale files

At 11:05:59 UTC, the recorded native model, supervisor and proxy PIDs were
absent, and the persistent MiMo cgroup had `populated 0`. A single passive
native-slot read at 11:06:54 UTC received connection refused. There was no retry.
MiMo remains the selected frontier, generation 12, but it is **not loaded**.

The proxy file's `active_requests=1` observation dates to 03:36:16 UTC; it is
not evidence of current inference. The last owner guard dates to 07:39:55 UTC.
Physical process absence does not retrospectively turn the failed request into
a successful drain/settlement. No hold or historical uncertainty was cleared.

## What was and was not measured

There were **484 SSE keepalive comments**, zero output-delta/data events, no
usage, no finish reason and no `[DONE]`. The last keepalive was at 07:39:41 UTC.
Normal HTTP drain, final correctness and native timing were not established.

The last retained authenticated processed-token count is the **early 03:39:04
snapshot: 10,240 tokens**. No later processed-token count was retained, so the
fraction of the prompt completed at failure cannot be reconstructed. Keepalives
must not be counted as generated tokens or proof of continuing prefill progress.

Across 2,925 retained guard samples, 03:36:15–07:39:55 UTC:

| Measurement | Observed value | Meaning |
|---|---:|---|
| MiMo cgroup memory, sampled maximum | 572.78 GiB | Includes file cache; not process RSS |
| Frontier GPU device memory used | 85.85 GiB | Device-wide total minus free, not allocator-reserved memory |
| Frontier GPU free memory | 9.75 GiB | 9,979 MiB in every retained sample |
| Frontier GPU temperature | 35–71°C; last 61°C | Sampled range, not continuous sensor trace |
| Host available memory, sampled minimum | 357.67 GiB | Host `MemAvailable` |
| MiMo cgroup swap | 0 | Host has unrelated pre-existing swap use |
| MiMo OOM / OOM-kill counters | 0 / 0 | No recorded MiMo out-of-memory event |

The persistent slice's 640.17 GiB historical peak is broader than this request
and is not reported as its peak. These samples support capacity during the
observed interval; they do not qualify a completed 950K turn. No throughput,
time-to-first-token or correctness result is available for this attempt.

## Next work, planning only

1. Identify shared lifecycle-lock contention and correct the demonstrated
   supervision/settlement behavior. Reconcile the held owner through the normal
   lifecycle path after independent absence checks; preserve failure evidence.
2. Perform a short controlled recovery/qualification before considering another
   long test. Do not rerun 950K automatically or restore GLM.
3. Continue independent Codex tool/context/UI repairs in parallel. MiMo's native
   failure and the existing MiniMax-to-MiMo HTTP400 are separate defects.

The [Codex completion plan](../ai-harness/PLAN-CODEX-COMPLETION.md) defines
worker allocation, acceptance gates and an initial proposed two-hour window.
No implementation or recovery was performed during H022.

Compact evidence is in [the machine-readable report](h022-950k-status.json).
Raw stream, private request and protected state remain outside Git.
