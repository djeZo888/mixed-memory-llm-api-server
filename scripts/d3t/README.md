# D3T: one bounded GLM trial

**Source prepared; generation, N76 load, native-capacity load and occupied-context
acceptance NOT_TESTED.** Root separately reviews D3P's measured patched image and
this source before the live owner runs the commands below. Final roster is
GLM5.3 + Qwen3.8; this runner probes GLM only. No installer integration.

## Fixed trial

Preserve old D1 all-CPU32K rollback. Compare four32K requests on that baseline
and four on N76: ordinary cold/warm (256 output each), streamed tool call and
nonstream continuation (512 each). Exact cold/warm/tool bodies match; continuation
comparison normalizes only the native tool-call ID. Actual hashes are retained
for every body. Require exposed cold cached count0 and useful warm reuse.
D1 and D3P are different images, so this is a comparison of complete configurations;
a timing difference cannot be attributed solely to expert placement.

Then root loads ONE native1048576 container with the same N76 patched image.
Preserve that container through occupied65536/131072/262144/524288/1048576 windows.
Each stage has cold retrieval128, streamed tool256, streamed continuation256
output caps. Each initial prompt is within256 tokens of window-8192; output,
tool result and continuation consume the reserved8192. Stage elapsed caps are
2/4/8/12/24h including preparation, prefill and continuation. Comparison requests
have600s caps and a combined2400s generation cap. No automatic retries or reloads.

All requests use low reasoning and temperature0. Native accounting sends the
exact body to `/apply-template`, then the returned prompt to `/tokenize` with
`add_special=true,parse_special=true,with_pieces=false`; it checks `/props`.
A deterministic append-only record corpus grows by a bounded18-iteration native
token-fit search per stage. This is input construction, with no generation or
runtime parameter search. Each request is independently accounted and token IDs
are checkpointed privately. Actual usage must subsequently agree with the native
count. Matching token prefixes alone do not prove backend cache reuse.

## Source preparation and profile output

```sh
python3 -B scripts/d3t/profiles.py --output /private/task/d3t-profile-plan.json
python3 -B -m unittest discover -s tests/d3t -p 'test_*.py' -v
```

The generator emits NOT_TESTED, nondeployable proposals with `runtime:null`,
using pinned existing schema-v1 sources. D3P/root must later bind its measured
strict-alias image in a separate deployment through Manager. It never rewrites
configs or instances. Only N76 at32K/native and the separately reviewed all-CPU
native headroom fallback exist. Client ownership permits no fallback or reload.
The old all-CPU32K source is unchanged. Manager accepts only bounded reviewed
placement/context combinations; Q38 dispatch/imports remain unchanged.

## Later live owner commands

Use an ordinary worker account, exclusive root-coordinated ownership and a
private0700 directory outside the repository. Keep the existing authenticated
loopback tunnel to ai-vm port30002 alive. Obtain the key through the reviewed
A1 protected-file workflow; the key value never appears on argv or in outputs.
`--key-file` names an owned0600 regular nonsymlink file. No server-side tool runs.
Native accounting and telemetry use fixed `ssh ai-vm` stdin Python adapters;
the key for native routes is read only in the remote process memory. No VM
scripts, service state or keys are installed by these adapters.

```sh
python3 -B scripts/d3t/probe.py init --run /private/task/d3t-run \
  --base-url http://127.0.0.1:30002/v1 --key-file /private/task/api-key
python3 -B scripts/d3t/probe.py bind --run /private/task/d3t-run \
  --phase baseline --container-id FULL_REVIEWED_CONTAINER_ID --image-id REVIEWED_D1_IMAGE_ID
python3 -B scripts/d3t/probe.py prepare --run /private/task/d3t-run --stage baseline
python3 -B scripts/d3t/probe.py status --run /private/task/d3t-run
# Only when PREPARED:
python3 -B scripts/d3t/probe.py start --run /private/task/d3t-run
python3 -B scripts/d3t/probe.py status --run /private/task/d3t-run
```

