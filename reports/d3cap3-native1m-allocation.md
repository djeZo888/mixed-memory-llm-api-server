# D3CAP3 — unchanged native1M restart stopped on new host swap

**FAIL_NEW_HOST_SWAP_DURING_LOADING. One allocation restart attempted; zero generations. Ownership released.**

The corrected loading monitor observed new host swap activity, so the authorized
single attempt stopped. No native1M capacity, idle readiness, effective allocated
F16 cache, fused graph, or smoke was accepted. Host swap cause is unknown;
this result is not a model-OOM diagnosis.

## Measured outcome

| Observation | Result |
| --- | --- |
| Fresh admission counters pswpin / pswpout / oom_kill | 19063 / 38936 / 0 |
| First rejected sample and final counters | 19064 / 39034 / 0 |
| New counter deltas | **+1 / +98 / +0** |
| First safety failure | 2026-09-15T05:27:36.253778Z; after 15 retained safe samples |
| Target at rejected sample | running, PID288305; VmSwap0; OOMKilledfalse |
| RSS / MemAvailable | 102.708 / 763.886 GiB |
| GPU0 / GPU1 free | 85.224 / 73.556 GiB |
| Numeric CUDA / OOM / runtime / storage / fusion errors | all zero in retained/rejected samples and final current-lifetime logs/kernel checks |
| Final target | exited137, OOMKilledfalse; PID0 |
| Final selected / desired / observed / policy | native1M / stopped / stopped / manual; failure null |
| Readiness, idle PSS, smoke, occupied prefix | NOT_ACCEPTED / NOT_MEASURED / NOT_RUN / NOT_TESTED |

The fresh rejected observation and all its metric-call timings are retained in
[first-transition-failure.json](d3cap3-evidence/first-transition-failure.json).
There were no further counter increments between that row and final inspection.
Target VmSwap0 and host oom_kill0 do not identify the process responsible for
host swap. No waiver, fallback, tuning, second allocation, or rollback occurred.

The Manager recorded `auth_error` after the asynchronous safety signal. Its
pinned `runtime_io.probe` catches `LifecycleError` and returns `auth_error`; the
task signal handler raises that exception. The ordering is consistent with this
mapping. No HTTP response status was retained to establish an independent auth
failure. Protected key bytes and metadata remained identical.

The first bounded Manager stop returned `LifecycleError` without a retained
specific code. Target `FinishedAt` was **2026-09-15T05:30:11.291780286Z**.
A later exact read confirmed exit; existing Manager.stop then reconciled stale
state without starting or signaling the already-exited container. Exit137 does
not establish OOM. Original stop failure evidence is preserved.

## Exact identity and unchanged contract

- Base: `dad2d58b57ab2367dee254cff1a885567b0c76f4`; branch `milestone/d3cap3-native1m`.
- Profile: `glm-5.3-ud-q4-k-xl-n76-native1m`; model GLM5.3 UD-Q4_K_XL, sealed 11-shard registration.
- Runtime: `llama-cpp-v0.4.1-d3br`; tag `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d`.
- Image/index: `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9`.
- Reused target: `3108f42bfaab08010164340b2c3e709e03c4aebeb36374e6b87d8bac226296fb`.
- CAP3 start: `2026-09-15T05:27:20.440229039Z`; PID288305/startticks2835552; restart_count0.
- Transition owner286271 and target288305 are absent at release.
- Protected actual Docker argv: context1048576, parallel1, N76, ngl999, layer split1,1,
  devicesCUDA0,CUDA1, load-mode none, aliasglm-5.3, clear_thinking true, key-file path only.
  Exact args are in admission.json and the final container record. No dtype CLI or
  container-environment override was present. Live PID argv/environment/binary
  checks planned for readiness were **not reached**.
- N76/32K `7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78`
  and D1 `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`
  remain stopped and preserved. No old32K process was required or recreated.

Configured context1048576/one slot/N76 is distinct from native observation:
this CAP3 lifetime had **no complete D3T graph/cache/compute block, slot context,
or native thread count**. No claimed actual1048576, fused selection or F16
allocation comes from older lines retained in the same container log.

## F16 evidence correction and remaining proof gap

The inherited assertion requiring one emitted line containing both `K (f16)`
and `V (f16)` was removed from readiness. The line exists in pinned source but
is suppressed by the default logging policy: `llama-kv-cache.cpp:301-304`
emits library INFO; `common/log.cpp:529-546` maps it to TRACE4, while the default
verbosity is3. Added D3T records use WARN and have no dtype field.

