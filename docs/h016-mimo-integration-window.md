# H016 — MiMo qualification and Sova integration

User authorized execution on 27 September 2026. Window starts 10:48:08 UTC
(12:48 Ljubljana), ends **13:48:08 UTC (15:48 Ljubljana)**. Stop admitting new
benchmark work at 13:25 UTC to leave time for settlement, recovery and reporting.
Sova downtime is allowed. Root coordinates/reviews/publishes; both Mac workers
perform implementation and VM work in fresh bounded native CLI sessions.

## Existing work to reuse

- Source baseline `02c24f148a85223290d37f6c3585518a83054923`.
- All 577,669,438,240 Pro-RL bytes are present. Twelve shards have existing hash
  receipts; only full-size shard 12 remains unverified. Check that file first;
  resume/redownload only if an actual integrity or length failure requires it.
- Reuse successful llama.cpp 7ac59a6 / CUDA 13.2.1 SM120a image `cdb6efd75f53`.
  No rebuild merely because this is a new execution window.
- Native MXFP4 expert weights, BF16/F32 nonexperts. No additional quantization
  or Flash fallback download without review of a concrete incompatibility.
- Reuse existing disabled MiMo adapter and shared frontier ownership/ledger.

## Parallel work

**Worker1 / ai-vm:** final shard verification and metadata; actual storage,
identity and memory preflight; preserve qualified GLM rollback; reviewed MiMo
launch on the fast frontier Blackwell plus CPU experts across all eight guest
NUMA nodes; native text/tool/count/stream proof; warmed 4K, 16K and 64K inputs.
Record actual tokens, prefill/decode/TTFT/total, host memory components, VRAM,
CPU/NUMA use and thermal limits. Keep placement and precision fixed across the
ladder. Use independent bounded jobs and compact incremental results.

**Worker2 / ai-harness:** preserve user state and pause upper app/task owners;
send an idle receipt before Worker1 changes the frontier owner. Wire MiMo into
the existing provider, delegation, status and ownership mechanisms; qualify the
actual MiniMax tool schemas and context admission. Independently review memory
and runtime evidence. After root review and a native pass, deploy and perform
a small real delegation/tool-follow-up test. Keep credentials host-side.

Initial native session bounds are at most 35 minutes; fresh sessions handle
later bounded tasks. Paid sessions exit while independent long jobs only run.
No simultaneous ownership of shared deployments or uncoordinated inference.

## Context and acceptance

- A 131,072 configured context is a practical initial ladder profile. Request
  inputs target 4,096 / 16,384 / 65,536 actual tokens, with 256 output tokens.
  Warm-up timing is discarded; measured prompts use fresh prefixes.
- Confirm native F16 cache and compact sliding-window allocation. Distinguish
  configured capacity from occupied input and actual allocated memory.
- After the ladder, estimate larger capacity from measured components and
  validate up to 1,048,576 configured tokens with a short allocation/request
  check if time and memory allow. Do not run an occupied 1M benchmark in this
  window or extrapolate its speed/correctness from small contexts.
- Preserve the 65,536 output ceiling with input-plus-output admission. Actual
  tool calls, reasoning history, tokenizer/template and stream settlement must
  agree before enabling the provider. No ambiguous request replay.
- One active frontier implementation; GLM and MiMo share its GPU initially.
  GLM remains a preserved rollback. Qwen remains coordinator/fast worker.
  Co-residency and the permanent default frontier are later decisions.

## Guards and completion

Keep 7% frontier GPU free, 15% host reserve, no owned swap/OOM and the existing
85 C or lower hardware cutoff. Preserve Qwen480K/image settings. No four-way
stress retry, BMC/fan/ECC work, driver changes, reboot or installer work.
Sova availability is not a gate during maintenance; user histories are.

Report measured results, current provider availability, unresolved defects and
context confidence limits. Publish reviewed code and compact evidence. If the
deadline is reached, settle owned work and report what remains; do not extend
the task automatically or leave uncontrolled GPU requests running.
