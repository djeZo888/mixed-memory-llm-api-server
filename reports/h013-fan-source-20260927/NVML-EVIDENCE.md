# NVML fan API evidence — 2026-09-27

OFFLINE documentation review only. No NVIDIA device/library was probed and no setter was run. This report does not establish control availability on any installed GPU/driver.

## Exact C interfaces

NVIDIA's [Device Commands reference](https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceCommands.html) specifies:

```c
nvmlReturn_t nvmlDeviceSetFanSpeed_v2(nvmlDevice_t device,
                                    unsigned int fan, unsigned int speed);
nvmlReturn_t nvmlDeviceSetDefaultFanSpeed_v2(nvmlDevice_t device,
                                           unsigned int fan);
```

The manual setter accepts 0–100 percent and switches control to manual. NVIDIA identifies Maxwell-or-newer CUDA-capable discrete products with fans as its scope. The default setter restores the default control policy; do not synthesize a low duty or select a policy with another setter. Invalid fan indices, unsupported devices and unexpected errors remain possible. A successful call acknowledges software control, not mechanical airflow. The manual-control warning places temperature monitoring responsibility on the caller. Therefore durable owned intent must precede the first setter, including a setter whose eventual result is unknown.

NVIDIA's [Device Queries reference](https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html) specifies:

```c
nvmlReturn_t nvmlDeviceGetNumFans(nvmlDevice_t device, unsigned int *numFans);
nvmlReturn_t nvmlDeviceGetFanSpeed_v2(nvmlDevice_t device,
                                    unsigned int fan, unsigned int *speed);
nvmlReturn_t nvmlDeviceGetTargetFanSpeed(nvmlDevice_t device,
                                       unsigned int fan, unsigned int *targetSpeed);
nvmlReturn_t nvmlDeviceGetFanControlPolicy_v2(nvmlDevice_t device,
                                            unsigned int fan,
                                            nvmlFanControlPolicy_t *policy);
nvmlReturn_t nvmlDeviceGetTemperature(nvmlDevice_t device,
                                    nvmlTemperatureSensors_t sensorType,
                                    unsigned int *temp);
```

Fan indices are zero-based; enumerate the count and attempt every returned fan. Dedicated fans are required. `GetTargetFanSpeed` reports the requested target; `GetFanSpeed_v2` reports intended operating percentage, which may exceed 100. Neither proves that an obstructed fan is spinning. The current query documentation has an inconsistent unsupported-device statement concerning newer-than-Maxwell hardware; treat each actual API result as authoritative for that operation. `GetTemperature` returns Celsius but is now deprecated in favor of `GetTemperatureV`; retaining the established simple ABI is a candidate compatibility choice, not proof of installed support.

The official [NVIDIA header](https://github.com/NVIDIA/go-nvml/blob/main/gen/nvml/nvml.h) supplies these ABI declarations; `nvmlDevice_t` is an opaque device pointer, returns are `nvmlReturn_t`, fan/count/speed/temperature arguments above are unsigned integers. Bind all ctypes argument and return types explicitly. The [NVML enum reference](https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceEnums.html) identifies manual and temperature-controlled policies. The official [NVML PDF](https://docs.nvidia.com/deploy/pdf/NVML_API_Reference_Guide.pdf) assigns `NVML_FAN_POLICY_MANUAL=1` and `NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW=0`. The GPU die sensor is `NVML_TEMPERATURE_GPU=0` ([NVIDIA sensor enum documentation](https://docs.nvidia.com/deploy/archive/R535/nvml-api/group__nvmlDeviceEnumvs.html)).

## Temperature and qualification boundaries

NVIDIA's [nvidia-smi temperature reference](https://docs.nvidia.com/deploy/nvidia-smi/#temperature) defines T.Limit as the remaining margin to maximum operating temperature, not absolute GPU temperature. A signed T.Limit can count down through zero. Use fresh absolute GPU-die Celsius for the 70 C boost and 65 C cooldown. Keep the independent 85 C load-test cutoff unchanged.

Source-review recommendations (inferences from the APIs and task safety contract): read target percentage and control policy for every fan; any missing getter or unsuccessful readback keeps owned intent and degraded status. Confirm manual/100 after boosting and temperature policy after default restoration. Missing or passive devices must not abort protection of other allowlisted devices. Read-only capability discovery can prove symbols/getters only; it cannot prove setters or safe firmware restoration. A kernel/driver call can remain stuck despite userspace process termination; bounded subprocess supervision limits the caller's wait, not the hardware's response or a late command. Default restoration requires a separate fresh cool qualification, and uncertain/timed-out restore must never be reported successful.

NOT_TESTED: every actual GPU's fan count, setter support, target/policy readback, firmware-default restoration, physical RPM/airflow, process timeout behavior with the installed driver, restart/systemd/watchdog behavior on the deployment host. Server GPU external motherboard fans require a separately verified vendor path; NVML cannot establish their protection. A changed fan policy confounds a subsequent ECC-off comparison, so such a comparison cannot isolate ECC causality.

ABI clarification from the [official raw header](https://raw.githubusercontent.com/NVIDIA/go-nvml/main/gen/nvml/nvml.h): `nvmlFanControlPolicy_t` is specifically `typedef unsigned int nvmlFanControlPolicy_t;` (current header lines 1656–1659), so policy readback requires `ctypes.c_uint` and `POINTER(c_uint)`, despite the documentation grouping policy constants under enums.
