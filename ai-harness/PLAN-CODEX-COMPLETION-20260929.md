# Sova — Codex completion review and execution plan

September 29, 2026. **H029 execution authorized: 01:25–03:25 UTC (03:25–05:25 Ljubljana).**
Stop new live submissions at 03:10 UTC; reserve the last 15 minutes for settlement,
review and publication. This is the first two-hour window described below.

Original review: planning only; no worker or VM contacted during that review.
Reviewed local source: `d4a2322fea929b29a1252b3405aca250ff032eee`, branch
`feature/glm53-flash`. No code was changed and no tests or inference were run.
This document updates the work order in `PLAN-CODEX-COMPLETION.md`; it does not
reopen any expired execution window. The user's follow-up now authorizes H029.

## Conclusion

Codex is an implemented optional preview, not a missing engine. Retain its
adapter and repair the local-provider boundaries, then qualify complete user
workflows. MiniMax remains available and the default during this work. Completing
Codex integration does not require another GPU benchmark, model download, engine
upgrade or million-token test.

Keep the pinned Codex 0.158.0 App Server/source
`064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`, private stdio transport, existing
rootless task containers, Sova web UI, storage and shared inference admission.
Codex uses local models through the existing Responses-to-Chat adapter; this
does not require paid OpenAI inference or a ChatGPT login. Local search/browser
and specialist image services remain the tool providers.

