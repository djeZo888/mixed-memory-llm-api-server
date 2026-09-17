# ai-vm API operations

Discover and load a model through the control API, then use its separate
OpenAI-compatible inference endpoint. Exactly **GLM5.3 UD-Q4_K_XL** and
**Qwen3.8-27B FP8** are in scope, with one active backend at a time.

**Status draft, 2026-09-17; final acceptance PENDING.** Published evidence covers
[small Qwen API/tool tasks](../reports/q38retry-tp2-1m.md) and
[working private control/catalog](../reports/apideploy-control-ready.md).
The [stage-one report](../reports/stage1-ai-vm-status.md) separates those results
from coordinated Qwen retrieval/OpenCode results awaiting durable links, new
alias-proof gates and outstanding GLM/switch/reboot acceptance. This guide is an
operator contract, not a fresh observation of the active backend.

## Endpoints and credentials

| Role | Native IPv4 loopback | Reviewed private address |
| --- | --- | --- |
| Control origin | `http://127.0.0.1:30000` | `http://10.156.100.60:30000` |
| GLM inference base URL | `http://127.0.0.1:30002/v1` | `http://10.156.100.60:30002/v1` |
| Qwen inference base URL | `http://127.0.0.1:30004/v1` | `http://10.156.100.60:30004/v1` |

Control uses `/control/v1/...`; it is not an inference proxy. Native listeners
remain on `127.0.0.1`. The reviewed private transport permits the approved
`10.156.100.0/24` LAN under the [firewall policy](private-network.md).
Current transport is trusted-LAN HTTP without TLS encryption; public, wildcard
and IPv6 exposure are outside this policy. Advertisement or an open port does
not prove reachability, authentication or readiness.

Every control route requires bearer authentication with the **dedicated control
key**. Native inference uses a **different key**:

| Purpose | Protected server key source |
| --- | --- |
| Control | `/etc/llm-server/control-api-key` (root-owned, mode 0600); service copy `/run/credentials/llm-control.service/control-api-key` |
| Native inference | `/data/services/secrets/llm-api-key` (registered data storage, mode 0600); container reference `/run/secrets/llm-api-key` |

