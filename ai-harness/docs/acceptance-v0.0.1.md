# ai-harness v0.0.1 acceptance

**Overall: BOUNDED_ACCEPTANCE_WITH_LIMITATIONS** — 2026-09-22, task
`H001-ACCEPTANCE-DOCS-20260922`. Final V2 Stop, same-chat follow-up and health
passed; historical failures, qualifications and unexecuted cases remain explicit.
This documentation task performs no live requests, builds or tests.
See the [machine-readable receipt](acceptance-v0.0.1.json) for exact case/source mappings.

## Release evolution

| Identity | Value |
| --- | --- |
| Initial tested app | `10dea3e406d6de88a1af152ff99124572c9e3fca` |
| Initial release | `/home/user/.local/share/ai-harness-app/releases/10dea3e406d6de88a1af152ff99124572c9e3fca/ai-harness` |
| Delete/lifecycle app; also docs source base | `d58020ca18147d7356d1459c1615532cebef1051` — activated 02:54:17 UTC |
| Final V2 app | `765995539e5298a08c4146b8eef9f2f91ed22111` — activated 03:08:50 UTC |
| V2 candidate | `29e29b6659b255664fcf24b9166ca5eb82dbfe76` |
| Engine image SHA-256 | `84ea979312f7743d9ab789465aae7adde92f97d6169744ec7b63776a9482b227` |
| MiniMax base | `ae65651df5f97ae1085ab4e19964f4b78c769a4e` |
| Engine patchset SHA-256 | `8d3575bc32df22794dea977a4daad75406f617f1a3a4787a739b0fbd651bb034` |

Final V2 activation retained the engine image, web and dependencies. Docs remain
on the original `d58020ca` base; that is not the final tested app revision.
Later ROOT notes supersede earlier pending/candidate status and token wording.

## Cases

LIVE_PASS/LIVE_FAIL are observed outcomes; FIXTURE_PASS is controlled evidence.
NOT_EXECUTED is unexercised; PENDING awaits evidence. Reconstructed-only success
is explicitly qualified. Cases use the initial app unless another revision is shown;
the runtime and tokenizer checks have no inference. Source keys resolve in JSON.

