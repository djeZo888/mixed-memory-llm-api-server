# H005 protected hardware owner integration — source candidate

The canonical text Manager and dedicated image Runtime enforce the same protected
boot latch before current model start. Text boot replay, manual start/restart,
image systemd start and explicit API recovery all reach those existing owners.
Restart preflight checks the latch before stop. The existing canonical lifecycle
lease serializes every latch producer/write and all owner mutations. No new lock
or model lifecycle engine is introduced. Existing source acceptance, registered
storage guards, target UUID resource admission and peer reservation remain intact.

State is fixed at the protected registered `services` root plus
`llm-manager/hardware-latch.json`, schema 1. The reviewed activation transaction
must install its initial `{"schema_version":1,"targets":{}}` **once**, before
switching owner source, after proving no earlier state exists in any retained
owner release. This is an activation prerequisite, not installer work. Runtime
code never creates empty state on missing/corrupt/read-failed persistence. Each
write repeats the registered root-payload guard before/after and uses the
registered mounted guard and AnchoredRoot, under the borrowed
canonical lease. App restart/manual GPU reset offers no clear operation.

Two distinct complete, successful, fresh inventories sampled after 120 seconds
of the current boot prove required UUID absence; a successful empty inventory is
valid evidence. Duplicates, malformed output, timeout and NVML initialization
failure are unknown. A trusted typed `gpu_fallen_off_bus` or
`gpu_unrecoverable_hardware_fault` map latches immediately, including boot grace.
Generic probe errors and ECC counters are never converted into those codes.
The current collector does not invent typed hardware faults from stderr.

An inherited boot-A latch remains protective during boot B until that exact
required UUID validates on B. While inherited, pending B absence observations
persist separately; two valid B observations promote the latch to B, so later
B presence cannot clear it. `hardware_latched_boot_id` retains the actual latched
boot and is never stamped from a later telemetry sample.

Starts first check the durable latch, then probe only each declared exact UUID.
Successful exact UUID proof with unchanged boot can clear an inherited latch;
there is no global inventory prerequisite for a healthy target. On target probe
failure the owner may collect one complete inventory and persist absence proof.
Independent periodic observation may call `HardwarePolicy.observe_inventory`
under a nonblocking existing canonical lease; GET handlers only read its result.
Unknown inventory does not kill in-flight work. A shared NVIDIA driver failure
can still prevent exact target probes; no per-GPU driver isolation is claimed.

Image residency now queries compute processes only on the dedicated Ada UUID.
It verifies concrete container labels/image/invocation, exact single DeviceRequest,
CUDA/NVIDIA UUID environment, no privileged/device/cgroup bypass, no host special
filesystem mounts, protected bridge/port policy, Docker PID membership and all
observed Ada GPU processes belonging to that container. Missing or failed peer
and unassigned GPU queries are not prerequisites. This is source-level ownership
proof; the strengthened inspect schema still needs exact installed/live review.

`read_latch_status(binding, gpu_uuids, current_boot_id=...)` is read-only. True
requires durable positive evidence and preserves the actual latch boot. False
requires fresh (at most 15 seconds old), current-boot, exact required-UUID healthy
proof for every required GPU. Empty/missing proof, wrong boot, future/stale proof
and unavailable state return null. Complete inventory presence alone does not
publish false. The additive protected `validated` map retains exact probe boot,
timestamp and observation ID; it is never an HTTP-readiness proof. Consumers add
its internal validation age to cache age so caching cannot renew freshness.
Its `identity` excludes timestamps and pending sample counts; it is suitable for
node target generation without metric poll churn.
The independent node process is not required to start healthy existing inference.

All fixtures are offline. Protected worker-file tests exercise the real mounted
writer and canonical lease with synthetic mount discovery; they do not establish
live hardware, mounted-device fault, systemd, or deployed readiness acceptance.
Changed critical owner bytes invalidate prior exact source receipts. Root must
review the new critical source manifest and bind the parallel runtime overlay
provenance before activation; historical acceptance is preserved unchanged.

Existing SGLang lifecycle/control observations now use the frozen authenticated
`/v1/readiness` contract for missing-key denial, wrong-key denial and strict Up
with exact model alias. All three requests share one bounded header/body budget.
No health or generation fallback is used. Unsupported old runtime returns
not_ready until the separately reviewed runtime overlay is activated. Generic
GLM probe semantics are unchanged. Loopback fixtures exercise this owner path and
existing warmup state transitions; they do not prove the native route is deployed.
