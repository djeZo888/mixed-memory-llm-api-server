# D1b runtime contract handoff — Worker2 / D3

Read-only verification on `ai-vm`: **2026-09-14T22:56:06Z** (VM UTC). Result: **PASS identity / recorded CLI contract; GLM inference and tool behavior NOT_TESTED**. No image, build, GPU, daemon, service, model, or disk changes were made by this check.

## Exact runtime identity

- Image ID: `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
- Tag: `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1`.
- `RepoDigests` reported by live Docker inspection: `local/llama-cpp@sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`. This is local inspection evidence; registry publication/pullability was not checked. Use the exact local image ID for later activation.
- Upstream: `ggml-org/llama.cpp`, release `v0.4.1`, commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`. Live source checkout HEAD matched; `git status --porcelain` was empty; Jinja-fix ancestor `ae9afff8d2c012ca760eb9c2adf41961cf6f6232` passed `merge-base --is-ancestor`.
- Actual binary version recorded by D1: `0.4.1-dev (build 62, commit b29c606)`; GNU 13.3.0, Linux x86_64. Preserve the actual `-dev` suffix.
- CUDA devel pin: `nvidia/cuda:13.2.1-devel-ubuntu24.04@sha256:0e1f7b8e96fa9ec5e36d4709a38c62df7b5665977446081811c12b8234d874bf`.
- CUDA runtime pin: `nvidia/cuda:13.2.1-runtime-ubuntu24.04@sha256:285c50be684df76df5cd0e3162687e74b7b67add47134ff55075e3a9cfa94044`.
- Ubuntu snapshot `20260914T000000Z`; CUDA compiler recorded as 13.2 / `V13.2.78`; CMake `Release`, `GGML_CUDA=ON`, `LLAMA_BUILD_SERVER=ON`, `CMAKE_CUDA_ARCHITECTURES=120a-real`; build jobs 8.
- Existing build state: `PASS_BUILD_CUDA_CLI_ONLY`, exit `0`. D1 recorded `CUDA0` and `CUDA1`, both RTX PRO 6000 Blackwell Workstation Edition. This proves enumeration only, not GLM loading or GPU execution under inference.

## CLI options present in the actual full help

Evidence: `/data/build/d1-glm53-20260915/evidence/llama-server-help.txt`, **58,136 bytes**, SHA256 `a144e0605fbd0092e6e68cc51d1cdc3c3f8ea75bb63e2f53e4478ab2cde9e8a5`, matching `repo/reports/d1-runtime-proof.json`. These are the recorded binary help semantics, not tested GLM request behavior. No binary/container was launched during D1b's read-only contract collection.

| Option | Help contract / handoff implication |
|---|---|
| `--chat-template-kwargs STRING` | Additional template parameters; STRING must be a valid JSON object. Presence does not prove a particular GLM template keyword is supported. |
| `--reasoning-format FORMAT` | Default `auto`; `none` leaves thoughts in `message.content`; `deepseek` extracts them into `message.reasoning_content`; `deepseek-legacy` retains thought tags in content and also populates reasoning content. `none` controls parsing, not whether the model thinks. |
| `--reasoning-budget N` | Default `-1` unrestricted; `0` immediate end of thinking; positive N token budget. Model/template enforcement still needs inference tests. |
| `--reasoning [on\|off\|auto]` | Default `auto`, detected from template. `--reasoning-effort LEVEL` is also present; default `default` retains template default. |
| `--cpu-moe` / `--n-cpu-moe N` | Keep all MoE weights, or MoE weights of the first N layers, on CPU. Actual memory fit and performance remain untested. |
| `--device <dev1,dev2,..>` | Comma-separated offload devices; `none` disables offload. Recorded enumeration names are `CUDA0,CUDA1`. |
| `--gpu-layers N` | Exact count, `auto`, or `all`; default `auto`. |
| `--split-mode {none,layer,row,tensor}` | `none`: one GPU; default `layer`: layers and KV split; `row`: weights split by row; `tensor`: weights and KV split, explicitly EXPERIMENTAL. |
| `--tensor-split N0,N1,...` | Relative offload proportions per GPU, e.g. `3,1`; does not establish a tested fit for this model. |
| `--jinja` / `--no-jinja` | Jinja chat engine defaults enabled. Custom `--chat-template` / `--chat-template-file` are present; normally the template comes from model metadata. |
| `--api-key-file FNAME` | One key per line; lines beginning with `#` are comments; default none. Keep real key files outside Git, under approved service-secret storage. Authentication behavior still needs tests. |
| `--no-webui` | Present (alias `--no-ui`); WebUI defaults enabled, so later API-only activation must explicitly disable it. |
| `--host HOST` / `--port PORT` | Defaults `127.0.0.1` / `8080`; later profiles must retain declarative host/port choices. Exposure beyond localhost requires the project's API-key and firewall/TLS policy. |
| `--skip-chat-parsing` / `--no-skip-chat-parsing` | Skip mode defaults disabled; enabling it puts reasoning and tool text into plain content. Structured tool-call acceptance must test the actual parser path. |

