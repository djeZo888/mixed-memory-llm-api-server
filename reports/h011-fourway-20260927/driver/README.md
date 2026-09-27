# H011 task driver and correction candidate

One systemd-owned driver coordinates four serial lanes with a local barrier.
Existing services remain at480000; no model load/reload, runtime, weight, cache,
placement, ECC, power-limit or CPU-pool changes are performed.

The initial executed case submitted exactly one request to each lane. Five
seconds after the barrier, the monitor failed because Ada uses Docker logging
`none`; it canceled the clients. Flash native work did not settle with socket
closure. Initial source is preserved as `attempt01-job-body.py`; raw assembled
source and fixtures remain in the task-side hash manifest. The corrected source probes Docker log capability before starting clients and explicitly
records unavailable Ada native phase logs. It was executed once after directly authorized original-owner recovery and a
completed8192-token warmup; the corrected pass stopped on Qwen1 reaching85C.
Flash subsequently hit its native watchdog again. No replay or second recovery
is permitted by this dated task.

The corrected candidate prepares one fresh65536-token Flash request (high
reasoning, clear_thinking,768output), twelve fresh262144-token fixtures per Qwen
(128output each), and at most eight opaque1920x1080 images. Submissions end at
300s; request cap900s; systemd cap1200s. No uncertain request is retried. Native
rendered tokens and Qwen token IDs are checked before inference; completed
native stream counts are checked again. Capped output is not failed reasoning.

The SSE path only timestamps, parses and buffers in memory. Separate threads
sample all GPUs in one query about every1s, collect native logs every5s, and
checkpoint bounded buffers every10s. Durable ownership precedes each request.
Current registered-storage/root guards and canonical lifecycle leases are used
at boundaries and batch checkpoints, never across inference or per token.
Safety checks enforce7% Flash free,16GiB Qwen free,5% Ada free,15% host available,
no owned swap/OOM, and below85C or a lower reported slowdown threshold. Five
consecutive swap-I/O intervals stop work; historical occupancy alone does not.
Software power-cap throttling is recorded without being classified as failure;
thermal or power-brake flags stop owned work.

Installed NVIDIA query documentation says `power.draw` is a one-second average
on these architectures, with advertised accuracy +/-5W/card. Same-query sensor
reads are not perfectly simultaneous electrical measurements. The three
Blackwells belong to the workstation; user-confirmed Ada uses a separate Core X
PSU. No wall power, PSU-output/transient validation or inferred CPU-TDP power.
CPU/package, hwmon and BMC devices were not exposed in the guest.

Checks:

```
python3 reports/h011-fourway-20260927/driver/test_fixture_safety.py
python3 reports/h010-flash64k-20260927/driver/test_stream.py
```

`analyze.py` reads saved evidence only. It reports same-sample sums and labeled
client/GPU/CPU activity proxies, never GPU-kernel simultaneity. Raw prompts,
streams, telemetry, exact jobs and any images stay outside Git. This candidate
is task-specific and is not a general replay/benchmark command.
