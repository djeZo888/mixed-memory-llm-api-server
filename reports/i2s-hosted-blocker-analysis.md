# I2S independent analysis of the first hosted failure

**STOP: fixture failure and incomplete cleanup reporting prevent acceptance.**
This is a read-only analysis of the existing artifact and source. No fix,
privileged operation or additional hosted run was performed during diagnosis.

## Observed facts

[Run 34916701374](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34916701374)
tested `50d2541e9dbd194ca0fd1471fb042955e648bff8`. Its source-bound `evidence.json`
records Ubuntu 24.04.5 LTS, kernel `6.17.0-1022-azure`, Python 3.12.3, systemd
255, util-linux 2.39.3 for sfdisk/losetup/mount, and e2fsprogs 1.47.0. The complete
orchestrator elapsed time was 0.442 seconds.

The shipped dry-run returned 0. Apply returned 1 with:

```text
FAIL: storage command failed: wipefs
Fixture loop detach has not completed; preserving backing file.
CLEANUP_INCOMPLETE: inspect /run/i1s-loop-yOAq3pja in disposable environment.
```

The independent parent observer records unchanged loop associations, unchanged
parent mount namespace, and the remaining new scratch directory. The orchestrator
stopped with `shipped_cleanup_unresolved_stop_matrix`. Writer, process adapters
and extended loops all remain **NOT_TESTED**. No GPT/ext4 transaction, exact
512-byte logical-sector result, filesystem payload preservation or mount-loss
acceptance can be inferred from this failed attempt. The artifact does not
contain whole-disk before/after hashes or a transaction-stage receipt.

## Wipefs: confirmed failure, cause not captured

`DiskIO.signatures()` constructs the read-only wipefs command at
`scripts/install/disk_init.py:279-284`. The shipped fixture rewrites its device
argument to its private `/run/.../root/dev/loopN` node
(`tests/install/loop_disk_transaction.py:244-249`). Those block nodes are created
with `mknod` at `:183-198`. `Storage._run()` catches every runner exception and
replaces it with the generic tool-name error (`scripts/install/storage.py:77-81`).
Therefore the observed wrapper return code is 1, but **wipefs's own return code,
stderr, syscall errno and exact failing transaction stage are unavailable**.

The leading explanation is the fixture's placement of usable device nodes below
a `nodev` `/run` mount. Upstream systemd 255 declares `/run` with `MS_NODEV`;
Linux 6.17 denies opening block/character nodes through a nodev mount with
`EACCES`. The wrapper checks `/run` is tmpfs but does not capture or validate its
device-access mount flags. This explains why creating/stat-ing the node can
succeed while wipefs's first open fails. It is **an inference**, because this
run did not preserve `/run` mount options or wipefs's error. Sources:
[systemd 255 mount setup, lines 93-97](https://github.com/systemd/systemd/blob/v255/src/shared/mount-setup.c#L93-L97),
[Linux 6.17 device-open checks, lines 3220-3247](https://github.com/torvalds/linux/blob/v6.17/fs/namei.c#L3220-L3247).

The matching upstream util-linux 2.39.3 wipefs source supports every requested
column and the `--no-act`, `--json`, `--output` flags. No argument incompatibility
was identified in that source. Wipefs's own version was not separately recorded
by this run. [Upstream wipefs source](https://github.com/util-linux/util-linux/blob/v2.39.3/misc-utils/wipefs.c).

## Cleanup: confirmed faulty predicate

At `tests/install/loop_disk_transaction.sh:93-99`, the wrapper detaches its
validated loop and then treats any output from an explicit-device NAME listing
as evidence the backing remains attached.

Upstream util-linux 2.39.3 explicitly creates a table row when one loop device is
selected; its NAME column comes from the selected device pathname. That row does
not require an active backing association. Consequently the shipped predicate
can report incomplete detachment for an already detached loop whose device node
still exists. This is a **source-confirmed predicate defect** consistent with
the parent's unchanged association inventory. It does not justify retroactively
labelling cleanup PASS: scratch was actually retained, and the run did not record
an independent exact post-detach sysfs/mount inventory inside the namespace.
[Upstream losetup NAME handling](https://github.com/util-linux/util-linux/blob/v2.39.3/sys-utils/losetup.c#L224-L230),
[explicit-device table handling](https://github.com/util-linux/util-linux/blob/v2.39.3/sys-utils/losetup.c#L328-L338).

## Recommended bounded coordinator fix

Assign the shipped fixture changes to its owner or a new explicit fix task:

1. Capture the exact node path, node major/minor, containing mount flags and a
   sanitized read-only-open/wipefs failure code before entering the transaction.
   Preserve the real tool busy checks and do not turn unknown signatures into an
   empty result.
2. If nodev is confirmed, place only this fixture's exact owned loop/partition
   nodes on a tiny device-capable tmpfs mounted at its own scratch `root/dev`
   inside the private namespace, with exact mount-ID cleanup. Review this added
   fixture mount first. Do not remount `/run`, expose all of `/dev`, change host
   mount policy or use a production identity override.
3. Replace the NAME-only detach predicate with a bounded read-only check of
   active associations to the recorded backing inode/filesystem, plus exact
   loop/sysfs identity. A recycled loop name must never trigger another detach.
   Preserve scratch whenever association ownership cannot be established.
4. Add source/safety coverage for an unbound explicit loop NAME row, unknown or
   recycled associations and nodev fixture paths. A newly reviewed actual run
   must still execute the shipped dry-run and apply before the remaining matrix.

The current I2S source is not patched around either problem. This failure is
useful actual fixture-discovery evidence, not a production storage safety
failure or proof that an inference tool was installed or executed successfully.
