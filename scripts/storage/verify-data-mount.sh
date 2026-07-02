#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="reports/m2-data-disk-setup.md"

usage() {
  cat <<'EOF'
Usage: scripts/storage/verify-data-mount.sh [--help]

Run read-only verification for the M2A /data setup and append results to
reports/m2-data-disk-setup.md.
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
    return "${statuses[0]}"
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
    return "${statuses[0]}"
  } >> "$REPORT_PATH"
}

fail() {
  local reason="$1"
  printf '\n## M2A Read-Only Verification Conclusion\n\nSTOP\n\nReason: %s\n' "$reason" >> "$REPORT_PATH"
  echo "STOP: ${reason}" >&2
  exit 1
}

append_header() {
  cat >> "$REPORT_PATH" <<EOF

## M2A Read-Only Verification

- Timestamp: $(date -Is)
- Hostname: $(hostname 2>/dev/null || printf unknown)
- User: $(whoami 2>/dev/null || printf unknown)
- Branch: $(git branch --show-current 2>/dev/null || printf unknown)
EOF
}

verify_dir() {
  local path="$1"
  local owner="$2"
  local group="$3"
  local mode="$4"
  [[ -d "$path" ]] || fail "required directory missing: ${path}"
  local actual_owner actual_group actual_mode
  actual_owner=$(stat -c '%U' "$path")
  actual_group=$(stat -c '%G' "$path")
  actual_mode=$(stat -c '%a' "$path")
  [[ "$actual_owner" == "$owner" ]] || fail "${path} owner ${actual_owner}, expected ${owner}"
  [[ "$actual_group" == "$group" ]] || fail "${path} group ${actual_group}, expected ${group}"
  [[ "$actual_mode" == "$mode" ]] || fail "${path} mode ${actual_mode}, expected ${mode}"
}

append_header
run_capture "findmnt /data" findmnt /data || fail "/data is not mounted"
DATA_SOURCE=$(findmnt -n -o SOURCE /data)
ROOT_SOURCE=$(findmnt -n -o SOURCE /)
[[ -n "$DATA_SOURCE" ]] || fail "could not determine /data source"
[[ "$DATA_SOURCE" != "$ROOT_SOURCE" ]] || fail "/data source equals root source"
DATA_DEV_ID=$(stat -fc '%d' /data)
ROOT_DEV_ID=$(stat -fc '%d' /)
[[ "$DATA_DEV_ID" != "$ROOT_DEV_ID" ]] || fail "/data and / are the same filesystem"
LABEL=$(sudo -n blkid -s LABEL -o value "$DATA_SOURCE" 2>/dev/null || true)
[[ "$LABEL" == "AI_DATA" ]] || fail "/data label is ${LABEL:-missing}, expected AI_DATA"
run_capture_shell "fstab active /data entry" "grep -E '^[[:space:]]*UUID=[^[:space:]]+[[:space:]]+/data[[:space:]]+ext4[[:space:]]+' /etc/fstab" || fail "/etc/fstab lacks active /data UUID entry"
if grep -Eq '^[[:space:]]*/dev/sdb1[[:space:]]+/data[[:space:]]+' /etc/fstab; then
  fail "/etc/fstab uses /dev/sdb1 instead of UUID"
fi
run_capture "df -hT / /data" df -hT / /data
run_capture "lsblk verification" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
run_capture_shell "root and data source summary" "printf 'root=%s\ndata=%s\n' '$ROOT_SOURCE' '$DATA_SOURCE'"

required_dirs=(
  /data
  /data/models
  /data/hf-cache
  /data/hf-cache/hub
  /data/hf-cache/xet
  /data/hf-cache/assets
  /data/hf-cache/datasets
  /data/hf-cache/transformers
  /data/hf-cache/xdg
  /data/docker
  /data/containerd
  /data/services
  /data/build
  /data/logs
  /data/backups
  /data/services/secrets
)
for path in "${required_dirs[@]}"; do
  [[ -d "$path" ]] || fail "required directory missing: ${path}"
done

verify_dir /data root root 755
verify_dir /data/models user ai 2775
verify_dir /data/hf-cache user ai 2775
verify_dir /data/hf-cache/hub user ai 2775
verify_dir /data/hf-cache/xet user ai 2775
verify_dir /data/hf-cache/assets user ai 2775
verify_dir /data/hf-cache/datasets user ai 2775
verify_dir /data/hf-cache/transformers user ai 2775
verify_dir /data/hf-cache/xdg user ai 2775
verify_dir /data/docker root root 711
verify_dir /data/containerd root root 711
verify_dir /data/services user ai 2775
verify_dir /data/build user ai 2775
verify_dir /data/logs user ai 2775
verify_dir /data/backups user ai 2775
verify_dir /data/services/secrets user ai 2770
run_capture_shell "directory permission verification summary" "stat -c '%A %a %U:%G %n' ${required_dirs[*]}"
run_capture_shell "AI data env vars in login shell" "bash -lc \"env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort\""

expected_env=(
  AI_DATA=/data
  HF_HOME=/data/hf-cache
  HF_HUB_CACHE=/data/hf-cache/hub
  HF_XET_CACHE=/data/hf-cache/xet
  HF_ASSETS_CACHE=/data/hf-cache/assets
  HF_DATASETS_CACHE=/data/hf-cache/datasets
  TRANSFORMERS_CACHE=/data/hf-cache/transformers
  XDG_CACHE_HOME=/data/hf-cache/xdg
  AI_BUILD_DIR=/data/build
  AI_LOG_DIR=/data/logs
)
for item in "${expected_env[@]}"; do
  bash -lc "env" | grep -Fxq "$item" || fail "login shell missing env var: ${item}"
done

cat >> "$REPORT_PATH" <<'EOF'

## M2A Read-Only Verification Conclusion

PASS

/data mount, UUID fstab entry, AI_DATA label, directory permissions, and AI/Hugging Face environment variables verified. Reboot verification is still required.
EOF

echo "PASS: verified /data mount"
