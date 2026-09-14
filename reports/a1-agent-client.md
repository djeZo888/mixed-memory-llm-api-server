# A1 bounded client and protocol acceptance

Date: 2026-09-15. Worker: Mac-Worker2. Branch: `milestone/a1-agent-client`.
Base: `7171167`. Scope is client-only implementation on the isolated worker.

## Checkpoint status: IN_PROGRESS

The stdlib transport, disposable fixture, acceptance runner, regression tests,
and OpenCode provider documentation are being integrated. Initial end-to-end
mock HTTP tests passed (9 tests); socket cleanup warnings and review findings
are being resolved before final validation. This checkpoint is not completion.

| Check | Status |
| --- | --- |
| Initial deterministic end-to-end HTTP scenarios | PASS, preliminary |
| Complete synthetic regression suite and final review | NOT_TESTED |
| Real VM endpoint/protocol/model fixture | NOT_TESTED |
| Actual OpenCode CLI/tool compatibility | NOT_TESTED |
| Ubuntu 24.04 clean installation | NOT_TESTED; separate I1/I2 |

No VM mutation, live inference, key retrieval, package installation, server
change, model download, or installer implementation was performed. Existing
current-state deployment claims are stale; Worker1 must publish the actual
endpoint, model ID, parser/reasoning configuration, limits and auth policy.

Next action: complete synthetic regressions, publish final evidence and docs,
then hand off the checked feature branch and A1.bundle for integration and V1.
