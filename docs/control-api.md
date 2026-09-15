# U1 protected asynchronous control API

## Delivery status

This is bounded independent source with an explicit synthetic lifecycle test
port. **Production Manager binding is incomplete and the production entry point
refuses to start a listener.** The base reviewed Manager lacks the frozen L1
loader/borrowed-lease dispatch source. An API extraction is not source delivery.
There is no legacy constructor, subprocess command, environment override or
fixture fallback in production. Source tests do not establish live readiness.

The API is separate from inference: IPv4 `127.0.0.1:30000`, a dedicated control
bearer key, JSON only. It serves no UI, inference proxy, agent tools or browser
control. I1c owns installation and enabling of the source unit template.

## Authentication and bounds

Every route, including unknown routes and unsupported methods, requires
`Authorization: Bearer <locally-provisioned-control-key>`. Missing/wrong keys
return the same 401 error. The installer must provision a distinct random control
key (32–256 nonspace ASCII bytes), root-owned mode 0600, and reuse it on resume.
It must never reuse the inference key. No key belongs in argv, environment,
source, profile, receipt or logs. HTTP input cannot select a key or file path.

The parser permits GET/POST only. It rejects Origin, browser fetch context,
WebSocket upgrades, chunking, folded/duplicate headers, ambiguous lengths,
absolute request targets, malformed UTF-8/JSON, duplicate JSON keys, nonfinite
numbers and nesting beyond the fixed limit. No CORS headers are generated.
Request line: 2,048 bytes; headers: 8,192 bytes and 32 fields; body: 4,096 bytes;
response: 256 KiB. One request per connection. At most 16 connection workers
plus one deadline supervisor and one transition executor. Socket lifetime is
five seconds; expired application calls retain their worker slot until return.
The transport closes excess connections. It writes no access/body/error logs.
Responses and journal fields use explicit allowlists; exception text is never
returned. Malformed framing can be rejected before authentication is parseable.

## Versioned routes

| Method and path | Contract |
| --- | --- |
| GET `/control/v1/catalog` | Installed deployment records plus status, generation, observation and current operation. |
| GET `/control/v1/status` | Selected/desired/observed deployment, opaque active identity, generation and freshness, plus the last completed operation. |
| POST `/control/v1/switch` | Exactly `deployment_id`, `expected_active`, `expected_generation`, `allow_interrupt`. |
| POST `/control/v1/stop` | Exactly `expected_active`, `expected_generation`; explicit interruption of identified backend. |
| GET `/control/v1/operations/{id}` | Original operation receipt, status, deadline, sanitized failure and outcome. |

Mutations require `Content-Type: application/json` and `Idempotency-Key`
(1–128 ASCII letters/digits or `_.:-`). IDs are bounded registered deployment
IDs. No arbitrary model names, URLs, paths, flags, environment, image references,
commands or profile contents are accepted. Unknown/extra fields are errors.
An identity is a 64-character lowercase opaque SHA-256 value or null;
generation is an integer, never a JSON boolean. Switch example:

```json
{"deployment_id":"registered-example","expected_active":null,"expected_generation":1,"allow_interrupt":false}
```

Use values from a fresh status response. Acceptance returns 202 with `operation`
(including `id` and `poll_url`), `replayed`, and `state_persisted`. Poll
`operation.poll_url`. Operation statuses are `pending`, `running`, `succeeded`,
`failed`, `interrupted`; times are epoch seconds. An operation's observed outcome
is a bounded snapshot, not a promise that no external CLI changes happened later.
Refresh status/discovery after success.

| Status | Examples |
| --- | --- |
| 400 | Invalid fields/types/JSON; bounded transport errors also use 413/414/431. |
| 401 | Missing or invalid dedicated control key. |
| 404 | Unknown route, operation or deployment. |
| 405 | Unsupported authenticated method. |
| 409 | Busy canonical owner, stale identity/generation, uninstalled target, missing interruption acknowledgment or idempotency content conflict. |
| 503 | Missing production binding, trusted observation/storage/owner, package admission or durable journal. |

## Admission, generation and interruption

One nonblocking in-process admission guard protects the handoff slot and entire
transition. There is no FIFO of future switches. A single executor thread calls
canonical `common.lifecycle_lease.acquire_lease(blocking=False)` and holds that
same minted context through all work. External CLI/installer ownership returns
409 before accepting a mutation. Requests never receive 202 on a lock probe
followed by later acquisition. L1 calls must borrow that exact lease; a read does
not take ownership away from loading work.

Under this lease the owner loads a fresh session, verifies authoritative package
admission, obtains trusted fresh observation, reconciles generation and interrupted
receipts, checks expected identity/generation, checks target eligibility, and
persists the new pending operation before accepting it. The full target preflight
runs before old-stop: root explicitly approved exact `Manager.prepare_start(d)`
including its anchored guard report. Configuration-only `dry_run` cannot replace
it. Then stop the old backend, prove it stopped, select/start the target, observe
its actual outcome and persist it. Failure never automatically resurrects the
old model. An invalid target or failed preflight leaves the old backend running.

