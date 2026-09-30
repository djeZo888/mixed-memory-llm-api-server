# H004 harness presentation and image-work improvements — 2026-09-24

This is the harness portion of the root task plan, adapted for Worker2's bounded
source/fixture session from `b2f6580cc5283479f28854b37e3200117610ddd0`.
Worker1 retains ai-vm/GPU ownership. Root reviews the exact source commit before a
fresh deployment/acceptance session. No deployment, service restart, ai-vm contact,
model request, push, installer change or history rewrite is part of this session.

## Problem and evidence

The newest relevant conversation was inspected read-only. Private content,
identities, raw traces and images remain outside Git in the task directory.
One completed run took 2481.651 seconds (41m22s); nine successful 1920x1080 image
jobs took 500.617 seconds total, including saving. Corresponding tool invocations
took 540.657 seconds, including polling. No image job failed. Later commentary
explicitly described regeneration after successful outputs. Research, local edits,
reads, text inference and deliberation account for the rest; these observations do
not establish a pure GPU benchmark or that every later illustration was redundant.
The open-ended request asked for research with images, with no explicit count.

The final saved answer contained ten Markdown image placements, all referencing
host workspace paths. Current Markdown rendered placeholders for every image.
Twenty artifacts belong to that run/final reply. Actual API serialization supplied
all twenty memberships and the canonical ZIP URL; read-only deployed DOM inspection
found the ZIP link, but it was over two screens above the viewport after automatic
scroll to the bottom. Thus this case demonstrates a presentation/discoverability
problem, not a proven missing ZIP field. Uploads were absent in this conversation;
upload ZIP coverage is a separate part of the user's explicit requested outcome.

## Accepted implementation plan

1. **Image work guidance.** Make the skill and tool descriptions require a small
   set of distinct purposeful illustrations; reuse successful artifacts. Embedding,
   links, layout and cosmetic self-verification are not reasons to regenerate.
   Explicitly requested variants, different illustrations, later user edits and
   retries for concrete failed requirements remain possible. Stop repeated local
   file edit/read self-verification once requested deliverables are acceptable;
   concrete unmet requirements and requested variants remain valid, without a cap.
   Preserve current request-id idempotency and uncertain-submission/no-replay
   behavior. Do not add
   output slots, frozen counts, prompt similarity filters or intent enforcement.
   Completed tool results provide canonical owned artifact Markdown for narrative
   placement. Never print base64, credentials or host paths in final answers.
2. **Inline final answers.** Resolve only the answer's owned artifact catalog to
   canonical same-origin raster preview/download routes. Known server-owned source
   provenance permits exact workspace references. Historical direct-child paths
   may be matched only under the exact registered workspace root, to one
   unique reply-owned name, with guarded byte-hash equality to the immutable
   snapshot; duplicate, modified or uncertain matches are not guessed. Never
   open a Markdown path. Preserve raw Markdown and original files in storage.
   Render valid image references where authored. If no narrative image resolves,
   provide a labeled fallback whose placement is explicitly unknown; avoid adding
   all omitted intermediate variants to an already illustrated answer. Raw HTML,
   external images, arbitrary paths and SVG inline injection stay blocked.
   Inline and fallback images do not repeat in the file gallery. Keep other image
   previews in a default-collapsed Additional image previews section, with every
   filename, Download and Use for next edit control outside the disclosure.
3. **Reply downloads.** Put Download all ZIP where a long reply can be found at
   both the final answer and file-list end. Server-selected run membership includes
   generated files and uploads explicitly attached to that run. User messages can
   download their own multi-file upload set. Reuse guarded file resolution, bounded
   streaming ZIPs and unique safe archive filenames. No client-submitted arbitrary
   file selection, cross-chat/reply inference or filename-based ownership. Keep the
   prior artifacts-only route compatible; do not mutate original attachments to
   assign them to later replies.
4. **Tables.** Give the first column usable minimum width, wrap long text and
   scroll each table horizontally on narrow screens. Keep the rest of the layout.
5. **Focused verification.** Backend fixtures inspect ZIP contents, duplicate
   archive names, correct run/message ownership, invalid IDs, traversal and symlink
   refusal. Tool fixtures cover returned Markdown and explicit multiple calls with
   existing idempotency/seed/size/approval protections. Browser fixtures use synthetic
   images only; assert narrative image positions separately from trays, historical
   rendering without message changes, desktop/narrow table dimensions, ZIP downloads
   and hostile Markdown refusal. Retain screenshots outside Git.
6. **Review handoff.** Deliver a clean feature commit, parent bundle relative to the
   exact base, sanitized diagnosis/report, focused result logs and screenshots.
   [Deployment procedure](deployment-h004.md) describes the later guarded switch
   and rollback. Root's exact-source review and fresh session are still required.

## Evidence boundaries and acceptance still outstanding

Guidance improves the agent contract but does not deterministically prevent a model
from choosing too many images or claiming a concrete failed requirement. No live
text/image behavior or latency improvement is established in this source session.
Natural-language intent is not enforced by the broker. Existing explicit seed,
geometry and external resize approval rules remain authoritative.

Historical placement can only be recovered when owned provenance is unambiguous;
missing/ambiguous references get a conservative fallback, not invented semantics.
Existing LAN/shared application access and gateway credentials are preserved;
this change does not add a per-person access model. Fixture acceptance is distinct
from native runtime/production deployment acceptance.

A later fresh acceptance session should verify the installed commit/engine, unchanged
history and artifact hashes, the existing ten image placements, table usability,
ZIP availability and exact contents, and only separately authorized bounded agent
behavior. No full image request is needed to verify the UI.
