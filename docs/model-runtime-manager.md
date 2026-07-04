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

M7B does not write real activation state. Future milestones may write state there after they add approved activation/deactivation behavior.

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

M7B requires `--dry-run` for mutating commands. Real activation, deactivation, download, runtime start, runtime stop, and API exposure all stop in M7B.

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

## Future API Integration

Backends must bind to `127.0.0.1` by default. A later API front door can route to the one active backend while keeping the external contract stable. Public or LAN exposure remains blocked until authentication, firewall, and TLS policy are reviewed.

The intended sequence is:

1. M7B: manager abstraction and dry-run planning only.
2. M8A: SGLang smoke-model deployment planning/dry-run.
3. M8B or later: approved smoke-model download and localhost runtime test.
4. M9: first real fast model benchmark.
5. M10: large model experiments one at a time.
