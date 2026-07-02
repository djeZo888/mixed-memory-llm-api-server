# M2A Data Disk Setup Report

## Milestone

- Milestone ID: M2A actual /data setup
- Timestamp: 2026-07-02T08:34:25+00:00
- Hostname: llmserver
- User: user
- Working directory: /home/user/codex-bootstrap/mixed-memory-llm-api-server
- Branch name: milestone/m2-data-disk-setup
- Git commit hash at run start: e1dcb5085a17e22d6b31f08c2f0eeae4700ad98d
- Mode: actual
- Target disk: /dev/sdb

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

## Required Tool Check

### command -v lsblk

```console
$ command -v lsblk
/usr/bin/lsblk

[exit=0]
```

### command -v findmnt

```console
$ command -v findmnt
/usr/bin/findmnt

[exit=0]
```

### command -v blkid

```console
$ command -v blkid
/usr/sbin/blkid

[exit=0]
```

### command -v sfdisk

```console
$ command -v sfdisk
/usr/sbin/sfdisk

[exit=0]
```

### command -v partprobe

```console
$ command -v partprobe
/usr/sbin/partprobe

[exit=0]
```

### command -v mkfs.ext4

```console
$ command -v mkfs.ext4
/usr/sbin/mkfs.ext4

[exit=0]
```

### command -v systemctl

```console
$ command -v systemctl
/usr/bin/systemctl

[exit=0]
```

### command -v stat

```console
$ command -v stat
/usr/bin/stat

[exit=0]
```

### command -v awk

```console
$ command -v awk
/usr/bin/awk

[exit=0]
```

### command -v sed

```console
$ command -v sed
/usr/bin/sed

[exit=0]
```

### command -v grep

```console
$ command -v grep
/usr/bin/grep

[exit=0]
```

### command -v sudo

```console
$ command -v sudo
/usr/bin/sudo

[exit=0]
```

## Initial Read-Only Inventory

### df -hT /

```console
$ df -hT /
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /

[exit=0]
```

### findmnt /

```console
$ findmnt /
TARGET SOURCE                            FSTYPE OPTIONS
/      /dev/mapper/ubuntu--vg-ubuntu--lv ext4   rw,relatime

[exit=0]
```

### findmnt /data

```console
$ findmnt /data || true

[exit=0]
```

### ls -ld /data

```console
$ if [ -e /data ]; then ls -ld /data; else echo '/data does not exist'; fi
drwxr-xr-x 4 root root 4096 Jul  1 00:52 /data

[exit=0]
```

### sudo -n find /data -maxdepth 4 -ls

```console
$ if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo '/data does not exist'; fi
   393230      4 drwxr-xr-x   4 root     root         4096 Jul  1 00:52 /data
   393231      4 drwxr-xr-x   2 root     root         4096 Jun 30 22:38 /data/docker
   393262      4 drwxr-xr-x   3 root     root         4096 Jul  1 00:52 /data/services
   393263      4 drwxr-xr-x   2 root     root         4096 Jul  1 00:52 /data/services/codex-smoke-test

[exit=0]
```

### lsblk inventory before setup

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

### sudo -n blkid before setup

```console
$ sudo -n blkid
/dev/mapper/ubuntu--vg-ubuntu--lv: UUID="bc752bce-bb3f-4802-8adf-69c45a88689d" BLOCK_SIZE="4096" TYPE="ext4"
/dev/sda2: UUID="1e35ddc8-6f3c-4eec-9650-6ef93d252b3b" BLOCK_SIZE="4096" TYPE="ext4" PARTUUID="d7b915e9-2dcd-45c9-9726-aefaa84b03eb"
/dev/sda3: UUID="2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp" TYPE="LVM2_member" PARTUUID="a8bd8ebb-e8b5-4fca-9bfc-dade9a0d89fb"
/dev/sda1: UUID="BBE0-E924" BLOCK_SIZE="512" TYPE="vfat" PARTUUID="3cf45807-c1be-47ef-966b-fc2f51bdf10a"

[exit=0]
```

### Safety Gate: actual preflight before any destructive command

- Required target: `/dev/sdb`
- Root disk: `/dev/sda`
- /boot disk: `/dev/sda`
- /boot/efi disk: `/dev/sda`

| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No filesystem signatures | No existing partitions | Not LVM | Not stack member | Safe | Reason |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/dev/sda` | 34359738368 | QEMU HARDDISK | drive-scsi0 | no | no | no | no | yes | no | no | no | no | size not approximately 2 TB; root disk, root ancestor, or protected boot ancestor; used by /boot or /boot/efi; mounted children: /boot/efi, /boot, /; existing partitions: /dev/sda1, /dev/sda2, /dev/sda3; partition filesystem signatures: /dev/sda1, /dev/sda2, /dev/sda3; LVM physical volume present; stack member/type: lvm |
| `/dev/sdb` | 2199023255552 | QEMU HARDDISK | aidata2tb | yes | yes | yes | yes | yes | yes | yes | yes | yes | all safety checks passed |

PASS: exactly one safe candidate exists and it is `/dev/sdb`.

### Safety Gate: immediately before moving root-disk /data aside

- Required target: `/dev/sdb`
- Root disk: `/dev/sda`
- /boot disk: `/dev/sda`
- /boot/efi disk: `/dev/sda`

| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No filesystem signatures | No existing partitions | Not LVM | Not stack member | Safe | Reason |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/dev/sda` | 34359738368 | QEMU HARDDISK | drive-scsi0 | no | no | no | no | yes | no | no | no | no | size not approximately 2 TB; root disk, root ancestor, or protected boot ancestor; used by /boot or /boot/efi; mounted children: /boot/efi, /boot, /; existing partitions: /dev/sda1, /dev/sda2, /dev/sda3; partition filesystem signatures: /dev/sda1, /dev/sda2, /dev/sda3; LVM physical volume present; stack member/type: lvm |
| `/dev/sdb` | 2199023255552 | QEMU HARDDISK | aidata2tb | yes | yes | yes | yes | yes | yes | yes | yes | yes | all safety checks passed |

PASS: exactly one safe candidate exists and it is `/dev/sdb`.

## Move Existing Root-Disk /data Aside

### existing /data before move

```console
$ sudo -n find /data -maxdepth 4 -ls
   393230      4 drwxr-xr-x   4 root     root         4096 Jul  1 00:52 /data
   393231      4 drwxr-xr-x   2 root     root         4096 Jun 30 22:38 /data/docker
   393262      4 drwxr-xr-x   3 root     root         4096 Jul  1 00:52 /data/services
   393263      4 drwxr-xr-x   2 root     root         4096 Jul  1 00:52 /data/services/codex-smoke-test

[exit=0]
```

### move /data aside

```console
$ sudo -n mv /data /data.pre-mount-root-20260702-083425

[exit=0]
```

Moved old root-disk /data aside to: `/data.pre-mount-root-20260702-083425`

### create fresh /data mountpoint

```console
$ sudo -n mkdir -p /data

[exit=0]
```

### set /data mountpoint permissions before mount

```console
$ sudo -n chmod 0755 /data

[exit=0]
```

## Partition Disk

### Safety Gate: immediately before partition table creation

- Required target: `/dev/sdb`
- Root disk: `/dev/sda`
- /boot disk: `/dev/sda`
- /boot/efi disk: `/dev/sda`

| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No filesystem signatures | No existing partitions | Not LVM | Not stack member | Safe | Reason |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/dev/sda` | 34359738368 | QEMU HARDDISK | drive-scsi0 | no | no | no | no | yes | no | no | no | no | size not approximately 2 TB; root disk, root ancestor, or protected boot ancestor; used by /boot or /boot/efi; mounted children: /boot/efi, /boot, /; existing partitions: /dev/sda1, /dev/sda2, /dev/sda3; partition filesystem signatures: /dev/sda1, /dev/sda2, /dev/sda3; LVM physical volume present; stack member/type: lvm |
| `/dev/sdb` | 2199023255552 | QEMU HARDDISK | aidata2tb | yes | yes | yes | yes | yes | yes | yes | yes | yes | all safety checks passed |

PASS: exactly one safe candidate exists and it is `/dev/sdb`.

### create GPT partition table and one Linux filesystem partition

```console
$ printf 'label: gpt\n, , L\n' | sudo -n sfdisk /dev/sdb
Checking that no-one is using this disk right now ... OK

Disk /dev/sdb: 2 TiB, 2199023255552 bytes, 4294967296 sectors
Disk model: QEMU HARDDISK
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes

>>> Script header accepted.
>>> Created a new GPT disklabel (GUID: 270EEF83-6C54-474C-8CBB-85D3C7446AC2).
/dev/sdb1: Created a new partition 1 of type 'Linux filesystem' and of size 2 TiB.
/dev/sdb2: Done.

New situation:
Disklabel type: gpt
Disk identifier: 270EEF83-6C54-474C-8CBB-85D3C7446AC2

