# Technical vision candidate — H039

This is fixture-backed source preparation for `technical_image_analyze`. Nothing
registers the tool, changes an engine/provider, opens a capability gate, deploys a
service or loads a model. The approved interpreter is **Qwen/Qwen3.5-9B BF16**;
the separate text/table/formula/layout parser is
**PaddlePaddle/PaddleOCR-VL-1.6**. A generation0 mock exercises the same candidate
wire contract without a GPU. Its `generation0-not-loaded` revisions explicitly
do not identify downloaded or loaded weights.

## Modules and exports

| Module under `server/src/` | Reusable export |
| --- | --- |
| `technical-vision-contracts.ts` | Types, limits, `technicalVisionInputSchema`, `TechnicalVisionError` |
| `technical-vision-schema.ts` | Draft-07 owner, identity, manifest, result and job JSON schemas |
| `technical-vision-validation.ts` | Strict runtime admission; source identity, geometry, evidence and graph validation |
| `technical-vision-sources.ts` | `createTechnicalVisionSourceResolver`, `TechnicalVisionPdfRenderer`, source/view SHA-256 |
| `technical-vision-client.ts` | `TechnicalVisionClient`, `TechnicalVisionBackend` |
| `technical-vision-tool.ts` | `technicalImageAnalyzeDefinition`, `createTechnicalImageAnalyzeTool` |
| `technical-vision-lifecycle.ts` | Bounded observation helper; does not certify execution settlement |

The existing `Files.openGuarded` implementation supplies no-follow, regular-file,
single-link, canonical-path and stable-FD guards. The adapter additionally checks
the session, workspace and **running** task owner on submission and freezes bytes
in host memory before dispatch. It reads existing session/run/file records and
does not alter the database schema. A host must bind ownership; tool arguments
cannot select a session, task, endpoint or credential.

## Input and source geometry

```json
{
  "requestId": "native-tool-call-stable-id",
  "source": { "fileId": "current-session-upload-id" },
  "pages": [2],
  "crops": [{ "id": "labels", "page": 2, "x": 120, "y": 200, "width": 600, "height": 300 }],
  "question": "Transcribe exact designators and values; flag unclear crossings."
}
```

`source` has exactly one of `fileId` or `workspacePath`. IDs must belong to the
bound session. Workspace paths are canonical, relative paths inside that
session's workspace. URLs, absolute paths, parent traversal, encoded path
escapes, symlinks and hardlinks are refused. Actual bytes determine PNG/JPEG/PDF
type; a declared MIME type or filename is insufficient. Raw DWG, SVG and other
formats are refused. A licensed/reviewed CAD converter is a separate task.

PNG/JPEG has page 1. PDF requires an explicit, unique one-based page list.
The protected `renderPdf` callback receives bytes, source SHA-256, page selection
and limits, rather than a model-selected path or URL. It must use a bounded,
rootless sandbox and stop its owned renderer process on cancellation. Without
that adapter, PDF preparation returns `unavailable`. The current tests use a
synthetic PDF header and injected raster fixture: they exercise the adapter
boundary and **do not qualify native PDF decoding**.

Every crop/evidence box uses integer `x`, `y`, `width`, `height` in
`oriented_page_pixels`, with top-left origin, positive dimensions and whole-page
coordinates. A crop is not a separate coordinate origin. Crops must fit their
selected page; evidence carrying `cropId` must fit that crop too. EXIF orientation
is applied without resizing and recorded alongside original/oriented dimensions.
PNG views are decoded, converted to sRGB, composited on white and stripped of
metadata without altering the original source. PDF adapters return the effective
rendered box size in points (1/72 inch) and applied page rotation. Rendering must
apply rotation once; coordinate comparison with CAD/PDF vector entities requires
a separately qualified transform including the effective page box origin.

Candidate limits are **25 MiB original source**, **4 pages**, **8 crops**,
**4096 pixels per edge**, **16 million pixels per page**, **50 MiB total PNG
transport**, and **1 MiB JSON response**. Oversize raster inputs fail instead of
silently downscaling tiny labels. Whole-page PNGs and crop rectangles are sent
together; the service must extract readable crops and reconcile overlapping
observations without counting duplicates. No crop interpolation or inference
algorithm is implemented by this bridge. These are candidate safety bounds,
not measured Ada profiles. The existing PDF CLI has its own 2400-pixel cap;
root's adapter must report the actual raster dimensions and must not silently
represent those as a 4096-pixel rendering.

