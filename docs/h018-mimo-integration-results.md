# MiMo integration continuation — 28 September 2026

## Current checkpoint

The two-hour window runs from23:38:03UTC September27 to01:38:03UTC September28.
The swap-limit mechanism has been reproduced locally and a narrow repair has
passed small-container checks and independent review. Deployment of the ordinary
MiMo service began its ordinary 950K load at **00:03:07 UTC**; actual readiness
and Sova acceptance remain pending at this checkpoint. No long benchmark is running.

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
not yet readiness or long-context qualification.

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
