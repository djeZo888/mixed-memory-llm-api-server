# H036 protected interruption recovery

SOURCE/FIXTURES ONLY. Execution remains **BLOCKED** until current root-authorized
readback, separately reviewed physical cleanup/evidence, and an explicit GO.
The retained container is still only known as created/PID0; that is not absence.
This command performs no cleanup, networking, inference, replay or service action.

The one supported disposition is physical release of one named interrupted
Codex owner and its exact accepted GPU0 request set. Original release `74507f64`,
its pinned main/gateway source hashes and fixed `DEFAULT_UPSTREAMS` endpoint bind
the original request. A root-protected normalized proof joins archived evidence
hashes with authenticated same-machine SSH host-key lineage, a newer whole-node
boot after acceptance, a fresh native runtime, and a reviewed absence of durable
request replay. No old per-request PID is required. Root must review the underlying
captures; the CLI checks the closed attestation schema and every archived hash,
not arbitrary text inside historical command output. Synthetic test fixtures
are never operational authority. Exact task container/image/user/workspace/native
history lineage and supported exact removal followed by `container exists` exit 1
are separate mandatory evidence.

The proof and archived captures must be root-owned regular files (no writable
ancestors, symlinks or group/world write), readable by the existing app user.
Current release files, effective environment and preserved deployment unit may
be app-owned: their exact paths, UID, mode and SHA256 are separately checked.
The proof pins the DB path/device/inode/UID, complete logical snapshot, current
deployed semantic build and source commit. Its lifetime is at most 15 minutes.
Current root-owned `/etc/nginx/` configuration, a served 503 capture no older than
five minutes at issuance, and the exact observed nginx worker PID/start-tick set
bind maintenance. A reload/config change invalidates the proof.

## Separately authorized operator sequence

1. Root reviews/deploys the exact integrated build, preserves all chats/native
   history/files, and holds existing maintenance. Stop the app and establish a
   reviewed **masked, inactive, dead, MainPID=0** service boundary. This is a
   prerequisite, not an action this CLI takes. The existing real user unit under
   `~/.config/systemd/user` is not assumed to be overridden by a runtime mask.
   Root must separately review a reversible arrangement preserving its exact
   original bytes at the proof's `deployment.unit.path`; never delete/replace it
   using an unreviewed generic mask recipe. No other app-UID process may have the
   DB open. Current source/config/unit hashes must describe the intended deployed
   release, with the CLI executing that exact `server/dist` build.
2. Under its separate GO, the assigned owner validates original container/mount
   lineage, completes exact supported cleanup, and captures absence. Root joins
   those archives with current authenticated provider boot/runtime/no-replay
   evidence, endpoint mapping and deployment closure. Root obtains the stopped
   DB's read-only `recoverySnapshot` digest and writes the short-lived protected
   `RecoveryProof` schema defined in `server/src/recovery-proof.ts`. The schema is
   intentionally narrow, including exact target UUIDs; no wildcard selector exists.
3. As the **existing non-root app user**, using the actual reviewed absolute paths:

   ```sh
   node /EXACT/RELEASE/ai-harness/server/dist/interrupted-recovery.js preflight --proof /ROOT-PROTECTED/recovery.json --session f006fc27-e488-4b82-b07c-65d63116da85
   node /EXACT/RELEASE/ai-harness/server/dist/interrupted-recovery.js apply --proof /ROOT-PROTECTED/recovery.json --session f006fc27-e488-4b82-b07c-65d63116da85
   ```

   Preflight never constructs Store. It inspects a private mode-0700 DB+WAL copy
   through read-only SQLite, preserving uncheckpointed data without creating
   source WAL/SHM files; the copy is removed. Apply opens the explicit offline
   Store mode, skips all migrations/startup recovery, and checks the complete
   snapshot again in one transaction. Concurrent drift, missing proof or another
   recovery fails closed. Duplicate apply explicitly refuses without another event.
4. Root reviews the compact output and durable audit. Rebind the existing
   settlement reader to the exact deployed candidate/build using the established
   deployment process: its historical H021 source/receipt/unit/build pins in
   `acceptance/settlement-readback.py` have deliberately **not** been overwritten.
   Its reviewed `readback` semantics now distinguish
   `physicallySettledInterruptedUnknown` from `completedSuccess`. The old pinned
   command is not an executable attestation for this new deployment.
5. Only after separate admission approval, restore the reviewed unit/start normal
   app operation and submit a **distinct new explicit user turn**. Gateway restart
   recognizes the additive release and retains original accepted bytes/usage;
   unrelated uncertainty remains blocked. Shared lane/frontier state is not
   rewritten here. The same native thread is resumed once; no accepted POST,
   Python tool, original prompt or large prefill is replayed. The old run remains
   interrupted/unknown, without an invented assistant final or successful usage.

The atomic audit retains the prior owner/turn/session/run/quarantine, original
request bytes, proof/snapshot digests and cleanup/done disposition events. The
only old admission changes are this native owner becoming idle/turn-null and its
exact quarantine removal. History, artifacts and unrelated records are preserved.
