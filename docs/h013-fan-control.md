# GPU fan boost and motherboard fan control

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

## Evidence and comparison

The existing 1M run remains unchanged. Worker1 inspects live read-only support;
Worker2 prepares the separate offline NVML service and tests. Neither capability
inspection nor mocked tests prove physical fan behavior. Live verification and
any missing external control must be reported separately.

The next concurrency test changes ECC and cooling policy. It can establish
whether the combined configuration completes the workload under the same
guards; it cannot determine the isolated thermal effect of ECC.
