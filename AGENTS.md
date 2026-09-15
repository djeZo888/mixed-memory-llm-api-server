# AGENTS.md

Current guidance for agents and operators. Read the
[current scope and ownership checkpoint](docs/orchestration/2026-09-15-status.md)
and the relevant task handoff before work; preserve their evidence boundaries.

## Authorized sequence and ownership

- Finish working **ai-vm first**: authenticated private-network inference and
  model catalog/switching APIs, verified from another host. Then complete the
  separate frontend VM task, **then the installer**.
- **All installer work is PAUSED**, including implementation, composition and
  tests. Preserve historical installer code/evidence; no installer requirement
  or test gates current VM completion.
- Existing explicit project authorization persists. Stale milestone STOP text
  does not require redundant approval. Stay within the current bounded task and
  root-reviewed ownership/leases; actual destructive or irreversible actions
  still require approval. Source-only work authorizes no host mutation.
- Mac-Orchestrator plans, coordinates, reviews and synchronizes. Remote
  implementation/builds/tests run through fresh bounded Codex sessions in
  isolated mac-worker1/mac-worker2 copies. Worker1 owns authorized VM mutations;
  Worker2 owns independent client acceptance. Only assigned workers contact ai-vm.
- Preserve project task/status/session artifacts, prompts, session IDs, remote
  paths, bundles, results and dirty checkouts for continuation. Record checks,
  warnings, pass/fail limits and next action in the task's designated handoff;
  use `reports/` when within scope. Do not edit concurrently owned source.

## VM role, models and evidence

- ai-vm is API-only, with an OpenAI-compatible inference contract and one active
  model/backend at a time. Tools, browsing, scraping, browser automation and
  agents run on clients as an explicit ordinary user in a trusted workspace;
  human chat UI belongs on the separate frontend VM.
- Exactly two current model identities: **GLM5.3 UD-Q4_K_XL** flagship and
  **Qwen3.8-27B FP8** fast model. No automatic downloads or activations.
- Use [`scripts/llmctl`](scripts/llmctl) and declarative
  [model](configs/models/) and [runtime](configs/runtimes/) profiles. Keep the
  architecture extensible without hard-coding a model, quantization, backend,
  host or port into deployment logic. Prefer official implementation sources.
- Aim for the highest practical supported context capacity on the hardware.
  Distinguish declared capacity, configured capacity and measured occupied
  context. Neither 32K nor a 2048-token test output budget is a product limit;
  source/build checks do not establish accepted native 1M context.
- Runtime/model readiness, direct API behavior and current profile status must
  come from durable reviewed/current evidence, never this guidance snapshot.
  Source checks are not live inference, agent, context or installation acceptance.
- Native API listeners remain authenticated IPv4 loopback (`127.0.0.1`). Frontend
  clients use reviewed private transport and explicit protected access policy,
  including API-key authentication and documented firewall/TLS policy. No public,
  wildcard or IPv6 exposure; reuse reviewed modules without a new policy framework.

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
