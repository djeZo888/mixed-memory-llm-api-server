# M4A Docker/containerd Storage Planning Report

- Milestone ID: M4A
- Timestamp: 2026-07-02T18:52:17+00:00
- Branch: `milestone/m4a-docker-containerd-plan`
- Current main commit: `760b0312e50dabba1b9de8f5be2a8766a604736c`
- Hostname: `llmserver`
- User: `user`

## Scope

M4A was planning and dry-run only. No packages were installed, no apt repositories were added, no package downloads were performed, no Docker/containerd config files were edited, no services were started or restarted, no users were added to groups, and no Docker images or models were downloaded.

## /data Mount Summary

```console
$ findmnt /data
TARGET SOURCE    FSTYPE OPTIONS
/data  /dev/sdb1 ext4   rw,relatime

$ df -hT / /data
Filesystem                        Type  Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4   15G  6.5G  7.1G  48% /
/dev/sdb1                         ext4  2.0T  1.4M  1.9T   1% /data
```

`/data` remains mounted on `/dev/sdb1`, ext4, separate from `/`.

## Root-Disk Guard Result

`scripts/common/require-data-mounted.sh` passed.

`scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md` passed. The generated M3 report change was restored before commit because M4A only needs to record this result here.

## Current Docker/containerd State

| Check | Result |
| --- | --- |
| `command -v docker` | not installed |
| `command -v dockerd` | not installed |
| `command -v containerd` | not installed |
| `/var/lib/docker` | absent |
| `/var/lib/containerd` | absent |

This is the expected pre-M4B state.

## Proposed Docker Install Method

Use Docker's official Ubuntu apt repository method:

1. Verify `/data` and root-disk guard.
2. Verify required base tools are available.
3. Install Docker's apt signing key from `https://download.docker.com/linux/ubuntu/gpg`.
4. Add Docker's Ubuntu apt source for the detected architecture and Ubuntu codename.
5. Install:
   - `docker-ce`
   - `docker-ce-cli`
   - `containerd.io`
   - `docker-buildx-plugin`
   - `docker-compose-plugin`

Do not use Docker shortcut installer scripts. Do not add `user` to the `docker` group by default. Do not configure GPU container runtime support in M4.

Official references checked during M4A:

- Docker Engine install on Ubuntu: <https://docs.docker.com/engine/install/ubuntu/>
- Docker daemon `data-root`: <https://docs.docker.com/reference/cli/dockerd/>
- containerd configuration: <https://github.com/containerd/containerd/blob/main/docs/man/containerd-config.toml.5.md>

## Proposed Docker Data Root

Docker Engine must use:

```json
{
  "data-root": "/data/docker"
}
```

`scripts/docker/configure-docker-data-root.sh` is designed to preserve existing valid `daemon.json` settings and add or update only `data-root`.

## Proposed Containerd Storage Plan

containerd persistent data must not remain under `/var/lib/containerd`.

Planned M4B config:

```toml
root = "/data/containerd/root"
state = "/run/containerd"
```

Snapshotter data is treated as persistent and should remain under the containerd root unless a future backend-specific policy explicitly sets a separate `/data/containerd` path. If an existing containerd config cannot be changed safely, M4B must stop and report instead of guessing.

## Tests And Checks Run

- `bash -n scripts/docker/install-docker.sh`
- `bash -n scripts/docker/configure-docker-data-root.sh`
- `bash -n scripts/docker/verify-docker-storage.sh`
- `bash -n tests/shell/test-docker-scripts-static.sh`
- `tests/shell/test-docker-scripts-static.sh`
- `scripts/common/require-data-mounted.sh`
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- `scripts/docker/install-docker.sh --dry-run`
- `scripts/docker/configure-docker-data-root.sh --dry-run`
- `scripts/docker/verify-docker-storage.sh || true`
- `git diff --check`
- grep-based secret scan

`scripts/docker/verify-docker-storage.sh` returned STOP because Docker is not installed yet. That is expected and acceptable for M4A.

## Secret Scan Result

The grep-based secret scan found only intentional documentation, static-test, sanitizer, `.gitignore`, CI, and prior report command strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.

## PASS/STOP

PASS

## Next Recommended Task

M4B actual Docker/containerd installation after human review.
