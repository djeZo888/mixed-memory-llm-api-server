# ai-vm API operations

**Production activation acceptance is PENDING.** These instructions describe
reviewed source `04143b18cca7aca724d9a4a4bcf943fe86c040db`. ACTIVATE owns all VM
work. Installation and schema 3 migration do not establish serving, switching,
service replay or independent client acceptance; the actual final receipt is
still required. Examples below were not executed in this documentation task.

## Modes, endpoints and identities

Default `dual-qwen` uses GPU0 Qwen and GPU1 Qwen. Optional `glm-qwen` replaces
only GPU0 with GLM; GPU1 retains its instance and endpoint. Return to dual-qwen
by explicitly switching GPU0 back to Qwen. There is no mode-switch URL, common
inference router or automatic fallback.

| Placement / API target | `deployment_id` = public `instance_id` | Inference alias | Private base URL |
| --- | --- | --- | --- |
| GPU0 / `glm`, default | `qwen38-27b-q0-480000-yarn4-bf16kv` | `qwen3.8-27b-gpu0` | `http://10.156.100.60:30002/v1` |
| GPU1 / `qwen`, both modes | `qwen38-27b-q1-480000-yarn4-bf16kv` | `qwen3.8-27b` | `http://10.156.100.60:30004/v1` |
| GPU0 / `glm`, optional | `glm-5.3-ud-q4-k-xl-g1-480000` | `glm-5.3` | `http://10.156.100.60:30002/v1` |

The legacy target `glm` means GPU0 even while Qwen occupies it. Public instance
ID identifies a deployment choice; `active_identity` is a different opaque
container/start identity used with generation to protect mutations.

Control origin is `http://10.156.100.60:30000`, with routes under `/control/v1`.
All native host listeners remain authenticated `127.0.0.1` on the same ports.
Reviewed private transport permits the approved `10.156.100.0/24` LAN; it is
HTTP without TLS. There is no public, wildcard-host or IPv6 exposure. A catalog
URL alone does not establish private connectivity or readiness. See
[private policy](private-network.md) and [client transport](direct-client-network.md).

Every deployment configures 480,000 tokens on the existing 72-vCPU guest. Both
Qwen instances share CPUs 0–7 (union 8); optional GLM uses 0–71, overlapping
Qwen's eight CPUs. See [model matrix](model-matrix.md) for caps, pins and measured
occupied context. Affinity is not exclusive cores or physical host pinning.

## Credentials and discovery

