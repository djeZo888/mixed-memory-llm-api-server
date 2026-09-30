# H034 Qwen capability-query compatibility

The retained full original request failed with its empty-object capability contract.
A new explicit read-only `{"query":"capabilities"}` contract passed three short
provider probes: original context with strict true, retained error-feedback context
with strict true, and original context with strict false. The contract change is
supported by these bounded observations. Strict mode alone is not the demonstrated
reason for improvement, and this is not a completed image-workflow qualification.

## Source change and ownership

`codex-provider.ts` now enables Qwen request-level strict enforcement only for
namespace `mcp__image`, function `image_capabilities`, and the exact reviewed query
schema: object, one required string `query`, singleton enum `capabilities`, closed
additional properties. It accepts either the probe schema or that schema with the
actual MCP draft-07 `$schema` marker; unknown dialects and all other schema shapes
are not promoted. Existing explicit strict values remain unchanged. MiMo, other
namespaces/tools, the original empty schema, AUTO choice, parallel policy,
descriptions, schemas, raw arguments and error feedback retain their behavior.
No invalid arguments are stripped, filled or converted to success.

The one translation call in `codex-responses.ts` applies this policy before native
inference. W2 owns the paired explicit MCP schema/handler, instructions and policy
pins. The actual W2 `tools/list` descriptor was inspected: SHA-256
`8c1984c1d6829a21a82485d91fd42762798c592fddff53ffbdc36796336adc46`.
Tests use its exact schema including the optional native-boundary dialect marker.
The live probes used the new query schema without the MCP marker and the original
description plus a short query instruction; W2's final descriptive wording is not
relabelled as already live-tested.

## Eight bounded probes

Initial grant: six calls. Root's 17:35 inbox authorized exactly two additional
fixed contrasts (07/08). Every call used the same installed GPU0 Qwen identity,
AUTO, nonthinking profile, at most256 output tokens and120-second HTTP timeout.
No model-generated tool, shell command, MCP action or image job executed.

| Case | Input tokens | Output tokens | Guarded seconds | Actual result |
|---|---:|---:|---:|---|
| 01-minimal | 332 | 22 | 18.867 | PASS {} |
| 02-retained | 12128 | 65 | 21.546 | FAIL extra prompt/references/seed/size |
| 03-strict-auto | 12128 | 256 | 27.071 | FAIL length256, missing arguments |
| 04-empty-guidance | 12165 | 43 | 21.104 | FAIL extra references/size |
| 05-minimal-strict | 332 | 26 | 19.381 | PASS {} |
| 06-parameterized-query | 12166 | 33 | 20.673 | PASS query=capabilities |
| 07-feedback-query | 12265 | 33 | 20.251 | PASS query=capabilities |
| 08-query-nonstrict | 12166 | 33 | 20.931 | PASS query=capabilities |

Total: 73,682 input and 511 output tokens.
Guarded seconds include admission and postguard reads; they are not pure inference
latency. Case03 reached256 tokens with a function name and zero argument bytes;
normalization rejected `Tool finish mismatch`. It was not coerced to `{}`.
Case01 and05 produced real complete empty calls, so this evidence does not support
a global empty-object, namespace or Qwen incompatibility claim.

## Source discrimination

The adapter already preserved schema, strict flag, call IDs, arguments and feedback.
The installed template matches pinned SHA-256
`c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`.
Installed SGLang source routes strict AUTO tools through Qwen structural tags.
XGrammar0.2.1 explicitly maps strict:false tool parameters to unconstrained `true`.
The retained apply_patch wrapper was already strict:true, requesting structural tags,
while image_capabilities strict:false left its argument schema unenforced.

CPU-only inspection of the installed empty-object grammar accepted the complete
two-newline XML form, rejected an extra parameter and accepted ordinary AUTO text.
The pinned template renders an empty history call with one newline; that form was
rejected by the strict grammar. Its empty payload allows arbitrary whitespace.
These are measured static format differences, not proof that case03 generated a
whitespace loop or that its runtime compiler was defective. The parser emits a
function name before closing the call and emits `{}` only after the close tag;
SSE alone does not expose the hidden in-call text. No runtime/template change was made.

## Verification and settlement

39 focused tests passed across Qwen compatibility, Responses, provider, namespace
and diagnostics suites. TypeScript typecheck and build passed. Reused dependencies have the
same server package-lock SHA-256
`4a856f31e26e89171b743e4f1e6e194b9e88a862d5e0f77fd597b03c0533c401`.
New tests cover the actual MCP schema, canonical boundary form, changed/omitted
schema fields, namespace lookalikes, MiMo preservation, raw invalid/omitted arguments,
matched error feedback, truncated calls, valid queries and ordinary AUTO text.

All8 calls returned HTTP200, healthy EOF, DONE and usage, with unchanged current
instance identity and passing before/after production identity/hardware/capacity
checks. App active/queued counts and current gateway unsettled records were zero;
post-call GPU0 inference TCP checks were empty. The existing two historical uncertain
owners and three quarantines were not modified or reconciled. A first helper
preflight wrongly expected the two historical uncertain owners in the gateway table;
it rejected before generation. Read-only inspection showed zero unsettled gateway
records, and the predicate was corrected to require zero. This was not an inference
retry and remains in the private ledger.

Native worker thread: `01a0ee2c-ef8f-75c3-a8ad-3b38de7fa52d`.
Base: `efde32a0bb2057d014d5168b3a613fc3dbccd801`.
Raw prompts, requests, responses and source captures remain private outside Git;
selected metrics/hashes are in RESULTS.json and SOURCE-MANIFEST.json. The task output
contains the private-evidence manifest, test logs, patch and commit bundle. Final
native process exit is recorded by the outer wrapper, not predicted here.

No push, deployment, configuration/ticket change, runtime/model reload, hardware
change, long-context test, MiMo inference or full image workflow occurred. Coordinator
and W2 exact review plus integrated acceptance remain necessary before deployment.
