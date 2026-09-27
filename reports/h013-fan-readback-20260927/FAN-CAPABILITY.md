# H013 fan capability — read only

NVML observed 2026-09-27T04:10:19.539612+00:00 through 2026-09-27T04:10:19.616070+00:00; guest hardware 2026-09-27T04:10:49.201725+00:00. Source pinned `31522361aee0b2eb3fa0037c0820c9cc1708cecd`.

**Policy is NOT active. Setters NOT TESTED.** Desired future policy: fan 100% at GPU >=70 C, subject to root review after current 1M settles. No activation code was created.

| GPU | Exact UUID | C | Fans | Intended % | Target % | Min/max % | Policy | Measured RPM |
|---|---|---:|---:|---|---|---|---|---|
| Q0 | `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237` | 36 | 2 | 30/30 | 30/30 | 30/100 | 0/0 | 1199/1200 |
| Flash | `GPU-69acfa26-8b60-61b5-702d-aee252c163cc` | 61 | 2 | 36/36 | 30/30 | 30/100 | 0/0 | 1355/1354 |
| Q1Server | `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528` | 37 | 0 | rc=2 | rc=2 | rc=2 | rc=2 | rc=2 |
| Ada | `GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23` | 35 | 1 | 30 | 30 | 30/100 | 0 | 999 |

All UUID/name/temperature/fan-count calls returned **0 (NVML_SUCCESS)**. All integrated-fan getters returned 0. Server legacy fan-percent returned **3 (Not Supported)**; min/max and fan-0 current/target/policy/RPM checks returned **2 (Invalid Argument)**. Fan-0 calls on Server were read-only unsupported checks, not evidence of a physical NVML fan. RPM for CHA_FAN3 is unavailable.

Policy 0 is the installed binding's temperature-continuous software policy (automatic). Intended percent is not RPM. Flash's intended 36% and target getter 30% are preserved as distinct raw getters; no physical fan-ramping action or policy change is inferred.

NVML 13.595.84; driver 595.84; installed nvidia-ml-py 13.615.71. Binding source was read from the existing Flash container, copied exactly into transient guest Python memory, and used against `/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.595.84`. No installation or guest-file write. The RPM structure/version and call signature came from that binding, including per-fan index; no guessed ABI.

All queried getter symbols and `nvmlDeviceSetFanSpeed_v2`, `nvmlDeviceSetFanControlPolicy`, `nvmlDeviceSetDefaultFanSpeed_v2` exist. Setter symbols were only resolved, never called. Getter success makes NVML a plausible integrated-fan control route; permission, writable policy transitions and setter success remain untested.

Guest `/sys/class/hwmon` has no entries, so no names/labels/fan inputs/controller links can be reported. No `/dev/ipmi*` nodes or IPMI class devices. DMI identifies QEMU Standard PC (Q35 + ICH9, 2009), pc-q35-11.0; physical baseboard fields are absent. Existing sysfs records show the guest SMBus I801 adapter and NVIDIA I2C adapters; this does not expose or identify CHA_FAN3. No bus scan or module loading occurred.

The user identifies Server fans as physically connected to motherboard **CHA_FAN3**. That route is separate from NVML. Its host/BMC/controller path is **unknown / needs root review**, with no known authorized host access established and no host/BMC contact attempted. No hwmon-index-to-header inference was made.

H011 baseline remains immutable. Applying the proposed fan policy would add a cooling variable to the future ECC comparison; it would no longer support ECC-only causality.

Probe SHA256: `17bf2d3755939a8db1c4159ce642154e6cfc81cad42075389971a7708f7cc01b`. Binding SHA256: `2828e66b483bec218f461314f6da96c1e56330ed4b297a20b3444b4c43cdd14e`. Hardware probe SHA256: `47e591d5cfb177b626cbb088cce958cbcabf7e53848301a25e2f10d280d09bd8`.

Full timestamps, all per-device return codes, symbol results, source versions and evidence hashes: [FAN-CAPABILITY.json](FAN-CAPABILITY.json). Private scripts and readbacks retained in `private/`.
