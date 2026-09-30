# Technical image understanding

**Research and proposed qualification plan — 1 October 2026.**
Implementation follows the compaction priority. Creative image generation
acceptance is deferred; understanding drawings is a separate capability.

## Goal

Feed an image or rendered document to a locally served vision specialist and
return a detailed, source-linked textual description to Qwen/MiMo. Codex does
not need native pixel input for this tool workflow.

Prioritize electrical schematics, electronic components and pinouts,
microcontroller/PCB diagrams, scientific plots, mechanical and architectural
drawings, and technical PDF pages. General object descriptions are secondary.

## Candidate selection

First qualify the existing Qwen3.8-27B-FP8 model family. Its official artifact
contains a vision encoder; Sova's current text profile and unsupported native
Codex vision do not prove that the underlying model cannot interpret images.
Whether the installed artifact and pinned serving runtime support a useful
vision endpoint still requires inspection and live qualification.

Keep Qwen3.5-9B BF16 as the smaller dedicated-Ada comparison: it leaves more
memory for detailed crops and working buffers. Consider PaddleOCR-VL-1.6 as a
document parser alongside the reasoning model, not as a replacement for
electrical or spatial reasoning. Exact sources, artifact sizes and benchmark
limits are in the [research note](../docs/research/2026-10-01-memory-and-technical-vision-models.md).

Do not select a larger model solely from a generic vision leaderboard. Measure
the user's actual diagrams and the supported precision/runtime on Ada.
The external Core X Ada was absent from the current H038 deployment. Its
availability and cooling/link stability must be reverified before placement;
this plan does not assume an idle, accessible second GPU.

## Input and geometry pipeline

1. Preserve originals, file identity, page number, orientation and source units.
2. Inspect a whole-page overview for layout and relationships.
3. Process bounded overlapping crops at readable resolution for small labels,
   pin numbers, junction dots and dimension text.
4. Return page/crop coordinates with extracted content.
5. Reconcile duplicated objects and relationships across crop boundaries.
6. Retain uncertainty and request a better view or source data where necessary.

Use OCR/document parsing to recover text, tables and equations, then combine
that output with visual interpretation. Never silently turn a faint junction
into a proven connection. Small labels should not disappear through hidden
whole-page downscaling.

Raw DWG is not a raster-image input. Use a licensed CAD decoder/converter to
extract layers, blocks, units, dimension entities and geometry, then render
views for the vision model. DXF can use the reviewed ezdxf toolchain. Where a
source netlist or structured CAD data exists, it is stronger evidence than
pixel-inferred connectivity. DWG converter licensing is a separate decision,
not an assumed MIT dependency.

## Output contract

Return both a readable technical description and structured observations:

- Source/page/crop identifiers and coordinates.
- Exact visible labels, reference designators, component values and pin numbers.
- Symbols, components, relationships and explicitly observed connections.
- Dimensions and tolerances as printed, with units and uncertain readings.
- Plot axes, scales, series, legends and any extracted measurements.
- Ambiguities, missing detail and conflicting crop observations.

Every critical claim needs an evidence reference. A confidence score is not
proof; retain the supporting image region or vector entity. Derived conclusions
must be marked separately from visible source facts.

## Service and harness integration

Expose a specialist tool such as technical_image_analyze. It accepts validated
uploads, workspace artifacts or PDF pages and returns textual observations and
artifact references. Keep binary pixels out of ordinary text conversation
payloads where a reference is sufficient.

Advertise qualified formats, image/crop limits, model revision and actual
availability through the service registry. Keep credentials on the service
side. Apply bounded jobs, queueing, cancellation, duplicate protection and
ownership settlement; browser disconnection must not repeat inference.

The general agent selects relevant pages/crops and uses the description for
further research or engineering work. It should revisit the source where an
important assertion remains uncertain. A dedicated utility-model instance is
an option, not a requirement to activate vision on all 480K text sessions.

Start with short bounded vision requests, for example 16K–32K total tokens,
and measured image/crop budgets. These are proposed qualification profiles,
not a change to the existing text Qwen context. Keep approximately 7% Ada
VRAM reserve where this placement is selected; artifact size alone does not
establish runtime fit, maximum resolution or concurrency.

## Acceptance and decision

Build an annotated corpus with schematic crossings/junctions, rotated and
small labels, component values, dimensions, chart scales, tables and ambiguous
details. Include representative files from the user's engineering work.

Measure exact identifier/value/unit accuracy; component and connection
precision/recall; OCR/table errors; dimensional correctness; abstention on
illegible details; evidence-reference validity; crop reconciliation; duration
and peak VRAM. Grade critical facts against the answer key, not only an LLM judge.

Compare existing Qwen3.8, smaller Qwen3.5-9B and optional parser assistance on
the same fixtures. Verify operation through a normal Codex tool request and
follow-up. Keep electrical connectivity and CAD reasoning explicitly
unqualified if only descriptive/OCR cases pass.

Enable only the operations and input profiles that pass. No current generic
benchmark establishes reliable electrical-net reconstruction or CAD editing.
New model installation, GPU reassignment and a live acceptance window will
be scheduled as a separate implementation task.
