# Proposal only: later ncu 2025.3.1 launch/attach A/B reload

**Not for existing R6. No execution approval.** Parent explicitly requested this
addition at continuation. Root/W1 would own any later reload, request and recovery.
The command forms below follow the retained
[2025.3.1 CLI manual](https://archive.docs.nvidia.com/nsight-compute/2025.3.1/NsightComputeCli/index.html).
Angle-bracket fields are deliberately unresolved; these are not runnable commands.

Reuse the complete existing Nsight Compute tool tree/injection libraries from image
`sha256:a85c9f5af049f0ab679c1669ae6fa8393022886739af7361e85bb96878e8cdd4`,
which exposes `/usr/local/cuda/bin/ncu` 2025.3.1.0 build 36398880 and
`/opt/nvidia/nsight-compute/2025.3.1/`. A lone copied ncu launcher is insufficient.
No installation, rebuild or download is proposed. Read-only reuse/mount layout,
symlink targets, ABI/dependencies, writable tool-state location, injection into the
existing runtime and loopback-only helper binding remain **UNKNOWN**. Do not mount
the tool image's whole CUDA tree over the inference runtime or guess Docker mounts.

Exact requested metric candidates:

| Name to query/request | Intended meaning / unit |
|---|---|
| `dram__bytes_read.sum` | Per-profiled-kernel device-memory read bytes, B |
| `dram__bytes_write.sum` | Per-profiled-kernel device-memory write bytes, B |
| `gpu__time_duration.sum` | Profiled kernel duration, time; normalize reported unit to seconds |

The pinned guide describes device-memory bytes/throughput and the pinned release
notes name the duration metric. **The retained receipt did not query either byte
metric on GB202. Their exact availability, units, simultaneous pass count and
attribution must be verified before these candidate names can be accepted.**
Do not substitute throughput percent or silently expand to a full metric set.
A future review could request documented offline chip enumeration (not run here):

```text
<retained-ncu-2025.3.1> --config-file off --query-metrics --chips gb202 --query-metrics-mode suffix --metrics dram__bytes_read,dram__bytes_write,gpu__time_duration
```

Chip enumeration would still not prove live counter availability or permission.
A negative result stops this proposal; no guessed alternate metric.

Two-stage command shape after mounting/permissions/lifecycle and phase selection
are reviewed; launcher is the actual llama executable, with its approved unchanged
arguments/environment, not a shell wrapper:

```text
<retained-ncu-2025.3.1> --config-file off --mode launch --port <reviewed-loopback-port> --max-connections 1 <approved-llama-executable> <approved-arguments>

<retained-ncu-2025.3.1> --config-file off --mode attach --hostname 127.0.0.1 --port <same-port> --max-connections 1 --devices <verified-target-local-index> --metrics dram__bytes_read.sum,dram__bytes_write.sum,gpu__time_duration.sum --launch-skip <reviewed-decode-kernel-offset> --launch-count 3 --kill no --replay-mode kernel --cache-control none --clock-control none --export <registered-protected-log-dir>/h016-ab-three-kernels.ncu-rep --page raw --csv --print-units base
```

Launch mode injects and suspends at the first intercepted CUDA API until attach;
this is a new instrumented process and later model reload. Attach continues that
prepared target; it cannot attach to the existing uninstrumented process. The
selected index must map only to UUID `GPU-69acfa26-8b60-61b5-702d-aee252c163cc`
in the collector's actual namespace. The helper's listen address is not proven by
`--hostname 127.0.0.1`; verify loopback binding separately before any launch.

The offset is intentionally not guessed: initial kernels can be loading/warmup or
prefill. A reviewed phase boundary/offset is required to call these decode samples.
Count 3 limits profiled kernel launches, not replay passes or wall time. Root must
separately bound the profiling window to at most 20–30 seconds and approve managed
collector completion/cleanup; `--kill no` does not prove immediate detach or a
bounded CLI lifetime. No timeout/kill recipe is presumed safe here.

Perturbations are explicit: default ncu kernel serialization remains; kernel replay
may repeat each selected launch and save/restore its memory if counters require
multiple passes. Reject a multi-pass result if the later experiment forbids replay.
`--cache-control none` requests no profiler cache flush and `--clock-control none`
requests no GPC/memory clock changes, but neither removes serialization, injection,
profiling overhead, thermal/DVFS effects or replay-induced cache changes. The pinned
CLI also defaults `--pipeline-boost-state` to `stable`; its effect/current baseline
must be reviewed, not assumed inert. No nonperturbing ncu promise is made.

This measures **three profiled kernels**, not systemwide DRAM bandwidth, all decode
kernels, copies, other GPU contexts or idle gaps. For each accepted kernel compute
read/write B/s from the observed byte counts divided by that kernel's duration
(after unit normalization), then /1e9 for decimal GB/s. Do not equate this with
whole-request wall-time bandwidth or infer full-device coverage. Preserve the
reported pass count, kernel identity, units and ncu report; compare an unprofiled A
run to instrumented B with matching workload/state, while labeling the perturbation.
Counter privileges and conflicts must be resolved without lowering perf permissions
or stopping mandatory guards. All artifact paths require current registered-storage
approval and guards. Nothing above was launched, mounted or tested.
