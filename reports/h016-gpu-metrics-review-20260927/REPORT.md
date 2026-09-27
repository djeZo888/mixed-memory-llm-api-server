# H016 GPU DRAM metrics review

**BLOCKED for the requested measurement. No ready collector command.** The retained toolchain cannot provide qualified, actual GPU DRAM read/write bytes/s from the already running uninstrumented R6 process under the no-restart/no-injection/no-replay constraints. Nsight Systems is absent; its documented built-in DRAM/VRAM read/write metrics are percentages. Existing Nsight Compute has no arbitrary-process attachment workflow. This conclusion does not assert that every possible NVIDIA SDK collector is incapable.

Review ended on documentation evidence; no wait for R6. Sova recovery remains **HOLD**. R6 execution and load remain solely Worker1-owned. Root must review any future execution.

## Evidence and compatibility

The small task-root `GPU-TOOL-PREFLIGHT.json` was the first evidence file read. SHA256: `4a006058d3e620a91669d55eb520ed0ed0b155d29390cbebc0285daf6c114874` (1,781 bytes).

- W1 receipt: CUDA 13.0.3 image `sha256:a85c9f5af049f0ab679c1669ae6fa8393022886739af7361e85bb96878e8cdd4`; `/usr/local/cuda/bin/ncu`, version **2025.3.1.0 build 36398880**; `--list-chips` includes `gb202`. Section deployment warned about unavailable user home and used image sections. Both probes returned 0. No GPU was attached or counters tested.
- W1 receipt: exact CUDA 13.2.1 devel tag/digest is not locally addressable. It must not be pulled or substituted. User-supplied W1 inventory says no host PATH/standard-path `nsys`, `ncu` or `dcgmi`; that inventory is a prompt observation, not contained in this JSON. The image's ncu is a separate retained capability.
- Target identity is user/W1-supplied: RTX PRO 6000 Blackwell / SM120, driver 595 series, UUID `GPU-69acfa26-8b60-61b5-702d-aee252c163cc`. No duplicate VM probe.
- Version-pinned [Compute 2025.3.1 release notes](https://archive.docs.nvidia.com/nsight-compute/2025.3.1/ReleaseNotes/index.html#gpu-support) list GB20x and require a CUDA-13-compatible driver. [CUDA compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html) gives R580 as the CUDA 13.x family minimum. Reported R595 clears that family threshold; this is not live counter qualification or proof of every feature on this exact SKU.
- Current official [Systems release page](https://developer.nvidia.com/nsight-systems/get-started) identifies **2026.5.1**, Linux x86-64 CLI distribution, and Turing-or-newer support. The GPU-metrics driver table in both reviewed user guides stops at Ampere (R440/R450/R470 TRD1/R455); it supplies **no explicit GB202/SM120-specific driver floor or guaranteed set alias**. Do not substitute the CUDA trace floor or ncu's R580 floor for a Systems GPU-metrics floor. No installed nsys version/help/set is available to verify the exact target/595 combination.

NVIDIA's [SKU exception page](https://developer.nvidia.com/err_nvgpu) separately restricts RTX 6000D BSE and RTX 5090D/DD on older tools. It does not identify the supplied ordinary RTX PRO 6000 as one of those SKUs. A `gb202` chip-name list alone is therefore weaker than actual SKU/counter qualification.

## Nsight Systems: device sampling is suitable in principle; units are not

[Current user guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html#gpu-metrics): GPU metrics are device-wide, single-pass sampling, without process/context attribution. Together with optional application launch and the [release notes' non-injection classification](https://docs.nvidia.com/nsight-systems/ReleaseNotes/index.html), this supports observing existing GPU work without CUDA API injection or workload replay. It is not arbitrary CUDA API attachment. `--trace=none` disables API tracing; also select `--sample=none` and `--cpuctxsw=none` to avoid unrelated CPU collection. No Linux `--system-wide=true` switch is needed: that switch is Windows injection.

Exact documented discovery/options (future review only; **nsys is absent**):

| Purpose | Documented interface |
|---|---|
| Version / general help | `nsys --version`; `nsys profile --help` |
| Device enumeration | `nsys profile --gpu-metrics-devices=help` |
| Set enumeration | `--gpu-metrics-devices=<verified-index> --gpu-metrics-set=help` on `nsys profile` |
| Device / set / frequency | `--gpu-metrics-devices`, `--gpu-metrics-set`, `--gpu-metrics-frequency` |
| Duration / file | `--duration=20` (or 30); `--output=<approved-path>` |

There is no documented GPU-metrics `--list-metrics` switch here. Set-help lists compatible sets, not proof of arbitrary raw-counter support. Literal GPU UUIDs are not documented values for `--gpu-metrics-devices`; documented selections are IDs/indices, `cuda-visible`, `all`, `none`. Future selection must map the authorized UUID to the listed index; never assume index 0 or use `all`. `file:` custom sets do not by themselves prove a supported bytes/s metric.

[2025.3 user guide](https://archive.docs.nvidia.com/nsight-systems/2025.3/UserGuide/index.html#gpu-metrics) documents these DRAM metrics (also present in current docs):

| Metric | Unit / meaning |
|---|---|
| `dramc__read_throughput.avg.pct_of_peak_sustained_elapsed` or `dram__read_throughput.avg.pct_of_peak_sustained_elapsed` | %, interface read activity relative to elapsed cycles |
| `dramc__write_throughput.avg.pct_of_peak_sustained_elapsed` or `dram__write_throughput.avg.pct_of_peak_sustained_elapsed` | %, corresponding write activity |
| VRAM variants prefixed `FBPA.TriageA.`, `FBSP.TriageSCG.`, `FBSP.TriageAC.` | Same percent-valued read/write families; no target alias asserted |

Export preserves those units: `.nsys-rep` can be exported with `nsys export -t sqlite <report.nsys-rep>`; documented tables include `GPU_METRICS` and `TARGET_INFO_GPU_METRICS`. Export cannot turn percent into actual bytes. No collection/export was made and no remote export path is approved by this report.

The documented sampling range is 10–200,000 Hz, default 10,000 Hz; the chosen set has its own recommended range. A future 20–30 s capture is bounded well below the [2025.3 release notes](https://archive.docs.nvidia.com/nsight-systems/2025.3/ReleaseNotes/index.html) five-minute support limit. NVIDIA describes low overhead, but gives no defensible percentage for this R6/GB202 case. Higher sampling/load can overflow buffers or produce missing/inconsistent samples. No frequency is qualified here.

GPU counters need [administrator permission](https://developer.nvidia.com/ERR_NVGPUCTRPERM): Linux root/sudo or suitable capability; NVIDIA documents CAP_SYS_ADMIN and CAP_PERFMON support from R565 with stated execution/container caveats. Existing permission is unknown. Do not relax perf/kernel restrictions or alter containers. CPU `perf_event_paranoid` is a separate issue, not a reason to change it for GPU-only sampling. Only one subscribing counter tool may run per applicable resource; Systems lists conflicts with Compute, Graphics and DCGM. Do not pause a mandatory guard to acquire counters; an unresolved conflict is a stop condition.

## Nsight Compute 2025.3.1: attach is a prepared-target protocol

The [exact-version CLI manual](https://archive.docs.nvidia.com/nsight-compute/2025.3.1/NsightComputeCli/index.html#modes) documents three modes: `launch-and-attach` injects while starting the application; `launch` injects and suspends at the first intercepted API; `attach` connects to that previously prepared target. The 2025.3.1 manual describes port-based connection (`--port`, `--max-connections`, attach `--hostname`), not arbitrary-PID injection into running llama. Do not import the newer manual's `--pid` option into this pinned proposal. The inspected CLI has no standalone/system-wide collector mode that avoids this workflow.

`--replay-mode=kernel` is the default; `application` relaunches the application; `range` captures/replays API/kernel ranges; `app-range` relaunches for range collection. Range modes can preserve intra-range concurrency but still require prepared targets and their capture/relaunch semantics. None is ready for existing R6.

The [2025.3.1 profiling guide](https://archive.docs.nvidia.com/nsight-compute/2025.3.1/ProfilingGuide/index.html#pm-sampling) says PM sampling is device-wide internally and uses context-switch data for attribution. It is still part of the ncu target workflow. `--query-metrics-collection pmsampling` enumerates candidates; only metrics individually fitting one pass are supported, while multiple pass groups may be needed for a selection. `--pm-sampling-max-passes` is a collection limit, not a no-injection/no-serialization guarantee. PM sampling excludes vGPU; passthrough versus vGPU is not independently verified here.

One pass may avoid repeated workload execution, but does not eliminate default kernel serialization, `--cache-control=all` flushing, or `--clock-control=base` clock requests. Selecting `none` for the latter two would not solve attachment or prove unchanged execution. Ncu PM sampling also allocates device buffers. There is no measured ncu overhead or proven GB202 read/write-byte metric list in the receipt. No ncu command can meet existing-R6 constraints. The separately authorized later-reload proposal in FUTURE-AB-PROPOSAL.md deliberately changes those constraints and is not executable approval.

## Measurement contract and least additional capability

- DRAM-active/controller utilization is time/activity fraction. Peak-bandwidth percentage is a normalized value, not a byte total.
- Multiplying a percentage by advertised bandwidth produces **estimated derived bandwidth**, not observed read/write bytes. Clock, normalization and transaction details matter.
- PCIe/NVLink traffic counts interconnect transfers, not all VRAM DRAM accesses. Some Systems link metrics are percentages despite names containing “bytes.”
- Required evidence is separately measured DRAM read and write byte counts/rates over known decode wall-time intervals, including gaps. Counter-derived bytes divided by measured elapsed seconds is valid; assumed peak times utilization is not. Report B/s and decimal GB/s (B/s divided by 1e9), with device-wide attribution and sample-loss qualifications.

The least capability root would need to approve for the unchanged-workload requirement is **qualification of a separate device-level periodic counter collector that actually exposes GB202 DRAM read/write byte counters in one supported configuration**, with current-driver compatibility, privileged access, exclusive counter ownership, UUID mapping, bounded buffering and loss checks. A narrow SDK/source feasibility review should precede any acquisition/build or GPU execution. [CUPTI PM Sampling documentation](https://docs.nvidia.com/cupti/main/main.html#cupti-pm-sampling-api) provides device-index enable/start/stop and metric-enumeration APIs, rejects multi-pass configurations, and requires buffer draining. This is a candidate mechanism, not an available collector or proven GB202 byte-counter solution; its public example launches its own workload and is not a ready external R6 monitor. Acquiring nsys alone, or upgrading ncu alone, does not resolve the demonstrated requirements.

Still **NOT_TESTED**: exact nsys/GB202/595 set compatibility; GPU counter permission/availability; byte metric names/units and pass count; arbitrary external collection; concurrent collector conflicts; target index mapping; 20–30 s loss/overhead; device buffer reserve impact; exported values; R6 attribution. No memory-copy bandwidth benchmark, inference, host/BMC/harness contact, instrumentation, build, package/driver/CUDA/tool acquisition, restart, runtime mutation, guard change, subagent or push occurred. Raw docs remain outside Git. Sanitized reports only; documentation checks, not an execution qualification.
