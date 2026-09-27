# H014 — MiMo frontier comparison

## Execution checkpoint — 07:40 UTC, 27 September

The isolated llama.cpp7ac59a6 /CUDA13.2.1 SM120a image built successfully and
passed CLI identity/help checks. Image digest:
`sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e`.
This establishes a build, not GPU/model compatibility or inference quality.
The exact13-shard Pro download remains independent and bounded through
08:50:01UTC. At07:37:18,111,105,009,056 of577,669,438,240 bytes were present,
including incomplete files;1/13 shards was hash-verified. Preserve partials
and verify every final file before load. No MiMo listener or model is active.

The disabled provider adapter passed11 focused tests and TypeScript checking;
it is not routed from Sova. Next: native exact-token counting, normal text and
tool continuation, memory/placement qualification, then the benchmark ladder
and existing frontier-lane integration. Do not treat source fixtures as live
qualification. Qwen/GLM/image production services are restored; Sova's GLM1M
release is active. There is no remaining dependency on a successful four-way
stress test, but no further such test is authorized while cooling remains
insufficient. [Latest checkpoint](../reports/h014-checkpoint-20260927/CHECKPOINT.md).

Both workers are idle at the agreed time-limit checkpoint. The independent
download may finish within its existing deadline; collect its terminal result
without paid waiting. Resume model-load/benchmark work in the next bounded
execution window. Do not redownload completed shards or rebuild this image
without evidence of a concrete defect.

## Latest selection priority

The user clarified that the best practical MiMo quality is the primary goal.
Keeping GLM and MiMo resident together is optional and must not drive a
quality-reducing quantization choice. Root selects **MiMo-V2.6-Pro-RL for the
first bounded trial**, after the source review completed at 06:39 UTC.

Selected candidate: `AesSedai/MiMo-V2.6-Pro-RL-GGUF`, revision
`ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d`, thirteen MXFP4 shards totaling
**577,669,438,240 bytes / 537.997 GiB**. The published tensor inventory is
207 MXFP4, 163 BF16 and 357 F32 tensors. Inspect actual downloaded metadata,
verify all published file hashes, and record the unresolved author converter /
source-checkpoint provenance. This is a concrete candidate, not a claim of
verified bit-equivalence or local inference quality.

Runtime research pin: llama.cpp `7ac59a6e3ad851cd41af00f678effab0598ba9a8`.
Use an isolated SM120 build; no production runtime replacement. First establish
normal 4K generation and tools before committing to larger tests. Pro's CPU
expert prefill can be much slower than GLM's layerwise GPU prefill; no rate is
assumed. Native weight format does not establish activation arithmetic quality.

The fallback, if Pro is incompatible or impractical, is the MXFP4/BF16 Flash
candidate at `AesSedai/MiMo-V2.6-Flash-RL-GGUF`, revision
`05c13439c18ba7183cb6afe294924c75ba7aa7b4`, **162.896 GiB**. Do not download it
alongside Pro merely as a precaution. The earlier 155.875 GiB ggml-org artifact
also converts attention/nonexpert matrices to Q8 and is no longer the selected
quality-first artifact. [Source review and exact manifests](../reports/h014-mimo-selection-20260927/REPORT.md).

Pro's 1M F16 global cache is 50 GiB; its nonexpert trunk matrices are roughly
39.5 GiB before workspace. Keep suitable nonexpert tensors in system RAM if
needed to preserve precision and the GPU reserve. Validate actual compact
sliding-window allocation and placement before claiming 1M capacity. Host file
bytes, resident memory and reclaimable cache are separate measurements.

Authorized27September2026. Execute after H013 production1M promotion, cooling,
ECC-off reboot and the single guarded overlap test settle. A failed thermal
guard is a recorded result; it does not authorize repetitive stress testing.
Do not start MiMo load if the assigned frontier GPU is unhealthy or unsafe.

## Objective

