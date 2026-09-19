# Temporary GPU split benchmark — BENCHPREP authority

## BENCHG1 observational logging repair — 2026-09-19

The first4K attempt stopped before warmup because its native log omitted weight
and offload records; its valid cache/graph allocation is not model failure.
Original production restoration passed. The pinned callback maps library INFO
to verbosity4 while default3 still prints server INFO. G1-only now adds exactly
`--log-verbosity 4` at all three sizes; historical scopes/default manifests stay
unchanged. See `reports/benchg1-logging-source.json`. No model, tensor/cache,
image, reasoning/batch or gate changes. Root reviews exact repair source/arm
before a new attempt; preserve failed journals and the original epoch/deadline.

## BENCHG1 source preparation — 2026-09-19

`arm --scope g1-only` continues the original campaign with the unchanged G1
manifests at 4096, 16384 and 65536: first GPU UUID, 96 guest CPUs, N76, F16,
load-mode none, fit off, fixed batch/reasoning/runtime. Exactly three discarded
warmups and five measured cases: 256-output retrieval at each capacity, plus
16K anchor repeat and separate 512-output generation. No tool, mixed, Qwen,
G2 or larger-context dispatch. Prior fixture entries and outcomes stay immutable;
only new GLM fixtures are fitted. Explicit `--resume` retains epoch
1789826207.34127 and deadline 1789847807.34127; restoration is outside budget.

The existing GLM offload gate remains active. G1-only additionally requires
native CUDA0 cache bytes to equal 95232 times configured capacity and 78 main /
21 indexer graph nodes. Saved historical GLM timing fields support native warmup
proof; missing current evaluated/cache proof still refuses warmup. No Qwen
cache-policy derivation is applied to GLM. Fresh recovery captures the current
canonical lock before restoration callbacks check the preserved witness.

During G1 requests, proven OOM, sustained owned-model swap growth, or numeric
GPU/host reserve violations set a cancellation event. The HTTP transport closes
the socket within its 250 ms polling interval after the event, retains received
partial bytes, then releases request admission before the existing owned stop
and restoration path. Detection latency also includes the approximately 1 s
telemetry interval and collection delay. Missing telemetry or parser/reporting
errors do not cancel a healthy request; they prevent subsequent admission.
No immediate kernel-level cancellation or complete response is claimed.

Source preparation is offline; root reviews the exact source, arm and guarded
old-to-new staging package before VM contact. GLM memory-only projections retain
at least 16 GiB GPU reserve and 25% host-demand reserve, with verified measured
components/slopes required; untested speed/quality remain unknown.

## BENCHQ256 source preparation — 2026-09-19

The fresh BENCHQ256 task adds only `arm --scope q1-256k`: one single-GPU Q1
manifest with context and native pool both 262144, one discarded accepted warmup,
and one early/middle/late archive retrieval with a 256-token output cap. Native
fitting targets 261504–261632 actual input tokens; configured capacity is reported
separately. The pinned FP8 weights, BF16 KV, YaRN factor 4, assigned GPU UUID,
16 guest CPUs and `mem_fraction_static=0.8` remain unchanged. Historical `full`
and `q1-only` plans remain unchanged; no 128K, 512K, Q2, GLM, tool, generation or
mixed dispatch is added to this arm.

Retain `benchrun-20260919`, epoch `1789826207.34127`, deadline `1789847807.34127`
and explicit `run --resume`. Previous evidence stays immutable and separate;
fit only the new 262144 fixture after exact root source/arm GO. No live contact
is authorized during source preparation. Restoration uses the existing reviewed
owner/witness/canonical-lease callbacks; fresh-process recovery first initializes
its lock baseline through direct capture. Source tests prove no live result.
A successful result may inform an untested physical-memory projection using a
10% device reserve, separately from the unchanged 80% static allocator policy
and existing live safety gates. No speed/quality claim follows at untested sizes.

## BENCHQ1 source preparation — 2026-09-19

