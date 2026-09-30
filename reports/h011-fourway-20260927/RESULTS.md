# H011 corrected four-model load — THERMAL STOP / NOT QUALIFIED

Latest direct-authorized continuation: [attempt03 fan-adjusted repeat](attempt03/RESULTS.md)
also stopped thermally; all four services were recovered ready at 480K. This
document preserves attempt02 and its then-current authority/end state.

The requested roughly five-minute load did **not** complete. The single
corrected pass reached the Qwen1 Server Blackwell's85°C stop threshold after
about38s; the next sample reached86°C. All new submissions stopped and all
owned clients were canceled. No second recovery or test cycle was attempted.
This establishes a thermal limit in this observed workload, not a PSU failure.

## Recovery and exact execution

The [first attempt](attempt01/RESULTS.md) failed because the recorder tried
Docker logs on Ada's existing `none` logging driver. After client cancellation,
Flash's scheduler watchdog expired and its original container exited. Direct
user authorization then allowed one original-owner recovery and one correction.

On27September2026 UTC:

| Event | Timestamp / result |
|---|---|
| Original Flash stopped / GPU compute process absent verified | Before01:20:50; no halt needed |
| Installed original-owner resume |01:20:50.143–01:20:51.304|
| Actual native readiness |01:22:16.965|
| Native capacity/cache/CPU readback |480000 / FP8 E4M3 /64 workers,8 NUMA pools|
| Brief representative warmup |8192 native input,128 output; COMPLETE01:23:26.484|
| Warmup TTFT / classification |28.803s; output cap reached, not failed reasoning|
| All owned work settled / four services ready before correction |01:23:55.818|
| Corrected job |`h011-fourway02`, PID3609088, dispatched01:23:57.408|
| Complete idle telemetry preflight |01:23:59.277|
| Local barrier |01:24:00.597|
| Thermal trigger sample / client cancellation |01:24:38.605 /01:24:38.672|

The same Flash container ID was resumed; its StartedAt changed. It was not
recreated. Both Qwens and Ada retained their original IDs and StartedAt. The
installed owner, canonical lease and current registered-storage/root guards
were used. Runtime, weights, source,480K profiles, cache, CPU placement, ECC,
power limits and production watchdog were unchanged. No1M allocation/inference.

Every telemetry/log path executed once before the barrier. Ada Docker logging
was explicitly unavailable; its existing API-owner journal was read successfully
but exposed no native GPU phase. GPU/cgroup/kernel monitoring remained required.
The recovered baseline and exact execution/fixture SHA256 values are recorded
in EXECUTION-IDENTITY.json. The prepared correction had1Flash+12Qwen0+12Qwen1
fresh fixtures and≤8images; only one request per lane was actually submitted.

## Actual requests and compute evidence

| Lane | Submitted native-counted input / output cap | Client interval UTC | Native evidence |
|---|---|---|---|
| Flash |65536 /768|01:24:01.029–01:24:38.673|HTTP200, no output delta/usage, no prefill/decode phase record|
| Qwen0 |262144 /128|01:24:01.582–01:24:38.673|83 native prefill records,01:24:02.361–01:24:42.921|
| Qwen1 |262144 /128|01:24:00.779–01:24:38.673|85 native prefill records,01:24:01.536–01:24:41.478|
| Ada |Opaque1920x1080, n=1|01:24:01.282–01:24:38.673|GPU generation activity; owner later ready/idle; no response artifact received|

The exact intersection of all four client intervals is37.091s. The1s
left-sample estimator gives38.010s; these measurements are distinct. About
39.010s of sampled intervals had both Qwens and Ada≥50% GPU utilization plus
Flash≥16 busy guest-core equivalents, including post-cancellation work. Flash
GPU utilization was low, and busy CPU threads without native progress do not
prove advancing inference. There is no five-minute actual-compute acceptance
or GPU-kernel simultaneity claim. Qwen logs show real prefill progress after
client closure, so closure is explicitly not an atomic drain guarantee.

Inputs were counted natively and rendered before submission; the Qwen token-ID
hashes matched. None of these four requests yielded a completed native usage
record. Prepared input size is not a completed occupied-context qualification.
No completed output correctness, image dimensions/hash, or image visual
acceptance is claimed for this canceled pass. No request was replayed.

