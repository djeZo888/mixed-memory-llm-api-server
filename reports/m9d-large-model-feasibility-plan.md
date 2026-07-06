# M9D Large-Model Feasibility And Selection Plan

- Timestamp: `2026-07-06T23:37:55Z`
- Branch: `milestone/m9d-large-model-feasibility-plan`
- Base branch: `main`
- Conclusion: PASS for planning. STOP for actual download/deploy until human review.

## Context-Sync Result

PASS. Context-sync ran on VM hostname `llmserver` in `/data/services/mixed-memory-llm-api-server`, synced `main`, verified Git identity as `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`, read the source-of-truth handoff/docs/reports, and ran the required read-only guards before this branch was created.

Context-sync checks passed:

- Repo was clean on `main` before branch creation after restoring known verifier report side effects.
- `/data` mount guard passed.
- Root-disk guard passed.
- Docker storage verifier passed.
- GPU verifier passed with the already-approved CUDA verifier image.
- Current active real model is healthy.
- Endpoint `http://127.0.0.1:30001/v1` responded through `/v1/models`, non-streaming chat, and streaming chat during the live verifier.
- No repo changes remained after restoring known tracked report refreshes.

Known verifier side effects restored before branch creation:

- `reports/m3-root-disk-guard.md`
- `reports/m4b-docker-containerd-install.md`

## Active Current Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Runtime image: `lmsysorg/sglang:v0.5.14-cu130`.
- Warm VRAM at context-sync: about `76294 MiB` on GPU 0 and `76326 MiB` on GPU 1.
- Public API exposure remains absent.

## Hardware Baseline

- GPU inventory: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition.
- VRAM: `97887 MiB` per GPU, about 192 GB total before overhead.
- System RAM: about 1 TB nominal; Linux reports `881 GiB` total and about `862 GiB` available at M9D context-sync.
- Root filesystem: about `15G` total, `4.5G` free at context-sync.
- `/data`: about `2.0T` total, `1.8T` free at context-sync.
- Current `/data/models`: `59G`.
- Current `/data/hf-cache`: `13M`.
- Current `/data/docker`: `27G`.
- Current `/data/containerd`: `66G`.

## Software Baseline

- NVIDIA driver: `595.71.05`.
- NVIDIA Container Toolkit: installed and verified.
- Docker Root Dir: `/data/docker`.
- containerd root: `/data/containerd/root`.
- SGLang image available locally: `lmsysorg/sglang:v0.5.14-cu130`.
- Current Qwen3-30B service is running and healthy.
- Host CUDA Toolkit and `nvcc` remain absent.
- KTransformers, KT-Kernel, vLLM, ik_llama, PyTorch, and CUDA Toolkit were not installed by M9D.

## Current-Source Model Findings

Storage estimates are the sum of `.safetensors` files from Hugging Face model metadata API with `blobs=true` on 2026-07-06 UTC. They exclude tokenizer/config files, download staging overhead, cache duplication, runtime build artifacts, and logs.

