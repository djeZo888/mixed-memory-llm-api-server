# Bounded client and API acceptance

A1 supplies a Python 3.10+ standard-library Chat Completions client and a bounded
acceptance harness. Tools execute on the client worker. The inference VM serves
only the model API; install no agent, browser, or OpenCode on `ai-vm`.

**A1/A2A synthetic regression results are separate from live acceptance.** No live
inference, key retrieval, or OpenCode installation is part of A1/A2A. V1 must wait
for the reviewed A2A source bundle before using the new effort option. Coordinate V1
with Worker1 after it publishes the endpoint, exact API model ID, context and
output limits, reasoning/tool-parser settings, and authentication policy. Older
30B deployment claims in the handoff are stale. The GLM flagship and Qwen fast
model plan does not establish which model is currently serving.

## Local verification now

Run from the repository root on the client worker:

```sh
python3 scripts/agent/acceptance.py --help
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_agent*.py' -v
python3 -m json.tool scripts/agent/opencode.template.json >/dev/null
git diff --check
```

The regression suite uses deterministic HTTP fixtures bound to loopback and
fresh temporary workspaces. It does not contact the inference VM. No pip
packages, GPU stack, or backend installation is required.

## Optional reasoning effort

`--reasoning-effort VALUE` and the Python `Client(..., reasoning_effort=None)`
argument select an optional request field. The default is `None`: the client
**omits** `reasoning_effort` from JSON, preserving the endpoint's existing
default. An explicit selection is sent as the top-level `reasoning_effort` on
every Chat Completions request: ordinary and authenticated probes, missing/wrong
credential probes, the invalid-model probe, nonstream and streaming requests,
initial tool requests, and every tool-result continuation. It is not placed in
`chat_template_kwargs`. There is no arbitrary request-body injection option.
The report records the selection at `limits.reasoning_effort` (`null` when
omitted).

The client validates this exact generic enum before any HTTP request:
`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. Other values and
non-string values other than `None` fail locally. This list spans possible
backend conventions; it does **not** mean every backend or model accepts every
value. Use only a value confirmed by the runtime/model owner.

For the reviewed D3 GLM run, use exactly `--reasoning-effort low`. Its reviewed
template accepts only `low`, `high`, and `max`; absent or unsupported template
values can default to `max`. The pinned runtime handles `none` separately to
disable thinking, so `none` is not equivalent to `low`. D3's source evidence is
the [pinned runtime handling](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-common.cpp#L1327)
and [pinned GLM artifact card](https://huggingface.co/unsloth/GLM-5.3-GGUF/blob/346b3591c7f28d1a23716f97a065ecf12ec14771/README.md).

Keep the reviewed `clear_thinking=true` setting configured server-side. The
client still excludes returned reasoning from replayed assistant messages;
the effort option adds no preserved/interleaved-reasoning compatibility claim.
There is no client reasoning-budget option. Keep `--max-tokens 2048` for the
initial coordinated D3 verification and review actual termination evidence
before changing budgets.

Reproduce a synthetic acceptance report, including authenticated mock requests,
streamed tool calls and real fixture tests, in a fresh worker directory:

```sh
umask 077
export A1_SYNTHETIC_RUN="$(mktemp -d "${TMPDIR:-/tmp}/a1-synthetic.XXXXXX")"
python3 tests/test_agent_acceptance.py \
  --write-evidence "$A1_SYNTHETIC_RUN/synthetic.json"
```

The command refuses an existing report path and starts only its own dynamic
loopback mock endpoint. Compare its evidence structure with the committed
[`a1-synthetic-evidence.json`](../reports/a1-synthetic-evidence.json); timings and
temporary paths vary. Synthetic evidence proves the harness, not a live model.

## Live run after the Worker1 handoff

These commands are for coordinated V1 after bundle review, **not execution
during A1/A2A**. Set the
following to the actual values Worker1 publishes; do not infer them from old
profiles. Use a separate terminal for the tunnel and keep it open:

```sh
export A1_BACKEND_PORT='REPLACE_WITH_WORKER1_PORT'
ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -N \
  -L "127.0.0.1:30002:127.0.0.1:${A1_BACKEND_PORT}" ai-vm
