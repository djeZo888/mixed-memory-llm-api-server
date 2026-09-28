# H020 status identity repair — Worker2

Source candidate: `739462b7e246f92a3c4161c4535a1a2d8a0886f2` over root
`e256814c6f2b9cc421ba68cde3febd1e0a6c9aa8`. Native Mac-worker2 session
`01a0e62a-3ce0-7432-9a50-c750e08bee7a`, launched 2026-09-28 03:58:42 UTC;
hard deadline 04:28:42 UTC. Root coordinates/reviews/publishes; no push from worker.

## Result and cause

Source/tests and isolated status-only staging are complete. **Not activated at
this report revision; exact root GO is still required.** Running status PID301728
started 2026-09-27 07:32:20 UTC from release
`7143c17d73173db9364b77956679c86d7026a4ae`. Its actual executable is the retained
Node24.21.0 binary, with cwd ending `/ai-harness/server` in that release. Its
registry SHA256 is `b9b9120afda6d9c007008a9222be375aa49f82b43faab07ba1c47f6256acd3cd`;
there is no active-frontier file in that older release.

The loaded systemd unit instead points at
`34959c67baea0d8a357cbea4cefac1658f3553f0-h019-prep01`. Drop-in
`30-h008-registry.conf` changed 2026-09-28 03:21:06 UTC without restarting status.
The base unit and 10/20 drop-ins remain present; `NeedDaemonReload=no`. The loaded
H019 registry hash is
`a2d69b9ba6ddba922b9ec128ce2a7cf89e16602154d47fafc5376dd3f1bf5ddc`;
its active selection is MiMo with exact bytes hashed
`6fac2925b81e0c40154635643a327f8f3149f7211cf8b78a4f321f6d5b09dc22`.
Both releases have status-main.js hash
`14ad79727feda98572e345d633faa0986a0f3f5afd80c818a035655832e87287`.

A single existing passive native-status read through ai-harness showed separate
MiMo ready and GLM unqualified/not-ready rows sharing a reported required GPU UUID.
The old registry omitted MiMo, so sanitization removed that service and its GPU
impact identity. The old UI called impact IDs “Assigned”. The source selection
helper also replaced configured display names with model-specific literals.
`passive-before.json` retains only compact descriptive/observation evidence; raw
responses stay outside Git. No inference or benchmark result was requested.

## Patch

- Optional configured model descriptors preserve model/instance display names,
  expected native alias and frontier selection group. Selection is separate
  runtime metadata from the trusted active-frontier file; no label rewriting.
- Fresh node/service evidence and exact expected-alias match gate current
  readiness. Missing, stale, unavailable and mismatched observations cannot make
  a configured model ready. Dormant rows are explicit; nonselected raw-ready
  observations produce a selection conflict, never current ready health.
- Observed model alias, deployment label, node/service and required UUIDs remain
  separate from configured names. Missing observed instances expose null IDs.
- Measured GPU UUID rows join only matching projected-ready service dependencies.
  Required UUIDs and action impact IDs are not process-occupancy evidence. The UI
  labels those relationships explicitly and masks readiness on transport loss.
- Distinct Qwen aliases/instances and unsupported nodes remain visible. Seven
  action IDs, node/transport/credential allowlists, confirmations, dispatch locks
  and queues are unchanged. No public credential/transport expansion.

The registry still does not route every workload. See
`ai-harness/docs/status-registry.md` for actual endpoint owners (including GLM
30010/v1 and MiMo30012/v1). Deployment labels are observer data, not process
attestation. The MiMo 950000/65536 values are the preserved deployed selection,
not a new qualification or a benchmark result. Ordinary Sova chat remains paused
after its separately unresolved HTTP400 delegation failure.

## Validation

- 17 focused tests pass across frontier-registry, system-registry and
  status-service. Cases include editable labels, both selections, missing/wrong
  alias, stale node/service/GPU, absent measured GPU, both frontiers reporting
  ready, unknown selection, two Qwen instances and unsupported/missing nodes.
- The old missing-node fixture incorrectly expected five ai-vm rows; it now uses
  configured row count and executes the remaining no-authority/redaction checks.
- TypeScript checks and declarations for the three changed status modules pass.
  Retained esbuild compiles only those three JS modules; no dependency download,
  native engine build or inference runtime build occurred.
- Existing synthetic Chrome status/admin test passes on final compiled modules:
  configured labels, selected/dormant rows, full UUID/dependency language,
  desktop/mobile, transport-failure masking, unchanged typed action/recovery
  confirmation and no page errors. Synthetic only, no live action submissions.
- Staged compiled registry loads as the ordinary ai-harness account and selects
  MiMo. Directory comparison against H019 reports exactly seven changed files:
  three JS files, three corresponding declarations and system-registry.json.

## Exact activation proposal

`deployment-manifest.json` lists byte hashes, base and candidate paths.
`systemd-proposed.diff` adds only
`/etc/systemd/system/ai-harness-status.service.d/40-h020-status.conf`, setting
WorkingDirectory and resetting ExecStart to the reviewed status-main.js path.
No symlink/current pointer, app unit, helper, search or native owner is changed.
The new release derives from retained H019; its active-frontier file is identical
and no protected state/credential files are copied or changed by this patch.

After exact root GO, verify manifest and unchanged current state, install that
single drop-in (root:root 0644), run `systemctl daemon-reload`, then run exactly one
normal `systemctl restart ai-harness-status.service`. Verify actual PID/cwd/args,
loaded unit/selection hashes and passive `/api/status/v1/system` and `/status`
rendering. App must remain inactive. No inference, model switching, benchmark
readback, other service restart or hardware action is part of acceptance.

Rollback preparation: retain both the actually running `7143c17...` release and
loaded H019 release. The new drop-in is additive; removing it restores the H019
loaded-unit path, **not** the old running process. To restore the exact pre-H020
status executable, a separately reviewed drop-in must target the retained
`7143c17d73173db9364b77956679c86d7026a4ae/ai-harness/server` with its unchanged
status-main.js; only status would restart. This knowingly restores the old
mislabel limitation. No rollback has been executed or automatically authorized.

Private task directory retains full unit/process receipts, original failed-test
logs, raw passive DTOs, build outputs and screenshots. Early staging used a tar
with macOS metadata warnings and directory modes needing correction; it was never
activated. Final staging uses a files-only Python tar, original base directory
modes, ordinary-account import verification and a full release diff. The earlier
4e05c1b candidate is retained but superseded. No failure evidence was removed.

Prepared activation commands are in `activate-status.sh` (precondition/hash checks,
only status drop-in/restart). Copy its reviewed drop-in to the named temporary
path before running it on ai-harness under root GO. If any precondition changed,
stop and re-review rather than broadening the command. Rollback's exact previous
process configuration is `rollback-status.conf`; after separate root rollback GO,
install it over only the H020 status drop-in, daemon-reload and restart only
status once. Never remove the new release or retained evidence during rollback.
