# H035 IMAGE-HANDOFF01 source handoff

Production source: `dbcd579f8b5ee91ff86c4035bfe643d51e8cd3d1`.
Base: `20fdbe7b7c759cfe212d47c6ab5e7c86572348c1`.
Includes W2's reviewed instruction/PDF source commit
`0ccadadeea93997620e4ce0ab69df91684686c5a` with its original ancestry.

**Source and deterministic test implementation complete; no activation or live
workflow acceptance performed.** Root reviews/integrates/pushes; W2 alone owns
later deployment and live admission. No native exit is claimed by this report;
the task wrapper records its actual session/exit receipt separately.

## Correction

The retained H034 edit returned `awaiting_approval`; actual user approval was
18:46:52.757 UTC, while the parent still reported pending approval at
18:47:20.538 UTC. The original image finished at18:47:28.989 UTC,526 ms after the
parent ended. That historical answer stays unchanged. This source does not
resubmit or retroactively repair that completed job.

- `image_status({jobId})` performs exactly one authenticated GET of an existing
  session-owned image job. It does not submit, approve, cancel, wait or start a
  model turn. Unknown/foreign identities are refused; revoked bearer access
  remains refused. Owned reads remain available after creative qualification
  expires. Existing generation/edit gates are unchanged.
- Exact states remain `awaiting_approval`, `queued`, `running`, `saving`,
  `completed`, `failed`, `cancelled`, `interrupted`. Only completed results carry
  successful inline image Markdown. Retained outputs carry their actual state
  and authorized download links; cancellation while running/saving is draining,
  and `image_completion_unknown`/interruption does not claim success.
- A terminal job produces one new **Image service result** message using its
  original run/job/artifact identity. Its provenance is `origin=image_service`,
  `imageJobId`, phase unclassified. It is not a native final/turn receipt, cannot
  replace `run.finalMessageId`, and does not rewrite old model text or reassign
  the artifact's original message association.
- The app transaction writes the message, dedup key and replayable event together.
  A crash gap retries delivery only; repeated reads/replay/restart cannot create
  another image job or duplicate durable result. Successful deliveries leave
  the pending set, so recurring ticks do not rescan their artifacts.
- Each next explicit user turn receives a fresh compact snapshot of the newest
  20 owned jobs (including the total count), with IDs/states/artifact links and
  no image prompt bytes. Older jobs remain readable by their exact existing ID.
  Native completion is not external completion. Instructions prohibit a model
  busy-poll loop; app delivery needs no automatic inference continuation.

## Cutover and UI

New submissions persist `resultEligible=true`. Previously pending jobs become
eligible for their future terminal transition. Historical terminal records
without that flag are read-only and receive no backfilled messages, including
the retained H034 edit. Startup repairs only eligible terminal delivery gaps.
Deleted/deleting conversations do not receive new result messages.

The UI displays app provenance separately, uses the original authorized image
and download links, and does not infer a late image into old model text for a
new eligible job. Historical completed jobs without eligibility retain their
previous previews. Event replay/reload preserves the original final. Existing
artifact previews in the file section are suppressed when the result already
renders that image inline.

## Delivery pairing

Both Codex profiles expose read-only status; only the existing creative profile
exposes generation/edit. The Responses namespace and ordinary permission policy
accept this exact tool name. No model limits, routing or media qualification
changed.

The existing file-overlay validator pins the helper/MCP, ordinary image/PDF
skills and profile seeder. The ordinary launcher mounts the PDF skill as well.
The seeder accepts only exact H033/H034 image and H034 PDF predecessor bytes to
the supplied H035 successors. It validates the full roster and all applicable
private backups before replacements, retains arbitrary-edit refusal, and
preserves history/native identity. Interrupted multi-file replacement is safely
resumable; it is not a filesystem transaction against concurrent writers.
The missing-image roster path validates PDF before adding image.

Tool policy SHA-256:
`4ab2f4935c2a90691b9abdd713b74e389922baeab2262ddc6d41a3b1ddd88b87`.
Exact file pins and test outcomes are in [results.json](results.json).

## Focused verification

Counts below overlap and are not a unique combined total.

| Check | Result |
| --- | --- |
| Image broker/integration plus ordinary policy | PASS46 |
| Actual pinned MCP SDK/helper contract and process tests | PASS40 |
| Replies/Markdown UI, including legacy cutover and single result preview | PASS98 |
| Paired current instructions, PDF outcome reporting and namespace | PASS22 |
| Existing store/run/follow-up/namespace seams | PASS23 |
| Exact managed-skill migration and profile fixtures | PASS73;1 installed-CLI check skipped |
| Fake-runtime overlay protections | PASS16 |
| Fake-runtime ordinary launcher | PASS21 |
| Fake-runtime Codex launcher/status discovery | PASS19 |
| Server TypeScript/build and web TypeScript/build | PASS |
| Real deployment, real model/image job, browser approval/live reconnect | NOT_TESTED; outside this task |

Tests exercise approval return followed by success after parent completion,
one original backend job, atomic rollback and disconnected event delivery,
restart/replay dedup, immutable old text, fresh next-turn context, rejection,
failed/uncertain outcomes, Stop during saving, exact authorization/artifact
identity, and no legacy backfill. They use deterministic local fixtures, not
production image/model/API/VM/service requests.

The initial MCP run failed because this isolated worker lacked the SDK. Root's
20:03 inbox explicitly authorized an isolated install using the unchanged
lockfile; SDK1.30.0/zod4.6.5 then passed all actual MCP tests. Other dependencies
were reused. Initial changed-expectation and stale copied-fixture failures were
retained before correction; none is relabelled as a pass. Three adjacent web
image-jobs submission-argument expectations fail unchanged on base20fdbe7
(missing the newer requestId argument); the focused delivery tests pass.

## Activation caveats

Use the paired source and verified pins together. Root review is required before
activation; this report grants no deployment, live job, ticket or runtime change.
First inspect the existing H034 edit with read-only status and preserve its
historical failure. Any later live regression is a distinct acceptance run.
No main merge, push, model/native-image/GPU/fan/config-state changes or benchmarks
were performed here. Raw retained captures, prompts and credentials remain
outside Git; source bundles/receipts live in the task's external output directory.

The first commit attempt also refused because this isolated checkout had no
Git author configuration. The successful commit used the repository's existing
Worker1 identity for that command only; no global/local Git configuration was
changed. External diagnostic receipts preserve this failure as well.
