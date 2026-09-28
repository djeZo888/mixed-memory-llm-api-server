# H024 image argument boundary: offline source and pinned native fixture

Status at 2026-09-28 17:04 UTC: fixture PASS; historical image acceptance remains FAIL.
No production adapter/MCP code was changed by this investigation. No VM, model,
gateway, image job, deployment, package install, or live acceptance was invoked.

## Retained facts and the missing evidence

- `H021-ACCEPT06-20260928/evidence/CODEX-IMAGE-NATIVE.jsonl` SHA-256
  `932edbb7b02536e7a517ee2c87942f8fecafc925bfebfb0873854ff501051e31`:
  line 14 retains a native `response_item.function_call` with namespace
  `mcp__image`, name `image_capabilities`, call ID
  `call_0293558689b546449e593ea0`, and raw arguments `{"__ns": "10"}`.
  Lines 19 through 89 retain 15 more calls with raw arguments `{"ns": "10"}`;
  these are strings with numeric contents, not JSON number values.
- `H021-REPAIR-ACCEPT09-20260928/evidence/457e363d-3c63-43ae-ae4d-7be6a52045fa-native.jsonl`
  SHA-256 `767cdef3b4afada4a8e5a2fbdac09ed87dc1bf75cd3c2e81a4bc27e9e905340c`:
  lines 18 and 23 retain exactly `{"__v": "0"}` for call IDs
  `call_4d486394f83f445ca76a1404` and `call_5913d976a0de4ae5b5ab3965`, same native
  namespace/name. Supplied error extract retains strict MCP rejection for both.
- The above are native rollout response items, not retained upstream Chat bytes.
  None of the three inspected image/native rollout files has `finish_reason`.
  A targeted search of H021 ACCEPT05, ACCEPT06 and REPAIR-ACCEPT09 evidence JSON,
  JSONL, log and text files for `finish_reason`, `chat.completion.chunk`,
  `providerArguments` and `response_terminal` found only the prior PDF cause
  discussion. No historical provider wire was located by that search.
- Therefore the historical origin of `__v`/`__ns`/`ns` cannot be proven from
  upstream retained bytes. No deterministic translation repair is established.
  Do not strip these keys, synthesize `{}`, weaken validation, or claim model
  origin conclusively from these native records.

## Source chain

Pinned source: H021-ADAPTER02 private source `openai-codex-064c6b8`;
pin `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3` per assigned input.

- `ai-harness/tools/image/image.mjs:27`: actual `capabilitiesInput = z.object({}).strict()`.
- `image-mcp.mjs:25`: actual MCP tool registration passes `capabilitiesInput`.
- Pinned `codex-rs/core/src/tools/handlers/mcp.rs:496-527`: tool spec uses MCP
  conversion and attaches the native namespace separately from parameters.
- Pinned `codex-rs/tools/src/responses_api.rs:121-134`: normal MCP definition
  parsing/renaming does not create application argument keys.
- Current `translateResponses` maps native tuple to
  `sova_ns_mcp__image_image_capabilities`, preserves the empty parameters schema,
  and copies function argument strings into reconstructed Chat history.
- Current `ResponsesStream` accumulates ordinary function argument fragments and
  emits the raw accumulated string with native namespace/name/call ID.
- Pinned `codex-rs/core/src/mcp_tool_call.rs:143-154`: nonempty raw argument
  strings are parsed with `serde_json::from_str`; no `__v`/`__ns` injection or
  deletion exists at that conversion.

## New owned files and actual executed check

Only new repository files created by this investigation:

- `ai-harness/server/test/codex-image-native.test.ts`
  SHA-256 `cc0d084038403da6a83088bc9995aeb464683e3f44e15c956ee6b91098bdb02d`.
- `ai-harness/server/test/fixtures/codex-image-native-mcp.mjs`
  SHA-256 `18f18805e22574b3d0711c50882b5309c63e451c91460d4d662eeb7d2efdc4fe`.

Executed from this isolated repo using existing cached dependencies:

```sh
CODEX_NATIVE_FIXTURE_BINARY=/Users/agent/CodexProjects/llm-orchestration/tasks/H021-ADAPTER02-20260928/private/codex-0.158.0-macos-arm64 \
CODEX_NATIVE_FIXTURE_EVIDENCE_DIR=/Users/agent/CodexProjects/llm-orchestration/tasks/H024-ADAPTER01-20260928/private/native-image-final \
ai-harness/server/node_modules/.bin/tsx --test ai-harness/server/test/codex-image-native.test.ts
```

