# H026 — quick Qwen 600/550/500 W comparison

User authorizes temporary 550 W and 500 W caps with a short benchmark. Two Qwen
Blackwells exist; asynchronous scope clarification was offered. After the reply interval, root
stated the default: both cards, measured sequentially; later user steering wins. Orchestrator plans and
reviews. W1 executes on ai-vm through a fresh bounded native CLI; W2 independently
reviews the small method/source in parallel without live changes.

Window: September 28, 2026, 21:03–21:30 UTC. Stop new measurements by21:23 and
reserve cleanup/report time. No automatic extension or new model/runtime work.
Base source776a135a319291d1228f21772b6946daa2423ac1. H025 has fully settled;
all4 native services reported ready20:58:11 and final native exited0 at20:59:33.
Permanent MiMo selection remains unchanged and MiMo absent. GLM is resident but
its16K request timed out in H025; do not use it for this test.

## Short method

Reuse an existing Qwen streaming benchmark helper/fixture where practical. Do
not reuse H025's multi-lane deadline/owner state machine for this sequential test.
Do not create a framework or repeat GPU transfer/context capacity benchmarking.

Keep exact current Qwen weights/runtime,480K configured context, cache precision,
GPU UUID assignment and fan policy. No competing inference during a measured
request. Retain other models loaded; ordinary temporary upper-service quieting
is authorized if needed, preserving history and in-flight ownership.

For each selected GPU, execute sequentially:
- Read original configured/enforced limit and exact identity.
- One representative warm-up at600W, discard timing.
- One measured request each at600,550,500, then repeat600 as drift anchor.
- Target about64K native input tokens and512 output tokens; use an identical
  fixture with fresh leading nonce, reasoning disabled, same output cap/settings.
  The task should naturally fill the output budget. Record actual input/output;
  never claim512 output if fewer were generated. No prefix-cache reuse inflation.
- Read back each applied cap; allow a short fixed settling interval without a
  new model load. Keep timeout180s per request and bounded telemetry.
- Use native prompt/decode timing if the existing interface provides it. If not,
  report input_tokens/TTFT explicitly as an end-to-end prefill proxy; report
  output tokens per measured stream interval with its limitations. Distinguish
  HTTP completion from settled native work.
- Capture same-request GPU power, temperature, utilization, clocks and throttle
  flags (~1s sampling); do not infer electrical transients or PSU certification.
- Report percent changes versus600W and anchor drift. No extra sweep; if noise
  obscures small differences, report uncertainty rather than open-ended retries.

Retain85C/fan/telemetry guards. Abort new admissions on failure; safely settle
accepted work through the known owner. Never replay an uncertain request or kill
unrelated models. Restore each original600W limit in cleanup, verify readback and
native readiness, leave models resident and restore any upper services. No
persistent boot cap policy is implied by this benchmark request.

Exact targets:
- Qwen0 motherboard: GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237, port30002.
- Qwen1 server: GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528, port30004.
- Frontier GPU-69acfa26-8b60-61b5-702d-aee252c163cc and Ada remain unchanged.

Deliver compact source/settings/results, speed/power table and recommendation;
credentials/bulky raw traces remain private. Keep original failures and raw
measurement receipts. Publish reviewed results to feature/glm53-flash/PR10.
