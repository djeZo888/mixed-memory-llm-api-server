# AGENTS.md

## Active H016 execution window

Latest user extension adds45minutes for the requested4-thread and conditional2-thread comparisons: **final18:33:08UTC /20:33Ljubljana**. RunningR9 deadlines remain unchanged; new tasks use the new bounded window.
MiMo Pro is now explicitly the intended primary frontier replacing GLM, after
qualification. Keep two Qwen instances and the image model. R7's single
GOMP_SPINCOUNT=0 change improved unprofiled output to5.885tok/s for128 tokens
and6.005tok/s for512; profiled3.364tok/s is separate. R8's same83-input/128-output
fixture reached7.76308tok/s (+31.9% overR7), with fullstream/nativeidle evidence.
The user subsequently requested two bounded **8-decode/64-batch** comparisons:
one CPU per guest NUMA node, then eight CPUs on guest node0. Keep external
memory interleave fixed and disable GGML NUMA affinity in both so strict decode
masks are effective. Verify actual active-thread affinity. Guest node0 is not
proof of physical host GPU locality; aggregate Proxmox affinity is insufficient.
The8spread profile is the measured incumbent at9.20988outputtok/s,18.64% above16threads. Whole-window affinitydiagnostic wasINCONCLUSIVE; fourlater snapshots show the eight expected singletonguestCPUs. User now requires4spread (CPUs0,24,40,56), and2spread (0,40) onlyif4isfaster. Retain131072context,83-input/128-output fixture,64batch/GOMP0/interleave. Do notinterrupt runningR9 orhotpatch itsbounds. First4/2candidate mustwaitR9exactsettlement.
Validate maximum safe F16 allocation (target decimal1,000,000, fallback917,504)
while retaining7% freeVRAM. No cache precision change. The latest user explicitly
authorizes a near-1M occupied-context test as the FINAL independent background
job after short/native/production/Sova qualification. The reviewed final sequence
runs 4K/16K and full native tool continuation in the foreground; the last
independent job runs the pending 64K benchmark first, then near-1M only after
64K correctness, guards and full native settlement pass. Qualify production
truthfully at occupiedTested=16384; never predeclare 64K or 1M success. Report
64K running / near-1M queued at dispatch. Reserve output/template
space within the actual usable window. Verify startup, logs and safeguards,
close all paid sessions, pause monitoring and wait for the user's later nudge.
Give that job a finite eight-hour active budget; do not poll it with paid workers.
Production MiMo requests get eight hours active plus a separate 30-minute queue;
provider timeout is eight hours31minutes. Qwen and GLM retain existing limits.
The user explicitly requests a NEW4K/16K/64K ladder at final optimized settings;
the old prohibition below no longer applies to that new ladder. The 64K rung
now runs in the final independent job to avoid paid observation. Complete native
17-tool/65,536-ceiling and actual Sova delegation before primary activation.
All clients must be independent Linuxsystemd jobs with durable streamed
timestamps/results; never SIGINT/resume a CLI whose foreground tool owns a
request. One native17 response completed but its local driver was interrupted
and its terminal SSE/tool continuation was lost; it is NOT_QUALIFIED, not a
model failure. A14:54:34 Proxmox UMC capture was idle, not decode. Preserve it
and coordinate a replacement with actual native phase evidence.
R7 settled and originalGLM readiness15:14:33 was verified. R8 normal settlement
was requested15:32:36 after its completedresult and GLM restored15:34:27.
No warm adoption. R9 dispatched at16:45:04UTC using the measured eight-thread
spread profile; its existing17:17 request deadline is unchanged. The new four-thread
and conditional two-thread tests must wait for its exact physical settlement.
Retain recovery/reporting time before18:33:08. Do not hotpatch deadlines of an
already-running owner.
Qualified permanent production may remain warm. This paragraph supersedes older
15:48 checkpoint and initial131K promotion instructions below. Read latestSTATUS.

