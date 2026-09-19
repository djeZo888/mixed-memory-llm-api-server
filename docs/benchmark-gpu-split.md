# Temporary GPU split benchmark — BENCHPREP authority

The user explicitly approved this experiment on 2026-09-19. The task authority
is `../APPROVED-PLAN.md` and `../CURRENT-HANDOFF.md` in task
`BENCHPREP-20260919`; source baseline is
`748e8657251de30662937cb4b5a294202ecb90b7`. This document records that approval
so the older one-active-backend milestone does not prevent the bounded dual
benchmark. Production remains one selected backend. Installer and frontend work
remain outside scope. No new weights, runtime image, cache quantization, host
NUMA claim, Proxmox change, boot preference change or production redesign.

BENCHPREP implements/offline-tests source, captures a read-only baseline, commits
a feature branch and delivers a bundle. It must not deploy, stop/start services,
acquire the VM lifecycle lease, create containers, run inference, load models or
execute the campaign. Root reviews PREP and dispatches a fresh BENCHRUN owner;
BENCHVERIFY is a further fresh independent review. No contact with worker2 from
PREP. Source tests and saved production observations are not live acceptance.

## Offline preparation

```sh
python3 scripts/bench/prepare-gpu-split.py --output ..
python3 -m unittest discover -s tests -p 'test_benchmark_*.py' -v
git diff --check
```

The preparation CLI only writes worker-local artifacts: twelve exact command
manifests, trial order and six private raw serialization samples plus separate
scorers. Raw fixtures stay outside Git, mode 0600 inside a 0700 directory.
Commands in `command-manifest.json` are data for review, not a RUN permission or
shell script. Source modules import without starting requests or workloads.

`configs/benchmarks/gpu-split-20260919.json` pins unchanged production model,
runtime and authentication source declarations, observed GPU UUIDs, registered
UUIDs and the installed guard/source hashes. Refresh those facts before RUN;
do not use a stale helper path if identity differs. No production declaration or
production auth file is modified by this experiment.

## Placements and actual proof

| Placement | Visible guest GPU UUIDs | Native allocation request |
| --- | --- | --- |
| G2 | both configured UUIDs | N76, layer split 1,1, CUDA0,CUDA1 |
| G1 | first configured UUID only | N76, split none, CUDA0/main-gpu 0 |
| Q2 | both configured UUIDs | TP2, local base-gpu 0, step 1 |
| Q1 | second configured UUID only | TP1, local base-gpu 0, step 1 |

Context/pool capacities are 4096, 16384 and 65536. GLM changes `--ctx-size`;
Qwen changes both `--context-length` and `--max-total-tokens`. Optional 131072
is disabled in launch generation until a root decision and source review.
N76 stays fixed. GLM uses observed production load-mode `none`, F16 cache,
batch 2048/ubatch 512, threads 96 for prefill/decode and fit off. Explicit fixed
threads, no-cache-prompt and fit-off prevent varying placement or cache reuse
from confounding the ladder; these explicit flags differ from production
defaults and are recorded. Qwen retains FP8 weights, BF16 cache/compute,
factor4 YaRN, no-thinking, one slot, disabled radix/graphs and existing pinned
execution settings across all capacities and placements.

The benchmark Qwen launcher is a small process-local adapter over the exact
unchanged production file-auth source hash. It validates each changed tuple
(context/pool/TP/alias/port) then reuses all remaining native raw/resolved mode,
auth, environment, alias and warmup checks. It mounts only in benchmark
containers. Its Python synthetic tests are not actual-image acceptance:
BENCHRUN must first verify this adapter through the pinned native preparation,
resolution, middleware and spawn path without model loading, before live use.
No fallback to an unauthenticated stock launcher is permitted.

All Docker host publications are IPv4 loopback: 31002 for GLM and 31004 for
Qwen, aliases `bench-glm-5.3` and `bench-qwen3.8-27b`. Credentials remain the
existing protected file mount. Access from the worker uses the reviewed SSH
private transport, for example explicit local forwards
`-L 127.0.0.1:31002:127.0.0.1:31002 -L 127.0.0.1:31004:127.0.0.1:31004`
with `ExitOnForwardFailure=yes`. There is no new wildcard/IPv6/LAN exposure,
firewall change or TLS policy. Native container bind is its private bridge
interface, as in the existing deployment; host listeners stay authenticated
IPv4 loopback. Do not copy protected keys into command lines or source files.

