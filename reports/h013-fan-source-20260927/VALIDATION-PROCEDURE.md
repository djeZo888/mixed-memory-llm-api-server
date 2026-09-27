# Post-1M live validation procedure — REVIEW ONLY, NOT RUN

Root review and current 1M terminal settlement are prerequisites. Worker1 alone
owns any eventual live execution. No workload, new API or force CLI mode is
needed. This task did not execute these operations. Validate the exact delivered
source first; source/getter evidence is not setter acceptance.

1. Establish a bounded idle maintenance window after 1M settlement, with no
   competing fan owner or simultaneous lifecycle work. Check service/process
   ownership through the reviewed operations owner. Do not stop or adopt an
   unknown controller. Use the protected exact-UUID config, protected state and
   the candidate's dedicated flock. No model lifecycle lock is acquired by the
   fan adapter. Missing config/state protection or a busy flock aborts.
2. Under that lock, load state via `Store.load()`. If any prior intent is owned,
   use the existing owner's conservative recovery procedure; do not run a new
   cold validation, clear/edit JSON or assert ownership manually. `Controller`
   and `BoundedJobs` must use this same `Store` throughout.
3. Run `jobs.batch(dict.fromkeys(INTEGRATED, "inspect"), controller.owned)`.
   Qualify each device independently: exact UUID binding succeeded, no getter
   error/conflict, >=1 enumerated fans, all policies automatic=0, finite fresh
   absolute temperature <=65 C, sample age <=6s. Record excluded devices as
   missing/unsupported/degraded, never successful. Server remains
   external-control-needed and is never submitted to a fan job. Recheck cool
   freshness immediately before each initial test device's transition.
4. For each qualified device, set its entry in the in-memory owner map and call
   `store.save(controller.owned)` successfully **before** passing that map to
   any mutation job. This is the existing atomic/fsync durability path, not a
   hand-edited JSON file or an unbacked `owned=True`. Add that UUID to
   `controller.recover` to require the conservative recovery/cooldown sequence.
   On save failure, issue no new setter and stop the adapter. Keep the lock.
5. Use the existing bounded `jobs.batch({uuid: "boost"}, controller.owned)`;
   it re-enumerates and requests 100% on every fan, checking manual policy=1
   and target=100 for all. Every actual per-device/per-fan success must be
   recorded; error/timeout/unsupported readback is degraded. Do not equate
   automatic target with reported speed. Worker1 may separately observe RPM
   rise using its existing read-only getter receipt path; allow mechanical
   ramp and never require immediate maximum RPM. Intended-setting success
   alone is not physical airflow qualification.
6. Run only the existing `controller.cycle()` every 2s within an absolute
   **90-second total adapter deadline**. Do not call `device_job(...,"default",
   ...)` directly. Its controller resets restart/gap/error cooldown and only
   requests the official default API after a new continuous fresh <=65 C
   30-second sequence; it rechecks temperature before each default setter.
   Record automatic-policy readback separately for every restored device.
   No custom low duty is permitted.
7. If any test-device error, stale/unknown observation, hot state, interruption
   or deadline occurs, end validation and call `controller.cycle(stopping=True)`
   while still holding the same lock. This attempts 100% for owned intent,
   never defaults. Preserve owned state and report degraded. Do not release
   intent based only on elapsed time, a client timeout or a partial restore.
   Successful normal default restoration is the only path that clears intent.
   A subsequent service recovery must qualify its own new full cooldown.
8. A clean stop calls the same boost-only stopping cycle. The operations owner
   must supervise abrupt failure with the reviewed unit's ExecStopPost path
   and retain ownership state. Apply a bounded outer process lifetime, but do
   not claim it cancels kernel calls: surviving child lock inheritance can
   block global restart until the driver settles. Never launch an overlapping
   controller to bypass this lock. A failed adapter must not leave monitoring
   responsibility ambiguous; root chooses the subsequent reviewed owner.

This is a small procedure against the existing adapter primitives, not a new
one-shot force feature or an activation script. Root must review the concrete
bounded invocation before execution, including exception/finally handling,
per-device records and the chosen unit's kill/StopPost behavior. No physical
control availability is accepted until actual setter plus readback succeeds for
each device. Preserve the independent 85 C load-test guard and disclose the fan
policy as a confounder in any later ECC-off comparison.
