# Current State

This file is the compact source-of-truth handoff for future Codex and ChatGPT sessions.

## Project

- Repo SSH URL: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Public URL: `https://github.com/djeZo888/mixed-memory-llm-api-server`
- Repo path on VM: `/data/services/mixed-memory-llm-api-server`
- Target VM: `ai-vm / 10.156.100.60`
- Hostname: `llmserver`
- User: `user`
- OS: Ubuntu 24.04.4 LTS
- Project state: M0-M9B merged into `main`; M9C benchmark/lifecycle/resource review is complete on branch `milestone/m9c-real-model-benchmark-review` and ready for human review. Active backend remains `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang at `http://127.0.0.1:30001/v1`, bound to `127.0.0.1` only. Public API exposure is still not configured; M10 API/front-door/auth planning is next after M9C review/merge.

## Git Attribution

Future commits must use:

```text
CodexAIagent <133749519+djeZo888@users.noreply.github.com>
```

Old commits were previously attributed incorrectly due to this placeholder email:

```text
12345678+djeZo888@users.noreply.github.com
```

Old history was not rewritten. Do not create new commits unless Git config uses the correct email. M4B was squash-merged into `main` after attribution was fixed.

## Completed Milestones

- M0 repo bootstrap: merged
- M1 VM preflight: merged
- M2 data disk setup: merged
- M3 root-disk guard: merged
- M4A Docker/containerd plan: merged
- M5A CUDA/NVIDIA compatibility gate: merged
- M4B Docker/containerd install: squash-merged by this task
- M5A CUDA/NVIDIA compatibility research: merged into main
- M5B NVIDIA host driver: passed and merged into main
- M6A NVIDIA Container Toolkit planning/dry-run: merged into `main` with corrected future test image `nvidia/cuda:13.2.1-base-ubuntu24.04`
- M6B NVIDIA Container Toolkit install: merged into `main`; pre-reboot install, GPU container test, guest reboot, and post-reboot verification passed
- M7A model/runtime research: merged into `main`; research-only report is `reports/m7a-model-runtime-research.md`
- M7A main merge report: `reports/m7a-main-merge.md`
- M7B model/runtime manager abstraction: merged into `main`; dry-run/planning report is `reports/m7b-model-runtime-manager.md`
- M7B main merge report: `reports/m7b-main-merge.md`
- M8A SGLang smoke deployment plan: merged into `main`; planning/dry-run only, report is `reports/m8a-sglang-smoke-plan.md`
- M8A main merge report: `reports/m8a-main-merge.md`
- M8B SGLang smoke deployment: merged into `main` after full-image remediation; report is `reports/m8b-sglang-smoke-deploy.md`
- M8B main merge report: `reports/m8b-main-merge.md`
- M8C smoke lifecycle manager: merged into `main`; report is `reports/m8c-smoke-lifecycle-manager.md`
- M8C main merge report: `reports/m8c-main-merge.md`
- M9A first real fast-model plan: merged into `main`; report is `reports/m9a-first-real-fast-model-plan.md`
- M9A main merge report: `reports/m9a-main-merge.md`
- M9B first real fast-model deployment: merged into `main`; deployment report is `reports/m9b-first-real-fast-model-deploy.md`; main merge report is `reports/m9b-main-merge.md`
- M9C real model benchmark/lifecycle/resource review: complete on branch `milestone/m9c-real-model-benchmark-review`; report is `reports/m9c-real-model-benchmark-review.md`; benchmarking doc is `docs/real-model-benchmarking.md`

## Current Storage

