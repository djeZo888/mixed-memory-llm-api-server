# Status registry

The independent status process loads `ai-harness/config/system-registry.json`
from the reviewed release at startup. In an installed layout the exact location
is `@HARNESS_DIR@/config/system-registry.json`, adjacent to `server/`; both
`server/src/system-registry.ts` and compiled `server/dist/system-registry.js`
resolve that same file. Ship the config with the reviewed server build. It is
trusted release configuration with the same protected deployment/ownership
boundary as server code, not writable through any HTTP API. There is no browser,
request, URL or environment override. Invalid configuration fails startup. Restart
of the status process loads reviewed configuration changes. H020 permits only a
root-reviewed status release/restart; it does not authorize other service changes.

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
| frontier-private | ai-vm private IPv4 GLM 30010/v1; MiMo 30012/v1 | active-frontier.ts selects frontier.json / mimo-candidate.json and protected qualification receipt; frontier.ts / mimo-frontier.ts own workload clients |
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

## H020 model identity and selection

Each model service may declare a `model` descriptor with `display_name`,
`instance_name`, `expected_alias`, and `selection_group` (`frontier` or null).
Service display names, model labels, instance names, placement (`node_id`) and
endpoint references are trusted descriptive configuration. For example the two
Qwen instances share a model label but retain separate service IDs, expected
native aliases, instance names, endpoint references and observed deployments.
These descriptors grant no execution or action authority. Existing canonical
frontier IDs/aliases, owner nodes and endpoint references remain pinned.

`active-frontier.json` is the separate trusted selection authority, loaded at
startup by the existing selection validator. Its model is attached as runtime
`selected_frontier` metadata; selection never rewrites registry labels. Every
public node includes that loaded selection snapshot. Missing or invalid selection
fails startup rather than falling back to a different model. A reviewed status
restart is required to load changed files; changing a unit path without restarting
leaves the old process and its old configuration in memory. The repository GLM
default is not the live selection: the H020 candidate preserves deployed H019
MiMo selection bytes exactly.

Service rows expose `configured_model`, `selection` (selected, dormant, unknown,
or not_applicable), `observed_model` and `identity_status` separately. A model's
current readiness requires fresh node and service observations plus an exact
configured expected-alias match. Missing aliases remain unknown; wrong aliases
are mismatch; stale/unavailable observations cannot certify readiness. Dormant
frontier rows retain explicit observer evidence, but current ready/admitting are
null and health unknown. Neither model can borrow the other's service evidence.
Non-model services retain their existing independently observed readiness.
Browser transport failure also clears displayed current ready/admitting and model
dependency joins while retaining historical evidence with stale labels.

Measured GPU rows remain keyed by their observed UUID, with their own observation
freshness. `required_gpu_uuids` is the node's reported dependency configuration;
`affected_services` is action impact scope. Neither proves process occupancy.
The additive `observed_ready_dependents` joins a freshly observed matching model
with projected current readiness and its reported required UUID to a freshly
measured GPU row. Dormant or unknown-selection instances never enter this ready
dependency list, even when their raw observer reports ready; a dormant instance
reporting ready instead shows an explicit selection conflict in its service row. The UI explicitly
calls these ready model dependencies, not occupancy, and displays unchanged action
impact IDs separately. Missing hardware rows are never synthesized from required
UUIDs. No GPU ordinal or configured model label substitutes for UUID evidence.

Status availability does not qualify ordinary Sova chat (still paused following
the separate HTTP400 delegation failure), and does not establish independent
near-950K benchmark completion. H020 changes no workload endpoints, selection,
inference service, native owner, driver, GPU policy, action allowlist, credentials,
confirmation, dispatch interlock or queue.

### Harness engine catalog and passive app observations (H021)

The existing `harness` service may carry a bounded `engines` catalog for
MiniMax and Codex: display name, expected deployment-policy version (nullable),
preview label and descriptive capability names. It adds no services or controls.
Only the reviewed `ai-harness` / `harness-local` binding accepts this catalog and
its required `engine_health` endpoint (private IPv4, port, private IPv4 Host and
exact `/api/health` path; no credential or method configuration).
Older registries without it remain valid. On deployment, add
the catalog plus engine-health endpoint to
the **actual current registry**, preserving every model/placement entry and the
separate active-frontier selector; never replace these with repository defaults.

The existing status process observes the configured local app with bounded
`GET /api/health` (release-configured hostname/port/Host; current catalog uses
loopback 8080 and app Host `10.156.100.61`; no credentials,
redirects or retry). Its independent ObserverCache polls every 5 seconds with
2-second deadline and 15-second freshness threshold. An abort-ignoring request
retains its observer slot until settled. No native engines are started, and
this observer never calls model, control or node endpoints.

Public `nodes[].engines[]` separates `configured` catalog from allowlisted
`observed` app health: version, configured/enabled policy, preview,
protocol qualification, capability flags and per-capability qualification.
`version_evidence: app-deployment-policy` is **not an observed native process
version**. MiniMax health now explicitly reports selectable with unknown native
version and qualification; both native startup readiness values remain
unprobed. Codex still follows its existing deployment gate. Neither a package
version, app availability, node readiness nor model readiness is a startup test.

Engine rows retain the catalog when unavailable/missing, compare a reported
version only against a configured expectation, and retain last observations
with age after failure. Current selection enablement/protocol qualification
are null on stale, unavailable or mismatching observations. A wholly failed
status transport also suppresses current enablement/default in the page while
labelling retained capability data as last observed. `ready` is always null;
`actions` is empty. Capability qualification is exactly what app health reports,
not additional live acceptance or model readiness. H020's model identity,
selection, placement and observation aging are unchanged.

Focused offline qualification:
`tsx --test test/engine-status.test.ts test/status-service.test.ts test/system-registry.test.ts test/frontier-registry.test.ts`
and `node test/engine-status-browser.mjs <fresh.png> <stale.png>` after build.
The browser fixture runs local synthetic observers in existing installed Chrome;
it does not contact production or perform native/model work.
