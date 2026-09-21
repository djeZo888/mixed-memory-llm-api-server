# A1 bounded client and protocol acceptance

Date: 2026-09-15. Worker: Mac-Worker2. Branch: `milestone/a1-agent-client`.
Base: `7171167`. **A1 result: PASS for implementation and synthetic acceptance.**
Live endpoint acceptance, actual OpenCode compatibility and clean Linux
installation remain **NOT_TESTED**.

## Delivered behavior

- `scripts/agent/protocol.py`: Python stdlib Chat Completions transport with
  configurable URL/model/key, request and overall deadlines, byte/token bounds,
  strict JSON and SSE reconstruction, separate reasoning, native tool IDs and
  roles, HTTP errors, model identities and available usage. No proxy environment,
  redirect following, backend dependencies, installation, or automatic retries.
- `scripts/agent/fixture.py`: freshly created private disposable workspace;
  `read_file`, `write_file`, and fixed `python3 -I -B test_calc.py` execution.
  Only arithmetic `add(a, b)` code is editable. Immutable tests are hash-checked.
  No imports/calls/attributes, arbitrary shell commands, inherited credentials,
  traversal, symlink/hard-link escape, or unknown tool/schema is allowed.
  Read batches are supported; writes/tests must each occupy their own round.
- `scripts/agent/acceptance.py`: API/auth/stream/model probes and a bounded
  read → edit → requested test → final-answer loop. Success requires relevant
  reads before the first real edit, a passing model-requested test after the
  last write, unchanged tests, actual diff and independent final verification.
  Report files are private and never overwritten. Redaction happens at the
  report boundary without mutating executable protocol messages or fixed
  report schema/outcome fields.
- `tests/test_agent_acceptance.py`, `tests/test_agent_fixture.py`, and
  `tests/test_agent_protocol.py`: deterministic loopback HTTP and actual local
  subprocess regressions. Mock startup avoids reverse DNS.
- [`docs/agent-client.md`](../docs/agent-client.md) and
  [`opencode.template.json`](../scripts/agent/opencode.template.json): exact
  CLI/tunnel/secret instructions, provider template and installer handoff.

## Checks and evidence

Validation ran on this macOS worker with **Python 3.14.7**, not on `ai-vm`.

| Check | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_agent*.py' -v` | **PASS: 75 tests, 6.266s** |
| Protocol regression subset | PASS: 38 tests |
| Fixture regression subset | PASS: 26 tests |
| End-to-end acceptance regression subset | PASS: 11 tests, including additional subcases |
| `python3 scripts/agent/acceptance.py --help` | PASS |
| `python3 tests/test_agent_acceptance.py --write-evidence <new-file>` | PASS; synthetic HTTP only |
| `python3 -m json.tool scripts/agent/opencode.template.json` | PASS |
| Python 3.10 grammar parse of all new Python; nine documented shell blocks and embedded Python syntax | PASS; grammar check is not Linux execution |
| `git diff --check` and staged whitespace check | PASS |
| Local grep-based staged secret scan and credential-free `git remote -v` inspection | PASS before each push |
| Real VM models/chat/stream/tools/auth | **NOT_TESTED** |
| Actual OpenCode CLI/tool E2E | **NOT_TESTED** |
| Ubuntu 24.04 runtime and fresh installation | **NOT_TESTED**; I1/I2 owns installer/clean validation |

The credential-URL scan's one match was the intentional localhost URL with
dummy user/password in `test_invalid_base_url_and_limits`. It was inspected
and excluded by exact literal in that test file only; no real credential was
present and the other secret patterns had no matches.

[`a1-synthetic-evidence.json`](a1-synthetic-evidence.json) records one complete
run against `synthetic-add-model`: 14 HTTP requests, four agent rounds, two
actual reads, one implementation write and one model-requested test. Initial
real unittest exit was **1**; the model-requested test and independent final
test both exited **0**. Tests remained unchanged, and the workspace was removed.
The actual code diff is:

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

The synthetic report covers missing/wrong/correct authentication on models and
chat, nonstream chat, SSE termination, interleaved streamed tool arguments,
invalid-model rejection and native result-ID continuation. Usage and timings
are recorded as returned/measured for the mock; **they are not model performance
measurements**. Other regressions cover disabled-auth NOT_TESTED labeling,
malformed JSON, numeric overflow, ID errors, unsafe paths/code, immutable tests,
output/time/round/call bounds, HTTP errors, mismatched identities, claimed-only
success, post-hoc reads, missing tests and edits after a passing test.

## Risks and validation boundaries

1. Worker1 must publish the exact runtime/model ID, endpoint port, limits,
   reasoning/parser configuration and authentication policy before V1. Stale
   30B handoff claims were not used, and no old endpoint was probed.
2. A1 stores reasoning separately and does not replay it into continuation
   requests. Backends requiring preserved/interleaved reasoning need a separately
   validated contract in V1; the documented Z.AI limitation is explicit.
3. The arithmetic AST fixture is deliberately narrow. It establishes this
   bounded repair workflow, not isolation for arbitrary untrusted repositories
   or general model coding ability. Tools execute only on the client worker.
4. OpenCode custom-provider documentation was verified from primary sources
   on 2026-09-15, but the template is not OpenCode E2E evidence. V1 must run the
   actual installed worker CLI and real file/edit/test continuation.
5. No VM disks, services, runtime/model profiles, shared manager, AGENTS.md,
   current-state, README or operations files changed. No credentials were
   retrieved, packages installed, models downloaded, or inference run. VM
   `/data` guards are not applicable to this worker-only source/test task.

## Next exact live command (V1 only, after coordination)

Use the protected run directory/key setup in the client documentation. Obtain
`A1_BACKEND_PORT` and `A1_MODEL` from Worker1; do not guess model or port. In a
separate terminal keep the loopback-only tunnel open:

```sh
ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -N \
  -L "127.0.0.1:30002:127.0.0.1:${A1_BACKEND_PORT}" ai-vm
```

Then, for the intended authenticated endpoint:

```sh
python3 scripts/agent/acceptance.py \
  --base-url http://127.0.0.1:30002/v1 --model "$A1_MODEL" \
  --api-key-file "$A1_KEY_FILE" --auth enabled \
  --request-timeout 120 --overall-timeout 900 --test-timeout 10 \
  --max-rounds 12 --max-tool-calls 32 --max-tokens 2048 \
  --max-output-bytes 16384 --max-response-bytes 262144 \
  --stream-tools --workspace-parent "$A1_RUN" --report "$A1_RUN/report.json"
```

If Worker1 explicitly publishes auth disabled behind the tunnel, omit the key
option and use `--auth disabled`; auth checks will be NOT_TESTED. Run one active
model at a time under Worker1's coordination. I1/I2 should retain the stdlib,
configurable client commands and keep all client tools off the inference VM.

## Synchronization

The report-only checkpoint `8dfdbec` was pushed during implementation. Final
owned files are committed and pushed only to
[`milestone/a1-agent-client`](https://github.com/djeZo888/mixed-memory-llm-api-server/tree/milestone/a1-agent-client)
with attribution `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.
The final commit ID and synchronization verification are recorded in the worker
handoff `/Users/agent/LLMServer-orchestration/20260915/A1/progress.md`.

The incremental bundle is
`/Users/agent/LLMServer-orchestration/20260915/A1/A1.bundle`; it contains this
feature branch and requires base `7171167`. Verify with `git bundle verify`
from a repository containing that base before orchestrator integration. No
push to main or shared-file integration is part of A1.
