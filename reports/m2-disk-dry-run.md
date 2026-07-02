# M2 Data Disk Dry-Run Report

## Milestone

- Milestone ID: M2 dry-run
- Name: Data disk dry-run
- Timestamp: 2026-07-02T04:16:24+00:00
- Hostname: llmserver
- User: user
- Working directory: /home/user/codex-bootstrap/mixed-memory-llm-api-server
- Branch name: milestone/m2-data-disk-dry-run
- Git commit hash: fc045842b31e04373d5aaf48b84fb9e5dfc06d97

## Git Remote

```text
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (fetch)
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (push)
```

## Sudo Gate

### sudo -k

```console
$ sudo -k

[exit=0]
```

### sudo -n true

```console
$ sudo -n true

[exit=0]
```

### sudo -n id

```console
$ sudo -n id
uid=0(root) gid=0(root) groups=0(root)

[exit=0]
```

## Initial Summary

- Root filesystem summary: /dev/mapper/ubuntu--vg-ubuntu--lv ext4   14.1G  6.2G  7.2G /
- Root disk summary: /dev/sda  32G disk                               QEMU HARDDISK drive-scsi0
- /data state: exists but is not mounted; root-disk directory until M2 actual setup
- Existing /data contents summary: 3 entries below /data within depth 4

## Identity

### hostname

```console
$ hostname
llmserver

[exit=0]
```

### whoami

```console
$ whoami
user

[exit=0]
```

### date -Is

```console
$ date -Is
2026-07-02T04:16:24+00:00

[exit=0]
```

### pwd

```console
$ pwd
/home/user/codex-bootstrap/mixed-memory-llm-api-server

[exit=0]
```

## Git

### current branch

```console
$ git branch --show-current
milestone/m2-data-disk-dry-run

[exit=0]
```

### git remote -v

```console
$ git remote -v
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (fetch)
origin	git@github.com:djeZo888/mixed-memory-llm-api-server.git (push)

[exit=0]
```

### latest commit hash

```console
$ git rev-parse HEAD
fc045842b31e04373d5aaf48b84fb9e5dfc06d97

[exit=0]
```

## Root Mount

### df -hT /

```console
$ df -hT /
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.3G  7.2G  47% /

[exit=0]
```

### findmnt /

```console
$ findmnt /
TARGET SOURCE                            FSTYPE OPTIONS
/      /dev/mapper/ubuntu--vg-ubuntu--lv ext4   rw,relatime

[exit=0]
```

### lsblk full inventory

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                      QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat              BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4              1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member       2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4              bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                      QEMU HARDDISK aidata2tb

[exit=0]
```

## Existing Filesystem Signatures

### sudo -n blkid

```console
$ sudo -n blkid
/dev/mapper/ubuntu--vg-ubuntu--lv: UUID="bc752bce-bb3f-4802-8adf-69c45a88689d" BLOCK_SIZE="4096" TYPE="ext4"
/dev/sda2: UUID="1e35ddc8-6f3c-4eec-9650-6ef93d252b3b" BLOCK_SIZE="4096" TYPE="ext4" PARTUUID="d7b915e9-2dcd-45c9-9726-aefaa84b03eb"
/dev/sda3: UUID="2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp" TYPE="LVM2_member" PARTUUID="a8bd8ebb-e8b5-4fca-9bfc-dade9a0d89fb"
/dev/sda1: UUID="BBE0-E924" BLOCK_SIZE="512" TYPE="vfat" PARTUUID="3cf45807-c1be-47ef-966b-fc2f51bdf10a"

[exit=0]
```

## /data State

### findmnt /data

```console
$ findmnt /data || true

[exit=0]
```

### ls -ld /data

```console
$ if [ -e /data ]; then ls -ld /data; else echo "/data does not exist"; fi
drwxr-xr-x 4 root root 4096 Jul  1 00:52 /data

[exit=0]
```

### sudo -n find /data -maxdepth 4 -ls

```console
$ if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo "/data does not exist"; fi
   393230      4 drwxr-xr-x   4 root     root         4096 Jul  1 00:52 /data
   393231      4 drwxr-xr-x   2 root     root         4096 Jun 30 22:38 /data/docker
   393262      4 drwxr-xr-x   3 root     root         4096 Jul  1 00:52 /data/services
   393263      4 drwxr-xr-x   2 root     root         4096 Jul  1 00:52 /data/services/codex-smoke-test

