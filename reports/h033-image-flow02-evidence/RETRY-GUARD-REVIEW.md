# Bounded schema-error guard review

Read-only review of exact deployed source aa5bdb826b422122d3497492f8f749948640d175. No retry mechanism implemented or tested.

No dedicated consecutive identical schema-error/no-progress limiter was found in the reviewed Sova adapter path. `codex-engine.ts:670` rejects a new unique native item once its item map already contains 10,000 items; `codex-children.ts:261` applies the same general bound to a child turn. These are item-count guards, not an eight-error limit.

`codex-engine.ts:751` accepts completed/failed/declined tool terminal statuses, retains arguments/result/error (`:778`), and emits progress (`:795`). A failed MCP result does not itself abort the native turn or increment a dedicated schema-error streak here.

Both `deploy/codex/config.toml:27` and `config-image-jobs.toml:27` set request_max_retries=0 and stream_max_retries=0. These disable transport replay, not new model tool calls after errors. `codex-responses.ts:474` bounds argument bytes per response (4 MiB aggregate, 1 MiB per call), not repeated schema failures across requests.

`tools/image/image.mjs:202` rejects capability arguments. The actual feedback is the MCP SDK's earlier -32602 rejection, not the helper's own accepts-no-arguments message. Generation/edit submission uses one POST (`:216`) and explicitly avoids submission retry (`:220`); job observation backoff is separate from model retry behavior.

Corrected acceptance: 11 completed schema-invalid capabilities calls with identical raw arguments; 12 gateway requests; zero image jobs. Exact errors with matching call IDs reached the next normalized provider request for calls 1-10. Call 11's error appears only in request 12 pre-normalization; that request has no normalized/provider capture. Operator Stop was accepted, so classify BOUNDED_ACCEPTANCE_FAILED_REPEATED_SCHEMA_ERRORS with operator termination, not natural terminal failure. See CORRECTED-NONPROGRESS.json and CORRECTED-BOUNDARY-AUDIT.json.

Scope: narrow review of the listed application/provider/tool files; not an exhaustive native Rust audit. No claim about unreviewed components.

Reviewed source hashes (byte-equal to deployed commit):

- `ai-harness/server/src/codex-engine.ts` SHA-256 `e0df995c1d652bc1d08c89379cb09f1d1268df793310db23c2ae5a8fb2a461ba`
- `ai-harness/server/src/codex-children.ts` SHA-256 `272b9126f4da64d963874ca8ac8fc0424844404ad684985bacb63bf06ce0af0e`
- `ai-harness/server/src/codex-responses.ts` SHA-256 `c107f0b5e741c9ca3749c36ba5ed311b790f9ca11be681aeb7a190a5dbb9d7c0`
- `ai-harness/server/src/codex-provider.ts` SHA-256 `a8e0b6938e14e3e1ff048ee3cce89004adca3267d65dae6d7e2141a46393a20c`
- `ai-harness/tools/image/image.mjs` SHA-256 `6914e0d198ee43576b4ac985c42cbccb128c2ced080082ab01e88888c0edd671`
- `ai-harness/deploy/codex/config.toml` SHA-256 `97f0b812b30380a51da742810e2804fb6ce63546ac2773ddff38a8bb6f442ccd`
- `ai-harness/deploy/codex/config-image-jobs.toml` SHA-256 `6aa9b28745c1200ac7f0c5c7132eba78df91e86f04a9cb85dc4215eb04c10a14`
