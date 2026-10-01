# Vision for future regarding this project

**Sova — user direction recorded on 1 October 2026.**

This document records the intended direction of Sova. It separates future goals
from deployed capabilities and does not authorize an unbounded implementation,
new model installation or hardware change. Detailed work remains in the
[TODO index](../todo/README.md). Current deployment evidence remains in the
[project README](../README.md) and dated reports.

## 1. Purpose

Sova should become a practical, locally hosted agentic AI system for lengthy
technical discussions and substantial projects: software engineering,
electronics, microcontrollers, electrical and mechanical engineering, technical
research and eventually CAD. It should operate through useful tools and
specialist models, with clear progress, durable results and recoverable work.

The target is useful end-to-end work, rather than a visual clone of a particular
commercial product. Local inference and local tools should support operation
without a paid cloud dependency. Internet research still requires connectivity;
offline mode should use previously saved documents, source material and local
tools and clearly identify when current external information is unavailable.

## 2. Immediate priorities

1. Make context compaction dependable for long technical discussions and projects.
2. Use the existing fast Qwen as the default compactor; qualify retention and
   recovery instead of assuming a larger model produces a better summary.
3. Add technical image understanding through a specialist-to-text bridge.
4. Defer creative image generation/editing qualification for now.

MiMo is the current frontier worker for difficult reasoning. Its tool workflows
passed; its compaction quality has not been independently qualified. Qwen has
passed small and large compaction cases, with important remaining evidence gaps.
See the [compaction plan](../todo/context-compaction-reliability.md).

## 3. Durable memory beyond one context window

Compaction must support continued work without silently discarding original
conversations, uploads, generated files or task evidence. A summary is a working
index and continuation aid, not the only surviving copy of a project.

Use complementary records:

- Original, source-addressable conversation and tool history.
- Explicit user constraints and accepted decisions, including superseded choices.
- Project interfaces, exact identifiers, units and numerical requirements.
- Task state, completed checks, failures, unresolved questions and next steps.
- Source files, artifact versions and references to the evidence behind claims.
- Summaries appropriate to the next bounded task, with retrieval of omitted detail.

Protect these records from cross-project and future cross-organization mixing.
An ordinary narrative summary must not be treated as authoritative evidence that
a test passed or that a user granted permission. Retain those facts from their
actual records. Where a summary loses a detail, Sova should be able to retrieve
the relevant original material instead of guessing.

The goal is the experience of persistent project memory. It is not lossless
unlimited model context. Software should preserve recoverable state through
timeouts, failed summaries, interruptions and restarts; summary quality must be
measured on representative technical work and repeated compaction cycles.

## 4. Project mode: orchestrator and bounded workers

Add an explicit **Project mode** toggle when the underlying workflow is qualified.
The main chat remains the user's planning and coordination thread. Its agent
owns the big picture: objectives, constraints, dependencies, decisions,
integration and final review. Detailed exploration, implementation and testing
go to workers.

Each worker receives a bounded task in its own context, with only the necessary
briefing and references. A task brief should identify:

- The concrete objective and acceptance criteria.
- Relevant constraints, interfaces and source files.
- What the worker may change, and who owns shared files or deployment.
- Its resource/time budget, dependencies and required result format.
- The evidence to return and any known failures or unresolved assumptions.

Completed workers return a concise result with artifacts and validation evidence.
The coordinator does not ingest full raw logs by default. A later independent
task can start a fresh worker context; follow-ups resume a worker only when its
retained state is useful. Workers may themselves compact when necessary.

Codex already supplies native child threads and delegation. Sova's retained
tests verify child execution and parent result continuation. They do not yet
prove that every child starts with only a minimal briefing: inherited-context
behavior needs an explicit first-request inspection before Project mode is
claimed complete.

~~~mermaid
flowchart TD
    User["User / main project chat"] --> Coordinator["Coordinator: plan, delegate, review"]
    Coordinator <--> Memory["Project state, decisions and original evidence"]
    Coordinator --> Briefs["Bounded task briefs and resource admission"]
    Briefs --> WorkerA["Worker A / separate context"]
    Briefs --> WorkerB["Worker B / separate context"]
    Briefs --> Specialist["Specialist model or tool"]
    WorkerA --> Results["Results, artifacts and check receipts"]
    WorkerB --> Results
    Specialist --> Results
    Results --> Coordinator
    Results --> Memory
~~~

Independent contexts do not create additional GPUs or inference slots.
Admission, cancellation, deadlines and fair queues apply to the whole worker
tree. Release a parent's inference slot before it waits for children. Isolate
parallel writes and keep one owner for each shared deployment.

## 5. Headless Linux workers and a public agentic API

Shell and CLI operation are core capabilities. A future small worker stub on
headless Linux should connect a machine to Sova's agentic API, making its
authorized shell, files and tools available for coding, administration and
operations. Sova should not require a human-oriented desktop or computer-use UI
to perform work that can be expressed through commands and structured data.

