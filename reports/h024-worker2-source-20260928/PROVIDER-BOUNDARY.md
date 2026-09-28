# Provider boundary checkpoint

W1 contract received and used verbatim from task input. W2 changes only the
Responses adapter/fixtures and the runtime-to-child typed argument.

- `translateResponses(value, outputLimit=65536, provider?)` checks the explicit
  selected descriptor against the model contract. Qwen stays 480000/65536 with
  no reasoning; MiMo stays separately 950000/65536 with plaintext reasoning.
- MiMo emits actual upstream `reasoning_content` as pinned `reasoning_text`
  content, with empty summary and null encrypted content. It reconstructs that
  text on the associated Chat assistant message across tool continuations.
  Unknown/encrypted/summary-only/cross-provider/interleaved forms fail closed.
- Existing custom tool wrappers, raw ordinary tool arguments, namespace/call
  IDs, tool-result identities and terminal-drain order are retained.
- `CodexRuntime.qualifiedChildModels` is an optional trusted host policy. Its
  default is Qwen only; passed to W1's fourth `CodexChildren` constructor arg.
  Root/host qualification is still required to allow MiMo descendants.

## Explicit unresolved native flag incompatibility

Pinned `core/src/session/turn.rs:1561` sets `parallel_tool_calls:true`;
`core/src/client.rs:1005` retains it unless `use_responses_lite` is enabled.
Actual pinned native fixture requests confirm true. The reviewed MiMo provider
requires false, and W2 rejects the conflict. Changing `use_responses_lite` would
also affect prompt/tool construction; no such change or silent flag coercion
was made. Thus native-to-adapter MiMo operation remains blocked even though
plaintext reasoning serialization passes independently.

The native fixture uses direct synthetic Responses to prove pinned serialization
and separate explicitly serial synthetic Chat fixtures to prove translation.
It does not label their combination as an end-to-end MiMo success. No live
model request or hosted API key was used. Image/native vision/live frontier
gates remain closed; MiMo's 950K is configured capacity only.

## Compile dependencies owned by W1

W1 files were copied unchanged as local compile support and are excluded from
W2 commits. Root must integrate the matching W1 files with this checkpoint:
`server/src/codex-provider.ts` and `server/src/codex-children.ts` (four arguments).
The exact hashes are retained in the final source manifest. W2 did not edit
provider/gateway/host/catalog/children production files.

Independent source review additionally tightened two cases before checkpoint:
reasoning-only `stop` fails before canonical completion, and the serial MiMo
stream rejects an emitted second tool index. Old paired multi-call history is
still preserved; it is distinct from permission to generate a new parallel batch.
The typed descriptor retained by the stream is immutable.

Validation: 56 focused Responses/provider/namespace/engine/child tests passed
with the supplied W1 compile support. Native reasoning serialization is separately
recorded in IMAGE-TRACE.md; live route qualification remains blocked as above.

## Final reviewed serial adaptation (supersedes the initial flag blocker)

Root and W1 explicitly approved treating native `parallel_tool_calls:true` as
permission, not a required batch. Only the exact reviewed MiMo serial descriptor
now maps that permission to false. Translation retains immutable
`toolPolicy.requestedParallelToolCalls` and `effectiveParallelToolCalls`; both
provider-finish and canonical-terminal diagnostics copy those booleans. Qwen's
requested value stays unchanged. Serial output index validation, old history,
namespace/call/result identity and `tool_choice:none` rejection remain intact.
No native binary or `use_responses_lite` change was made.

The final pinned-native MiMo fixture now exercises the entire actual local mock
path: native request (true) -> real translator (effective false) -> synthetic
Chat plaintext reasoning plus one tool -> real ResponsesStream -> actual native
MCP -> next actual native request -> real translator. Exact reasoning/call/result
identity and requested/effective metadata pass. Earlier blocker captures remain
preserved privately. This is offline contract PASS, not live MiMo qualification.
See the final section of IMAGE-TRACE.md for exact hashes and scope.
