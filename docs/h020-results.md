# H020 — correct status identity and plan an optional Codex harness

## Outcome

The status-only release was activated on September 28, 2026 at **04:20:28 UTC**.
Its passive API and live desktop/mobile browser checks passed. MiMo appears as
the selected, observed frontier; GLM remains an explicitly dormant alternative.
Only MiMo appears in the frontier GPU's ready-model dependency list.

The [Codex harness plan](../ai-harness/PLAN-CODEX-HARNESS.md) is published as
**plan only**. No Codex integration or provider configuration was executed.

## Why GLM was still displayed

The running status process used release `7143c17d`, while its systemd definition
already pointed to the later H019 release. Changing the unit had not restarted
the old process. That older registry did not include MiMo, so it filtered out
MiMo's observation and still displayed the retained GLM identity.

Two source problems compounded this: selection replaced configured names with
hardcoded labels, and the UI called GPU action-impact IDs assignments. Those
IDs describe which services depend on a device, including dormant alternatives;
they do not prove that those models are running on it.

## Configuration and observations

| Source | Responsibility |
|---|---|
| `ai-harness/config/system-registry.json` | Host/service inventory, model and instance display names, expected native aliases, selection groups, observation transports and endpoint references |
| Deployed `ai-harness/config/active-frontier.json` | Selected frontier; live MiMo selection bytes were preserved |
| Existing authenticated node observations | Native alias, deployment label, readiness, observed capacity and measured GPU UUID/telemetry |
| Existing gateway/frontier/image clients and runtime owners | Actual workload URLs, launch and GPU placement policy; these were not migrated by this repair |

The status inventory is centralized. **The entire inference configuration is not
yet one file.** The [configuration guide](../ai-harness/docs/status-registry.md)
documents the separate workload endpoint owners. A reviewed status restart loads
configuration edits; there is no automatic mutation or hot reload of runtime
placement. Labels and registry membership cannot confer readiness or permission
to execute an administrative action.

Status now distinguishes configured identity, selected/dormant state and observed
identity. Missing aliases, mismatches and stale observations cannot report a
configured model as ready. Conflicting observations remain visible. GPU joins
require an exact measured UUID plus a fresh, matching, currently ready service;
the page labels these as dependencies, not independently measured GPU-process
occupancy. Qwen's two instances remain separate. Offline configured hosts and
missing services stay visible with unknown state.

## Validation and deployment

- Worker2: 17 focused tests, status-module typechecking and synthetic Chrome
  status/admin checks, including desktop/mobile and loss of status transport.
- Worker1: independent exact-source review; 19 focused, six inherited regression
  cases and six additional cases passed, plus status-entry typechecking. These
  overlap Worker2's checks and are not 48 unique tests.
- Root review corrected an endpoint-documentation error and required a regression
  for contradictory dormant-ready evidence before activation.
- Runtime source: `739462b7e246f92a3c4161c4535a1a2d8a0886f2`. Staged bytes and
  the unchanged live MiMo selector were checked before installing one status-only
  drop-in and performing one normal status-service restart. New status PID527553
  runs the reviewed release. App remains inactive with PID0.
- Live `/status` checks passed at 04:23:04 UTC at 1440×1000 and 390×844, with
  no page errors or viewport overflow. All eight browser requests were GET-only
  status/assets/passive-API requests returning HTTP200.

The first browser forwarding attempt had an invalid Host and received403.
Verification then used SSH SOCKS while preserving the existing public Host;
no Host guard, proxy or security setting was weakened.

Source review and preparation evidence are in the
[Worker1 review](../reports/h020-review02-20260928/REVIEW.md) and
[Worker2 report](../reports/h020-status-repair-20260928/README.md).
Original failures and superseded staging receipts remain historical evidence.

## Boundaries and remaining work

No inference request, model switch, ai-vm service restart, hardware change or
benchmark-result check was performed for H020. The independent near-950K request
was left to its existing owner and deadline. Passive status observations are
not a completion result for that benchmark.

Ordinary Sova chat remains paused after the separate MiMo child-request HTTP400
reported in [H019](h019-mimo-finalization-results.md). This status repair does
not claim to repair that workflow. The feature branch remains a draft while
that integration acceptance is incomplete.

The Codex proposal retains MiniMax, reuses Sova's UI/storage/queues/tools, and
begins with a bounded Responses compatibility test against the actual local
models. Engine implementation, native tool/context/lifecycle acceptance and a
matched-task comparison follow only after a later execution request.
