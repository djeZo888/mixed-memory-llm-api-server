# H010 bounded qualification driver

Task-only adaptation of the H009 qualifier. This is the exact source for one
8,192-token warmup and one fresh65,536-token input request, high reasoning and
clear_thinking, at the unchanged480000 native context and actual FP8 pool.
Warm output is128; measured output is256 including reasoning. This dated driver
must not be replayed as a general benchmark or used to retry the experiment.

`dispatch.py` assembles the pinned `vm-common.py`, fixture source, exact installed
identities and `qualify-body.py`. It requires the task-side actual Worker2 quiet
receipt and explicit root lane handoff. It creates a durable owner record before
launching the independently bounded `h010-flash64k-qualification` systemd unit.
The model is never started, reloaded, stopped or reconfigured by this driver.

The request reader only timestamps, parses and appends to bounded memory. It
performs no filesystem writes, storage guards, lifecycle acquisition or fsync in
the SSE loop. A separate5s sampler records GPU/process/cgroup/host/NUMA data and
native logs; a separate15s writer batches guarded anchored writes under short
canonical lifecycle leases. Boundary ownership and terminal records are durable.
The bounded buffers can lose up to the checkpoint interval plus guard latency
on abrupt process death. A clean CLI handoff leaves the systemd job alive.

Raw batches are bounded128MiB total and8192events per named buffer; telemetry is
also capped1600samples. Read lines are bounded1MiB and post-DONE tail8MiB. Native
logs are bounded150lines per5s poll and retain timestamped windows. Small logging
gaps and GPU peaks between samples cannot be excluded. Bucket names mark the
sampler's current mode; classify native logs by their actual timestamps because
a boundary poll can contain the preceding request's last lines.

Warm cap1200s, measured cap4200s, request absolute end2026-09-27T00:58Z; the systemd
job absolute end01:02Z allows bounded cleanup before worker closure01:06Z. Socket
closure is not atomic native-drain evidence; a canceled request needs separate
bounded settlement observations. No automatic retry exists.

Offline checks:

```
python3 reports/h010-flash64k-20260927/driver/fixture_native.py --self-test
python3 reports/h010-flash64k-20260927/driver/test_stream.py
```

The fixture self-test uses a character tokenizer only. Each actual request is
counted again by the pinned native tokenizer, including template/generation
prefix, and must exactly match the frozen /v1/tokenize response before inference.
Fixtures use distinct seeds and varied synthetic records across20technical
subjects. Exact rendered token spans/hashes and expected codes/arithmetic are
saved in the task receipt. Full payloads/raw output remain task-side.

A capped answer is UNPROVEN_OUTPUT_CAP even if its visible JSON looks complete.
Client TTFT and incremental-usage rate include transport/reader overhead. Native
scheduler windows are separate; neither short windows nor capacity estimates
establish full-request native speed or broad reasoning quality.
