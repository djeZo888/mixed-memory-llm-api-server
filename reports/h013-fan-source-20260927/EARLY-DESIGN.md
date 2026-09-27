# H013 fan candidate — early design risks (2026-09-27 04:11 UTC)

OFFLINE source only; no device/VM/host contact or activation. Native task
01a0e10c-227c-7162-95e9-53ec50ea7dd6; base f71af8b85cbf31caa0b6930d4e484321623e6dad.

* NVML manual set requires nvmlDeviceSetFanSpeed_v2(device, fan, speed);
  release requires nvmlDeviceSetDefaultFanSpeed_v2(device, fan). Fan count
  must come from NVML. Symbols do not prove support on any installed GPU.
* Record owned/manual intent durably BEFORE setters; retain it on errors,
  abrupt exit and restart. Unknown/stale temperature never authorizes default.
  Releasing multiple fans is non-atomic: partial failure must reboost all.
* Calls can hang inside the driver. Use bounded isolated device jobs, keep
  other GPUs independent, kill timed-out children and refuse overlapping jobs
  if a child cannot be reaped. A timeout cannot guarantee an in-flight kernel
  call was cancelled or physical fan RPM. Watchdog/ExecStopPost are best effort.
* Read target and policy back; intended percent is not measured RPM/airflow.
  Stop/failsafe paths only boost or retain control, never restore default.
* Server UUID has external motherboard fans: external-control-needed, never
  NVML fan-control success. ASUS BMC/IPMI support does not establish CHA_FAN3
  write interface or Linux hwmon mapping. No host agent until vendor mapping,
  competing ownership and effects on other host devices are verified.
* Updated root authority: dedicated fan-controller process/lock exclusively for
  allowlisted NVML fan control and protected fan state; no model lifecycle lease.
  Refuse unowned manual policy and report controller conflict. A cooperative lock
  cannot exclude unrelated root tools; activation requires exclusive ownership.
* New fan policy confounds ECC causal comparison. Keep 85C load-test cutoff;
  do not touch the running 1M request, its deadline or scientific evidence.
