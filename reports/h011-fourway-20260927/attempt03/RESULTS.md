# H011 fan-adjusted repeat — thermal stop; all services recovered

The authorized fan-adjusted repeat did **not** qualify the requested five-minute
concurrent workload. Qwen1 Server reached the unchanged 85°C cutoff after
49.007 seconds. Qwen0 also reached 85°C while cancellation settled. No further
load was submitted. All four native services were ready again by 01:44:35 UTC,
with no active owned request. Sova remains paused. No 1M work occurred; the user
requires cooling to be fixed before that test.

The physical Qwen1 fan adjustment is user-reported. Its `fan.speed` readback was
`[N/A]`; there is no measured fan RPM or controlled fan-effectiveness claim.
The previous recorder failure and corrected thermal stop remain separately
preserved in [attempt01](../attempt01/RESULTS.md) and [attempt02](../RESULTS.md).

## Recovery and execution — 27 September 2026 UTC

| Event | Actual observation |
|---|---|
| Prior Flash owner | Already stopped by its existing watchdog; no initial halt needed |
| Initial same-container resume | 01:34:35.799386–01:34:36.904438 |
| Native 480K ready | 01:36:06.622011 |
| Representative warmup | 8192 native input / 128 output, transport complete and SSE done; TTFT 152.377s |
| Warmup interpretation | Output ceiling reached in reasoning; not a reasoning failure or uncontended benchmark |
| Fresh native settlement readback | 01:40:53–01:40:57; all APIs ready, image idle, no established model sockets |
| Job | `h011-fourway03`, PID 3856248; dispatched 01:41:00.106702 |
| Complete idle telemetry preflight | 01:41:01.866228 |
| Local barrier | 01:41:02.180099 |
| Thermal trigger sample | Qwen1 85°C at 01:41:51.187347; Qwen0 then 82°C |
| Client cancellation | 01:41:51.260078 |
| Qwen0 later thermal sample | 85°C at 01:41:54.187627 |
| Task terminal | 01:42:15.443119; inactive/PID 0 |

One driver owned all four serial lanes. Fresh native-counted fixtures were
65536 Flash tokens and twelve 262144-token cases per Qwen; token-ID/rendered
parity was checked. Caps were one Flash request, twelve per Qwen, eight opaque
1920×1080 images, 768/128 text output tokens, 300s new submissions, 540s per
request and 900s per job. The shorter request/job caps reserved safe-end time
inside this continuation. Exactly one request per lane was submitted.

All optional logging paths were exercised before the barrier. Ada Docker
logging remained explicitly unavailable (`none`); its existing API journal,
GPU, kernel and cgroup collection succeeded. Required safety was unchanged.

## Actual work and overlap

| Lane | Client interval UTC | Native work evidence |
|---|---|---|
| Flash | 01:41:02.620008–01:41:51.261101 | HTTP 200; no prefill/decode log, output delta or completed usage |
| Qwen0 | 01:41:02.372627–01:41:51.261006 | 97 prefill records, 01:41:03.141854–01:41:55.809351 |
| Qwen1 | 01:41:02.873377–01:41:51.260614 | 95 prefill records, 01:41:03.712788–01:41:51.649712 |
| Ada | 01:41:03.171021–01:41:51.261547 | GPU generation activity; later native ready/idle; no returned image artifact |

The exact four-client interval intersection was **48.089593s**. The one-second
left-sample proxy was 49.008s; 48.008s had both Qwens and Ada at least 50% GPU
utilization with Flash using at least 16 guest-core equivalents. Flash GPU
utilization never reached 50%. Busy Flash CPU threads without native progress
do not establish advancing inference. Neither HTTP overlap nor nonzero GPU
utilization proves simultaneous kernels. Five-minute actual-compute overlap
was not achieved.

No four-way request completed. No response correctness, completed occupied
context, or successful image dimensions/hash is claimed. Native Qwen work
continued briefly after client closure; cancellation was not an atomic drain.
The final task status is `FAILED`: the thermal cancellation was first, then a
terminal identity/readiness read timed out. This secondary recorder timeout
does not replace the thermal cause. No uncertain request was replayed.

## Power, temperature and stability

The highest **same-sample three-Blackwell subtotal was 1335.53 W**, at
01:41:44.186740. Ada, powered by the separate user-confirmed Core X PSU, drew
294.27 W in that sample. The all-four diagnostic sum was 1629.80 W.

