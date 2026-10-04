# Sova: the user's future vision

This preserves the user's direction recorded on 1 October 2026 and incorporates the later corrections recorded in V1's final instructions. It describes goals, not deployed capabilities. The [original vision](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/1f9bd99621d079f049d945dd1cc65bce96ae0c29/docs/Vision%20for%20future%20regarding%20this%20project.md) remains in history; older choices in it are superseded where stated below.

## Purpose and latest first-release direction

Sova should be a practical locally hosted agentic system for long technical discussions and substantial software, electronics, microcontroller, electrical/mechanical engineering and research projects, eventually including CAD. Useful tools, specialist models, clear progress, durable results and recoverable work matter. Local inference and tools should enable operation without a paid cloud dependency. Offline work uses saved sources; current internet research still requires connectivity and must identify unavailable external information.

The latest product direction is **Codex as the sole active engine, automatic model/tool selection, and no model or harness selector**. One chat should move from ordinary Qwen work to MiMo for difficult reasoning/research, to technical image understanding, or to image generation when needed. The first useful release targets one user on one PC. This supersedes the original vision's selectable MiniMax/default-engine wording. Preserve old conversations and files through an agreed migration path; engine interoperability and a lossless native-history converter are not required.

All required model instances must be able to remain resident and run concurrently within measured resource limits. Technical reading and creative generation are independent capabilities. The original temporary deferral of generation is historical; the final V1 work requested both reading and generation. A simple chat interface should not expose internal harness names or deployment details.

## Memory that outlives a context window

Compaction supports continued work without discarding original conversations, uploads, generated files or evidence. A summary is a continuation aid and index, not the only surviving project record. Retain source-addressable history, explicit constraints and decisions, superseded choices, exact interfaces/identifiers/units, task state, artifacts and check results. Retrieve omitted details instead of guessing. Never infer user authorization or a passed test from ordinary summary prose.

Use the fast Qwen compactor as the V1 comparison baseline; measure technical retention, repeated cycles and recovery. MiMo's intelligence does not establish better summarization. The experience sought is persistent project memory, with project and future organization isolation. It is not a promise of lossless unlimited model context.

## Project mode and bounded workers

An eventual Project mode leaves the main chat as coordinator of objectives, constraints, dependencies, decisions and final integration. Workers receive bounded tasks in separate contexts: objective, acceptance criteria, needed sources, permitted changes, resource/time budget, ownership and expected evidence. Return concise results and artifacts; the coordinator can retrieve raw records when needed. Test actual first-request inheritance before claiming a minimal briefing.

Independent worker contexts do not create inference capacity. Admission covers the whole worker tree, including compaction and specialist calls. Parents release inference slots before waiting for children; parallel writes and shared deployments have explicit owners. Fresh contexts are appropriate for independent tasks, while retained useful state can support a follow-up.

## Headless operation and specialist tools

Shell and CLI work are core. A small headless Linux worker stub should expose authorized shell, files and tools through Sova's agentic API, without requiring a desktop for work expressible as commands and structured data. Durable job IDs, progress, bounded output, artifacts, reconnect, cancellation and unambiguous settlement are required. A lost connection must not rerun a command or imply it stopped. Distinguish coding-workspace access from machine administration; untrusted project files cannot grant operator authority.

General agents coordinate specialists for technical vision, document parsing, image transformation and later audio/video or other extensions. Route by qualified capability and healthy compatible instances. Technical vision must preserve drawing labels, dimensions, symbols, connections, spatial relationships and uncertainty through whole-page views, readable crops and original vector information where available. Return source-linked text to the general agent. A guessed dimension or junction cannot become an accepted engineering fact.

Programmatic CAD is a research direction: geometry queries, parametric operations and qualified tool APIs, exact units/tolerances/entity references, and deterministic checks for solids, constraints and assemblies. Rendering supplements those checks. Raw CAD tokens do not establish understanding; DWG parsing/conversion requires separately reviewed tooling and licensing. Sandboxed coding environments are a later extension, not a prerequisite for every headless worker.

## Organization ownership and scale

**Organization is the central ownership entity.** Chats, projects, files, jobs, worker registrations and applicable configuration belong to an organization. Multiple people and service identities have authentication and explicit permissions. API keys identify scoped principals with organization membership; they do not bypass authorization. Protect chat/artifact access, tool/model use, workspace writes and worker/system administration.

Services have logical identities and configured placement. One suitable machine/VM, split harness/inference, and multiple hosts or instances are all valid targets; BMC and particular datacenter hardware are optional. Later scale harness capacity by assigning organizations to owning servers. Cross-server inference needs shared admission; moving an organization needs coordinated data and active-work migration. A load balancer alone supplies neither ownership nor consistent storage. Missing hardware must be visible without hiding unrelated healthy services.

## AI-developed first-party software

The user's goal is that **every new line of first-party Sova code is authored by AI**. Humans provide requirements, decisions, permissions, evaluation and review. Retain task records, available model/engine identity, changes and validation evidence. Do not claim that upstream runtimes/libraries were AI-authored by Sova or invent provenance for older code.

Self-improvement is a long-term direction: propose, implement, test and review bounded improvements. Promotion requires controlled maintenance, compatibility checks and rollback. These goals do not authorize silent deployment or unbounded autonomous changes.

## Development order

First establish a small working chat system with reliable compaction and technical vision, then complete independent generation and the agreed first-release workflow gates. Keep Project mode, organization permissions, headless API/workers, horizontal scaling, wider specialists and CAD as explicit later scope. Installation, maintenance and provenance mature with qualified foundations. [TODO](../TODO.md) records the concrete backlog; [V2 design input](V2-DESIGN-INPUT.md) is the next design review.
