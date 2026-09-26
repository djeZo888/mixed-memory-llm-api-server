# H005 hardware latch semantics — owner source candidate

Frozen result:
- `hardware_latched:true`: durable positive target evidence, sticky for its exact
  `hardware_latched_boot_id`; unchanged by service restart/reset/late HTTP success.
- `hardware_latched:false`: every required exact GPU has independently validated
  hardware proof from current boot, fresh <=15000 ms. An empty latch record does
  NOT establish false. Whole inventory presence does NOT establish false.
- `hardware_latched:null`: proof missing, stale, future, wrong boot, or protected
  state unavailable. Unknown is no absence proof or permission to kill in-flight work.

Fixed protected state: registered services/llm-manager/hardware-latch.json.
Existing schema1 targets are accepted. Additive optional private `validated` map
contains UUID -> {boot_id, observed_at, observation_id}. Initial empty schema1
remains unknown until exact validation; no runtime missing-file initialization.
RegisteredLatchStore verifies registry, mounted writer and root-payload guards,
and borrows the same canonical lifecycle lease for all writes.

Trusted producer API:
```
HardwarePolicy(RegisteredLatchStore(binding, lease=lease), lease=lease).validate_required(
    gpu_uuid, current_boot_id=boot_id, observed_at=utc_probe_time,
    observation_id=distinct_bounded_receipt_id)
```
The producer must prove the exact required UUID and unchanged boot around its
hardware probe. HTTP readiness cannot supply this call. The method validates
current boot and freshness after protected state read, persists exact proof, and
clears only inherited-boot protection. Same-boot positive remains true. Root's
single hardware producer can consume each bounded GpuCollector last_proof;
it does not need new hardware queries or unlimited collector slots.

Read-only API:
```
read_latch_status(binding, gpu_uuids, current_boot_id=current_boot_id)
```
False includes internal-only `hardware_validation_age_ms` (number),
`hardware_validated_boot_id`, `hardware_validated_gpu_uuids`. Node projection must
add cached observation age to validation age before publishing false and must
verify current boot + exact required UUID set. No new public wire fields.
Positive includes original hardware_latched_boot_id. `identity` excludes ages,
timestamps and observation IDs so metric/proof refresh does not churn generation.

Absence remains two distinct successful COMPLETE fresh inventories sampled after
120-second boot grace. Successful EMPTY inventory is complete evidence. Timeout,
malformed/duplicate inventory and NVML init failure remain unknown. Explicit typed
hardware failure may latch immediately, including grace. Inherited A remains
protective during B pending evidence; two B absence proofs promote to B so later
B recovery cannot clear it. Exact required GPU validation can clear inherited A
on B even if peer/unassigned GPUs make global NVML inventory fail.

Source/offline proof only. Exact runtime/source activation binding and live
acceptance remain root-owned gates. No credentials, deployment or GPU action used.
