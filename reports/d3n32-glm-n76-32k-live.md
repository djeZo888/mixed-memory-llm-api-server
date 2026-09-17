# D3N32 — GLM N76/32K measured runtime sanity

**PASS — N76/32K runtime sanity, native auth/strict-model/SSE, real tool
continuation, and one matched short comparison completed. N76 remains ready;
request ownership is released. Control remains inactive/disabled.**

Execution uses the approved mac-worker1 session and SSH ai-vm. The server remains
API-only. This report covers the short 32K sanity task; `highest_proven_window`
remains `null`. Configured 32,768-token capacity is not occupied-context proof.

## Exact identity and source publication

| Field | Value |
| --- | --- |
| Reviewed integration | `e8d8bbad3f2f6345295d440b25f084fed83dc734` |
| Profile | `glm-5.3-ud-q4-k-xl-n76-32k` |
| Runtime | `llama-cpp-v0.4.1-d3br` |
| Container | `7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78` |
| Container name | `llmctl-glm-5.3-n76-32k` |
| Docker image / OCI index | `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9` |
| Image tag | `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d` |
| Upstream source | `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Derived tree; derived commit | `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`; `null` |
| Instance / owner | `ai-vm-d0b` / `mixed-memory-llm-api-server` |
| Native endpoint / alias | `127.0.0.1:30002` / `glm-5.3` |
| Existing private transport | `10.156.100.60:30002`, unchanged |

Source publication PASS: 77 explicit root-owned files, 972,876 bytes, 39 changed
or new byte payloads plus one mode-only completion described below. This is the reviewed 75-file closure plus the two unchanged L2 supplements;
all 46 previously protected paths remain included. No recursive config copy or
adapter change. Final selected roster is GLM + Qwen3.8; Q38VC source bytes were
included without Q38 key/native receipt activation. Coder-Next remains deferred.

- Protected source: `/usr/local/lib/llm-server/control-api`.
- Immutable release: `/data/services/releases/e8d8bbad3f2f6345295d440b25f084fed83dc734-d3n32-20260915`.
- Source manifest: `/usr/local/lib/llm-server/control-api.manifest.json`, SHA256
  `8fe8b5c32da9e212cae7e1d50751deec0d91c8aa1405a10e343fe21b33e712e0`.
- Original metadata/closure and rollback profiles:
  `/data/services/llm-manager/d3n32-20260915`.
- Private VM report root: `/data/logs/d3n32-20260915`, root0700.

Under the existing canonical lease and anchored writer, added only
`instance.runtime_evidence["llama-cpp-v0.4.1-d3br"]`: exact image above,
`flags_verified:true`, the 17 measured supported flags, `load_mode:"none"`, and
`evidence:"/usr/local/lib/llm-server/control-api/reports/d3rp-runtime-proof.json"`.
The complete delta is in the source inventory and stage evidence.

| Protected instance bytes | SHA256 |
| --- | --- |
| Before | `55a1516385441e58c47e410a387afd71cfc20e58cb251ca9f495d9606e79a3ab` |
| After additive delta | `afd1e6e07db92f4e7b6d713752a33b9886f516d57ac3153971310e72688ba2e6` |

Staging preserved original state/intent/recovery bytes until the explicit
transition, instance identity, D1 runtime evidence, model receipts, registry,
key bytes/metadata, private transport, and stopped/disabled control. Both frozen
registered guard hashes were checked. Root available after staging was
5,208,567,808 bytes: above the 4 GiB stop threshold, below the 6 GiB warning.

## Controlled transition and first load

The reviewed Manager preflight inspected the exact local image and entrypoint
before stopping D1. D1 container
`bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`
was stopped at `2026-09-15T04:09:18.064082Z` and retained for rollback. N76 start
was dispatched at `04:09:19.124922Z`; Docker StartedAt was
`04:09:20.746242473Z`. Manager recorded ready at `04:11:47.677524Z`, approximately
146.93 seconds after container start and 178.97 seconds into the transition.
The profile deadline was 7,200 seconds, with 5-second polling/request limits.
Lifecycle lease release was recorded at `04:11:47.770667Z`.

Ready state was persisted: `desired:running`, `observed:ready`,
`container_running:true`, `failure:null`, `boot_policy:manual`, with old D1 as
`last_selected`. Docker restart policy remains `no`; control remains separately
unqualified. First load/readiness facts were published to task `live-status.md`.

The first existing full collector timed out at its 30-second collection limit;
its owned sampler was closed. The first reduced loading sample at elapsed
54.4175 seconds is **partial**, with no PSS or full native allocation result.
The first full **post-readiness** sample passed; it must not be described as a
complete during-load PSS trace.

| Sample | RSS KiB | PSS KiB | MemAvailable KiB | GPU0 / GPU1 free |
| --- | ---: | ---: | ---: | --- |
| Loading, 54.4175 s; partial | 365,172,192 | unavailable | 542,624,124 | 87,269 / 75,321 MiB |
| First full post-readiness | 419,671,520 | 419,671,516 | 482,114,072 | 84,400,930,816 / 75,920,048,128 bytes |

Post-readiness GPU allocated bytes were 18,241,028,096 / 26,721,910,784. Sampled
free VRAM exceeded 16 GiB on both cards. Process swap was zero; host swap used
14,080 KiB was pre-existing and unchanged, with zero sampled `pswpin`, `pswpout`
and `oom_kill` deltas. Both registered mounts passed; post-readiness root free was
5,209,489,408 bytes. Numeric CUDA/OOM/storage/runtime/fusion-fallback error
counters were zero. All **259 request samples passed**: maximum RSS/PSS
419,910,768 / 419,910,764 KiB; minimum MemAvailable 481,900,660 KiB; minimum GPU
free 84,358,987,776 / 75,892,785,152 bytes; maximum allocated GPU memory
18,282,971,136 / 26,749,173,760 bytes. Maximum adjacent sample gap was 1.825214 s.
The sampler was closed after the tool/fixture and restarted before continuation.
Final full telemetry also passed. These are sampled observations, not peak guarantees.

### Native diagnostic allocation boundary

The new numeric `D3T_NATIVE_V1` record, emitted only for `LLM_ARCH_GLM_DSA`, reported `n_ctx=32768`, `n_ctx_seq=32768`,
`n_seq_max=1`, `n_batch=2048`, `n_ubatch=512`, threads112, and N76 placement.
Selected graph path recorded `flash_attn=1`, `fused_lid=1`, 21 LID nodes and 78 FA
nodes. The allocation record has **`no_alloc=0`**.

| Native backend buffer | CUDA0 bytes | CUDA1 bytes |
| --- | ---: | ---: |
| Compute | 4,467,457,152 | 520,099,840 |
| Cache | 1,610,612,736 | 1,509,949,440 |

These are emitted backend-buffer allocation sizes with `no_alloc=0`. The graph
and scheduler reservations describe the selected startup plan; `no_alloc=0`
distinguishes it from allocation-free planning. They do not measure executed
fused kernels or a runtime workspace peak.
The retained numeric sample does not expose a separately labeled workspace total;
do not invent one or add these buffers to overall GPU usage a second time. This
is diagnostic graph/allocation evidence, not a full kernel profiler result.

## Native protocol and tool checks

Recorded native checks: `/health` 200; `/v1/models` missing/wrong key 401 and
correct key 200; chat missing/wrong key 401. Unknown, null, empty-string and
object-valued supplied models rejected 400 for both JSON and streaming requests,
before generation/SSE. Keys, request bodies and headers are not logged here.

Ordinary alias generation passed in the matched request below. Omitted-model
native SSE passed with model `glm-5.3`, HTTP200, completed stream marker,
`finish_reason:stop`, 23 input / 5 output tokens, and 10.567400 seconds wall time.
The native SSE tool request passed protocol handling with `finish_reason:tool_calls`,
205 input / 13 output tokens, and 37.387318 seconds wall time. A real worker-local
`read_file` of `calc.py` was executed and its result supplied to continuation.

Continuation **PASS**: HTTP200, `finish_reason:stop`, 247 input / 60 output
tokens (217 cached; 30 evaluated), 101.354301 seconds observed wall time. The
existing A1 helper executed exactly one real `read_file(calc.py)`; native call
identity and actual tool result were preserved, with no reasoning replay. The
continuation reported the real file contents. **Protocol PASS; agent
PASS_REAL_READ_TOOL_AND_CONTINUATION.** Four generations completed in total.
Requests use existing A1 semantics with explicit
`reasoning_effort:low` and bounded budgets. No OpenCode client was installed;
Worker2 direct-client acceptance remains subsequent work.

## One matched short comparison

Exactly one candidate replay used the frozen private D3BASE body, 600-second
deadline, `model:glm-5.3`, `reasoning_effort:low`, `temperature:0`,
`max_tokens:256`, `stream:false`. Both returned 64 output tokens. The candidate
completed HTTP200 with `finish_reason:stop`.

| Metric | D1 baseline | N76 candidate |
| --- | ---: | ---: |
| Native input tokens | 1,370 | 1,370 |
| Cached tokens | 50 | 0 |
| Evaluated prompt tokens | 1,320 | 1,370 |
| Output tokens | 64 | 64 |
| Prompt seconds | 22.135537 | 37.115145 |
| Decode seconds | 112.294399 | 117.054310 |
| Wall seconds | 137.054919 | 154.219367 |

Cache conditions differ: the baseline is partially cached; the candidate reports
zero cached tokens. This single sample establishes no general performance or
occupied-context claim. D3BASE's `cold_cache_NOT_TESTED` checkpoint remains
unchanged; there is **no cold baseline PASS** and no repeated attempt to force
zero cache. N76 was 12.5% slower in observed wall time for this pair; unequal
cache counts and one sample limit that observation. Wall time is worker-observed
completion time and can include the last telemetry collection (up to 1.47 s);
backend prompt/decode timings are retained separately.

| Private identity; contents omitted | SHA256 |
| --- | --- |
| Exact frozen request body | `6682c1aaae6491aaa900da3297c05e17a63bc35adbceaef310bc8ded47b1f89d` |
| Native token vector | `469dd72637c5825cf9cd3b936e7c7033ab0d99ed1dfb14ca94ce4db92bbe455c` |
| Rendered prompt | `9bcde19e00224e1f7d5892196e079ea3c4951f7c99760f52337f06a216742d5d` |
| Template | `347dc716e1e8a9917eb124503836943107686ace6a3848d16bf23ae50964bb49` |
| Candidate response | `d647bbf0a7f95f5275248406a0e014075050954905fd41dfa49a8596f522a9cf` |

Native token accounting retained `add_special:true`, `parse_special:true` and
configured context32768. Frozen baseline material remains private under
`/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial`.

## Rollback procedure — source reviewed, not executed

After requests are drained and exclusive lifecycle ownership is available, the
following command, run on ai-vm through this worker SSH session, uses the existing Manager. It preflights and validates retained D1
before stopping the exact N76 owner, then selects/starts D1 with manual intent.
Rollback profiles stay outside the final catalog; source/instance evidence stays
preserved. Any mismatch stops the procedure.

```sh
sudo -n /usr/bin/python3 -I -B - <<'PY'
import json
import sys
from pathlib import Path
from types import SimpleNamespace

