# H021 — Optional Codex harness execution

Started 2026-09-28 05:10 UTC, base f5a15bbf99fdb7ba96c9d6d199bb268a60f04a4e.

The user authorized implementation of the published Codex plan with both workers, while leaving H019's near-950K MiMo test running.

## Work allocation

1. Worker1: pin Linux Codex/source/schema; Responses-to-local-provider contract and short Qwen tool/continuation qualification. Initial session budget 40 minutes. No live MiMo request.
2. Worker2: independent schema/license/contract review, offline Engine lifecycle and persistence foundation. Initial session budget 40 minutes. Share engine and gateway contracts early; UI activation follows protocol qualification.
3. Root: integration decisions, focused source review, synchronization and publication. Later bounded tasks cover tools/delegation, preview deployment and cross-worker acceptance.

## Preserved boundaries

- H019 model/benchmark/process configuration remains untouched. No long-test polling and no competing MiMo work.
- Existing MiniMax remains the default and old chats retain engine identity. Codex is a preview option.
- Existing queues, task isolation, tokens, artifacts, image guards and status identity are reused; no paid OpenAI fallback.
- Short Qwen calls require existing global admission ownership. No sustained stress tests.
- MiMo live qualification and the existing MiniMax/MiMo HTTP400 issue are explicitly separate outstanding evidence.
- Historical status-only release and active MiMo selector must survive application deployment.

## Acceptance status

The optional preview and central engine-status view are deployed. The
[stage 3 report](../reports/h021-codex-stage3.md) records the successful real
Qwen coding/tool/follow-up gate and retained first failures. The
[current acceptance report](../reports/h021-codex-preview.md) contains the
completed matched cases and later focused checks. MiniMax remains default;
MiMo acceptance remains deferred while the separate long test owns its runtime.

## Wave 1 checkpoint — 2026-09-28 05:50 UTC

Both initial native worker sessions completed and exited successfully. Worker1
source `9ca04d799b3c68f6fa8f0f6c66630801670e711c` and Worker2 handoff
`65b0a426c7610cb965a2ee3bdfc59f136a7e11d2` are merged, preserving their history.

- Exact Codex 0.158.0 Linux binary and generated schemas are pinned. Linux and
  Mac schema parity passed. Native mock-provider tests exercised two tool IDs,
  an actual patch, and a subsequent read/assertion in the same native thread.
- Session migration, immutable engine choice, streamed messages, reconnect,
  cancellation and retained gateway ownership have fixture coverage. Cross-review
  found and fixed a queued-successor ownership race before live acceptance.
- Worker2 reports 445 server and 180 web tests passed. Worker1 reports 47 focused
  provider/ownership checks and 18 launcher fixtures passed. Its separate full
  suite had one stale status assertion already corrected in Worker2's merge.
  Integrated regression runs belong to the next worker checkpoint.
- These results do not qualify live Qwen, real container tool workflows, native
  delegation, compression recall or deployment. Codex remains disabled by default.

Fresh bounded sessions now complete host composition, tools, delegation and
workflow acceptance. A small Qwen0 test requires an explicit app-owner handoff:
keep the inactive application from starting concurrently, preserve unresolved
lane state, and use one gateway on its existing port. No distributed inference
scheduler is introduced for this pilot. MiMo/H019 remain untouched and unpolled.
