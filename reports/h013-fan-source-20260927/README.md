# H013 fan safety source candidate

**PROPOSAL_READY_ONLY — no activation or fan-setter availability claim.**
Isolated offline Worker2 task on base `f71af8b85cbf31caa0b6930d4e484321623e6dad`;
branch `worker2/h013-fan-source`. No VM, Proxmox, harness, NVIDIA device/library,
BMC or live-host contact; no inference, package installation, push, historical
H011/H012 edits or runtime hash-controlled source edits.

## Candidate and ownership

* `scripts/thermal/fan_boost.py`: Python stdlib/ctypes, inert import, explicit
  `run`, `failsafe`, `capabilities`, `dry-run` modes. The last two only query;
  no state writes/lock creation/setters. `--help` is offline.
* `scripts/thermal/local-ai-fan-boost.service`: proposed root systemd service,
  watchdog and boost-only ExecStopPost. No unit installed or enabled.
* `scripts/thermal/fan-boost.example.json`: exact required four UUID identities;
  no aliases, duplicates, unknown fields, unknown devices or configurable unsafe
  thresholds. Server is inventory-only, never a setter target.
* `tests/test_h013_fan_boost.py`: focused mocked safety/regression tests.

Direct updated root authority grants one dedicated fan-controller process/lock,
solely for allowlisted NVML fan setters/default restoration and protected fan
state. No model lifecycle lease is acquired on samples, setters or failsafe.
No model/container/ECC/reset capabilities exist in this candidate.

Default config is `/etc/local-ai-server/fan-boost.json`; tiny ownership metadata
and `controller.lock` live in `/var/lib/local-ai-fan-boost` (0700, root). Config,
state and every ancestor must be root-owned with no group/other write or symlink;
state/lock files must be single-link regular 0600 files. State has fixed owner
identity and exactly the integrated UUIDs. Atomic replacement, file fsync and
directory fsync precede any new manual setter. Parent keeps flock; forked jobs
inherit it. Durable intent stays true through failed/unknown setters/restores.
Malformed/unprotected config or state fails closed with no setters; never remove
state as a recovery shortcut. Root must review deployment/storage/log retention
separately; this is control metadata, not model data or an installer change.

A competing cooperating controller is refused by nonblocking flock. Unowned
manual policy (or unreadable policy) is refused as controller conflict, without
adopting that controller's fans. Exclusive ownership must also be verified
operationally: an unrelated root tool can ignore flock and NVML has no atomic
compare-and-set ownership token. Same-setting external controllers cannot be
identified reliably. Do not activate over another fan controller. State with
owned intent grants only recovery of this controller's own prior intent, not a
newly discovered manual controller. No automatic ownership takeover/reset.

## Policy and error behavior

| Identity | Treatment |
| --- | --- |
| Qwen0 `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237` | Integrated fans, runtime enumeration |
| Flash `GPU-69acfa26-8b60-61b5-702d-aee252c163cc` | Integrated fans, runtime enumeration |
| Ada `GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23` | Integrated fans, runtime enumeration |
| Server `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528` | Always `external-control-needed`; no fan setters |

Fresh absolute GPU temperature >=70 C takes durable manual intent and requests
100% on **every** NVML-enumerated fan. Count/index is never inferred from model
name or the root receipt below. Manual success requires target=100 and manual
policy=1 on every fan, using official `nvmlDeviceSetFanSpeed_v2`. This verifies an
intended setting, not RPM, physical movement, airflow or a thermal outcome.

Stay boosted until valid <=65 C observations span at least 30 seconds with no
sample gap >6 seconds, error or invalid/stale observation. Poll pause is 2s;
read and mutation device jobs each have a 2s wall deadline. Continuous here means
a continuous sequence of bounded fresh samples, not knowledge between samples.
Restart discards cooldown history, reboosts durable owned intent first, then
qualifies a new full cooldown. Setter/readback failures reset cooldown; a later
fresh continuous cooldown can recover normally. Default release uses only
`nvmlDeviceSetDefaultFanSpeed_v2`, with another fresh <=65 C check immediately
before each fan and automatic-policy=0 readback. There is no low-duty setter.

Unknown/stale temperature or getter/setter/readback failure while owned retains
intent and attempts all enumerated fans at 100%, reporting degraded. Partial
restore failure reboosts every enumerated fan; release is not atomic. Failed or
missing/passive devices are reported separately and do not prevent other device
jobs. Cold, hot or stale clean stop and ExecStopPost/watchdog recovery NEVER
restore default; they reboost owned fans and may acquire a fresh hot unowned
automatic device. An unowned unknown-temperature device is not silently adopted.

