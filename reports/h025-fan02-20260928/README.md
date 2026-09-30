# H025 FAN02 stop credential repair and normal lifecycle qualification

Normal start, cool40, stop-high80 including the separate ExecStopPost process,
and restart/fresh-cool40 passed. No model load was performed. Source commit
58c42edfdbb0649f689b2ee562b6888e7b1d1511 was reviewed before installation.

The exact denied ancestor was identified using metadata only: systemd255.4
presents /run/credentials as root0000 in ExecStopPost. The protected parent walk
then fails with EACCES at the per-unit child, before opening the credential file.
This establishes namespace visibility, not an inferred internal ACL-teardown bug.

The unit now binds exactly the two existing private0600 credentials read-only
into /run/sova-cha-fan3-credentials, a user:user0700 RuntimeDirectory. It keeps
User=user, Group=user, ProtectHome=yes and the other sandbox, lock, latch,
invariant and status protections. No credential copy, contents, original-mode
change or extra privilege is involved. The obsolete root0440 exception is removed.

Two focused synthetic credential fixtures passed on ai-harness, including
missing files, symlinks, hardlinks, wrong ownership, group readability and
writable parents. Matching sandbox phase checks passed protected reads of both
credentials in start and stop, EROFS on write-open, and hidden original/unrelated
home paths. Unit verification passed. The earlier58 broad checks were not repeated.

Root exact GO at19:42 authorized one known-stop-fault archive and reconciliation.
All old startup/invariant/stop failures, original baseline, pending receipts,
installed source/unit and journal were preserved in private host evidence.
The current blocker was archived by exact hash; it was not automatically reset.

| UTC | Phase | Curve configuration | Raw tach |
| --- | --- | --- | --- |
| 19:43:12 | Initial cool, independent | 40 | 3600 |
| 19:43:34 | Separate ExecStopPost PID65213 exits0 | 80 | Settling |
| 19:43:46 | Independent settled stop-high | 80 | 5040 |
| 19:44:52 | Independent final cool after restart | 40 | 3600 |

Tach units are absent; curve configuration is not measured PWM. Mode4, source000,
all other zones and the original baseline invariant stayed unchanged. Main stop
exited0; post-stop exited0, verified high, and needed no extra PUT. Current
qualified process PID65410 started19:44:04.170295UTC, host boot
a80a9860-7fde-4483-abc4-00903793c201, node boot
17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125. Full pins and receipts are in results.json.

The first independent readback helper used the credential8192-byte default for
baseline.json and hit file_size. Only that read-only helper was corrected to the
existing65536-byte state cap; the controller and lifecycle were not replayed.

The protected status contract is unchanged and still requires fresh<=15second
status/readback/tach/source before W2 admission. This is a timestamped qualification,
not an enduring load authorization. Root owns separate workload admission.
Crash/watchdog fault injection, a real70C GPU crossing and overlap were NOT_TESTED
in this narrow task. No GitHub push, runtime/model/TDP change or other-zone write.
