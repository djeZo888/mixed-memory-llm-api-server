# GPU fan boost and motherboard fan control

## Current H042 policy — source candidate, 1 October

The new CHA_FAN3 policy is **40% below70 C**, **80% from70 C through80 C**,
and **100% strictly above80 C**. Escalation is immediate. A reduction from100%
to80% requires30 continuous fresh seconds at <=80 C; a reduction from100% or80%
to40% requires30 continuous fresh seconds below70 C. The two dwell periods are
independent: crossing70 C resets the40% dwell, and crossing above80 C resets both.
Startup, node boot change, sample gap/regression, missing/stale telemetry,
transport error and stop demand100% and reset dwell. Stable69–78 C no longer
holds100% indefinitely. Poll5seconds and maximum telemetry age15seconds remain.

The target is unchanged: server Blackwell UUID, Zone4(CHA_FAN3), array_index3,
PWMNum3, PWMSrc0, mode4, disabled CPU source bits000, and20/45/65/90/100 C knots.
Only the first four curve duties change. Other fan zones, CHA_FAN1 and integrated
GPU fans remain untouched. Durable intents, confirmed_expected_duty, independent
readback reconciliation, lock/invariant checks and late-stop cancellation are
preserved; cancellation now covers both40% and80% lowering. Configured curve
duty is distinct from measured PWM, tach and RPM.

This candidate is source-tested on Mac with inert imports and fake backends.
The current installed controller and physical10–15second cycling are separate
qualification questions. Installation, protected authentication, latch archival,
start and stop each require an exact current finite root GO bound to worker2,
the reviewed source/helper/unit/config graph and actual current preflight.
Unknown start ownership quarantines without blind stop or retry.
See [H042 fan05 result](../reports/h042-fan05.md) for actual execution disposition.

## Retained H040 policy — reviewed source candidate, 1 October

The latest specific user override assigns CHA_FAN3 **80% at >=70 C** and
**100% strictly above80 C**. At exactly80 C the minimum is80%; an existing100%
setting is retained through78 C and any other warm reading until fresh <=65 C
telemetry persists for30 continuous seconds. Missing/stale telemetry,
startup/stop/failsafe and transport recovery conservatively request100%.
Poll5seconds, maximum telemetry age15seconds, boot/sample-gap/error dwell reset,
fixed mode4/source000/index3/PWMNum3/PWMSrc0 and20/45/65/90/100 C knots remain.
The only new fixed-channel BMC payload duties are **40/80/100**. CPU/source and
other-zone writes remain forbidden. CHA_FAN1 remains exclusively BMC/user-owned.

Prepared40/80/100 intents reconcile through READ-ONLY actuator inspection of the
unchanged full invariant and exact before/intended readback, never PUT replay.
Verified receipts are left intact by reconciliation; a following normal command
records its distinct fresh intent. Preserve all old state/receipts in a private
predeployment snapshot before any owned stop/install. Unknown/mismatch retains
uncertainty and the durable latch; do not clear it or write through it. Baselinev2,
controller lock/CAS, late-stop guard, credential protection and honest configured
curve-duty versus instantaneous-PWM/tach reporting are unchanged. Retained80
proof is not proof of the new100% startup/failsafe or >80 C tier.

The four integrated NVIDIA GPU UUIDs already use100% at >=70 C via unchanged
NVML source; the fanless/server Blackwell is excluded and uses this CHA_FAN3
path. No model role or physical slot mapping is changed by this source candidate.
Deployment and physical qualification are **NOT_TESTED** here. After exact-source
root GO, use the existing ai-harness service and unchanged unit: bounded startup100
then fresh cool40; one normal stop/restart100 then fresh cool40; independent pinned
configuration/tach readback and unrelated-zone comparison. No thermal stress or
actual70 C/>80 C heat claim follows from synthetic threshold tests.
See [H040 source report](../reports/h040-fan100-source.md).

## Retained external-fan state — 28 September

