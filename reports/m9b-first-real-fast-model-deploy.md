# M9B First Real Fast-Model Deployment

- Timestamp: `2026-07-05T15:24:28Z`
- Branch: `milestone/m9b-first-real-fast-model-deploy`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Conclusion: PASS. The first real fast model is deployed and active locally.

## Context-Sync Result

PASS.

- Hostname gate: PASS, remote hostname is `llmserver`.
- Repo path gate: PASS, path is `/data/services/mixed-memory-llm-api-server`.
- Base branch sync: PASS, `main` was fast-forward current at the M9A handoff before branching.
- Git identity: PASS, `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.
- Repo cleanliness: PASS after restoring known verifier side effects before branch creation.
- `/data` guard: PASS.
- Root-disk guard: PASS.
- Docker storage verifier: PASS.
- GPU container verifier: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl doctor`: PASS.
- `scripts/llmctl validate`: PASS with 7 model profiles and 4 runtime profiles.
- Smoke lifecycle verifier: PASS before transition.
- Smoke API check: PASS before transition.

## Smoke Stop Result

PASS. Smoke was stopped through `scripts/llmctl stop --yes` only.

- Previous smoke model/backend: `qwen3-0.6b-smoke` on SGLang.
- Previous endpoint: `http://127.0.0.1:30000/v1`.
- Stop result: container `sglang-smoke-qwen3-0.6b` exited cleanly.
- Port `30000`: not listening after stop.
- Smoke model files preserved: `/data/models/qwen3-0.6b-smoke`, size `1.5G`.
- Smoke Docker image preserved; no image deletion or prune was run.

## Model Download

PASS. Download used the approved SGLang image as a helper container with all Hugging Face cache paths under `/data/hf-cache`.

- Downloaded model: `Qwen/Qwen3-30B-A3B-Instruct-2507` only.
- Local model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Model size: `57G`.
- Download method: `huggingface_hub.snapshot_download` inside `lmsysorg/sglang:v0.5.14-cu130`.
- Cache root: `/data/hf-cache`.
- Root-cache check: PASS; no model/cache data landed in `/root/.cache` or `/home/user/.cache`.
- Required files found: `config.json`, tokenizer files, `model.safetensors.index.json`, and 16 safetensors shards.
- Model config: `model_type=qwen3_moe`, `max_position_embeddings=262144`, `torch_dtype=bfloat16`.
- No fallback, larger, alternate, or coder model was downloaded.

## SGLang Image And Compose

- Image used: `lmsysorg/sglang:v0.5.14-cu130`.
- Image inspect: `id=sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3 repo_digests=lmsysorg/sglang@sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3 size=13197829770`.
- Compose file path: `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml`.
- Container name: `sglang-qwen3-30b-a3b-instruct-2507`.
- Container status: `running|healthy`.
- Host bind: `127.0.0.1:30001:30000` only.
- Rendered Compose config showed `host_ip: 127.0.0.1` and `published: "30001"`.
- Container-internal SGLang host: `0.0.0.0`, accepted only behind localhost-only host publishing.

## Launch Args Actually Used

```text
python3 -m sglang.launch_server \
  --model-path /data/models/qwen3-30b-a3b-instruct-2507 \
  --host 0.0.0.0 \
  --port 30000 \
  --served-model-name qwen3-30b-a3b-instruct-2507 \
  --tp 2 \
  --context-length 32768 \
  --mem-fraction-static 0.75
```

No startup remediation was required. The first launch reached healthy state.

## API Results

- `/v1/models`: PASS, HTTP `200`, returned `qwen3-30b-a3b-instruct-2507`, `max_model_len=32768`.
- Chat smoke: PASS, HTTP `200`, non-empty content: `The first real model is working.`
- Streaming chat: PASS, HTTP `200`, received SSE chunks and `[DONE]=True`.
- Technical prompt: PASS, HTTP `200`, non-empty answer excerpt: `PCIe passthrough allows a virtual machine (VM) to directly access and use a physical GPU as if it were connected directly to the VM, bypassing the host operating system's GPU driver stack. This enables the VM to leverage the full performance and capabilities of the GPU for tasks like gaming, machine learning, or 3D rendering, with minimal overhead. The GPU is exclusively assigned to the VM, meaning the host system cannot use it simultaneously, and proper hardware support (like VT-d or AMD-Vi) an`