`prepare` and `start` each return promptly after detaching a worker. Monitor
`status` at least every60s in a NEW CLI session as needed. After STEP_PASS, repeat
prepare/start for that stage's next step. After STAGE_PASS, the root-owned
lifecycle task may release ownership and load the reviewed next configuration;
this runner performs no lifecycle operation. Bind `candidate` only after baseline
PASS and `native` only after candidate PASS. Native binding cannot be replaced.
Run stages64k,128k,256k,512k,near1m in order, three steps each, with the same binding.
Do not run multiple stage commands concurrently. Per-run locks prevent duplicate
dispatch from this run; the existing root-coordinated exclusive client lease is
a prerequisite and is not replaced by these local locks.

`request.lock` rejects another owner immediately. Short `state.lock` transactions
retry every 25ms for at most 5s, including worker reads and success/failure writes.
Brief status reads therefore serialize with the worker. Exhaustion raises
`state_lock_timeout`; failure publication gets its own bounded lock attempt. If
that also expires, the last durable STARTING/IN_FLIGHT checkpoint remains for
unknown-completion reconciliation. Request deadlines and owner cancellation
still apply after waiting; no request is automatically retried.

Only `status` resumes monitoring. STARTING/IN_FLIGHT never dispatch again.
IN_FLIGHT_UNKNOWN/PENDING_RECONCILIATION require root to reconcile server completion;
never rerun the request to guess. PREPARATION_UNKNOWN/NOT_TESTED also stop the plan.
A failed or timed-out stage leaves all later stages PENDING_NOT_TESTED, without a
claim that the model lacks that capacity. `cancel --run ...` asks only this worker
to close its own request socket. Sampler cleanup targets only its own SSH child.
No tunnel is created/killed and no arbitrary process is signaled. Socket closure
cannot prove server cancellation; retain ownership until root reconciles it.

## Resource and native selection evidence

The concrete adapter verifies exact current-D3 ext4 mount UUIDs and root free>=4GiB,
both GPU free>=16GiB, target process swap0, no new host swap activity, no new
CUDA/OOM/storage errors, and RSS/PSS/MemAvailable. Historical host swap usage is
reported separately, not silently treated as current request swapping. Live owner
runs the existing common storage/root guards before and after lifecycle changes.

A bounded1Hz sampler retains private rows. Samples and sampled extrema establish
only sampled values, never instantaneous peak proof. Stale samples, identity drift,
threshold/error violations, accounting mismatch or missing exact cache counts stop
advancement. No extra profiling toolchain is involved.

Native admission requires actual context, one slot, fused_lid/indexer and FA graph
selection plus positive exact compute/cache allocations on both cards. Current
old32K logs do not expose those selections. The tiny `D3T_NATIVE_V1` startup patch
plan is separately owned by D3P and combined with strict-alias in ONE reviewed
build. Selected reserved graph + actual allocation logs and later sanity establish
the accepted evidence boundary; they do not claim every kernel was profiled.
Unfused64GiB score path is outside budget and blocks occupancy.

## Private checkpoint/result schema v1

`state.json`: stage/step/status, durable start/deadline, frozen body SHA256,
actual input/render/token hashes, exact common-prefix count, completed result
records and highest_proven_window. `native_configured_capacity` is separate.
`highest_proven_window` stays null through baseline/candidate short comparisons;
their PASS records remain under `stages` as comparison evidence. Only a complete
native occupancy stage, after its initial actual-count lower bound and successful
retrieval/tool/continuation sequence, advances occupied proof. Later failures
preserve the last proven value. Source-test fixture values are not live evidence.
Each result has exact body/raw hashes, elapsed seconds, nullable backend
prompt/completion/total/cached/evaluated/decode counts and prompt/decode timing,
retrieval/tool checks and sampled evidence location/count. Missing metrics are
null and are never reconstructed from differences. Native raw timings/usage stay
in private `*.response.json`; request bodies, token IDs and raw output stay in
private0600 files. Public status contains only safe hashes/counts/state.
The actual worker-local tool reuses A1's exact read_file schema and executes one
real deterministic calc.py read with its native ID preserved in continuation.
Reasoning is parsed separately and never replayed. Credential echoes are
redacted or refused before raw/parsed output persistence.
