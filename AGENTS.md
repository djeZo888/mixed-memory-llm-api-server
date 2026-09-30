# Sova — H037 coordination

Read the [H037 plan](reports/h037-execution-plan.md) and
[upstream audit](reports/h037-upstream-codex-audit.md). The previous
[H036 instructions](reports/h036-agent-instructions.txt) are a historical record,
not the current deployment state. H036 recovery and failed outcomes remain in
[its report](reports/h036-resumed-recovery.md).

## Current assignment

H037 began 30 September 2026 at 10:37:52 UTC; its hard deadline is 13:37:52 UTC.
H037 is paused at its execution-window checkpoint. Reviewed source/config
delivery and normal MiMo/image start dispatch passed; live qualification remains
incomplete. Read reports/h037-checkpoint.md and reports/h037-results.json.
Do not duplicate existing starts or infer readiness from dispatch. New execution
requires a new user-authorized bounded window. Optional tools remain closed.

The user retained 480,000 context, the existing 400,000 Codex compaction threshold
and 65,536 output ceiling. No adaptive output budget is part of H037.
Codex becomes the new-chat default; existing chats retain their engine and files.
MiniMax remains selectable. Sova's Codex runtime stays pinned at 0.158.0 because
the audited upstream main differs substantially. The three Mac CLIs are 0.159.2;
that does not update the separately pinned Sova runtime.

The planned active roster is MiMo on RAM plus a fast Blackwell, two 480K Qwens on
their fast and Gen3 x4 Blackwells, and Qwen-Image on the internal Gen4 x16 Ada.
Retire the Ada's separate 200K Qwen through its owned stop without deleting
weights or history. Preserve Full HD, guarded edits, seed restrictions and 5%
image VRAM reserve. The external Core X Ada remains intentionally absent.

## Working rules

Root plans, coordinates, reviews and publishes. Both Mac workers implement,
build and test through fresh bounded native CLI sessions using GPT 6.1 Sol Ultra,
isolated copies, actual session IDs and terminal receipts. One named owner
performs each shared deployment. Keep paid sessions closed during model loading
or dependency waits. Retain partial and failed outcomes honestly.

Use current lifecycle/storage/ownership guards and coherent protected source
successors. Necessary MiMo restart must produce a fresh truthful native identity.
Preserve unrelated uncertain owners, quarantines, chats, files and credentials.
Keep private prompts, secrets and bulky traces outside Git.

Reuse unchanged qualification. Do not repeat 950K tests, the passed large Qwen
compaction paste or occupied-480K benchmarks. Source fixtures do not qualify a
new native placement or workflow. Codex native vision remains unsupported;
MiniMax recognition is partial. OCR and image generation are separate capabilities.

No new models, Proxmox, drivers, fan changes, general installer or automatic
upgrades are authorized by H037. The repository default branch is main.
