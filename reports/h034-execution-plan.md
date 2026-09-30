# H034 — Qwen/Codex tool compatibility first

User renewed a two-hour execution window and explicitly made Qwen/Codex
compatibility the first priority. Start: 2026-09-29 17:09:44 UTC; deadline:
19:09:44 UTC (21:09:44 Ljubljana). Worker live cutoff18:58 UTC. No automatic
extension. Sova may remain in maintenance; do not restore an old baseline.

## Objective

Find and correct the demonstrated repeated invalid tool-call behavior without
pretending that Qwen is wholly incompatible: coding, research, follow-ups and
MiMo delegation already passed. The failing empty-object image_capabilities
calls and failed guarded edit are the primary unchanged regression fixtures.

## Parallel tasks

Worker1: provider/Qwen isolation using installed source and at most six short
initial inference probes (up to256 outputtokens, no imagejobs). Compare the
preserved real declaration/context with a minimal control; inspect schema,
namespace, template/parser and supported structured tool controls. Implement
only a demonstrated provider/translation correction with focused tests.

Worker2: native Codex/MCP tool declaration and feedback handling; explicit
instruction behavior for retained chats/children; bounded deterministic repeated
schema-error handling. Worker2 is the sole application deployment and acceptance
owner. The loop guard prevents wasted work but is not a successful tool repair.

Both workers use fresh bounded native Codex CLI sessions through SSH aliases,
isolated copies and real process-exit receipts. First session per worker is at
most40minutes, with an early concrete hypothesis/result within10minutes. Agree
source ownership and live request scheduling once. Root coordinates, reviews,
integrates and publishes. No root implementation/build/VM tests.

## Evidence and acceptance

Reuse H033: corrected fresh instructions reached Qwen; ten error results were
preserved with matching callIDs in the next provider request. No need to repeat
that proof. The older successful child generation is a partial pass, not proof of
reliable capability calls or guarded edits. Existing parents/children retain old
base instructions; preserve their histories and provenance.

A documented explicit schema/tool-contract change or supported provider control
is allowed when justified. Never silently strip invalid arguments, fake results,
replace the original prompt with an easier one, or relax creative-action ownership,
geometry, reference or seed guards. Do not replace Qwen or use hosted inference.

After source review and targeted checks, run a small bounded live acceptance set:
unchanged original request, independent ordinary task and guarded follow-up edit
with a child where useful. Stop at a few repeated deterministic schema errors;
report the failure rather than allowing another long loop. Preserve originals
and exercise explicit resize approval externally for test fixtures when needed.
At least one fresh and one retained-session path must have honest provenance.
No broad prompt or parameter sweep. Reuse unrelated passed release checks.

## Finish

No new long workflow after18:35; Stop/settle active acceptance by18:55; close
paid worker CLI sessions by18:58. Final root review/publication by19:09:44.
Maintain current model runtimes/weights/contexts/GPU/fan/ECC/power settings.
No950K or other capacity test, no GLM restore, accounts/scaling/installer or main
merge. Preserve chats/files, two historical uncertain owners, three quarantines
and original failure evidence. Publish reviewed source/settings/report to
feature/glm53-flash and existing draftPR10. Report actual pass/fail/missing evidence.
