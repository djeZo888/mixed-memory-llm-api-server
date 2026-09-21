# Protected asynchronous control API

## Current source and acceptance status

**Production activation acceptance is PENDING.** This contract describes
reviewed source `04143b18cca7aca724d9a4a4bcf943fe86c040db`. ACTIVATE owns VM
work; source installation and lifecycle schema 3 migration do not establish
serving, switching, durable service replay or independent client acceptance.
The prior U1/L2 and singleton reports remain historical evidence.

Control is separate from inference: authenticated IPv4 `127.0.0.1:30000`,
a dedicated bearer key and JSON only. It serves no UI, inference router,
agent tools or browser control. [API usage](ai-vm-api-operations.md) gives
private endpoint and protected-key examples. Installer work remains paused.

## Dual Qwen and optional GPU0 GLM

Default `dual-qwen` selects Qwen on each GPU. Optional `glm-qwen` replaces only
GPU0 with GLM; return explicitly to GPU0 Qwen. The [production contract](concurrent-api.md)
uses persisted/API target `glm` for GPU0 and `qwen` for GPU1. Public
`instance_id` equals the deployment ID; it is distinct from the opaque
`active_identity` used for compare-and-swap.

| Placement / target | Deployment and public instance ID | Alias / native port |
| --- | --- | --- |
| GPU0 / `glm`, default | `qwen38-27b-q0-480000-yarn4-bf16kv` | `qwen3.8-27b-gpu0` / 30002 |
| GPU1 / `qwen`, both modes | `qwen38-27b-q1-480000-yarn4-bf16kv` | `qwen3.8-27b` / 30004 |
| GPU0 / `glm`, optional | `glm-5.3-ud-q4-k-xl-g1-480000` | `glm-5.3` / 30002 |

All configure 480,000 tokens on the existing 72-vCPU guest. Q/Q shares CPUs
0–7; optional GLM uses 0–71. Affinity does not establish exclusive cores or
physical host pinning. [Model matrix](model-matrix.md) separates configuration,
protected accepted capacity and measured occupied context.

Status/catalog expose current/default/available modes, declared per-slot
context, readiness/degraded state, mutation busy and switch cost. Current mode
is based on selected deployments; it is not a readiness or activation receipt.
`mutation_busy` describes lifecycle work. `inference_busy` has status `unknown`,
with null running/queued counts, observation time and freshness. External
backlog remains unknown and client-owned. Ready never means idle. Cold-load
switch duration remains unmeasured (`seconds:null`).

Every running-target switch/restart requires `allow_interrupt:true` and fresh
target-slot identity/generation. The future harness pauses dispatch and drains
its own backlog before acknowledging interruption. Direct inference bypasses
the lifecycle lease, so the server provides no atomic drain guarantee or
inference admission reservation. There is no automatic fallback policy.

The protected private transport advertises `http://10.156.100.60:30002/v1`
for GPU0 and `http://10.156.100.60:30004/v1` for GPU1. Native listeners remain
loopback with their separate inference key; the catalog discovers endpoint
and readiness independently. Endpoint-local `/v1/models` is not a combined
catalog. A URL advertisement is not transport acceptance.

## Pair status and mutations

The lifecycle owner explicitly migrates protected v2 state to v3; the API never
migrates implicitly. Singleton v2 support remains for preserved recovery paths.
The following contract governs the reviewed pair; legacy singleton differences
are identified below.

`GET /control/v1/status` in pair mode returns `schema_version:2`, `mode:"pair"`
and exactly `slots.glm` and `slots.qwen`, with no singleton `selected` projection.
Each slot contains selected/desired/observed, opaque `active_identity`, semantic
`generation`, `generation_current`, endpoint, persistence/freshness and its own
current/last operation. `GET /control/v1/status/glm` and
`GET /control/v1/status/qwen` return the corresponding slot directly.
`GET /control/v1/catalog` includes that pair status plus installed entries with
`slot`, endpoint and independently observed readiness/capabilities.

All mutation bodies are closed schemas with the existing content type and
idempotency headers. `target` is exactly `glm` or `qwen`; generation and identity
come from a fresh response for that same slot. The following bodies are exact;
replace the sample CAS values with the target's current values:

