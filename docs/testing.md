# Testing

## Policy

Every script or config must have tests or documented verification commands.

## Shell Scripts

Shell scripts must use `set -euo pipefail`, support `--help`, and destructive scripts must support `--dry-run`.

## Storage Tests

Later storage tests must verify `/data` survives reboot, is mounted by UUID, is a different filesystem than root, and large AI data is not on root.

## Root-Disk Guard Tests

M3 adds static and fixture tests for `scripts/common/require-data-mounted.sh` and `scripts/common/root-disk-guard.sh`.

Run:

```bash
bash -n scripts/common/require-data-mounted.sh
bash -n scripts/common/root-disk-guard.sh
bash -n tests/shell/test-root-disk-guard-static.sh
bash -n tests/shell/test-root-disk-guard-fixtures.sh
tests/shell/test-root-disk-guard-static.sh
tests/shell/test-root-disk-guard-fixtures.sh
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
```

The fixture test builds fake roots under `tests/fixtures` and must not touch real `/`, real `/data`, `/etc/fstab`, Docker, NVIDIA, or model directories.

## Docker Tests

Later Docker tests must verify Docker Root Dir is `/data/docker`, root Docker/containerd directories are absent, empty, small, relocated, or documented, and `hello-world` works.

M4A adds static tests for Docker/containerd planning scripts:

```bash
bash -n scripts/docker/install-docker.sh
bash -n scripts/docker/configure-docker-data-root.sh
bash -n scripts/docker/verify-docker-storage.sh
bash -n tests/shell/test-docker-scripts-static.sh
tests/shell/test-docker-scripts-static.sh
scripts/docker/install-docker.sh --dry-run
scripts/docker/configure-docker-data-root.sh --dry-run
scripts/docker/verify-docker-storage.sh || true
```

`hello-world` is reserved for M4B after Docker Root Dir is verified as `/data/docker`.

## GPU Tests

Later GPU tests must verify host `nvidia-smi` and GPU access inside Docker containers.

## API Tests

Later API tests must cover auth failures, auth success, non-streaming chat, streaming chat, invalid model names, `health/live`, and `health/ready`.