Device     Start        End    Sectors Size Type
/dev/sdb1   2048 4294965247 4294963200   2T Linux filesystem

The partition table has been altered.
Calling ioctl() to re-read partition table.
Syncing disks.

[exit=0]
```

### notify kernel of partition table

```console
$ sudo -n partprobe /dev/sdb

[exit=0]
```

### udevadm settle

```console
$ sudo -n udevadm settle

[exit=0]
```

### lsblk after partition

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                      QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat              BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4              1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member       2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4              bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                      QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part

[exit=0]
```

## Format Partition

### Safety Gate: before mkfs.ext4

STOP: partition already has filesystem signature

## Conclusion

STOP

Reason for STOP: partition failed safety check immediately before mkfs.ext4

---

# M2A Data Disk Setup Resume

## Milestone

- Milestone ID: M2A actual /data setup
- Timestamp: 2026-07-02T08:36:37+00:00
- Hostname: llmserver
- User: user
- Working directory: /home/user/codex-bootstrap/mixed-memory-llm-api-server
- Branch name: milestone/m2-data-disk-setup
- Git commit hash at run start: e1dcb5085a17e22d6b31f08c2f0eeae4700ad98d
- Mode: actual
- Target disk: /dev/sdb

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

## Required Tool Check

### command -v lsblk

```console
$ command -v lsblk
/usr/bin/lsblk

[exit=0]
```

### command -v findmnt

```console
$ command -v findmnt
/usr/bin/findmnt

[exit=0]
```

### command -v blkid

```console
$ command -v blkid
/usr/sbin/blkid

[exit=0]
```

### command -v sfdisk

```console
$ command -v sfdisk
/usr/sbin/sfdisk

[exit=0]
```

### command -v partprobe

```console
$ command -v partprobe
/usr/sbin/partprobe

[exit=0]
```

### command -v mkfs.ext4

```console
$ command -v mkfs.ext4
/usr/sbin/mkfs.ext4

[exit=0]
```

### command -v systemctl

```console
$ command -v systemctl
/usr/bin/systemctl

[exit=0]
```

### command -v stat

```console
$ command -v stat
/usr/bin/stat

[exit=0]
```

### command -v awk

```console
$ command -v awk
/usr/bin/awk

[exit=0]
```

### command -v sed

```console
$ command -v sed
/usr/bin/sed

[exit=0]
```

### command -v grep

```console
$ command -v grep
/usr/bin/grep

[exit=0]
```

### command -v sudo

```console
$ command -v sudo
/usr/bin/sudo

[exit=0]
```

## Initial Read-Only Inventory

### df -hT /

```console
$ df -hT /
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /

[exit=0]
```

### findmnt /

```console
$ findmnt /
TARGET SOURCE                            FSTYPE OPTIONS
/      /dev/mapper/ubuntu--vg-ubuntu--lv ext4   rw,relatime

[exit=0]
```

### findmnt /data

```console
$ findmnt /data || true

[exit=0]
```

### ls -ld /data

```console
$ if [ -e /data ]; then ls -ld /data; else echo '/data does not exist'; fi
drwxr-xr-x 2 root root 4096 Jul  2 08:34 /data

[exit=0]
```

### sudo -n find /data -maxdepth 4 -ls

```console
$ if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo '/data does not exist'; fi
   401802      4 drwxr-xr-x   2 root     root         4096 Jul  2 08:34 /data

[exit=0]
```

### lsblk inventory before setup

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                      QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat              BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4              1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member       2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4              bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                      QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part

[exit=0]
```

### sudo -n blkid before setup

```console
$ sudo -n blkid
/dev/mapper/ubuntu--vg-ubuntu--lv: UUID="bc752bce-bb3f-4802-8adf-69c45a88689d" BLOCK_SIZE="4096" TYPE="ext4"
/dev/sda2: UUID="1e35ddc8-6f3c-4eec-9650-6ef93d252b3b" BLOCK_SIZE="4096" TYPE="ext4" PARTUUID="d7b915e9-2dcd-45c9-9726-aefaa84b03eb"
/dev/sda3: UUID="2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp" TYPE="LVM2_member" PARTUUID="a8bd8ebb-e8b5-4fca-9bfc-dade9a0d89fb"
/dev/sda1: UUID="BBE0-E924" BLOCK_SIZE="512" TYPE="vfat" PARTUUID="3cf45807-c1be-47ef-966b-fc2f51bdf10a"
/dev/sdb1: PARTUUID="b793b230-9046-4bba-9c45-f09eaf1f1378"