| GPU | Independent peak W | W at three-Blackwell peak | Observed min–max °C | Minimum free MiB |
|---|---:|---:|---:|---:|
| Flash Blackwell | 114.67 | 91.17 | 38–45 | 65720 |
| Qwen0 Blackwell | 603.00 | 599.08 | 35–85 | 35610 |
| Qwen1 Server Blackwell | 645.28 | 645.28 | 36–85 | 35613 |
| Ada, external PSU | 299.32 | 294.27 | 35–73 | 4372 |

The table covers the run telemetry window, not startup/recovery. Physical UUIDs:

| Lane | GPU UUID |
|---|---|
| Flash | `GPU-69acfa26-8b60-61b5-702d-aee252c163cc` |
| Qwen0 | `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237` |
| Qwen1 Server | `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528` |
| Ada | `GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23` |

Independent card peaks are not summed. The separate instantaneous field's
same-query three-Blackwell maximum was 1388.92 W at 01:41:39.186155. Installed
NVIDIA query documentation describes `power.draw` as a one-second average and
states ±5 W/card; sequential device reads introduce skew and can miss fast
peaks. These are GPU telemetry readings, not wall power, PSU output, headroom,
or transient validation for the 2200 W workstation PSU. CPU package power,
guest powercap/hwmon and BMC measurements were unavailable; no TDP substitution.

Qwen1 started at 36°C, rose to 85°C in about 49s, cooled to 56°C by the final
run sample, 39°C at the ready handback and 37°C at 01:46:02. Qwen0 reached
85°C after cancellation and cooled to 43°C at 01:46:02. At that final readback,
Flash was 42°C and Ada 40°C; every GPU reported 0% utilization. Qwen1 fan
readback remained unavailable; other cards exposed percentage, not RPM.

The raw series contains 74 approximately one-second samples, maximum gap
1.0032s; the receipt also counts its separate initial baseline. Minimum host
available memory was 564.832 GiB. Flash 7%, host 15%, Qwen 16 GiB and Ada 5%
reserves held. All owned cgroups had zero swap, no OOM/limit increments, and
host swap-in/out deltas were zero. Qwen0 and Ada showed normal software power
cap activity. No sampled hardware/thermal/power-brake slowdown flags appeared;
the explicit temperature cutoff still correctly stopped the job. PCIe replay
counter query was unsupported. No kernel Xid, PCIe failure or OOM was recorded
from recovery through final readiness; ECC error counts did not increase.

## Safe end and final identity

Flash remained native-uncertain after client cancellation. The directly
authorized installed original owner halted only Flash at
01:42:16.454422–01:42:51.583071. Its existing container exited at
01:42:51.366436 with exit 137, OOMKilled false, PID 0, and no Flash GPU compute
process. This was the targeted owner stop, not a watchdog/PSU failure.
Resume occurred at 01:42:51.636801–01:42:52.727281; actual readiness returned
at **01:44:30.252340**. The same full container ID was retained; StartedAt
changed, with no recreation. Other three containers and start times were
unchanged. No inference followed safe-end recovery.

Final native readback: all three text context/pools 480000; Flash FP8 E4M3,
64 CPU workers, eight NUMA pools and the existing guest CPU placement. All
three Blackwells retain ECC enabled, Ada disabled, and power limits remain
600/600/600/300 W. Twenty-one installed source/config hashes matched; current
registered-storage/root guards passed. Weights, runtime, cache and watchdog
were unchanged. Boot ID stayed `1c706f0b-7243-41a0-aea3-c447ef51664f`, with guest
uptime 16121s at final snapshot. No reboot/reset or latch clearing occurred.

Canonical hardware-latch targets were empty and all service hardware-latched
flags false. Text native ready/capacity, image ready/not-busy, no established
model sockets, idle GPU samples and Flash's explicit process release establish
the terminal handback; there is no native atomic active-counter claim. The
read-only final Sova **user unit** was loaded/enabled, inactive and PID 0.
Sova was not restored or claimed running.

Scoped fixture/safety assertions and source compilation passed during
preparation; native fixture parity and complete idle telemetry passed live.
The live guard stopped on 85°C. No broad test campaign or extra quality
benchmark was run. Compact source/results are committed; raw prompts, streams,
images (none returned for this run), telemetry and native logs remain taskside
with hash manifests. Manual 1M runner: **NOT_STAGED**; no 1M allocation/inference.
