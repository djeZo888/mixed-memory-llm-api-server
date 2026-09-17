# ai-vm API operations

Discover and load a model through the control API, then use its separate
OpenAI-compatible inference endpoint. Exactly **GLM5.3 UD-Q4_K_XL** and
**Qwen3.8-27B FP8** are in scope, with one active backend at a time.

**PENDING — source guide frozen 2026-09-17.** The
[anticipated selection](l2-live-snapshot.md) is not an accepted deployment or
active default. Coordinated Worker1 result at **2026-09-17 05:18:10 UTC** on exact source
`821df4a561173c078ed35c9286a07b82867b7953` reports the genuine native no-GPU
fixture pair at **128K and 256K PASS** (report not yet committed; no model
allocation or inference PASS), while actual Qwen model loading/inference,
1M extension acceptance and final live API/switch/network/boot/client
acceptance remain **PENDING**. These are reviewed source contracts, not fresh
observations of serving state.

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

| Model | Inference `model` / `endpoint.served_model` | Anticipated switch `deployment_id` |
| --- | --- | --- |
| GLM5.3 UD-Q4_K_XL | `glm-5.3` | `glm-5.3-ud-q4-k-xl-n76-native1m` |
| Qwen3.8-27B FP8 | `qwen3.8-27b` | `qwen38-27b-1000000-yarn4-tp2-bf16kv` (**PENDING**) |

Switch with an ID returned in catalog `entries`; infer with the discovered
alias. Repository profiles do not prove an installed catalog entry. Native Qwen
128K/256K profiles are retained validation baselines, not additional model
identities or extra choices in the anticipated two-entry catalog. Exact pins:
[selection handoff](l2-live-snapshot.md#exact-selected-source).

GLM uses fast system RAM and both GPUs with 1,048,576 declared/configured tokens.
[D3CAP4 (2026-09-15)](../reports/d3cap4-native1m.md) proved one slot allocated at
that capacity and one HTTP 200 response using 19 prompt and 3 completion tokens.
It did not prove occupied 1M context, tools, switching, private-client access or
boot, and is not current health evidence.

Qwen's GPU-resident native baseline declares 256K (262,144). The source candidate
retains FP8 weights and uses both GPUs (TP2), BF16 KV and official factor-4 YaRN
settings for 1,000,000 tokens; acceptance is **PENDING**. See
[Q38MAX scope](../reports/q38max-source.md). Catalog `context_limit` and
`context.configured_tokens` describe configuration;
`context.verified_occupied_tokens` is `null` and
`context.verified_occupied_provenance` is `"unknown"`. Neither a short response
nor a 2048-token output budget measures usable context capacity.

## Discover, switch, poll, then infer

After root-reviewed activation, use this sequence. All control requests use
the control credential; inference uses the native key. Examples contain no
credentials and are not live acceptance results.

1. **Discover:** authenticated `GET /control/v1/catalog` returns a status
   snapshot plus `entries`. Read each entry's `deployment_id`, `state`, `context`
   and `endpoint`. `available` means eligible for start checks, not loaded;
   start preflight still revalidates artifacts.
2. **Refresh:** authenticated `GET /control/v1/status` returns `selected`,
   `desired`, `observed`, `observed_deployment`, `active_identity`, `generation`,
   `generation_current`, `freshness`, `current_operation`, `last_operation` and
   `endpoint`. Use a fresh observation with `generation_current:true` before
   requesting a change; it may be false while another owner is busy.
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

Send `Content-Type: application/json` and a new `Idempotency-Key` identifying
the intended mutation (1–128 ASCII letters/digits or `_.:-`). Retry an uncertain
submission with the **same key and identical payload** to retrieve its operation;
changed content with that key returns 409. Normal terminal receipts and keys
expire together 24 hours after completion. For a changed intention, refresh
status and use a new key. Stale state or a busy owner also returns 409; do not
blindly resubmit. Missing/wrong control credentials return 401; unavailable
trusted state/storage can return 503.

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
`POST /chat/completions` is `/v1/chat/completions`. After GLM is ready, this
compact request follows the historical tiny-smoke body:

```json
{"model":"glm-5.3","messages":[{"role":"user","content":"Reply with the single word READY."}],"reasoning_effort":"low","temperature":0,"max_tokens":128}
```

Reviewed settings are GLM `reasoning_effort:"low"` and the anticipated Qwen
fast-client preset `reasoning_effort:"none"`; Qwen continuation remains pending.
Token budgets and client limits come from the accepted operator handoff.

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
needs reviewed integration. Installer work and tests remain paused.
