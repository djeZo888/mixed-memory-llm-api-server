# F1A installed SGLang contract — early handoff

Investigation in progress; no inference or auth readiness has been tested.

- Live `lmsysorg/sglang:v0.5.14-cu130` image ID and RepoDigest both match R1: `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`.
- Installed metadata: SGLang `0.5.14`, PyTorch `2.11.0+cu130`, Transformers `5.8.1`, FlashInfer `0.6.12`.
- Installed source root: `/sgl-workspace/sglang/python/sglang`; isolated evidence `/data/build/f1a-qwen-20260915/runtime/evidence/`. Disposable source containers: no network, read-only image, no model/GPU/service/public bind, task-only writable mount, Docker logging disabled.
- `srt/models/qwen3_next.py:991,1294` defines/registers `Qwen3NextForCausalLM`; `srt/function_call/function_call_parser.py:38,80` registers `qwen3_coder`. Enumeration/source support is not model execution proof.
- `srt/server_args.py:6296–6301,7213–7232` supports native `--config /protected/file.yaml`; `srt/server_args_config_parser.py:114–120,141–187` uses safe YAML then converts fields to an internal argument list. Prefer a protected, read-only mounted YAML with `api-key` (hyphen spelling) over process arguments/environment. File contents must never enter Docker metadata or logs.
- **Do not use a live key yet:** `srt/entrypoints/engine.py:217,784` logs the complete `server_args` representation; `api_key` at `server_args.py:1139–1142` is an ordinary field. Redaction is under fixture investigation and must be explicitly solved in F1S before live activation. No native `--api-key-file` found in inspected server args; do not assume llama.cpp syntax.
- `srt/utils/auth.py:74–146`: ordinary routes require the configured Bearer token; comparison uses `secrets.compare_digest`. `/health*`, `/metrics*` and OPTIONS bypass auth; an admin-only key does not protect normal routes. `http_server.py:2283–2317` installs auth only for single-tokenizer mode. F1S should force `tokenizer_worker_num=1` and probe actual endpoint behavior later.
- F1A changes no lifecycle, llmctl or model/runtime profiles. F1S owns the declarative adapter and synthetic auth checks; F1D owns actual authenticated inference, parser round trips, memory fit and readiness on reviewed merged code.

Strict old/new UUID and common storage guards PASS before inspection; root free 5,197,127,680 bytes (accepted below-6-GiB warning). No image pull or host mutation.
