# D3TR: two probe review corrections

Source-only correction of the two P2 findings in the supplied D3T review.
Base: `ab881aa1b7953d1cad09e895170f77a6f9ab5f68`.
Branch: `milestone/d3tr-probe-review`.
Session: `01a0a2f6-f0f2-7413-b888-a19df9338bab`.
Author and committer: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.

## Corrections and review matrix

| Finding | Correction | Focused verification |
| --- | --- | --- |
| Status contention can cancel an active request or discard its result | Keep request ownership immediately exclusive/nonblocking. All existing state-lock transactions retry at 25ms intervals with a 5s monotonic bound, including initial/active reads and success/failure publication. Recheck cancellation and deadline after waits before acceptance. | Real status-reader OS-lock contention at initial read, predispatch, active polling, final result and failure publication. Exactly one dispatch; successful cleanup only after PASS. |
| Short comparisons falsely establish 32K occupancy | Advance `highest_proven_window` only on a completed native stage. Retain separate baseline/candidate PASS results and public stage status. | Complete both short comparisons with proof null; enforce 64K initial lower bound; advance only after retrieval/tool/continuation; fail later 128K cache check while retaining 65536 and comparison evidence. Underfilled initial native accounting refuses. |

Exhausted locking is explicit: `state_lock_timeout` stops the request and gets a
separate bounded failure-publication attempt. If both waits exhaust, no unlocked
write occurs: the durable active checkpoint remains unknown and blocks dispatch
until reconciliation. Existing owner cancellation and stage deadlines still stop
the request. A normal successful transfer still receives its existing final
socket cleanup; tests distinguish this from premature cancellation.

No helper seam or source ownership expansion was needed. Changes are limited to
`scripts/d3t/probe.py`, its README, directly relevant probe tests, and this report.
Manager, profiles, accounting, telemetry, backend/runtime/provenance, Q38,
control/client and installer sources are unchanged.

## Checks and result

- **PASS: 21 focused non-network tests**, Python3.14.7/macOS. Thirteen driver
  tests plus eight real-lock tests, including cancellation/reconciliation,
  deadlines, body identity, native accounting/reserve checks and tool sequences.
- **PASS: 3 negative controls**: new active-poll, final-publication and occupied
  proof regressions all reject the exact original `ab881aa` probe source.
- Independent read-only review against the supplied P2 matrix: **PASS**.
- Lock-contention fixtures use independent real OS descriptors/status reads.
  Transport, token counts and GPU/resource samples are injected CPU fixtures.
  The existing loopback network test and broad/installer suites were excluded.
- An initial deadline-test fixture froze sample timestamps and hit the existing
  replay guard; corrected the fixture to keep timestamps increasing. A negative
  control summary initially counted subtests as separate methods; normalized
  that summary. Neither required changing production accounting/telemetry gates.

Reproduce only the focused suite from the repository root:

```sh
python3 -B -W error::ResourceWarning - <<'PY'
import sys, unittest
sys.path.insert(0, 'tests/d3t')
import test_probe
loader = unittest.defaultTestLoader
names = ['test_probe.DriverTests.' + name
         for name in loader.getTestCaseNames(test_probe.DriverTests)
         if 'loopback' not in name]
names += ['test_probe_locking.LockingTests']
result = unittest.TextTestRunner(verbosity=2).run(loader.loadTestsFromNames(names))
raise SystemExit(not result.wasSuccessful())
PY
```

Publication gates require the exact base/branch and author/committer, an explicit
five-file allowlist, filename-only secret scans, Python3.10 grammar parsing,
`probe.py --help`, whitespace checks and a clean committed tree. Final committed
source checks, full-bundle verification and exact helper-pushed remote SHA are
recorded in the accompanying external `result.json`/`progress.md`; the bundle
contains this correction report. No merge or rebase is part of this correction.

## Evidence boundary and next action

Original D3T reported 13 tiny native non-generation accounting calls with actual
15/184/226-token fixtures and three telemetry samples on the old baseline.
Those historical observations remain in
[the original source report](d3t-native-context-source.md); none was repeated
here. They are separate from these synthetic source regressions and prove no
native occupied inference or N76/GPU acceptance.

**Installer remains STOPPED. Live occupation remains NOT_TESTED.** No ai-vm
SSH/request, model/image download/build/runtime execution, service or disk/network
configuration change occurred. Worker1 owns later actual context tests. Next:
review the corrected source/full bundle, then use the separately owned live
authorization and reconciliation process. This source PASS is not live approval.
