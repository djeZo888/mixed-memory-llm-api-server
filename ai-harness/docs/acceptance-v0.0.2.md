# ai-harness 0.0.2 acceptance

**Bounded deployed acceptance is complete with explicit limits.** One owned main
request and queued follow-up settled; the four approved WEB corrections are
deployed and final readback passed. Native child browser execution remains
unproven. See the [release plan](../PLAN-v0.0.2.md),
[JSON receipt](acceptance-v0.0.2.json) and preserved
[0.0.1 acceptance](acceptance-v0.0.1.md).

## Scope and identities

- Generation/campaign base: `78bef292c33c5a689b8b7486ca6ba95c203ccd32`.
- Four WEB fixes: `42612a514387fcc812ac5b396cb603f70c8de2b4`; root-deployed
  source and final readback: `cacfdd43c42d675ab154ba7308404d71c81a64f1`.
- Unchanged production runtime:
  `sha256:4af6da23f70c3bc20d557be623d3d3bed7ef5d889e2b510debe556dc54936da3`.
- Origin: `http://10.156.100.61`; task `H002-UI-LIVE-20260922`;
  Worker2 native session `01a0c7cf-c3c2-7f01-8256-51618094ed21`.
- Owned chat `cbbe3d60-5dc9-4b27-b227-071a14e02295`; main run
  `65a3fe76-5d00-4041-8067-5be54b895c25`; queued run
  `8f3b2019-e4ea-46d2-8af2-2cbca90fc3ba`.
- Browser utility, distinct from the production engine:
  `sha256:84ea979312f7743d9ab789465aae7adde92f97d6169744ec7b63776a9482b227`
  (Node 24 / Chromium 153 / Playwright 1.63), with approved seccomp SHA256
  `0474c063b32acee85a1eb5ccfc35f7b1f66278af8da722c45b1d25eb2ae1cfbb`.

Generation used the explicit root GO for the campaign base. Corrected-site
readback and locale comparison used separate read-only grants, with no new
messages, uploads or inference. The approved rootless Chromium retained its true
sandbox, catatonit, keep-id, cap-drop ALL, no-new-privileges, read-only root and
bounded owned mounts/resources. Inspection was scoped to the owned chat and
unrelated sidebar labels were masked. Both runs settled; owned browser,
fixture and diagnostic processes/containers were cleaned up. Chat, artifacts
and original evidence remain. Worker2 made no shared-service or ai-vm changes.

## Requested UX checklist

`LIVE_PASS` means actual deployed observation; `FIXTURE_PASS` means source or
saved/synthetic fixture evidence; `NOT_TESTED` marks a remaining evidence limit.
Initial failed observations remain in their original receipts.

| Check | Result | Evidence and limit |
| --- | --- | --- |
| Context and keyboard | LIVE_PASS | Untouched 0 / 480,000; Enter newline; actual Ctrl+Enter send. Settled context estimate 26,317 / 480,000 (5.5%) is not full-capacity acceptance. |
| Actual attachment and filename | LIVE_PASS | Visible chooser FilePayload uploaded NFC `načrt.txt`; actual UI download returned that exact suggested name, 85 bytes and the expected SHA256 with valid RFC 5987 header under the combined UTF-8/sl-SI utility configuration. |
| Main, queue and reconnect | LIVE_PASS | Exactly one main and one follow-up; follow-up queued while active, refresh reconnected, both completed separately. Main final 70 words; follow-up confirmed nonce/filenames and created no files. |
| Progress and final separation | LIVE_PASS | Genuine emitted intermediate updates appeared, collapsed after classified final and remained on reopening. Proven for new native replies; old merged text remains original/unclassified without exact metadata. No hidden reasoning was invented. |
| Native count and tools | LIVE_PASS | One real child summary and actual main shell command creating exactly two nonce-labelled SVGs; canonical status, command/details/timestamps retained. Zero children alone was not completion. |
| Child public browser execution | NOT_TESTED | Requested `https://www.w3.org/WAI/standards-guidelines/wcag/`. Model reported native tool unavailable and headless Chromium fallback; neither execution path was independently proven. |
| Reply files, previews and ZIP | LIVE_PASS | Main owns two registered SVGs, follow-up none. Both render as 200×60 images. Real ZIP contains exactly two entries matching individual downloads; final readback preserves gallery/ZIP grouping. |
| Desktop and mobile | LIVE_PASS | Actual 1440×1080 desktop and 390×844 mobile views were reviewed; nonce labels rendered, layout readable, unrelated labels masked. Final corrected desktop capture retained outside Git. |
| Timezone and version | LIVE_PASS | Version 0.0.2; actual 06:57/06:59 UTC records displayed 08:57/08:59 Europe/Ljubljana. Worker1 independently verified host and Node Intl timezone. |
| Additional activity and history | LIVE_PASS | Final deployed readback shows 43 primary / 156 collapsed Additional activity rows. Only 71 legacy compatibility summaries were folded; stored records and real count updates remain. |
| Nonterminal timing | FIXTURE_PASS | Recorded completed → in_progress transition retained stale finishedAt and initially showed 0.0 s. Focused tests and saved active snapshot verify terminal-only duration/finish; settled deployed readback does not requalify an active transition. |
| Whitespace-only responding row | LIVE_PASS | Corrected deployed view has zero blank responding rows while preserving the stored whitespace tail, two progress messages and nonempty partial/unclassified text. |
| Drag/drop and other edge fixtures | FIXTURE_PASS | Drag/drop, error/draft retention, shared/no-message ownership, unknown/stale context, composition guards and locale conversion have fixture coverage; OS drag automation was not performed. Actual chooser upload is separately live-proven. |
| Broader qualification | NOT_TESTED | Platform IME, Cmd+Enter, PNG/JPEG variants, hostile SVG execution/security, full context/output, broad provider/lifecycle and later all-user history health were not established. Earlier 0.0.1 evidence remains linked above. |

