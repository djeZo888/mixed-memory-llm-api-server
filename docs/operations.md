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
