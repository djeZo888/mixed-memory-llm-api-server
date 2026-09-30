# PROFILE09 — R7 speed confirmed; tool qualification incomplete

**Do not treat the 17-tool gate as passed.** The native CLI turn interruption removed the session-bound Mac receiver/SSH process after first output. Turn1 finished natively at14:53:36.347704Z (slot release14:53:36.348009Z); authenticated slot was idle at14:54:07.937Z and14:56:40.249Z. Final SSE, usage, finish/DONE/drain, call ID and arguments were not preserved. The actual file read and turn2 were never executed. No replay or replacement512 was dispatched. ROOT-NOTICE and TOOL17-URGENT.json report this before packaging. Root must decide the next gate; no automatic retry.

Turn1 sent14:50:53.574954Z, first output14:53:16.426975Z/mono33499.774721107. Exact production17 roster hash80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c includes browser and unchanged nested strict fields. Initial user text array/count9505/max_tokens65536/thinkingtrue/auto/parallelfalse reached native generation. Native log:9505 prompt/121 predicted,142624.30ms prompt/20095.17ms decode. These log counts are not saved usage parity and cannot qualify actual tool continuation. A host counter interval starting after14:53:36 would miss this turn's decode. Exact last-output receipt time is unavailable; do not substitute native log end for it.

## Verified R7 comparison

Source base46f8c79815455c2e2dca2bc2df496b159996e762; sole changed treatment GOMP_SPINCOUNT=0. BASELINE128 native decode21.579608s/5.885186t/s,6.29289x R6; PROFILE12837.753028s/3.363969t/s,3.42468x R6. Native uses127 intervals for128 output. Same-phase request and output content hashes match R6/R7. A/B fixtures and outputs differ; profile follows baseline, so order/profiler bias remains. R7 raw/native spans agree within0.1ms;130chunks/128output events, no observed coalescing. Both samples are throughput ceilings, UNSCORED.

R7 saved perf:8.590875cores,2.533IPC;49.52% kernel finish_task_switch,38.13% exact native MXFP4 GEMV,7.98% kernel spin-unlock. R6 known libgomp pause offsets account for94.56%; R7 records zero samples at those offsets and100/19073 samples across all libgomp (0.5243%). Do not interpret samples as wall-time recoverability. Context switching increased substantially. Boundary CPU averages10.99/8.16 vs58.37/58.91; no request major-fault/read-byte growth, swap/OOM or throttling. R7 dmon SM8.67%, PCIe46/11.44MB/s are discrete snapshots, not host DRAM or GPU VRAM GB/s.

## Completed host-capture request

Single original unprofiled512 sample:100input/512output, finish length, DONE/full drain, native slot idle. Body14:47:54.704672Z; first14:47:57.080934Z; last14:49:22.182157Z; DONE14:49:22.182261Z; drain14:49:22.182354Z. Native2362.739ms prompt,85101.241ms decode,6.004613t/s. First-output event was written immediately to this task's ROOT-NOTICE and private/profile9/UMC512-PROGRESS.jsonl. User host sample alignment/result is root-owned; actual bandwidth remains pending. No CPU perf/activity collectors were added. Latest root steering holds replacement512; none sent.

## Exact continuing owner and next session

R7 systemd unit h016-mimo-profile-20260927-r7.service, invocation2034e3b8f6004f6da8ebf7a92a389690, owner229308. Containerb0c319cce5c8fcececc28acb01ec92f68693588ba843c8136107927aa7ffbac1/native232672/StartedAt14:28:05.871420053Z remains warm. Imagecdb6efd, llama7ac59a6,131072/F16/nativeMXFP4,704GiB cap, no owned swap. Admission15:15, owner settlement15:35, global15:48:08 unchanged. Sova stays paused; no tuning/reload/stop/adoption here. Last boundary14:56:40 passes storage/root guards and authenticates native idle. Normal exact-owner stop/GLM restore remains the next explicitly reviewed transition.

Production owner staged one level above repo: SHAee5d623f3334afba341e1539383ca672f7f4db096cf329adf1c69d2b871ec814 verified locally, not applied. Root's13offlinechecks are root-reported, not rerun. Clean production launch belongs to next fresh bounded native session after the actual gate decision, normal R7 settlement and GLM restore; never hot-adopt. Publish/configure/occupy context separately; no1Mi occupied-context claim.

SOURCE-PACKET, MEMORY-IDENTITY, GUARD-MEMORY and QUALIFICATION JSON provide granular facts. Native raw/effective template hashes remain11ea52e1…/16b2dac3… with3867/3866bytes. Registered owner sources/DSO prior pins retained; no runtime bootstrap, full pin/shard inventory or new profiling was repeated. Cgroup current611GiB roughly497GiB anon+113GiB file+1GiB kernel; mapped-file/shmem are subsets, not additional allocations. Exact values and whole-cgroup lifetime peak are in GUARD-MEMORY.

## Collection defect and required future repair

Task client sources are historical execution evidence, **not approved durable launchers**. The local receiver used ordinary subprocess SSH under native exec; raw chunks were retained only in remote memory until final stdout RECEIPT. A turn interruption lost them. stdout failure can also preempt the client's exception cleanup because FAILURE is emitted before settlement. Do not reuse these clients unchanged for the next native qualification.

A future reviewed collector should be systemd-owned remotely under the existing model owner, with a launchd-owned Mac receiver. Persist exact request intent/progress and bounded buffered SSE to anchored registered logs; write final VM receipt before best-effort notification; keep cleanup independent of stdout. No per-token guard/lease/fsync, no duplicate model owner, no retry after ambiguity. Source-only repair can be reviewed separately; nothing was installed now.

CLI started14:41:00Z; absolute cap15:01:00.438481Z. Wrapper writes exact exit-code/finished-utc after exit. Raw/perf/private prompts, SSE and manifests live outside Git at task/private/profile9. Existing pair15files/3649138bytes were preserved off-VM with verified hashes; final telemetry and512 receipts are additionally manifested. Source syntax/help and offline comparison checks passed; no Git push.