[exit=0]
```

### Safety Gate: actual preflight before any destructive command

- Required target: `/dev/sdb`
- Root disk: `/dev/sda`
- /boot disk: `/dev/sda`
- /boot/efi disk: `/dev/sda`

| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No filesystem signatures | No existing partitions | Not LVM | Not stack member | Safe | Reason |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/dev/sda` | 34359738368 | QEMU HARDDISK | drive-scsi0 | no | no | no | no | yes | no | no | no | no | size not approximately 2 TB; root disk, root ancestor, or protected boot ancestor; used by /boot or /boot/efi; mounted children: /boot/efi, /boot, /; existing partitions: /dev/sda1, /dev/sda2, /dev/sda3; partition filesystem signatures: /dev/sda1, /dev/sda2, /dev/sda3; LVM physical volume present; stack member/type: lvm |
| `/dev/sdb` | 2199023255552 | QEMU HARDDISK | aidata2tb | yes | yes | yes | yes | yes | no | yes | yes | no | existing partitions: /dev/sdb1; partition filesystem signatures: /dev/sdb1 |

STOP: No safe candidate disk found.

Full unpartitioned-disk setup path is not available; checking for a safe resume state.

### Safety Gate: resume preflight before formatting existing unformatted partition

This gate is only for resuming after a prior STOP where the GPT partition was created but no filesystem was written.

| Disk | Resume safe | Reason |
| --- | --- | --- |
| `/dev/sda` | no | size not approximately 2 TB; root disk, root ancestor, or protected boot ancestor; used by /boot or /boot/efi; disk or child mounted; expected exactly one partition, found 3 |
| `/dev/sdb` | yes | resume partition state is safe |

PASS: exactly one safe resume candidate exists and it is `/dev/sdb` with unformatted `/dev/sdb1`.
Resume old root-disk /data path: `/data.pre-mount-root-20260702-083425`

## Format Partition

### Safety Gate: before mkfs.ext4

PASS: `/dev/sdb1` exists, belongs to `/dev/sdb`, is unmounted, has no filesystem signature, and is not in the root/boot stack.

### format /dev/sdb1 as ext4 AI_DATA

```console
$ sudo -n mkfs.ext4 -F -L AI_DATA /dev/sdb1
mke2fs 1.47.0 (5-Feb-2023)
Discarding device blocks:         0/536870400                   done
Creating filesystem with 536870400 4k blocks and 134217728 inodes
Filesystem UUID: 8daf56f1-5649-4163-9d87-919c2d271875
Superblock backups stored on blocks:
	32768, 98304, 163840, 229376, 294912, 819200, 884736, 1605632, 2654208,
	4096000, 7962624, 11239424, 20480000, 23887872, 71663616, 78675968,
	102400000, 214990848, 512000000

Allocating group tables:     0/16384           done
Writing inode tables:     0/16384           done
Creating journal (262144 blocks): done
Writing superblocks and filesystem accounting information:     0/16384           done


[exit=0]
```

Filesystem UUID: `8daf56f1-5649-4163-9d87-919c2d271875`

## Configure fstab And Mount /data
fstab line added: `UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2`

### append /data UUID entry to /etc/fstab

```console
$ printf '%s\n' 'UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2' | sudo -n tee -a /etc/fstab >/dev/null

[exit=0]
```

### systemctl daemon-reload

```console
$ sudo -n systemctl daemon-reload

[exit=0]
```

### findmnt --verify --verbose

```console
$ sudo -n findmnt --verify --verbose

0 parse errors, 0 errors, 1 warning
/
   [ ] target exists
   [ ] source /dev/disk/by-id/dm-uuid-LVM-D0hEPqSC65yIgSwQFqIKUKgY3LkGwv8uEH507SgwjH26kwwHnX0yJk7uJ26nQV1u exists
   [ ] FS type is ext4
/boot
   [ ] target exists
   [ ] source /dev/disk/by-uuid/1e35ddc8-6f3c-4eec-9650-6ef93d252b3b exists
   [ ] FS type is ext4
/boot/efi
   [ ] target exists
   [ ] source /dev/disk/by-uuid/BBE0-E924 exists
   [ ] FS type is vfat
none
   [W] non-bind mount source /swap.img is a directory or regular file
   [ ] FS type is swap
/data
   [ ] target exists
   [ ] userspace options: nofail,x-systemd.device-timeout=30
   [ ] UUID=8daf56f1-5649-4163-9d87-919c2d271875 translated to /dev/sdb1
   [ ] source /dev/sdb1 exists
   [ ] FS type is ext4

[exit=0]
```

