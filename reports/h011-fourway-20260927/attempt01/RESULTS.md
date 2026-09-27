# H011 four-model load — NOT QUALIFIED

Worker1 native session `01a0e05f-fc9a-7823-9166-be7657008b7e`, exact base
`5328a771596db54bee8b28e5f33b99892b3f5b7e`. No push, deployment, model reload,
profile change or1M allocation/inference. Ada is on the user-confirmed separate
Core X PSU. The workstation has the three Blackwells.

## Outcome and ownership

The requested approximately five-minute four-model compute overlap was **not
completed**. One VM-owned driver submitted all four requests after the actual
Worker2 quiet receipt/root handback. Its native-log monitor failed at
01:07:14UTC because Ada's existing Docker logging driver is `none`, so
`docker logs` returns1. This is a task-recorder defect, not a PSU/model failure.
The driver closed all four clients, stopped submissions and exited. Socket
closure did not settle native Flash work. At01:13:45.699UTC its scheduler
reported the existing300s watchdog timeout; SIGQUIT followed at01:13:50.700.
The original container exited at01:13:56.927UTC (ExitCode0, OOMKilled=false).
Worker1 performed no service halt/reload. All raw partial records are retained.

Root authorized one corrected pass after actual settlement, with fresh IDs,
capability-probed logging and twelve Qwen fixtures/lane. It has NOT been
dispatched. Root subsequently bounded natural-settlement observation to
01:17UTC, directing a fresh native session with direct updated authority if
Flash remained uncertain. This session does not recycle Flash. No safe app
restoration handback is claimed while that native ownership remains uncertain.
Flash is now terminal by container exit, not successfully settled/ready.
Final read at01:15:41UTC found port30010 refused; both Qwens and Ada were ready
in their unchanged containers. The exact cause of the scheduler stall is not
established. A fresh directly authorized native session must recover Flash.
See FINAL-HANDBACK.json for the latest observation and ownership.

## Submitted requests and overlap

| Lane | Submitted | Actual prepared input | Output cap | Client interval UTC | Result |
|---|---:|---:|---:|---|---|
| Flash | 1 |65536 native/rendered|768|01:07:09.375–01:07:14.257|Canceled before any delta/usage|
| Qwen0 |1|262144 native/rendered|128|01:07:09.628–01:07:14.256|Client canceled before headers|
| Qwen1 |1|262144 native/rendered|128|01:07:09.957–01:07:14.257|Client canceled before headers|
| Ada image |1|1920x1080 opaque requested|1 image|01:07:10.482–01:07:14.257|Client canceled; native later idle|

Four-client interval intersection is about3.774s. The1s left-sample estimator
reports4.003s; these are deliberately distinct. Eight sampled intervals
(~8.003s) had both Qwens/Ada at least50% GPU utilization and Flash at least16
busy CPU-core equivalents, including work after client closure. This does not
prove Flash was advancing inference or simultaneous GPU kernels. No Flash
prefill/decode phase completed in the captured initial native log windows.
Ada native phase logs are unavailable. No successful image output or native
completion token counts were received, so no image/hash or reasoning-quality
acceptance is claimed. Prepared token counts are not completed-request usage.

## Power and resource samples

Thirty driver samples cover roughly30s, including post-cancellation activity.
The same-sample **three-Blackwell peak was1290.35W**, at
`2026-09-27T01:07:14.184847+00:00`. Ada was separately294.20W in that sample;
all-four diagnostic sum1584.55W. Individual peaks below are NOT summed.

| Card | Independent sampled peak W | W at three-card peak | Peak C | Minimum free MiB |
|---|---:|---:|---:|---:|
| Flash Blackwell |94.96|87.96|38|65718|
| Qwen0 Blackwell |600.88|599.55|60|35610|
| Qwen1 Server Blackwell |602.84|602.84|64|35613|
| Ada, external PSU |298.24|294.20|63|15080|

The initial sample window met GPU/host reserves; minimum host available RAM
was565.382GiB. All four cgroups had zero owned swap and no new OOM/limit events.
Host swap-in increased10pages, swap-out0; this small burst did not meet the
sustained-pressure stop criterion. Qwen0 and Ada showed normal software
power-cap activity; no sampled thermal slowdown, hardware slowdown or power
brake. Later settlement observations are retained separately, not folded into
this failed short case. Flash retained CPU activity after cancellation while
GPU utilization was only1–2%; readiness200 was insufficient to establish idle.

Installed NVIDIA help defines `power.draw` here as a1s average and advertises
+/-5W/card. Sampling was about1s with small sequential per-device read skew;
brief peaks/transients can be missed. `power.draw.average` and
`power.draw.instant` were also captured where supported. CPU package power is
UNAVAILABLE: guest powercap/hwmon empty, no exposed BMC device; no host discovery
or packages. These samples establish neither wall power, actual2200W PSU
output/headroom, nor transient capability. No CPU-TDP inference is made.

## Source preparation and validation

Initial native fixture/API validation passed. The corrected, unsubmitted set
contains one fresh65536-token Flash fixture and24 fresh262144-token Qwen
fixtures; Qwen native token-ID hashes match rendered hashes. Offline exact-fit,
reserve/thermal/power-brake/owned/sustained-swap assertions pass. Ten inherited
H010 stream tests pass; those tests cover the reused capture contract, not full
live acceptance of the new multi-lane implementation. Source compiles; corrected
multi-lane/live behavior remains untested.

All21 installed source hashes and four installed guard hashes matched the
current H010/H009 evidence before work. Initial boot and all four container
identities matched. Three Blackwells ECC enabled and Ada disabled; pinned
480000 profiles, CPU64/eight-pool configuration and power limits were not changed.
Final per-service evidence distinguishes the three ready services from stopped
Flash. Kernel logs since dispatch show the watchdog py-spy attachment, with no
NVIDIA Xid, OOM, or PCIe failure lines. The PCIe replay query field was unsupported.
No claim of all-four final readiness is made.

Manual1M runner: **NOT_STAGED**. Root moved any future1M execution/recovery to a
fresh directly authorized native session. No candidate was staged or executed
in this session. Sova remains under Worker2/root ownership; this report does not
claim it is running.
