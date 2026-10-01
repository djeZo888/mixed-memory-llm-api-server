# H039 D — technical vision bridge preparation

**PASS — source preparation only.** Corrected implementation commit `1d2551f638bdd00c021a26be898bb758c89db87c` on
`h039/d-vision-bridge`. No service activation or live inference is qualified.

Native worker2 session `01a0f4d8-c550-78a3-86bf-184759a1c9d3` used the fresh local
Codex CLI 0.159.2 with configured `gpt-6.1-sol` / `ultra`; launch/thread receipts
remain in the private task directory. Started 2026-10-01T00:24:02.043830+00:00, hard deadline
2026-10-01T01:54:02.043830+00:00; root's 00:50 UTC adoption was read from INBOX. No extra
paid subagents or waits for C were used. The server's pinned 0.158.0 was unchanged.

## Delivered

Seven new `technical-vision-*` modules provide types/JSON schemas, bounded strict
validation, guarded upload/workspace/PDF source preparation, host-only service
credentials and a candidate external HTTP client/tool factory. The single
version-1 API works against a generation0 HTTP mock without any GPU. All active
engine/gateway/provider/registry/bootstrap files and root handoff/roster are
untouched. Existing files, conversations, credentials and failed evidence remain.

Exact labels/designators/values/units/pins, tables/formulas/layout, components and
relationships have source-linked evidence boxes; uncertainties and derived
conclusions are separate. Validation checks source hashes, pinned service
identity, page/crop bounds, record uniqueness and typed claim references.
No native Codex pixels, source URLs, raw DWG or creative-image fallback is used.

## Validation

| Check | Result |
| --- | --- |
| Vision generation0, sources, evidence and factory suite | PASS: 29 passed, 0 failed, 0 skipped (corrected candidate) |
| `npm run build` | PASS |
| `npm run typecheck` | PASS on prior candidate; corrected build also typechecks source |
| Full server `npm test` | Retained prior candidate PASS: 1012 passed, 0 failed, 4 skipped, 1016 total |
| Staged whitespace check | PASS |

Coverage includes invalid source/path/owner, actual format/EXIF geometry, explicit
PDF page metadata seam, crop/evidence bounds, duplicate admission and conflict,
queue full, lost-response lookup without source rereading, timeouts including a
non-cooperative renderer/auth callback, unavailable/redirect/malformed/oversize
responses, cancellation draining, ownership isolation and late-output suppression.

**Retained FAIL:** the initial typecheck found new literal-default/Buffer typing
errors. These were corrected; the initial failed output remains outside Git in
`../output/h039-typecheck-initial.log`. The prior candidate build/typecheck and both suites passed. The corrected
candidate passes 29 focused tests and build; the full suite was not rerun after
the enum fix, following root instruction. Four existing opt-in native tests are skipped; their exact names
and all final private receipt locations are in [the JSON report](h039-vision-bridge.json).


**Retained review FAIL, corrected:** root independently reproduced array-valued
runtime enums bypassing state/revision guards in initial commit `175a796c8b728b0362781d1379479f35b80e2db9`.
The helper now requires a string before membership checks. Regressions cover
mode, media type, text kind, relationship kind, job state and error code, plus a
real HTTP client response with array-valued failed state. Corrective source
commit `1d2551f638bdd00c021a26be898bb758c89db87c` passes 29 focused tests and build. The earlier full-suite
receipt is preserved without being presented as a run on the corrected commit.

## Limits and root handoff

**NOT_TESTED:** native PDF decoding/renderer process settlement; loaded model
revisions/provenance/accuracy; actual Ada combined runtime fit/reserve; durable
service restart and native GPU process cancellation; normal Codex tool/follow-up
integration; electrical-net reconstruction and CAD reasoning. The parser-seam
PDF header, blank PNG and annotated result are synthetic contract fixtures.
They are not predictions or electrical interpretation evidence.

The service must persist atomic `(workspaceId,sessionId,runId,requestId)` admission,
frozen views and owner outcomes. Transport loss is ambiguous; read-only request
lookup avoids rerunning inference or reopening changed files. Running Stop remains
`cancelling` and unsettled until service-owned execution drains. The in-memory
fixture verifies the contract only; it does not qualify durable runtime behavior.

Root/A/C's exact construction, routes, policy/catalog/registry proposals and PDF
adapter responsibilities are in [technical-vision.md](../ai-harness/docs/technical-vision.md#exact-integration-proposal-for-rootac).
None requires D to edit another owner's files. Root should review the commits,
agree C's protected service origin/identity and implement one owned integration
candidate before live accuracy/memory/native-tool qualification. Gates stay closed
until that review and evidence exist. No GitHub publication, merge, VM write,
upstream upgrade, Proxmox, driver or fan work was performed.
