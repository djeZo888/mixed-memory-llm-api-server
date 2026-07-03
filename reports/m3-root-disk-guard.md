# M3 Root-Disk Guard Report

- Milestone ID: M3
- Timestamp: 2026-07-03T17:15:35+00:00
- Hostname: llmserver
- User: user
- Branch: main
- Commit before work: 1037886799211e311325173217fbbdeb3545ec00
- Root path inspected: `/`
- Data path checked/excluded: `/data`
- Sudo coverage: sudo -n available for read-only inspection
- Confirmation: no cleanup or destructive changes were made.
- Confirmation: no Docker, NVIDIA, model, inference backend, systemd service, or API changes were made.

### findmnt root summary

```console
$ findmnt /
TARGET SOURCE                            FSTYPE OPTIONS
/      /dev/mapper/ubuntu--vg-ubuntu--lv ext4   rw,relatime

[exit=0]
```

### findmnt /data summary

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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  9.0G  4.5G  67% /
/dev/sdb1                         ext4  2.0T  689M  1.9T   1% /data

[exit=0]
```

### AI/Hugging Face env vars

```console
$ bash -lc env\ \|\ grep\ -E\ \'\^\(AI_DATA\|HF_HOME\|HF_HUB_CACHE\|HF_XET_CACHE\|HF_ASSETS_CACHE\|HF_DATASETS_CACHE\|TRANSFORMERS_CACHE\|XDG_CACHE_HOME\|AI_BUILD_DIR\|AI_LOG_DIR\)=\'\ \|\ sort
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

## Mount Summary

| Path | Source | Fstype | Label | UUID/identity | Free GiB |
| --- | --- | --- | --- | --- | --- |
| `/` | `/dev/mapper/ubuntu--vg-ubuntu--lv` | `ext4` | n/a | device id `785818` | 4 |
| `/data` | `/dev/sdb1` | `ext4` | `AI_DATA` | `8daf56f1-5649-4163-9d87-919c2d271875` | 1912 |

## Root Free Space Thresholds

- Minimum root free space: 4 GiB
- Warning root free space: 6 GiB
- High-risk path warning: 512 MiB
- High-risk path failure: 2048 MiB
- Suspicious large file failure: 128 MiB

## /data Identity Check

`/data` is mounted and has a different filesystem identity from `/`.

## /data Required Directory Check

Required `/data` directories were checked by `require-data-mounted.sh`.

## Hugging Face Environment Check

AI and Hugging Face environment variables were checked in a fresh login shell.

## Inspected High-Risk Root Paths

| Path | Exists | MiB | Status | Note |
| --- | --- | ---: | --- | --- |
| `/var/lib/docker` | no | 0 | PASS | absent |
| `/var/lib/containerd` | no | 0 | PASS | absent |
| `/var/lib/containers` | no | 0 | PASS | absent |
| `/root/.cache` | no | 0 | PASS | absent |
| `/root/.cache/huggingface` | no | 0 | PASS | absent |
| `/root/.cache/torch` | no | 0 | PASS | absent |
| `/root/.cache/pip` | no | 0 | PASS | absent |
| `/home/user/.cache` | yes | 1 | PASS | below warning threshold |
| `/home/user/.cache/huggingface` | no | 0 | PASS | absent |
| `/home/user/.cache/torch` | no | 0 | PASS | absent |
| `/home/user/.cache/pip` | no | 0 | PASS | absent |
| `/home/user/.cache/pypoetry` | no | 0 | PASS | absent |
| `/home/user/.cache/uv` | no | 0 | PASS | absent |
| `/home/user/.cache/nvidia` | no | 0 | PASS | absent |
| `/home/user/codex-bootstrap` | yes | 2 | WARN | expected old bootstrap repo; small |
| `/tmp` | yes | 1 | PASS | below warning threshold |
| `/var/tmp` | yes | 1 | PASS | below warning threshold |
| `/var/log` | yes | 258 | PASS | below warning threshold |
| `/opt` | yes | 1 | PASS | below warning threshold |
| `/srv` | yes | 1 | PASS | below warning threshold |
| `/models` | no | 0 | PASS | absent |
| `/hf-cache` | no | 0 | PASS | absent |
| `/docker` | no | 0 | PASS | absent |
| `/containerd` | no | 0 | PASS | absent |
| `/build` | no | 0 | PASS | absent |
| `/logs` | no | 0 | PASS | absent |
| `/data.pre-mount-root-20260702-083425` | yes | 1 | WARN | expected M2 backup and below warning threshold |

## Suspicious Large File Scan

| Path | MiB | Status | Category |
| --- | ---: | --- | --- |
| none | 0 | PASS | no suspicious large model/cache/archive files found on root |

## Secret-Looking Filename Scan

| Path | Status | Category |
| --- | --- | --- |
| none | PASS | no secret-looking filenames found in scanned root paths |

## WARN Entries

- /home/user/codex-bootstrap exists and is small
- /data.pre-mount-root-20260702-083425 exists and is small
- root free space is 4 GiB, below warning threshold 6 GiB

## STOP Entries

- None.

## Tests And Checks Run

- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- Additional milestone checks are appended after command execution.

## Conclusion

PASS

## Next Recommended Milestone

M4 Docker/containerd storage.
