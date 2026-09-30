# H036 — recovery after the hardware change

Updated September 30, 2026. This report supersedes the availability and pending-work statements in the [earlier hardware checkpoint](h036-reboot-recovery.md), while retaining its original failure evidence.

## Current result

The user removed the external Core X image GPU from ai-vm passthrough and authorized software recovery. At 04:30 UTC, **MiMo and all three Qwen instances were ready**. The application and private search service were healthy by 04:43 UTC. The final Codex/MiMo workflow passed at 07:39 UTC and public access was restored at 07:45 UTC. Both ordinary HTTP and the reloaded browser passed.

The first fresh Codex requests at 04:56 UTC were rejected before generation: the control projection did not establish a qualified Qwen route. The protected Qwen pair record still pinned the old status-observer source. The new observer was reviewed and deployed during recovery, but its dependent record was missed. Worker1 applied the reviewed two-file metadata correction at 05:28:52 UTC. Normal authenticated control readiness passed for both Qwens at 05:29:02 UTC. All historical measurements and native model identities remain unchanged; no service/model restart was required. No successful recall or Codex delegation is claimed from the rejected requests. Both physically settled with their failed outcomes preserved.

MiniMax's separate fresh MiMo delegation passed: a native child executed one Python calculation, continued from the tool result and returned the correct answer to its parent. All six provider requests and both native sessions settled by 05:06:49 UTC. The largest MiMo request contained 11,979 input tokens; this is a workflow check, not a throughput or maximum-context benchmark.

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
| Corrected Qwen control readiness | Passed for both lanes, current generations and ready endpoints; native identities unchanged |
| Distinct recovered-chat follow-up | Passed: actual retained-file read, four correct facts, 0.825 W and physical settlement |
| Browser ZIP and saved-link reload | Passed in normal headless Chrome; 1,038 bytes, exact four files, CRC passed |
| Fresh MiniMax → MiMo delegation | Passed, actual child/tool continuation/final and complete settlement |
| Fresh Codex → MiMo delegation | Final corrected case passed: actual Python tool, continuation, child and parent finals, all seven provider requests settled |

Previously passed image generation, guarded editing, saved-image follow-up, coding and PDF/OCR cases remain dated evidence. Image hardware is absent during this recovery, so no new image acceptance was attempted. MiniMax native image recognition remains partial; Codex native vision is unsupported. Neither limitation is replaced by OCR or image-generation support.

The Codex in-app browser's separate ZIP event wait timed out; it is not relabeled as a completed download. The worker's subsequent ordinary Chrome check captured actual completion, saved the archive with the original expected hash, verified its contents and reloaded the saved link. Root independently reviewed the retained coding conversation, both uploads, generated files and follow-up answer after reload.

The original Qwen compaction processed 402,104 input tokens into a 237-token summary retaining all four facts. Automatic triggering was inferred from the ordinary UI/native source path; raw trigger metadata was absent. Its later interrupted request remains a separate failure. The large paste and the failed near-950K MiMo benchmark were not repeated.

After the readiness correction, a distinct resumed follow-up completed. It read the unchanged 98-byte file and returned all four facts and 0.825 W. The file also contains those facts, so this does not isolate summary-only recall. Its two requests used 93,460 and 93,654 input tokens. Both settled; no original failed outcome was relabeled.

The fresh Codex delegation reached an actual MiMo child. A subsequent parent count request failed because the control endpoint returned HTTP 503 `observation_unavailable` after 15,768 ms. Both lanes' initial identity/native checks had passed; this was a control transport failure, not a demonstrated model identity or allocation change. The child was cancelled before its tool call and fully settled by 05:40:15 UTC; its scoped ticket was removed. That failed case remains unchanged. A distinct final case passed after the adapter repair, as recorded below.

Worker1 measured 512 repeated storage-verification calls in one status observation. The installed observation took 9,683.858 ms, including 8,769.2 ms of cumulative storage verification; native model probes took 523.09 ms. A controlled source comparison reduced the observation to 1,247.102 ms while retaining fresh path and mount checks. Its 83 focused/adjacent tests passed. This establishes substantial avoidable overhead, but does not identify the exact exception inside the historical 15,768 ms failure.

