# H039 native adapter — disabled source candidate

This directory is E's source preparation. Default export has `enabled:false`
and `capabilities:[]`. Importing it starts no server, process or inference.
No fixture result qualifies native execution, current production browser/UI,
installed config support, container mounts/egress, retention or cold resume.

`adapter.ts` implements the external `h039-compaction-adapter-v1` shape and
exposes `createNativeAdapter(input)` for a later root-owned entry module.
Run B's controller under the existing pinned `server/node_modules/.bin/tsx`
loader when importing this TypeScript source. B owns the evolving controller,
legal IDs, normalization, independent expected input and checkpoint schema.
The default adapter cannot pass B's runtime/capability gates. Do not add
capability names or change unknown metadata to satisfy those gates.

`bootstrap.ts` proposes one temporary Linux app/gateway for the whole suite.
It requires a root-reviewed candidate/source closure and a fresh independently
observed normal owned-stop/quiescence/preserved-production receipt. It creates
a private app DB, profiles, workspaces and sibling host-private state. Existing
Store, GatewayOwnershipLedger, createApp, CodexEngine, composeCodexHost and the
current production Qwen verifier/counter are reused. Shared dispatch holds
are read through a read-only SQLite connection with existing fail-closed
semantics. It never stops production, changes its history, sweeps ports or kills
unknown listeners. Only `127.0.0.1:8081` and `127.0.0.1:18081` are bound;
`EADDRINUSE` is retained and propagated. No nginx or public activation occurs.
The 18081 surface is the temporary app API; browser/UI is NOT_TESTED.

Native launch uses only the unchanged reviewed rootless `deploy/run-codex.sh`
script, image, egress and policy with `http://10.0.2.2:8081/v1`. No host Codex,
arbitrary provider port or direct model bypass exists. Main initialization
remains `experimentalApi:false` in the existing engine. Separate probes use
CodexConnection, `experimentalApi:true`, fresh `thread/start`, empty distinct
profile/workspace, read-only sandbox, never approval, no environments, disabled
agents/tools/MCP/memories and zero project document budget. Source support is
documented by the root/A pinned-source audit; installed support is NOT_TESTED.

`projection.ts` extracts only one new persisted `compacted.payload.message`
from an unchanged scoped rollout prefix, with exact native thread, independently
observed native turn/action, bounded dispatch/settlement window and a reviewed
native summary prefix. Empty, prefix-only, unmatched, ambiguous, truncated and
rollback/revert suffixes fail. `replacement_history` is never projected or read
as context. The exact native summary prefix must be supplied from A's source
audit before any compaction dispatch; E's read attempt failed host-key validation.
No source-fetch fallback or trust weakening was attempted.

`dispatch-guard.ts` enforces summary scope in awaited `countQwen`, before
tokenization/generation. Final translated `body.tools` and raw tools must be
exactly `[]`; compiled instructions and typed Responses input must equal the
reviewed frozen manifest. Old calls/results, parent identities, additional probe
requests, missing captures, changed translation, expired scope or failed durable
capture reject without rewriting tools. Pre-normalization and normalized request
bytes are independently retained, rehashed and bound to authenticated gateway
request/session plus observed native thread/turn/action/run. The normal real
counter still performs current shared-provider admission. Diagnostics swallow
errors; the count gate is the rejection mechanism.

Probe handles have controller cancellation and an owned total deadline through
terminal completion after ACK. Stop sends only an observed owned interrupt,
revokes admission and awaits exact native cleanup plus gateway settlement.
Interrupt ACK/PID exit do not prove settlement. Host close first aborts/awaits
all direct handles. Rerouting, tools, incomplete/unstarted items, conflicting
completion and `itemsView:notLoaded` fail. Terminal summary is matched to the
last actually completed agent message. Invalid answer JSON retains settlement
and failed private output. Unknown mount/network evidence remains null.

`checkpoint.ts` fsyncs original rollout/profile, Store SQLite export, workspace
file bytes and identity/hash manifest outside model mounts before manual
compaction after confirmed settlement. Changed/deleted sources, unsafe links
and renewed writers fail and preserve partial output. Original failed native
output is separately retained. Native context replacement precedes persistence;
these checkpoints do not promise atomic rollback. Recovery requires reviewed
no-writer reconciliation, never replay of an ambiguous compaction.

Remaining concrete blockers: scoped dynamic retrieval is unavailable because
the pinned CodexConnection rejects all server calls; there is no qualified
read-original tool/settlement seam. Main continuation artifact collection and
accepted-grade/cold checkpoint handoff are unqualified and fail honestly.
Cold resume and clean-child first-request qualification are unavailable. After E
closed, B finalized legal IDs, complete raw request/typed-input binding and
message-only projection from separately bound full state in source commit
`4581a186`. The trusted collector, actual native envelope compatibility and B/E
integration remain unqualified. Runtime binary/tokenizer observation,
exact installed compiled-input manifest and actual mount/egress attestation
must be obtained separately. Unknown counts and revisions remain unknown.

Source validation, from `ai-harness/server`:

```sh
./node_modules/.bin/tsc -p ../acceptance/compaction/native-adapter/tsconfig.json
./node_modules/.bin/tsx --test --test-timeout=15000 test/h039-native-adapter*.test.ts
```

Root's 01:17 UTC update freezes all ai-vm deployment, inference and live native
testing for the authorized guest shutdown. E performs only Mac source work and
closes by 01:35 UTC. A later live sequence requires a concrete E/A/B candidate,
root review/GO and the then-current authority. No near-threshold case, old
950K/four-fact test, MiMo/image/GPU load, hardware or native upgrade is included.
