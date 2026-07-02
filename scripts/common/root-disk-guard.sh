#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

REPORT_PATH="reports/m3-root-disk-guard.md"
ROOT_PATH="/"
DATA_PATH="/data"
MIN_ROOT_FREE_GIB=4
WARN_ROOT_FREE_GIB=6
WARN_PATH_MIB=512
FAIL_PATH_MIB=2048
LARGE_FILE_MIB=128
SKIP_MOUNT_CHECK=0
NO_SUDO=0
SUDO_AVAILABLE=0
TEST_MODE=0

warnings=()
stops=()
path_rows=()
large_file_rows=()
secret_rows=()

usage() {
  cat <<'EOF'
Usage: scripts/common/root-disk-guard.sh [options]

Read-only guard that checks whether AI-server data is leaking onto the small
root filesystem.

Options:
  --help                         Show this help text.
  --report PATH                  Markdown report path.
  --root-path PATH               Root path to inspect. Default: /.
  --data-path PATH               Data path to exclude/verify. Default: /data.
  --min-root-free-gib N          STOP below this free-space threshold. Default: 4.
  --warn-root-free-gib N         WARN below this free-space threshold. Default: 6.
  --warn-path-mib N              WARN when high-risk path reaches this size. Default: 512.
  --fail-path-mib N              STOP when high-risk path reaches this size. Default: 2048.
  --large-file-mib N             STOP for suspicious files above this size. Default: 128.
  --skip-mount-check-for-tests   Skip /data mount checks for fixture tests.
  --no-sudo                      Do not use sudo for read-only inspection.
EOF
}

add_warning() {
  warnings+=("$*")
}

add_stop() {
  stops+=("$*")
}

