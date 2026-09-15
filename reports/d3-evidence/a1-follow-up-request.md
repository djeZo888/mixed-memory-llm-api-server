# D3 -> coordinator: tiny A1 reasoning request follow-up

2026-09-15. Source-only review; no VM contact, source patch, live request, or service change performed by this reviewer. Main D3 owns live proof. This request does not relax A1 acceptance or authorize changing the protected runtime invocation.

## Required small change

Add optional `--reasoning-effort` to `scripts/agent/acceptance.py` and optional `reasoning_effort=None` to `scripts/agent/protocol.py:Client`. Validate an explicit supported enum, preserve the current omitted default, and send a non-None value as top-level `reasoning_effort` on **every** chat request, including stream, auth probes, invalid-model probe and each tool continuation. Record the selected value in the report. For this GLM run use exactly `low`; do not substitute `minimal` or `medium`.

This is needed because current `Client.chat` (line 513) builds only model/messages/stream/max_tokens/tools. The current A1 CLI has no reasoning knob. Existing GLM deployment profiles already provide `--chat-template-kwargs {"clear_thinking":true}`; preserve that setting. The client deliberately removes reasoning from replayed assistant messages (`protocol.py:193-205`, `acceptance.py:49-56`), so no preserved/interleaved-reasoning claim is warranted without live continuation evidence.

### Pinned/runtime evidence

- Exact runtime commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, [server-common.cpp lines 1327-1354](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-common.cpp#L1327): request `chat_template_kwargs` merge over CLI defaults; top-level `reasoning_effort` is passed to the Jinja template. `none` separately disables thinking, so it is not equivalent to `low`.
- Same pin, [common/chat.cpp lines 882-889](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/common/chat.cpp#L882): reasoning effort reaches template capability handling.
- [Pinned Unsloth artifact card](https://huggingface.co/unsloth/GLM-5.3-GGUF/blob/346b3591c7f28d1a23716f97a065ecf12ec14771/README.md) and [official model card, Note](https://huggingface.co/zai-org/GLM-5.3-BF16#note): accepted GLM efforts are low/high/max; absent or other values default to max. Explicit clear_thinking=true is recommended for chat.
- Reviewed binary `--help` independently confirms CLI effort/budget controls in `reports/d1-cli-selected.txt:84-94`; using them would require a separate reviewed manager/profile change. The per-request knob avoids that change.

## Length diagnostic defect to fix alongside the knob

Current `_completion` and `_stream` call `_finish` before returning; `_finish` treats `length` as a generic termination error. `_request` only records model/usage/finish_reason after successful parsing (`protocol.py:490-493`). Thus a valid response exhausting all 2048 tokens can lose finish_reason and token counts in A1 evidence and be mistaken for tool/parser failure.

Keep `length` a failed/incomplete acceptance outcome. Add a bounded structured diagnostic for valid envelopes/streams reporting `finish_reason="length"`, returned token usage, model and an explicit `token_budget_exhausted` classification. Preserve strict tool-argument/ID validation and never execute a partial call. A dedicated termination exception carrying only bounded diagnostic fields is one small implementation option. For malformed partial JSON caused by truncation, preserve the observed length metadata independently and label parsing failure separately; do not silently accept malformed tool calls. Redact diagnostic provider values at the existing report boundary.

## Optional only after D3's independent low-effort probe

If explicit low effort still exhausts the output budget, request a second tiny knob `--reasoning-budget-tokens N` / `Client.reasoning_budget_tokens`, omitted by default, validating integer `0 <= N < max_tokens`. A conservative candidate for a 2048-token request is 256. The exact API field is `reasoning_budget_tokens`, **not** `reasoning_budget`.

[Pinned server-common.cpp lines 1293-1305](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-common.cpp#L1293) supports this field (and alias thinking_budget_tokens), but passes budget to sampling only when the template/parser supplies thinking_end_tags. [Pinned chat.cpp lines 1244-1250](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/common/chat.cpp#L1244) shows tag discovery. D3 must validate effective behavior before claiming a bounded reasoning budget. Do not add or activate this knob merely from this proposal.

## Smallest meaningful tests and verification

1. Synthetic HTTP: default request omits effort; configured low is preserved in nonstream, stream and tool-result continuation bodies; no reasoning_content is replayed; invalid types/enum fail before networking.
2. End-to-end synthetic acceptance: selected effort is recorded and sent consistently to every chat probe/agent round; existing default run remains unchanged.
3. Valid nonstream and complete SSE ending with length record token_budget_exhausted, finish_reason and usage, remain FAIL, and execute no truncated tool call. Include a length response with partial tool JSON and a normal malformed response without length to keep the classifications distinct. Retain missing [DONE], bad IDs/JSON and credential-redaction regressions.
4. If the optional budget knob becomes necessary, add omission/type/range and exact JSON-field tests. Do not bundle it into the first patch without the live need.

Worker verification:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_agent*.py' -v
python3 scripts/agent/acceptance.py --help
git diff --check
```

After coordinator reviews the tiny patch, add `--reasoning-effort low` to the reviewed A1 command. Run the bounded fixture once without `--stream-tools` and once with it (separate fresh report paths) to prove both nonstream and stream tool invocation/continuation; one run only covers one tool mode. Keep 2048 output tokens initially and record actual finish reasons rather than increasing the budget silently. Main D3 can independently issue an authenticated worker-side low-effort request before the patch is ready, capturing raw bounded response metadata and runtime timings.

## V1/OpenCode handoff

The reviewed V0 `scripts/client/client_common.py:152-163` config generator exposes model/context/output but no reasoning setting. `verify_install` rejects edited generated configs, so do not hand-edit the installed OpenCode config. V1/root should determine the pinned OpenCode 1.18.31 provider's supported low-effort source option and verify the actual outgoing request in a local synthetic fixture, then review a tiny source change if needed. The A1 knob alone does not establish OpenCode low-effort behavior or overall READY. Keep all fixture execution on the worker; no VM execution tools.
