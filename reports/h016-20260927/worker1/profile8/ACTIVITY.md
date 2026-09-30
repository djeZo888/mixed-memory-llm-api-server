Saved R6 activity evidence: both 128-token request windows were CPU active without swap, major-fault growth, or cgroup throttling.

BASELINE128: boundary 2026-09-27T14:10:24.008692+00:00 to 2026-09-27T14:12:43.548450+00:00 (139.539757 s); cgroup CPU 8144.296691 s, averaging 58.365 logical CPUs. Process major faults +0, minor faults +6911, read_bytes +0; swap 0, all memory-event deltas and throttling zero. Host available 356.781–357.112 GiB across 28 saved in-window telemetry samples (not exact boundary extrema).

PROFILE128: boundary 2026-09-27T14:12:44.110586+00:00 to 2026-09-27T14:14:57.948097+00:00 (133.837512 s); cgroup CPU 7883.779956 s, averaging 58.906 logical CPUs. Process major faults +0, minor faults +5491, read_bytes +0; swap 0, all memory-event deltas and throttling zero. Host available 356.727–356.930 GiB across 26 saved in-window telemetry samples (not exact boundary extrema).

PROFILE128 activity: 137 samples, nominal 1 s. dmon: 27 nominal 5 s samples, SM {'min': 0, 'mean': 2.888888888888889, 'max': 5}, memory utilization {'min': 0, 'mean': 2.4814814814814814, 'max': 5}; PCIe Rx {'min': 0, 'mean': 15.407407407407407, 'max': 32}, Tx {'min': 0, 'mean': 4.481481481481482, 'max': 7} in emitted MB/s. These are neither host DRAM nor GPU VRAM bandwidth. First dmon zero sample precedes request; discrete observations may miss bursts.

Idle snapshot: 76 TIDs; affinity groups {'0-7,16-71': 13, '16-23': 8, '24-31': 8, '32-39': 8, '40-47': 8, '48-55': 8, '56-63': 8, '64-71': 8, '0-7': 7}. Last-scheduled CPUs cover guest NUMA nodes [0, 1, 2, 3, 4, 5, 6, 7]. Thread CPU deltas span saved post-load state, tiny warmup and both requests through 14:17:44 idle snapshot; no per-request per-TID attribution is possible. Node masks are groups of CPUs, not one-thread/one-core pinning.

Saved post-load placement: 497.269 GiB resident across all eight nodes; {'interleave:0-7': 503}. This predates the requests; policy/residency cannot establish traffic balance or bandwidth.

PROFILE128 follows BASELINE128, so timing changes combine order/warming, request content differences and profiling overhead. CPU activity is not arithmetic-only time; spin/barrier samples must be separated by perf analysis.
