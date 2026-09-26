#!/usr/bin/env bash
# ACP transport only: stdout belongs to mcode, diagnostics belong to stderr.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: run-engine.sh --profile-dir ABS --workspace ABS

Run the reviewed MiniMax image through local, rootless Podman using ACP stdio.
Both existing directories must be owned by this user, resolve without symlinks,
and be distinct. They are mounted at the identical absolute paths. The profile
gets isolated state/ and state/home directories; native sibling lock files stay
inside that mount. No other host directory or socket is mounted.

Required environment:
  AI_HARNESS_GATEWAY_TOKEN  Ephemeral per-runner text/image gateway token;
                           16..4096 characters, no ASCII control characters.
  AI_HARNESS_SESSION_ID     1..128 letters/digits/._-, first character alphanumeric.
Optional environment:
  AI_HARNESS_GATEWAY_URL    http://10.0.2.2:8081/v1 (the only reviewed endpoint).

The local image must already exist with the reviewed MiniMax revision label.
No image pull, sudo, host-network mode, or browser sandbox bypass is performed.
A fresh root-owned task-egress policy attestation and fixed user slice are required.
Actual Linux egress isolation/gateway/browser capability requires live acceptance.
EOF
}

die() { printf 'run-engine: %s\n' "$*" >&2; exit 64; }