| POST route | Exact example body |
| --- | --- |
| `/control/v1/start` | `{"target":"glm","deployment_id":"glm-5.3-ud-q4-k-xl-g1-480000","expected_active":null,"expected_generation":1}` |
| `/control/v1/switch` | `{"target":"qwen","deployment_id":"qwen38-27b-q1-480000-yarn4-bf16kv","expected_active":null,"expected_generation":1,"allow_interrupt":false}` |
| `/control/v1/stop` | `{"target":"glm","expected_active":null,"expected_generation":1}` |
| `/control/v1/restart` | `{"target":"qwen","expected_active":null,"expected_generation":1,"allow_interrupt":true}` |

Start selects and starts the registered target, refusing a running target with
`409 already_running`; it does not stop the peer. Switch preflights before any
stop, then stops/selects/starts only its target. Restart preflights and
stops/starts the same target selection while preserving its boot policy.
Switch/restart of a running target require `allow_interrupt:true`; stop is itself
an explicit interruption request. None interrupts, cancels, drains or reserves
the other model's inference. Ordinary target interruption semantics remain:
in-flight target requests may end; another lifecycle mutation returns busy while
one transition owns the executor. There is no force-kill or preemptive-cancel API.

The deployment must belong to the chosen physical slot (GPU0 Qwen or GLM; GPU1 Qwen). Unknown slots or
extra fields return `400 invalid_request`; model/slot mismatch returns
`409 target_mismatch`. Existing targetless singleton bodies remain valid. In a
v3 record, targetless mutation is accepted only with exactly one selected slot;
two selected slots (even if one is stopped), or no selected slot, return
`409 target_required`. An explicit slot against unmigrated v2 state returns
`409 target_unavailable`; use the root-reviewed migration procedure first.

The same one executor, canonical lease and idempotency journal own every
transition. Client generations are scoped control observation counters;
Docker restart identity, desired/selected state and lifecycle slot generation
all contribute. A peer-only transition cannot invalidate the target's CAS.
The adapter separately passes the observed lifecycle slot generation to Manager
before each dispatch. Global busy admission still serializes all mutations.
Operation receipts add `slot` and retain deployment `target`, including for stop;
matching idempotency replay never executes a second transition. Changing the
slot under the same unexpired idempotency key is a content conflict.

Schema 1 operation journals remain readable. First pair reconciliation under the
canonical lease records schema 2 with exactly two scoped fingerprint/counter
records, preserving existing entries and the legacy counter. Interrupted
receipts reconcile against their own slot and never replay a mutation after
service restart. Recovery stops retain the exact target identity, use the same
/run-only trusted ownership path, and report `state_persisted:false` if storage
is unavailable. Healthy peer observations stay separate from a failed target.
For a transaction durably proven `dispatch:not_dispatched`, a validated v3
pending ownership record may be observed as exactly absent. The adapter binds
the complete pending record digest to its slot fingerprint and marks absence
only with that proof and successful exact-name inspection. A recovery stop
still checks the client's target identity/generation
and rechecks exact absence under the canonical lease before clearing that pending
intent. Dispatched (`uncertain`) and older markerless records retain ownership
through any number of empty inventories; an eventual exact container can still
be reconciled. CLI failure/timeout, inspection error or identity mismatch
supplies no non-creation proof. This path neither invents a container identity nor
clears the peer's intent.
Root rollback must drain control and preserve/restore its protected journal with
the prior source, because old source does not read schema 2 journals.

Catalog `context.configured_tokens` and `context_limit` are declarations.
`accepted_configured_tokens:null`, `acceptance_status:"unvalidated"`,
`verified_occupied_tokens:null` and empty evidence remain explicit without a
validated acceptance receipt. A protected receipt must pass the lifecycle
`check_acceptance` source/profile/resource/instance/storage gates; only then
`acceptance_status:"reviewed"` and its accepted configured and largest occupied
values are exposed, with the receipt digest as an opaque evidence ID. Raw private
paths and free-form evidence strings are never returned. Neither successful source tests, a loaded backend,
a Ready probe nor saved intent proves large occupied-context acceptance. Profile
availability does not bypass the lifecycle owner's exact approved-pair checks.

