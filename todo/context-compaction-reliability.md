# Context compaction reliability

**Priority: first. Plan and source audit recorded on 1 October 2026.**
H039 source preparation is underway; no fresh native retention or deployment acceptance is implied. ai-vm is held for user-authorized shutdown and installation of a second Ada 48 GB. Mac source work can finish; live checks wait until the user confirms the hardware is ready.
Image generation qualification is deferred by the user.

## Objective and current evidence

Enable lengthy technical discussions and substantial projects to continue
through repeated compaction without silently losing accepted requirements,
work state or the original evidence. Default to the existing fast Qwen.

Current source selects Qwen for the main Codex thread:
[host selection](../ai-harness/server/src/codex-host.ts).
Both model descriptors use 480,000 configured context, a 400,000 Codex
compaction threshold and a 65,536 output ceiling:
[provider](../ai-harness/server/src/codex-provider.ts),
[catalog](../ai-harness/deploy/codex/models.json).
Keep these settings during the initial qualification. Context admission must
also reserve templates, tools and output; the visible threshold is not the
entire admission calculation.

| Evidence | Proven scope and limitation |
| --- | --- |
| H030 small manual compaction | Four-fact recall without tools passed; the summary also misstated a 22-byte file as 18 bytes. This is a concrete factual error, not a transport failure. |
| H036 large Qwen compaction | 402,104 input tokens became a 237-token summary retaining four facts. The original AUTO trigger metadata is absent. |
| H036 resumed follow-up | Returned the facts and correct calculation after reading a file that also contained those facts. Summary-only recall is not isolated. |
| H038 MiMo workflows | Child tool execution, continuation and handoff passed. MiMo-specific summarization quality was not tested. |
| Existing source fixtures | Cover history retention, duplicate/restart/failure handling and settlement. They do not establish semantic fidelity or native atomic replacement under every fault. |
| H039 native audit and lifecycle fixes | Exact 0.158.0 source audit; 95 focused and 1,008 broader source tests passed, four optional native tests skipped. Metadata-only resume, startup ownership, scoped retry and per-frame bounds are corrected. Native replacement-before-persistence and flush-warning limits remain; no atomic rollback claim. |

Sources:
[H030 summary](../reports/h030-flow03-20260929/SUMMARY.md),
[H036 results](../reports/h036-resumed-recovery-results.json),
[H038 checkpoint](../reports/h038-checkpoint.md),
[H039 native audit](../reports/h039-compaction-native.md),
[H039 current checkpoint](../reports/h039-adoption-checkpoint.md).
Retain original failed and partial outcomes.

## Two distinct acceptance requirements

**Operational reliability:** compaction has a durable identity, completes once
or reports a recoverable failure, preserves original history/files, releases
owned capacity and never blindly replays work after interruption.

**Technical retention:** subsequent work can recover exact constraints,
decisions, identifiers, quantities and unfinished tasks. A fluent summary is
insufficient. No finite evaluation proves that a generative summary can never
omit or invent a fact; the system therefore also needs durable records and
retrieval. The target is dependable continuation, not an unsupported universal
100% semantic-fidelity claim.

## 1. Confirm the pinned native implementation

Audit the exact Codex 0.158.0 source and protocol used in Sova, including native
summary generation, context replacement, persistence and error handling.
H039 subsequently recovered and audited the immutable source archive for upstream `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`. Per-file digests and exact protocol/persistence findings are recorded in the linked H039 report. The installed Linux binary remains separately unqualified by these source checks; do not substitute current upstream main.

Verify pre-turn and mid-turn automatic triggering, compaction request metadata,
handling of ContextWindowExceeded, retry/trimming behavior and the order in which
new context replaces old context. A failed semantic check performed after native
replacement is not a transactional rollback.

Reuse the existing event and settlement contracts:
[Codex engine](../ai-harness/server/src/codex-engine.ts),
[Responses adapter](../ai-harness/server/src/codex-responses.ts),
[broker](../ai-harness/server/src/broker.ts).
Do not identify compaction by searching an arbitrary user prompt for the word
"summary". Use trusted native operation metadata or a specifically qualified
native integration point.

## 2. Default model and routing

Main-thread compaction already uses Qwen through its native provider. Keep this
as the baseline. MiMo child requests currently retain MiMo routing, including
their own compaction. Do not label that path as Qwen summarization.

