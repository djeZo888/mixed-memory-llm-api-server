# REAL72 three-case follow-up — final results and retained warm pair, 2026-09-20

**Both models are retained warm under the current B3 keeper. All four retrieval requests passed; science was intentionally user-cancelled and remains incomplete.** All five logical requests were attempted, with no whole-benchmark quality PASS or production API acceptance claimed. Original `ad76` cleanup is historical; the final pair belongs to `b69`. [Data and evidence hashes](postrestart72-three-case-followup-20260920.json).

| Request | Native input / actual output (cap) | Outcome | Client any-TTFT / total, s | Native decode, tokens/s | Q client input / output proxies, tokens/s |
| --- | --- | --- | ---: | ---: | ---: |
| B1 G4K | 3539 / 152 (256) | Strict + semantic PASS | 52.030679 / 384.613731 | 0.454044 | — |
| B1 Qnear480K | 479487 / 82 (256) | Strict + semantic PASS | 249.336559 / 252.687414 | unavailable | 1923.051328 / 24.483755 |
| B2 science | 65 / unavailable (4096) | UserCancelled; raw transport failure | 4.701058 / 5281.832632 | 0.453594614 partial snapshot | — |
| B3 G65008 | 65008 / 68 (256) | Strict + semantic PASS | 925.867894 / 1073.688050 | 0.453261513 | — |
| B3 Qnear480K | 479487 / 82 (256) | Strict + semantic PASS | 250.053467 / 253.329167 | unavailable | 1917.537902 / 25.031979 |

B2's 2394 observed decode-progress counter is not final usage; final completion/reasoning/final-text counts remain unavailable. Q rates are client input/any-TTFT and `(completion−1)/(last−first output)` proxies, not native timing. Slow scientific decode is an observation, not a CPU72 causal fix or minimum-core finding.

B1/B2 source `ad76a6435dd6af2c95f7c47bd3d4453f58b43c69`, campaign `benchrun-p72b-20260920`, native session `01a0c049-bc7f-7a80-8191-ea1522cb2a6a`. This report repo was fast-forwarded to reviewed B3-only `b69bd5c2a34adb462ee87333e2a238bd1c05436d` with normal published `b88a358` ancestry. Saved 25-PASS source review was reused, not rerun. Saved final request/case summaries, sealed bindings and CONTROL action/closure receipts govern this update. B2 visible final-channel text was reviewed privately through the existing SSE parser; reasoning and headers were excluded. No timing reconstruction, results/progress stream, VM/endpoint/keeper IPC contact, implementation, tests, builds, profiling or inference occurred.

## Sealed plan and unchanged profile

| Case | Measured requests | Output caps | Status |
| --- | --- | --- | --- |
| B1 | Simultaneous G~4K retrieval + Qnear479487 | 256 each | Both complete |
| B2 | Exact finite-element scientific request; Q resident idle | 4096 including reasoning | UserCancelled; raw transport failure |
| B3 | Simultaneous G65008 retrieval + Qnear479487 | 256 each | Original NOT_RUN; fresh G/Q PASS |

The original plan has exactly five logical measurements. B1/B2 dispatched on `ad76`; B2 was partial. Its closed controller and canonical cleanup required a fresh reviewed B3-only reload at `b69`, with two additional discarded 32-output warmups before only the two B3 requests. B1/B2 were not rerun; the reload warmups are not measurements. No tuning, inference retry or best-run selection. Historical G64/Q82/etc are actual output counts, not caps. Absent explicit user override, slow decode, output cap or semantic/format outcomes do not cancel later cases. Actual faults stop; timeout advances only after exact verified owned drain and fresh safety proof. Each request receives 7200 s from HTTP dispatch. Six-hour admission starts with first measurement, excludes preparation and never clips admitted requests.

Science reuses `decode_diag.long_body` exactly, SHA256 `adfc0b6c1225ac5dc1f7e8ddb5c8022911c9a4551e48fd201d2228bc3abe86fe`; saved native recount confirms 65 input tokens. Cap 4096 includes reasoning; **OUTPUT_LIMIT does not mean a naturally completed answer**. Prior science 13.574729 native `(n−1)` t/s / 306.313486 s total was configured 65536, not 480000.

Both configured/native capacities 480000 are distinct from occupied context. G: GPU 0, UD-Q4_K_XL/N76/F16 KV, 72 threads and batch threads 72, guest CPUs 0–71, batch 2048/ubatch 512. Q: GPU 1, FP8/BF16 KV/YaRN4/chunk2048, eight allowed CPUs 0–7 shared with G. Allowed union 72, not 80; runtime process threads are separate. Both Mems 0–7. Image/model pins and bound profile hashes are in JSON; unchanged images/profiles.

