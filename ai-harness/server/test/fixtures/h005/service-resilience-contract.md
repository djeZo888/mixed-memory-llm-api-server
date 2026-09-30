# H005 node contract proposal — v1, awaiting root/Worker2 review

Use existing credentialed control30000 private transport (native IPv4 loopback behind existing reviewed private access). Bearer credential remains server-only. No browser direct control access, no new port, no GET reconciliation or native /health.

- GET /control/v1/node/status -> 200 cached partial snapshot, constant bounded work, never waits on collector/lifecycle/storage; freshness is explicit. Poll every 5s; each collector deadline 2s; stale after 15s; one outstanding worker per collector, no replacements while hung. Unknown/stale/unreachable is NOT absence.
- version: `schema_version: 1`, node_id `ai-vm` or `ai-harness`. Stable services on ai-vm: `qwen-gpu0`, `qwen-gpu1`, `image`, `control`; harness owns its separate registered IDs. GPU identity exact UUID only, index/BDF metadata only. Extra GPUs remain unassigned.
- snapshot: `schema_version`, `node_id`, `boot_id` (null unknown), `observed_at` (UTC ISO8601 or null), `age_ms` (null unknown), `freshness` (`fresh|stale|unknown`), `inventory` and `services` and `gpus`. Each independent observation has `state` (`ok|unknown|error|timeout`), `observed_at`, `age_ms`, `freshness`, `reason` (allowlisted code or null). Inventory adds `boot_id`, `complete` boolean and UUID list. GPU facts include uuid, name, index, pci_bus_id, memory_total_mib, memory_used_mib, temperature_c, ecc_mode, ecc_uncorrected_volatile, pcie_generation, pcie_width; unavailable facts are null, never fabricated zero.
- service: `service_id`, `installed_capabilities` (strings), `availability` (`available|unavailable|unknown`), `reason` code or null, `required_gpu_uuids`, `hardware_latched` bool, `activity` (`idle|busy|unknown`), `queue_depth` (integer or null), `active_requests` (integer or null). Capabilities describe installation, not current readiness. Baseline capabilities: Qwens `chat.completions`, `responses`; image `images.generations`, `images.edits`; control `node.status`, `node.actions`.
- Hardware boot latch: require boot ID + two distinct fresh successful COMPLETE inventories after 120s boot grace proving target absent or explicitly hardware-faulted; malformed/ambiguous/failed inventory yields unknown. Persist latch across app restart and reset; clear only different boot + valid target inventory. No reset-induced clearing. Software unavailable/quarantine is separate.
- POST /control/v1/node/actions -> `{schema_version:1,node_id,action,service_id?,gpu_uuid?,idempotency_key,expected_boot_id,expected_generation,allow_interrupt:boolean}`. Expected boot and service generation compared under existing canonical lease before dispatch (stale -> 409); generation unknown rejects. Strict keys, actions only `service.start|service.stop|service.restart|gpu.reset|node.reboot`; IDs allowlisted, interruption confirmation required for stop/restart/reset/reboot. No shell input. GPU reset rejected unsupported unless dedicated target + capability + no consumers proven; no VM-wide safety claim.
- Accepted action -> 202 `{schema_version:1,operation_id,node_id,action,status,poll_url}`. GET /control/v1/node/operations/{operation_id} -> 200 receipt `{schema_version:1,operation_id,node_id,action,status,created_at,updated_at,reason,affected_services}`; status `accepted|running|succeeded|failed|interrupted|unknown`. Existing canonical lifecycle lease/owners/storage guards execute; no alternate lifecycle engine.
- Idempotency exact repeat returns same operation, different request same key -> 409; malformed/unknown action/target -> 400; unsupported action -> 422; capacity/storage unavailable -> 503. Persist receipt/audit before mutation, redact payload/secrets. Restart never blindly replays unfinished mutation; report unknown/interrupted. POST deadline 2s admission; async mutation finishes independently. Client timeout does not mean failed/cancelled: query receipt or retry same key. Operation read is cached/bounded; reboot success requires later boot evidence (before then accepted/running/unknown).

Fixture contract only until root and Worker2 approve. Root steering read at natural checkpoints; use first coherent source component if wider scope needs another task. No source claim establishes deployment/live acceptance.

## Frozen amendments (root review 2026-09-25)
The shared fixture `tests/fixtures/service_resilience/node-status-v1.json` fixes
field names, scalar types, enum spellings and unknown values. This section
supersedes provisional baseline capability/confirmation wording above.
Node/service/GPU targets have nullable `generation` (integer only when observed;
unknown rejects actions), `affected_services`, and each service has nullable
`ready`/`admitting`, `deployment_id`, `model_alias`, `configured_context_tokens`,
`max_output_tokens`, and `operation_profiles`. `hardware_latched` is nullable when
protected latch state cannot be read. Readiness never implies idle. Only proven
installed capabilities are listed: no Responses API promise. Target generations
change with identity/selection/latch/ownership, never metric polls. Existing
canonical text generations remain authoritative. qwen-gpu0 maps to legacy `glm`
(alias qwen3.8-27b-gpu0); qwen-gpu1 maps to legacy `qwen` (qwen3.8-27b).

Every action requires schema_version, node_id, action, idempotency_key,
expected_boot_id, expected_generation, allow_interrupt; service actions add
service_id, GPU reset adds gpu_uuid, node reboot adds neither. No other fields.
Status `affected_services` is the impact displayed before explicit confirmation.
Compare target generation and boot under canonical owner lease before dispatch;
return the same receipt on exact repeat even after target changes, conflict on
same key/different request. Request timeout never authorizes replay with a new key.
Operation receipts add service_id and gpu_uuid (null when inapplicable), expected_boot_id,
expected_generation and affected_services. All time strings are UTC ISO8601.
The exact accepted-request/receipt examples are adjacent fixture JSON files.
Unsupported dedicated reset ->422, with no global reset fallback. A VM self-reboot
cannot be marked succeeded until later changed-boot evidence. Dispatch freezing,
protected durable audit and runtime-owner enforcement are implementation gates;
wire fixtures do not claim these exist in production.

Each observation envelope includes state, observed_at, age_ms, freshness, reason.
Missing facts are null, unknown activity is `unknown`, and queue counts unknown
are null. `resources` contains independently enveloped cpu/memory/disk/network;
CPU percent defines100%=all logical CPUs of this node; memory/disk are bytes,
network and disk rates bytes/s, pressure avg10 is percent. GPU telemetry is its
own observation; UUID inventory success is independent of unavailable sensors.
Power is watts, temperature C, GPU memory MiB. Current/max PCIe generation and
width are separate. Temperature min/max include sampling_since. No nominal zeros
are substituted for absent telemetry.

Absent-target latch requires two distinct successful complete inventories after
120s of that boot. Explicit typed proven hardware fault may latch immediately;
NVML failure, ambiguous inventory, missing sensor, stale/timeout never proves it.
Latch clears only new boot + valid target; reset/app restart/late probe cannot.
All routes are additive behind existing credentialed transport. Status reads use
only cached memory and never execute collection, owner probes, reconciliation,
storage operations, writes or lifecycle locks. Collectors run independently every
5s with2s budgets; after15s evidence is stale. A hung collector permanently occupies
its single slot until it returns, preventing replacement thread/process growth.

Harness owns server-only transport, sanitized browser aggregate, CSRF/peer checks,
independent daemon and routing fallback; this repository component does not edit
harness. Unknown aggregate telemetry must not erase a positive boot latch or
request quarantine, or kill healthy in-flight work. Independently bounded passive
readiness may guide new routing where available.
