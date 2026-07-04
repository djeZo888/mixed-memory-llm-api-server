# M8A Main Merge Report

- Timestamp: `2026-07-04T15:16:24Z`
- Source branch: `milestone/m8a-sglang-smoke-plan`
- Target branch: `main`
- Merge commit hash: `a43c9a6d00c7bc1115a609809c2a417b637115f4`
- M8A source commit hash: `fda5e3c7a910e064fa2b34b76a5711fb56d3b1fa`

## Summary

M8A SGLang smoke-model deployment planning/dry-run was merged into `main` with a no-fast-forward merge. M8A remains planning-only. It added the SGLang smoke Compose template, environment placeholder, dry-run planning and verification scripts, OpenAI-compatible local API smoke script, static tests, deployment documentation, and `reports/m8a-sglang-smoke-plan.md`.

## Planned Smoke Runtime

- Proposed SGLang image tag: `lmsysorg/sglang:v0.5.14-cu130-runtime`
- linux/amd64 digest recorded by M8A: `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`
- Digest rule: M8B must verify the linux/amd64 digest again before any pull or run.
- Smoke model: `Qwen/Qwen3-0.6B`
- Model license: Apache-2.0
- Context length: `32768`
- Planned local model path: `/data/models/qwen3-0.6b-smoke`
- Planned bind/port: `127.0.0.1:30000`
- Planned endpoint: `http://127.0.0.1:30000/v1/chat/completions`

## Manager/Profile Integration

- Model profile: `qwen3-0.6b-smoke`
- Runtime profile: `sglang`
- `scripts/llmctl validate` passed.
- `scripts/llmctl active` reported `active: none`.
- `scripts/llmctl status` remained `planning_only` with `active: none`.
- M8A added smoke-specific planning around `127.0.0.1:30000`; the generic M7B SGLang runtime profile remains a reusable runtime profile.

## Tests And Checks Run Before Merge

- `git config --show-origin --get-regexp '^user\.(name|email)$' || true`
- `git config --global --show-origin --get-regexp '^user\.(name|email)$' || true`
- `git fetch origin`
- `git checkout milestone/m8a-sglang-smoke-plan`
- `git pull --ff-only origin milestone/m8a-sglang-smoke-plan`
- `scripts/common/require-data-mounted.sh`
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- `scripts/docker/verify-docker-storage.sh`
- `scripts/nvidia/verify-gpu-containers.sh`
- `scripts/llmctl doctor`
- `scripts/llmctl validate`
- `scripts/llmctl active`
- `scripts/llmctl show-model qwen3-0.6b-smoke`
- `scripts/llmctl show-runtime sglang`
- `scripts/llmctl plan-download qwen3-0.6b-smoke`
- `scripts/llmctl plan-activate qwen3-0.6b-smoke --runtime sglang`
- `scripts/llmctl activate qwen3-0.6b-smoke --runtime sglang --dry-run`
- `bash -n scripts/sglang/plan-sglang-smoke.sh`
- `bash -n scripts/sglang/verify-sglang-smoke-plan.sh`
- `bash -n scripts/api/smoke-openai-chat.sh`
- `bash -n tests/shell/test-sglang-smoke-static.sh`
- `tests/shell/test-sglang-smoke-static.sh`
- `scripts/sglang/plan-sglang-smoke.sh --dry-run`
- `scripts/sglang/verify-sglang-smoke-plan.sh`
- `scripts/api/smoke-openai-chat.sh --dry-run`
- `git diff --check`
- Grep-based secret scan
- `git checkout main`
- `git pull --ff-only origin main`
- `git merge --no-ff milestone/m8a-sglang-smoke-plan -m "merge M8A SGLang smoke plan"`
- Merge commit attribution check
- `git push origin main`

## Secret Scan Result

The grep-based scan matched only intentional documentation, placeholders, static-test/sanitizer patterns, historical report text, and safety strings. No real token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory file was identified.

## No-Action Confirmation

No model download, Hugging Face download, `git-lfs` download, SGLang image pull, SGLang/model/backend container run, backend install, Docker/containerd config change, Docker/containerd restart, service creation, or API exposure occurred. Only the existing approved GPU verifier CUDA `nvidia-smi` container checks ran.

## Result

PASS.

## Next Recommended Milestone

M8B actual localhost-only SGLang smoke deployment after human review in a fresh context.