## Active State

`/data/services/llm-manager/active/active.json` now records the real model and contains no secrets.

```json
{
  "bind": "127.0.0.1",
  "compose_file": "/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml",
  "compose_profile": "",
  "container_name": "sglang-qwen3-30b-a3b-instruct-2507",
  "deployed_at": "2026-07-05T15:20:34Z",
  "endpoint": "http://127.0.0.1:30001/v1",
  "image": "lmsysorg/sglang:v0.5.14-cu130",
  "launch_args": {
    "--context-length": "32768",
    "--mem-fraction-static": "0.75",
    "--tp": "2"
  },
  "model_path": "/data/models/qwen3-30b-a3b-instruct-2507",
  "model_profile": "qwen3-30b-a3b-instruct-2507",
  "port": 30001,
  "runtime_profile": "sglang",
  "served_model_name": "qwen3-30b-a3b-instruct-2507",
  "status": "active"
}
```

`scripts/llmctl active`, `status`, `logs --dry-run`, `stop --dry-run`, and `restart --dry-run` correctly reflect the real model. `restart --yes` remains unsupported for the M9B real model until M9C lifecycle/benchmark review.

## Live Verification

- `scripts/sglang/verify-sglang-real-fast-live.sh`: PASS.
- `scripts/llmctl validate`: PASS.
- `scripts/llmctl active`: PASS, real model active.
- `scripts/llmctl status`: PASS, `manager_status: active`.
- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS.
- `sudo -n docker exec sglang-qwen3-30b-a3b-instruct-2507 nvidia-smi`: PASS.
- Runtime VRAM after warmup: about `76294 MiB` on GPU 0 and `76326 MiB` on GPU 1.
- Startup logs show weights loaded, KV cache allocated, CUDA graphs captured, and Uvicorn listening inside the container.

## Disk Usage

```text
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  9.0G  4.5G  67% /
/dev/sdb1                         ext4  2.0T  124G  1.8T   7% /data
```

```text
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          4         1         69.75GB   26.69GB (38%)
Containers      2         1         351.2MB   171.9MB (48%)
Local Volumes   0         0         0B        0B
Build Cache     0         0         0B        0B
```

```text
27G	/data/docker
66G	/data/containerd
57G	/data/models/qwen3-30b-a3b-instruct-2507
1.5G	/data/models/qwen3-0.6b-smoke
7.4M	/data/hf-cache
4.0K	/data/logs/sglang-qwen3-30b
```

## Warnings

- SGLang logs warn that NUMA affinity could not be set inside the container without additional capabilities; startup and API tests still passed. No M9B capability change was made.
- SGLang logs warn missing optimized MoE kernel config for `NVIDIA_RTX_PRO_6000_Blackwell_Workstation_Edition`; performance tuning is deferred to M9C.
- Full 262K context was not attempted in M9B by design.
- `restart --yes` for the real model remains intentionally unsupported until M9C lifecycle review.

## Secret Scan

- Broad grep scan: matched only intentional documentation, tests, safety strings, scanner patterns, and prior report text.
- Changed-file value-shaped scan: PASS with no matches.
- No real secret, token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory content was identified.

## No-Action Confirmations

- No public API exposure was configured.
- No host bind to `0.0.0.0` was configured.
- No firewall, Caddy, reverse proxy, TLS, auth, or front-door service was created.
- No systemd service was created.
- No fallback/larger/alternate model was downloaded.
- `Qwen/Qwen3-Coder-30B-A3B-Instruct` was not downloaded.
- No host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, or ik_llama install occurred.
- Docker/containerd daemon configuration was not modified.
- Docker/containerd was not restarted.
- No model files or Docker images were deleted.
- Docker prune was not run.
- No disks, fstab, mountpoints, partitioning, or Proxmox host state were touched.

## PASS/STOP Conclusion

PASS. M9B deployed the first real fast model on localhost-only SGLang.

Next recommended task: human review, then merge M9B into `main` if PASS. After merge, choose either M9C first real model lifecycle/benchmark review or M10 API/front-door/auth planning.