[Verified source snippets](d3cap3-evidence/f16-source-proof.json) bind current
clean upstream files to commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` and
checked patch SHA `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b`.
The source directory `/data/build/d3p-d3b2-20260915/source` is clean upstream,
not the derived tree. The actual immutable image carries derived-tree identity
`0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`; the patch leaves type/default/cache
and logger logic unchanged. No diagnostic patch or rebuild was made.

`common/common.h:587-588` defaults K/V parameters to F16. Types propagate via
`common/common.cpp:1751-1752` and upstream `llama-context.cpp:385-395` to
GLM_DSA's main MLA and indexer caches. `llama-kv-cache.cpp:230-234` creates
shared key storage for MLA and **no independent V tensor allocation**.
Source defaults plus exact protected launch state are necessary because byte
counts alone cannot distinguish F16 from another 16-bit type.

A meaningful acceptance would combine current PID/launch/default provenance
with fresh no_alloc0 allocation and the exact cache totals corroborated by
reviewed model metadata: CUDA0 `(40*576+12*128)*2*1048576` = 51,539,607,552 bytes;
CUDA1 `(38*576+9*128)*2*1048576` = 48,318,382,080 bytes. These are **expected
48/45GiB arithmetic, not CAP3 observed allocations**. That combined proof was
not reached. Missing live allocation/PID evidence remains explicit; missing
log text is not a model failure. The preliminary independent local source and
monitor review is retained with its original pre-run PENDING label.

## Monitoring evidence

Reused D3PERFVM cheap sampler and existing Manager; task-local correction only.
Target1Hz; true loading freshness/gap ceiling10s; >2s recorded as slow sampling.
Metric commands consume the remaining heartbeat+10s budget, including identity
inspection. A watchdog stops missing freshness beyond10s. The final implementation
has no earlier1.5s/2s loading-call timeout gate. No synchronous health/inspection
poll runs in the controller drain loop. Manager performs its existing readiness
polls separately. No PSS/smaps read occurred during load or request.

- 15 retained safe rows plus one preserved rejected row across 14.981777s.
- Actual producer gaps: min0.982515s / median0.999796s / max1.001835s.
- Snapshot durations: 0.034616–0.050818s, with separate cycle and command timings.
- Slow gaps >2s:0; no true10s freshness failure. Rejected row freshness age0.999273s.
- Maximum retained controller receipt interval: 1.102195s.
  Producer UTC and controller receipt UTC are retained separately. Host clocks
  were not calibrated; their subtraction is not a measured transport delay.
- Current `StartedAt` filters old D3CAP2 log lines. Context/graph fields stay absent
  until emitted by the current lifetime; stale records are not fresh evidence.

[Offline checks](d3cap3-evidence/monitor-offline-checks.json) exercised actual
monitor function with synthetic gaps1/2.637/9.9/10.01 seconds and >10s duration:
slow cases accepted, true bound violations rejected. Cheap source has no PSS;
controller is a pure drain. These are monitor checks, not live model acceptance.
No full repository or installer suite ran.

## Guards, hygiene and release

Full installed registered-storage checks with and without --root-guard passed
at admission/final/report boundaries. Root final available
**5,208,080,384 bytes (4.850403GiB)**;
WARN<6GiB remains, above4GiB hard stop. Registered ext4 UUIDs remain
/data `8daf56f1-5649-4163-9d87-919c2d271875` and /data/models-large
`a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`.
Guard SHA21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d
mode0755/root-owned and storage dependency SHA4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505
mode0644 match the reviewed authority. No fallback guard was used.

All77 installed closure files/hashes/modes, instance, registry, network, control,
manifest and exact key bytes/metadata remained unchanged. Control is inactive/
disabled; manual/restart-no remains. Task-added artifacts were reports under root-owned0700
`/data/logs/d3cap3-20260915`; existing Manager/Docker lifecycle state and log
writes followed reviewed registered-data paths. Existing scratch dirs had
inherited2700; they were revalidated without mutation. Preparation corrections
for inherited setgid and clean-upstream source identity are retained; no model
allocation was attempted until the final monitor/source checks passed.

[Lease release](d3cap3-evidence/lease-release.md): canonical lifecycle lease
released; worker request lock free; zero owned requests/samplers/tunnels, prior
and CAP3 process IDs absent, no established native API connection. Final
read-only report transfer completed2026-09-15T05:31:45.854954Z; no more VM calls
scheduled. Q38 fixture PIDs were absent at admission/final. Root reported all
three Q38FIX containers closed/no more runs; Worker2 source work did not own
real inference. No Worker2 requests occurred. Installer remains paused.

## Preserve D3CAP2 and next decision

D3CAP2 remains FAIL: its late actual1048576/one-slot/fused/realallocation block
appeared after monitor stop; readiness/F16/PSS/smoke were not accepted. Its
58 retained samples had no new swap; shutdown window later had +13 pages-in /
+3114 pages-out, oom_kill0, targetexit137/OOMKilledfalse; cause unknown.
Its rejected producer timestamp/per-call timings were not retained. The roughly
2.637s last-emitted-to-failure interval is not an exact known producer gap or
proof of model/resource failure. No CAP3 evidence relabels D3CAP2.

No further attempt is authorized by this report. Root chooses the next action
from the actual new host-swap evidence. Occupied-context, current direct client,
agent, model switching/catalog and boot acceptance remain open. Historical
D1 recovery assets and [exact old rollback command](d3cap3-evidence/historical-d3n32-rollback-command.txt)
are preserved, not invoked. That command's original N76/32K ownership assertion
must be reconciled with the now-stopped native1M state before any separately
authorized use. No fallback settings or new rollback were invented.

Final task-local operator source copies are under `operator-code/*.txt`; they
are review artifacts, not production changes. The final versions plus retained
preparation errors do not claim every earlier read-only invocation used identical
helper bytes. No raw prompt/body/key/environment dump is included.
