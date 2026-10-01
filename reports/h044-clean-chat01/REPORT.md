# H044 clean Sova chat — source export

Source commit `46fa6fd6f121d138eb4ea27ff11d37710fd31b0e` from reviewed base `58bff2ec474fd0cf4a7ba3f71028bb2710555c88`. Only the 29 exact owned web paths listed in SOURCE-MANIFEST.json changed. No server, package, lock, deployment or live resource changed.

The normal interface is Sova: chat list, conversation, composer, attachments, inline results, Send/Stop and Compact context. Harness/model selection, migration controls, preview capability/configuration panels and runtime/model metadata were removed. Memory/storage keys and original records remain unchanged. Historical messages, files and native identifiers are preserved; their content is not bulk rewritten. New chats explicitly request the sole active Codex engine even if a service reports an old default. Old or unidentified engines are readable, with a plain new-chat path; send, recovered-submit retry, upload, reuse and handoff cannot start hidden historical-engine execution. This fallback starts a fresh chat; it does not claim automatic transfer of old context/files.

The held V web hunks were applied with an exact five-file 3-way patch onto the current source and then reconciled deliberately. Technical image analysis stages normal attachments independently of creative-image references and capability gates. Its literal extracted text, source download, uncertainty, native final answer and persisted replay remain separate. Completion requires a settled completed saved result with valid display structure. Malformed/unavailable output stays unavailable. Actions use the store's scoped transport and original handle/run, with separate observation/cancel locks. Stop cancels known unsettled analysis after the text turn ends. Cancellation/observation errors remain useful; no completion or progress was synthesized. Backend ownership, provenance, admission and qualification remain external prerequisites.

## Actual verification

- `typecheck-sealed`: standalone web typecheck, exit 0.
- `web-tests-sealed`: 254 tests passed in 24 files, exit 0.
- `web-build-sealed`: TypeScript plus Vite build, exit 0.
- `browser-sealed`: 17 Chrome Playwright contract tests, exit 0, rendering `http://127.0.0.1:4193/` from this checkout's built dist and owned fixture.
- `diff-check`: exit 0; source ownership check found no extra path.
- Owned fixture PID 88316 from the prior corrected run and PID recorded in the sealed receipt were observed with birth/process metadata. No observed process identity remains in the sealed receipt. Post-run lsof found no listener on port 4193 (empty stdout/stderr, actual expected exit 1).

Desktop/mobile rendered screenshots and image/analysis views are in `output/sealed-screenshots`; their exact hashes and original command argv/cwd/UTC/exits/stdout-stderr hashes are recorded in RESULTS.json and private `output/commands`. Desktop conversation, technical analysis and mobile renders were visually inspected. They are real browser renders of explicit fixtures, including procedural image bytes and fixture OCR; they do not qualify model correctness, native compaction or a deployed browser. Earlier failed screenshot/trace sets remain in output alongside original failed logs.

## Retained failures and corrections

Initial OWNED-SCOPE read used the repo-relative path and returned exit 1; the authoritative parent `../OWNED-SCOPE.json` was loaded before edits. Initial reference-vision/web lookup returned no such directory; the root-sealed `reference-current/U-clean-chat.full-index.diff` supplied the correct five owned hunks. These were read-only setup failures, not test passes.

The first typecheck failed on narrowed connection comparisons and an unused import; those were corrected. Original unit runs failed on old engine defaults/selectors, changed metadata expectations, ambiguous file text after reuse controls and the cancellation ACK race. Corrections retained substantive keyboard/IME, upload safety, cancellation ordering, compact idempotence, submission deduplication, replay, file ownership, unavailable-capability and legacy-execution checks; the final complete suite passes. The first browser attempt failed before rendering because the cached headless executable was absent. Installed Chrome was used without downloading browsers. Its first run had four obsolete/ambiguous checks; these were corrected to inspect attachment lists and preserved server metadata, then all 17 scenarios passed. A source commit initially failed with exit 128 because the isolated checkout had no Git author configuration. The corrected command used per-invocation public author metadata adopted from the reviewed base, without changing shared/global config. All original receipts and stdout/stderr are retained.

## Boundaries and integration

Native/live/inference/deployed-browser/physical: **NOT_TESTED**. No Linux SSH, deployment, service/lifecycle, model/GPU, registry, fan/BMC, driver, Proxmox or download action occurred. Runtime 0.158.0/upstream064c/context480000/auto400000/output65536, histories, credentials, downloads and native rerouted-model guards were preserved by leaving their sources/resources unchanged. Dependencies were copied into this checkout; no shared tree was mutated. No push, PR or merge was performed.

Root must integrate/review this source with the independently owned corrected normal vision/server/native routing candidate and issue a separate finite exact source-bound GO for operational qualification. Availability uses returned operational capability flags; source-PASS creates no enable flag. Current worker native/wrapper/outer terminal receipts and final worker-process absence cannot be recorded before this exec returns; root collects and reviews them afterward. Test-process closure is distinct from that worker closure.

Tracked report files bind the source commit and source/check hashes. The external output export binds the final report commit, candidate.bundle, all changed source/report hashes and artifact integrity; it avoids circular self-hashes.
