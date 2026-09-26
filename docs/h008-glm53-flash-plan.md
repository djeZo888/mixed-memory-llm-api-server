# H008 — GLM-5.3-Flash frontier worker

Approved 2026-09-26. Root coordinates/reviews; mac-worker1 and mac-worker2
implement, build and test in isolated copies through fresh bounded native CLI
sessions. Execution started 16:24:45 UTC. At approximately 19:24:45 UTC, stop
dispatching new tasks, let current bounded work settle and report completion,
time spent, failures and remaining work. This round's three hours includes
preparation/download/build, superseding the earlier qualification-only budget.

## Placement and capacity

- Retain Qwen0 on GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237.
- Move Qwen1 from GPU-69acfa26-8b60-61b5-702d-aee252c163cc to slow-link Server
  GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528. Warm first, then benchmark about
  64K actual input tokens against its unchanged 480,000-token allocation.
  Record input/decode speed, latency, VRAM and temperatures. Bad performance is
  reported separately and does not prevent starting Flash.
- Place Flash on the freed fast Blackwell with CPU experts in system RAM.
  Keep at least **7% free GPU VRAM under peak load**, not a 15% VRAM reserve.
  The separate 15% host available-RAM reserve remains unchanged.
- Preserve image service/Ada assignment, both Qwen weights/runtime pins,
  protected data and old GLM rollback weights. No installer or Proxmox changes.

Deploy official GLM-5.3-Flash FP8 (~306 GiB weight files), pinned KTransformers
and compatible SGLang/Transformers components. Use its documented SM120 and
AVX-512 hybrid path in an isolated runtime. Start with 64 CPU expert threads,
topology-aware placement, native-precision attention cache, one inference slot.
Target 480,000 context; qualify first at 65,536, then repeat a short fixture at
480,000. If capacity fails, test 256K then 128K and report the accepted limit.
Configured capacity does not constitute full-window correctness testing.

Reference: https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/GLM-5.3-Flash-Tutorial.md

## Maintenance and implementation

Downtime is explicitly authorized. Stop upper Sova services on ai-harness and
preserve before-state/restore instructions; avoid repeated continuity probes.
Worker1 owns ai-vm. Worker2 owns ai-harness. Download may start immediately after
registered storage checks. Downloads are authorized without further permission.
Reuse canonical lifecycle lock, storage guards and exact runtime identities.
New GPU placement needs new truthful profile evidence, not edited old receipts.
Source/activation review should be brief and focused, without redundant gates.

Proposed fixed private backend: 10.156.100.60:30010/v1, model glm-5.3-flash;
check port availability before installation. Native listener is authenticated
loopback behind the established private transport. Add status/readiness and
isolated failure behavior; no global GPU-index assumptions. Models stay warm;
idle waiting must block after ten minutes without work. Automatic updates stay
disabled. No driver replacement without demonstrated compatibility need.

## Native frontier agent

Reuse pinned MiniMax native custom-agent lifecycle. Add named `frontier` worker
with separate provider `/frontier/v1`, exact model alias and its own context
budget, 65,536-token output ceiling, explicit high reasoning effort and correct
GLM template/parser settings. One independent inference slot, eight waiting
requests, 30-minute queue deadline; existing two Qwen slots stay separate.
Retain two-hour active request and frontier-delegation execution limits.

Full approved research/coding/browser/PDF/image tools are available. Deny
recursive task/task_append delegation. Parent and child share a workspace;
code-changing tasks run sequentially unless ownership is disjoint. Reuse native
Stop/continuation/progress; no automatic replay of ambiguous requests or edits.
Release GPU admission between completions, not after the whole agent task.

Flash admission must count the actual template/tools/history with its pinned
tokenizer, and native compaction must use model-aware counting or a validated
conservative bound. The existing o200k_base estimator is not automatically
correct for Flash. Attribute child context/model/progress separately from the
main Qwen conversation.

## Routing and benchmark evidence

Qwen remains the default for coding, agentic execution and orchestration.
Flash is a selectively invoked worker for deep research, large-document
synthesis, difficult reasoning and independent diagnosis. Exceptional blocked
coding work may escalate with justification; Qwen reviews/applies the outcome.
No blanket claim that either model is better at every task is justified.

Current official publisher figures:

| Model | Terminal-Bench 2.1 | DeepSWE 1.1 |
|---|---:|---:|
| Qwen3.8-27B | 73.0 | 42.2 |
| GLM-5.3-Flash | 84.3 | 63.4 |

Sources: https://huggingface.co/Qwen/Qwen3.8-27B and
https://autoclaw.z.ai/blog/model/glm-5.3-flash/ . These do not establish a
controlled ranking: Qwen's DeepSWE uses Claude Code/256K; Flash uses
mini-swe-agent/400K. Terminal harnesses also differ. They do not support the
general claim that Qwen outperforms Flash at coding/agents, nor prove local
Flash superiority. Small paired tasks will supplement these imperfect signals.

## Acceptance and bounded work

After Qwen migration: coherent Flash smoke/tool/stream tests; short-input
2,048-output sustained decode; approximately 4K/16K/64K prompt checks; larger
configured-capacity allocation/short-request check. Record prompt speed,
decode speed over time, actual counts, TTFT, total time, RAM/VRAM, CPU and GPU
activity/temperature. If sustained below one token/s for five minutes, capture
diagnostics and pause that test. One targeted diagnostic retry; no model or
runtime sweep. Partial measurements remain useful and are not rerun needlessly.

Worker2 implements gateway/native worker/accounting/tests against fixtures in
parallel. Root reviews the completed sources before coordinated deployment.
Live acceptance requires a Qwen parent selecting Flash, a research and code
task, child result return, independent inference admission, cancellation,
context accounting/compression and service-failure isolation. Optional large
inputs and extra benchmarks are dropped first when time is limited.

Deliver reviewed code/settings, actual evidence, rollback state and GitHub PR.
Do not claim completion while runtime or native-agent acceptance is pending.
