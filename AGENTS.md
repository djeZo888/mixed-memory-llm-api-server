# Sova — H036 current coordination

Current override: read the [September 30 reboot recovery checkpoint](reports/h036-reboot-recovery.md)
first. ai-vm's requested cable-trial shutdown was accepted at 02:05:46 UTC;
SSH became unreachable. Wait for the user to confirm hardware work is complete
before VM probes, deployment or model work. ai-harness was left in maintenance.
Recovery source is reviewed/tested but not deployed. Older state below is
historical and must not override fresh evidence or the cable-trial hold.

Read the [H036 execution plan](reports/h036-execution-plan.md),
[current completion checkpoint](reports/h036-completion-checkpoint.md) and
[results](reports/h036-completion-results.json) first. H036 remains authorized
for the specified image repair, MiMo 480K transition, normal workflow and
compaction acceptance, with default-branch merge conditional on final gates and
required CI. H036 has no new hard user deadline; individual native assignments
remain bounded. Historical [H035](reports/h035-codex-checkpoint.md),
[results](reports/h035-codex-results.json) and
[next plan](reports/h035-next-execution.md) retain their original scope.

Root coordinates, reviews and publishes. mac-worker1/mac-worker2 implement and
test through fresh bounded native CLI sessions in isolated copies. One assigned
owner controls deployment/live admission. Preserve session IDs and actual
outer-wrapper exits. Coordinate recovery centrally; do not duplicate another
owner's live work or wait in a paid native session for missing external evidence.

## Current evidence and remaining gates

- MiniMax remains default; Codex is a per-chat preview. Ordinary release and main
  merge are held for reachability and settlement. Root/W2 report both VM endpoints
  unreachable; W2 reports BMC healthy. One authorized Mac1 check independently
  timed out on all three assigned TCP endpoints. The user reports Proxmox
  reachable and no changes; the VM outage cause remains unknown. W2 CLI exit
  at 23:40:42 UTC is not evidence that guest jobs settled.
- Child image edit, saved-result follow-up with inline/download/reload, fresh
  generation, coding/follow-up and PDF/OCR passed their stated cases. Actual image
  download passed. ZIP HTTP/CRC passed; browser ZIP completion is NOT_CONFIRMED
  (1,038-byte partial). Preserve the original H035/H036 failures.
- Qwen native compaction completed at 23:28:57 UTC: 402,104 input / 237 output,
  four facts retained; next request 92,320 and UI estimate 92,544. Automatic
  triggering is inferred from the ordinary UI and native source path; RAW_AUTO
  metadata is absent. Initial paste run `d17d4942` completed. Compaction/follow-up
  owner `346c89f0-a3f6-4668-b3ed-e6230111cf8f` has unknown final/tool result and
  settlement after the outage; session `f006fc27` remains the recovery reference.
- MiMo native 480K readiness passed at 23:07:48 UTC, not occupied-context
  qualification. A tiny first-turn read passed; the second tool-result turn sent
  at 23:28:20 UTC has unknown completion/settlement. Fresh both-engine delegation
  remains pending. Profile fix `47d386` / root `4d927fee` is reviewed and
  source-tested but UNDEPLOYED; the effective MiniMax profile still reports 950K.
- MiniMax native image transport works, recognition PARTIAL; Codex native vision
  UNSUPPORTED. Document extraction/OCR is separate from native vision.
- Prior local checks passed 888 lifecycle tests with 2 existing skips, 5 shell
  suites and whitespace checks. Root verified all eight GitHub checks at
  `92325eff` SUCCESS and now reports all eight push/PR checks at root candidate
  `4d927fee` SUCCESS. The profile fix remains UNDEPLOYED. Neither receipt
  establishes checks for later commits; global capability gates remain closed.

## Recovery and publication

On restored connectivity, the assigned owner first verifies maintenance and
actual owned jobs. The last browser acceptance window was OPEN; do not assume
the scheduled 23:59:10 UTC watcher ran through a possible reboot. Preserve
uncertain ownership and inspect existing operations before any distinct action.
Collect the current compaction/follow-up final, tool continuation, reload and
settlement receipts; then finish protected profile delivery and fresh MiMo 480K
qualification within root's coordinated assignments. Reuse passed evidence.

Root reviews final capability descriptors, public readiness and required checks
for the exact integrated candidate before lifting maintenance or merging to the
actual repository default branch. Keep MiniMax default unless the user changes
that preference. Preserve chats/files, original errors, historical uncertain
owners/quarantines and benchmark failures. Do not replay uncertain work, force
calls, restore GLM or relabel old 950K evidence as 480K. Keep credentials, private
prompts and bulky captures outside Git. This checkpoint does not expand H036's
already-authorized scope into new models, hardware, accounts or installer work.
