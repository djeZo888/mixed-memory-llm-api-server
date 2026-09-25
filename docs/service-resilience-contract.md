# H005 node contract v1

Frozen by root's 2026-09-25 contract review and subsequent independent-transport
amendment. Exact shared wire fixtures are in
`tests/fixtures/service_resilience/{node-status-v1,gpu-v1,node-action-v1,node-operation-v1}.json`.
This is a source checkpoint; the implementation limits below are release gates.

## Transport and identity

The independent `llm-node` service listens only on `127.0.0.1:30008`. The reviewed
private socket proxy exposes `10.156.100.60:30008` with the existing protected
IPv4 interface/firewall policy and server-only Bearer credential. Existing
llm-control30000 routes remain unchanged. No browser or task container receives
backend credentials. The node lifetime does not require chat, control, Docker or
registered storage to be available. No node-manager stop target is exposed.

- GET `/control/v1/node/status`:200 cached partial snapshot, no collection,
  reconciliation, native health, writes, storage or lifecycle locks in GET.
- POST `/control/v1/node/actions`: typed request,202 only after canonical owner
  confirms a durable operation receipt. Unsupported owner adapters return422.
- GET `/control/v1/node/operations/{operation_id}`:200 receipt only,404 unknown;
  never replay or reconcile a mutation on GET.

Node IDs: `ai-vm`, `ai-harness`. VM service IDs: `qwen-gpu0`, `qwen-gpu1`, `image`,
`control`. Harness IDs: `harness`, `search`, `status`; gateway is a dependent
component of harness, not an independently restartable service. VM placement:
qwen-gpu0 maps to legacy `glm`, alias `qwen3.8-27b-gpu0`; qwen-gpu1 maps to legacy
`qwen`, alias `qwen3.8-27b`. Aliases do not select another deployment/model.
GPU identity is exact UUID; BDF/index are metadata only. Extra cards are unassigned.

Harness owns its independent daemon, server-only relay, same-origin CSRF, real
peer/container restriction, and browser surfaces: GET `/api/status/v1/system`,
GET `/api/admin/v1/targets`, POST `/api/admin/v1/actions`, and
GET `/api/admin/v1/operations/{id}`. The status alias does not expose mutations.
Operation IDs are namespaced by node by the relay.

## Observation and availability

The fixture fixes fields/types and represents completely unknown startup.
Snapshots carry `schema_version:1`, `node_id`, `boot_id`, nullable integer
`generation`, `affected_services`, observation metadata, `inventory`, `resources`,
`services` and `gpus`. Each independent observation carries `state`
(`ok|unknown|error|timeout`), UTC ISO8601 `observed_at`, nullable `age_ms`,
`freshness` (`fresh|stale|unknown`) and nullable allowlisted `reason`.

Poll5s; observer budget2s; stale after15s. Each collector owns at most one thread
and external command. A hung collector retains its slot until it returns; no
replacement growth. Late results are discarded. Successful cached data retains
its original timestamp across failures. Snapshot reads do not refresh evidence.

Inventory adds `boot_id`, `complete`, `observation_id`, `gpu_uuids` and
`hardware_faults`. A successful empty inventory is valid complete evidence;
failed initialization/timeout/ambiguous/malformed/other-boot inventory is unknown,
not empty-success. Nullable sensor values never prove a card missing.

Services carry semantic `generation`, `affected_services`, proven
`installed_capabilities`, `availability` (`available|unavailable|unknown`),
nullable independent `ready` and `admitting`, `required_gpu_uuids`, nullable
`hardware_latched`, `activity` (`idle|busy|unknown`), nullable `queue_depth` and
`active_requests`, `deployment_id`, `model_alias`, `configured_context_tokens`,
`max_output_tokens`, and `operation_profiles`. Unknown counts are null, not zero.
Readiness never implies idle. No Responses API claim: proven text capability is
`chat.completions`; image capabilities are `images.generations`/`images.edits`
only when verified installation evidence supplies them. Unknown installation is
an empty capability list. Configured context is distinct from measured occupied
context; known deployed text configuration remains480000.