source = Path('/usr/local/lib/llm-server/control-api')
sys.path.insert(0, str(source / 'scripts'))
from common.lifecycle_lease import acquire_lease
from lifecycle.manager import load_manager, Manager

old_id = 'bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55'
new_id = '7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78'
old_profile = 'glm-5.3-ud-q4-k-xl-32k'
rollback_configs = Path('/data/services/llm-manager/d3n32-20260915/rollback/configs')
with acquire_lease(blocking=False) as lease:
    current = load_manager(SimpleNamespace(instance=None), source / 'configs')
    assert current.instance['id'] == 'ai-vm-d0b'
    state = current.read_state()
    assert state['container']['id'] == new_id
    assert state['selected'] == 'glm-5.3-ud-q4-k-xl-n76-32k'
    current.trusted_container(state['container'])
    rollback = Manager(rollback_configs, current.instance, binding=current.binding)
    deployment = rollback.deployment(old_profile)
    rollback.prepare_start(deployment)
    old = rollback.docker.inspect(old_id)
    assert old and old['Id'] == old_id and not rollback.running(old)
    rollback.trusted_container(rollback.identity(old, deployment))
    rollback.validate_reused_contract(old, deployment)
    rollback.network_check(old, deployment)
    current.dispatch('stop', lease=lease)
    rollback.dispatch('select', deployment_id=old_profile,
                      boot_policy='manual', lease=lease)
    print(json.dumps(rollback.dispatch('start', lease=lease), sort_keys=True))