is_abs() {
  [[ "$1" == /* ]]
}

parse_positive_int() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo "STOP: $name must be a non-negative integer" >&2
    exit 2
  }
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
    --root-path)
      [[ $# -ge 2 ]] || { echo "STOP: --root-path requires a path" >&2; exit 2; }
      ROOT_PATH="$2"
      shift 2
      ;;
    --data-path)
      [[ $# -ge 2 ]] || { echo "STOP: --data-path requires a path" >&2; exit 2; }
      DATA_PATH="$2"
      shift 2
      ;;
    --min-root-free-gib)
      [[ $# -ge 2 ]] || { echo "STOP: --min-root-free-gib requires a value" >&2; exit 2; }
      parse_positive_int "$1" "$2"
      MIN_ROOT_FREE_GIB="$2"
      shift 2
      ;;
    --warn-root-free-gib)
      [[ $# -ge 2 ]] || { echo "STOP: --warn-root-free-gib requires a value" >&2; exit 2; }
      parse_positive_int "$1" "$2"
      WARN_ROOT_FREE_GIB="$2"
      shift 2
      ;;
    --warn-path-mib)
      [[ $# -ge 2 ]] || { echo "STOP: --warn-path-mib requires a value" >&2; exit 2; }
      parse_positive_int "$1" "$2"
      WARN_PATH_MIB="$2"
      shift 2
      ;;
    --fail-path-mib)
      [[ $# -ge 2 ]] || { echo "STOP: --fail-path-mib requires a value" >&2; exit 2; }
      parse_positive_int "$1" "$2"
      FAIL_PATH_MIB="$2"
      shift 2
      ;;
    --large-file-mib)
      [[ $# -ge 2 ]] || { echo "STOP: --large-file-mib requires a value" >&2; exit 2; }
      parse_positive_int "$1" "$2"
      LARGE_FILE_MIB="$2"
      shift 2
      ;;
    --skip-mount-check-for-tests)
      SKIP_MOUNT_CHECK=1
      TEST_MODE=1
      shift
      ;;
    --no-sudo)
      NO_SUDO=1
      shift
      ;;
    *)
      echo "STOP: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

is_abs "$ROOT_PATH" || { echo "STOP: --root-path must be absolute" >&2; exit 2; }
is_abs "$DATA_PATH" || { echo "STOP: --data-path must be absolute" >&2; exit 2; }
[[ -d "$ROOT_PATH" ]] || { echo "STOP: root path does not exist: $ROOT_PATH" >&2; exit 2; }

run_readonly() {
  if [[ "$SUDO_AVAILABLE" -eq 1 ]]; then
    sudo -n "$@"
  else
    "$@"
  fi
}

capture_cmd() {
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
  } >> "$REPORT_PATH"
}

root_join() {
  local rel="${1#/}"
  if [[ "$ROOT_PATH" == "/" ]]; then
    printf '/%s' "$rel"
  else
    printf '%s/%s' "${ROOT_PATH%/}" "$rel"
  fi
}

display_path() {
  local path="$1"
  if [[ "$ROOT_PATH" == "/" ]]; then
    printf '%s' "$path"
  else
    local prefix="${ROOT_PATH%/}"
    if [[ "$path" == "$prefix" ]]; then
      printf '/'
    elif [[ "$path" == "$prefix/"* ]]; then
      printf '/%s' "${path#"$prefix/"}"
    else
      printf '%s' "$path"
    fi
  fi
}

path_mib() {
  local path="$1"
  local output
  if output=$(run_readonly du -sx -m "$path" 2>/dev/null); then
    awk '{print $1}' <<<"$output"
    return 0
  fi
  return 1
}

root_free_gib() {
  local path="$1"
  local avail_bytes
  avail_bytes=$(df -P -B1 "$path" | awk 'NR==2 {print $4}')
  awk -v bytes="$avail_bytes" 'BEGIN { printf "%.0f", bytes / 1024 / 1024 / 1024 }'
}

source_for_path() {
  local path="$1"
  findmnt -rn -o SOURCE --target "$path" 2>/dev/null || true
}

fstype_for_path() {
  local path="$1"
  findmnt -rn -o FSTYPE --target "$path" 2>/dev/null || true
}

blkid_value() {
  local key="$1"
  local source="$2"
  local value
  value=$(blkid -s "$key" -o value "$source" 2>/dev/null || true)
  if [[ -z "$value" && "$SUDO_AVAILABLE" -eq 1 ]]; then
    value=$(sudo -n blkid -s "$key" -o value "$source" 2>/dev/null || true)
  fi
  printf '%s' "$value"
}

check_sudo() {
  if [[ "$NO_SUDO" -eq 1 || "$TEST_MODE" -eq 1 ]]; then
    SUDO_AVAILABLE=0
    return
  fi
  sudo -k 2>/dev/null || true
  if sudo -n true 2>/dev/null; then
    SUDO_AVAILABLE=1
  else
    SUDO_AVAILABLE=0
    add_warning "sudo -n was unavailable; unreadable root paths were inspected with reduced coverage"
  fi
}

check_mounts() {
  if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then
    add_warning "/data mount check skipped for fixture test mode"
    return
  fi

  if ! "$SCRIPT_DIR/require-data-mounted.sh" >/tmp/root-disk-guard-require-data-mounted.out 2>/tmp/root-disk-guard-require-data-mounted.err; then
    add_stop "require-data-mounted.sh failed; /data is missing, not mounted, or not ready"
    return
  fi

  local root_dev data_dev data_source data_label data_uuid
  root_dev=$(stat -fc '%d' "$ROOT_PATH")
  data_dev=$(stat -fc '%d' "$DATA_PATH")
  [[ "$root_dev" != "$data_dev" ]] || add_stop "$DATA_PATH is the same filesystem as $ROOT_PATH"

  data_source=$(source_for_path "$DATA_PATH")
  data_label=$(blkid_value LABEL "$data_source")
  data_uuid=$(blkid_value UUID "$data_source")
  [[ -z "$data_label" || "$data_label" == "AI_DATA" ]] || add_stop "$DATA_PATH label is $data_label, expected AI_DATA"
  [[ -z "$data_uuid" || "$data_uuid" == "8daf56f1-5649-4163-9d87-919c2d271875" ]] || add_stop "$DATA_PATH UUID is $data_uuid, expected 8daf56f1-5649-4163-9d87-919c2d271875"
}

check_required_data_dirs() {
  if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then
    return
  fi

  local dirs=(
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

  local path
  for path in "${dirs[@]}"; do
    [[ -d "$path" ]] || add_stop "required /data directory missing: $path"
  done
}

check_env() {
  if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then
    return
  fi

  local expected=(
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
  local item
  for item in "${expected[@]}"; do
    if ! bash -lc "env" | grep -Fxq "$item"; then
      add_stop "login shell missing expected environment variable: $item"
    fi
  done
}

inspect_high_risk_paths() {
  local rel_paths=(
    /var/lib/docker
    /var/lib/containerd
    /var/lib/containers
    /root/.cache
    /root/.cache/huggingface
    /root/.cache/torch
    /root/.cache/pip
    /home/user/.cache
    /home/user/.cache/huggingface
    /home/user/.cache/torch
    /home/user/.cache/pip
    /home/user/.cache/pypoetry
    /home/user/.cache/uv
    /home/user/.cache/nvidia
    /home/user/codex-bootstrap
    /tmp
    /var/tmp
    /var/log
    /opt
    /srv
    /models
    /hf-cache
    /docker
    /containerd
    /build
    /logs
  )

  local rel path size status note display
  for rel in "${rel_paths[@]}"; do
    path=$(root_join "$rel")
    display=$(display_path "$path")
    if [[ ! -e "$path" ]]; then
      path_rows+=("| \`$display\` | no | 0 | PASS | absent |")
      continue
    fi

    if ! size=$(path_mib "$path"); then
      path_rows+=("| \`$display\` | yes | unknown | WARN | unreadable |")
      add_warning "could not read high-risk path: $display"
      continue
    fi

    status="PASS"
    note="below warning threshold"
    if (( size >= FAIL_PATH_MIB )); then
      status="STOP"
      note="size exceeds fail threshold"
      add_stop "$display is ${size} MiB, at or above fail threshold ${FAIL_PATH_MIB} MiB"
    elif (( size >= WARN_PATH_MIB )); then
      status="WARN"
      note="size exceeds warning threshold"
      add_warning "$display is ${size} MiB, at or above warning threshold ${WARN_PATH_MIB} MiB"
    elif [[ "$display" == "/home/user/codex-bootstrap" && "$size" -gt 0 ]]; then
      status="WARN"
      note="expected old bootstrap repo; small"
      add_warning "$display exists and is small"
    fi
    path_rows+=("| \`$display\` | yes | $size | $status | $note |")
  done

  local old_data
  while IFS= read -r old_data; do
    [[ -n "$old_data" ]] || continue
    display=$(display_path "$old_data")
    if ! size=$(path_mib "$old_data"); then
      path_rows+=("| \`$display\` | yes | unknown | WARN | unreadable old /data backup |")
      add_warning "could not read old /data backup: $display"
      continue
    fi
    status="PASS"
    note="expected M2 backup and below warning threshold"
    if (( size >= FAIL_PATH_MIB )); then
      status="STOP"
      note="old /data backup exceeds fail threshold"
      add_stop "$display is ${size} MiB, at or above fail threshold ${FAIL_PATH_MIB} MiB"
    elif (( size >= WARN_PATH_MIB )); then
      status="WARN"
      note="old /data backup exceeds warning threshold"
      add_warning "$display is ${size} MiB, at or above warning threshold ${WARN_PATH_MIB} MiB"
    else
      status="WARN"
      add_warning "$display exists and is small"
    fi
    path_rows+=("| \`$display\` | yes | $size | $status | $note |")
  done < <(compgen -G "$(root_join /data.pre-mount-root-*)" || true)
}

high_risk_scan_roots() {
  local rel_paths=(
    /var/lib/docker
    /var/lib/containerd
    /var/lib/containers
    /root/.cache
    /home/user/.cache
    /home/user/codex-bootstrap
    /tmp
    /var/tmp
    /var/log
    /opt
    /srv
    /models
    /hf-cache
    /docker
    /containerd
    /build
    /logs
  )

  local rel path old_data
  for rel in "${rel_paths[@]}"; do
    path=$(root_join "$rel")
    [[ -e "$path" ]] && printf '%s\n' "$path"
  done
  while IFS= read -r old_data; do
    [[ -n "$old_data" ]] && printf '%s\n' "$old_data"
  done < <(compgen -G "$(root_join /data.pre-mount-root-*)" || true)
}

find_prune_args() {
  local -n out_ref=$1
  local prune_paths=(
    "$DATA_PATH"
    "$(root_join /data)"
    "$(root_join /proc)"
    "$(root_join /sys)"
    "$(root_join /dev)"
    "$(root_join /run)"
    "$(root_join /mnt)"
    "$(root_join /media)"
    "$(root_join /snap)"
    "$(root_join /tmp/systemd-private-*)"
  )

  local path
  out_ref=()
  for path in "${prune_paths[@]}"; do
    out_ref+=( -path "$path" -o )
  done
  unset 'out_ref[${#out_ref[@]}-1]'
}

scan_large_files() {
  local prunes=()
  find_prune_args prunes

  local find_cmd=(
    find "$ROOT_PATH" -xdev
    '(' "${prunes[@]}" ')' -prune -o
    -type f
    '('
      -iname '*.gguf' -o
      -iname '*.safetensors' -o
      -iname '*.bin' -o
      -iname '*.pt' -o
      -iname '*.pth' -o
      -iname '*.ckpt' -o
      -iname '*.onnx' -o
      -iname '*.engine' -o
      -iname '*.tar' -o
      -iname '*.tar.gz' -o
      -iname '*.tgz' -o
      -iname '*.zip' -o
      -iname '*.zst' -o
      -iname '*.parquet' -o
      -iname 'pytorch_model*' -o
      -iname 'model-*' -o
      -iname 'tokenizer*' -o
      -iname 'consolidated*' -o
      -iname '*.arrow'
    ')'
    -size +"${LARGE_FILE_MIB}"M
    -printf '%s\t%p\n'
  )

  local output
  if ! output=$(run_readonly "${find_cmd[@]}" 2>/dev/null); then
    add_warning "suspicious large file scan had unreadable paths or reduced coverage"
    return
  fi

  local size path mib display
  while IFS=$'\t' read -r size path; do
    [[ -n "${path:-}" ]] || continue
    mib=$(( (size + 1024 * 1024 - 1) / 1024 / 1024 ))
    display=$(display_path "$path")
    large_file_rows+=("| \`$display\` | $mib | STOP | suspicious model/cache/archive pattern on root |")
    add_stop "suspicious large file on root: $display (${mib} MiB)"
  done <<<"$output"
}

scan_secret_names() {
  local scan_root output path display
  while IFS= read -r scan_root; do
    [[ -n "$scan_root" && -e "$scan_root" ]] || continue
    if ! output=$(run_readonly find "$scan_root" -xdev -type f '(' \
      -name id_ed25519 -o \
      -name 'id_ed25519.pub' -o \
      -name id_rsa -o \
      -name 'id_rsa.pub' -o \
      -name '*.pem' -o \
      -name '*.key' -o \
      -name auth.json -o \
      -name '.env' \
      ')' -printf '%p\n' 2>/dev/null); then
      add_warning "secret-looking filename scan had unreadable paths or reduced coverage under $(display_path "$scan_root")"
      continue
    fi
    while IFS= read -r path; do
      [[ -n "$path" ]] || continue
      display=$(display_path "$path")
      secret_rows+=("| \`$display\` | STOP | secret-looking filename in high-risk root path |")
      add_stop "secret-looking file path found in high-risk root path: $display"
    done <<<"$output"
  done < <(high_risk_scan_roots)
}

write_report_header() {
  mkdir -p "$(dirname "$REPORT_PATH")"
  cat > "$REPORT_PATH" <<EOF
# M3 Root-Disk Guard Report

- Milestone ID: M3
- Timestamp: $(date -Is)
- Hostname: $(hostname 2>/dev/null || printf unknown)
- User: $(whoami 2>/dev/null || printf unknown)
- Branch: $(git branch --show-current 2>/dev/null || printf unknown)
- Commit before work: $(git rev-parse HEAD 2>/dev/null || printf unknown)
- Root path inspected: \`$ROOT_PATH\`
- Data path checked/excluded: \`$DATA_PATH\`
- Sudo coverage: $(if [[ "$SUDO_AVAILABLE" -eq 1 ]]; then printf 'sudo -n available for read-only inspection'; else printf 'non-sudo or reduced coverage'; fi)
- Confirmation: no cleanup or destructive changes were made.
- Confirmation: no Docker, NVIDIA, model, inference backend, systemd service, or API changes were made.
EOF
}

write_report_body() {
  local root_source data_source data_label data_uuid root_free data_free root_fstype data_fstype conclusion
  root_source=$(source_for_path "$ROOT_PATH")
  root_fstype=$(fstype_for_path "$ROOT_PATH")
  if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then
    data_source="skipped fixture mode"
    data_fstype="skipped fixture mode"
    data_label="skipped fixture mode"
    data_uuid="skipped fixture mode"
  else
    data_source=$(source_for_path "$DATA_PATH")
    data_fstype=$(fstype_for_path "$DATA_PATH")
    data_label=$(blkid_value LABEL "$data_source")
    data_uuid=$(blkid_value UUID "$data_source")
  fi
  root_free=$(root_free_gib "$ROOT_PATH")
  if [[ -d "$DATA_PATH" ]]; then
    data_free=$(root_free_gib "$DATA_PATH")
  else
    data_free="unknown"
  fi

  if (( root_free < MIN_ROOT_FREE_GIB )); then
    add_stop "root free space is ${root_free} GiB, below minimum ${MIN_ROOT_FREE_GIB} GiB"
  elif (( root_free < WARN_ROOT_FREE_GIB )); then
    add_warning "root free space is ${root_free} GiB, below warning threshold ${WARN_ROOT_FREE_GIB} GiB"
  fi

  {
    cat <<EOF

## Mount Summary

| Path | Source | Fstype | Label | UUID/identity | Free GiB |
| --- | --- | --- | --- | --- | --- |
| \`$ROOT_PATH\` | \`${root_source:-unknown}\` | \`${root_fstype:-unknown}\` | n/a | device id \`$(stat -fc '%d' "$ROOT_PATH")\` | $root_free |
| \`$DATA_PATH\` | \`${data_source:-unknown}\` | \`${data_fstype:-unknown}\` | \`${data_label:-unknown}\` | \`${data_uuid:-unknown}\` | $data_free |

## Root Free Space Thresholds

- Minimum root free space: ${MIN_ROOT_FREE_GIB} GiB
- Warning root free space: ${WARN_ROOT_FREE_GIB} GiB
- High-risk path warning: ${WARN_PATH_MIB} MiB
- High-risk path failure: ${FAIL_PATH_MIB} MiB
- Suspicious large file failure: ${LARGE_FILE_MIB} MiB

## /data Identity Check

$(if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then printf 'Skipped for fixture test mode.'; else printf '`/data` is mounted and has a different filesystem identity from `/`.'; fi)

## /data Required Directory Check

$(if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then printf 'Skipped for fixture test mode.'; else printf 'Required `/data` directories were checked by `require-data-mounted.sh`.'; fi)

## Hugging Face Environment Check

$(if [[ "$SKIP_MOUNT_CHECK" -eq 1 ]]; then printf 'Skipped for fixture test mode.'; else printf 'AI and Hugging Face environment variables were checked in a fresh login shell.'; fi)

## Inspected High-Risk Root Paths

| Path | Exists | MiB | Status | Note |
| --- | --- | ---: | --- | --- |
EOF
    printf '%s\n' "${path_rows[@]}"
    cat <<'EOF'

## Suspicious Large File Scan

| Path | MiB | Status | Category |
| --- | ---: | --- | --- |
EOF
    if [[ "${#large_file_rows[@]}" -eq 0 ]]; then
      printf '| none | 0 | PASS | no suspicious large model/cache/archive files found on root |\n'
    else
      printf '%s\n' "${large_file_rows[@]}"
    fi
    cat <<'EOF'

## Secret-Looking Filename Scan

| Path | Status | Category |
| --- | --- | --- |
EOF
    if [[ "${#secret_rows[@]}" -eq 0 ]]; then
      printf '| none | PASS | no secret-looking filenames found in scanned root paths |\n'
    else
      printf '%s\n' "${secret_rows[@]}"
    fi
    cat <<'EOF'

## WARN Entries

EOF
    if [[ "${#warnings[@]}" -eq 0 ]]; then
      printf -- '- None.\n'
    else
      local warning
      for warning in "${warnings[@]}"; do
        printf -- '- %s\n' "$warning"
      done
    fi
    cat <<'EOF'

## STOP Entries

EOF
    if [[ "${#stops[@]}" -eq 0 ]]; then
      printf -- '- None.\n'
    else
      local stop
      for stop in "${stops[@]}"; do
        printf -- '- %s\n' "$stop"
      done
    fi
  } >> "$REPORT_PATH"

  if [[ "${#stops[@]}" -eq 0 ]]; then
    conclusion="PASS"
  else
    conclusion="STOP"
  fi

  cat >> "$REPORT_PATH" <<EOF

## Tests And Checks Run

- \`scripts/common/root-disk-guard.sh --report $REPORT_PATH\`
- Additional milestone checks are appended after command execution.

## Conclusion

$conclusion

## Next Recommended Milestone

M4 Docker/containerd storage.
EOF

  echo "$conclusion"
}

main() {
  check_sudo
  check_mounts
  check_required_data_dirs
  check_env
  inspect_high_risk_paths
  scan_large_files
  scan_secret_names
  write_report_header
  capture_cmd "findmnt root summary" findmnt "$ROOT_PATH"
  if [[ "$SKIP_MOUNT_CHECK" -eq 0 ]]; then
    capture_cmd "findmnt /data summary" findmnt "$DATA_PATH"
    capture_cmd "df -hT / /data" df -hT / /data
    capture_cmd "AI/Hugging Face env vars" bash -lc "env | grep -E '^(AI_DATA|HF_HOME|HF_HUB_CACHE|HF_XET_CACHE|HF_ASSETS_CACHE|HF_DATASETS_CACHE|TRANSFORMERS_CACHE|XDG_CACHE_HOME|AI_BUILD_DIR|AI_LOG_DIR)=' | sort"
  else
    capture_cmd "df -hT fixture root/data" df -hT "$ROOT_PATH" "$DATA_PATH"
  fi
  local conclusion
  conclusion=$(write_report_body)
  if [[ "$conclusion" == "PASS" ]]; then
    echo "PASS: root disk guard passed"
    exit 0
  fi
  echo "STOP: root disk guard failed" >&2
  exit 1
}

main
