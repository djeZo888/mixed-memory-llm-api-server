# Sova — H036 current coordination

Read the [September 30 resumed recovery](reports/h036-resumed-recovery.md) and
[compact results](reports/h036-resumed-recovery-results.json) first. They
supersede current-availability statements in the [earlier hardware checkpoint](reports/h036-reboot-recovery.md)
and [September 29 completion checkpoint](reports/h036-completion-checkpoint.md).
Historical failures retain their original outcomes.

## Current state

The user removed the external Core X image GPU from ai-vm passthrough, restarted
ai-vm and authorized software recovery. MiMo 480K and all three Qwen instances
are ready. Application, search and protected MiMo 480K/65,536 profile delivery
are recovered. Image hardware is intentionally absent: its unavailable state
must not block text services. No host, cable, GPU, BMC, fan or driver work is
authorized by this software recovery assignment.

The selected interrupted Codex chat is physically released for a distinct new
follow-up. Its original accepted request remains interrupted/unknown, not
successful. Preserve original messages, requests, runs, native history and
files. Two older uncertain owners and three older quarantines remain separate.
Never replay the interrupted prompt or clear unrelated ownership.

Public maintenance and main merge remain held for final acceptance. MiniMax is
the default; Codex remains a per-chat preview. Worker1's backend task closed
successfully at 04:33:08 UTC. Worker2's application activation closed at
04:48:36 UTC and a fresh bounded task owns the remaining workflow acceptance.
The first new Codex requests rejected before generation due to control readiness
disagreeing with healthy node/native observations. A fresh Worker1 task owns that
backend diagnosis; Worker2 retains inference and application ownership. Normal
Chrome ZIP completion/CRC/reload passed. Do not duplicate either live owner.

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

Remaining live checks are a distinct recovered-chat follow-up, browser ZIP and
reload, and short MiMo delegation through both engines. Use the existing scoped
acceptance mechanism. Keep global capability claims tied to actual evidence.
Image generation/editing has retained historical qualification but current
availability is false. MiniMax native recognition is partial; Codex native
vision is unsupported. Do not claim OCR establishes native vision.

Do not repeat the large compaction paste, near-950K benchmark or full occupied
480K test. MiMo's new allocation and tiny tool continuation are not a long-context
performance qualification. Preserve old 950K receipts without relabeling them.
No GLM restoration, model download, runtime upgrade or new benchmark is part of
this closeout. Keep credentials, private prompts and bulky traces outside Git.

Root reviews final capability descriptions, readiness and exact-candidate checks
before lifting maintenance or merging into the actual default branch, `main`.
The [H036 execution plan](reports/h036-execution-plan.md) and historical
[H035 checkpoint](reports/h035-codex-checkpoint.md) retain their scope.