## Download evidence and environment boundary

Attachment `554104fe-8f32-461d-a56c-6da16c6c6469` is 85 bytes, SHA256
`3d4b3c96ee6dd650ab9603a0226beb2939f1369cb9e50761f20f304b19b85cfc`.
Actual Chromium response header:
`attachment; filename="na_rt.txt"; filename*=UTF-8''na%C4%8Drt.txt`.
The accepted same-UI/path/route-guard comparison used task Chromium
`LANG=C.UTF-8` and `LC_ALL=C.UTF-8` together with Playwright context locale
`sl-SI`, yielding exact `načrt.txt`. Earlier unset locale/ASCII-charmap utility
observations suggested literal `download`; these remain a test-environment
finding, not an unresolved production bug. The variables changed together;
individual causality was not isolated. Original failed receipts are preserved.

The earlier filesystem-path upload produced no request; its cause, including
host normalization, remains unproven and separate from the locale finding.
The authorized FilePayload retry exercised the visible composer/server path.

ZIP entries `1-nacrt-a.svg` and `2-nacrt-b.svg` each contain 229 bytes and match
registered artifacts `9583f1fb-5104-4dd0-91df-49591ee22067` and
`08517008-20d4-4b8d-804b-138a02c50df2` respectively. SHA256 values:
`f9a067d182f6ecb3ab54ee328dd05e5610b44e986a065c57c5b4020f76cb81c4` and
`f0508152e14b3e4467c0686866694e30ce1a5f40085993217a916ae9e088c026`.
There are no extraneous archive entries or follow-up artifacts.

## Deployment and source verification

Independent Worker1 `ROOT-FINAL-deployment.json` proves final source `cacfdd43`,
unchanged runtime, idle/health/static success and HTTP restored at
`2026-09-22T07:28:51.598Z` after a **1.974 s** admission barrier. Paired message
and file fingerprints match for **68 messages**, **72 regular files**
(**825,197 bytes**); the verified private backup has **30 SQL file rows**.
The earlier `ROOT-deployment.json` is distinct: **61 original messages**,
**27 SQL file rows**, **66 regular files**, paired fingerprints matching.
Its initial Host-probe error caused about 80 s outage/rollback; corrected
activation succeeded with a 1.754 s barrier. These are bounded barrier proofs,
not a later all-user audit. Raw database backups remain private and outside Git.

The four WEB corrections fold compatibility summaries into Additional activity,
ignore stale nonterminal finish/duration, set `download={attachment.name}` and
filter whitespace-only assistant/progress rendering. No engine, server, policy
or stored-history change is included. Existing **62 focused reply tests**,
build/typecheck and one isolated network-none saved-snapshot Chromium check
passed at `42612a5`. These remain `FIXTURE_PASS`; actual corrected presentation
and Unicode filename readback at `cacfdd43` are separately `LIVE_PASS`.

Root-supplied current `cacfdd43` CI **35699502666** and D2 **35699502737** succeeded.
Unchanged deferred installer run **35699502718** failed the TMPDIR regex at
`tests/install/test_container.py:185`: **313 tests / 1 failure / 1 skip**.
No installer edits are included; this report does not claim all CI green.

## Durable evidence

Evidence root:
`/Users/agent/CodexProjects/llm-orchestration/tasks/H002-UI-LIVE-20260922/evidence`.
Compact receipts: `actual/receipts.jsonl`, `actual/file-verification.json`,
`visual-review.json`, `native-child-diagnosis.json`,
`final-web/results/receipt.json`, `FINAL-WEB-HANDOFF.json`,
`readback/readback-receipt.json`, `locale-diagnostic/diagnostic-receipt.json`,
`ROOT-FINAL-deployment.json` and `LATEST-ROOT-FACTS.md`.
The initial readback receipt retains its filename failure; the accepted locale
receipt supplies the final filename outcome. Final presentation screenshot:
`readback/corrected-owned-chat.png`; original desktop/mobile and fixture images
remain alongside their receipts. Event/run/message IDs and actual command
metadata remain durable outside Git. Generic denied events 223/329/393 do not
identify an operation/cause; no native or fallback browser proof is inferred.
Earlier synthetic evidence remains under `H002-UI-FIXTURES-20260922/evidence`.
