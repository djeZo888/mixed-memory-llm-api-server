# Private rootless SearXNG service

This directory owns only the separate private SearXNG service. First-party
helpers/configuration are MIT; SearXNG remains AGPL-3.0-or-later, with its
verbatim license and exact upstream source reference in `NOTICE.md`.
`image-pin.json` records the reviewed official OCI index, amd64 manifest,
configuration digest and source revision. The derived Containerfile preserves
that pin and bakes the unchanged reviewed settings plus license/notice/pin.
There are no host configuration or workspace bind mounts.

## Deployment

Run on ai-harness as the existing rootless Podman user, with bash, Python3,
Podman, systemd user manager, sha256sum and ss already available:

```sh
podman pull ghcr.io/searxng/searxng@sha256:1ef964f6dcc811a60e01049717b6e526b25a1c52935350143f04e0ae291b3dbd
./deploy.sh --dry-run
./deploy.sh
```

The dry run validates ownership/conflicts and prints exact paths without making
changes. No sudo, accounts, host packages, app/engine edits, reverse proxy, or
host bind mounts are used. The service uses existing user-manager linger for
boot persistence; the script never changes it. Deployment enables only
`ai-harness-searxng.service`. Start is asynchronous: an active unit is not by
itself API readiness.

The script retains a 0600 secret in `~/.config/ai-harness-searxng/service.env`
under a 0700 directory. It creates a content-addressed release under
`~/.ai-harness-searxng/releases/` with an owned `current` symlink. This avoids
requiring changes to shared `~/.local` ancestry. Source files are read-only;
launcher scripts/directories are owner-executable. `SHA256SUMS` validates the
installed release on start/stop and `image.id` pins runtime to the derived local
image ID. The tag is SHA256 of the ordered source-file checksum list. The build
uses an isolated context containing only five needed image inputs, no build
network, and timestamp zero. This is service-scoped reproducibility, not a host
installer; exact bytes/image identities are recorded in deployment evidence.

Deployment is idempotent for identical source content. Unowned names/paths,
unsafe ancestors, listener conflicts, incomplete releases, checksum mismatches,
and a different existing current release fail closed. No replacement, forced
container removal, cache pruning or secret rotation is automatic. A stopped
owned container left after an abnormal Podman failure also prevents restart;
inspect ownership/image before a separately reviewed recovery. A new source
release requires stopping this service and explicitly migrating the verified
`current` symlink; retain old releases as evidence. The helper intentionally does
not automate upgrades or rollback.

## Runtime and transport

The container uses read-only root (automatic writable tmpfs disabled), ignored
upstream image volumes, UID:GID 977:977, no capabilities, no new privileges,
64 MiB tmpfs each for `/tmp` and `/var/cache/searxng`, 1 GiB memory, two CPUs,
and 256 PIDs. Podman 4.9 uses `--mount type=tmpfs,...,U=true` to give tmpfs
ownership to the specified container user. No host content is chowned.
Only IPv4 **127.0.0.1:8082:8080** is published. In-container `GRANIAN_HOST=0.0.0.0`
overrides upstream IPv6. No port 80, public interface or reverse proxy is used.

SearXNG's own rootless network disallows host-loopback access. The independently
owned engine uses its reviewed `slirp4netns:allow_host_loopback=true` route and
literal MCP environment endpoint **`http://10.0.2.2:8082`**. See `../search/README.md`
for the unchanged stdio adapter and profile `mcp.json` contract. No engine changes
are part of this service. A worker may temporarily forward its localhost port
through SSH for adapter acceptance, then close that forward.

JSON is the only enabled search-result format, although other local service
routes exist behind loopback. The small configuration disables the limiter and
needs no Valkey. Public engines can time out or rate limit; successful local HTTP
or MCP transport does not establish complete search coverage. Never represent
fixtures or empty results as live search success.

## Operation and verification

```sh
systemctl --user status ai-harness-searxng.service --no-pager
systemctl --user restart ai-harness-searxng.service
~/.ai-harness-searxng/current/run.sh stop --dry-run
curl --max-time 15 --get http://127.0.0.1:8082/search \
  --data-urlencode 'q=site:docs.python.org asyncio' --data 'format=json'
```

`run.sh check` validates release/image ownership, not readiness. Container name
and image identity must match before stop. Stop removes only that exact stopped
container ID without force, completing cleanup before systemd restarts it. `stop --dry-run` validates without
stopping. The unit reads EnvironmentFile; Podman receives `--env SEARXNG_SECRET`
by name only. The secret is never in argv/source/image and survives restart.
Do not dump container environments or the EnvironmentFile; inspect selected
non-secret fields instead.

Focused checks: `bash -n run.sh deploy.sh`, both `--help` paths, deployment dry
run, `systemd-analyze --user verify` (performed during deployment), actual IPv4
listener, selected container controls, writable owned tmpfs/read-only root,
bounded real JSON plus unchanged MCP adapter queries, and service restart with
secret identity compared privately. Source checks are not live acceptance.
The task evidence records outcomes, errors and limits.