On27September the user authorized final MiMo shard verification/recovery,
native integration, warmed4K/16K/64K benchmarks and maximum-context analysis.
Original window10:48:08–13:48:08UTC. At~13:26 the user extended it by two
hours to **15:48:08UTC** for MiMo decode bottleneck investigation and targeted
optimizations. R5 completed64K, settled normally13:40:11, and restored GLM
readiness13:42:07. R6 dispatched13:58:55 with unchanged native settings and
admission15:15/settlement15:35. Its independent owner runs the reviewed short
baseline/profile pair; do not duplicate those requests. Short output-focused tests
only; no repeat large-context ladder or1M run. W1 measures actual CPU/ISA/GPU and
available hostDRAM/GPUmemory counters; W2 reviews pinned runtime and primary
sources. Distinguish GB/s counters from utilization percentages/theory. At most
two evidence-based short A/B optimizations after review, no blind rebuild or
fallback download. Prefer MiMoFlash only if Pro remains impractical and after
review; no Flash download has been dispatched. The extension supersedes old
13:48 handoff/restore instructions below.
Sova downtime is explicitly allowed. This supersedes the previous H014 hold
for a new window. Read [H016 plan](docs/h016-mimo-integration-window.md) and
local orchestration/tasks/H016-20260927/STATUS.md. Both workers execute;
root plans, reviews and publishes. Reuse the existing successful image and
verified shards. No four-way stress, BMC/fan/ECC, reboot or driver work.

H016 checkpoint: the final retained shard passed its hash at10:55:21UTC;
all13 shards /577,669,438,240bytes are verified. Reuse them and imagecdb6efd.
The cold mmap path passed text and tiny tool/continuation semantics, but suffered
severe disk paging; none of those timings is a warmed benchmark. Explicit loading
then exposed a blocking monitor diagnostic and a likely huge CUDA-host allocation.
The monitor is corrected; R5 adds only --no-host to none/interleave and loaded
at12:48:55UTC. Warmed4K,16K and64K passed at about61input/.91output tokens/s.
The65536-input run completed13:28:56 in1121.75seconds. Decode used about58
CPU-core equivalents with low sampledGPUutilization and no16K/64KstorageI/O
growth. Zen4library mapping is proven; actualCPUexpertkernel/barrier split and
DRAM/VRAMbyte rates remain pending. GuestUMC/uncorePMUs are unavailable.
Read docs/h016-mimo-results-20260927.md for measured evidence and limits.
Do not repeat completed tests or old loading attempts. MiMo harness overlay
6641df04 and the single production owner/node source passed offline checks;
host release928b3b4-h016 is staged but unactivated. Full17-tool native acceptance,
live lifecycle and application delegation remain NOT_TESTED. Receipt access
under protected /etc/ai-harness needs a narrow future correction; do not loosen
private directory permissions. Prioritize short profiling/causal optimizations
and exact final settlement/original GLM-Sova recovery by15:48:08. No late
production reload or activation without complete native and application checks.
Sova app is paused and histories/files are preserved.
The older H014 download hold below is historical; latest H016 STATUS is authority.

## Current work — 27 September 2026

User resumed after Codex updates. Root coordinates/reviews/publishes; remote
workers implement and test. Explicit current user instructions supersede older
milestone restrictions. Do not repeat completed setup or tests just because a
historical handoff still calls them pending.

Read the latest local task STATUS/HANDOFF files and the relevant repository
report before acting. Current plans: [H013](docs/h013-ecc-off-repeat.md),
[fan control](docs/h013-fan-control.md), [H014 MiMo](docs/h014-mimo-trial-plan.md).
The exact Flash 1,000,000-input-token trial PASSED at04:30:46UTC; never replay it
as a readiness test. Original evidence is immutable and archived privately.

H013 production promotion is complete: Flash1,048,576, matching Sova release
7143c17/image9ef885, plain display label, preserved chats/files, and all four
services ready at07:37UTC. ECC is off on all GPUs. The one guarded four-model
repeat stopped after50.086s at the server Qwen85C cutoff; native work settled
and normal services were restored. No further stress retry until physical
cooling improves and the user authorizes a repeat. Read the actual result in
reports/h013-ecc-off-comparison-20260927 and Sova activation receipt. The
authorized guest reboot occurred at
05:33:56UTC; newboot6535a867-8e27-49d9-8a04-4ecc1adb1e32 and all four ECC modes
Disabled/Disabled were verified. Do not reboot again without a concrete new
recovery need and review. No Proxmox reboot, GPU reset or driver update.

