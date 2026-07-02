#!/usr/bin/env bash
set -euo pipefail

ROOT_GUARD="scripts/common/root-disk-guard.sh"
REQUIRE_DATA="scripts/common/require-data-mounted.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$ROOT_GUARD" ]] || fail "$ROOT_GUARD missing"
[[ -x "$ROOT_GUARD" ]] || fail "$ROOT_GUARD is not executable"
[[ -f "$REQUIRE_DATA" ]] || fail "$REQUIRE_DATA missing"
[[ -x "$REQUIRE_DATA" ]] || fail "$REQUIRE_DATA is not executable"

grep -q 'set -euo pipefail' "$ROOT_GUARD" || fail "$ROOT_GUARD lacks set -euo pipefail"
grep -q 'set -euo pipefail' "$REQUIRE_DATA" || fail "$REQUIRE_DATA lacks set -euo pipefail"

"$ROOT_GUARD" --help >/dev/null
"$REQUIRE_DATA" --help >/dev/null

for option in --root-path --data-path --report --skip-mount-check-for-tests; do
  grep -q -- "$option" "$ROOT_GUARD" || fail "$ROOT_GUARD missing $option"
done

grep -Eq 'find[[:space:]].*(-xdev|-mount)' "$ROOT_GUARD" || fail "$ROOT_GUARD must use find -xdev or find -mount"

destructive_patterns=(
  'rm -rf'
  'mkfs'
  'wipefs'
  'sgdisk'
  'parted'
  'fdisk'
  'mount /data'
  'umount'
  'systemctl restart'
  'systemctl stop'
  'docker pull'
  'docker run'
  'huggingface-cli download'
  'git clean -fdx'
)

for pattern in "${destructive_patterns[@]}"; do
  if grep -Fq "$pattern" "$ROOT_GUARD" "$REQUIRE_DATA"; then
    fail "destructive pattern found in guard scripts: $pattern"
  fi
done

if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$ROOT_GUARD" "$REQUIRE_DATA"; then
  fail "hard-coded secret-like content found"
fi

echo "PASS: root-disk guard static checks"