Guest 72, eight NUMA nodes, configured 896 GiB. Host mask 0–63,72–79 covers 64 physical cores / 72 host logical threads; it proves neither individual-vCPU pinning nor actual RAM locality. Hard caps 640/32 GiB, sampled required-working-set **ESTIMATE** margin 15%, GPU reserve 16 GiB G / 10% Q. Current charge, lifetime charge peak, RSS and cache are nonadditive; estimate headroom is not a minimum-RAM claim.

## Completed B1

| Metric | G4K | Qnear480K |
| --- | ---: | ---: |
| Native input / actual output / occupied | 3539 / 152 / 3691 | 479487 / 82 / 479569 |
| Cap / owner terminal / cap reached | 256 / COMPLETE / no | 256 / COMPLETE / no |
| Strict exact JSON / optional single-fence semantic | PASS / PASS | PASS / PASS |
| Client TTFT any / reasoning / content, s | 52.030679 / 52.030679 / 267.877082 | 249.336559 / unavailable / 249.336559 |
| Client total, s | 384.613731 | 252.687414 |
| Native prompt, s / t/s | 51.919813 / 68.162803 | unavailable |
| Native decode, s / `(n−1)` t/s | 332.566911 / 0.454044 | unavailable |
| Native cached tokens | 0 | unavailable |
| Client input / any-TTFT, tokens/s (**proxy**) | — | 1923.051328 |
| Client `(completion−1)/(last−first output)`, tokens/s (**proxy**) | — | 24.483755 |

Both exact expected retrieval objects matched, with no outer fence removed. JSON retains expected START/MIDDLE/END marker identities and expected-object hashes from saved fixtures; per-position native token offsets are unavailable. Scoring is saved aggregate exact-match evidence, not a new raw-answer rescore. Literal API finish reasons and final-answer-only token counts were not retained and remain null. Both owner drains are VERIFIED_DRAIN; no retry.

Q native cache, evaluated prompt and prompt/decode timing are unavailable, never zero. JSON separately labels client input/TTFT and completion-minus-one/output-arrival-span proxies. G rolling native decode windows are unavailable: insufficient cumulative native progress. Its beginning/middle/end **SSE-event** rates 0.453850/0.445127/0.454156 events/s are not native token rates; an SSE event is not necessarily one token.

Dispatches were 1.950521 s apart. Request overlap 252.687414 s; arrival-based G-output/Q-prefill overlap 199.256401 s, both-output overlap 3.308316 s, G tail after Q drain 129.975796 s (Q idle). These are client phase proxies, not native decode-boundary proof. B3 final evidence below confirms Q completed during G prefill, with no simultaneous decode overlap.

## B2 — explicit cancellation, partial science

Root's execution override set boundary STOP at **21:15:40.331196 UTC**, then closed the exact identity-bound B2 TCP connection at **21:15:40.749105 UTC** (`ss -K`, rc0; tuple absent afterward; no signals). **UserCancelled** is operator authority/reason, separate from raw **TRANSPORT_FAILURE / STOP_NATIVE_OR_TRANSPORT**. The raw row still says **UNRESOLVED_TRANSPORT, drained=false**; it was not rewritten. `B2-case COMPLETE` means case processing ended, not a completed scientific answer. `deadline_expired=false`: this was neither the full 7200-second timeout nor an established model error.

| B2 metric | Saved evidence |
| --- | ---: |
| Client elapsed to transport failure | 5281.832632 s |
| Client TTFT any / reasoning / content | 4.701058 / 4.701058 / 42.103893 s |
| Last observed prompt progress / prompt time | 65 / 4.592720 s |
| Last observed decode progress / decode time | 2394 / 5275.635839 s |
| Observed cumulative native `(n−1)` rate | 0.453594614 tokens/s |
| Native rolling beginning / middle / end | 0.453571500 / 0.453565837 / 0.453646477 tokens/s |
| Final completion / reasoning / final-text token counts | unavailable |
| Cap / final finish reason / final usage | 4096 / unavailable / absent |

The 65/2394 snapshot is **observed cumulative progress, not final usage**. Final native prompt/decode summary fields remain unavailable; three saved rolling counter windows are valid only over their observed intervals. No DONE was captured; response/event capture is incomplete. The 2394 SSE events do not prove one token per event. Q was resident idle.

Private review found a coherent organized **incomplete tutorial fragment**, with no obvious repetition or gibberish. It covers the PDE, weak formulation, boundary conditions, functional setting and Galerkin discretization, then cuts off mid-item during matrix assembly's connectivity/scatter-add explanation. The worked 1D example, error estimation and practical pitfalls were not reached. Some formulation wording and assumptions need review; this is basic coverage/coherence inspection, **not scientific correctness acceptance**. Character length 7133 is not a token count. Raw visible text, reasoning and headers are excluded from the report.

## Fresh B3 continuation — completed pair

