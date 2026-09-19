# Q1 saved-evidence verification — 2026-09-19

**Review ready; production restoration verified from saved Worker1 receipts.**
Fresh session `01a0ba93-cd61-7ad1-9829-c50d6c8a097e` performed local recalculation
only. No VM contact, load, inference, tool execution, source repair or broad test
suite. [Compact JSON](benchq1-verified-20260919.json) contains full identities,
per-row hashes, formulas, memory counters and 40 evidence-file hashes. Private
requests, responses, credentials and host traces remain outside Git.

Final owner phase is RESTORED; finalization exited 0 at **16:48:31 UTC**.
The authenticated Worker1 LAN receipt binds the original snapshot and restoration
challenge. Original Qwen `qwen38-27b-1000000-yarn4-tp2-bf16kv` selection,
desired running/boot resume, source, storage, guards and credential witnesses
match; original control active/running and boot active/exited are enabled.
Owned containers, campaign host and benchmark listeners are absent; the canonical
lease is released. This is saved observation, not a new live health check.

The automatic restoration failed with sanitized `OwnerError`; fresh-process
restore then failed `recovery_lease_inode_changed` because its lock baseline was
uninitialized, despite the unchanged canonical inode. Fresh capture initialized
that baseline and the existing restoration tail completed without restarting the
healthy original model or changing source. Both exit-1 receipts remain immutable.
The initial 4K startup also failed its 30-second `/get_server_info` timeout before
any accepted measurement; its allocation log and diagnosis remain preserved.
The original six-hour budget remains **1789826207.34127–1789847807.34127** epoch
seconds; prior journals/prefixes and all Q2 evidence pins match.

**Identity and comparability.** Final reviewed source is
`92037adb208c59217f9953c97979e63403c65980`; the preceding successful Q1 4K/16K
source was `b2d8cfaed40b56351794eef3a46c5bfe7d3f56c4`. The final runner change
bound the reviewed semantic disposition and remaining 64K continuation. Q2 source
is `fbb0fbd74385bd8b4a70a26bb053ad1f3deb0969`.

| Identity | Exact value |
|---|---|
| Model | `Qwen/Qwen3.8-27B-FP8` @ `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` |
| Runtime | SGLang v0.5.19, source `0bcd822377da7b5718e674eaf9c870d349424dd1` |
| Image reference digest | `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` |
| Q1 canonical arm | `105735cd31bd12be578b5240852c67698e6d65afc04f202e70a41db71b44d960` |
| Q2 canonical arm | `5dbc4dcc75c65ce12aff7a36a83b1e99e2b8bd7683727ad7696bfacd23696d2b` |
| Template SHA256 | `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041` |

Q1 is TP1 on GPU UUID ending `52c163cc`, guest CPUs **96–111 (16)**; Q2
is TP2 on both recorded GPU UUIDs, guest CPUs **0–111 (112)**. Full UUIDs and
image IDs are in JSON. Both use FP8 weights, BF16 KV, disabled radix cache,
2048-token prefill chunks, one running request, disabled overlap/CUDA graphs,
and the same YaRN factor-4 override. Native positional capacity is **262,144**;
that metadata is distinct from these smaller configured/allocated pools.

Exact requests regenerate from their frozen fixtures with only the nonce changed.
Shared fixture SHA256 prefixes are `21964c48bd5d` (4K, 87 records),
`f949c0180c3e` (16K retrieval/anchor, 399), and `e2dbe91cf975` (generation, 393).
Full hashes are in JSON. Nonce tokenization explains input-count differences;
raw requests/token-ID hashes differ. Q2 has **no 64K result**.

**Client performance, locally recalculated.** Output delivery is
`(completion_tokens − 1) / (last_output − first_output)`. Effective input is
`input_tokens / client TTFT`, **not native prefill throughput**. Latency below
is transport dispatch to drain, including stream completion; separate trial
orchestration latencies are retained in JSON. All finish reasons here are `stop`.

