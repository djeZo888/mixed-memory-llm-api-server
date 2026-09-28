# Sova current task — H022

Latest user request: check the existing H019 near-950K benchmark, then prepare
the next Codex implementation plan. This turn is read-only on the VMs and
planning/documentation only. Worker1 may collect the existing unit's current
progress or terminal evidence once; this supersedes H021's no-poll instruction
for that collection only. No rerun, new inference, holds removal, deployment,
model/runtime changes or hardware work. Worker2 reviews source/evidence offline.
Root coordinates, reviews and publishes the plan. Use fresh bounded native
worker CLI sessions and close them after their result, with no paid waiting.

H021 has completed a deployed optional Codex preview. The app is active;
MiniMax remains default. Codex image tools remain disabled, the separate MiMo
hold and historical quarantines remain. Old statements below describing the
app as paused or authorizing implementation are historical, not current grants.
See ai-harness/PLAN-CODEX-COMPLETION.md for the next proposed work.

## Historical execution instructions — H021

Latest user request authorizes implementation of ai-harness/PLAN-CODEX-HARNESS.md with both workers. This supersedes H020's plan-only limit. Root plans, coordinates, reviews and publishes; mac-worker1 and mac-worker2 implement/build/test over SSH in fresh bounded native Codex CLI sessions and isolated copies. Retain session IDs, incremental commits and compact durable evidence. Do not keep paid sessions idle waiting for native work. Historical instructions: docs/orchestration/AGENTS-H020-archive.md.

Leave the existing h019-final950k.service benchmark on ai-vm untouched. Do not poll it, send competing MiMo inference, change any inference runtime/configuration or restart control/node/model services, hardware, drivers or VMs. No GLM restoration. No new GPU stress tests or BMC/fan changes. MiMo-specific live Codex acceptance is deferred until that benchmark is known settled; fixture/source qualification can proceed. Qwen short acceptance is permitted only through centrally coordinated existing admission ownership, never by bypassing global capacity. Avoid sustained server-Blackwell load. Image short acceptance likewise requires existing job ownership. No model capacity benchmarks.

Implement Codex as a selectable controlled preview beside MiniMax, keeping MiniMax default and existing native sessions tied to their engine. Stage A pins the exact Linux CLI/source/schema and qualifies local Responses/tools/continuation before UI activation. Use private App Server stdio inside existing rootless task isolation, scoped local gateway credentials, no OpenAI inference/auth/search fallback. Preserve chats, uploads, artifacts, original histories, trusted configuration and status repair. Keep stop/restart/uncertain-work ownership truthful; no blind request replay or premature slot release. Preserve actual reasoning fields only under a verified local contract, never fabricate encrypted state or internal reasoning.

Worker1 owns protocol/provider/gateway/tool integration; Worker2 owns engine adapter/session persistence/UI. Coordinate shared contracts before editing. Worker2 may develop independent offline lifecycle fixtures while Worker1 resolves the protocol gate. Cross-review each other's focused changes before root approves an exact pilot deployment. Source/build/test work stays on workers. Root may synchronize code, edit project plans/reports, review and publish. No additional user permission needed for routine authorized changes.

The existing Sova app is paused; a separate MiniMax/MiMo HTTP400 issue remains unresolved. Do not claim it fixed by Codex acceptance. Preserve active-frontier MiMo selection and the deployed H020 status release; runtime descriptive inventory must not silently revert to repository default GLM. Deployment must preserve prior releases and data and must not affect the running MiMo benchmark. Keep status available where practical, but do not spend time maintaining general app availability during implementation.

Use feature/glm53-flash and draft PR10. Do not merge incomplete acceptance into main. Automation remains paused. No automatic engine/dependency upgrades. Record actual PASS/FAIL/NOT_TESTED evidence and limitations. Latest user task has no new fixed wall deadline; each assigned worker task remains bounded and produces a terminal checkpoint before continuation.

H021 PILOT05 completes the planned central engine-status view. A reviewed
ai-harness-only status release is permitted alongside the final app release;
preserve H020's model identity/placement repair, actual registry/selector and
user data. The earlier exact status-PID preservation check was for releases
that did not change status code; it is superseded only for this intentional
status update. Engine data comes from configured app health with explicit
freshness/unavailable states, independently of model readiness. No ai-vm node,
control, model or benchmark inspection/mutation is authorized. Do not restart
the app until Worker2 has released all acceptance ownership.
