# H013 — inspect 1M, disable GPU ECC and repeat concurrent load

Authorized on 27 September 2026. The user requests a progress/result check of
Flash's existing 1M test, then ECC off and an ai-vm reboot after that test ends,
followed by a repeat of the four-model load test. No Proxmox reboot is authorized.

## Sequence and ownership

1. **Worker1, fresh bounded session:** read the actual H012 attempt02 owner,
   native progress and terminal result. The current request began at 02:36:10 UTC
   and has a 04:36:10 UTC deadline. Do not disturb it. Preserve all terminal
   evidence off-VM before maintenance. Return a prompt progress update; a paid
   session must not wait through a long inference request.
2. **Worker2, independent source review in parallel:** reuse the H011 fan-adjusted
   driver and fixtures. Identify the smallest durable change that preserves a
   qualified 1,048,576-token Flash configuration through reboot, including the
   native pool and subsequent Sova capacity advertisement. Inspect ECC policy
   enforcement, status readback and reboot readiness. Do not deploy or infer.
3. **After terminal settlement and review:** if 1M passes all correctness/usage/
   guard checks, prepare and activate the reviewed durable 1M configuration.
   Preserve the successful candidate/evidence until replacement is confirmed;
   no silent reversion to 480K. If 1M fails, preserve the failure and use the
   confirmed original 480K recovery. Keep weights, runtime, CPU placement and
   cache precision pinned. Sova remains paused and user data preserved.
4. **Worker1 maintenance:** record each GPU's UUID, ECC current/pending, power
   limits, clocks, fan readings and thermal thresholds. Disable ECC on the three
   identified Blackwells only; Ada remains off. Keep existing error counters.
   Stop services through their owners, confirm settlement, reboot ai-vm once,
   and verify a new boot ID, UUID mapping, actual ECC current/pending state,
   storage, native contexts and service health. Do not infer that pending means
   applied. If passthrough prevents application by guest reboot, report the
   exact limitation instead of resetting hardware or rebooting Proxmox.
5. **One guarded four-way repeat:** reuse the prior real-inference workload and
   synchronized owner. Target approximately five minutes of actual overlapping
   computation: Flash 65,536-token input, both Qwens with fresh 262,144-token
   inputs, and bounded Full HD Ada generations. Qwen pools remain 480,000; Flash
   is 1,048,576 only if qualified by the completed test. Use existing per-request
   and owner limits, fresh short warm-ups and settled comparable starting
   temperatures. Do not repeat the 1M input or expand into a benchmark sweep.
   Stop new work at the deadline and settle owned requests. A thermal stop is a
   reported outcome, not permission for another repeat or raising thresholds.

## Comparison and evidence

Keep the 85°C temperature cutoff, 7% free Flash VRAM, existing Qwen/Ada memory
reserves, 15% host reserve and no-swap model cgroups. Preserve source/storage and
lifecycle guards; never clear owner records to force a retry. No runtime/driver
updates, fan or power-limit changes, clock locking, new models or installer work.
A different Flash configured pool after successful 1M is a disclosed difference
from H011, so the result is not a perfectly isolated ECC causal experiment.

Sample UUID-mapped temperature, GPU power/utilization, clocks, fan telemetry,
memory and thermal/power slowdown indicators. Record fan readings as unavailable
where the external server fans are not exposed. Keep separate simultaneous sums
for the three Blackwells on the workstation PSU and the externally powered Ada.
CPU/wall/PSU power remains unmeasured unless an existing sensor supplies it.
Compare the same early interval against H011, plus sustained behavior if reached.
Different ambient/inlet conditions and user-adjusted external fans limit causal
attribution. The 85°C test guard is distinct from a driver thermal-throttle limit.

ECC overhead can affect memory traffic/capacity and workload performance. Its
specific effect on Blackwell temperature is a hypothesis to measure, not an
established explanation. NVIDIA's historical GDDR bandwidth example is not a
measured Blackwell GDDR7 penalty.

## Bounds and closeout

Initial readback task: at most 10 minutes; independent review: at most 20 minutes.
Use fresh remote Codex CLI sessions for bounded tasks and retained IDs for direct
follow-ups. Aim to finish maintenance and one repeat within 90 minutes after the
1M job settles. Stop on a concrete unsupported operation or guard failure; save
an honest partial result rather than create open-ended recovery/tuning work.

Publish reviewed fixes/settings and concise machine-readable results to the
existing GitHub branch/PR. Keep credentials and bulky traces outside Git. Final
report: 1M outcome/timing/memory; ECC current/pending after reboot; four-way overlap,
completion/thermal outcome and comparison; actual final model and Sova state.
All four services should be restored ready when safe. Restore Sova only after
result/configuration review confirms accurate model capacity and service state.
