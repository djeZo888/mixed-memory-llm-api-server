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

Implementation in progress. No Codex live behavior is claimed as passed yet.
