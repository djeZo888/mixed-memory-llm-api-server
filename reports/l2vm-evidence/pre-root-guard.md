# M3 Root-Disk Guard Report

- Milestone ID: M3
- Timestamp: 2026-09-15T03:00:07+00:00
- Hostname: llmserver
- User: root
- Branch: unknown
- Commit before work: unknown
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
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  8.6G  4.9G  64% /
/dev/sdb1                         ext4  2.0T  664G  1.3T  35% /data

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