Integrated fan control is installed and live-tested:100% at>=70C, return to
firmware after<=65C for30s. External Server CHA_FAN3 remains user-set100% while
BMC login and all four fan GETs passed at08:36UTC after the user changed sova
to Administrator; the same probe's earlier Operator reads returned500. Actual
readback maps Zone4(CHA_FAN3) to array index3/PWMNum3/PWMSrc0, with100% duty at
20/45/65/90/100C. These are configured values, not measured instantaneous duty.
The screenshot labels CPU Package Temperature; do not substitute it for GPU
temperature. No fan write or BMC controller has been qualified/deployed. Keep
the dedicated credential privileged for this control route unless a narrower
working alternative is verified; LLM/task containers must not receive it.
Desired external policy
is100% at>=70C and50% below70C; missing/stale GPU temperature must not lower
cooling. The protected credential stays on ai-harness. No guessed PWM/IPMI writes.
Worker1 owns ai-vm; Worker2 owns BMC/ai-harness and independent acceptance.

Keep85C or the lower hardware cutoff,7% frontier GPU reserve,16GiB per Qwen,
5% Ada and15% host reserve. Stop an experiment on concrete guard failure;
no automatic thermal retry. Cooling/ECC changes together cannot isolate ECC's
thermal effect. Three Blackwells use the workstation PSU; Ada has its own PSU.
Do not equate summed GPU board power with wall/PSU power.

H014 prioritizes the best practical MiMo frontier quality, not GLM co-residency.
Root selected Pro for the first bounded trial after source review, with
MXFP4/BF16 Flash as fallback if impractical. Retain native expert precision and
BF16/F32 nonexperts; the old155.9GiB Flash artifact also quantizes attention toQ8.
Verify actual tensor metadata, source/runtime identity and memory reserves.
The isolated SM120 runtime build has passed version/help checks; MiMo has not
loaded. At08:55UTC, all577,669,438,240 expected bytes were present, but only
12/13 shards (528,287,426,336 bytes) were hash-verified. The90-minute download
job timed out at08:50:03 during the last hash check; shard12 remains a full-size
49,382,011,904-byte .partial. All owned processes settled. Do not call the
artifact verified, redownload complete files, or rebuild the successful image.
The download heartbeat is paused. The next bounded execution window starts
with verification of the retained final shard, then native load, warmed
4K/16K/64K and tool/technical checks. Review allocation/runtime before full1M.
Retain GLM and initially compare serially on the frontier GPU. Concurrent
GLM/MiMo residency is a later option to assess after MiMo1M; user then decides.
Keep paid CLI sessions closed while independent bounded jobs merely run.
Use systemd on Linux or launchd on macOS for long-lived jobs. A detached/nohup
child alone did not survive a native CLI deadline during H013. Verify the job
survives CLI exit; retain its intent and inspect actual remote state before
recovering an interrupted launcher. Never infer dispatch from a local PID alone.

The prior full guidance is retained in Git history at commit5a06690. Old
update holds, source-only phases, singleton models, ECC-on settings and historic
installer milestones do not override this current scope. Installer work stays
paused. Preserve useful rollback artifacts and historical receipts.

## Authorized sequence and ownership

- Finish working **ai-vm first**: authenticated private-network inference and
  model catalog/switching APIs, verified from another host. Then complete the
  separate frontend VM task, **then the installer**.
- **All installer work is PAUSED**, including implementation, composition and
  tests. Preserve historical installer code/evidence; no installer requirement
  or test gates current VM completion.
- Existing explicit project authorization persists. Stale milestone STOP text
  does not require redundant approval. Stay within the current bounded task and
  root-reviewed ownership/leases. Actual destructive or irreversible actions
  require explicit authorization for their exact scope; reuse authorization already
  given in this project and do not ask again. Source-only work authorizes no host
  mutation.
- Mac-Orchestrator plans, coordinates, reviews and synchronizes. Remote
  implementation/builds/tests run through fresh bounded Codex sessions in
  isolated mac-worker1/mac-worker2 copies. Worker1 owns authorized VM mutations;
  Worker2 owns independent client acceptance. Only assigned workers contact ai-vm.
- Preserve project task/status/session artifacts, prompts, session IDs, remote
  paths, bundles, results and dirty checkouts for continuation. Record checks,
  warnings, pass/fail limits and next action in the task's designated handoff;
  use `reports/` when within scope. Do not edit concurrently owned source.