- Root filesystem: ext4 on `/dev/mapper/ubuntu--vg-ubuntu--lv`, about 15G
- `/data`: `/dev/sdb1`, ext4, label `AI_DATA`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`
- `/data` is mounted by UUID in `/etc/fstab`
- Required `/data` directories exist:
  - `/data/models`
  - `/data/hf-cache`
  - `/data/docker`
  - `/data/containerd`
  - `/data/services`
  - `/data/build`
  - `/data/logs`
  - `/data/backups`
  - `/data/services/secrets`

## Current Docker/Containerd

- Docker: `29.6.1`
- containerd: `v2.2.5`
- Docker Compose: `v5.3.0`
- Docker Root Dir: `/data/docker`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- `/var/lib/docker`: absent
- `/var/lib/containerd`: absent
- `/data/docker` may be mode `0710` and is Docker-managed
- `/data/containerd` root/state policy is documented
- `hello-world`: passed
- `user` was not added to the `docker` group
- NVIDIA Container Toolkit is installed:
  - `nvidia-container-toolkit 1.19.1-1`
  - `nvidia-container-toolkit-base 1.19.1-1`
  - `libnvidia-container-tools 1.19.1-1`
  - `libnvidia-container1 1.19.1-1`
- `nvidia-ctk`: `/usr/bin/nvidia-ctk`, `NVIDIA Container Toolkit CLI version 1.19.1`
- Docker runtimes include `nvidia`; default runtime remains `runc`
- Docker daemon config backup from M6B: `/etc/docker/daemon.json.pre-m6b-nvidia-container-toolkit.20260703T162043Z.bak`
- M6A confirms Docker Root Dir remains `/data/docker`
- M6A confirms containerd root remains `/data/containerd/root`


## Current GPU Driver State

- M5A is merged into `main`.
- M5A execution report: `reports/m5a-cuda-nvidia-compatibility.md`.
- M5A main merge and pre-M5B handoff report: `reports/m5a-main-merge.md`.
- M5B host NVIDIA driver installation passed with Ubuntu `nvidia-driver-595-open` / `nvidia-utils-595`.
- M5B execution report: `reports/m5b-nvidia-host-driver.md`.
- M5B main merge report: `reports/m5b-main-merge.md`.
- Installed NVIDIA driver version: `595.71.05`.
- `nvidia-smi -L` reports exactly two GPUs:
  - GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:01:00.0`, memory `97887 MiB`.
  - GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:02:00.0`, memory `97887 MiB`.
- No RTX 6000 Ada is expected or reported.
- `nouveau` is not loaded or bound to the GPUs; the NVIDIA driver is bound.
- `nvcc` is absent.
- CUDA Toolkit is absent.
- NVIDIA Container Toolkit is installed and Docker runtime configuration is present.
- `nvidia-ctk` is installed.
- Approved CUDA container test image `nvidia/cuda:13.2.1-base-ubuntu24.04` passed. GPU container verification passed again during M8A merge validation.
- The CUDA container saw exactly two NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPUs with `97887 MiB` each.
- M6B pulled and ran `nvidia/cuda:13.2.1-base-ubuntu24.04` for `nvidia-smi` only.
- Host CUDA Toolkit and `nvcc` remain absent.
- PyTorch, KTransformers, ik_llama, models, and API exposure remain blocked until their approved milestones.
- M7A did not install PyTorch, KTransformers, ik_llama, vLLM, SGLang, CUDA Toolkit, model weights, backend services, or API exposure.
- Human Proxmox review: VM 120 has `hostpci0: 0000:c1:00,pcie=1,rombar=1` and `hostpci1: 0000:e1:00,pcie=1,rombar=1`, with parent snapshot `before-m5b-nvidia-driver-595-open`; `qm status 120` reports running.
- Proxmox host logs show VFIO reset activity with reset-done lines during VM stop/start/reboot.
- Proxmox host logs show correctable PCIe AER Data Link Layer events around GPU reset/start activity, especially root port `0000:e0:01.1`; human decision: monitor after M6/M7/load tests, but not a blocker for M6.
- QEMU Guest Agent status after M5B merge: human Proxmox host check `qm agent 120 ping` returned no output and produced no new guest-ping warning, so QGA currently works. Older guest-ping timeouts are documented as historical/temporary, not a current blocker.
- Live snapshots with VFIO GPUs remain disallowed because prior logs showed `VFIO migration is not supported in kernel`; use stopped/offline snapshots unless explicitly tested and approved.

## Guardrails

- Run `scripts/common/require-data-mounted.sh` before heavy work.
- Run `scripts/common/root-disk-guard.sh` before and after Docker, model, build, log, or service work.
- Run `scripts/docker/verify-docker-storage.sh` after Docker/containerd changes.
- Do not install NVIDIA/CUDA/PyTorch GPU/KTransformers GPU/ik_llama CUDA/NVIDIA Container Toolkit before M5A compatibility research passes and the human approves the selected version matrix.
- Do not download additional models before the relevant milestone explicitly approves the model, path, cache, runtime, and verification sequence.
- Do not expose API without authentication/firewall review.
- Do not commit secrets.
- M7A is a research gate only. It does not approve model downloads, backend installs/builds, service creation, Docker/containerd changes, restarts, or API exposure.
- M7B is a dry-run/planning manager gate only. It added profiles, templates, docs, and tests, but does not approve model downloads, backend installs/builds, Docker image pulls, runtime containers, service creation, Docker/containerd changes, restarts, or API exposure.

## Current M7A Result

- M7A report: `reports/m7a-model-runtime-research.md`.
- M7A was merged into `main` with merge commit `e4f5dbf6ad2680d3a96965bd7083c03bdc2e5081`.
- M7A main merge report: `reports/m7a-main-merge.md`.
- PASS for research and shortlist.
- STOP for downloads, backend installs/builds, service creation, Docker/containerd changes, restarts, and API exposure until a later approved milestone explicitly expands scope.
- Human decision: model choice is intentionally not final. The system should support several model/runtime profiles and allow only one active model/backend at a time.
- M7B must build a model/runtime manager abstraction, not a single hard-coded model path.
- Top large/high-quality candidates:
  - `Qwen/Qwen3-235B-A22B-Instruct-2507`
  - `MiniMaxAI/MiniMax-M3`
  - `zai-org/GLM-5.2`
- Large feasibility comparator:
  - `deepseek-ai/DeepSeek-V4-Flash`
- Top smaller/faster candidates:
  - `Qwen/Qwen3-30B-A3B-Instruct-2507`
  - `Qwen/Qwen3.6-35B-A3B`
  - `Qwen/Qwen3-30B-A3B-Thinking-2507`
- Coding-specific alternate:
  - `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Recommended first download after approval: `Qwen/Qwen3-0.6B` for smoke testing only.
