# D3CAP4 — native 1M allocation and tiny sanity PASS

2026-09-15. Worker1 completed **one unchanged allocation and one ordinary tiny
request**. The existing native1M backend remains running/ready/manual with
control OFF. Task ownership is released; no further VM calls are scheduled.
This establishes configured/allocated capacity and a tiny response only.
**Occupied 1M, long-prefix quality, tool/agent behavior, throughput, switching,
private-client acceptance and boot were not tested by D3CAP4.**

## Exact target and authorization

- Reviewed repository base: `dad2d58b57ab2367dee254cff1a885567b0c76f4`.
- Frozen [D3SWAP seam](d3cap4-evidence/swap-contract.md) consumed before start;
  [task-local contract](d3cap4-evidence/task-swap-contract.md) and five focused
  synthetic tests published before allocation.
- [CAP3 release](d3cap4-evidence/d3cap3-lease-release.md) proved exact stopped
  target/quiescence/ownership release. CAP2/CAP3 failure outcomes stay unchanged.
- Root [drain directive](d3cap4-evidence/coordination-input.md) arrived during
  allocation and was consumed before smoke. No extra acceptance requests,
  fallback, retry, tuning, cleanup, next phase or installer work.
- Existing deployment `glm-5.3-ud-q4-k-xl-n76-native1m`, alias `glm-5.3`;
  context 1,048,576, one slot, N76, F16, layer split 1:1, 112 threads.
- Container `3108f42bfaab08010164340b2c3e709e03c4aebeb36374e6b87d8bac226296fb`;
  PID `295514`, start ticks `2917536`,
  StartedAt `2026-09-15T05:41:00.282872024Z`.
- Runtime `llama-cpp-v0.4.1-d3br`; image
  `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9`; tag
  `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d`.
  Derived tree `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`, upstream
  `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`.
- Reviewed sealed GLM weights: 467289116837 bytes, 11 shards at
  `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL`.
  Existing Manager prepare_start/reused contract and protected model receipt
  were checked; no download or repeat full-weight rehash.

## Fresh allocation and idle proof

Manager start dispatched 05:40:59.067469Z; current container started 05:41:00.282872Z.
Manager health/models ready 05:43:22.187440Z; accepted idle/F16 allocation
05:43:23.499395Z. These are one restart observations, not a cold-load benchmark.

Fresh current-lifetime native block:
`n_ctx=1048576/n_ctx_seq=1048576/n_seq_max=1/n_batch=2048/n_ubatch=512`,
`flash_attn=1/fused_lid=1/lid_nodes=21/fa_nodes=78/no_alloc=0`.

| Actual allocation | CUDA0 bytes | CUDA1 bytes |
| --- | ---: | ---: |
| MLA plus indexer cache | 51,539,607,552 (48 GiB) | 48,318,382,080 (45 GiB) |
| Compute | 5,104,543,744 | 4,680,849,408 |

Effective F16 is established from the exact reused CAP3 pinned-source/default
proof, protected actual PID launch/argv with no dtype environment override,
verified binary SHA256 `c81262fd063e9d2fc098d9e116d0ae742ca7ea37344ee3f4b56eb5d088206e0a`,
and fresh native real allocation matching the MLA/indexer arithmetic. The INFO
dtype summary is suppressed by unchanged default logging. This is not a directly
emitted dtype observation; no independent V allocation exists for this storage.
The reused source proof contains historical CAP3 guard records, explicitly
separate from CAP4's fresh guard reports.

Full PSS at accepted idle before/after tiny request was
402.264225/402.324661 GiB.
Both full checkpoints retained measured Rss/Pss/Swap and fresh cheap proof on
each side of smaps with stable PID/startticks/cgroup identity. Swap and VmSwap
were zero. No PSS was collected during loading or request sampling.

## Model-scoped swap and other guards

All schema 2 samples require integer `cgroup_swap_current_bytes` in bytes, equal
to zero. Live owned PID membership yielded exactly
`/system.slice/docker-3108f42bfaab08010164340b2c3e709e03c4aebeb36374e6b87d8bac226296fb.scope`.
Protected whole-root cgroup2 mount, anchored no-follow file reads, memory
controller, PID membership, directory/file identity and stable Docker/PID/start
binding passed. There was no root aggregate, supplied path, missing-controller
fallback or unexpected host path. Read metadata is separate from path identity.
This is a small task-local CAP3 collector correction; production D3MON and the
installed closure were not changed.