That intermediate candidate was **not deployed** and its shared-module change
was reverted. The final fix, `052994a`, places the wrapper in the adapter and
keeps the shared storage module unchanged. It passed 91 focused/adjacent tests,
51 existing cold-transition tests (two existing skips), and all eight GitHub
checks. The 1,247 ms comparison above belongs to the earlier shadow candidate;
actual final deployed observations are recorded below.

Deployment preflight also found two historical differences between the control
and node packages. The approved delivery aligns the control copies with the
already reviewed, running node versions. This changes no additional MiMo
manifest entries. Both packages now match the same reviewed source inventory.

Two staging attempts stopped on lifecycle-lock contention before writing any
file or changing a service. A later capture showed the ordinary node observer
holding that lock for approximately 0.72 seconds. The holder at the first
failure was not captured. The last bounded operational attempt waits up to ten
seconds to acquire the same lock, with the existing ownership and source checks
unchanged. No forced unlock or hardware action is authorized.

The final delivery completed at 07:09 UTC. Both package copies now match the
reviewed source. Normal control and node endpoints returned HTTP 200 and both
Blackwell Qwen lanes were ready with unchanged native identities. One normal
MiMo start created its new owned `LOADING` instance at 07:09:48; readiness passed at 07:23 UTC using the current owner, native properties and the
sole idle 480K slot. The old container remains archived and stopped. Ordinary controller requests now
take 0.993 and 0.959 seconds; the node request took 0.013 seconds. These are
readiness observations, not a repeated model benchmark.

Two operational sequencing defects were corrected without changing production
ownership rules: the deployment helper now distinguishes its own held lock from
another service's lock, and it restarts the normal hardware-status producer
before the owner requires a fresh GPU-health proof. No latch was manually edited
or cleared. The original refusals and intermediate states remain recorded.


## Final Codex delegation

The final application aligns its controller-version pin with the reviewed
backend. The sole new Codex case was accepted at 07:25:46 UTC and completed with
full physical settlement at 07:39:14 UTC. MiMo's child actually executed
`python3 -c "print(19*23)"`, received exit status zero and output **437**, then
completed its tool-result continuation. The parent delivered the correct final
answer. All seven provider requests settled, no request remained pending, and
the scoped acceptance ticket was removed at 07:39:38 UTC.

MiMo's two requests used 15,130 and 15,322 counted input tokens with the normal
65,536-token output allowance. This was an end-to-end harness workflow check,
not a speed benchmark; the previous controller failure did not recur. Native
engine images and the original chat/file evidence remain preserved.

## Release and review

The exact protected qualification was installed using the existing validator.
The final application restart passed normal readback; public access was restored
at 07:45:07 UTC. Ordinary root and health requests returned HTTP 200. Codex
frontier delegation is enabled, MiniMax remains the default, and Codex remains
a per-chat preview. Image workflow qualification is retained separately from
its current unavailable hardware. No inference was submitted after the restart.

Root independently reloaded the normal browser and opened the completed test:
connected, ready, zero active subagents, MiMo available and idle, correct final
answer **437**, 480,000 configured/allocated context, and the image-unavailable
notice. Histories, files and original failed outcomes remain intact.

[PR 10](https://github.com/djeZo888/mixed-memory-llm-api-server/pull/10) records
reviewed publication and main-branch merge status. Compact results identify
source checks separately from deployment and actual live acceptance. Both workers
are closed; the final native and outer processes exited zero at 07:47:45 UTC,
without deadline termination.

Compact [machine-readable results](h036-resumed-recovery-results.json) identify the retained receipts. Credentials, prompts and bulky process/network traces remain private outside Git.

## External GPU link

No new cable or bandwidth test was performed. A model whose weights and working state remain on the GPU avoids repeated host transfers; slower links primarily affect loading and transferred inputs/results. CPU offload or frequent cross-device transfers can make link speed important. A 20 Gb/s link does not imply half the inference speed. NVIDIA recommends keeping intermediate data on the device and minimizing host/device transfers: [CUDA Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#data-transfer-between-host-and-device).

The user's earlier `20 Gb/s` speed with two lanes already represented 40 Gb/s per direction. The effect of an actual 20 Gb/s configuration on this image model remains unmeasured.
