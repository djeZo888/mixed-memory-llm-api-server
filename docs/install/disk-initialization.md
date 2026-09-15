# I1S disk transaction interface (schema 1)

Source implementation contract; whole-install readiness still awaits I1b/I2.

- `disk_init.plan(storage) -> dict`: read-only, requires initialize mode, exact
  `/dev/disk/by-id` plus matching basename confirmation. Save this storage plan
  (or the installer envelope containing it) before apply. Config digest excludes
  only `disk_plan`, allowing its path to be supplied after planning.
- `disk_init.initialize(storage) -> registration`: called only by the initialize
  branch of `Storage.adopt`. Owns a fixed, nonblocking disk-transaction lock in
  `/etc/local-ai-server`; the enclosing installer must retain L1 lifecycle lease.
  Calls `Storage(... storage_mode='existing', data_uuid=<intended UUID>,
  model_uuid=<same UUID>).adopt()` after the exact owned filesystem is mounted.
  Does not change Runner or the main stage interface.
- Production has no disk/journal/root override flags or environment overrides.
  `DiskIO` is an internal, injectable Python test boundary, not a CLI. It owns
  narrowly scoped disk-tool subprocesses, bounded process-group termination and
  child reaping; existing Storage discovery uses the supplied Runner.

Fixed trust anchor: `/etc/local-ai-server/disk-initialization.json`, root-owned
0600 regular file, single link, at most 32 KiB, protected 0700 parent. Atomic
replacement fsyncs file and directory. Schema keys: `schema_version`,
`transaction_id`, `plan`, `plan_sha256`, `config_sha256`, `ids` (disk_guid,
partition_uuid, filesystem_uuid, filesystem_label), `stage`. Stages in order:
`prepared`, `gpt_intent`, `gpt_done`, `fs_intent`, `fs_done`, `mount_intent`,
`mounted`, `complete`. Intended identities exist at `prepared`, before mutation.

Recovery checks hardware, full saved plan/config, exact GPT and single partition,
filesystem identity, topology, holders and mounts before continuing. Intent
stages may reconcile their complete postcondition after a missing receipt. Only
an entirely blank precondition can retry a destructive command. Partial/foreign
metadata is refused for operator investigation; no wipe/force repair is provided.
Completed transactions revalidate without formatting or rewriting receipts.

Supported shape: GPT, one 1 MiB-aligned Linux-data partition, ext4, explicit UUID
and label, zero reserved blocks. Models share data; a separate model filesystem
requires existing/UUID mode. No daemon changes or reboot.

## Saved-plan and execution boundary

`Storage.plan()` returns the storage object below; `install.sh plan` embeds it in
`storage`. Both forms are accepted by `disk_plan`. Read-only planning requires
root read access to the selected block device; it creates no journal, directories,
partition or filesystem. The saved plan must be a regular nonsymlink single-link
file. An ordinary user's saved plan is accepted only after exact rediscovery;
the protected journal becomes authoritative before any disk write.

The plan contains `schema_version:1`, `mode:initialize`, `identity` (by_id, serial,
wwn, size_bytes, sector_bytes), identity/config SHA256 digests, `shape` (GPT,
partition count, logical sector size, explicit start/count, ext4 block size,
reserved percentage, data/model paths and partition name), and `precondition`
(empty signatures/table/children/holders/mounts plus stable root/boot identity
observations). Kernel names and major:minor are re-observed, never saved as the
stable identity. Direct `scsi-*`, `wwn-*` and `nvme-*` whole-device IDs are supported.
Logical sectors may be 512 or4096 bytes; disk minimum is64MiB. The partition starts
at1MiB and ends before the final1MiB; ext4 block size is4096 bytes.

The initializer accepts only an explicit top-level dedicated data mount such as
`/data` or `/ai-data`, outside system locations. Models must be nested below it.
No other filesystem is acquired by this transaction. A new disk must read entirely
as zero, in addition to having no signatures, partition table, mounts or holders.
This conservative policy refuses signature-free foreign data in the disk middle.
Scanning is streamed in8MiB chunks, with a3600-second deadline per scan; planning
and destructive preconditions each recheck blankness. Large/slow media may stop
at that deadline. There is no bypass or force mode.

I1b integration is still required: the existing `main.run_boundary()` explicitly
raises `blank_disk_mutation_requires_i1b` before invoking storage. I1S does **not**
edit that concurrently owned gate. I1b must remove it only within its reviewed
integration, retain the canonical L1 lifecycle lease, and preserve full-apply's
pending status until all selected stages and acceptance are integrated. No public
standalone destructive helper CLI is provided; a Python-injected fixture is the
only alternate I/O mechanism. The loop wrapper's `--dry-run` is its plan step.

Prerequisites before selecting initialization: Linux root, a writable installer
Runner, util-linux (`lsblk`, `findmnt`, `wipefs`, `sfdisk`, `mount`), e2fsprogs
(`mkfs.ext4`, `e2fsck`) and `udevadm`. I1S installs none of these. I1R/I1b own any
package/bootstrap integration. New disk-tool subprocesses are confined to
`DiskIO`; this task adds no generic Runner allowlist entries or execution hooks.

## Recovery rules

| Durable stage | Accepted media state | Next action |
| --- | --- | --- |
| prepared | Entire disk blank | Write gpt_intent, then create GPT |
| gpt_intent | Blank, or exact complete intended GPT | Create only if blank; otherwise reconcile |
| gpt_done | Exact GPT, blank owned partition | Write fs_intent, then mkfs |
| fs_intent | Exact GPT plus blank partition or intended ext4 | Format only blank; validate ext4 if present |
| fs_done | Exact GPT/ext4, unmounted | Read-only fsck, prepare mount |
| mount_intent | Exact GPT/ext4, unmounted or at exact data target | Mount by UUID if needed; revalidate |
| mounted | Exact owned mounted filesystem | Resume existing Storage.adopt, fstab and completion |
| complete | Exact owned mount, registration and fstab entry | Revalidate; no journal/fstab/registration rewrite |