### mount /data from fstab

```console
$ sudo -n mount /data

[exit=0]
```

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T   28K  1.9T   1% /data

[exit=0]
```

### lsblk after mount

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### grep /data /etc/fstab

```console
$ grep -E '[[:space:]]/data[[:space:]]' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

## Directory And Permission Setup

### create ai group if missing

```console
$ getent group ai >/dev/null || sudo -n groupadd ai

[exit=0]
```

### add user to ai group

```console
$ id -nG user | tr ' ' '\n' | grep -qx ai || sudo -n usermod -aG ai user

[exit=0]
```
Note: group membership changes may require a new login or reboot to become visible in existing sessions.

### create required /data directories

```console
$ sudo -n mkdir -p /data/models /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services/secrets /data/build /data/logs /data/backups

[exit=0]
```

### set /data ownership

```console
$ sudo -n chown root:root /data

[exit=0]
```

### set /data mode

```console
$ sudo -n chmod 0755 /data

[exit=0]
```

### set user writable data ownership

```console
$ sudo -n chown -R user:ai /data/models /data/hf-cache /data/services /data/build /data/logs /data/backups

[exit=0]
```

### set setgid modes on user data directories

```console
$ sudo -n find /data/models /data/hf-cache /data/services /data/build /data/logs /data/backups -type d -exec chmod 2775 {} +

[exit=0]
```

### set secrets ownership

```console
$ sudo -n chown user:ai /data/services/secrets

[exit=0]
```

### set secrets mode

```console
$ sudo -n chmod 2770 /data/services/secrets

[exit=0]
```

### set docker ownership

```console
$ sudo -n chown root:root /data/docker

[exit=0]
```

### set docker mode

```console
$ sudo -n chmod 0711 /data/docker

[exit=0]
```

### set containerd ownership

```console
$ sudo -n chown root:root /data/containerd

[exit=0]
```

### set containerd mode

```console
$ sudo -n chmod 0711 /data/containerd

[exit=0]
```

### directory permission summary

```console
$ stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets

[exit=0]
```

## AI Data Environment

### write /etc/profile.d/ai-data-paths.sh

```console
$ sudo -n tee /etc/profile.d/ai-data-paths.sh >/dev/null <<'PROFILE_EOF'
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

[exit=0]
```

### set profile ownership

```console
$ sudo -n chown root:root /etc/profile.d/ai-data-paths.sh

[exit=0]
```

### set profile mode

```console
$ sudo -n chmod 0644 /etc/profile.d/ai-data-paths.sh

[exit=0]
```

### profile file contents

```console
$ sudo -n cat /etc/profile.d/ai-data-paths.sh
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

[exit=0]
```

## Final Setup Verification

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T   88K  1.9T   1% /data

[exit=0]
```

### lsblk final

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### fstab /data entry

```console
$ grep -E '[[:space:]]/data[[:space:]]' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

## Scope Confirmation

- Partitioned and formatted only the verified safe disk: `/dev/sdb`.
- Created partition path: `/dev/sdb1`.
- Filesystem UUID: `8daf56f1-5649-4163-9d87-919c2d271875`.
- fstab line added: `UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2`.
- Old root-disk /data path moved aside to: `/data.pre-mount-root-20260702-083425`.
- Docker was not installed or configured.
- NVIDIA drivers or toolkit were not installed or configured.
- No models were downloaded.
- No API was exposed.
- VM was not rebooted automatically.

## Conclusion

PASS

## Next Recommended Task

Reboot VM 120 only, then run M2B post-reboot verification.

## M2A Read-Only Verification

- Timestamp: 2026-07-02T08:36:48+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m2-data-disk-setup

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### fstab active /data entry

```console
$ grep -E '^[^#][[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab

[exit=1]
```

## M2A Read-Only Verification Conclusion

STOP

Reason: /etc/fstab lacks active /data UUID entry

## M2A Read-Only Verification

- Timestamp: 2026-07-02T08:37:17+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m2-data-disk-setup

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### fstab active /data entry

```console
$ grep -E '^[[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T   88K  1.9T   1% /data

[exit=0]
```

### lsblk verification

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### root and data source summary

```console
$ printf 'root=%s\ndata=%s\n' '/dev/mapper/ubuntu--vg-ubuntu--lv' '/dev/sdb1'
root=/dev/mapper/ubuntu--vg-ubuntu--lv
data=/dev/sdb1

[exit=0]
```

### directory permission verification summary