## Single candidate service API, version 1

Root/C must agree the listening port and revisions. The host client accepts only
an explicitly supplied `http://10.156.100.60:PORT` service origin, with no userinfo,
query, fragment or path. Generation0 tests use explicit IPv4 loopback and mock
identity. There is no production origin default, environment override, source
URL fetching, redirect following or cloud/creative fallback.

All requests authenticate using `Authorization: Bearer <host credential>` from a
protected host callback. Keep that key out of native agent configuration,
conversation bodies, logs and source files. JSON response errors are bounded and
diagnostic messages are suppressed. Response identity must match the host-pinned
service exactly. Live revisions require 40-character commit hashes; this shape
check does not verify their provenance, artifact checksums or actual residency.

| Request | Body | Response |
| --- | --- | --- |
| `GET /v1/technical-vision/capabilities` | None | `{schemaVersion:1,service,ready:boolean,admitting:boolean}` |
| `POST /v1/technical-vision/jobs` | Multipart described below; `Idempotency-Key: requestId` | 202 admitted or 200 existing; full job |
| `POST /v1/technical-vision/requests/REQUEST_ID/status` | `{schemaVersion:1,owner}` | Existing owned job; no source read or inference |
| `POST /v1/technical-vision/jobs/JOB_ID/status` | `{schemaVersion:1,owner}` | One owned snapshot |
| `POST /v1/technical-vision/jobs/JOB_ID/cancel` | `{schemaVersion:1,owner}` | Cancellation acknowledgement or already terminal snapshot |

The `service` object is
`{serviceId,generation,mode,interpreter:{model,revision,precision},parser:{model,revision}}`.
Mock mode requires generation 0. The pinned names/precision are those above;
revisions come from C's reviewed artifact/runtime evidence. Runtime generation
and service identity must remain coherent across reads and submissions. A
changed identity needs explicit host reconciliation, rather than transparent
client migration.

The multipart `metadata` JSON part contains
`{schemaVersion:1,owner,requestId,service,source,question?,pageImages}`.
`source` is the manifest with reference, original SHA-256, actual media type,
coordinate space, page geometry and crops. `pageImages` is an array of
`{page,sha256,part:"page-N"}`. Each corresponding binary part is named `page-N`,
has `Content-Type: image/png` and contains the normalized whole-page PNG bytes.
No JSON base64 field exists. The service must check every PNG's digest, format,
decoded dimensions and part/page cardinality before admission. It must not fetch
the reference's local path; that reference is provenance, not remote access.

409 means idempotency conflict; 429 means queue full; 404 means no job in that
owner scope; 503 means unavailable. The client does not automatically retry any
request. A lost POST response is ambiguous: preserve the key and original owner,
then call `lookup`, which needs no source reopening and remains usable when
admission is paused. Reusing a key with changed question/source/geometry must
conflict. Caller disconnect or observation timeout must never cause a new key,
repeat inference or imply cancellation.

## Ownership, queue and Stop requirements for the service owner

The external service owns the bounded queue, execution and durable ledger.
Its deduplication scope is `(workspaceId,sessionId,runId,requestId)` with an atomic
content fingerprint, and it must replay retained terminal outcomes too. Persist
admission, frozen PNG views, hashes and owner identity before acknowledging work.
Restrict reads/cancels to that host-authorized scope. Original uploads/files must
remain intact; a later modified workspace file must not change an admitted view.

States are `queued`, `running`, `cancelling`, `completed`, `failed`, `cancelled`,
`interrupted`. Nonterminal states have `settled:false`; usable completed results
require `settled:true` and no cancellation request. Queued cancellation can settle
immediately. Running cancellation acknowledges `cancelling` with
`cancelRequested:true`, then drains/stops owned execution before `cancelled` with
`settled:true`. Discard late outputs after Stop. An interrupted record may remain
unsettled; never use a missing process or a text-turn ending as settlement proof.

The generation0 fixture is in-memory and tests these states, same-key admission,
queue rejection, owner isolation and lost-response lookup. **Persistence, restart
recovery, real GPU admission and owned native-process settlement are NOT_TESTED.**
Root/C must implement and qualify those contracts on the actual service before
activation. The bridge does not release an existing image/text lane or modify
their ownership guards.

