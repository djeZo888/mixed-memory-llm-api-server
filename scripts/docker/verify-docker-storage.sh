#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${M4_REPORT_PATH:-reports/m4b-docker-containerd-install.md}"
SMALL_ROOT_MIB="${M4_SMALL_ROOT_MIB:-128}"
DOCKER_DATA_ROOT="/data/docker"
CONTAINERD_DATA_ROOT="/data/containerd"
CONTAINERD_ROOT="/data/containerd/root"
CONTAINERD_STATE="/run/containerd"
DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
CONTAINERD_CONFIG="/etc/containerd/config.toml"

usage() {
  cat <<'EOF'
Usage: scripts/docker/verify-docker-storage.sh [--help] [--report PATH]

Read-only verification for Docker/containerd storage policy. This script does
not edit config, restart services, or configure GPU runtime support.
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

run_shell_capture() {
  local label="$1"
  local command="$2"
  {
    printf '\n### %s\n\n' "$label"
    printf '```console\n'
    printf '$ %s\n' "$command"
    set +e
    bash -o pipefail -c "$command" 2>&1
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
[[ -d "$CONTAINERD_ROOT" ]] || stop "$CONTAINERD_ROOT is missing"

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

command -v docker >/dev/null 2>&1 || stop "Docker is not installed"
command -v containerd >/dev/null 2>&1 || stop "containerd is not installed"

run_capture "systemctl is-active containerd" sudo -n systemctl is-active containerd || stop "containerd service is not active"
run_capture "systemctl is-active docker" sudo -n systemctl is-active docker || stop "docker service is not active"
run_capture "systemctl status containerd" sudo -n systemctl status containerd --no-pager || true
run_capture "systemctl status docker" sudo -n systemctl status docker --no-pager || true
run_capture "sudo docker version" sudo -n docker version || stop "sudo docker version failed"
run_capture "sudo docker info" sudo -n docker info || stop "sudo docker info failed"
run_capture "sudo docker compose version" sudo -n docker compose version || stop "sudo docker compose version failed"
run_capture "sudo docker buildx version" sudo -n docker buildx version || stop "sudo docker buildx version failed"

docker_root=$(sudo -n docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)
[[ "$docker_root" == "$DOCKER_DATA_ROOT" ]] || stop "Docker Root Dir is ${docker_root:-unknown}, expected $DOCKER_DATA_ROOT"

grep -Fq "\"data-root\": \"$DOCKER_DATA_ROOT\"" "$DOCKER_DAEMON_JSON" || stop "$DOCKER_DAEMON_JSON does not set data-root to $DOCKER_DATA_ROOT"
grep -Fxq "root = \"$CONTAINERD_ROOT\"" "$CONTAINERD_CONFIG" || stop "$CONTAINERD_CONFIG does not set root to $CONTAINERD_ROOT"
grep -Fxq "state = \"$CONTAINERD_STATE\"" "$CONTAINERD_CONFIG" || stop "$CONTAINERD_CONFIG does not set state to $CONTAINERD_STATE"

run_capture "hello-world image inspect" sudo -n docker image inspect hello-world:latest || stop "hello-world image missing; run sudo -n docker run --rm hello-world in M4B"
run_capture "sudo docker system df" sudo -n docker system df || stop "sudo docker system df failed"
run_shell_capture "Docker/containerd root and data sizes" "sudo -n du -sh /var/lib/docker /var/lib/containerd '$DOCKER_DATA_ROOT' '$CONTAINERD_DATA_ROOT' '$CONTAINERD_ROOT' 2>/dev/null || true"
run_capture "post-verification root-disk guard" scripts/common/root-disk-guard.sh || stop "root-disk guard failed after Docker verification"

cat >> "$REPORT_PATH" <<EOF

## Docker/containerd Verification Summary

- Docker installed: yes
- containerd installed: yes
- Docker Root Dir: $docker_root
- containerd root: $CONTAINERD_ROOT
- containerd state: $CONTAINERD_STATE
- hello-world image present: yes
- root-disk guard: PASS

## Docker/containerd Verification Conclusion

PASS
EOF

echo "PASS: Docker/containerd storage verified"
