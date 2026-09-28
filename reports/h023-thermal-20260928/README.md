# Cooling and concurrent workload — September 28, 2026

**Third-GPU cooling passed the bounded test. Four-way thermal/PSU qualification is partial.** All accepted requests completed, all four models remain resident, and temporary benchmark processes were closed at 16:50:22 UTC.

## Third Blackwell

With CHA_FAN3 configured at 75% and the GPU power limit unchanged at 600 W, 103 Qwen requests completed over 221.6 seconds, including 181.2 seconds of active HTTP inference. The observed maximum was **79°C**. No thermal, model-swap or OOM fault occurred. This is a short workload result, not an indefinite cooling guarantee.

## Four-way workload

The test submitted one MiMo request, 78 requests to the stock-cooled Qwen, 61 to the server-card Qwen, and three Full HD images. All reached HTTP completion. Two additional Qwen records failed during counting/bookkeeping before submission; they were not extra inference requests.

The benchmark duplicated its growing request history into `STATUS.json`, exceeded the existing 1 MiB storage limit, and lost its monitor at **16:41:49 UTC**. Independent monitoring resumed at **16:47:13 UTC**. The original failed records remain unchanged; a separate receipt reconciles completed work using full HTTP evidence and current native-owner idle state. The run is **not** a complete five-minute thermal or PSU pass.

| Model/card | Peak temperature before the monitoring gap | Sampled peak GPU power before the gap |
|---|---:|---:|
| MiMo / fast Blackwell | 53°C | 101.33 W |
| Qwen / stock-cooled Blackwell | 75°C | 482.89 W |
| Qwen / server Blackwell | 73°C | 621.89 W |
| Image / Ada, separate PSU | 71°C | 299.99 W |

Closed request intervals overlap across all four services for **90.37 seconds**. All four GPUs report nonzero utilization in 36 of 123 samples before the gap. These are different measurements; neither establishes uninterrupted full GPU load. The three Blackwells' highest same-sample sum was **1,143.81 W**. Host CPU, RAM, motherboard, wall power and PSU losses were not measured. No GPU power limits were changed.

MiMo's first request after loading completed 16,276 input and 20 output tokens in **414.92 seconds**. Native timings report **39.48 input tokens/s** and **9.15 output tokens/s**, with no cached input. The output sample is short and this was first-use inference during concurrent activity, not a warmed steady-state speed benchmark. The configuration remained 950,000 tokens with 8 decode / 64 batch threads; this does not qualify an occupied 950K context.

## Fan control

The BMC accepted CHA_FAN3 at 100% at 16:42:43 UTC and verified it at 16:42:53, preserving the other zones, source and mode. This occurred after the original monitor had failed. Raw tach changed 5040→2760 with units unconfirmed, so a physical speed increase is **not proved**. The configured setting remains 100% pending a later controlled return to the user's 75% baseline while idle. No permanent GPU-driven BMC fan controller was installed.

## Follow-up

H024 proceeds with the separately authorized two-hour Codex implementation window. No thermal or large-context repeat is scheduled. Before reusing this benchmark driver, compact its status record while retaining per-request evidence and make monitor failure close admissions reliably. Do not widen the shared storage limit or present this partial run as hardware qualification.

[Machine-readable results](RESULTS.json) contain exact evidence hashes. Credentials and bulky traces remain private.
