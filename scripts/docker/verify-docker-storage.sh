#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${M4_REPORT_PATH:-reports/m4a-docker-containerd-plan.md}"
SMALL_ROOT_MIB="${M4_SMALL_ROOT_MIB:-128}"
DOCKER_DATA_ROOT="/data/docker"
CONTAINERD_DATA_ROOT="/data/containerd"

usage() {
  cat <<'EOF'
Usage: scripts/docker/verify-docker-storage.sh [--help] [--report PATH]

Read-only verification for Docker/containerd storage policy. This script does
not pull images, run containers, edit config, or restart services.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help)
      usage
      exit 0
      ;;
    --report)
      [[ $# -ge 2 ]] || { echo "STOP: --report requires a path" >&2; exit 2; }
      REPORT_PATH="$2"
      shift 2
      ;;
    *)
      usage >&2
      echo "STOP: unknown option: $1" >&2
      exit 2
      ;;
  esac
done

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

append_header() {
  mkdir -p "$(dirname "$REPORT_PATH")"
  cat >> "$REPORT_PATH" <<EOF

## Docker/containerd Storage Verification

- Timestamp: $(date -Is)
- Hostname: $(hostname 2>/dev/null || printf unknown)
- User: $(whoami 2>/dev/null || printf unknown)
- Branch: $(git branch --show-current 2>/dev/null || printf unknown)
EOF
}

run_capture() {
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

path_mib() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    printf '0'
    return
  fi
  sudo -n du -sx -m "$path" 2>/dev/null | awk '{print $1}'
}

stop() {
  printf '\n## Docker/containerd Verification Conclusion\n\nSTOP\n\nReason: %s\n' "$*" >> "$REPORT_PATH"
  echo "STOP: $*" >&2
  exit 1
}

cd "$(repo_root)"
append_header

run_capture "require /data mounted" scripts/common/require-data-mounted.sh || stop "/data mount requirement failed"
run_capture "pre-verification root-disk guard" scripts/common/root-disk-guard.sh || stop "root-disk guard failed before Docker verification"
run_capture "df -hT / /data" df -hT / /data
[[ -d "$DOCKER_DATA_ROOT" ]] || stop "$DOCKER_DATA_ROOT is missing"
[[ -d "$CONTAINERD_DATA_ROOT" ]] || stop "$CONTAINERD_DATA_ROOT is missing"

docker_mib=$(path_mib /var/lib/docker)
containerd_mib=$(path_mib /var/lib/containerd)
{
  printf '\n### /var/lib Docker/containerd size summary\n\n'
  printf '| Path | MiB | Policy |\n'
  printf '| --- | ---: | --- |\n'
  printf '| `/var/lib/docker` | %s | absent/empty/small or documented |\n' "$docker_mib"
  printf '| `/var/lib/containerd` | %s | absent/empty/small or documented |\n' "$containerd_mib"
} >> "$REPORT_PATH"

if (( docker_mib > SMALL_ROOT_MIB )); then
  stop "/var/lib/docker is ${docker_mib} MiB, above ${SMALL_ROOT_MIB} MiB"
fi
if (( containerd_mib > SMALL_ROOT_MIB )); then
  stop "/var/lib/containerd is ${containerd_mib} MiB, above ${SMALL_ROOT_MIB} MiB"
fi

if ! command -v docker >/dev/null 2>&1; then
  run_capture "docker command lookup" command -v docker || true
  stop "Docker is not installed yet; this is expected during M4A dry-run"
fi

run_capture "systemctl status docker" systemctl status docker --no-pager || true
run_capture "systemctl status containerd" systemctl status containerd --no-pager || true
run_capture "sudo docker version" sudo -n docker version || stop "sudo docker version failed"
run_capture "sudo docker info" sudo -n docker info || stop "sudo docker info failed"
run_capture "sudo docker compose version" sudo -n docker compose version || stop "sudo docker compose version failed"

docker_root=$(sudo -n docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)
[[ "$docker_root" == "$DOCKER_DATA_ROOT" ]] || stop "Docker Root Dir is ${docker_root:-unknown}, expected $DOCKER_DATA_ROOT"

run_capture "post-verification root-disk guard" scripts/common/root-disk-guard.sh || stop "root-disk guard failed after Docker verification"

cat >> "$REPORT_PATH" <<'EOF'

## Docker/containerd Verification Conclusion

PASS
EOF

echo "PASS: Docker/containerd storage verified"
