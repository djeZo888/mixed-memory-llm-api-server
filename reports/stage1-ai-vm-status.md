# Stage-one ai-vm status — qualified acceptance, 2026-09-17

**Core stage-one API/model/switch/reboot/independent LAN acceptance PASS.
Cleanup PENDING; qualifications remain explicit.** The evidence cutoff is
2026-09-17T08:06:22.492747Z. The [independent acceptance report](apiaccept-lan-acceptance.md)
and [sanitized summary](apiaccept-evidence/summary.json) document the completed
requests; [alias publication](aliasdeploy-proof-publication.md) binds the
corrected deployed source `ab6daa475cc2f1c04956d862f460f9f01c4ee952`. This status
does not claim overall project completion, full occupied context or swap-free
GLM qualification. It is not a fresh host query.

The deliverable is an API-only server with one active backend: **GLM5.3
UD-Q4_K_XL** for flagship work or **Qwen3.8-27B FP8** for fast work. Ordinary
user clients execute tools in trusted workspaces and return their results to
inference. ai-vm exposes inference and control, not an agent execution service.
The separate frontend VM is later work; all installer work and tests are paused.
See the [operator guide](../docs/ai-vm-api-operations.md) for endpoints, separate
protected credentials, discovery, switch/poll and client examples.

## Demonstrated capabilities and limits

| Capability | Evidence and boundary |
| --- | --- |
| Qwen API and real tools | Authentication, exact models, chat/SSE and real read/edit/test passed. The original A1 suite remains FAIL because unknown alias returned 200; later corrected-source rejection and valid continuation passed separately. [Q38RETRY](q38retry-tp2-1m.md) retains the smaller UID-1000 tool case and its fenced-JSON limitation. |
| Qwen occupied-context retrieval | PASS: 144,244 input tokens initially, 144,026 on genuine tool-result continuation, with `read_file`, beginning/middle/end retrieval and strict JSON; 47.611 s total. Largest completed retrieval input is 144,244, not 1,000,000. |
| Qwen real OpenCode read/edit/test | All eight original functional/integrity checks PASS; saved-event replay with CLIENTTEXT `4173d339` passed without an inference rerun. The original blank-fragment verifier failure remains preserved. |
| GLM API, client and retrieval | A1 all 11 checks PASS in 52.764 s; real OpenCode all eight PASS in 128.042 s. Retrieval/tool/strict JSON PASS: 4,154 initial input, 4,196 continuation, 74.827 s total. The 4,196 maximum is specific to retrieval; OpenCode input+cache counters reached 5,791, without independent native pre-count. Configured context remains 1,048,576. |
| Control, catalog and switching | Dedicated authentication, exact two-model catalog/status, stale-generation 409 without transition and identical body/key replay PASS. Qwen → GLM succeeded in 308.041 s (generation 3); GLM → Qwen in 88.192 s (generation 5). Durations cover whole operations, not isolated loading; every 202 was followed to terminal success and rediscovery. |
| Corrected Qwen alias contract | New genuine native 128K/256K and 1M extension proofs PASS; exact ab6 source published at 07:22:01.997357Z without GLM reload. After switchback, unknown alias returned native HTTP 400, top-level `BadRequestError`. Offline interpretation corrected a nested-envelope verifier false negative, with no retry/runtime change. Two valid streamed calls then passed real `read_file`, continuation, correct interpretation and strict JSON. |
| Default and reboot | Fast Qwen is selected/default with resume intent. One actual normal reboot succeeded at 07:57:22 UTC. Exactly four independent postboot LAN requests passed by 08:06:22.492747Z: control READY at generation 6, no-native-key 401, exact authenticated model and one short streamed expected completion. No rich agent/context suite was rerun after boot. |

All acceptance rows above use the independent report linked at the top, except
the explicitly linked earlier Q38RETRY record and Worker1 alias/reboot handoffs.
Rich Qwen agent/context results belong to the **predecessor launcher**. Corrected
ab6 has new exact-source proofs, the narrow three-call regression and postboot
smoke, with the same weights/TP2/BF16-KV/official-1M profile. These are separate
evidence scopes, not an assertion that old receipts cover changed bytes.

The [new receipt publication](aliasdeploy-proof-publication.md) records native
SHA256 `95178ab3a9bcd9ffad79e2496bbfb7a3014a8195dfe0e097949e845487c3514f`
and extension SHA256
`ec628c0ef48efa583a4c06ba6f5ccfa07214b0b8489b16a7b1812bc9aa9a2b44`.

The control catalog provides configured context, installed profile identity and
fresh readiness observations. It has no structured occupied-context receipt;
`context.verified_occupied_tokens` therefore remains `null`. A model-list entry,
source test, proof fixture, startup allocation and completed agent task are
different evidence. Neither full occupied maximum has been established;
near-cap tasks were NOT_TESTED, not silently passed.

## Placement, capacity and timing