Missing or malformed journals, unexpected stages, identity/config/shape drift,
foreign signatures, extra GPT entries, CRC/header/table mismatch, changed UUIDs,
LVM/RAID/mapper devices, holders, root/boot ancestry and other mount targets stop.
Partial GPT/partial ext4 is never automatically repaired or reformatted. Retain
the saved plan and journal for review; do not delete them to force a retry. An
unmounted completed filesystem requires restoring its expected UUID mount before
rerunning; the initializer does not reinterpret that as a new disk.

Both on-disk GPT headers and partition arrays are read and CRC-checked directly.
An interrupted format is accepted only after exact UUID/label/size/reserved-block
checks and a successful unmounted `e2fsck -f -n`. Formatting uses explicit UUID,
label, `-m 0`, disabled lazy inode/journal initialization and `nodiscard`; no `-F`.
Duplicate disk GUID/PARTUUID/filesystem UUID observations are refused.

The helper retains a fixed journal flock and pinned device descriptors in children.
A parent crash cannot release the child-held transaction lock. Command failure,
timeout, or surviving process-group descendants stop before the next receipt;
timeouts kill the private process group and reap the leader. Limits: partition60s,
mkfs/fsck600s, mount30s, udev settle10s inside a15s process deadline; discovery30s.
Kernel-uninterruptible I/O may delay termination/reaping beyond these deadlines;
the transaction must retain ownership and stop rather than falsely advance.

Kernel-wide exclusive-open prechecks detect use outside the caller's mount
namespace. The precheck claim is released before external tools open the pinned
FD path: retaining it makes their own busy checks fail. Tools retain their normal
in-use/reread checks, with no force or bypass flags. This is not an atomic lease
against unrelated privileged administrators changing mounts/devices concurrently;
operators must honor the installer's exclusive maintenance window. I2 must verify
these exact tool versions and descriptor-path behavior on disposable Linux.

The underlying mountpoint is empty, nonsymlink, root-owned0700, with directory and
parent fsynced before mount. Mount uses the globally checked UUID and immediately
revalidates UUID, filesystem, exact mount and topology through existing Storage.
Only then does existing-mode adoption create managed directories and registration.
Its anchored-write integration remains I1b-owned; I1S makes no broader claim about
that independently owned mount-detach race.

Fstab is inspected for conflicting/duplicate entries and octal-escaped target
conflicts. The new UUID entry is appended atomically, preserving every existing
byte as a prefix, including CRLF and trailing blank lines. Missing final LF gets
one separator. No daemon reload is run. Fstab is bounded to32KiB, journal to32KiB;
there are no logs, model/cache/build payloads or bulk backups on root.

## Verification and evidence classes

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -v
bash -n tests/install/loop_disk_transaction.sh
./tests/install/loop_disk_transaction.sh --help
./tests/install/loop_disk_transaction.sh --dry-run
# Only in an explicitly disposable Linux environment with loop/mount capabilities:
sudo ./tests/install/loop_disk_transaction.sh --apply
```

The wrapper creates its own256MiB sparse backing file on an already-tmpfs `/run`,
new loop device, private mount namespace, fixture-only device nodes, journal,
fstab and data mount. It refuses caller-supplied disks and validates exact backing
inode, size, offset, loop identity and mount identity before work/cleanup. It tests
crashes after actual successful GPT/mkfs commands before receipts, checks GPT UUID,
PARTUUID, ext4 UUID/label/reserved blocks, preserved fstab bytes and completed replay.
Its loop-type/serial and container-root adapters are explicit test-only substitutions.
Global physical-device exclusion still requires independent I2 host acceptance.

Worker evidence: synthetic transaction fixtures and regular-file GPT/superblock
parser fixtures are source tests. They do not verify actual formatting. The Linux
loop fixture is **NOT_TESTED** on this Mac worker. Full fresh installation remains
pending independent I2 execution and integration acceptance.

## Primary implementation references

- [util-linux sfdisk manual](https://raw.githubusercontent.com/util-linux/util-linux/master/disk-utils/sfdisk.8.adoc): explicit GPT input and no-wipe options.
- [libfdisk GPT implementation](https://raw.githubusercontent.com/util-linux/util-linux/master/libfdisk/src/gpt.c): in-memory header recovery is why raw copies are checked.
- [e2fsprogs mke2fs manual](https://raw.githubusercontent.com/tytso/e2fsprogs/master/misc/mke2fs.8.in) and [e2fsck manual](https://raw.githubusercontent.com/tytso/e2fsprogs/master/e2fsck/e2fsck.8.in): filesystem options and read-only checking.
- [e2fsprogs mount/busy detection](https://raw.githubusercontent.com/tytso/e2fsprogs/master/lib/ext2fs/ismounted.c), [libfdisk device opening](https://raw.githubusercontent.com/util-linux/util-linux/master/libfdisk/src/context.c), [Linux partition scanning](https://raw.githubusercontent.com/torvalds/linux/master/block/genhd.c): tool ownership checks.
- [util-linux losetup](https://raw.githubusercontent.com/util-linux/util-linux/master/sys-utils/losetup.8.adoc) and [Python subprocess](https://docs.python.org/3/library/subprocess.html): isolated loop ownership and child cleanup.
