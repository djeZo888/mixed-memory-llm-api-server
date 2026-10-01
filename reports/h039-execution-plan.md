# H039 — compaction reliability and technical vision preparation

Authorized on 1 October 2026. This plan supersedes H038's closed execution
window and its prohibition on new models only for the work described here.
The user permits Sova downtime and retirement of the smaller Ada Qwen. Creative
image acceptance remains deferred. No Proxmox, driver, fan or upstream Codex
upgrade is included.

## Current hardware hold

The user subsequently authorized orderly ai-vm guest shutdown to install a second Ada 48 GB. The assigned artifact attempt has ended with a guarded staging failure and no running download. C owns the shutdown. Freeze new VM work and leave the guest down until the user confirms installation is complete; Mac source tasks can finish within their recorded deadlines. Live compaction/vision qualification remains deferred. See the current roster for actual terminal and shutdown receipts.

## Bounded parallel work

Root coordinates, reviews and publishes. Actual implementation is performed by
fresh native Codex CLI sessions on the two Macs, using `gpt-6.1-sol` with `ultra`
reasoning. Each task has a separate checkout, prompt, session ID, deadline and
terminal receipt. A Mac can run two independent sessions; those sessions do not
share a conversation or automatically inherit this orchestrator's full history.

| Task | Mac | Scope and owned files | Restrictions |
| --- | --- | --- | --- |
| A: native compaction | mac-worker1 | Exact pinned Codex source audit; narrow lifecycle fixes in `codex-engine.ts`, `codex-connection.ts`, their tests; `reports/h039-compaction-native.*` | No shared VM writes, live inference or deployment; propose changes outside this ownership first |
| B: retention acceptance | mac-worker2 | `ai-harness/acceptance/compaction/`, isolated scorer/controller fixtures, `reports/h039-compaction-retention.*` | No engine, gateway, deployment or database-schema changes; no live tests until reviewed |
| C: vision artifacts/runtime | mac-worker1 | Pinned official Qwen3.5-9B and PaddleOCR-VL-1.6 downloads on ai-vm; isolated candidate configuration under `configs/vision/`, `containers/vision/`, `scripts/vision/`; `reports/h039-vision-runtime.*` | Sole VM-storage writer; no GPU load, production activation, driver/OS changes or destructive cleanup |
| D: vision tool bridge | mac-worker2 | New technical-vision contract/client/tool modules and isolated tests; `ai-harness/docs/technical-vision.md`, `reports/h039-vision-bridge.*` | Fixture-backed preparation; no existing registry/engine/gateway activation or shared deployment |

Each source task has at most 90 minutes, and the initial H039 coordination window
ends at **02:25 UTC / 04:25 Ljubljana on 1 October**. Task C closes its paid CLI
once a durable bounded download is launched; a download is not kept inside a
paid agent waiting loop. Native and background-process deadlines are recorded
separately. No automatic continuation or extra window is implied.

Each worker exports a compact result and actual changed paths, source commit,
tests, failures, next steps and ownership. Raw prompts, events, technical test
answers, credentials and large traces remain in private task directories.
Implementation commits remain isolated until root review. No worker merges or
deploys another task's work.

## Shared contracts

### Compaction

Retain Codex **0.158.0**, upstream source
`064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`, Qwen as the main model,
480,000 configured context, 400,000 automatic compaction threshold and 65,536
maximum output. Main Qwen and MiMo child compaction are distinct paths; MiMo
compaction quality is unqualified. Do not change routing by merely replacing a
model string.

Task A must establish native triggering, replacement/persistence, failure and
settlement semantics before claiming atomic rollback. Task B provides a new
50–100-fact technical corpus and deterministic scoring, separating summary-only
recall, source retrieval and real continuation. Missing usage metadata must
remain unknown rather than becoming fabricated zero occupancy. Tests must
retain failed outcomes and original history.

Task B's reusable acceptance record includes runtime/model revision, action and
native thread/turn IDs, trigger type and evidence, cycle number, actual or
unknown token counts, exact critical/noncritical scores, retrieval use,
duration and settlement. Native-only metadata that cannot be obtained is
explicitly absent. Do not repeat the old four-fact paste or MiMo 950K test.

### Technical vision

The user approved **Qwen/Qwen3.5-9B BF16** and
**PaddlePaddle/PaddleOCR-VL-1.6** as the first dedicated-Ada pair, replacing the
earlier existing-Qwen-first research order. Pin actual official revisions and
artifact checksums. Approximately 21 GB of combined weights does not qualify
their combined runtime fit: cache, page crops, activation peaks and parser
components must be measured later with approximately 7% free Ada VRAM.

The smaller 200K Qwen may be retired. H038 already recorded it retired and the
internal Ada reassigned to creative images. Task C must report current actual
GPU UUIDs and service ownership; do not assume an unused Ada from old names.
This preparation phase does not silently replace the creative-image service.
Root will coordinate any reassignment after artifacts and runtime candidates
are ready. The user is repairing the external Ada and permits Sova downtime.

Task D prepares `technical_image_analyze` with an external service contract,
without sending pixels to Codex natively. Validated source references identify
uploads/workspace/PDF pages; results include model/revision, page and crop
coordinates, exact labels/values/units, structured observations, evidence and
uncertainties. OCR extraction and derived interpretation are distinguished.
Raw DWG needs a licensed CAD decoder; no new DWG dependency is authorized.
Use fixtures for geometry, source validation, timeout, cancellation, duplicate
jobs and unavailable backends. Do not enable a capability without live evidence.

## Integration gates after source preparation

1. Review A/B contracts, diffs and tests; address factual retention and native
   lifecycle gaps, rather than marking source fixtures as live qualification.
2. Stage one coherent candidate with one deployment owner. Preserve chat IDs,
   engines, transcripts, files, protected configuration and rollback artifacts.
3. Run three small compaction cycles with corrections and exact-fact grading;
   cold resume; lifecycle failure cases. Capture one justified automatic trigger
   with actual metadata only after the small suite passes.
4. Review C/D artifacts and serving support for Ada SM 8.9. When a selected Ada
   is available, measure both resident services and bounded vision profiles.
5. Qualify technical diagrams through an ordinary Codex tool call/follow-up,
   retaining uncertainty and source regions. General OCR does not qualify
   electrical connectivity or CAD reasoning.
6. Publish reviewed evidence; resolve remaining integration/CI issues before
   merging PR #11. Do not declare compaction universally lossless or Sova fully
   complete from a passing small fixture.

See the [handoff](h039-handoff.md),
[compaction plan](../todo/context-compaction-reliability.md),
[vision plan](../todo/technical-image-understanding.md), and
[future vision](<../docs/Vision for future regarding this project.md>).


The worker's [shutdown receipt](h039-ai-vm-shutdown.json) records accepted guest poweroff at **01:33:22 UTC / 03:33 Ljubljana**, command exit 0, fsynced guarded receipt and two subsequent SSH connection-closed probes. Independent hypervisor/physical stopped state was not checked. Leave ai-vm down for the user's hardware installation; no automatic restart or further VM work before their confirmation.
