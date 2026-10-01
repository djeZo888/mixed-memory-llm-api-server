#!/usr/bin/env bash
# private AppServer transport only: stdout belongs to Codex, diagnostics belong to stderr.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: run-codex.sh --profile-dir ABS --workspace ABS [--image-jobs-qualified]

Run the reviewed Codex image through local, rootless Podman using private AppServer stdio.
Both existing directories must be owned by this user, resolve without symlinks,
and be distinct. They are mounted at the identical absolute paths. The profile
gets isolated state/ and state/home directories; native sibling lock files stay
inside that mount. Reviewed delivery files are individually hash-checked and
mounted read-only; no additional writable directory or socket is mounted.

Required environment:
  AI_HARNESS_GATEWAY_TOKEN  Ephemeral per-runner text/image gateway token;
                           16..4096 characters, no ASCII control characters.
  AI_HARNESS_SESSION_ID     1..128 letters/digits/._-, first character alphanumeric.
Optional environment:
  AI_HARNESS_GATEWAY_URL    http://10.0.2.2:8081/v1 (the only reviewed endpoint).

The local image must already exist with the reviewed Codex revision label.
No image pull, sudo, host-network mode, or browser sandbox bypass is performed.
A fresh root-owned task-egress policy attestation and fixed user slice are required.
Actual Linux egress isolation/gateway/browser capability requires live acceptance.
EOF
}

die() { printf 'run-codex: %s\n' "$*" >&2; exit 64; }

