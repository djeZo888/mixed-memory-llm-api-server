# H009 Flash results — phase1 backend complete, lane released20:48UTC

The corrected core cases passed tool/answer semantics with actual480000 native context/pool and torch.float8_e4m3fn cache. The additional16K sample reached128 output tokens. **Two native40-token decode windows measured13.42 and13.51tokens/s**; full-request native average is unmeasured. Worker1 released the warm Flash lane to coordinator/Worker2 at20:48:06.

| Completed case | Native input/output | TTFT / client elapsed | Semantic result |
|---|---:|---:|---|
| AUTO weather |177/15|18.324 /53.367s|weather({"city":"Ljubljana"}), tool_calls|
| Forced weather |177/15|20.022 /54.975s|Same complete call, tool_calls|
| Discarded warm |4096/3|225.397 /229.481s|12, stop|
| Measured4K |4096/3|20.724 /24.771s|12, stop|
| Measured16K |16384/19|84.128 /104.536s|12, stop|
| Extra long-answer16K |16384/128|66.899 /204.731s|length; semantics unproven at cap|

All measured inputs match the exact native tokenizer/template including generation prefix. The original measured caps were64 but outputs naturally ended3/19; the separate128-cap sample reached128.4K decode is invalid/insufficient;16K is a short19-token sample. Native usage reports reasoning_tokens0, while16 reasoning deltas advanced completion1–16; no separate authoritative reasoning total is asserted. Extra128 similarly had59 nonempty reasoning deltas despite native reasoning_tokens0;59is not asserted as a native token count. API cache detail is null; native prefill receipts record cached0. First4K warm includes lazy context allocation and fallback/default kernel configuration; isolated compile time is unmeasured.

| Memory/temperature across360 samples from all six cases | Observed |
|---|---:|
| Flash GPU peak used / minimum free |32152 /65098MiB (66.50% free)|
| Maximum GPU temperature |53°C|
| Minimum host available |603415572480bytes (63.73%)|
| Cgroup sampled current peak / lifetime peak |628393144320 /640475009024bytes|
| Cgroup sampled anonymous / file peaks |314822549504 /312204632064bytes|
| Sum process RSS sampled peak |329710243840bytes; shared pages may double count|
| Owned cgroup swap maximum |0bytes|
| Host swap occupied range |48234496–49545216bytes|
| Maximum interval host swap-in / swap-out |79 /315pages|
| CPU temperature |NOT_AVAILABLE|

Reserves exceeded7% GPU and15% host throughout these observations. After warm: GPU32150MiB used, host604341211136bytes available, cgroup627830005760bytes, owned swap0. Existing host swap occupancy is retained rather than reported as zero.

All64 expert threads had positive CPU ticks in all six cases; pools each contain8 singleton guest masks covering0–7,16–71. Per-thread CPU seconds ranged25.04–49.15 AUTO,25.80–51.15 forced,150.54–220.18 warm,18.31–18.57 measured4K,82.81–83.39 measured16K. Mean busy guest CPU equivalents were33.04,32.93,50.08,39.41,48.80 respectively. Extra128 per-thread CPU time was73.00–73.41s;22.27 mean busy guest CPU equivalents includes the long client drain, not just native computation. This proves actual guest coverage, not100% utilization, host1:1 physical-core pinning, or physical RAM locality. [Complete compact CPU/page proof](evidence/CPU-UNDER-LOAD.json).

At20:47:29, all node services were fresh, available/ready/hardware-unlatched. At20:41:37, image FHD was rejected400 while health remained200; temporary maximum1760x992 persists until the final Ada ECC-off reboot restores capacity. All three Blackwells remain ECC enabled; Ada is currentEnabled/pendingDisabled. Second reboot, Worker2 acceptance and idle600/wake remain pending or NOT_TESTED. All three owned qualification units were inactive/MainPID0 with success at20:48:06, no established30010 connections were observed, and the model remained warm. Native active counter is unavailable; no atomic-drain claim.

Native rates use generated-token count divided by `perf_counter` elapsed, reset at each decode statistics log. Windows20:44:28.964689746→31.944514394 and31.944514394→34.905059551 each contain40 tokens, one running request/zero queued, with no intervening prefill. The earlier0.09 rate includes idle/prefill and is excluded. Rates include native scheduler/output dispatch, not only GPU kernels; client0.9497tokens/s includes synchronous receipt I/O and is not native speed. [Exact formula/source/window receipts](evidence/NATIVE-THROUGHPUT.json). No additional request is needed.

[Machine-readable results](RESULTS.json), [core receipts](evidence/FINAL-QUALIFICATION-SUMMARY.json), [raw31-file hash manifest](evidence/QUALIFICATION-RAW-MANIFEST.json), [source/bundle identity](evidence/SOURCE-CHECKPOINT-FINAL.json), [handoff](HANDOFF.md). Raw7.78MB SSE/telemetry remains task-owned outside the report; no large logs or wheel copied here.

The earlier boot monitor recorded brief host swap I/O at20:28:04–16 with Flash cgroup swap0. Canonical LeaseBusy prevented its attempted failure flush/halt; its RESOURCE_FAILURE label then stayed stale after healthy samples resumed. The monitor was retired and disabled once independent request telemetry covered the warm model. This monitoring limitation is preserved in [the receipt](evidence/LOAD-WATCH-LIMITATION.json), rather than represented as a current model failure or a successful protection action.
