# H004 source/fixture verification — 2026-09-24

Source preparation only, from `b2f6580cc5283479f28854b37e3200117610ddd0` on
Worker2. Exact delivered commit and bundle checksum are in the parent `REPORT.md`.
[Plan](improvements-20260924.md) and [deployment/rollback](deployment-h004.md).

## Implemented behavior

- Image skill/tool guidance plans distinct purposeful images, reuses successful
  outputs and forbids cosmetic/embedding regeneration. Completed results expose
  fixed artifact preview/download routes and narrative Markdown. Broker admission,
  idempotency, seed/size/resize rules and native runtime pins are unchanged.
- Final Markdown resolves only owned artifact references to same-origin raster
  images at authored positions. Remote images, raw HTML, SVG and ambiguous aliases
  are blocked. Exact new source provenance is stored atomically in an additive
  companion table; historical paths require same-reply ownership, exact workspace
  root, unique direct-child name and guarded immutable-byte equality. No stored
  chat/event/file rewrite. Read-time recovery is capped at100 candidates/256MiB
  combined hashing per response; other cases retain labeled placement fallback.
- Download all ZIP appears at final-answer start and file-list end. A run ZIP
  combines its generated files with its explicit uploads; user-message ZIPs include
  only that message's uploads. Original artifacts-only routes stay compatible.
  Reused uploads retain many-to-many request membership. Prior generated images
  selected as edit references keep their original reply ownership.
- Tables wrap text, retain an11rem minimum first column and scroll within the
  reply on narrow screens.
- Inline/fallback previews register only artifact IDs selected by the existing
  safe renderer; the bottom gallery excludes these IDs without interpreting
  Markdown a second time. Other previews live in default-collapsed Additional
  image previews. Every file/download/edit control and both ZIP links remain
  outside the disclosure; files, ownership and stored history are unchanged.

## Verification

The table below records the parent source phase, before the narrow review
follow-up. Its durable evidence remains in `H004-HARNESS-20260924/evidence`.
All runs use local fixtures, Node24.21.0 and pinned dependency locks.

| Check | Result |
| --- | --- |
| Server typecheck and build | PASS |
| ZIP/source/history tests plus H002, store, atomic-save and image integration |30/30 PASS |
| App, image broker, image integration, policy regression selection |75/75 PASS |
| Image MCP adapter tests |32/32 PASS |
| Web typecheck/build and H004/UI/reply/grouping tests |80/80 PASS |
| Chrome fixture browser: H004 desktop/narrow + existing reply lifecycle |3/3 PASS |
| Extracted profile-skill procedure, synthetic dry-run/update/rollback/refusal |PASS |
| Whitespace and staged source/privacy checks |PASS at final handoff |

Parent browser fixtures verified two authored narrative image positions among19 tray
images, ordinary download links,22-entry combined ZIP contents,2-entry upload
ZIP contents, cross-chat/query refusal and zero external image requests. The
backend independently checks real ZIP CRC/contents, duplicate names, invalid
memberships, path/symlink/origin refusal, immutable bytes, deleted-chat access,
source savepoint rollback and late output publication. Desktop first-column
width measured184.64px; narrow first column154px with horizontal table scroll
and no body overflow. Screenshots are parent task `evidence/h004-*.png`, not Git.

Integrated tests caught a late-output regression: alias resolution initially
rejected soft-deleted session metadata during legitimate cancellation drain.
Internal metadata lookup now supports that drain while public deleted-chat
snapshot/download routes still return404; the unchanged lifecycle test passes.
Browser fixture development also corrected a root-font-size width assertion
an existing stale application-version expectation, and renderer remounts that
reset table scroll during state updates. Stable component identities now preserve
scroll and image-error state. Initial failures remain
in parent evidence; they are not presented as production failures.

## Narrow source-review follow-up

Evidence is outside Git in `H004-HARNESS-REVIEW-20260924/evidence`. Only affected
checks are rerun: web typecheck/build, H004 and reply rendering unit tests,
H004 browser fixtures and exact-hash profile-skill update/rollback fixtures.
Prior backend and adapter passes remain parent evidence, not new executions.

- Web build/typecheck and focused unit selection: PASS, 73/73 tests. Covers 19 PNGs
  with 10 narrative placements and 9 additional previews, always-accessible file
  and edit controls/ZIPs, exact reference-style and legacy resolution, ambiguous
  and unrelated reference refusal, fallback deduplication, StrictMode, repeated
  placements, failed inline images, catalog refresh and streamed message/artifact
  changes. Existing safe SVG gallery behavior remains available when expanded.
- H004 browser fixtures: PASS, 3/3 cases. The fixture matches the 19/10/9 split
  and checks default collapse, expansion, reload and stream updates, edit controls, responsive
  tables and owned ZIP downloads. Seven reviewed screenshots and a sanitized
  browser summary are in follow-up evidence; synthetic files only, no model calls.
- The packaged guidance also stops repeated local edit/read self-verification
  once deliverables are acceptable, while preserving concrete unmet requirements
  and explicitly requested variants without a count cap. Candidate skill SHA256
  is `56449a3fa8055915f085333c85a295a3e1c2676489efff3a2a5428c71aad3c01`.
  Extracted deployment helper dry-run/update/idempotence/rollback/refusal and
  unchanged profile-seeder compatibility fixtures PASS. Production rollback hash
  and custom-content/history preservation remain in the deployment handoff.

## Read-only production findings and limits

The newest run took41m22s with nine successful image calls; job execution/saving
accounted for8m21s and tool polling added40s. Its final answer already had ten
Markdown image references. All ten exact workspace paths matched their owned
immutable artifact bytes. The deployed DOM had ten placeholders and zero final
images. ZIP serialization/membership was correct and one ZIP link existed, but
it lay2239px above the default bottom viewport. Candidate UI fixes discoverability;
this is not evidence of a previously missing backend ZIP field.

Existing private activity timestamps additionally separate 25 browser invocations
(14.161s) and 7 search invocations (5.623s); their disjoint union is 19.784s. All
non-image tool intervals occupy 36.474s. The 1904.520s outside recorded tool
intervals cannot be attributed to text-model time: no text gateway start/end or
latency metrics are present. These are tool invocation durations, not isolated
network waits; no new profiling or host inspection was performed.

Live behavioral improvement/latency, production candidate rendering, deployment,
engine-overlay build, live profile update and rollback are **NOT_TESTED**. Guidance
cannot guarantee model compliance or semantically detect every redundant output.
No text/image model request, ai-vm contact, production mutation, push or installer
work occurred. Existing per-person access limitations are unchanged. Before later
activation, update exact old/new image skill bytes in existing profiles using the
reviewed procedure; an engine-only switch would fail existing profile validation.
