# H040 controller and native collector contract

This is source preparation. All native dimensions, Linux transport, model
retention and rollback remain **NOT_TESTED**. The default adapter and both
checked-in controller configurations are disabled. B changes no engine,
gateway, store, deployment, native-adapter or live machine state.

## Logical and raw hash domains

New evidence records use schema version **2** and
`logicalManifestFormat:"h040-sorted-json-v1"`. Logical JSON recursively sorts
object keys, preserves arrays in order and uses ordinary JSON string escaping.
B and E use this same serialization. SHA-256 of actual request, normalized
request, rollout, selected record and receipt bytes remains byte-exact; those
bytes are never sorted or regenerated for hashing.

Archived H039 evidence used insertion-order `JSON.stringify` and schema version
1. It remains unchanged and belongs to its recorded H039 source revision. The
new validator rejects that version rather than silently assigning the new hash
semantics. Replaying an old evidence object under this source does not constitute
requalification. Corpus and ground truth remain unchanged.

## Profiles and honest dimensions

`h040-summary-stage-v1` uses one disposable manual cycle: 56 active facts,
49 critical and 7 noncritical, one isolated summary probe, original preservation,
and owned cleanup. Its budget is exactly nine native calls, including cleanup.
It cannot qualify the full suite. Measured observations have their own status;
unobserved corrections, later cycles, retrieval, continuation, cold resume and
child context remain `NOT_TESTED`.

`h040-full-retention-v1` preserves all three cycles and all original guards. It
requires both the baseline cold boundary and a second cold resume **after the
latest independently accepted continuation**, then clean child context. Its
bounded native budget is exactly 39 calls. The archived 37-call synthetic flow
remains testable; it does not qualify the mandatory H040 post-continuation cold
dimension. Do not enable an automatic case under either profile.

`qualification.schema.json` is the reusable dimension report contract.
`actualStatus` covers observed deterministic checks with explicit synthetic or
native qualification; `nativeStatus` requires full mandatory native coverage.
Every observation retains cycle, mode, evidence reference and exact-fact totals
when applicable. `nativeAcceptance`/`semanticAcceptance` cannot be PASS for
synthetic runs or incomplete stages. Source test PASS is separate from that
aggregate. A retained native failure or uncertain cleanup prevents acceptance.

## Fresh persisted-message representation

Root may approve `review.freshProjectionSpec`:

```text
format: h040-fresh-persisted-message-v1
frozenPolicy: independently approved exact string
prefixInput: independently approved actual typed native system/developer scaffold
collectorManifestUtf8: actual immutable reviewed closure manifest bytes
collectorSourceSha256: SHA256(collectorManifestUtf8)
```

B first validates full state, independent prebaseline, exactly one fresh selected
compaction, owning `session_meta`, operation/turn/record binding and settlement.
Rollback/revert suffixes are rejected because their reconstruction is not
qualified. The summary comes only from exact `compacted.payload.message`.
`replacement_history` and adapter-declared `checkpoint.messages` are rejected
for this representation. No abstract summary role is injected into the native
request.

B independently derives one user text with canonical logical JSON:

```text
{policy: frozenPolicy, persistedCompactedMessage: selectedMessage, questions: approvedQuery}
```

It appends that text to the frozen native scaffold. The entire raw Responses
envelope, actual typed input, tools, instructions, metadata and unknown fields
must match approval. Only three explicitly reviewed identity placeholders may
bind captured native IDs: `@h040:probe-native-thread-id` at
`client_metadata.thread_id`, and `@h040:probe-native-turn-id` at `turn_id` and
`root_turn_id`. Other fields remain literal; unknown placeholders fail.

The verifier invokes the actual production `translateResponses`, including its
Qwen instruction adaptation, and compares the **entire** actual normalized
provider body. It does not maintain a second translation algorithm or approve
an adapter-supplied normalized body. Native CLI execution verifies the root's
`translatorHashes` for `src/` and `dist/` copies of `codex-responses`,
`codex-provider` and `errors` before importing the translator.

The portable closure manifest is
`{format:"h040-collector-closure-v1",sourceRevision,files:{repoRelativePath:rawSHA}}`.
It includes every constructor/native-adapter and server runtime source sibling,
package/lock and reviewed dependency closure. Native CLI checks actual files
and rejects omitted source siblings, changed bytes or symlink substitutions.
E separately owns deployed launcher/image/installed dependency and provider
receipt bindings. Local source hashes do not qualify installed bytes.

