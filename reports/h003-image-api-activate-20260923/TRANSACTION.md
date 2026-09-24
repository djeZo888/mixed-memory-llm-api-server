# Proposed narrow activation and rollback

**Not executed. No host contact authorized at this checkpoint.** Before action,
consume the final capacity HANDOFF, exact approved manifest, SOURCE-PACKET and
current COORDINATOR-NOTE together with separately transported root GO. Root GO
must bind final manifest bytes/SHA256, this helper SHA256, exact source hashes and
capacity window release. Null pending hashes in SOURCE-PACKET are not approval.
Use final measured/root-visual receipts; reconcile the stale capacity snapshot.

## Fixed files and owners

- Source: `/usr/local/lib/llm-server/image-api/scripts/image_api/{app.py,protocol.py}`;
  root:root0644. Verify all seven existing and replacement source hashes.
- Manifest: `/etc/llm-server/image-api.json`, root:root0644. Retained predecessor
  SHA256 `12969d9966f222217891791f0a2d6f4202ee2b0a7f83ef36f18d734a96721b07`.
  Preserve the six accepted generation records exactly; add only final approved
  measured operation/reference-count/size records. No count-based qualification.
- Existing API owner: `llm-image-api.service`; installed recovery command
  `/usr/bin/sudo -n -- /usr/local/libexec/llm-image-backend-recover`.
  Installed runtime: `/data/services/image21-runtime-20260923/source/service.py`.
  Runtime config SHA256 `4ded6e9261b512d952c5033b0634d4eaba79fa115685635c6307defe78c11d76`.
- Reuse `Runtime.guards()`, installed registered storage/root guards and its
  `RegisteredStorageBinding`/`AnchoredRoot`, plus canonical lease
  `/run/llmctl/lifecycle.lock`. Do not substitute helpers from an old checkout.
- Private transaction/rollback: `/data/services/h003-image-api-activate-20260923`.
  Reviewed helper/payload staging: `/data/services/h003-image-api-activate-20260923-inputs`;
  prepare through the same installed anchored storage guards, root-owned0700.

## Exact sequence after GO

1. Confirm capacity explicitly released its lease and sole-caller window, all
   accepted operations settled, API PID/listener absent, native backend healthy.
   Retain the failed-stop classification; accept stopped `inactive` or `failed`
   state with MainPID0, never rewrite it as successful ASGI shutdown.
   Read-only harness broker check must establish zero queued/active image jobs
   before API startup: its existing reconcile path pumps queued work when idle.
   Root's sole-caller window must cover no new image submissions or approvals
   from this check through Worker2 handoff; a one-time queue snapshot is insufficient.
   If pending work exists, stop for root coordination; do not cancel jobs or start.
2. Collect fresh private before evidence: installed source/config/unit/drop-ins/
   recovery identity, protected key identity, API state, image container/run ID/
   init PID/GPU model PID, both text container IDs/PIDs/StartedAt/configuration
   hashes/native480000 contexts, all-device free memory, host MemAvailable,
   `/proc/vmstat` pswpin/pswpout and each current cgroup's memory.current,
   memory.swap.current, memory.events and memory.swap.events. Retained PIDs below
   are comparison operands, not current observations. Refuse unexpected drift.
3. Assemble private payload with `source_commit` exactly9de9ecf, `source` containing
   all seven exact UTF-8 files, `qualification` the final manifest byte-preserving
   UTF-8 string, and `manifest_sha256` the root-approved SHA256. Offline
   `install.py --check-payload` must pass. Validate the manifest with reviewed
   `image_api.protocol.qualification(strict_json(bytes))` in the retained local
   venv before staging. Bind staged helper/payload hashes to GO before execution.