Source validation includes `tests/test_control_slots.py` and
`tests/test_control_slots_manager.py` for targeted
CAS/idempotency, independent peer state, partial failures, interrupted receipts,
loading/readiness and storage-loss stop. Real simultaneous inference and stream
survival during target restart remain required in the separately authorized
Worker1 activation session.

## Authentication and bounds

Every route, including unknown routes and unsupported methods, requires
`Authorization: Bearer <locally-provisioned-control-key>`. Missing/wrong keys
return the same 401 error. The deployment owner must provision a distinct random control
key (32–256 nonspace ASCII bytes), root-owned mode 0600, and reuse it on resume.
It must never reuse the inference key. The dedicated source is fixed at `/etc/llm-server/control-api-key`, root:root
0600 on the root filesystem; the inference key stays at its registered data
path. `LoadCredential` uses that root-resident source and the service reads the
fixed `/run/credentials/llm-control.service/control-api-key` copy. Both survive
loss of model/data storage for a new control process. Deployment provisioning
must compare protected inference/control bytes and reject shared paths/inodes
when inference evidence exists. The adapter also compares actual key values
before start; missing/equal inference credentials cannot establish Ready and
never prevent an exact trusted stop. No real keys are copied by this source task.
No key belongs in argv, environment,
source, profile, receipt or logs. HTTP input cannot select a key or file path.

The parser permits GET/POST only. It rejects Origin, browser fetch context,
WebSocket upgrades, chunking, folded/duplicate headers, ambiguous lengths,
absolute request targets, malformed UTF-8/JSON, duplicate JSON keys, nonfinite
numbers and nesting beyond the fixed limit. No CORS headers are generated.
Request line: 2,048 bytes; headers: 8,192 bytes and 32 fields; body: 4,096 bytes;
response: 256 KiB. One request per connection. At most 16 connection workers
plus one deadline supervisor and one transition executor. The absolute HTTP
socket lifetime is 130 seconds; expired application calls retain their worker slot until return.
Production read and admission budgets are explicitly 60 seconds each (generic
Application defaults remain 10 seconds; configured values are capped at 60).
A normal status/catalog read can spend 60 seconds refreshing under the lease
then 60 seconds on fresh observation/catalog. Use a bounded 140-second client
timeout. Storage-loss recovery may request an additional 60-second observation,
so that failure path can still exceed the absolute transport deadline. Ticket
expiry still prevents late admission from mutating; a client disconnect does
not cancel an acknowledged operation. Transition deadlines and all connection,
header and body limits remain unchanged.
The transport closes excess connections. It writes no access/body/error logs.
Responses and journal fields use explicit allowlists; exception text is never
returned. Malformed framing can be rejected before authentication is parseable.

## Versioned routes and response semantics

| Method and path | Pair contract |
| --- | --- |
| GET `/control/v1/catalog` | Pair status and installed deployment entries with endpoints and context evidence. |
| GET `/control/v1/status` | Both slots, modes, readiness, freshness and mutation state. |
| GET `/control/v1/status/glm` or `/control/v1/status/qwen` | One target slot. |
| POST `/control/v1/start` | `target`, `deployment_id`, `expected_active`, `expected_generation`. |
| POST `/control/v1/switch` | Start fields plus `allow_interrupt`. |
| POST `/control/v1/stop` | `target`, `expected_active`, `expected_generation`. |
| POST `/control/v1/restart` | Stop fields plus `allow_interrupt`. |
| GET `/control/v1/operations/{id}` | Operation receipt, status, deadline and sanitized failure/outcome. |

There is no HTTP `/select` or mode-switch route. Use a targeted switch to select
and start the desired deployment. Legacy singleton requests omit `target`;
in pair mode follow the explicit target requirements above.

Mutations require `Content-Type: application/json` and `Idempotency-Key`
(1–128 ASCII letters/digits or `_.:-`). IDs are bounded registered deployment
IDs. No arbitrary model names, URLs, paths, flags, environment, image references,
commands or profile contents are accepted. Unknown/extra fields are errors.
An identity is a 64-character lowercase opaque SHA-256 value or null;
generation is an integer, never a JSON boolean. Switch example:

