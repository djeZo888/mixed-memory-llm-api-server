# Status registry (H006 source candidate)

The independent status process loads `ai-harness/config/system-registry.json`
from the reviewed release at startup. In an installed layout the exact location
is `@HARNESS_DIR@/config/system-registry.json`, adjacent to `server/`; both
`server/src/system-registry.ts` and compiled `server/dist/system-registry.js`
resolve that same file. Ship the config with the reviewed server build. It is
trusted release configuration with the same protected deployment/ownership
boundary as server code, not writable through any HTTP API. There is no browser,
request, URL or environment override. Invalid configuration fails startup. Restart
of the status process to load a reviewed change is deployment, outside this source
candidate's authorization.

`nodes` controls enumeration and display names. Each `node-v1` observer resolves
its `observation.transport` through `transports`, then performs only
`GET /control/v1/node/status`. `services` joins each host's `observation_key` to
its native service row, retaining configured rows when absent. Duplicate IDs,
duplicate observation keys, unknown transport/credential references, malformed
fields, dangling/cyclic parents and invalid placements fail closed. Limits are
16 nodes/transports and 128 services/components. One existing ObserverCache per
node polls every 5 seconds with a 2-second deadline and a 15-second freshness
threshold; hung work cannot spawn replacement probes. GET status serves cache
only. The HTTP adapter rejects redirects and caps responses at 512 KiB.

## Transport and credential boundary

Default references map `ai-vm-private` to private IPv4 `10.156.100.60:30008`
and `local-helper` to `/run/ai-harness-admin/helper.sock`. The local-helper
binding is accepted only for `ai-harness`; unfamiliar nodes cannot fall through
to it. Existing action-node bindings remain pinned to their existing owner
endpoints. Generic passive transports accept literal private IPv4 (RFC1918) or
explicit IPv4 loopback, valid ports, and an explicitly declared protected
credential reference. No DNS, wildcard, public IP, IPv6, caller-selected path,
redirect or arbitrary Unix socket is accepted.

`credentials` maps logical IDs to protected systemd credential names, never to
secret values or arbitrary file paths. `control-api-key` is reserved for the exact
existing ai-vm node and `10.156.100.60:30008`; a third node cannot reference that
transport/key, even if it points at the same endpoint. Startup resolves this
existing credential through unchanged `AI_HARNESS_CONTROL_KEY_FILE` at
`/run/credentials/ai-harness-status.service/control-api-key`.

Each additional node requires its own unique logical reference and a separately
provisioned `node-...` systemd credential under that same fixed protected mount.
The existing status credential loader's root ownership, exact immutable tmpfs,
ACL mask modes, protected ancestry, nofollow, identity and post-read checks are
reused without weakening the control-key path. Duplicate references/names, reuse of one credential reference across transports,
undeclared references, missing/unsafe files, and token values equal to any other
loaded node or the control token fail closed at startup. No fallback credential.
The transport/credential maps and values are never returned by the status API.
This patch creates no keys, accounts or credential files.

To add a compatible third passive node, add an operator-reviewed transport such
as the following, then a node and its expected service rows. This example is
configuration only and was not contacted or provisioned. First declare a
credential reference in `credentials`:

```json
{ "id": "lab-observation", "systemd_credential": "node-lab" }
```

A separately authorized owner must provision that distinct credential and add a
reviewed `LoadCredential=node-lab:<protected-owner-source-file>` to the existing
status systemd unit. The loader requires the same protected modes/ACL provenance
as the current control credential; never copy the ai-vm token for this purpose.
Then add the passive transport:

```json
{
  "id": "lab-status",
  "kind": "private-http",
  "host": "10.156.100.62",
  "port": 30008,
  "socket_path": null,
  "credential_ref": "lab-observation"
}
```

```json
{
  "id": "lab",
  "display_name": "Laboratory host",
  "observation": { "adapter": "node-v1", "transport": "lab-status" }
}
```

```json
{
  "id": "lab-service",
  "node_id": "lab",
  "display_name": "Laboratory service",
  "observation_key": "native-service-id",
  "owner": "reviewed lab owner",
  "capabilities": [],
  "endpoint_ref": null
}
```

The host must already implement the bounded passive v1 schema with
`schema_version: 1`, exactly matching `node_id`, and native observation envelopes
(`state`, `observed_at`, `age_ms`, `freshness`, `reason`) on node, inventory,
service and resource data. Service keys must match their configured observation
keys. Missing/malformed metrics stay null; incomplete observations stay unknown.
Authentication must already accept that node's separately provisioned credential,
with protected provisioning and trusted private-network firewall/TLS policy
approved for that peer. The current ai-vm administration token is never an
additional-node credential. A node without a compatible observer can use
`{"adapter":"unsupported","transport":null}` to remain visible as unknown.
The local synthetic third-node fixture proves the generic passive path; no extra
host was contacted.

