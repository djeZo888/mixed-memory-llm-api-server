# H016 Worker1 phase3 — r4 dispatched, loading independently

Latest observation: 2026-09-27T12:25:38.227000+00:00. Session `01a0e2c2-52f5-7450-ae4a-0aa88e17396b`; wrapper deadline **12:41:21 UTC**. No new admission after13:25; unadopted candidate settles13:40; global end13:48:08.

## Actual r4 owner

- Unit: `h016-mimo-initial-20260927-r4.service`
- Invocation: `df2fbf94060b45ed935260449f3e9beb`
- Supervisor:2577861; native PID:2580497
- Container:`7eac71ae92738b478612a3e4bbc3777323e81e5fbe44475020d847e953a64ffe`
- Native StartedAt:`2026-09-27T12:24:27.253246722Z`
- Status:`LOADING`; inference `body_sent=false`; no native identity/qualification/first4K receipt yet.
- Source:`/data/build/H016-20260927/worker1-r4`; logs:`/data/logs/H016-20260927/worker1-r4`.

Launch SSH exited. Separate observation verified the same active unit/native and four consecutive guard samples12:25:19→12:25:34, spacing~5.06seconds. Latest sample age4.04seconds at observation. This demonstrates independent execution after launcher exit; coordinator must verify actual state after this paid CLI exits.

## Narrow correction and evidence

R3 used only the approved none/interleave loading delta derived from reviewed782bd29. It exposed a monitor defect: unbounded process placement ran before mandatory safety assertions. At12:17:15 the last guard sample was197seconds old and guard thread was in `m_start`. R3 was stopped through its exact original owner. PID0/cgroup-empty/GPU-absence receipt12:18:03; normal GLM restoration12:19:30; old unit MainPID0/ControlPID0 verified before r4.

Root directly authorized the single r4 retry12:19. R4 removes all process status/maps/smaps/thread reads from the mandatory safety loop. GPU commands have2second timeouts; GPU temperature/reserves, host reserve and cgroup swap/OOM remain fail-closed. Optional placement runs only after load and after warmup, in a3second diagnostic subprocess with at most0.2seconds additional reap wait. Unavailable diagnostic evidence is not classified as physical failure. An already-set settlement flag prevents a second monitor signal from interrupting owner cleanup. Native options, image, precision, two readonly dependency binds, security, model files, deadlines and GLM lifecycle remain unchanged.

18 focused tests:17PASS,1 historical private-fixture SKIP. Current production17 private fixture test passed. Blocked-diagnostic regression demonstrates repeated mandatory checks and thermal cutoff, plus reserve/swap/OOM/missing-GPU fail-closed cases. Real blocked diagnostic child returns UNAVAILABLE and settles; an unreaped child has bounded wait and retained exact PID. Independent local source review passed. No source-only adoption draft was deployed.

Tiny guard diff: `r4/GUARD-CORRECTION.diff`. Frozen r3/r4 owner/guard hashes and W2 namespace/deadline contract: `r4/COORDINATOR-W2-CONTRACT.json`, also task-level `FROZEN-R3-R4-CONTRACT.json`. W2 owns prospective `scripts/runtime/mimo` and `scripts/control/node*`; W1 did not modify them.

## Retained results and next action

R2 text checks passed. Its tool call completed122input/26output in925.867seconds, and continuation160input/23output in333.836seconds; exact correctness assertions passed. Discarded4K warmup was interrupted; no measured4K completed. R2/r3 sources, stages, logs, stopped containers and private raw evidence are preserved. R3 diagnostic collection spans time and is explicitly non-atomic; it confirmed interleave mappings but is not a loaded-readiness claim.

R4 will independently run native identity, production17 native count, minimal text/tool continuation, discarded representative4K warmup and fresh4096input/256output thinking-off measurement. Read observed count before claiming the9461 pin. No16K/64K before root reviews first4K timing/projection; no1M force. No persistent adoption or activation. Final clean production reload after qualified viability is preferred by root.

Exit paid CLI now while only the independent load/qualification is running. Collect retained OWNER, NATIVE-OBSERVED, optional placement status, TELEMETRY and named result receipts without repeating deep proc reads during load. No benchmark completion is claimed and no linear projection is available.

## Final pre-exit checkpoint

At 2026-09-27T12:29:17.949337+00:00 the same r4 unit/native remains FAILED_SETTLING. Latest guard age 142.716seconds; body_sent=inspect request/slot evidence; SUBMITTED alone does not prove body sent. Named qualification receipts: none. Full sanitized receipt: r4/R4-EXIT-CHECKPOINT.json. This is the final pre-exit observation, not a benchmark completion or proof of future state.

## URGENT r4 terminal failure found12:29:17UTC

Previous loading status is superseded. R4 unit MainPID0/ControlPID0/failed; same invocation. OWNER=FAILED_SETTLING, guard_failure=TimeoutExpired, no native_settled/GLMrestored receipt yet. Last freshguard is older142.7seconds. No identity/qualification/requestresult files; no4K. Worker1 is checking exact candidate/native/service recovery now through original documentedowner path; no retry.

## R4 stop confirmed; documented recovery dispatched

Candidate stopped12:27:59.25659636, PID0/OOMKilled=false. Before recovery, nativePID2580497 absent, originalcgroupempty, frontierGPUcomputeempty reverified. Originalowner andExecStopPost had timedout before thatasynchronousstop completed. Exactsame hash-pinned candidate_owner.py --settle now runs under a boundedindependent recoveryunit; no modelreload/retry/ownerreset. MandatoryGPUquery TimeoutExpired means unavailableGPUtelemetry, not provenphysicalovertemperature/reservefailure. No body sent or4K. See r4/RECOVERY-LAUNCH.json and TERMINAL-FAILURE.md.

## ROOTGO12:34 — CPU override trace confirms --no-host applicability

CPU-MoE isCPU sentinel→firstsupportedCPUbufferlist; withnone, CUDA_Host precedesCPUextra/plainCPU andcalls cudaMallocHost. --no-host excludesGPUhostentry; CPU_Repack/plainCPU useordinaryCPUallocator. SmallGPUuploadstagingpinnedbufferscanremain. Nativebuffername NOTobserved inr3/r4 (loggedonlyafteralloc), CUDA_Host issource-supported inference. Exactpins/excerpts/tinyflag+namespace diff savedphase3/r5. R4settledandGLMrestored12:31:49; recoveryunitsuccess/inactive. Oneauthorizedr5 readyforindependentdispatch, no2sguardrelaxation.

## R5 independent launch 2026-09-27T12:37:25.582643+00:00

MainPID=2779569
ExecMainStartTimestamp=Sun 2026-09-27 12:37:26 UTC
ControlGroup=/system.slice/h016-mimo-initial-20260927-r5.service
ActiveState=active
SubState=running
InvocationID=4600b556d5d04305a9157da80149a511

Source trace passed; exactly single --no-host added to same r4 nativeoptions andguard. R4terminal settlement/GLMrestoration verified bylaunchpreflight. NativePID/startfollow inpostdispatchreceipt; no inferenceyetclaimed.