```console
$ stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets

[exit=0]
```

### AI data env vars in login shell

```console
$ bash -lc "env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort"
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg

[exit=0]
```

## M2A Read-Only Verification Conclusion

PASS

/data mount, UUID fstab entry, AI_DATA label, directory permissions, and AI/Hugging Face environment variables verified. Reboot verification is still required.


## Final Post-Run Repository Checks

- Timestamp: 2026-07-02T08:37:49+00:00
- `tests/shell/test-prepare-data-disk-static.sh`: PASS.
- `scripts/storage/prepare-data-disk.sh --dry-run`: PASS before actual setup.
- `scripts/storage/prepare-data-disk.sh --yes-format-verified-data-disk /dev/sdb`: PASS after safe resume from partition-created, unformatted state.
- `scripts/storage/verify-data-mount.sh`: PASS after verifier fstab regex correction.
- `bash -n scripts/storage/prepare-data-disk.sh`: PASS.
- `bash -n scripts/storage/verify-data-mount.sh`: PASS.
- `bash -n tests/shell/test-prepare-data-disk-static.sh`: PASS.
- `git diff --check`: PASS.
- Grep-based sensitive-value scan: PASS; matches were intentional safety wording, sanitizer patterns, test patterns, workflow references, and ignore entries only. No real secret was detected.

Earlier STOP sections in this report document safety-gate defects found during execution: the first treated GPT PARTUUID as a filesystem signature before `mkfs.ext4`, and the second used an overly strict fstab verification regex. Both were corrected before final verification. The live final state is PASS.

## Final M2A Result

PASS

VM still needs reboot verification. Next recommended task: reboot VM 120 only, then run M2B post-reboot verification.


## M2B automated reboot prepared

- Timestamp: 2026-07-02T09:15:41+00:00
- Temporary service path: `/etc/systemd/system/m2b-post-reboot-verify.service`
- Temporary runner path: `/data/services/m2b-post-reboot/m2b-post-reboot-verify.sh`
- Log path: `/data/logs/m2b-post-reboot-verify.log`
- Status path: `/data/services/m2b-post-reboot/PASS` or `/data/services/m2b-post-reboot/STOP`
- Service enabled: `m2b-post-reboot-verify.service`
- Reboot command to be run from inside the guest only: `sudo -n systemctl reboot`
- Reboot target: VM 120 guest only; no Proxmox UI action and no forced reboot.
- Docker was not installed or configured.
- NVIDIA drivers or toolkit were not installed or configured.
- No inference backends were configured.
- No models were downloaded.
- No API was exposed.

## M2A Read-Only Verification

- Timestamp: 2026-07-02T09:17:14+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m2-data-disk-setup

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### fstab active /data entry

```console
$ grep -E '^[[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  796K  1.9T   1% /data

[exit=0]
```

### lsblk verification

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### root and data source summary

```console
$ printf 'root=%s\ndata=%s\n' '/dev/mapper/ubuntu--vg-ubuntu--lv' '/dev/sdb1'
root=/dev/mapper/ubuntu--vg-ubuntu--lv
data=/dev/sdb1

[exit=0]
```

### directory permission verification summary

```console
$ stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets

[exit=0]
```

### AI data env vars in login shell

```console
$ bash -lc "env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort"
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg

[exit=0]
```

## M2A Read-Only Verification Conclusion

PASS

/data mount, UUID fstab entry, AI_DATA label, directory permissions, and AI/Hugging Face environment variables verified. Reboot verification is still required.

## M2A Read-Only Verification

- Timestamp: 2026-07-02T09:17:15+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m2-data-disk-setup

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### fstab active /data entry

```console
$ grep -E '^[[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  808K  1.9T   1% /data

[exit=0]
```

### lsblk verification

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### root and data source summary

```console
$ printf 'root=%s\ndata=%s\n' '/dev/mapper/ubuntu--vg-ubuntu--lv' '/dev/sdb1'
root=/dev/mapper/ubuntu--vg-ubuntu--lv
data=/dev/sdb1

[exit=0]
```

### directory permission verification summary

```console
$ stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets

[exit=0]
```

### AI data env vars in login shell

```console
$ bash -lc "env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort"
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg

[exit=0]
```

## M2A Read-Only Verification Conclusion

PASS

/data mount, UUID fstab entry, AI_DATA label, directory permissions, and AI/Hugging Face environment variables verified. Reboot verification is still required.

## M2B post-reboot verification

