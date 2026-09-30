#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo 'Usage: run.sh {run|stop|check} [--dry-run]'
  echo 'Private rootless SearXNG only. Uses this release/image.id and SHA256SUMS.'
  echo 'run requires SEARXNG_SECRET from the protected systemd EnvironmentFile.'
  exit 0
fi
fail() { printf '%s\n' "$1" >&2; exit 1; }
action=${1:-}; dry=${2:-}
[[ $# -ge 1 && $# -le 2 && ( -z $dry || $dry == --dry-run ) ]] || fail 'Use --help.'
[[ $action == run || $action == stop || $action == check ]] || fail 'Use --help.'
[[ $(id -u) != 0 ]] || fail 'Refusing root: use the existing service user.'
release=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$release"
[[ -f SHA256SUMS && ! -L SHA256SUMS && -f image.id && ! -L image.id ]] || fail 'Missing release receipt.'
# Releases are owner-readable/executable only, never group/other writable.
[[ $(stat -c %u "$release") == "$(id -u)" ]] || fail 'Wrong release owner.'
[[ -z $(find "$release" \( -type l -o -perm /022 -o ! -user "$(id -un)" \) -print -quit) ]] || fail 'Unsafe release ownership, permissions, or symlink.'
sha256sum --check --status SHA256SUMS || fail 'Release checksum mismatch.'
image=$(cat image.id)
[[ $image =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'Invalid image ID receipt.'
[[ $(podman info --format '{{.Host.Security.Rootless}}') == true ]] || fail 'Rootless Podman required.'
[[ $(podman image inspect "$image" --format '{{index .Labels "io.ai-harness.service"}}') == searxng ]] || fail 'Wrong image ownership label.'
name=ai-harness-searxng
if podman container exists "$name"; then
  container_id=$(podman inspect "$name" --format '{{.Id}}')
  [[ $container_id =~ ^[a-f0-9]{64}$ ]] || fail 'Invalid container identity.'
  [[ $(podman inspect "$container_id" --format '{{index .Config.Labels "io.ai-harness.service"}}') == searxng ]] || fail 'Unowned container name conflict.'
  [[ $(podman inspect "$container_id" --format '{{.Image}}') == "${image#sha256:}" ]] || fail 'Container image differs from release; refusing mutation.'
  if [[ $action == run ]]; then fail 'Container already exists; inspect it before restarting.'; fi
  if [[ $action == stop ]]; then
    if [[ $dry != --dry-run ]]; then
      podman stop --time 15 "$container_id" >/dev/null
      # Complete cleanup before systemd terminates foreground Podman. No force;
      # exact verified ID only, and --ignore tolerates --rm winning the race.
      podman rm --ignore "$container_id" >/dev/null
    fi
  fi
elif [[ $action == run ]]; then
  [[ ${SEARXNG_SECRET:-} =~ ^[a-f0-9]{64}$ ]] || fail 'Missing/invalid protected SEARXNG_SECRET.'
  if [[ -n $(ss -H -lnt '( sport = :8082 )') ]]; then fail 'Port 8082 is already in use.'; fi
  [[ $dry == --dry-run ]] && { echo 'Validated private service start (dry run).'; exit 0; }
  exec podman run --rm --name "$name" --pull=never \
    --label io.ai-harness.service=searxng \
    --read-only --read-only-tmpfs=false --image-volume=ignore \
    --user 977:977 --cap-drop=all --security-opt=no-new-privileges \
    --network=slirp4netns:allow_host_loopback=false \
    --publish 127.0.0.1:8082:8080 \
    --mount type=tmpfs,destination=/tmp,tmpfs-size=67108864,tmpfs-mode=1770,U=true,nosuid,nodev,noexec \
    --mount type=tmpfs,destination=/var/cache/searxng,tmpfs-size=67108864,tmpfs-mode=0700,U=true,nosuid,nodev,noexec \
    --env SEARXNG_SECRET --env GRANIAN_HOST=0.0.0.0 \
    --pids-limit=256 --memory=1g --cpus=2 \
    --log-driver=none "$image"
fi
printf 'Validated release/action %s for %s (not a readiness check).\n' "$action" "$name"