- Recommended first real model after smoke: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Recommended first backend to implement in M7B: pinned, localhost-only SGLang Docker profile with all model/cache/log/build paths under `/data`.
- KTransformers/KT-Kernel remains the large-MoE heterogeneous RAM+VRAM path to prototype after SGLang smoke is defined.
- The manager should make new model profiles easy to add without changing the API contract or hard-coding one backend/model into scripts.
- QGA is currently working based on human Proxmox host verification with `qm agent 120 ping`; older guest-ping timeouts are historical/temporary and not a current blocker.
- Future work must not configure containerd NVIDIA runtime, install CUDA Toolkit, install PyTorch, install KTransformers, install ik_llama, download models, configure inference backends, or expose API unless explicitly expanded by the relevant milestone.

## Current M7B Result

- M7B report: `reports/m7b-model-runtime-manager.md`.
- M7B was merged into `main` with merge commit `dc32c8239baf1bcf9cd38c1e57939bb268364969`.
- M7B main merge report: `reports/m7b-main-merge.md`.
- `scripts/llmctl` exists and supports metadata, validation, planning, dry-run activation, dry-run deactivation, status, logs dry-run, download planning, and environment inspection commands.
- Model profiles exist under `configs/models/profiles/`:
  - `qwen3-0.6b-smoke`
  - `qwen3-30b-a3b-instruct-2507`
  - `qwen3-235b-a22b-instruct-2507`
  - `minimax-m3`
  - `glm-5.2`