```json
{"target":"glm","deployment_id":"qwen38-27b-q0-480000-yarn4-bf16kv","expected_active":null,"expected_generation":1,"allow_interrupt":false}
```

The null identity/generation above is illustrative for a stopped target only.
Use values from a fresh response for that same target. Acceptance returns 202 with `operation`
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
including its anchored guard report. U1B also calls actual `create_args(d)`
before old-stop: the base `prepare_start` alone omits local image tag/ID and
entrypoint validation. L1B incorporates that same call into prepare_start;
U1B's repeated read-only validation is retained. Missing/mismatched images and
invalid entrypoints must leave the old backend running. Configuration-only `dry_run` cannot replace
it. Then stop the old backend, prove it stopped, select/start the target, observe
its actual outcome and persist it. Failure never automatically resurrects the
old model. An invalid target or failed preflight leaves the old backend running.

An ordinary switch preserves the current trusted Manager boot preference,
`manual` or `resume`. The production adapter reads and validates this preference
inside its bounded select call while holding the same canonical lease, then
passes it explicitly to Manager selection. Unreadable or invalid state refuses
selection through the existing failure path. No request field sets boot policy.
After a successful switch, desired intent is `running`; boot-start resumes the
selected model only when the preserved preference is `resume`.

An explicit API stop persists `desired=stopped` independently of boot preference.
A stopped/resume selection stays stopped across service restart and boot-start;
a later explicit switch deliberately starts its chosen model while preserving
resume. CLI selection retains its existing default/explicit policy behavior.
Deactivate still clears selection and resets manual; boot-stop preserves desired
intent. Recovery and volatile stop retain the persistence limits documented below.

U1 owns semantic generation: the counter changes when selected deployment,
desired running/stopped intent, immutable container/start identity, or actual
running state changes. It does not change on polling times or health checks.
The identity includes instance, deployment, immutable container ID and a digest
of image ID plus freshly observed Docker `State.StartedAt`, so same-profile stop/start cannot reuse stale client expectations.
Reads reconcile under nonblocking canonical admission when idle. If another
owner is busy, status still observes freshly but may return
`generation_current:false`; mutations reconcile again and fail stale requests.
Unknown observation never becomes Ready based on saved state.

A running backend requires `allow_interrupt:true` for a switch. Direct inference
requests and agent sessions have no lifecycle lease, drain guarantee or session
reservation. `switch_effect` is `interrupts_inference` for singleton state and
`interrupts_target_inference` for slot state. Stop may terminate the explicitly
targeted model's in-flight response/stream. The peer is not stopped. Stop during another transition returns 409; no
preemptive cancellation or force-kill route exists. The source service template's
process termination and reboot behavior require later live acceptance.

Deadlines are finite (default operation 8,000 seconds, maximum 14,400; production
reads/admission 60 seconds, generic defaults 10, maximum 60). The explicit test
port must honor each supplied monotonic deadline. The executor checks before/after bounded calls and retains
ownership while a call is outstanding. It never releases a live lease to admit
another model because a timer elapsed. Session Docker, probe, host-guard and Storage-runner subprocess calls are capped
to their supplied remaining deadlines. Actual L1 loader calls precede session
wrapping and retain L1's finite per-call limits (normally 30 seconds), so an
unhealthy loader can outlive the HTTP admission/read budget. Timed-out admission
cannot proceed to destructive work; its slot/lease remain owned until it returns.
Filesystem/kernel calls and artifact hashing cannot be forcibly cancelled by a
Python thread. Installed-host timing remains an acceptance gate.
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
path. An acknowledged durable receipt remains in the durable journal even if its
running-update write fails and the stop moves to volatile recovery; subsequent
successful saves retain its idempotency digest for restart replay. A separate
volatile result window contains at most 16 recovery stops;
these keys/results expire on process restart or replacement by later recovery
stops. Durable receipts are preserved. Such receipts and outcomes explicitly
return `state_persisted:false`. Restore registered storage and repeat stop
before reboot to persist stopped intent. When the durable journal is unavailable
after restart, the trusted recovery observation supplies a volatile generation;
clients must refresh status before stop. Restoring the journal never rewinds
the current process counter. The journal can never turn a volatile
stop into a durable stopped-intent claim.

