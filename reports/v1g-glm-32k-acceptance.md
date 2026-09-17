# V1G — actual GLM 32K client acceptance

## Result: FAIL — invalid model accepted

The initial A1 nonstream attempt stopped at its invalid-model probe. The server
accepted a generated invalid model ID with **HTTP 200**, returned `glm-5.3`, and
finished with `stop`. A1 requires rejection with HTTP 400, 404, or 422.
Classification: **model identity / API contract failure**. This result does not
establish model quality, token exhaustion, or tool capability.

No live retry occurred. The external stop guard preserved the failure and exited
before the remaining authentication probes and fixture requests. The second A1
run and actual OpenCode path were stopped. The owned SSH tunnel was closed and
the generation request lease released; Worker1 owns subsequent runtime work.

## Actual observations

Run: **2026-09-15 01:29:42–01:29:58 UTC**. A1 elapsed **15.656353 s**;
external supervisor elapsed **15.786960 s**, exit **1**, no timeout.

| Probe, in order | Result | HTTP | Prompt / completion / total tokens | Elapsed s |
| --- | --- | --- | --- | --- |
| Correct-key `/models` | PASS, `glm-5.3` listed | 200 | Not applicable | 0.008416 |
| Correct-key ordinary chat | PASS, content and `stop` | 200 | 18 / 11 / 29 | 6.500652 |
| Correct-key actual SSE chat | PASS, parsed content, `stop`, `[DONE]` | 200 | NOT_REPORTED | 2.004981 |
| Invalid model chat | **FAIL: accepted, returned `glm-5.3`** | 200 | 15 / 25 / 40 | 7.131564 |

Reported cached prompt tokens were 10 and 11 for the two nonstream completions.
Reasoning-token counts were not reported. No complete token total or throughput
is calculated because SSE usage is missing. All three chat requests used the
reviewed shared A1 request builder with explicit `reasoning_effort=low` and
`max_tokens=2048`. No request ended with `length`.

A request-record `success: true` means HTTP/parsing succeeded. The invalid-model
**acceptance check is FAIL**; that transport field is not an acceptance result.

### Required evidence that was not reached

| Evidence | Status |
| --- | --- |
| Missing/wrong-key rejection on models and chat | NOT_TESTED |
| Dedicated later correct-key auth checks | NOT_TESTED; earlier correct-key requests succeeded |
| A1 nonstream tool read/edit/requested test/independent final test | NOT_TESTED |
| Fresh A1 `--stream-tools` run | NOT_TESTED |
| Actual OpenCode 1.18.31 bootstrap, native events and agent run | NOT_TESTED |
| Word-count fixture baseline, model edit, exact requested test, independent final test and test hashes | NOT_TESTED; fixture was not created |
| Hosted validation in this session | NOT_TESTED |
| Full fresh Linux install / reboot | NOT_TESTED / NOT_TESTED |

Observed live tool sequence: **empty**, with **0 calls and 0 results**. No agent
fixture or fixture test subprocess was created. No native OpenCode event counts,
tokens, source/test hashes, or passing assistant answer are invented.
`opencode_e2e` remains `NOT_TESTED` in the A1 summary.

## Source and runtime provenance

- Session: `01a0a2ac-177e-7b80-850c-f173fb5dd43e`.
- Branch: `milestone/v1g-glm-agent`.
- Executed A1 source: `66ef3d45f2225b3187e3d246637f6aaa3cf32514`.
  Working A1 source matched the reviewed Git blobs; there were no implementation edits.
- Approved A2O: `0880e01ca2d283617feb3a129c18ce3cb6c7f4c4`, delivered by
  `incoming.md` revision 2. Its complete bundle verified. Normal merge preserving
  A2A: `ebd428e1bfb0ad03eb88b7f11699ca0a674ed21c`. No generated OpenCode
  configuration was edited or used; merging source is not live CLI evidence.
- D3 handoff: `glm-5.3-ud-q4-k-xl-32k`, alias `glm-5.3`, one slot/context 32768,
  `clear_thinking=true`, runtime `v0.4.1/b29c606`, image
  `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
  These runtime facts are handoff evidence, not remeasured by V1G. A1 has no
  outgoing context-limit field. All client tools stayed on the worker.

## Commands and bounds

`PRIVATE` below denotes the actual fresh worker directory outside the checkout;
it had mode 0700. Its key file had mode 0600, current-worker ownership, one link,
regular-file type, printable bytes and no newline. No key bytes were put in argv,
console, environment variables, Git, or logs. The existing root-owned VM key was
reused, not regenerated. The transfer's stdout was directed straight to that file:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=15 \
  ai-vm 'sudo -n cat /data/services/secrets/llm-api-key' \
  > "$PRIVATE/llm-api-key" 2> "$PRIVATE/ssh-key-transfer.stderr"
```

