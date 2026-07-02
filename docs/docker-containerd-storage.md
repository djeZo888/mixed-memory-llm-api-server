# Docker And Containerd Storage

M4 moves container storage planning behind the `/data` and root-disk guard policy. Docker defaults are unsafe on this VM because the root filesystem is about 15 GiB. Docker images, build cache, container writable layers, volumes, logs, and containerd snapshots can fill that disk quickly.

## Policy

- Docker persistent data-root must be `/data/docker`.
- containerd persistent root must be under `/data/containerd`.
- Docker and containerd storage must not use `/var/lib/docker` or `/var/lib/containerd` for nontrivial persistent data.
- M3 guards must pass before and after Docker/containerd installation or configuration.
- Do not pull images or run containers until storage verification passes.

## Docker Data Root

Docker Engine defaults to `/var/lib/docker`. M4B must configure `/etc/docker/daemon.json` with:

```json
{
  "data-root": "/data/docker"
}
```

If `daemon.json` already exists, valid existing settings must be preserved and only `data-root` should be added or updated.

## Containerd Root And Snapshotter Data

containerd defaults persistent state under `/var/lib/containerd`. M4B must either configure containerd persistent root under `/data/containerd` or stop with a written reason if the existing config cannot be changed safely.

The planned M4B policy is:

```toml
root = "/data/containerd/root"
state = "/run/containerd"
```

Snapshotter data is treated as persistent and should remain under the containerd root unless a future backend-specific policy explicitly sets a separate `/data/containerd` path.

## Separate Paths

`/data/docker` and `/data/containerd` are separate so Docker Engine data, Docker-managed volumes, and containerd runtime/snapshotter state can be inspected independently. This makes future root-disk guard failures easier to diagnose and avoids hiding containerd growth inside Docker-only reports.

## Docker Group

Users are not added to the `docker` group by default. Membership in that group is effectively root-equivalent on the host. Operators should use `sudo -n docker ...` until a later security milestone explicitly approves a different access model.

## Docker-managed Permissions After Installation

M2 creates `/data/docker` and `/data/containerd` as bootstrap placeholders before Docker and containerd are installed. Those initial permissions are intentionally simple so later milestones can prove the paths exist on `/data`.

After M4B, Docker and containerd own and manage these storage trees. The daemons may tighten permissions under their data roots. `/data/docker` mode `0710` is acceptable when Docker Root Dir is `/data/docker` and Docker storage verification passes.

Do not recursively `chmod` Docker's data-root. Do not change Docker data-root permissions just to match older M2 bootstrap expectations. Post-M4 verification is based on `scripts/docker/verify-docker-storage.sh` and `scripts/common/root-disk-guard.sh`, not on forcing daemon-managed paths back to placeholder modes.

## M4A Versus M4B

M4A is planning and dry-run only. It creates scripts, static tests, documentation, and reports. It does not install packages, add apt repositories, edit `/etc/docker/daemon.json`, edit `/etc/containerd/config.toml`, restart services, pull images, run containers, or change group membership.

M4B is the reviewed actual install/configuration milestone. It must run the same scripts with explicit approval flags:

```bash
scripts/docker/install-docker.sh --yes-install-docker
scripts/docker/configure-docker-data-root.sh --yes-configure-docker-storage
scripts/docker/verify-docker-storage.sh
```

## Verification Commands

Dry-run and planning:

```bash
scripts/docker/install-docker.sh --dry-run
scripts/docker/configure-docker-data-root.sh --dry-run
scripts/docker/verify-docker-storage.sh || true
```

Post-install verification in M4B:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
sudo -n docker version
sudo -n docker info
sudo -n docker compose version
```

`hello-world` is intentionally reserved for M4B after storage configuration is verified.
