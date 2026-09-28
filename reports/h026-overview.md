# H026 — Qwen at 600, 550 and 500 W

## Result

Both Qwen cards completed the warm-up and all four measured requests. **500 W
was a useful tradeoff in this short test:** output generation remained essentially
unchanged, while complete requests took 6.5% longer on the motherboard card and
3.8% longer on the server card. At 550 W, the increases were 2.3% and 1.9%.
This is a one-sample comparison with a repeated 600 W anchor, not a statistical
qualification or a sustained full-system power test.

The user authorized both VMs to be shut down afterward for another Ada GPU.
Original 600 W limits were restored and read back before shutdown; no persistent
500/550 W policy was installed. ai-vm accepted graceful poweroff at21:20:08UTC and SSH closed at21:20:11.
ai-harness accepted poweroff at21:24:20UTC; its SSH/web ports became unavailable
and its journal connection closed at21:24:29. Hypervisor power state was not
independently queried. See the shutdown receipts for exact evidence.

## Measurements

Each request used 63,974–63,981 actual input tokens and exactly 512 output tokens.
Both runtimes retained 480,000-token configured capacity, FP8 weights, BF16 cache,
disabled prefix cache, and their existing GPU assignment. One representative
600 W warm-up per card was discarded. Cards were tested sequentially using fresh
leading nonces, temperature zero, and reasoning disabled.

| Qwen card | Limit | Input proxy tok/s | Output proxy tok/s | Complete request (s) | Mean board power (W) | Peak temperature |
|---|---:|---:|---:|---:|---:|---:|
| Motherboard | 600 W | 6,638 | 36.58 | 23.608 | 445.0 | 63 C |
| Motherboard | 550 W | 6,177 | 37.02 | 24.161 | 421.4 | 68 C |
| Motherboard | 500 W | 5,695 | 36.73 | 25.147 | 416.8 | 70 C |
| Motherboard | 600 W anchor | 6,389 | 36.97 | 23.837 | 454.6 | 74 C |
| Server / PCIe x4 | 600 W | 7,238 | 38.02 | 22.282 | 410.0 | 67 C |
| Server / PCIe x4 | 550 W | 6,990 | 37.70 | 22.709 | 400.6 | 71 C |
| Server / PCIe x4 | 500 W | 6,712 | 37.59 | 23.128 | 384.0 | 69 C |
| Server / PCIe x4 | 600 W anchor | 7,182 | 37.62 | 22.490 | 403.7 | 73 C |

**Timing definitions:** native prompt/decode timing fields were unavailable.
Input speed is actual input tokens divided by dispatch-to-first-output time,
including transport, prefill and first-token overhead. Output speed is
(actual output tokens minus one) divided by first-to-last output arrival time;
chunk buffering can bias this estimate. These are comparable client observations,
not native kernel throughput. Full terminal SSE, actual usage, DONE and HTTP EOF
were retained for every request; exact runtime ownership and readiness matched.

The final 600 W anchors took 1.0%/0.9% longer than the initial baselines. Output
varied about 1% between these anchors; apparent tiny output gains at lower caps
are within this variability. The motherboard prefill proxy drifted by about 3.8%,
so do not overinterpret a small difference from a single measurement.

Mean request board power at 500 W was 416.8 W / 384.0 W, versus 445.0 W /
410.0 W initially at 600 W. These are roughly 1 Hz board samples, excluding CPU,
other cards and PSU losses. A software power limit is not a hard transient ceiling:
the server card briefly sampled 513.4 W at its verified 500 W setting. This test
does not establish sufficient PSU capacity for an additional GPU.

Maximum sampled temperatures across the full sequences were 74 C / 73 C. There
were no thermal guard faults. Different starting temperatures and fan hysteresis
mean these sequential samples do not quantify steady-state cooling at each cap.

## Execution and evidence

- Successful measurement unit: `h026-caps02.service`, September 28, 2026,
  21:14:36–21:18:54 UTC; all ten requests settled, no retries during inference.
- One earlier pre-dispatch failure found an inherited setgid bit on the private
  raw-output directory. It sent no inference, stopped no runtime and restored
  caps. The failure was preserved; fixing the directory mode preceded the run.
- Worker1 used native session `01a0e9d7-255c-7153-907a-b9136e22c032`. Worker2's
  short source review used `01a0e9d7-f14b-74e0-89db-66798f81319b`; its coordinator
  subsequently checked the two corrected conditions against exact source hashes.
- Benchmark-only transport fixes distinguish unsent cancellation from partial
  dispatch, and retain a completed request when later metric checks fail.
  Worker1 reports 17 focused client tests passed; root did not rerun them.
- Credentials, request/response bodies and bulky raw telemetry remain private.
  Compact results, exact source and shutdown receipts are published alongside
  this overview. Existing histories/files were preserved.

## Recommendation

Use **500 W as the candidate permanent Qwen cap** if the priority is GPU power
headroom: this run retained output speed with a modest total-latency cost. A
550 W cap offers a smaller prefill penalty. Neither setting has been installed
as a persistent policy; the benchmark restored the original 600 W configuration.
Choose and persist the desired limits after the hardware addition, then validate
the intended simultaneous workload. No additional stress test was run here.

## Closed checkpoint

Worker1 exited0 at21:22:59UTC; worker2 shutdown session
`01a0e9e5-5156-7632-bdb5-03eb4fcd0566` exited0 at21:25:37UTC. No worker remains
waiting, and no more inference or VM operations are planned in this task.

Evidence: [benchmark details](h026-caps-20260928/README.md),
[machine-readable measurements](h026-caps-20260928/RESULTS.json),
[ai-vm shutdown](h026-caps-20260928/VM-SHUTDOWN.json),
[ai-harness shutdown](h026-shutdown/AI-HARNESS.json), and
[corrected-source review](h026-review/CORRECTED-SOURCE-REVIEW.json).
