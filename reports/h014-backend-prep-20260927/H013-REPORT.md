H013 event captured; full raw archive retained off VM in private/H013-RAW.tar (23,797,760 bytes; SHA256 1fbd3514a36c952360606662bfcaf566b9b110796681637d3eb11745b49a39b4). ROOT-NOTICE.json carries detailed samples and exact owner settlement.

Main cancellation 07:11:05.089532 UTC: qwen1_thermal_limit, conservative threshold 85C. Zero completed main requests: all four partial/error after cancellation; no main quality/performance PASS. Warm02 completed separately. Main native helper SETTLED 07:11:30.339948, all four exact container PIDs zero/absent and cgroups empty; main ended 07:11:31.228139. No retry.

Whole-record temperatures: Qwen0 36–82C; Flash 40–46C; Ada 34–70C; Qwen1 Server 36–85C. Nearest cutoff sample 07:11:05.008895: Qwen0 81C, two fans reported100%,2881/2877RPM; Flash44C,30%,1201/1200RPM; Ada70C, intended100% but reported88%,3047RPM; Server85C, external user100% but RPM/unmapped control unverified. Fan command/target is not measured speed.

Same-sample three-Blackwell power.draw peak1384.03W at07:10:59.008410: Qwen0601.04W + Flash91.95W + Server691.04W; each reported limit600W. Ada separately295.06W/300W limit. At cutoff Blackwells1258.54W and Ada297.90W. Board telemetry does not measure PSU/wall power or prove PSU headroom.

Compared with preserved ECC-on fan03: server cutoff49.007s after barrier versus this run50.086s; old extrema Qwen085C/Server85C/Ada73C/Flash45C, this82/85/70/46C. Old same-sample BW peak1335.53W versus1384.03W here. Both runs zero completed main requests. Different cooling, starting/ambient state, reboot/cache/warmup and 1M allocation confound ECC-only attribution. No ECC-only effect or sustained-load qualification established.

Normal restoration is now separately authorized by root; exact source/desired state/hardware admission checks precede existing owner resume. No latch clearing. H014 download/build remains separately authorized after exact settlement. Original session hard deadline07:35:32UTC; checkpoint07:56UTC unchanged.