If Qwen is to compact every MiMo thread as well, qualify an explicit separate
compaction-model contract. It must translate the entire input representation,
use Qwen's tokenizer and output reservation, share Qwen admission, record the
actual summarizer and return correctly to MiMo continuation. A body.model
substitution alone bypasses model-specific compatibility and is not sufficient.
If the pinned native runtime has no suitable override, design that extension
separately; first finish dependable Qwen main-thread compaction.

MiMo can be an explicitly recorded escalation for a failed fidelity comparison;
it is not assumed to be a better summarizer from its general intelligence.
Compaction and child requests use the same finite inference slots as other
requests. A parent waiting for a child or queued compaction must not retain one.

## 3. Structured project memory and recoverable summaries

Preserve original transcripts and tool results as source-addressable records.
Add a versioned project state containing:

- Current objective and accepted user constraints.
- Exact interfaces, paths, model/configuration identifiers and relevant quantities.
- Latest decisions, explicitly superseding earlier decisions.
- Task ownership, completed checks, failures, blockers and pending work.
- Original-history/file references supporting each important claim.

User-pinned constraints and authoritative check receipts should survive
independently of a narrative summary. Preserve negation, units and authorization
boundaries. Do not let untrusted document instructions become new permissions.

Choose a summary size from fidelity measurements; the observed 237 tokens is
not a prescribed budget. Test several bounded sizes, such as 2K/4K/8K, only
where the native configuration provides a qualified control. Preserve a useful
recent tail and critical project state without expanding beyond token admission.

Provide scoped transcript/file retrieval so the agent can recover omitted
details. First implement exact references and text search; embeddings are an
optional later enhancement. Retrieval remains within the session/project and
future organization boundaries.

For any new candidate-summary validation layer, inspect native persistence
before selecting its mechanism. Prefer a supported pre-commit hook; otherwise
use a staged/forked context with controlled promotion or a documented recovery
checkpoint. Never report an atomic commit without proving it.

## 4. Focused acceptance suite

Use a new technical corpus of 50–100 facts, with an explicit answer key covering
units, pin mappings, interface names, numerical limits, error states, decisions,
rejected alternatives and tasks not yet completed. Include small code snippets
and corrections spread across the conversation. This is not a repeat of the
previous four-checkpoint retrieval benchmark.

Run three small compaction cycles, adding new facts and changed decisions
between them. At each cycle evaluate separately:

1. **Summary-only recall:** no tool access and no duplicate answer file.
2. **Durable recall:** retrieve cited original records for deliberately omitted
   details and answer accurately.
3. **Task continuation:** use the retained state to make a correct technical
   change or calculation, then verify it independently.

Require every designated critical fact to be correct, no invented successful
tests or permissions, and no revival of superseded choices in the suite.
Report noncritical coverage and failures as well. Do not use a model judge as
the only authority for exact facts.

Add offline cases for boundary admission, automatic-operation attribution,
child first-request context inheritance, empty/truncated/invalid summaries,
timeouts, cancellation, process death, duplicate actions, restart and missing
usage events. Verify that original records remain recoverable and owned work
settles or is explicitly quarantined.

After improvements, perform one targeted near-threshold Qwen case capturing
the actual automatic trigger and repeated continuation. This new case is
justified by the missing AUTO metadata and summary-only recall coverage.
Do not replay the unchanged old large paste or MiMo 950K benchmark.

Cold resume and browser reconnect must retain the accepted state. A completed
native compaction without a usage event may show "compaction completed;
context usage awaiting measurement". Do not fabricate zero occupancy or reject
an otherwise settled completion solely because usage is unavailable.

## 5. Delivery and work allocation

Use a bounded two-hour initial implementation/acceptance window when scheduled.
One worker owns native/source audit and lifecycle/fault fixtures; the other owns
technical retention fixtures, state/retrieval design and independent scoring.
Root reviews interfaces and evidence. Shared deployment has one named owner.
Reuse resident models and keep paid sessions closed during dependency waits.

Save compact machine-readable results: runtime/model/prompt revisions, source
hashes, cycle and trigger type, actual input/summary counts, durations, exact-fact
scores, retrieval evidence and settlement. Keep private technical conversations
and bulky traces outside Git.

Start with the existing Qwen. A dedicated summarizer is an optional pilot only
after a measured quality or contention reason exists; see
[model research](../docs/research/2026-10-01-memory-and-technical-vision-models.md).
No model download, runtime upgrade or GPU reassignment is part of this plan's
publication.
