# AGENTS.md

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

H013 continues durable Flash1,048,576 production promotion, matching Sova
configuration/plain display label, ECC off on all three Blackwells (Ada off),
and one guarded four-model repeat. The authorized guest reboot occurred at
05:33:56UTC; newboot6535a867-8e27-49d9-8a04-4ecc1adb1e32 and all four ECC modes
Disabled/Disabled were verified. Do not reboot again without a concrete new
recovery need and review. No Proxmox reboot, GPU reset or driver update.

Integrated fan control is installed and live-tested:100% at>=70C, return to
firmware after<=65C for30s. External Server CHA_FAN3 remains user-set100% while
BMC web-session authentication/mapping is unresolved. Desired external policy
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
After H013 settles, proceed with the selected pinned SM120 mixed CPU/GPU runtime, warmed
4K/16K/64K and tool/technical checks. Review allocation/runtime before full1M.
Retain GLM and initially compare serially on the frontier GPU. Concurrent
GLM/MiMo residency is a later option to assess after MiMo1M; user then decides.
Keep paid CLI sessions closed while independent bounded jobs merely run.

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
