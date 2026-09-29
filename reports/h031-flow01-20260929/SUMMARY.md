# H031 FLOW01 bounded Qwen acceptance

Six accepted runs settled; the integration remains incomplete because the original PDF workflow failed. No application source, build, deployment, model lifecycle or VM configuration changed in this task. The app remains exact `2b40610e937ad6256450e055ffd1d5647997f4c5`; the isolated checkout remains `70e3e7c1e59eb846eab65f16c11215c000f79351`.

| Actual case | Result |
|---|---|
| Retained original same-thread continuation | PASS: native Python assertion/exit0, exact follow-up line, three unchanged files. This did not induce a new H031 app restart. |
| Original PDF | FAIL: installed helper extracted/rendered page1; original source unchanged. No summary PDF or requested numeric final answer. Native image viewing reported unsupported image input; later final provider response stopped with no tool call. No retry or prompt rescue. |
| Codex to MiniMax handoff | PASS: fresh target native history, actual file reads and Python assertion/exit0; original history/files preserved. |
| Both480K lanes | PASS for small actual workflow requests; simultaneous counting ownership sampled on both lanes. No480K prefill/benchmark. |
| Shared-workspace serialization and queued Stop | PASS: queued Codex waited behind active MiniMax and was cancelled before provider dispatch. |
| Active Stop | PASS for active continuation cancellation and source-bound drain/cleanup. The native sleep had already ended; interruption of sleep remains NOT_TESTED. |
| SSE reconnect | PASS for internal API cursor replay on the same run. Browser UI reconnect was not tested. |

Global specialist gates and MiMo candidate flags stayed closed. Image/frontier tasks were not authorized. Unhealthy-lane fallback, shared gateway queue depth, fresh restart and remaining profile/release gates remain NOT_TESTED. Ordinary coding/follow-up/dedupe/compaction/recall results were reused.

The initial pre-POST hold was preserved until root10:10 GO bound W1's definitive no-more-writes10:09:58. One deployed Qwen-specific verifier per480K lane passed before admission; no tokenization/inference occurred in that preflight. Each consequential POST had a prior standalone INBOX read and explicit acknowledgment. No unchanged submission was retried.

Final10:27 app/ledger readback: zero active runs, pending gateway requests, native task containers or scoped tickets; historical uncertainowners2/quarantines3 preserved. Public chat503/status200; appPID118087/statusPID14480 and MiniMax default unchanged. Final10:28 file and history hashes match. Temporary cancellation quarantine/draining observations were preserved and settled by normal cleanup; no manual clearing occurred.

The continuation's extra claim that followup.txt was18bytes is inaccurate; actual preserved length is22bytes. This did not change the requested exact line or files. Detailed actual failures and scope limits are recorded separately in the result files.

`RESULT.json` lists every session/run/submission/ticket and source binding. `COLD-RESULT.json`, `PDF-RESULT.json`, `HANDOFF-RESULT.json`, `STOP-RESULT.json`, `TWO-LANE-RESULT.json`, `SSE-RECONNECT.json`, `FINAL-STATE.json` and `FINAL-PRESERVATION.json` contain sanitized evidence. Private raw provider/native captures and task adapters remain outside this bundle. CHECKPOINT.json is the retained initial preparation checkpoint, superseded by RESULT.json.

No GitHub push or main merge occurred. A report-only commit and importable SOURCE.bundle are exported with prerequisite70e3e7c1e59eb846eab65f16c11215c000f79351. Runtime/application source remains unchanged. The wrapper's real exit-code and finished-utc are terminal authority and must be read after the native task exits; this report does not fabricate them. Root owns publication and any later authorization.
