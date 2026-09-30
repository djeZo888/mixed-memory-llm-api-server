# H038 — Codex default and current model qualification

**Active checkpoint, 30 September 2026.** The execution window ends at
16:45:26 UTC (18:45:26 Ljubljana). This report records current results and will
be updated at closure; it does not declare full completion.

## Passed

- Status collection restored, protected current image selection adopted, and both
  VMs visible. MiMo and both 480K Qwens are loaded and ready.
- New chat with engine omitted uses Codex. Attachment, real Python calculation,
  generated file and file-based follow-up passed. Refresh shows separate replies,
  reply activities, downloadable files and context usage.
- Codex delegated to the current MiMo, which ran Python, consumed its tool result,
  returned437, and handed the result to its parent. All six provider requests and
  the native child settled. Largest MiMo input was14,558 tokens; this is a short
  workflow qualification, not occupied-480K performance evidence.
- Reviewed status display patch separates current native readiness, unknown native
  output ceiling and configured Sova policy.21 focused checks and server build
  passed. The display patch was deployed at15:16:33UTC after the active cases settled.

- MiniMax delegated to MiMo, which ran Python, consumed the tool result and
  returned667 to its parent. Native agents and all five requests settled. Root
  reviewed both workflows and approved frontier qualification independently of
  the still-unavailable image service. Ordinary frontier activation passed at
  15:22:00UTC with image disabled, no active requests and no model restart.

## Remaining

Image startup failed at its GPU-visibility check before model loading. The exact
image, file permissions, evidence-directory access and adaptive source guard passed
in a diagnostic without GPU exposure. A narrow, bounded startup receipt was added
and deployed. One ordinary recovery then recorded `unexpected_gpu_visibility` at
that check; it did not reach overlay setup, logging or model execution. The specific
argument/environment comparison is still being isolated.

The internal Ada's installed source/configuration pair was adopted in the protected
status registry at15:57UTC. Fresh readback matched its UUID, configuration and VM
boot. Frontier remains enabled and image remains disabled. Generation, guarded
follow-up editing and native image-child handoff are **NOT_TESTED** on this new
placement. Earlier external-Ada image evidence does not qualify it.

## Scope retained

480,000 context /400,000 compaction /65,536 output. Codex0.158.0 remains pinned;
the substantial upstream upgrade is a separate task. Original conversations,
engine identities and files are preserved. No long-context benchmark or large
compaction test was repeated. Native Codex vision is unsupported; PDF/OCR and
creative image generation are separate functions.

See [machine-readable results](h038-results.json), the
[execution plan](h038-execution-plan.md), and historical
[H037 checkpoint](h037-checkpoint.md). PR11 remains draft while qualification
is incomplete. Credentials and bulky transcripts remain outside Git.
