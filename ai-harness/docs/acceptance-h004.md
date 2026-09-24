# H004 deployment and bounded acceptance — 2026-09-24

Worker2 deployed the exact root-reviewed combined source on ai-harness and
completed the authorized historical-chat checks and one fresh normal-chat image
case. No application source was changed during activation. This acceptance
document is the only addition after reviewed source `c0a07cc`.

## Deployed identity and preservation

| Identity | Verified value |
| --- | --- |
| Source commit | `c0a07cc0260b6d697616cf9366ec4b598f4cd41f` |
| Deployed ai-harness tree | `dc2d1e18517197967e0d877dc9ab31eb8c7226b6` |
| Reviewed bundle SHA256 | `a66434ac13f759d09a0cb69f95f3608468497f3884074cdfcb2f8922b9d7dcd6` |
| Source archive SHA256 | `daef212b7494ae57680d044d62694f83ce2fe0c2ef7b6b3f4429b159dd64a445` |
| Engine image | `f957fd7149295c3cca031814bcd1c13add31dfd651ac219520998ffe31b81c29` |
| Engine digest | `sha256:c0009c9d44eba98098fa6df4f1f1365c614d1ab8b2d4b75d9d776b9025d7547c` |
| Image profile skill SHA256 | `56449a3fa8055915f085333c85a295a3e1c2676489efff3a2a5428c71aad3c01` |

Activation completed at 13:27:33 UTC. All 234 archived source files matched the
reviewed manifest. Native Linux server/web builds and network-disabled overlay
syntax checks passed with the existing Node and dependency pins. The overlay
changed only the two image adapter files and packaged image skill; hashes of all
other inspected native runtime, tools/dependencies and skills matched the retained
image. Existing revision/patch labels were preserved.

The app, image jobs, text lanes and active native profile were settled immediately
before the single clean stop. The checks are not an atomic drain mechanism.
Storage/ancestry gates passed before and after staging, backup and activation.
SQLite backup integrity and complete stopped-state persistent-tree copy/manifest
equality passed (20,397 entries). Credentials/config were unchanged. Eight exact-old
profile skills passed dry-run, upgraded, and left zero pending; custom content was
not overwritten. The fresh acceptance profile subsequently matched the new hash.

Readback verified app PID 16459 at the exact release, native acceptance engine PID
17135 on the image above, HTTP 200 health, zero app restarts, and unchanged listeners:
private nginx port 80 and IPv4 loopback app/gateway ports 8080/8081. No direct ai-vm
contact, model/driver/placement change, nginx change or installer work occurred.

## Actual acceptance

- **Existing authorized newest conversation:** ten loaded inline images matched
  their stored Markdown narrative blocks. Nine other previews were collapsed by
  default, expanded successfully and did not duplicate inline images. All 20 file
  downloads, 19 enabled edit controls and both prominent reply ZIP links remained
  outside the disclosure. Reload restored the same rendering and normal SSE
  connection. No browser runtime/network errors in the final pass.
- **Downloaded reply ZIP:** exactly 20 ordered, numbered catalog names; every size
  and decompressed SHA256 matched both the owned immutable downloads and the
  pre-activation file inventory. All CRC checks passed. No unrelated membership.
- **Tables:** real desktop 1440px and narrow 390px views wrapped correctly with no
  page overflow; first-column widths were 177.78px and 154px. This particular table
  fit both widths. Horizontal overflow/scroll remains covered by the retained
  source fixtures, not a new live overflow claim.
- **One fresh normal chat:** one message submission, exactly one native
  `image_generate` invocation and one admitted/completed job. The chat finished in
  45 seconds within its ten-minute observation window. Persisted native MCP result
  contained stable `imageMarkdown` and matching owned preview/download routes;
  the same 1024x576 artifact rendered between two short paragraphs at desktop and
  narrow widths. Seed 487263763 matched job/result/artifact metadata. No edits,
  variants, extra generation, research or resize-approval bypass occurred.
- **Final preservation/settlement:** the historical final text, original 20
  immutable files, ten referenced workspace files and exact original nine job
  records matched the private pre-activation inventory. App and native profile
  remained healthy/settled; zero active runs and unfinished image jobs.

Retained [source/fixture verification](verification-h004.md) is separate evidence,
not re-executed wholesale here. Private observer corrections handled Chrome's
20MB response-cache eviction, a table that fits the narrow viewport, and duplicate
content/details representations of one native tool result; no production source
patch was needed. Initial observer failures are retained with the passing receipts.

## Rollback and limits

The prior source release `9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27` and engine
`11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87` remain retained.
Protected rollback directory:
`/home/user/.local/share/ai-harness-deploy/H004-ACTIVATE-20260924/rollback-final`.
It contains the old unit/config, final consistent SQLite backup and full data copy.
The [reviewed procedure](deployment-h004.md) requires a fresh settled window, an
exact-hash skill rollback dry-run/update, restoration of the prior unit and engine
alias, then health readback. Preserve new history; do not automatically restore
SQLite or the whole data tree. Production rollback was **not executed**.

This single bounded case does not prove arbitrary long-research latency improvement
or general elimination of redundant image generation. Guidance is not deterministic
enforcement; seed, geometry, guarded editing and resize-approval limits are unchanged.
Existing access-policy limits remain. Private user text, screenshots, traces,
credentials and artifact bytes are outside Git in the protected deployment task.

The combined [GPU report](../../reports/h004-gpu-20260924/RESULT.md) retains its
measured limits and fourth-card initialization/telemetry blocker. Fourth-card
bandwidth and new-card image capacity remain **BLOCKED / NOT_TESTED**. This harness
acceptance adds no GPU qualification or recovery claim. No main merge or force push.
