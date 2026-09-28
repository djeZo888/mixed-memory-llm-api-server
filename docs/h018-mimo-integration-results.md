# MiMo integration continuation — 28 September 2026

## Current checkpoint

The two-hour window runs from 23:38:03 UTC September 27 to 01:38:03 UTC September 28.
The swap-limit mechanism was reproduced and its repair passed focused checks.
Both ordinary MiMo loads reached actual 950K readiness and passed tiny text,
but supervision stopped the subsequent native tool requests. The replacement
load failed on lifecycle-lock contention during a GPU health-proof refresh.
**MiMo is not qualified for Sova, and neither the optimized 64K nor near-950K
benchmark has started.**

Original GLM rollback started at **01:14:12 UTC**. Authenticated readiness and
the **1,048,576-token** configuration passed at **01:19:33 UTC**. Original
Sova release `7143c17d` / image `9ef88598` started at **01:22:52 UTC** and
its required HTTP endpoints passed at **01:24:11 UTC**. The two Qwen
instances and image service were kept resident. All 26 chats, 133 messages,
62 recorded files and 17,597 workspace files were preserved. The image lane
reconciled normally to idle; the existing workspace quarantine was retained.

At the beginning of the window, Sova was paused normally at 23:41:52 UTC. Chats, files and existing quarantines
were preserved. The original GLM process was normally stopped and its exact
process/cgroup/GPU allocation released. Both Qwens and image remain resident.

## Confirmed failure mechanism

