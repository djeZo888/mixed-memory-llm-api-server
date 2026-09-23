# IMAGE21 three-GPU compatibility — Worker1 rollout handoff

This is source/offline preparation only. Root must review the exact delivered
source commit and a separate fresh Worker1 task must own publication/restoration.
No production acceptance, VM observation, restoration or inference is granted by
these synthetic tests. Image API/service/network changes are outside this patch.
The [approved IMAGE21 plan](qwen-image-2.1-ada-plan.md) supplies the bounded scope.

## Invariant and retained policy

`GPU_UUIDS[0]` remains `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237` (GLM or Qwen0);
`GPU_UUIDS[1]` remains `GPU-69acfa26-8b60-61b5-702d-aee252c163cc` (Qwen1).
Each must occur exactly once. All inventory rows must have valid identities and
unique physical indices/UUIDs. Additional GPUs, including Ada
`GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23`, are allowed; names, row positions and
current ordinals cannot redirect either text slot. Fresh total/free MiB samples
are converted to bytes and matched to the exact UUID in each accepted slot proof.
Both the target and each resident slot retain their own total and free checks.

All profile/runtime/model/wrapper pins, text480000 settings, masks, host caps,
no-swap rules, Blackwell VRAM reserves, sampled working-set 15% host policy,
canonical lock and storage/auth/network guards remain unchanged. Ada's image-only
5% VRAM policy does not apply to text. Historical two-GPU inventories and old
measurement proofs stay intact; a fresh inventory is amendment evidence, not a
replacement measurement or a new capacity claim.

## Required evidence placeholders

Worker1 must resolve and root must review these from the current protected
installation, not substitute paths or hashes from historical documentation:

- `OLD_SOURCE_COMMIT`, `OLD_SOURCE_ROOT`, retained exact old source/recovery bytes,
  manifest and raw file hashes; current installed registered guard paths/hashes.
- `NEW_REVIEWED_SOURCE_COMMIT`, verified delivery/bundle SHA256, installed new
  release root, complete new source manifest and changed critical old/new hashes.
- `INSTANCE_PATH`, exact old instance bytes and raw/canonical SHA256;
  `RECEIPT_PATH = binding.path('data', ACCEPTANCE_SUFFIX)`, exact old receipt
  bytes and raw/canonical SHA256; captured `concurrent_pair_acceptance` reference.
- Protected rollback/evidence locations beneath verified registered roots,
  `AMENDMENT_EVIDENCE_REFERENCE`, root review identity and Worker1 task/session ID.
- Fresh timestamped GPU index/UUID/total/free output, storage guard results,
  selected deployments, boot intent, operation/recovery journals and full owned
  container/start identities (including failed/stopped containers).

These uppercase names are required evidence fields, not executable shell defaults.
Missing bytes, unreviewed source differences or ambiguous ownership stop rollout.
Keep credentials out of reports; retain the protected original instance privately.

## Ordered Worker1 publication and restoration

1. Confirm root's exact source review and fresh Worker1 mutation ownership.
   Resolve and use the **current installed registered storage and root-disk
   guards**, before and after writes/changes. Verify registry, mounts, protected
   ancestry and operation paths. Use no stale checkout guard or fallback.
   Drain the control executor, settle outstanding operations and exclude competing
   boot/restart/mutation owners through the existing reviewed maintenance path.
   Capture actual state; historical stopped/failed reports are not current proof.

2. Acquire `common.lifecycle_lease.acquire_lease()` at the canonical
   `/run/llmctl/lifecycle.lock` and retain it throughout publication. Validate it
   around writes and pass the same in-process lease to nested Manager operations.
   Do not acquire a second lock or run a separately locking CLI while holding it.
   Keep maintenance ownership until final source/receipt/instance verification.

3. With `RegisteredStorageBinding.load(StorageRunner(), roles=('data', 'models'))`
   and the shipped anchored storage routines, retain the exact old source,
   receipt and instance **bytes**, plus state/journal/boot/container evidence.
   Record raw SHA256 of every retained file and canonical receipt/instance hashes
   with `concurrent_profiles.receipt_sha256(parsed_value)`, plus the prior source
   commit. Parse/read protected JSON through `binding.read_json`; preserve raw
   bytes separately using guarded anchored reads/writes. JSON reserialization is
   not an exact-byte backup. Verify backups and the prior receipt digest/reference
   before changing anything. Verify old critical hashes against the retained old
   source; the old source may already refuse today's three-GPU inventory.

