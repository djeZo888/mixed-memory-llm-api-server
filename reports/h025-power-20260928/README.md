# Three-Blackwell power and an additional Ada

The exact 300-second H025 EXEC05 admission window contained 223 power samples,
with mean spacing 1.347 seconds. Means are arithmetic sample averages, not
energy-integrated measurements. The existing Ada uses its separate enclosure
PSU and is excluded from the three-Blackwell sum.

| Card | Mean board power | Maximum recorded board power |
|---|---:|---:|
| Qwen0, motherboard Blackwell | 357.90 W | 511.29 W |
| GLM, motherboard Blackwell | 87.95 W | 109.59 W |
| Qwen1, server Blackwell | 397.89 W | 619.79 W |
| All three, same sample | 843.74 W | 1,172.43 W |

The maximum combined reading was at 20:39:52.692 UTC on September 28, 2026.
Independent per-card maxima must not be added and called a simultaneous peak.
All three configured power limits were 600 W; the server card nevertheless
reported a 619.79 W sample. This is telemetry, not a measurement of electrical
transients or a guarantee that a limit is an instantaneous ceiling.
No sampled hardware thermal or power-brake flag was active. Qwen0's software
power-cap flag was active in 84 of 223 samples, which is distinct from an
external PSU power-brake event.

## Adding another RTX 6000 Ada to the workstation PSU

Using the user's allowances, and assuming 2,200 W is the PSU's continuous DC
output at the operating input voltage:

- Existing sampled Blackwell peak: 1,172.43 W.
- CPU allowance: 400 W; other hardware allowance: 200 W.
- Additional Ada board budget: 300 W.
- Estimated total at that sampled peak: **2,072.43 W**.
- Arithmetic remaining capacity: **127.57 W (5.8%)**.

The Ada's 300 W rating is in [NVIDIA's official specifications](https://www.nvidia.com/en-us/products/workstations/rtx-6000/), checked September 28, 2026.
CPU/peripheral allowances are assumptions, not wattage measured by this test.
Do not add AC conversion losses directly to a DC-output PSU budget; wall draw
would be a separate measurement.

The user later proposed a more representative CPU allowance of 200–250 W and
500 W Blackwell caps. With 250 W for the CPU, the measured Blackwell peak plus
200 W of other hardware and a 300 W Ada would total **1,922.43 W**, leaving
**277.57 W**. With all three Blackwells actually reaching 500 W, the same
budget becomes **2,250 W** (or 2,200 W with a 200 W CPU allowance), leaving no
useful reserve. The CPU estimate is plausible for planning this workload but
has not been measured or established as a maximum.

[NVIDIA documents software power limits](https://docs.nvidia.com/deploy/nvidia-smi/index.html#pl-power-limit-power-limit)
within the minimum/maximum range reported by each card. Supported ranges are
now verified by a read-only query during normal H025 cleanup: both workstation
Blackwells report 150–600 W; the server Blackwell reports 300–600 W. All three
therefore support 500 W. Current/default/enforced limits remained 600 W.
See [exact range readback](supported-limits.json).

A possible profile for a future performance test is 500 W on each Qwen card
and 200 W on the frontier workstation card. These values are within the reported
ranges and sum to 1,200 W. Adding a 300 W Ada, 250 W CPU allowance and 200 W
peripheral allowance gives 1,950 W, leaving 250 W. This profile was suggested,
not applied or performance-qualified. The frontier card's low draw in this
small-context run does not establish its needs for future larger contexts.

This run does not justify unrestricted operation with the additional card.
GLM averaged only about 88 W of GPU board power, so this was not three saturated
Blackwells. The configured card limits plus the proposed Ada and host allowance
sum to 3 x 600 + 300 + 400 + 200 = **2,700 W**. Use a separate PSU or evaluate
supported GPU power caps before adding the Ada to the existing 2,200 W supply.
A combined Blackwell budget near 1,000 W would leave roughly 300 W of arithmetic
headroom under these assumptions, but performance and transient behavior would
need a separate validation. No power limits were changed in H025.

The five-minute power evidence remains useful, but the benchmark software
reported a cutoff error and the GLM request later exhausted its 900-second
budget. Therefore this is not a complete four-model functional qualification
or a worst-case PSU certification. See the final H025 overview for settlement
and service restoration.
