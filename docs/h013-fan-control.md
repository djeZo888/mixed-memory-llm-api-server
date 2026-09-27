# GPU fan boost and motherboard fan control

## Current deployment and BMC access — 27 September, 08:24 UTC

Integrated NVML fan boost is deployed and live-tested, including restart after
the guest reboot. It commands 100% at 70 C and restores firmware control after
65 C or below for 30 seconds. The ECC-off overlap still reached the server
Blackwell's 85 C guard; no further stress repeat is planned before cooling is
improved. External fans remain user-set 100%.

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
