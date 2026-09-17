# D3CAP2 — native1M allocation observed; acceptance failed

**One allocation attempt, zero generations. Native startup eventually recorded
1,048,576 tokens and one slot, but this run did not pass capacity/sanity
acceptance.** The cheap sampler's inherited two-second timestamp predicate
failed during loading. The operator requested a canonical stop before startup
completed. No retry, tuning, fallback, tiny smoke or occupied-prefix work ran.

At release, the target and both retained rollback containers were stopped.
Manager state was reconciled to `desired:stopped`, `observed:stopped`,
`container_running:false`, `failure:null`, manual boot. Control remained
inactive/disabled. Sole request and canonical lifecycle ownership were released
at **2026-09-15 05:14:37.707115 UTC**; the last read-only report transfer ended
05:15:48.352810 UTC. D3CAP2 makes no later VM calls.

## Exact scope and admission

Actual Worker1 session on `mac-worker1.local`, checkout base
`dad2d58b57ab2367dee254cff1a885567b0c76f4`, branch
`milestone/d3cap2-native1m`. All VM operations used Worker1 SSH and isolated
`sudo -n /usr/bin/python3 -I -B`. No Worker2 request or additional Codex session.
Installer work remained stopped. The root-approved continuation followed the
ROOTSPACE release and D3PERFVM's explicit release; original D3CAP had used no
allocation allowance.

The exact installed 77-file D3N32 closure was verified in place, including both
N76 profiles, measured runtime/proof, Manager and guards. Its publication source
was `e8d8bbad3f2f6345295d440b25f084fed83dc734`. No source, closure, registry,
credential, network, unit, image or deployment configuration was republished.
Protected D1 rollback files were also verified. The model artifact check used
the existing Manager and sealed 11-shard GLM integrity contract; no weight
rehash, historical-model scan or download was performed.

| Protected item | Verified identity |
| --- | --- |
| Registered guard | `/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`; SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`; root0755 |
| Guard dependency | adjacent `scripts/install/storage.py`; SHA256 `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`; root0644 |
| Registry | `/etc/local-ai-server/storage.json`; protected ancestry and registered semantics |
| Data | `/data`, ext4, UUID `8daf56f1-5649-4163-9d87-919c2d271875` |
| Models | `/data/models-large`, ext4, UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` |
| Instance | `/data/services/llm-manager/deployment-instance.json`; SHA256 `afd1e6e07db92f4e7b6d713752a33b9886f516d57ac3153971310e72688ba2e6` |
| Source manifest | SHA256 `8fe8b5c32da9e212cae7e1d50751deec0d91c8aa1405a10e343fe21b33e712e0` |
| Native key | `/data/services/secrets/llm-api-key`, root0600; exact bytes and metadata compared privately and unchanged |

Both registered guard modes passed before and after operations. Initial root
free space was 5,208,215,552 bytes; final closure guard reported
5,208,219,648 bytes (4.85053 GiB). The below-6-GiB warning remained; the
4-GiB hard stop did not trigger. Reports reside under the new protected
`/data/logs/d3cap2-20260915`, root0700. No filesystem cleanup occurred.

Preparation corrections are retained. The report directory inherited setgid
from its parent; only this newly created task directory was set to the required
0700. First Manager preflight then refused `mount_source_missing_or_symlink`:
the three target-specific cache, log and service-data directories did not exist.
Under the canonical lease and registered `AnchoredRoot`, the operator created
only those exact empty profile-defined directories. No existing directory or
service configuration changed. Subsequent preflight passed while N76/32K was
still running. These were preparation commands, not allocation retries.

Admission revalidated old container/PID/start ticks/image, manual intent,
native loopback publication, key metadata and unchanged instance/state hashes.
Established API connections and D3PERFVM sampler processes were zero; the last
native release marker remained 04:32:15.806020433 UTC. Qwen fixture process
names were absent at admission and final checks. Those endpoint observations
do not establish absence throughout unobserved intervals.

## Runtime, model and container identity

| Item | Exact value |
| --- | --- |
| Target deployment | `glm-5.3-ud-q4-k-xl-n76-native1m` |
| Target profile SHA256 | `a15c41c0532f565720c0ead787e0b5ca0908b467e691d3bfad937c839243b47d` |
| Runtime | `llama-cpp-v0.4.1-d3br` |
| Image tag | `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d` |
| Docker image / OCI index | `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9` |
| Platform manifest | `sha256:384a22a0b15b9668b89e4ec46ed7363f2bb02e91d3344db102411288551ef62b` |
| Image config | `sha256:89a1ea2575d8a5ea2c2debd618d420ac03194b1c2d54b85972a8ebff850f3938` |
| Upstream source | `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Reviewed derived source tree | `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e` |
| Combined patch SHA256 | `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b` |
| Reviewed binary SHA256 | `c81262fd063e9d2fc098d9e116d0ae742ca7ea37344ee3f4b56eb5d088206e0a` |
| Target container | `3108f42bfaab08010164340b2c3e709e03c4aebeb36374e6b87d8bac226296fb` |
| Target process | PID 273833, start ticks 2728699; now absent |
| Docker start | `2026-09-15T05:09:31.919565878Z` |
| Retained N76/32K | `7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78`, stopped |
| Retained D1 | `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`, stopped; image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` |

