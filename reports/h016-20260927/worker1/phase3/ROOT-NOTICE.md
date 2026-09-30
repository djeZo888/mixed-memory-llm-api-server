# H016 Worker1 phase3 — R5 launched, exit before12:41:21

Latest actual read: 2026-09-27T12:37:56.478207+00:00. R5 status **LOADING**, body_sent=False; no first4K result claimed.

- Unit:`h016-mimo-initial-20260927-r5.service`
- Invocation:`4600b556d5d04305a9157da80149a511`
- Supervisor:2779569; native:2782009; StartedAt:2026-09-27T12:37:37.213589148Z
- Container:`c724b72b99f57f9e72b21bbc2a1fc104a9109b970657d5694ba05c25160a8308`
- Source/log:`/data/build/H016-20260927/worker1-r5` and `/data/logs/H016-20260927/worker1-r5`
- Latest guard sample age:3.10109seconds. Separate SSH observation confirms independentexecution after launcher exit.

R4 stopped exactcandidate at12:27:59 after mandatoryGPU query TimeoutExpired. Its originalstop/finally timed out before asynchronousstopfinished. Worker independently verified PIDabsence/cgroupempty/GPUabsence and ran only originalowner --settle in systemd recovery48bffd94fed0409b9033523c82ea82a7. GLMnormalrestore completed12:31:49; recovery success/inactive verified12:31:58. R5preflight reconfirmed terminalr4+normalGLM before suppressing/stoppingGLM again.

The failing command is `nvidia-smi --query-gpu=uuid,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu,power.draw --format=csv,noheader,nounits`, configuredtimeout2seconds. Exactelapsed was not persisted; no fabricatedduration. Lasthealthy12:26:55 had ownedSwap/OOM0, hostavailable383776641024B and531016941568Bshmem. Timeout proves unavailablemandatorytelemetry, not physicalovertemperature. Evidence: r4/GPU-TIMEOUT-EVIDENCE.json, R4-EXIT-CHECKPOINT.json, RECOVERY-LAUNCH.json and r5/R4-SETTLEMENT.json.

RootGO12:34 authorized oneR5 after exactsource trace. `--cpu-moe` is aCPUbuffer sentinel; loader resolves firstsupportedCPUbufferlist. Pinnedsource ordersGPUhost beforeCPUextra/plainCPU when no_host=false. CUDA_Host allocates via cudaMallocHost; none does not take mmap's host→CPUreplacement. `--no-host` removesGPUhost from thatlist; CPU_Repack andCPU allocate ordinaryRAM. SmallpinnedGPUuploadstaging may remain. This is source-supported mechanism; r3/r4never emitted completed modelbuffername. R5must retain actualloadedbuffer/RSS/NUMA readback before claimingordinaryCPU success. Exactcommit/filehashes/excerpts: r5/PINNED-NO-HOST-TRACE.json and SOURCE-EFFECT.md.

R5adds SINGLE --no-host toexactR4none/interleaveargv plusfreshnamespace; telemetry hash remains`2c0e7483845530cf9b669d699c67b574e0f4a8cbba21dd6c511bc7ddf7f817aa`. Ownerhash`11041d78f05bb0522d48b293f0a4283629d4a15f787e8477be6591b4b7faa483`. Focusedargv equality, unchangedguard/proxy/identity andsyntax passed. R4guardregression18tests17PASS/1historicalprivateSKIP is retained; no broadretest/rebuild/download. Allweights/nativeMXFP4/BF16/F32, GPUtrunk/CPUexperts,128K/F16KV, batch/threads/security/deadlines unchanged. Tiny diff:r5/NO-HOST-CORRECTION.diff.

IndependentR5 will qualify nativeidentity/count, minimaltext/toolcontinuation, discardedwarm4K andfresh4096input/256output thinkingoff. Newadmission closes13:25; unadoptedcandidate settles13:40; globalend13:48:08. No16K/64K untilroot first4K timing/projectionreview. No liveadoption orproductionactivation. W2owns source-only ordinaryproductionowner/node; thosefiles were untouched.

R2text/toolcorrectness retained; no measured4Kcompleted inR2/R3/R4. Allr3/r4source/stage/stoppedcontainers/receipts preserved. Rawprompts/traces outsideGit. Root must verify actualunit/guard/results afterthisCLI exits. No furtherautomaticretry.
