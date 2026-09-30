# Diagnostics-only review boundary

- Three source files: codex-admission.ts, codex-production.ts, codex-diagnostics.ts. New codex-control-transport.test.ts.
- Original verifier predicates, native/pinned schemas, identity checks, 15s freshness, 480000 capacity, 30000ms GET timeout and 512KiB response bound remain unchanged.
- Public ApiError remains HTTP503/codex_qwen_identity_unqualified with original message. No retries, fallback lane selection, provider dispatch, main.ts edit, model/VM/deployment change.
- Optional transport projection on existing schema1 rejection event: static kind; integer HTTP100–599; exact control/http error-code allowlist. Remote text/body/error/credentials never retained; logger reprojects independently.
- Stage event carries subtype; lane/tokenize rollups remain existing static reason with same requestId, so consumers can correlate without changing their schemas.
- PASS 11 selected tests, including 4 new transport/projection fixtures; PASS TypeScript typecheck. Initial fixture-only status/statusCode typo and initial wrong-workdir correction command are recorded separately.
- Independent read-only source review PASS. Known diagnostic limit: simultaneous explicit cancellation and timeout is classified cancelled by precedence. Production verifier currently supplies no explicit caller signal to get().
- Deployment pins unchanged: policy/adapter/core/manager/receipt remain baseline. Only normal reviewed harness source build/release needed if root chooses activation. Worker1 has not deployed this patch.