Result: 2 passed, 0 failed, 0 skipped, duration 1.351 seconds. Native binary
SHA-256 is enforced before launching:
`788a818fbb9596869c7a487554507cb8bdca17584b8671112b23f9e225ba35c8`.

The native test is opt-in; ordinary test execution without the binary variable
runs the adapter check and skips the native test explicitly. It does not download
a binary or dependencies. Synthetic provider binds only 127.0.0.1. Native HOME,
CODEX_HOME, workspace and environment are isolated with only a fixture token.

Five cases: valid `{}`, the three byte-exact historical argument strings above,
and additional negative numeric `{"ns":10}`. For each case the mock creates Chat
tool deltas, the real adapter emits Responses SSE, the pinned native App Server
executes the actual image MCP server with a mock image client, and the fixture
captures the exact stdin `tools/call` before schema validation. All five objects
arrive unchanged. Only `{}` invokes the mock client; all four invalid objects
produce native failed MCP lifecycle items and strict unrecognized-key errors.
The following native Responses request preserves the original argument string,
native tuple/call ID, and tool error. Exactly ten provider requests occur; there
is no provider retry, hidden argument repair, or real generation/edit operation.

Private final captures (do not put in Git):

- `private/native-image-final/native-image-capture.json` SHA-256
  `a1d1444049ee29dee6d9ab3036fec1ac58adacdbf822ccaf470158c2c02fdee8`.
- `private/native-image-final/native-image-result.json` SHA-256
  `31d1327780f89fde4e6d5e1236380aa4fbec0c4c87b9451a904d0a4f0d801bef`.

Native fixture process exit is recorded true. No thin image layer/build change
is required by these test-only files. Production `codex-responses.ts` was being
edited by the owning parent concurrently; after this pass its observed hash was
`7c9b8fda51230f3201e3bb6b3de7a94a67e14985e804e263d426e94958abd1ff`.

## Remaining acceptance boundary

This is transport/schema fixture evidence, not live image capability PASS.
Generation, guarded edit, and child image path remain NOT_TESTED here, with
operational image gate false. No unchanged live image replay is justified by
this finding. Next useful evidence must correlate a real upstream tool call's
ID/namespace/schema and raw-argument digest/shape to emitted Responses and native
MCP input under root's next reviewed combined acceptance assignment. Parent is
adding bounded diagnostic callbacks; W1 should record them with provider/request
identity. Historical captures must remain preserved and classified as incomplete.

## Follow-up: pinned MiMo reasoning serialization and native serial blocker

Historical checkpoint below: the initial serial flag blocker was subsequently
resolved for the offline adapter path by explicit root-reviewed policy adaptation.
See the final section; original captures and findings remain retained.

Parent assigned this extension at 17:05 UTC. New file only:
`ai-harness/server/test/codex-mimo-native.test.ts`, SHA-256
`87cde80e69136a30753027bdcaba64b28f7bc4199f0a41e435948e84aa94e5ec`
(final serial-emission correction; original checkpoint was `e6064dca...`).

Pinned `protocol/src/models.rs:1048-1061,1624-1631,1990-1993` supports the exact
item `{type:"reasoning",id,summary:[],content:[{type:"reasoning_text",text}],encrypted_content:null}`.
Its serialization preserves `ReasoningText`; `Text` alone does not establish the
same retained-content contract. No summary or encrypted substitute was used.

Two separate checks were deliberately kept distinct:

1. An explicitly synthetic **serial** adapter request (`parallel_tool_calls:false`)
   streams nonempty MiMo `reasoning_content`, then one tool call. The
   real Responses adapter emits the exact plaintext reasoning item and reconstructs
   the next Chat assistant `reasoning_content` with a separately constructed older
   two-call history and distinct tool-result identities/content intact. This is an adapter fixture, not actual
   native MiMo admission.
2. A direct synthetic Responses loopback sends that exact reasoning item plus two
   separate `image_capabilities {}` calls to pinned native App Server. The next
   actual native request retains the exact reasoning item (including ID, text,
   empty summary and null encrypted content), both native tool tuples/call IDs,
   and both successful mock MCP results. The **actual** native
   `parallel_tool_calls:true` is captured and the reviewed serial provider
   translator is asserted to reject that request. It is never silently rewritten.

