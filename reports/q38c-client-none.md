# Q38C explicit none: pinned OpenCode wire proof

2026-09-15. **PASS: reasoning option and actual client-to-synthetic-server proof.**
Final evidence is taskroot `wire-run-2`; publication details are recorded below. **Live Q38 native
formatter and agent quality: NOT_TESTED** by Q38C, pending authorized Worker1/V1 gates.

## Scope and option contract

Base `6ffd620`, branch `milestone/q38c-client-none`, worker2 source session.
Read AGENTS, current roster and incoming at phase boundaries. Exactly GLM 5.3
and Qwen3.8-27B FP8 are current targets. No installer, VM access, inference,
model download, runtime/control/Manager/agent edit, service activation or reboot.
N1C owns endpoint work; V2 owns verifier files. URL/CA/environment code is unchanged.

Only the reasoning validator in `client_common.py` and reasoning help in
`bootstrap.py` change production code. Literal strings `none` and `low` are
accepted; null, booleans, numbers, collections, string subclasses, other enums,
casing and whitespace are rejected. Omission retains the existing config and
manifest shape. `none` is an explicit value, never a synonym for omission.

The existing model option path remains
`provider.local.models[model].options.reasoningEffort`. Strict generated-config
verification and identical-repeat behavior remain intact. Every change among
omission/none/low requires a fresh private prefix; no installed files are patched.
GLM low behavior is retained. The Q38 fast profile selects none explicitly.

## Exact pinned client and serialization

| Component | Exact version / identity | Evidence kind |
| --- | --- | --- |
| OpenCode wrapper / native / plugin | 1.18.31 | Actual private package metadata; bootstrap checks native `--version` on installation and identical repeat |
| OpenCode source | `014614d35b397775e5d397a490fc72368c894ec2` | Official v1.18.31 source |
| Bundled AI SDK `ai` | 6.0.168 | Exact source root catalog and resolved bun.lock; not a separately installed SDK substitute |
| Bundled `@ai-sdk/openai-compatible` | 2.0.41 | Exact OpenCode package source and existing A2O published-source comparison |
| Bundled direct `@ai-sdk/provider` | 3.0.16 | Exact OpenCode package source |
| Actual macOS arm64 native SHA256 | `16c960ba77421da11b53e785f359b73f328a86118b48feb4af143db5d9afb198` | Hash of each of five installed binaries |