GLM uses system RAM and both GPUs with configured target **1,048,576** tokens.
Qwen uses both GPUs/TP2, FP8 weights and BF16 compute/KV, with official factor-4
YaRN configuration for **1,000,000** tokens. Q38RETRY confirmed that context and
token pool, maximum request input 999,994, one running request and one Mamba
cache slot. Its startup logs reported 14.66 GB weights and K 15.26 GB + V 15.26 GB
per rank, retaining the server's GB labels. These allocation facts do not measure
long-context correctness. Native Qwen 128K/256K profiles remain historical
validation baselines, not additional offered models.

Models and large server writes use protected registered `/data` storage,
including `/data/models-large`, `/data/hf-cache`, `/data/docker`,
`/data/containerd`, `/data/build`, `/data/logs` and `/data/services`. The authority
is `/etc/local-ai-server/storage.json` with exact mount/identity checks and
current installed guards. Root-resident control credentials/recovery code are
deliberate; model/cache/log payloads do not belong on root. Historical guard
identities in reports are not current execution instructions.

The earlier published Qwen short response used **34 prompt / 87 completion tokens in
3.533211 seconds**, or **24.623494 completion tokens per elapsed second**,
including prefill and transport. It is neither steady decode throughput nor an
occupied-context rate. GLM's historical **9.686 tokens/s** observation was a
[single 32K-configured decode comparison](d3perfvm-n76-cheap-monitor.md), not a
current 1M benchmark.

Current-profile GLM timing comes from the already-saved retrieval responses;
no benchmark was rerun:

| GLM request | Input / output | Cached / evaluated input | Wall seconds | Native prompt tokens/s | Native decode tokens/s | Completion tokens / elapsed second |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial tool request | 4,154 / 13 | 50 / 4,104 | 67.408 | 69.299 | 1.507 | 0.193 |
| Continuation | 4,196 / 45 | 4,166 / 30 | 7.271 | 34.703 | 6.906 | 6.189 |

Native decode uses the server's `(predicted_n - 1) / seconds` convention.
These tiny outputs and warm-cache-sensitive observations are not sustained
benchmarks. Qwen retrieval requests took 23.285 and 24.181 s; native timing
counters were unavailable. Do not compare those wall observations to GLM native
decode or infer an apples-to-apples model speed ranking.

**Separate user-supplied observation:** the user's own SSH heredoc completed a
74,987-input / 52-output-token demonstration in 10.49 s with all three checkpoint
values correct. The response used a Markdown JSON fence. This corroborates
manual retrieval but is not the controlled 144K acceptance case, strict bare-JSON
acceptance or live execution of the repository example. Whole-request elapsed
time does not isolate native prefill or decode; no derived rate is claimed here.

**Memory qualification:** GLM semantic/API/agent results passed, but strict
zero-swap is **NOT_PASS_NONZERO_CGROUP_SWAP**. Model cgroup swap was **32 KiB**
during the case versus **248 KiB** immediately before; host swap was **16.75 MiB**.
Individual PID VmSwap was **NOT_MEASURED**. No swap growth or OOM was observed;
these numbers do not establish a cause or explain the measured rates. Qwen's
46 in-window samples recorded host/cgroup swap 0 and OOM delta 0, but its sampler
ended 1.7859 s before the case terminal after broad cancel-text matching.
Post-case replacement samples are excluded. Resource maxima are sampled,
not continuous coverage or absolute-peak proof. See the
[telemetry qualifications](apiaccept-lan-acceptance.md).

## Obstacles and what resolved them

These issues explain substantial investigation time without treating every
historical test as current acceptance.

- **Host capacity and NVIDIA mismatch — host failures.** Crash artifacts filled
  root headroom; [exact archive-and-remove recovery](rootspace-recovery.md)
  preserved them on registered data and restored guard PASS. Later unattended
  driver updates left loaded/userspace versions inconsistent. The authorized
  [host recovery](hostrecover-20260917/final.md) reboot aligned kernel
  6.8.0-139/NVIDIA 595.84, restored both GPUs and mounts, and installed bounded
  apt/journal maintenance and coordinated driver-update policy. Its 5.180 GiB
  root headroom remained below the 6 GiB warning. That recovery reboot does not
  satisfy final selected-model reboot acceptance. A reporting-wrapper type error
  stopped an already-ready GLM; that was an orchestration failure, not failed
  model allocation. Managed Qwen core limits address the crash/root-fill hazard.
- **Native import environment — fixture isolation defect.** Genuine imports can
  add environment state which a later launcher invocation rejects. Q38FIN
  reproduced FlashInfer's CUDA-13 `TRITON_PTXAS_BLACKWELL_PATH` side effect in
  source, while the original VM offender name was not retained. The fixture now
  restores its validated pre-import snapshot at invocation boundaries; initial
  invalid inputs still fail. This was not proof of a production compiler/model
  failure. See [Q38FIN](q38fin-startup-core.md).
- **Resolved defaults — launcher validation defect.** Native resolution changes
  `grpc_worker_threads` from raw `None` to integer 4 even with gRPC disabled.
  The narrow [Q38MAX correction](q38max-source.md) accepts that pinned resolved
  default while refusing enabled gRPC and unreviewed values.
