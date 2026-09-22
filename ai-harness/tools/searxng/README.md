# Private SearXNG proposal for PREP

Source/configuration proposal only. PREP owns image composition, rootless service
lifecycle and acceptance. `image-pin.json` is the immutable upstream OCI index
verified directly from official GHCR; raw index/architecture/config bytes and
verification script are in the task evidence directory. `settings.yml` was
checked against the exact upstream settings loader and engine names.

Bake `settings.yml` into a derived image at `/etc/searxng/settings.yml` and retain
`LICENSE-AGPL-3.0.txt` plus `NOTICE.md`. PREP's agreed build context is
`ai-harness/`, so use source paths under `tools/searxng/`:

```dockerfile
FROM ghcr.io/searxng/searxng@sha256:1ef964f6dcc811a60e01049717b6e526b25a1c52935350143f04e0ae291b3dbd
COPY --chown=977:977 tools/searxng/settings.yml /etc/searxng/settings.yml
COPY tools/searxng/LICENSE-AGPL-3.0.txt tools/searxng/NOTICE.md /usr/local/share/doc/searxng/
```

This is a source fragment for PREP's separately owned Containerfile, not a service
start. No host configuration/workspace mount is needed. The upstream image declares two volumes; use Podman's
`--image-volume=ignore` so it does not create implicit anonymous volumes. Supply
an ephemeral tmpfs for `/var/cache/searxng` and `/tmp`. Exact ready-to-copy build
and runtime fragments are in `evidence/DEPENDENCY-CONTRACT.md` in the handoff.

Run the separate service with container UID:GID `977:977` (upstream source
`container/dist.dockerfile`), read-only root, dropped capabilities, and no new
privileges. Override upstream `GRANIAN_HOST=::` with `GRANIAN_HOST=0.0.0.0` for
in-container IPv4. Only publish **127.0.0.1:8082:8080**, never wildcard/IPv6/host
port80. There is no public search UI or reverse proxy. JSON is the only enabled
search result format; other local SearXNG routes still exist behind loopback.

`SEARXNG_SECRET` is a required protected service environment value, generated and
managed by PREP at deployment time. The committed empty sentinel is not a usable
secret; do not put a real secret in the image/source, logs, argv or reports.
No Valkey is needed for this small private configuration with limiter disabled.

The adapter receives `AI_HARNESS_SEARXNG_URL=http://10.0.2.2:8082`; this candidate
route requires PREP's existing rootless slirp4netns host-loopback arrangement.
Render the chosen literal endpoint into the adapter's `env` entry in
`${MINIMAX_DATA_DIR}/mcp.json` (profile filename has no leading dot), using the
fragment in `../search/README.md`. Pinned profile configuration does not expand
`${VAR}` strings; the separate workspace `.mcp.json` loader does. The deployment
profile must not copy the workspace-only interpolation example unchanged.
The search adapter fixes the configured endpoint at startup and never accepts
an endpoint in a query. No service was started, no image layers were pulled, and
no actual search was performed during this source task. Linux execution,
rootless transport and real engine results remain NOT_TESTED.