The worker protocol needs durable job identities, progress, output bounds,
artifact transfer, reconnect, cancellation and unambiguous completion. Long
commands should run through managed sessions with incremental output. A network
disconnection must not accidentally rerun a command or be mistaken for stopping it.

Capabilities and credentials belong to the authorized organization and worker.
Distinguish an ordinary coding workspace from machine administration; keep
operator authority outside untrusted project files and document contents.
Later sandboxed coding environments remain an extension, not a prerequisite for
every headless deployment.

## 6. Specialist models and technical perception

General-purpose models coordinate work. Specialist models handle operations
where dedicated capability improves quality or efficiency. Examples include
technical vision, document parsing, image transformation and future audio/video
work. Models are replaceable; the system should route by qualified capabilities
and healthy available instances rather than hardcoded GPU indices.

Technical vision should extract meaningful descriptions of drawings, diagrams,
charts, schematics and scanned documents. Preserve labels, dimensions, symbols,
connections, spatial relationships and uncertainty. Return structured textual
evidence to the general-purpose agent, so native vision in the selected harness
is not mandatory.

Large engineering drawings require whole-page interpretation plus readable
crops and, where available, original vector information. A guessed net
connection or dimension must not become an accepted engineering fact.
See the [technical vision plan](../todo/technical-image-understanding.md) and
[model research](research/2026-10-01-memory-and-technical-vision-models.md).

## 7. CAD through geometry and programmatic tools

Explore CAD creation and modification using structured geometry, parametric
operations and tool APIs. STEP, DXF and other representations can expose
geometric information; raw file tokens alone do not ensure that an LLM
understands the object or preserves valid topology.

Prefer compact queries and operations through a qualified geometry kernel,
with exact units, tolerances and entity references. Validate solids, constraints
and assemblies with deterministic tools. Rendering and visual comparison may
complement those checks without requiring the model to operate a CAD application's
GUI. DWG conversion/parsing needs a separately reviewed, licensed toolchain.
This is a research direction, not a promised current capability.

## 8. Organizations, users and permissions

**Organization is the central ownership entity.** Chats, projects, files, jobs,
worker registrations and applicable configuration belong to an organization.
An organization can have multiple users with different authentication methods
and read/write/administration permissions.

An API key represents an authenticated principal with explicit organization
membership and scoped permissions, rather than a bypass around the user model.
Support service identities as well as people. Future policy must cover chat and
artifact access, model/tool use, workspace writes, worker administration and
system administration. Authentication and authorization are distinct.

This direction is accepted; the detailed schema, policy model and migration plan
will be a separate task. No accounts or tenancy boundaries are implemented by
this document.

## 9. Horizontal scalability and placement

Every service has a logical identity and configured placement. A deployment may
run all services in one suitable machine/VM, split harness and inference, or use
many machines with multiple instances of each model. BMC access and specific
datacenter hardware remain optional.

Initially scale harness capacity by assigning groups of organizations to
different frontend/harness servers. Route each organization's work to its
owner. Cross-server model use needs shared admission; moving an organization
requires coordinated migration of its data and active work.

A load balancer does not by itself supply tenancy isolation, shared job
ownership or consistent storage. Preserve these prerequisites as explicit work.
Status and health must describe configured services and actual observations,
including missing hardware, without blocking unrelated healthy services.

## 10. Harness selection

Use the harness that performs best for Sova's actual workloads. Codex is the
current new-chat default. There is no requirement to maintain Codex/MiniMax
conversation interoperability or to develop a lossless native-history converter.

MiniMax may be retired once the chosen Codex implementation is qualified and
existing conversations/files have an agreed preservation path. It remains
selectable in the recorded current deployment; this vision does not remove it.
Future scaling plans should describe the active harness rather than assume that
MiniMax is permanently part of the architecture.

## 11. Fully AI-developed first-party code

The user's goal is that **every new line of first-party Sova code is authored
by AI**. Humans supply requirements, decisions, permissions, evaluation and
review. Retain task records, model/harness identity where available, code
changes and validation evidence so this development approach is inspectable.

Do not claim that upstream Codex, model runtimes or third-party libraries were
written by Sova's AI workers. Preserve their attribution and licenses.
Historical code without authoring evidence must remain explicitly unverified;
do not invent retrospective provenance.

Self-improvement is a long-term direction: Sova should propose, implement,
test and review improvements through bounded work. Production promotion still
requires controlled maintenance, compatibility checks and rollback. Improving
itself does not mean silently deploying untested changes.

## 12. Order of development

1. Qualify compaction lifecycle, technical retention and source-linked recovery.
2. Qualify technical vision and the textual specialist bridge.
3. Add Project mode and durable project/task memory.
4. Design and implement organizations, permissions and worker identities.
5. Expose a stable agentic API and headless Linux worker protocol.
6. Scale by organization ownership and shared model admission.
7. Expand specialist capabilities and investigate programmatic CAD.
8. Complete controlled maintenance, reproducible installation and development
   provenance as those foundations stabilize.

These priorities guide later plans. Each implementation should have a concrete
scope, bounded execution window and honest pass/fail evidence.