Categorical status/action/error changes are logged immediately; otherwise a
summary is emitted at most every 60 seconds. Changing temperatures/timestamps
do not defeat deduplication. Sampling and watchdog timing remain unchanged.

A bounded supervisor runs one outstanding job per device in parallel. It kills
and briefly joins timed-out children. An unreaped child blocks new calls to that
device, while other devices continue. Each later batch nonblockingly reaps a
previously blocked child once it exits, closes it, then permits a fresh job;
a still-live child is never overlapped. The inherited controller flock deliberately
prevents overlapping restart/failsafe ownership while an old child survives;
this can block **global recovery until the kernel call settles**. Timeouts and
SIGKILL cannot guarantee cancellation of an in-flight driver operation, especially
a default restore, or any resulting mechanical fan state. Watchdog and StopPost
are best effort, including failure of systemd/OS/storage or lost hardware.
No source can promise protection through power loss, a hung kernel or competing
root tooling. Keep the independent 85 C load-test cutoff unchanged.

The unit's Type=notify/WatchdogSec and ExecStopPost behavior follows official
[systemd service documentation source](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml)
and [control-group kill documentation](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml).
A service being active/READY or issuing watchdog pings means the supervisor is
running, not that any GPU control/airflow has been qualified. JSON per-device
status is the evidence. No network listener/API is provided; systemd notify uses
only its local Unix socket.

## Separate root-supplied observation, not this task's acceptance

Root relayed a read-only NVML receipt at **2026-09-27 04:10:19 UTC**: Qwen0 and
Flash each enumerated two fans; Ada one; all policy=0 automatic, min/max 30–100%.
Server returned zero fans/unsupported getters. Guest hwmon/IPMI enumeration was
empty; this establishes no host/BMC absence. Flash reported intended 36% while
GetTargetFanSpeed was 30% in automatic policy. The candidate does not equate
automatic target and reported percentage. Root also relayed RPM getters:
Qwen0 1199/1200, Flash 1355/1354, Ada 999. These are external observations, not
this task's probes or accepted physical cooling measurements. No RPM feature was
added and no immediate physical maximum is required after a manual set.
**Setter/default restoration remains NOT_TESTED on every GPU.**

## Motherboard path and future gate

User-confirmed BMC network address: **10.156.100.40**. Prefer the motherboard's
network BMC route over assuming a guest hwmon/IPMI interface. Consider dedicated
`sova` with Operator privilege initially **only if supported** for the required
LAN/API reads/control; exact privileges remain unverified. Keep credentials in
protected files outside containers; never put passwords in chat, argv or logs.
Root/Worker1 separately owns any read-only BMC verification; none occurred here.

See [ASUS primary-source evidence](ASUS-EVIDENCE.md). Per-header CHA_FAN3 API,
connector-to-sensor/control identity, shared fan-zone effects, exclusive control,
privileges and watchdog/fail-full mapping are UNVERIFIED. Do not guess IPMI raw
registers, PWM channel 3, fan mappings or writes. No motherboard fan agent or
listener was implemented. A future small host agent consuming authenticated
fresh UUID-bound absolute GPU telemetry and forcing full on stale remains a
proposal until the vendor interface and impact on other host devices are
verified. A generic BMC feature or Linux driver listing is not that verification.

## Review and validation boundaries

Activation requires root review, separately authorized live support probes, and
settlement of the current 1M request. No current 1M request/deadline, historical
driver, workload or scientific result was altered. A changed fan policy means
any future ECC-off comparison **cannot isolate ECC causality**; disclose this
alongside other configuration/ambient changes. Keep 85 C load-test cutoff.

Read the [post-1M bounded validation procedure](VALIDATION-PROCEDURE.md),
[NVML signatures and primary URLs](NVML-EVIDENCE.md) and
[focused test evidence](TESTS.md). Hardware NOT_TESTED: actual setters and default
restore on all devices, per-fan readback after setters, physical RPM/airflow and
thermal effectiveness, installed-driver hangs/cancellation, power loss/reboot,
real systemd/watchdog recovery, deployment permissions and conflicts, BMC API,
CHA_FAN3 mapping/privilege/watchdog and motherboard fan effects on other devices.