- Runtime profiles exist under `configs/runtimes/`:
  - `sglang`
  - `ktransformers`
  - `ik-llama`
  - `vllm`
- Only one model/backend should be active at once.
- Model choice is intentionally not final.
- New models should be added as declarative profiles instead of hard-coding model-specific behavior into deployment logic.
- M7B did not download models, install backends, pull backend Docker images, run model/backend containers, expose API, modify Docker/containerd config, restart Docker/containerd, or create services.


## Current M8A Result

- M8A is merged into `main` with merge commit `a43c9a6d00c7bc1115a609809c2a417b637115f4`.
- M8A source commit: `fda5e3c7a910e064fa2b34b76a5711fb56d3b1fa`.
- M8A report: `reports/m8a-sglang-smoke-plan.md`.
- M8A main merge report: `reports/m8a-main-merge.md`.
- SGLang smoke deployment doc: `docs/sglang-smoke-deployment.md`.
- M8A completed as planning/dry-run only.
- Active model/backend remains none.
- `scripts/llmctl status` remains `planning_only` with `active: none`.
- Proposed pinned SGLang image for M8B review: `lmsysorg/sglang:v0.5.14-cu130-runtime`.
- linux/amd64 digest recorded by M8A: `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`.
- M8B must verify the linux/amd64 digest before any pull or run.
- Smoke model: `Qwen/Qwen3-0.6B`.
- Smoke model license: Apache-2.0.
- Smoke model context length: `32768`.
- Model profile: `qwen3-0.6b-smoke`.
- Runtime profile: `sglang`.
- Planned local model path: `/data/models/qwen3-0.6b-smoke`.
- Planned localhost bind: `127.0.0.1:30000`.
- Planned OpenAI-compatible endpoint: `/v1/chat/completions` at `http://127.0.0.1:30000/v1/chat/completions`.
- Backend remains localhost-only.
- No public API exposure is allowed in M8.
- No model was downloaded by M8A.
- No SGLang image was pulled by M8A.
- No backend is running from M8A.
- No API was exposed by M8A.

## Current M8B Result

- M8B branch: `milestone/m8b-sglang-smoke-deploy`.
- M8B source commit: `e204955f9268a2124f0590c80a30e1f0ad8b6fa2`.
- M8B merged into `main` with merge commit `2330b8b432243cea6ddc6effc1fb60065d7d1759`.
- M8B main merge report: `reports/m8b-main-merge.md`.
- Pre-M9 handoff: `docs/pre-m9-handoff.md`.
- M8B report: `reports/m8b-sglang-smoke-deploy.md`.
- Result: PASS after remediation.
- The linux/amd64 digest for `lmsysorg/sglang:v0.5.14-cu130-runtime` was re-verified as `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`.
- The pinned image was pulled successfully; Docker stores the tag under repo digest `lmsysorg/sglang@sha256:9e436f44523e9f53519c6175fefd1e0d373322bf54b8154bb331a2f5e4840ad2`.
- `Qwen/Qwen3-0.6B` was downloaded to `/data/models/qwen3-0.6b-smoke`.
- Downloaded smoke model size: `1.5G`.
- Initial failure: the runtime image Python environment raised `ModuleNotFoundError: No module named 'distro'` while importing `openai` during `python3 -m sglang.launch_server`.
- Remediation: human review approved switching to the full image `lmsysorg/sglang:v0.5.14-cu130`.
- Full image linux/amd64 manifest digest verified: `sha256:9611bd4c5624b0e9e17829506188a12f17205f2083de0dd44d6c521733553a50`.
- Full image import gate passed for `distro`, `openai`, and `sglang.srt.entrypoints.openai.protocol`.
- Runtime compose file exists outside Git at `/data/services/llm-manager/compose/sglang-smoke.compose.yml`.
- The compose file publishes only `127.0.0.1:30000:30000` and rendered config showed `host_ip: 127.0.0.1`.
- Container `sglang-smoke-qwen3-0.6b` is running and healthy from image `lmsysorg/sglang:v0.5.14-cu130`.
- Active model/backend: `qwen3-0.6b-smoke` on SGLang.
- Endpoint: `http://127.0.0.1:30000/v1`.
- Bind: `127.0.0.1` only.
- Image: `lmsysorg/sglang:v0.5.14-cu130`.
- Model path: `/data/models/qwen3-0.6b-smoke`.
- `/health` returned HTTP 200.
- `/v1/models` returned `qwen3-0.6b-smoke`.
- Non-streaming chat completion smoke passed.
- Streaming chat completion smoke passed with SSE chunks and `[DONE]`.
- `/data/services/llm-manager/active/active.json` records the active smoke backend and contains no secrets.
- No public API exposure was configured.
- No first real model, Qwen3-30B, or larger model was downloaded.
- No host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, ik_llama, or unrelated backend install occurred.
- The runtime image `lmsysorg/sglang:v0.5.14-cu130-runtime` is currently rejected for this smoke path because it is missing the `distro` dependency; do not reuse it until upstream fixes the issue and the image is re-verified.
- Root-disk guard, Docker storage verifier, and GPU container verifier passed after remediation.

