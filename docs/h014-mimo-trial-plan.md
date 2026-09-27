# H014 — MiMo frontier comparison

## Latest selection priority

At 06:22 UTC the user clarified that the best practical MiMo quality is the
primary goal. Keeping GLM and MiMo resident together is optional and must not
drive a quality-reducing quantization choice. The proposed Flash GGUF preserves
the released experts' native MXFP4 format; its conversion/runtime still requires
verification. Root and Worker2 are checking whether the stronger Pro variant is
practical on the same RAM plus one fast Blackwell before the download decision.
No MiMo weights have been downloaded. Assess Pro first if its runtime support
and memory reserves are practical; full-quality Flash remains the alternative.
The Flash-specific steps below remain the candidate plan pending that assessment;
they do not authorize silently downgrading precision for sharing. Weight-file
size alone is not a complete allocation estimate, and published benchmark
advantages do not establish local inference speed or reliable tool use.

Authorized27September2026. Execute after H013 production1M promotion, cooling,
ECC-off reboot and the single guarded overlap test settle. A failed thermal
guard is a recorded result; it does not authorize repetitive stress testing.
Do not start MiMo load if the assigned frontier GPU is unhealthy or unsafe.

## Objective

Keep qualified GLM-5.3-Flash available while installing MiMo-V2.6-Flash-RL as a
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
   SM120/CUDA/CPU-expert support, and downloads only selected native-MXFP4 GGUF
   shards (approximately155.9GiB). Preserve native4-bit experts; noQ2 reduction.
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
