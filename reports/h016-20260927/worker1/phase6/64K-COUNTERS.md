64K benchmark PASS at 2026-09-27T13:28:56.526621+00:00: 65,536 prompt / 45 completion tokens; all three codes, product 323 and safe ADC 4095 correct. Finish stop, DONE and full HTTP drain true; cache 0, thinking false.

Native prefill 1073.242495 s (61.063553 tokens/s); native decode 48.187979 s (0.913091 tokens/s). TTFT 1073.556601 s; total 1121.745314 s. Output budget was 256, actual output 45; no 65,536-output or full17 qualification.

| Phase | Samples | cgroup GiB min–max | anon / file / kernel GiB maxima | Host available minimum | Frontier used max / free min MiB | Frontier maximum C | Sampled interior CPU cores |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whole request | 221 | 679.932144–680.005554 | 497.265148 / 181.141891 / 1.598503 | 356.015972 GiB (40.374%) | 46482 / 50769 | 51 | 51.824432 |
| Prefill to TTFT | 212 | 679.932144–679.968842 | 497.228523 / 181.141891 / 1.598427 | 356.058289 GiB (40.379%) | 46482 / 50769 | 51 | 51.566001 |
| Decode after TTFT | 9 | 680.005543–680.005554 | 497.265148 / 181.141891 / 1.598503 | 356.015972 GiB (40.374%) | 46482 / 50769 | 45 | 58.179247 |

Exact boundary counters 2026-09-27T13:10:14.464680+00:00–2026-09-27T13:28:56.811750+00:00: 58145.658144 CPU seconds / 1122.347070 wall seconds = 51.807199 core equivalents. Major faults +0; file/anon refaults +0/+0; direct scan/steal +0/+0; kswapd scan/steal +0/+0; total page faults +19202. Every exact per-device read/write byte and operation delta is zero. No throttled CPU time increase.

Lifetime memory.peak is unchanged at 680.506729 GiB; this differs from the sampled rung maximum. shmem is 248.777344 MiB, already included in file. Sampled file dirty/writeback remain zero. Owned cgroup swap and snapshot process VmSwap are zero; memory events including OOM/OOM-kill remain zero. Host swap is separately nonzero.

All sampled GPU temperatures remain below 85 C. Frontier free memory remains above the 7% requirement and host MemAvailable above 15%. These are sampled extrema, not proof of continuous peaks; phase split uses observed TTFT with coarse periodic counters. The client PID is absent and its cgroup no longer exists in the terminal snapshot; this analysis does not alter or settle the independent native owner.

Earlier MEMORY-COUNTERS.json/.md remain unchanged as partial-snapshot evidence. No VM calls or new inference were performed.