4. Invoke once, as root on ai-vm, the staged `install.py --install` with that
   protected payload on stdin. It requires the API already stopped, takes the
   canonical lease, runs installed guards, privately preserves previous bytes/
   metadata and installs only app/protocol/manifest via same-filesystem fsynced
   atomic replacement. This is three individual replacements while the owner is
   stopped, not a filesystem-wide atomic transaction. It compensates partial
   failure; verify rollback receipt before any further step. `installed.json` is
   explicitly provisional: preserve successful helper stdout/exit plus final
   hashes before startup. A compensation/failed exit forbids proceeding even if
   an earlier provisional receipt exists. Do not invoke old FHD
   helper, update examples, change units, reset failure history or daemon-reload.
5. Release the lease before **one** `systemctl start llm-image-api.service`.
   Startup `Owner.reconcile()` invokes the existing recovery helper once, replacing
   the image backend and executing its existing fixed generation warmup once.
   Do not call recovery separately or send any images POST. Existing warm request:
   1024x1024 teapot, seed42, n1,40steps,CFG1,CPU RNG; no edit/capacity rerun.
   Respect the existing 900s recovery budget; no second start/retry on failure.
   Readiness observation may span the unit's920s startup allowance; use short
   bounded GETs while reporting progress, not the old FHD helper's200s cutoff.
6. Collect startup-owned telemetry/evidence and fresh after counters. Require
   >=5% sampled GPU free and >=15% host available margins; report actual coverage,
   global swap deltas and old/new cgroup values, not a blanket zero-swap claim.
   q1 retained148MiB/155086848bytes is historic; no text restart/tuning.
   Never subtract counters belonging to different image cgroups after reload.
7. Authenticated GETs only: ready=true, admitting=true, busy=false;
   `/v1/image-capabilities` exactly matches the approved records and pins, expected
   geometry/input_padding, opaque output PNG/b64_json metadata; `/v1/models` alias.
   Missing/invalid auth must return401. Compare protected key bytes privately with
   before, verify credential root:root0440 and listener/proxy identity/reachability
   through existing published transport. No secret in argv/environment/logs.
   Synchronous response/seed behavior is source+fixture evidence here; Worker2
   owns later live inference acceptance. Do not claim a new public image response.
8. Existing harness timer calls `ImageBroker.reconcile()` after authenticated
   ready+idle; recheck zero queued/active jobs and confirm broker lane idle/admission
   restored with zero new jobs, using existing read-only broker/store evidence.
   No harness restart, rebuild, DB edit, key rotation or manual adoption path.
   Capture final hashes, guards, old/new image IDs/PIDs and warm receipt/count;
   prove both text identities/settings unchanged. Explicitly release sole window
   for root-authorized Worker2 and cease actions while acceptance owns it.

## Rollback

Before installation, privately retain all seven source files, manifest and exact
metadata plus unit/config/key identity. `install.py --rollback` restores only the
three mutated files from this task's protected backup after verifying hashes and
requiring API stopped. It never starts/restarts anything. In-process install
failure compensates touched files, including replace-success/readback-failure.
If rollback itself partly fails, preserve the emitted verified-restored list and
remain stopped; no automatic retry or claim that all predecessor bytes returned.
If startup began, establish API stopped outside the lease and known native
settlement before source rollback; do not force classification or infer idle from
health alone. Unknown native outcome stays closed for root. A second warmup or
restoration start is not authorized by this one-start transaction.

Source rollback returns stopped predecessor bytes; it cannot restore the old
image PID/container after the intentional startup reset. Record actual identities.
Retained image container `ca750f6dca24f2117ef8b91d0d28a1688d4a66b0bd671622840b8b1e243cfb8d`,
initPID146684/modelPID147055 and run `a5a5aad28d4f4f01851fe0008f132e8e` require fresh comparison.
Retained text IDs `a2afad49380a592739944f2766f5547687a5cf302badd375bda14fffdb09f75c`
(PID53058) and `a71924b9e7fa4f72c6eeefc243731f59bdc0d951b817de1d32f32dbfd67f450e`
(PID32207), both480000, must remain unchanged.
Harness accepted9de9ecf / engine11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87 /
PID49895 remains untouched; chats/data/proxy secret remain private and preserved.
