# H029 Worker2 — source, deployment and two failed acceptance gates

The ordinary Codex tool workflow remains **unqualified**. Both accepted attempts failed identity verification before generation; neither produced tools or artifacts. The second attempt captured an HTTP subtype but did not repair or explain the historical failure.

| Checkpoint | Source | Result |
| --- | --- | --- |
| APP01 | b7cd5bad (integrated fbb2eee) | Submission-ID/atomic acceptance/UI source and local checks passed; no live inference |
| DEPLOY01 | 0d924679 | App-only activation passed at 02:05:48 UTC; live acceptance not run in that session |
| ACCEPT01 | 0d924679 | FAIL: count/control_before transport, 9,145 ms; subtype not recoverable |
| ACCEPT02 | 2662bd08 | Diagnostic app activation passed at 02:42:06 UTC; FAIL at count/control_after: HTTP 409 target_unavailable, 9,357 ms |

APP01 fixes stable submission intent, canonical conflicts, atomic initial persistence and explicit UI retries. Its server/web focused results were 76/56 passed; final affected checks were 10/7 passed. These counts overlap and must not be added. Server/web builds passed. DEPLOY01's 19 combined and seven overlapping policy checks passed. ACCEPT02 built only the server using cached dependencies and exact retained APP01 web bytes. Its reviewed 11 diagnostic fixtures/typecheck were reused for the exact source. No native image or web rebuild occurred in ACCEPT02.

Both live attempts passed admission for both 480K lanes and selected Qwen0. ACCEPT01 failed before tokenization; ACCEPT02 reached one tokenizer POST and local response validation, then failed the later verification. This tokenization conclusion follows the exact source path; raw token count/response was not captured. Neither dispatched generation, so provider finish_reason and usage are absent. No actual artifact repair or independent Python assertion ran.

Each live case retained one submission, run, user message, native task and gateway request, with 14 events. Active and **interrupted-terminal** same-ID replay passed; changed text, attachments and image references returned 409 without additional dispatch. **Completed-run** replay remains NOT_TESTED. Followup, original H021 PDF and compaction were not run after either first-gate failure. Existing healthy-lane survival fixtures passed; no live failure injection occurred.

Both owned attempts settled through the source-bound broker/native cleanup and gateway authority. Consumed tickets were removed; historical uncertain owners and quarantines were preserved. ACCEPT02 final app/status/ownership health passed at 02:54:24 UTC, with app PID 44539 and unchanged H028 status PID 14480. All 36,613 original rows across 25 checked tables were preserved under the documented normal startup exceptions. No active runs, pending gateway requests or task containers remained.

The safe diagnostic records distinguish ACCEPT02's `http_status / 409 / target_unavailable` at count/control_after from ACCEPT01's unknown count/control_before transport subtype. The control service's underlying reason remains unknown, and the new result does not retroactively diagnose ACCEPT01. W1's separate masking correction was rolled back; original control code remained at this checkpoint. Full launch-fingerprint equivalence was not established. Later W1 work is outside this report.

MiniMax remains default. Image/frontier are false and MiMo disabled. Native image/policy/catalog, resident Ada200K, both 480K assignments, histories, files, auth, holds, fans/power/ECC/runtime policies and first failures were preserved. No benchmarks, large-context tests, engine upgrades or GitHub publication were performed by this worker.

RESULTS.json contains source/test/deployment hashes, owned IDs, honest per-case results, first preparation failures and limitations. ADMISSION-ACCEPT01.json and ADMISSION-ACCEPT02.json contain only bounded static diagnostic metadata. Raw native/provider bodies, real user content and credentials remain private. This is a report-only packet based on 2662bd08; root publishes to the feature branch/draft PR. The incomplete branch is not merge-ready.
