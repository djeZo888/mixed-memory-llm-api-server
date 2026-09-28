# H025 EXEC03 source checkpoint

Native session `01a0e99f-2487-7c13-88cb-01852523aa80`; first executor timestamp 2026-09-28T20:05:28Z; hard deadline 20:35 UTC; campaign start cutoff 20:10 UTC.

Clock-only source commit `9b09c5dcb2c5b831a54795ed167d6ead20749d7b` updates `contract.py` line 145: absolute admission ceiling 20:05 -> 20:15 UTC and absolute settlement ceiling 20:20 -> 20:35 UTC on 28 September 2026. Exactly two literals changed. The nine other driver package file hashes are unchanged. All guards and 300/390/900/60/1020 second bounds remain unchanged.

One focused offline clock-boundary fixture PASS: admission 20:15 / settlement 20:32 accepted; admission 20:15:01 and absolute settlement 20:35:01 refused. No broad test rerun and no model/guest test. The unchanged 1020 second relative settlement bound makes 20:32 the latest possible settlement at the 20:15 admission cap; 20:35 is only the outer session/absolute ceiling.

Live campaign at this source checkpoint: NOT_TESTED; new actual fan proof and exact reviewed root GO have not been delivered. No guest access/mutation, app pause, bridge, campaign namespace or model request. Historical EXEC02 failure and consumed H025-TEST01 namespace remain unchanged. Historical retained host/model state was not refreshed by this source-only checkpoint and is not represented as current readiness.

Root reports the user's physical mapping: CHA_FAN1 is a 120 mm auxiliary fan rated over 6000 rpm, cooling motherboard Blackwells GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237 (Qwen0) and GPU-69acfa26-8b60-61b5-702d-aee252c163cc (GLM). Mapping and rated speed are user-reported, not independently measured tach evidence. No W2 BMC probe/write or thermal-controller change.

Closed source-only at 2026-09-28T20:08:51.129253+00:00. Live campaign NOT_TESTED: actual new fan proof/exact root GO not received by completion of useful source preparation. No paid waiting, automatic retry or additional native session. This is a source-only closure, not evidence that W1 recovery failed. No current host health claim is made.
