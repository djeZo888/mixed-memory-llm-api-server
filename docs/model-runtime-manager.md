# Model Runtime Manager

M7B adds a model/runtime manager abstraction without downloading models, installing backends, building runtimes, starting services, or exposing an API. The goal is to make model and backend selection data-driven so future milestones can add profiles without rewriting deployment logic.

## Why The Model Choice Is Not Final

M7A found several viable model/runtime paths with different tradeoffs. The smoke path should be small and low risk, the first real path should be fast enough to benchmark, and large MoE paths need separate memory and runtime proof. Locking one final model now would make the system brittle and would force later large-model experiments to rewrite scripts.

The current policy is:

- Keep several model profiles available.
- Keep several runtime profiles available.
- Allow only one active model/backend at a time.
- Keep the future API front door stable while the active profile changes behind it.

## One-Active-Model Policy

Only one model/runtime pair should be active at once. This prevents GPU/RAM contention, avoids ambiguous API routing, and makes logs and benchmark results easier to interpret.

The manager state root is:

```text
/data/services/llm-manager/state
```

The active state root is:

```text
/data/services/llm-manager/active
```

M8C manages the already deployed SGLang smoke backend through `/data/services/llm-manager/active/active.json`. New model activation remains guarded for later milestones.

## Model Profiles

Model profiles live under:

```text
configs/models/profiles/
```

Each profile declares the model identity, provider, Hugging Face repository, role, model type, parameter counts, context window, license, estimated storage, minimum memory expectations, preferred runtimes, download policy, notes, and source URLs.

The model catalog is:

```text
configs/models/catalog.yaml
```

The first intended smoke profile after M7B is:

```text
qwen3-0.6b-smoke
```

The first intended real model after smoke is:

```text
qwen3-30b-a3b-instruct-2507
```

Large model profiles remain blocked for download until human review approves storage, memory, and runtime plans.

## Runtime Profiles

Runtime profiles live under:

```text
configs/runtimes/
```

Each runtime profile declares the runtime name, kind, status, OpenAI compatibility, localhost default, GPU requirement, heterogeneous RAM+VRAM capability, config template, healthcheck path, default port, risks, and source URLs.

The first intended runtime is SGLang through a pinned Docker profile selected later. KTransformers/KT-Kernel is kept as the second path for large heterogeneous MoE experiments. vLLM remains a cross-check option, and ik_llama is the GGUF/quantized fallback path.

LiteLLM or another gateway can be evaluated later, but it is optional and not required for M7B.

## Activation Plan

The manager supports planning commands such as:

```bash
scripts/llmctl plan-activate qwen3-0.6b-smoke --runtime sglang
scripts/llmctl activate qwen3-0.6b-smoke --runtime sglang --dry-run
```

The plan validates the model and runtime profiles, checks storage and GPU prerequisites, confirms localhost binding policy, and prints the mounts and paths that would be used later.

M7B required `--dry-run` for mutating commands. M8C keeps new model activation and downloads guarded, but allows lifecycle operations for the already deployed smoke backend.

## M8C Smoke Lifecycle Commands

M8C adds lifecycle commands for the existing `qwen3-0.6b-smoke` SGLang deployment only:

```bash
scripts/llmctl status
scripts/llmctl active
scripts/llmctl logs --dry-run
scripts/llmctl logs --yes
scripts/llmctl stop --dry-run
scripts/llmctl stop --yes
scripts/llmctl start --dry-run
scripts/llmctl start --yes
scripts/llmctl restart --dry-run
scripts/llmctl restart --yes
scripts/llmctl deactivate --dry-run
scripts/llmctl deactivate --yes
```

Every mutating lifecycle command requires `--yes`. Without `--yes`, the command stops and prints the matching dry-run command. `logs --yes` prints recent logs for the active smoke container; `logs --dry-run` prints the exact `docker logs` command without reading logs.

`stop --yes` stops the smoke container and updates `active.json` to `status: stopped`. It does not delete model files, Docker images, or Docker data.

`start --yes` starts the existing smoke deployment from `/data/services/llm-manager/compose/sglang-smoke.compose.yml`, verifies `/data`, Docker storage, Docker Root Dir, GPU containers, compose localhost binding, model files, and port ownership, then updates `active.json` to `status: active`.

`restart --yes` performs a guarded stop/start cycle and updates `active.json` with `status: active` and `restarted_at`.

`deactivate --yes` runs compose `down` for the smoke deployment only, then moves active state to:

```text
/data/services/llm-manager/active/history/active-YYYYMMDD-HHMMSS.json
```

It leaves no active model. It must not delete model files, remove images, or run Docker prune.

`deactivate` and `stop` are intentionally different:

- `stop` keeps the smoke deployment selected but stopped, so `start --yes` can bring it back.
- `deactivate` archives `active.json` and leaves no active backend selected.

`scripts/llmctl active` reads `active.json` and warns when the recorded state is stale, such as `status: active` with no running container, or `status: stopped` while port `30000` is listening. Manual Docker commands can therefore make state stale until `llmctl` updates it again.

## Why M7B Does Not Download Models

M7B is a manager abstraction milestone. Downloading even the smoke model would mix policy/script work with model storage and runtime work. Downloads are deferred so M8 can verify cache placement, model placement, logs, auth, API behavior, and rollback as a focused deployment milestone.

Required storage policy for later downloads:

- Models: `/data/models`
- Hugging Face cache: `/data/hf-cache`
- Logs: `/data/logs`
- Build artifacts: `/data/build`
- Secrets: `/data/services/secrets`

The manager must never read or print secret values.

## Adding A New Model

To add a model later:

1. Add one YAML profile under `configs/models/profiles/`.
2. Add the profile name to `configs/models/catalog.yaml`.
3. List only runtimes that are plausible for that model.
4. Set `allowed_first_download` to `false` unless the human has approved the first download path.
5. Run `scripts/llmctl validate`.
6. Add or update tests if the profile needs new policy behavior.

No deployment logic should need hard-coded model names beyond tests and documentation.


## M8A SGLang Smoke Plan

M8A keeps `qwen3-0.6b-smoke` as the smoke model profile and `sglang` as the preferred smoke runtime. The smoke-specific deployment plan lives in:

```text
configs/compose/compose.sglang-smoke.template.yml
configs/sglang/smoke.env.example
scripts/sglang/plan-sglang-smoke.sh
scripts/sglang/verify-sglang-smoke-plan.sh
scripts/api/smoke-openai-chat.sh
```

The planned M8B local model path is `/data/models/qwen3-0.6b-smoke`, the planned cache root is `/data/hf-cache`, the planned log directory is `/data/logs/sglang-smoke`, and the planned local endpoint is `http://127.0.0.1:30000/v1/chat/completions`.

M8A proposes `lmsysorg/sglang:v0.5.14-cu130-runtime` for human review. M8B must still pull and verify the exact digest after approval. No final large model is selected.

## Future API Integration

Backends must bind to `127.0.0.1` by default. A later API front door can route to the one active backend while keeping the external contract stable. Public or LAN exposure remains blocked until authentication, firewall, and TLS policy are reviewed.

The intended sequence is:

1. M7B: manager abstraction and dry-run planning only.
2. M8A: SGLang smoke-model deployment planning/dry-run for `qwen3-0.6b-smoke` on SGLang.
3. M8B or later: approved smoke-model download and localhost runtime test on `127.0.0.1:30000`.
4. M9: first real fast model benchmark.
5. M10: large model experiments one at a time.
