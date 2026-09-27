Retained R5 memory and counters (phase6 snapshot ending 2026-09-27T13:17:49.447621+00:00).

4K and 16K completed correctly. The retained 64K evidence is partial prefill only: 26,624 / 65,536 tokens at 13:17:27.290464Z. No terminal or 64K qualification is claimed.

| Interval | Samples | cgroup GiB min–max | anon / file / kernel GiB maximum | Host available min | Frontier used max / free min MiB | GPU max C | CPU cores in sampled interior |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4096 whole | 22 | 680.155–680.228 | 497.222 / 181.408 / 1.598 | 356.171 GiB (40.392%) | 46482 / 50769 | 43 | 54.798 |
| 4096 prefill to TTFT | 13 | 680.155–680.192 | 497.186 / 181.408 / 1.598 | 356.196 GiB (40.394%) | 46482 / 50769 | 43 | 52.330 |
| 4096 decode after TTFT | 9 | 680.228–680.228 | 497.222 / 181.408 / 1.598 | 356.171 GiB (40.392%) | 46482 / 50769 | 43 | 58.351 |
| 16384 whole | 65 | 679.969–680.235 | 497.229 / 181.408 / 1.598 | 356.105 GiB (40.384%) | 46482 / 50769 | 46 | 52.896 |
| 16384 prefill to TTFT | 53 | 680.161–680.198 | 497.192 / 181.408 / 1.598 | 356.243 GiB (40.400%) | 46482 / 50769 | 46 | 51.702 |
| 16384 decode after TTFT | 12 | 679.969–680.235 | 497.229 / 181.408 / 1.598 | 356.105 GiB (40.384%) | 46482 / 50769 | 43 | 58.415 |
| 65536_partial partial prefill | 90 | 679.932–679.932 | 497.192 / 181.142 / 1.598 | 356.058 GiB (40.379%) | 46482 / 50769 | 44 | 51.949 |

Lifetime cgroup memory.peak is 680.506729 GiB; it is not a 4K/16K/64K peak. shmem stays at 248.777 MiB and is included within file, not additional memory.

4096 boundary counters (2026-09-27T12:52:35.903194+00:00 to 2026-09-27T12:54:32.537745+00:00): 6067.543473 CPU seconds / 116.634551 wall seconds = 52.022 cores. Major faults +0; file refaults +0; direct scan/steal +0/+0; kswapd scan/steal +0/+0. Nearest periodic samples outside the request; coarse brackets include small adjacent intervals; not exact request-only counters. The discarded warmup had already released at 12:52:35.234035Z.

16384 boundary counters (2026-09-27T13:00:09.231342+00:00 to 2026-09-27T13:05:38.900685+00:00): 17388.883777 CPU seconds / 329.669343 wall seconds = 52.746 cores. Major faults +0; file refaults +0; direct scan/steal +0/+0; kswapd scan/steal +69696/+69696. Exact retained before/after request capture; includes 0.276615 seconds after response and pre-body admission interval.

16K exact IO deltas are zero for every retained block device and all byte/operation fields. Its 69,696 kswapd-reclaimed pages equal 272.25 MiB at 4 KiB/page, matching the clean file-cache reduction; no major-fault, file-refault, direct-reclaim or read-IO increase accompanies this. This does not by itself measure stalls. 4K IO is NOT_MEASURED at exact request boundaries.

Owned cgroup swap remains zero, process VmSwap is zero at the snapshot, all sampled memory events (including OOM/OOM-kill) are zero, and CPU throttled time does not increase. Host swap is separately nonzero and must not be described as zero. All sampled GPU temperatures stay below the 85 C cutoff; frontier free memory stays above 7%, and host available memory above 15%. Sampled prefill/decode extrema and CPU averages do not establish continuous peak or scheduler-level behavior.

The JSON retains exact byte ranges, per-GPU ranges, counter deltas and timestamp limits. No new inference, profiling, runtime changes or VM calls were performed for this analysis.
