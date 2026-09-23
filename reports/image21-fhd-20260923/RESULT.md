# Full HD bounded change — candidate awaiting root review

Public maximum: **1920x1080 / 2073600 pixels**. Six opaque generation profiles:
1024x1024, 1024x576, 1216x704, 1472x832, 1760x992 and1920x1080.
Full HD runs the unchanged qualified native1920x1088 /2088960-pixel workload,
then removes exactly the bottom eight rows. No resize. Editing/transparency
remain unqualified; public1920x1088 and UHD are refused.

14 focused offline fixtures passed; see [result](focused-test-result.txt).
The [proposed manifest](qualification.json) changes only the largest profile and
adds exact fixed limits. Its Full HD evidence hash points to [crop evidence](crop-evidence.json),
which binds the exact protocol/fixture/result hashes to the immutable historical
native qualification receipt. Five smaller profiles and their evidence hashes
are unchanged. This is not live acceptance and does not claim a new memory benchmark.

Historical native1920x1088:53.3355s,44776.3125MiB sampled device peak,8.8801% free.
Original receipts and results remain unchanged. Model, runtimeimage, placement,
precision, steps40, CFG1, CPU RNG, offload and cache policy remain unchanged.

Activation waits for root review of exact candidate source/bundle. Planned:
guarded stopped-owner atomic protected source/config-manifest update with exact
previous bytes preserved; release canonical lease before normal API startup;
one normal reconciliation/warm; one seed42 Full HD Lake Bled generation via the
root-reviewed Worker2 example helper. No text service restart or extra image call.
Final deployment, PNG hash/dimensions, health and cleanup receipt are pending.