Platform/config/source/binary rows above are the preserved D3RD measured proof,
bound by the verified installed hashes and current immutable image ID. D3CAP2
did not re-execute a binary measurement or rebuild the image.

Model: `unsloth/GLM-5.3-GGUF` at
`346b3591c7f28d1a23716f97a065ecf12ec14771`, UD-Q4_K_XL, 11 sealed shards.
Manager emitted the existing N76, GPU0/GPU1, split `1,1`, layer split,
ngl999, load mode `none`, one-slot contract; actual startup later reported
112 threads. Alias remained `glm-5.3`. Native host publication was
`127.0.0.1:30002`; the existing private proxy/configuration remained unchanged.
Docker restart stayed `no`, with no boot-intent or control activation.

## One transition and its failure

| UTC | Event |
| --- | --- |
| 05:07:55.537675 | Target Manager preflight passed; zero allocation attempts |
| 05:07:56.514357 | Admission complete; one idle full-PSS observation of old 32K |
| 05:09:01.187785 | Target preflight revalidated under canonical lease, owner PID 270294 |
| 05:09:28.901542 | N76/32K Docker finish; retained stopped |
| 05:09:30.290486 | ONE target start dispatched through Manager |
| 05:09:31.919566 | New container started |
| 05:09:32.387699 | First retained cheap sample |
| 05:10:29.347233 | Last retained cheap sample, index58 |
| 05:10:31.984352 | Remote sampler emitted `sample_gap`; signaled its own Manager supervisor |
| 05:10:32.271835 | Manager start failure recorded; controlled stop invoked |
| 05:11:41.679838 | Native complete graph/allocation diagnostic appeared after the stop request |
| 05:11:45.015116 | Native log initialized one slot with `n_ctx_slot=1048576` |
| 05:13:06.781397 | Docker ultimately exited, code137, `OOMKilled:false` |
| 05:13:34.372110 | Read-only reconciliation observed exit/PID0; Manager still held stale failed/running observation |
| 05:14:37.707115 | Existing Manager stop reconciled the already-exited owner; final guards and ownership release |

The first canonical stop used existing Manager's `docker stop --time 120`
with its 150-second command bound and returned `command_failed` (a nonzero
command exit, not the separate `command_timeout` error). At a bounded
intermediate read, PID 273833 was a zombie while Docker still reported running.
The later read observed exited/PID0. A final Manager `stop` found that exact
container already exited and only reconciled durable stopped state. No force
Docker operation, alternate argv, daemon restart, container deletion or second
allocation occurred. Exit137 alone is not an OOM diagnosis.

### What the sampler failure establishes

The task copied D3PERFVM's emitted cheap collector functions, retaining
identity, RSS/VmSwap, host counters, GPU, mount/root and numeric native/kernel
checks. The per-request D3PERFVM loop was adapted for the new target identity,
1M context and pre-readiness loading. It inherited the `(0, 2]` second
remote timestamp predicate and `<2s` collection-duration predicate. It was
not a reusable monitoring-source change or a D3MON implementation.

In the actual `monitor_load` thread on ai-vm, the timestamp assertion runs
**before appending and emitting the sample**. The worker controller only reads
JSON lines; it does not run health checks or determine sample gaps. Existing
Manager readiness polling runs in the remote main thread. Thus the failure
label comes from a remote sample predicate, not an elapsed time inferred from
the worker's log-drain timing.

All emitted sample indices 1–58 were drained and retained. The failing next
sample was rejected before append/emit, so its exact timestamp, contents and
individual command timing were not preserved. The failure event occurred
2.636999 seconds after the last accepted event; that interval is **not** the
missing sample's measured gap. No evidence identifies Docker inspection,
GPU query, health polling, process scheduling or transport as the blocking
cause. The task load loop also performs an outer `inspect_container` before
calling the cheap collector, which itself inspects Docker. This extra task-level
inspection is outside `_local_snapshot.sample_elapsed_seconds`; those duration
statistics cover the inner collector, not the full loop. Its presence is source
evidence of a possible uninstrumented delay point, not evidence that it blocked.
Accepted gaps were 0.952561–1.006790 seconds. This is a monitor-triggered
stop, not a demonstrated model-memory or context-capacity failure.

Root subsequently authorized a separate D3CAP3 with a loading-specific
10-second freshness/gap bound after this release. D3CAP2 made no such setting
change and did not retry. Original failed-run evidence remains intact.

## Measured memory and native capacity limits

