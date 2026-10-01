# Latest human steering

Read the GPU placement and thermal authority in [H040 plan](reports/h040-execution-plan.md). At >=70 C, the four integrated GPU cards command100%; the latest CHA_FAN3 exception commands80% at70 C and100% strictly above80 C; this specifically supersedes the earlier no-fan-change restriction. Slot2/slot5 UUID mapping is pending; no new GPU starts until verified. Stable Ada is visual-to-text, returned Ada is image gen/edit.

# Current H040 authority — 1 October 2026

The user confirmed ai-vm is back up with the second Ada and authorized resuming planned work. The H039 hardware hold and expired initial deadline are superseded by [H040 plan](reports/h040-execution-plan.md), 02:26:10–04:26:10 UTC / 04:26:10–06:26:10 Ljubljana. Adopt existing closed sessions/failed download state. Compaction reliability stays first; preserve existing runtime/routing/context and all original histories/credentials. Root reviews concrete candidates before live work. A is initial sole backend lifecycle owner; C is sole artifact writer and waits for A/root handoff. E/B implement isolated source. No driver/Proxmox changes, creative-image acceptance, upstream upgrade or PR merge. Earlier H039/H038 sections below are retained history.

# Sova — H039 coordination

## Current authorization — 1 October 2026

Read [H039 plan](reports/h039-execution-plan.md) and
[handoff](reports/h039-handoff.md), adopting existing worker sessions first.
The user authorized parallel compaction implementation/retention fixtures and
Qwen3.5-9B BF16 plus PaddleOCR-VL-1.6 artifact/runtime/vision-tool preparation.
Sova may remain offline; smaller Ada Qwen retirement is permitted. H039 initial
window closes 02:25 UTC on 1 October. Creative image acceptance, driver/fan/
Proxmox work and upstream Codex upgrade remain outside this window. A/B/D own
isolated source only; C is the sole ai-vm artifact-storage writer. Shared live
deployment follows root candidate review. Latest user authority supersedes the
older H038 no-new-model rule for these two approved artifacts only.

Latest user steering: shut ai-vm down after its currently assigned work ends so a second Ada 48 GB can be installed. The bounded artifact attempt ended in staging failure with no active download. C completed orderly guest poweroff at 01:33:22 UTC / 03:33 Ljubljana, and all native Mac source tasks have closed. Freeze all new ai-vm downloads, deployment and inference. Read the current worker roster for the actual shutdown receipt. Leave the guest down until the user confirms hardware installation is complete; no automatic restart. This authorization covers normal guest shutdown, not host/Proxmox, driver or fan changes.

The H038 text below is retained deployment evidence, not current task authority.

Read the [H037 plan](reports/h037-execution-plan.md) and
[upstream audit](reports/h037-upstream-codex-audit.md). The previous
[H036 instructions](reports/h036-agent-instructions.txt) are a historical record,
not the current deployment state. H036 recovery and failed outcomes remain in
[its report](reports/h036-resumed-recovery.md).

## Retained H038 assignment

The user authorized H038 on 30 September 2026, 13:45:26–16:45:26 UTC
(15:45:26–18:45:26 Ljubljana). Read reports/h038-execution-plan.md.
H038 passed default Codex and fresh Codex/MiniMax MiMo delegation. Frontier is enabled.
Status collection/display are restored. Image startup is repaired and the current
registry matches; image workflow qualification remains incomplete and its gate is
closed. Read reports/h038-checkpoint.md and reports/h038-results.json. Reuse repaired
source and loaded models. A new execution window requires user authorization; do
not replay migration, text acceptance, source audits or long-context tests.

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
upgrades are authorized by H038. The repository default branch is main.