## Evidence, components and action authority

Public v1 remains additive: `registry_version`, node `display_name`, service
placement/metadata, separate node `components`, and sanitized `node_manager` /
`support` facts are added. `configured_capabilities` is distinct from native
`installed_capabilities`; `model.control` is retained. Native timestamps and
independent ages survive joins and cached transport failures. Historical values
may remain visible in resource details with stale/unknown evidence; the top
summary and current service health never treat them as fresh proof.

Components include in-process gateway, image broker and dispatch; on-demand task
and tool capabilities; local proxy/admin/egress/task-slice support; SearXNG
container support; and Worker1-provided ai-vm unit/socket placement. The supplied
Worker1 inventory was observed on 2026-09-26 around 10:00–10:02 UTC; its transient
unit states are not embedded as live status. Only producer `node_manager.running`
proves that informational process state. Other ai-vm support rows remain unknown
until Worker1's producer supplies separately reviewed observations. No ai-vm
producer is changed here.

The existing local helper adds four fixed observation-only unit reads: nginx,
admin, egress and task-slice. Four capped independent polling slots are separate
from lifecycle journals, service generations and action `SERVICES`. Status GET
performs no command. `active/exited` is a valid oneshot state; no PID requirement
turns it into a failed daemon. A socket-triggered inactive proxy is not a failure
claim. Process/unit state does not prove API readiness, admission or task policy
correctness. In-process and on-demand capabilities have
`independently_restartable=false`, unknown health, and no inherited parent
readiness. Separate support rows always have `actions: []`; restartability
metadata describes ownership, not permission.

The seven reviewed action IDs remain `qwen-gpu0`, `qwen-gpu1`, `image`, `control`,
`harness`, `search`, `status`. Existing node/GPU action ownership, confirmation,
freeze/lease, CAS and durable no-replay safeguards remain in force. Only those
fixed service identities on their original nodes can appear in the action menu.
Third nodes and extra services/components are read-only, even if their producer
advertises generations or action fields. Registry changes confer no action rights.

## Inventory placement versus execution

`endpoint_ref` is a validated informational reference to existing runtime
configuration, **not consumed by gateway/inference clients in this patch**:

| Reference | Current runtime binding | Existing owner/source |
|---|---|---|
| qwen-gpu0-private | ai-vm private IPv4 port 30002 | gateway.ts / backend-readiness.ts |
| qwen-gpu1-private | ai-vm private IPv4 port 30004 | gateway.ts / backend-readiness.ts |
| image-private | ai-vm private IPv4 port 30006 | image-upstream.ts |
| control-private | ai-vm private IPv4 port 30000 | existing model control transport |
| harness-local | ai-harness IPv4 loopback 8080; gateway 8081 in same process | main.ts / gateway.ts |
| search-local | ai-harness IPv4 loopback 8082 | existing SearXNG unit / task profile |
| status-uds | ai-harness independent status UDS | status-main.ts |

The table records reviewed current source bindings; it is not automatic live
endpoint validation. Observation transports are actually consumed from the
registry; workload endpoint consumers remain existing constants/configuration.
Future shared consumption requires a separate root-reviewed change. Editing
placement does not migrate data/services, provision machines, discover hosts,
change the fixed inference lanes, dynamically route models or enable node actions.

Execution placement additionally requires compatible CPU/RAM/GPU capacity and
runtime/driver versions; pinned reviewed models and runtimes; registered model,
cache, build and log storage with installed guards; existing ordinary task user,
container/cgroup/egress prerequisites; protected credentials and private transport;
and the real service/lifecycle owner with accepted capacity, health, leases and
recovery evidence. None of these are established by a displayed registry row or
source/synthetic test. The existing two-node status/helper deployment was checked
separately in [the H006 live report](../../docs/h006-closeout-20260926.md).
Deploying workloads on additional nodes, changing inference routing and installer
work remain later steps.

## Focused offline verification

Use installed locked dependencies and Node24; no package download is needed.

```sh
cd ai-harness/server
npm run typecheck
npm run build
./node_modules/.bin/tsx --test --test-timeout=15000 test/system-registry.test.ts test/status-service.test.ts test/observer-cache.test.ts test/admin-actions.test.ts test/admin-security.test.ts test/node-client-diagnostics.test.ts test/dispatch-freeze.test.ts test/status-credential.test.ts
node test/status-browser.mjs /tmp/status-desktop.png /tmp/status-mobile.png /tmp/admin-recovery.png
cd ../..
python3 -m unittest discover -s ai-harness/deploy/admin -p 'test_*.py' -v
```

The browser fixture uses already installed Playwright and Chrome against local
synthetic backends, including an offline third node, both real IDs, unified Host /
Type / State columns, nulls, desktop/mobile layout, transport loss and existing
action/recovery confirmations. It is not evidence of deployed UI or live VM health.
