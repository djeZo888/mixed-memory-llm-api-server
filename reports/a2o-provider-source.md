# A2O pinned OpenCode provider source review

Date: 2026-09-15. **PASS for the supported source mapping.** This report does
not establish outgoing-request or real-model acceptance; the separate local
wire fixture must establish actual process behavior before V1 review.

## Exact implementation inspected

- Official OpenCode `v1.18.31` resolves to commit
  `014614d35b397775e5d397a490fc72368c894ec2`:
  [official tag reference](https://api.github.com/repos/anomalyco/opencode/git/ref/tags/v1.18.31).
- That version pins `@ai-sdk/openai-compatible` **2.0.41** in
  [package.json, line 71](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/package.json#L71).
  The compatible provider is bundled and selected through its official factory;
  the factory receives the provider ID as its name:
  [provider.ts, line 123](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/provider/provider.ts#L123),
  [lines 1831-1839](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/provider/provider.ts#L1831).
- The SDK's official version tag resolves through annotated tag
  `1d28226094dd98b2664799c8dd212f06606781b4` to commit
  `99327b1d7b3d172ed0aae7230ae153f2d32b0ebb`:
  [SDK tag object](https://api.github.com/repos/vercel/ai/git/tags/1d28226094dd98b2664799c8dd212f06606781b4).
  The published npm 2.0.41 chat implementation and option schema matched those
  exact official source files byte for byte. The
  [published package metadata](https://registry.npmjs.org/@ai-sdk/openai-compatible/2.0.41)
  has integrity
  `sha512-kNAGINk71AlOXx10Dq/PXw4t/9XjdK8uxfpVElRwtSFMdeSiLVt58p9TPx4/FJD+hxZuVhvxYj9r42osxWq79g==`.
- OpenCode's
  [pinned compatible-provider patch](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/patches/%40ai-sdk%252Fopenai-compatible%402.0.41.patch)
  only changes streamed error forwarding from the error's message to the error
  object; it does not alter the request option mapping.

## Supported configuration and request path

The supported configuration location is
`provider.local.models[model_id].options.reasoningEffort` with string value
`low`. It is a model generation option, not a provider-construction option,
variant selection, server flag, or reasoning-token budget.

| Step | Pinned official source evidence |
| --- | --- |
| Model options belong in the model's `options` object; agent options can override them | [OpenCode model documentation, lines 67-106](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/web/src/content/docs/models.mdx#L67) |
| The configured model options are retained | [provider.ts, line 1557](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/provider/provider.ts#L1557) |
| Each request merges model options after generated defaults, before agent/variant options | [llm/request.ts, lines 80-91](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/session/llm/request.ts#L80) |
| Compatible-provider options use the provider ID prefix; for this client it is `local` | [transform.ts, lines 1449-1465](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/provider/transform.ts#L1449) |
| OpenCode passes the mapped options to `streamText` | [llm.ts, lines 280-316](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/session/llm.ts#L280) |
| The SDK accepts optional string `reasoningEffort` | [SDK chat option schema, lines 12-15](https://github.com/vercel/ai/blob/99327b1d7b3d172ed0aae7230ae153f2d32b0ebb/packages/openai-compatible/src/chat/openai-compatible-chat-options.ts#L12) |
| The SDK reads the compatible/provider namespace and serializes `reasoning_effort` at the top level | [SDK chat implementation, lines 146-163](https://github.com/vercel/ai/blob/99327b1d7b3d172ed0aae7230ae153f2d32b0ebb/packages/openai-compatible/src/chat/openai-compatible-chat-language-model.ts#L146), [line 243](https://github.com/vercel/ai/blob/99327b1d7b3d172ed0aae7230ae153f2d32b0ebb/packages/openai-compatible/src/chat/openai-compatible-chat-language-model.ts#L243) |

The SDK schema accepts a string rather than checking a model-specific effort
enum. A2O therefore validates its deliberately narrow supported option in the
client generator. The SDK comment describing a default does not insert a value:
the serializer reads the optional property, so omission remains omission unless
OpenCode supplies a model-specific default. The existing generator's omission
behavior must remain intact; this review does not assign GLM semantics to other
model IDs.

## Streaming and nonstreaming boundary

The SDK has both `doGenerate` and `doStream`; both call the same request-argument
builder. Only `doStream` adds `stream: true`:
[SDK nonstream implementation, lines 257-275](https://github.com/vercel/ai/blob/99327b1d7b3d172ed0aae7230ae153f2d32b0ebb/packages/openai-compatible/src/chat/openai-compatible-chat-language-model.ts#L257),
[stream implementation, lines 360-384](https://github.com/vercel/ai/blob/99327b1d7b3d172ed0aae7230ae153f2d32b0ebb/packages/openai-compatible/src/chat/openai-compatible-chat-language-model.ts#L360).

The pinned ordinary OpenCode agent interface exposes a stream and invokes
`streamText`; it exposes no ordinary agent nonstream generation switch:
[LLM interface, lines 54-55](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/session/llm.ts#L54).
CLI `--format default` versus `--format json` controls output rendering/events,
not HTTP streaming:
[run.ts, lines 174-178](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/cli/cmd/run.ts#L174).
Actual-process evidence must therefore identify the observed transport. An SDK
unit test or source reading cannot be reported as an actual OpenCode nonstream
request. No unsupported adapter or transport override is needed for the
supported streaming path.

## Checks, limitations, and next action

- Checked the official tag, exact dependency, SDK tag, published source match,
  relevant source path, and OpenCode's SDK patch.
- Read the existing private installation's package metadata and native binary
  without modifying its config or state. Package metadata reports 1.18.31;
  the native binary contains the compiled top-level effort mapping. Its SHA-256
  is `16c960ba77421da11b53e785f359b73f328a86118b48feb4af143db5d9afb198`.
  The main A2O worker separately ran the actual native `--version` under an
  isolated task-private environment and obtained 1.18.31.
- Downloaded only public source/package material into task-private research
  storage. No VM, inference endpoint, model weights, real credential, global
  installation, or existing client config was used or changed by this review.
- **Next:** generate the optional setting through the reviewed bootstrap,
  capture allowlisted metadata from the actual pinned process against the local
  synthetic fixture, and verify every ordinary/tool/continuation request. Root
  review and later V1 real-model acceptance remain separate requirements.
