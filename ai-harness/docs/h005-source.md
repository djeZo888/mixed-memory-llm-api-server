# H005 harness source candidate

This source-only follow-up starts at `46a6654205275aa7ced12e60ef608dab6a9e7dc2`
and changes only `ai-harness/`. It completes the protected dispatch/action source
seams left by the intermediate checkpoint. It grants no deployment, VM contact,
credential provisioning, inference, push or PR authority. Root reviews this exact
candidate together with Worker1's canonical owner implementation before activation.
Installer work remains paused. Existing models, contexts, image sizes, native pins,
H004 presentation, histories, artifact and seed/approval protections are preserved.

## Dispatch and action ownership

The private app socket is `/run/ai-harness-dispatch/control.sock`, mode0600, with no
TCP fallback or route on8080/8081. The durable gate/relay journal is
`/var/lib/ai-harness-dispatch/state.sqlite`, mode0600 in a service-UID0700 directory
with protected root ancestry. Neither may be mounted into any task workspace or
profile. The launcher rejects these directories and ancestors: keep-id means UID
and socket mode alone do not isolate a mount-exposed capability.

The relay records an exact typed action and durable hold before private UDS
acknowledgement, then sends the unchanged Worker1 NodeAction once. Stable
idempotency lookup precedes boot/generation validation; mismatched key409. Owner
identity/target/expected boot/generation are checked on receipts. Unknown outcomes
persist across daemon restart; no automatic POST retries or replay. The admin UI
can submit a new explicitly confirmed recovery restart with a fresh displayed CAS
and new key. It retains the original unknown operation as evidence.

Hold scope is the actual affected target:

- A Qwen action holds only its lane; the healthy peer keeps serving main, child
  and compaction requests from the existing shared FIFO and byte accounting.
- Image action holds image only. Search/status/control actions do not hold GPU
  inference. Unassigned GPU reset holds no model lane.
- ai-vm reboot holds both text lanes and image; local harness stop/restart or
  ai-harness reboot holds all app dispatch.

Whole-app holds gate new chat/follow-up admission, engine spawn and the final
native prompt boundary after asynchronous preparation. Gateway and image check at
the final pre-upstream boundary; owned preparation reservations remain retained.
Active work keeps its settlement path. UI impact uses target activity/counts,
unknown explicitly, and shows exact affected dispatch scope. Whole-app aggregate
counts are component reservations, not distinct user requests or proof of idle.

An unreachable app is unknown, never idle. A durable hold still protects its next
startup. Explicit interruption may authorize whole-app/node stop/reboot; partial
model actions require the app UDS acknowledgement. Non-inference scopes can be
acknowledged privately without chat, preserving independent status/admin recovery.

The local adapter independently checks exact persisted action/hash/scope/ack under
the existing canonical lifecycle lease, refreshes identities and rechecks CAS
before fixed registered systemd commands. Harness/search use the existing user
manager, status/reboot the system manager. Stop/restart success requires old
invocation settlement evidence; reboot remains unknown until changed boot. No
caller supplies shell, unit, URL or path. Remote GPU reset remains exclusively
Worker1-owned, guarded and typed.

## Reconciliation and degraded service

A stopped target stays held until validated start; matching completed canonical
stop plus validated start also settles only that target's old request ownership. Successful restart/reboot needs
canonical settlement plus validated readiness. A remote changed boot can release
maintenance holds while confirmed unavailable/latched peers remain gated normally,
so a healthy Qwen is not held behind a missing peer. Failed-before-dispatch actions
release only their own hold. Uncertain operations require confirmed recovery; they
are never treated as cancellation or success based on timeout/readiness.

Private request-lane reconciliation requires an exact successful canonical owner
restart/reboot receipt (or matched completed stop plus validated start) and applies only to the corresponding upstream target.
Restarting the local harness does not settle remote ai-vm requests. Image uncertain
ownership is durable and cannot be cleared by passive ready/idle alone. Existing
queued/approval image jobs survive restart with exact identity, seed, reference,
geometry and approval token; old running/saving work remains interrupted and is
never replayed. Canonical settlement proof cannot leak into the next generation.

