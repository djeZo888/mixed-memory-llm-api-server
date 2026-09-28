# H025 — fan hysteresis and four-model overlap

Authorized September 28, 2026. Root coordinates/reviews/publishes; both Macs run
fresh bounded native CLI sessions in isolated copies. Overall execution window
18:50–20:20 UTC (90 minutes), with final 15 minutes for settlement and reporting.
Keep this focused: no Codex work, MiMo repair, large-context test or runtime update.

## Policies

- Integrated fans: 100% at GPU >=70 C; return to normal firmware control at <=65 C.
  Retain the existing short stable-cool interval if already deployed. Validate
  actual setters/readback by UUID; the added fixed auxiliary fan is user hardware.
- External server Blackwell GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528 controls only
  BMC Zone4/CHA_FAN3. Normal low duty 40%; high duty 80% at >=70 C; lower only
  at <=65 C. Hold prior state in between. Preserve the user-disabled CPU source.
- No conflicting fan writers, oscillation or repeated writes without a transition.
  Use protected BMC credentials, bounded telemetry freshness and channel readback.
  On lost telemetry/controller failure keep high cooling and expose the failure;
  retain the independent 85 C workload stop. Verify host-service restart behavior.

## Worker allocation

Worker1 owns integrated-fan verification and a small persistent CHA_FAN3 controller
on ai-harness, using existing authenticated ai-vm GPU telemetry and the verified
BMC API. Reuse existing source/pin/channel evidence. Focused hysteresis/error tests,
idle setter/tach verification, then deployment after source review. Do not touch
other fan zones, source bits, model placement, drivers or power limits.

Worker2 owns retained GLM 5.3 Flash readiness/recovery for this test, bounded
four-way driver repair and independent controller review. The user explicitly
allows GLM instead of unavailable MiMo. Preserve MiMo weights/config/failures;
do not alter Sova's permanent frontier-selection policy. Load retained GLM on
the free fast Blackwell only after exact MiMo native absence is established.
Do not repeat model tuning or rebuild/download. Both Qwens remain 480K and image
remains the existing Full HD profile on Ada.

## Acceptance

1. Reuse passing integrated fan behavior; establish live current source/settings.
2. Test the 70/65 state transitions with controlled telemetry fixtures and actual
   bounded actuator readback while idle. Label simulated temperature as simulated.
3. Fix H023's growing STATUS.json: keep compact current status, append bounded
   request/telemetry history separately. Monitoring failure stops admissions and
   settles/halts accepted work through its owner. No monitoring gaps called PASS.
4. Once fan control and four native services are ready, run a single five-minute
   overlapping ordinary workload: GLM around 16K input, both Qwen lanes with
   bounded contexts/output, and repeated Full HD images. Warm up modestly first.
   Small configured contexts need not replace retained profiles; actual prompts
   stay bounded. No 950K/1M prompt.
5. Record per-GPU min/max temperatures, fan command/readback, utilization, power,
   memory, CPU pressure, RAM/swap and request completions. Compute actual four-way
   request overlap and same-sample power of the three Blackwells (Ada has own PSU).
   Distinguish sampled board power from wall/PSU total and sustained full load.
6. Stop on 85 C guard, fan failure, OOM/swap growth or monitoring failure. Do not
   reduce power limits or retry automatically. Preserve original evidence.

Native work must settle before the clients close. Keep healthy resident models
warm where feasible; accurately report which frontier is resident/selected.
Publish reviewed source/settings and compact results to existing draft PR10.

## Time control

First bounded sessions: at most 45 minutes, checkpoint by 19:35 UTC. One short
fresh execution session may finish the reviewed deployment/overlap by 20:05.
Close paid sessions promptly; do not spend the window observing unchanged state.
At 20:05 stop new tests and settle/report. No automatic extension or unrelated fixes.