- 141 cheap load samples. Maximum duration
  1.270968s; maximum producer gap
  2.215952s. Two gaps 2.197728/2.215952s were retained
  as slow samples; none exceeded 10s. Remaining-deadline subprocess budgets,
  raw producer timestamps/durations and separate controller receipts retained.
- Three in-request cheap samples plus one request-admission sample; maximum
  duration 0.131047s and gap
  1.075947s, under the existing 2s request bound.
- Every cheap/full sample: target VmSwap 0, cgroup swap 0; both full smaps Swap 0.
  Lowest sampled MemAvailable 480,297,156 KiB
  (458.047062 GiB), above 67,108,864 KiB.
  Lowest GPU free [31.489258, 23.213867]GiB,
  each above 16 GiB. Sampled checks do not establish instantaneous minima.
- Fresh host diagnostic baseline pswpin 19067/pswpout 39034/oom_kill 0;
  final 19077/39034/0, deltas +10/+0/+0 pages. Final host SwapUsed 27136 KiB.
  Host-only activity was retained without model attribution or abort. No
  counter rewriting, global swap/sysctl/Docker swap-setting change.
- All observed OOM/runtime/CUDA/storage/fusion/kernel error counts 0; current
  Docker OOMKilled false. No monitor abort or auth error occurred.
- Fresh full registered guards before mutation and after final report writes
  PASS. Final root 5,208,174,592 bytes
  (4.850491 GiB): below 6 GiB warning,
  above 4 GiB hard stop. Exact registered data/model mounts unchanged.

## The single ordinary tiny request

Dispatched 05:43:40.745219Z, complete 05:43:43.137571Z. Body:

```json
{"model":"glm-5.3","messages":[{"role":"user","content":"Reply with the single word READY."}],"reasoning_effort":"low","temperature":0,"max_tokens":128}
```

HTTP 200; actual model `glm-5.3`; output **READY**; finish `stop`.
Wall 2.392318s against 600s deadline. Native usage 19 prompt,
0 cached, 3 completion, total 22 tokens. Native prompt_ms 1266.182 and
predicted_ms 1103.214 retained verbatim with all native timing fields in the
[smoke evidence](d3cap4-evidence/smoke-result.json). This tiny response does not
establish sustained speed or an occupied context window.

## Final state, release and retained evidence

Final VM transfer 05:44:21.928939Z; local lease/process release verification
2026-09-15T05:45:54.190537+00:00. [Immediate release handoff](d3cap4-evidence/lease-release.md)
was published before report packaging, with final/capacity/smoke SHAs.
Canonical lifecycle lease released; worker request lock verified free; zero
owned temporary request, sampler, tunnel or operator/SSH processes; no native
API connections. Persistent model PID 295514 remains intentionally running.

Manager native1M/desired running/observed ready/manual/failure null; control
inactive/disabled, restart no. Original N76/32K
`7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78` and D1
`bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55` retained stopped. No rollback or removal.

All installed 77-file source hashes/modes, registry/instance/network/control/
manifest identities and protected native key exact bytes+metadata unchanged.
Key metadata is retained without the key value. Existing loopback endpoint
127.0.0.1:30002/v1 and private proxy 10.156.100.60:30002/v1 are unchanged;
CAP4's smoke used loopback from worker-operated ai-vm, not independent private
client acceptance. Protected reports are root 0700 under
`/data/logs/d3cap4-20260915`; worker copy is
`/Users/agent/CodexProjects/llm-orchestration/tasks/D3CAP4-20260915/trial/remote`.

[Exact artifact audit](d3cap4-evidence/artifact-audit.json),
[transfer hashes](d3cap4-evidence/report-transfer.json), and source/producer/
controller evidence are retained in `reports/d3cap4-evidence/`.
Only report/evidence files are committed. No full suite, installer test,
additional probe, restart or VM call followed release.
