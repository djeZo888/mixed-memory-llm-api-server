# M7B - Model Runtime Manager

- Timestamp: 2026-07-04T10:52:30+02:00
- Branch: `milestone/m7b-model-runtime-manager`
- Base branch: `main`
- Scope: scripts/docs/templates/tests only
- Conclusion: PASS for model/runtime manager abstraction if checks below pass. STOP for model downloads, backend installs/builds, Docker/containerd changes, runtime containers, services, and API exposure.

## Current System State Summary

- M0-M7A are merged into `main`.
- M7A model/runtime research passed and is merged.
- Host GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition.
- Host NVIDIA driver: `595.71.05`.
- CUDA Toolkit and `nvcc`: absent.
- Docker Root Dir: `/data/docker`.
- containerd root: `/data/containerd/root`.
- NVIDIA Container Toolkit works for the approved CUDA `nvidia-smi` container verifier.
- Model storage root: `/data/models`.
- Hugging Face cache root: `/data/hf-cache`.
- Build root: `/data/build`.
- Log root: `/data/logs`.
- Secret root: `/data/services/secrets`.

## Files Created

- `scripts/llmctl`
- `configs/models/catalog.yaml`
- `configs/models/profiles/qwen3-0.6b-smoke.yaml`
- `configs/models/profiles/qwen3-30b-a3b-instruct-2507.yaml`
- `configs/models/profiles/qwen3-235b-a22b-instruct-2507.yaml`
- `configs/models/profiles/minimax-m3.yaml`
- `configs/models/profiles/glm-5.2.yaml`
- `configs/runtimes/sglang.yaml`
- `configs/runtimes/ktransformers.yaml`
- `configs/runtimes/ik-llama.yaml`
- `configs/runtimes/vllm.yaml`
- `configs/compose/compose.sglang.template.yml`
- `configs/compose/compose.ktransformers.template.yml`
- `docs/model-runtime-manager.md`
- `tests/shell/test-llmctl-static.sh`
- `tests/shell/test-llmctl-fixtures.sh`
- `reports/m7b-model-runtime-manager.md`

## Files Updated

- `AGENTS.md`
- `.gitignore`
- `ROADMAP.md`
- `docs/current-state.md`
- `docs/model-matrix.md`
- `reports/m3-root-disk-guard.md`

## Model Profiles Created

| Profile | Role | Preferred runtime | Download policy |
| --- | --- | --- | --- |
| `qwen3-0.6b-smoke` | smoke | `sglang` | Allowed only after M8 approval; M7B plans only |
| `qwen3-30b-a3b-instruct-2507` | fast | `sglang` | Allowed after smoke approval; M7B plans only |
| `qwen3-235b-a22b-instruct-2507` | large | `sglang` | Blocked until human approval |
| `minimax-m3` | research | `ktransformers` | Blocked until human approval |
| `glm-5.2` | research | `ktransformers` | Blocked until human approval |

## Runtime Profiles Created

| Runtime | Kind | Status | Purpose |
| --- | --- | --- | --- |
| `sglang` | docker | planned | First smoke and 30B-class OpenAI-compatible path |
| `ktransformers` | hybrid | experimental | Later large MoE heterogeneous RAM+VRAM path |
| `ik-llama` | native | experimental | Later GGUF/quantized fallback path |
| `vllm` | docker | planned | Later cross-check backend |

## Manager Commands Implemented

- `llmctl --help`
- `llmctl doctor`
- `llmctl list-models`
- `llmctl list-runtimes`
- `llmctl show-model <name>`
- `llmctl show-runtime <name>`
- `llmctl validate`
- `llmctl active`
- `llmctl plan-activate <model-profile> --runtime <runtime>`
- `llmctl activate <model-profile> --runtime <runtime> --dry-run`
- `llmctl deactivate --dry-run`
- `llmctl status`
- `llmctl logs --dry-run`
- `llmctl plan-download <model-profile>`
- `llmctl env`

Real `download`, `start`, `stop`, and `restart` actions stop in M7B.

## Validation And Safety Behavior

- Profiles are declarative YAML.
- `scripts/llmctl` uses Python standard library only; no Python packages were installed.
- Metadata commands do not require host GPU/Docker checks.
- Runtime/download planning commands validate profiles and use required guards.
- Mutating commands require `--dry-run`.
- Real activation/deactivation/download remains blocked.
- Backends bind to `127.0.0.1` by default in templates.
- Manager state is reserved for `/data/services/llm-manager/state`.
- The manager does not read or print secret values and does not read `/data/services/secrets` contents.

## Tests And Checks Run

Baseline:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
```

Manager commands:

```bash
scripts/llmctl --help
scripts/llmctl doctor
scripts/llmctl list-models
scripts/llmctl list-runtimes
scripts/llmctl validate
scripts/llmctl plan-download qwen3-0.6b-smoke
scripts/llmctl plan-activate qwen3-0.6b-smoke --runtime sglang
scripts/llmctl activate qwen3-0.6b-smoke --runtime sglang --dry-run
```

Shell tests:

```bash
bash -n tests/shell/test-llmctl-static.sh
bash -n tests/shell/test-llmctl-fixtures.sh
tests/shell/test-llmctl-static.sh
tests/shell/test-llmctl-fixtures.sh
git diff --check
```

Secret scan:

```bash
grep -RInE "(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)" . --exclude-dir=.git || true
```

Result: matched only intentional docs/test/safety/report strings, including static-test patterns and report command text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, local Codex memory files, or model credentials were identified.

## No Runtime Changes

Confirmed for M7B:

- No models were downloaded.
- No backend software was installed.
- No SGLang, KTransformers, vLLM, ik_llama, PyTorch, or CUDA Toolkit package was installed.
- No backend Docker image was pulled.
- No model container was run.
- No API was exposed.
- Docker/containerd config was not modified.
- Docker/containerd were not restarted.
- Disks, fstab, mountpoints, and systemd were not touched outside repo docs/templates.

## PASS/STOP

PASS:

- Model/runtime manager abstraction exists.
- Profiles validate.
- Dry-run planning works.
- Tests cover static safety and fixture behavior.

STOP:

- Real model download remains blocked.
- Real backend activation remains blocked.
- Backend installation/build remains blocked.
- API exposure remains blocked.

Next recommended task: M8A SGLang smoke-model deployment planning/dry-run after M7B review and merge.
