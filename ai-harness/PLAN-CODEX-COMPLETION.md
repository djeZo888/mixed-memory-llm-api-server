# Sova — complete the local Codex integration

**September 28, 2026. Implementation authorized: 16:52–18:52 UTC.**

The H024 execution window follows the hardware checks. All four models were
resident at its start and existing benchmark requests are settled. The third-GPU cooling
test passed; four-way qualification remains partial because its test monitor
hit a journal-size limit. No further thermal or large-context test runs here.

Worker1 owns current model qualification, provider/gateway/frontier integration
and any required ai-vm supervision repair. Worker2 owns Responses/tool/PDF
compatibility, context/UI work and deployment of the combined harness release.
They use isolated copies and fresh bounded native CLI sessions on their Macs;
root coordinates, reviews and publishes. Reserve the last15minutes for health,
settlement and publication. MiniMax remains available/default while Codex is
qualified. Later sections retain the original investigation/acceptance scope;
this assignment supersedes their earlier worker allocation.

This follows [the original plan](PLAN-CODEX-HARNESS.md) and the deployed
[H021 preview](../reports/h021-codex-preview.md). Keep MiniMax available and
default while qualifying Codex. Preserve existing conversations, native thread
identities, files, model services and failed-test evidence.

## H024 implementation checkpoint

Combined application source `e2e0a946cd4057ee33657a4714da473cf16ab5ca`
was activated at 18:22 UTC. It includes per-model provider budgets, protected
single-run diagnostics, reference staging, an owned manual compaction action,
the clearer response label and MiMo's demonstrated medium-effort mapping.
These source/fixture results do not qualify remaining live workflows.
MiniMax remains default; ordinary Codex image and frontier gates remain closed.

MiMo stopped at 18:04:30 after its five-second hardware guard could not acquire
the common lifecycle lease. A read-only reproduction measured the control
service holding that lease for about nine seconds. The historical holder at
the failure instant is not proved. Repair slow status observation and identity
publication before another load or large-context test; preserve the guard.
See [worker evidence and proposed repair](../reports/h024-acceptance02-20260928/RESULTS.md)
and the [bounded-window report](../reports/h024-codex-checkpoint.md).

The user resolved CHA_FAN3 cycling by removing its CPU-temperature source.
Preserve that setting; the requested GPU-driven 40%/80% policy is still pending.

## Historical H021 baseline

Codex 0.158.0 is pinned to source
`064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`. Sova application source
`bbeec44d44c29d1b50ce8374c5d26170bc844f5a` is deployed. No engine upgrade or
inference-runtime replacement is needed merely to start this work.

| Capability | Evidence at the H021 checkpoint | Remaining work |
|---|---|---|
| Python, C++, Node editing/testing; web research | Passed bounded real cases | Retain regressions; repeat only affected cases |
| Native child agent; cold resume; reconnect; Stop then follow-up | Passed real cases after documented repairs | Extend to concurrent lanes, child cancellation and restart |
| PDF tools | Individual helpers work; two complete Codex tasks failed | Find why a turn ends before the requested result exists |
| Image tools | Invalid capabilities arguments; no image job submitted | Repair tool contract and qualify generation/editing before enabling |
| Second Qwen instance | Codex current-generation check failed | Repair metadata/qualification; retain the guard |
| MiMo frontier | Native short tool turns passed; MiniMax child request rejected HTTP400 | Repair shared request integration, then qualify each harness |
| Context compression | Protocol fixtures passed | Live local-model recall, continuation and history preservation |
| UI phases | Some new replies lack reliable phase metadata | Remove misleading label; qualify progress/final mapping |

The 950K MiMo result is a separate native-capacity test. Passing it cannot
establish Sova delegation, tool or Codex compatibility. H022's read-only check
found that the existing client failed before its deadline due to recorded
`lifecycle_busy` during hardware supervision, followed by settlement timeout.
At that H022 checkpoint MiMo was selected but no longer resident and held
ownership remained. The old hold was subsequently reconciled with an audited
exact inverse in H024; MiMo's later 18:04 outage is recorded above. See the
[result and limits](../reports/h022-950k-status.md). A running
or unsettled request continues to block new MiMo inference. No automatic repeat
of this expensive test is proposed. Allocation alone does not qualify 950K.

## 0. Resolve the frontier test outcome without repeating it

