# Sova TODO

The deployed harness, image and status features described here are documented
from `feature/system-topology` (PRs 5–8) and are **not yet merged into main**.
Their current source/configuration/evidence links explicitly target that
feature branch; this main-based change adds documentation only.

Current H007 work and future design are separate below. See the
[system overview](README.md), [architecture](docs/sova-architecture.md) and
[H006 closeout](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/docs/h006-closeout-20260926.md) for current boundaries and dated
evidence. This list is not an implementation or deployment acceptance report.

## Immediate H007 policy

- **IN PROGRESS — Worker1: disable all automatic OS, package and Sova updates
  now**, preserving explicit manual update action. Root will integrate
  Worker1's verified outcome and exact scope later. This documentation task
  neither changes hosts nor claims that disabling is complete.
- This manual-update policy supersedes H006's package-installation-enabled
  policy going forward; the historical report remains unchanged. Worker1's
  outcome is **not yet accepted**. The expected
  [root-owned H007 policy report](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/docs/h007-update-policy-20260926.md) is
  **pending publication**, not evidence of completion.
- Keep needrestart protection distinct: deferring automatic restarts of managed
  AI services does not disable package installation or every restart mechanism.
  [H006 maintenance protection](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/docs/h006-maintenance-robustness.md) remains dated
  evidence; H006 correctly recorded security package updates enabled then.

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

**ACCEPTED DESIGN / IMPLEMENTATION PENDING.** The current harness still uses one
Qwen family, two instances and two shared inference slots. The image tool path
is separate; there is no GLM harness integration or arbitrary-model selection.

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
installer implementation and tests remain paused.

## Future organizations and access control

**PLANNED — not implemented.** Add organizations, users and permissions with
tenant, session and artifact isolation, and explicit admin/operator/end-user
scopes. Current shared-LAN access is not a tenant or per-user privacy boundary.