Campaign `benchrun-p72b3-20260920`, native session `01a0c0b6-2901-7943-acbd-dd02d87b7e29`, source `b69bd5c` loaded the unchanged pair once after original cleanup. Native CLI exited 0 at **21:33:27.902627 UTC**; B3 admission began about 21:36:51 UTC. Fresh native counts confirm G 65008/Q 479487, configured 480000 each. Both retrieval caps 256; actual outputs 68/82. No extra 512-output case, retries or B1/B2 rerun.

| Final B3 metric | G65008 | Qnear480K |
| --- | ---: | ---: |
| Input / actual completion / occupied | 65008 / 68 / 65076 | 479487 / 82 / 479569 |
| Strict / optional single-fence semantic | PASS / PASS | PASS / PASS |
| Native prompt seconds / tokens/s | 925.733888 / 70.223204 | unavailable |
| Native decode seconds / `(n−1)` tokens/s | 147.817536 / 0.453261513 | unavailable |
| Client any / reasoning / content TTFT, s | 925.867894 / 925.867894 / 937.061412 | 250.053467 / unavailable / 250.053467 |
| Client total, s | 1073.688050 | 253.329167 |
| Native cached tokens | 0 | unavailable |
| Owner terminal / drain | COMPLETE / VERIFIED_DRAIN | COMPLETE / VERIFIED_DRAIN |

Both exact retrieval objects matched without fence removal. Final answer-only token counts and literal API finish reasons are absent in saved final summaries; caps were not reached. Q proxies remain separately labelled in the leading table. G final native counters establish 68 completion tokens, unlike B2's unfinished 2394-progress snapshot. G rolling native windows are unavailable; SSE beginning/middle/end 0.431747/0.454010/0.454404 are events/s, not token rates.

Actual request overlap was 253.329167 s. Q completed entirely during G prefill: prefill/prefill proxy overlap 250.053467 s, G-prefill/Q-output 3.235861 s, output/output 0 s. G continued 818.407613 s after Q drain with Q idle; Q tail after G was 0. These are saved client arrival phase proxies, consistent with G's 925.733888 s native prefill. They provide no simultaneous G-decode contention result. Current B3 request/profile hashes are distinct from the original unexecuted B3 bindings.

## Precomputed CPU and resource coverage

Mean / elapsed-time-weighted interval p95 core-equivalents below use existing aggregates; phases use client arrival boundaries. B2 prefill has only 3 intervals; its output proxy is sustained, with G 151 runtime threads and Q 32/1/55/19 across four processes, distinct from allowed 72/shared 8 CPUs. CPU span coverage and point telemetry coverage differ; all CPU phase summaries remain PARTIAL despite complete counter inventory.

| Window | CPU intervals / span coverage | G mean / p95 | Q mean / p95 | Point telemetry coverage |
| --- | --- | ---: | ---: | ---: |
| B1-G4K prefill_proxy | 44 / 99.507% | 1.000 / 1.001 | 1.022 / 1.029 | 85.059% |
| B1-G4K decode_proxy | 274 / 99.377% | 70.490 / 70.876 | 1.002 / 1.003 | 83.247% |
| B1-G4K request | 321 / 99.757% | 61.069 / 70.872 | 1.005 / 1.005 | 83.611% |
| B1-Qnear480K prefill_proxy | 211 / 99.900% | 56.491 / 70.869 | 1.006 / 1.005 | 84.725% |
| B1-Qnear480K decode_proxy | 1 / 36.164% | 70.797 / 70.797 | 1.009 / 1.009 | 60.454% |
| B1-Qnear480K request | 213 / 99.522% | 56.628 / 70.869 | 1.006 / 1.005 | 84.550% |
| B2-Gscience prefill_proxy | 3 / 74.323% | 1.000 / 1.000 | 1.004 / 1.004 | 75.980% |
| B2-Gscience decode_proxy | 4371 / 99.983% | 70.625 / 70.880 | 1.002 / 1.003 | 82.863% |
| B2-Gscience request | 4376 / 99.977% | 70.563 / 70.880 | 1.002 / 1.003 | 82.861% |
| B3-Qnear480K prefill_proxy | 215 / 99.564% | 1.000 / 1.001 | 1.008 / 1.005 | 86.239% |
| B3-Qnear480K decode_proxy | 2 / 72.069% | 1.000 / 1.001 | 1.015 / 1.015 | 84.176% |
| B3-Qnear480K request | 218 / 99.659% | 1.000 / 1.001 | 1.008 / 1.005 | 86.308% |
| B3-G65008 prefill_proxy | 795 / 99.939% | 1.000 / 1.001 | 1.005 / 1.005 | 85.927% |
| B3-G65008 decode_proxy | 121 / 99.355% | 70.525 / 70.883 | 1.002 / 1.003 | 83.585% |
| B3-G65008 request | 919 / 99.991% | 10.566 / 70.797 | 1.005 / 1.005 | 85.603% |