| Placement / configured tokens / case | Actual input | Output / cap | TTFT s | Output tokens/s | Effective input tokens/s | Latency s | Strict status |
|---|---:|---:|---:|---:|---:|---:|---|
| Q1 / 4,096 / retrieval | 3,509 | 80 / 256 | 0.408 | 38.06 | 8,605 | 2.511 | PASS |
| Q2 / 4,096 / retrieval | 3,512 | 80 / 256 | 0.329 | 35.08 | 10,672 | 2.611 | PASS |
| Q1 / 16,384 / retrieval | 15,813 | 84 / 256 | 1.870 | 39.85 | 8,455 | 3.980 | PASS |
| Q2 / 16,384 / retrieval | 15,813 | 84 / 256 | 1.522 | 34.10 | 10,387 | 3.986 | PASS |
| Q1 / 16,384 / anchor | 15,814 | 84 / 256 | 1.842 | 39.16 | 8,587 | 3.988 | PASS |
| Q2 / 16,384 / anchor | 15,815 | 84 / 256 | 1.479 | 34.27 | 10,692 | 3.932 | PASS |
| Q1 / 16,384 / generation | 15,591 | 492 / 512 | 1.841 | 38.06 | 8,467 | 14.770 | HARNESS_FAILURE* |
| Q2 / 16,384 / generation | 15,592 | 490 / 512 | 1.512 | 33.77 | 10,310 | 16.027 | PASS |
| Q1 / 65,536 / retrieval | 65,019 | 83 / 256 | 9.874 | 38.23 | 6,585 | 12.046 | PASS |

*Q1 generation's immutable strict-format failure remains unchanged. Removing
exactly one enclosing JSON fence gives the separately root-approved semantic
PASS; row/response/content hashes and final arm binding all verify. Its complete
492-token delivery timing is usable with this qualification, versus Q2's 490
tokens. This is distinct from Q2's genuine tool output-contract failure: after
successful `read_file` integration, its final output requested unoffered
`write_file` despite `tool_choice=none`, omitting START/MIDDLE/END answers.
That original HARNESS_FAILURE and separate diagnosis are preserved; no tool was
retested or executed here. Archive commentary is **not code-analysis coverage**.

Q1 output delivery is 8.5–16.9% faster on these shared cases; TTFT is 21.8–24.5%
longer. CPU allocation, TP and source revisions differ, so this does not isolate
GPU causality. Two 16K retrieval observations give range/mean variability of
1.55% TTFT / 1.75% output rate / 0.20% latency for Q1, versus
2.88% / 0.48% / 1.36% for Q2; this is not a statistical confidence interval.
Native prefill/decode timings and evaluated/cached token counters are unavailable.

**Memory accounting.** B means bytes; GiB = 2³⁰ B, GB = 10⁹ B. Native rounded
`GB` log labels remain unconverted: weights **28.72** per Q1 load, K/V respectively
**0.13/0.13**, **0.50/0.50**, **2.00/2.00**, with actual pools
4,096/16,384/65,536 BF16 token slots. Numeric allocation receipts were rehashed
and matched to current-load manifests/observations. Successful-load raw native
logs have saved upstream hashes but no local copies in these evidence folders;
they were not independently reparsed. Standalone allocator/workspace bytes remain
unknown, and rounded weight labels are not exact weight-byte measurements.

| Q1 pool | Load peak before readiness GiB | Warm GiB | Lifecycle/request peak GiB | Lifecycle samples / span s | Warm cgroup GB | Warm process-tree PSS GB |
|---|---:|---:|---:|---:|---:|---:|
| 4,096 | 30.533 | 31.129 | 31.129 | 66 / 63.10 | 4.475 | 5.224 |
| 16,384 | 31.303 | 31.898 | 31.898 | 86 / 86.67 | 4.456 | 5.206 |
| 65,536 | 34.305 | 34.900 | 34.902 | 83 / 92.28 | 4.457 | 5.208 |

Pre-readiness sample counts are 45/45/42; client load durations are
45.67/46.56/43.71 s. Each successful load has one discarded 2,343-input-token
warmup with cache-disabled derived prefill proof, not a native evaluated counter.
Readiness PSS is 5.103/5.133/5.135 GB. PSS was quiescent only; it is separate from
cgroup accounting and is never added to it. Q2 warm GPU use was
16.859/16.891 GiB at 4K and 17.266/17.297 GiB at 16K; warm cgroup was
7.542/7.510 GB and PSS 8.348/8.314 GB. Q2 numeric native K/V pools and required
host-demand decomposition are unavailable in synchronized records.

