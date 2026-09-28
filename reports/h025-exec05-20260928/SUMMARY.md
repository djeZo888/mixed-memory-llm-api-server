# H025 EXEC05 corrected campaign — failed, settled and restored

**Software campaign FAIL. A full300-second admission window was measured; GLM did not complete within its full900-second budget. All accepted producers were genuinely settled and all four models are now ready.**

Same native session01a0e9a5-f9b1-7b73-af31-d1c67a412b9d, under root's explicit corrected-source GO and21:00 deadline. Exact reviewed W1 source2ecd1704/package01ed8314;25focusedPASS supplied by W1. New namespace/unit only; original EXEC04 failure retained. UnitRestart=no, one launch20:36:35, barrier20:36:36.032424, admission ends20:41:36.032424. No inference retry or later campaign.

## Results and limits

| Lane | Full HTTP completions | Outcome |
|---|---:|---|
| Qwen0 |162|One additional counted but unsent row failed at the cutoff; owner physically stopped.|
| Qwen1 |124|All submitted requests settled.|
| Ada image |6|All FullHD requests settled.|
| GLM Flash |0|16268 native input tokens; HTTP200,0responsebytes, noDONE/usage/EOF; timeout900.150458s.|

The driver marked the last Qwen0 row failed84ms after the300s deadline. Its durable record has no send-start/body-sent timestamp. This is consistent with the pre-send cutoff path; original Refusal text was not retained. The failed row was not rewritten. GLM's timeout produced a physical stop followed by LeaseBusy bookkeeping; the existing owner halt genuinely reconciled20:52:38 while its original UNKNOWN record remained intact. No synthetic driver FINAL was fabricated. The exact client and bridge stopped only after producer settlement; no healthy accepted request was killed merely because admission ended.

- 223 samples fall inside the exact300-second window. Submitted HTTP in-flight four-way intersection:167.139683s, including the unfinished GLM transport until timeout. Successful full-EOF four-way intersection:0s. This is not proof of full GPU load or successful four-model qualification.
- Longest in-flight gaps during admission: GLM0.577832s; Qwen02.166797s; Qwen12.051312s; image2.160498s. Full interval detail is private and hashed.
- Total monitoring including drain:1000.953933s/787samples. Admission all-four nonzero GPU-utilization samples:140; these are sampled utilization, not native processing intervals.
- Admission peaks: Qwen072°C, GLM41°C, Qwen175°C, Ada71°C. No85°C stop. Owned cgroup swap/OOM peaks zero; telemetry, RAM/CPU/swap ranges and fan transitions are in METRICS.json. No corrected mirror monitor failure was recorded.
- CHA3 naturally changed40→80 with matching readback and rawtach3600→5040 (maximum5160), then returned40 during cooling. SourceTTL15s/mirrorTTL5s unchanged. Integrated target/actual transitions are retained; raw external tach units remain unknown. No W2 fan/BMC/power writes.

## Power evidence

Three Blackwell board power during admission averaged843.7424W and same-sample peaked1172.43W across223samples (mean interval1.346658s). Per-card mean/peak W: Qwen0357.9009/511.29; GLM87.9509/109.59; Qwen1397.8905/619.79. Existing Ada is on a separate PSU and excluded. These are board readings, not wall/PSU draw. No thermal or power-brake flag was sampled; Qwen0 software-power-cap flag was active84samples.

With assumed CPU400W+other200W+addedAda300W, sampled peak arithmetic leaves127.57W against2200W; configured three600W limits instead total2700W including those loads. The read-only supported ranges are150–600W for each workstation card and300–600W for the server card; all current/default/enforced limits remain600W.500W is within the reported ranges but was not applied. Three500W+CPU200W+other200W+addedAda300W totals2200W; CPU250W totals2250W. This arithmetic does not qualify PSU transient, wiring or sustained simultaneous-load capacity.

## Restore and preservation

Qwen0 normal manager restore completed20:54:23 (generation41); GLM existing owner resumed20:55:14. Qwen1 and image were retained. Final exact identities/capacities and all-four readiness PASS at2026-09-28T20:58:11.595159+00:00; image is idle/admitting. App/status public health both200, searchPID1655 retained, controllerPID72409 healthy. Both Qwen480K and GLM1048576 configured capacities unchanged; no large-context test. Permanent MiMo generation12 remains selected; no MiMo call/restart.

All51native session bindings and session/message/file/run/gateway/image counts are preserved; holds0 and historical quarantines3 remain. Normal restart appended six events; no manual historical row edits. Original EXEC04 and EXEC05 unknown/failure evidence remains private outside Git. Source, compact reports and full-history bundle are supplied; no further paid CLI or campaign is required by this checkpoint.
