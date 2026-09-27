# H013 — ECC-off four-model load comparison

**Result: thermal cutoff; sustained concurrency and PSU capacity remain
unqualified.** The independent test stopped when the server Blackwell running
Qwen1 reached 85 C, despite ECC being disabled and its external fans being set
to 100% by the user. Do not repeat sustained load before cooling is improved.

## Execution and recovery

The warm-up completed at 07:09:55 UTC: Flash 8,192 input / 128 output tokens;
both Qwens 4,096 / 16. The main barrier opened at 07:10:15.004478; all four
requests were submitted by 07:10:17.697167. Flash used configured context
1,048,576, both Qwens 480,000 and the image model the existing Full HD profile.
Main fixtures requested Flash 65,536 input / 768 output, each Qwen 262,144 /
128, and Full HD generation. The first four requests were interrupted before
completion; none produced a final native usage record. No main throughput or
correctness result is claimed.

The stop reason was `qwen1_thermal_limit` at 07:11:05.089532. Independent native
settlement verified the four exact owned containers stopped with zero/absent
PIDs and empty process groups at 07:11:30.339948. Main ended at 07:11:31.228139.
Service restoration is a separate normal-owner action, not a benchmark retry.

## Temperatures and cooling

Ranges cover the whole 77-sample record, including settlement after cutoff.

| Device / role | Minimum | Maximum |
|---|---:|---:|
| Workstation Blackwell — Qwen0 | 36 C | 82 C |
| Workstation Blackwell — GLM Flash | 40 C | 46 C |
| Ada — image service | 34 C | 70 C |
| Server Blackwell — Qwen1 | 36 C | 85 C |

Near cutoff, Qwen0 was 81 C with both fans reporting 100%, 2,881/2,877 RPM.
Flash was 44 C with fans at 30%, 1,201/1,200 RPM. Ada was 70 C: the controller
requested 100%, with measured speed still rising through 88% / 3,047 RPM.
External server-card fan speed/control was not independently measured during
this run; the user's 100% setting was retained. BMC control remains deferred.
Commanded fan speed is distinct from measured fan speed.

## Power and comparison limits

The largest common-sample three-Blackwell `power.draw` subtotal was **1,384.03 W**
at 07:10:59: Qwen0 601.04 W + Flash 91.95 W + server Qwen1 691.04 W. Each card
reported a 600 W configured limit; these are driver telemetry samples, not
independent electrical measurements or a claim of sustained power above that
limit. Ada reported 295.06 W on its separate PSU in that sample.

CPU, motherboard, drives, losses and wall/PSU power were not measured. The
thermal stop prevents a sustained full-load or 2,200 W PSU headroom conclusion.

The earlier ECC-on `fan03` fixture reached the server cutoff after 49.007 s;
this run did so after 50.086 s. Earlier maxima were Qwen0 85 C, server 85 C,
Ada 73 C and Flash 45 C; both runs completed zero main requests. Fan policy,
starting state, ambient conditions, reboot/cache/warm-up and Flash allocation
also differ. This does not isolate ECC's thermal effect. It does establish
that switching ECC off did not remove the server-card cooling limit.

## Evidence

Worker1 native launcher: `01a0e1af-af0d-74b2-be86-05f00c8035fe`; post-test
capture: `01a0e1b3-7ec8-7762-b133-555f2a792c11`. Driver package
`ff31aca7a201b29226a844c0047545f8fe79aa240b7ad915802dcf59c1bcebee`;
controller `6fecc33efa6d163b4d550571b8402adfad0fed9912970a57ee681cd451002472`.
Private immutable raw archive: 23,797,760 bytes, SHA256
`1fbd3514a36c952360606662bfcaf566b9b110796681637d3eb11745b49a39b4`.
Root reviewed the worker's structured cancellation, owner-settlement,
per-device fan/temperature and common-sample power receipt.

The original successful million-token GLM experiment is unchanged; see the
[separate measured result](../../docs/h013-status-20260927.md#measured-flash-1m-result).