Q1 request samples number 3/4/4/14/12 in table order, covering an estimated
89.2–94.9% of dispatch-to-drain windows by union of ±0.5-second windows.
Maximum gaps are 1.068–1.076 s; collection wall time is 5.25–6.29% of request
time, not a measured slowdown. Peaks can be missed. Cgroup lifetime peaks
(4.919/4.457/4.475 GB) are not request peaks. No sampled Q1 cgroup swap is present.

The maximum sampled required host components are **13,287,989,248 B (13.288 GB)**:
12,797,124,608 anon + 98,963,456 kernel + 391,901,184 retained file, zero extra
workspace. This belongs to the **failed initial 4K container**, with its saved
load tracker at 52 samples / 64.22 s; it must not be reassigned to a successful
load. The later warm 4K required-components value is 4,473,470,976 B. Warm 16K/64K
required-demand receipts are unavailable. Reclaimable cache is kept separate
(zero at that peak); shared RSS is not unique required RAM. Cold-cache loading,
absolute transient peak, larger-context host demand and whole-VM RAM requirement
remain unknown. A 4.47 GB warm cgroup is therefore not a safe RAM sizing claim.

**Capacity planning only; nothing above 65,536 was tested.** Measured 64K GPU
total/used/free are **102,641,958,912 / 37,476,106,240 / 64,497,909,760 B**
(95.592773 / 34.902344 / 60.068359 GiB). The unavailable/reserved device gap is
**667,942,912 B (0.622070 GiB)**: total is not used + free.

Using the 65,536 B/token BF16-KV hypothesis, measured whole-device slopes are
67,242.67 B/token (4K→16K) and 65,621.33 (16K→64K). Their fixed residuals are
30.878906/30.898438/30.902344 GiB; native rounded K/V labels are consistent with
the hypothesis, not exact slope proof. Use the largest residual conservatively:
`used(N) = 30.90234375 GiB + N × 65,536 B`, comprising weights plus unresolved
runtime/workspace in the fixed term. Project **measured free**,
`free(N) = 64,497,909,760 − (N − 65,536) × 65,536 B`.

| Estimated pool tokens | KV GiB | Fixed aggregate GiB | Total used GiB | Free GiB |
|---|---:|---:|---:|---:|
| 131,072 | 8 | 30.902 | 38.902 | 56.068 |
| 262,144 — native positional capacity | 16 | 30.902 | 46.902 | 48.068 |
| 524,288 — YaRN extension | 32 | 30.902 | 62.902 | 32.068 |
| 720,896 — upper illustration, not recommended | 44 | 30.902 | 74.902 | 20.068 |

The 16 GiB reserve alone gives an arithmetic ceiling of **787,552 tokens**.
Separately, a conservative `mem_fraction_static=0.8` screen retaining 20% of
total (19.118555 GiB) yields **736,457 tokens**. This screen is not a calculation
of accepted runtime allocator capacity; internal pools, rounding and workspace
growth can tighten it. The 720,896 illustration leaves less than 1 GiB above
that screen. Neither ceiling is a supported maximum.

Retain **64K as the measured ceiling**. For future planning, **128K–262,144** is
a conservative next range; 512K has arithmetic room but needs separate allocation,
occupied-context, speed and quality acceptance. Preserve native 262,144 versus
YaRN extension. These projections prove neither simultaneous GLM/Qwen deployment
nor a usable RAM cap, and authorize no further tests in this task.

Reproduction: run `python3 scripts/bench/verify-q1-saved.py --tasks TASKS
--output OUTPUT.json` from this source copy, with the two saved Worker1 task
folders under `TASKS`. The focused verifier checks hashes, frozen request bytes,
saved answers, timing/coverage arithmetic, memory sums and restoration bindings.
Publication, push, PR and merge remain for root review; this task stops here.
