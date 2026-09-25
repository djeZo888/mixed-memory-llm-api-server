# H005 harness source checkpoint

This is an **intermediate SOURCE checkpoint, not a deployment-ready H005 release**.
It starts at `cea6ae80dec6737f96f36ef4e0af7213dd0c0bdb` and changes only
`ai-harness/`. No VM contact, configuration/credential mutation, deployment,
inference, real conversation inspection, push or PR occurred. Worker1 retains
node/runtime/lifecycle authority; its shared v1 fixtures are copied unchanged in
`server/test/fixtures/h005/` with provenance. Existing runtime/model pins and
two 480000 Qwens plus Ada image geometry/approval rules are unchanged.

## Source behavior

- `/` remains the existing chat application. `/status` and `/admin` have a
  separate Node24 entry point (`dist/status-main.js`) and private HTTP UDS at
  `/run/ai-harness-status/http.sock`. Nginx routes these independently of chat8080.
  The optional `status.ai-harness` vhost is read-only. No chat service dependency
  is added to status, and no status dependency is added to chat.
- Any trusted reachable LAN/VPN visitor has identical admin authority. There
  are no accounts, login, user keys or roles. `AdminSecurity` is the future policy
  boundary. Exact Host/Origin checks, signed SameSite/HttpOnly CSRF cookie plus
  header, JSON bodies, no CORS, CSP and actual-peer nginx restrictions protect
  changes. CSRF/path names do not authenticate users or contain task containers.
- Browser paths use `/api/status/v1/system`, `/api/admin/v1/targets`,
  `/api/admin/v1/actions`, `/api/admin/v1/operations/{node}~{id}`. The server alone
  contacts `10.156.100.60:30008/control/v1/node/*`; the early 30000 proposal is
  superseded. It never collects from reconciling legacy control/status/catalog
  GETs, native health, or inference routes. Local node observations/actions use
  the distinct `/run/ai-harness-admin/helper.sock`.
- Polls run every5s, have2s deadlines and stale15s. Each observer retains at most
  one underlying operation even after timeout; late success is discarded.
  Receipt of cached JSON does not refresh component timestamps. Per-component
  CPU (100%=all logical CPUs), memory/pressure, disk/network and GPU facts retain
  nullable values and independent freshness. Public projection removes arbitrary
  payloads, private errors, commands, histories, prompts and credentials.
  Registered root/data/models volume roles render separately with their own
  freshness and nullable capacities; roles are never summed. GPU rows include
  UUID suffix/assignment and sampled temperature range/interval. All visual
  evidence uses synthetic fixtures, including four distinguishable GPUs.
- Configured chat admission observes the passive node endpoint **directly**,
  independently from the status daemon. `--node-control-key-file ABS` opts the
  existing server launcher into that source seam. Without configuration and
  without a previously persisted latch, baseline admission is preserved. Once
  configured, unknown/stale telemetry triggers independent bounded passive
  readiness: text30002/30004 `/v1/readiness` (strict ready/up contract) and
  image30006 `/v1/image-capabilities` (ready with admitting or busy). These routes
  were explicitly approved by root; the new text endpoint is Worker1-owned and
  not deployed in this phase. No `/health` fallback is used. Telemetry display
  stays unknown, while independently ready services can dispatch. If readiness
  is also unknown, dispatch pauses and existing queue/approval work is retained.
  Positive latches, fresh software unavailability and request quarantine cannot
  be bypassed by this fallback. Software observations expire after15s; a stale
  software-unavailable receipt cannot indefinitely block independently healthy
  readiness. Readiness is never evidence of idle.
- Positive authoritative hardware latches persist in `node_hardware_latches`
  separately from `gateway_lanes`. App restart, late readiness and GPU reset do
  not clear them. `hardware_latched_boot_id` retains the authoritative latch
  origin, including a latch inherited from a previous boot; a current boot is
  never substituted for unknown origin. Unknown-origin receipts retain a separate
  first observed-boot boundary and stay blocked on that boot. Clearing requires
  a different boot, complete fresh valid
  inventory of exact required UUIDs, no target faults, and authoritative service
  validation, durably committed before reuse. Existing ambiguous request lanes
  remain quarantined even after fresh status. No replay/retry/GLM fallback was
  added. The one shared FIFO continues across main/child/compaction requests.
- One eligible Qwen serves supported tasks. Permanent last-lane loss promptly rejects
  queued work and releases byte reservations. Image known-unavailable admission
  permanently rejects undispatched queued/approval jobs and cannot reopen on readiness while
  the hardware gate is closed; dispatched partial work and artifacts retain their
  original settlement path. Idempotency, seeds, references, original geometry,
  resize approval and output validation are preserved. Chat/tools expose degraded
  or unknown availability without claiming absent hardware. A healthy busy
  image service with `admitting:false` stays eligible; its owned lane schedules
  the waiters. Temporary observation failure holds pending work, not terminally
  fails it. A hold during image preparation retains the existing reservation.

## Explicit follow-up before release

