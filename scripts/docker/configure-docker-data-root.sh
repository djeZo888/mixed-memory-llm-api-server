#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${M4_REPORT_PATH:-reports/m4-docker-containerd-storage.md}"
DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
CONTAINERD_CONFIG="/etc/containerd/config.toml"
DOCKER_DATA_ROOT="/data/docker"
CONTAINERD_ROOT="/data/containerd/root"
CONTAINERD_STATE="/run/containerd"
NONTRIVIAL_MIB=128

usage() {
  cat <<'EOF'
Usage: scripts/docker/configure-docker-data-root.sh [--help] [--dry-run] [--yes-configure-docker-storage]

Plan or configure Docker/containerd storage so persistent container data does
not land on the root filesystem.

Modes:
  --help                             Show this help text.
  --dry-run                          Print planned checks and changes only.
  --yes-configure-docker-storage     Apply configuration. Refuses without this flag.

Policy:
  Docker data-root: /data/docker
  containerd persistent root: /data/containerd/root
  containerd state: /run/containerd
EOF
}

mode=""
case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --dry-run)
    mode="dry-run"
    ;;
  --yes-configure-docker-storage)
    mode="configure"
    ;;
  "")
    usage >&2
    echo "STOP: refusing Docker storage configuration without --yes-configure-docker-storage" >&2
    exit 2
    ;;
  *)
    usage >&2
    echo "STOP: unknown option: $1" >&2
    exit 2
    ;;
esac

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

path_mib() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    printf '0'
    return
  fi
  sudo -n du -sx -m "$path" 2>/dev/null | awk '{print $1}'
}

print_plan() {
  cat <<EOF
M4 Docker/containerd storage configuration plan

No commands are executed in dry-run mode.

Required preconditions:
- /data is mounted and separate from /
- /data/docker exists
- /data/containerd exists
- root-disk guard passes
- existing /var/lib/docker and /var/lib/containerd are absent, empty, small, or have a written migration plan

Planned Docker configuration:
- Create /etc/docker if needed.
- Preserve valid existing $DOCKER_DAEMON_JSON settings.
- Set "data-root" to "$DOCKER_DATA_ROOT".

Planned containerd configuration:
- Create /etc/containerd if needed.
- Use containerd's generated default config when no config exists.
- Set top-level root to "$CONTAINERD_ROOT".
- Keep runtime state at "$CONTAINERD_STATE".
- Treat snapshotter data as persistent data under containerd root unless a future config explicitly overrides it.
- STOP if existing config cannot be parsed or changed safely.

This script never deletes existing Docker/containerd data automatically.
Report path for actual configuration: $REPORT_PATH
EOF
}

append_report_header() {
  mkdir -p "$(dirname "$REPORT_PATH")"
  cat >> "$REPORT_PATH" <<EOF

## Docker/containerd Storage Configuration

- Timestamp: $(date -Is)
- Hostname: $(hostname 2>/dev/null || printf unknown)
- User: $(whoami 2>/dev/null || printf unknown)
- Branch: $(git branch --show-current 2>/dev/null || printf unknown)
EOF
}

run_logged() {
  local label="$1"
  shift
  {
    printf '\n### %s\n\n' "$label"
    printf '```console\n'
    printf '$'
    printf ' %q' "$@"
    printf '\n'
    set +e
    "$@" 2>&1
    local status=$?
    set -e
    printf '\n[exit=%s]\n' "$status"
    printf '```\n'
    return "$status"
  } >> "$REPORT_PATH"
}

if [[ "$mode" == "dry-run" ]]; then
  print_plan
  exit 0
fi

cd "$(repo_root)"

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh

[[ -d /data/docker ]] || { echo "STOP: /data/docker missing" >&2; exit 1; }
[[ -d /data/containerd ]] || { echo "STOP: /data/containerd missing" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "STOP: python3 required to preserve daemon.json safely" >&2; exit 1; }

docker_root_mib=$(path_mib /var/lib/docker)
containerd_root_mib=$(path_mib /var/lib/containerd)
if (( docker_root_mib > NONTRIVIAL_MIB )); then
  echo "STOP: /var/lib/docker is ${docker_root_mib} MiB; write and review a migration plan before configuring" >&2
  exit 1
fi
if (( containerd_root_mib > NONTRIVIAL_MIB )); then
  echo "STOP: /var/lib/containerd is ${containerd_root_mib} MiB; write and review a migration plan before configuring" >&2
  exit 1
fi

append_report_header
run_logged "pre-configuration /var/lib sizes" sudo -n du -sx -m /var/lib/docker /var/lib/containerd
run_logged "create Docker config directory" sudo -n install -m 0755 -d /etc/docker
run_logged "write Docker daemon.json data-root" sudo -n env DOCKER_DAEMON_JSON="$DOCKER_DAEMON_JSON" DOCKER_DATA_ROOT="$DOCKER_DATA_ROOT" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["DOCKER_DAEMON_JSON"])
data = {}
if path.exists() and path.stat().st_size:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
if not isinstance(data, dict):
    raise SystemExit("daemon.json must contain a JSON object")
data["data-root"] = os.environ["DOCKER_DATA_ROOT"]
tmp = path.with_suffix(path.suffix + ".tmp")
with tmp.open("w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
    handle.write("\n")
tmp.replace(path)
PY

run_logged "create containerd config directory" sudo -n install -m 0755 -d /etc/containerd
if [[ ! -s "$CONTAINERD_CONFIG" ]]; then
  command -v containerd >/dev/null 2>&1 || { echo "STOP: containerd command missing; install Docker packages before configuring containerd" >&2; exit 1; }
  run_logged "generate default containerd config" sudo -n bash -c "containerd config default > '$CONTAINERD_CONFIG'"
fi
run_logged "configure containerd root and state" sudo -n env CONTAINERD_CONFIG="$CONTAINERD_CONFIG" CONTAINERD_ROOT="$CONTAINERD_ROOT" CONTAINERD_STATE="$CONTAINERD_STATE" python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path(os.environ["CONTAINERD_CONFIG"])
text = path.read_text(encoding="utf-8")
if "root =" not in text or "state =" not in text:
    raise SystemExit("containerd config missing top-level root/state keys")
text = re.sub(r'(?m)^root\s*=.*$', f'root = "{os.environ["CONTAINERD_ROOT"]}"', text, count=1)
text = re.sub(r'(?m)^state\s*=.*$', f'state = "{os.environ["CONTAINERD_STATE"]}"', text, count=1)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(text, encoding="utf-8")
tmp.replace(path)
PY
run_logged "create containerd data root" sudo -n install -m 0711 -d "$CONTAINERD_ROOT"
run_logged "post-configuration /var/lib sizes" sudo -n du -sx -m /var/lib/docker /var/lib/containerd
run_logged "post-configuration root-disk guard" scripts/common/root-disk-guard.sh

cat <<EOF
PASS: Docker/containerd storage configuration written. Review and restart services only in an approved milestone.
EOF

