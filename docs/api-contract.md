# Inference API contract

**Live production acceptance PASS — 2026-09-21, 03:21 UTC.** Saved proof for
source `04143b18cca7aca724d9a4a4bcf943fe86c040db` covers authenticated private
serving, Qwen schema/tool continuation and both GPU0 mode switches with GPU1
preserved. See the [dated proof and limits](../reports/dualq-480k-20260921.md#dated-production-acceptance--2026-09-21).
Hardware boot, cold-boot replay and live full rollback remain NOT_TESTED.

Default `dual-qwen` serves two Qwen instances. Optional `glm-qwen` replaces
GPU0 only. Each configured context is 480,000 tokens on the 72-vCPU guest.
Use [catalog/status discovery](control-api.md) to obtain the current instance,
endpoint and served alias; an inference `model` field does not load a model.

| Instance | Private OpenAI-compatible base | Exact `model` alias |
| --- | --- | --- |
| GPU0 Qwen | `http://10.156.100.60:30002/v1` | `qwen3.8-27b-gpu0` |
| GPU1 Qwen | `http://10.156.100.60:30004/v1` | `qwen3.8-27b` |
| Optional GPU0 GLM | `http://10.156.100.60:30002/v1` | `glm-5.3` |

Each base exposes authenticated `GET /models` and `POST /chat/completions`;
`stream:true` requests SSE. Model listing is endpoint-local, not a combined
catalog. Missing/wrong inference keys must be rejected, invalid model names
must return a client error. Actual Qwen streaming/schema/tool-result continuation
passed in the dated acceptance; this does not certify every task or future request.
Runtime health routes and unauthenticated Qwen
health/metrics exceptions are not model/API authentication proof.

Use the separate native inference key; control on port 30000 has its own key
and is not an inference proxy. Native host listeners remain `127.0.0.1`.
The reviewed private transport is trusted-LAN HTTP without TLS; no public,
wildcard-host or IPv6 exposure is authorized. See [private policy](private-network.md).

Clients explicitly choose an endpoint and alias for each request. There is no
common router, automatic fallback, tool executor or server-side agent policy.
Inference busy/queue counts remain unknown even when Ready. A future harness
owns dispatch and backlog/drain; the control API provides no atomic drain.
Configured context, protected acceptance receipts and measured occupied tokens
are separate. See [model matrix](model-matrix.md) and
[practical API usage](ai-vm-api-operations.md).