On ai-vm's Docker29.6.1/systemd255/cgroupv2 environment, a disposable64MiB
container started with `memory.swap.max=0`. After `systemctl daemon-reload`, its
limit became `max`, while its memory limit remained64MiB. This reproduces the
mechanism described by [Moby issue51446](https://github.com/moby/moby/issues/51446).
The original H017 failing literal was not retained; this is a new controlled
reproduction, not a reconstructed historical observation.

The deployed repair uses an explicit dedicated `llmmimo.slice` with a704GiB
memory limit and zero swap, and puts the model's Docker scope beneath it.
The owner verifies the exact ancestry and sole model child, the persistent
unit, actual kernel limits and zero owned swap/OOM. It classifies Linux's
`max` value without treating it as zero. A leaf unlimited swap setting is
acceptable only when the independently checked parent enforces zero swap.
The service requires and starts after the slice, so ordinary starts do not
depend on a one-time manual setup.

The actual production container is beneath the required slice. At startup,
both parent and child had the 704 GiB limit, zero swap limit/current and no
owned OOM events. The deployment worker exited at 00:10:04 UTC while the
ordinary service continued loading independently. This is startup evidence,
not long-context qualification. The later readiness check confirmed 950,000
usable tokens on both native and private API, the same process identity,
10,091 MiB of GPU memory free out of 97,887 MiB, and a 36°C GPU temperature.
Container memory was 622,077,083,648 bytes, including file cache; owned swap
and OOM remained zero.

At 00:16:03, the owner refused an unconfirmed GPU health-latch status during
the first 9,536-token tool prefill. Cleanup separately exceeded its command
timeout. A 00:19:51 read verified the exact process, cgroup and GPU allocation
were released. The later protected hardware state had no positive fault and
a fresh proof, which does not reconstruct its state at the failure instant.
The original failed request and uncertainty records remain retained. This
second failure is distinct from the repaired swap-limit reset.

The last successful health proof was nearly 11 seconds old five seconds before
the failure, against a 15-second freshness limit. This supports expiry as the
cause; the exact failing projection was not retained. The correction reuses the
owner's existing fresh GPU measurement to renew an expired, same-boot negative
proof under the canonical lock. Positive faults, unknown storage and invalid
evidence still stop the service. Explicit monotonic deadline checks preserve
the five-second total guard budget even when a lower-level helper catches a
timeout exception. The shared hardware-policy module remains unchanged.

Independent review reproduced and rejected an earlier timer-handling defect,
then verified the corrected owner with a delayed-read fixture. The final
owner SHA-256 is `218c890f1f3d8f7f80998aaf5cf7463c32febf5e454713f40da76a9ed60027d0`.
Focused owner checks passed (48 passes and one historical skip). Failed
request evidence and its exact physical/proxy settlement remain preserved;
the unfinished request was not replayed.

A subsequent start at 00:43 was rejected for lock contention before creating
any model process. One fresh ordinary start then succeeded at 00:47:40 with a
new launch identity and the corrected owner. Its persistent parent again
enforces 704 GiB and zero swap. This is load-start evidence only.

The exact production parent settings were exercised using a tiny64MiB child,
without allocating704GiB or loading model weights. Parent704GiB/zero-swap
remained enforced through reload, child restart and another reload. The
candidate's actual policy checker accepted all four observations. Test
containers and prototype policy were removed afterward.

The two Qwen and image containers' limits and swap counters were unchanged.
They already had unlimited leaf swap settings before this test, with about
1.52GiB combined existing swap charges. These are separate from MiMo's required
zero-swap policy; this task did not change their limits or attribute those
charges to MiMo.

## Settings and acceptance

Keep the previously verified MiMo Pro-RL checkpoint, native MXFP4 expert
weights/BF16-F32 nonexperts, existing runtime, eight decode threads,64 batch
threads and F16 cache. Configured capacity remains950,000 tokens.

Focused owner regressions, existing short-client and final-client regressions
passed:78 passes and one historical fixture skipped. Worker2 independently
reviewed the exact owner, service/slice and manifest closure without findings.
It also prepared the existing950K
Sova configuration using retained compiled artifacts. No native rebuild or
model download is required.

Allocation/readiness passed twice. Remaining gates after the next deployment
are native tool/result continuation, then genuine Qwen-parent → MiMo-child →
Qwen-verification in Sova.
Only after these pass will the final independent job run optimized64K followed
by948,975 input tokens and up to1,024 output tokens within the950K window.
Its total background limit is eight hours. After startup verification, paid
worker sessions close and the user can request a later result check.

## Second attempt and remaining blocker

The replacement load reached native/private 950,000-token readiness at
00:59:53 UTC. Tiny text completed at 00:59:58. The next tool prefill was
interrupted at 01:00:16 by `lifecycle_busy` while the supervisor tried to
refresh expired health evidence. Cleanup separately timed out at 01:00:25.
The exact native process, cgroup, GPU allocation and proxy were later proven
released under the canonical lock. The failed request remains recorded as
terminated without a proven complete HTTP response; it was not replayed.

At readiness the GPU had **10,091 / 97,887 MiB free**: approximately
**85.74 GiB device memory used and 9.85 GiB free**, at **36°C**. Container
memory was **625.47 GiB including reclaimable file cache**; owned swap/OOM
were zero. These are allocation/short-request observations, not a successful
950K input test or a prediction of large-context speed.

The node-status service was directly observed holding the lifecycle lock at
01:10:54. The holder at the earlier failure instant was not captured. The
later inactive-client staging operation occurred at 01:01:22–01:01:23, so it
did not cause the 01:00:16 failure.

Source review and a focused regression established that four updated GPU
health proofs cause eight recursive root-directory scans while holding the
lock. The declared observer timeout does not interrupt those Python scans.
A narrow source correction removes the duplicate scans from periodic proof
writes, retaining the existing lease, registration, mount, path, protected JSON
and atomic-write checks. Full scans remain at initialization and lifecycle
boundaries. The regression changed from eight scans to zero; **59 focused
checks passed**. This correction is **not deployed or live-qualified**.
It does not establish the exact historical lock holder or guarantee that all
remaining observer operations fit their time budget.

Most of this window went into the supervisor/storage fixes, two model loads,
failure investigation and restoration. There was no model download, native
runtime rebuild, thread sweep or repeated large-context benchmark.

## Next bounded execution

1. Deploy the reviewed periodic-write correction with matching hashes across
   the control, node and imported policy copies; preserve the closed H018
   manifests and receipts as historical evidence.
2. Measure healthy proof freshness and canonical-lock duration before another
   model load. Capture the holder at the failure instant if contention recurs.
   Review the separately identified nested lease-acquisition path as well.
3. Stage all clients before loading, then repeat genuine native tool/result and
   Sova delegation acceptance. Do not stage files under the lifecycle lock
   while a request is active.
4. Only after acceptance, launch the independent 64K → near-950K job and close
   paid sessions. Old admission clocks must not be reused.

The automatic follow-up remains paused. There is no long test to wait for at
this checkpoint. Both worker CLI sessions exited successfully: Worker1 at
01:24:23 UTC and Worker2 at 01:26:23 UTC. No paid worker remains waiting.

## Evidence

- [Backend failure, exact settlement and recovery](../reports/h018-recovery06-20260928/README.md)
- [Original Sova recovery and preserved histories/files](../reports/h018-original-recovery07-20260928/REPORT.md)
- [Periodic-write source fix and 59 focused checks](../reports/h018-latch-write-fix06-20260928/README.md)
- [Independent locking review](../reports/h018-lease-review05-20260928/README.md)
- [Historical optimized 4K/16K performance](h016-mimo-results-20260927.md)
