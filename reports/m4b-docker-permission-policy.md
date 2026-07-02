# M4B Docker Permission Policy

- Timestamp: 2026-07-02T20:18:15+00:00
- Branch: milestone/m4b-docker-containerd-install
- Base commit before policy fix: 9f046a8e30129ccd3ef39810db772f968f234378

## Previous STOP Reason

The M4B merge readiness run stopped because `scripts/storage/verify-data-mount.sh` still enforced the original M2 bootstrap placeholder mode for `/data/docker`. After Docker installation, Docker owns and manages its data-root and changed `/data/docker` to mode `0710`.

## Policy Decision

`/data/docker` mode `0710` is acceptable after M4B when all of these are true:

- Docker Root Dir is `/data/docker`.
- `scripts/docker/verify-docker-storage.sh` passes.
- `scripts/common/root-disk-guard.sh` passes.
- The Docker data-root is root-owned and is not group-writable or world-writable.

The verifier now distinguishes the M2 pre-Docker placeholder policy from the post-M4 Docker/containerd daemon-managed policy.

## Live Permission State

```text
710 root:root /data/docker
711 root:root /data/containerd
700 root:root /data/containerd/root
```

## Docker And Containerd State

- Docker Root Dir: `/data/docker`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- `/data/docker` size: `236K`
- `/data/containerd` size: `336K`
- `/data/containerd/root` size: `332K`
- `/var/lib/docker`: absent
- `/var/lib/containerd`: absent

## Verification Results

- `scripts/storage/verify-data-mount.sh`: PASS
- `scripts/docker/verify-docker-storage.sh`: PASS
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS
- Docker `hello-world`: PASS

## Tests And Checks Run

- `bash -n scripts/storage/prepare-data-disk.sh`
- `bash -n scripts/storage/verify-data-mount.sh`
- `bash -n tests/shell/test-prepare-data-disk-static.sh`
- `bash -n tests/shell/test-storage-verifier-docker-permissions.sh`
- `tests/shell/test-prepare-data-disk-static.sh`
- `tests/shell/test-storage-verifier-docker-permissions.sh`
- `scripts/storage/verify-data-mount.sh`
- `scripts/common/require-data-mounted.sh`
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- `scripts/docker/verify-docker-storage.sh`
- `sudo -n docker info`
- `sudo -n docker version`
- `sudo -n docker compose version`
- `sudo -n docker buildx version`
- `sudo -n docker run --rm hello-world`
- `sudo -n docker system df`
- `sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true`
- `git diff --check`
- Grep-based secret scan

## Secret Scan Result

The grep-based secret scan matched only intentional documentation, sanitizer, static-test, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.

## Safety Confirmation

No `chmod`, `chown`, package install, Docker/containerd restart, Docker/containerd reconfiguration, NVIDIA/CUDA work, model download, inference backend work, or API exposure was performed for this policy fix.

## Conclusion

PASS. The storage verifier now accepts restrictive Docker/containerd daemon-managed permissions after M4B while preserving strict mount, UUID, label, base directory, and user-writable AI directory checks.

## Next Recommended Task

Retry the M4B merge into `main`.