GPU indices in the visible namespace are only launch requests. On RUN verify
Docker UUID DeviceRequests, native device UUID mapping and process allocation
from logs and observations, actual N76 offload/TP, cache types, exact model
revision/load path, configured context/pool and cache/workspace allocations.
Require at least 16 GiB free reserve on every used GPU; missing proof is a skip
or harness issue, never a successful placement. The isolated G1 fit is unknown.

## Fixtures, timings and telemetry

`fixtures.py` keeps expected retrieval answers in scorer data and only their
correct archive rows in the outgoing prompt. Exact outgoing bytes are checked
by regenerating the fixture and checking contamination. Every placement of a
model reuses the same seed, record count and kind; only the leading nonce changes
for uncached trials. Recount the new nonce and retain hashes. If token fitting
chooses a different record count, do not silently call it a matched fixture:
freeze the first safe count across that model's placements and verify each exact
body remains within the target tolerance. Prefix/template overlap and any
reported cached tokens remain visible; do not relabel cached work as evaluated.

`accounting.native_counter` uses GLM `/props`, `/apply-template`, `/tokenize`,
or Qwen `/v1/tokenize` with full chat/tool options. Bind calls to protected
current runtime identity. Qwen additionally needs the loaded template digest;
the counting route does not prove that digest. Record body/template/token-ID
hashes and actual token counts. Fit near capacity minus output cap and 256-token
extra headroom (tool rounds also reserve 1024). Tool continuation preserves the
actual call ID, reads a real fixed-path file in an ordinary-user trusted
workspace, appends its result and recounts the complete continuation body.

Warm every new loaded configuration and discard warmup timing. Run the 256
output-cap retrieval ladder, repeat the 16K anchor, and separately run 16K
512-output generation and real tool continuation. Length termination is an
output-budget observation, not a correctness regression; malformed framing is
a harness failure. Validate scoring only after valid parsing. No blind retries.
The client drains healthy requests if its observer/report parser fails, then
persists private raw request/response and allowlisted hashes/counters/timings.
Client TTFT distinguishes content, reasoning and tool deltas; role-only chunks
do not count. Native counters/timings retain their native provenance. Missing
native prefill/decode/workspace information stays unavailable; no invented TPS.

During timed requests use `telemetry.sample_series` at approximately one second:
host MemAvailable/swap/page faults, cgroup current/peak/anon/file/swap/OOM and
optional known-process VmRSS, per-GPU memory/utilization/power by UUID. Cgroup
v2 has no true RSS metric: its absence is null; summed process RSS may double
count shared pages. Report sampled peak separately from kernel lifetime peak,
sampling gaps, coverage and collection overhead. Model swap growth needs a fresh
owned-cgroup baseline; host swap alone does not establish model swapping.

**Never sample full smaps/PSS at 1 Hz or during timed GLM decode.** Full PSS may
be obtained once per verified quiescent readiness and warm-idle point using
`/proc/<verified-owned-pid>/smaps_rollup`; record time and owner/PID generation,
then stop that observer before requests. If unavailable, retain null. Existing
heavy full-PSS monitoring disrupted GLM, so this is a measurement constraint.

## Six-hour campaign and mixed schedule

Persist `CampaignBudget.start('maintenance')` immediately before first actual
maintenance (or `model_trial` if earlier). Six hours includes configuration
loads, warmups, requests and switches. Each request has an absolute deadline at
most 7200 seconds and at most the remaining budget. Restoration is outside that
budget and cannot reopen measurements. `/data` ledgers require explicit anchored
read/write callbacks plus installed before/after guards; no root-disk fallback.

Proposed order: Q2 ladder, Q1 ladder, G2 ladder, G1 ladder; repeat/generation/tool
cases while each 16K configuration remains loaded. Then mixed A and B if budget
and measured reserve allow. This is a prioritized order, not a promise every
trial fits six hours. Update estimated remaining cost after each observed
load/prefill. Skip later trials explicitly when unsafe or out of budget; reserve
no restoration time inside the budget. Larger-case repeats only resolve an
instability or close ranking. Allocation-only checks are optional and separately
labeled; do not extrapolate speed or quality.

Use identical arrivals and fixtures in A/B: initially all five arrivals at t=0,
one approximately 64K GLM request and four approximately 16K Qwen requests.
`workload.execute_mixed` actually dispatches A's four serial Qwen jobs followed
by a measured owner-mediated switch to GLM, or B's GLM alongside one serial
Qwen lane. It waits for healthy in-flight work on an error in the other lane.
Callbacks must return scored PASS for correctness acceptance. Report initial
readiness/load separately, actual per-job service/queue/latency, makespan,
switch duration, per-model interference and memory. Returning to original
production is timed separately. Never sum unlike models' token rates.

