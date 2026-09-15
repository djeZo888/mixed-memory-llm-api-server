# I1S: explicit blank-disk provisioning continuation

I1b owns `scripts/install/storage_io.py` and runtime/acquisition. It makes **no
edits to `scripts/install/storage.py`**. Assign fresh I1S after I1b/I1R to finish
blank-disk provisioning; do not overlap another storage.py author. The optional
blank-disk path remains fail-closed until that source and verification pass.

## Exact existing seam

`Storage(config, runner).plan()` dispatches `storage_mode == "initialize"` to
`_disk_plan()`. That method checks stable by-id, exact confirmation, serial/WWN,
bytes, signatures, partitions, holders and protected root/boot ancestry. Its
schema1 result carries `identity`, `identity_sha256`, `disk_mutation_performed:
false` and a pending checkpoint. `adopt()` rechecks the saved plan digest and
currently raises `StorageCheckpoint`. The public dispatcher additionally refuses
initialize before adoption. I1S must replace both intentional checkpoints only
after the new transaction is tested; preserve existing/mount registration paths.

## Required transaction

1. Reuse reviewed D0 identity/non-use checks generically: exact stable by-id,
   planned bytes/serial/WWN, blank unused whole device, no force, no root/boot or
   cross-disk ancestry, partition/LVM/RAID/holder/signature exclusions. Handle
   NVMe partition names from observed topology, never suffix guessing.
2. Before the first mutation persist a small protected bootstrap transaction
   under `/etc/local-ai-server`, since verified data storage does not yet exist.
   Record immutable planned device identity plus each owned partition/filesystem
   identity and checkpoint. A resumed run may adopt partial work only when that
   exact transaction proves ownership; ambiguous preexisting signatures fail.
3. Revalidate target before each partition/format/mount operation. No implicit
   populated-disk overwrite, fallback device, historical VM UUID, or auto reboot.
   Complete durable partition/filesystem/UUID checkpoints, mount by UUID, backup
   and narrowly merge fstab, verify actual mounted identity, then issue the fixed
   root-owned schema1 registry used by `Storage.guard()`.
4. After registration, move bulk state/evidence to registered roots using
   `AnchoredRoot` and `MountedStorageGuard`; preserve the tiny bootstrap locator.
   Use the reviewed L1 lease/I1R package admission interface. No competing lock.

## Required evidence

Exercise actual public source entrypoints with interruption at every checkpoint,
changed serial/bytes/by-id, unowned partial signatures, root/boot/LVM/RAID/holder
refusal, and saved plan drift. Actual format/mount/fstab tests may use disposable
Linux loop devices in an isolated mount namespace only. Mac synthetic tests do
not prove actual formatting. No ai-vm block device is an authorized test target.

I1c must wait for reviewed I1S completion, plus release protection, native SGLang
auth proof, lifecycle/control/client and chosen-role acceptance. Full installer
readiness cannot be inferred from disk, package, runtime or download markers.