The fresh BENCHQ1 task narrows continuation to `arm --scope q1-only`: Q1 at
4096/16384/65536, retrieval at each capacity, repeated 16K retrieval and separate
16K generation with a 512-token output cap. Each load retains discarded warmup.
The runner and host validate exactly three unchanged Q1 manifests; no tool,
mixed, Q2 or GLM dispatch is included. Omitted scope retains historical full
behavior. Q1 requires the existing execution epoch and explicit `run --resume`;
failed/inflight measurements still stop and require review.

Keep campaign `benchrun-20260919`, first epoch `1789826207.34127` and deadline
`1789847807.34127`. Reuse the supplied frozen 4K/16K fixtures with fresh prefixes
and native recount; only 64K is newly fitted. Saved Q2 64K is unavailable.
Archive-commentary generation does not establish code-analysis coverage.
Prior Q2 PASS rows and the terminal tool failure remain immutable in BENCHRUN;
BENCHQ1 has separate truthful progress referencing that evidence. Root reviews
the source, candidate arm and guarded stage-update proposal before live work.
Source/offline checks establish no new allocation, inference or restoration proof.

## Historical full-campaign authority

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
batch 2048/ubatch 512, G2 threads/threads-batch 112 and G1 96, and fit off.
G2/Q2 get all 112 guest CPUs; isolated G1 uses 0-95 and isolated Q1
96-111, exactly matching mixed B. The CPU allocation differs between one-
and two-GPU results and is recorded in every command manifest. Explicit fixed
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
resolution, middleware and spawn path without model loading, before live use. The worker offline suite exercises the actual shipped wrapper
main, native argv/environment, alias rejection, tuple/pool checks and middleware
missing/wrong/correct authentication using synthetic native seams.
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
the counting route does not prove that digest. Qwen max_model_len is retained
as tokenizer metadata (representative pinned value 262144); it need not equal
the smaller configured pool. Actual runtime allocation is the capacity gate. Record body/template/token-ID
hashes and actual token counts. Fit near capacity minus output cap and 256-token
extra headroom (tool rounds also reserve 1024). Tool continuation preserves the
actual call ID, reads a real fixed-path file in an ordinary-user trusted
workspace, appends its result and recounts the complete continuation body.

Warm every new loaded configuration with a distinct prefix and native-counted
2304–2432 input tokens. Require a successful parsed inference with positive
output and at least2048 proven prefill tokens (native evaluated count, prompt
minus explicitly reported cache, or the validated Qwen cache-disabled derivation
described below); discard warmup timing. Missing
evaluation proof stops the harness. This exercises the configured2048-token
prefill chunk/batch. Run the 256
output-cap retrieval ladder, repeat the 16K anchor, and separately run 16K
512-output generation and real tool continuation. Length termination is an
output-budget observation, not a correctness regression; malformed framing is
a harness failure. Validate scoring only after valid parsing. No blind retries.
The client drains healthy requests if its observer/report parser fails, then
persists private raw request/response and allowlisted hashes/counters/timings.
Client TTFT distinguishes content, reasoning and tool deltas; role-only chunks
do not count. Native counters/timings retain their native provenance. Missing
native prefill/decode/workspace information stays unavailable; no invented TPS.

During timed requests the integrated runner samples at approximately one second:
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

Before starting either arrival clock, fit/freeze and native-count all five exact
workload fixtures. A prepares GLM first, retires it, then prepares Qwen; its
subsequent switch reloads/warms GLM and verifies the same template identity. B
prepares both ready models before dispatch. Fitting/counting durations are
reported separately; A switch includes reload plus discarded warmup, as labeled.
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
required RAM components are known; `split_resources` applies 25% headroom to
measured anon + kernel + necessary resident file-backed weights/pages + any
workspace not already in anon. CUDA_Host workspace is reported separately and
not double-counted. Mapped file pages/shmem remain conservatively retained;
unmapped reclaimable model-file cache is separate. GLM nonmapped CPU weight
allocation and load-mode none are required to justify its anonymous weight basis.
Raw memory.current/peak is never multiplied blindly. Fresh MemAvailable is
sampled only after previous owned containers retire; proposed caps still need
actual future load validation. Set memory and memory-swap equal to cap to prevent new container swap.
Do not invent caps from weight file sizes. Memory projections separate weights,
cache, runtime, workspace and GPU reserve. GLM 95232 and Qwen 65536 aggregate
bytes/configured token are hypotheses; compare actual allocations before using
128K/256K/512K/published-max projections. Per-GPU fit and workspace scaling stay
unproven until observed. No extrapolated throughput/correctness.

