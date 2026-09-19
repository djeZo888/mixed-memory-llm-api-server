# GLM repair: structured output passes; slow-decode cause unproved

Current G1 schema output measured **12.64 tokens/s**; the historical 0.45–1.49 tokens/s behavior was not reproduced. The unchanged schema-free warmup was also fast. The cause is not proven. Original Qwen production service is restored.

## Structured and unconstrained outcomes

G1 completed the exact accepted D schema request with only `model` changed from `glm-5.3` to `bench-glm-5.3`. Native recount preserved the schema and measured 3,546 input tokens; cache use was zero. The response stopped normally after 145 output tokens and matched all three historical retrieval values exactly: one JSON object, 99 final characters, no literal closing-think delimiter, and no output repair. The response schema requires only `START`, `MIDDLE` and `END` string fields, forbids additional properties, and contains no answer constants. Temperature 1.0, seed 1729, cap 256, messages and nonce were unchanged. There was one measured request and no retry or second seed.

| Phase | Input / output | Native prefill / decode | Client elapsed | Disposition |
|---|---:|---:|---:|---|
| Distinct discarded warmup | 2,390 / 32 | 36.866 / 2.989 s | 39.879 s | Full-batch proof, cached 0 |
| Schema request | 3,546 / 145 | 51.751 / 11.391 s | 63.222 s | Strict exact PASS, cached 0 |

Main native decode was 12.641 tokens/s using `(n - 1) / decode_seconds`; native prefill was 68.521 tokens/s. Configured capacity was 4,096; measured occupied context was 3,691 tokens. This establishes neither occupied 1M context nor unconstrained correctness. The earlier duplicate-JSON/literal-close defect remains unresolved, and temperature 1 is not a demonstrated fix. Historical strict `HARNESS_FAILURE` labels denoted invalid final-answer JSON, not necessarily transport failure.

Production D on both GPUs also passed this schema contract, with 3,546 input / 232 output tokens, 3,545 cached input tokens and native prefill/decode times of 0.244 / 18.266 seconds. Different cache use and output lengths prevent a direct input-speed or pure placement comparison. The original unconstrained case produced the same malformed 206-character final content on both GPU counts. Temperature 1 / seed 1729 was not a remedy. D greeting-only stream/nonstream checks passed; arithmetic-reasoning acceptance remains NOT_TESTED. A real `read_file` call with matching tool-result ID and semantic continuation passed; a full coding task was not tested.

## Using the tested native schema envelope

Set `response_format` in the ordinary chat-completions request as shown. Keep the task in `messages`; the schema constrains fields and types, not answer values. The verified fixture used explicit `reasoning_effort: "low"`, temperature 1.0, seed 1729, stream true and max_tokens 256. This is a tested contract for that fixture, not a universal sampling recommendation. Validate the returned JSON and task values; malformed or truncated responses must remain failures.

```json
{"response_format":{"type":"json_schema","json_schema":{
  "name":"retrieval","strict":true,"schema":{
    "type":"object","additionalProperties":false,
    "required":["START","MIDDLE","END"],
    "properties":{"START":{"type":"string"},
      "MIDDLE":{"type":"string"},"END":{"type":"string"}}
  }
}}}
```

## Unchanged G1 and observed performance

The original first-GPU-only N76/F16 profile passed its strict native allocation gate after a 147.941-second load: 96 threads, cpuset 0–95, batches 2,048/512, split none, load mode none, original poll 50, fixed 640 GiB equal memory/memory-swap, no container swap, and 16 GiB GPU reserve. Sampled main cgroup current peaked at 472.567 GiB, GPU use at 34.854 GiB with 60.118 GiB free, and host available memory stayed above 463.598 GiB. Process RSS peaked at 400.396 GiB. The 70.639 GiB file-minus-mapped accounting gap is not extra model weights and is not proven entirely reclaimable. Swap and OOM deltas were zero. The cap is not a minimum RAM estimate.

Saved launch argv, image and explicit environment match after campaign paths are normalized; realized CPU/memory limits and affinity also match. Both strict allocation gates passed. Exact process cmdline, full runtime environment and effective numeric poll values are unavailable in the inspected receipts. Warmup decode improved from 68.290 seconds in that G1 run, and 69.881 seconds in FIX, to 2.989 seconds here; warmup contains no schema, so schema or measured-request sampling cannot explain that acceleration. Saved guest NUMA page placement differs substantially. This is an observation, not physical-host placement or causal proof; no tuning or additional trial was performed. Exact comparison and unavailable fields are in the JSON report.

## Profiling limits

One requested eight-second software `cpu-clock:u` capture started after a positive decode count and a guarded warmup/slot-task recheck. The measured process span was 9.834 seconds. It extended beyond the short warmup decode into inter-request time, but its conservative end preceded the main request by 3.810 seconds: the main measurement was uninstrumented. Original receipts are preserved, including a wrapper EOF race that incorrectly overwrote native capture success with `SKIP`.

Named Q4/Q5/Q6 dot-product kernels account for 51.90% of displayed samples; major libgomp addresses remain unresolved. The mixed-phase sample establishes some quantized arithmetic activity but cannot identify barriers/spin or diagnose the historical slow decode. Full saved top leaf rows, timestamps and interval proof are retained. No second capture occurred.

## Restoration and source evidence

The original Qwen 1M TP2 selection is restored ready with running intent and resume boot policy. Original control/boot service state, authenticated LAN inference/control, released canonical lease, absent benchmark resources/listeners and closed worker tunnel ports are verified. A transient pending-systemd-job check interrupted the final status snapshot after local restoration; the existing fresh-process restore-only path completed verification without another model cycle or inference.

Production source/configuration was unchanged. The predecessor's deployed GLM native low default remains: saved D checks establish omitted effort equals low, request kwargs high changes rendering, and explicit top-level low overrides kwargs. That default correction is separate from schema-scoped correctness; no generic client schema injection or A1 expansion occurred.

Runtime source `594ca4ad836caf6d2bed0b92bafca9fe9c95a31a`, session `01a0bbc7-8f81-7881-a29a-a6f8db8dba16`, exact arm/profile/body identities, the immutable 20-minute dispatch clock and restoration receipt are in the companion JSON. Preparation took 260 seconds; measurements finished before the original 22:46:52.900 UTC deadline. Restoration is outside the measurement budget. Forty-seven focused checks and saved-data consistency checks passed.
