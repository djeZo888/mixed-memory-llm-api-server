# Current Sova backlog

V1 is retired. Carry these still-valid requirements into [Sova V2](https://github.com/djeZo888/SovaV2); do not reopen dated V1 worker phases or operational approvals. The [user vision](docs/VISION.md) defines product direction and the [design input](docs/V2-DESIGN-INPUT.md) makes the next review concrete.

## Four V2 foundation tasks

- [ ] **Redraw architecture and execution flows.** Agree responsibilities, state owners, public interfaces, placement and dependencies. Draw chat, research, recognition, generation/editing, compaction, cancellation, reconnect and restart. Classify V1 reuse. Identify the first working release and later extensions. Done when one current design is reviewed by the user.
- [ ] **Define configurational architecture and exact configuration files.** Specify files, schemas, readers, defaults, precedence, validation, versions, migration and reload/restart effects. Separate model definitions, instances and nodes; separate intent, protected secret references and observations. Done when documented examples validate and components start without consulting historical reports.
- [ ] **Define intra-communication protocols.** Version request, event, error and ownership contracts; define identities, authentication, admission, cursors, idempotency, deadlines, cancellation and actual settlement. Done when each boundary has a direct executable contract check and documented failure behavior.
- [ ] **List tests, write tests and create an execution system.** Map requirements to unit, component, real-model and normal-user workflow tests. Provide reproducible commands, retained original results and clear PASS/FAIL/PARTIAL/NOT_TESTED labels. Done when a clean checkout can reproduce failures and report first-release readiness.

## Gates for the first useful release

- [ ] One user, one PC and one chat: Codex is the sole active engine; Sova selects models and specialist tools automatically, with no model/harness selector or internal configuration clutter.
- [ ] Complete ordinary answers, tool use and research tasks; distinguish an engine's final event from actual task fulfillment. Surface incomplete results and support bounded continuation.
- [ ] Server-owned runs survive browser disconnect/reconnect, without replay. Qualify PC sleep separately. Preserve history, uploads, file cards, public retrieval and interrupted-run recovery.
- [ ] Reliable manual, automatic and repeated compaction: preserve originals, exact constraints and evidence; test summary-only recall separately from retrieval and resumed work. Qualify the agreed context/output limits with real occupied workloads.
- [ ] Technical image understanding: readable labels, values, units, symbols and relationships with source regions and uncertainty. Qualify the normal upload/tool/follow-up flow using representative engineering drawings.
- [ ] Normal image generation, FullHD where supported, and editing: genuine current owner, warmup, decoded saved/public output, follow-up and supported cancellation. Reading and generation operate independently.
- [ ] All required model instances remain resident and can operate concurrently under measured capacity admission. Idle GPU visibility and independent service starts do not pass this gate.
- [ ] Maintenance of one capability preserves unrelated work and fresh health observations. Test readiness/receipt races, distinct host boot IDs, uncertain owners, unavailable specialists and recovery.
- [ ] One complete single-PC rehearsal exercises success, failure, cancellation, reopen and artifact retrieval. Each reused component passes its direct tests before this integration gate.

## Later requirements, separate from the first release

- [ ] Durable project/task memory and Project mode: coordinator, bounded worker contexts, minimal briefings, ownership, independent checks and reviewed integration.
- [ ] Organization-centered ownership; people and service identities; authentication and scoped read/write/admin permissions for chats, files, jobs, tools and workers.
- [ ] Public agentic API and headless Linux worker stub with managed shell/file sessions, reconnect, artifacts and cancellation.
- [ ] Configurable model definitions, multiple compatible instances, placement, shared admission and horizontal scaling by organization ownership.
- [ ] Status improvements: readable tabs/tables, optional multi-host sensors, stable sensor identities and units, configurable polling and freshness, protected collector-only credentials.
- [ ] Hardware-critical handling that stops or aborts active requests while preserving services and resident models, durable incidents and manual recovery. Qualify each runtime's actual pause/cancel support; retain unsupported cases explicitly.
- [ ] Broader fan management, notifications and controlled incident exceptions. CHA_FAN3's unresolved physical behavior remains deferred; retirement is not fan-operation authority.
- [ ] Controlled maintenance windows, application-consistent backups, compatible updates and rollback that preserves newer user data. General installation follows a qualified supported deployment.
- [ ] Specialist tools and extensions, future audio/video, programmatic CAD with exact geometry/units and deterministic validation; separately review format licensing. Sandboxed coding is an optional extension.
- [ ] Inspectable AI-authored first-party development and controlled self-improvement, with human requirements, review and production promotion decisions.

Historical MiniMax interoperability, arbitrary old runtime migrations, dated worker-session tasks and unfinished qualification packet chains are not carried forward as product requirements.
