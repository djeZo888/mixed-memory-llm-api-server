# U1 protected asynchronous control API

## Delivery status

U1B binds the reviewed U1 core to actual L1 `load_manager`, package admission,
canonical borrowed leases, preflight, dispatch and protected recovery APIs. The
fixed production entrypoint validates installed source/config/credentials before
opening a listener. There is no fixture fallback or runtime configuration input.
**Combined production review remains required.** The base L1/I1W anchored writer
has a known `check_path` forwarding gap. Isolated composition with committed
L1B `9cb9395` and the frozen I1c Storage overlay passes all 180 control tests.
I1c final source and combined review remain required; controlled-resource HTTP
results are not installed-host acceptance.

The API is separate from inference: IPv4 `127.0.0.1:30000`, a dedicated control
bearer key, JSON only. It serves no UI, inference proxy, agent tools or browser
control. I1c owns installation and enabling of the source unit template.

## Authentication and bounds

Every route, including unknown routes and unsupported methods, requires
`Authorization: Bearer <locally-provisioned-control-key>`. Missing/wrong keys
return the same 401 error. The installer must provision a distinct random control
key (32–256 nonspace ASCII bytes), root-owned mode 0600, and reuse it on resume.
It must never reuse the inference key. The dedicated source is fixed at `/etc/llm-server/control-api-key`, root:root
0600 on the root filesystem; the inference key stays at its registered data
path. `LoadCredential` uses that root-resident source and the service reads the
fixed `/run/credentials/llm-control.service/control-api-key` copy. Both survive
loss of model/data storage for a new control process. Installer provisioning
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
plus one deadline supervisor and one transition executor. Socket lifetime is
five seconds; expired application calls retain their worker slot until return.
The transport closes excess connections. It writes no access/body/error logs.
Responses and journal fields use explicit allowlists; exception text is never
returned. Malformed framing can be rejected before authentication is parseable.

## Versioned routes

| Method and path | Contract |
| --- | --- |
| GET `/control/v1/catalog` | Installed deployment records plus status, generation, observation and current operation. |
| GET `/control/v1/status` | Selected/desired/observed deployment, opaque active identity, generation, server-relative endpoint and freshness, plus the last completed operation. |
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
including its anchored guard report. U1B also calls actual `create_args(d)`
before old-stop: the base `prepare_start` alone omits local image tag/ID and
entrypoint validation. L1B incorporates that same call into prepare_start;
U1B's repeated read-only validation is retained. Missing/mismatched images and
invalid entrypoints must leave the old backend running. Configuration-only `dry_run` cannot replace
it. Then stop the old backend, prove it stopped, select/start the target, observe
its actual outcome and persist it. Failure never automatically resurrects the
old model. An invalid target or failed preflight leaves the old backend running.

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
reservation. `switch_effect` is always `interrupts_inference`. Stop may terminate
an in-flight response/stream. Stop during another transition returns 409; no
preemptive cancellation or force-kill route exists. The source service template's
process termination and reboot behavior require I1c/I2 acceptance.

Deadlines are finite (default operation 8,000 seconds, maximum 14,400; reads and
admission 2 seconds, maximum 5). The explicit test port must honor each supplied
monotonic deadline. The executor checks before/after bounded calls and retains
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

`context_limit` remains the configured deployment limit. The accompanying
`context` object contains `configured_tokens`, `configured_provenance` (`declared`
when configured), `verified_occupied_tokens:null`,
`verified_occupied_provenance:"unknown"`, and `evidence:[]`. Existing protected
profiles provide no structured occupied-context acceptance receipt. A Ready
backend or successful short prompt at a large configured limit supplies no such
proof. The current GLM 32K context and 2048 output settings are baseline test
limits; the eventual one-user/one-slot target is the highest practical native
context up to 1,048,576 tokens with sequential prefix reuse, subject to D3M's
measured progression and an approved final profile. U1 neither enforces these
baseline values universally nor claims that the target has been demonstrated.

Production discovery reads protected deployment/model/runtime profiles via the
actual L1 `Manager.deployment`, validates the existing protected completion
receipt through `Manager.check_completion`, and checks registered source paths
and runtime attestations. `installed_verified_at` is when that small receipt
metadata was checked, not acquisition time or a fresh payload hash. Historical
attestation without a completion receipt is insufficient for listing. Current
source schemas contain no structured capability verification or GPU/RAM evidence;
those fields stay unknown. Unsupported future profiles remain unavailable until
the lifecycle owner accepts them; the catalog contains no per-model exception.

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

The exact installer contract is checked in at
`reports/u1b-installer-contract.md`. `scripts/control/llm-control.service.in`
installs as **llm-control.service** with only `@REGISTERED_DATA_ROOT@`
substituted from the fixed protected storage registration. Source root is
`/usr/local/lib/llm-server/control-api`; `WorkingDirectory=/`. Source imports
and the control key must be on the root filesystem. The exact required recovery
import list and normal-only resources are in `scripts/control/source-closure.json`.
The separate directory respects L1's existing exact boot-recovery file set.
No model, instance, data directory or profile is required just to start the
listener. Normal operations retain all full gates. I1c must install the reviewed
closure, protect all ancestors, and provide `/run/llmctl` root0700 via boot
tmpfiles without removing its shared recovery record on unit shutdown.

Fixed config: `/etc/llm-server/control.json`, root:root 0600, exactly
`{"schema_version":1}`. No path/host/port/command/backend/environment overrides.
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
whole/fresh installation remain NOT_TESTED. I1c/I2 and live acceptance owners must
complete those checks after combined review.