| Case | Result | Evidence and boundary |
| --- | --- | --- |
| Initial readiness | LIVE_PASS | HTTP port 80 health/static 200, host/gateway loopback, invalid Host/Origin rejected; transient startup 502 retained. (core) |
| Chat/progress/reconnect/follow-up | LIVE_PASS | Active reload, progress and remembered follow-up facts; no duplicate message IDs. (core, ui, ui_summary) |
| Original history retention | LIVE_PASS | Four initial native/API records retain both prompts; separate from compression. (history, ui) |
| Image upload and follow-up | LIVE_PASS | Synthetic shapes/colors recognized and recalled; no general format or per-endpoint coverage claim. (ui, ui_summary) |
| PDF text and local OCR | LIVE_PASS | Two-page text facts/boundaries and local scan OCR independently checked. (ui) |
| Basic PDF creation/artifacts | LIVE_PASS | One-page PDF heading/table/totals, visual and registered download checks. (ui, ui_summary) |
| Search and rendered public page | LIVE_PASS | Three relevant W3C results and native rendered page; this query had no engine-unavailable warning, not a provider-wide health claim. (ui) |
| Public PDF download | LIVE_PASS | Initial frame-reference attempt failed; supported visual-position click downloaded 13264 bytes; independent PDF checks passed; UI filename was UUID. (ui, ui_summary) |
| Python/C++/Node coding | LIVE_PASS | Three native child delegations and actual edits/tests; external before-fail/after-pass Python 7/Node 8/C++ 9 cases; three implementation files changed, supplied tests unchanged. (coding_before, coding_after, coding_files, coding_tools) |
| Background-only overlap | LIVE_PASS | 24 samples with two active inference lanes at 02:16:05-02:16:29 UTC; parent settled 02:16:38. (root) |
| Three concurrent chats | LIVE_PASS | 11 samples with three app runs/two inference lanes; all completed. (root) |
| Exact FIFO ordering | FIXTURE_PASS | Exact FIFO has fixture coverage only, not live instrumentation. (root) |
| Main context estimate | LIVE_PASS | Estimated main usage consistency, not independent complete-wire token reconstruction. (root, context) |
| Representative tokenizer reconstruction | LIVE_PASS_RECONSTRUCTED_ONLY | Representative reconstructed prompt: 15,375 tokens, HTTP 200; original body unavailable, not equivalence or a three-token estimator error. (root2, tokenizer) |
| Output configuration | LIVE_PASS | Prepared native envelope maxTokens 65536; not a full-output generation case. (context, budget) |
| Stop cleanup and same-chat new task | LIVE_PASS | Cancelled state and cleanup, then explicit same-chat new task completed; retained files/history. (ui) |
| Initial intentional-Stop error semantics | LIVE_FAIL | Intentional cancellation emitted spurious engine_failed. (ui) |
| Upstream drain observation | LIVE_PASS | Inference lane outlived cancelled app work and later settled; configured ceiling 65536 via unchanged path; original Stop wire body not retained; text request is not a hard cap. (root, fix, drain, budget) |
| Initial active Delete | LIVE_FAIL | Actual active Delete returned 400; no deletion accepted. (ui) |
| Files after successful Delete | LIVE_PASS | `d58020c`; Original chat idle; shared PDF and both markers retain exact bytes/hashes; original registered PDF download 29,461 bytes. Hashes below. (ui_recheck, ui_recheck_data, root5) |
| Shared-workspace handoff | LIVE_PASS | Shared workspace marker/hash, prior facts and old history retained. (ui, ui_summary) |
| First Stop/Delete source regressions | FIXTURE_PASS | Prior Stop 14 focused/115 regressions; Delete 3/3 and real-parser 400 to 202; fixtures did not establish live Stop correction. (fix, ui) |
| First corrected Stop error semantics | LIVE_FAIL | `d58020c`; Tiny Stop still emitted engine_failed despite cancelled guard, exact cleanup and idle lanes. Fixtures reproduce missing branches; generic live error does not identify the exact throw. (stop_recheck, root5) |
| Cancellation error during successful Delete | LIVE_FAIL | `d58020c`; Successful deletion still emitted the older engine_failed; preserved separately from deletion/preservation success. (ui_recheck, root5) |
| V2 Stop source regressions | FIXTURE_PASS | `29e29b6`; 20 focused checks passed; nine new cases failed on the prior candidate. Candidate 29e29b6 integrated as 7659955; prior typecheck/build receipts only. (stop_v2, root5) |
| V2 tiny Stop and cleanup | LIVE_PASS | `7659955`; One tiny first-delta Stop cancelled with no new error events; exact container died/removed and absent. Both lanes idle before follow-up; primary cleanup proof and capture limits below. (root_final, final_core, final_cleanup) |
| V2 same-chat follow-up | LIVE_PASS | `7659955`; Explicit same-chat follow-up returned 42 at 03:11:21.069 UTC with the same native session and settled guard; no new run errors. (root_final, final_core, final_readiness) |
| Final health | LIVE_PASS | `7659955`; At 03:12:00 UTC exact final app active; HTTP 80 health/static and loopback API 200, ports 8080/8081 loopback, both lanes idle, zero active app runs. An idle reusable follow-up runner may remain. (root_final, final_core, final_readiness) |
| Corrected-source active Delete | LIVE_PASS | `d58020c`; Real active Delete 202 then GET 404, DB deleted, run cancelled and cleanup; older spurious cancellation error still emitted. (ui_recheck, root5) |
| Clean restart/resume | LIVE_PASS | `d58020c`; Root-reviewed clean restart/resume passed; incomplete compact file is not the authority. (root5) |
| Controlled app crash/no replay | LIVE_PASS | `d58020c`; Sole active run, counter 1 and idle lanes before crash; after restart interrupted/quarantined, counter still 1, old container absent. One controlled case. (root5, crash) |
| Installed runtime/tools/ACP/cleanup | LIVE_PASS | Real runtime/tools, ACP initialize/session/settlement and owned-container termination; no live model case. (runtime) |
| Manual native compaction | LIVE_PASS | Corrected three-turn manual native probe: native-reported estimate 14,580 to 13,311, not independently measured occupancy; summary 2,297 input/310 output; same profile reopened, exact facts/latest 12 MHz recalled. (root3, compaction, compaction_data) |
| Compaction follow-up no-tool compliance | LIVE_FAIL | Unavailable todo_write attempted/rejected; no execution or retrieval supplied answers; factual recall remains valid. (root3, compaction, compaction_data) |
| Web compression rendering | NOT_EXECUTED | Manual native probe did not exercise web compression rendering. (compaction, compaction_data) |
| Full 480,000 occupied context | NOT_EXECUTED | No full occupied-context acceptance. (root) |
| Automatic compression at 412,416 | NOT_EXECUTED | Production automatic threshold unexercised; separate from manual compaction and retained history. (root) |
| Full 65,536-token generation | NOT_EXECUTED | No full-output generation claim. (core) |
| Two-hour streaming | NOT_EXECUTED | No two-hour live stream claim. (scope limit) |

