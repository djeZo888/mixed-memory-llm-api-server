# Dated four-GPU transfer observations — H005 publication checkpoint

These are saved measurements, not a new run. First three cards reuse
[H004, 2026-09-24](../h004-gpu-20260924/RESULT.md); the Server uses the retained
H005-NEWGPU-QUALIFY-20260925 receipt. Exact raw SHA256 values are in the
[evidence index](acceptance-evidence.json). Current overall acceptance remains
[PARTIAL / PENDING](../../docs/service-resilience-acceptance.md).

Rates are median **decimal GB/s (10^9 bytes/s)** from nvbandwidth pinned copy-engine
transfers, 256 MiB, five measured samples per direction per card, with one excluded warmup sample
per direction per card.
VRAM is capacity in MiB. PCIe values are dated observations; idle Gen1 must not
be read as loaded capability. Endpoint capability and the NVML path maximum are
separate from the observed loaded link.

| Card / model | Date | VRAM MiB | Idle / loaded PCIe | Endpoint / NVML maximum | H2D / D2H GB/s | Sampled core °C |
|---|---|---:|---|---|---:|---:|
| 01 — NVIDIA RTX PRO 6000 Blackwell Workstation Edition | 2026-09-24 | 97,887 | Gen1 x16 / Gen5 x16 | Gen5 x16 / Gen5 x16 | 57.00 / 56.50 | 33–35 |
| 02 — NVIDIA RTX PRO 6000 Blackwell Workstation Edition | 2026-09-24 | 97,887 | Gen1 x16 / Gen5 x16 | Gen5 x16 / Gen5 x16 | 57.00 / 56.50 | 34–36 |
| 03 — NVIDIA RTX 6000 Ada Generation | 2026-09-24 | 49,140 | Gen1 x4 / Gen3 x4 | Gen4 x16 / Gen3 x16 | 2.61 / 2.89 | 32–38 |
| 04 — NVIDIA RTX PRO 6000 Blackwell Server Edition | 2026-09-25 | 97,887 | Gen1 x4 / Gen3 x4 | Gen5 x16 / Gen3 x16 | 3.57 / 3.53 | 29–32 |

**Memory temperature was unavailable on all four cards. D2D/P2P was NOT_TESTED**;
the separate [September 23 bandwidth record](../image21-bandwidth-20260923/RESULT.md)
remains dated evidence and is not merged into these runs.

| Telemetry interval, UTC | Frames / cadence | Core temperature boundary |
|---|---|---|
| H004, September 24, 12:58:07.421602–12:58:38.834301 | 158; nominal 200 ms; actual min/median/max 135.957/200.070/264.089 ms | First three rows above |
| H005 Server warmup, September 25, 17:14:00.939–17:14:05.341 | 23; actual 187.905/200.031/212.541 ms | 29–31 °C |
| H005 Server measurement, September 25, 17:14:36.869–17:14:54.876 | 91; actual 194.018/200.123/206.091 ms | 29–32 °C |

No continuous monitoring is claimed across the Server interval gap. All 83
load-attributed frames in the Server measured window were Gen3 x4; its measured process ran 16.898 s.
This supersedes H004's fourth-card initialization failure only for the successful
brief transfer sanity. The other three cards were not remeasured.

The Server remains unassigned, with no final compute/graphics consumers or
card-device descriptors in that receipt. No ECC setting changed. These short
samples establish neither sustained thermal/stability acceptance nor peak platform
bandwidth, model/image capacity or context capacity. The later image warm/load
33–72 °C interval is separately reported in the current acceptance document and
must not be substituted for this dated transfer interval.
