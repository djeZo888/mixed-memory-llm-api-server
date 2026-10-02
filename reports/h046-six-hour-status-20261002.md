# Sova H046 six-hour work report — 2 October 2026

The execution window is 13:14–19:14 Ljubljana time (11:14–17:14 UTC). The final normal-chat checks completed before the limit. Basic chat and manual context compaction are now demonstrated on the deployed release; the requested image functions and full workflow are unfinished. This is a factual report, not a request to change sessions.

## Original incomplete chat

The STRIX research chat `50d3d298-6f5b-4325-9b8e-00bc64efe0e5` ended with a 178-character planning sentence: “Excellent — full technical specs. Now let me get the tactical enduro page, the battery page, the GIZ military-industry cluster page, and the ownership data from companywall/bizi.” The native engine emitted that same text as its final completion, and Sova stored it. It did not fulfill the research request.

The retained records show no cancellation, timeout, server error, or context-limit event. They do not retain the raw provider finish reason or the time the user's PC disconnected, so they cannot establish why the model stopped early or connect it to the PC being closed. Premature task completion remains unresolved.

A separate real browser-disconnect test passed on the previous release: the browser tab was closed during a 20-second file task; server work continued, the completed chat reopened, and the file downloaded with the expected hash. This establishes tab-disconnect independence for that test. Physical PC sleep and this behavior on the new release need separate acceptance evidence.

## Changes completed

- Used all three SSH workers with fresh isolated GPT-6.1 Sol Ultra sessions for implementation. Source-only checks, raw exits, process inventories and bundle/source hashes were reviewed before integration. Interrupted or failed work retains its actual result.
- Fixed several blockers in protected native startup and publication: exact metadata integer preservation; narrow private-group ancestor validation; measured Podman 4.9.3 isolation; measured no-generation bootstrap notifications; producer-object serialization order for the existing signed ordinary entry. The final local integration HEAD is `1eaa050d`.
- Performed a real minimal Codex startup with initialize/thread-start acknowledgements, no provider calls and no generation. Its native process exited and was reaped; process group and scope absence were independently checked. Publication of the ordinary entry and its source sidecar passed with the existing credential.
- Staged the immutable application release `/opt/ai-harness/releases/ea3d90451773a8f77638575810a4fa6488a61254-h046-podman19`, verified all 942 source/build files and preserved dependency graphs, then restarted the application once. The old owner was absent and the new owner was independently observed healthy. The restart helper itself returned 1 because its immediate readiness request raced startup; that failed receipt is retained and no second restart was issued.
- Retained the original STRIX history projection hash `0abf4ea273f61996cbebcaa2f8b3f812a8634fc87766a390e39479b64c079049`, credentials, model downloads, runtime pins and existing uncertain histories.

## New live-chat failure and recovery

The first normal chat on the new release failed before model inference with `No currently qualified Qwen lane`. It was not an incomplete model answer or a browser-disconnect failure. Native startup succeeded, and its owned process, group and scope later closed.

The vision-maintenance runner held the shared lifecycle lock while waiting for further authorized steps. The node's scheduled real GPU validator needs that same lock, so its hardware proofs aged beyond their 15-second validity. Both Qwen lanes then failed admission despite current GPU inventory. This was interference caused by our maintenance workflow and needs a durable orchestration correction.

An exact owned cancellation was issued with zero model/stage effects. The cancellation helper returned 1 after signaling because it read the outer receipt during an empty-before-write race. The original operation exited with its real nonzero result; independent lock and process checks are used for closure, not an invented successful cancellation receipt.

After the lock was released, real hardware proofs refreshed automatically. At 16:57:23 UTC the deployed ordinary Qwen verifier passed all five real metadata checks. No hardware fields were fabricated, no admission guard was loosened, and no lane reset or GPU service restart was used. A fresh normal UI chat was submitted after this readback; its result is recorded below when complete.

## Images and hardware

Image recognition and image generation are not working in normal Sova use at the end of this work so far. Existing vision owners were verifiably stopped; source-only recovery/qualification helpers were reviewed and staged, but no new vision-model load, 960×640 recognition accuracy acceptance, new NORMAL owner, or normal image upload was completed.

Generation controls, state-CAS helpers and original-result collectors were repaired or staged. No generation API start, backend warmup, image job, FullHD output or editing operation was executed. The saved state refers to an old boot and the reading Ada; it must only be updated against genuine new current owners. The generation warmup/cleanup envelope would exceed the remaining execution window, so it was not started.

The final verification bridge on linux-worker3 is PARTIAL and unqualified. It still compares distinct VM and harness boot IDs as if they must match. Its actual native termination was -15 and wrapper/child waits 143; its outer process's own kernel wait was not captured. Known process groups were subsequently absent. This work is not integrated as a passing validator.

