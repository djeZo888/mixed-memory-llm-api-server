# Combined Qwen benchmark verification — 2026-09-19

**Single-GPU Qwen reached a configured and natively allocated 262,144-token pool.**
Its one measured retrieval used **261,525 input / 89 output tokens**, with
**84.330 s client TTFT, 87.050 s transport latency and 32.740 output tokens/s**.
The immutable strict result is **HARNESS_FAILURE** because of one enclosing JSON
fence; the exact saved answer has a separately root-approved **semantic PASS**
after removing that fence. This is not an unqualified strict PASS, transport
failure or output-limit event. No measured request was repeated.

Q1 used one GPU and 16 guest CPUs; Q2 used two GPUs and 112 guest CPUs. On shared
4K/16K fixtures, Q1 delivered output 8.5–16.9% faster but had 21.8–24.5% longer
TTFT. The 256K request peaked at **46.939 GiB used / 48.031 GiB directly free**.
Using the request-window peak as the primary anchor, an observed-slope projection
gives approximately **63 GiB used at 512K** and **890K tokens with a 10%
physical-memory margin**; lifecycle peaks are recorded separately.
Those larger capacities are untested for allocation, speed and quality; a
separate 0.8-total occupancy proxy is stricter and is not an established SGLang
allocator formula. Single-GPU serving was benchmarked, not deployed. Original
**Qwen 1M TP2 production is restored**.

[Compact JSON](benchq1-verified-20260919.json) retains exact counters, formulas,
identities and evidence hashes. Retained verification session:
`01a0ba93-cd61-7ad1-9829-c50d6c8a097e`; interim commit:
`80e50f0535428c4be99951ad887b59079adb5ae3`. This follow-up read saved Worker1
files only. No VM contact, source repair, inference, tool retest or 512K test.
Publication integrates only the report/JSON/verifier onto reviewed benchmark
source `b750bb37dd3107cf5b1e7aaabe6237ebc435085c`. That publication base and the
historical tested sources below are distinct from the final report commit.

**Measured performance.** Output delivery is
`(completion_tokens − 1) / (last_output − first_output)`; effective input is
`input_tokens / client TTFT`, **not native prefill throughput**. Latency is
transport dispatch to drain. Client event arrival includes chunk/transport
costs. Native prefill/decode timings and evaluated/cached counters are unavailable.
All table responses finished with `stop`, below their output caps.

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
| Q1 / 262,144 / retrieval | 261,525 | 89 / 256 | 84.330 | 32.74 | 3,101 | 87.050 | HARNESS_FAILURE* |

*Both framing rows retain separate root-approved semantic PASS dispositions.
For 256K, exactly START/MIDDLE/END and their expected values match, without extra
answer content. Its last output arrived at 87.017718 s; `(89−1)/(87.017718−84.329896)`
gives 32.740260 tokens/s. Total trial orchestration was 128.754 s, including
fixture preparation/reporting; it is distinct from 87.050 s request latency.
The complete 492-token Q1 generation timing remains explicitly qualified, and
its output length differs from Q2's 490 tokens.

Q2's four PASS rows and separate genuine output-contract failure remain unchanged.
After successful `read_file` integration, the tool continuation emitted **literal
write_file markup in assistant content**, not a structured API tool call, despite
`tool_choice=none`; retrieval answers were absent. **No write_file executed.**
Its original HARNESS_FAILURE is not the enclosing-fence issue, and these new
results do not establish tool reliability or code-analysis coverage.

Shared frozen fixture hashes/record counts match: `21964c48bd5d` / 87 (4K),
`f949c0180c3e` / 399 (16K retrieval/anchor), `e2dbe91cf975` / 393 (generation).
The new 256K fixture is `454d7892a5bf` / 6,627 records. Full hashes are in JSON;
exact requests regenerate with fresh nonces, explaining small input-count changes.
Q2 has no 64K or 256K baseline. Two 16K retrieval observations yield range/mean
variability of 1.55% TTFT / 1.75% output rate / 0.20% latency for Q1, versus
2.88% / 0.48% / 1.36% for Q2. These are not confidence intervals. Different CPU
allocation, TP and source revisions prevent a GPU-only causal speed claim.

