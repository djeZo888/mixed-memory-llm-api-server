# Operations

Operational procedures will be implemented in later milestones.

## Baseline Checks

- `/data` mounted after M2.
- Root-disk guard passes after M3.
- Docker storage under `/data/docker` after M4.
- `nvidia-smi` works after M5.
- GPU containers work after M6.
- API health checks work after M8.

## Logs

Service logs must live under `/data/logs` after the data disk is prepared.

## Root-Disk Guard

Run the root-disk guard before and after any operation that can write large files, including Docker installation, containerd setup, model downloads, source builds, service deployment, and benchmarks.

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
```

To write an explicit report:

```bash
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
```

The guard is read-only. It reports suspicious files, large high-risk root paths, root free-space pressure, `/data` mount problems, and Hugging Face cache environment mistakes. It does not clean or repair anything.

## Docker/containerd Storage

Before M4B actual installation, review the M4A dry-run report and confirm Docker/containerd storage will stay on `/data`.

Dry-run commands:

```bash
scripts/docker/install-docker.sh --dry-run
scripts/docker/configure-docker-data-root.sh --dry-run
scripts/docker/verify-docker-storage.sh || true
```

Actual M4B commands require explicit approval flags:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/install-docker.sh --yes-install-docker
scripts/docker/configure-docker-data-root.sh --yes-configure-docker-storage
scripts/docker/verify-docker-storage.sh
```

Do not pull images or run containers until `scripts/docker/verify-docker-storage.sh` confirms Docker Root Dir is `/data/docker` and `/var/lib/docker` plus `/var/lib/containerd` are absent, empty, small, relocated, or documented.

After M4B, `/data/docker` is Docker-managed. Its observed mode may be `0710`; that is acceptable when Docker Root Dir remains `/data/docker`, `scripts/docker/verify-docker-storage.sh` passes, and the root-disk guard passes. Do not change Docker data-root permissions merely to match the earlier M2 bootstrap placeholder policy.
