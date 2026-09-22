# ai-harness v0.0.1 deployment

This directory implements the bounded deployment portion of plan0355d6d.
The host is `user@10.156.100.61`; the server and gateway run as that existing
ordinary user. nginx alone listens on private `10.156.100.61:80`, forwarding
to `127.0.0.1:8080`. No model lifecycle changes or ai-vm mutation are part of
these scripts. Server and web source remain separately owned.

## Privileged bootstrap

Review `bootstrap-host.sh`, `nginx/ai-harness.conf` and their exact
`bootstrap.SHA256SUMS` before an operator runs them. Keep the script, manifest
and nginx subdirectory together. Root must authorize a new versioned staging
directory after exact review. The former `/home/user/ai-harness-bootstrap`
is retired: do not run, modify or reuse it. The task result records frozen
source hashes; no new staging is authorized by this README.

```sh
cd /ABS/ROOT-REVIEWED-VERSIONED-STAGING
sha256sum -c bootstrap.SHA256SUMS
sudo ./bootstrap-host.sh --dry-run
sudo ./bootstrap-host.sh
```

The script requires Ubuntu24.04, existing UID/GID1000 `user`, the inspected
subuid/subgid allocation and the private address. It installs only the requested
Podman/uidmap/slirp4netns/fuse-overlayfs/nginx package set and dependencies,
enables user linger, validates nginx configuration, then starts/reloads nginx.
It preserves subordinate IDs, SSH configuration, users and sudoers. It makes no
AppArmor/sysctl relaxation and requests no reboot. AppArmor's global userns
restriction remains enabled; the on-disk vendor Podman profile permits userns,
but actual rootless capability must be checked after package installation.

Before package installation it checks for unexpected nginx configuration. The
main/default files must match installed `nginx-common` conffile checksums;
other enabled sites or conf.d entries cause an explicit abort. The only
unrelated site it may disable is the enabled distro-stock default. Both that
link and its target content are preserved in a printed
`/var/backups/ai-harness-bootstrap.*` directory. It never edits the default
site content. Existing harness configuration must exactly match the reviewed
asset for an idempotent rerun; an upgrade requires fresh review.

A temporary service-start policy suppresses nginx package auto-start while
preserving/chaining any existing regular policy file and restoring it on exit.
This prevents a newly installed default wildcard listener. If nginx validation
fails, the prior default enabled link is restored without requesting service
start/reload. Completed package operations are not automatically undone.

The proxy permits a **50MiB HTTP request body**, disables response buffering for
SSE, and uses7200-second read/write inactivity timeouts. The server enforces the
separate two-hour active-generation deadline. A502 before server deployment is
expected. The published plan uses no-login LAN access; this bootstrap does not
change the user's network/firewall policy or configure TLS.

For operator rollback, disable the harness link/service as appropriate and
restore the preserved default link only after reviewing its wildcard exposure.
Always run `nginx -t` before reload. No global package removal, pruning, sudoers
change or automatic reboot is included.

## Ordinary-user runtime and image

See [RUNTIME.md](RUNTIME.md) for the checksum-verified official Node24 prefix,
server launcher and systemd user-unit template. The service uses an explicit
Node PATH and supplies only the protected inference-key **path** to the backend.
Do not put upstream or lifecycle keys in the container/profile/build context.
The backend creates short-lived inference-only runner tokens.

After rootless Podman is available and reviewed sources are staged, build once
as `user` from this directory:

```sh
podman build --file Containerfile \
  --tag localhost/ai-harness-engine:0.0.1-ae65651df5f9 .
podman image inspect localhost/ai-harness-engine:0.0.1-ae65651df5f9
```

Retain the resulting image ID and build log outside Git. The Containerfile
builds exact MiniMax source rather than copying a vendor tree into this repo;
see [engine/README.md](engine/README.md) for source/artifact pins and limitations.
Use the deployment directory alone as build context, with no host secrets.
No automatic build or pull occurs inside `run-engine.sh`.

The backend invokes:

```sh
./run-engine.sh --profile-dir /ABS/session/profile --workspace /ABS/workspace
```

It supplies `AI_HARNESS_GATEWAY_TOKEN` (ephemeral inference-only),
`AI_HARNESS_SESSION_ID` and optionally the single reviewed
`AI_HARNESS_GATEWAY_URL=http://10.0.2.2:8081/v1`. Do not put a token literal in a
command/history or unit. Container HOME is profile/home; only that session
profile and workspace are mounted, at their original absolute paths. No host
SSH/Codex directories, service data root, credentials or management sockets are
mounted. Optional reviewed skills/tools integration remains with the tools task;
the initial launcher has no arbitrary extra-mount escape hatch.

The launcher uses `slirp4netns:allow_host_loopback=true` to reach the host gateway
at127.0.0.1:8081 through10.0.2.2:8081 without publishing the gateway. It clears
ambient environment, confirms local rootless Podman, verifies the image revision
and patchset label and resolves the image to an immutable local ID. All main/light/summarizer
generation uses logical `qwen3.8-27b` through the same gateway, with explicit
480000 context and65536 maximum output in the generated custom provider.

The recorded source patches cover151-minute request timeouts (including direct
auxiliary calls) and real ACP compaction lifecycle notifications. Smaller native
title output-token budgets remain unchanged. The profile enables native image
input following root's separate inference gate; image-file handling through the
deployed application still needs acceptance. `patches/identity.json` records
both original and resulting source hashes. The Containerfile checks upstream
HEAD, patch bytes and source bytes before building.

The host Python3 supervisor redacts the ephemeral token, including split chunks
and JSON escaping, from both stdout and stderr. It uses an exact random container
name for bounded cleanup on exit/TERM; failed or unconfirmed cleanup returns125.
Nonsecret ACP bytes are preserved. Root must allow at least40 seconds after TERM
before forcibly killing this supervisor. The inspected SERVER implementation's
five-second escalation must be aligned before activation. The user systemd
template already allows150 seconds. SIGKILL or a host crash cannot establish
container settlement; retain SERVER workspace quarantine in that case.

## Verification boundary

Worker1 runs shell syntax/ShellCheck, mocked launcher/profile checks and pin
checks. These do not establish a built image, actual rootless networking,
Chromium sandbox, live ACP, inference, SSE or service/reboot acceptance.

After bootstrap/build, acceptance must run a nonroot browser and confirm its
sandbox works with the actual host AppArmor/userns and container security
settings. Never add `--no-sandbox`, `--privileged`, host networking, a management
socket or a global userns-disable workaround. Report the actual denial if the
reviewed default security settings block nested Chromium. Also verify the
gateway from the actual rootless namespace with an ephemeral token, while the
host gateway remains loopback-only. Tool/search/PDF integration and full user
flows depend on their separately owned source and bounded live acceptance.