## Current M8C Result

- M8C branch: `milestone/m8c-smoke-lifecycle-manager`.
- M8C report: `reports/m8c-smoke-lifecycle-manager.md`.
- M8C source commit: `fe4e196d21dc5a0bd73fe875f885959bd7a49468`.
- M8C merged into `main` with merge commit `88ce5abd478a15a4cb40acbec4268ed2c5745618`.
- M8C main merge report: `reports/m8c-main-merge.md`.
- Result: PASS and merged.
- `scripts/llmctl` supports smoke lifecycle commands: `start`, `stop`, `restart`, `deactivate`, `logs`, `active`, and `status`.
- Lifecycle command forms:
  - `scripts/llmctl status`
  - `scripts/llmctl active`
  - `scripts/llmctl logs --dry-run`
  - `scripts/llmctl logs --yes`
  - `scripts/llmctl stop --dry-run|--yes`
  - `scripts/llmctl start --dry-run|--yes`
  - `scripts/llmctl restart --dry-run|--yes`
  - `scripts/llmctl deactivate --dry-run|--yes`
- Mutating lifecycle commands require `--yes`; dry-run plans are available with `--dry-run`.
- `stop --yes` stops the smoke container and records `status: stopped`.
- `start --yes` starts the existing smoke compose deployment and records `status: active`.
- `restart --yes` performs a guarded stop/start cycle and records `status: active`.
- `deactivate --yes` archives `active.json` under `/data/services/llm-manager/active/history/` and leaves no active backend; it does not delete model files or images.
- `scripts/sglang/verify-sglang-lifecycle.sh` verifies active or stopped smoke state without modifying state.
- Controlled M8C validation stopped, started, and restarted the smoke container, then left it active and healthy.
- Active endpoint after M8C validation: `http://127.0.0.1:30000/v1`.
- Active bind after M8C validation: `127.0.0.1` only.
- Public API exposure remains unconfigured.
- The first real model has not been downloaded.
- No models were downloaded, no Docker images were pulled, and no host backend packages were installed by M8C.


## Current M9A Result

- M9A branch: `milestone/m9a-first-real-fast-model-plan`.
- M9A source commit: `670e1349e18f33cd004a8f49fe63ddb16bd987ca`.
- M9A merged into `main` with merge commit `e04385fe096ee3d2ed0e41e28f8c3feaf11312b2`.
- M9A planning report: `reports/m9a-first-real-fast-model-plan.md`.
- M9A main merge report: `reports/m9a-main-merge.md`.
- Result: PASS and merged. STOP for actual download/deployment until M9B human approval.
- Context-sync before M9A branch creation passed on `llmserver` in `/data/services/mixed-memory-llm-api-server`.
- M9A merge validation passed with the live smoke backend active, healthy, and localhost-only at `http://127.0.0.1:30000/v1`.
- Recommended M9B primary model: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Fallback model after human review if coding-specific quality is needed: `Qwen/Qwen3-Coder-30B-A3B-Instruct`.
- Planned M9B local path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Planned first real bind: `127.0.0.1:30001:30000`.
- Planned SGLang image: `lmsysorg/sglang:v0.5.14-cu130`.
- First real model has not been downloaded yet.
- No first real Docker image pull or real-model/backend container run has occurred.
- Smoke remains active: `qwen3-0.6b-smoke` on SGLang at `http://127.0.0.1:30000/v1`.
- M9B must run in a fresh Codex context.
- M9B may stop smoke through `scripts/llmctl` only after explicit human approval.
- M9B must not expose a public API or bind the host to `0.0.0.0`.
- M9B must preserve Docker/containerd storage policy and `/data` guardrails.