## Catalog, evidence and discovery

Port 30000 is reserved for control. An installed inference deployment configured
on that port is unavailable and cannot be selected until its lifecycle owner
assigns a nonconflicting inference port.

The reviewed roster has exactly two model identities, **GLM5.3** and
**Qwen3.8-27B FP8**, and the three deployment instances listed above. ACTIVATE
owns the protected installed snapshot and selected intent. The catalog lists
installed published profiles; saved state or acquisition evidence alone does
not add entries or prove live availability. Historical alternatives and extra
models are outside this reviewed pair.

The catalog consumes generic trusted registered model/deployment/runtime and
small acquisition-evidence DTOs. Multiple deployments per model and a third
future model require no routing code rewrite. Missing/uninstalled/historical or
research-only entries are excluded. An installed
record with failed current mount/profile checks is unavailable. Catalog/status
never scan or hash large weights; full start preflight revalidates artifacts.

Records include stable deployment/model IDs, display name, immutable revision,
backend/runtime identity, context, quantization, installed bytes, resource
estimates/measurements with evidence, installed verification time and
`start_revalidation_required:true`. Capabilities are `verified`, `declared`, or
`unknown`; verified requires actual end-to-end evidence. A parser flag or model
list cannot prove tool calling. Evidence references are bounded opaque IDs.

`context_limit` remains the configured deployment limit. The accompanying
`context` object separates declared configured tokens, root-reviewed accepted
configured capacity, and largest occupied context. Legacy profiles without a
structured receipt retain unknown accepted and occupied capacity. Pair profiles
use the protected receipt validation described above; no Ready backend or short
probe can supply that receipt. Historical 32K test limits, 2048 output budgets
and TP2/1M declarations do not establish accepted pair capacities.

Production discovery reads protected deployment/model/runtime profiles via the
actual L1 `Manager.deployment`, validates the existing protected completion
receipt through `Manager.check_completion`, and checks registered source paths
and runtime attestations. `installed_verified_at` is when that small receipt
metadata was checked, not acquisition time or a fresh payload hash. Historical
attestation without a completion receipt is insufficient for listing. Current
source schemas contain no structured capability verification; capability fields
stay unknown. Resource acceptance in the separate pair receipt does not by itself
create catalog GPU/RAM measurement DTOs. Unsupported future profiles remain unavailable until
the lifecycle owner accepts them; the catalog contains no per-model exception.

Ready requires trusted immutable identity, matching deployment, safe network,
authenticated expected-model response and runtime health. Loading requires an
owned live operation. Saved state and `/v1/models` during warmup are insufficient.
Missing data remains unavailable/unknown.

By default an endpoint contains `base_url`, `served_model`, `authentication_required:true`,
`server_relative:true`, `address_scope:server_loopback`, and `ready`. Its URL is
relative to the server's loopback, not the remote client's. Port and alias may
change with each switch. Tunnel that port, use the separate local inference key,
and refresh discovery before reconnecting. The optional approved LAN DTO policy
is defined below; there is no permanent model-selection URL.

## Source deployment and verification handoff

The historical installer contract (currently paused) is checked in at
`reports/u1b-installer-contract.md`. `scripts/control/llm-control.service.in`
installs as **llm-control.service** with only `@REGISTERED_DATA_ROOT@`
substituted from the fixed protected storage registration. Source root is
`/usr/local/lib/llm-server/control-api`; `WorkingDirectory=/`. Source imports
and the control key must be on the root filesystem. The exact required recovery
import list and normal-only resources are in `scripts/control/source-closure.json`.
The separate directory respects L1's existing exact boot-recovery file set.
No model, instance, data directory or profile is required just to start the
listener. Normal operations retain all full gates. L2VM must publish the reviewed
closure, protect all ancestors, and provide `/run/llmctl` root-owned mode-0700 via boot
tmpfiles without removing its shared recovery record on unit shutdown.

Fixed config: `/etc/llm-server/control.json`, root:root 0600, defaults to
`{"schema_version":1}`, with the optional `advertised_endpoint_policy` setting
defined below. No path/host/port/command/backend/environment overrides.
Journal: registered data role plus `services/llm-control/operations.json`,
root0600. Reads use actual `binding.read_json`; writes use actual
`Manager.persistent_json` and its anchored storage owner. Missing/corrupt/unmounted
storage has no root-disk journal fallback.

