# H016 Worker1 phase4 — R5 survived; still loading

Actual read: **2026-09-27T12:43:48.842079+00:00**. Exact unit invocation `4600b556d5d04305a9157da80149a511`, supervisor **2779569**, native **2782009**, and container `c724b72b99f57f9e72b21bbc2a1fc104a9109b970657d5694ba05c25160a8308` match phase3. Unit is active/running; native StartedAt remains `2026-09-27T12:37:37.213589148Z`. This is post-phase3-session survival evidence, not a readiness claim.

Owner status is **LOADING**. Native log shows `load_model` and unused MTP tensor notices; it has not emitted a completed tensor buffer name or server-ready line. No NATIVE-IDENTITY, count9461, text/tool, warm4K, or BENCH4096 receipt exists at this observation. No new request was submitted.

At guard sample `2026-09-27T12:43:48.507890+00:00`, age **0.334 s**:

| Counter | Bytes | GiB |
|---|---:|---:|
| Candidate cgroup current | 556842057728 | 518.60 |
| Anonymous allocation | 308717449216 | 287.52 |
| File/cache allocation | 247207936000 | 230.23 |
| Shmem (included in file) | 8392704 | 0.00782 |
| Host MemAvailable | 607202992128 | 565.50 |

Frontier GPU: **39,282 MiB used / 57,969 MiB free, 35 C**. All four GPU reserve/temperature checks and host15% reserve pass at this sample; candidate swap/OOM/oom_kill are zero. Mandatory guard source is unchanged: `2c0e7483845530cf9b669d699c67b574e0f4a8cbba21dd6c511bc7ddf7f817aa`. Limit remains **704 GiB**.

Meaningful load progress: anonymous allocation grew from **13971447808 B** at `2026-09-27T12:37:53.392877+00:00` to **308717449216 B** now, while shmem stayed **8,392,704 B** and cgroup major faults stayed **16**. Current exact cgroup I/O reports **293,565,526,016 read bytes on 8:32**, plus **1,064,960 on 8:16**. This supports ongoing ordinary anonymous allocation/load progress; it does not yet prove the completed approximately495GiB CPU buffer, process RSS, native readiness or generation. File-cache reclaim is visible (pgscan **11320128**); no claim of zero reclaim.

Cgroup effective affinity is `0-7,16-71`, memory nodes `0-7`. The actual cgroup node-byte distribution is retained in STATUS.json and is uneven during loading. It is neither final process page placement nor thread-affinity evidence. No process status/maps/smaps/task probe was run during loading.

**Exit now rather than wait for loading.** The existing independent job owns qualification, discarded4K, and measured4096/256. Approximately12:57:37 load deadline; admissions close13:25; unadopted owner settles13:40; overall hard end13:48:08. Root must review the first4K result/projection before any16K/64K. No settlement was needed at this healthy snapshot. GLM remains suppressed under the same MiMo owner; Sova quiet state is inherited, not re-probed here. No source/deployment/build/download/parameter/hardware/node changes or GitHub push.

Reporting gap for root: existing telemetry records major faults/CPU, but the request collector does not capture exact per-request read-I/O boundaries. This loading I/O observation must not be relabeled as first4K before/after. RSS breakdown and post-load NUMA evidence remain pending. Any instrumentation source change requires root review.

Private full observation: task `private/phase4/snapshot-01.json`, SHA256 `80d249f17789fdb7bcce6d5284eab73febdc77b3ee4eee4f87d34aa244f62e1f`. Public machine evidence: STATUS.json. Wrapper started12:42:34; deadline13:07:34.038353UTC; session `01a0e2e3-7af6-7963-bf7e-2f3c6df30dc4`.
