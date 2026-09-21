# Closed 480K CPU comparison — source handoff

This narrow source correction uses fixed identity `benchrun-c480-cpu-cont2-20260920`,
prepared from reviewed `0414f8fe`.
The predecessor Q480 reached readiness but native proof failed; its on-wire
response was not retained. A same-image restored-production safe-field receipt
confirms flat top-level context_length, tp_size, pool/input and one internal state.
Its1M/TP2 values are not failed-Q480 measurements. The same five cases and four
warmups remain. The inherited IDFIX correction preserves the earlier0755-extraction
failure provenance and checks owned0700/no-symlink private artifacts before host
staging/ownership.
PREP performs no VM contact, model operation, inference, profiling, deployment,
source publication or measurement clock. Root reviews the source, arm and current
ownership before bound GO resumes this same retained Worker1 session/copy for RUN.
Production remains the original Qwen TP2/1M singleton; G480/Q700 validation and production activation are deferred.

Exactly four manifests configure both models at480000:

| Layout | Active guest vCPU budget | GLM threads / cpuset | Qwen permitted vCPUs / cpuset |
|---|---:|---|---|
| A |112|96 / `0-95`|16 / `96-111`|
| B |96|88 / `0-87`|8 / `96-103`|

The guest still has112 vCPUs. B leaves16 unused by these models; this does not
establish an actual96-vCPU VM, physical pinning or locality. Q8 describes affinity
capacity, not eight runtime threads. Thread counts are observed separately.
All model/runtime/cache/tensor/batch/sampling settings remain fixed: GLM
UD-Q4_K_XL/N76/F16/GPU0; Qwen FP8/BF16KV/YaRN4/TP1/static0.8/chunk2048/GPU1.
The original exact GPU UUIDs and640/32GiB equal no-swap caps remain mandatory.

Root's durable incoming override selects explicit
`sampled-required-working-set-15pct-v1`: sampled required working-set ESTIMATE
multiplied by1.15 must fit each cap. This is not15% of host RAM or an allocation
claim. Raw cache/current/peak stay separate; the existing estimated-demand formula
and historical native floor provenance remain visible. Absent policy retains the
legacy25% receipt field semantics. The only production-source edit adds explicit
policy selection to a future reviewed acceptance receipt; no profile declaration,
API behavior, receipt fabrication or activation is included.
Fresh688GiB host admission, remaining-cap obligations with disjoint resident
anon/no-swap-shmem credit,16GiB OS/GPU reserves, Qwen10% GPU comparison, OOM,
owned swap, storage and ownership checks remain. GLM480000 is provisional until
actual native allocation/cache/free-memory proof passes. Qwen must prove an
actual480000 pool and479994 input limit from scheduler metadata, independently
of configured arguments.

The closed sequence has five measured requests, no extras:

1. Load A's two models and perform one discarded80-record native-counted warmup
   per load:2048–4096 input tokens,32 output cap. Cheap before/after samples plus
   existing monitoring must prove positive same-identity process/cgroup CPU
   deltas and valid counters for all112 guest CPUs before long admission.
   Missing evidence stops with the exact saved UNAVAILABLE cause; no sleep or
   longer output is added to obtain samples.
2. Barrier-dispatch frozen GLM2028-record retrieval (historical input65008,
   schema/temp1/seed1729/low/max256) and one near480K Qwen retrieval/max256.
   Native counts bind the final body/template; output256 plus margin256 is
   reserved. Qwen's bounded fitting never silently downsizes the target.
3. Immediately after A's near-Q drains, run exactly one frozen common-input
   Q256K request in the same480000 pool, while the same GLM request is active
   when possible. Preserve actual peer condition and observed overlap. Its
   historical count was261622; a fresh leading nonce is natively recounted.
4. Drain, capture quiescent NUMA pages, retire A, then load/warm B and run one
   matched GLM/Q-near pair. B reuses A's Q logical fixture with a fresh prefix.
   No common-Q repetition, fillers, standalone ladders, tools or output512.

Strict retrieval and one-outer-fence semantic retrieval remain separate. Real
count/correctness/transport/resource/storage/ownership failures stop new cases;
a healthy admitted peer drains. GLM speed alone records/notifies and never aborts.

CPU evidence records process/cgroup time deltas, all guest per-vCPU counters,
average and p95 core-equivalents, own-cgroup quota/throttling, steal and CPU/memory/
IO PSI. Process stat also supplies runtime thread count. Timed sampling reads no
smaps, maps, per-thread inventory or NUMA; NUMA pages are boundary-only. Native
aggregate timing remains separate from worker output-event proxy phase windows.
Missing/disabled counters remain UNAVAILABLE; observed coverage, tick precision,
RPC clock uncertainty, collection overhead and short-decode p95 limitations stay
explicit. Utilization alone does not establish cores needed. The five-case
comparison reports observed paired timing and incomplete CPU evidence honestly.
The prior Q256K/700160-pool result is only a historical comparison; it cannot
attribute all near700K slowdown to allocation size.

Runtime retains original start1789899296.052823 (10:14:56.052823UTC). Root
authorized ONE internal extension because harness faults consumed the self-imposed
75-minute window before measurements: former4500 seconds / deadline1789903796.052823
(11:29:56.052823UTC), FINAL7200 seconds total / deadline1789906496.052823
(12:14:56.052823UTC). This is not user-requested, rolling or a reset. Loads, warmups
and counting remain inside the fixed window; canonical restoration remains outside.
Bound root GO names the same retained PREP/RUN session; the fresh campaign never
reuses failed predecessor ownership. Each request remains bounded by min(7200 seconds,
remaining window). Historical clocks, failures and ledgers are preserved. Saved planning: two GLM requests at prior935.4s each about31–32min,
four loads about7min, common Q about1.5min (now may overlap GLM). Allow roughly
40–55min with counting/overhead; changed pool/CPU effects are unmeasured.
Budget exhaustion records missing cases, without resetting or repeating.

`PYTHONPATH=scripts python3 -B -m benchmark.concurrent_cpu_run prepare
--task-dir "$TASK" --session-id "$PREP_SESSION"` is offline and requires a clean
source commit plus the task's immutable saved-evidence index and incoming file.
It preserves private frozen fixtures/proofs, INITIAL progress, control file,
protected-key metadata, arm, receipt and a non-authorizing GO template. No key
bytes are packaged. The exact full package is constructor/checkpoint/prepare-job
checked against a non-network stub before handoff. RUN verifies every required
file/hash, source commit, exact profiles/plan, same retained session and root GO before
staging. `run` and recovery-only `restore` take the same source-bound GO; there is
no generic resume/reset. A recovery-only outcome never upgrades measurements.

Canonical ownership records create intent before dispatch and retains uncertain
create identity on timeouts. Original QwenTP2/1M, boot/control/API state, locks,
credentials and tunnels restore through existing paths on exit. On
RECOVERY_REQUIRED, capture one safe fixed diagnostic and go once to fresh direct
canonical recover/finalize, with authenticated Worker1 LAN verification. Never
repeat a failed wrapper or invent a repair. Failed canonical recovery retains
its durable ledger/owning session for root; source checks are not restoration
acceptance.
