# Root-Disk Guard

The root-disk guard prevents large AI-server data from filling the small root filesystem. This VM uses `/data` for model weights, Hugging Face caches, Docker layers, containerd snapshots, build trees, service data, logs, backups, and secrets after M2.

## Why /data Must Be Mounted

Heavy work is allowed only after `/data` is mounted, separate from `/`, and has the expected `AI_DATA` filesystem identity. If `/data` is missing or only a normal root-disk directory, downloads and builds can silently fill the root filesystem.

Run this first:

```bash
scripts/common/require-data-mounted.sh
```

## Same-Filesystem Scans

`scripts/common/root-disk-guard.sh` scans root with `find -xdev` and same-filesystem sizing. This prevents the guard from descending into `/data` or other mounted filesystems while still detecting large model, cache, archive, Docker, containerd, build, log, and service paths on `/`.

The guard is read-only. It reports problems but does not delete, move, clean, mount, unmount, or reconfigure anything.

## High-Risk Paths

The guard checks paths that commonly accumulate AI-server data on root:

- `/var/lib/docker`
- `/var/lib/containerd`
- `/var/lib/containers`
- `/root/.cache`
- `/home/user/.cache`
- `/home/user/.cache/huggingface`
- `/home/user/.cache/torch`
- `/home/user/.cache/pip`
- `/home/user/.cache/pypoetry`
- `/home/user/.cache/uv`
- `/home/user/.cache/nvidia`
- `/home/user/codex-bootstrap`
- `/tmp`
- `/var/tmp`
- `/var/log`
- `/opt`
- `/srv`
- root-level `/models`, `/hf-cache`, `/docker`, `/containerd`, `/build`, and `/logs`
- `/data.pre-mount-root-*` backups from M2

Small repo files, documentation, reports, test fixtures, and the expected small M2 backup are not automatic failures.

## Thresholds

Default live thresholds:

```bash
scripts/common/root-disk-guard.sh \
  --min-root-free-gib 4 \
  --warn-root-free-gib 6 \
  --warn-path-mib 512 \
  --fail-path-mib 2048 \
  --large-file-mib 128
```

The guard stops when root free space is below the minimum, a high-risk root path exceeds the failure threshold, a suspicious model/archive file exceeds the large-file threshold, `/data` is not mounted, or `/data` is the same filesystem as `/`.

## When To Run

Future milestones must run both guards before and after any work that can write large files:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
```

Run them:

- Before and after Docker installation.
- Before and after containerd setup.
- Before model downloads.
- Before source builds or container builds.
- Before service deployment.
- Before benchmarks.
- Before enabling logs for long-running services.

Stop the milestone if either guard fails. If the guard reports warnings, document the warning and decide whether it is acceptable before continuing.

## Fixture Mode

Tests can run the guard against fake roots:

```bash
scripts/common/root-disk-guard.sh \
  --root-path /path/to/fake-root \
  --data-path /path/to/fake-root/data \
  --skip-mount-check-for-tests \
  --no-sudo
```

Fixture mode is only for tests. Live milestones must not skip mount checks.

