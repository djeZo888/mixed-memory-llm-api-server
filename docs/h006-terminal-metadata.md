# H006 terminal metadata correction

Source task based on `11c24d9c5a0bac3682cd633905fa7991ec968f19`, followed by
separate reviewed activation of exact worker commit
`4eebece053b3a0e40143ea16dd3892482b55d949`. The source task performed no VM
actions. The subsequent deployment restarted only the node API and retained
all loaded model identities and warm receipts. See the
[closeout report](h006-closeout-20260926.md) for live evidence and limitations.

## Behavior and limits

The owner selects the action outcome once, independently of terminal publication.
`_finish` retries only canonical `LeaseBusy` **entry** admission for up to one
monotonic second, sleeping at most 50 ms between attempts in its existing owner
thread. Once admitted, validation, journal update and release run once. Unsafe
lease, storage, update and release errors never retry that body. Dispatch,
completion observation and accepted/uncertain work never replay.

An unsuccessful publication emits a fixed `llm-node terminal_metadata_uncertain`
syslog message with operation ID, selected status, selected reason and one of:
`lease_busy_deadline`, `lease_invalid`, `storage_unavailable`, `publication_failed`.
No exception text, request contents, paths or credentials are logged. The fixed
node unit discards stderr, so stderr logging would not provide this diagnostic.
Syslog delivery is best effort: failure of that transport is nonfatal and does
not trigger journal/action retries. It is not a second durable receipt. A live
syslog receipt is not claimed by source tests.

On admission exhaustion the existing durable accepted/running evidence and
audit remain unchanged; GET stays cached. A post-rename/fsync/guard error may
already have stored the selected terminal result. Existing `_save` invalidates
the cache on write uncertainty so subsequent admission reloads durable evidence.
No fallback failed receipt overwrites success because terminal publication had
contention. An action failure keeps its original reason; reboot retains its
existing `unknown/reboot_pending` outcome. The one-second bound covers admission
contention, not arbitrary filesystem stalls after admission.

Focused offline command: `python3 -B tests/test_node_action_owner.py -v`.
This covers real fixture flock contention, single dispatch/audit, persistent
uncertainty, unsafe entry, post-entry validation/update/release errors,
pre/post-commit storage errors, retained action failures and reboot uncertainty,
nonfatal diagnostic transport failure, and startup audit preservation.

## Existing old operation

`1405e70bbdf0488589c5dc15f5710f3f` remains historically uncertain. The prior
maintenance capture reported running with only accepted/dispatch audit and
separately successful image warm/recovery receipts. This patch cannot determine
the lost exception and cannot establish retroactive operation success.

The existing `_load` runs under `_work`'s canonical lease only after the fixed
node listener binds. For a non-reboot accepted/running operation it writes
`interrupted/operation_interrupted`, appends the corresponding audit event, and
preserves operation ID, request/key digests, dispatch flag and prior audit.
`operation()` does not reconcile. Reboot is the separate existing special case:
same boot remains unknown; changed boot can establish reboot success. The old
image restart is not that special case. No new reconciler is added.

## Reviewed matched publication procedure

The task's external `SOURCE-TRANSITION.json` binds exact before/after hashes and
candidate metadata; `SOURCE-RESULT.json` binds the commit and test logs. Inputs
are the prior maintenance phase's protected source captures and the matching
retained boot publication artifacts, not a fresh installed-state claim.

Required matched set:

| Object | Required change |
| --- | --- |
| `/usr/local/lib/llm-server/node-api/scripts/control/node_action_owner.py` | Exact reviewed candidate bytes, preserving root ownership and mode0644 |
| `/usr/local/lib/llm-server/control-api/scripts/control/node_action_owner.py` | Same candidate bytes; part of its source identity, not its running action owner |
| `/data/services/releases/h006-terminal-metadata-20260926/` | New immutable successor of `/data/services/releases/h005-boot-restore-20260925/`; preserve its full manifest closure except this owner file |
| Successor `SOURCE-MANIFEST.json` | Complete delivery hashes and exact reviewed commit; preserve old immutable release/manifest |
| `/data/services/llm-manager/evidence/dualq-480k.accepted.json` | Change only this file's `source_sha256` entry, reviewed commit and appended source-transition evidence |
| `/data/services/llm-manager/deployment-instance.json` | Change only `concurrent_pair_acceptance.sha256` and `.reviewed_source_commit`, preserving its path |
| `/etc/systemd/system/llmctl-boot.service` | Reviewed release-root substitution only; daemon-reload, never start/restart this unit |
| `/data/services/h006-terminal-metadata-20260926/TRANSITION.json` and `DELIVERY-MANIFEST.json` | New protected publication evidence, exact source/metadata hashes and before/after checks |
| `/data/backups/h006-terminal-metadata-20260926/MATCHED-BACKUP.json` and its recorded files | New protected matched backup; journals are evidence only |

The 81-entry `concurrent_profiles.source_identity()` changes exactly one entry.
The unchanged control/node closure JSON files enumerate paths, not hashes;
preserve them, and verify both complete closures. The old release has 140 files.
Do not overwrite unrelated files from the newer repository checkout when
constructing its successor. Source-only inheritance preserves every capacity,
runtime/auth, context, allocation and original measurement field; it is not a
new acceptance measurement. No image config, image immutable release, runtime
binding, model profile, boot intent, latch or credential changes are needed.