## Current M9B Result

- M9B branch: `milestone/m9b-first-real-fast-model-deploy`.
- M9B report: `reports/m9b-first-real-fast-model-deploy.md`.
- M9B source commit: `4fb333a649d5e0169d616fd3b1c1980b7b0ac15d`.
- M9B merged into `main` with merge commit `c33d09d31bba66f6a0af2bb4c8b9b451887adbe0`.
- M9B main merge report: `reports/m9b-main-merge.md`.
- Result: PASS and merged; the first real model is active locally.
- Smoke backend was stopped cleanly through `scripts/llmctl stop --yes`.
- Smoke model files remain preserved at `/data/models/qwen3-0.6b-smoke` (`1.5G`).
- First real model downloaded: `Qwen/Qwen3-30B-A3B-Instruct-2507` only.
- First real model path: `/data/models/qwen3-30b-a3b-instruct-2507` (`57G`).
- Active model/backend: `qwen3-30b-a3b-instruct-2507` on SGLang.
- Active endpoint: `http://127.0.0.1:30001/v1`.
- Active bind: `127.0.0.1:30001` only; no public API exposure is configured.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`, healthy from image `lmsysorg/sglang:v0.5.14-cu130`.
- Runtime compose file outside Git: `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml`.
- Active state outside Git: `/data/services/llm-manager/active/active.json`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- `/v1/models`, non-streaming chat, streaming chat, and a technical PCIe passthrough prompt passed.
- Runtime VRAM after warmup was about `76294 MiB` on GPU 0 and `76326 MiB` on GPU 1.
- Root-disk guard, Docker storage verifier, and GPU container verifier passed after deployment.
- `scripts/llmctl active`, `status`, `logs --dry-run`, `stop --dry-run`, and `restart --dry-run` reflect the real model. `restart --yes` is intentionally unsupported for the real model until M9C lifecycle review.
- No fallback/coder/larger/alternate model was downloaded.
- No host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, or ik_llama install occurred.
- No Docker/containerd daemon config change or restart occurred.
- No model files/images were deleted and Docker prune was not run.

## Current M9C Result

- M9C branch: `milestone/m9c-real-model-benchmark-review`.
- M9C report: `reports/m9c-real-model-benchmark-review.md`.
- Benchmarking doc: `docs/real-model-benchmarking.md`.
- Result: PASS on the branch; human review and merge to `main` are next.
- Active model/backend remains unchanged: `qwen3-30b-a3b-instruct-2507` on SGLang.
- Active endpoint remains `http://127.0.0.1:30001/v1`.
- Active bind remains `127.0.0.1:30001` only; no public API exposure is configured.
- Launch args remain `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Benchmark cases passed: `tiny_health`, `technical_short`, `coding_short`, `streaming_short`, `context_4k`, `context_8k`, and `context_16k`.
- Largest context tested successfully: `context_16k` with `16581` prompt characters and reported `3518` prompt tokens.
- Streaming result: TTFT about `0.033s`, total elapsed about `0.614s`, `155` SSE chunks.
- Non-streaming output throughput where token usage was returned was about `158-249` output tokens/sec across the modest cases.
- GPU snapshots showed memory steady around `76360 MiB` on GPU 0 and `76392 MiB` on GPU 1, peak observed GPU utilization `100%`, peak observed power about `287 W` on GPU 0 and `310 W` on GPU 1.
- Lifecycle checks were dry-run only: `status`, `logs --dry-run`, `stop --dry-run`, and `restart --dry-run` passed.
- Root-disk guard, Docker storage verifier, GPU container verifier, and SGLang real-fast live verifier passed after benchmarks.
- SGLang log tail had no warning/error lines matching the M9C scanner during the captured post-benchmark window.
- No model download, Docker image pull, package install, launch-arg change, real stop/restart, public exposure, model/image deletion, or Docker prune occurred.


## Next Recommended Milestone

- Human review, then merge M9C into `main` if PASS.
- After M9C merge, M10 API/front-door/auth planning is next.
- Public API exposure remains unconfigured and blocked until a separate approved implementation milestone.
- Real restart testing and launch-arg tuning should remain separate human-approved lifecycle/tuning tasks.

## Carry-Forward Operational Warnings

- Correctable PCIe AER warnings have been observed during passthrough reset/start activity and should be monitored during future load tests.
- VFIO reset activity has shown reset-done lines.
- Avoid live snapshots with VFIO GPUs because live snapshot previously failed with VFIO migration unsupported.
- QGA is currently working based on human `qm agent 120 ping` verification.

## Known Future Model Candidates

- `Qwen/Qwen3-0.6B` for small smoke-test model first
- `Qwen/Qwen3-30B-A3B-Instruct-2507`
- `Qwen/Qwen3.6-35B-A3B`
- `Qwen/Qwen3-30B-A3B-Thinking-2507`
- `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- `Qwen/Qwen3-235B-A22B-Instruct-2507`
- `MiniMaxAI/MiniMax-M3`
- `zai-org/GLM-5.2`
- `deepseek-ai/DeepSeek-V4-Flash` as large feasibility comparator

