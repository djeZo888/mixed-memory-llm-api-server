# Stage-one ai-vm status — draft, 2026-09-17

**Completion PENDING.** ai-vm has demonstrated Qwen inference/tool serving and
an authenticated private control API. Final acceptance is still running under
root coordination. This draft is based on source
`ab6daa475cc2f1c04956d862f460f9f01c4ee952`, published evidence below, and explicitly
identified coordinated results awaiting durable report links. It is not a live
host observation or a completion certificate.

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
| Qwen serving at the selected TP2/BF16-KV/official-1,000,000 profile | [Q38RETRY](q38retry-tp2-1m.md) records READY, exact alias, missing/wrong-key 401, authenticated chat/SSE ending with DONE, actual `read_file` as ordinary UID 1000 and correct semantic continuation. The small continuation used fenced JSON, so this is not strict bare-JSON acceptance. |
| Private control and exact two-model discovery | [APIDEPLOY](apideploy-control-ready.md) records authenticated fresh/persisted status with current generation and the GLM/Qwen catalog; missing/wrong keys returned 401. Qwen was ready, selected, desired-running with resume intent at release. GLM was available/stopped. This is a dated state, not a claim about every subsequent moment. |
| Qwen occupied-context agent retrieval | **Coordinated result; durable APIACCEPT report link PENDING.** Root reports the actual selected Qwen profile completed a 144,244-token retrieval task with tool execution and strict retrieval JSON, PASS. It does not establish occupied 1,000,000 tokens. |
| Independent OpenCode read/edit/test | **Coordinated result; durable APIACCEPT report link PENDING.** Actual file reads, edit and test execution completed correctly; all eight verifier checks passed after replay of the already-saved original events with CLIENTTEXT. No inference rerun. The [source correction report](clienttext-stream-verifier.md) alone proves neither that replay nor live acceptance. |
| GLM native 1,048,576 configuration/allocation | [D3CAP4](d3cap4-native1m.md) records one allocated slot and a tiny HTTP 200 response (19 prompt/3 completion tokens). [HOSTRECOVER](hostrecover-20260917/final.md) later recorded readiness after recovery, then a task-wrapper-triggered stop and zero inference requests. Final GLM API/client/context acceptance remains PENDING. |
| Qwen unknown-model rejection | Reviewed source `705ddd75aa0305b121dbfa3e4942fa8a6c6e6c39`, integrated at this base, adds exact alias validation to both native chat and completion validators. Root reports 60 focused source checks and inventory PASS. New native-pair/extension proofs, one Qwen restart and live alias rejection are **PENDING**. |

The control catalog provides configured context, installed profile identity and
fresh readiness observations. It has no structured occupied-context receipt;
`context.verified_occupied_tokens` therefore remains `null`. A model-list entry,
source test, proof fixture, startup allocation and completed agent task are
different evidence. Neither full occupied maximum has been established.

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

The published Qwen short response used **34 prompt / 87 completion tokens in
3.533211 seconds**, or **24.623494 completion tokens per elapsed second**,
including prefill and transport. It is neither steady decode throughput nor an
occupied-context rate. GLM's historical **9.686 tokens/s** observation was a
[single 32K-configured decode comparison](d3perfvm-n76-cheap-monitor.md), not a
current 1M benchmark. No comparable final-profile sustained benchmark is claimed.

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
  passing test. Root's reported original-event replay PASS awaits its durable
  link; it did not rerun inference.
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
  Source checks are complete; installed rejection is not yet accepted. Earlier
  Q38RETRY proof receipts bind different launcher/fixture bytes and cannot cover
  this change.

The older successful native pair and extension receipts remain valid historical
evidence for their exact sources. They do not transfer to changed source merely
because the model, image or profile is unchanged.

## Remaining ai-vm completion plan

1. Finish the new exact-source Qwen native 131,072 → 262,144 pair and separate
   extension proof, then the coordinated Qwen restart/live alias-rejection
   checks. Preserve valid-alias inference and authentication evidence with the
   new source identities; retain rollback and historical receipts.
2. Attach durable APIACCEPT reports for the 144,244-token Qwen retrieval and
   original-event OpenCode replay. Keep actual tool/JSON evidence and measured
   occupied tokens distinct from configured maxima.
3. Complete **Qwen → GLM → Qwen** through the real control API from the assigned
   independent client: 202 receipts, completion polling, fresh discovery and
   authenticated inference after each transition. Final GLM API/SSE, ordinary
   agent-client work and occupied-context evidence remain **PENDING**, as does
   the switchback. Record the achieved context instead of assuming full 1M.
4. Leave fast **Qwen selected as default after acceptance**. Complete the
   selected-model reboot/resume and postboot private API/client checks under
   existing ownership, storage and lifecycle rules; earlier host recovery is
   not a substitute. Reboot acceptance remains **PENDING**.
5. Finish only root-reviewed exact obsolete-path cleanup after replacement
   acceptance and refreshed identity/in-use checks, retaining D1 rollback and
   recovery evidence. Cleanup remains **PENDING**. Publish the final evidence
   links and precise remaining limits before changing this draft to complete.

No frontend, installer, extra-model or co-residency work is part of this plan.
This STAGE1DOCS task changed only README, the operator guide and this report.
Validation was limited to documentation diff/whitespace, relative links and
source-contract reading; no tests, builds, downloads, VM access, model/control
requests or host mutations were performed.