- **Caps directory — fixture classification gap.** The device-name gate rejected
  `/dev/nvidia-caps`. The [correction](q38max-caps-followup.md) accepts only an
  empty, ordinary nonsymlink root-owned 0755 directory, or absence; device nodes
  and nonempty/unsafe directories remain refused. The initial observation did
  not establish contents or creator. This avoids classifying a proven harmless
  directory as GPU access without weakening actual device isolation.
- **Rayon — bounded native-fixture resource failure.** The real tokenizer/chat
  constructor failed to initialize its global pool (`WouldBlock`, errno 11).
  [Fixture-scoped `RAYON_NUM_THREADS=1`](q38max-rayon-followup.md) bounds workers
  while retaining genuine constructors and auth checks. PID-cap exhaustion was
  a hypothesis, not measured causality; this was not a failed model load.
- **YaRN — resolved-metadata comparison gap.** The extension resolver retained
  the expected context/dtype but added legacy `rope_parameters.type:"yarn"`.
  The corrected exact resolved-object comparison was followed by genuine
  extension proof and actual TP2/1M serving in [Q38RETRY](q38retry-tp2-1m.md);
  [original operands](q38retry-native256-evidence/extension-resolution.json)
  preserve the earlier mismatch. This was not evidence of failed 1M allocation.
- **Optional null SSE metadata — client parser gap.** The client rejected
  `role:null` and nullable incremental tool metadata before executing the tool.
  [CLIENTNULL](clientnull-streaming.md) treats optional null fragments as absent
  while keeping final IDs/names/JSON arguments and DONE checks strict.
  Q38RETRY subsequently demonstrated real tool execution/semantic continuation;
  its retained fenced-JSON limitation is separate.
- **Blank intermediate OpenCode text — verifier gap.** A whitespace fragment
  caused `native_empty_text` despite correct read/edit/test evidence and a later
  nonempty final answer. [CLIENTTEXT](clienttext-stream-verifier.md) ignores blank
  fragments but still requires valid ordering and nonempty final text after the
  passing test. The independent report now records original-event replay PASS;
  it did not rerun inference or rewrite the original failure.
- **Control reads — service budget defect.** Root's coordinated complete-read
  diagnostic measured **5.6126 seconds against a 2-second budget**, with repeated
  protected storage/profile checks. CONTROLREAD reuses the selected deployment
  within observation and sets bounded read/admission budgets to 10 seconds and
  HTTP lifetime to 30 seconds. The [published live result](apideploy-control-ready.md)
  records status at 7.872330 s and catalog at 8.581904 s, both semantically valid.
  The complete 5.6126 s diagnostic remains task-local as named there; it is not
  the earlier 2.190814 s timed-out diagnostic. This blocker is resolved, not a
  model failure or grounds to bypass storage checks.
- **Missing SGLang model-alias validation — runtime API gap.** The
  [reviewed launcher source](../scripts/runtime/sglang38_file_auth.py) now checks
  the request model against the active served name in both native validators.
  New exact-source native/extension proofs and live HTTP 400 rejection now pass.
  A later task-local checker falsely expected a nested error instead of native
  top-level `BadRequestError`; the retained response was interpreted offline
  without retry or runtime change. Both the original runtime defect and later
  verifier false negative remain recorded. Earlier Q38RETRY receipts still bind
  their predecessor bytes, not this correction.
- **Delayed directive pickup — orchestration overhead.** Some time was lost
  because active remote CLI sessions did not promptly consume incoming-file
  directives. Source-only checkpoints and direct same-session resume made
  handoffs immediate. This was coordination overhead, separate from model or
  runtime failure; no new workflow implementation is part of this report.

The older successful native pair and extension receipts remain valid historical
evidence for their exact sources. They do not transfer to changed source merely
because the model, image or profile is unchanged.

## Remaining completion work and retained qualifications

The required model/API/switch/reboot sequence is complete. Accepted idle handoff
before reboot was 07:51:04.325268Z; independent postboot request ownership ended
at 08:06:22.492747Z with no active/inflight requests. Qwen remains the accepted
default. No additional acceptance or benchmark run is initiated by this report.

Cleanup remains **PENDING** until its separate completion report arrives. Finish
only reviewed exact obsolete paths after refreshed identity/in-use checks,
retaining D1 rollback and recovery evidence, then attach the actual cleanup
report. A dry-run or this documentation update is not cleanup completion.
Keep near-cap NOT_TESTED, GLM nonzero-swap qualification, sampled telemetry
limits and predecessor/corrected-source boundaries in the final closeout.

The user-requested [standalone Qwen context example](../examples/qwen-context-test.py)
is **NOT_LIVE_EXECUTED** and not an acceptance gate. It has in-memory syntax/basic
offline helper checks only. Its published-console command must use the exact
full revision confirmed after publication; this task did not fetch or run it.

No frontend, installer, extra-model or co-residency work is part of this plan.
This follow-up owns only README, the operator guide, this report and the example;
independently owned evidence was read without modification. Validation was
limited to documentation diff/whitespace, relative links, source-contract reading
and the example's basic offline checks. No formal/broad test suite, build,
download, VM access, model/control request or host mutation was performed.