## Model and evidence boundaries

- Sova separates logical models, instances and services. Current deployments
  use two Qwen3.8-27B FP8 instances at 480,000 context, one GLM-5.3-Flash
  frontier with CPU experts and a fast Blackwell, and Qwen-Image-2.1 on Ada.
  Historical full GLM and older models are retained only as documented rollback.
  Read current receipts for availability; this file is not a health check.
- Qwen coordinates and normally handles coding/agentic work. Flash is selective
  for research, many documents, hard reasoning and independent review; exceptional
  stuck coding requires explicit justification and Qwen verification. Never
  infer model superiority from size or one benchmark.
- Reuse existing llmctl, profiles and transport. Native inference remains
  authenticated on IPv4 loopback, exposed to clients only through the reviewed
  private transport/access policy. No new public/wildcard/IPv6 listener.
- Separate published, configured and actually occupied context, allocation
  checks, native inference, tool workflow and full application acceptance.
  Preserve model/runtime/tokenizer/quantization identity in results. Never use
  an old model's alias or capacity rules to disguise a new model.
- Benchmark readers must drain promptly: no lifecycle lock, full storage scan,
  full receipt rewrite or fsync per token. Heavy checks belong at boundaries,
  with separate periodic telemetry and bounded buffered checkpoints. Separate
  prefill, decode and total request time; HTTP overlap alone is not compute proof.

## Storage, lifecycle and recovery

- The protected root-owned `/etc/local-ai-server/storage.json` is storage
  authority. Verify exact registered data/model UUIDs, mounts, filesystem types,
  roots and operation paths with protected ancestry and anchored guards. Mere
  `/data` directory existence is not proof; no environment identity overrides.
- Before and after authorized downloads, builds, container/service changes or
  AI-server log/data writes, use the current root-reviewed installed registered
  storage and root-disk guards; stop on failure. Refresh installed guard/source
  identities from the current handoff. Never run stale old-checkout helper paths
  or fall back to historical guards for missing, partial or invalid registration.
  See [registered guard source](scripts/common/registered-storage.py) and the
  [path/anchored guard contract](docs/orchestration/writer-api.md) for mechanics,
  not installer authorization.
- Keep models, Hugging Face cache, Docker layers, containerd snapshots, builds,
  AI-server logs and service data off the root disk, in verified registered
  `/data` roots including the registered model mount. No model download before
  storage verification. Guard reports belong under protected registered logs.
- Reuse the [canonical lifecycle lease](scripts/common/lifecycle_lease.py) at
  `/run/llmctl/lifecycle.lock`; pass its active lease to nested lifecycle calls.
  Honor root-reviewed request/mutation ownership; no alternate lock or bypass.
  Preserve protected credentials, active/stopped intent and recovery state.
- Preserve the [D1 rollback runtime](configs/runtimes/llama-cpp-v0.4.1-d1.json),
  image and recovery evidence. Cleanup may remove only exact root-reviewed
  obsolete paths after replacement acceptance and refreshed identity/in-use
  checks; no global prune or unrelated cleanup.

## Source and credential hygiene

- Use scoped feature/milestone branches; never push directly to `main`. Confirm
  `git remote -v` has no credentials and run a local grep-based secret check
  before every push. Inspect the diff, whitespace, commit metadata and clean tree.
- Never print or commit secrets: real `.env`, tokens, passwords, private/SSH/API
  keys, sudo/auth files or service secrets. Do not dump environments or signed
  URLs, rotate keys unnecessarily, or commit weights, `MEMORY.md` or Codex memory.
- Shell scripts use `set -euo pipefail` and support `--help`. Destructive scripts
  support `--dry-run` and refuse unsafe/ambiguous states; disk changes require a
  reviewed dry-run/report before action. Scripts/configs need scoped tests or
  documented verification commands. Docs-only maintenance needs no test suite.

## Historical provenance

Earlier milestones (including M0/M2 disk rules and M5A installation STOP), old
model-selection/default-download plans and [installer records](docs/installation.md)
are historical; see [reports](reports/). Their approval gates do not supersede
current explicit authorization or gate VM completion. Coder-Next and older
models are historical/deferred, with no automatic download or activation.
Retain useful evidence and rollback artifacts without treating them as current
readiness or reopening paused installer work.