The unit retains hardening and writes only registered data and canonical `/run`.
Its optional data write path permits startup when that path is absent. No data
`BindsTo`, `RequiresMountsFor` or mount condition may disable recovery. Systemd's
[credential and filesystem namespace contract](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml)
supports the fixed system-unit credential path; actual installed namespace,
mount-loss propagation, Docker/guard access and shutdown still require Linux QA.
No client Docker group or sudo grant is provided. Application logging is disabled.

Verification (worker-local, synthetic resources; no VM/model/image operations):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PYTEST'
import sys, unittest
sys.path.insert(0, 'scripts')
import lifecycle, install  # Prevent tests/lifecycle from shadowing real modules.
suite = unittest.defaultTestLoader.discover('tests', pattern='test_control*.py')
raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
PYTEST
python3 -I -B scripts/control/serve.py --help
python3 -I -B scripts/control/serve.py --check-binding
```

The worker `--check-binding` must exit 3 because it is not the fixed protected
installation. Installed success exits 0 with `binding_validated`, no listener and
`normal_lifecycle_acceptance:not_performed`. It checks source/config/control
credentials, not package/storage/backend acceptance. Ordinary invocation starts
only `127.0.0.1:30000` after those checks. No production fixture flags exist.

Local HTTP tests use the actual adapter, Manager and canonical lease with
controlled Docker/storage/probes and disposable credentials. The real-writer
regression separately records the base L1B dependency. A copied recovery-import
closure is tested in a fresh process from `/`; this does not simulate installed
systemd. See `reports/u1b-control-binding.md` for exact counts and evidence limits.
Real two-installed-model switches, discovered-endpoint inference/OpenCode,
interrupted inference streams, Linux mount detach, service/reboot recovery and
whole/fresh installation remain NOT_TESTED. Installer work is paused; live acceptance owners must
complete those checks after combined review.

## Current ai-vm advertised endpoints (L2 source contract)

The protected root-owned mode-0600 `/etc/llm-server/control.json` may select the N1S policy:

```json
{"schema_version":1,"advertised_endpoint_policy":"private_network"}
```

No host, port or URL override is accepted. `read_advertised_policy()` consumes
`control.private_network.load_policy()` with no arguments after root source
validation. Only the N1S fixed protected `/etc/llm-server/network.json` supplies
`10.156.100.60` and role ports 30000/30002/30004. The control listener and every
backend endpoint remain authenticated loopback. N1S owns the private transport.

Public catalog/status DTOs use validated profile placement and ports. GPU0
Qwen uses the historical private network role `glm` on 30002; GPU1 Qwen uses
`qwen38` on 30004. Optional GPU0 GLM also uses `glm` on 30002. The served alias
remains the actual profile alias. An approved mapped endpoint reports
`address_scope:"private_network"`, `server_relative:false`; unmatched ports
retain their loopback/tunnel DTOs. Request headers never choose the origin.

The optional policy is resolved at control startup. Missing or invalid N1S
policy raises the safe `PrivateNetworkError` and falls back to the existing
loopback/tunnel DTO; it does not disable local authenticated control, status,
or trusted stop/recovery. Configuration and source integrity failures still
fail closed. The N1S Python module is part of the root source closure, but the
network policy file is not a recovery dependency. A subsequently changed
protected policy requires control restart to refresh this DTO snapshot.

Advertisement does not prove a reachable listener, firewall protection or
remote authentication. Endpoint `ready` continues to reflect existing backend
observation; direct LAN acceptance remains Worker1/remote-client work. Current
transport is trusted LAN HTTP. No TLS, CORS or frontend behavior is introduced.

The installed two-model source selection and real receipt prerequisites are in
[the L2 snapshot handoff](l2-live-snapshot.md). Configured context is declared;
occupied context remains unknown without separate live evidence. Focused
source checks: `python3 tests/test_l2_advertised_endpoints.py -v` and
`python3 tests/test_l2_control_runtime.py -v`. Actual deployed service, Linux
mount loss and inference remain **NOT_TESTED** by these checks.
