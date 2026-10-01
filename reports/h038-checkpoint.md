# H038 — Codex default and current model qualification

**Partial closeout, 30 September 2026.** The authorized execution window was
13:45:26–16:45:26 UTC (15:45:26–18:45:26 Ljubljana). Text workflows passed;
full completion still requires image workflow acceptance on the internal Ada.

## Working and tested

| Capability | Result |
|---|---|
| New chat defaults to Codex 0.158.0 | PASS |
| Attachment, real Python calculation, generated file and file-based follow-up | PASS |
| Codex delegates to MiMo; real tool result, child continuation and parent handoff | PASS; result437, all six requests and native work settled |
| MiniMax delegates to MiMo; real tool result, child continuation and parent handoff | PASS; result667, all five requests and native work settled |
| Frontier delegation activation | PASS; enabled15:22UTC without a model restart |
| Status display separates native readiness from unknown capacity fields | PASS;21 focused checks, server build and deployment |
| Current image source/configuration adopted in protected status registry | PASS; matching UUID, configuration and VM boot |
| Repaired image startup | PASS through visibility, overlay, logging and native execution; API subsequently reports ready/admitting |
| Full HD output and Codex image generation/editing/child workflow on this placement | Not yet qualified |

MiMo and both Qwens retain480,000-token configurations. Codex compaction remains
400,000 and output allowance65,536. Largest fresh MiMo workflow input was14,558
(Codex) and11,977 (MiniMax) tokens; these are workflow tests, not occupied-480K
performance evidence. Original conversations, engine identities and files remain
preserved. The separate Ada200K Qwen is stopped and disabled; weights/history remain.

## Image repair and remaining acceptance

The original startup failed before its backend log opened. A no-GPU diagnostic
ruled out source-integrity and filesystem access failures. Bounded startup receipts
then localized the failure to the GPU-visibility check.

A current GPU-exposed import-only diagnostic showed that container configuration
retained the selected UUID while its process observed `NVIDIA_VISIBLE_DEVICES=void`.
Its argument count, full UUID and `CUDA_VISIBLE_DEVICES` comparison were valid. The
inner guard rejected the observed sentinel. The exact original failed container's
process environment was not retained; today's reproduced mechanism is the direct
evidence, not a recovered historical environment.

The narrow fix accepts only the selected UUID or literal `void` for that NVIDIA
field. Exact UUID/CUDA checks and outer single-GPU containment remain mandatory.
The new positive/negative regression passed, and independent review found no blocker.
Source/configuration were installed16:27:56UTC; one ordinary recovery passed the
previous startup stages. A16:34:34 readback reported the image service ready and
admitting on the internal Gen4x16 Ada. The matching protected registry was installed
16:34:33UTC. MiMo and unrelated source/ownership were unchanged.

**Image tools remain disabled in Sova.** Generation, a fresh-seed guarded follow-up
edit and native image-child handoff require completed live evidence on this placement,
including artifact review and memory/temperature evidence. Earlier external-Ada
results do not substitute for those tests. Frontier delegation remains enabled.

## What consumed the window

Fresh MiMo delegation required actual native tool/result continuation and physical
settlement: the Codex and MiniMax cases completed sequentially. Most remaining work
was image startup diagnosis, guarded source/configuration delivery and rebinding the
status registry. The small diagnostic initially could not start because its resource
bounds were insufficient for the OCI hook; a larger bounded diagnostic reached Python
and exposed the visibility mismatch. Late worker slices completed binding/readiness
checks but did not qualify the image chat workflows. No long-context benchmark or
large compaction test was repeated.

## Publication and next bounded task

Reviewed source, settings and this report are pushed to PR11. It remains draft and
unmerged while image acceptance is incomplete. Native Codex remains0.158.0: the
substantial audited upstream upgrade is a separate task. Native Codex vision remains
unsupported; MiniMax recognition is partial; PDF/OCR and image creation are separate.

Next: reuse the repaired resident image service; verify one Full HD output, then
Codex image generation with a native child and a same-chat fresh-seed follow-up edit.
Review the actual artifacts and settled ownership, enable image qualification,
verify final status/health, and merge the reviewed work to main. Do not reload MiMo,
repeat passed text tests or retry old uncertain jobs blindly.

See [machine-readable results](h038-results.json), [execution plan](h038-execution-plan.md),
and historical [H037 checkpoint](h037-checkpoint.md). Credentials and bulky traces
remain outside Git.