B1 Q output has one CPU interval (1.196417 s of 3.308316 s); its p95 is particularly weak. B3 Q output has only 2 intervals, so its output p95 is also coarse; G values in B3-Q rows describe the Q request window; B3-G rows describe the completed G request. The long G prefill hides its high output-phase CPU mean in whole-request averages. Core-equivalents include spin, not proof of useful work or cores needed. Guest/process/cgroup channels overlap. Runtime threads, guest totals, PSI, throttling and sampled GPU utilization/power/memory are in JSON. Owned-cgroup throttle deltas are zero in observed intervals; inherited quota and global CPU-full PSI are unavailable. Guest steal uses existing whole-request USER_HZ counter extrema/deltas; phase rate aggregates are unavailable. Counters named host describe the guest, not Proxmox.

Independent extrema over each G request window (Q active time plus idle tail), binary GiB; initial G1/Q1 rows are B1:

| Model | GPU used max / free min | Process RSS max | Cgroup current max / lifetime peak | Charged file max | Retained estimate / ×1.15 |
| --- | ---: | ---: | ---: | ---: | ---: |
| G1 | 77.971 / 17.001 | 401.455 | 408.366 / 412.274 | 405.755 | 403.168 / 463.643 |
| Q1 | 60.045 / 34.926 | 5.972 | 4.338 / 12.483 | 0.166 | 13.904 / 15.990 |
| B3 G1 | 77.971 / 17.001 | 401.472 | 409.159 / 411.857 | 406.531 | 403.185 / 463.663 |
| B3 Q1 | 60.045 / 34.926 | 5.972 | 4.238 / 12.389 | 0.069 | 11.145 / 12.817 |

Per-phase extrema and availability counts are in JSON. Lifetime peak and retained estimate may predate a request; RSS can double count shared pages, while file/mapped/shmem do not establish reclaimability. Collection wall time is not measured inference perturbation; sampled peaks are not absolute peaks.

## Baseline comparison

Prior published REAL72 G3538/output256 with Q idle: 626.918232 s total, native prefill 67.395964 t/s and decode 0.444114 t/s. B1 output 152 and active Q differ: compare rates and coverage, not totals alone. Old fast 4K 12.641392 t/s/ 63.22248 s total used configured 4096, a capacity confound. Prior 112 G65008/output64: 941.819041584 s total, 927.980198 s prompt, 13.718008 s decode, 4.592504 `(n−1)` t/s; Q479487/output87: 253.166461 s total / 249.665222 s TTFT. One pair, new nonces, topology, peer activity and output lengths prevent causal conclusions. Old reports unchanged; no 96WIP merge.

Relative to the prior 112 baseline, G native prefill was 70.223 versus 70.053 tokens/s (0.24% faster); client total increased 14.0% with different 68 versus 64 actual outputs. Q elapsed increased 0.064% (82 versus 87 outputs). CPU-reduction causality remains unproved.

The earlier keeper release and one new pair load remain historical facts, without tuning. RUN native exited 0 at 19:36:48.708091 UTC. Following the later intentional B2 cancellation, saved RUN is **RESTORED** and the final canonical receipt is **RESTORED_WITH_MEASUREMENT_FAILURE, STOPPED/manual**, with authenticated Worker1 verification. CONTROL's 21:18:05.253440 UTC absence proof establishes both exact model containers and all recorded backend process generations absent; keeper/SSH ended, tunnels closed and lease free. Native slot-idle was not captured before removal; earlier unavailable-slot/ambiguous-inspect observations alone were not closure proof. The historical B2 registration and unresolved raw transport row remain unchanged.

## Current warm retention

The original pair's **RESTORED** state belongs to the cancelled `ad76` campaign. The fresh `b69` pair is now **HELD**, guarded, with no active inference or review/unavailable reasons and its canonical lease retained. Existing remote checkpoints at **22:00:09.655193** and **22:01:44.062647 UTC on 2026-09-20** advance after the actual CLI exit. Saved warm-hold pair IDs, source/session/owner bindings, status receipt hash and release template agree; Worker1 keeper 71966 and its SSH child 71972 were alive. The small periodic checkpoints do not themselves repeat identities; their stable budget and task-local receipt chain bind them to the retained pair. Full small receipts and final verification are preserved off-VM, privately hashed.

**mac-worker1 must remain online** to retain keeper/SSH/tunnels. Future GO is null; no further inference is authorized. This sealed controller supports status and an explicitly authorized bound release to STOPPED/manual, not arbitrary warm followups. The private 0600 task-root handoff records exact task/control/status/release-template paths and keeper/SSH/owner/session/source IDs. Timestamped warm retention is not production API acceptance. Only the two reports are committed over reviewed b69; source bytes are unchanged and no implementation tests were rerun. Publication follows root review.