- Timestamp: 2026-07-02T09:17:15+00:00
- Hostname: llmserver
- Uptime:  09:17:15 up 0 min,  3 users,  load average: 0.19, 0.07, 0.02
- Git branch: milestone/m2-data-disk-setup
- Commit before verification: aeafb731b496ae9a6487464e9ec56a783368bccc

### findmnt /data Summary

```text
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime
```

### df -hT / /data Summary

```text
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  812K  1.9T   1% /data
```

### lsblk Summary

```text
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data
```

### fstab /data Line

```text
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2
```

### Directory And Permission Summary

```text
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets
```

### Old Root-Disk /data Backup Summary

```text
drwxr-xr-x 4 root root 4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425
   393230      4 drwxr-xr-x   4 root     root         4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425
   393231      4 drwxr-xr-x   2 root     root         4096 Jun 30 22:38 /data.pre-mount-root-20260702-083425/docker
   393262      4 drwxr-xr-x   3 root     root         4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425/services
   393263      4 drwxr-xr-x   2 root     root         4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425/services/codex-smoke-test
```

### Environment Variable Check

```text
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg
```

### Checks Before Commit

```text
bash -n scripts/storage/prepare-data-disk.sh: PASS
bash -n scripts/storage/verify-data-mount.sh: PASS
bash -n tests/shell/test-prepare-data-disk-static.sh: PASS
tests/shell/test-prepare-data-disk-static.sh: PASS
scripts/storage/verify-data-mount.sh: PASS

```

### PASS/STOP Conclusion

PASS

/data survived reboot on /dev/sdb1 with ext4 label AI_DATA and UUID 8daf56f1-5649-4163-9d87-919c2d271875. /data is separate from /. The fstab entry uses UUID= and not /dev/sdb1. Required directories, ownership, permissions, old root-disk /data backup, and AI/Hugging Face login-shell environment variables were verified.

No Docker, NVIDIA, inference backend, model download, or API exposure changes were made by this post-reboot verifier.

Next recommended milestone: M3 root-disk guard.

## M2B post-reboot verification

- Timestamp: 2026-07-02T09:17:15+00:00
- Hostname: llmserver
- Uptime:  09:17:15 up 0 min,  3 users,  load average: 0.19, 0.07, 0.02
- Git branch: milestone/m2-data-disk-setup

### PASS/STOP Conclusion

STOP

Reason: secret scan found possible real secret

No Docker, NVIDIA, model, or API configuration was intentionally changed by this post-reboot verifier.

## M2A Read-Only Verification

- Timestamp: 2026-07-02T09:17:57+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m2-data-disk-setup

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### fstab active /data entry

```console
$ grep -E '^[[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  824K  1.9T   1% /data

[exit=0]
```

### lsblk verification

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### root and data source summary

```console
$ printf 'root=%s\ndata=%s\n' '/dev/mapper/ubuntu--vg-ubuntu--lv' '/dev/sdb1'
root=/dev/mapper/ubuntu--vg-ubuntu--lv
data=/dev/sdb1

[exit=0]
```

### directory permission verification summary

```console
$ stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets

[exit=0]
```

### AI data env vars in login shell

```console
$ bash -lc "env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort"
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg

[exit=0]
```

## M2A Read-Only Verification Conclusion

PASS

/data mount, UUID fstab entry, AI_DATA label, directory permissions, and AI/Hugging Face environment variables verified. Reboot verification is still required.

## M2A Read-Only Verification

- Timestamp: 2026-07-02T09:17:57+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m2-data-disk-setup

### findmnt /data

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

[exit=0]
```

### fstab active /data entry

```console
$ grep -E '^[[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2

[exit=0]
```

### df -hT / /data

```console
$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  836K  1.9T   1% /data

[exit=0]
```

### lsblk verification

```console
$ lsblk -o NAME\,PATH\,SIZE\,TYPE\,FSTYPE\,LABEL\,UUID\,MOUNTPOINTS\,MODEL\,SERIAL
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data

[exit=0]
```

### root and data source summary

```console
$ printf 'root=%s\ndata=%s\n' '/dev/mapper/ubuntu--vg-ubuntu--lv' '/dev/sdb1'
root=/dev/mapper/ubuntu--vg-ubuntu--lv
data=/dev/sdb1

[exit=0]
```

### directory permission verification summary

```console
$ stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets

[exit=0]
```

### AI data env vars in login shell

```console
$ bash -lc "env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort"
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg

[exit=0]
```

## M2A Read-Only Verification Conclusion

PASS

/data mount, UUID fstab entry, AI_DATA label, directory permissions, and AI/Hugging Face environment variables verified. Reboot verification is still required.

## M2B post-reboot verification

- Timestamp: 2026-07-02T09:17:57+00:00
- Hostname: llmserver
- Uptime:  09:17:57 up 1 min,  3 users,  load average: 0.09, 0.06, 0.02
- Git branch: milestone/m2-data-disk-setup
- Commit before verification: aeafb731b496ae9a6487464e9ec56a783368bccc

### findmnt /data Summary

```text
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime
```

### df -hT / /data Summary

```text
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.4G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  836K  1.9T   1% /data
```

### lsblk Summary

```text
NAME                      PATH                               SIZE TYPE FSTYPE      LABEL   UUID                                   MOUNTPOINTS MODEL         SERIAL
sda                       /dev/sda                            32G disk                                                                        QEMU HARDDISK drive-scsi0
├─sda1                    /dev/sda1                            1G part vfat                BBE0-E924                              /boot/efi
├─sda2                    /dev/sda2                            2G part ext4                1e35ddc8-6f3c-4eec-9650-6ef93d252b3b   /boot
└─sda3                    /dev/sda3                         28.9G part LVM2_member         2PRJo6-giqY-jfyu-CBsX-1A7g-qwn3-6Vlfwp
  └─ubuntu--vg-ubuntu--lv /dev/mapper/ubuntu--vg-ubuntu--lv 14.5G lvm  ext4                bc752bce-bb3f-4802-8adf-69c45a88689d   /
sdb                       /dev/sdb                             2T disk                                                                        QEMU HARDDISK aidata2tb
└─sdb1                    /dev/sdb1                            2T part ext4        AI_DATA 8daf56f1-5649-4163-9d87-919c2d271875   /data
```

### fstab /data Line

```text
UUID=8daf56f1-5649-4163-9d87-919c2d271875 /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2
```

### Directory And Permission Summary

```text
drwxr-xr-x 755 root:root /data
drwxrwsr-x 2775 user:ai /data/models
drwxrwsr-x 2775 user:ai /data/hf-cache
drwxrwsr-x 2775 user:ai /data/hf-cache/hub
drwxrwsr-x 2775 user:ai /data/hf-cache/xet
drwxrwsr-x 2775 user:ai /data/hf-cache/assets
drwxrwsr-x 2775 user:ai /data/hf-cache/datasets
drwxrwsr-x 2775 user:ai /data/hf-cache/transformers
drwxrwsr-x 2775 user:ai /data/hf-cache/xdg
drwx--x--x 711 root:root /data/docker
drwx--x--x 711 root:root /data/containerd
drwxrwsr-x 2775 user:ai /data/services
drwxrwsr-x 2775 user:ai /data/build
drwxrwsr-x 2775 user:ai /data/logs
drwxrwsr-x 2775 user:ai /data/backups
drwxrws--- 2770 user:ai /data/services/secrets
```

### Old Root-Disk /data Backup Summary

```text
drwxr-xr-x 4 root root 4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425
   393230      4 drwxr-xr-x   4 root     root         4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425
   393231      4 drwxr-xr-x   2 root     root         4096 Jun 30 22:38 /data.pre-mount-root-20260702-083425/docker
   393262      4 drwxr-xr-x   3 root     root         4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425/services
   393263      4 drwxr-xr-x   2 root     root         4096 Jul  1 00:52 /data.pre-mount-root-20260702-083425/services/codex-smoke-test
```

### Environment Variable Check

```text
AI_BUILD_DIR=/data/build
AI_DATA=/data
AI_LOG_DIR=/data/logs
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg
```

### Checks Before Commit

```text
bash -n scripts/storage/prepare-data-disk.sh: PASS
bash -n scripts/storage/verify-data-mount.sh: PASS
bash -n tests/shell/test-prepare-data-disk-static.sh: PASS
tests/shell/test-prepare-data-disk-static.sh: PASS
scripts/storage/verify-data-mount.sh: PASS

```

### PASS/STOP Conclusion

PASS

/data survived reboot on /dev/sdb1 with ext4 label AI_DATA and UUID 8daf56f1-5649-4163-9d87-919c2d271875. /data is separate from /. The fstab entry uses UUID= and not /dev/sdb1. Required directories, ownership, permissions, old root-disk /data backup, and AI/Hugging Face login-shell environment variables were verified.

No Docker, NVIDIA, inference backend, model download, or API exposure changes were made by this post-reboot verifier.

Next recommended milestone: M3 root-disk guard.
