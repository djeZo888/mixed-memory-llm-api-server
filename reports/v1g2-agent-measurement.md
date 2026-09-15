# V1G2: genuine GLM 32K baseline agent measurement

2026-09-15 — **A1 protocol aggregate FAIL; actual A1 agents PASS; actual OpenCode PASS.**
The sole A1 failure in both unchanged CLI runs is the known invalid-model
incompatibility: an unknown requested model returns HTTP 200 with `glm-5.3`.
The original V1G A1 aggregate **FAIL remains unchanged**. This measurement does
not establish overall server readiness or waive the model-name contract.

## Authority and measured source

Fresh Worker2 session `01a0a2b2-7c4c-7602-a496-2a090a05b540`, reviewed integration
`6cffccbf1927ff610c21cfc6a0bea3b2f14bd85a`, feature branch
`milestone/v1g2-glm-agent`. Read AGENTS, current PLAN and D3 handoff; taskroot
incoming Revision2 explicitly confirmed the sole GLM request lease before any
network access. Incoming was reread at phase boundaries. Root explicitly
allowed the unchanged A1 CLI to finish all ordinary checks despite this one
known failure and allowed independent OpenCode measurement when all other
A1 checks and both agent loops passed.

The D3 handoff identifies deployment `glm-5.3-ud-q4-k-xl-32k`, served alias
`glm-5.3`, VM loopback `127.0.0.1:30002/v1`, one 32768-token slot, runtime
v0.4.1/b29c606, image
`sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`,
and `clear_thinking=true`. Those runtime identities are handoff evidence;
V1G2 made no VM mutation, tuning, lifecycle or model change. All tools, tests,
client software and logs ran on Worker2.

Full SHA256 bindings for unchanged A1/client/lock files and the new fixture are
in [the sanitized evidence](v1g2-evidence.json). No existing implementation,
validator, acceptance criterion, generated client config or reasoning-replay
policy changed. Reproduction commands are in the
[fixture README](../scripts/validation/v1g2/README.md).

## Unchanged A1 acceptance

Both runs used `--auth enabled --reasoning-effort low --max-tokens 2048
--request-timeout 300 --overall-timeout 1800`, the exact model alias and the
protected file credential. The second invocation only adds `--stream-tools`.
Each ran once to its ordinary completion and exited 1; neither timed out.
The existing Client.chat injects low on every generation POST, including
invalid-model/auth probes and continuations; model-list GETs have no generation
options. No observer interrupted either CLI after the known failure.

| Check | Normal tools | Streamed tools |
| --- | --- | --- |
| Protocol aggregate | **FAIL** | **FAIL** |
| Missing/wrong key: models and chat | PASS: all four HTTP 401 | PASS: all four HTTP 401 |
| Correct key: models and chat | PASS: HTTP 200 | PASS: HTTP 200 |
| Published model, ordinary chat, SSE completion | PASS | PASS |
| Invalid requested model | **FAIL: HTTP 200, returned glm-5.3** | **FAIL: HTTP 200, returned glm-5.3** |
| Genuine read/edit/test agent and tool roundtrip | **PASS** | **PASS** |
| Total CLI measurement | 60.138521 s | 53.101493 s |
| Agent loop | 46.288264 s, 4 rounds | 44.169321 s, 4 rounds |

Each actual agent sequence was `read_file(calc.py)`, `read_file(test_calc.py)`,
`write_file(calc.py)`, `run_tests`, then final assistant content. Both read calls
were in the first response; write and test occurred in separate later responses.
Each started with a genuinely failing fixture, changed the implementation,
kept immutable tests unchanged, obtained a model-requested passing test result,
and passed the harness's independent final test. Tool IDs/arguments were parsed
by the unchanged strict protocol/harness; published call-ID hashes preserve
correlation without raw events. Finish reasons in each loop were
`tool_calls`, `tool_calls`, `tool_calls`, `stop`. All four streaming agent
responses reached SSE `[DONE]`; ordinary SSE passed in both CLI runs.

Normal-tool agent provider usage per round:

| Round | Prompt | Completion | Cached prompt | Finish |
| --- | ---: | ---: | ---: | --- |
| 1 | 544 | 25 | 9 | tool_calls |
| 2 | 802 | 30 | 568 | tool_calls |
| 3 | 908 | 6 | 831 | tool_calls |
| 4 | 1131 | 44 | 913 | stop |

Provider usage was **NOT_REPORTED** for the A1 SSE chat and all four streamed
agent responses. The unchanged A1 client does not add `stream_options`;
missing counters were not replaced with zero or recovered through another
request. Per-request HTTP status, elapsed time, finish and returned usage are
retained in the sanitized JSON. Timing is full response/loop wall time, not
TTFT, prefill time or a decode-speed benchmark. No reasoning fields were present
in the observed A1 agent responses. The unchanged client would record returned
reasoning separately and exclude it from replay. Both actual continuations
succeeded with the handed-off clear-thinking runtime; replay of returned
reasoning fields was not exercised.

## Actual pinned OpenCode 1.18.31

