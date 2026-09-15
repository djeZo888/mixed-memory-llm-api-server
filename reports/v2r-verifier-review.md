# V2R ordinary-verifier review corrections

2026-09-15 — **PASS, source verification only.** Session
`01a0a2e2-b4fe-7d00-ac24-31c8dbe22dca`, Worker2 (`mac-worker2`, ordinary UID 502),
base `d5d36771e0eb6fb7c4bc0b8cb76034ea5a8669c8`.

## Corrections

- Credential scrubbing retains the raw and OpenCode representations and adds
  exact `json.dumps(key)[1:-1]` escaping. Synthetic quote/backslash/literal-brace
  echoes now pass through actual JSONL parsing and production success/failure
  artifact writers without retaining any complete representation, including
  after decoding nested evidence. No real credential was used.
- SIGTERM/SIGHUP latch the first observed cancellation. During owned-process
  supervision, signals request the existing cleanup; repeated signals cannot
  interrupt it. Partial output and the observed cleanup result are retained
  before cancellation checkpoints. Reports remain FAIL with a fixed signal
  diagnostic; cancellation during final report writing triggers one bounded
  FAIL rewrite. Original handlers and the timer are restored, including on
  artifact-write errors.

**Reported helper seam:** `verify_events.run_bounded` needed an optional
`cancel_requested` predicate beside its timeout check. A throwing handler alone
would lose captured output and could interrupt its existing `finally`. The
seven-line helper change was reported before editing and acknowledged in the
phase-boundary incoming note as within the authorized correction. Default
behavior, owned PID/group tracking, output/time bounds and cleanup policy remain
unchanged. The added argument refuses non-callable values.

## Worker verification

| Check | Result |
| --- | --- |
| Relevant verifier suite, warnings treated as errors | PASS: 68 tests, 42.557 s |
| Combined-character success and failure artifacts | PASS: raw/JSON/OpenCode complete representations absent in bytes, decoded JSON and JSONL; private modes and raw hash checked |
| Original V2 negative control in a separate disposable source copy | Expected FAIL: both new redaction regressions expose the original omission |
| Real harmless cancellation tree | PASS: TERM-ignoring parent and descendant, initial TERM and HUP, acknowledged repeated cancellation, PID and process group absent |
| First cancellation during timeout cleanup | PASS: retained stdout/stderr, truthful timeout and cleanup result, failed report |
| Outside-process and artifact cancellation | PASS: handler/timer restoration, write-error path, otherwise-PASS report rewritten to FAIL |
| Final runtime manifest | PASS: exactly the two verifier runtime files changed; fixed fixture/client sources unchanged |
| Independent source review | No blocking findings |

Reproduce the relevant suite:

```sh
python3 -B -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_verify*.py'
```

[The V2R manifest](v2r-source-manifest.json) binds runtime source digest
`a2f716d41d2e9f91be2a4cc6b3971607a3be440ed385dec4c3af7cd7d6e2c938`.
The success/failure regressions require their actual producer manifest to equal
that file; source-drift checks are not bypassed. Final committed Git-object,
bundle and feature-publication gates are recorded in the external V2R session
handoff. The original [V2 report](v2-client-verifier.md), manifest and synthetic
HTTP evidence remain unchanged and are not relabeled as V2R evidence.

## Boundaries and next action

Actual pinned OpenCode synthetic rerun: **NOT_RUN**. The command, fixture, event
grammar and native client bytes are unchanged; these corrections are exercised
at their actual Python serialization and process-supervision boundaries. The
previous V2 native synthetic run remains historical evidence.

No ai-vm access, live model request, installation, bootstrap, URL/reasoning,
receipt/challenge, runtime/control/storage or separately owned N1C/Q38C change.
Installer work stays paused. Hard SIGKILL, hostile same-user interference and
unobserved daemonization remain outside the cleanup guarantee. Artifact I/O
failure can prevent a report; handler restoration is still tested.

Next: root reviews and integrates the bounded V2R feature bundle. This is not
installer or live-model acceptance.
