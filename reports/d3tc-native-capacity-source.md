# D3TC: independent native-capacity trial mode

Source-only change on `milestone/d3tc-native-capacity`, reviewed base
`e8d8bbad3f2f6345295d440b25f084fed83dc734`. The root-approved architecture plan's
later report-only reference does not require rebasing this reviewed source.
Session: `01a0a33d-f542-7231-a3c3-1460270b98f7`.
Author and committer: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.

## Behavior

`init --trial-mode native-capacity` creates a new private run with one native
binding and eligible stages `64k -> 128k -> 256k -> 512k -> near1m`. Comparison
remains the default, including configs without the field. Unknown modes refuse.
There is no mode conversion, checkpoint import, stage-PASS command or retry.

Native admission reads the measured image from the single reviewed source file
`configs/runtimes/llama-cpp-v0.4.1-d3br.json`, requires its build/CLI validation
status and an image distinct from D1, then calls the existing exact-container
1048576 guard and native snapshot check. The binding and admission retain the
container/image/PID/start identity. No baseline/candidate binding, request,
file or synthetic PASS is created in this mode.

A shared gate checks eligible stages, preceding PASS results and revisits before
direct preparation and before detached PREPARING/spawn. Dispatch also rejects
unknown modes and excluded stages. Refused `_prepare` calls cannot overwrite
active/unknown/failed checkpoints or another preparation's lock. Status exposes
the mode, `comparison_status: NOT_RUN_IN_THIS_TRIAL`, eligible stage states and
the actual highest occupied proof.

Global STAGES indices, native corpus fitting/body construction and prefix
predecessors are unchanged. Both modes reuse the existing HTTP runner,
accountant, parser, telemetry, tool execution and cache checks. Elapsed budgets,
nonblocking request ownership, bounded state transactions, cancellation and
durable STARTING/IN_FLIGHT-before-dispatch remain in force.

The internal native `.cold` step means **initial occupied retrieval**. It is not
a zero-cache benchmark. Actual nullable cache/evaluated counts are retained;
later requests still require useful-prefix evidence. Only a complete accounted
retrieval/tool/continuation stage advances occupied proof, and later failure
preserves the last proof. Configured1048576 and separate 32K sanity remain
distinct from occupied capacity.

## Verification and evidence boundary

**PASS: 64 focused source/mock tests** (47 retained regressions and17 new mode
tests), Python3.14.7/macOS. Python3.10 grammar and the byte-identical native body
construction check also pass. Warnings: all model inputs/resource samples here
are synthetic; no live generation, cache qualification or capacity is proven.

The bounded suite covers the existing D3TR driver/real-lock regressions,
accounting/telemetry guards and new public-function native-mode tests. All
external accounting, generation and telemetry dependencies are injected CPU
fixtures. The loopback listener and profile/installer/broad repository suites
are excluded. No test establishes live occupied capacity.

Acceptance covers fresh native binding through64K without comparison files;
legacy/absent-field comparison gates and zero-cache failure; exact measured
image, native context and complete diagnostics; unknown mode, reuse, duplicate
binding, stage skips/revisits and comparison refusal; byte-identical original
failed fixture; three accounted steps before proof;128K dependency/prefix growth;
nullable counters, missing reuse and later failure; restart, STARTING/IN_FLIGHT,
unknown completion, contention, cancellation and duplicate-dispatch gates.

Reproduce the source/mock checks from the repository root:

```sh
python3 -B -W error::ResourceWarning - <<'PY'
import sys, unittest
sys.path.insert(0, 'tests/d3t')
import test_probe
loader = unittest.defaultTestLoader
names = ['test_probe.DriverTests.' + name
         for name in loader.getTestCaseNames(test_probe.DriverTests)
         if 'loopback' not in name]
names += ['test_probe_locking.LockingTests', 'test_accounting', 'test_guards',
          'test_native_capacity']
result = unittest.TextTestRunner(verbosity=2).run(loader.loadTestsFromNames(names))
raise SystemExit(not result.wasSuccessful())
PY
```

Final committed and full-bundle imported checks, Python3.10 grammar, preserved
body/guard/accounting source comparisons, whitespace, four-file scope, secret
scan, author/committer, clean tree and exact feature-remote SHA are recorded in
the external D3TC check artifacts and `final.md`. Independent read-only review
found no concrete defect in the mode/seam changes.

## Next action

Root reviews the source commit and full `D3TC.bundle`, then separately schedules
the native load and occupied trial after D3N32 and the ownership release.
The exact gated new-run command sequence is in the
[probe README](../scripts/d3t/README.md#fresh-native-capacity-run).

Preserve the original D3BASE failed run and all response/body/hash/count bytes.
A new directory is organizational separation, not request-quiescence evidence;
the external completion/reconciliation and lease handoff remain necessary.

**Live capacity: NOT_TESTED. Installer: STOPPED.** No VM access/request, model,
runtime/profile/deployment/storage/transport/Manager/ownership-framework change
or current D3N32 interruption was performed. This source result grants no live
authorization. No install, service activation, disk mutation or reboot occurred.
