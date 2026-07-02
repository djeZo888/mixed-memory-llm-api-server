#!/usr/bin/env bash
set -euo pipefail

EXPECTED_LABEL="AI_DATA"
EXPECTED_UUID="8daf56f1-5649-4163-9d87-919c2d271875"
DATA_PATH="/data"

usage() {
  cat <<'EOF'
Usage: scripts/common/require-data-mounted.sh [--help]

Read-only guard that verifies /data is mounted, separate from /, and has the
expected AI data layout before any heavy AI-server work runs.
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

stop() {
  echo "STOP: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

blkid_value() {
  local key="$1"
  local source="$2"
  local value
  value=$(blkid -s "$key" -o value "$source" 2>/dev/null || true)
  if [[ -z "$value" ]] && sudo -n true 2>/dev/null; then
    value=$(sudo -n blkid -s "$key" -o value "$source" 2>/dev/null || true)
  fi
  printf '%s' "$value"
}

[[ -e "$DATA_PATH" ]] || stop "$DATA_PATH does not exist"
findmnt -rn --target "$DATA_PATH" >/dev/null || stop "$DATA_PATH is not mounted"

ROOT_SOURCE=$(findmnt -rn -o SOURCE --target /)
DATA_SOURCE=$(findmnt -rn -o SOURCE --target "$DATA_PATH")
DATA_FSTYPE=$(findmnt -rn -o FSTYPE --target "$DATA_PATH")

[[ -n "$ROOT_SOURCE" ]] || stop "could not determine root filesystem source"
[[ -n "$DATA_SOURCE" ]] || stop "could not determine /data filesystem source"
[[ "$ROOT_SOURCE" != "$DATA_SOURCE" ]] || stop "/data source equals root source"

ROOT_DEV_ID=$(stat -fc '%d' /)
DATA_DEV_ID=$(stat -fc '%d' "$DATA_PATH")
[[ "$ROOT_DEV_ID" != "$DATA_DEV_ID" ]] || stop "/data is the same filesystem as /"

LABEL=$(blkid_value LABEL "$DATA_SOURCE")
if [[ -n "$LABEL" ]]; then
  [[ "$LABEL" == "$EXPECTED_LABEL" ]] || stop "/data label is $LABEL, expected $EXPECTED_LABEL"
else
  warn "could not determine /data filesystem label"
fi

UUID=$(blkid_value UUID "$DATA_SOURCE")
if [[ -n "$UUID" ]]; then
  [[ "$UUID" == "$EXPECTED_UUID" ]] || stop "/data UUID is $UUID, expected $EXPECTED_UUID"
else
  warn "could not determine /data filesystem UUID"
fi

required_dirs=(
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
  [[ -d "$path" ]] || stop "required directory missing: $path"
done

cat <<EOF
PASS: /data is mounted and ready
- root source: $ROOT_SOURCE
- data source: $DATA_SOURCE
- data fstype: $DATA_FSTYPE
- data label: ${LABEL:-unknown}
- data UUID: ${UUID:-unknown}
EOF