## Exclusive ownership, maintenance and rollback

Review `lifecycle.plan_campaign(snapshot, campaign)` plus exact command hashes
before mutation. `scripts/bench/run-gpu-split.py` is the deterministic worker
entry. Its persistent SSH endpoint `benchmark-host.py` uses `LinuxHost` and the
protected installed Manager/lease in the same process, with registered anchored
writers, exact container IDs, allocation checks and request admission. No adapter
implementation is deferred to RUN. No production source is replaced.

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


## Executable arm, run and explicit recovery

The root-reviewed worker executes as an ordinary user. `arm` is offline and
binds a closed source inventory plus twelve exact serialized manifests. It
refuses overwriting an existing campaign. Root reviews its emitted SHA256.
These are future BENCHRUN commands; PREP executes only arm/help/tests.

```sh
python3 scripts/bench/run-gpu-split.py arm --state ../campaign-arm --campaign benchrun-20260919
python3 scripts/bench/run-gpu-split.py status --state ../campaign-arm
python3 scripts/bench/run-gpu-split.py run --state ../campaign-arm --reviewed-arm-sha256 ARM_SHA256 --inference-key-file PROTECTED_WORKER_INFERENCE_KEY_PATH --control-key-file PROTECTED_WORKER_CONTROL_KEY_PATH
python3 scripts/bench/run-gpu-split.py restore --state ../campaign-arm --reviewed-arm-sha256 ARM_SHA256 --inference-key-file PROTECTED_WORKER_INFERENCE_KEY_PATH --control-key-file PROTECTED_WORKER_CONTROL_KEY_PATH
```

The two key paths must be existing protected worker clients' files, supplied by
root; key values never enter argv, environment, source or reports. `run` stages
the reviewed source under `/data/services/benchrun-20260919/source` using installed
anchored writers and the canonical lease, then starts the exclusive host owner.
First-stage UTC epoch is durably saved before staging in `execution.json`; it
bounds the six-hour campaign. Shared admission is serialized before each count,
warmup, generation and continuation request. Per-request deadlines are <=7200s.

Worker state automatically writes `progress.json`, `results.jsonl`, `samples.jsonl`,
`warmups.jsonl`, `execution.json`; private raw requests/replies, frozen fixtures
and ordinary-user tool workspaces live under `private/` (0700/0600). Host ownership,
snapshot, first-epoch budget, allocation receipts/private logs, mixed measured
caps and restoration challenge live under `/data/logs/benchrun-20260919/`.
Sources are separate under the registered service root; nothing goes to root-disk
AI output. The source manifest is shareable; raw artifacts remain private.

GLM CUDA mapping uses the existing native `llama-server --list-devices`, explicit
ordered CUDA_VISIBLE_DEVICES UUIDs and container-visible nvidia-smi UUIDs. It
does not invoke Python inside the GLM image. Exact-image no-GPU helper probes
under canonical ownership establish helper availability before production stop;
no installation or image change. Qwen retains its existing Python driver query.
Exited/dead/OOM containers fail promptly with bounded private diagnostics. Load
and readiness subprocess/HTTP deadlines are bounded by the remaining campaign
budget; restoration stays outside those deadlines.

On a trial/report/pressure failure, complete healthy registered requests, stop
new admission, and restore the exact captured original intent outside the
budget. Local restoration ends in POST_RELEASE_LAN_VERIFICATION_PENDING; the
worker proves authenticated direct private-LAN control and inference (only if
originally running), then submits the fresh challenge-bound receipt to finalize.
A measurement error still runs these checks and exits nonzero after restoration.
`restore` reacquires the canonical owner from its protected exact-ID ledger;
it does no measurements. It refuses ambiguity and active inference. Never
manually start production alongside an unresolved benchmark owner.

