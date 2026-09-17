# CLIENTNULL: nullable streaming deltas

Base: `91e962abb9dc7f8bcd2d8ba522b541cdd5f12f66`. Source-only work on
mac-worker2; scope is the agent protocol, its focused tests, and this report.
The coordinator's task-local `incoming.md` superseded the initial restriction
on per-chunk arguments nullability.

Explicit null now means omitted for streamed `delta.role`, tool-call
`id`/`type`/`function`, and function `name`/`arguments`. A null legacy
`function_call` placeholder is ignored; every non-null legacy call remains
unsupported. Existing nullable `content`/`tool_calls` behavior is unchanged.
Non-null type checks, assistant-only role, allowed function/tool keys, string
fragment concatenation, indexes, response bounds, model consistency, finish
reason and `[DONE]` requirements are unchanged. Final assembled calls still
require valid unique IDs, names and JSON-object argument strings; missing or
only-null argument fragments cannot form a valid call.

Primary justification: OpenAI's generated
[chat completion delta types](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/chat_completion_chunk.py),
retrieved 2026-09-17, lines 44–86: these fields are optional, while tool index
is a required integer. Retrieved source SHA256:
`44bc28a96e088a6aa176b9426c495649d52b708fd7dab7f652cad75cf188bb08`.

The supplied Worker1 account describes a 2359-byte, eight-event native Qwen
stream rejected first at `role:null`, before tool execution or continuation;
it reports backend READY. No private wire/artifact was read or copied here.
Tests use synthetic identifiers/model metadata and representative fragmented
`read_file` arguments only. This change establishes no live inference, agent,
context or VM acceptance; control protocol, source inventory, runtime,
configuration, fixtures and installer remain untouched.

Validation: **PASS**, 51 tests in 1.065s, one focused run of
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_agent_protocol.py -v`.
Synthetic nullable/fragmented streams and invalid metadata/final identities/
arguments pass alongside existing finish/DONE, indexes, model, bounds and
normal-stream regressions. Exact three-file scope, whitespace and quiet secret
pattern scan checked before commit; no broad suites run.
Next action after the incremental bundle: coordinator integration and separately
authorized live acceptance. This task stops at the bundle without publication.