Both Ada cards were visible and idle. The external Ada's VM kernel records showed no new Xid/AER/USB4/Thunderbolt error in the inspected interval. Neither this session's idle inventory nor the user's Proxmox observation qualifies the external cable/card under sustained model load. The reading Ada is also idle after stopping the old vision owner. Two Blackwells remain assigned to Qwen and the third to MiMo; simultaneous model operation and 480k context workloads have not been accepted by this session.

CHA_FAN3 was left as configured in BMC at 100%; fan control and its oscillation fix remain postponed as instructed.

## Final acceptance and remaining work

The final real single-PC chat is `b47a0a3a-a95d-4202-b91f-9fff9802adf4`, using the same native thread `01a0fd8c-ff5b-7d81-a72e-c3d1751d6be2` across turns and compaction:

| Check | Actual outcome |
| --- | --- |
| Normal answer | Completed at 16:58:12.889 UTC with three complete requested sentences. |
| Browser closed during file task | Entire tab closed while Running; server completed at 16:59:59.789 UTC. Reopening restored the answer and file card. |
| File publication | `artifacts/demo-check.md`, 131 bytes, SHA256 `63215c23490107efcefc408252cd53e62654a9241e2c25046652fddaf2218ad9`. Public download endpoint returned HTTP200 and those exact bytes. Browser automation's download-event wait timed out, so a completed browser download is unconfirmed. |
| Manual native compaction | Run `3d5b745c-ab54-4db6-be28-eb663d624354` completed at 17:02:23.777 UTC. Genuine native compaction start/completed evidence, gateway settlement and settled checkpoint `24498e1d-0a46-4769-961b-010b9eca6025` were retained. |
| Follow-up after compaction | Completed at 17:03:25.314 UTC; correctly recalled `amber-otter-46` and read all three checklist items. The previous visible messages and file card remained present. |
| Automatic compaction at large context | NOT_TESTED. This short manual check does not establish 400k/480k performance or every restart/recovery scenario. |

The native answer incorrectly said no downloadable URL could be produced, although Sova successfully added the file card. It also exposed a thinking paragraph in an earlier reply. These capability-prompt and UI issues remain. No suggested ad-hoc HTTP server was started.

Final host readback at 17:07:02 UTC showed the new application active, health HTTP200, PID627898/start22700317, unchanged invocation `9007d4498a054b0cb5226536d37366c9`, and NRestarts0. All 942 release hashes matched. The original STRIX history hash, prior visible acceptance messages, protected credential metadata and the demo file were preserved. Each of the four final acceptance runs' exact native producer birth, process group, container birth and scope was absent; their requests were settled. Application active runs were empty. A separate historical gateway record from 29 September still reported accepted and was retained without mutation, so this report does not claim every global historical gateway record is settled.

All three workers' known task processes were independently absent at closure: worker1's 18 phase paths/34 known identities, worker2's 15 phases and paid CLI, and worker3's 367 known PID references/368 candidate groups plus current native CLI. These are current absence checks; they do not convert historical unknown raw waits or deadline-terminated source work into passes.

The unused vision runner's actual exit was -2 after one SIGINT; its VM outer and initial SSH exited75; the cancellation helper exited1. Four recorded births and three groups were absent. The original canonical lock at device26/inode1698 remained in place, and a nonblocking exclusive probe acquired it and closed the descriptor. All six operation effects remained unspent, no image models were started, and no source41 model code was installed. The historical systemd parent's exit remains `UNKNOWN_GC`.

Required remaining work includes: reliable task fulfillment beyond a premature native final; durable separation of maintenance waiting from short-lived GPU proof refresh; automatic large-context compaction and recovery; qualified vision owner and automatic routing with actual upload/recognition; generation current-owner state adoption, warmup and normal FullHD result; image editing; qualified MiMo research; and a complete single-PC rehearsal.

Private original evidence is preserved under `/Users/agent/Documents/LLMServer/orchestration/tasks/H046-20261002`. The native/publication reviews are in `chat-key-native-ready20`, the live failure diagnosis in `chat-live-acceptance20/BASIC-FAILURE-DIAGNOSIS.json`, and image/hardware lane evidence in the vision and generation directories. Failed original checks, expired unused approvals and historical `UNKNOWN_GC` exits are retained with those labels.

Root's final reviewed source references and acceptance limits are in `ROOT-FINAL-REVIEW.json`. The final UI screenshot is `CHAT-COMPACTION-FOLLOWUP.jpg`. No further model turn or worker implementation session was started after the final follow-up.