Explicit `run --resume` is only allowed after verified restoration and within
the original budget. Completed measurements are skipped; an inflight marker
requires restoration/review and is never retried automatically. An interrupted
mixed schedule is not a fresh comparable makespan: its partial per-job records
remain evidence; root must decide whether a separate newly armed campaign is
needed. The runner never resets the budget or blindly repeats failed trials.
All installed Linux command/native-image/allocation and recovery behavior still
requires the fresh RUN session; mocked tests establish source behavior only.


## Final receipt correction and resolved source expectation

Historical baseline lease inode is **2132**, as recorded in task-root
`baseline.json` and `baseline-summary.md`; earlier2207 text was incorrect.
Future RUN establishes fresh identity under the canonical lease.

Bounded read-only pinned-source inspection resolved the exact GLM log semantics.
`src/llama-model.cpp` at b29c606e28a01b1bc8c1351026a0fa6e616bf6c4,
SHA256 dc852c79709927631135ff9482e7fa7597d9b975a1867eb49003c14f93594ad3,
lines1412 and1818–1821 defines denominator n_layer_all+1 and numerator
min(n_gpu_layers,n_layer_all+1). Retained model metadata has79 blocks; the
reviewed argument is999, so the required log is **80/80**. This is derived from
the exact formatter, not inferred from placement slots. Sanitized source/identity
receipt: `reports/benchprep-glm-offload-source.json`. Current build-source bytes
match the pinned blob and previously retained source hash; the receipt records
that the build checkout is user-owned, not an immutable production authority.
RUN still requires actual current-load 80/80, N76 arguments, CPU/GPU buffers,
cache/context/UUID/reserve proof. Source arithmetic establishes no live allocation.
The preflight refuses missing or unreviewed count evidence before staging.

Cheap memory sampling begins immediately after Docker start and before readiness
HTTP, then continues through load/warmup/timed work. The durable host peak includes
transient loader anon/kernel/mapped-file demand. Load sample count/span and
sampled-peak limitations remain explicit; this is not an absolute transient peak.
Mixed admission rejects missing load-phase evidence, includes required demand
plus25%, and samples usable host capacity after prior owned instances retire.
Its generated commands, component evidence and usable capacity are also emitted
to worker `results.jsonl` for root synchronization. No proposed cap is called
accepted until the future capped load succeeds.

Root monitors/synchronizes only worker-local `campaign-arm/progress.json`,
`results.jsonl`, `samples.jsonl` and `warmups.jsonl`; private raw evidence stays
on the worker. The future RUN session remains attached until an actual handled
failure/completion checkpoint. Progress includes group PREPARING/DISPATCHING,
explicit MISSING measurements on interruption, terminal outcome and required
RAM evidence. No automatic replay of failed or interrupted groups is allowed.


## Final warmup and request-window correction

Pinned Qwen source emits `usage.prompt_tokens_details: null` when cache reporting
is disabled; its benchmark wrapper does not enable that report. Warmup accepts
an explicit `derived_cache_disabled_prompt_tokens` proof only with successful
positive-output inference, >=2048 native prompt tokens, accepted current allocation,
exact observed native argv including `--disable-radix-cache`, and current server
args confirming that flag is true. Fresh warmup prefixes remain required. Native
cached/evaluated counters stay null when absent; the separate `prefill_proof`
records the derivation and argv hash. Missing runtime policy evidence fails the
harness. Source path/hash receipt: `reports/benchprep-qwen-warmup-source.json`.
This proves source semantics, not a live warmup result.

Each sample persists worker-monotonic transport dispatch/drain boundaries before
post-drain parsing and reporting. Trial telemetry uses only that interval for
sampled request memory peaks, fault deltas and coverage. Tool continuation has
its own interval and telemetry; fitting/counting telemetry is recorded separately
under fixture preparation. `client_total_seconds` retains its explicit trial
orchestration scope. Cgroup lifetime peak counters remain labeled lifetime, never
an absolute request peak. Load/readiness/warm-idle sampling, mixed fixture fitting
before arrival timing, and healthy-stream drain on parser/report errors remain.