Source-backed blocker: pinned `core/src/session/turn.rs:1561` sets prompt
`parallel_tool_calls:true`; `core/src/client.rs:1005` computes
`prompt.parallel_tool_calls && !model_info.use_responses_lite`. The reviewed
catalog uses `use_responses_lite:false`. That flag is also involved in native
instructions/tools transformation (`client.rs:912`) and transport headers, so
flipping it is not a demonstrated narrow fix. Both actual MiMo-native fixture
requests have true. The live/native-to-adapter MiMo path remains BLOCKED while
the explicit MiMo serial contract rejects true; no live MiMo PASS is claimed.
Parent notified root/W1 of this blocker during the session.

Final combined focused pass at 17:09 UTC, after parent provider/adapter source
arrived: 4 passed, 0 failed, 0 skipped, 1.406 seconds. Command is the image command
above with evidence directory `private/native-boundaries-final` and both
`codex-image-native.test.ts` and `codex-mimo-native.test.ts` test paths. This was a
necessary rerun after the parent changed the shared Responses source/provider
contract. No broad suite/build was run by this investigation.

Observed Responses source SHA-256 after the MiMo test was
`c831c9be5998fba1dfa1bc66dd09735681908ea2ba043f1c0e5c9be0dbf93a92`;
provider module SHA-256 was
`a8e0b6938e14e3e1ff048ee3cce89004adca3267d65dae6d7e2141a46393a20c`.
Parent still owns those files and may make subsequent changes.

Final private artifacts and SHA-256 (all outside Git):

- `private/native-boundaries-final/native-image-capture.json`:
  `769bdb34d3bd748a675d44668186aea9b7c23344b1b81d98a42d5f0498cbe761`.
- `private/native-boundaries-final/native-image-result.json`:
  `31d1327780f89fde4e6d5e1236380aa4fbec0c4c87b9451a904d0a4f0d801bef`.
- `private/native-boundaries-final/native-mimo-capture.json`:
  `3422d0b19272095c25fcd30664aa00dd11f110ccf1ca2c28d9fec886c3bcdef8`.
- `private/native-boundaries-final/native-mimo-result.json`:
  `d7566b6e06873b01b7e8d494a8b0bb001d8a10511f00e20d0eb453e75cc61fe9`.

Both native fixture processes exited. A scoped process check after the standalone
MiMo pass found no retained native fixture/MCP processes. `git diff --check` passed.
No source checkpoint was committed by this child agent; parent owns integration.

At parent review, the first synthetic serial fixture was corrected: provider
serial generation must not emit two tool indexes. Final test emits one call;
historical multicall retention is checked separately. The direct native fixture
still emits two calls only in its explicitly separate native serialization case,
where actual parallel=true is preserved and adapter rejection remains asserted.
Corrected MiMo focused pass: 2 passed, 0 failed, 0 skipped, 0.547 seconds.
Final private capture `private/native-mimo-serial-final/native-mimo-capture.json`
SHA-256 `6ec6a81e72b38299580dbeb003a9acc8e166a366c9ec65ef57f6f93eb708f08c`;
result digest remains `d7566b6e06873b01b7e8d494a8b0bb001d8a10511f00e20d0eb453e75cc61fe9`.

## Follow-up: actual manual compaction and fresh resume

Parent assigned a final native fixture extension. New test-only file
`ai-harness/server/test/codex-compaction-native.test.ts`, SHA-256
`8e82be586971abcf10f0fc0b3823d82bfeeb57d9e7e42ddd7d39a4c3a5629fb9`.

Executed opt-in with the same pinned Mac binary/cached server dependencies,
evidence directory `private/native-compaction-final`. Final result: 1 passed,
0 failed, 0 skipped, 0.666 seconds. No real model or VM.

Actual workflow uses three fresh App Server processes with one isolated saved
native home: first process starts thread and receives original prompt; second
process resumes exact thread and invokes `thread/compact/start` once; third
process resumes exact thread and runs recall once. All provider requests pass
through the real Responses translation/stream and deterministic synthetic Chat
responses. Exactly three provider requests, one compact RPC and two turn RPCs
occur. No request retry/replay or duplicate dispatch.