## New-chat Instruction

Future sessions should read:

- `AGENTS.md`
- `ROADMAP.md`
- `docs/current-state.md`
- `docs/cuda-driver-compatibility.md`
- `docs/root-disk-guard.md`
- `docs/docker-containerd-storage.md`
- `reports/m5a-cuda-nvidia-compatibility.md`
- `reports/m5a-main-merge.md`
- `reports/m5b-nvidia-host-driver.md`
- `reports/m5b-main-merge.md` if present
- `docs/nvidia-container-toolkit.md` if present
- `reports/m6a-nvidia-container-toolkit-plan.md` if present
- `reports/m6a-main-merge.md` if present
- `reports/m6b-main-merge.md` if present
- `reports/m6b-nvidia-container-toolkit-install.md` if present
- `reports/m7a-model-runtime-research.md` if present
- `reports/m7a-main-merge.md` if present
- `docs/model-runtime-manager.md` if present
- `docs/model-matrix.md` if present
- `reports/m7b-model-runtime-manager.md` if present
- `reports/m7b-main-merge.md` if present
- `reports/m8a-sglang-smoke-plan.md` if present
- `reports/m8a-main-merge.md` if present
- `docs/sglang-smoke-deployment.md` if present
- `docs/pre-m9-handoff.md` if present
- `reports/m8b-main-merge.md` if present
- `docs/pre-m8b-handoff.md` if present
- `docs/pre-m8-handoff.md` if present
- `reports/m4b-main-merge.md`
- `reports/m9a-first-real-fast-model-plan.md` if present
- `reports/m9a-main-merge.md` if present
- `docs/pre-m9b-handoff.md` if present
- `reports/m9b-first-real-fast-model-deploy.md` if present
- `reports/m9b-main-merge.md` if present
- `docs/pre-m9c-handoff.md` if present
- `docs/real-model-benchmarking.md` if present
- `reports/m9c-real-model-benchmark-review.md` if present
- Latest reports

Then continue with human review and merge of M9C if PASS, followed by M10 API/front-door/auth planning.
