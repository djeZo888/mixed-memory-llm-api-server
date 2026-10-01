# Status service improvements

**State: planned; documentation only.** Updated 30 September 2026 following the
user's clarified pause and credential requirements. No UI, collector, safety
controller, credential migration or VM changes are implemented by this document.

## 1. Goals and boundaries

Make Sova's status pages readable and driven by the protected global registry,
configured hardware placement and actual observations. Add optional monitoring
of multiple baremetal hosts and a hardware-critical inference pause. Sova must
remain usable without BMC/IPMI access and on a single machine or many VMs.

During a critical pause, **keep every service running and keep models loaded and
warm wherever the runtime supports this**. Stop inference computation and refuse
new work across the system until the condition is corrected and an administrator
resumes it. Do not shut down VMs, stop model containers, restart services, reset
GPUs or unload weights as the normal pause mechanism.

The health collector, status pages, administration and cooling controls continue
running. Their small monitoring/control load is necessary; the zero-load goal
means no inference, agent/task computation, synthetic warm-up or idle busy-wait,
not literally zero CPU activity on a live operating system.

Fan-management redesign, accounts, notification delivery, general software
incidents and temporary safety exceptions are separate TODO projects. Existing
hardware-absence latches and stricter thermal backstops remain independent.

## 2. Page layout

Increase the desktop content maximum from 1,208 to **1,450 px**, approximately
20%, and align the header and content. Keep responsive padding. Use four tabs:

| Tab | Contents | Visibility |
|---|---|---|
| Services | Model instances, software services, placement, readiness, capabilities and evidence | Status and admin |
| Resources | CPU/GPU occupancy, RAM/VRAM, storage and network transfer rates | Status and admin |
| Hardware health | Temperatures, fan/pump speeds and voltage readings | Status and admin |
| Manage | Existing registered administrative actions and future Resume control | Admin only |

Reuse current status/admin routes; retain the selected tab in the URL hash with
refresh, back/forward and direct-link support. Provide accessible tab semantics,
keyboard navigation and a horizontally scrollable tab bar on narrow screens.
Read-only status must not expose administrative controls or credential metadata.

### Tables and cards

- Capability table: default **180 px capability**, **220 px qualification**,
  remaining width for evidence. Use human labels such as “Native delegation”.
- Service table: default **320 px service**, **140 px host**, **100 px type**,
  **120 px state**, **240 px health/activity**, remaining width for evidence.
  Treat these as configurable desktop column widths; use local table scrolling
  when the viewport cannot fit them.
- Keep host names such as `ai-harness`, short identifiers, units and state badges
  on one line. Remove indiscriminate word breaking from label columns. Wrap long
  paths, UUIDs and evidence text in their own cells or expandable details.
- Let concise resource cards share a row on wide screens and stack on smaller
  screens. No whole-page horizontal overflow.
- Distinguish configured capability, observed readiness, unknown capacity,
  stale observations and dated qualification. A healthy service is not proof
  that every workflow has passed acceptance.
- Move GPU temperatures and other health sensors into Hardware health; GPU
  occupancy tables retain identity, placement, utilization and memory figures.

A critical banner remains above the tabs. Hardware health groups readings by
**Baremetal #1**, **Baremetal #2**, etc., with configured VM membership and GPU
UUIDs. Cards show descriptions, value, unit, sample age and freshness/error state.

## 3. Protected global configuration

Extend the existing [system registry](../ai-harness/docs/status-registry.md)
through a versioned, validated schema migration. The current strict validator
does not accept these new fields. Existing node, service and credential contracts
must keep working; this example is **future schema**, not deployable configuration.

### Global variables

| Proposed key | Default | Meaning |
|---|---:|---|
| `sensor_poll_interval_ms` | **2000** | Start a batched sensor poll every two seconds |
| `sensor_request_timeout_ms` | 2000 | Deadline for an individual provider request |
| `sensor_freshness_timeout_ms` | 15000 | Maximum age before a reading becomes unavailable |
| `numeric_critical_dwell_ms` | 10000 | Continuous verified numeric violation before a critical incident |
| `critical_recovery_safe_dwell_ms` | 30000 | Continuous safe readings required before admin Resume |
| `paused_request_timeout_seconds` | 3600 | Maximum retained pause duration for resumable/queued work |
| `layout.page_max_width_px` | 1450 | Desktop content width |
| `layout.table_column_widths_px` | See section 2 | Label/qualification/service table widths |

