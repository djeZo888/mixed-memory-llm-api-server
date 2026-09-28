# H024 owned compaction and phase UI source checkpoint

Offline source/fixture work only. No VM contact, model inference, deployment, native runtime/CLI upgrade, or default-engine change. MiniMax remains default. Live context compression/recall remains **NOT_TESTED**.

## Behavior

- Completed messages without an authoritative final phase display **Assistant response**. Streaming, commentary, thinking and explicit final mappings retain their existing semantics; original content, phases and native IDs are unchanged.
- `POST /api/sessions/:id/compact` accepts only `{ "actionId": "bounded-client-identifier" }`. It rejects MiniMax, an empty/new native thread, unknown fields and duplicate distinct pending actions. `/compact` prompt text stays unsupported.
- `Engine.compact?(): Promise<"completed" | "cancelled">` is typed and optional. The broker calls the existing Codex implementation through an ordinary `compact` run; it never exposes arbitrary native RPC or substitutes a prompt.
- Compaction enters the existing per-workspace queue and retains its lock through native completion, cancellation, cleanup and settlement. Original messages, file records and native thread identity remain in place. Failures are visible; uncertain cleanup keeps quarantine and blocks siblings.
- Companion table `h024_compaction_actions` atomically binds `(session_id, action_id)` to the existing run. Duplicate delivery returns the original run while queued/running or after completion, failure, cancellation or restart. Interrupted durable runs are never replayed. Capacity rejection creates no action/run binding.
- The web action persists its ID in `sessionStorage` before dispatch. A lost acknowledgement, HTTP 408, 5xx or unreadable acknowledgement retains the same ID for explicit reconciliation; there is no automatic retry. Refresh retains the unresolved action. Confirmed terminal run events/snapshots clear a known binding, a known 4xx rejection other than HTTP 408 releases only a fresh action; rejection of a retry retains the previously unresolved action, and a subsequent deliberate action can receive a fresh ID. A storage write failure occurs before dispatch.

## Focused verification

All commands below ran on mac-worker2 with the cached dependencies previously used for H021.

| Check | Result |
|---|---|
| `cd ai-harness/server && node_modules/.bin/tsx --test --test-timeout=15000 test/compaction.test.ts` | PASS, 8 tests |
| `cd ai-harness/server && node_modules/.bin/tsx --test --test-timeout=15000 --test-name-pattern='compaction\|handoff\|queue\|workspace\|cancel' test/app.test.ts` | PASS, 33 affected lifecycle tests |
| `cd ai-harness/server && npm run typecheck` | PASS |
| `cd ai-harness/web && npm test -- --run tests/compaction.test.tsx tests/replies.test.tsx tests/queue.test.ts` | PASS, 76 tests in 3 files before the final lost-ack/rejection correction |
| `cd ai-harness/web && npm test -- --run tests/compaction.test.tsx` | PASS, final 11 compaction tests including lost-ack then HTTP 401/409/429 then same-ID retry |
| `cd ai-harness/web && npm run build` | PASS, final TypeScript and Vite; JS asset `index-CLHuYAhl.js` |
| `git diff --check` | PASS |

The initial new UI completion-before-ack fixture raced asynchronous initial subscription creation; waiting for the established fixture stream corrected it. Earlier command attempts from the wrong working directory failed before running tests/writing the new server fixture; corrected commands are listed above. No failed production acceptance was retried or reclassified.

Server fixtures cover session/body guards, shared-workspace ordering, history/file/native-ID preservation, durable duplicate action delivery and restart, explicit failure, unconfirmed cleanup quarantine, persisted interrupted action recovery without replay, capacity rejection and Stop. Web fixtures cover the exact endpoint/body, pending status, original history, completion-before-ack, visible rejection, lost acknowledgement across a fresh store/refresh, an intervening HTTP 401/409/429 rejection without discarding that unresolved ID, fresh ID after confirmed completion, and MiniMax/empty-chat restrictions. These mock-engine fixtures do not establish local-model recall quality.

## Smallest next live acceptance after combined source review and root GO

Use one short owned Codex chat with three explicit facts/constraints and a small owned file reference. Retain the initial native thread ID, visible messages, run IDs, file IDs and file hash. Submit the explicit compact action once with a recorded action ID; observe native compaction lifecycle, its terminal run, cleanup and fresh context evidence. Repeat only the same HTTP action delivery to verify the same run ID without a second native compaction. In a fresh resumed follow-up on that same native thread, ask for the facts/constraints and file reference. Compare exact recall and preserved history/files; record PASS/FAIL without prompt rescue. If compaction fails or settlement is uncertain, retain that action/failure and stop this acceptance. No PDF, image or already-passed coding/research repeats are needed for this UI/queue change.