Keep qualified GLM-5.3-Flash available to restore while installing MiMo-V2.6-Pro-RL as a
second selectable frontier implementation. Initial standalone comparisons share
one fast Blackwell and system RAM and run serially in the frontier slot. Preserve both warm
Qwen480K lanes and the Ada image service. Do not replace a working default with
an untested candidate. Initial Sova default remains GLM until results are reviewed.

Compare for delegated technical research, electrical/electronic engineering,
microcontrollers, software engineering and difficult coding. Qwen remains the
coordinator and fast worker. Published benchmarks guide the trial, but cannot
replace measured local tool reliability or establish electronics expertise.

## Bounded work

1. Worker1 pins a current MiMo-capable runtime and exact model revision, verifies
   SM120/CUDA/CPU-expert support, and downloads only the thirteen selected Pro
   shards. Preserve native expert precision and BF16/F32 other tensors; no
   extra Q8, Q2 or other storage quantization to make room for GLM.
   A recent llama.cpp is the first candidate. Confirm native loader, chat/tool
   parser and mixed CPU/GPU placement before a large allocation. Alternate
   runtimes require a concrete incompatibility or performance hypothesis.
2. Preserve GLM source/image/model/profile and qualified1M rollback. Build in a
   separate pinned image/registered data path; no global CUDA/driver/production
   dependency changes. Downloads and long inference run under independent
   bounded jobs with incremental durable logs; paid Codex sessions exit while
   only waiting. Allow up to90minutes for first download/build, then report any
   unresolved blocker rather than an open-ended runtime sweep.
3. Worker2 independently prepares the existing Sova frontier/provider/status
   configuration for the additional model identity and one-owner frontier slot.
   No false concurrent capacity, dropped credentials/history or unqualified
   routing. Keep a reproducible return to GLM. Scope changes beyond existing
   API/profile mechanisms are reviewed before implementation.
4. After a warm-up, run4,096,16,384 and65,536-token fixtures serially, each with
   actual native token counts and reserved output/template space. Reuse the GLM
   retrieval/arithmetic intent and fixed settings; tokenization differences must
   be recorded. Use one primary run per size, bounded output and fresh prompts.
   Capture input speed, output speed, TTFT, total duration, RAM/VRAM, CPU/GPU
   utilization, placement and temperature. No prefix-cache speed inflation.
5. Run a bounded native tool-call/continuation and actual Sova delegation check,
   plus a small scored engineering/coding set: datasheet-grounded constraint
   reasoning, embedded-code repair with meaningful tests, and evidence-backed
   technical synthesis. Record correctness, failed tool loops and task time;
   do not present the small sample as a general benchmark ranking.
6. Prepare1,048,576 configured capacity using component memory estimates and a
   short allocation check only if prior results pass. Full1M occupied inference
   follows review of the4K/16K/64K evidence, actual allocation and a bounded
   runtime estimate. It is not inferred from small-context correctness.

The user additionally asks to consider keeping both frontier models resident
and running concurrently after MiMo1M qualification. Do not assume they cannot
coexist merely because they share a GPU. Preserve individual memory-component
measurements; evaluate combined peaks/reserves, CPU-expert contention and host
memory bandwidth. The user will decide on this configuration after those
results. Initial tests remain serial so there is a useful standalone baseline.

## Guards and output

Keep the established85C or lower hardware cutoff,7% frontier GPU reserve,
16GiB perQwen reserve,5% Ada reserve,15% host reserve and no owned swap/OOM.
Keep storage/identity/lifecycle protection and short stream-capture paths.
The user authorizes downloads and temporary service downtime for this work.
Stop on concrete failures, preserve incremental results and restore working
GLM when a candidate cannot be accepted. No repeated full-context tests without
a specific changed condition.

Workers use fresh bounded native Codex sessions, isolated source copies and
session IDs in task files. Root plans, reviews, synchronizes and publishes.
Publish code/settings and compact machine-readable results; no weights, private
credentials or bulky traces. Final comparison separates published model claims,
local runtime support, measured performance and tested task quality. Keep both
installed models, with one active frontier, for the user's default decision.