```

The forwarding listener and backend remain loopback-only. SSH supplies the
encrypted connection and SSH authentication. No VM listener or service change
is needed. In the client terminal:

```sh
export A1_MODEL='REPLACE_WITH_WORKER1_API_MODEL_ID'
export LLM_BASE_URL='http://127.0.0.1:30002/v1'
umask 077
export A1_RUN="$(mktemp -d "${TMPDIR:-/tmp}/a1-live.XXXXXX")"
export A1_RUN="$(cd "$A1_RUN" && pwd -P)"
```

### Protected key file

D2 intends an authenticated backend using a protected VM key at
`/data/services/secrets/llm-api-key`, subject to runtime support. A1 does not
retrieve it. V1 must obtain the agreed credential through the coordinated
protected transfer, or an operator can enter it locally without terminal echo
or a shell-history value:

```sh
export A1_KEY_FILE="$A1_RUN/llm-api-key"
python3 - <<'PY'
import getpass
import os
key = getpass.getpass('API key (hidden): ')
if not key or len(key) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key):
    raise SystemExit('Expected a nonempty printable ASCII key without whitespace, at most 8192 bytes')
fd = os.open(os.environ['A1_KEY_FILE'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(key)
PY
```

Use a regular file owned by the current user with mode `0600`, in a directory
with mode `0700`. Keep it outside the repository. Never print it, paste it into
a command argument, add it to a real `.env` committed to Git, or include it in a
report. The CLI also accepts `--api-key-env LLM_API_KEY` for an already securely
supplied environment variable; choose one credential source. The report
redacts the configured key, including values echoed by an endpoint. Avoid
shell tracing and HTTP debug logging around credentials.

### Authenticated acceptance

```sh
python3 scripts/agent/acceptance.py \
  --base-url "$LLM_BASE_URL" --model "$A1_MODEL" \
  --api-key-file "$A1_KEY_FILE" --auth enabled \
  --request-timeout 120 --overall-timeout 900 --test-timeout 10 \
  --max-rounds 12 --max-tool-calls 32 --max-tokens 2048 \
  --max-output-bytes 16384 --max-response-bytes 262144 \
  --report "$A1_RUN/report.json"
```

This checks missing, deliberately wrong, and correct credentials. The wrong
credential is generated locally; it is not read from another account or file.
Rejection must be an authentication error, not a transport failure.
For D3's reviewed GLM command, add `--reasoning-effort low` after review of the
A2A bundle. Omit the option for other endpoints unless their owner confirms the
appropriate effort value.

If Worker1 explicitly publishes a backend with authentication disabled behind
the loopback SSH tunnel, use:

```sh
python3 scripts/agent/acceptance.py \
  --base-url "$LLM_BASE_URL" --model "$A1_MODEL" --auth disabled \
  --request-timeout 120 --overall-timeout 900 --test-timeout 10 \
  --max-rounds 12 --max-tool-calls 32 --max-tokens 2048 \
  --max-output-bytes 16384 --max-response-bytes 262144 \
  --report "$A1_RUN/report.json"
```

Disabled authentication tests are labeled skipped, not passed. Optional
`--stream-tools` streams the agent rounds as well as the standalone streaming
probe. Run a second coordinated acceptance with that option to exercise live
streamed tool arguments, using a new `--report` path such as
`"$A1_RUN/report-stream-tools.json"`. Report files are mode `0600`; existing
reports are never overwritten. `--workspace-parent "$A1_RUN"` can place the fresh
disposable fixture under the protected run directory; it does not permit the
model to access an existing project. The harness removes its fixture after
capturing evidence. Preserve the report separately before removing the run
directory or credential file.

Both separate runs are required for D3 continuation evidence: one without
`--stream-tools` and one with it, each with `--reasoning-effort low`, unchanged
initial token limits, and a fresh report path. A single run exercises only one
tool mode even though the standalone streaming probe always runs.

`--max-output-bytes` bounds tool arguments and results; `--max-response-bytes`
bounds HTTP bodies and accumulated request conversations. `--max-tokens` is
sent to the endpoint for each completion, while `--max-rounds` and
`--max-tool-calls` bound the full agent loop. The request, test and overall
deadlines include incomplete/slow responses. The fixture parent must have no
symlink ancestors; `pwd -P` above resolves macOS system temporary-path aliases.

## What acceptance proves

The protocol probes cover `GET /v1/models`, nonstream chat, streamed content
and stream termination, an invalid model, and native tool-result continuation.
The model ID is configurable; record both the requested identity and identities
the API actually returns. A backend silently serving a different or unknown
model must not be reported as a successful invalid-model rejection.

The fixture starts with a bug and an actual failing test. Success requires
model-requested reads of relevant fixture files, an implementation write, a
model-requested `run_tests` execution that actually passes, and a final
independent verification. An assistant statement that tests passed is not
evidence. Tests remain immutable to model writes and are checked for tampering.
The report records the initial real failure, executed calls and their IDs,
actual implementation diff, model-requested test output/status, final real test
status, model identity, elapsed time, and usage when supplied by the API.
Unavailable usage is unavailable, not zero. Reasoning is kept separate from
assistant content and tool results.

The harness records returned reasoning separately and does not replay it in
later assistant messages. Some provider modes require that replay: Z.AI's
documented preserved-thinking mode requires the original `reasoning_content`
sequence. V1 must check the published runtime/parser mode against this
continuation contract; this harness does not establish compatibility with
preserved-thinking modes. [Z.AI thinking mode](https://docs.z.ai/guides/capabilities/thinking-mode)

### Token exhaustion and malformed responses

A valid completion envelope, or complete SSE stream ending in `[DONE]`, with
`finish_reason="length"` remains **FAIL/incomplete**. The protocol raises
`CompletionError` before returning a message for tool execution. Its diagnostic
records `classification="token_budget_exhausted"`, `finish_reason="length"`,
returned model identity, returned usage, and `stream_done` (`false` for
nonstream, `true` for complete SSE). The same fields are retained in the failed
request record, and the failed probe or agent run includes a `diagnostics`
object. This records observed exhaustion; it does not establish that increasing
the limit would make acceptance pass.

Diagnostics contain only bounded allowlisted fields. Model identity is at most
1024 printable ASCII characters; control/non-ASCII text is omitted as `null`.
Usage includes only nonnegative integer counts up to `2**63 - 1`:
`prompt_tokens`, `completion_tokens`, `total_tokens`,
`prompt_tokens_details.{cached_tokens,audio_tokens}`, and
`completion_tokens_details.{reasoning_tokens,audio_tokens,accepted_prediction_tokens,rejected_prediction_tokens}`.
Unavailable or unusable usage is `null`, not zero. Unknown provider fields,
response text, reasoning text, and tool arguments are excluded from termination
diagnostics and exception messages. Provider diagnostic values are redacted at
the report boundary; the configured credential is never diagnostic evidence.

If a length-terminated response also contains incomplete tool-argument JSON or
another invalid reconstructed assistant message, the length metadata survives
and `parsing_failure="invalid_assistant_message"` records the separate
validation failure. No partial call executes. Strict ID, duplicate-key, and
tool-argument validation still apply. A malformed response without observed
length retains its ordinary safe validation error. A missing `[DONE]` or
unfinished SSE event retains its incomplete-stream error, even if a length
finish was seen; it does not establish a complete token-exhaustion response.

Only `read_file`, `write_file`, and `run_tests` are available. Reads are limited
to `calc.py` and immutable `test_calc.py`; only `calc.py` may be written. The
fixed command is `python3 -I -B test_calc.py`, using the client's Python
executable in the disposable directory with a scrubbed environment. The model
cannot supply a shell command or change the test invocation. The fixture accepts
only a narrow arithmetic Python AST, not arbitrary Python programs. Absolute
paths, traversal, symlinks/escapes, unknown tools, bad schemas/JSON, invalid or
duplicate call IDs, and output/time/round overruns fail closed. Independent
reads may be grouped; dependent changes and testing must use separate rounds
when a batch is incompatible. A fresh directory is an isolation boundary for
this restricted fixture, not a general-purpose operating-system sandbox.

| Result | Interpretation and next step |
| --- | --- |
| PASS, synthetic suite | Client behavior passed deterministic worker tests; live model behavior remains unproven. |
| PASS, coordinated live report | The specified endpoint/model completed this bounded protocol and fixture run. |
| FAIL, HTTP/auth/model/protocol | Check the reported status and Worker1 handoff; do not patch the server to satisfy the client. |
| FAIL, path/schema/ID/batch | The model emitted an unsafe or incompatible call; inspect the redacted call/error and retry only after understanding it. |
| FAIL, timeout/token/round/output limit | The run was incomplete; agree suitable budgets and server context/output limits before another live request. |
| FAIL, no real edit or no passing tool test | The model did not establish the required repair, regardless of its final answer. |
| NOT_TESTED or skipped | No success evidence for that check. Auth disabled does not prove authentication works. |

## OpenCode provider template for V1

OpenCode plus the generic API client is the selected client path. A1 verifies
the documented configuration and ships
[`opencode.template.json`](../scripts/agent/opencode.template.json); **OpenCode
E2E remains NOT_TESTED until V1 runs the actual CLI against the published
endpoint**. Harness success does not establish OpenCode compatibility.
The generic A2A effort option does not configure OpenCode. A2O owns the separate
`scripts/client` integration; V1 must use its reviewed source and validate the
actual outgoing effort field. Do not hand-edit an installed generated OpenCode
config to add this setting.

Official documentation retrieved **2026-09-15** specifies
`@ai-sdk/openai-compatible` for Chat Completions custom providers, with
`options.baseURL`, optional `options.apiKey`, and a `models` map. Each configured
model must match the endpoint's published ID. This template uses provider ID
`ai-vm`. [OpenCode custom providers](https://opencode.ai/docs/providers/#custom-provider)

The template uses `{env:LLM_BASE_URL}` and `{env:LLM_API_KEY}`. OpenCode also
supports `{file:/absolute/path}` for a protected credential. The following
local rendering step replaces the model placeholder and uses a file reference
without reading or copying the key into JSON. Omit `A1_KEY_FILE` only for the
explicitly unauthenticated tunnel setup. [OpenCode configuration variables](https://opencode.ai/docs/config/#variables)

```sh
export A1_REPO="$PWD"
python3 - <<'PY'
import json
import os
from pathlib import Path
source = Path(os.environ['A1_REPO']) / 'scripts/agent/opencode.template.json'
config = json.loads(source.read_text())
model = os.environ['A1_MODEL']
if not model or model.startswith('REPLACE_'):
    raise SystemExit('Set A1_MODEL to the Worker1 published API model ID')
config['model'] = 'ai-vm/' + model
provider = config['provider']['ai-vm']
provider['models'] = {model: {'name': model}}
key_path = os.environ.get('A1_KEY_FILE')
if key_path:
    provider['options']['apiKey'] = '{file:' + str(Path(key_path).resolve()) + '}'
else:
    provider['options'].pop('apiKey', None)
output = Path(os.environ['A1_RUN']) / 'opencode.json'
with output.open('x') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
output.chmod(0o600)
PY
python3 -m json.tool "$A1_RUN/opencode.json" >/dev/null
```

Once V1 provides the installed worker CLI and authorizes the coordinated live
run, use a fresh worker directory. `OPENCODE_CONFIG` selects the generated
config; `--model` uses `provider/model`, and `--format json` captures events.
[OpenCode custom config](https://opencode.ai/docs/config/#custom-path),
[OpenCode run flags](https://opencode.ai/docs/cli/#run)

```sh
mkdir -m 700 "$A1_RUN/opencode-workspace"
cd "$A1_RUN/opencode-workspace"
OPENCODE_CONFIG="$A1_RUN/opencode.json" \
  opencode run --model "ai-vm/$A1_MODEL" --format json \
  'Reply with the single word READY.' >"$A1_RUN/opencode-smoke.jsonl"
```

That command is a transport smoke test. V1 must additionally prove actual
OpenCode file reads, edits, test execution and continuation in a disposable
fixture, record the installed OpenCode version/config, and review its tool
permissions and evidence. OpenCode's tools and permissions are separate from
the stdlib harness's restrictions. No OpenCode E2E or arbitrary-code isolation
claim follows from the template or the smoke command.

## Installer handoff

The A1 client needs Python 3.10+ and its standard library on the client worker;
commands are portable to the Ubuntu 24.04 target's Python 3 environment. A1
does not install a complete server or claim clean-install validation. I1/I2 own
the fresh Linux installer and its clean-machine proof. Keep model selection,
base URL, time budgets and credential paths configurable; retain secure
loopback plus SSH access, one active backend, and client tools off the VM.