**Measured memory.** GiB = 2³⁰ B; GB = 10⁹ B. Rounded native `GB` labels are
preserved, not converted into exact bytes: Q1 weight-load usage **28.72** at all
four pools; K/V labels are **0.13/0.13, 0.50/0.50, 2.00/2.00, 8.00/8.00**.
Configured context, configured pool and actual native BF16 allocation agree at
4,096/16,384/65,536/**262,144**. Allocation proofs and one discarded 2,343-input-token
warmup per load passed; warmup prefill is a cache-disabled derivation, not a
native evaluated counter. Numeric receipts were rehashed and bound to manifests
and observations. Successful-load raw logs are represented by saved upstream
hashes, without local copies to reparse; standalone workspace remains unknown.

| Q1 pool | Sampled load peak GiB | Warm used GiB | Request peak GiB | Lifecycle peak GiB | Warm cgroup GB | Warm PSS GB |
|---|---:|---:|---:|---:|---:|---:|
| 4,096 | 30.533 | 31.129 | 31.129 | 31.129 | 4.475 | 5.224 |
| 16,384 | 31.303 | 31.898 | 31.898 | 31.898 | 4.456 | 5.206 |
| 65,536 | 34.305 | 34.900 | 34.902 | 34.902 | 4.457 | 5.208 |
| 262,144 | 46.340 | 46.938 | 46.939 | 46.941 | 4.457 | 5.207 |

Q256 client load took 45.606 s. Its 45 pre-readiness samples span 35.979 s;
165 lifecycle samples span 182.725 s. Load/request sampled cgroup current peaks
were **4,388,352,000 / 4,578,885,632 B** (4.087/4.264 GiB); kernel cgroup lifetime
high-water was **4,645,113,856 B**, not a request-only peak. Warm PSS/cgroup were
**5,207,480,320 / 4,456,722,432 B** (4.850/4.151 GiB); readiness PSS was
5,135,050,752 B. PSS was quiescent only and is not added to cgroup usage.
Request minimum host MemAvailable was 867.802 GiB; sampled cgroup swap was zero.
This large host availability is not a minimum VM RAM requirement.

Q256 request coverage: **82 samples**, estimated **93.69%** by union of ±0.5 s
windows; maximum gap **1.078 s**, collection wall time **4.81%** of request time.
The smaller Q1 cases have 3/4/4/14/12 request samples, 89.2–94.9% coverage and
5.25–6.29% collection wall time. Peaks may be missed, and collection time is not
measured slowdown. Q2 warm GPU use was 16.859/16.891 GiB at 4K and
17.266/17.297 GiB at 16K; warm cgroup 7.542/7.510 GB and PSS 8.348/8.314 GB.
Its native K/V allocation and required-host decomposition remain unavailable.

The retained maximum sampled required host demand is **13,287,989,248 B
(13.288 GB)**, from the **failed initial Q1 4K loader**, not Q256 or a successful
load: 12,797,124,608 anon + 98,963,456 kernel + 391,901,184 retained file bytes;
its tracker recorded 52 samples / 64.22 s. Later warm 4K required components were
4,473,470,976 B. Required-demand receipts at 16K/64K/256K are unavailable.
Reclaimable cache is separate (zero at that loader peak); shared RSS is not
unique required RAM. Cold-load demand, absolute transient peak, separately sized
workspace and whole-VM RAM requirement remain unknown. Warm cgroup usage cannot
be used as a safe RAM cap.

**Untested capacity projections with the requested 10% margin.** Actual device
total is **102,641,958,912 B = 95.592773 GiB**. Q256 request used/free are
**50,400,854,016 / 51,573,161,984 B = 46.939453 / 48.031250 GiB**. The persistent
unavailable/reserved gap is **667,942,912 B = 0.622070 GiB**; total is not used +
free. Project directly measured free bytes. The final-estimate reserve is
**0.10 × actual total = 10,264,195,891.2 B = 9.559277 GiB**. The historical live
benchmark's 16 GiB gate is retained as provenance, not the final projection margin.

The observed 64K→256K warm slope is **65,738.67 B/token**, also matching the
request-peak delta: 12 GiB cache growth plus **38 MiB additional fixed-overhead
growth**. This is not a pure KV measurement. Earlier lifecycle slopes were
67,242.67 (4K→16K) and 65,621.33 B/token (16K→64K). Keep the observed extrapolation
separate from the **65,536 B/token cache-only hypothesis**. At the 256K request
anchor, cache-only accounting is 16 GiB KV plus 30.939453 GiB aggregate
weights/runtime/workspace; these fixed subcomponents cannot be separated exactly.

For each specified anchor and slope `s`, use
`used(N)=anchor_used+(N−262144)×s`,
`free(N)=anchor_free−(N−262144)×s`, and
`physical_max=262144+floor((anchor_free−0.10×total−extra_workspace)/s)`.

| Projection basis / anchor | 512K used / free GiB | Physical maximum tokens, 10% margin | With another 4 GiB workspace allowance |
|---|---:|---:|---:|
| Observed slope / request peak — primary | 62.989 / 31.982 | 890,525 | 825,191 |
| Observed slope / lifecycle peak — separate observation | 62.991 / 31.980 | 890,493 | 825,159 |
| Observed slope / warm — native handoff | 62.987 / 31.984 | 890,557 | 825,223 |
| Cache-only slope / request peak — root cross-check | 62.939 / 32.031 | 892,468 | 826,932 |

Thus the native handoff and root arithmetic agree once slope and anchor are
explicit: warm/request/lifecycle peaks differ by 2 MiB steps. The extra 4 GiB is
an illustrative allowance, not a measured workspace bound. All these maxima are
physical projections, not supported context limits.

Separately, a **0.8-total occupancy proxy including the unavailable device gap**
uses `262144+floor((anchor_free−0.20×total)/s)`. With the request anchor it yields
**734,389 tokens for observed slope** or **735,849 for cache-only**; conservative
lifecycle/observed gives 734,357. This reflects `mem_fraction_static=0.8` as a
policy screen, **not the verified SGLang allocator formula or an accepted maximum**.
Allocation rounding, other pools and growing workspace may tighten it further.

Retain **262,144 as the largest allocated/measured pool**, with the strict versus
semantic qualification above and only one retrieval fixture. Native positional
capacity 262,144 is distinct from **YaRN-extended 512K and larger contexts**.
512K has projected memory room under these assumptions, but no tested allocation,
speed or quality acceptance. No simultaneous GLM/Qwen feasibility follows.

**Exact identities and restoration.** Model: `Qwen/Qwen3.8-27B-FP8` at
`017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`. SGLang v0.5.19 source:
`0bcd822377da7b5718e674eaf9c870d349424dd1`; image digest:
`sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`.
Template SHA256: `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`.
Q1/Q256 use GPU UUID ending `52c163cc`, CPUs 96–111 (16); Q2 uses both recorded
UUIDs, CPUs 0–111 (112). Full identifiers are in JSON. FP8/BF16, disabled radix
cache, 2048-token prefill chunks, single request, disabled overlap/CUDA graphs
and YaRN factor 4 remain common. Q256 native argv differs from Q1/64K only in
context/pool size. These measurements used YaRN settings even inside the native
positional range; they do not establish a separate unextended-RoPE benchmark.

| Scope | Reviewed source | Canonical arm SHA256 |
|---|---|---|
| Q2 | `fbb0fbd74385bd8b4a70a26bb053ad1f3deb0969` | `5dbc4dcc75c65ce12aff7a36a83b1e99e2b8bd7683727ad7696bfacd23696d2b` |
| Q1 final / 64K | `92037adb208c59217f9953c97979e63403c65980` | `105735cd31bd12be578b5240852c67698e6d65afc04f202e70a41db71b44d960` |
| Q256 | `b750bb37dd3107cf5b1e7aaabe6237ebc435085c` | `328830179bfcd4488a1f7ecf23083126b472ef41d7f883a1174f177f65497af1` |

Q1's earlier 4K/16K source was `b2d8cfaed40b56351794eef3a46c5bfe7d3f56c4`.
Q256 failed-row SHA256 is
`0e28306969447642459452e17fcb7395dbdd1c0f8387d6ce25d66e49b176664f`;
response SHA256 is `c58d5e6db1e05f1fc3f9d0ef25a937a7054d18f9c8bfcbf2da196fa54b55c61d`;
semantic receipt raw SHA256 is
`f5d247b7ea6b7150cfa2ca8acbbc8849a2abee030f7b4e170b7f2a5b5a6ccd31`.
The saved native-parser replay/disposition, exact normalized answer and immutable
row/request/response/journal hashes verify. Protected/private traces stay outside Git.

Q256 measurement ended **17:14:09 UTC, RESTORED**, with subprocess exit **1**
preserving HARNESS_FAILURE; the completed Codex CLI exited **0**. Formal owner,
authenticated Worker1 LAN and service receipts verify original
`qwen38-27b-1000000-yarn4-tp2-bf16kv` running/boot-resume production restored,
control active/running and boot active/exited enabled, no owned containers,
benchmark listeners/host or held canonical lease. No recovery retry was required.
This is saved evidence, not a fresh live check.

Earlier Q1 automatic restoration failed with sanitized OwnerError; fresh-process
restore failed on an uninitialized canonical-lock baseline. Fresh capture enabled
the existing restoration tail to finish at **16:48:31 UTC** without restarting
healthy original production or changing source. Both failed receipts remain.
The initial 4K `/get_server_info` startup timeout also remains, with no accepted
measurement from that attempt. The original six-hour budget
**1789826207.34127–1789847807.34127** and all prior evidence/fixture entries are
unchanged; only Q256's new fixture/measurement was added in its separate task.

Reproduce the focused saved-data check with
`python3 scripts/bench/verify-q1-saved.py --tasks TASKS --output OUTPUT.json`.
The three saved Worker1 task folders must be present under `TASKS`; historical
Q1 and accepted Q256 source are read from their separate checkouts. No benchmark
modules changed during report integration. Only the bounded saved-data verifier
was rerun; no broad suite or live work. Root authorized feature-branch publication
and a PR targeting `milestone/server-completion-20260915`; the task handoff records
the final publication commit and PR separately from these historical measurements.
