# A2A — reasoning effort and truthful termination diagnostics

## Result and scope

**PASS: worker-only source and synthetic verification. Live acceptance remains NOT_TESTED.**

Session: `01a0a295-a0d4-7553-afbc-4cf525925fce`
Source base: `e6c77debb4989ada0c7a563159f8df45aa89f7b5`
Branch: `milestone/a2a-reasoning-client`
Author and committer: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`

Read repository AGENTS, current-state/orchestration handoffs, taskroot
`D3-CLIENT-REQUEST.md` and `incoming.md` at phase boundaries (Revision1).
Only `scripts/agent/acceptance.py`, `scripts/agent/protocol.py`,
`tests/test_agent_acceptance.py`, `tests/test_agent_protocol.py`,
`docs/agent-client.md` and this report changed. The fixture implementation,
acceptance success criteria, server configuration and A2O client files are unchanged.

## Behavior

- `Client(..., reasoning_effort=None)` and CLI `--reasoning-effort` share the
  explicit enum `none,minimal,low,medium,high,xhigh,max`. Invalid types/values
  fail before HTTP; the client revalidates before each chat request.
- The default omits the JSON field entirely; it does not send null or select
  an effort. A configured value is top-level `reasoning_effort` on every chat
  request: ordinary, nonstream, SSE, missing/wrong/correct auth, invalid model,
  tool invocation, and every actual continuation. No arbitrary body injection.
- `limits.reasoning_effort` records `null` or the selected value. Synthetic
  propagation exercised both omission and `low`; no live selection was sent.
- The generic enum spans backend conventions, not universal model support.
  D3's reviewed GLM template supports only low/high/max: use exactly low for
  its reviewed follow-up. None is not low. Server-side clear_thinking and
  reasoning exclusion from replay are preserved. No reasoning-budget knob.
- Valid length-terminated nonstream responses and complete SSE raise
  `CompletionError`, remain FAIL/incomplete, and never return calls to execute.
  Failed requests and probe/agent diagnostics retain `token_budget_exhausted`,
  `finish_reason=length`, model, usage, and stream_done.
- Partial argument JSON and invalid assistant calls under length retain that
  metadata plus `parsing_failure=invalid_assistant_message`. Malformed responses
  without length retain ordinary validation errors; missing DONE/unfinished SSE
  retain incomplete-stream errors and are not classified as valid exhaustion.
- Diagnostics allow only model identity bounded to 1024 printable ASCII
  characters after redaction, standard token-count fields/nested details with
  integer values from 0 through 2**63-1, and fixed classification/finish flags.
  Missing/unusable metadata is null. Unknown provider data, response/reasoning
  text and arguments are excluded. Credential redaction preserves trusted
  counter names and enums; expansion beyond the model bound becomes null.

## Verification on Mac-Worker2

Python: **3.14.7**. All HTTP was deterministic loopback synthetic traffic.
No packages or inference software were installed or built.

| Command/check | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_agent*.py' -v` | **PASS: 94 tests, 10.145s** |
| Final suite breakdown | 48 protocol + 20 acceptance + 26 unchanged fixture tests |
| `PYTHONDONTWRITEBYTECODE=1 python3 scripts/agent/acceptance.py --help` | PASS; optional enum and omission semantics shown |
| `git diff --check` | PASS |
| Existing invalid IDs, duplicate keys, argument/schema, key redaction, transport/byte/time limits | Retained and PASS |
| Full fixture with default/low, nonstream/stream tools | PASS; actual reads, write, requested tests and independent verification |
| Valid content/tool length and partial JSON length, both modes | Expected FAIL/incomplete; zero executed tool calls; safe metadata retained |
| CLI invalid effort and Python invalid enum/type | Rejected before HTTP; CLI creates no report |

The full authenticated synthetic fixture still issues 14 HTTP requests, including
10 chat requests and four agent rounds. Captures check exact top-level body keys
and every tool-result ID continuation. The successful fixture still repairs
`return a - b` to `return a + b`, with two reads, one write, one requested test,
unchanged tests and independent verification. No acceptance requirement was weakened.
The length fixtures report synthetic prompt/completion/total counts 7/2048/2055;
these are diagnostic test inputs, not live performance measurements.

Final worker test output and help are retained in taskroot `a2a-tests.txt` and
`a2a-help.txt`. Earlier 92-test verification passed before two final metadata
redaction regressions; the 94-test result above covers the final source.

## Delivery and next action

Source is committed on the feature branch with exact author/committer attribution.
Pre-publication verification includes an exact six-file scope check, filename-only
credential-pattern scan, staged whitespace check, credential-free HTTPS remote,
commit metadata, clean tree and a full self-contained `A2A.bundle` verification.
The commit ID, bundle SHA-256 and publication outcome are in taskroot `final.md`;
no main push is part of this task.

Warnings/limits: synthetic tests do not prove live GLM reasoning behavior,
throughput, preserved thinking, OpenCode compatibility or overall READY.
No ai-vm contact, real-key access, VM/network/runtime/model/lifecycle/installer
changes or inference requests occurred. VM data-disk guards are not applicable
to this worker-only source/test task.

Next: coordinator reviews the bundle. D3/V1 then use the reviewed A1 command with
`--reasoning-effort low`, initially `--max-tokens 2048`, once without and once
with `--stream-tools`, each with a fresh report path. V1 waits for bundle review;
A2O owns OpenCode source integration. No additional knob or budget increase is
justified by these synthetic results.