NodeAvailability preserves healthy-busy backpressure, temporary unknown holds,
soft-state expiry, independent bounded passive text `/v1/readiness` and image
capabilities fallback, and hardware latch provenance. Public telemetry remains
unknown during fallback. A prior-boot latch clears only on fresh authoritative
current-boot exact-required-UUID validation with unchanged UUID set and known
origin/observed-boot boundary. Global inventory failure does not defeat independent
target-positive validation; complete inventories remain required for absence proof.
Same-boot and independent request uncertainty protections remain separate.
Exact Worker1 fixtures and `LATCH-SEMANTICS.md` are copied with provenance under
`server/test/fixtures/h005/`.

## Source deployment prerequisites and rollback

No activation occurred. See [network matrix](../deploy/security/H005-NETWORK.md)
and [local helper procedure](../deploy/admin/README.md). Root activation must
provision the private directories from
`deploy/systemd/ai-harness-dispatch.conf.in` using the existing account, then
explicitly initialize `DispatchFreeze(DISPATCH_STATE)` from the reviewed built
module once at first deployment, before exposing admin. Production open requires
an existing valid schema; never recreate a missing journal to recover a restart.
Back up and retain its holds/receipts with existing harness state. Restrict all
parent paths and SQLite sidecars; status/app share the existing UID, not task mounts.
The main app requires no running status/admin daemon. An exact stale private socket
is removed only after refused connection and matching inode/UID/mode; live or
unknown ownership fails closed. Provision the protected canonical lease helper
source and `/run/llmctl` as documented; do not invent another lifecycle lock.

Credentials stay server-only. Existing node control authority is provisioned only
in a separately authorized activation task using protected credential paths and
systemd `LoadCredential`; no values enter task environment, browser, Git or logs.
Node30008 is separate from unchanged control30000. nginx trusted LAN policy remains
anonymous, with actual-peer denial, exact Host/Origin, CSRF and sibling header
sanitization. Do not expose admin before actual-container denial passes.

Rollback removes external admin routing first, settles exact affected tasks and
restores reviewed prior app/nginx source as a coordinated set. Preserve gate/audit,
latch/quarantine and old files/history. Never globally flush task policy or replay
interrupted work. Prior source does not understand new holds: root must explicitly
reconcile them before rolling back to a version without dispatch gates.

## Verification boundary

Native offline checks cover protected gate/idempotency/unknown/CAS, local fixed
owner/lease/settlement, browser confirmation and scoped healthy-peer behavior,
image persistence/ownership and exact node fixtures. Focused command groups are
`server/node_modules/.bin/tsx --test --test-timeout=15000` with affected tests,
`npm run build` in server, Python admin/launcher fixtures, and the synthetic
`server/test/status-browser.mjs` using fake backends and installed Chrome.
Exact counts and source/bundle hashes are in the task parent report.

Live Linux UDS/peer credential and namespace denial, nginx routes/header handling,
cgroup-v2 socket ancestry/Slirp descendants, task DNS/IPv6/redirect/browser denial,
long-lived tasks after policy watcher failure, systemd signals and managers,
cross-host credentials/node/readiness, actual resources, lifecycle/reboot/GPU reset
and all inference are **NOT_TESTED**. A401 from30000/30008 proves authentication
only. Preserve8081/8082/configured DNS/public research80/443 in later acceptance.
Worker1 canonical stop/restart proof is delivered in `CANONICAL-SUCCESS.md`
(Worker1 source `109d3b4`, 459 focused offline checks per its receipt). Root must
review both exact final sources before enabling combined release.
Serial reachable reboots, all-three-scheduler >=11-minute quiet window with status
polling, and subsequent wake/warm checks require a new root-owned live grant.