| Model | License | Total params | Active params | Context | Expected storage | Expected VRAM/RAM | Runtime candidates | Feasibility on current hardware | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | Apache-2.0 | 235B | 22B | 262,144 native; 1,010,000 with Qwen long-context config | 470.19 GB / 437.90 GiB | Native BF16 weights exceed 192 GB VRAM; fit system RAM but not GPU memory. Qwen states about 1000 GB total GPU memory for 1M context. | SGLang, vLLM, KTransformers/llama.cpp noted by card | Not a first M9E full-GPU fit on 2 x 96 GB. Possible only with a proven heterogeneous/offload or quantized path and reduced context. | High memory risk; medium runtime risk; low license risk |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` | Apache-2.0 | 235B | 22B | 262,144 native | 236.43 GB / 220.19 GiB | FP8 weights still exceed aggregate VRAM before KV/cache/runtime overhead. System RAM fit is fine. | SGLang, vLLM, possible KTransformers after validation | Better than BF16, but still not a clear two-GPU SGLang/vLLM fit. Treat as fallback only after proving a current CPU/GPU offload path. | High VRAM risk; medium runtime risk; low license risk |
| `zai-org/GLM-5.2` | MIT | Source card describes flagship MoE; config has 256 routed experts and 8 experts/token | Not clearly published as an active parameter number on the model card | 1,048,576 config/context | 1506.67 GB / 1403.19 GiB | Native weights exceed VRAM and consume most of `/data`; system RAM alone is insufficient for comfortable BF16 plus overhead. `zai-org/GLM-5.2-FP8` metadata is about 755.63 GB / 703.74 GiB. | KTransformers/KT-Kernel plus SGLang tutorial, SGLang, vLLM | BF16 is not a first download. FP8 KT path is plausible later but has very large disk/RAM impact. | Very high storage/RAM risk; high runtime complexity |
| `MiniMaxAI/MiniMax-M3` | MiniMax Community | about 428B | about 23B | 1M | 854.18 GB / 795.51 GiB | Native BF16/MX source weights exceed VRAM; fit system RAM but leave substantial pressure for runtime/cache. | SGLang, vLLM, KTransformers/KT-Kernel, Transformers | Not a first BF16 download. Use the official MXFP8 variant instead if MiniMax is selected. | High storage/RAM risk; community license/custom-code risk |
| `MiniMaxAI/MiniMax-M3-MXFP8` | MiniMax Community | about 428B | about 23B | 1M | 443.75 GB / 413.27 GiB | Fits `/data` and system RAM. Does not fit full GPU memory, but KTransformers tutorial documents CPU-offloaded MXFP8 serving with selected experts on GPU. | KTransformers/KT-Kernel plus SGLang hybrid is primary; SGLang/vLLM full GPU is not assumed | Recommended first M9E proof-of-life candidate if human accepts license/custom-code/build risk. Start with text-only, single request, reduced context. | High runtime/build risk; medium-high RAM pressure; license review needed |
| `nvidia/MiniMax-M3-NVFP4` | MiniMax Community License; NVIDIA says ready for non-commercial use | 428B | about 23B | 1M | 250.10 GB / 232.93 GiB | Smaller than MXFP8, but still above 192 GB before KV/cache overhead. NVIDIA card says vLLM and Blackwell, but sample command uses TP8 and a nightly image/support path. | vLLM nightly with NVFP4/ModelOpt support | Relevant, but not a first M9E target on this 2-GPU VM unless current stable support and a two-GPU memory plan are proven. | High runtime maturity risk; non-commercial/license constraints; high VRAM risk |

## Runtime Feasibility Table

| Runtime path | Supports CPU/GPU heterogeneous? | Supports target model? | Host/container strategy | CUDA/toolkit needs | Expected complexity | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| SGLang full-GPU / FP8 | No meaningful CPU expert offload for these large candidates in the current repo baseline; primarily GPU-serving oriented. | Qwen FP8 is explicitly listed; model cards list SGLang for Qwen/GLM/MiniMax. | Prefer existing Docker pattern with pinned image, localhost-only bind, `/data` mounts. Do not use auto-download from model ID. | Use container CUDA stack; no host CUDA Toolkit. Existing `lmsysorg/sglang:v0.5.14-cu130` is verified for Qwen3-30B, not for these large variants. | Medium | Not a two-GPU memory fit for Qwen FP8 or MiniMax MXFP8 without offload; use only as comparison or if current docs prove a fit. |
| KTransformers / KT-Kernel plus SGLang hybrid | Yes. Docs describe CPU-GPU expert scheduling, hot experts on GPU, cold experts in CPU RAM, and SGLang integration. | Current docs advertise GLM-5.2 and MiniMax-M3 day-zero support. MiniMax tutorial targets `MiniMaxAI/MiniMax-M3-MXFP8`. | M9E would need an approved build/install or containerized build under `/data/build`; no install/build in M9D. Bind localhost only. | Tutorial requires CUDA 12.0+ and CUDA 12.8+ for FP8/MXFP8. Since host CUDA Toolkit is absent, M9E must choose a container/build strategy before install. | High | Best functional path for this VM, but Blackwell workstation support is uncertain. MiniMax tutorial names SM90 Hopper and upstream SM100 Blackwell datacenter so RTX PRO 6000 Blackwell must be proven, not assumed. |
| vLLM comparison | Limited; primarily GPU serving. It has OpenAI-compatible server and quantization ecosystem. | Qwen docs list vLLM; NVIDIA MiniMax NVFP4 card names vLLM but says nightly support is needed. | Comparison-only unless human approves install/image. Bind localhost only. | Requires compatible vLLM/PyTorch/CUDA image or install; not present in M9D. | Medium | NVFP4 support is not stable per NVIDIA card; Qwen FP8 still exceeds 2-GPU memory. |
| ik_llama / GGUF path | Yes for GGUF CPU/GPU offload when high-quality quantized GGUF exists. | No current official GGUF path was selected from the required sources for these candidates. | Defer. Would need separate quantization/source review and build plan. | CUDA build or CPU path depending quantization. | Medium-high | Not selected for M9E because official HF/KTransformers paths are more direct. |

## Preliminary Recommendation

- Recommended first large proof-of-life model: `MiniMaxAI/MiniMax-M3-MXFP8`.
- Recommended runtime path: KTransformers/KT-Kernel plus SGLang heterogeneous CPU/GPU serving.
- Fallback candidate: `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8`.
- Fallback condition: use only if human review prioritizes Apache-2.0 and accepts that M9E must first prove a current two-GPU/offload path; otherwise keep MiniMax-MXFP8 as the only practical first large path.
- Comparison candidate only: `nvidia/MiniMax-M3-NVFP4`, because current NVIDIA card is relevant for Blackwell but depends on vLLM nightly support and uses an 8-GPU sample shape.

Reasoning:

- Full-GPU SGLang/vLLM does not clearly fit any required large model on 2 x 96 GB once weights, KV cache, activations, and runtime overhead are included.
- `MiniMaxAI/MiniMax-M3-MXFP8` has the clearest current official/upstream hybrid tutorial for one 96 GB-class GPU plus CPU offload, and its 413 GiB footprint fits `/data` and system RAM.
- The recommendation is still high-risk because it requires new runtime installation/build work and Blackwell workstation validation in M9E.

## Recommended M9E Context And Launch Strategy

- Keep current 30B model running through M9D and until M9E human review.
- Do not auto-start or auto-switch models.
- M9E should stop the current 30B model only after human approval, then run one large backend at a time.
- First large proof should use a distinct localhost port such as `127.0.0.1:30002` to avoid confusing it with the current 30B endpoint.
- First request context target: 8192 tokens or less.
- First server token budget should be conservative: one running request, small chunked prefill, and low `max-total-tokens` until memory is observed.
- Do not attempt 1M context in the proof-of-life.
- Use text-only requests first for MiniMax-M3; defer image/video/multimodal inputs.
- If any build/install/runtime support is unclear, STOP and document the exact missing compatibility evidence.

## Expected Disk Impact

- Recommended MiniMax-M3-MXFP8 model files: about 443.75 GB decimal / 413.27 GiB.
- Practical M9E reserve should be at least 500-650 GB on `/data` for model files, cache, build artifacts, extracted sources, logs, and rollback room.
- Current `/data` free space is about 1.8T, so storage capacity is sufficient if only one large model is downloaded and no duplicate checkpoints are created.
- GLM-5.2 BF16 should not be downloaded first because it is about 1.4 TiB and would leave too little room for safe operation.

## Expected VRAM/RAM Impact

- Current 30B model uses about 76.3 GiB per GPU while active, so a large M9E proof cannot run concurrently with it.
- MiniMax-M3-MXFP8 is expected to rely heavily on system RAM for offloaded experts; expect hundreds of GiB of RAM pressure.
- GPU memory pressure depends on `--kt-num-gpu-experts`, tensor parallel size, KV cache, chunked prefill, and CUDA graph buffers. Start with very few GPU experts and one request.
- If KTransformers/KT-Kernel cannot use this RTX PRO 6000 Blackwell workstation stack, M9E should STOP before model download where possible, or before launch if discovered after download.

## Boot/Restart Policy Note

Current services do not auto-start after reboot. M9C fixed readiness reporting and `llmctl start --yes` waiting behavior, but no Docker restart policy or systemd auto-start service exists. Boot persistence remains a later milestone and must not be added in M9D or M9E unless separately approved.

## Source URLs And Titles

Model sources:

- `Qwen/Qwen3-235B-A22B-Instruct-2507 - Hugging Face`: https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507
- `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8 - Hugging Face`: https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507-FP8
- `zai-org/GLM-5.2 - Hugging Face`: https://huggingface.co/zai-org/GLM-5.2
- `MiniMaxAI/MiniMax-M3 - Hugging Face`: https://huggingface.co/MiniMaxAI/MiniMax-M3
- `MiniMaxAI/MiniMax-M3-MXFP8 - Hugging Face`: https://huggingface.co/MiniMaxAI/MiniMax-M3-MXFP8
- `nvidia/MiniMax-M3-NVFP4 - Hugging Face`: https://huggingface.co/nvidia/MiniMax-M3-NVFP4
- `Hugging Face model metadata API`: `https://huggingface.co/api/models/<repo>?blobs=true`

