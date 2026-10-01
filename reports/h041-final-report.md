# H041 final report — 1 October 2026

**Context compaction and final Codex production integration are incomplete.** Work ran from 08:05:07 UTC to the final worker closure at 16:58:53 UTC: **8 hours 54 minutes**, plus report/publication time. The user requested wrap-up; both workers closed voluntarily, with actual native CLI and outer-wrapper exits 0/0 and no remaining same-session process at 17:00:17 UTC. This is a stopping point with preserved source and evidence, not a completed acceptance run.

## Accomplished

Worker1 implemented durable session memory/checkpoints, scoped retrieval, human correction CAS, shared Store/Broker recovery ownership and shutdown joining. The ordinary Memory panel now uses protected memory/proposal/accept/source/acknowledgement/recovery APIs and preserves unsaved corrections. These are source changes; the full ordinary workflow has not been accepted on production.

Runtime source now keeps the bounded launch-receipt waiter alive, exposes factual private startup diagnostics and distinguishes raw failure evidence from verified native receipt getters. Compaction qualification source registers genuine sessions and performs pre-enqueue/queued-start/native-dispatch admission under the same canonical stop lease. The guardian registers actual peer identity before execution; cold re-adoption requires the original parent role, an independently exited old worker and a genuinely new owned peer. Restoration verifies original source, configuration, credentials, database identity/open FD, listener owners and health response rather than accepting a service name or exit code alone.

Worker2 connected admission, carrier, acceptance and retained-artifact consumers, asynchronous observations, owned cancellation and native-clock evidence. AUTO evidence preparation retains original token-usage and native compaction events and joins the latest actual pre-call numeric gate to a genuine event. The pinned upstream already emits startedAtMs; no invented clock was introduced. Important consumer gaps remain, and AUTO activation is disabled.

The reviewed CHA_FAN3 source correction changes expected duty only after a verified command/readback, removing a possible false overwrite detection after a transient BMC failure. Seventy-two source cases passed. It is committed but **not installed**. Worker2 also exported a partial, disabled recovery helper and fourteen corrected synthetic checks; it has no live approval.

Reviewed application source is preserved on the existing draft PR branch. Final report-only worker commits, important unintegrated patches and the partial helper are retained separately as [disabled WIP](../docs/h041-wip/README.md). Existing protected credentials, original failure receipts and raw private evidence remain outside Git.

## Evidence and limits

| Evidence | Result | What it establishes |
|---|---|---|
| E sealed 5d836b7 original source graph | 1,410 total; 1,406 pass; four skips; zero fail; EXIT0; post-seal focused 20/20 | That worker graph's source checks. It predates the final A import. |
| A final ca42389 separate source graph | 1,411 total; 1,406 pass; one fail; four skips; EXIT1 | Preserved genuine fixture/schema integration failure; no clean combined result. |
| E final fan helper | Corrected 14/14; syntax and adapter strict EXIT0 | Local synthetic helper/compile evidence; first failed check retained. |
| Final root A8a + E5d graph | No final coherent full/build/browser qualification | Earlier passing graphs cannot qualify this combination. Hosted CI covers only its configured checks. |
| Startup/manual/full/ordinary/cold resume/AUTO/production | NOT_TESTED as accepted native behavior | No H041 production activation or semantic retention PASS. |

The actual startup08c command exited 13; original Node stderr identified an unsettled top-level await at the launch-receipt wait. The source waiter was corrected. The later startup09d wrapper exited 1 at 16:44:02 before observing/installing the approval key/forking/claiming/launching Node: the installed Node ancestor /home/user/.local was group-writable (0775), so the strict protection check rejected it. No ACK or native compaction proof was produced. Earlier dependency/ancestry/layout failures remain preserved. Every old GO is expired, spent or withdrawn; none can be reused.

## Why it took so long and the hardest problem

The hardest problem was proving the complete real lifecycle across a stop lease, child-local Broker admission, original Store/native history, process exit, cold restart and exact restoration. A wrapper exit or a passing fixture cannot establish that the right native process ran, every retained artifact survived, an unrelated writer stayed untouched, or AUTO was caused by the genuine 400,000-token threshold. Early failures exposed cleanup and evidence-persistence gaps; process-local admission freshness also required explicit in-child registration and re-adoption.

Repeated adapter/producer/consumer corrections, stricter source/dependency closure, integration failures and protected Linux startup preparation consumed most of the window. Fan investigation added a separate live-state and BMC transport thread. Capacity failures and deadline terminations also interrupted exports. These are recorded rather than relabelled successful.

**The orchestration mistake was allowing many source-only phases and repeated continuation of the same two worker sessions before securing a small real startup proof.** The task should have stopped or been re-scoped at the overall time boundary. The next session should use a fresh worker chat for each bounded task, a small first acceptance gate and a reserved wrap-up period. A percentage or reliable completion-time estimate is not supported.

## Fan status

At the latest successful readback (16:40 UTC), the controller on ai-harness remained failed, MainPID0/exit78, with the original overwrite blocker preserved. BMC configuration remained at 100%; the one thermal GET returned tach 3360 without units. Earlier matching GPU telemetry was 34 C. A stopped controller cannot itself be issuing repeated commands during that interval, but the physical cause of the reported cycling is unresolved. The source correction has not cured or changed the live system.

The 16:30 whole-state preflight failed during the thermal transport step. A corrected one-GET diagnostic succeeded later; it does not replace a complete fresh recovery gate. No latch clearing, installation, start, new fan command or thermal stress occurred in wrap-up. CHA_FAN3 retains at least 80% at 70 C, 100% strictly above 80 C, and 100% until fresh <=65 C continuously for 30 seconds; available integrated NVIDIA fans retain 100% at >=70 C.

## What remains

1. Prove one minimal no-generation startup and owned close using a separately reviewed protected byte-identical Node copy, finite executor and preserved actual terminal receipt.
2. Finish source-supported Store startup recovery verification, direct manual AbortSignal/cleanup wiring, actual same-parent cold re-adoption and V2 AUTO empty-marker/parent-ancestry/producer composition. Qualify the coherent final source graph.
3. Run the bounded manual stage, then repeated full retention with scoped retrieval, real cold resumes and same-parent child; ordinary UI/manual/restart/human correction/Unicode/SSE/failure recovery; finally one genuine 400k AUTO case after prerequisite gates.
4. Activate and accept the ordinary production integration under exact owner/preservation/restore review. Remaining technical vision service/fit/workflow work is retained from H040 and stays secondary to compaction.
5. Independently finish/review fan recovery, obtain a fresh complete state/BMC/GPU/failed-owner proof, and permit one start plus 90-second observation only under a new exact root packet.

## Worker tracking and continuation

Yes: the [worker outcome ledger](h041-worker-outcomes.md) accounts for all **22 initiated H041 phases**, their original sessions, starts/ends, integer native/outer exits, source check provenance, failures and reasons. Eleven ended at deadlines, nine closed cleanly at the CLI layer, and two ended with capacity failures. All are closed; none is marked native PASS merely because its CLI exited 0. Earlier adopted phases and download history are separately identified. Native logs, bundles, manifests and failures are retained privately; credentials are not included in the public ledger.

Read the compact [final handoff](h041-final-handoff.md) in a fresh chat. It contains the current blockers and only the private pointers needed for the next gate. The [SSH orchestration procedure](../docs/h041-worker-orchestration.md) specifies fresh sessions, deadlines, completion checks and follow-ups. PR11 remains draft and unmerged; GitHub readback and current hosted checks are verified during publication. No shutdown of ai-vm or new model/download/placement work was performed during wrap-up.
