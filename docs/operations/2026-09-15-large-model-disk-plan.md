# D0 phase 1 — 3000 GiB model disk initialization plan

**Result: PASS for discovery and dry-run; STOP before phase 2.** Mac-Worker1 for Mac-Orchestrator. Live evidence: SSH alias `ai-vm`, host `llmserver`, 2026-09-14 22:25–22:30 UTC (2026-09-15 Europe/Ljubljana). Read `AGENTS.md` and the supplied R1 early evidence; did not repeat R1's broad audit or wait for its final report. This report is at the user's explicitly requested path instead of the generic `reports/` milestone path.

The user assigned a new approximately 3 TB disk and authorized eventual initialization, but this task authorizes **discovery/dry-run only**. No partition, filesystem, mount, fstab, package, service, download, or reboot changes were performed. `sudo -n true` succeeded; normal SSH/sudo audit logging may occur. Local reports and this feature-branch commit/push are authorized. **A separate explicit orchestrator follow-up is required before executing any phase 2 commands below.**

## Identity and preservation boundary

| Role | Live device and stable identity | Bytes / filesystem |
| --- | --- | --- |
| **New candidate** | `/dev/sdc`; `/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2`; model `QEMU HARDDISK`; serial `drive-scsi2` | **3,221,225,472,000 bytes**, exactly 3000 GiB / 2.9296875 TiB; no detected signatures |
| **Preserve root disk** | `/dev/sda`; by-id `scsi-0QEMU_QEMU_HARDDISK_drive-scsi0`; model `QEMU HARDDISK`; serial `drive-scsi0` | 34,359,738,368 bytes; GPT; EFI sda1, boot sda2, LVM PV sda3 |
| **Preserve existing data disk** | `/dev/sdb`; by-id `scsi-SQEMU_QEMU_HARDDISK_aidata2tb` (also `scsi-0QEMU_QEMU_HARDDISK_drive-scsi1`); model `QEMU HARDDISK`; serial `aidata2tb` | 2,199,023,255,552 bytes; GPT; sdb1 ext4 `AI_DATA`, 2,199,021,158,400 bytes |

Candidate by-path is `/dev/disk/by-path/pci-0000:09:03.0-scsi-0:0:0:2`; SCSI HCTL `2:0:0:2`; sysfs topology ends `0000:09:03.0/virtio4/host2/target2:0:0/2:0:0:2/block/sdc`. Udev reports `ID_SERIAL=0QEMU_QEMU_HARDDISK_drive-scsi2`, `ID_SERIAL_SHORT=drive-scsi2`, `ID_MODEL=QEMU_HARDDISK`, `ID_BUS=scsi`. No WWN is advertised. Logical/physical sectors are both 512 bytes; disk is writable (`RO=0`). These combined properties identify the guest device; QEMU serial/path can change or be reused by VM configuration changes, so the by-id link alone is insufficient evidence later.

Fresh exact mounts:

- `/`: `/dev/mapper/ubuntu--vg-ubuntu--lv`, ext4 UUID `bc752bce-bb3f-4802-8adf-69c45a88689d`, device `252:0`; parent sda3, PV UUID `2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp`, VG `ubuntu-vg`. Root GPT ID `17AFA941-9664-4825-B26A-0FD0C592D685`.
- `/data`: `/dev/sdb1`, ext4 label `AI_DATA`, UUID **`8daf56f1-5649-4163-9d87-919c2d271875`**, device `8:17`; PARTUUID `b793b230-9046-4bba-9c45-f09eaf1f1378`; data GPT ID `270EEF83-6C54-474C-8CBB-85D3C7446AC2`.
- `/boot`: sda2, ext4 UUID `1e35ddc8-6f3c-4eec-9650-6ef93d252b3b`; `/boot/efi`: sda1, vfat UUID `BBE0-E924`. Swap is `/swap.img`, not the candidate.
- `/data/models-large` is absent. `/data` is root:root 0755; existing `/data/models` is user:ai, UID:GID 1000:1001, mode 2775. Group `ai` includes `user`.
- Available bytes: root **5,197,508,608** (~4.84 GiB, below guard's 6 GiB warning threshold); old `/data` **1,406,234,140,672**. These are volatile. No cleanup, relocation, root expansion, or changes to existing model/cache content are included.

## Read-only checks and dry-run results

| Check run | Result |
| --- | --- |
| `lsblk -b -e 7` with identity, topology, filesystem, UUID, mount, sector and RO columns; by-id/by-path links; `udevadm info`; `blockdev --getsize64` | PASS: candidate identity above; exactly one whole disk, no children |
| sysfs `holders` / `slaves`; block-backed `findmnt`; `fuser -v` | PASS: candidate has no holders/slaves/mounts/open users; fuser exit 1, no output |
| `sudo -n wipefs --no-act "$DISK"` | PASS: exit 0, no signatures |
| `sudo -n blkid -p -c /dev/null "$DISK"` | PASS: exit 2, no recognized signature |
| `sudo -n sfdisk --dump "$DISK"` | PASS: exit 1, explicitly no recognized partition table |
| `sudo -n mdadm --examine "$DISK"`; `/proc/mdstat` | PASS: exit 1, no MD superblock; no active MD arrays |
| `sudo -n pvs --readonly --nohints --config 'devices { write_cache_state=0 } backup { backup=0 archive=0 }' -o pv_name,pv_uuid,vg_name,pv_size,pv_attr` | PASS: only root sda3 PV; candidate is not a detected LVM member |
| Root/data `sfdisk --dump`; exact `findmnt --mountpoint`; sanitized fstab read/hash | PASS: exclusions and existing mounts freshly verified |
| Exact proposed `sfdisk --no-act --lock=yes --wipe never --wipe-partitions never` input below | PASS: start 2048, end 6291453951, 6291451904 sectors; output explicitly **“The partition table is unchanged (--no-act).”** Subsequent wipefs remained empty |
| Full repository storage guards | NOT RUN in phase 1: root guard writes report/temp files and invokes `sudo -k`; direct read-only checks used instead |

No detected filesystem, partition, RAID or LVM signature conflicts with the user's blank-new-disk assignment. This is signature-level evidence, not a forensic proof that every sector is zero. An initial probe stopped because remote `rg` was unavailable and partition sysfs entries lack `slaves`; it was rerun successfully with `grep` and existence checks. Nothing was installed.

Fstab active entries were inspected with credential-bearing option values redacted before output; none required redaction. Existing `/data` entry is:

```fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2
```

Fstab SHA-256: `aa677f87f02186076e1eb52bf6454dd6a57e197d01fe8d387149cd3ceea436f3`. Existing root, boot, EFI and swap entries must remain byte-for-byte unchanged. No fstab write occurred.

## Phase 2 plan — commands for future review, NOT executed

These are ordered operator-run command fragments, not a deployed script. Run through **SSH alias `ai-vm`**, in Bash with `set -euo pipefail`. Stop on any error, unexpected output, or failed assertion; never use force flags or erase unknown signatures. If converted to a script, implement `--help`, default `--dry-run`, explicit execution selection, and all refusal gates required by AGENTS.md.

### 1. Revalidate before every destructive step

Set the immutable expectations:

```bash
set -euo pipefail
DISK=/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2
PART=${DISK}-part1
OLD_DATA_UUID=8daf56f1-5649-4163-9d87-919c2d271875
ROOT_UUID=bc752bce-bb3f-4802-8adf-69c45a88689d
DATA_DISK=/dev/disk/by-id/scsi-SQEMU_QEMU_HARDDISK_aidata2tb
ROOT_DISK=/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi0
assert_base_mounts() {
  test "$(findmnt -rn -M / -o UUID)" = "$ROOT_UUID"
  test "$(findmnt -rn -M /data -o UUID)" = "$OLD_DATA_UUID"
  test "$(findmnt -rn -M /data -o FSTYPE)" = ext4
  test "$(readlink -f "$(findmnt -rn -M /data -o SOURCE)")" = "$(readlink -f "${DATA_DISK}-part1")"
  test "$(findmnt -rn -M / -o MAJ:MIN)" != "$(findmnt -rn -M /data -o MAJ:MIN)"
}
assert_base_mounts
sudo -n true
test -b "$DISK"
test "$(sudo -n blockdev --getsize64 "$DISK")" = 3221225472000
test "$(readlink -f "$DISK")" != "$(readlink -f "$DATA_DISK")"
test "$(readlink -f "$DISK")" != "$(readlink -f "$ROOT_DISK")"
```

**Mandatory manual gate immediately before partitioning:** repeat every identity/signature/topology probe in the evidence table; require the same model, serial, path/HCTL, 512-byte sectors, byte size and blank state, and the same protected root/data identities. Require one candidate whole-disk node, zero child partitions, empty holders/slaves, no mounts/swap/LVM/MD/open users. Confirm `/data/models-large` remains absent, is not a symlink, and has no fstab/systemd mount configuration. Re-read fstab and compare its hash with phase 1; drift requires STOP and a revised review. Missing output is not success except the documented signature results; distinguish expected no-signature exit codes from probe/I/O failures. Keep other disk/configuration work quiescent through formatting.

From the reviewed deployment checkout under `/data/services`, run `scripts/common/require-data-mounted.sh` and `scripts/common/root-disk-guard.sh` before and after phase 2; STOP on either failure. Preserve R1's dirty reports by directing root guard `--report` to a new `/data` evidence path. Do not run the stale boot verifier or change branches/services. Review guard temporary-file behavior before execution: this task did not authorize or run it. Root guard cannot be redirected to the new mount with `--data-path`: its expected identity remains old `AI_DATA`.

After `assert_base_mounts`, place phase 2 evidence/backups under `/data/services/backups/d0-<UTC>/` (never root). Use a unique, previously absent directory and preserve fstab metadata:

```bash
BACKUP=/data/services/backups/d0-$(date -u +%Y%m%dT%H%M%SZ)
test "$(readlink -f /data/services)" = /data/services
sudo -n test ! -L /data/services/backups
sudo -n mkdir -p -- /data/services/backups
sudo -n test ! -e "$BACKUP"
sudo -n mkdir -m 0700 -- "$BACKUP"
sudo -n cp -a -- /etc/fstab "$BACKUP/fstab.before"
sudo -n sha256sum /etc/fstab
```

Save fresh identity/signature/geometry evidence there after the guards pass. There is no recognized candidate partition table to dump as a restorable table; do not pretend a blank-table report is a data backup.

### 2. Preview and create exactly one GPT partition

Use this same input for both the reviewed dry-run and eventual execution. Explicit sectors avoid ambiguous TB/TiB sizing and leave 1 MiB at each end (including GPT metadata). Partition bytes: **3,221,223,374,848**. Dry-run's generated GPT GUID is only a preview; capture actual GPT/PARTUUID after execution. `--no-act` avoids disk writes; `--lock=yes` coordinates with udev; exact sector input is honored by sfdisk. [util-linux sfdisk manual](https://man7.org/linux/man-pages/man8/sfdisk.8.html)

```bash
layout() {
  cat <<'TABLE'
label: gpt
unit: sectors
sector-size: 512

start=2048, size=6291451904, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="AI_MODELS"
TABLE
}
layout | sudo -n sfdisk --no-act --lock=yes --wipe never --wipe-partitions never "$DISK"
# FUTURE PHASE 2 ONLY: repeat section 1's complete gate immediately before this line.
layout | sudo -n sfdisk --lock=yes --wipe never --wipe-partitions never "$DISK"
sudo -n udevadm settle --timeout=30
sudo -n sfdisk --verify "$DISK"
sudo -n sfdisk --dump "$DISK"
```

**Second mandatory gate before mkfs:** recheck the parent by-id/model/serial/bytes/path, exclusions, holders/users/mounts, and the new GPT. Require exactly one partition: stable `$PART` resolves to the candidate's partition 1, start 2048, size 6291451904 sectors, Linux filesystem type, name `AI_MODELS`; no extra partitions. Verify `blockdev --getsize64 "$PART"` equals 3221223374848 and its `lsblk -ndo PKNAME` equals the current candidate kernel name. Whole disk now has expected GPT/PMBR signatures only; `$PART` must have no filesystem/LVM/RAID signatures (`wipefs --no-act`, `blkid -p -c /dev/null`, `mdadm --examine`), mounts, holders, or users. If interrupted after partitioning, STOP and inspect current state; never rerun partitioning or formatting automatically.

```bash
sudo -n mkfs.ext4 -L AI_MODELS -m 0 "$PART"
NEW_UUID=$(sudo -n blkid -p -s UUID -o value "$PART")
[[ "$NEW_UUID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]
test "$NEW_UUID" != "$OLD_DATA_UUID"
test "$NEW_UUID" != "$ROOT_UUID"
test "$(sudo -n blkid -p -s TYPE -o value "$PART")" = ext4
test "$(sudo -n blkid -p -s LABEL -o value "$PART")" = AI_MODELS
```

No `-F` is used. `-m 0` reserves no blocks for root on this dedicated data filesystem; ext4 metadata still reduces usable capacity. Record actual UUID and capacity, never invent a future UUID. [e2fsprogs mke2fs manual](https://man7.org/linux/man-pages/man8/mke2fs.8.html)

### 3. Back up, validate fstab, mount only the new volume

Reassert `/data`, reject any occupied/symlink mountpoint or duplicate label/UUID/fstab entry, and confirm no concurrent fstab edits. The underlying directory is mode 000 so normal users cannot accidentally write to old `/data` when the new volume is absent; root still requires the explicit mount gates.

```bash
assert_base_mounts
test ! -e /data/models-large && test ! -L /data/models-large
sudo -n mkdir -m 000 -- /data/models-large
sudo -n cp -a -- "$BACKUP/fstab.before" "$BACKUP/fstab.after"
printf '\nUUID=%s /data/models-large ext4 defaults,x-systemd.requires-mounts-for=/data,x-systemd.device-timeout=30s 0 2\n' "$NEW_UUID" |
  sudo -n tee -a "$BACKUP/fstab.after" >/dev/null
sudo -n findmnt --verify --verbose --tab-file "$BACKUP/fstab.after"
# Review locally; redact any credentials before sharing this diff.
DIFF_RC=0
sudo -n diff -u -- "$BACKUP/fstab.before" "$BACKUP/fstab.after" || DIFF_RC=$?
test "$DIFF_RC" -eq 1
# MANUAL GATE: review exactly one added entry; stop before the next block.
```

Only after reviewing that exact candidate diff, replace fstab and mount:

```bash
sudo -n cmp -- /etc/fstab "$BACKUP/fstab.before"
sudo -n test ! -e /etc/fstab.d0-new
sudo -n cp -a -- "$BACKUP/fstab.after" /etc/fstab.d0-new
sudo -n mv -T -- /etc/fstab.d0-new /etc/fstab
sudo -n systemctl daemon-reload
assert_base_mounts
sudo -n mount /data/models-large
```

The preceding manual review must confirm exactly one new entry and all old entries/content preserved. Do not use `mount -a`. Proposed literal entry (substitute only the captured UUID):

```fstab
UUID=<actual-new-UUID> /data/models-large ext4 defaults,x-systemd.requires-mounts-for=/data,x-systemd.device-timeout=30s 0 2
```

The new entry omits `nofail`: a missing new disk can block normal boot/local-fs completion and require console recovery. `/data` is an explicit prerequisite; existing `/data` retains its current `nofail` option. Systemd generates mount units from fstab at boot/reload. Check generated `Requires`/`After` dependencies without rebooting; do not change this policy silently. [systemd mount documentation](https://github.com/systemd/systemd/blob/main/man/systemd.mount.xml)

### 4. Verify exact mounts, ownership, capacity and future download gates

Before ownership changes, test writes, or any model download, assert both exact mountpoints (not merely `findmnt --target`, which can return a parent filesystem):

```bash
assert_large_mount() {
  assert_base_mounts
  test "$(findmnt -rn -M /data/models-large -o UUID)" = "$NEW_UUID"
  test "$(findmnt -rn -M /data/models-large -o FSTYPE)" = ext4
  test "$(findmnt -rn -M /data/models-large -o FSROOT)" = /
  test "$(readlink -f "$(findmnt -rn -M /data/models-large -o SOURCE)")" = "$(readlink -f "$PART")"
  test "$(findmnt -rn -M /data/models-large -o MAJ:MIN)" != "$(findmnt -rn -M /data -o MAJ:MIN)"
  test "$(findmnt -rn -M /data/models-large -o MAJ:MIN)" != "$(findmnt -rn -M / -o MAJ:MIN)"
  test "$(sudo -n blkid -p -s LABEL -o value "$PART")" = AI_MODELS
}
assert_large_mount
sudo -n chown user:ai /data/models-large
sudo -n chmod 2775 /data/models-large
df -B1 --output=source,fstype,size,used,avail,target / /data /data/models-large
stat -c '%U:%G %u:%g mode=%a %n' /data/models-large
sudo -n findmnt --verify --verbose
systemctl show "$(systemd-escape --path --suffix=mount /data/models-large)" -p Requires -p After -p What -p Where
```

Check expected partition capacity/parent, new filesystem capacity/available bytes, mounted read-write options, and ownership 1000:1001 mode 2775. Perform a unique small file create/read/remove as `user` **only after `assert_large_mount`**, then rerun both repository guards with new `/data` report destinations. Compare preserved root/data UUIDs, partition tables and fstab entries against baseline. Stop on guard failure; report root-space warnings.

No download is part of either this discovery or the initialization plan. Before later large downloads, a reviewed launcher must persist the expected new UUID and require both mount assertions in its own mount namespace, plus both repository guards before/after the milestone. Explicitly place model output, download cache and temporary staging on the verified new filesystem; check resolved paths and required free space. Merely creating `/data/models-large`, seeing `/data` mounted, or having fstab text is insufficient. Current model/cache paths and content are preserved; no migration or profile/cache rewrite is included here.

**Reboot validation: NOT TESTED and no reboot planned.** R1 independently found an enabled stale M6B boot verifier that changes deployment branches and writes reports. Remediate/review that in a separate authorized task before any reboot; fstab/static dependency checks are not a reboot test.

### 5. Backup/rollback handling

- Before the first disk write: cancel freely; nothing has changed on the disk. Phase 2 backup holds fstab metadata/content and evidence, not user data from a supposedly blank disk.
- After GPT/mkfs: no data-preserving undo exists. Leave the new partition/filesystem intact for review; never automatically wipe it to simulate rollback. Formatting an unexpected data-bearing device is forbidden.
- If mount/fstab verification fails: stop consumers if any, revalidate target, then `sudo -n umount /data/models-large` only if it is the expected new mounted filesystem. Never use force/lazy unmount, and never unmount old `/data` or root.
- If live fstab still exactly matches `$BACKUP/fstab.after`, restore `$BACKUP/fstab.before` via the same checked temporary-copy/atomic-rename procedure; otherwise stop and review a merge removing only the new entry, preserving concurrent edits. Run `findmnt --verify --verbose` and `systemctl daemon-reload` after restoration. Remove only an unmounted, empty, verified `/data/models-large` directory with `rmdir`; no recursive deletion. Keep evidence/backups and report partial state.

## Handoff and validation

`../disk-plan.md` was published immediately after identity/signature discovery, before this report and commit. `../progress.md` tracks delivery. Local validation: PASS for report-only diff review, whitespace, Bash command-fragment syntax (syntax only; phase 2 not executed), independent safety review, and silent grep-based credential scan using repository patterns plus URL/credential checks. The independent review prompted moving the fstab diff gate ahead of replacement. Git remote must match the pinned `djeZo888/mixed-memory-llm-api-server` HTTPS/SSH repository; push only `milestone/d0-large-model-disk-plan`. Do not commit handoff files, secrets, or unrelated changes. Mac-Worker1 authorship is stated here; existing repository Git attribution is preserved.

**Next recommended action:** Mac-Orchestrator reviews this exact target, mount/boot policy and command plan, then sends a separate explicit phase 2 follow-up. No installation, backend/model work, download, service restart, or phase 2 execution is authorized by this report.