| Measurement | Observed value / boundary |
| --- | --- |
| Old 32K idle RSS/PSS | 400.465214 / 400.465210 GiB; one pre-transition PSS read |
| Retained load samples | 58 over 56.959534 s, accepted cadence 1.000710 Hz |
| Cheap collection duration | median 39.687 ms, maximum 83.647 ms in retained samples |
| Largest sampled target RSS | 395.119652 GiB |
| Lowest sampled MemAvailable | 469.608109 GiB |
| Lowest sampled GPU free | CUDA0 85.223633 GiB; CUDA1 73.555664 GiB |
| Target VmSwap / host counter increments | zero in all 58 retained samples |
| Numeric CUDA/OOM/storage/runtime/fusion errors | zero in retained samples and bounded final native/kernel scan |
| Final host counter change from admission | pswpin+13, pswpout+3114, oom_kill+0; arose after the retained monitoring window |
| Final target PSS | unavailable: no accepted idle native1M readiness; target subsequently exited |

No PSS/smaps read occurred during load or a request. No request ran. No
post-readiness native1M full-PSS observation exists. The final host swap changes
are real, with no process attribution or timing inside the shutdown interval;
the retained zero-swap samples must not be extended across that gap. GPU free
after the late full allocation was not sampled under this monitor, so the
required >=16 GiB per GPU margin at full allocation is **not established**.

The bounded native startup log contains a complete `D3T_NATIVE_V1` block:
`n_ctx=1048576`, `n_ctx_seq=1048576`, `n_seq_max=1`, `n_batch=2048`,
`n_ubatch=512`, `flash_attn=1`, `fused_lid=1`, `lid_nodes=21`, `fa_nodes=78`,
`no_alloc=0`, followed by both CUDA compute/cache rows and `kind=end`.

| Native buffer | Exact allocated bytes | GiB |
| --- | ---: | ---: |
| CUDA0 cache | 51,539,607,552 | 48 |
| CUDA1 cache | 48,318,382,080 | 45 |
| CUDA0 compute | 5,104,543,744 | 4.753977 |
| CUDA1 compute | 4,680,849,408 | 4.359381 |
| CUDA_Host compute | 2,172,727,328 | 2.023510 |

These are observed reserved-graph selection and actual allocation diagnostics,
not a full GPU profiler result. The later slot log also explicitly reported
1,048,576 capacity. The earlier conservative `actual_capacity:NOT_ESTABLISHED`
string in the intermediate reconciliation JSON is superseded by these parsed
facts and `closure-result.json`; accepted readiness remains unestablished.

**Actual K/V F16 dtype was not established:** the retained bounded native log
had no explicit F16 dtype record. The reviewed F16 expectation and 48/45GiB
cache arithmetic cannot substitute for an actual dtype observation. Manager
health/models acceptance and tiny ordinary sanity did not complete because
the stop preceded native startup completion. No completion or prompt token
counts exist: zero generation calls. Near1M occupation remains `NOT_TESTED`;
`highest_proven_window` does not advance.

## Recovery, release and remaining gates

No rollback was invoked. Both previous profiles, containers, images and source
evidence are retained. The existing reviewed rollback procedure remains the
[retained D3N32 rollback command](d3cap2-evidence/rollback-reference-d3n32.txt): acquire canonical lease, validate current
immutable owner and desired stopped state, prepare/validate the retained
rollback profile, then Manager stop/select/start. D3CAP2's changed current
owner is the exact native1M container above. Reusing N76/32K uses the installed
config root and `glm-5.3-ud-q4-k-xl-n76-32k`; D1 uses
`/data/services/llm-manager/d3n32-20260915/rollback/configs` and
`glm-5.3-ud-q4-k-xl-32k`. These are preserved recovery references, not an
automatic fallback instruction or authorization to start here.

Final guards passed, key exact bytes/metadata and protected stable files
matched admission, all 77 source hashes/modes remained unchanged, control
was inactive/disabled, and API connections were zero. Native PID 273833 and
transition PID 270294 were absent. The existing worker request lock was free;
no owned request, sampler or tunnel remained. See
[explicit lease release](d3cap2-evidence/lease-release.md) and
[final closure](d3cap2-evidence/closure-result.json).

Next decisions belong to root. Capacity acceptance still needs reliable load
monitoring, fresh safety at full allocation, explicit dtype evidence, accepted
idle health/PSS and ordinary sanity. Occupancy awaits corrected D3MON review.
Independent clients, model switching/catalog, boot/manual-intent acceptance
and the separate frontend remain outside this run. Installer remains paused.

## Evidence and verification

Selected reports were transferred from the root0700 VM task directory and
SHA256-checked. `report-transfer.json` records original bytes; committed JSON
is normalized with GPU UUID fields removed. `SHA256SUMS` covers the normalized
report evidence. Raw key/body/prompt/response data is excluded from Git.
The private baseline key comparison never left ai-vm.

Verification comprised exact base/source hashes and modes, existing Manager
preflight/dispatch, canonical storage/lease checks, actual cheap load samples,
bounded native diagnostics, failure reconciliation and final ownership checks.
No full repository, installer, model-performance or framework test suite ran.
The report-only commit, author/committer, bundle verification, quiet secret
scan and clean-tree result are recorded in the task's external `../final.md`.
