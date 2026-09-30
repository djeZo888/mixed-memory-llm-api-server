# H036 MiMo 480K — concrete activation proposal

SOURCE ONLY. Requires root GO for the exact final bundle, owner/helper hashes,
profile hashes and a W2-confirmed admission gap. No VM write, stop, start, install,
model request or qualification change has been performed by this task.

## Exact candidate and current pins

`ACTIVATION-PINS.json` is the machine-readable contract. It binds current boot
992bf979-efae-495b-9ab2-26e75ed5c5d0, launch e5984f1e7e08434c89a7367a07b048fa,
old selection generation12 and its exact raw digest, old raw/canonical manifest,
old/new owner bytes, proposed manifest and delta, helper and unchanged launch.
The 21:53:15 UTC current read is an observation, not permission to ignore drift.
Preparation and install recheck current state/source/boot/selection/physical
ownership/hardware. Any mismatch stops the sequence; it is not autoaccepted.

Only `context`950000->480000, `native_argv[11]` and `[16]`950000->480000,
and the explicit reviewed `source/owner.py` pin change. Selection advances12->13
and binds the new manifest. `launch.json` remains byte-identical. Output65536,
parallel1, runtime7ac59a6/build/image, model/artifacts/template, GPU69acfa26,
threads8/batch64, affinity/NUMA/cache/no-host/memory/swap/fan/power remain exact.
Qwen/image receive no writes or lifecycle actions; their captured container IDs,
images, StartedAt and PIDs are in CURRENT-READBACK.json for later comparison.

## Finite sequence after a separate GO

1. W2/root confirms the short exclusive native lifecycle gap and no model/app/VM
   writer or pending request. Capture fresh state hash, the prepared intent hash
   when created, and later settled state hash as runtime CAS values. Do not use
   the RUNNING-state hash as the SETTLED-state hash. Keep stderr/return codes and
   client timeout receipts. Source-qualified admission is not actual readiness.
2. Stage exact reviewed `owner.py`, `install-candidate.py`, pins and the two
   PRIVATE files `context-reduction-manifest.json` / `context-reduction-delta.json`
   under protected `/data/build/h036-mimo-480k01-20260929`. Verify root ownership,
   protected ancestors and review hashes before importing. Stage the two context
   JSON files with exclusive creation under the registered storage guard at
   `/data/services/mimo-h016-20260927/`. No current profile/source replacement yet.
   A pre-existing context file/attempt is a review boundary, not an overwrite.
3. Run the staged candidate once with `prepare-context-reduction`,
   `--expected-state-sha256 FRESH_RUNNING_STATE_RAW_SHA`,
   `--expected-boot-id` from pins, `--expected-manifest-sha256 manifestOldSha256`,
   and `--expected-delta-sha256 deltaRawSha256`. Installed old owner/manifest remain
   intact. Preparation checks exact running owner, idle proxy, fresh guard, boot,
   unit/job/cgroup, native/process identities, target GPU hardware proof and CAS.
   Its exclusive `context-reduction-stop-BOOT-LAUNCH.json` archives exact old
   source/manifest/selection/state/guard/proxy and the reviewed candidate/delta.
4. Dispatch exactly one normal `systemctl stop llm-frontier-mimo.service` while the
   OLD owner is still installed. Existing SIGTERM/ExecStopPost behavior and
   45-second systemd stop timeout remain unchanged. Use a bounded SSH wrapper
   with enough time for the supported stop (e.g.90 seconds); preserve an uncertain
   client result. Do not issue a second stop, manual settle, kill, reset-failed or
   source change to repair an unexpected result.
5. Require a confirmed clean command return AND exact durable SETTLED predecessor:
   request_hold=false, original owner_interrupted/RUNNING failure retained, no
   other failure field, empty service/native descendant cgroups, no old process,
   no target GPU compute or MiMo listener, stopped exact old container. The
   install helper rechecks these through existing owner functions under the
   canonical nonblocking lifecycle lease and current storage guard. Old container
   validation uses the OLD manifest. No old file is rewritten to look successful.
