# H036 IMAGE-COMPLETION01 — early proposal

Actual local start: 2026-09-29T21:29:39Z. Exact base: 7fe2bf0adde6ffdae1e5d7f04bd5d1c4c4cfeee8. Offline only; no subagents, inference, host calls or deployment.

## Observation

Both retained H035 pre-normalization requests carry the current Qwen instructions byte-for-byte (SHA256 f7bb7510b3df3546210fee7e6d305f86df9e45c971186088dc6c157977dbecc7). Both also contain the complete current config developer instruction, including completing requested work/artifacts before ending and treating intended next steps as incomplete. Thus missing generic persistence/completion wording is not established. H034 source instructions hash matches the supplied successful-capture comparison (84260e8947aa0e146a75ebbea318ad33e3c99ea19b6c2bf09551c8c240892971); that version already contains the same generic persistence and explicit host-capability requirement.

The H035 developer inputs contain no image-disabled/unqualified clause and no global imageToolEnabled/imageJobsQualified field. Source keeps public image qualification false independently from trusted exact-session acceptance: acceptance selects the image-enabled native config and gates creative gateway POSTs. Read-only image GET remains separate. Captured declarations include image tools and delegation. This does not prove that the model interpreted availability correctly, but there is no observed explicit false-capability instruction to repair.

Retained histories have 63/65 input items, including 20 old calls; eight old image_capabilities calls have invalid prompt-shaped arguments. Original failures, promises, current request, job IDs, references and history must remain intact. H034 successful initial request has only three input items and a different task; it is not a controlled comparison. The provider stop with zero calls cannot establish a unique instruction/history/ambiguity cause.

## Concrete hypothesis and proposed interface

Leading remaining hypothesis: long retained failed-tool/promise history plus the request's fresh-child/completed-job identity combination influences provider action selection, despite already explicit completion instructions. Competing hypothesis: the model interprets host enablement conservatively despite available schemas; competing instruction interaction: new operation/status guidance differs from H034. Stochastic/provider behavior is not excluded. No transport-loss conclusion.

Current recommendation: **no production source change justified yet**. Do not add blanket retry/forced tools, another generic persistence paragraph or gate weakening. I will export focused deterministic evidence/tests for the actual app context/Responses boundary and a finite acceptance specification. Proposed later source interface, only if a controlled observation supports it: explicit trusted per-turn image availability metadata derived from the existing exact-session gate (not public qualification), leaving enforcement unchanged. That interface is not being implemented on hypothesis alone and would require coordinated app/host review.

## Smallest later live comparison (not authorized here)

One unambiguous completed-job status/retrieval request in the SAME original owned chat, with exact saved ID and zero new creative submissions, compared with the retained strict failure. This deliberately changes the current task while preserving history; it is a discriminating probe, not proof of a unique cause or a perfectly controlled replay. Then one separate normal fresh edit with current instructions and an owned reference, normal approval and one creative submission maximum. Keep the exact old conflicting fixture separately labelled strict regression. Never copy an old job into a new app session or silently replace its native parent for a fresh-history comparison. Root/W2 must authorize/admit each live case. See ACCEPTANCE.md in the source report for the precise separate criteria.