PY
```

## Evidence, checks and remaining boundary

Task-private worker evidence is under
`/Users/agent/CodexProjects/llm-orchestration/tasks/D3N32-20260915/trial`:
`stage-apply.txt`, `source-inventory.json`, `first-load.json`,
`load-diagnostics.json`, `load-samples.jsonl`, `transition-events.jsonl`,
`request-events.jsonl`, and `comparison.json`. Sanitized committed evidence is in
[d3n32-evidence](d3n32-evidence/SHA256SUMS); private VM copies and final guard
reports are under `/data/logs/d3n32-20260915`. The existing D3RD binding verifier, exact
source/delta checks, stage dry-run/apply checks, native telemetry and bounded HTTP
requests are the task verification boundary; no full installer suite or broad
historical test rerun is claimed.

Native1M remains declared `NOT_TESTED` and was not loaded. Occupied context,
long-context correctness, tuning grids, full kernel profiling, boot/reboot,
control qualification, Q38 activation and Worker2 client acceptance are outside
this result. No driver/daemon/network changes, downloads, image builds, historical
asset cleanup, reboot or installer actions occurred.

## Final checks and handoff

- Final registered data/model/root guards PASS; root available 5,208,498,176 bytes,
  retaining the below-6-GiB warning and above-4-GiB stop margin.
- Exact 77-file protected closure and immutable release hashes/modes PASS; all
  original closure bytes remain in the rollback backup. The first final check
  found `registered-storage.py` retained its prior0644 mode while the reviewed
  Git/manifest mode was0755. Completed only that mode refresh on the same inode;
  its frozen SHA256 and bytes did not change. The original0644 backup remains.
  The original verification error and correction record are retained. No runtime
  allocation/kernel/readiness failure occurred and no rollback was needed.
- Actual final Manager status/launch contract PASS. Active/recovery SHA256:
  `90757bf8175f23881d6cbde6b4513cf929bf9eeb5172838e640bd376332bee8f`.
  N76 running/ready, desiredrunning, manual; Docker restart=no; D1 stopped,
  both restart counts0 and no OOM. No boot unit/reboot acceptance is claimed.
- Original key exact bytes/metadata, registered identity, model completion
  receipts, control config/unit and existing private transport PASS unchanged.
- D3N32 request lease released `2026-09-15T04:20:37.752414Z`. Existing request
  lock is free; zero native API connections; owned tunnel PID32823 absent and
  port54911 unbound; zero owned remote samplers; transition owner exited. All
  request/fixture processes returned and sampler/tunnel Popen handles were reaped.
- D3BASE remains `PENDING_RECONCILIATION / cold_cache_NOT_TESTED`; no checkpoint
  edit, extra comparison, Native1M load or occupied-context claim.

Verification commands/APIs: `python3 -B scripts/d3rd/verify_binding.py`; Python
syntax/help checks for fixed task transcripts; actual stage dry-run; existing
`Manager.prepare_start/dispatch`, canonical `acquire_lease`, registered guards
and `AnchoredRoot`; A1 `Client`, `d3t.accounting` and one direct `Transfer` replay;
`d3t.guards` telemetry and exact final source/state/identity checks. No new product
harness, adapter, installer or ownership framework was added. Product sources
remain exactly at the reviewed integration. Final Git changes are this report
and sanitized evidence only; local secret scan and bundle verification accompany
the task handoff.

**Next:** parent may schedule the separate native-capacity/occupied-context or
Q38 stage after taking the released request lease. Keep control stopped pending
its separate qualification. The observed short comparison does not justify a
performance preference or a proven context window.
