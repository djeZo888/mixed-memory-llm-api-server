#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="reports/m1-vm-preflight.md"
CONCLUSION="PASS"
STOP_REASONS=()
WARNINGS=()
CODEX_STATUS="not checked"
SUDO_STATUS="not checked"
ROOT_DISK_SUMMARY="not checked"
DATA_DISK_SUMMARY="not checked"
DATA_STATE_SUMMARY="not checked"
GPU_STATE_SUMMARY="not checked"
NETWORK_STATE_SUMMARY="not checked"
FIREWALL_SUMMARY="not checked"
FAILED_UNITS_SUMMARY="not checked"
BOOT_ERRORS_SUMMARY="not checked"

usage() {
  cat <<'EOF'
Usage: scripts/preflight/vm-preflight.sh [--help]

Run a non-destructive VM readiness preflight and write reports/m1-vm-preflight.md.

This script collects read-only host, storage, GPU, network, firewall, listener,
and system-health facts. It does not install packages, partition or format disks,
mount filesystems, edit /etc/fstab, configure Docker, configure NVIDIA drivers,
configure systemd, download models, or expose APIs.

Required behavior:
- exits nonzero if codex is missing
- exits nonzero if sudo -k && sudo -n true fails
- never prompts for a sudo password
EOF
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" != "" ]]; then
  usage >&2
  exit 2
fi

mkdir -p reports

sanitize() {
  sed -E \
    -e 's/(HF_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
    -e 's/(OPENAI_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
    -e 's/(GITHUB_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
    -e 's/(Authorization:[[:space:]]*Bearer[[:space:]]+)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's/((password|passwd)[=:][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's/[[:blank:]]+$//'
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
    "$@" 2>&1 | sanitize
    local statuses=("${PIPESTATUS[@]}")
    set -e
    printf '\n[exit=%s]\n' "${statuses[0]}"
    printf '```\n'
  } >> "$REPORT_PATH"
}

run_capture_shell() {
  local label="$1"
  local command="$2"
  {
    printf '\n### %s\n\n' "$label"
    printf '```console\n'
    printf '$ %s\n' "$command"
    set +e
    bash -o pipefail -c "$command" 2>&1 | sanitize
    local statuses=("${PIPESTATUS[@]}")
    set -e
    printf '\n[exit=%s]\n' "${statuses[0]}"
    printf '```\n'
  } >> "$REPORT_PATH"
}

capture_value() {
  local command="$1"
  set +e
  local output
  output=$(bash -o pipefail -c "$command" 2>&1 | sanitize)
  local status=$?
  set -e
  if [[ $status -eq 0 ]]; then
    printf '%s' "$output"
  else
    printf 'command failed with exit %s: %s' "$status" "$output"
  fi
}

add_stop_reason() {
  STOP_REASONS+=("$1")
  CONCLUSION="STOP"
}

remote_text_has_credentials() {
  git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'
}

HOSTNAME_VALUE=$(hostname 2>/dev/null || printf 'unknown')
USER_VALUE=$(whoami 2>/dev/null || printf 'unknown')
PWD_VALUE=$(pwd 2>/dev/null || printf 'unknown')
BRANCH_VALUE=$(git branch --show-current 2>/dev/null || printf 'unknown')
REMOTE_VALUE=$(git remote -v 2>/dev/null || printf 'unknown')
TIMESTAMP_VALUE=$(date -Is)

cat > "$REPORT_PATH" <<EOF
# M1 VM Preflight Report

## Milestone

- Milestone ID: M1
- Name: VM preflight
- Timestamp: ${TIMESTAMP_VALUE}
- Hostname: ${HOSTNAME_VALUE}
- User: ${USER_VALUE}
- Working directory: ${PWD_VALUE}
- Branch name: ${BRANCH_VALUE}

## Git Remote

\`\`\`text
${REMOTE_VALUE}
\`\`\`
EOF

if remote_text_has_credentials; then
  add_stop_reason "git remote appears to contain credentials"
fi

if ! command -v codex >/dev/null 2>&1; then
  CODEX_STATUS="STOP: codex missing from PATH"
  add_stop_reason "codex is missing from PATH"
else
  CODEX_PATH=$(command -v codex)
  CODEX_VERSION=$(capture_value 'codex --version')
  CODEX_LOGIN=$(capture_value 'codex login status')
  CODEX_STATUS="found at ${CODEX_PATH}; version: ${CODEX_VERSION}; login: ${CODEX_LOGIN}"
fi

if ! sudo -k >/dev/null 2>&1; then
  SUDO_STATUS="STOP: sudo -k failed"
  add_stop_reason "sudo -k failed"
elif ! sudo -n true >/dev/null 2>&1; then
  SUDO_STATUS="STOP: sudo -n true failed after sudo -k"
  add_stop_reason "sudo -n true failed after sudo -k"
else
  SUDO_ID=$(capture_value 'sudo -n id')
  SUDO_STATUS="PASS: sudo -n true worked after sudo -k; sudo -n id: ${SUDO_ID}"
fi

ROOT_SOURCE=$(findmnt -n -o SOURCE / 2>/dev/null || true)
ROOT_FSTYPE=$(findmnt -n -o FSTYPE / 2>/dev/null || true)
ROOT_SIZE=$(df -hT / 2>/dev/null | awk 'NR==2 {print $3 " total, " $5 " used, fstype " $2}' || true)
ROOT_DISK_SUMMARY="source=${ROOT_SOURCE:-unknown}; fstype=${ROOT_FSTYPE:-unknown}; df=${ROOT_SIZE:-unknown}"

if lsblk -dn -o PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL 2>/dev/null | awk '$1=="/dev/sdb" {found=1} END {exit found?0:1}'; then
  SDB_LINE=$(lsblk -dn -o PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL /dev/sdb 2>/dev/null | tr -s ' ' || true)
  SDB_MOUNT=$(lsblk -dn -o MOUNTPOINTS /dev/sdb 2>/dev/null | tr -d '[:space:]' || true)
  SDB_FSTYPE=$(lsblk -dn -o FSTYPE /dev/sdb 2>/dev/null | tr -d '[:space:]' || true)
  if [[ -z "$SDB_MOUNT" && -z "$SDB_FSTYPE" ]]; then
    DATA_DISK_SUMMARY="likely candidate: ${SDB_LINE}; no top-level filesystem or mountpoint detected"
  else
    DATA_DISK_SUMMARY="/dev/sdb present but not an untouched top-level disk: ${SDB_LINE}"
    WARNINGS+=("/dev/sdb exists but has a filesystem or mountpoint; M2 must verify before any action")
  fi
else
  DATA_DISK_SUMMARY="/dev/sdb not found; M2 must identify the data disk before any action"
  WARNINGS+=("expected /dev/sdb was not found")
fi

if findmnt -n /data >/dev/null 2>&1; then
  DATA_STATE_SUMMARY="/data is mounted: $(findmnt -n -o SOURCE,FSTYPE,OPTIONS /data 2>/dev/null | tr -s ' ')"
else
  if [[ -e /data ]]; then
    DATA_STATE_SUMMARY="/data exists but is not a mountpoint; likely a root-disk directory until M2 verifies"
  else
    DATA_STATE_SUMMARY="/data does not exist"
  fi
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_STATE_SUMMARY="nvidia-smi present: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | paste -sd '; ' - || true)"
else
  GPU_STATE_SUMMARY="nvidia-smi not installed or not in PATH"
fi

if getent hosts huggingface.co >/dev/null 2>&1 && getent hosts github.com >/dev/null 2>&1; then
  NETWORK_STATE_SUMMARY="basic DNS for huggingface.co and github.com resolved"
else
  NETWORK_STATE_SUMMARY="one or more basic DNS checks failed; see Network section"
  WARNINGS+=("one or more DNS checks failed")
fi

FAILED_UNITS_COUNT=$(systemctl --failed --no-legend 2>/dev/null | sed '/^$/d' | wc -l | tr -d ' ' || printf 'unknown')
FAILED_UNITS_SUMMARY="failed systemd units: ${FAILED_UNITS_COUNT}"
BOOT_ERROR_COUNT=$(journalctl -b -p err -n 100 --no-pager 2>/dev/null | sed '/^-- No entries --$/d' | sed '/^$/d' | wc -l | tr -d ' ' || printf 'unknown')
BOOT_ERRORS_SUMMARY="current boot error lines captured: ${BOOT_ERROR_COUNT}"
FIREWALL_SUMMARY="see Firewall and listeners section"

cat >> "$REPORT_PATH" <<EOF

## Executive Summary

- Codex status: ${CODEX_STATUS}
- Sudo status: ${SUDO_STATUS}
- Root disk summary: ${ROOT_DISK_SUMMARY}
- Candidate data disk summary: ${DATA_DISK_SUMMARY}
- /data state: ${DATA_STATE_SUMMARY}
- GPU state: ${GPU_STATE_SUMMARY}
- Network state: ${NETWORK_STATE_SUMMARY}
- Firewall/listener summary: ${FIREWALL_SUMMARY}
- Failed systemd units: ${FAILED_UNITS_SUMMARY}
- Current boot errors: ${BOOT_ERRORS_SUMMARY}
EOF

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  printf '\n## Warnings\n\n' >> "$REPORT_PATH"
  for warning in "${WARNINGS[@]}"; do
    printf -- '- %s\n' "$warning" >> "$REPORT_PATH"
  done
fi

if [[ ${#STOP_REASONS[@]} -gt 0 ]]; then
  printf '\n## Stop Reasons\n\n' >> "$REPORT_PATH"
  for reason in "${STOP_REASONS[@]}"; do
    printf -- '- %s\n' "$reason" >> "$REPORT_PATH"
  done
fi

cat >> "$REPORT_PATH" <<'EOF'

## Identity
EOF
run_capture "hostname" hostname
run_capture "whoami" whoami
run_capture "id" id
run_capture "date -Is" date -Is
run_capture "pwd" pwd

cat >> "$REPORT_PATH" <<'EOF'

## OS
EOF
run_capture_shell "/etc/os-release" 'cat /etc/os-release'
run_capture "uname -a" uname -a

cat >> "$REPORT_PATH" <<'EOF'

## Codex
EOF
run_capture_shell "command -v codex" 'command -v codex'
if command -v codex >/dev/null 2>&1; then
  run_capture_shell 'ls -l "$(command -v codex)"' 'ls -l "$(command -v codex)"'
fi
run_capture "codex --version" codex --version
run_capture "codex login status" codex login status

cat >> "$REPORT_PATH" <<'EOF'

## Sudo
EOF
run_capture "sudo -k" sudo -k
run_capture "sudo -n true" sudo -n true
run_capture "sudo -n id" sudo -n id

cat >> "$REPORT_PATH" <<'EOF'

## Root Filesystem
EOF
run_capture "df -hT /" df -hT /
run_capture "findmnt /" findmnt /

cat >> "$REPORT_PATH" <<'EOF'

## Block Devices
EOF
run_capture "lsblk block inventory" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
run_capture "sudo -n blkid" sudo -n blkid

cat >> "$REPORT_PATH" <<'EOF'

## /data State
EOF
run_capture_shell "findmnt /data" 'findmnt /data || true'
run_capture_shell "ls -ld /data" 'if [ -e /data ]; then ls -ld /data; else echo "/data does not exist"; fi'
run_capture_shell "sudo -n find /data -maxdepth 4 -ls" 'if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo "/data does not exist"; fi'

cat >> "$REPORT_PATH" <<'EOF'

## GPU Inventory
EOF
run_capture_shell "lspci display inventory" "if command -v lspci >/dev/null 2>&1; then lspci -nn | egrep -i 'nvidia|vga|3d|display' || true; else echo 'lspci not installed'; fi"
run_capture_shell "nvidia-smi" 'if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; else echo "nvidia-smi not installed or not in PATH"; fi'
run_capture_shell "current boot journal nvidia/nouveau" "journalctl -b --no-pager 2>/dev/null | egrep -i 'nvidia|nouveau' | tail -n 200 || true"

cat >> "$REPORT_PATH" <<'EOF'

## Network
EOF
run_capture "ip -br addr" ip -br addr
run_capture "ip route" ip route
run_capture "getent hosts huggingface.co" getent hosts huggingface.co
run_capture "getent hosts github.com" getent hosts github.com
run_capture "getent hosts docker.com" getent hosts docker.com
run_capture "getent hosts nvidia.com" getent hosts nvidia.com
run_capture "curl -I --max-time 10 https://huggingface.co" curl -I --max-time 10 https://huggingface.co
run_capture "curl -I --max-time 10 https://github.com" curl -I --max-time 10 https://github.com

cat >> "$REPORT_PATH" <<'EOF'

## Firewall And Listeners
EOF
run_capture_shell "sudo -n ufw status verbose" 'sudo -n ufw status verbose || true'
run_capture_shell "sudo -n ss -tulpn || ss -tulpn" 'sudo -n ss -tulpn || ss -tulpn || true'

cat >> "$REPORT_PATH" <<'EOF'

## System Health
EOF
run_capture "systemctl --failed --no-pager" systemctl --failed --no-pager
run_capture "journalctl -b -p err -n 100 --no-pager" journalctl -b -p err -n 100 --no-pager

cat >> "$REPORT_PATH" <<EOF

## Scope Confirmation

- No disk, partition, filesystem, mount, or fstab changes were made.
- /dev/sdb was not initialized, partitioned, formatted, mounted, or otherwise modified.
- /data was not created, mounted, initialized, or modified.
- Docker was not installed or configured.
- NVIDIA drivers or toolkit were not installed or configured.
- systemd was not configured.
- No API was exposed.
- No models were downloaded.
- No secrets, tokens, passwords, private keys, auth files, real .env files, MEMORY.md, or local Codex memory files were read or written.

## Conclusion

${CONCLUSION}
EOF

if [[ "$CONCLUSION" == "PASS" ]]; then
  cat >> "$REPORT_PATH" <<'EOF'

The VM preflight completed. Critical checks for Codex availability and non-interactive sudo passed. Review warnings and raw command output before M2.
EOF
else
  cat >> "$REPORT_PATH" <<'EOF'

The VM preflight reached a STOP condition. Do not proceed to destructive milestones until the stop reasons are resolved.
EOF
fi

cat >> "$REPORT_PATH" <<'EOF'

## Next Recommended Milestone

M2 data disk dry-run.
EOF

if [[ "$CONCLUSION" == "PASS" ]]; then
  exit 0
fi
exit 1
