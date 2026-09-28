# H025 CHA_FAN3 candidate and interface

Candidate only until root/W2 exact-source review and live idle actuator test.
Integrated ai-vm NVML controller is reused unchanged: deployed/source SHA256
`47adea43b4c404ab325b2470ca0a701ab825dfd079f2c6e6f6edf258f8c6bfb3`,
enabled/running PID1634 at18:54UTC, fixed integrated UUID allowlist and external
UUID excluded. 70C boost100%, <=65C30seconds restores firmware. No rebuild.

External UUID `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528` uses only
`Zone4(CHA_FAN3)`/index3/PWMNum3/PWMSrc0. Target first four curve duties40/80;
20/45/65/90/100C knots and last100C100% point are unchanged. Mode4, CPU/user
source bits0 and full PWM4 source mask0 are mandatory. No source/mode writes.
Live18:58:48 read-only inventory: duty75, raw tach4920, units absent,
GPU34C, node boot17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125. Other zones captured.

## Fixed transport and failure policy

BMC10.156.100.40:443 leaf DER SHA256
`0f1ee547edbdbca346ea2d884d3271a8f28351d57a16baa911c388198063f7ec`
is checked on every socket before auth. Existing proven session/CSRF API, one
login reused across polls, at most one renewal after401/403 and >=60seconds
between login attempts; owned logout. Requests bounded3seconds/socket2seconds,
262144-byte response cap; exact routes/payloads. Historical helper/modules are
reference only and never imported/executed by this service.

Node uses authenticated non-browser HTTP to10.156.100.60:30008, GET only
`/control/v1/node/status`: genuinely cached DTO, no lifecycle lease. Checks
schema/node/boot/inventory/unique UUID, envelope freshness and timestamp/age
<=15seconds, finite absolute `temperature_c`. Full DTO is never logged.

Poll5seconds; >=70C commands80; <=65C for30continuous seconds permits40;
65–70 holds prior. Missing/stale telemetry raises/retains >=80 and resets cooldown.
Startup/stop/failure/restart verifies >=80, preserving higher existing setting
until fresh cooldown. It never restores75 or CPU source. Independent85C workload
cutoff and existing83/85 safeguards remain W2/owner responsibilities.

Writes occur only when command differs from actual curve readback. The held/named
controller lock and stop flag are checked immediately at the PUT send boundary;
a stop during sampling cancels any lowering command. Local durable-state and
credential errors are not classified as recoverable network outages. Complete
readback validates other-zone/mode/source/knots invariant before/after writes.
Overwrite/mismatch durably latches `blocked.json` (file and parent-directory
fsync) BEFORE one safe-high attempt; source
or invariant drift cannot pass the safe-high precondition. Subsequent starts
and ExecStopPost refuse further writes while blocked. Exit78 prevents restart
fighting. A failed write/readback is unavailable, never a physical fan claim.
Transient BMC read/login/tach transport failure publishes degraded/unknown
readback and retries with10/20/30second capped backoff, resetting cool dwell.
Watchdog heartbeats during backoff indicate process liveness, not fan health.
An ambiguous fixed-channel PUT is recorded in pending-write.json and a separate
uncertain-write.json. Recovery READS full invariants and actual duty first; only
exact intended or exact before-write state reconciles it. No blind PUT replay.
After reconciliation high is requested from fresh readback before another cool
dwell. Confirmed conflicting readback/scope remains a durable hard block.
Ordinary crash uses ExecStopPost high; watchdog30seconds catches stalled loops;
automatic crash restart is bounded3/300seconds with30second spacing. Clearing a
blocker requires an owner investigation; do not remove latch automatically.

## Status contract for W2

Atomic `/var/lib/sova-cha-fan3/status.json`, directory0700/file0600, service user
`user`; host-only read using existing SSH. No new network API, credentials,
canonical lock, task-container access, or model dependency. A separate flock
`controller.lock` permits exactly one cooperative writer. Current status is
bounded64KiB (normal <4KiB), no append history; system journal rate limited5/min.

Schema version1 fields (all present):

- Identity: `gpu_uuid`, `host_boot_id`, `pid`, `source_sha256`, `started_at`,
  `invariant_sha256`, `channel`, `mode`, `source_bits`.
