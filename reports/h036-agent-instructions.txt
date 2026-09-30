# Sova — H036 current coordination

Read the [September 30 resumed recovery](reports/h036-resumed-recovery.md) and
[compact results](reports/h036-resumed-recovery-results.json) first. They
supersede current-availability statements in the [earlier hardware checkpoint](reports/h036-reboot-recovery.md)
and [September 29 completion checkpoint](reports/h036-completion-checkpoint.md).
Historical failures retain their original outcomes.

## Current state

The user removed the external Core X image GPU from ai-vm passthrough, restarted
ai-vm and authorized software recovery. All three Qwen instances and MiMo at 480K are ready after the reviewed adapter
deployment. Application, search and protected MiMo 480K/65,536 profile delivery
are recovered. Image hardware is intentionally absent: its unavailable state
must not block text services. No host, cable, GPU, BMC, fan or driver work is
authorized by this software recovery assignment.

The selected interrupted Codex chat is physically released for a distinct new
follow-up. Its original accepted request remains interrupted/unknown, not
successful. Preserve original messages, requests, runs, native history and
files. Two older uncertain owners and three older quarantines remain separate.
Never replay the interrupted prompt or clear unrelated ownership.

Public access was restored at 07:45 UTC after final qualification and ordinary
readback passed. MiniMax is the default; Codex remains a per-chat preview.
PR 10 records publication and the main-branch merge. The stale Qwen readiness record
was corrected at 05:28 UTC without restarting models. The recovered chat's new
follow-up, MiniMax MiMo delegation and normal Chrome ZIP/CRC/reload passed.
The subsequent Codex MiMo child spawned, but its parent failed on a slow
controller observation; the failed run and child fully settled.

The final adapter fix `052994a` passed 91 focused tests, 51 cold-transition tests
and all eight GitHub checks. It keeps the shared storage module unchanged.
Deployment aligned two historically different control-package files with the
reviewed node-package versions. Normal control/node readiness passed at 07:09 UTC.
MiMo started normally at 07:09:48 and current owner/native 480K readiness passed
at 07:23. All Qwen native identities are unchanged. The old MiMo
container and original failed attempts remain preserved. No paid worker waits
through model loading.

Worker2's final application updates the harness's controller-version pin to the
reviewed adapter hash. The actual final Codex MiMo workflow passed: one Python
call returned 437, tool-result continuation completed, child and parent returned
final answers, and all seven provider requests settled. Root reviewed the exact
protected qualification; the final restart/public-release readback passed.
Root independently reloaded the ordinary browser and confirmed the completed
answer, ready/connected state, zero active children and image unavailability.
Retained image/MiniMax evidence has explicit provenance review; no schema expansion.

## Working rules

Root coordinates, reviews and publishes. mac-worker1/mac-worker2 implement and
test in fresh bounded native Codex CLI sessions with isolated working copies.
Record native IDs, actual exits, compact results and private trace locations.
Do not keep paid sessions open waiting for hardware or another owner.

Reuse passed tests. Backend tests passed 323 cases with five existing skips;
the full server suite passed 973 with four existing skips; adjacent application
tests passed 115 with one existing skip. Exact source `75b384f` passed all eight
GitHub push/PR checks. Later source changes need appropriate validation; these
receipts do not automatically qualify a different candidate.

The final live Codex MiMo workflow, recovered-chat follow-up, MiniMax and ZIP
receipts all passed. Do not repeat them without a relevant change. Final
release readback also passed. Keep capability claims tied to actual evidence;
new work requires the user's next assignment.
Image generation/editing has retained historical qualification but current
availability is false. MiniMax native recognition is partial; Codex native
vision is unsupported. Do not claim OCR establishes native vision.

Do not repeat the large compaction paste, near-950K benchmark or full occupied
480K test. MiMo's new allocation and tiny tool continuation are not a long-context
performance qualification. Preserve old 950K receipts without relabeling them.
No GLM restoration, model download, runtime upgrade or new benchmark is part of
this closeout. Keep credentials, private prompts and bulky traces outside Git.

Root reviews capability descriptions, readiness and exact-candidate checks
before release; the actual default branch is `main`.
The [H036 execution plan](reports/h036-execution-plan.md) and historical
[H035 checkpoint](reports/h035-codex-checkpoint.md) retain their scope.