Observed compaction lifecycle exactly matches current engine expectations:

`turn/started -> item/started(contextCompaction) -> item/completed(contextCompaction) -> turn/completed`

All events retain the owned thread ID and the same compaction turn ID; started
and completed compaction items share the same item ID. Both resume RPCs preserve
the native thread ID. Original visible user text remains in both resumed thread
histories, including after compaction. Native rollout bytes saved before
compaction remain an identical prefix afterward. Resumed recall input contains
the deterministic summary/fact; native final output is `COBALT-731`.

This proves pinned native serialization/lifecycle through the real Responses
bridge, **not** local-model semantic recall or Linux production qualification.
The real CodexEngine initialization requires Linux platform attestation and
cannot directly consume the Mac binary without spoofing that attestation; no
attestation was spoofed. Source expectations were compared to actual RPC capture.
No engine repair is indicated by this fixture.

Private final artifacts:

- `private/native-compaction-final/native-compaction-capture.json` SHA-256
  `d46bb60a46b26f10aa4671c6312a945ae35e51434d843368b7f9a1675cd27639`.
- `private/native-compaction-final/native-compaction-result.json` SHA-256
  `059464fb50c6070cd72240093490bd9d6167117d5c897932243f71cc5d484979`.

All three fixture processes exited. `git diff --check` remained clean. These
new test files require no image layer/rebuild and introduce no public RPC API.

## Final 17:17 UTC: root-reviewed explicit serial adaptation, actual native bridge PASS

Root explicitly authorized adapting native `parallel_tool_calls:true` permission
to the selected MiMo provider's serial policy, with observable requested/effective
metadata. Parent implemented `translation.toolPolicy` and retained strict serial
output enforcement. This supersedes the **adapter/native offline compatibility
blocker** above; it does not convert any live qualification to PASS.

`codex-mimo-native.test.ts` final SHA-256:
`9f0e1117c987d44bced285fcd6b6e0adf59c8be4614baed9711e3ebfe77982a1`.
The test now exercises the complete actual native boundary rather than a direct
Responses bypass:

1. Actual pinned native MiMo request arrives with `parallel_tool_calls:true`.
2. Real `translateResponses(request, 65536, reviewedProvider)` records
   `{requestedParallelToolCalls:true,effectiveParallelToolCalls:false}` and
   produces an outbound Chat request with false. The captured original native
   request is unchanged.
3. Synthetic Chat emits exact nonempty `reasoning_content` plus **one** tool call;
   real `ResponsesStream` emits Responses SSE consumed by native.
4. Actual native invokes the actual strict image MCP server with a mock client.
5. Actual next native request preserves the exact emitted reasoning item, tool
   call ID/namespace/name/arguments and tool result. Real `translateResponses`
   reconstructs Chat reasoning_content, alias, call ID and result intact, again
   exposing requested=true/effective=false metadata.

Separate focused checks preserve older two-call history while new emission stays
serial, and assert an upstream attempt to emit tool index 1 fails closed.
Final focused result: **3 passed, 0 failed, 0 skipped, 0.554 seconds**. Exactly
two native provider requests; fixture process exited. No gateway admission,
tokenizer, real model, Linux runtime or deployment qualification occurred.

Command: same opt-in runner as above, file `codex-mimo-native.test.ts`, output
directory `private/native-mimo-serial-adaptation`.

Final private evidence (original blocker captures were not overwritten):

- `private/native-mimo-serial-adaptation/native-mimo-capture.json` SHA-256
  `d8b6312562e8d646695253bb5c9bc5a96faa9edeff7332663c64ac030430f6b6`.
- `private/native-mimo-serial-adaptation/native-mimo-result.json` SHA-256
  `93e131b835829d1ca7b0a880cce44dc9d6a6ee1253a0e6e61b994083785ee436`.
- Parent Responses source observed for this pass SHA-256
  `29d238b4f7b35dc8ba9409eb8028ce8dec38cd35c6ebe2b18cb18dc337489769`;
  provider descriptor module SHA-256 remains
  `a8e0b6938e14e3e1ff048ee3cce89004adca3267d65dae6d7e2141a46393a20c`.

Final owned repository files are four new test/helper files only: image test,
image MCP mock helper, MiMo test and compaction test. No existing production
files were edited by this child. No commits were made; parent owns integration.