Runtime sources:

- `Welcome to SGLang - SGLang Documentation`: https://docs.sglang.io/
- `Server Arguments - SGLang Documentation`: https://docs.sglang.io/docs/advanced_features/server_arguments
- `Hyperparameter Tuning - SGLang Documentation`: https://docs.sglang.io/docs/advanced_features/hyperparameter_tuning
- `Expert Parallelism - SGLang Documentation`: https://docs.sglang.io/docs/advanced_features/expert_parallelism
- `SGLang - Qwen`: https://qwen.readthedocs.io/en/latest/deployment/sglang.html
- `vLLM - Qwen`: https://qwen.readthedocs.io/en/latest/deployment/vllm.html
- `vLLM latest docs`: https://docs.vllm.ai/en/latest/
- `Introduction - KTransformers`: https://kvcache-ai.github.io/ktransformers/
- `kvcache-ai/ktransformers - GitHub`: https://github.com/kvcache-ai/ktransformers
- `Running GLM-5.2 with SGLang and KT-Kernel`: https://raw.githubusercontent.com/kvcache-ai/ktransformers/main/doc/en/kt-kernel/GLM-5.2-Tutorial.md
- `Running MiniMax-M3 with SGLang and KT-Kernel`: https://raw.githubusercontent.com/kvcache-ai/ktransformers/main/doc/en/kt-kernel/MiniMax-M3-Tutorial.md
- `CPU-GPU Expert Scheduling Tutorial`: https://raw.githubusercontent.com/kvcache-ai/ktransformers/main/doc/en/kt-kernel/experts-sched-Tutorial.md