The source metadata was checked by read-only `sudo -n stat` before transfer.
The task-owned tunnel used existing host verification, loopback port **55756**,
private control socket, PID **63192**, `ExitOnForwardFailure=yes`,
`ControlPersist=no`, keepalive 30 s / count 3, and forwarding to
`ai-vm`'s `127.0.0.1:30002`. It was opened as a separate owned process group.

The as-run command was:

```sh
python3 -B scripts/validation/v1g/run_a1.py \
  --private-dir "$PRIVATE" --base-url http://127.0.0.1:55756/v1 --mode nonstream
```

It invoked unchanged `scripts/agent/acceptance.py` with:

```text
--base-url http://127.0.0.1:55756/v1 --model glm-5.3
--api-key-file PRIVATE/llm-api-key --auth enabled --reasoning-effort low
--request-timeout 300 --overall-timeout 1800 --max-tokens 2048
--max-rounds 12 --max-tool-calls 32 --test-timeout 10
--workspace-parent PRIVATE/nonstream --report PRIVATE/nonstream/report.json
```

The external supervisor used an 1800 s bound. The trace observer copies completed
check metadata and exits on the first failed probe; it changes no request, model
response, fixture, successful outcome, or acceptance rule. The as-run wrapper is
preserved with its source hash. It intentionally requires the original A2A HEAD,
so running it from the final merged HEAD is refused. Further live execution needs
a new coordinator-owned lease and reviewed follow-up task.

The wrapper's general process-group cleanup does not track separately sessioned
fixture tests if interrupted; no such process existed on this failure path.
This limitation is recorded rather than retroactively changing the executed wrapper.

## Verification and evidence handling

- Local A1 synthetic regression suite: **94 passed**, 9.341 s.
- Local client regression suite: **42 run, 41 passed, 1 skipped**, 3.430 s.
  The installed-CLI check was skipped because no `V0_CLIENT_PREFIX` was supplied. These tests do not
  prove actual OpenCode/model behavior or a Linux installation.
- External guard synthetic verification: accepted-invalid-model fixture produced
  exactly four requests, then overall FAIL/exit 1; no subsequent auth/tool
  request; every chat carried low effort; synthetic key absent from report.
  The first ad hoc verifier had a mock default-model setup error; the guard
  correctly stopped at chat identity mismatch and the verifier raised KeyError.
  Only synthetic setup was corrected. This was not a live retry.
- Independent source review confirmed the fail guard cannot turn this failure
  into PASS and A1 source matches the reviewed commit.
- Summarizer synthetic checks covered allowlisting, partial reports, unavailable
  counters, length diagnostics, omitted raw content, exact-key refusal,
  0600 output, and refusal to overwrite.

Reproduction of local checks (no VM requests):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_agent*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s scripts/client/tests -p 'test_*.py' -v
python3 -B scripts/validation/v1g/test_stop_guard.py -v
python3 -B scripts/validation/v1g/run_a1.py --help
python3 -B scripts/validation/v1g/summarize_a1.py --help
git diff --check
```

The private A1 parsed report retains content/reasoning for the successful chat
and SSE probes. The failed invalid-model probe retains HTTP/model/usage/finish
metadata but discards its returned content/reasoning; those lengths are
NOT_REPORTED. The reviewed harness does not archive HTTP byte streams or SSE
chunk counts. Published text lengths describe decoded strings after A1
redaction, not raw-wire lengths.
No raw reports or credential-bearing output were copied into Git.

[Sanitized A1 metadata](v1g-a1-nonstream.json) records checks, per-request usage,
lengths and unavailable values. [Verification metadata](v1g-verification.json)
records source hashes, timings, evidence classifications and cleanup. The
actual-key scan of all 397 tracked files, filename-only credential-pattern scan
of the six owned files, credential-free remote check, whitespace check and
exact-scope check passed before commit. Actual key bytes stayed in memory.

## Lease release and next action

The owned tunnel control exit returned **0**; the control socket, owned SSH
process and loopback listener were confirmed absent. `progress.md` notified the
coordinator and `lease-release.md` released the sole generation lease. No model,
service, disk, VM package, runtime setting, or configuration was changed.

**Next action:** coordinator/Worker1 should open a separate bounded task for the
invalid-model rejection contract, with source review before any correction or
new live acceptance. Keep both A1 tool modes and actual OpenCode acceptance
pending. No readiness, agent capability, or model-quality conclusion is justified.