Installed bytes and loaded process code are distinct. The reviewed control
entrypoint `serve.py` creates `adapter.production_application`, which uses
`ProductionBackend`/`ManagerSession`; it neither imports nor instantiates
`ProductionNodeActionOwner`. Only `node_serve.py` creates that owner. Control's
unchanged `source_identity()` reads shipped bytes from disk when acceptance is
checked, and `ProductionBackend.load()` loads the current instance per session.
Thus updating its installed owner file maintains the source/acceptance binding;
it does **not** claim to reload control's Python process. No changed executable
control code requires a restart. Preserve its exact PID/invocation and recheck
this source lineage during activation. Unexpected deployed code requiring a
control restart is a blocker for this node-only plan, not restart authority.

1. Root reviews exact commit, diff, focused results and proposed matched set.
   Assign a fresh Worker1 activation window; coordinate no new lifecycle actions
   with all clients. Refresh protected installed hashes, registered storage,
   root-disk guard identities and current journals. Any unreviewed source drift,
   new running operation or active owner transition beyond the exact step2
   completion-observation exception is a stop condition.
2. Capture boot, node/control/image unit invocation IDs/PIDs/jobs, all three
   container IDs/images/start times/PIDs and native process start ticks. Preserve
   both Qwen480000 configuration bindings, image warm run/receipt hashes,
   ready/admitting observations, intent/recovery/latch and control journal hashes.
   Reconfirm no other active node/control operations, fixed image helpers or
   systemd jobs. Root11:10 explicitly permits interruption of **this known
   operation's completion observation only**: image operation
   `1405e70bbdf0488589c5dc15f5710f3f`, with its exact accepted/dispatch record.
   Acquire the canonical lease **before stopping node**, excluding
   dispatch mutation, and preserve model identities. No invasive `_busy` or
   Python-stack inspection is needed when these constraints are proved; absence
   of such inspection alone is not a blocker. Any other active work is a stop.
3. With current installed guards and canonical lease, preserve a new protected
   matched backup under `/data/backups/h006-terminal-metadata-20260926/`, including
   source files, old release manifest, acceptance, instance and boot unit. Capture
   journals as evidence only, never as rollback replacement inputs. Preserve the
   old maintenance backup and `/data/services/h006-maintenance-deploy-20260926/DELIVERY-MANIFEST.json`.
4. Keep the **same canonical lease continuously held through node stop and all
   publication**, releasing it only after verification and before node start.
   Stop **only** `llm-node.service`. Stage the new release and metadata with
   protected ancestry, mounted guards and anchored registered writes. Before
   publication prove the staged 140-file closure matches the old release with
   exactly one owner-file hash changed, and all 81 critical source entries match
   the proposed receipt. Under canonical ownership, CAS-check captured before bytes,
   publish the two source copies and matching acceptance/instance/boot binding,
   and re-read complete hashes. Individual replacements are atomic; this set is
   not one atomic transaction. Keep node stopped on partial failure. No live
   control action may be admitted during publication; the canonical lease guards
   mutation. Its running process does not import the changed node owner.
5. After publication repeat that closure proof from both installed roots and
   the successor release;
   validate existing acceptance for both modes/all three supported text profiles
   using read-only checks, not lifecycle commands. Verify unchanged image closure,
   all protected guards and model identities. Write the new protected delivery
   manifest. Release the canonical lease **before** node startup reconciliation.
6. `systemctl daemon-reload` loads only the boot unit path change;
   `systemctl start llm-node.service` completes the controlled stop/start. Do not
   restart control, boot, image API/backend, Docker, text containers or harness.
   Do not use a model action API to activate this source change. Installed binding
   checks must use the existing proper systemd credential context without exposing
   the key. Startup takes the canonical lease and applies the existing `_load`.
7. Passive acceptance: node PID/invocation must change; boot and control/image
   invocations, all three container/image/start/PID/native-process identities and
   both480000 contexts must not. Read authenticated node status/operation and
   protected journal: the old ID must now be `interrupted`, reason
   `operation_interrupted`, with original digests, accepted/dispatch audit and
   dispatch flag retained plus exactly one interruption audit. No new operation
   or start/recover/warm receipt may appear. Both text services and image remain
   ready; image remains warm/admitting with the same run. Recheck intents,
   recovery, latches, control journal, guard results and matched publication.
   Any difference stops acceptance without automatic model recovery or replay.

## Rollback

In a separately reviewed quiescent window, stop only node; use current installed
guards and canonical ownership to restore the backed-up two owner source copies,
acceptance/instance reference and old boot-unit path as one matched set. Retain
candidate release, delivery manifest and failure evidence. Verify complete old
source identity and acceptance before releasing the lease; daemon-reload and
start only node. Repeat the same passive model-preservation checks. Never restore
old node/control journals, active intent, recovery or latch files: the old
operation's interruption audit must survive rollback. No model restart or
inference is a rollback step. If the old binding no longer matches current
protected state, stop for root review instead of overwriting newer evidence.
