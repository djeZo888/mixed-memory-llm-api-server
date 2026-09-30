# H028 — fifth GPU, status recovery and Qwen Ada 200K

September 29, 2026 (Europe/Ljubljana). Hardware, short inference, controlled
restart and independent authenticated private API/status checks passed.
Both final native worker sessions exited successfully at 23:54 UTC September 28.

## Measured result

The new RTX 6000 Ada runs the existing Qwen3.8-27B FP8 weights with BF16 KV cache
on one GPU. The pinned runtime uses its Triton FP8 backend on Ada SM89; the
Blackwell-specific CUTLASS setting is not compatible with this GPU. No weights,
cache precision, driver, power limit or existing model assignments were changed.

Native readback confirmed both configured context and allocated token capacity
of **200,000**. A discarded 3,519-input-token warm-up preceded the measured case.

| Measurement | Result |
|---|---:|
| Actual measured input | 15,625 tokens |
| Actual output | 446 tokens |
| Time to first output | 4.557 s |
| Complete request, through EOF | 24.202 s |
| Effective input rate, input / time to first output | 3,429 tokens/s |
| Output rate, client arrival interval | 22.70 tokens/s |
| Peak device VRAM used | 43,662 MiB / 42.64 GiB |
| Minimum device VRAM free | 4,850 MiB / 4.74 GiB / 9.87% |
| Peak sampled GPU temperature | 61 C |
| Peak sampled GPU board power | 300.1 W |

The input rate includes client/serving overhead and first-token work; it is not
an isolated kernel prefill measurement. Output rate uses completion tokens minus
one divided by the interval from first to last output event. Streaming batching
can affect that estimate. All requests completed with HTTP 200, normal finish,
`[DONE]` and EOF. Early/middle/late retrieval, a structured `add(2,3)` tool call
and continuation returning `5` passed. Raw prompts/streams remain private;
[compact evidence](h028-hardware01-20260929/RESULT.json) retains counts and hashes.

The 200K cache pool was allocated, but the largest occupied input tested was
15,625 tokens. This does not establish full-200K speed, correctness or worst-case
workspace demand. Reported free memory stayed above the requested 7% reserve
during this short test. The percentage uses reported total memory; the device's
separate 628 MiB reservation is not counted as free.

## Hardware and fans

There are five detected GPUs. Their persistent UUIDs remain stable despite new
guest PCI addresses after adding the card. Current mapping:

| Current guest PCI address | GPU | Assigned role | UUID prefix |
|---|---|---|---|
| 01:00.0 | RTX 6000 Ada 48 GB, new | Separate Qwen 200K | GPU-14c23cbc |
| 02:00.0 | RTX PRO 6000 Blackwell 96 GB | Qwen0 480K | GPU-88058d9d |
| 03:00.0 | RTX PRO 6000 Blackwell 96 GB | Selected frontier profile | GPU-69acfa26 |
| 04:00.0 | RTX 6000 Ada 48 GB, external enclosure | Image service | GPU-5d895991 |
| 05:00.0 | RTX PRO 6000 Blackwell 96 GB, server card | Qwen1 480K | GPU-93dbfca8 |

The new Ada sustained **PCIe Gen4 x16** during an isolated three-second transfer
test. Its idle link downshifts normally; the current idle generation is not its
load capability. No directional transfer-bandwidth claim is made from this
short link-negotiation check. ECC was already off on all five cards.

The new Ada is included in NVIDIA fan control: 100% at >=70 C, return to firmware
control after <=65 C continuously for 30 seconds. Policy fixtures and live fan
discovery passed; the natural hot/cool threshold cycle was not exercised because
the GPU peaked at 61 C. CHA_FAN1 remains exclusively user/BMC controlled.

CHA_FAN3 was at 80% because its authenticated temperature feed was unavailable.
After transport recovery, the existing controller observed the server Blackwell
at 27 C and automatically returned to healthy 40% at 23:18:15 UTC. No manual BMC
override or controller restart was needed. Its existing 70/65 C hysteresis remains.

## Status failure and repair

The web page and API themselves returned HTTP 200. The ai-vm panel lost telemetry
because private API sockets stayed stopped after the network-failed boot. The
MAC-based Netplan rename is now verified. Normal ingress/socket recovery restored
both node feeds. A bounded recurring helper re-arms enabled stopped private
listeners after the configured network returns; healthy listeners are unchanged.
Disabled/masked listeners are respected. It does not start model services.

Separately, the node only collected detailed metrics for four registered GPUs.
Passive discovery now observes unassigned GPUs by UUID as well. Missing or failed
devices retain independent status; adding hardware does not grant lifecycle or
fan-control authority. The UI shows current PCI addresses and explicit transport
failure reasons. The new Qwen has its own catalog entry and native 200K readback.

## Scope and handoff

The new instance is separate from the shared 480K harness pool. Harness scheduling,
engine integration, frontier repair, existing-model restarts, full-context tests
and multi-GPU power tests are outside H028. Other configured model services were
stopped following the hardware reboot; their actual unavailability remains visible.

Dedicated API base: `http://10.156.100.60:30014/v1`, model alias
`qwen3.8-27b-ada200k`, using the existing protected API key. Anonymous access
returned HTTP 401. The private listener retains the existing VLAN/subnet policy.
The seventh transport participates in delayed-network recovery; the original
twelve transport unit files were unchanged. The final timer checks after 45
seconds of boot, then 60 seconds after each bounded recovery run completes.

An actual service restart exposed a preflight bind failure before model startup.
Its precise transient cause was not established. The corrected probe permits
reusing a recently closed connection while still rejecting an active listener;
both cases passed focused socket tests. The final service started successfully
at 23:44:52 UTC. One short authenticated response at 23:47:20 returned `OK` with
16 input / 2 output tokens and complete EOF. The original benchmark was not
repeated. Persistent startup uses a relative warm-up budget and a qualified
immutable model profile instead of an expired campaign deadline.

Root reviewed source and evidence; mac-worker1 performed hardware/inference work
and ai-vm deployments, and mac-worker2 implemented/tested status and recovery code.
No implementation, build, benchmark or VM operation ran on Mac-Orchestrator.
Future startup is ordered after the existing boot job to avoid competing for the
lifecycle lock. This does not start that job or propagate its failure, but can
delay the new Ada service while a long boot job finishes. The final ordering
change used daemon-reload only; the model stayed resident.

Evidence:

- [Hardware, benchmark and fan qualification](h028-hardware01-20260929/RESULT.json).
- [Persistent service and private API deployment](h028-finalize01-20260929/README.md).
- [Independent status and API acceptance](h028-accept01-20260929/REPORT.md).
- [Authenticated LAN checks](h028-accept01-20260929/lan-get-acceptance.json).
- [Worker1 exit receipt](h028-accept01-20260929/worker1-terminal.json) and
  [Worker2 exit receipt](h028-accept01-20260929/worker2-terminal.json).

The final integrated source matches all 16 deployed source pins. Worker1 reported
96 focused checks passing; Worker2's final status change passed the existing 16
status/registry checks and TypeScript build. Browser visual acceptance, a
whole-VM reboot and deliberate network-failure injection remain untested.
