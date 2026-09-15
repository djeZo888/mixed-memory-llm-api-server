# V2 ordinary-user client verifier

2026-09-15 — source-only delivery. Incoming Revision2 superseded the original
installer receipt task: receipt/challenge/producer approval and bootstrap
composition are **DEFERRED**. The resulting command is a source-run ordinary-user
verifier against an existing configured prefix. No installer, shared client,
lock, lifecycle, control, runtime, or agent-protocol source was modified.

## Result and behavior

`python3 -B scripts/client/verify.py --prefix ABS --output-dir NEW_ABS` creates a
private bounded report and the exact V1G2 disposable fixture. It verifies the
reviewed installed client bytes, actual versions and authenticated model-list
identity; requires actual native read/read/edit/exact-test/final behavior; checks
immutable test bytes; independently reruns the tests; and verifies process
cleanup. Failures and length termination remain private FAIL diagnostics.

No arbitrary command/body/model/pin override or challenge option exists. Context,
output and reasoning come from the configured prefix. Source artifacts and raw
private evidence are hash-bound. Native counts remain distinct from provider
usage. Detailed invocation, limits, privacy and verification commands are in
[client verification](../docs/client-verification.md).

## Validation

| Check | Result |
| --- | --- |
| Full client suite | PASS: 103 tests, one optional installed-prefix test skipped |
| Native parser + real process/outer-deadline regressions | PASS, included above |
| Offline reviewed-cache/native integrity against existing V1G2 prefix | PASS: 29 packages, 3,650 files |
| Exact original V1G2 fixture bytes and five baseline assertion failures | PASS, no import errors |
| Actual pinned OpenCode against synthetic authenticated HTTP | PASS on final source, exit 0, 1.069414 s native run |
| Native tool flow | PASS: read/read/edit/bash; five starts, five finishes, final text |
| Exact requested tests, immutable bytes, independent final rerun, cleanup | PASS: all eight checks true |
| Model identity before/after, key persistence scan, private raw hash | PASS |
| Source manifest equals actual passing run's manifest | PASS |

The actual client versions were Node `v24.21.0`, npm `11.19.0`, OpenCode
`1.18.31`, and plugin `1.18.31`. The final runtime source digest is
`91110fd3b069a6d313b450c7f8bd08f62f37e87c1a09ea3852e5b75597146ace`.
[Exact artifact hashes](v2-source-manifest.json) and
[sanitized synthetic evidence](v2-synthetic-http.json) accompany this report.

Two preceding synthetic runs truthfully failed on denied edit permission; their
private reports remain unchanged and the sanitized evidence retains both FAILs.
The final permission rule follows the pinned binary's actual implementation:
edit paths are relative to its non-Git worktree root `/`. It permits only this
fixture's implementation, without a wildcard expansion. No human modified the
verification workspace implementation or tests. The deterministic HTTP test
double requested the fix; the actual native OpenCode tool applied it.

Independent review also found and fixed a deadline interaction: an outer alarm
could interrupt child cleanup. A real TERM-ignoring process regression now
proves cleanup and partial diagnostics survive that deadline. Immutable tests
are rechecked after the independent execution as well as before it.

Validation classes remain distinct: source unit tests, real local process tests,
pinned client against synthetic HTTP, previous V1G2 live evidence, and a new
coordinated live invocation are not interchangeable. The short synthetic elapsed
time is not an inference-speed measurement. No provider usage was fabricated.

## Warnings and next action

- **Live V2 GLM/Qwen acceptance: NOT_RUN.** No request lease or live generation was
  used, and no VM services/models/disks were mutated.
- **Direct separate-host transport: GATED.** N1C owns implementation of the
  approved canonical RFC1918 literal HTTP(S) policy; that source is not yet
  integrated here, so V0 loopback validation remains unchanged. No remote
  allowlist was guessed and no prefix configuration was hand-edited.
- **Installer receipt/import/approved registry: DEFERRED.** No production
  acceptance or installed verifier launcher is claimed.
- **Known GLM invalid-model protocol FAIL: preserved.** This client-only verifier
  does not test or override protocol/server readiness.
- **Practical hardware contexts, fresh Linux installation and full installer:
  NOT_TESTED.** Synthetic context values are not hardware approval.

Next: root reviews the source bundle, integrates Q38C/N1 changes under their
explicit ownership, then supplies one bounded direct-endpoint live request
lease. Exactly GLM5.3 and Qwen3.8 acceptance remain the live finish priorities.