profile_dir=''
workspace=''
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --profile-dir)
      (($# >= 2)) || die '--profile-dir needs an absolute path'
      [[ -z "$profile_dir" ]] || die 'duplicate --profile-dir'
      profile_dir=$2; shift 2 ;;
    --workspace)
      (($# >= 2)) || die '--workspace needs an absolute path'
      [[ -z "$workspace" ]] || die 'duplicate --workspace'
      workspace=$2; shift 2 ;;
    *) die 'unknown argument (see --help)' ;;
  esac
done
[[ -n "$profile_dir" && -n "$workspace" ]] || die 'both directory arguments are required'
((EUID != 0)) || die 'invoke as the ordinary service user, never root or sudo'
[[ -n "${HOME:-}" && "$HOME" = /* && -d "$HOME" ]] || die 'HOME must name the service user home'
host_home=$(cd -- "$HOME" && pwd -P)
host_uid=$(id -u)
host_gid=$(id -g)
host_user=$(id -un)

validate_directory() {
  local path=$1 purpose=$2 physical sensitive
  [[ "$path" = /* && "$path" != / ]] || die "$purpose must be an absolute directory below a data root"
  [[ "$path" != *:* && "$path" != *,* && ! "$path" =~ [[:cntrl:]] ]] || die "$purpose contains unsupported path characters"
  [[ -d "$path" && -O "$path" && -w "$path" ]] || die "$purpose must exist and be owned and writable by this user"
  physical=$(cd -- "$path" && pwd -P) || die "$purpose cannot be resolved"
  [[ "$physical" = "$path" ]] || die "$purpose must be canonical, with no symlink, dot component, or trailing slash"
  [[ "$host_home" != "$path" && "$host_home" != "$path/"* ]] || die "$purpose cannot expose the user home or an ancestor"
  # Host-only freeze/audit state must never be exposed through a same-UID bind.
  for sensitive in /var/lib/ai-harness-dispatch /run/ai-harness-dispatch /var/lib/ai-harness-admin /run/ai-harness-admin /run/ai-harness-status; do
    [[ "$sensitive" != "$path" && "$sensitive" != "$path/"* && "$path" != "$sensitive/"* ]] || die "$purpose cannot expose private control state or ancestors"
  done
  for sensitive in .ssh .codex .gnupg .aws .azure .kube .docker .config .local/share/containers .local/share/keyrings; do
    sensitive=$host_home/$sensitive
    [[ "$sensitive" != "$path" && "$sensitive" != "$path/"* && "$path" != "$sensitive/"* ]] || die "$purpose cannot expose credential directories or their ancestors"
  done
  case "$path/" in
    /bin/*|/sbin/*|/etc/*|/usr/*|/opt/*|/boot/*|/lib/*|/lib64/*|/proc/*|/sys/*|/dev/*|/run/*|/root/*)
      die "$purpose cannot expose an administrative or runtime path" ;;
    */.ssh/*|*/.codex/*|*/.gnupg/*|*/.aws/*|*/.azure/*|*/.kube/*|*/.docker/*|*/.config/*|*/.local/share/containers/*|*/.local/share/keyrings/*)
      die "$purpose cannot expose a credential or container-management path" ;;
  esac
}
validate_directory "$profile_dir" profile
validate_directory "$workspace" workspace
[[ "$profile_dir" != "$workspace" && "$profile_dir" != "$workspace/"* && "$workspace" != "$profile_dir/"* ]] || die 'profile and workspace must not overlap'

gateway_url=${AI_HARNESS_GATEWAY_URL:-http://10.0.2.2:8081/v1}
gateway_token=${AI_HARNESS_GATEWAY_TOKEN:-}
session_id=${AI_HARNESS_SESSION_ID:-}
[[ "$gateway_url" = http://10.0.2.2:8081/v1 ]] || die 'gateway URL must be the reviewed rootless host-loopback endpoint'
[[ ${#gateway_token} -ge 16 && ${#gateway_token} -le 4096 && ! "$gateway_token" =~ [[:cntrl:]] ]] || die 'an ephemeral gateway token of 16..4096 characters without control characters is required'
[[ "$session_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && ${#session_id} -le 128 ]] || die 'a valid session identifier is required'
podman_bin=$(type -P podman) || die 'Podman is not installed; the reviewed bootstrap requires user execution'
[[ "$podman_bin" = /* && -x "$podman_bin" ]] || die 'Podman must resolve to an absolute executable in the service PATH'
python_bin=$(type -P python3) || die 'Python 3 is required for bounded ACP supervision and token redaction'
[[ "$python_bin" = /* && -x "$python_bin" ]] || die 'Python 3 must resolve to an absolute executable in the service PATH'
launcher_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

# Remove export attributes without logging or placing credential values in argv.
# In particular, drop CONTAINER_HOST/CONTAINER_CONNECTION, proxy variables,
# upstream keys, SSH agent variables, NODE_OPTIONS and container config overrides.
while IFS= read -r exported_name; do
  export -n "${exported_name?}"
done < <(compgen -e)
export PATH=/usr/bin:/bin HOME="$host_home" USER="$host_user" LOGNAME="$host_user"
export XDG_RUNTIME_DIR="/run/user/$host_uid"
export AI_HARNESS_GATEWAY_URL="$gateway_url"
export AI_HARNESS_GATEWAY_TOKEN="$gateway_token"
export AI_HARNESS_SESSION_ID="$session_id"
unset gateway_token

rootless=$("$podman_bin" --remote=false info --format '{{.Host.Security.Rootless}}' 2>/dev/null) || die 'local Podman rootless readiness check failed'
[[ "$rootless" = true ]] || die 'Podman must report rootless=true'

image_tag=localhost/ai-harness-engine:0.0.2-ae65651df5f9
revision=ae65651df5f97ae1085ab4e19964f4b78c769a4e
patchset=69d7fe14ed8b1e394fe7315e04724e3ef89c2efbd21118a42fa1842f5ed48eff
image_metadata=$("$podman_bin" --remote=false image inspect --format '{{.Id}}|{{index .Labels "org.opencontainers.image.revision"}}|{{index .Labels "org.opencontainers.image.ai-harness.patchset"}}' "$image_tag" 2>/dev/null) || die 'reviewed engine image is absent; build it separately after bootstrap'
image_id=${image_metadata%%|*}
image_labels=${image_metadata#*|}
image_revision=${image_labels%%|*}
image_patchset=${image_labels#*|}
[[ "$image_id" =~ ^(sha256:)?[0-9a-f]{64}$ && "$image_revision" = "$revision" && "$image_patchset" = "$patchset" ]] || die 'local image identity, MiniMax revision or patchset label does not match the reviewed pins'

# Native proper-lockfile writes a sibling dataDir.lock. Nest dataDir inside the
# existing profile mount so its lock remains writable without mounting parents.
for legacy_entry in config.yaml home AGENTS.md mcp.json skills; do
  [[ ! -e "$profile_dir/$legacy_entry" && ! -L "$profile_dir/$legacy_entry" ]] || die 'legacy root-level profile requires explicit migration before this launcher'
done
container_data=$profile_dir/state
if [[ ! -e "$container_data" && ! -L "$container_data" ]]; then
  mkdir -- "$container_data"
fi
validate_directory "$container_data" 'isolated engine state'
container_home=$container_data/home
if [[ ! -e "$container_home" && ! -L "$container_home" ]]; then
  mkdir -- "$container_home"
fi
validate_directory "$container_home" 'isolated engine home'

# Do not add -t: ACP is newline-delimited JSON, never terminal text.
# Preserve AppArmor and the pinned Podman seccomp rules, with only chroot
# admitted for Chromium inside its nested user namespace. No outer caps added.
security_profile=$launcher_dir/security/chromium-seccomp.json
"$python_bin" - "$security_profile" <<'PY_SECCOMP' || die 'reviewed Chromium seccomp profile identity mismatch'
import hashlib, sys
try:
    valid = hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest() == '0474c063b32acee85a1eb5ccfc35f7b1f66278af8da722c45b1d25eb2ae1cfbb'
except OSError:
    valid = False
sys.exit(0 if valid else 1)
PY_SECCOMP
exec "$python_bin" "$launcher_dir/engine/task-egress.py" -- \
  "$launcher_dir/engine/redact-acp.py" "$podman_bin" \
  --remote=false --cgroup-manager=systemd run --cgroup-parent=aiharnesstasks.slice --init --init-path /usr/bin/catatonit --rm --interactive --pull=never \
  --userns keep-id --user "$host_uid:$host_gid" \
  --network slirp4netns:allow_host_loopback=true \
  --cap-drop ALL --security-opt no-new-privileges \
  --security-opt "seccomp=$security_profile" \
  --read-only --pids-limit 1024 --shm-size 512m \
  --tmpfs /tmp:rw,nosuid,nodev,size=1g,mode=1777 \
  --tmpfs /run:rw,nosuid,nodev,size=64m,mode=755 \
  --tmpfs /var/tmp:rw,nosuid,nodev,size=256m,mode=1777 \
  --stop-signal SIGTERM --stop-timeout 20 \
  --volume "$profile_dir:$profile_dir:rw,rprivate" \
  --volume "$workspace:$workspace:rw,rprivate" \
  --workdir "$workspace" \
  --env "HOME=$container_home" --env "MINIMAX_DATA_DIR=$container_data" \
  --env PATH=/opt/ai-harness-python/bin:/opt/ai-harness/tools/runtime/node_modules/.bin:/opt/ai-harness/bin:/usr/local/bin:/usr/bin:/bin \
  --env TZ=Europe/Ljubljana \
  --env TERM=dumb --env NO_COLOR=1 \
  --env MCODE_DISABLE_TELEMETRY=1 --env DO_NOT_TRACK=1 \
  --env MCODE_CHROME_PATH=/usr/bin/chromium --env PYTHONDONTWRITEBYTECODE=1 \
  --env AI_HARNESS_GATEWAY_URL --env AI_HARNESS_GATEWAY_TOKEN \
  --env AI_HARNESS_SESSION_ID \
  "$image_id"