H025 deployed the GPU-driven CHA_FAN3 controller on ai-harness. It commands
80% at server Blackwell temperature >=70 C, returns to 40% after <=65 C for
30 continuous seconds, and holds its previous state between those thresholds.
The CPU-temperature source remains disabled. Missing or stale GPU telemetry
requests the high setting and exposes a degraded state; the separate 85 C
workload stop remains in place. Readback and physical actuator checks, normal
stop/restart, and the target-only configuration migration passed. See
[H025 fan qualification](../reports/h025-fan04-20260928/README.md).

**CHA_FAN1 belongs exclusively to the BMC/user.** It cools both motherboard
Blackwells using the PCIe2/PCIe5 slot temperatures. Sova never writes that
channel. Its changes are recorded for audit without stopping CHA_FAN3 or
restoring old values. CHA_FAN3 target identity, sources, curve and expected duty
remain guarded against conflicting changes.

The two motherboard Blackwells retain their existing NVIDIA fan controller:
100% at >=70 C, then normal firmware control after <=65 C for 30 continuous
seconds. The server Blackwell is excluded from this integrated-fan controller.
The H025 concurrent-load result is recorded separately from idle actuator and
synthetic threshold qualification.

### Earlier September 28 observations

The user replaced the server Blackwell's external fan. A bounded ordinary-load
check at the user-set 75% duty reached 79 C; the separate four-way test has
incomplete monitoring and does not establish full PSU/thermal qualification.
See [H023 results](../reports/h023-thermal-20260928/README.md).

The user subsequently observed repeated changes between about 2500 and 5000
RPM. No deployed Sova script was found writing this BMC channel; the NVML fan
boost service explicitly excludes the server GPU. Host-side writer inspection
was unavailable. On September 28 the user disabled CPU temperature as CHA_FAN3's
source and physically confirmed that revving stopped. Readback confirmed the
Zone4 CPU source bit changed from 1 to 0, with the curve unchanged. Preserve
this working setting; do not restore the CPU-temperature source automatically.

At that earlier checkpoint the GPU-driven external fan policy was not deployed;
H025 above supersedes that limitation. A flat BMC CPU-temperature curve alone
does not follow the GPU temperature.

## Historical deployment and BMC access — 27 September

**08:36 update:** the user changed sova to Administrator. The unchanged probe
then passed login, all four fan GETs and owned logout (six HTTP200 responses).
CHA_FAN3 is exactly `Zone4(CHA_FAN3)`, array index3, PWMNum3, PWMSrc0; the saved
five points are20/45/65/90/100 C, all100% duty. Actual fan writes remain untested.
The same route failed its reads under Operator, so do not assume a role
downgrade will preserve future control. The intended dedicated host-side
controller needs a credential authorized for recurring changes, with no model
or task-container access to that credential. A permanent browser login is not
needed. [Administrator readback](../reports/h015-bmc-admin-20260927/HANDOFF.md).

Integrated NVML fan boost is deployed and live-tested, including restart after
the guest reboot. It commands 100% at 70 C and restores firmware control after
65 C or below for 30 seconds. The ECC-off overlap still reached the server
Blackwell's 85 C guard; no further stress repeat is planned before cooling is
improved. External fans remain user-set 100%.

The following paragraph records the earlier access failure, now superseded by
the successful Administrator comparison above.

BMC web authentication now succeeds with the saved sova credential. Four fan
GETs return HTTP500 under the Operator account, while the user confirms the
administrator can open Fan Control. A user-side role elevation is the next
controlled comparison; it has not been performed. The admin screenshot shows
Zone4(CHA_FAN3), flat100% duty and CPU Package Temperature as the curve input.
The requested GPU-temperature policy still requires a telemetry bridge and
qualified channel-only control/failure behavior. No fan writes were made.
[Current access evidence](../reports/h015-bmc-login-20260927/REPORT.md).

## Design and historical qualification steps

User steering, 27 September 2026: command GPU fans to 100% at 70C or above.
The passive Server Blackwell uses external fans connected to CHA_FAN3 on the
ASUS Pro WS WRX90E-SAGE SE. This is an amendment to the H013 comparison, not
evidence that a fan policy has already been activated.

