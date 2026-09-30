# H036 — recovery after the hardware change

Updated September 30, 2026. This report supersedes the availability and pending-work statements in the [earlier hardware checkpoint](h036-reboot-recovery.md), while retaining its original failure evidence.

## Current result

The user removed the external Core X image GPU from ai-vm passthrough and authorized software recovery. At 04:30 UTC, **MiMo and all three Qwen instances were ready**. The application and private search service were healthy by 04:43 UTC. Public maintenance remains the default, with a bounded window for final chat/delegation checks.

The first fresh Codex requests at 04:56 UTC were rejected before generation: the control projection did not establish a qualified Qwen route. Later readback showed current generations but failed control readiness, while the same backends reported healthy through node/native checks. Worker1 is tracing that discrepancy; no successful recall or Codex delegation is claimed from these rejected requests. Both requests physically settled with their failed outcomes preserved.

| Service | Current configuration | Observed result |
|---|---|---|
| MiMo V2.6 Pro-RL | CPU experts plus its existing Blackwell; 480,000 tokens | Native readiness, a real tool call and its result continuation passed; requests settled |
| Qwen0 and Qwen1 | Existing Blackwells; 480,000 tokens each | Healthy; native identities and start times preserved |
| Separate Ada Qwen | Existing internal Ada; 200,000 tokens | Supervisor recovered; health passed; remains outside harness routing |
| Image service | External Ada intentionally absent | Reports unavailable and does not block text services |
| Sova application and SearXNG | Reviewed existing runtimes | Cold-start recovery passed; no native engine/model rebuild |

MiMo's protected profile now delivers **480,000 context / 65,536 maximum output tokens** to both launch paths. The fresh native check used only 99 and 123 input tokens. It establishes tool continuation and configured allocation, **not occupied-480K performance or correctness**. Unchanged-runtime support for the full tool roster, nested schemas and output ceiling is explicitly carried forward from historical evidence; those large/structural cases were not repeated.

## Repairs and preservation

- MiMo's interrupted old-boot owner is reconciled only after confirming that its original native process is gone. The old state, request and failure evidence are archived. One normal model start created the new owner; the interrupted request was not replayed or marked successful.
- Ada supervisor status writes are atomic. The stale temporary file that caused its previous failure remains preserved.
- SearXNG removes only its own stopped container before starting. The live cold-start check passed with its image, configuration and private secret unchanged.
- The selected interrupted Codex conversation was released for a **new** follow-up through the reviewed offline recovery command. Its original messages, accepted requests, run outcomes and generated files remain unchanged. The original incomplete turn remains `interrupted_unknown`; physical settlement is distinct from successful completion.
- Two older uncertain owners and three older quarantines remain separate and unchanged. App startup added its normal restart audit events; this is not a claim of whole-database byte identity after startup.
- The old application release, all static assets and native engine images were preserved. The new release differs only by the reviewed recovery/profile files.

The strict process scan initially encountered Linux `/proc` permissions. The one-shot recovery command ran as the application user with narrowly scoped transient `CAP_SYS_PTRACE` and `CAP_DAC_READ_SEARCH`, retained groups and `no-new-privs`. It did not grant persistent service capabilities, set file capabilities or change host sysctls. The new release's writable directory modes were corrected before the unchanged source-integrity check passed. See [offline recovery operations](../ai-harness/docs/h036-offline-recovery.md).

## Validation

| Check | Result |
|---|---|
| Recovery backend focused/adjacent tests | 323 passed, five existing skips |
| Full application server regression suite | 973 passed, four existing skips, zero failures |
| Adjacent application recovery/profile tests | 115 passed, one existing skip; typecheck/build passed |
| Exact published source `75b384f` GitHub checks | All eight push/PR checks passed |
| Fresh native MiMo tool/result continuation | Passed, full HTTP drain and physical idle confirmed |
| Selected Codex offline recovery and preservation | Passed at 04:38 UTC |
| App/search cold start | Passed; no repeated app restart |
| Distinct recovered-chat follow-up | First new request rejected before generation; readiness diagnosis in progress |
| Browser ZIP and saved-link reload | Passed in normal headless Chrome; 1,038 bytes, exact four files, CRC passed |
| Fresh MiMo delegation through both engines | Pending final acceptance |

Previously passed image generation, guarded editing, saved-image follow-up, coding and PDF/OCR cases remain dated evidence. Image hardware is absent during this recovery, so no new image acceptance was attempted. MiniMax native image recognition remains partial; Codex native vision is unsupported. Neither limitation is replaced by OCR or image-generation support.

The Codex in-app browser's separate ZIP event wait timed out; it is not relabeled as a completed download. The worker's subsequent ordinary Chrome check captured actual completion, saved the archive with the original expected hash, verified its contents and reloaded the saved link. Root independently reviewed the retained coding conversation, both uploads, generated files and follow-up answer after reload.

The original Qwen compaction processed 402,104 input tokens into a 237-token summary retaining all four facts. Automatic triggering was inferred from the ordinary UI/native source path; raw trigger metadata was absent. Its later interrupted request remains a separate failure. The large paste and the failed near-950K MiMo benchmark were not repeated.

## Runtime records and remaining release work

Worker1's activation session `01a0f078-e01f-7353-a6df-4e6b64270cf8` exited zero at 04:33:08 UTC after completing backend recovery. Worker2 owns final application acceptance. A fresh Worker1 task separately traces the newly observed control-readiness discrepancy, without issuing inference or changing model lifecycle state. Public admission and the main-branch merge remain held until those checks and the final candidate review pass. MiniMax remains the default; Codex remains a per-chat preview.

Compact [machine-readable results](h036-resumed-recovery-results.json) identify the retained receipts. Credentials, prompts and bulky process/network traces remain private outside Git.

## External GPU link

No new cable or bandwidth test was performed. A model whose weights and working state remain on the GPU avoids repeated host transfers; slower links primarily affect loading and transferred inputs/results. CPU offload or frequent cross-device transfers can make link speed important. A 20 Gb/s link does not imply half the inference speed. NVIDIA recommends keeping intermediate data on the device and minimizing host/device transfers: [CUDA Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#data-transfer-between-host-and-device).

The user's earlier `20 Gb/s` speed with two lanes already represented 40 Gb/s per direction. The effect of an actual 20 Gb/s configuration on this image model remains unmeasured.
