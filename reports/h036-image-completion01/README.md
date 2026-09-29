# H036 IMAGE-COMPLETION01 — offline diagnosis complete, no production correction justified

W1 started at 2026-09-29T21:29:39Z on exact base `7fe2bf0adde6ffdae1e5d7f04bd5d1c4c4cfeee8`. The early proposal was exported through OUTBOX and output/PROPOSAL.md within the first ten minutes. No subagents, external threads, live/native inference, VM/app calls, deployment, tickets, shared policy edits or runtime/capacity changes were performed. This report is written while the worker is still running; its actual exit receipt belongs to the wrapper after exit.

## Finding

A production repair cannot yet be justified from the retained offline evidence. The specific hypothesis that installed instructions lack generic action persistence or a distinction between promises and finished work is disconfirmed: both actual H035 requests already contain the current full model template AND the config developer instruction requiring completed artifacts and saying intended next steps are not a completed result. The same model-template persistence sentence and explicit host-enablement sentence exist in H034 source whose hash matches the successful-capture comparison. No blanket completion paragraph, retry, forced child/tool policy, output rewrite or gate change was added.

The [audit](RETAINED-AUDIT.json) and [reproducible script](audit-retained.ts) verified 142 first-failure and 202 retest files. Current `translateResponses` reproduces the entire actual normalized request body byte-for-byte after excluding only the gateway-selected model lane. Original history and exact current prompt survive unchanged. Replaying the captured provider SSE through current `ResponsesStream` returns the original final bytes, `stop`, and no synthetic calls. This independently confirms preservation; it does not execute the requested work or establish its cause.

Effective instructions SHA256: `f7bb7510b3df3546210fee7e6d305f86df9e45c971186088dc6c157977dbecc7`.
H034 successful instruction source SHA256: `84260e8947aa0e146a75ebbea318ad33e3c99ea19b6c2bf09551c8c240892971`.
H034 raw capture is not available in this isolated task; its supplied W2 comparison is reused and matched against retained Git source. No fresh H034 runtime claim is made.

## Capability and history distinction

Source `codex-host.ts` keeps public `imageToolEnabled` qualification separate from trusted exact-session `imageAcceptance`; the latter selects `config-image-jobs.toml` at launch. Gateway authorization allows owned GET/status separately and gates creative POST on qualification or trusted acceptance. Current app and launcher source agree on this split. The H035 parent has image and delegation schemas, not a captured instruction explicitly saying the image gate is false. Developer-message absence checks are bounded textual checks, not a proof that the model could not interpret another phrase conservatively. The host-enablement wording is shared with successful H034, so it is not a unique explanation. Public false qualification was not weakened.

The retained H035 requests have 63/65 input items, including 20 historical calls and eight invalid prompt-shaped image_capabilities calls. H034's successful initial request has three items and a different generation task. Stale failure/promise history, the mixed fresh-child/completed-job identity request, interaction with newer status/operation guidance and provider variability remain competing explanations. The failed response is not evidence of a dropped call, output-limit truncation, absent spawn schema or proved snapshot-only causality.

## Verification and next bounded step

Thirteen existing focused tests passed: instruction trust/load boundaries; exact assembled request/history/reference provenance; approval/status/continuation behavior; deferred result delivery; creative-gate expiry with retained read/cancel/drain. See [command receipt](TEST-RECEIPT.json). No broad suite/build was run for unchanged production source. Earlier known stale expectation failures are not reclassified as passing.

[Separate acceptance cases](ACCEPTANCE.md) specify fresh editing, completed-job status and the untouched strict original fixture. The smallest proposed live diagnostic is one explicit status/retrieval request in the original owned chat, with zero creative submissions, followed separately by normal fresh editing acceptance. It requires root/W2 authorization; none was executed here. A fresh session cannot inherit the old job identity across ownership boundaries.

Exports contain reports and the offline audit script only. The production-only patch is intentionally empty. Full image qualification remains false and both original H035 failures remain failures. No successful live workflow or actual worker exit is claimed by this report.

Optional offline profile pointer: harness frontier profile generation is in `ai-harness/deploy/engine/configure-profile.mjs`, with Codex catalog in `ai-harness/deploy/codex/models.json`; W2 owns those capacity changes. No native MiMo host profile was inventoried or touched.
