#!/usr/bin/env bash
set -euo pipefail

SCRIPT="scripts/preflight/vm-preflight.sh"
REPORT="reports/m1-vm-preflight.md"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$SCRIPT" ]] || fail "$SCRIPT does not exist"
[[ -x "$SCRIPT" ]] || fail "$SCRIPT is not executable"
grep -Fq 'set -euo pipefail' "$SCRIPT" || fail "$SCRIPT does not use set -euo pipefail"
"$SCRIPT" --help >/dev/null || fail "$SCRIPT --help failed"
grep -Fq "$REPORT" "$SCRIPT" || fail "$SCRIPT does not write $REPORT"

forbidden_patterns=(
  '(^|[^[:alnum:]_-])mkfs([.[:space:]]|$)'
  '(^|[^[:alnum:]_-])parted([[:space:]]|$)'
  '(^|[^[:alnum:]_-])sgdisk([[:space:]]|$)'
  '(^|[^[:alnum:]_-])wipefs([[:space:]]|$)'
  '(^|[;&|[:space:]])mount[[:space:]]+/data([[:space:]]|$)'
  '([>]{1,2}[[:space:]]*/etc/fstab|tee[[:space:]]+(-a[[:space:]]+)?/etc/fstab|sed[[:space:]]+-i[^\n]*/etc/fstab|perl[[:space:]]+-pi[^\n]*/etc/fstab)'
  'apt(-get)?[[:space:]].*install'
  'docker[[:space:]].*install|install[[:space:]].*docker'
  'nvidia-driver|ubuntu-drivers|install[[:space:]].*nvidia'
  'huggingface-cli[[:space:]]+download|(^|[;&|[:space:]])hf[[:space:]]+download|wget[[:space:]]|aria2c[[:space:]]'
)

for pattern in "${forbidden_patterns[@]}"; do
  if grep -EIn -- "$pattern" "$SCRIPT"; then
    fail "$SCRIPT contains forbidden destructive/install/download pattern: $pattern"
  fi
done

echo "PASS: vm-preflight static validation"
