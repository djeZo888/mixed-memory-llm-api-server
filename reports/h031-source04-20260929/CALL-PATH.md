# SOURCE04 pin and startup-path review (retained/source only)

Base: 711b24e283c16b61067621de39b796a8657ee309. Inspected at 2026-09-29 10:20 UTC.
This static review used local source and retained files only. The separate diagnostic tests use temporary fixture locks; no live lock probe or VM/network/model operation occurred.

## Pin verification

Read manifest.json directly from retained ACTIVATE02 private transition-final.tar.gz in memory. Raw SHA256: 56ad1378aeab24215e0b064d731a688ab0c1df4302994a82c976b697be78ad7d. Canonical SHA256: 9315a02f73288d9f6041b47316008fdf7502d7755be66278fd4ce0ec0ee0a9e9. Both equal retained ACTIVATE02 RESULT. Local mappings are comparisons with captured deployed pins, not a current VM readback.

At the 10:20 UTC base-source comparison, all 96/96 source manifest entries mapped to matching local bytes; 0 absent, 0 different after mapping installed namespace prefixes and the selection drop-in to its repository template. This describes the original 687aa9e5 owner. The authorized correction changes the owner; its final hash and updated comparison are pending root completion. Qualification and platform/model files are not claimed verified.

| Local dependency | SHA256 matching captured pin |
| --- | --- |
| scripts/runtime/mimo/owner.py | `687aa9e57f59103b39f6c4aefcf51d5ffc0bb9cf697fb443747d3757c332b090` |
| scripts/runtime/mimo/llm-frontier-mimo.service | `367b5ca357091523e6515889fb9920f9036821f839618bfab630378af8d343d5` |
| scripts/common/lifecycle_lease.py | `483ba038c62a8b4633449cef9c0f9a6664c00276662498abc748b58c8be644e0` |
| scripts/control/node.py | `32fa9fb3a0e7713799c28e7b52d783b87498e178e51187a2b3a691521017ff59` |
| scripts/control/node_collectors.py | `20ccafc8a4ba2937332f53ec59b34ce9d98a9047e09f0462bb528a6d77bcdb77` |
| scripts/control/node_observation.py | `0f9fd71419b81c6bd2d3dc33ae4e4beb12e17e551cfade680661b7ef8806e6e1` |
| scripts/control/hardware_latch.py | `a23e3e55453fefd3bbd5dbb6bce7d8e16da08db2f6debfcdfe01110815353685` |
| scripts/lifecycle/hardware_policy.py | `05fafa5697d389f2224cec8cece5aaaa6944acda433b49d0995719de1961fa18` |
| scripts/lifecycle/storage_binding.py | `69e61ce6685c310ce83449de75d45b209e63c6454c175f03d42bdad3daea7fbf` |
| scripts/lifecycle/manager.py | `a6c391406638a24da264ab381177ddcf88319ea702a205dd67a982db4b75f5be` |
| scripts/install/storage.py | `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505` |
| scripts/install/storage_io.py | `5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a` |

Important unverified setup boundary: owner.py hardpins external `/data/build/h014-pro-7ac59a6-20260927/prep.py` to `03c0933c194c79a6aca5e98e26bd1682f99927c0f9dbfe53f25d9938caf3724c`. The local `scripts/h014/prep.py` is `6e8d364344ba31cc33247b1d1e55d3fdb826d48fc812336573e22a594c11040b`, so its implementation cannot be called exact installed helper evidence. Neither listed retained tar archive includes prep.py. Its local setup imports lease/storage and reads registration; transaction() acquires a lease, but supervise calls setup()/manifest(), not transaction(). Exact installed setup()/manifest() helper bytes remain a dependency-evidence gap. The sole local git-history revision also hashes6e8d3643, not the required03c0933c. No fetch attempted.

## Startup and acquisitions (base line numbers)

