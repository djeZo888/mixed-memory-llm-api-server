# H036 RECOVER03 source review and remaining activation

No VM operations occurred. Root must review this exact source/pins and separately authorize activation. Root INBOX22:37 reports W2 settled and maintenance restored; that report is not an activation action by this task. No GitHub push.

The new explicit context timeout supplement preserves the original intent287e044d, both raw failures and exact950000→480000 profile pair. Only the original candidate owner pin advances1e14a0fe→6e59b5ae7d4cc88a8f67bdc4fb6eebb34ae97b206255a5424f144327f7de1c53; the installed old owner2406d9a0 is still the predecessor. The corrected delta and manifest have new filenames. The old source-only receipt cannot authorize this transition. Clean-stop reconciliation still refuses the retained settlement_failure.

Final pins are in ACTIVATION-PINS.json. Owner SHA256 `6e59b5ae7d4cc88a8f67bdc4fb6eebb34ae97b206255a5424f144327f7de1c53`; helper `355ac7f6ab8d297550ab84c98d4c8a53f12e6f391af1471c72cd68f37085e046`; corrected480K canonical manifest `da9b2c00422bd7a65c8cec7f9faa5a6c6804a5a71bdb141a986f824858ce09b7`; corrected delta raw `401d87454a4f15b785b84f5f2c70158b2d67e911ffc22f129f2e76b0b6d4018a`. Stopped state `e74a0e274a14fbc2c8baa95366dbfa1f76a2c01a3f447ab44bec02215fb2359a`; original intent `287e044d6ff2baad3aaf19e9b3f8e2cd14f655210f3805cb2a6b29f8e4aadc53`. The runtime amendment is the exclusive `context-reduction-stop-timeout-992bf979-efae-495b-9ab2-26e75ed5c5d0-e5984f1e7e08434c89a7367a07b048fa.json`; its SHA cannot be predicted because it contains fresh physical/hardware proof. It has NOT been prepared. The installed owner/profile, selection12, original staging and retained container are unchanged by this task.

After separate root GO, use this finite sequence; no repeated original prepare or stop:

1. Confirm the exclusive W2/root lifecycle gap. Verify exact stopped state/intent/source/boot/selection pins; any drift or active/unknown work stops this sequence. Preserve failed unit status and old exited137 container at its original name. Do not reset-failed, manually settle, kill or restart950K.
2. Exclusively stage the reviewed output owner.py, install-candidate.py, ACTIVATION-PINS.json and private/context-reduction-corrected-{manifest,delta}.json into `/data/build/h036-mimo-recover03-20260929` using known protected access. Verify each SHA before importing; root-owned protected ancestors required. Old staging directory and original prepared bytes remain intact. Under the staged owner's existing nonblocking canonical lease and MountedStorageGuard, validate storage_paths/source_preflight/current pins, then use exclusive_recovery_write for ONLY context-reduction-corrected-manifest.json and context-reduction-corrected-delta.json under `/data/services/mimo-h016-20260927`. The helper serializes sorted indent2 JSON plus newline, matching the supplied raw pins. Existing files are a review boundary, never overwrite. No canonical lease around systemctl.
3. Execute this one stopped-state supplement command (not a pre-stop intent, no stop action):

```sh
python3 -I -B /data/build/h036-mimo-recover03-20260929/owner.py prepare-context-reduction-timeout \
  --expected-state-sha256 e74a0e274a14fbc2c8baa95366dbfa1f76a2c01a3f447ab44bec02215fb2359a \
  --expected-boot-id 992bf979-efae-495b-9ab2-26e75ed5c5d0 \
  --expected-manifest-sha256 fef303948bb4ef5b9d4ffc404483ac0ad87cd8646901530fbb811a5f1af3e88d \
  --expected-delta-sha256 b130e10123e4027846b0360c7c51deb029818af4a31e1f1a2e81a1e75b11edfe \
  --expected-intent-sha256 287e044d6ff2baad3aaf19e9b3f8e2cd14f655210f3805cb2a6b29f8e4aadc53 \
  --expected-corrected-delta-sha256 401d87454a4f15b785b84f5f2c70158b2d67e911ffc22f129f2e76b0b6d4018a \
  --expected-successor-manifest-sha256 da9b2c00422bd7a65c8cec7f9faa5a6c6804a5a71bdb141a986f824858ce09b7
```