The help also advertises built-in agent/tools/MCP options, all disabled by default. Their existence is not authorization to enable them on this API-only VM. D3 tool-call proof means model/API serialization and round trips with an external caller, subject to that milestone's scope.

## Remaining gates

1. Acquisition acceptance: all eleven exact R2 GLM shards, 467289116837 bytes, independently computed SHA256/size agreement and final storage guards. See `acquisition-state.md` for the active job snapshot.
2. Actual GLM loading and GPU execution; memory fit; readiness; authenticated OpenAI-compatible requests and streaming.
3. Model-specific Jinja rendering, requested reasoning behavior/budget, structured tool-call generation and tool-result round trip; lifecycle and performance acceptance.

D1/D1b identity, help, and CUDA enumeration do **not** satisfy those gates or authorize D3 activation. No Qwen or additional model was acquired by this subtask.

## Read-only verification commands executed

All commands targeted the same existing D1 run. The initial unprivileged Docker inspect was denied; the following `sudo -n` read-only inspect succeeded. `rg` is absent on `ai-vm`, so the successful help extraction used `grep`.

```bash
ssh ai-vm 'sudo -n docker image inspect local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1 --format "{{json .Id}} {{json .RepoTags}} {{json .RepoDigests}} {{json .Config.Labels}}"'
ssh ai-vm 'sha256sum /data/build/d1-glm53-20260915/evidence/llama-server-help.txt; stat --format="%n %s bytes" /data/build/d1-glm53-20260915/evidence/llama-server-help.txt'
ssh ai-vm 'git -C /data/build/d1-glm53-20260915/source rev-parse HEAD; git -C /data/build/d1-glm53-20260915/source status --porcelain; git -C /data/build/d1-glm53-20260915/source merge-base --is-ancestor ae9afff8d2c012ca760eb9c2adf41961cf6f6232 HEAD'
ssh ai-vm 'grep -n -A 9 -E -- "--chat-template-kwargs|--reasoning-format|--reasoning-budget N|--cpu-moe |--n-cpu-moe |--device |--tensor-split |--split-mode |--jinja,|--api-key-file |--ui,|--skip-chat-parsing" /data/build/d1-glm53-20260915/evidence/llama-server-help.txt'
ssh ai-vm 'grep -E "CMAKE_CUDA_ARCHITECTURES:|CMAKE_BUILD_TYPE:|GGML_CUDA:|LLAMA_CURL:|LLAMA_BUILD_SERVER:" /data/build/d1-glm53-20260915/evidence/CMakeCache.txt; grep -n -E "^ARG |^FROM " /data/build/d1-glm53-20260915/repo/containers/llama-cpp/Dockerfile'
ssh ai-vm 'cat /data/build/d1-glm53-20260915/build.state /data/build/d1-glm53-20260915/build.exit /data/build/d1-glm53-20260915/evidence/llama-server-version.txt /data/build/d1-glm53-20260915/evidence/llama-server-list-devices.txt /data/build/d1-glm53-20260915/evidence/nvcc-version.txt /data/build/d1-glm53-20260915/evidence/source-commit.txt'
```