1. `llm-frontier-mimo.service:13-15`: ExecCondition invokes `check-selected`; ExecStart invokes `supervise`; ExecStopPost invokes `settle`. Unit has Restart=no. check-selected reads selection only (owner:1878); it does not setup/import prep or acquire a lease.
2. `supervise:1626`: manifest read -> setup (hardpin/import PREP; h.setup; registration check) -> source_preflight -> selection -> prior state -> recovery branch -> assert_launch_admission. source_preflight:357 verifies manifest/deployed closure/storage/qualification/GLM/interleave/launch args/artifact metadata/runtime image. It has no explicit canonical acquire; mapped storage helpers have no flock/acquire, only internal threading.RLock.
3. HELD goes only through recovery_for_start:1583, requiring explicit NEW_BOOT_RECONCILED archive/receipt/manifest/selection, unchanged old state and unconsumed marker. SETTLED with amended manifest goes through settled_source_for_start:1454. Its same-boot STOP_TIMEOUT branch verifies archived original+corrected delta+supplement, exact prior bytes, old identity, request_hold=false and SETTLED release tuple. No acquisition in these recovery readers.
4. `supervise:1658` is the first explicit canonical acquisition in the verified owner source: `h.acquire_lease(blocking=False)`. It occurs before admitted=True, state writes, receipt consumption and Docker mutations. Shared implementation `common/lifecycle_lease.py:167-211` opens canonical lock, validates owner/path identity, takes LOCK_EX|LOCK_NB, raises LeaseBusy for EAGAIN/EACCES, and always closes its descriptor. No admission budget exists here; any ordinary brief contention is immediate refusal.
5. Under the acquired lease: storage/root checks, require_selected, exact prior state/current manifest checks, revalidate receipt and same-boot timeout_physical:1210 (full predecessor physical absence + no OOM/exited), or settled/new-boot absence; lease.validate; GLM stopped; MiMo GPU compute empty. Then unchanged bounded5s launch sample: memory/budget, temperature limit, sample_guard exact MiMo GPU and boot/current memory, memory policy, latch.
6. `sample_guard:523` has no lease acquisition. `latch:585` receives `lease=lease` at startup:1691 and validates the borrowed capability. Its refresh_lease uses nullcontext for supplied lease, so startup does not reacquire. `RegisteredLatchStore`/`HardwarePolicy` only validate/borrow that lease. read_latch_status is passive. Same-boot intentional/STOP_TIMEOUT recovery deliberately supplies evidence=None, so stale proof cannot be refreshed from the sample; current external exact-target proof is required. Positive/unknown/identity/storage faults remain refusals. During ordinary RUNNING guard cycles, no startup lease is held and latch's own acquisition at629 retries only entry within existing5s cycle, checks canonical identity/fresh sample and never replays acquired body.
7. Only after all checks: exact stopped Docker predecessor -> persist CREATING ownership/admitted -> exclusive consumed marker -> rename predecessor -> state baseline/write -> create/start. Dry-run exits before lease/side effects.
8. Before admission errors pass to top-level main:1900 `failure(exc,'CLI')`; failure:100 maps any type named LeaseBusy to lifecycle_busy and does not report throw site. `finally` settlement runs only if admitted. Therefore retained label alone does not prove which helper raised it.
9. ExecStopPost `settle`: setup + validate_manifest, read old state, check saved supervisor invocation equals new INVOCATION_ID at1890 BEFORE settle_state/its settlement lease. With retained old state/new invocation it correctly refuses recovery_invocation_changed and preserves old owner/failures.

## Node producer path

`HardwareEvidenceCollector.__call__:296` starts a finite callback deadline, repeatedly attempts canonical nonblocking entry:313 at25ms max intervals, and only retries LeaseBusy from __enter__. After entry, `production_binding(remaining())` at321 calls `RegisteredStorageBinding.read_registered(BoundedRunner())` (`node_observation:282`); this does not take a canonical lease or call lifecycle manager admission. `HardwarePolicy(RegisteredLatchStore(binding,lease=lease),lease=lease)` borrows the same capability. Inventory observations/exact-GPU proofs age through delays; remaining() constrains callback work. This source establishes a legitimate competing canonical-lock user, not the identity of either historical holder. No nested self-contention appears in this verified path.

Other explicit owner canonical sites: latch612/629; settlement766; prepare-source-stop1046; prepare-source-stop-timeout1278; reconcile-settled-source1384; reconcile-new-boot1532; supervise1658; rollback1806. Those administrative entry points are separate CLI actions, not nested supervise startup calls.

## Authorized correction and evidence limits

At 10:24 UTC, ROOT explicitly authorized a narrow correction in INBOX.md after review of the diagnostic fixture: an ordinary transient canonical-lease holder can make the original immediate startup entry permanently refuse before any mutation. Implementation is complete;61 focused checks pass. New owner SHA256: `2875de12f543ba06de36d57d06f4a8d87553765f74cd4cb69e0d7c76942a698c`. BASELINE-FAIL.log records the expected original-source failure.

The authorized `startup_lease` helper bounds only initial canonical acquisition to 2 seconds with short sleeps, preserving canonical inode and boot across the wait. It retries only `LeaseBusy` raised by context entry. Once acquired, it revalidates the current manifest/source/selection/prior state and recovery chain before body/native mutations. Acquired body exceptions must propagate without reentry. The existing five-second active launch/guard deadline, all source/storage/physical/hardware/ownership checks and native limits remain unchanged. This is a local owner correction, not a generic lease API change or stale-proof fallback.

The actual ACTIVATE02 and SOURCE03 captures establish two CLI lifecycle_busy refusals before changed ownership/consumption and subsequent recovery_invocation_changed. They did not sample lock holder/stack. Static source and the finite real-flock diagnostic demonstrate immediate admission failure under controlled transient occupancy; they do not establish either historical holder, historical throw site, or historical nested self-acquisition. Corrected source fixtures remain separate from live acceptance.

The changed owner is pinned in the current retained manifest. This packet deploys nothing and does not change any installed manifest, selection, receipt, configuration or capability. Before any future activation, root must review the exact final owner/dependency hashes and updated source closure, a precise approved source delta, and an explicit compatible transition/reconciliation that preserves immutable predecessor history, existing receipt/intent/supplement chain, uncertain owners, failures and quarantines. Current physical absence and exact MiMo-target hardware proof must be established under the separately authorized activation protocol. Existing consumed or uncertain work must not be replayed. No automatic deployment, baseline restoration or activation is authorized by this source packet.

External PREP remains an explicit source-evidence gap; local fixture helpers do not prove its installed setup()/manifest() behavior. Existing full closure guards retain the required hardpin.
