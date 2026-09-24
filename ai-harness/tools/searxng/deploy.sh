#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Bounded installation of this one rootless service into the existing user home.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo 'Usage: deploy.sh [--dry-run]'
  echo 'Run on the target as the existing rootless Podman user; no sudo.'
  echo 'Installs only ai-harness-searxng, preserving its private secret.'
  echo 'Requires bash, python3, Podman, systemd user manager, sha256sum, ss.'
  exit 0
fi
fail() { printf '%s\n' "$1" >&2; exit 1; }
[[ $# == 0 || ( $# == 1 && $1 == --dry-run ) ]] || fail 'Use --help.'
[[ $(id -u) != 0 ]] || fail 'Refusing root.'
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
state=$HOME/.ai-harness-searxng
config=$HOME/.config/ai-harness-searxng
unit=$HOME/.config/systemd/user/ai-harness-searxng.service
[[ $HOME == /* && $HOME != *$'\n'* && $HOME != *'%'* && $HOME != *' '* ]] || fail 'Unsupported home path.'
[[ $(podman info --format '{{.Host.Security.Rootless}}') == true ]] || fail 'Rootless Podman required.'
systemctl --user show -p Version --value >/dev/null || fail 'Existing user manager required.'
# Inspect only path metadata, never the protected environment contents.
python3 - "$HOME" "$state" "$config" "$unit" <<'PY'
import os, pathlib, stat, sys
home, state, config, unit = map(pathlib.Path, sys.argv[1:])
uid = os.getuid()
for target in (home, state, state / 'releases', config, unit.parent):
    for path in [target, *target.parents]:
        if path == pathlib.Path('/'):
            break
        if path.is_symlink():
            raise SystemExit('Refusing symlink in service path ancestry: '+str(path))
        if path.exists():
            s = path.stat()
            if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, uid) or s.st_mode & 0o022:
                raise SystemExit('Unsafe service path ancestry: '+str(path))
for path in (state, config):
    if path.exists():
        marker = path / '.owner'
        if not marker.is_file() or marker.is_symlink() or marker.read_text() != 'ai-harness-searxng-v1\n':
            raise SystemExit('Unowned service directory conflict: '+str(path))
        if path.stat().st_uid != uid or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise SystemExit('Service directory must be owned and 0700: '+str(path))
if unit.is_symlink() or unit.exists() and (not unit.is_file() or unit.stat().st_uid != uid or not unit.read_text().startswith('# Managed exclusively by ai-harness/tools/searxng; ownership marker v1.\n')):
    raise SystemExit('Unowned user unit conflict')
secret = config / 'service.env'
if secret.is_symlink() or secret.exists() and (not secret.is_file() or secret.stat().st_uid != uid or stat.S_IMODE(secret.stat().st_mode) != 0o600 or secret.stat().st_nlink != 1):
    raise SystemExit('Unsafe secret file metadata')
PY
loaded=$(systemctl --user show ai-harness-searxng.service -p FragmentPath --value)
[[ -z $loaded || $loaded == "$unit" ]] || fail 'Conflicting unit loaded from another path.'
if podman container exists ai-harness-searxng; then
  [[ $(podman inspect ai-harness-searxng --format '{{index .Config.Labels "io.ai-harness.service"}}') == searxng ]] || fail 'Unowned container conflict.'
fi
files=(Containerfile settings.yml LICENSE-AGPL-3.0.txt NOTICE.md image-pin.json run.sh deploy.sh ai-harness-searxng.service.in README.md)
cd -- "$source_dir"
for file in "${files[@]}"; do [[ -f $file && ! -L $file ]] || fail "Missing/non-regular source: $file"; done
content=$(sha256sum "${files[@]}" | sha256sum | cut -d' ' -f1)
release=$state/releases/$content
tag=localhost/ai-harness-searxng:$content
if podman image exists "$tag"; then
  [[ $(podman image inspect "$tag" --format '{{index .Labels "io.ai-harness.service"}}') == searxng ]] || fail 'Unowned image tag conflict.'
fi
if [[ -e $state/current || -L $state/current ]]; then
  [[ -L $state/current && $(readlink "$state/current") == "releases/$content" ]] || fail 'Different current release; review and stop the old service before explicit migration.'
fi
if [[ -n $(ss -H -lnt '( sport = :8082 )') ]] && ! systemctl --user is-active --quiet ai-harness-searxng.service; then
  fail 'Port 8082 conflict outside the active owned service.'
fi
printf 'Release: %s\nImage tag: %s\nUnit: %s\nPublish: 127.0.0.1:8082:8080\n' "$release" "$tag" "$unit"
[[ ${1:-} == --dry-run ]] && exit 0
umask 077
mkdir -p -- "$state" "$config" "$state/releases" "$(dirname -- "$unit")"
chmod 700 "$state" "$config" "$state/releases"
printf 'ai-harness-searxng-v1\n' > "$state/.owner"
printf 'ai-harness-searxng-v1\n' > "$config/.owner"
# Exclusive creation; existing secret bytes are validated, never regenerated.
python3 - "$config/service.env" <<'PY'
import os, re, secrets, sys
path = sys.argv[1]
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
except FileExistsError:
    with open(path, 'rb') as f:
        if not re.fullmatch(rb'SEARXNG_SECRET=[a-f0-9]{64}\n', f.read(256)):
            raise SystemExit('Invalid protected environment format; preserving file')
    print('Existing protected secret preserved.')
else:
    with os.fdopen(fd, 'w') as f:
        f.write('SEARXNG_SECRET='+secrets.token_hex(32)+'\n')
    print('Protected secret created (value withheld).')
PY
if [[ -e $release || -L $release ]]; then
  [[ -d $release && ! -L $release && -f $release/SHA256SUMS ]] || fail 'Incomplete/conflicting release; inspect before retry.'
  (cd "$release"; sha256sum --check --status SHA256SUMS) || fail 'Existing release checksum mismatch.'
else
  mkdir -- "$release"
  for file in "${files[@]}"; do install -m 400 "$file" "$release/$file"; done
  chmod 500 "$release/run.sh" "$release/deploy.sh"
  # Minimal isolated build context; no environment, SSH, app or engine source.
  build_context=$(mktemp -d "$state/build.XXXXXXXX")
  trap 'rm -rf -- "$build_context"' EXIT
  mkdir -p "$build_context/tools/searxng"
  for file in Containerfile settings.yml LICENSE-AGPL-3.0.txt NOTICE.md image-pin.json; do
    install -m 400 "$release/$file" "$build_context/tools/searxng/$file"
  done
  # Timestamp normalization makes the derived layer reproducible for these inputs.
  podman build --pull=never --network=none --timestamp=0 \
    --tag "$tag" --iidfile "$release/image.id" \
    --file "$build_context/tools/searxng/Containerfile" "$build_context"
  chmod 400 "$release/image.id"
  (cd "$release"; sha256sum "${files[@]}" image.id > SHA256SUMS; chmod 400 SHA256SUMS)
  chmod 500 "$release"
fi
"$release/run.sh" check
if [[ ! -L $state/current ]]; then ln -s "releases/$content" "$state/current"; fi
install -m 600 "$release/ai-harness-searxng.service.in" "$unit"
systemd-analyze --user verify "$unit"
systemctl --user daemon-reload
systemctl --user enable --now ai-harness-searxng.service
systemctl --user show ai-harness-searxng.service -p LoadState -p ActiveState -p SubState -p FragmentPath
printf 'Image ID: %s\n' "$(cat "$release/image.id")"
