# Sova TODO

Current H036 completion gates, retained H007 update policy and future design
are separate below. See the
[system overview](README.md), [architecture](docs/sova-architecture.md) and
[H006 closeout](docs/h006-closeout-20260926.md) for current boundaries and dated
evidence. This list is not an implementation or deployment acceptance report.

## H036 completion gates

See the [current checkpoint](reports/h036-completion-checkpoint.md) and
[results](reports/h036-completion-results.json). MiniMax remains default;
Codex remains a per-chat preview. Root alone finalizes publication.

- **BLOCKED / current state unknown:** resolve the HTTP/SSH connectivity loss
  reported around September 29, 23:32 UTC, then record current availability and
  owned-work settlement without replaying uncertain actions. The user reports
  Proxmox reachable with no changes; the VM cause remains unknown. W2 CLI exit
  at 23:40:42 UTC does not establish guest-job settlement. Recovery stays root-coordinated.
- **PARTIAL:** native Qwen compaction completed at 23:28:57 UTC and retained
  four facts. Automatic triggering is inferred; RAW_AUTO metadata is absent.
  Initial paste run `d17d4942` completed. Finish final/tool continuation, reload
  and settlement review for compaction/follow-up owner
  `346c89f0-a3f6-4668-b3ed-e6230111cf8f` in session `f006fc27`. Missing receipts
  do not establish a full PASS.
- **PENDING / UNKNOWN:** MiMo 480K first-turn read passed and a second tool-result
  turn was sent at 23:28:20 UTC; complete continuation/settlement are unknown.
  Deploy/verify the reviewed profile fix `47d386` (root `4d927fee`) and complete
  fresh both-engine delegation. The fix is source-ready but UNDEPLOYED.
  Readiness at 23:07:48 passed; historical 950K qualification is separate.
- **NOT_CONFIRMED:** completed browser ZIP save. HTTP response/CRC and 2 uploads
  plus 2 outputs passed; the browser produced only a 1,038-byte partial file.
- **PENDING:** root's final capability/qualification descriptors, current public
  readiness and reviewed default-branch merge. Root verified all eight GitHub
  checks at `92325eff` SUCCESS and subsequently all eight push/PR checks at
  root candidate `4d927fee` SUCCESS; the profile fix is still UNDEPLOYED.
  No result for later commits is implied. Global gates remain closed pending proof. Do not announce maintenance
  removal or switch defaults. The last acceptance browser window was open;
  recovery must verify maintenance rather than assume the scheduled watcher ran.
- **PARTIAL / UNSUPPORTED:** MiniMax native image transport works but recognition
  is partial; Codex native vision is unsupported. Keep document extraction/OCR
  distinct. Broader media support and MiMo compaction quality remain separate work.

Guarded child edit, completed-image follow-up/render/download/reload, fresh
image generation, coding/follow-up, PDF/OCR and the plain-HTTP secure UUID repair
have passed their stated cases. Preserve earlier failures and reuse that evidence.
This TODO does not authorize new live work or repeated benchmarks.

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
H036 selects native MiMo at 480K; fresh current-capacity delegation acceptance
and MiniMax profile delivery remain pending. Qwen remains coordinator; the image path stays separate. This is
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