U1 owns semantic generation: the counter changes when selected deployment,
desired running/stopped intent, immutable container/start identity, or actual
running state changes. It does not change on polling times or health checks.
The identity includes instance, deployment, immutable container ID and start
generation, so same-profile stop/start cannot reuse stale client expectations.
Reads reconcile under nonblocking canonical admission when idle. If another
owner is busy, status still observes freshly but may return
`generation_current:false`; mutations reconcile again and fail stale requests.
Unknown observation never becomes Ready based on saved state.

A running backend requires `allow_interrupt:true` for a switch. Direct inference
requests and agent sessions have no lifecycle lease, drain guarantee or session
reservation. `switch_effect` is always `interrupts_inference`. Stop may terminate
an in-flight response/stream. Stop during another transition returns 409; no
preemptive cancellation or force-kill route exists. The source service template's
process termination and reboot behavior require I1c/I2 acceptance.

Deadlines are finite (default operation 8,000 seconds, maximum 14,400; reads and
admission 2 seconds, maximum 5). The explicit test port must honor each supplied
monotonic deadline. The executor checks before/after bounded calls and retains
ownership while a call is outstanding. It never releases a live lease to admit
another model because a timer elapsed. Actual L1 call bounds remain a production
integration gate; a Python thread cannot forcibly cancel arbitrary backend code.
A timed-out admission must not execute unacknowledged destructive work.

## Journal, restart and unavailable storage

The journal stores at most 128 operations and at most 1 MiB of strict metadata,
request/key digests, semantic counter and fingerprint. Original keys, request
bodies, raw lifecycle objects and private paths are excluded. Terminal receipts
and idempotency records expire together 24 hours after completion. Unexpired
keys are never evicted to admit normal work; full capacity returns 503. Expired
keys may be reused and represent a new request. Matching content returns the
original operation; different canonical content with the same key returns 409.

On restart, fresh canonical reconciliation marks pending/running operations
`interrupted` and records current observation. It never resumes or replays a
switch. Saved Ready is not live readiness. Corrupt storage remains fail-closed;
a previously unavailable journal must be read successfully before any write can
replace it. An uncertain atomic write does not authorize execution.

An explicit trusted stop may continue despite storage/package/journal loss or
journal capacity, only after the same canonical lease and exact protected
`/run/llmctl/recovery.json` immutable identity validation. No name adoption,
arbitrary kill, config read, package recovery or new start is allowed in this
path. A separate volatile result window contains at most 16 recovery stops;
these keys/results expire on process restart or replacement by later recovery
stops. Durable receipts are preserved. Such receipts and outcomes explicitly
return `state_persisted:false`. Restore registered storage and repeat stop
before reboot to persist stopped intent. When the durable journal is unavailable
after restart, the trusted recovery observation supplies a volatile generation;
clients must refresh status before stop. Restoring the journal never rewinds
the current process counter. The journal can never turn a volatile
stop into a durable stopped-intent claim.

## Catalog, evidence and discovery

The catalog consumes generic trusted registered model/deployment/runtime and
small acquisition-evidence DTOs. Multiple deployments per model and a third
future model require no routing code rewrite. Missing/uninstalled/historical or
research-only entries (including research-only Q38) are excluded. An installed
record with failed current mount/profile checks is unavailable. Catalog/status
never scan or hash large weights; full start preflight revalidates artifacts.

Records include stable deployment/model IDs, display name, immutable revision,
backend/runtime identity, context, quantization, installed bytes, resource
estimates/measurements with evidence, installed verification time and
`start_revalidation_required:true`. Capabilities are `verified`, `declared`, or
`unknown`; verified requires actual end-to-end evidence. A parser flag or model
list cannot prove tool calling. Evidence references are bounded opaque IDs.

Ready requires trusted immutable identity, matching deployment, safe network,
authenticated expected-model response and runtime health. Loading requires an
owned live operation. Saved state and `/v1/models` during warmup are insufficient.
Missing data remains unavailable/unknown.

An endpoint contains `base_url`, `served_model`, `authentication_required:true`,
`server_relative:true`, `address_scope:server_loopback`, and `ready`. Its URL is
relative to the server's loopback, not the remote client's. Port and alias may
change with each switch. Tunnel that port, use the separate local inference key,
and refresh discovery before reconnecting. There is no permanent routed URL.

## Installer and verification handoff

`scripts/control/llm-control.service.in` is a source template only. I1c must
substitute protected source/data/key locations, provision the distinct 0600 key,
validate actual root/Docker/registry/credential access and registered mounts,
arrange credential survival across storage loss, and verify systemd hardening.
Do not add a data-mount BindsTo that removes the trusted-stop listener on loss.
No broad Docker group or sudo grant belongs to a client user. Logging is disabled;
any future logs require registered data storage and bounded retention.
The current `serve.py` exits 3 with a safe `production_adapter_unavailable`
result before opening a listener, including with `--check-binding`.

Verification (local disposable fixtures; no VM/model/image operations):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_control*.py' -v
python3 -I -B scripts/control/serve.py --help
python3 -I -B scripts/control/serve.py --check-binding
```

The last command is expected to exit 3. Actual local TCP HTTP tests use a
disposable key and explicit synthetic lifecycle sessions with the real canonical
lease. They are not live inference or installed-systemd acceptance. Worker1/V1
owns two installed-model HTTP switches, discovered-endpoint inference/OpenCode,
real interrupted-client-stream behavior and service/boot recovery. I1c/I2 owns
fresh-host installer and unit acceptance. All remain NOT_TESTED by U1 here.
