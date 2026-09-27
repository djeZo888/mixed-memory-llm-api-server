# R8 actual unprofiled result

R8 same83-input/128-output ADC payload, seed270927/thinkingfalse/temp0, cached0, finishedlength, DONE/fullHTTPdrain/authenticatednativeidle. Native N−1 rate7.763077714t/s; first-to-last independentSSE7.763106698t/s. Nativeprefill2.140196s, TTFT2.456856745s, total18.816394168s. R7 comparableunprofiled5.88518568t/s → +31.909%; R7 profiled3.36397 is excluded. This is outputthroughput only, not qualityPASS.

Exact first output2026-09-27T15:26:59.000942UTC /35522.348658294monotonic; last15:27:15.360367UTC /35538.708088215monotonic. Native128count uses127 measureddecodeintervals/16.359491s; actualinput83 and output128. Payloadhash/rawreceipt hashes and native identity inR8-RESULT.json/private receipts. Root selected16threads in scopedROOT-WINNER after result notice.

Boundary19.119099651s:176.930125CPU seconds→9.2541averageCPU-coreequivalents (whole request+boundaries, not decodeworkerclassification). Minor faults+7338, majorfaults0, processreadbytes0, allcgroupIOcountersunchanged. No DRAM/VRAMGB/s counters; GPUutilization is a percentage, not bandwidth. Peak observedfrontiertemperature42C, minimumfree50771MiB/97887MiB, otherGPUs<=40C. Minimumhostavailable383629598720/946820976640bytes, ownedSwap0. Maximumsampledcgroup625591197696bytes includesfilecache; do not doublecount.

Postwarm28TIDs:13havefullallowed64CPU mask; node0restrictedmask has1TID; node1–7masks have2TIDseach. These are actual affinitymask observations, not activeworker labels. FullTIDs/masks and residentNUMA pages retained privately, compactmapping inR8-RESULT.json.

Normalstop15:32:36.979877UTC, nativeexit15:32:49.880568758, physicalsettlementPID0/cgroupempty/GPUempty15:32:50.090521, originalGLMready15:34:27.707968, independentexactgate+authenticatedreadiness15:35:16.320242. Unitfailed/exit-code normalSIGTERM artifact retained, OWNER SETTLED_GLM_RESTORED. No inference replay or third tuning/profiler.