Clients use separately provisioned protected local credentials, not these server
paths. Supply the `Authorization` bearer header through the reviewed credential
mechanism. Never put key values in URLs, query strings, shell arguments, source
or logs; avoid shell tracing and HTTP debug output. See
[protected client key handling](agent-client.md#protected-key-file) and
[direct client policy](direct-client-network.md).

## Aliases, deployment IDs and capacity

| Model | Inference `model` / `endpoint.served_model` | Published catalog `deployment_id` |
| --- | --- | --- |
| GLM5.3 UD-Q4_K_XL | `glm-5.3` | `glm-5.3-ud-q4-k-xl-n76-native1m` |
| Qwen3.8-27B FP8 | `qwen3.8-27b` | `qwen38-27b-1000000-yarn4-tp2-bf16kv` |

Switch with an ID returned in catalog `entries`; infer with the discovered
alias: it names the already loaded model and does not load or switch one.
Native Qwen 128K/256K profiles are retained validation baselines, not additional
model identities or choices in the published two-entry catalog. Refresh catalog
and status before use; source profiles alone do not prove installation. The
[selection handoff](l2-live-snapshot.md#exact-selected-source) records profile pins.

GLM uses fast system RAM and both GPUs with 1,048,576 declared/configured tokens.
[D3CAP4 (2026-09-15)](../reports/d3cap4-native1m.md) proved one slot allocated at
that capacity and one HTTP 200 response using 19 prompt and 3 completion tokens.
It did not prove occupied 1M context, tools, switching, private-client access or
boot, and is not current health evidence.

Qwen uses both GPUs (TP2), FP8 weights, BF16 compute/KV and official factor-4
YaRN settings. [Q38RETRY](../reports/q38retry-tp2-1m.md) establishes 1,000,000
configured/allocated tokens and small-task serving. Root reports a completed
144,244-token retrieval task with tools and strict JSON; its durable link is
pending. No full occupied 1M claim follows. Catalog `context_limit` and
`context.configured_tokens` describe configuration; its structured
`context.verified_occupied_tokens` remains `null` with provenance `"unknown"`.
Neither startup allocation nor a 2048-token test output budget establishes
occupied capacity or a product limit.

Models live on registered `/data/models-large`; cache, Docker/containerd,
builds, logs and service data use the registered `/data` roots. The protected
`/etc/local-ai-server/storage.json` is authoritative, not directory existence.
Operators use current registered-storage/root guards and the canonical
`/run/llmctl/lifecycle.lock` for authorized lifecycle work. Clients need neither
host filesystem access nor Docker privileges; see the
[storage contract](l2-live-snapshot.md#canonical-registered-storage-input).

## Discover, switch, poll, then infer

Use this sequence with the current coordinated endpoint. All control requests
use the control credential; inference uses the native key. Examples are not
live acceptance results.

1. **Discover:** authenticated `GET /control/v1/catalog` returns a status
   snapshot plus `entries`. Read each entry's `deployment_id`, `state`, `context`
   and `endpoint`. `available` means eligible for start checks, not loaded;
   start preflight still revalidates artifacts.
2. **Refresh:** authenticated `GET /control/v1/status` returns `selected`,
   `desired`, `observed`, `observed_deployment`, `active_identity`, `generation`,
   `generation_current`, `freshness`, `current_operation`, `last_operation` and
   `endpoint`. Use a fresh observation with `generation_current:true` before
   requesting a change; it may be false while another owner is busy. HTTP 200
   alone is insufficient: inspect `freshness`, `failure_code` and `observed`.
3. **Switch/load:** `POST /control/v1/switch` requires exactly `deployment_id`,
   `expected_active`, `expected_generation`, `allow_interrupt`. Copy
   `active_identity` into `expected_active` (opaque 64-character lowercase
   SHA-256 or `null`) and the integer `generation` into `expected_generation`.
   Do not substitute `selected`. Set `allow_interrupt:true` to replace a
   running backend.
4. **Poll:** HTTP **202** returns `operation`, `replayed`, `state_persisted`.
   GET the returned `operation.poll_url` (`/control/v1/operations/{id}`) on the
   same control origin with the control key. Polling returns the operation
   object directly; its `status` is
   `pending`, `running`, `succeeded`, `failed` or `interrupted`.
   A 202 acknowledges acceptance, not readiness.
5. **Rediscover:** after `succeeded`, refresh status/catalog. Confirm the target
   `selected` and `observed_deployment`, `observed:"ready"` and
   `endpoint.ready:true`; use the fresh `endpoint.base_url` and
   `endpoint.served_model` for inference. An old receipt is only a snapshot.

For example, **only if** fresh status reports `active_identity:null`,
`generation:1`, no running backend, and the catalog offers this GLM deployment,
the switch body is:

```json
{"deployment_id":"glm-5.3-ud-q4-k-xl-n76-native1m","expected_active":null,"expected_generation":1,"allow_interrupt":false}
```

The identity/generation pair is compare-and-swap (CAS): it protects against
acting on a backend that changed after discovery. Never hard-code this example's
null identity or generation into a client.

Send `Content-Type: application/json` and a new `Idempotency-Key` identifying
the intended mutation (1–128 ASCII letters/digits or `_.:-`). Retry an uncertain
submission with the **same key and identical payload** to retrieve its operation;
changed content with that key returns 409. Normal terminal receipts and keys
expire together 24 hours after completion. For a changed intention, refresh
status and use a new key. Stale state or a busy owner also returns 409; do not
blindly resubmit. Missing/wrong control credentials return 401; unavailable
trusted state/storage can return 503.

Current source allows 10 seconds each for read/admission work and a 30-second
HTTP lifetime. A client should allow more than 30 seconds per control request;
model loading continues asynchronously, with a default operation deadline of
8,000 seconds. Do not use a two-second HTTP timeout or equate it with a failed
switch. Poll the existing operation and refresh status instead.

There is no switch queue, inference drain guarantee or session reservation.
`switch_effect` is `"interrupts_inference"`: a switch can interrupt responses,
streams and agents. Preflight failure leaves the old backend running; failure
after stopping it does not automatically restore it. Explicit
`POST /control/v1/stop` takes only `expected_active` and `expected_generation`,
with the same authentication, JSON and idempotency rules. It may interrupt
inference and cannot cancel another transition. Switching preserves the saved
boot policy; no request field sets it. The [full control contract](control-api.md)
covers recovery and `state_persisted:false` limits.

## Readiness and inference

Control `ready` requires fresh trusted matching backend identity, safe network
binding, an authenticated expected-model response and runtime health. Saved
selection, container health or `/v1/models` alone during warmup is insufficient.
Qwen's [native health/metrics/OPTIONS exceptions](qwen38-runtime.md) do not prove
authentication or model readiness. `loading` requires an owned live operation;
missing evidence remains unavailable/unknown.

An endpoint with `server_relative:true`, `address_scope:"server_loopback"`
belongs to ai-vm, not the client: use the reviewed tunnel transport. With the
validated private policy it can instead report `server_relative:false`,
`address_scope:"private_network"`. Refresh after every switch; port and alias
can change. Do not infer through port 30000 or treat `model` as a load request.

At the discovered inference base URL, `GET /models` is `/v1/models` and
`POST /chat/completions` is `/v1/chat/completions`; `stream:true` requests SSE.
Use the exact served alias. Unknown-model rejection in the changed Qwen launcher
still needs fresh native/extension proofs and a restart/live check; the earlier
successful requests do not establish this new behavior. Reviewed client effort
settings are GLM `"low"` and Qwen `"none"`.

## Protected-file request examples

Use an ordinary client user with separately provisioned control and inference
files, each owned by that user, mode 0600, in a mode-0700 directory outside Git.
The following Python example uses the existing protected-file loader from a
reviewed checkout; it makes no installation or credential copy. It decodes that
loader's OpenCode JSON escaping before constructing an HTTP header. Run without
shell tracing or HTTP debugging. `http.client` uses no ambient proxy or redirect.

```python
import http.client
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts/client")  # Run from the reviewed checkout root.
from client_common import load_key

key_dir = Path.home() / ".config/ai-vm-keys"  # Already provisioned; outside Git.

def api(port, path, key_name, body=None, idempotency_key=None):
    encoded = load_key({"kind": "file", "reference": str(key_dir / key_name)})
    headers = {"Authorization": "Bearer " + json.loads('"' + encoded + '"')}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    conn = http.client.HTTPConnection("10.156.100.60", port, timeout=60)
    try:
        conn.request("GET" if body is None else "POST", path,
                     body=None if body is None else json.dumps(body), headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()

code, catalog = api(30000, "/control/v1/catalog", "control-api-key")
code, status = api(30000, "/control/v1/status", "control-api-key")
print(code, status["selected"], status["observed"], status["freshness"])
```

For an intended switch, supply a catalog deployment ID and a fresh current
status. This example acknowledges interruption of the running backend:

```python
body = {"deployment_id": "glm-5.3-ud-q4-k-xl-n76-native1m",
        "expected_active": status["active_identity"],
        "expected_generation": status["generation"], "allow_interrupt": True}
code, receipt = api(30000, "/control/v1/switch", "control-api-key", body,
                    idempotency_key="operator-switch-001")
```

Choose a new idempotency key for each intention and retain it with the body
privately before sending; reuse both after an uncertain submission. On 202,
poll with `api(30000, receipt["operation"]["poll_url"], "control-api-key")`
until terminal, then rediscover. These are control calls, not inference calls.

Only after fresh status confirms the published Qwen endpoint is ready, this
additional call makes one small inference request using the separate key:

```python
code, reply = api(30004, "/v1/chat/completions", "llm-api-key", {
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "Reply with the single word READY."}],
    "reasoning_effort": "none", "temperature": 0, "max_tokens": 128,
})
print(code, reply.get("choices", [{}])[0].get("message", {}).get("content"))
```

For GLM, use its freshly discovered endpoint/alias and `reasoning_effort:"low"`.
The 128-token example budget is not a serving limit. For real agents, use the
[reviewed client](client-install.md) with a protected `--api-key-file` reference.
Provision client limits from the current handoff, not this short example.

## External agents and future frontend

Actual tools/file work needs an external agent such as the
[reviewed OpenCode client](client-install.md), running as an ordinary OS user in
an explicit trusted workspace. The client executes tools and returns results;
ai-vm serves inference only. Workspace selection is not an OS sandbox.
[Agent protocol acceptance](agent-client.md) and
[ordinary-client verification](client-verification.md) describe separate
evidence; a reply claiming an edit or passing test proves neither.

A future separate frontend can use catalog/status, switch/poll and inference
endpoint discovery. No frontend is delivered or accepted here. The control API
rejects browser Origin/fetch context and provides no CORS; future browser access
needs a trusted server-side integration that keeps control credentials out of
browser code. No such integration is implemented here. Installer work and tests
remain paused.