Retain the actual returned supplement_sha256 as SUPPLEMENT_SHA and verify the immutable record. It binds the exact retained state, original intent/pair, corrected owner/profile, fresh physical absence and current target-GPU hardware proof. No old intent/delta/manifest/state is changed.

4. Execute once, substituting the actual supplement digest:

```sh
python3 -I -B /data/build/h036-mimo-recover03-20260929/install-candidate.py \
  --candidate-owner /data/build/h036-mimo-recover03-20260929/owner.py \
  --pins /data/build/h036-mimo-recover03-20260929/ACTIVATION-PINS.json \
  --expected-settled-state-sha256 e74a0e274a14fbc2c8baa95366dbfa1f76a2c01a3f447ab44bec02215fb2359a \
  --expected-intent-sha256 287e044d6ff2baad3aaf19e9b3f8e2cd14f655210f3805cb2a6b29f8e4aadc53 \
  --expected-supplement-sha256 SUPPLEMENT_SHA
```

This helper requires the reviewed exact state/intent pins and supplement chain. It rechecks physical release/current hardware, writes an exclusive context-reduction-install-BOOT-LAUNCH attempt archive, then installs only owner and manifest. Selection/state remain old. A partial write or pre-existing attempt refuses replay; preserve it and return to root review.

5. Reconcile once using the installed owner:

```sh
python3 -I -B /data/services/mimo-h016-20260927/source/owner.py reconcile-context-reduction \
  --idle-stop-timeout-settled \
  --expected-state-sha256 e74a0e274a14fbc2c8baa95366dbfa1f76a2c01a3f447ab44bec02215fb2359a \
  --expected-boot-id 992bf979-efae-495b-9ab2-26e75ed5c5d0 \
  --expected-manifest-sha256 da9b2c00422bd7a65c8cec7f9faa5a6c6804a5a71bdb141a986f824858ce09b7 \
  --expected-delta-sha256 401d87454a4f15b785b84f5f2c70158b2d67e911ffc22f129f2e76b0b6d4018a \
  --expected-supplement-sha256 SUPPLEMENT_SHA
```

This archives both original faults, creates a separate SAME_BOOT_CONTEXT_REDUCTION_STOP_TIMEOUT_SETTLED context receipt and advances selection12→13; no clean-stop fiction. All original files and source-only history remain archived/unchanged.

6. One normal `systemctl start llm-frontier-mimo.service`. Existing startup admission rechecks the exact chain, current physical absence, source/boot/selection and strict hardware proof. Preflight failure leaves the receipt unconsumed. Successful admission persists successor ownership, consumes once, renames the old container to its prior-LAUNCH name, and creates/starts one480K owner. Any error is retained; no blind retry or rollback.
7. Observe owned LOADING/native identity within a finite short bound, record it, and release the lifecycle gap. This is not readiness. Close the native session and let its outer wrapper record actual exit. Later separately bounded readiness must confirm actual props+slots480000 and one short tool continuation/count-vs-usage proof with W2. No occupied-context benchmark or qualification relabel.

All weights/runtime/image/template/output65536/parallel1/decode8/batch64/actual GPU/affinity/NUMA/cache/memory/swap remain exact. launch.json is unchanged. No hardware producer/latch clear or five-second running guard change.

Stop timing: retained systemctl wrapper22:17:21.574195–22:17:34.449859 UTC rc0; first command_timeout22:17:29.361717; durable settlement_failure22:17:29.657866. Docker FinishedAt22:17:33.941785249, exited137; systemd stopped22:17:34.473211. Internal Docker client start/end were not separately instrumented. The source command was docker stop --time3 with7s client timeout. The new one-shot wait is up to20s, clipped by30s local/caller deadline including up to10s lease contention and4s postchecks. It holds the common lease longer; unit45s, guard5s and proof15s stay unchanged. True expiry remains command_timeout/unknown; no stop retry is added. Host-memory unmapping remains unproven. See TIMING.json and retained private captures.

Tests:8 context timeout cases (including exact private chain and real supervise path) plus6 deterministic deadline cases pass. Existing context/source-only/amendment/startup/settlement groups pass; groups overlap and are not summed. Two optional H031 private fixtures skipped; H036 exact private replay passed. TEST-RECEIPT.json identifies logs and retained development failures. Prior ACTIVATE02 staging AttributeError (`old_installed_owner` lacks `transition_stop_name`) and command_timeout are separate original failures; neither is erased or relabeled.
