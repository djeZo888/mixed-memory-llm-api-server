# D0B — large-model disk applied

**PASS — storage verified 2026-09-14 22:39:47 UTC (2026-09-15 Europe/Ljubljana).**
Executed by Mac-Worker1 through SSH alias `ai-vm` on `llmserver`, following
Mac-Orchestrator's reviewed D0 disk plan and explicit phase-2 approval for the
user-supplied new disk. Local branch: `milestone/d0b-large-model-disk-applied`.

## Result

| Item | Verified value |
| --- | --- |
| Mount | `/data/models-large`, ext4, current device `/dev/sdc1` |
| Filesystem UUID | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` |
| Stable partition | `/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2-part1` |
| GPT PARTUUID | `e2b5ae5c-7050-4913-bcda-1741ab6f8252` |
| Parent identity | QEMU HARDDISK, serial `drive-scsi2`, 3221225472000 bytes |
| By-path / HCTL | `pci-0000:09:03.0-scsi-0:0:0:2` / `2:0:0:2` |
| Geometry | 512-byte logical/physical sectors; GPT; one Linux `AI_MODELS` partition; start 2048, size 6291451904 sectors (3221223374848 bytes) |
| Filesystem | Label `AI_MODELS`; reserved block count 0 |
| Permissions | Mounted root `user:ai` (1000:1001), mode 2775; empty underlying directory verified `root:root 000` before mount |

Actual `df -B1` at verification; space values are time-specific:

| Mount | 1B-blocks | Used | Available |
| --- | ---: | ---: | ---: |
| `/` | 15186501632 | 9195188224 | 5197541376 |
| `/data` | 2163348520960 | 657884557312 | 1395496128512 |
| `/data/models-large` | 3169495220224 | 28672 | 3169478414336 |

The new UUID-based fstab entry is exactly:

```fstab
UUID=a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a /data/models-large ext4 defaults,x-systemd.requires-mounts-for=/data,x-systemd.device-timeout=30s 0 2
```

## Checks and evidence

Evidence and metadata-preserving fstab backup are on the verified old data
filesystem at `/data/services/backups/d0-20260914T223347Z/`.

- **PASS:** full by-id/by-path, serial/model, byte-size, HCTL, sector-size and
  excluded root/data identity gates; blank `wipefs --no-act`, `blkid -p -c
  /dev/null`, `sfdisk --dump`, `mdadm --examine`, read-only PVS; no children,
  holders/slaves, swap, mounts in inspected process namespaces or open device users.
  Repeated immediately before partitioning; PVS contained only root `/dev/sda3`.
- **PASS:** `sfdisk --no-act --wipe never --wipe-partitions never` preview, then
  identical input with `--lock=yes --wipe never --wipe-partitions never`.
  Input SHA-256: `3f1ebd40d795c82d60d9c288503fd0ade2b8f011ec8300859ef4a2d2998b4dbe`.
- **PASS:** settled udev, verified stable part1 parent/geometry and only expected
  GPT/PMBR signatures on the disk; partition had no filesystem/RAID/LVM signature.
  Full pre-format gate repeated immediately before
  `mkfs.ext4 -L AI_MODELS -m 0 "$PART"`. No erase or force-format option used.
- **PASS:** fstab duplicate/conflict checks, candidate and applied `findmnt
  --verify --verbose`; zero parse errors/errors. Original fstab bytes preserved
  plus exactly one entry. Generated mount is active, with `Requires` and `After`
  including `data.mount`; new entry has no `nofail`.
- **PASS:** exact `findmnt --mountpoint` source/UUID/type checks, three distinct
  filesystem identities, ext4 geometry/capacity/reserve/ownership checks, and
  small user write/fsync/read/remove with inherited group `ai`.
- **PASS:** before/after `require-data-mounted.sh` and `root-disk-guard.sh
  --report <evidence>/root-disk-guard-{before,after}.md --min-root-free-gib 4
  --warn-root-free-gib 6`. Evidence copy of the root guard changes only its two
  fixed `/tmp` output paths to `/data`; its diff is saved. Guard checks and
  checked-in scripts are unchanged. Exact-byte checks supplement rounded GiB.

Fstab SHA-256 before: `aa677f87f02186076e1eb52bf6454dd6a57e197d01fe8d387149cd3ceea436f3`;
after: `54247ff4b42aa9ecc98700136d580f767b9d4fb6a7d80d599a41e86b1ed263a1`.
Backup `fstab.before` preserves original owner/mode/timestamps; metadata recorded.

## Preserved state and warnings

Root UUID remains `bc752bce-bb3f-4802-8adf-69c45a88689d`; existing `/data`
remains `/dev/sdb1`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`. Both excluded
partition tables compare unchanged. Remote dirty reports `m3-root-disk-guard`,
`m4b-docker-containerd-install`, and `m6b-nvidia-container-toolkit-install` retain
their hashes/status. Inspected AI environment, Docker/containerd configurations,
and obsolete M6B boot unit retain their hashes; boot-unit enabled state unchanged.

Accepted warnings: root below 6 GiB but above the exact 4 GiB halt threshold;
small existing bootstrap and pre-mount-root backup directories; existing fstab
swap-file warning. No final STOP conditions. Post-GPT validation initially
stopped on probe-output assumptions: flat `lsblk` JSON, protective-MBR `mdadm`
output, GPT metadata from `blkid`, and absent `slaves` directory for a plain
partition. Read-only checks resolved these; final full gate passed before mkfs.
Failed attempts and corrected validation evidence are retained.

Only mount-definition daemon-reload was performed. No reboot/service restart,
download, installation, runtime/model deployment or cache-path change. Boot
persistence is untested; obsolete M6B boot verification requires separate work.

## Rollback and next action

Healthy setup remains mounted. If rollback is later authorized: stop consumers,
unmount only `/data/models-large` normally (no force/lazy), remove only its new
fstab entry, reload definitions, then remove the empty underlying directory.
Restore `fstab.before` wholesale only after proving no concurrent fstab edits.
Partitioning/formatting has no data-preserving undo: leave the new GPT/ext4 disk
intact for review. Never alter root or existing data storage.

Storage handoff was written immediately to task artifact `storage-ready.md`.
Before future large work, rerun both guards and exact expected UUID mount checks;
downloads/runtime work still needs its separate authorization. Publication is a
separate bounded task; this milestone makes a local documentation commit only.
