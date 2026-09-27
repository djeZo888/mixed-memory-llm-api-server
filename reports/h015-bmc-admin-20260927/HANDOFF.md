# H015 Administrator read-only access receipt

PASS at 2026-09-27T08:36:46.190961+00:00. One owned UI login, exactly four established fan GETs, owned logout; all six requests HTTP 200 and all six actual TLS sockets matched the approved DER SHA-256 pin. Prior Operator four GETs were HTTP 500. Administrator role change is user-reported; role metadata omitted. No retries, fan writes, account changes, optional Thermal request or other host checks.

Returned PWMName `Zone4(CHA_FAN3)` is array index 3 (fourth display item), PWMNum 3, PWMSrc 0. FanMode is 4. CurrentPWMdata (Temp,Duty) is [(20,100),(45,100),(65,100),(90,100),(100,100)]. GenericPWMdata is [(20,20),(45,40),(65,70),(70,100),(100,100)]. Raw source fields PWM4_1=1, PWM4_2=0, PWM4_3=0; PWM4_LastSource=0. All sanitized original mode/PWM/source/last_source values are preserved in RECEIPT.json. Source labels and mode meaning were not newly decoded. Screenshot CPU Package Temperature is not proof of GPU temperature binding or actual duty; returned configuration is not measured duty.

Reused unchanged reviewed protected ai-harness probe.py/ui_probe.py, matched to repository SHA-256 identities recorded in RECEIPT.json. Only in-process probe.DEADLINE changed from 1790486340 to 1790498378.78828, exactly task hard deadline minus 20 seconds. Actual requests ran from ai-harness to 10.156.100.40:443 via mac-worker2 SSH. Credential remained on ai-harness. No raw authentication/private vendor copies retained.

Native ID: 01a0e201-bb5c-7f51-a0c6-221125e42564. Source base: 511a2ed93d556147d200ddc6c97b4ced38868657. Wrapper start: 2026-09-27T08:35:58Z; hard deadline: 2026-09-27T08:39:58.788280+00:00. Probe start: 08:36:45.442361 UTC; finish: 08:36:46.190961 UTC; SSH/probe process exit 0. Wrapper records actual native exit after this session ends; no exit value fabricated here.

Write ability remains UNQUALIFIED. Root reviews receipt and writes final prose. Any future write requires current access/identity checks and separate write qualification/authorization; no Administrator-to-Operator change is part of this task. No further probe scheduled.

Parent-wrapper final receipt: native exited0 at08:37:50UTC,112 seconds after
start and within the four-minute bound. No worker process remains.

Root conclusion: for the selected HTTPS route, plan on retaining an authorized
Administrator credential in the dedicated host-side controller. This is ongoing
service access, not a permanently logged-in browser or credentials for LLMs.
The exact minimum permission for writes is untested; an alternative protocol
could permit a narrower role, but none has been qualified. Static firmware
curves can persist without an active controller, but this CPU-temperature
curve does not implement the requested NVIDIA GPU-temperature policy.