## Preserved evidence and limits

Successful Delete preserved the 29,461-byte PDF SHA-256
`bd4c62fc3953b52674b6259c7a3ca74a58b25f0312dd85fcd026d58c1fc72ff3`;
both marker files retained `20b6f9be7c63406cfd37d5323c3e15d0bee80635018ac3ac05e58dce97a9e53c`.
Manual compaction retained the exact original six-message snapshot/hash
`d46a339629be9a24fd89a4bbaf10de9f4c4a05c5555842d336da37023d4fa426` and display history.
The first two-turn fixture preserved the last two queries by design. A later
selector mistake chose a metadata sidecar; selecting the exact snapshot and
reopening the same profile completed evidence/recall without repeat compaction.
These are fixture/evidence qualifications, not production compression defects.

Fixed limits remain 480,000 context, 65,536 output and two Qwen inference slots.
Output reservation puts normal automatic compression near 412,416 input tokens.
Native automatic compression is supported; CLI slash commands remain unsupported
in the web integration. Manual native success proves neither that threshold nor
web compression rendering. Context values are native estimates; original usage
15,378 input + 23 output = ACP 15,401 is not independent complete-wire counting.

Stop/container cleanup does not establish upstream idleness. One observed drain
lasted roughly 12 minutes with 26,830 completion tokens despite a textual request
for fewer than 1,800. The unchanged provider/gateway configured ceiling was 65,536;
the original Stop wire body was unavailable. The tiny V2 pass does not erase this.
Final cleanup rests on exact Podman create/died/remove events and container absence.
The sampler expired before submission: numeric init PID was not captured, and the
process scan had one unreadable/racing entry. Exact cgroup/launcher checks complement
that proof; no exhaustive process-table or zero-containers-after-follow-up claim.

## CI and provenance

Root-reviewed client-regressions and deterministic-worker-tests passed. The missing
acceptance-report target is supplied here; repository-sanity rerun remains pending.
Installer fixtures retain a pre-existing main TMPDIR failure in
`test_real_stage_entrypoint_order_and_second_verified_noop`: 313 tests, 1 failure,
1 skip, baseline `72dffca67f45a7012d77a51b86984502b292a68d`. Deferred and untouched;
no all-CI-green claim or new test execution.

`SOURCE-MAP.json` maps external receipts; full paths are in the JSON. CORE, UI,
RUNTIME and COMPACTION task receipts stay outside Git. `ROOT-INTERIM.md` through
`ROOT-INTERIM-5.md` supply reviewed chronology and correct compaction's stronger
“measured” wording to native-reported context/estimate. `FINAL-STOP-RECEIPT.md`
and `FINAL-CORE-STOP-RESULT.md` close final Stop/follow-up/health and supersede the
earlier activation time with 03:08:50 UTC. This is bounded acceptance, not all-pass.