## Same-sample power and resources

The maximum three-Blackwell subtotal was **1313.07W** at
`2026-09-27T01:24:38.604658+00:00`. Ada, on the user-confirmed separate Core X
PSU, was **297.03W** in that sample. The all-four diagnostic sum was1610.10W.
Individual peak samples below are deliberately not summed.

| GPU | Separate sampled power peak W | W at three-Blackwell peak | Peak temperature C | Minimum free MiB |
|---|---:|---:|---:|---:|
| Flash Blackwell |111.12|92.53|46|65720|
| Qwen0 Blackwell |602.33|598.24|79|35610|
| Qwen1 Server Blackwell |622.30|622.30|86|35613|
| Ada, external PSU |299.54|297.03|73|4372|

The separately exposed `power.draw.instant` fields had a same-query
three-Blackwell maximum1371.83W at01:24:37.605UTC. This is still sampled device
telemetry, not transient electrical capture. Installed NVIDIA documentation says
`power.draw` is a1s average on these architectures and advertises±5W/card.
The query reads devices sequentially with small skew; fast peaks can be missed.
Reported board power can briefly differ from the600W configured limit. No power
limit was changed. All-four sums are diagnostic, not workstation-PSU load.

The driver collected63 samples at roughly1s intervals (the terminal snapshot
also counts its initial baseline). GPU reserves passed, including Ada's5%
floor. Minimum host available RAM was564.952GiB, above15%. All four cgroups had
zero owned swap and no OOM/limit-event increments; host swap-in/out deltas were
zero during this case. Cgroup current includes file cache, not exclusive RAM.
Qwen0 and Ada reported normal software power-cap activity. No sampled hardware
slowdown, hardware/software thermal slowdown or power-brake flags appeared;
the explicit85°C temperature policy nevertheless correctly stopped the case.
PCIe replay-counter query was unsupported. Kernel evidence and final native
settlement are recorded separately in FINAL-HANDBACK.json.

CPU package power, guest hwmon/powercap and BMC measurements were unavailable;
no host discovery, new packages or CPU-TDP substitution was performed. These
readings do not establish wall power,2200W PSU output/headroom or transient
capability. The five-minute PSU-related workload remains unqualified.

## Evidence and limits

Raw prompts, native logs, partial streams, telemetry, exact assembled jobs and
fixtures remain outside Git in the task evidence directory and registered VM
log directory. Hash manifests bind them. First-attempt records are preserved
under attempt01 and in the preceding commit. The first attempt is not merged
into corrected-case metrics.

Scoped fixture/safety assertions pass; the reused H010 stream tests passed in
the first session. The corrected full telemetry preflight passed live before
all clients, and the explicit thermal guard stopped live work. This is not an
end-to-end success claim. No new whole-project test campaign was run.

Manual runner: NOT_STAGED. No1M work occurred. Worker2/root retain Sova's paused
state; no Sova-running claim or all-four-ready handback is made unless supported
by the final receipt. There is no second recovery/test cycle in this continuation.

## Final terminal handback —01:30:09UTC

Flash again reached its unchanged300s scheduler watchdog at01:29:33.490,
received SIGQUIT at01:29:38.493, and exited at01:29:44.669. The same container
had PID0, ExitCode0, OOMKilled=false; no Flash GPU compute process remained.
There was no second owner halt/resume. The causal mechanism of the native
stall after cancellation remains unestablished; it is not assigned to the PSU.

All owned work is now terminal by native container exit, **not** successful
request completion. Both Qwens and Ada remain in their original ready containers.
Qwen1 cooled to39°C; Qwen0 was40°C and Ada39°C. Canonical hardware-latch targets
were empty, all hardware_latched flags false; no latch was cleared. Qwen1 was
API-available after cooling, but root explicitly prohibits further Server
inference in this round. Flash was canonical unavailable/native connection
refused. Kernel logs record the built-in watchdog py-spy attachment attempts;
no Xid, PCIe failure or OOM was observed. No all-four-ready/Sova-running claim.

Root requested immediate closure and a fresh direct recovery-only session.
The1M gate is NOT PASSED; no1M or additional stress work occurs here.
