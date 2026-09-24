#!/usr/bin/env bash
# Bounded ai-harness host bootstrap. Review before running with sudo.
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: sudo ./bootstrap-host.sh [--dry-run]
Ubuntu24.04 only. Installs podman uidmap slirp4netns fuse-overlayfs nginx,
preserves user/subordinate IDs, enables user linger, and serves private HTTP80.
No SSH/sudoers/user creation, AppArmor relaxation or reboot. --dry-run changes nothing.
HELP
}
die() { printf 'bootstrap: %s\n' "$*" >&2; exit 1; }
dry_run=false
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  --dry-run) dry_run=true; shift ;;
esac
[[ $# -eq 0 ]] || { usage >&2; exit 2; }
[[ $EUID -eq 0 ]] || die 'Run explicitly as root with sudo; no automatic escalation.'
[[ -f /etc/os-release ]] || die 'Missing OS identity.'
# shellcheck source=/dev/null
. /etc/os-release
[[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 ]] || die 'Requires Ubuntu24.04.'
[[ $(id -u user) == 1000 && $(id -g user) == 1000 ]] || die 'Expected existing user UID/GID1000.'
[[ $(getent passwd user | cut -d: -f6) == /home/user ]] || die 'Unexpected user home.'
ip -o -4 address show | grep -q ' 10\.156\.100\.61/' || die 'Private10.156.100.61 is not assigned.'
for file in /etc/subuid /etc/subgid; do
  [[ -f $file && ! -L $file ]] || die "Missing or symlinked $file; no account edits are performed."
  grep -qx 'user:100000:65536' "$file" || die "Expected existing subordinate allocation missing from $file."
  awk -F: '$1!="user" && $2<165536 && ($2+$3)>100000 {bad=1} END {exit bad}' "$file" || die "Overlapping subordinate allocation in $file."
done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
asset="$script_dir/nginx/ai-harness.conf"
asset_sha=d078bf243a68df9214401420224fdb15df0fc991da2b483bd060ccfe67a22ac3
[[ -f $asset && ! -L $asset ]] || die 'Missing regular bundled nginx asset.'
[[ $(sha256sum "$asset" | cut -d' ' -f1) == "$asset_sha" ]] || die 'Bundled nginx asset hash mismatch.'
# H003's reviewed site requires a separately provisioned host-only credential.
# Refuse before package/config mutation; never read or print the secret here.
approval_include=/etc/ai-harness/image-approval-proxy.conf
[[ -f $approval_include && ! -L $approval_include ]] || die 'Provision the protected /etc/ai-harness/image-approval-proxy.conf before bootstrap; see RUNTIME.md.'
[[ $(stat -c '%u:%g:%a:%h' "$approval_include") == 0:0:600:1 ]] || die 'Approval proxy include must be a root:root0600 regular file with one link.'
stock_file() {
  local path=$1 expected actual
  [[ -f $path && ! -L $path ]] || die "Expected regular stock file: $path"
  expected=$(dpkg-query -W -f='${Conffiles}\n' nginx-common 2>/dev/null | awk -v p="$path" '$1==p {print $2}')
  [[ $expected =~ ^[a-f0-9]{32}$ ]] || die "Cannot establish package stock identity: $path"
  actual=$(md5sum "$path" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || die "Unexpected modified nginx configuration: $path (left unchanged)."
}
audit_nginx() {
  local entry
  if [[ -e /etc/nginx/nginx.conf ]]; then
    stock_file /etc/nginx/nginx.conf
  elif [[ -d /etc/nginx ]] && find /etc/nginx -mindepth 1 -print -quit | grep -q .; then
    die 'Existing incomplete nginx configuration; inspect manually. Left unchanged.'
  fi
  shopt -s nullglob dotglob
  for entry in /etc/nginx/conf.d/*; do
    die "Unexpected nginx conf.d entry: $entry (left unchanged)."
  done
  for entry in /etc/nginx/sites-enabled/*; do
    case "$entry" in
      /etc/nginx/sites-enabled/default)
        [[ -L $entry && $(readlink -f "$entry") == /etc/nginx/sites-available/default ]] || die 'Unexpected enabled default site; left unchanged.'
        stock_file /etc/nginx/sites-available/default ;;
      /etc/nginx/sites-enabled/ai-harness.conf)
        [[ -L $entry && $(readlink -f "$entry") == /etc/nginx/sites-available/ai-harness.conf ]] || die 'Unexpected harness site link.' ;;
      *) die "Unrelated enabled nginx site: $entry. Resolve explicitly; left unchanged." ;;
    esac
  done
  if [[ -e /etc/nginx/sites-available/ai-harness.conf || -L /etc/nginx/sites-available/ai-harness.conf ]]; then
    [[ -f /etc/nginx/sites-available/ai-harness.conf && ! -L /etc/nginx/sites-available/ai-harness.conf ]] || die 'Unexpected harness site file.'
    cmp -s "$asset" /etc/nginx/sites-available/ai-harness.conf || die 'Existing harness site differs; explicit reviewed upgrade required.'
  fi
  shopt -u nullglob dotglob
}
audit_nginx
if $dry_run; then
  printf '%s\n' 'DRY RUN: checks passed; would install five packages, enable user linger and configure private nginx80.'
  exit 0
fi
# Serialize this bounded bootstrap; this is not the ai-vm lifecycle lock.
exec 9>/run/ai-harness-bootstrap.lock
flock -n 9 || die 'Another ai-harness bootstrap is running.'
work=$(mktemp -d /run/ai-harness-bootstrap.XXXXXX)
policy=/usr/sbin/policy-rc.d
policy_saved=false
policy_installed=false
cleanup() {
  local rc=$?
  if $policy_installed; then
    rm -f -- "$policy"
    if $policy_saved; then mv -- "$work/policy-rc.d.original" "$policy"; fi
  fi
  rm -rf -- "$work"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
install -o root -g root -m 0644 "$asset" "$work/site.conf"
[[ $(sha256sum "$work/site.conf" | cut -d' ' -f1) == "$asset_sha" ]] || die 'Asset changed while copying.'
asset="$work/site.conf"
# Prevent package maintainer scripts from starting stock wildcard nginx.
# Preserve any existing policy exactly, and chain it for other services.
if [[ -e $policy || -L $policy ]]; then
  [[ -f $policy && ! -L $policy ]] || die 'Non-regular existing policy-rc.d; leave it unchanged and request operator review.'
  cp -a -- "$policy" "$work/policy-rc.d.original"
  policy_saved=true
fi
policy_installed=true
cat > "$policy" <<POLICY
#!/bin/sh
service=''
for arg do
  case "\$arg" in --quiet|--) continue ;; esac
  service=\$arg
  break
done
case "\${service##*/}" in nginx|nginx.service) exit 101 ;; esac
if [ -x '$work/policy-rc.d.original' ]; then exec '$work/policy-rc.d.original' "\$@"; fi
exit 0
POLICY
chmod 0755 "$policy"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends podman uidmap slirp4netns fuse-overlayfs nginx
audit_nginx
backup=''
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  backup=$(mktemp -d /var/backups/ai-harness-bootstrap.XXXXXX)
  cp -a /etc/nginx/sites-enabled/default "$backup/default.enabled"
  cp -a /etc/nginx/sites-available/default "$backup/default.stock"
  rm /etc/nginx/sites-enabled/default
  printf 'Preserved stock default site in %s\n' "$backup"
fi
install -o root -g root -m 0644 "$asset" /etc/nginx/sites-available/ai-harness.conf
created_harness_link=false
if [[ ! -L /etc/nginx/sites-enabled/ai-harness.conf ]]; then
  ln -s /etc/nginx/sites-available/ai-harness.conf /etc/nginx/sites-enabled/ai-harness.conf
  created_harness_link=true
fi
if ! nginx -t; then
  if $created_harness_link; then rm -f /etc/nginx/sites-enabled/ai-harness.conf; fi
  if [[ -n $backup ]]; then cp -a "$backup/default.enabled" /etc/nginx/sites-enabled/default; fi
  die 'nginx validation failed; prior enabled default restored, no service start/reload requested.'
fi
loginctl enable-linger user
systemctl enable nginx.service
if systemctl is-active --quiet nginx.service; then systemctl reload nginx.service; else systemctl start nginx.service; fi
printf '%s\n' 'Bootstrap complete. No application/container was started. Next: user-local runtime and rootless/browser acceptance.'
