# Testing

## Policy

Every script or config must have tests or documented verification commands.

## Shell Scripts

Shell scripts must use `set -euo pipefail`, support `--help`, and destructive scripts must support `--dry-run`.

## Storage Tests

Later storage tests must verify `/data` survives reboot, is mounted by UUID, is a different filesystem than root, and large AI data is not on root.

## Docker Tests

Later Docker tests must verify Docker Root Dir is `/data/docker`, root Docker/containerd directories are absent, empty, small, relocated, or documented, and `hello-world` works.

## GPU Tests

Later GPU tests must verify host `nvidia-smi` and GPU access inside Docker containers.

## API Tests

Later API tests must cover auth failures, auth success, non-streaming chat, streaming chat, invalid model names, `health/live`, and `health/ready`.
