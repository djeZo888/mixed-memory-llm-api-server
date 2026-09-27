# Affinity14 source packet — held for exact root GO

Reuse of affinity02: one independent Linux systemd controller, sequential R12
4-decode then conditional R13 2-decode, each with its own durable owner/client.
Nothing in this packet changes running R9 or the ordinary/LAST client/proxy.
No source staging or new inference has occurred in this task.

R12 guest CPUs 0,24,40,56; R13 0,40. Both use strict masks, batch64 strict full
mask, GGML NUMA disabled, external interleave0-7, outer CPUs0-7,16-71/mems0-7,
704GiB, GOMP0, fixed131072/F16 and unchanged image/model/native precision,
loadnone/nohost, batch2048/ub512 and zero prompt cache. This compares guest whole
profiles; it proves no host GPU locality. Existing7% GPU/15% host/no-owned-swap/
85C guards and protected storage/identity/lifecycle ownership remain enforced.

Each owner runs only the unchanged tiny warm8 and exact83-input/128-output
ADC fixture, seed270927, thinkingfalse, temperature0, no profiler or retry.
Raw SSE/native timings/counts/TTFT/prefill/total/first-last UTC and monotonic,
full DONE/drain and authenticated slot idle are saved privately. Length samples
remain UNSCORED. The bounded existing affinity sampler accepts configured N;
its full-window transition result remains separate from fixed0.5s-later evidence.

R13 requires R12 native N-1 tps strictly greater than9.209882711781072,
full transport/guard checks and physical settlement/GLM readiness, and900s left
before cleanup. Otherwise it is NOT_TESTED, with no alternate or retry. The first
profile also needs only900s, not1800. All clients end17:48UTC, cleanup17:50,
physical deadline17:57:30, global18:33:08 on2026-09-27. Exact GO expires17:35;
starts must precede that time. No expiry rewrite loop is provided.

Root reviews SOURCE-SHA256.json plus the task's unauthorized GO template.
Only a later exact authorized ROOT-AFFINITY14-GO.json permits stage_pair.py,
then dispatch_pair.py once. Stage/launch check actual remote namespaces,
units/containers/receipts before writing or submitting; ambiguous launch results
require actual readback, never replay from a local PID. No canonical lease
surrounds systemd-run or pure postdispatch receipt writes. Both owners independently
prove exact R9 PID0/cgroup/GPU retirement and terminal OWNER, original GLM ready,
and the original three preserved containers unchanged before any model load.

No winner is selected. R9's8-decode acceptance does not qualify4/2. Any subsequent
ordinary final profile must be selected from actual results, freshly loaded and
complete maximum-pool/4K/16K/native17 and production/Sova acceptance under root
GO before the held64K→near1M finite8-hour chain. LAST's BUSY contract remains
unchanged pending the separate W2 findings/root authorization.

Offline validation: `python3 -B -m unittest discover -s scripts/h016/affinity14
-p 'test_*.py'` and the six profile contract tests in
`r12-spread4/test_profile_contract.py`. No online benchmark is a source check.
