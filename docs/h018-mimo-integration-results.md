# MiMo integration continuation — 28 September 2026

## Current checkpoint

The two-hour window runs from23:38:03UTC September27 to01:38:03UTC September28.
The swap-limit mechanism has been reproduced locally and a narrow repair has
passed small-container checks and independent review. Deployment of the ordinary
MiMo service began its ordinary 950K load at **00:03:07 UTC** and actual native
and private-API readiness was confirmed at **00:15:43 UTC**. The tiny text
request passed, but the subsequent native tool test was interrupted by a
separate hardware-status proof failure. A reviewed owner-only correction is
installed and a fresh load began at **00:47:40 UTC**. Native tool and Sova
acceptance remain pending. No long benchmark is running.

Sova was paused normally at23:41:52UTC. Chats, files and existing quarantines
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

Remaining gates are actual production allocation/readiness, native tool/result
continuation, then genuine Qwen-parent → MiMo-child → Qwen-verification in Sova.
Only after these pass will the final independent job run optimized64K followed
by948,975 input tokens and up to1,024 output tokens within the950K window.
Its total background limit is eight hours. After startup verification, paid
worker sessions close and the user can request a later result check.
