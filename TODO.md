# Sova TODO

The **[compact TODO index and separate plans](todo/README.md)** is the entry
point for future work, including
[status service improvements](todo/status-service-improvements.md) and the
planned fan-management investigation. The records below retain their dated
outcomes; they are not all descriptions of the current deployment.

Dated H036 completion gates, retained H007 update policy and future design
are separate below. See the
[system overview](README.md), [architecture](docs/sova-architecture.md) and
[H006 closeout](docs/h006-closeout-20260926.md) for current boundaries and dated
evidence. This list is not an implementation or deployment acceptance report.

## H036 completion gates

See the [current recovery report](reports/h036-resumed-recovery.md) and
[results](reports/h036-resumed-recovery-results.json). Earlier checkpoints retain
original failures. MiniMax remains default; Codex remains a per-chat preview.
Root alone finalizes publication.

- **DONE:** application/search and four text instances recovered after the host
  reboot and user removal of the external image GPU. Image availability remains
  false and does not block text. Original interrupted work was not replayed.
- **DONE, with limits:** original Qwen compaction processed 402,104 tokens into a
  237-token summary retaining four facts. Automatic triggering is inferred;
  raw trigger metadata is absent. The original interrupted outcome is preserved.
  A distinct follow-up read its retained file and returned four facts and
  0.825 W. Because the file contains those facts, summary-only recall is not isolated.
- **DONE:** protected MiMo 480K/65,536 profile delivery, fresh native tool-result
  continuation and MiniMax child delegation. Full occupied-480K behavior and
  MiMo-specific compaction quality remain untested.
- **DONE:** ordinary Chrome ZIP completion, exact four entries, CRC and saved-link
  reload. The separate in-app-browser download-event timeout remains recorded.
- **DONE:** the observer optimization and coherent controller records are deployed.
  Normal control observations now take about one second. The final Codex MiMo
  child executed Python, continued from the actual tool result and returned the
  correct answer to its parent; all seven requests settled. Earlier failures
  retain their outcomes. Source d634207 passes all eight GitHub checks.