[exit=0]
```

### existing /data contents summary

```console
$ if [ -e /data ]; then count=$(sudo -n find /data -maxdepth 4 -mindepth 1 -print | wc -l); echo "$count entries below /data within depth 4"; else echo "/data does not exist"; fi
3 entries below /data within depth 4

[exit=0]
```

## Disk Inventory

### all disks, partitions, filesystems, labels, UUIDs, mounts, model, serial

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                      QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat              BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4              1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member       2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4              bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                      QEMU HARDDISK aidata2tb

[exit=0]
```

### all top-level disks

```console
$ lsblk -dn -o PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
/dev/sda  32G disk                               QEMU HARDDISK drive-scsi0
/dev/sdb   2T disk                               QEMU HARDDISK aidata2tb

[exit=0]
```

### all partitions

```console
$ lsblk -rno NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL | awk '$4 == "part" {print}' || true
sda1 /dev/sda1 1G part vfat  BBE0-E924 /boot/efi
sda2 /dev/sda2 2G part ext4  1e35ddc8-6f3c-4eec-9650-6ef93d252b3b /boot
sda3 /dev/sda3 28.9G part LVM2_member  2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp

[exit=0]
```

### all LVM members and logical volumes

```console
$ lsblk -rno NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL | awk '$4 == "lvm" || $5 == "LVM2_member" {print}' || true
sda3 /dev/sda3 28.9G part LVM2_member  2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm ext4  bc752bce-bb3f-4802-8adf-69c45a88689d /

[exit=0]
```

### devices participating in root, boot, and EFI mounts

```console
$ for target in / /boot /boot/efi; do echo "## $target"; source=$(findmnt -n -o SOURCE "$target" 2>/dev/null || true); if [ -n "$source" ]; then findmnt -n -o TARGET,SOURCE,FSTYPE,OPTIONS "$target" || true; lsblk -s -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS "$source" || true; else echo "not mounted"; fi; done
## /
/      /dev/mapper/ubuntu--vg-ubuntu--lv ext4   rw,relatime
NAME                  PATH                               SIZE TYPE FSTYPE      LABEL UUID                                   MOUNTPOINTS
ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4              bc752bce-bb3f-4802-8adf-69c45a88689d   /
└─sda3                /dev/sda3                         28.9G part LVM2_member       2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─sda               /dev/sda                            32G disk
## /boot
/boot  /dev/sda2 ext4   rw,relatime
NAME  PATH      SIZE TYPE FSTYPE LABEL UUID                                 MOUNTPOINTS
sda2  /dev/sda2   2G part ext4         1e35ddc8-6f3c-4eec-9650-6ef93d252b3b /boot
└─sda /dev/sda   32G disk
## /boot/efi
/boot/efi /dev/sda1 vfat   rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=iso8859-1,shortname=mixed,errors=remount-ro
NAME  PATH      SIZE TYPE FSTYPE LABEL UUID                                 MOUNTPOINTS
sda1  /dev/sda1   1G part vfat         BBE0-E924                            /boot/efi
└─sda /dev/sda   32G disk

[exit=0]
```

## Candidate Disk Evaluation

- Root filesystem summary: `/dev/mapper/ubuntu--vg-ubuntu--lv ext4   14.1G  6.2G  7.2G /`
- Root disk summary: `/dev/sda`
- /boot disk summary: `/dev/sda`
- /boot/efi disk summary: `/dev/sda`
- /data state: /data is not mounted

| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No disk signature | No partition filesystems | Not LVM PV | Not stack member | Safe | Reason |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/dev/sda` | 34359738368 | QEMU HARDDISK | drive-scsi0 | no | no | no | no | yes | no | no | no | no | size not approximately 2 TB; root disk, root ancestor, or protected boot ancestor; used by /boot or /boot/efi; mounted children: /boot/efi, /boot, /; partition filesystem/signature: /dev/sda1, /dev/sda2, /dev/sda3; LVM physical volume present; stack member/type: lvm |
| `/dev/sdb` | 2199023255552 | QEMU HARDDISK | aidata2tb | yes | yes | yes | yes | yes | yes | yes | yes | yes | all safety checks passed |

## Selected Future Data Disk

`/dev/sdb`

## Reason Selected Disk Is Safe

Exactly one candidate disk passed all dry-run checks: disk type, approximately 2 TB, not root, not a root ancestor, not used by /boot or /boot/efi, unmounted, no mounted children, no disk filesystem signature, no partition filesystem signatures, not an LVM physical volume, and not part of mdraid/dmcrypt/LVM stack.

## Proposed Future Commands - NOT RUN

The following commands document the intended future M2 actual setup shape only. They were not run by this dry-run script.

```bash
# NOT RUN - documentation for future M2 actual setup only.
# Preconditions: human review of this dry-run report, exact target disk confirmed,
# and a fresh dry-run immediately before destructive commands.

# 1. If existing root-disk /data contains only safe bootstrap/test files, move it aside.
sudo mv /data /data.root-disk-pre-m2.$(date -u +%Y%m%dT%H%M%SZ)

# 2. Create a GPT partition table and one data partition on the verified disk.
sudo parted --script /dev/VERIFIED_DATA_DISK mklabel gpt
sudo parted --script /dev/VERIFIED_DATA_DISK mkpart AI_DATA ext4 0% 100%
sudo partprobe /dev/VERIFIED_DATA_DISK

# 3. Format ext4 with label AI_DATA.
sudo mkfs.ext4 -L AI_DATA /dev/VERIFIED_DATA_PARTITION

# 4. Get UUID and create mountpoint.
sudo blkid /dev/VERIFIED_DATA_PARTITION
sudo mkdir -p /data

# 5. Add /etc/fstab line by UUID, then mount.
echo 'UUID=VERIFIED_UUID /data ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount /data

# 6. Create required data directories.
sudo mkdir -p /data/models /data/hf-cache /data/docker /data/containerd
sudo mkdir -p /data/services /data/build /data/logs /data/backups /data/services/secrets

# 7. Create AI data environment file.
sudo tee /etc/profile.d/ai-data-paths.sh >/dev/null <<'PROFILE_EOF'
export AI_DATA=/data
export HF_HOME=/data/hf-cache
export HF_HUB_CACHE=/data/hf-cache/hub
export HF_XET_CACHE=/data/hf-cache/xet
export HF_ASSETS_CACHE=/data/hf-cache/assets
export HF_DATASETS_CACHE=/data/hf-cache/datasets
export TRANSFORMERS_CACHE=/data/hf-cache/transformers
export XDG_CACHE_HOME=/data/hf-cache/xdg
export AI_BUILD_DIR=/data/build
export AI_LOG_DIR=/data/logs
PROFILE_EOF

# 8. Verify before reboot.
findmnt /data
df -hT / /data
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL

# 9. Reboot and verify again.
sudo reboot
findmnt /data
df -hT / /data
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
```


## Post-Run Repository Checks

- `chmod +x scripts/preflight/disk-dry-run.sh tests/shell/test-disk-dry-run-static.sh`: PASS.
- `tests/shell/test-disk-dry-run-static.sh`: PASS.
- `scripts/preflight/disk-dry-run.sh`: PASS; generated this report and selected `/dev/sdb`.
- `bash -n scripts/preflight/disk-dry-run.sh`: PASS.
- `bash -n tests/shell/test-disk-dry-run-static.sh`: PASS.
- `git diff --check`: PASS.
- Grep-based sensitive-value scan: PASS; matches were intentional documentation warnings, workflow references, existing redaction patterns, and ignore entries only. No real sensitive value was detected.

## Scope Confirmation

- No partition commands were run.
- No format commands were run.
- No wipe commands were run.
- No filesystem was mounted or unmounted.
- /etc/fstab was not edited.
- /data was not created, moved, deleted, mounted, or modified.
- /dev/sdb was not initialized or modified.
- No packages were installed.
- Docker was not configured.
- NVIDIA drivers were not configured.
- systemd was not configured.
- No models were downloaded.
- No API was exposed.

## Conclusion

PASS

Selected future data disk: `/dev/sdb`.

## Next Recommended Milestone

M2 actual /data setup after human review.
