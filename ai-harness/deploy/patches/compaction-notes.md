# ACP compaction extension patch v1

Patch `0002-acp-compaction-notifications.patch` applies only to MiniMax Code
`ae65651df5f97ae1085ab4e19964f4b78c769a4e`. It adds the server's reviewed
`mcode/session/compaction_update` notification to the existing version 1 extension.
The pinned source extraction remains outside the repository and unchanged.

The patch adds a projection for actual native compaction started/completed/failed
events after the existing extension-notification opt-in check. It resolves only
the exact directly attached native session, excludes internal subagent sessions,
and checks projection cancellation, attachment identity, attachment retirement,
and unchanged native session identity immediately before notification. Delegated
child events are not attributed to a main context. Each transition has a distinct
key containing ACP session ID, native compaction ID and status, preventing the
native scheduler from replacing a pending start with its completion.

The payload contains only schema version 1, attached ACP session ID, native
compaction ID, mapped status (`start`, `completed`, `failed`), `estimated: true`,
and available native nonnegative safe integer `tokensBefore`/`tokensAfter`.
It never spreads the native event or includes errors, stacks, prompts, history,
tokens, or auxiliary token usage. The existing completed-event `usage_update`
projection is unchanged and remains the independent source of occupied context.
No compression algorithm, selector, threshold, messages, or prompt policy changes.
Notifications retain the native best-effort projection behavior; they are not a
new durable transport or a replay guarantee.

## Identities (SHA-256)

| File | Original | Patched |
| --- | --- | --- |
| `packages/tui/src/acp/agent.ts` | `f52c7031a0f22663c79cf33819e5df8f7b56c1352c2f087eb4c3d798c9728b79` | `3d78cf5b25cdee1f01ff81cd9f39de3d8b86173933fa2efea489603dc7f9c5ba` |
| `packages/tui/src/acp/extensions.ts` | `85ffe239d726d88106f15ce85835a6af810850954cf4a9eda54c61246c9f379a` | `5e747161117a8f713271dffe2f13665fac7686e1ba3c66ffefafeb72e49ae76d` |

Patch SHA-256: `ec56ccb5834dd75f7e4c9a9bff9599ebaf1da41c101c0cbde858c47f46cc8d2f`.
Container builds additionally verify the exact upstream commit before patching.

## Local PREP checks

Command (Node 24.21.0):

```sh
node ai-harness/deploy/tests/test-compaction.mjs /absolute/path/to/pristine/pinned/source
node --check ai-harness/deploy/tests/test-compaction.mjs
```

Eleven checks passed on 2026-09-22. The suite verifies the two original file
identities, applies the actual patch to a disposable copy with `git apply --check`
and `git apply`, and checks full modified TypeScript syntax via Node type stripping.
It executes the actual patched projection function plus native attachment,
opt-in, usage, delegation identity, and scheduler helpers extracted from source.
Fixtures cover all three statuses, version-1 advertisement and opt-in, exact
session isolation, missing/invalid IDs, no invented events, safe token counts,
redacted payload whitelist, cancellation/retirement/replacement/identity change,
distinct transition keys, a fully busy native queue preserving quick transitions,
and genuine usage refresh independently of extension opt-in.

These are focused native-function/source checks using a mocked notification sink
and runtime snapshots. They are not TypeScript typechecking, the full upstream
suite, a full engine build, actual ACP SDK transport, actual model compaction,
container execution, or live server/browser acceptance. Node reports its standard
experimental warning for `stripTypeScriptTypes`. No dependencies were installed
for these checks, and no host bootstrap, SSH, sudo, or inference call was used.
