# H011 — Four-model load and manual 1M Flash preparation

Started 2026-09-27 00:55 UTC. Root coordinates/reviews; two workers use fresh
bounded Codex CLI sessions and isolated copies of root commit 5328a77. Aim to
finish active preparation within 90 minutes. The user subsequently authorized
starting the durable 1M job after the concurrency test, then ending the turn
while it runs. They will return after about one hour to check progress.

## Worker1: one owner for all four inference clients

Use one task driver on ai-vm to coordinate all requests and telemetry. Do not
repeat H010's separate-worker wall-clock launch mechanism. Worker2 pauses the
harness after verifying no user work; models remain resident and unchanged.

Exercise Flash + both Qwens + Ada image concurrently for roughly five minutes
of actual model load. Use existing real inference fixtures/clients: Flash 64K
input with bounded output, repeated fresh Qwen inputs (prefer 256K and bounded
output to load prefills), and repeated qualified Full HD generation. Keep
existing model/context/cache/runtime/placement/power settings. Bound total work,
individual requests and image count; no synthetic hardware torture or changes
to GPU power limits. Main target is overlapping active computation, not merely
HTTP intervals or four ready processes. Retain phase and utilization evidence.

Run the owner only after all clients are prepared. Use one shared start barrier,
then bounded loops or staggered starts within the owner to maintain overlap.
Allow at most one explicitly justified workload correction if an initial request
ends too early; never replay uncertain work. Stop new submissions at deadline;
let owned work settle under bounded limits before normal restoration.

Sample each GPU's power/utilization/memory/temperature/throttle/error state and
CPU/host memory about once per second; calculate the peak sum from the SAME
sample, not the sum of unrelated maxima. Preserve pre/post NVIDIA Xid/PCIe/OOM
and boot/service identity evidence. Use existing safety/thermal/storage guards.
If host/BMC/CPU-package power is not exposed, report unavailable. Do not claim
GPU telemetry proves wall power, PSU input/output or transient capability.
The user confirms the three Blackwells use the workstation 2200W PSU; Ada uses
the separate Core X PSU. Report their loads separately. No Proxmox operations or driver/ECC changes.

### Fan-adjusted repeat authorized during execution

The initial attempt stopped because the recorder assumed Ada supported Docker
logs. Its corrected attempt stopped at the Server Blackwell's85C temperature
cutoff (one later86C sample), before sustained qualification. The user then
increased that card's fan speed and confirmed readiness for another attempt.
This explicitly authorizes one fan-adjusted repeat with unchanged temperature,
memory and power settings. Preserve all attempts and label fan speed as a
user-reported change; no RPM measurement is implied. A further failure does not
authorize a tuning sweep or forced1M launch.

## Worker2: independent review and manual 1M preparation

Pause/restore the application using existing correct health/status parsers and
preserve user data. No inference competing with Worker1.

Inspect exact runtime/profile/wrapper context constraints and prepare a guarded
manual command/script for the user to run later. A 1M API payload cannot pass the
current 480K profile. The runner must safely configure the declared 1,048,576
capacity, verify allocation with a short request, then submit a fresh exact
1,000,000-token input with a 1,024-token answer budget and template reserve, preserving 7% GPU/15% host
reserves and recording timing/correctness/memory. Account for the 650 GiB cgroup.

Prefer a supported isolated maintenance profile using existing pinned weights
and runtime; no new engine/model, global sed, bypassed storage/auth/lifecycle
checks, or production-default increase. Snapshot exact prior state, prevent
harness use of the experimental lane, and retain the verified 1M candidate on success. Restore the qualified 480K
service through its owner on failure/timeout only. Protect against uncertain in-flight work,
SSH disconnect and duplicate submission. Preserve the other three models.
The preparation session remains source/offline only. After root review and
staging, a fresh bounded Worker1 native session with direct updated authority
will allocate the temporary profile, verify a short probe, and start the
1,000,000-token request. It exits once independent job ownership and actual
running progress are confirmed; no paid worker session needs to wait for inference.
Explain live-unverified boundaries rather than claim acceptance before results.

Derive a rough duration from 64K measured TTFT (246.468s), clearly separating a
linear planning reference (~63min for 1,000,000 input tokens) from unknown
nonlinear attention/workspace effects. Use a two-hour main-request limit plus bounded setup/restoration, no
automatic retries, durable logs/result JSON and a short status command.

## Finish

Review actual concurrent load/stability, not just request admission. Preserve
all four model services and publish compact evidence/code/commands in the
existing GitHub branch/PR, with PSU measurement limits. Keep Sova paused for
the long job. The user further directs that a successful 1M instance stays loaded. On
verified success retain it with explicit ownership for production promotion;
on failure/timeout restore the original 480K Flash backend. Result review,
promotion of a successful 1M profile into Sova, and app restoration follow when
the user returns. That promotion is already authorized. Never claim the 1M test passed merely because it started.