[Root package catalog](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/package.json#L67),
[resolved lock](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/bun.lock#L3055),
[OpenCode dependencies](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/package.json#L71).
These small primary files were fetched again in Q38C. Root package SHA256:
`b1aa48ddbe8074072e308daf98e30eba2596fd2ad479bbbe061d04504b7a757e`;
lock: `0b2900f5353569f871b55346ddcbd1a6ddceb7577295bba5a38480a6d94c3161`;
OpenCode package: `778160ff537cfb76b0abdb160292e48268f1d900a29e8e9276863b67d0fca19d`.

The model option overrides generated defaults for both ordinary and small/title
requests in [request preparation](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/session/llm/request.ts#L76-L84).
The compatible SDK serializes it to **top-level `reasoning_effort`** in its
[pinned argument builder](https://github.com/vercel/ai/blob/99327b1d7b3d172ed0aae7230ae153f2d32b0ebb/packages/openai-compatible/src/chat/openai-compatible-chat-language-model.ts#L243).
See [A2O's complete provider path](a2o-provider-source.md) for the namespace and
published source comparison. No generic provider-options mapping is assumed;
no adapter, SDK substitute, body injection or manually edited config is used.

## Primary SGLang / exact model no-thinking proof

**No per-request `chat_template_kwargs` field is required** for this exact
contract. The observed wire is top-level `reasoning_effort:"none"`, model
`qwen3.8-27b`, `stream:true`, with no template/reasoning/body override.
Reviewed server default: `--default-chat-template-kwargs '{"enable_thinking":false}'`.

SGLang v0.5.19 resolves to **`0bcd822377da7b5718e674eaf9c870d349424dd1`** via
[official tag](https://api.github.com/repos/sgl-project/sglang/git/tags/59f20bffdde59a35cc628372d85d20a979f6271b).
Model: **Qwen/Qwen3.8-27B-FP8@017b9c7af6b5689d5dd426a76e0bc077eb5ca20a**;
[config](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/blob/017b9c7af6b5689d5dd426a76e0bc077eb5ca20a/config.json)
names Qwen3_5ForConditionalGeneration/qwen3_5.

1. [Request normalization, protocol.py:1025–1038](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/protocol.py#L1025-L1038)
   turns literal none into `thinking:false` and `enable_thinking:false`, using
   setdefault. These are backend-produced values, not observed client fields.
2. [Default merge, serving_chat.py:1104–1111](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/serving_chat.py#L1104-L1111)
   also uses setdefault, preserving both false switches.
   [Jinja preparation, 1357–1414](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/serving_chat.py#L1357-L1414)
   passes effort none and those switches to tokenizer.apply_chat_template,
   including its fallback. Neither path re-enables thinking.
3. The [exact model template](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/blob/017b9c7af6b5689d5dd426a76e0bc077eb5ca20a/chat_template.jinja)
   gates effort validation/instructions on thinking enabled (lines 46–56).
   With false it appends a closed empty think block (163–169), including after
   tool-result history. The [pinned card](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/blob/017b9c7af6b5689d5dd426a76e0bc077eb5ca20a/README.md#L454)
   demonstrates false to disable thinking; none is SGLang's normalized off switch,
   not one of the card's enabled-thinking effort levels.
4. [Encoder selection](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/chat_encoding.py#L108-L143)
   chooses no special Python encoder for this architecture/parser.
   [Template loading](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/parser/template_manager.py#L145-L174)
   uses the checkpoint template. [Toggle detection](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/parser/template_detection.py#L147-L208)
   recognizes enable_thinking, with no always-on override for this template.
   [Request reasoning mode](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/serving_chat.py#L2430-L2505)
   therefore stays false. Native renderer/parser verification remains Q38B's gate.

Downloaded primary SHA256s: protocol.py
`a7cf91c1db5d076b9ad647248351f10b0249153998b974ed4d00610306b01653`;
serving_chat.py `7b05e6ab1d09a71ce253040c9cd62ea7c55a52020b44cf9b76d91c8df9e23240`;
model template `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`;
model card `a247d876f5398eed9ae898f32a984083552de57237b5e20714657e1675e26d2e`.
Exact source inspection and five extracted-statement checks passed; those
stdlib AST checks did not import SGLang/Pydantic/Transformers or render a model.
The full research note, 13-file source/hash manifest and check helper remain in
taskroot `research-q38c/` for review. They are not native execution evidence.

**Boundary:** explicit true template overrides can win; input_ids can bypass
templating. The client fixture rejects these fields. `low` normalizes true
before server defaults merge, so it would re-enable Qwen thinking despite the
false default. This is why Q38 needs explicit none and must not inherit GLM low.
The proof assumes the reviewed default, exact source/model/template identity,
normal chat messages and no conflicting overrides. It does not promise that
a model can never emit an unexpected reasoning marker.

## Actual synthetic wire run

The [allowlisted evidence](q38c-wire-evidence.json) is generated by the
[actual-CLI fixture](../scripts/client/tests/wire_fixture.py), using five fresh
private prefixes and the committed npm lock. Each install and identical repeat
checks the real native version. Each launcher executes ordinary and tool sessions
in a trusted disposable workspace, with no network or bash/edit tool grants.

| Selection | Requests | Effort on every request | CLI events | Completed reads |
| --- | ---: | --- | ---: | ---: |
| Default GLM | 5 | omitted | 9 | 1 |
| GLM low | 5 | low | 9 | 1 |
| Generic synthetic ID low | 5 | low | 9 | 1 |
| Default Qwen | 5 | omitted | 9 | 1 |
| Qwen none | 5 | none | 9 | 1 |

**10 cases, 25 HTTP requests, 45 CLI events, 5 actual read tools / two-round loops.**
Each selection produces two recognized title requests, one ordinary request,
one initial tool request and one continuation. Title identification uses the
exact pinned [title request marker](https://github.com/anomalyco/opencode/blob/014614d35b397775e5d397a490fc72368c894ec2/packages/opencode/src/session/prompt.ts#L193-L236).
All requests pass effort validation before classification. The listener counts
all HTTP methods, rejects unexpected methods/paths, and requires received and
validated counts to match. Every request has stream true and no template/body
injection. No requests are discarded for being auxiliary.

The server supplies a read tool call, then OpenCode actually reads a private file.
Its unpredictable marker must appear in a completed read event and in the next
HTTP request with the same assistant/tool call ID. Final text, unchanged fixture
contents and no extra workspace files are required. Ordinary sessions have
3 CLI events; tool sessions have 6. Synthetic response/usage values are fixture
inputs, not measured model performance. Configured 32768 context / 2048 output
are fixture limits, not live Qwen/GLM capacity qualification.

Headers, keys, raw bodies and CLI transcripts stay out of published evidence.
Only fixed metadata/counts, source hashes and package versions are retained.
The generated protected key is scanned for accidental persistence and removed;
process groups and listener are cleaned up. Work roots must be new and outside
any Git checkout/worktree. Five actual package installs use task-private storage;
no global install or inference software build occurs.

## Verification, warnings and next action

| Check | Result |
| --- | --- |
| Strict reasoning option tests | PASS: 22 |
| Full client suite with actual installed none-prefix check | PASS: 51, no skips |
| Unchanged A1 suite | PASS: 94 |
| Final actual pinned OpenCode synthetic run | PASS: 10 cases / 25 requests / 45 events / 5 read loops |
| Five fresh installs and identical repeats; all native/package pins | PASS |
| Every none/title/ordinary/tool/continuation wire field | PASS; no extra template field |
| Default GLM/Qwen omission and low GLM/generic | PASS |
| Source hash binding, private key scan/removal, listener/process cleanup | PASS |
| Exact per-function ownership via AST comparison | PASS; all unrelated code unchanged |
| Python 3.10 syntax, bootstrap/fixture help, whitespace/local links | PASS |
| Independent source/wire/report review | PASS; HTTP method accounting strengthened |
| Native SGLang formatter/parser, live Q38 agent, VM/network exposure | NOT_TESTED |
| Linux execution / nonstream OpenCode agent path | NOT_TESTED / NOT_SUPPORTED by this CLI path |

Final client command used `V0_CLIENT_PREFIX` pointing to taskroot
`wire-run-1/none-qwen`; it checks real version/config without inference. Final
wire run independently checks all five new `wire-run-2` prefixes. Evidence hashes
match the final generator, launcher, package lock and wire fixture sources.

**Warning:** an independent concurrent guard run hit EPERM in the pre-existing
process-group descendant-cleanup test (6/7 guards passed). The main initial
50-test suite and final 51-test suite both passed that same test, with ResourceWarning
escalated; both actual wire runs passed process cleanup. The discrepancy is
recorded rather than hidden. No production cleanup code was changed for it.

Reproduce offline checks and opt-in actual wire run using
[documented commands](../docs/client-install.md#regressions-and-upgrade-policy).
The latter requires npm HTTPS for the locked client packages and an unused
private task root; it has no external inference endpoint or key input.
All observed agent HTTP requests stream. Ordinary OpenCode 1.18.31 exposes no
nonstream agent switch; no nonstream CLI or SDK substitute is claimed.

Early `handshake.md` and Q38B incoming notice coordinate exactly top-level none,
absent per-request template kwargs, reviewed false server default and ordinary/
tool-continuation native gate. Q38B owns server source. Worker1/V1 must verify
actual native prompt/parser behavior and live agent quality after authorization.
Private-network exposure belongs to N1C/Worker1/V2 and was not exercised here.

Publication is feature-branch only, with exact author AND committer
`CodexAIagent <133749519+djeZo888@users.noreply.github.com>`. The taskroot
`final.md` and `publication.json` record source SHA, session, safe remote-SHA
verification and full `Q38C.bundle` validation. No main push.