Only after both A1 gates passed apart from the expected invalid-model check,
bootstrapped a fresh private prefix through the reviewed package lock using
`--reasoning-effort low --context-tokens 32768 --output-tokens 2048`. The actual
binary returned 1.18.31 and the installed config/model/dummy-key check passed.
The low-effort wire basis is [reviewed A2O actual pinned-client proof](a2o-opencode-reasoning.md)
and unchanged verified generation; V1G2 did not intercept, rewrite or manually
edit requests/config. The OpenCode agent transport is streaming.

**Observed OpenCode PASS: one run, exit 0, 151.156741 seconds, no timeout or
operator retry/budget increase.** The launcher ran as the ordinary Worker2
user in an explicit trusted private workspace, with read/glob/grep, invocation
edit permission and only `python3 -I -B test_text_utils.py` allowed for bash.
A task-owned outer supervisor enforced 1800 seconds and process-group cleanup;
the observed launcher/native descendants were independently confirmed absent
after completion. The reviewed launcher itself does not supply this timeout.

The initial ordinary-workspace source contains the required `split(" ")` bug.
Its immutable tests explicitly import the sibling source with importlib and
run under Python isolated mode. Baseline: exit 1, three test methods, **five
intended assertion failures**, no ImportError/ModuleNotFoundError.

| Observed native tool sequence | Result |
| --- | --- |
| Read text_utils.py in the workspace | completed |
| Read test_text_utils.py outside the workspace | denied by external-directory permission |
| Read test_text_utils.py in the workspace | completed |
| Edit text_utils.py | completed; only `split(" ")` became `split()` |
| Bash: exact `python3 -I -B test_text_utils.py` | completed, exit 0, tests OK |
| Final assistant text and terminal finish | observed, stop |

The denied read is retained as evidence. The model corrected its file path
inside the same run; permissions were not expanded, tools were not substituted,
and no human fixed the code or tests. Native output contained five step starts,
five step finishes, five tool events (one denied, four completed), one final
text event, and no top-level error event. Independent final rerun: exit 0,
three tests PASS; only the implementation changed.

| File state | SHA256 |
| --- | --- |
| Initial source | `8bff6135c956d931fa755b0cb4e25f19fc5dee661e88f51efbd3d7ec55dd4b44` |
| Model-edited final source | `3fd34f6eaad8377d745966c43047f1ac2c2914a6c731e69e0b281f98e77e45d1` |
| Immutable tests, before and after | `b51a86da2ac6fbcf76b7b4b8cebadbdc5d28ab4c6bf833dbca11265dcb3e6c43` |

Native OpenCode counters are preserved without relabeling them as independently
captured provider HTTP usage. **Provider usage: NOT_REPORTED separately.**
No wire body capture was added. Native reasoning/cache-write/cost values were
zero; that is client-reported data, not proof of zero internal reasoning or a
priced cost. Auxiliary/title usage is not separately exposed in this event set.

| Step | Native input | Native cached read | Native output | Native total | Finish |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 5058 | 10 | 59 | 5127 | tool-calls |
| 2 | 271 | 5126 | 74 | 5471 | tool-calls |
| 3 | 352 | 5470 | 55 | 5877 | tool-calls |
| 4 | 106 | 5822 | 43 | 5971 | tool-calls |
| 5 | 106 | 5928 | 84 | 6118 | stop |

These five steps report 315 output tokens. The largest native input plus
cached-read count is 6034; this is a small baseline task within a configured
32768 context, not a large occupied-context qualification.

## Verification, privacy and remaining decisions

- PASS: private explicit-import baseline failed for the intended assertions;
  actual OpenCode test tool and independent final run passed; immutable hashes
  and only-source-change review passed.
- PASS: unchanged A1/client/lock source hashes; actual pinned client version
  and configuration check; documented fixture commands and shell-block syntax.
- PASS: own SSH alias/known-host enforcement, loopback-only free port,
  ExitOnForwardFailure and private control identity; existing key transferred
  directly by SSH sudo to an owned fresh 0700 directory / 0600 regular file,
  with printable exact bytes, no newline, symlink or hard link.
- PASS: both A1 process groups and actual OpenCode process group finished;
  observed OpenCode descendants absent; owned tunnel identity verified before
  exit, control socket removed and listener closed. Lease released at
  2026-09-15T01:43:09.686758+00:00 with zero active V1G2 requests.
- Sanitized publication contains only fixtures, commands, statuses, hashes,
  numeric usage/timing and tool metadata. Raw prompts, responses, events and
  logs stay task-private outside Git. Exact-key in-memory and grep-based secret,
  filename/scope, attribution, whitespace and clean-tree publication gates are
  recorded in taskroot final/result alongside commit and bundle hashes.

**Next action:** root must decide the model-name compatibility policy while
preserving both original V1G and V1G2 A1 aggregates as FAIL. Full installer and
`server_ready` remain **pending that explicit compatibility decision**. Genuine
agent capability is separately observed PASS here. Highest practical context,
large occupied context, fresh Linux installation, reboot, hosted CI and full
installer acceptance are **NOT_TESTED by V1G2**. Worker1 remains the sole VM
mutation owner; any context follow-up requires a separately bounded task.