Generations change with relevant boot/identity/selection/latch/ownership, not
metric polls. Canonical text generation remains authoritative. Unknown generation
rejects actions. A positive hardware latch survives stale telemetry; absence of
a latch reader is null, never a fabricated safe state.

Resources are independently enveloped cpu/memory/disk/network. CPU percent uses
100%=all node logical CPUs; capacity is bytes; I/O/network rates are bytes/s;
memory pressure avg10 is percent. GPU memory isMiB, powerW, temperatureC.
Current/max PCIe generation/width are separate. Temperature min/max carry
`sampling_since`; missing sensor is null. Exact names are fixed by fixtures.
No prompt/chat/credential/argv/raw exception data is public.

## Boot hardware latch

Proven absence requires matching boot ID and two distinct increasing successful
complete inventories, each fresh and collected after120s boot grace. Explicit
proven typed hardware faults may latch immediately under a reviewed producer;
this checkpoint conservatively requires two consistent fault receipts too.
Generic NVML errors/ECC counts alone are not proven hardware fault. App restart,
reset and late healthy probes in the same boot cannot clear the latch. A new boot
plus valid healthy target evidence clears it. Unknown new-boot evidence does not.
Software failure and uncertain-request quarantine are separate.

Runtime owners must enforce this latch for boot restore, manual start and image
recovery before release. Protected persistence precedes publishing transitions;
missing/unreadable state cannot silently initialize a fresh latch. Passive GET
only reads cached latch results.

## Typed actions and receipts

Required request fields: `schema_version:1`, `node_id`, `action`,
`idempotency_key`, `expected_boot_id`, integer `expected_generation`, boolean
`allow_interrupt`. Service actions add `service_id`; GPU reset adds `gpu_uuid`;
node reboot adds neither. Strict keys, no commands/paths/units/URLs. Action enum:
`service.start|service.stop|service.restart|gpu.reset|node.reboot`.

The target's status-carried affected services/activity is displayed before
explicit interruption confirmation. Stop/restart/reset/reboot require
allow_interrupt; direct clients may bypass harness, so idle UI is not proof.
Harness freezes affected dispatch before mutation; the node independently
rechecks boot/generation/identity under the existing canonical lease/owner.
Exact-repeat idempotency returns the same receipt even after target changes;
same key/different request returns409. Persist audit/receipt before dispatch.

Receipt fields are exactly illustrated by node-operation-v1.json: operation ID,
node/action/target, expected boot/generation, affected services, created/updated
UTC timestamps, reason, poll_url, status. Status enum:
`accepted|running|succeeded|failed|interrupted|unknown`. Admission targets2s;
mutation finishes asynchronously. Timeout does not mean cancelled/failed:
query receipt or retry the same key. Restart never blindly replays unfinished
operations. Reboot succeeds only after later changed-boot evidence. Unsupported
reset returns422; supported reset requires all concrete consumers stopped,
proven supported dedicated scope, and no other-GPU/global reset fallback.
Errors:400 malformed,404 unknown operation,409 stale/conflict/confirmation,
422 unsupported,503 owner/storage/deadline unavailable.

## This source checkpoint's limits

The standalone candidate collects passive boot/inventory/process/CPU/memory and
independent GPU telemetry. It deliberately reports unknown model readiness,
installed metadata, canonical generation and latch state until protected owner
adapters exist. Disk/network resource fields remain null. It is not a routing
readiness source yet. Unknown aggregate telemetry must not kill healthy in-flight
work or erase a known latch/quarantine; harness needs independent passive backend
readiness for routing.

All production mutations return422: the typed owner seam and fixture durable
receipts do not implement actual canonical action dispatch. Protected latch
persistence and enforcement exist as a tested injected component, not wired to
live owners. Runtime scheduler binding is separate required follow-up. Changing
the private port policy requires a reviewed additive policy/receipt migration;
source replacement alone must not overwrite current protected network state.
No deployment or live acceptance is established by this checkpoint.
