# v0.0.3 guarded editing acceptance

The bounded browser workflow passes on source `9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27`
with repaired engine `11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87`,
digest `sha256:d60f138286d755fb9857f08f0f981c88084e8a82f763abe354f8c421f2102d64`.
Exactly **three edits completed**, with no generation, retry or fallback. One
additional resize request was rejected before dispatch. Root visual review: **A/B/C PASS**. The window was returned settled at 14:36:23 UTC, 23 September 2026.
The [earlier failed-worker report](acceptance-v0.0.3-historical-worker-failure.md)
and its [original summary](acceptance-v0.0.3-historical-worker-failure.json) remain available as historical evidence.

| Check | Result / evidence |
|---|---|
| Deployment and published profiles | PASS: root-reviewed live-ready/activation receipts; public capabilities match all nine exact profiles and model/runtime pins. |
| Main native edit | PASS: one actual `mcp__image__image_edit`, with seed omitted; exact uploaded source hash, new artifact and 1024×1024 output. |
| Use for next edit / ordinary worker | PASS: real button stages A; fresh ordinary child `mvs_f26a0ecc5e6b44c8a28b3e0610fbd8c8` invokes native `image_edit` once, seed omitted, zero shell/fallback calls. B's reference hash equals A's downloaded hash. |
| Preview, download and provenance | PASS: three distinct artifacts, browser previews/clicked downloads, opaque PNG decode/CRC/dimensions/hash checks. Retained originals remain byte-identical. Running/completed job revisions are retained; B's card screenshot captures completion. |
| External resize rejection | PASS: real 1920×1080 → 1536×864 card, external Reject change returns 200; cancelled job never queues/starts and has no artifact. |
| Refresh then external approval | PASS: new explicit request, unchanged job/request/source/proposal across refresh, external Approve resize returns 200; same saved job completes with no new message/run/model submission. One edit call in that run. |
| Visual result | A/B/C root PASS. Creative preservation, not pixel-exact fidelity. |
| Additional coverage | No new generation, two-reference workflow, queue/Stop, security-isolation, collision/idempotency or benchmark campaign. Existing focused fixtures and prior live checks remain separate. No natural multi-artifact reply, so ZIP not tested here. |

## Accepted profiles and measured qualification

Generation (zero references): **1024×1024, 1024×576, 1216×704, 1472×832,
1760×992, 1920×1080**. Public ceiling: 1920×1080 / 2,073,600 pixels; Full HD
uses native 1920×1088 and removes eight bottom rows. This campaign did not repeat generation.
Editing: **one reference at 1024×1024 or 1536×864; two references at 1024×1024**.
Opaque PNG output only; no masks/transparency or larger editing geometry.

The following are Worker1's retained [capacity measurements](../../reports/h003-edit-capacity-20260923/RESULT.md)
(publication `1d8095d`), not the later browser acceptance timings. Duration is
HTTP monotonic elapsed for the native operation. Memory is sampled total Ada
**device** usage, not an allocator peak; 1 GiB = 1024 MiB.

| Qualification case | References / size | Seconds | Peak device MiB | Minimum free | Decision |
|---|---|---:|---:|---|---|
| C01 | 1 / 1024×1024 | 27.151 | 39,982 | 9,158 MiB / 18.637% | Qualified |
| C02 | 1 / 1536×864 | 36.476 | 41,206 | 7,934 MiB / 16.146% | Qualified |
| C03 | 1 / 1920×1080 | 65.496 | 46,984 | 2,156 MiB / 4.387% | **Excluded:** below 5% reserve despite visual pass |
| C04 | 2 / 1024×1024 | 31.217 | 42,744 | 6,396 MiB / 13.016% | Qualified |

All four qualification windows had zero new swap deltas; sampled extrema cannot
exclude unseen instantaneous peaks. Existing text q1 cgroup swap was **155,086,848
bytes (148 MiB)**, with memory.events max441 near its 32 GiB cap; its cause remains
unproven. Historical cumulative swapdelta305/5323 retains its attribution caveat.
Memory/swap during this later browser acceptance interval was **NOT_MEASURED**;
old post-generation samples cannot establish peak reserve or no-swap success.

## This browser campaign

| Case | Result | Effective seed | Dimensions | Broker execution interval, UTC | Seconds |
|---|---|---:|---|---|---:|
| A main | Turquoise teapot → cobalt blue | 4322739 | 1024×1024 | 14:29:24.299–14:29:52.082 | 27.783 |
| B fresh worker | A blue teapot → emerald green | 2250473401 | 1024×1024 | 14:30:59.679–14:31:28.320 | 28.641 |
| C approved | Island church orange roof → muted blue | 739097034 | 1536×864 | 14:34:27.952–14:35:05.374 | 37.422 |

C preserved the original 1920×1080 bytes and proposed a 1536×864 working image
with **zero padding**. The text turn finished before user approval; the image
completed later under that same run. The rejected job consumed no image admission.
C job `ec258379-7447-4065-bff3-5847ddc1bf19`, request
`3797be41-9361-4dcb-b7c3-eb0259d8f55e`, run
`396ba990-03a9-42cd-8bf8-aeb0e885720a`, artifact
`f10d2c0d-def3-4201-bed6-e9f37e7d6f73` belong to owned chat
`d866d605-287f-4984-bac5-5a9d489b1df0`. Both owned chats were idle and the public
backend ready/admitting/idle at return; the task browser was closed.

All effective seeds differ from the known input/ancestor seeds. Native argument
proof of omitted seed covers A/B; C records the requested omission and saved seed.

## Material limits and provenance

Fresh random seeds and the known source/ancestor-seed guard are an approved
workaround. **The exact original seed42 severe failure remains FAIL**; seed43's
successful counterpart does not prove intrinsic model repair. New-chat uploads
preserve bytes but do not import old generation ancestry; unknown imported
provenance cannot guarantee collision detection. Existing same-session
source/ancestor rejection fixtures were not rerun or presented as new live proof.
The earlier frozen worker's HTTP fallback remains a historical failure.

Clean-host `npm ci`: **NOT_EXECUTED** in this cached engine build. Native startup,
role/provider fixtures and old security/queue fixtures remain distinct from live
execution. Explore/verifier/custom restrictions were unchanged. No new service,
model, deployment, credential access, ai-vm contact or production patch occurred.
A separately authorized read-only harness trace accessed only the owned A/B
profile and exact parent/child; it proves one main and one worker edit, no fallback.

Exact IDs, hashes, pins, evidence digests and limits are in the [compact result](acceptance-v0.0.3.json).
Full sanitized screenshots, original/output PNGs, job events, native trace,
one-shot markers and session/exit records remain under task
`H003-EDIT-ACCEPT-20260923`, outside Git. [Chat examples](chat-examples-v0.0.3.md)
describe the accepted workflow without authorizing another acceptance campaign.
