# D3MON — cheap occupancy telemetry source

Worker2 source-only task, base `dad2d58b57ab2367dee254cff1a885567b0c76f4`,
branch `milestone/d3mon-cheap-telemetry`.
Session `01a0a359-ed17-7921-95e7-20f103c50964`.
Author/committer: CodexAIagent <133749519+djeZo888@users.noreply.github.com>.

## Change and evidence boundary

D3T now collects fresh VmRSS/VmSwap at1Hz without reading smaps_rollup in
periodic samples. Full Rss/Pss/Swap is required at admission and before/after
each request. Snapshot schema2 distinguishes cheap/full explicitly and rejects
stale rollup fields on cheap rows. PSS is checkpoint evidence, never a1Hz maximum.
The same bounded sampler consumes complete incremental native graph/cache/error
logs and retains all existing resource floors and runtime checks. Process start
ticks/state, paused/restarting/dead state, restart count and host swap consistency
are also checked, following Worker1's supplied cheap sampler strategy.

After successful transport and complete JSON/SSE response validation, one fixed
stdin command requests the terminal full checkpoint; queued cheap
samples remain checked. A failed/missing post checkpoint cannot publish PASS or
advance highest_proven_window. Original available response bytes/hash/transport
status survive a later guard failure, with credential redaction retained. Failure
first cancels its owned socket and closes its exact sampler without a PSS request.
Unconfirmed backend completion explicitly leaves the terminal checkpoint
UNAVAILABLE; missing evidence and the original failure remain preserved. No extra API
request, retry, fallback, deadline extension or state/lock ownership change.

Worker1 supplied sanitized D3PERFVM source and evidence outside Git. Its unchanged
N76/32K/image/container/body/settings/112-thread comparison returned64 decode
tokens in6.607434s (9.686tok/s), versus117.054310s under earlier full telemetry.
Both inputs were1370 tokens, but cheap evaluated1197/cached173 versus1370/0;
cache and order differ, so this is **correlation, not causal speedup proof**.
Cheap wall27.488748s, prompt20.857048s;27 active samples took0.036–0.069s each.
Full finalPSS/guards passed in the supplied evidence. The separate supplied
result's `full_sample_pass:false` is retained: this was not continuous full-PSS
acceptance. Those historical measurements do not test this implementation.

## Focused verification

Initial `b436aee4` verification: **81 bounded synthetic source tests PASS** on macOS/Python3.14.7, including
the retained64 D3TC checks and17 telemetry/evidence regressions. Python3.10
grammar, whitespace and exact unchanged native body/accounting/request helpers
also passed. Root/architecture subsequently found the failure-path blocker below;
that initial review did not establish final source acceptance.

### Root-review correction

Client cancellation can leave backend prefill running. The follow-up moves the
existing successful response parser ahead of any full-checkpoint command and
removes all failure-cleanup PSS requests. `done=True`, transport error, partial
JSON EOF or incomplete SSE finish/[DONE] cannot earn a checkpoint or PASS.
`transfer_done` and `backend_response_complete` now identify separate evidence.
Available response bytes/hash/status are preserved again after bounded owned
sampler closing, without a PSS read, idle query, backend wait or new request.
Normal successful completed responses still require one full checkpoint before
PASS/window advancement. Guards and snapshot schema are unchanged by this fix.
**Correction: 82 bounded synthetic checks PASS**, including explicit continuing
backend cancellation/error fixtures and zero terminal commands for partial
JSON/SSE. Independent correction review reports no blocking findings.
Initial bundle/checks are retained under external `initial-b436aee4/`; corrected
focused, committed and bundle verification results are in external `final.md`.

Synthetic tests execute the collector against controlled proc/CLI/log fixtures,
checking actual smaps read paths rather than only source strings. They cover
repeated cheap reads, full admission/pre/post, missing/malformed metrics, stale
PSS rejection, process/host/GPU/root/mount/swap/OOM/native refusals, post-failure
no-PASS/no-highest behavior, original evidence retention and one dispatch.
Existing native body/accounting, retrieval/tools/cache, cancellation/deadline
and real OS-lock regressions remain in the bounded suite. Exact final results
and committed/imported-bundle checks are recorded in external `final.md`.
The first development run's admission-artifact assertion failure is retained
outside Git: its fixture was corrected to require exact rejected evidence and
unchanged state/config. The original failure was not retried as a live operation.

Reproduce only the bounded D3T suite:

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

**Live new sampler, generation, native occupied capacity/performance: NOT_TESTED.**
No ai-vm SSH, model/profile/runtime/thread/NUMA/Manager, Qwen or installer changes
or tests. Source scope is guards.py, monitor seams in probe.py/README.md, focused
D3T tests and this report. Root and independent review are required before any
native-capacity trial; this source task performs no automatic live execution.
Early schema/checkpoint/result seam, supplied input, session/check records,
full D3MON.bundle and final.md are preserved outside the repository.