- **DONE:** final protected capability qualification and public admission review.
  Public HTTP and the normal browser passed after release at 07:45 UTC. MiniMax
  remains the default. [PR 10](https://github.com/djeZo888/mixed-memory-llm-api-server/pull/10)
  records publication and the main-branch merge.
- **PARTIAL / UNSUPPORTED:** MiniMax native image recognition is partial; Codex
  native vision is unsupported. Extraction/OCR and specialist image generation
  remain separate capabilities.

Retained image, coding, document and compaction cases must not be repeated
without a new relevant change. No new model, driver, hardware, power or cooling
work is authorized by this recovery closeout.

## Retained H007 update policy

- **DONE on ai-vm and ai-harness:** automatic APT updates and discovered
  refresh/update timers disabled, with a global indefinite Snap hold. Sova launch
  paths remain pinned; explicit manual updates remain available. See the
  [verified policy and coverage limits](docs/h007-update-policy-20260926.md).
- This supersedes H006's package-installation-enabled policy. Proxmox, Macs,
  future installations and arbitrary external schedulers were not changed.
  Enforce the same policy when provisioning additional Sova nodes.
- Deferring restarts with needrestart does not itself disable package updates.
  [H006 maintenance protection](docs/h006-maintenance-robustness.md) remains
  historical evidence of the policy in effect then.

## Future controlled maintenance software

**PLANNED — not implemented by H007.** No automatic all-package upgrade policy
or updater scheduler is implemented now. Future maintenance must use explicit
authorized windows and preserve manual operator control. Required work:

- Close admission and drain affected work through its owner, accounting for
  queued, active, draining and uncertain operations before changing components.
- Take application-consistent preupdate snapshots/backups after quiescing writers.
  Capture compatible configuration, metadata, artifacts and data/schema versions;
  protect secrets and their restore permissions without exposing them in reports.
  A hypervisor snapshot requires explicit integration and authority; it is not
  an implicit capability of the current VM/node API.
- Review management/inference source coupling so a status-only upgrade need not
  reload a resident model. Preserve explicit provenance and compatibility checks;
  do not bypass existing owner records while that design is pending.
- Stage and pin selected component updates, with reviewed dependency and
  configuration/data compatibility checks. Cover OS/packages, drivers, model
  runtimes and Sova components through scoped procedures, not an automatic
  all-package upgrade.
- Verify health, deterministic warm-up and appropriate smoke checks before
  reopening admission. Record exact versions, outcomes and unresolved failures.
- Support component rollback with configuration/schema compatibility and a
  recovery plan that preserves newer user data. Do not blindly restore an older
  whole-system snapshot over newer conversations or artifacts.
- Recover or pause safely on partial failure; retain ownership and receipts,
  isolate affected components and require reconciliation of uncertain actions
  rather than replaying them or declaring success.

## Future routing and scaling

**ACCEPTED DESIGN / GENERAL ROUTING IMPLEMENTATION PENDING.** H009 adds a fixed
frontier lane beside the two Qwen slots. It initially served GLM-5.3-Flash;
H036 selects native MiMo at 480K. MiniMax profile delivery and fresh delegation
and final Codex delegation passed. Qwen remains coordinator; the
image path stays separate. This is
selective native child delegation, not arbitrary-model selection or distributed
capacity management.

- Implement ModelDefinition / ModelInstance / Node separation and multiple
  general-purpose and specialist models, with N compatible instances per model.
- Keep one configured general-purpose delegation model. Route each delegation
  to a healthy compatible free instance of that same model, otherwise use a
  bounded fair queue; never silently substitute another model or an image
  specialist for general-purpose delegation.
- Validate capabilities, context and quantization/runtime compatibility in
  deterministic code. Enforce shared admission across main sessions, all
  subagents and auxiliary requests to prevent GPU/RAM/instance oversubscription.
- Extend beyond registry observation to explicit workload placement and routing
  only with compatible runtime, hardware, storage, network and security support.
- Before optional load balancing or horizontal harness replication, implement
  session/run/workspace ownership, shared durable metadata/artifacts and
  consistent admission, cancellation, drain, reconnect and recovery behavior.
- Design load-balancing mechanisms and horizontal scalability of MiniMax with
  those prerequisites. This is future design, not a distributed MiniMax runtime
  implemented today. Reserve free capacity atomically through shared admission
  and leases across replicas; readiness or a status-page sample is insufficient.
  Release inference slots before awaiting subagents; unknown capacity is not idle.

See the [future routing contract](docs/sova-architecture.md#accepted-future-model-and-routing-design).
No distributed MiniMax deployment or new capacity benchmark is claimed. General
installer expansion remains deferred; narrow H036 repairs to existing CI are
recorded separately and do not implement a general installer.

## Optional Codex harness

The local Responses adapter, private App Server, persistent per-engine chats,
tools and central engine status are implemented. Keep the pinned App Server's
experimental status explicit. The [H036 gates above](#h036-completion-gates)
supersede the obsolete open-work list from H024 without rewriting its failures.
See [historical H024 results](reports/h024-codex-checkpoint.md) and the
[original completion plan](ai-harness/PLAN-CODEX-COMPLETION.md).

Small manual compaction/recall/continuation, Qwen lane routing and later PDF/image
work have distinct dated receipts; reuse them within their scope. If optimizing
latency, measure gateway validation, tokenization, queue, inference and native
continuation separately. Existing gaps do not establish a unique cause.
Do not change the default engine based only on features or scripted fixtures.

## Flash follow-up qualification

- Measure varied technical input and first-use behavior separately from warmed
  repetitive fixtures. H009's first full-tool request took 620 seconds, while
  its three continuations took 109, 45 and 49 seconds. Do not extrapolate a
  constant speed from either the fastest native decode window or that first turn.
- **H010 completed:** varied 8192-token warm-up and one correct 65536-token
  occupied technical fixture at unchanged 480000 configured context. See the
  [64K report](docs/h010-status-20260927.md). Larger occupied contexts remain
  separate future work; the 1,048,576-position memory estimate is not acceptance.
- A full four-instance overlap test remains unverified. H010 passed both Qwens
  plus image together, but its Flash smoke client never dispatched due test
  coordination. All four instances retained independent resident services.
- Investigate supported prefix reuse in a later pinned runtime. The current
  GLM KPool implementation forces radix caching off for correctness; do not
  bypass that guard as a performance tweak.
- Refine Flash's conservative local context estimator, which can compact prose
  earlier than the backend's actual token capacity. Preserve exact backend
  tokenizer admission and original history while doing so.
- Qualify the new Flash service's 600-second idle/wake behavior separately.
  The current live workflow proves request processing after an idle interval,
  but no controlled before/after CPU-idle measurement was performed in H009.
  H010 naturally observed zero CPU ticks from all 64 expert threads over 376 s
  before successful warm-up; it does not prove the exact 600-second transition.

## Future organizations and access control

**PLANNED — not implemented.** Add organizations, users and permissions with
tenant, session and artifact isolation, and explicit admin/operator/end-user
scopes. Current shared-LAN access is not a tenant or per-user privacy boundary.
