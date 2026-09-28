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
remained. The existing compiled MiniMax and server payload were retained. A
small qualification/configuration overlay was subsequently built and applied;
application acceptance is recorded separately below.

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
At 03:01:42 UTC both the native and private APIs reported an idle 950,000-token
slot. Container memory was approximately 572.8 GiB including file cache, GPU
memory was 85.74 GiB used / 9.85 GiB free, GPU temperature was 35 C, and owned
swap/OOM remained zero. This is a readiness sample, not an inference peak.

Current native acceptance passed at 03:07:22 UTC. A tiny text request and two
turns with all 17 tool schemas offered completed with actual usage, terminal
SSE, full HTTP drain and authenticated idle settlement. MiMo called the real
file-read tool and returned the correct sum and marker from its result.

| Native tool turn | Actual input | Actual output | Input tokens/s | Output tokens/s | Total seconds |
|---|---:|---:|---:|---:|---:|
| Tool call | 9,536 | 63 | 67.37 | 9.39 | 149.39 |
| Tool-result continuation | 9,635 | 70 | 65.43 | 9.58 | 155.73 |

Neither turn reused a cached prefix. These are short output samples with a
65,536-token requested ceiling, not evidence of a full 65,536-token generation.
The qualified record distinguishes 950,000 allocated tokens from 9,635 occupied
tokens tested. Original model/runtime lineage is retained without another weight
download, native build or full shard hash pass.

## Sova application result

The matched source `34959c67` and image `5ec05218` were applied with the current
native qualification. An initial preflight refused a task-private receipt with
mode 0664 before any model request. Changing that one file to 0600 preserved its
contents; the failed attempt remains recorded.

A distinct attempt started at 03:25:32 UTC. Qwen used file tools and genuinely
delegated a foreground task to `frontier`. Its child received HTTP 400 from the
MiMo request adapter before any MiMo generation was admitted. Qwen reported the
failure without retrying. The acceptance driver's missing-result-ID assertion
was a consequence of that rejection, not evidence that delegation was absent.

The exact rejected field remains unproven: the test's capture hook normalized the
request before persisting it, so the invalid child body was not retained. The
HTTP status narrows the failure to request validation or tool-history validation.
This is an unresolved Sova integration issue; application acceptance **failed**.

The fixture container exited and was absent, the application remained stopped,
all recorded lanes were idle, and the fixture had zero frontier requests or
quarantines. A later authenticated native readback at 03:29:59 showed the 950K
slot idle. The original supervisor's `SETTLEMENT_UNKNOWN` receipt is preserved;
later independent observations establish settlement rather than rewriting it.
Conversations, files and production histories remained unchanged.

## Independent near-950K test

Worker1 verified the exact current process, generation, idle native slot, zero
proxy requests/quarantine, fresh hardware proofs and zero owned swap/OOM. The
final private-API test uses genuine native-tool and production checks; no Sova
PASS evidence is supplied.

The request body was sent once at **03:36:16 UTC**, with **948,975 input tokens**
and a **1,024-token output budget**. Its independent deadline is
**11:36:11 UTC / 13:36:11 Ljubljana**. The request is 2,581,549 bytes and has
SHA256 `932c76632afed416c80b2107d59b51cc85bde00e46e212d89e66c4a87661f0df`.
The optimized 64K test was skipped as requested.

Actual processing was verified at **03:39:04 UTC**: native task 654 was active,
10,240 prompt tokens had been processed, no prompt tokens came from cache, and
the private proxy owned exactly one request without quarantine. Hardware proofs
were current; frontier temperature was 43 C, GPU free memory was 9,979 MiB, and
owned swap/OOM remained zero. These are startup observations, not final peaks.
The eventual speed, memory peaks and retrieval correctness remain **pending**.

Keep MiMo selected and resident after the test. Do not restore GLM. The user will
request a later result check; paid workers do not remain active to watch this
multi-hour request, and the existing automation stays paused.

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
- Worker1 native qualification: `01a0e5f4-43f3-7da3-bd67-3d9d970768cf`,
  exit 0 at 03:07:15 UTC. The independent test completed at 03:07:22.
- Worker1 terminal collection: `01a0e5ff-60d7-70f3-9dc0-a5f691060708`,
  started 03:11:54 UTC; verified export produced at 03:13:39 UTC; exit 0 at
  03:16:56 UTC.
- Worker2 activation/application test: `01a0e602-537d-70d2-a65d-6912e5fa552d`,
  started 03:15:07 UTC, exit 0 at 03:34:39. The application test failed before
  MiMo admission. Later collection proved app/fixture settlement.
- Worker1 final launch: `01a0e611-7787-73b2-907f-cde0fb705559`, started
  03:31:39 UTC. The independent request was submitted once at 03:36:16 UTC;
  actual processing was verified at 03:39:04 UTC. Exit 0 at 03:42:40 UTC;
  all paid worker CLI sessions are closed. No subsequent VM polling occurred.

Credentials, detailed host traces and user conversations remain outside Git.
The existing follow-up automation stays paused.
