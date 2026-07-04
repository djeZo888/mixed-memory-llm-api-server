# M7A Main Merge Report

- Timestamp: 2026-07-04T00:53:06+02:00
- Source branch: `milestone/m7a-model-runtime-research`
- Target branch: `main`
- Merge commit: `e4f5dbf6ad2680d3a96965bd7083c03bdc2e5081`
- M7A source commit: `e63756941be4e1401deac301cecf72f5275b015a`
- Merge subject: `merge M7A model runtime research`

## Summary

M7A model/runtime research was merged into `main` with a no-ff merge commit. M7A was research/report only and did not download models, install backend packages, build runtimes, modify Docker/containerd configuration, create services, expose APIs, or touch disks/fstab/mountpoints/systemd.

Human decision after review: do not lock a final model yet. The next milestone should build a model/runtime manager abstraction that supports several model/runtime profiles while allowing only one active model/backend at a time.

## Shortlist Carried Forward

Top 3 large/high-quality candidates:

- `Qwen/Qwen3-235B-A22B-Instruct-2507`
- `MiniMaxAI/MiniMax-M3`
- `zai-org/GLM-5.2`

Top 3 smaller/faster candidates:

- `Qwen/Qwen3-30B-A3B-Instruct-2507`
- `Qwen/Qwen3.6-35B-A3B`
- `Qwen/Qwen3-30B-A3B-Thinking-2507`

Recommended smoke model:

- `Qwen/Qwen3-0.6B`

Recommended first real model:

- `Qwen/Qwen3-30B-A3B-Instruct-2507`

Recommended first backend:

- SGLang Docker profile

Large heterogeneous MoE path:

- KTransformers/KT-Kernel for large mixed RAM+VRAM experiments after M7B defines the manager/profile abstraction.

## Checks Run

Git identity:

```bash
git config --show-origin --get-regexp '^user\.(name|email)$' || true
git config --global --show-origin --get-regexp '^user\.(name|email)$' || true
```

Source branch verification:

```bash
git fetch origin
git checkout milestone/m7a-model-runtime-research
git pull --ff-only origin milestone/m7a-model-runtime-research
git status
```

Read-only guards:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
git diff --check
```

Merge:

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff milestone/m7a-model-runtime-research -m "merge M7A model runtime research"
git show -s --format='commit=%H%nAuthor=%an <%ae>%nCommitter=%cn <%ce>%nSubject=%s' e4f5dbf6ad2680d3a96965bd7083c03bdc2e5081
git push origin main
```

## Check Results

- Git identity: PASS, effective repo/global email is `133749519+djeZo888@users.noreply.github.com`.
- Source branch: PASS, source branch was up to date with `origin/milestone/m7a-model-runtime-research`.
- `/data` mount guard: PASS.
- Root-disk guard: PASS.
- Docker/containerd storage verification: PASS.
- GPU container verification: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`; both RTX PRO 6000 Blackwell GPUs were visible in the container.
- `git diff --check`: PASS.
- Merge conflicts: none.
- Merge commit attribution: PASS; author and committer are `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.

## Secret Scan Result

Command:

```bash
grep -RInE "(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)" . --exclude-dir=.git || true
```

Result: the scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, prior report, and scan-pattern strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, local Codex memory files, or model credentials were identified.

## No Runtime Changes

Confirmed:

- No model weights were downloaded.
- No backend software was installed.
- No CUDA Toolkit, PyTorch, KTransformers, ik_llama, vLLM, or SGLang package was installed.
- No Docker/containerd config was modified.
- Docker/containerd were not restarted.
- No service was created.
- No API was exposed.
- No disks, fstab, mountpoints, or systemd units were changed.

## PASS/STOP

PASS: M7A is merged into `main`, and the research shortlist is now part of the main branch.

STOP: Model downloads, backend installs/builds, runtime services, Docker/containerd changes, and API exposure remain blocked until explicitly approved by later milestones.

Next recommended milestone: M7B model/runtime manager abstraction.
