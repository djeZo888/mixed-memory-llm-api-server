# R4 guard correction

R3 inherited an unbounded placement() read before telemetry persistence and reserve assertions. The last emitted sample was12:13:58; at12:17:15 its readerthread was in m_start and sampleage197seconds. Root approved a single r4 retry after settlement. This is a demonstrated monitoring responsiveness defect; unavailable placement is not evidence of a physical reserve/thermal failure.

R4 removes process status, NUMA maps, smaps and thread reads from the mandatory loop. GPUqueries timeout after2seconds; hostMemAvailable, GPUtemperature/reserves and cgroupmemory/swap/OOM checks remain authoritative and failclosed. The loop retains5second waits. Placement runs only after successful nativeidentity and at the postwarm idle boundary, in a diagnosticchild with3secondtimeout and atmost0.2secondreapwait. It reports UNAVAILABLE and exactchildPID/settled status on timeout; it cannot interrupt the guard or reclassify unavailable evidence as hardwarefailure. The guard skips a second signal if owner settlement is already in progress.

18 focused tests:17PASS/1historicalprivatefixtureSKIP. Tests exercise blockeddiagnostic exclusion, two successful guarditerations followed by lowerhardwaretemperaturecutoff, host/GPUreserve/swap/OOM/missingGPU failures, proc-read exclusion, settlement no-resignal, realchildtimeout and bounded unreapedchildhandling. Privateproduction17fixturetest passed. Syntax/whitespace/unchangednativeargv checks passed.

Source-only W2 files scripts/runtime/mimo and scripts/control/node* remain untouched. Frozen sourcehashes and namespace/deadline contract are COORDINATOR-W2-CONTRACT.json. No persistentadoption or livehandoff machinery deployed.