Official documentation confirms Responses as the custom-provider wire API and
App Server operations for native threads, turns, interruption and compaction.
The generated schema from our pinned binary remains the implementation contract;
current online documentation is not proof of support in that binary.
[App Server](https://learn.chatgpt.com/docs/app-server) ·
[provider configuration](https://learn.chatgpt.com/docs/config-file/config-reference).

## 1. Implemented versus verified

| Area | Present implementation | Evidence and remaining gap |
|---|---|---|
| Engine selection and persistence | Optional Codex beside MiniMax; immutable engine per existing chat; native thread/turn IDs, history and workspace storage | H021 live selection, follow-up and reload passed. MiniMax stays default. |
| Local inference protocol | Responses translation, tool namespaces/IDs, streaming, native token counting, context/output limits | Real Qwen coding/tool continuation passed. Earlier unclassified decoding failure retained; diagnostics now exist. |
| Coding and public research | Native shell/patch plus local search/Chromium | H021 Python, C++, Node and researched answers passed; independently checked artifacts. |
| Child agents and lifecycle | Native children, resume, durable inference ownership and cancellation drain | One real child, cold resume, Stop then follow-up passed. Multi-lane child/cancellation/restart combinations remain to qualify. |
| Context | Provider budgets, 65,536 output ceiling, occupancy events, manual compaction with durable action ID | Source/fixture coverage; live compaction recall and resumed continuation are unqualified. |
| PDF | Extraction/render/creation tools installed | Tools pass directly; Codex twice ended before producing the requested answer/PDF. H024 retry was blocked before inference. |
| Image generation/editing | MCP and existing image broker integration, reference staging, approvals and private acceptance path | Ordinary Codex image gate remains closed. Invalid capability arguments (`__ns`, `ns`, `__v`) caused failures; no successful complete Codex image workflow. |
| MiMo frontier | Provider budgets, tokenizer route, reasoning/tool continuation and child configuration implemented | Live Codex gate remains closed. MiniMax medium-effort mapping was fixed, but full delegated task acceptance is outstanding for both engines. |
| UI | Engine selector, progress/history/context and shared file/artifact features | “Legacy response” label already fixed to “Assistant response.” Reliable phase behavior and remaining workflow cases still need acceptance. |
| Handoff and retries | Same-engine new-chat handoff; compaction retry ID | Cross-engine target selection and durable IDs for ordinary user submissions are missing. |

H024's last combined application deployment was source `e2e0a946...` on September
28 at 18:22 UTC. Subsequent H028 status deployment is separate. H028's final
record has only the new Ada Qwen running; the two Blackwell Qwens and image are
stopped, and MiMo is unavailable. This review did not refresh live state.

The older completion plan's fan-controller work is already resolved by H025/H028.
Five-GPU discovery, private status transport recovery, and Ada 200K native
qualification also passed H028. Do not redo that work or count it as Codex
workflow acceptance.

## 2. Highest-priority defects

### A. Slow control observations occupy the lifecycle lock

Current `scripts/control/core.py` still enters the common lease in `_work()`
before refresh calls `_fresh()` and reconciles observations. H024 measured a
control read holding that lock for about nine seconds; MiMo's guard has a
five-second acquisition budget. The historical owner at the original failure
instant is unproved, but the present contention mechanism was demonstrated.

Split slow read-only collection from the short publication critical section.
Publish only after rechecking boot, selected profile, runtime identity and owner
generation; discard observations invalidated by an intervening lifecycle change.
Keep actual starts/stops serialized. Do not substitute longer timeouts or stale
health for this repair. Verify that a deliberately blocked collector cannot
starve a hardware guard, and that changed identities cannot publish old results.

### B. Qwen admission hides the rejected condition

`codex-host.ts` runs lane checks with `Promise.allSettled` and filters failures
without recording their reasons. `codex-production.ts` maps many distinct
predicates to the same error. Standalone serial and parallel checks passed in
H024 while an actual Codex submission failed with “No currently qualified Qwen
lane.” Its exact failing condition is still unknown; parallelism alone is not
an established cause.

Add bounded, request-correlated reason codes and phase timings for each lane:
transport, freshness, boot/runtime identity, generation, source/profile, hardware
state and token capacity. Keep content/credentials out of these records. Reproduce
one short real submission, repair the demonstrated discrepancy, then qualify
each 480K lane and their shared queue. A healthy lane must remain usable when
another is unavailable; no request may bypass current identity/context checks.

### C. Provider configuration is not yet general enough for the new Ada

Status uses the system registry, but Codex provider/counter/host/catalog and
reviewed lane configuration still contain fixed aliases, endpoints and 480K
assumptions. The Ada registry entry deliberately has no routing endpoint.

Introduce one reviewed provider-profile configuration consumed by those adapters,
and link it to the existing service registry and runtime qualification. Distinguish
model identity, instance identity, available capabilities, context/output budget,
tokenizer and admission slot. Keep immutable policy checks separate from current
runtime availability. Remove misleading hardcoded frontier fallback names.

Preserve 480K as the main Qwen-chat profile. If adding Ada to harness execution,
expose it as a separate 200K profile for explicitly budgeted short child tasks.
Never silently route a 480K session to it or truncate history. Count complete
input plus reserved output and overhead. Derive compaction limits from the chosen
profile; a 200K profile cannot inherit the existing 400K threshold. Revalidate
Ada's Codex tool/tokenizer contract before enabling it. This extension follows
the repaired two-lane baseline and must not delay its initial acceptance.

## 3. Worker work packages and order

### Package 1 — dependable model admission

**Worker1:** current-state/ownership preflight, control-lock repair, lane diagnostics,
provider metadata consistency, ai-vm deployment and short native qualification.
Restore the same two 480K Qwens after safe preflight. Recover the selected MiMo
profile only after the control defect is repaired; no replacement with GLM and
no new capacity test. Retain the Ada model and current fan/power/ECC policies.

**Worker2 in parallel:** reproduce retained Responses/MCP/PDF boundaries using
local fixtures; preserve exact original prompts and record finish reasons, tool
arguments/results and native terminal events. Implement durable ordinary
submission IDs independently in the application/store. Same ID/same payload
returns the original run; same ID/different payload fails. Explicitly repeated
user prompts receive new IDs. Share the event/diagnostic interface before editing.

**Gate:** one ordinary Codex tool turn and follow-up pass through the actual
application; both qualified Qwen instances can be selected; an unavailable lane
does not disable the healthy lane. Control refresh leaves watchdog access intact.
No further live tool tests until admission is reliable.

### Package 2 — complete useful workflows

**Worker1:** shared provider queues and model-specific child policy; short MiMo
tool continuation and one deliberate research/analysis delegation through each
engine. Qwen remains coordinator and routine coding model. MiMo escalation is
deliberate, with its independent queue and existing long-request budget. Verify
that waiting parents release inference slots. Enable frontier capability only
after actual acceptance.

**Worker2:** finish image/PDF compatibility and run their unchanged workflows.
Trace malformed image arguments through raw model output, translation and MCP
input; do not blindly strip unexpected fields. Separate provider continuation
loss from a model choosing to stop early. Correct a demonstrated defect and
repeat that affected fixture once. If it remains a model-reliability problem,
report it and retain the capability restriction rather than marking it passed.

Image acceptance uses the existing guarded-edit policy, Full HD maximum, fresh
seed rules, originals retained, user canvas approval and separate image queue.
Require ordinary generation, follow-up editing and one child path; verify actual
image artifacts, inline previews and downloads. PDF acceptance requires the
correct numeric/unit answer and the actual readable summary PDF.

**Gate:** complete tasks pass through normal Sova chats, not just direct helper
calls or temporary diagnostic allowances. Both engines retain their supported
workflows and specialist-service ownership.

### Package 3 — context, lifecycle, experience and final release

**Worker2:** qualify native compaction on a small retained conversation, followed
by recall and cold-resume checks. Preserve visible original history and files;
count occupied context rather than lifetime token totals. Test capacity failure
without a long prefill. Add a target-engine choice for Continue in new chat,
passing a summary/file references into a fresh native session while preserving
workspace serialization. Never resume one engine's native history in the other.

Qualify progress/final phase mapping, real child count, queue/Stop state,
attachments, reply-specific artifacts and ZIP downloads. Keep absent native
phase metadata explicit. The completed label fix needs no reimplementation.
Mid-turn steering and native image/audio/video recognition remain later features.

**Worker1:** independently verify gateway ownership and timing, including two
overlapping short chats, parent/child overlap, queueing, queued and active Stop,
browser reconnect, partial provider stream, and service restart with owned work.
Use faithful fixtures for fault cases, with a small real restart/reconnect case.
Never replay uncertain accepted inference or release its slot before settlement.
Check local coding with external internet unavailable; research reports offline
state without hosted fallback.

Measure preparation/admission/tokenization/queue/prefill/decode/tool/continuation
separately before optimizing latency. H021's single matched cases were slower on
Codex (roughly 1.6–3.3x); that does not identify the cause or justify a throughput
claim. Repeat only an affected short comparison after a measured improvement.

**Gate:** publish a PASS/FAIL/NOT_TESTED matrix, preserved-state/rollback receipts
and known limits. Keep MiniMax selectable. A change of default engine is a later
decision based on demonstrated reliability and useful-task completion time.

## 4. Execution discipline and budget

- Begin with **one two-hour window**: about 15 minutes for a shared baseline,
  60 minutes of parallel bounded work, 30 minutes for reviewed integration and
  the first affected live acceptance, 15 minutes for settlement/reporting. This
  targets Package 1 plus independent Package 2 preparation, not a promise of
  complete feature parity in two hours.
- Use fresh native Codex CLI sessions on each Mac, isolated copies, retained
  session IDs and compact durable status. Reserve model load time explicitly;
  do not keep a paid worker session open merely waiting for a long native job.
- Worker1 owns control/provider/lane/registry code and ai-vm writes. Worker2 owns
  Responses/MCP, application/store/UI and ai-harness deployment. Coordinate edits
  to `main.ts`/`gateway.ts` through Worker1; use one combined reviewed release.
- Root coordinates, reviews source/evidence and publishes. No concurrent VM
  deployment writers. Independent source/fixture work is parallel; live tests
  follow one shared schedule with short inputs/outputs and no stress workload.
- One bounded reproduction per failure, then one focused repeat per demonstrated
  correction. Stop an unchanged failure to report its specific cause or missing
  evidence; no prompt sweeps, blanket reruns or automatic time extensions.
- Checkpoint after two hours. Propose another bounded window only for identified
  remaining work. Preserve failed evidence, histories, files and rollback state.
  Restore a working baseline if safe; report any unavailable model explicitly.
- Keep source/runtime pins unless a specific reproduced defect requires an
  upgrade. Do not mix a general Codex upgrade, driver update, model tuning,
  accounts, scaling, installer or 950K test into this work.
- Preserve existing upstream licenses/notices and MIT licensing of Sova's own
  additions. Engine integration does not alter model-weight license terms.
- Publish the plan and reviewed changes on the existing feature branch. Resolve
  Codex acceptance separately from unrelated frontier/capacity work before any
  proposed merge; the current draft branch is not wholly release-qualified.

## 5. Evidence and source anchors

- [H021 preview and live comparison](../reports/h021-codex-preview.md).
- [H024 deployment, failures and remaining gates](../reports/h024-codex-checkpoint.md),
  [machine-readable results](../reports/h024-codex-results.json).
- [Control-lock evidence and proposed repair](../reports/h024-acceptance02-20260928/CONTROL-REFRESH-FUTURE-FIX.md).
- [Latest hardware/status/model state](../reports/h028-overview.md).
- Source relative to `ai-harness/`: `../scripts/control/core.py` (`_work`),
  `server/src/codex-host.ts` (`currentAliases`),
  `server/src/codex-production.ts` (receipt/verifier),
  `server/src/codex-qwen.ts` (counter), and the provider, gateway, Responses,
  capability, app, broker and store modules in `server/src/`;
  `web/src/Replies.tsx` and `deploy/codex/`.

This is a source/evidence review, not a fresh live health report. The first worker
preflight must verify that the recorded deployment and model state still match.
