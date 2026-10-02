# Sova architecture and V2 foundation TODO

Added 2 October 2026 at the user's request. **PLANNED: the V2 rebuild decision
is pending.** These items authorize recording design work, not replacing the
running installation or discarding V1 code, credentials, weights or histories.

Simplicity is a design constraint: each component must have one clear purpose,
an explicit owner and contract, and an independent way to run and test it.
Separate working units do not require a separate service for every module.
Every additional process, protocol, configuration file or dependency must solve
a stated requirement. Keep historical evidence separate from current design
and runtime state.

## 1. Redraw architecture and flow according to the current design

- [ ] Redraw the architecture and execution flows, distinguishing the actual V1
  deployment from the user's current intended design and the proposed V2.
  Identify which description is authoritative and date the observed baseline.
- Define component responsibilities, public interfaces, state ownership,
  dependencies, model/GPU placement and deployment boundaries. Include chat,
  background runs, history/files, the agent engine, automatic model routing,
  model services, and lifecycle/resource management.
- Draw normal chat, research, image recognition, image generation/editing,
  compaction, browser disconnect/reconnect, cancellation and restart/recovery.
  A browser observes a server-owned run; it does not own its lifetime.
- Show independent text, recognition and generation services. Unavailability or
  maintenance of one must not disable another without a documented shared
  resource conflict. Models are selected automatically; no model/harness
  selector is part of the chat UI.
- Inventory V1 components as **reuse**, **simplify**, **replace** or **defer**,
  citing direct working tests and known failures. Retain model downloads,
  useful runtime adapters, persistence/artifact code and relevant tests where
  they satisfy the new boundaries; do not inherit operational chains merely
  because they already exist.
- Define the smallest first working version and its acceptance gates. Record
  longer-term requirements separately so deferred scope does not become an
  immediate dependency.

**Done when:** one current architecture and flow set describes the agreed
component boundaries, reuse decisions, first-release scope and later extension
points, and the user has reviewed the proposed design before rebuild execution.

## 2. Configurational architecture: define configuration files

- [ ] Define configuration architecture, the exact files, their schemas and
  examples, and which component reads each value.
- Establish one editable source for deployment intent: nodes, model definitions,
  model instances, stable GPU UUID placement, endpoints, runtime/model pins,
  routing policy, context/output/compaction limits, queues/timeouts and storage.
  Derive service-specific configuration where possible instead of duplicating
  independently editable values.
- Separate declarative configuration, protected secret references, and observed
  runtime/job state. Define defaults and override precedence, validation,
  schema versions/migrations, and which changes require reload or restart.
- Keep general model definitions distinct from instances and hosts. Preserve the
  ability to use multiple compatible instances without hardcoding the present
  five-card installation into the application.
- Provide a deterministic configuration-validation command and representative
  supported deployment examples. Document invalid or unsupported combinations
  with actionable errors.

**Done when:** every setting has one owner and documented meaning, examples
validate, and services can start from the documented files without hidden
dependencies on historical operational reports.

## 3. Define intra-communication protocols

- [ ] Define and version the contracts between the UI, application/run owner,
  agent adapter, model services, artifact store and lifecycle/resource owner.
- Specify request/response and event schemas, authentication, capability and
  readiness discovery, identifiers, and ownership. Distinguish model identity,
  service instance, host boot, chat, run, task and artifact IDs; different hosts
  must not be required to share a boot ID.
- Specify streaming and reconnect cursors, progress versus final results,
  queued/running/completed/failed/cancelled/uncertain states, deadlines, error
  codes, cancellation acknowledgement and actual settlement.
- Define idempotency and retry rules. Browser reconnection must not replay work;
  uncertain side effects require reconciliation rather than blind resubmission.
  Define how incomplete task fulfillment is surfaced separately from a native
  engine declaring its turn complete.
- Keep model endpoints independently callable for direct smoke tests. Separate
  observation from lifecycle mutation and keep locks scoped to their resources;
  a workflow waiting for its next step must not hold a global lifecycle lock.
- Define compatibility checks at configuration/deployment boundaries and the
  minimal current health/ownership checks needed during requests. Preserve
  real authentication, process ownership, isolation and capacity protection
  while removing dependence on chains of historical qualification packets.

**Done when:** each boundary has an executable contract check, documented
failure/timeout behavior and a standalone client or fixture, with no undocumented
cross-component state dependency.

## 4. List tests, write tests, create an execution system

- [ ] Create a requirement-to-test catalogue, implement the cases, and provide
  an execution system with reproducible commands and results.
- Separate fast unit tests, component/contract tests, real model-service smoke
  tests and normal single-PC chat workflow tests. Fixtures must not be reported
  as real GPU or complete workflow acceptance.
- Cover complete answers and premature-final handling; follow-ups; files and
  public retrieval; disconnect/reconnect; queueing/cancellation/settlement;
  application restart and interrupted-run recovery; manual/automatic/repeated
  compaction and retained context/history; and automatic Qwen/MiMo routing.
- Cover recognition of images/drawings and OCR; generation/editing at supported
  sizes; warmup and current-owner recovery; unavailable specialist behavior;
  actual concurrent model operation; stale telemetry and resource limits.
- Add regression tests for maintenance of one capability not blocking another,
  distinct host boot IDs, readiness after startup, and receipt publication races.
- Make deterministic suites runnable with one documented command and suitable
  for CI. Keep expensive live suites explicitly selected and bounded, with
  fixtures, model/runtime/config versions, original logs, cleanup and concise
  machine-readable PASS/FAIL/NOT_TESTED results.
- Require each reused component to pass its direct tests before integration,
  and require the first working version to pass the ordinary user flows. Source
  checks or a collection of passing helpers cannot substitute for those flows.

**Done when:** the first-release requirements have runnable tests, failures can
be reproduced from a clean checkout, and the same execution system produces a
clear component and end-to-end readiness report.

## Starting evidence

The [H046 six-hour report](../reports/h046-six-hour-status-20261002.md) records
the latest accepted basic chat, tab-disconnect continuation and manual compaction
checks, plus unresolved research completion and offline image capabilities.
Earlier success is a reuse candidate, not proof that it survives a new boundary
or deployment. Historical architecture documents remain reference material until
item 1 produces a current authoritative replacement.