## Integrated fans

Use NVIDIA NVML's supported per-fan controls, addressed by GPU UUID. Read actual
fan count and capability; a library symbol alone does not prove that this GPU
accepts the setter. Setting a target makes fan control manual. Never set a low
manual duty: boost all supported fans to 100% at >=70C, retain boost through
temperature oscillation, and return to firmware control only after <=65C for
30 continuous seconds. Unknown or stale temperature must not lower cooling.
Isolate missing/unsupported cards and report them explicitly.

The candidate needs a bounded sampling loop, restart/failure handling and
honest intended-duty versus actual RPM reporting. Preserve the independent 85C
workload cutoff. A live bounded command/readback check, source review and
focused error-path tests precede activation after the current 1M request ends.
No X server, Coolbits, driver change or power/clock tuning is needed for the
NVML approach if these cards support it.
[NVIDIA NVML fan commands](https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceCommands.html).

## External Server Blackwell fans

The GPU cannot operate a motherboard fan header through NVML. Guest PCI GPU
passthrough does not imply that motherboard fan-control hardware is exposed.
Check guest capabilities read-only, then use either the board's BMC or a small
Proxmox-side adapter for a verified supported controller.

ASUS documents fan control through IPMI; BIOS Q-Fan and Windows Fan Xpert have
a BMC-switch qualification. Do not change BMC mode, load probing modules, guess
IPMI raw commands or assume CHA_FAN3 equals Linux pwm3. Actual controller,
channel mapping and firmware ownership must be verified first.
[ASUS motherboard documentation](https://www.asus.com/ca-en/motherboards-components/motherboards/workstation/pro-ws-wrx90e-sage-se/).

If a host bridge is needed, it should accept authenticated temperature/health
reports for the allowlisted Server GPU, compute its own restricted fan policy,
and control only the verified CHA_FAN3 channel. It must default to full speed
when GPU telemetry is stale or ai-vm stops. A generic remote-command listener
is unnecessary. Do not start a host listener until access and the actual control
interface are known. The user has been asked for BMC network availability or an
existing Proxmox SSH alias; no passwords are requested in chat.

### Verified read-only discovery

At 04:20 UTC the user-provided BMC address `10.156.100.40` returned HTTP200
for `/` and `/redfish/v1`. It identifies an AMI MegaRAC Redfish service,
Redfish1.11.0, with Chassis, Managers and TelemetryService links. OEM RTP13.03
is an advertised component version, not a verified firmware release. No login,
linked-resource reads or setters were attempted. CHA_FAN3's writable interface
and Operator permissions remain unknown. The certificate is expired and lacks
the LAN IP in its names; authenticated access needs an appropriate trust setup.
The user was asked to create a dedicated `sova` account, initially Operator if
available, and store its credential privately on ai-harness outside Git and
task containers. No credential has been received or printed.

Guest NVML getters confirmed two integrated fans on each fast Blackwell and
one on Ada, with RPM and automatic-policy readback and reported range30–100%.
The Server Blackwell reports zero integrated fans. Guest hwmon/IPMI devices are
absent. These getter observations do not prove that fan setters work.

The reviewed [NVML candidate and limitations](../reports/h013-fan-source-20260927/README.md)
passed22 focused mocked checks. Root review added late-child recovery and
bounded idle logging. Live100% setter/default-restoration and real systemd
validation remain pending after1M settlement. A separate fan-only lock avoids
blocking thermal control on the inference lifecycle lease. Its tiny protected
system ownership record is control metadata; model data and bulk telemetry
remain under the existing registered storage policy.

## Evidence and comparison

The existing 1M run remains unchanged. Worker1 inspects live read-only support;
Worker2 prepares the separate offline NVML service and tests. Neither capability
inspection nor mocked tests prove physical fan behavior. Live verification and
any missing external control must be reported separately.

The next concurrency test changes ECC and cooling policy. It can establish
whether the combined configuration completes the workload under the same
guards; it cannot determine the isolated thermal effect of ECC.