Control uses its dedicated key from protected server source
`/etc/llm-server/control-api-key`; native inference uses the separate protected
`/data/services/secrets/llm-api-key`. Clients use already provisioned, protected
local credential files, not those server paths. Never put key values in URLs,
query strings, shell arguments, source or logs. See
[protected key handling](agent-client.md#protected-key-file).

Authenticated `GET /control/v1/catalog` returns status plus `entries` with
slot, placement, instance/deployment ID, endpoint, context and readiness.
`GET /control/v1/status` in pair mode returns `schema_version:2`, `mode:"pair"`
and `slots.glm` / `slots.qwen`; it does not flatten them into one selected model.
`GET /control/v1/status/glm` and `/control/v1/status/qwen` return one slot.
Persisted lifecycle state is schema 3; it is distinct from this API schema.

Read `default_mode`, `current_mode`, `current_mode_basis` and `available_modes`.
Current mode describes selected deployments, not readiness. Per-slot fields
include `selected`, `observed`, `active_identity`, `generation`,
`generation_current`, `freshness`, `endpoint`, `current_operation` and
`last_operation`. Refresh before changes and require trusted fresh observations.
Configured context, protected accepted capacity and verified occupied tokens
are separate catalog claims; an available profile or short Ready probe is not
large-context acceptance.

`mutation_busy` describes lifecycle admission/transition occupancy. By contrast:

```json
{"status":"unknown","running_requests":null,"queued_requests":null,"observed_at":null,"freshness":null}
```

is the `inference_busy` value. `external_backlog` is also unknown and client-owned.
Ready never means idle. A future harness owns dispatch, queued work, draining
and escalation decisions. Before replacement it pauses its dispatch and drains
its own backlog, then explicitly acknowledges interruption. Direct endpoints
bypass the lifecycle lease: there is no atomic server drain guarantee.

## Targeted switch and operation polling

For Q0 → GLM → Q0, target `glm` each time and keep GPU1 unchanged:

1. Refresh target-slot status. Copy its `active_identity` to `expected_active`
   and its integer `generation` to `expected_generation`; require
   `generation_current:true`. Do not use `instance_id`, `selected`, peer values
   or the CLI lifecycle generation for this comparison.
2. POST `/control/v1/switch` with exactly `target`, `deployment_id`,
   `expected_active`, `expected_generation` and `allow_interrupt`. Every
   running target requires `allow_interrupt:true`, even if unhealthy.
3. Send `Content-Type: application/json` and a fresh `Idempotency-Key` for the
   intended mutation. After an uncertain submission, replay the same key and
   identical body to retrieve the operation; do not blindly submit a new change.
4. A 202 response contains `operation`, `replayed` and `state_persisted`.
   GET `operation.poll_url` on the control origin using the control key.
   It returns the operation directly: `pending`, `running`, `succeeded`,
   `failed` or `interrupted`. A 202 is admission, not readiness.
5. After success, rediscover both slots. Verify target deployment,
   `observed:"ready"`, `endpoint.ready:true` and the preserved GPU1 identity.
   Use the returned target base URL and alias for inference.

A stopped target can use `/control/v1/start` with the same fields except
`allow_interrupt`. `/restart` takes target, expected identity/generation and
`allow_interrupt`; `/stop` takes target and expected identity/generation and
is itself an explicit interruption. Start refuses an already running target.
Both selected slots require explicit target. There is no HTTP `/select` route.

Preflight failure leaves the target running. Failure after stopping it does not
automatically restore it or replace the peer. All mutations share one executor
and canonical lease; 409 can mean busy, stale generation/identity or idempotency
conflict. Missing/wrong credentials return 401; unavailable trusted state may
return 503. Preserve failed operation/recovery evidence. See the full
[control contract](control-api.md).

Production control read and admission budgets are 60 s each; generic
Application defaults remain 10 s, with configured values capped at 60 s.
The absolute HTTP lifetime is 130 s; use a bounded 140 s control client timeout.
A normal status/catalog read can spend 60 s refreshing under the lease, then
60 s on fresh observation/catalog. Storage-loss recovery may need another
60 s and can exceed the 130 s transport deadline; a 140 s client timeout does
not guarantee that failure path completes. Expired application calls retain
worker/lease ownership until return. Filesystem/loader work is cooperative,
not forcibly preemptible; late admission cannot mutate after ticket expiry.
A disconnect does not cancel an acknowledged transition: retain and poll its
operation. Connection, header, body and authentication limits are unchanged.
Loading remains asynchronous with an 8,000 s default operation deadline.
Switch cost is a cold model load with unmeasured duration (`seconds:null`),
not a promised latency. See [transport and recovery limits](control-api.md).

## Protected-file examples

Run as an ordinary user from a reviewed checkout with existing mode-0600 key
files in a mode-0700 directory outside Git. This helper reuses the protected
file loader; keep shell tracing and HTTP debugging off. It uses neither ambient
HTTP proxies nor redirects. Merely defining it does not make a request.

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
    conn = http.client.HTTPConnection("10.156.100.60", port, timeout=140)
    try:
        conn.request("GET" if body is None else "POST", path,
                     body=None if body is None else json.dumps(body), headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()
```

After separate activation acceptance, discover without changing model state:

```python
code, catalog = api(30000, "/control/v1/catalog", "control-api-key")
code, status = api(30000, "/control/v1/status", "control-api-key")
slot = status["slots"]["glm"]
```

Only after the caller pauses/drains its own dispatch and intends replacement,
construct the request from fresh target status. This example changes Q0 to GLM:

```python
body = {"target": "glm", "deployment_id": "glm-5.3-ud-q4-k-xl-g1-480000",
        "expected_active": slot["active_identity"],
        "expected_generation": slot["generation"], "allow_interrupt": True}
code, receipt = api(30000, "/control/v1/switch", "control-api-key", body,
                    idempotency_key="operator-gpu0-switch-001")
# On 202, poll the same operation until terminal, then rediscover.
code, operation = api(30000, receipt["operation"]["poll_url"], "control-api-key")
```

To return GPU0 to Qwen, refresh the `glm` slot again, construct a new body with
`deployment_id:"qwen38-27b-q0-480000-yarn4-bf16kv"` and fresh identity/generation,
and use a new idempotency key. Never reuse the prior status snapshot for return.
The GPU1 selection remains `qwen38-27b-q1-480000-yarn4-bf16kv` throughout.

Only when fresh discovery confirms the intended endpoint ready, this separate
example sends one GPU1 inference request with the native inference credential:

```python
code, reply = api(30004, "/v1/chat/completions", "llm-api-key", {
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "Reply with the single word READY."}],
    "reasoning_effort": "none", "temperature": 0, "max_tokens": 128,
})
```

GPU0 Qwen instead uses port 30002 and `qwen3.8-27b-gpu0`; optional GLM uses
30002 and `glm-5.3` with reviewed effort `low`. Infer only through the discovered
current alias. The example output budget is not a product limit. Use
`stream:true` for SSE; actual streaming/tool continuation acceptance remains
pending the final receipt. `/v1/models` lists only its own endpoint's model.

## Ownership and historical examples

ai-vm's protected control, private transport and canonical boot services own
production. No Worker1/SSH/benchmark-keeper process must remain alive. The
source boot owner replays desired running/resume slots GPU1 first, then GPU0;
Docker restart stays `no`. Installed intents, service replay and any physical
reboot claim still require final ACTIVATE evidence. See [operations](operations.md).

The retained [manual Qwen context script](../examples/qwen-context-test.py)
and [prior singleton acceptance](../reports/apiaccept-lan-acceptance.md) have
historical scopes; they were not rerun or promoted to dual-Q acceptance here.
Tools and files are handled by ordinary external agents in trusted workspaces.
The server supplies no browser UI, CORS frontend or harness policy. Frontend
work is separate; installer work and tests remain paused.
