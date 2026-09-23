# ai-harness 0.0.3 — image integration and editing repair

User-approved implementation plan, 23 September 2026.

## Goal and fixed decisions

Integrate Qwen-Image-2.1 into pinned MiniMax for image generation, reference-based
creation and natural-language editing, including repair of observed editing
defects. All creative image transformations use the dedicated Ada image service.
Keep it resident/warm between requests and preserve both480K text Qwens.
Public output maximum1920x1080, opaque PNG only. Originals remain unchanged;
edits create new versions. Ask before resizing oversized uploads or making
necessary canvas adjustments. Minor creative variation is acceptable; severe
texture, contrast or lighting damage is not. Masks, pixel-perfect inpainting,
transparency, new models, GLM, Proxmox and general installer work are excluded.

## Required editing repair

The retained teapot recolouring failed preservation in SGLang and the reference
implementation. Its cause is unproven; weakening acceptance or changing runtime
alone is not a repair. Trace original/normalized pixels, conditioning and prompt
encoding, model/numerical/scheduler configuration, native decode and public output.
Check orientation, colour/alpha handling, reference order/geometry and unintended
resampling against pinned official source. A bounded VAE roundtrip may separate
reconstruction damage from instruction following.

Retain the exact original image, instruction and seed42 as regression evidence.
Current40-step guidance-free settings follow upstream recommendations; guidance
experiments need a specific hypothesis. Correct a demonstrated defect narrowly,
with meaningful focused tests and preserved generation behavior. Initial budget:
six diagnostic/editing requests, each hypothesis and observation recorded. Stop
for root review at that boundary, without an automatic sweep or broader campaign.
Accept repair only after original regression, independent edit and follow-up edit
achieve requested changes without severe artifacts or major unintended changes.
Preserve all old failures and before/after evidence. Unresolved model limitations
remain explicitly unqualified; generation delivery is not completed editing.

After repair, qualify single-reference1024x1024 then larger sizes through FHD
where safe; two references have separate qualification starting1024x1024. FullHD
editing needs explicit bottom8 reference padding to native1920x1088 followed by
bottom8 output removal, with no resampling of original pixels. Measure per-operation
memory, retaining5% device-free and15% host margin. Publish only actual accepted
operation/size/reference-count profiles; generation evidence does not prove edits.

## MiniMax and host image jobs

Add MCP image_capabilities, image_generate and image_edit to existing MiniMax.
Inputs are prompt, supported size, optional seed and validated upload/workspace/
prior-result references. Return artifacts/metadata, not base64 context payloads.
Keep backend credentials outside containers/browser; reuse session-scoped internal
authorization and the authenticated fixed ai-vm image API.

Host-side persistent image broker: one active job, eight waiting,30-minute queue
deadline, existing15-minute backend budget. Persist prompt/seed/references/state
and output provenance. Stable submission IDs prevent reconnect duplicates. Retry
only known non-admission; never replay ambiguous completion. Browser disconnect
does not cancel. Queued jobs can stop immediately; dispatched jobs retain their
slot until settled because native GPU cancellation is unavailable. Restart marks
unresolved jobs interrupted and reconciles availability before further dispatch.
Image jobs never hold a text inference slot. Main agents and subagents use the
same reviewed image skill/tools; no alternative paid or generative fallback.

## Chat and files

Reuse uploads, reply-specific activities, previews, downloads and ZIP. Add real
image job states/elapsed time; dimensions/model/seed; Use for next edit; and a
user-operated resize/canvas approval card with original/proposed dimensions.
Approval binds exact input and adjustment, cannot be supplied by the model, and
does not overwrite originals. Return clear unsupported/unavailable errors.
Default generationFHD landscape unless another supported format is requested.
Editing preserves source geometry if supported, otherwise proposes an approved
aspect-preserving adjustment without silent crop/stretch. Internal pixel decode,
approved preparation and saving are ordinary codec work; creative transformation
always belongs to Qwen-Image-2.1.

## Workers, verification and delivery

Mac-Orchestrator freezes interfaces, coordinates/reviews and integrates.
Worker1 repairs/qualifies image editing, implements the host broker and deploys.
Worker2 implements MCP/skill/engine packaging and web integration, then independent
acceptance. Fresh bounded remote Codex CLI sessions and isolated copies retain
IDs/status/results; source-only work overlaps GPU diagnosis. Root reviews exact
source before centrally coordinated shared service activation. Current accepted
bases are harnessfcfa12b and image8376682; integrate both without losing prior work.

Acceptance: original edit regression, independent/follow-up edits, generation and
editing through ordinary chat and native subagents; correct references/dimensions/
seeds/downloads/originals; approval/rejection/reconnect; text+image concurrency;
queue/Stop/idempotency/restart; independent VRAM evidence for enabled edit profiles.
Use focused fixtures and bounded live cases, not repeated text/large-GPU benchmarks.
Back up chats/files and retain rollback source. Publish plan, reviewed changes,
examples and honest acceptance report. Credentials, weights and bulky traces stay
outside Git. Finish with all three models warm; full editing is complete only
when both backend repair and harness workflow pass.