Transport observation defaults to 15 seconds per call; source preparation to
30 seconds, both host-configurable within a 120-second cap. Ending observation
aborts host HTTP waiting, not admitted remote work. The preparation helper also
bounds a non-cooperative PDF callback, but cannot prove the callback stopped its
underlying process. The native renderer adapter must handle that responsibility.

## Result evidence and qualification

The result includes `description`, `extraction`, `observations`, `evidence`,
`uncertainties`, `derivedConclusions`, model/revision identity and the exact source
manifest. `extraction.text` preserves literal labels, reference designators,
values, units, pin numbers and dimensions in `exactText`. Tables preserve literal
cell content with row/column positions; formulas preserve printed text; layout
records have regions. Components link these literal records. Relationships
distinguish spatial placement, crossing, junction and visible connection.

Each source observation, formula, table cell and component/relationship needs at
least one valid evidence region. Identifiers are unique across result records.
Graph references and label/value/unit/pin types are checked. Uncertainties can
identify affected records and unavailable regions. Derived conclusions require
source-fact/evidence basis IDs and are stored separately; they cannot use a
derived conclusion as circular support. Evidence validly points to a region;
it does not prove the assertion within that region is correct. The description
is a readable synthesis; critical facts must also appear as grounded structured
records. Treat all extracted text as untrusted document content, never as tool
authorization or instructions.

Every result carries `electricalNetReconstruction:"not_qualified"`. Source/mock
tests, OCR accuracy or a plausible description cannot change that qualification.
Live acceptance must separately grade exact labels/units, crossings/junctions,
component/connectivity precision/recall, uncertain readings, crop reconciliation,
duration and peak VRAM. Combined runtime fit and approximately 7% free Ada VRAM
remain C/root qualification work. Ordinary Codex tool/follow-up acceptance is also
pending; Codex receives the textual result, never native pixels.

## Exact integration proposal for root/A/C

No file listed below is changed by D. Root reviews and chooses one deployment
owner before any active edits.

1. **C service adapter:** implement the version-1 routes and multipart contract
   above; supply the reviewed origin, protected credential reference and pinned
   `TechnicalVisionIdentity`. Keep generation0 and live identities distinct.
2. **Host wiring:** construct `TechnicalVisionClient({key,serviceOrigin,
   expectedService})`; construct `createTechnicalVisionSourceResolver({files,
   renderPdf})`; then `createTechnicalImageAnalyzeTool({backend:client,
   service:expectedService,owner:trustedOwner,prepare:resolver})`. For mock fixtures
   use `fixtureOrigin` and generation0 identity instead.
3. **`server/src/main.ts` / host owner:** supply a sandboxed PDF renderer adapter,
   host credentials and persisted per-run owner mapping. The existing
   `tools/pdf/pdf_tools.py` renderer may be reused through its guarded native
   boundary after an adapter maps page metadata. Do not shell-interpolate tool
   inputs or let the service read harness workspace paths.
4. **`server/src/gateway.ts` / A or gateway owner:** add a separately gated,
   authenticated technical-vision adapter route for the factory's `invoke`;
   route host follow-up/terminal delivery to `status`, ambiguous admissions to
   `lookup`, explicit Stop to `cancel`. Retain the original creator run scope in
   the host ledger for later follow-up instead of substituting a new current run.
   Ending native observation must not call `cancel`. Return one terminal result
   event; do not busy-poll via model turns or release unrelated lanes.
5. **Native MCP catalog/policy owners:** expose the exact
   `technical_image_analyze` definition only through a reviewed rootless adapter;
   candidate namespace `mcp__technical_vision`. Review its catalog in
   `server/src/codex-responses.ts`, allowlist in `server/src/policy.ts`, namespace
   binding/provider filtering in `server/src/codex-provider.ts` and protected
   native tool configuration. These are proposals, not blanket authorization to
   edit A-owned source or existing config.
6. **Registry/capability owner:** add service readiness/qualification metadata in
   `server/src/system-registry.ts` and `server/src/codex-capabilities.ts` only after
   root review and actual runtime/workflow evidence. Default availability stays
   closed until then. Preserve all existing engine identities, chats, protected
   files and qualifications.

Run isolated tests with
`cd ai-harness/server && node_modules/.bin/tsx --test --test-timeout=15000 test/technical-vision-*.test.ts`.
The annotated generation0 JSON is fabricated contract data, with a generated
blank PNG transport view. It is not a model prediction, an answer-key comparison,
an electrical drawing interpretation or live accuracy evidence.