Source conflicts and uncertainty:

- Qwen model cards show SGLang/vLLM launch examples, but their examples assume more GPUs than this VM has and still need reduced context if OOM occurs.
- KTransformers documentation advertises GLM-5.2 and MiniMax-M3 support, but those tutorials require new runtime install/build work and CUDA stack decisions that are forbidden in M9D.
- MiniMax-M3 KT tutorial names SM90 Hopper as supported and says upstream SGLang targets SM100 Blackwell datacenter so far. This VM uses RTX PRO 6000 Blackwell Workstation Edition; compatibility must be proven in M9E.
- NVIDIA MiniMax-M3-NVFP4 is relevant because the card lists Blackwell and vLLM, but the card says nightly vLLM support is needed and shows TP8, so it is not recommended as the first M9E target on a two-GPU VM.

## Checks Run In M9D

Context-sync and planning checks:

```bash
hostname
pwd
git fetch origin
git checkout main
git pull --ff-only origin main
git status
git log --oneline -15
git config --show-origin --get-regexp '^user\.(name|email)$' || true
git config --global --show-origin --get-regexp '^user\.(name|email)$' || true
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-before-m9d.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
scripts/sglang/verify-sglang-real-fast-live.sh
scripts/llmctl active
scripts/llmctl status
nvidia-smi
df -hT / /data
sudo -n docker system df
sudo -n du -sh /data/models /data/hf-cache /data/docker /data/containerd 2>/dev/null || true
```

M9D did not perform any model download, Docker image pull, package install, runtime build, model/backend container start, active-model stop/restart, Docker/containerd daemon change, disk/fstab/mount change, public API exposure, or non-localhost bind.

Additional M9D branch checks run after file creation:

```bash
bash -n scripts/large-models/plan-large-model.sh
bash -n scripts/large-models/verify-large-model-plan.sh
bash -n tests/shell/test-large-model-plan-static.sh
tests/shell/test-large-model-plan-static.sh
scripts/large-models/plan-large-model.sh --dry-run
scripts/large-models/verify-large-model-plan.sh
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
scripts/sglang/verify-sglang-real-fast-live.sh
scripts/llmctl active
scripts/llmctl status
git diff --check
grep -RInE "(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth.json|ai-vm.sudo)" . --exclude-dir=.git || true
```

Results:

- Syntax/static checks passed.
- `plan-large-model.sh --dry-run` passed and printed the M9E plan without downloads, pulls, installs, runtime builds, model/backend container starts, active-model stop/restart, API exposure, or public bind.
- `verify-large-model-plan.sh` passed and verified the current active real model state.
- Final `/data`, root-disk, Docker storage, GPU container, SGLang real-fast live, `llmctl active`, `llmctl status`, and `git diff --check` checks passed.
- The broad secret scan matched only intentional documentation, test/scanner patterns, safety strings, and historical report text.
- The changed-file value-shaped secret scan matched only the new static-test/verifier scanner regexes. No real secret, token, password, private key, auth file, local sudo helper, or local Codex memory content was identified.
- The standard GPU verifier ran its approved short CUDA verifier container. No model/backend container was started.

## PASS/STOP Conclusion

PASS for planning.

STOP for actual download/deploy until human review. M9E is the earliest milestone that may download one approved large model and install/build/start one approved runtime path, and only with explicit localhost-only rollback instructions.
