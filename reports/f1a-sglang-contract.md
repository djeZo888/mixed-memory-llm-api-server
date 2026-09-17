# F1A — installed SGLang capability and auth contract

**PASS: installed identity, source/argument contract, synthetic parser/auth decisions, tiny FP8 linear kernel. NOT_TESTED: model loading/inference, tool round trips, live API auth and resource fit. Stock startup exposes api_key; F1S must prevent disclosure before real-key use.**

## Runtime and model

Live `lmsysorg/sglang:v0.5.14-cu130` ID and RepoDigest match R1 exactly: `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`. Installed SGLang0.5.14, Torch2.11.0+cu130, Transformers5.8.1, FlashInfer0.6.12. No image pull/build/change. Source root `/sgl-workspace/sglang/python/sglang`; line references below are relative to it.

Approved model: `Qwen/Qwen3-Coder-Next-FP8@da6e2ed27304dd39abadd9c82ef50e8de67bdd4c`, local `/data/models-large/qwen3-coder-next-fp8`. Require full acquisition 48-file/hash PASS before loading. Native `Qwen3NextForCausalLM` entry exists at `srt/models/qwen3_next.py:991–1028,1294`, with quantization wiring and fused QKV/gate-up mappings. Model config uses dynamic FP8 activations and128×128 weight blocks; use `--quantization fp8 --load-format safetensors`. Config/tokenizer have no auto_map; keep trust_remote_code=false.

`qwen3_coder` registers in `srt/function_call/function_call_parser.py:38,80`; detector recognizes XML-like `<tool_call><function=...><parameter=...>` at `qwen3_coder_detector.py:18–38,172–234`. Synthetic integer-argument parse PASS. Leave reasoning parser unset for this non-thinking model. No model-generated tool call was tested.

## Actual launch and resource contract

Installed argument registration supports `--model-path`, `--tokenizer-path`, `--served-model-name`, `--host`, `--port`, `--tp-size`, `--context-length`, `--max-running-requests`, `--mem-fraction-static`, `--tokenizer-worker-num`, `--attention-backend`, `--linear-attn-backend`, `--moe-runner-backend`, and **`--fp8-gemm-backend`** (not --fp8-gemm-runner-backend). Graph switches: `--cuda-graph-backend-decode disabled --cuda-graph-backend-prefill disabled`; old --disable-cuda-graph is deprecated. Defaults: host127.0.0.1, port30000, TP1, tokenizer workers1, context from config, static-memory fraction dynamically selected.

F1S candidate: **TP2, context32768, max-running-requests1, tokenizer-worker-num1**; explicit memory fraction such as0.80 remains an assumption for F1D measurement. Stored80.38GB weights are not a GPU allocation estimate. KV/GDN state, transient loading, graph/kernel workspace, allocator overhead and communication need measured headroom. Config maximum262144 is not a tested usable context; do not silently launch at that maximum.

Candidate SM120 backends: attention `flashinfer`, linear attention `triton`, MoE `triton`, block-FP8 GEMM `triton`. Source `fp8_utils.py:510–520` explicitly maps auto+SM120 FP8 GEMM to Triton. `server_args.py:4407–4463` selects FlashInfer on non-SM100 MHA hardware when available. Qwen TRTLLM MoE preference at4152–4180 is gated to SM100. `fp8.py:859–886,1817–1835,2065–2072` implements Triton block-FP8 MoE; separate CUTLASS MoE explicitly admits SM120. Source support is not full Qwen kernel proof.

Actual installed `triton_w8a8_block_fp8_linear` smoke PASS on both RTX PRO6000 SM12.0 GPUs: M16,N128,K128, BF16 input, e4m3 FP8 weight, block128×128 scale; max absolute error0.0 both. Peak Torch allocation53,760 bytes/device excludes CUDA context. Only this tiny quantization/linear path was tested; no MoE, GDN, attention, collective or model was run.

`python -m sglang.launch_server` remains supported; installed source recommends `sglang serve`. Thin entrypoint may use `prepare_server_args(public_args)` then `run_server(server_args)` (`launch_server.py:8–51,67–70`). Neither server launcher was invoked in F1A.

## Auth: supported input, mandatory disclosure prevention

1. Native `--config /run/secrets/sglang-auth.yaml` supports hyphenated `api-key`. `server_args.py:6296–6301,7213–7232`; `server_args_config_parser.py:114–120,141–187` use safe YAML then an internal argument list, without modifying OS argv. Synthetic mode0600 YAML parse PASS and original argv excluded value; fixture removed. **No --api-key-file exists** in actual parser; installed source/environ scan found no native server-key environment hook. Do not put real values in Docker metadata/env, Git or CLI.
2. **Stock redaction FAIL:** ordinary dataclass field `api_key` at `server_args.py:1139–1142`; synthetic repr and asdict retain it. `entrypoints/engine.py:217,784` logs full `server_args` repr; `utils/common.py:1357–1397` configures ordinary logging without redaction. --log-level warning suppresses these INFO lines but does not prove redaction.
3. YAML parse exceptions are logged with exception text (`server_args_config_parser.py:116–121`), potentially exposing file content. F1S must validate protected input with sanitized errors before runtime parsing; never log malformed secret YAML.
4. `/server_info` returns `dataclasses.asdict(server_args)` at `http_server.py:688–707`; `/get_server_info` delegates to it. F1S must deny or sanitize **both** diagnostic routes before real-key use. Do not persist raw diagnostic responses in readiness logs.
5. Concrete F1S requirement: reviewed minimal entrypoint loads/validates protected read-only key/config, establishes repr/log/error redaction before runtime use, denies/sanitizes both diagnostics, then passes args through supported Python launch API. Preserve the actual string for constant-time Bearer comparison and internal warmup Authorization. Synthetic fixtures must cover config failures, startup/child-process logging, both diagnostics and missing/wrong/correct auth. F1A owns no adapter/redactor implementation or real secrets.