`projectionReceiptUtf8` and SHA bind actual run/action/native parent/probe/turn,
host operation window, full parent state, selected record, summary, query,
policy, constructor closure, full first request, normalization, scope, input
manifest, complete envelope and owned probe settlement. `collectorManifestUtf8`
must equal the independently reviewed raw manifest, not an opaque hash label.
`probeSettledOperationUtf8` binds completed/released owned work, separate native
and gateway settlement, request captures and observed bounds. The exact fields
are enforced in `verifyFreshProjectionCapture` in `scorer.mjs`; absent independent
fields explicitly remain NOT_TESTED, never compare equal by JSON omission.

Scope still requires genuine `native-launcher-effective-scope` receipt bytes.
Booleans or a collector's declared capabilities cannot establish isolation.
Post-probe full parent state and its actual `owned-native-persisted-state`
receipt must match the accepted checkpoint. Missing proof is NOT_TESTED and
changed bytes fail. A trusted A/E supervisor transport is still a native gate.

## Native windows and cold continuation

The legacy receipt `windowId` denotes a **host operation window**. New native
compaction receipts must also expose `operationWindowId` equal to that value,
`windowIdProvenance:"host-operation-window"`, and independently captured
`nativeWindowId`. Native `window_id` is `thread_id:window_number`; it never comes
from the acceptance run ID. B verifies the actual `compact.requests` raw and
normalized capture bytes, parses canonical
`client_metadata["x-codex-turn-metadata"]`, checks thread/turn/manual compaction
semantics and requires any flat `x-codex-window-id` to agree. The settled receipt
must retain the same exact request-capture manifest. Absent canonical metadata
is NOT_TESTED; conflicting windows or manual metadata fail.

Evidence records expose `operationWindowId` and `nativeCompactionWindowId`
separately, each measured or explicitly absent. The first comes from the
reviewed owned operation; the latter is verifier-derived from actual captured
native metadata. Neither is relabeled as the other.

`resumeAcceptedContinuation` receives the independently captured current full
parent checkpoint plus accepted continuation action/artifact hashes. It must
return genuine `native-owned-host-cold-resume` receipt bytes proving distinct
owned host/application identities, old application exit, old gateway settlement
and no replay. Changing routine per-turn native process IDs is insufficient.
`native-owned-workspace-artifacts` receipt bytes include actual re-read artifact
UTF-8; parsed values and accepted hashes must match. B independently scores the
resumed engineering outputs again and checks another unchanged parent capture.
Missing bytes remain NOT_TESTED. No cold resume or rollback implementation is
provided by B.

## Runnable source checks and later root gates

```sh
node ai-harness/acceptance/compaction/controller.mjs plan ai-harness/acceptance/compaction/h040-summary-stage.config.json
cd ai-harness/server
./node_modules/.bin/tsx --test --test-timeout=15000 test/h040-compaction-retention*.test.ts
```

The collector tests honestly skip when `collector.ts` is absent from this
candidate. Set `H040_E_SOURCE_ROOT` to the reviewed read-only E `native-adapter`
directory to exercise its actual concurrent source. Host/database/protocol
boundaries remain explicitly synthetic; no model or native process is started.

Before any later `run-reviewed`, root must review a coherent A/B/E candidate,
actual runtime/model/tokenizer pins, current protected placement/provider tuple,
entire emitted native projection/envelope/tools, installed source/build closure,
real launcher scope and settlement transport. The immutable absolute review
deadline may not exceed **2026-10-01T04:26:10Z**. The disabled template grants no
permission. Root owns later live GO and all shared work.

The A `read_original` proposal is a distinct native tool from the synthetic
semantic `scoped.read_original_records` trace. Do not rename one to the other.
After A/E source review, propose a separate reviewed retrieval representation
that verifies actual `item/tool/call` thread/turn/call/item/argument/settlement
bytes against the branded frozen checkpoint and original-record hashes. A
native tool response alone does not prove consumption or retrieval acceptance.
The current full profile deliberately remains unqualified for that seam.

Root's physical-scope review found that empty roots/deny-all network cannot
describe the actual housekeeping mounts and gateway. B preserves the strict
gate and exports a [separate observed-scope proposal](h040-native-scope-proposal.md).
It does not fabricate denial from physical receipts. Native dispatch now uses
a frozen reviewed settlement reserve of at least 75 seconds, aborts outstanding
owned calls before close and checks retained close receipt consistency. Actual
producer/transport qualification remains required.