Mixed B exposes disjoint UUIDs and guest CPU sets GLM 0-95 (96), Qwen 96-111
(16), respecting the observed seven guest NUMA nodes of 16 CPUs. This is not
evidence about host NUMA. Generate B manifests only after measured isolated
cgroup demand is known; `split_resources` applies 25% headroom and checks host
headroom. Set memory and memory-swap equal to cap to prevent new container swap.
Do not invent caps from weight file sizes. Memory projections separate weights,
cache, runtime, workspace and GPU reserve. GLM 95232 and Qwen 65536 aggregate
bytes/configured token are hypotheses; compare actual allocations before using
128K/256K/512K/published-max projections. Per-GPU fit and workspace scaling stay
unproven until observed. No extrapolated throughput/correctness.

## Exclusive ownership, maintenance and rollback

Review `lifecycle.plan_campaign(snapshot, campaign)` plus exact command hashes
before mutation. `owner.CampaignOwner` is an explicit same-process owner with
injected host adapters; it is not an autonomous RUN command. Bind adapters to
the current protected installed Manager/source and canonical lease module,
guard, registered anchored writer, exact Docker IDs and authenticated worker
clients. No no-op gates or synthetic evidence in RUN. `HostCallbacks` defines
the narrow required host operations. RUN writes a reviewed task-local adapter;
it must not replace production source or weaken production profile validators.

1. Acquire the existing `/run/llmctl/lifecycle.lock` nonblocking once. Capture a
   complete protected snapshot under that lease: original selected/desired/ready
   and boot policy, control operations and request quiescence, exact service
   enabled/active/unit identities, registered storage/guard/source identities,
   credential metadata plus private equality witness and no pending systemd
   jobs. The PREP compact baseline is insufficient for this restoration record.
2. Persist snapshot/manifest/budget using guarded anchored logs. Stop only
   `llm-control.service` and verify no control process. Keep
   `llmctl-boot.service` active/exited unchanged: its ExecStop reacquires the
   lease, so stopping that unit while holding the campaign lease can deadlock.
3. Call `manager.dispatch('boot-stop', lease=owner.lease)` in the same process.
   This preserves selected/desired/boot intent while stopping production.
   Subprocess `llmctl` would reacquire the lease and must not be nested. Verify
   quiescent production and only then admit exact benchmark manifests. The
   lease prevents control/boot reconciliation while the owner is active.
4. Record planned create before Docker creation and inspected full ID before
   start. Root-reviewed source identities, storage guards, protected ancestry,
   lease validation and phase gates surround every operation. AI writes and
   caches stay under registered `/data`; preserve D1 rollback and images.
5. Stop on unsafe placement, allocation failure, sustained owned-model swap
   growth, OOM or genuine correctness regression. A parser/report failure is
   HARNESS_FAILURE. The owner has no context-manager cleanup that could stop a
   healthy model when a reporter throws. Finish or explicitly cancel requests
   under campaign ownership before retirement/restoration.

Explicit rollback is `owner.restore()` after quiescence, regardless of remaining
budget. It stops/removes only full IDs from the owned durable ledger, verifies
absence, calls `manager.dispatch('boot-stop', lease=lease)`, then selects the
**captured original deployment** with its captured boot preference and starts
only when original desired was running. Original empty/stopped states stay
empty/stopped. Original service enablement and boot unit are unchanged. Verify
selected/ready intent, source/storage/credential equality and no benchmark
processes/listeners before release; release the same lease; start control only
if originally active; verify authenticated LAN control/inference from worker
and exact service states afterward. A stopped original does not authorize a
restoration inference request; record that as not applicable.

On ambiguous interrupted create, reconcile its exact planned name/image/labels
and full ID before any cleanup; no broad Docker prune. On restoration refusal,
retain the owner/lease and RECOVERY_REQUIRED record for scoped recovery. If the
supervisor dies, the OS lock ends: a fresh owner must reacquire the canonical
lease, read protected ledger, establish exact IDs/current safety and restore;
never treat a missing process as evidence that restoration succeeded. Do not
enable/reconfigure boot units or rotate keys to recover this benchmark.

All live placement, actual-image adapter, occupied-context, speed, mixed-run and
restoration acceptance remains **NOT_TESTED in BENCHPREP**. The task-root READY
handoff carries the exact commit, bundle digest, baseline, tests and next root
review action; those are the preparation deliverables, not a live result.