`utils/auth.py:74–146` compares Bearer token with secrets.compare_digest. Fifteen pure synthetic decisions PASS: missing/wrong token rejects normal model/chat routes; correct allows. Allowed decisions retain an unused error_status_code401 default, not an HTTP response code. **/health*, /metrics* and OPTIONS bypass auth.** Admin-only key does not protect normal routes. Auth is installed only in single-tokenizer branch (`http_server.py:2283–2317`); multi-tokenizer initialization asserts no api_key at221–225. Force tokenizer-worker-num1.

Service later stays host loopback plus SSH forwarding. With bridge networking, publish `127.0.0.1:HOSTPORT:CONTAINERPORT`; container --host0.0.0.0 does not authorize public host binding. No browser/UI/server-side tool execution; one loaded model. GLM remains downloading only. F1D owns actual model output, streaming/tool round trips, authenticated readiness, resource fit and rollback after full acquisition and merged review.

## Evidence and boundaries

Helper `/data/build/f1a-qwen-20260915/runtime/inspect_sglang.py`; source snapshots/logs/results under runtime/evidence; cache/tmp under runtime/cache and runtime/tmp. Disposable f1a-sglang-source-inspect and f1a-sglang-fp8-kernel containers used no network, read-only image, only task mount, no Docker logs/model/public ports; removed afterward. Kernel container alone received GPUs.

Strict old/new UUID and common guards PASS before/after. Root final5,197,021,184 bytes, accepted <6GiB warning, unchanged4GiB stop. Initial unchanged guard wrote its two legacy tiny /tmp diagnostics; parent added TMPDIR support only to F1A isolated guard; subsequent diagnostics used /data/build/f1a-qwen-20260915/tmp. Deployment dirty files, stored models/images/secrets, GLM and services preserved.

## Verification commands and exact hashes

All ai-vm operations used worker `ssh ai-vm`. [Machine-readable proof](f1a-sglang-proof.json) includes all14 installed-source SHA256s, actual option defaults/choices, fixture results and kernel results. [Inspection helper](../scripts/f1a/inspect_sglang.py) has --help and three reproducible phases. Upstream [Qwen3-Coder documentation](https://github.com/QwenLM/Qwen3-Coder) corroborates dedicated parser/context; exact installed bytes govern executable compatibility.

Each phase ran `sudo -n timeout 60 docker run --rm --name NAME --network none --read-only --log-driver none --entrypoint python3` with the immutable image ID and `-v /data/build/f1a-qwen-20260915/runtime:/work`. Environment: PYTHONDONTWRITEBYTECODE=1, TMPDIR=/work/tmp, HOME=/work/cache, XDG_CACHE_HOME=/work/cache. Kernel phase additionally used --gpus all and TRITON_CACHE_DIR=/work/cache/triton, TORCH_EXTENSIONS_DIR=/work/cache/torch, CUDA_CACHE_PATH=/work/cache/cuda, FLASHINFER_WORKSPACE_BASE=/work/cache/flashinfer, HF_HOME=/work/cache/hf. Actual commands inside containers:

```bash
python3 /work/inspect_sglang.py --phase static
python3 /work/inspect_sglang.py --phase fixtures
python3 /work/inspect_sglang.py --phase kernel
```

Common/strict post-check used TMPDIR=/data/build/f1a-qwen-20260915/tmp with `/data/build/f1a-qwen-20260915/repo/scripts/d1/storage_guard.py --model-uuid a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a --report /data/build/f1a-qwen-20260915/runtime/evidence/root-after.md`. Source/fixture/kernel containers were absent afterward. GPU free memory returned to97,249/97,217MiB, comparable to audit idle values. Local helper AST/help, proof/helper identity and whitespace checks PASS.

Evidence root `/data/build/f1a-qwen-20260915/runtime/evidence/`:

| Artifact | SHA256 |
| --- | --- |
| ../inspect_sglang.py | f4fbed17884751c49ed8337eeaa7c48decdc89b0281ea599f3521a244daf077f |
| installed-static.json | c69880adeb88de7b1bbbd8970bf6ab7a100d3c632cbf458607f7ca34a5ab5b0a |
| installed-fixtures.json | 27c897f1888b105723300b81ee01a5b243380438bc98675d92a8bac42819424c |
| installed-kernel.json | 800e400b4e5acf36237de5e4b16565f52e366f37c0cbb545a21adb71e770eed6 |
| actual-parser-help.txt | 2b7cb81ab81611355442c9217dcce470058673a2c31731a5d0586526d8f6d5af |

Source snapshots stay on verified /data, not in Git. No F1A lifecycle/profile edits or activation. Next: F1S adapter/disclosure prevention and synthetic gates; F1D actual authenticated model/tool acceptance after reviewed merge and full exact acquisition PASS.