Root requires a protected harness dispatch-freeze acknowledgement before **local
and remote destructive actions**. This checkpoint does not implement that
interlock. The admin relay rejects every stop/restart/reset/reboot with422, and
the local helper independently rejects destructive actions. Registered starts
use canonical node/systemd owners, durable node idempotency/audit, asynchronous
receipts and generation/boot checks. The local helper's injectable freeze seam
is fixture infrastructure, not an enabled production bypass. There is no flag
that enables destructive relay without completing source review.

Immediate fresh Worker2 source follow-up must:

1. Add a protected UDS-only app admission interlock, inaccessible through nginx,
   gateway/session tokens and task mounts. Freeze the affected new chat/follow-up,
   child/compaction and image dispatch before acknowledging; preserve active
   ownership, queue accounting and uncertain results.
2. Bind freeze/impact to operation idempotency and current boot/generation;
   recheck at actual node-owner dispatch. Unreachable app means unknown work,
   not idle. Explicit interruption can authorize whole-app/node stop with unknown
   work, but cannot silently waive the required boundary.
3. Resume only after validated readiness or explicit failed-operation
   reconciliation; persist uncertain state across daemon/app restart. Complete
   remote and local service stop/restart, dedicated reset and orderly reboot.
   Reboot success requires a later changed boot. Complete admin impact display
   with protected aggregate activity (no histories); unknown counts stay unknown.
4. Integrate exact Worker1 producer/action fixtures and inspect source together.
   Test interruption/late work/idempotency/conflict/restart/no-replay end to end
   before root authorizes a deployment task.
5. Integrate Worker1's new passive text `/v1/readiness` implementation and confirm
   its exact alias/ready/state/status contract against these consumer fixtures.
   The source fallback and production adapter-to-broker outage/busy/latch fixtures
   are included here, but actual cross-host readiness behavior is NOT_TESTED.

## Credential provisioning template (not performed)

ai-vm authority remains `/etc/llm-server/control-api-key`, consumed there as
`/run/credentials/llm-control.service/control-api-key`. Node API retains that
existing protected machine authority. No new key is created or rotated here.
An authorized activation task must securely provision its reviewed copy to
root-owned0600 `/etc/ai-harness/control-api-key`, with protected ancestry.
The independent system unit uses `LoadCredential=control-api-key:...` and
`AI_HARNESS_CONTROL_KEY_FILE=%d/control-api-key`.

The existing user chat service needs a separately reviewed owner-only file copy
of the same authority passed via the **path-only** `--node-control-key-file`
argument (or an approved systemd credential delivery for that user service).
No key belongs in argv, environment values, browser JS, task-container mounts,
nginx output, diagnostics or Git. The launcher uses a clean environment and
engines receive only their existing ephemeral inference session token. Remove
no durable latch to compensate for missing credential configuration.

## Deployment and rollback boundaries

Do not activate this intermediate checkpoint. After the follow-up passes root
exact-source review, use [network activation/rollback](../deploy/security/H005-NETWORK.md)
and [local helper procedure](../deploy/admin/README.md). Build from unchanged
lockfiles with Node24, preserve the current harness release/data and protected
credentials, and apply only root-reviewed source/units/includes/policy. Never
use the paused general installer. Provision the independent daemons/UDS modes
and passive30008 transport; validate against synthetic endpoints before real
node operations. No model/runtime/GPU pin or storage-guard change belongs here.

Actual Linux nft socket/cgroup policy, Slirp/conmon placement, DNS/IPv6/redirects,
Chromium access, nginx inherited configuration, UDS/SO_PEERCRED, systemd signals,
cross-host transport/credentials, real boot/lifecycle effects and inference are
**NOT_TESTED**. Source fixtures do not establish network containment. Keep admin
unexposed until the actual-container matrix passes. Preserve gateway8081,
search8082, public research and the original image approval peer restrictions.

Rollback removes external admin routing first, settles/drains exact affected
tasks and restores the reviewed prior harness/nginx source. Keep the new scoped
firewall while any H005 task exists; never globally flush or prune. Restore
chat without deleting latches/quarantine or replaying interrupted work. Preserve
independent status evidence and helper audit for review.

## Focused verification commands

From `ai-harness/server`: `npm ci --ignore-scripts --no-audit --no-fund`,
`npm run build`, and `./node_modules/.bin/tsx --test --test-timeout=15000
test/{status-service,admin-security,observer-cache,node-availability,backend-readiness,gateway,image-broker,config,app}.test.ts`.
The synthetic UI fixture is `node test/status-browser.mjs /ABS/OUTSIDE/GIT/status.png`
after build; it uses installed Chrome with a fresh profile and fake backends,
never a production startup, model or chat.

From `ai-harness/web`: `npm ci --ignore-scripts --no-audit --no-fund`,
`npm run build`, `npm test -- --run tests/{availability,composer}.test.tsx
tests/{store,api}.test.ts`.

From repository root: `python3 ai-harness/deploy/tests/test-task-egress.py`,
`python3 ai-harness/deploy/tests/test-run-engine.py`,
`python3 ai-harness/deploy/tests/test-run-server.py`,
`python3 -m unittest discover -s ai-harness/deploy/admin -p 'test_*.py' -v`,
`bash -n ai-harness/deploy/{run-engine,run-server}.sh`, `git diff --check`.
These tests contain synthetic data only. Exact successful counts, commit IDs
and bundle identity belong in this task's parent REPORT.md.