Use integer milliseconds for polling and dwell times, and seconds for retained
request expiry. Validate positive values and sensible bounds, including
freshness greater than the polling/deadline interval. Longer configured polling
intervals necessarily increase detection latency; do not promise a two-second
reaction when an operator chooses a longer interval. Batch reads, prohibit
overlapping polls to the same provider, and expose missed/deadline-expired polls.

### Hardware, placement and sensor records

- `baremetal_hosts`: stable ID, display name, optional BMC transport and
  credential reference, and associated registry node IDs. The initial `bare1`
  contains `ai-vm` and `ai-harness`. Associations are configurable, not inferred
  from IP addresses. Unassigned VMs remain visible.
- GPU assignments use **UUIDs**, never enumeration indices. GPU absence or a
  reordered device list must not break the collector or hide other devices.
- Each sensor has a stable Sova ID and a structured source containing
  `target_kind`, `target_id`, `provider` and `source_sensor_id`. Display a
  qualified identifier such as `bare1.ipmi.CPU_FAN` or
  `GPU-<uuid>.nvidia.temperature.gpu`; do not parse ambiguous dotted strings to
  establish ownership. Source IDs containing punctuation remain intact.
- Configure display name, optional description, unit, visibility, optional
  upper/lower warning thresholds, optional upper/lower critical thresholds,
  and an explicit unavailable-reading policy.
- Unit declarations must agree with the qualified provider. In particular,
  NVIDIA fan percentage is **not RPM**. Do not convert it to RPM without an
  independently supported measurement. Verify BMC fan units before arming limits.

Illustrative configuration, with no secret values:

```json
{
  "hardware_health": {
    "sensor_poll_interval_ms": 2000,
    "sensor_request_timeout_ms": 2000,
    "sensor_freshness_timeout_ms": 15000,
    "numeric_critical_dwell_ms": 10000,
    "critical_recovery_safe_dwell_ms": 30000,
    "paused_request_timeout_seconds": 3600,
    "baremetal_hosts": [
      {
        "id": "bare1",
        "display_name": "Baremetal #1",
        "node_ids": ["ai-vm", "ai-harness"],
        "bmc": {
          "provider": "redfish",
          "endpoint": "https://bmc.example.lan",
          "credential_ref": "bmc-bare1-monitor",
          "trust_ref": "bmc-bare1-certificate"
        }
      }
    ],
    "sensors": [
      {
        "id": "bare1-cpu-fan",
        "source": {
          "target_kind": "baremetal",
          "target_id": "bare1",
          "provider": "redfish",
          "source_sensor_id": "CPU_FAN"
        },
        "display_name": "CPU_FAN",
        "unit": "rpm",
        "display": true,
        "warning": {"lower": 500},
        "critical": {"lower": 200},
        "unavailable_policy": "warning"
      }
    ]
  },
  "layout": {
    "page_max_width_px": 1450,
    "table_column_widths_px": {
      "capabilities": {"name": 180, "qualification": 220},
      "services": {"name": 320, "host": 140, "type": 100, "state": 120, "health": 240}
    }
  }
}
```

The example's sensor ID is illustrative; discovery must supply the qualified
provider's real ID. A host may declare more than one provider transport. Do not
silently substitute a protocol or guess credentials. Invalid settings fail
configuration activation while the previous validated configuration remains in
effect. Public status gets a sanitized projection; private transport addresses,
credential references and certificate material are not public sensor fields.

## 4. Secure BMC/IPMI credentials

**Recommended offline mechanism: systemd encrypted credentials.** Keep only a
logical `credential_ref` in the registry. Provision its secret interactively
without echoing it, and store an encrypted blob outside Git under a root-owned
credential store, for example `/etc/credstore.encrypted/sova-bmc-bare1.cred`.
Use owner-only store permissions and mode `0600` for encrypted blobs; secret
provisioning must not leave a plaintext temporary file behind.