Preserve the original client/native logs and failure. Trace the canonical-lock
holder and hold duration around the recorded failure. Review periodic health
checks, control/status callers, the lock timeout and settlement timeout. The
last measurements showed no recorded OOM or MiMo swap and sufficient free VRAM;
do not label this a capacity failure. Distinguish transient contention from a
positive hardware fault using bounded handling and fresh observations; retain
thermal, memory, identity and ownership protections. Reconcile the held request
through the lifecycle owner after independent absence checks, then recover the
same MiMo profile and perform a short qualification. Propose any long rerun
separately. Keep the
configured target distinct from the largest successfully occupied context.
This prerequisite affects MiMo activation; independent Codex/Qwen work can
proceed. H022 itself only collects status and prepares this plan.

## 1. Repair tool compatibility before adding more features

**Worker1: local provider/MCP boundary. Worker2: PDF workflow and independent review.**

Use retained failures to compare tool schemas and arguments at four boundaries:
Codex output, the Responses-to-Chat translation, raw model output and MCP input.
Record IDs, finish reasons and bounded diagnostic metadata; keep raw request
content private. Determine where the unwanted `__ns`, `ns` or `__v` arguments
originate. A simpler alias already failed; repeating that experiment is not a
new diagnosis. Preserve strict validation and tool-result identity.

For PDF completion, retain the upstream finish reason and native turn events.
Distinguish model early completion from dropped continuation or adapter errors.
Verify the original numeric answer and actual summary PDF, rather than accepting
a message promising further work. Avoid automatic prompt rescue or unbounded
retries. If this proves a local-model reliability limitation, record that and
keep the workflow unavailable instead of claiming a software repair.

Acceptance: the unchanged PDF fixture succeeds; image generation and a guarded
follow-up edit succeed through ordinary chat, with original uploads preserved,
correct references/seed/geometry, approval handling and inline/download artifacts.
Include one child-agent image-tool path. Re-enable Codex image tools only after
those checks. Image generation does not establish native visual understanding.

## 2. Qualify both Qwen lanes and frontier delegation

**Worker1: registry/provider readiness and MiMo validation. Worker2: routing and child lifecycle.**

Trace Qwen1's failed current-generation comparison against the observed runtime
and central registry. Correct stale or inconsistent metadata at its owner;
never bypass readiness checks or hardcode a GPU index. Qualification currently
uses a startup-built alias set; define how a reviewed new runtime generation is
requalified and reflected in health without treating a stale record as ready.
Qualify both instances
with short identical requests, then two independent chats and one parent/child
workload. Verify queueing when both slots are occupied and slot release while a
parent waits. Parents, children and compression share the same admission limits.

Once the existing MiMo benchmark is terminal and its native work is settled,
capture the rejected MiniMax request *before* normalization and identify the
precise HTTP400 validation failure. Fix the demonstrated contract mismatch,
then run a small tool/continuation case and one real delegated task through
MiniMax and Codex separately. Benchmark success is not a substitute for either.
Do not clear the frontier hold merely because its client process has exited.

Codex frontier support needs implementation as well as acceptance: its frontier
Responses route is currently explicitly blocked; counting, model catalog and
child configuration are Qwen-specific, and nonempty provider reasoning is
rejected. Add a reviewed per-model provider contract, tokenizer, context/output
budget and child profile before opening that route. Preserve real reasoning
fields only under a verified continuation contract, with no fabricated encrypted
state. Retain MiMo's eight-hour active-request allowance and separate queue
deadline; transport heartbeats are not token progress.

Keep Qwen as coordinator and routine coding model, MiMo for deliberate difficult
research/analysis, and the image model behind specialist tools. Read logical
model, instance, endpoint, context and readiness data from central configuration.
Do not silently fall back to a hosted service or restore GLM. Historical uncertain
requests and workspace quarantines require explicit reconciliation, not deletion.

## 3. Finish context handling and the chat experience

**Worker2 owns this work; Worker1 reviews provider/usage behavior.**

- Add an owned acceptance path for manual or reduced-threshold compression,
  using the pinned native schema. Check recall of goals, constraints, decisions,
  file references and tool results across compression and a fresh resumed turn.
  Preserve original visible history and Continue in new chat.
- Exercise compression failure and capacity rejection once with fixtures and a
  bounded live case where necessary. Fail clearly instead of looping.
- Retain Qwen's 480,000 context, 65,536 output ceiling and current 400,000
  compression threshold. Derive frontier budgets from its qualified registry
  capacity, reserving output and tool/template overhead. Report occupied context
  separately from cumulative inference tokens; check estimates with the tokenizer.
- Replace the misleading **Legacy response** label on newly unclassified output.
  Use reliable native phase/turn metadata where available. Keep progress and
  final answers distinct without inventing reasoning or relabeling uncertain
  content as a verified final answer. Show actual child count, queue and work state.
