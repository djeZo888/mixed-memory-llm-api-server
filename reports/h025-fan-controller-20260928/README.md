# H025 W1 fan controller handoff — blocked stop qualification

The external40/80 idle actuator check passed. The automatic service is **disabled**:
ExecStopPost cannot access its systemd credential, so stop/restart qualification
failed. It is not ready for workload admission. Final independent19:30:38UTC
readback: configured80, rawtach5160 (units absent), source000, mode4, GPU33C.

Native session01a0e95d-af31-7541-8199-b5e9ab2b19d6, September28 2026,
18:53:56UTC start, hard19:35UTC exit. Basea9fc29ffdaa5d0eb67f6b47917b5a1159e782ea5.
Final installed/reviewed implementationb63f352761538be9c94e294d3f9f4f1688f10585:

- Controller SHA256ff1e95d55dec1d08b70fb95703f545d9c72061c5a19b5afd29f04dc64773bdec.
- Unit SHA256cafdca77af862836445bfa9f6ff5b77b571e6421d68d2be65e700bfbf4f580ed.
- 58 focused synthetic fixtures PASS on ai-harness. No root-Mac tests/builds.
- Integrated ai-vm source/service/settings verified and reused unchanged;
  source SHA25647adea43b4c404ab325b2470ca0a701ab825dfd079f2c6e6f6edf258f8c6bfb3.
  Existing70C100% / <=65C30second firmware restoration and external exclusion remain.

## Actual idle evidence

Final revision ran65seconds with14 consecutive healthy captured rows atGPU33C.
It held80, then after fresh cool dwell commanded40 once. Independent readings:

| UTC | Configured curve duty | Raw CHA_FAN3 tach | Result |
| --- | --- | --- | --- |
| 19:29:20 | 80 | 5160 | Settled high |
| 19:30:15 | 40 | 3600 | Settled low; actual fan response |
| 19:30:38 | 80 | 5160 | Normal main-process stop raised high |

The API omits tach units. Curve configuration readback is not measured PWM duty.
Mode4, sourcebytes000/fullmask0, knots20/45/65/90/100C and last100C100% point,
and every other configured zone remained unchanged. No competing writer was
established. Total three BMC PUTs: initial75->80, final80->40, normal stop40->80.
No source-bit writes, sweeps, stress/inference, drivers/TDP/runtime/model changes.
Actual GPU70C crossing and four-model overlap were NOT_TESTED by W1.

## Preserved failures and current blocker

1. Initial19:18:02 startup rejected systemd's root:root0440 credential before any
   PUT. Root reviewed a fixed-path metadata exception; original failure archived.
2. At19:21:48, an invariant check blocked after the first80 command. The failing
   snapshot was not retained, so its exact cause remains unknown. A subsequent
   bounded read-only snapshot reproduced only unusedPWM8 LastSource0->2, with
   all configuration unchanged. Root reviewed exclusion of non-target LastSource
   observations and bounded future mismatch receipts; original baseline retained.
3. Normal stop19:30:16 commanded/proved80, but ExecStopPost19:30:17 failed
   protected_file_unavailable. A matching transient User=user/ProtectHome=yes/
   LoadCredential test reproduced readable root0440 file in ExecStart and
   **Permission denied in ExecStopPost**. No credential contents were printed.
   No restart or blind latch clear followed. Final service failed/disabled/PID0.

The next owner needs an exact reviewed stop-phase credential binding and fresh
stop/crash/restart qualification. Do not remove credential protection or claim
that the earlier healthy samples qualify the failed stop path. Original failures,
active blocker and latest independent high proof remain intact. Existing83/85
workload safeguards remain; server load must await root fan-readiness resolution.

## Installed files and access boundaries

- /usr/local/lib/sova-cha-fan3/cha_fan3.py, root:root0644.
- /etc/systemd/system/sova-cha-fan3.service, root:root0644; disabled at exit.
- /var/lib/sova-cha-fan3, user:user0700: controller.lock, original baseline.json,
  pending-write.json, status.json, current blocked.json, and timestamped archived
  startup/invariant blocked/status records. Files private0600.
- Private staging/evidence: /home/user/.config/sova-private/h025-fan01-20260928,
  including source, startup-failure-191802, invariant-failure-192148 and
  stop-failure-193017. Extra temporary read-only source /tmp/h025-cha_fan3-readonly.py.

Existing BMC/node credentials stayed in their original protected host paths.
Systemd LoadCredential supplied transient service-private runtime copies only;
no credential reached Git, task artifacts or model containers. Diagnostic
transient units were collected and added no persistent daemon. No app restart,
Proxmox access/credentials, frontier-policy change, GitHub push or merge by W1.

See [implementation/status contract](../../scripts/thermal/H025-CHA-FAN3.md) and
[compact results](results.json). Private full receipts remain in worker output;
root/coordinator owns publication and any newly bounded continuation.