- Freshness: `updated_at`, `node_boot_id`, `sampled_at`, `temperature_c`,
  `telemetry_age_seconds`.
- Control: `state`, `errors`, `desired_duty`, `readback_duty`, `readback_at`,
  `last_known_readback_duty`, `readback_kind`, `last_write_at`, `bmc_put_attempts`,
  `bmc_logins`.
- Tach: `actual_tach`, `actual_tach_units`, `tach_at`. Null units means UNKNOWN.

`readback_kind=first_four_curve_duties_not_measured_pwm` explicitly identifies
configuration readback, not measured PWM duty. Tach proves rotation and the idle
test must establish response to40/80 before qualification. `readback_duty=null`
means current unavailable, with older proof separately timestamped. Error path
can retain old tach with its old `tach_at`; never infer freshness from updated_at.

For load admission W2 must require state`healthy`, empty errors, exact reviewed
source/UUID, current boot/PID instance, mode4/source_bits[0,0,0], desired equal
readback40/80 (or retained higher100 with owner-reviewed proof), positive tach,
all timestamps and source age <=15seconds. Blocked/degraded/starting/stopped,
missing/stale status or bridge death must fail admission/settle through owner.
Readback/tach timestamps retain actual successful acquisition time; publication
and degraded-status refresh do not make older measurements fresh.
`healthy` is controller/readback health; the separate idle actuator PASS receipt
is also mandatory. Controller does not consume or depend on W2's task bridge.

## Deployment after exact-source GO

Only ai-harness; no app/model restart. Stage source privately and compare exact
reviewed SHA256 of cha_fan3.py and sova-cha-fan3.service before any install:

```
sudo install -d -m0755 /usr/local/lib/sova-cha-fan3
sudo install -o root -g root -m0644 REVIEWED/cha_fan3.py /usr/local/lib/sova-cha-fan3/cha_fan3.py
sudo install -o root -g root -m0644 REVIEWED/sova-cha-fan3.service /etc/systemd/system/sova-cha-fan3.service
sudo systemctl daemon-reload
sudo systemctl enable --now sova-cha-fan3.service
```

Root-owned system unit runs as user:user. systemd LoadCredential reads EXISTING
`/home/user/.config/sova-private/bmc.json` and
`/home/user/.config/ai-harness/node-control-key`; transient service-private copies
are `/run/credentials/sova-cha-fan3.service/{bmc.json,node-control-key}`. Original
credentials stay untouched. ProtectHome/ProtectSystem/PrivateDevices isolate
service access; only StateDirectory writable. No secret enters Git/evidence.

Systemd creates `/var/lib/sova-cha-fan3` and its controller.lock, baseline.json,
status.json, pending-write.json (last scoped write intent/result), uncertain-write.json
(only after uncertainty), and blocked.json (only on confirmed integrity fault). Baseline preserves first observed
settings apart from the four controlled duties/dynamic LastTemp fields.

Capture idle startup80, then30second fresh-cool transition40, with independent
readback/tach after settling. Check no external overwrite; stop/restart once
and verify high stop/start, then fresh-cool low. Allow no new inference. If no
clear tach response, stop and report ACTUATION_UNCERTAIN; no stress. No fan sweep.
Synthetic threshold tests are separate from actual actuator qualification; a
real GPU70C crossing is NOT_TESTED in W1 scope.

Rollback: `sudo systemctl disable --now sova-cha-fan3.service` invokes verified
high stop/ExecStopPost. Read status and independent pinned BMC inventory. Preserve
source/state/latch and credentials for evidence; do not restore75/CPU source or
remove files until verified high and owner settlement. If latched, stop makes
no repeated writes; report latest proof/actuator unavailability and do not load.

## Focused validation

Run `python3 test_cha_fan3.py` on ai-harness only: synthetic thresholds, cooldown,
stale/future/boot/UUID/schema rejection, protected source/channel payload,
unchanged zones, restart/no-low restoration, write-only-transitions, lock
collision, writer overwrite/latch/no-fight and honest readback/tach. No root-Mac
tests/builds, no thermal load, no driver/runtime/model/TDP/Proxmox change.