4. Capture fresh `nvidia-smi --query-gpu=index,uuid,memory.total,memory.free
   --format=csv,noheader,nounits` output. Validate required identities with the
   reviewed validator; compare each required UUID's total to its own old proofs
   in both modes. Record additional Ada independently. Missing/duplicate identities
   or changed required totals stop publication; do not adjust old proofs to fit.
   Current free memory still must pass normal admission at each start.

5. Narrowly replace the reviewed source release through the existing protected
   deployment path. Retain the old release for rollback. Inventory all differences
   between actual old critical bytes and the new `source_identity()` manifest:
   this patch intentionally changes only `scripts/lifecycle/concurrent_profiles.py`
   among critical files. Any other installed-source difference requires explicit
   root review; a branch-base assumption is insufficient. Refresh source consumers
   through the existing reviewed path; do not mix cached old Python modules with
   new on-disk source. Do not start a text backend against mismatched evidence.

6. Publish a root-reviewed amendment evidence record containing old/new source
   commits, old/new hashes for every changed critical file, old receipt raw and
   canonical hashes, old instance hashes/reference, retained source locations,
   fresh inventory/totals, review identity and preserved measurement lineage.
   State that allocation, inference, occupied-context and performance evidence
   are retained historical measurements, not rerun by this amendment. Root must
   explicitly accept their applicability to the reviewed compatibility change.

7. Form the amended receipt from the protected old receipt, preserving its
   schema/header kind/status, storage/instance identity, two-row historical
   `gpu_inventory`, both mode reviews, every slot proof and all old evidence.
   Change only `reviewed_source_commit`, `source_sha256` and append
   `AMENDMENT_EVIDENCE_REFERENCE` to top-level `evidence`. Compute `source_sha256`
   with **the new shipped** `concurrent_profiles.source_identity()` from the
   verified new release; compute the new canonical digest with its shipped
   `receipt_sha256(amended_receipt)`. Do not hand-roll the digest, drop a critical
   file, fabricate PASS fields or add a receipt-schema migration mechanism.

8. Under the active lease, re-read/compare the old protected receipt and instance
   against the captured originals immediately before publishing. Use existing
   `Manager.persistent_json(RECEIPT_PATH, amended_receipt)` and then
   `Manager.persistent_json(INSTANCE_PATH, amended_instance)`; only replace the
   instance's `concurrent_pair_acceptance` with exactly `path`, `sha256` and
   `reviewed_source_commit`. These call the mounted guard, `AnchoredRoot` and
   `atomic_json` (fsync/rename/directory-fsync), preserving protected single-link
   mode0600 storage. Do not use `lifecycle.manager.atomic_json`, which serves the
   volatile recovery journal. The caller must hold/validate the canonical lease.
   Each JSON replacement is atomic; source + receipt + instance is **not** one
   transaction. A failure between writes stays in maintenance and fails closed.
   Re-read both through protected storage, recompute raw/canonical hashes and
   source identity, compare the complete intended values, and call
   `check_acceptance` for both modes/all three profiles using the newly loaded
   instance and bound deployments before any boot/start. Re-run current guards.

9. Restore both Qwens with the existing reviewed slot/boot-owner paths, preserving
   exact owned identities, state and interruption requirements. For captured
   Q/Q running/resume intent, `Manager.dispatch('boot-start', lease=lease)` replays
   GPU1 then GPU0; otherwise root must review explicit selection/start operations
   for the captured intent. Do not silently rewrite intent, adopt containers or
   replay the singleton rollback procedure. Every start rechecks current UUID
   memory and native capacity. Capture authenticated native pool480000,
   input479994 and optional request479999 for each Qwen, fresh readiness and one
   tiny authenticated output per endpoint through existing reviewed private
   transport. Retain exact container/UUID/runtime/alias and guard evidence.
   No large context benchmark, image service, network or driver change is needed.
   Report failures explicitly; Worker1 live evidence alone can establish restored
   warm text service. Preserve old source/receipt/instance and amendment evidence.

## Rollback limits

Root and Worker1 must own any rollback under the same guards, maintenance and
canonical lease. Restore the matched old source, exact old receipt and old
instance reference together, re-read their hashes, reconcile current owned state
and follow the existing reviewed recovery path. Preserve the failed new release
and amendment for diagnosis. Do not overwrite state with a stale snapshot or
claim an artifact restore establishes readiness.

New source with the old receipt must reject; old source with the amended receipt
must reject. Restoring only source or only receipt/reference cannot safely boot.
Even a fully matched old triple retains the historical exactly-two-GPU/order
restriction and may still reject the current three-GPU host. This source task
authorizes no GPU removal or topology mutation to make rollback pass. Stop and
return evidence for root's reviewed recovery decision if that limit is reached.