profile_dir=''
workspace=''
image_config=config.toml
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --profile-dir)
      (($# >= 2)) || die '--profile-dir needs an absolute path'
      [[ -z "$profile_dir" ]] || die 'duplicate --profile-dir'
      profile_dir=$2; shift 2 ;;
    --image-jobs-qualified)
      [[ "$image_config" = config.toml ]] || die 'duplicate image gate'
      image_config=config-image-jobs.toml; shift ;;
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
receipt_dir=${AI_HARNESS_CODEX_RECEIPT_DIR:-}
receipt_nonce=${AI_HARNESS_CODEX_RECEIPT_NONCE:-}
trace_mode=${AI_HARNESS_CODEX_TRACE_MODE:-}
[[ -z "$trace_mode" || "$trace_mode" = post-sampling-token-usage-v1 && -n "$receipt_dir" && -n "$receipt_nonce" ]] || die 'trusted fixed trace receipt channel required'
[[ -z "$receipt_dir" && -z "$receipt_nonce" || -n "$receipt_dir" && -n "$receipt_nonce" ]] || die 'incomplete private receipt channel'
[[ "$gateway_url" = http://10.0.2.2:8081/v1 ]] || die 'gateway URL must be the reviewed rootless host-loopback endpoint'
[[ ${#gateway_token} -ge 16 && ${#gateway_token} -le 4096 && ! "$gateway_token" =~ [[:cntrl:]] ]] || die 'an ephemeral gateway token of 16..4096 characters without control characters is required'
[[ "$session_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && ${#session_id} -le 128 ]] || die 'a valid session identifier is required'
podman_bin=$(type -P podman) || die 'Podman is not installed; the reviewed bootstrap requires user execution'
[[ "$podman_bin" = /* && -x "$podman_bin" ]] || die 'Podman must resolve to an absolute executable in the service PATH'
python_bin=$(type -P python3) || die 'Python 3 is required for bounded private AppServer supervision and token redaction'
[[ "$python_bin" = /* && -x "$python_bin" ]] || die 'Python 3 must resolve to an absolute executable in the service PATH'
launcher_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
overlay_root=$(cd -- "$launcher_dir/.." && pwd -P)

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
if [[ -n "$receipt_dir" ]]; then
  export AI_HARNESS_CODEX_RECEIPT_DIR="$receipt_dir" AI_HARNESS_CODEX_RECEIPT_NONCE="$receipt_nonce"
fi
unset receipt_dir receipt_nonce
trace_args=()
if [[ -n "$trace_mode" ]]; then
  export AI_HARNESS_CODEX_TRACE_MODE="$trace_mode"
  trace_args=(--env RUST_LOG=off,codex_core::session::turn=trace --env LOG_FORMAT=json)
fi
unset trace_mode

# Pin the validator before executing source-controlled overlay checks.
"$python_bin" - "$launcher_dir/engine/validate-image-overlays.py" <<'PY_OVERLAY' || die 'reviewed overlay validator identity mismatch'
import hashlib, sys
try:
    valid = hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest() == '352e4f3ab089b5553948198e0feccff9bd3967f981c0e3d288740f08d1f67cf4'
except OSError:
    valid = False
sys.exit(0 if valid else 1)
PY_OVERLAY

# Fixed reviewed source overlays keep the baked runtime and dependency pins intact.
"$python_bin" "$launcher_dir/engine/validate-image-overlays.py" \
  "$launcher_dir" codex "$profile_dir" "$workspace" || die 'reviewed image delivery overlay validation failed'

rootless=$("$podman_bin" --remote=false info --format '{{.Host.Security.Rootless}}' 2>/dev/null) || die 'local Podman rootless readiness check failed'
[[ "$rootless" = true ]] || die 'Podman must report rootless=true'

image_tag=localhost/sova-codex:0.158.0-h024-release02
expected_image_id=d8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad
revision=064c6b8c737f5b41d171fdda80bd9ef10ad06eb3
patchset=dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec
image_metadata=$("$podman_bin" --remote=false image inspect --format '{{.Id}}|{{index .Labels "org.opencontainers.image.revision"}}|{{index .Labels "org.opencontainers.image.ai-harness.patchset"}}' "$image_tag" 2>/dev/null) || die 'reviewed engine image is absent; build it separately after bootstrap'
image_id=${image_metadata%%|*}
image_labels=${image_metadata#*|}
image_revision=${image_labels%%|*}
image_patchset=${image_labels#*|}
[[ "${image_id#sha256:}" = "$expected_image_id" && "$image_revision" = "$revision" && "$image_patchset" = "$patchset" ]] || die 'local image identity, Codex revision or patchset label does not match the reviewed pins'

# The cached native image retains its original label; mounted host policy has its own pin.
"$python_bin" - "$launcher_dir/codex" <<'PY_POLICY' || die 'Codex policy checksum mismatch'
import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1]); assert hashlib.sha256(b''.join((p/n).read_bytes() for n in ['config.toml', 'config-image-jobs.toml', 'requirements.toml', 'models.json', 'browser-mcp.mjs', 'skills/sova-local-tools/SKILL.md'])).hexdigest() == '38789bd752463b0a34beacb3849ea544ae5fc6fc4e6ea79204180ec229e5af59'
PY_POLICY
# Task state is persistent; trusted configuration is an immutable bind mount.
# Native proper-lockfile writes a sibling dataDir.lock. Nest dataDir inside the
# existing profile mount so its lock remains writable without mounting parents.
for legacy_entry in config.yaml home AGENTS.md mcp.json skills; do
  [[ ! -e "$profile_dir/$legacy_entry" && ! -L "$profile_dir/$legacy_entry" ]] || die 'legacy root-level profile requires explicit migration before this launcher'
done
container_data=$profile_dir/codex-home
if [[ ! -e "$container_data" && ! -L "$container_data" ]]; then
  mkdir -- "$container_data"
fi
validate_directory "$container_data" 'isolated engine state'
container_home=$container_data/home
if [[ ! -e "$container_home" && ! -L "$container_home" ]]; then
  mkdir -- "$container_home"
fi
validate_directory "$container_home" 'isolated engine home'
mkdir -p -- "$container_data/skills"
validate_directory "$container_data/skills" 'engine skills root'
[[ ! -L "$container_data/skills/sova-local-tools" ]] || die 'trusted skill target cannot be a symlink'

# Do not add -t: private AppServer is newline-delimited JSON, never terminal text.
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
  --volume "$overlay_root/tools/image/image-mcp.mjs:/opt/ai-harness/tools/image/image-mcp.mjs:ro,rprivate" \
  --volume "$overlay_root/tools/image/image.mjs:/opt/ai-harness/tools/image/image.mjs:ro,rprivate" \
  --volume "$launcher_dir/codex/$image_config:$container_data/config.toml:ro,rprivate" \
  --volume "$launcher_dir/codex/models.json:/opt/sova/codex/models.json:ro,rprivate" \
  --volume "$launcher_dir/codex/skills/sova-local-tools:$container_data/skills/sova-local-tools:ro,rprivate" \
  --workdir "$workspace" \
  --env "HOME=$container_home" --env "CODEX_HOME=$container_data" \
  --env PATH=/opt/ai-harness-python/bin:/opt/ai-harness/tools/runtime/node_modules/.bin:/opt/ai-harness/bin:/usr/local/bin:/usr/bin:/bin \
  --env TZ=Europe/Ljubljana \
  --env TERM=dumb --env NO_COLOR=1 \
  --env DO_NOT_TRACK=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env AI_HARNESS_GATEWAY_URL --env AI_HARNESS_GATEWAY_TOKEN \
  --env AI_HARNESS_SESSION_ID \
  "${trace_args[@]}" \
  "$image_id"
