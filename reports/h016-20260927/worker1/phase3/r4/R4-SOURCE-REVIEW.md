# H016 r4 independent local source review

Reviewed current r4 source, `GUARD-CORRECTION.diff`, staged hashes and recorded
checks. No blocker found in this correction. No ai-vm connection or runtime
mutation was made by this reviewer. This review does not establish live guard
freshness, native readiness or benchmark completion.

The r3 failure exposed a real ordering defect: its mandatory monitor performed
unbounded process placement reads before writing telemetry and before all host,
temperature, GPU reserve and swap/OOM assertions. A blocked `numa_maps` read could
therefore suspend every mandatory check without setting the shared failure flag.
This finding supersedes any interpretation of the earlier r3 source review as
proof that its guard remained responsive during eager loading.

R4 removes all native-process status, maps and task-stat reads from the mandatory
loop, including indirect placement calls. The loop reads GPU telemetry, global
`/proc/meminfo` and cgroup files; global meminfo is not native-process inspection.
The GPU queries use two-second timeouts. Existing reserve, lower temperature
cutoff, no owned swap/OOM checks and five-second sleeps remain. Five seconds is
the sleep interval, not a guaranteed maximum elapsed interval including sampling.
Failures still set the failure flag and interrupt the owner; a delayed exception
after settlement has begun does not send another signal into its cleanup.

Process placement runs only at post-load and post-warm boundaries in a diagnostic
subprocess. The default read budget is three seconds, followed on timeout by an
exact-child kill and at most 0.2 seconds of reap waiting. Timeout, failed startup,
nonzero exit and malformed output produce `UNAVAILABLE` diagnostic evidence.
An unreaped child is recorded explicitly with its PID and `diagnostic_settled=false`.
This tolerance applies only to optional diagnostics; it does not disable or
relax the independent mandatory physical guards. Anonymous page counts are
identified as pages in anonymous non-file VMAs; policy and thread affinity are
reported when the diagnostic succeeds.

All eight runtime/config files match `r4/STAGE.json`. `LAUNCH.json`, proxy, native
identity and GGUF inspector remain byte-identical to r3. The reviewed changed
runtime hashes are:

| File | SHA-256 |
| --- | --- |
| candidate_owner.py | `fd66a568d57f50c646c3a88b35020b0d1ecd4adc9ade33fe52cd5f304c38dcfa` |
| telemetry.py | `2c0e7483845530cf9b669d699c67b574e0f4a8cbba21dd6c511bc7ddf7f817aa` |
| benchmark.py | `ece4d5d801edc10505ae7d7e9e108a8d4a017e76ac436a220b050f0239e75803` |
| verify_retained.py | `67fda6d0a26047582e002a0e8cbe93cdb4e87bbcbe5acf79a285712863791de8` |

The source delta preserves the approved eager load/interleave policy, image,
security, model settings, admission/settlement deadlines and exact GLM cleanup.
No persistent adoption or node draft is included. `CHECKS.txt` records 18 tests:
17 PASS and one private legacy fixture SKIP, including guard responsiveness and
bounded diagnostic cases. This reviewer independently ran the four added guard
regressions before the final combined run; all passed. Earlier benchmark
`SUBMITTED` versus `body_sent` and interrupted partial-response evidence caveats
remain unchanged.
