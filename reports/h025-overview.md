# H025 — fan control and concurrent-load results

## Outcome

The requested fan policies are deployed. The corrected test completed its
five-minute admission window without reaching the 85°C stop threshold. It did
**not** pass full four-model functional acceptance: the benchmark driver
unnecessarily stopped Qwen0 on an unsent request at the cutoff, and GLM's sole
16K request timed out after 900 seconds without a completed response.

No additional load retry or model/runtime tuning was performed. All accepted
work was physically settled, with the original failure records preserved.
All four native services reported ready again at 20:58:11 UTC, with the web and
status endpoints returning HTTP 200. CHA_FAN3 was healthy at 40% after cooldown.
This is restored readiness, not a successful replacement for the failed GLM
inference. Exact identities and preserved data counts are in the
[EXEC05 report](h025-exec05-20260928/SUMMARY.md).

## Fan ownership and behavior

| Fan | Controller | Behavior |
|---|---|---|
| CHA_FAN1, cooling both motherboard Blackwells | BMC/user only | Existing PCIe2/PCIe5 temperature sources; Sova makes no changes |
| Built-in fans on the motherboard Blackwells | Existing NVIDIA controller | 100% at >=70°C; firmware profile after <=65°C for 30 continuous seconds |
| CHA_FAN3, cooling the server Blackwell | Sova service on ai-harness | 80% at >=70°C; 40% after <=65°C for 30 continuous seconds; hold state between thresholds |

The external controller preserves the disabled CPU-temperature source and
writes only the verified CHA_FAN3 channel. Unrelated user changes to CHA_FAN1
are audited without invalidating CHA_FAN3's target-only checks. Readback,
physical idle 80-to-40 behavior and stop/restart checks passed. The load test
also exercised a natural 40-to-80 transition as the server GPU warmed.
It returned to 40% during a cool interval and rose again on a fresh hot sample;
the complete sequence is retained, including one brief low-to-high transition
about seven seconds apart. The 30-second cool dwell reduces switching but does
not guarantee constant fan speed through separate workload bursts.
See [fan qualification](h025-fan04-20260928/README.md).

## Five-minute hardware observations

The exact window started at 20:36:36.032 UTC on September 28, 2026. There were
223 samples, with mean spacing 1.347 seconds and maximum gap 2.785 seconds.

| GPU and workload | Peak temperature | Average board power | Peak board power |
|---|---:|---:|---:|
| Motherboard Blackwell, Qwen0 | 72°C | 357.90 W | 511.29 W |
| Motherboard Blackwell, GLM | 41°C | 87.95 W | 109.59 W |
| Server Blackwell, Qwen1 | 75°C | 397.89 W | 619.79 W |
| Ada, image service, separate PSU | 71°C | Not summarized | 300.07 W |

The three Blackwells together averaged **843.74 W** and peaked at **1,172.43 W
in the same sample**. This excludes the independently powered Ada. There were
no sampled hardware thermal or power-brake events, no owned-cgroup swap/OOM
faults and no recorded kernel fault events. All four GPU utilization readings
were nonzero in 140 samples; GLM GPU utilization ranged from 0 to 46%.

These readings support improved cooling for this workload. They are not a
worst-case PSU certification: GLM used little GPU power, there were gaps between
requests, CPU/wall power was not measured, and sampled power misses electrical
transients. See [the additional-Ada power budget](h025-power-20260928/README.md)
for the user's 400 W and 200–250 W CPU assumptions and proposed 500 W caps.

## Request outcomes and software defects

- Qwen0: 162 genuine completed requests; one additional request was refused
  before send at the admission cutoff and unnecessarily triggered its runtime
  stop. The original refusal text was not retained. The row has no send-start
  or body-sent timestamp; source ordering supports an admission-boundary race.
- Qwen1: 124 genuine completed requests.
- Image service: six genuine completed Full HD requests.
- GLM: one 16,268-token request, HTTP 200 but zero response bytes and no final
  usage/DONE/EOF before the 900-second timeout. Physical stop and separate
  owner reconciliation passed; the original failed/unknown ledger is retained.

Observed in-flight transport overlap was about 167.14 seconds. A four-way
intersection of *successfully completed* HTTP intervals cannot be established
because GLM did not complete. In-flight waiting is not proof of simultaneous
model computation.

The earlier EXEC04 attempt stopped after 5.61 seconds on a monitor read failure.
A later bounded reproduction found a legitimate atomic replacement of the fan
status file could trigger the shared reader's hardlink guard. The corrected
reader reopens only after a confirmed valid replacement, at most three times;
shared storage protections remain unchanged. Twenty-five focused correction
tests passed, and the corrected campaign did not repeat that monitor fault.
See [original failure evidence](h025-exec04-20260928/SUMMARY.md) and
[reader correction](h025-mirrorfix-20260928/README.md).

## Follow-up work

The cutoff admission/ownership path and GLM's missing response need separate,
bounded investigation before claiming a complete four-model functional pass.
Do not automatically repeat stress work. MiMo repair, Codex completion, new
models and power-cap performance tests were outside this fan-control task.
Sova's permanent frontier selection was not changed: retained GLM was used only
as the explicitly authorized test fallback.
