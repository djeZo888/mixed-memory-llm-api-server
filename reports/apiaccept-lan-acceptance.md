# Independent LAN API acceptance — 2026-09-17

**API acceptance complete, including independent postboot LAN PASS.** Latest
cutoff: 2026-09-17T08:06:22.492747Z. This completion excludes cleanup and overall
project completion.

Evidence root: private sibling `APIACCEPT`; artifact paths in
[`apiaccept-evidence/summary.json`](apiaccept-evidence/summary.json) are relative
to it unless explicitly coordinator-relative. Sources: `result.md`, `status.json`,
`progress.md`, `telemetry-summary.md` and the postboot result. Raw evidence and
private values remain private. Documentation-only: no new tests or requests.

Postboot: exactly **four requests PASS**: authenticated control Qwen ready
(generation 6), native missing-key **401**, authenticated exact `qwen3.8-27b`
model, and one short streamed completion matching expected content. Evidence:
`private/cases/postboot-f_copxuw/postboot-result.json`. Terminal release recorded
no active/inflight requests; ownership returned to Worker1 C1, with no further
APIACCEPT requests after release.

Worker1 supplied reboot handoff: normal reboot **07:57:22.475249 UTC**, changed
boot identity, same Qwen container/pinned image auto-resumed with a new process;
guards/GPU/source/receipt/key preservation **PASS**. These are supplied host facts;
the postboot LAN checks have independent saved live artifacts.

Authenticated catalog/status **PASS**, with exactly two profiles:

| Model / served alias | Exact profile | Configured context |
| --- | --- | ---: |
| GLM5.3 UD-Q4_K_XL / `glm-5.3` | `glm-5.3-ud-q4-k-xl-n76-native1m` | 1,048,576 |
| Qwen3.8-27B FP8 / `qwen3.8-27b` | `qwen38-27b-1000000-yarn4-tp2-bf16kv` | 1,000,000 |

Wrong dedicated control key returned **401**; stale-generation switch returned
**409 `stale_state`**, preserving selection/identity/generation/operations.
Qwen→GLM **PASS, 308.041 s**; GLM→Qwen **PASS, 88.192 s**. These are completed
operation durations including transitions/loading, not isolated weight-load
measurements. Identical idempotent replay **PASS**: original succeeded operation,
`replayed:true`, unchanged identity/generation. HTTP 202 alone was not acceptance.
First control leg: 27 calls, including 17 polls and one new load; return operation:
two polls. These are scoped counts, not a session-wide request total.

Native auth, model list, chat/SSE and real tools passed for both models.
GLM A1 **all 11 PASS, 52.764 s**; real OpenCode **all 8 PASS, 128.042 s** agent
time (132.773 s wrapper). Checks covered reads, edit, exact test command, passing
tool result, final response, immutable tests, independent final check and cleanup.

Original Qwen A1 **FAIL** remains preserved: invalid alias returned 200. Auth,
chat/SSE and real read/edit/test agent passed (6.953 s agent; 8.085 s suite).
Original OpenCode whitespace-fragment verifier **FAIL** remains preserved
(11.970 s agent; 16.694 s wrapper); corrected **offline original-events replay
PASS**, retaining all eight original real functional/integrity checks. No agent
rerun occurred.

Those rich Qwen client/context runs used the predecessor launcher. Corrected
source `ab6daa475cc2f1c04956d862f460f9f01c4ee952` has accepted Worker1 genuine
native-pair/extension proofs plus completed narrow LAN regression. The original
invalid-alias reproduction returned native top-level **400 `BadRequestError`**.
A task-local checker wrongly expected a nested error envelope: its **FAIL** is
preserved alongside **offline contract PASS**, without request retry/runtime
change. Valid streamed real `read_file` and genuine tool-result continuation,
correct interpretation and strict JSON all **PASS**: input/output 406/26 then
188/17; wall 0.900634/0.522790 s. These do not constitute a rich-suite rerun.

Both retrieval cases passed real tool use, genuine continuation, early/middle/late
retrieval and strict JSON; effort GLM `low`, Qwen `none`, reserve 8,192:

| Retrieval case | Input, first / continuation | Output, first / continuation | Case elapsed |
| --- | ---: | ---: | ---: |
| GLM | 4,154 / 4,196 | 13 / 45 | 74.827 s |
| Qwen | 144,244 / 144,026 | 26 / 54 | 47.611 s |

Initial native pre-counts matched usage; continuation counts are returned usage.
GLM ordinary OpenCode inputs reached 5,791 by client input+cache counters, not
independent native pre-count; **4,196 is only its retrieval maximum**. Qwen's
accepted native 1,000,000-token pool is capacity evidence, separate from occupied
proof. Neither case establishes occupied-million-token reasoning. No retry,
ladder or near-cap case; preparation including waits: GLM 666.850 s, Qwen
922.805 s. A1 raw wire unavailable; context streams retained privately.

GLM returned native prompt rates **69.299 / 34.703 tokens/s** over **4,104 / 30
evaluated tokens**, separately **50 / 4,166 cached**. Native decode **1.507 /
6.906 tokens/s** uses server `(n−1)/seconds`; request wall **67.408 / 7.271 s**.
Cached continuation is not cold-prefill performance. Qwen native prefill/decode,
cache timing and TTFT unavailable; retrieval wall **23.285 / 24.181 s**, output
end-to-end **1.117 / 2.233 tokens/s**. GLM TTFT unavailable. No benchmark claim.

Coordinator-supplied existing Worker1 telemetry (`telemetry-summary.md`): Qwen
46 in-window samples, maximum interior gap 1.1365 s, none >2 s; last sample
**1.7859 s before terminal**. Sampler stopped early at 06:51:33.695 UTC through
broad cancel-text matching; replacement samples were after the case and excluded.
Sampled GPU maxima 48,518/48,550 MiB, both 100% utilization; minimum MemAvailable
864.63 GiB; maximum model cgroup 7.23 GiB; host/cgroup swap 0, OOM delta 0.

GLM: 75 samples, maximum gap 1.1715 s, none >2 s; final sample 0.056 s before
terminal; sampled GPU maxima 65,032/73,488 MiB; minimum MemAvailable 460.50 GiB;
OOM counters 0. Semantic case **PASS**; strict zero-swap
**NOT_PASS_NONZERO_CGROUP_SWAP**: cgroup **32 KiB** throughout versus **248 KiB**
immediately before; host **16.75 MiB**. Individual PID VmSwap **NOT_MEASURED**.
No observed pressure growth/OOM or swap increase; no cause attribution. Sampled
peaks are not absolute or continuous-coverage proof. These limitations do not
erase real functional PASS.