- Verify attachments, reply-specific artifacts, ZIP downloads, refresh and
  handoff against the same engine session. Add an explicit target-engine choice
  for **Continue in new chat**: current handoff always inherits the old engine.
  Carry a summary and permitted file references into a fresh native session;
  preserve the source chat and workspace serialization. Do not attempt to
  resume a MiniMax native history as a Codex thread or vice versa.
  Mid-turn steering is optional follow-up;
  current queued follow-ups remain usable until native steering is qualified.

Official App Server documentation describes compaction and streamed lifecycle
events; implementation must still match our pinned generated schema. A short
test threshold avoids another huge prefill just to exercise compression.
[App Server](https://learn.chatgpt.com/docs/app-server),
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## 4. Reliability and measured latency

**Worker1 measures provider/gateway phases; Worker2 independently checks lifecycle and UI.**

Use existing timestamps first, adding narrow timings only where missing:
request preparation, validation, tokenization, queueing, prefill, decode,
tool execution and native continuation. Current small tasks took roughly
1.6–3.3 times MiniMax's completion time; this does not yet identify the cause.
Optimize only a measured bottleneck without weakening readiness or ownership
checks. Compare one affected fixture with the same model and budgets afterward.

Add durable client submission IDs: repeated delivery of the same submission
returns its existing run, including after restart or completion. Reusing an ID
with a different payload must fail. Current active-run rejection and browser
event replay do not provide this guarantee. Do not deduplicate separate prompts
merely because their text matches.

Verify restart during owned work, queued/active Stop including children,
duplicate submission, dropped browser, partial provider stream and offline local
operation. Use fixtures for destructive/error cases where they faithfully test
the contract, plus a bounded real restart/reconnect path. No request is replayed
automatically after uncertain completion; accepted GPU work must settle before
capacity/workspaces are released. Preserve the already-passed cancellation repair.

## 5. Execution budget and release gate

Propose an initial **two-hour implementation window**, with a checkpoint rather
than an automatic extension. This is a bounded first window, not a promise that
all unresolved defects will be repaired in two hours.

1. First parallel wave: fresh 45–60-minute worker sessions, separate copies and
   agreed file ownership. Worker1 takes MiMo supervision/settlement diagnosis;
   Worker2 takes Codex image/PDF boundary diagnosis and its fixtures. Share a
   compact interface decision before edits. Later waves pair Worker1's model
   readiness/provider integration with Worker2's context/UI work; avoid editing
   shared adapters simultaneously.
2. Cross-review and one centrally coordinated integration/deployment. Workers
   may prepare independent fixtures in parallel, but live model requests use the
   existing queue and one shared acceptance schedule.
3. Run the smallest affected real tests. Each demonstrated correction gets one
   bounded acceptance attempt; a repeat failure yields a precise checkpoint,
   not parameter sweeps or indefinite prompt retries.
4. Record source/version, actual PASS/FAIL/NOT_TESTED, timing, residual issues,
   ownership settlement and rollback paths. Close paid workers during long native
   work and retain session IDs/results for the next bounded task.

Full integration requires ordinary and child tasks on both Qwens, actual MiMo
escalation, PDF completion, guarded images, compression/recall, truthful UI and
reliable lifecycle behavior. Publish focused evidence and a compact end-to-end
smoke comparison; do not repeat the completed GPU benchmarks or force a 64K
answer merely to test an output ceiling. MiniMax remains available. Changing
the default engine is a separate decision based on the reviewed results.

Optional work kept separate: native image recognition, audio/video, new models,
accounts/permissions, horizontal scaling, installer, new GPU stress tests and
general runtime/OS upgrades. Preserve MIT first-party code and upstream notices.

## Source review anchors

Worker2 reviewed base `898389cf24149a6ec0b84edfe6987f5695771e35` without
building, testing or contacting a VM. These are investigation anchors, not
proof of the image/PDF root causes:

- `server/src/codex-responses.ts`: raw function-argument forwarding and terminal
  mapping; capture upstream finish reason and each tool boundary before repair.
- `server/src/codex-engine.ts`: private compression method and absent-phase
  mapping; connect only a reviewed owned operation to the application.
- `web/src/Replies.tsx`: completed unclassified replies display “Legacy response”.
- `server/src/app.ts`, `server/src/broker.ts`: inherited-engine handoff and missing
  durable submission-ID contract; retain immutable existing sessions.
- `server/src/main.ts`, `server/src/gateway.ts`: startup qualification aliases
  and current-generation checks; update readiness through an explicit lifecycle.
  The gateway's blocked frontier Responses path, `codex-responses.ts` reasoning
  handling, `codex-host.ts`, `codex-children.ts` and the Codex model catalog require
  model-specific work before live frontier delegation.