Use `systemd-creds encrypt` and `LoadCredentialEncrypted=`. At collector service
activation, systemd decrypts the credential into its service credential directory
identified by `$CREDENTIALS_DIRECTORY`. Bind encryption to the host key, with
TPM2 binding where available; do not require a TPM in every VM or use null-key
encryption. The collector needs plaintext in memory to authenticate. Encryption
does not protect secrets from a compromised authorized collector or host root.
[Systemd credential documentation](https://systemd.io/CREDENTIALS/)

Run the collector under a dedicated identity with service mount isolation. Do not
give the web application, LLM processes or task containers access to its
credentials. Do not put passwords in command-line arguments, environment values,
URLs, logs, API output, crash reports, unit literals or repository examples.
Sanitize provider failures and bound/redact diagnostic output.

Use a **read-only BMC account** for sensor collection where firmware supports it.
Reading sensors normally does not need Administrator; qualify the exact board
and firmware rather than assuming that role names imply identical permissions.
Keep fan-writing authority in a separate future actuator service and credential.
The current board's administrator-only fan API does not justify sharing that
credential with every Sova component.

Prefer verified HTTPS Redfish, with a trusted CA or configured certificate pin;
do not silently disable certificate checking. If using IPMI LAN, require a
qualified encrypted/authenticated IPMI 2.0 session. Future SNMP support should
use qualified SNMPv3 authenticated/privacy access, not unprotected communities.

Document rotation, provisioning on a replacement VM and protected recovery.
Systemd credentials are acquired at service activation, so rotation restarts
only the collector after staging/verification; model services remain untouched.
Re-provision host-bound encrypted credentials after migration. A decryption or
authentication failure becomes unavailable telemetry and follows its configured
policy; no plaintext fallback. Existing private credential files are migrated
only in a future authorized implementation, never read or copied into this plan.

## 5. Initial hardware-health profile

Discover and retain actual sensor IDs and units before activating this profile.
Descriptions are optional; thresholds are configurable, with strict comparisons
**above** an upper value and **below** a lower value. Equality does not trigger.

| Sensor | Unit | Description | Warning | Critical |
|---|---|---|---|---|
| CPU Package Temp | °C | — | >80 | >90 |
| CPU_FAN | RPM | — | <500 | <200 |
| CHA_FAN1 | RPM | Cooling internal Blackwells | <500 | <200 |
| CHA_FAN3 | RPM | External Blackwell | <500 | <200 |
| CHA_FAN4 | RPM | Cooling memory | <500 | <200 |
| DIMMD1_Temp | °C | Top memory stick | >60 | >70 |
| DIMMH1_Temp | °C | Bottom memory stick | >60 | >70 |
| W_PUMP+ | RPM | CPU Water Pump | <500 | <200 |
| +12V | V | Power rail 12V | <11.5 | <11 |
| Configured GPU temperature, per UUID | °C | Configurable | >80 | >85 |

Omit unknown/unsupported limits rather than inventing readings. Preserve stronger
existing runtime guards, including immediate thermal backstops. This plan does
not weaken the existing GPU guard or change the fan policy at 70/65 °C.

Each sensor explicitly selects one unavailable-reading policy:

| Policy | Behaviour |
|---|---|
| `ignore` | Display unavailable; do not create a warning or critical incident |
| `warning` | Display unavailable warning; proposed default for the initial profile |
| `critical_after_30m` | Critical after 30 minutes of continuous unavailability |
| `critical_immediately` | Critical when the reading is declared unavailable |

Missing, invalid, unit-mismatched or stale readings are **unavailable**, not zero,
healthy or an indefinitely reused sample. Availability timers are separate from
the 10-second numeric dwell. Never infer ten seconds of continuous numeric
violation across a missing sample; cancel that dwell and apply the availability
policy. Reset an unavailability timer only on a fresh valid reading. Display both
the last known value and its age without treating it as current.

## 6. Observation and API design

Reuse the status collector's cached-read approach. Initial adapters cover BMC
Redfish/IPMI sensor reads and node-local NVIDIA NVML readings. Keep providers
registered and typed, so later protocols can be added without arbitrary shell
commands or browser-supplied URLs. Prefer stable raw sensor descriptors over
array offsets, partial-name matching or undocumented numeric IDs.

Collect each host/provider once per interval and publish normalized readings with
source identity, observed timestamp, unit, freshness, availability and a sanitized
error code. Status HTTP requests read the cache; they do not initiate BMC calls.
Use bounded deadlines and a monotonic clock for safety dwell/expiry. Persist
incidents across collector restarts without counting downtime as confirmed safe.

Add versioned hardware-health output to the status API, retaining existing node
and component response compatibility. Report all configured hosts, their VMs,
all services and available/unavailable GPU instances. BMC availability must not
be a prerequisite for resource statistics from existing node OS collectors.
Do not infer actual CPU power/load or memory occupancy from temperatures alone.

## 7. Warning display and critical inference pause

### Warnings

When the admin status page is opened, show a dismissible warning overlay listing
current warnings. `X` closes the overlay, not the incident or its monitoring.
New warning incidents may show it again. Keep warnings visible in Hardware
health. End-user chat does not need raw hardware/transport detail.

### Critical detection and admission

A fresh numeric critical condition continuously lasting **more than 10 seconds**
latches a hardware-critical incident and immediately closes system-wide work
admission. Availability critical policies use their own deadlines without an
extra numeric dwell. An existing stricter safety guard can act earlier.

The authoritative pause gate covers every configured inference instance, both
harness engines, their gateways, native subagents, compression/auxiliary calls,
image jobs and directly exposed managed inference APIs. Reject new chats,
follow-ups and other computation with HTTP **423 Locked** and a stable
`hardware_critical_paused` reason. Stop queue dispatch. In-flight admission races
must settle through the same gate; a browser-only disable is insufficient.

Persist the incident, affected resources, gate generation and owner receipts.
Send idempotent typed pause operations to each node. Lost contact is **pause
unconfirmed**, not evidence that remote inference stopped. Local node safety
participants retain applicable policy and the pause latch across controller
restarts. Controller/sensor loss uses the configured unavailable-reading policy;
do not invent a separate unconditional 15-second shutdown rule.

### Active work and warm model preservation

For each runtime, implement and qualify a capability describing whether active
inference can pause/resume with its request context and model retained. A pause
must stop GPU kernels/CPU inference computation, not merely suspend HTTP output.
Generic process `SIGSTOP`, a disconnected stream or a closed gateway is not proof
of GPU quiescence.

1. Close admission before pausing owners, including child/tool scheduling.
2. Use a verified native pause for resumable work. Retain ownership, model
   weights and cache, partial outputs and continuation state.
3. If native resume is unsupported, **cancel/abort the inference request** using
   the qualified runtime request API; keep the model process/service running and
   resident. Mark this request interrupted/failed and require a user retry later.
   Never kill or restart the model service as a fallback.
4. Suspend managed agent/tool computation without losing its ownership record.
   Keep orchestration/control daemons running in a blocking state.
5. Disable adaptive idle busy-wait and synthetic warm-up while paused. Model
   residency does not require inference keepalives. Retain thermal/fan monitoring.
6. Confirm compute has settled through runtime receipts and CPU/GPU telemetry.
   Report unconfirmed/unsupported cases explicitly rather than declaring success.

**Qualification gate:** if a runtime cannot stop its active computation without
terminating its service/unloading its model, this warm-preserving critical policy
is unsupported for that runtime. Resolve that limitation before enabling the
policy for the deployed system. Do not silently relax the requirement or claim
that a nonfunctional pause provides protection. This is an implementation risk
to investigate, especially for image jobs whose current GPU cancellation is
unavailable; request cancellation support cannot be assumed.

Existing queued and genuinely paused work remains durably paused until admin
Resume or `paused_request_timeout_seconds` expires, whichever comes first.
Respect any earlier original request deadline. Expired/aborted work becomes a
clearly failed request; preserve uploads, files and partial outputs, and never
automatically replay it. Browser reconnection cannot duplicate or unpause work.

### Admin view and recovery

Show all critical conditions at the top of admin status with large red styling:
**“Sova is temporarily paused because of critical hardware readings. Correct
the listed conditions before resuming.”** Distinguish active critical readings,
fixed-but-latched incidents and nodes whose pause is unconfirmed.

Require **manual admin Resume** after all triggering readings are fresh and safe
for 30 seconds, no critical incidents remain active, and task ownership has been
reconciled. Keep missing devices unavailable; do not clear independent
hardware-absence latches. Resume retained eligible work only through its owner,
with admission reopened only for qualified healthy instances.

Verify the same services/model identities and resident weights remain ready;
normal recovery must not reload them or dispatch a fake warm-up. If actual
hardware/process failure lost residency, show that separately and use an
explicit recovery operation rather than silently treating it as a pause.

Temporary incident ignores (for example 1 minute, 10 minutes, 1 hour or 24 hours),
notifications and software-event clearing belong to the separate critical
handling TODO. They are not an initial safety bypass in this release.

## 8. Implementation sequence — future authorized work

1. **Schema and contracts:** add global variables, baremetal membership, typed
   sensor sources, credential references and compatibility migration. Document
   sanitized API output and scope of the global pause barrier.
2. **Collector and credentials:** provision a separate sensor account and
   encrypted credentials; discover exact IDs/units; add cached BMC/NVML adapters.
   Deploy in observation-only mode first, without activating critical actions.
3. **UI:** implement tabbed layout, widths, host grouping, resource cards and
   warning/critical presentation using config/API data. This can proceed in
   parallel with collector work against retained fixtures.
4. **Runtime pause qualification:** investigate each text/image runtime's native
   request pause/cancel support, resident model preservation and busy-wait
   suppression. Keep unsupported cases explicit and resolve them first.
5. **Safety coordination:** implement durable incidents, global/node admission,
   owned pause, expiry and manual recovery only for qualified runtime profiles.
6. **Acceptance and rollout:** bounded protocol/fake-sensor tests, then an
   authorized nonhazardous end-to-end pause and recovery. Publish evidence,
   capability limits and rollback instructions before enabling safety policies.

No actual overtemperature, low-voltage event, deliberate fan failure or long
model benchmark is needed to test the state machine. UI/collector rollback must
preserve active safety latches and current conversation/artifact data.

## 9. Acceptance checklist

- Desktop page is approximately 20% wider; capability/service columns are
  readable, `ai-harness` does not split, and tablet/mobile overflow stays inside
  tables. Tabs, selected-tab restore and keyboard navigation work.
- Zero BMCs is a supported configuration. Two configured baremetal hosts,
  memberships, missing GPUs and changed enumeration preserve unrelated status.
- All requested sensors, descriptions and verified units display correctly.
  Source unavailability, invalid units and stale observations stay distinguishable.
- Polling is configurable with a 2,000 ms default; deadlines, nonoverlap,
  freshness and invalid-config rejection are verified with simulated time.
- Secret values never appear in config, Git, process arguments, public/admin
  responses or logs. Collector-only access, encrypted storage, rotation and
  decryption failure are exercised; monitoring works with minimum firmware role.
- Strict threshold/equality boundaries, continuous >10-second numeric dwell,
  each unavailable policy, 30-minute expiry and 30-second safe recovery pass.
- A triggered incident closes every inference/agent/image admission path,
  including direct managed APIs and races. No new work starts during the latch.
- Existing work pauses or its **request** aborts without stopping services.
  Service/container identities and loaded weights remain unchanged; CPU/GPU
  inference compute and busy-wait cease. Monitoring and fan control remain alive.
- Unsupported native cancellation/pause is reported and blocks qualification.
  A stalled/uncertain owner or unreachable node is not labeled successfully paused.
- Paused queue/context, expiry, partial artifacts, stream state and browser
  reconnect are durable; aborted/expired work is never blindly replayed.
- Restarting the collector/controller preserves critical latches; no auto Resume
  occurs. Manual recovery checks fresh readings and owned settlement, restores
  normal blocking/busy-wait policy and avoids model reload or fake warm-up.
- Admin warnings dismiss with `X`; critical information remains prominently
  visible across tabs until resolved and acknowledged through Resume.
- Fan-management writes, general notifications, accounts and future temporary
  exceptions remain outside this feature's qualified scope.

## 10. Source starting points

- [Status registry/configuration contracts](../ai-harness/docs/status-registry.md)
- [Current status UI](../ai-harness/server/src/status-ui.ts)
- [Typed admin actions](../ai-harness/server/src/admin-actions.ts)
- [Existing hardware-absence latch](../scripts/control/hardware_latch.py)
- [Architecture and routing](../docs/sova-architecture.md)
- [Compact TODO index](README.md)

These files are starting points, not proof that the proposed schema, sensors or
warm-preserving critical pause already exist.
