# H034 CHILD-CLOSE04 — source only

Base: `354a8d642e69e835d4f130fb2812a5f796d9e9d6`. Narrow compatibility correction is ready for root review. No push, deployment, host/service/model call, inference, install or live acceptance was performed.

## Failure boundary and evidence

Retained EDIT run `028e3931-aaaa-4b9c-8c09-f8032d886ca4` called close_agent on historical cancelled child `01a0ede6-0fad-7191-9e87-bcad69beb761`, using call `call_c6b86a86548d4b99953770e9`. Retained native ordinal128 is the call; ordinal130 is the canonical failed/not_found item; ordinal131 is its native error output; ordinal134 is the abort. No new child or image job preceded failure. Supplied triage records cleanup at18:22:22.995 and ticket removal18:23:20 (ticket timing supplied by task; no live verification).

The base source receiver loop at codex-children.ts:142–145 rejects an unknown non-spawn receiver before inspecting agentsStates. Offline reproduction against that exact Git source throws `Unknown native child` / `engine_settlement_unknown` for the reconstructed inProgress start and, separately, the normalized retained terminal. Thus a terminal-only exception would leave the earlier source boundary failing. **The archive contains no raw app-server start notification or host exception; the first actually thrown production notification is not historically proved.**

Trusted local Codex source pin `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`: core/src/tools/handlers/multi_agents/close_agent.rs emits the exact inProgress start before close, with sole receiver, null metadata and empty states. app-server-protocol/src/protocol/v2/item.rs:961 normalizes the Core terminal; :1299 maps NotFound to notFound/message:null. Generated v2/ThreadItem.ts and CollabAgentState.ts confirm the shape. Source/schema copies are in the existing H021-PROTOCOL01 durable task. Start fixture is reconstructed; terminal fixture is normalized from retained evidence, not a raw AppServer capture. Raw app/native/prompt archives remain outside Git.

## Correction

Only codex-children.ts changes production behavior. A bounded pending-call map records exact item/call ID, sender and sole unknown nonparent receiver for canonical closeAgent/inProgress. It adds no child/model ownership, subagent state, output or inferred terminal state. Pending close counts as unfinished. Only the bound canonical failed/notFound completion with null message clears it. No separate error text is inferred or rewritten: ThreadItem has no error/result field; native model feedback remains untouched.

Success, interrupted/ambiguous outcomes, active states, malformed state/errors, unmatched completion, receiver/call/sender/tool/type/metadata drift and unknown send/wait/resume remain fail-closed. A pending target becoming genuinely tracked cannot use the exception. Existing owned-child behavior remains unchanged. Confirmed native cleanup clears pending bookkeeping; process proof, gateway drain and quarantine code are unchanged.

## Focused validation and limits

27 selected tests passed: 7 new table-driven child tests, 9 existing child/schema tests, and 11 selected engine tests (7 new). Tests cover retained-terminal/reconstructed-start pair, continuation to a genuinely new child after cold resume, ownership/emission absence, meaningful rejection cases, bounded pending calls, tracked active turns and cancellation waiting for gateway drain. Targeted TypeScript checking of codex-children.ts and git diff --check passed. Dependencies reused from an existing matching lockfile; no install. An initial typecheck from repo root could not resolve Node types; rerunning from server cwd passed.

No full suite, build, native process, model, image, deployment or live acceptance result is claimed. Parent engine's existing duplicate-start suppression is unchanged; direct tracker start-drift tests do not prove engine-level detection of discarded duplicate starts. Terminal drift is exercised through the engine. Actual worker exit is recorded by the external wrapper, not claimed here.

Exact production diff, full patch, test receipt/logs, source commit and single-prerequisite Git bundle are exported in ../output. Root reviews and W2 owns any deployment/live acceptance.