6. Run the reviewed helper once:

   ```text
   python3 -I -B /data/build/h036-mimo-480k01-20260929/install-candidate.py
     --candidate-owner /data/build/h036-mimo-480k01-20260929/owner.py
     --pins /data/build/h036-mimo-480k01-20260929/ACTIVATION-PINS.json
     --expected-settled-state-sha256 ACTUAL_SETTLED_STATE_RAW_SHA
     --expected-intent-sha256 ACTUAL_PREPARED_INTENT_RAW_SHA
   ```

   These are argv lines for one invocation. The helper validates exact pins,
   prepared bytes, old source closure, state/selection/boot, physical ownership
   and current target-GPU hardware. It creates an exclusive immutable
   `context-reduction-install-BOOT-LAUNCH.json` containing old bytes and proof
   BEFORE either installed file changes. Anchored exclusive temporary write,
   fsync and replace install only owner.py; guarded atomic JSON installs only
   manifest.json. State and selection remain old. The gap therefore fails normal
   start admission until reconciliation completes. Any partial failure preserves
   the marker and refuses replay, even if it happened before profile replacement.
7. Run installed owner once with `reconcile-context-reduction`, the SAME actual
   settled-state SHA and boot, `--expected-manifest-sha256 manifestNewSha256`, and
   `--expected-delta-sha256 deltaRawSha256`. It validates the exact prepared pair,
   original clean stop, old native physical absence, current hardware and CAS.
   It archives state/failure/old records under distinct
   `settled-context-reduction-BOOT-NEWMANIFEST-*` names, creates a distinct
   SETTLED_CONTEXT_REDUCTION_RECONCILED receipt and advances selection12->13.
   No old source-only receipt, fault or history is relabeled or overwritten.
8. Dispatch one normal `systemctl start llm-frontier-mimo.service`. Under the
   existing bounded startup lease the new owner rechecks source, boot, selection,
   state, physical absence and hardware, validates old native under old manifest,
   durably records successor ownership, consumes the context receipt once and
   renames the old container to `llm-frontier-mimo-production-prior-LAUNCH`.
   The prior Docker container and logs survive. The single new create/start uses
   the new manifest. Original startup, settlement and mandatory-guard deadlines
   are unchanged; no latch clearing or global GPU availability dependency is added.
9. Observe a durable independently owned LOADING successor and matching native
   identity before releasing the lifecycle gap. This is not ready/tool-qualified.
   Use a finite short observation bound; if no owned LOADING appears, close with
   the actual failure/uncertainty and preserve all records. Do not wait through
   loading on paid native CLI. Wrapper records actual native exit afterward.

## Failure, backup and later evidence

Any stop `command_timeout`, settlement_failure, client timeout, request hold,
changed boot/source/selection, hardware uncertainty or missing physical release
HALTS this plan for explicit root review. The existing source-only late-timeout
supplement cannot authorize a context reduction. Its historical records remain
untouched. No blind replay, automatic rollback, retry or recovery framework.

Exact old source/profile/selection are backed up in prepared intent and install
attempt, and old state/faults/selection in reconciliation archive. Containers/logs
are preserved by the normal start rename. An interrupted write can leave a
source/profile mismatch that intentionally refuses admission. Recovery requires
separate review of the actual partial outcome; do not delete the attempt marker.

A later bounded task must obtain actual new props AND slots480000, native
container/boot/guard/selection/thread identities and current short readiness, then
one actual short tool continuation/count-vs-usage proof coordinated with W2.
No occupied480K or950K benchmark. Retained950K facts stay historical. The unchanged
manifest `qualified`/qualification hashes are source-admission inputs only;
this task neither creates a480K qualification receipt nor admits it as ready.
W2 alone owns harness480000/400000/65536, app/profile/qualification writes.
