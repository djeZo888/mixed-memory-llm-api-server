#!/usr/bin/env bash
set -euo pipefail

PREPARE="scripts/storage/prepare-data-disk.sh"
VERIFY="scripts/storage/verify-data-mount.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$PREPARE" ]] || fail "$PREPARE does not exist"
[[ -x "$PREPARE" ]] || fail "$PREPARE is not executable"
[[ -f "$VERIFY" ]] || fail "$VERIFY does not exist"
[[ -x "$VERIFY" ]] || fail "$VERIFY is not executable"
grep -Fq 'set -euo pipefail' "$PREPARE" || fail "$PREPARE missing set -euo pipefail"
grep -Fq 'set -euo pipefail' "$VERIFY" || fail "$VERIFY missing set -euo pipefail"
"$PREPARE" --help >/dev/null || fail "$PREPARE --help failed"
"$VERIFY" --help >/dev/null || fail "$VERIFY --help failed"
"$PREPARE" --dry-run --unexpected >/dev/null 2>&1 && fail "$PREPARE accepted extra args after --dry-run"
grep -Fq -- '--dry-run' "$PREPARE" || fail "$PREPARE lacks --dry-run support"
grep -Fq -- '--yes-format-verified-data-disk /dev/sdb' "$PREPARE" || fail "$PREPARE lacks exact actual-run flag text"

for needle in \
  'root disk' \
  '/boot' \
  '/boot/efi' \
  'mounted' \
  'filesystem signature' \
  'existing partitions' \
  'LVM' \
  'Multiple possible 2 TB data-disk candidates'; do
  grep -Fq "$needle" "$PREPARE" || fail "$PREPARE missing safety check text: $needle"
done

if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$PREPARE" "$VERIFY"; then
  fail "script appears to contain hard-coded secret material"
fi

python3 - "$VERIFY" <<'PY_CHECK'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
heredoc = None
violations = []
destructive = re.compile(r"^\s*(sudo\s+)?(mkfs(\.[^\s]+)?|wipefs|sgdisk|sfdisk|parted|fdisk|mount|umount|groupadd|usermod|chown|chmod|mkdir|mv|tee)(\s|$)")
fstab_edit = re.compile(r"(>\s*/etc/fstab|>>\s*/etc/fstab|tee\s+(-a\s+)?/etc/fstab|sed\s+-i[^\n]*/etc/fstab|perl\s+-pi[^\n]*/etc/fstab)")
heredoc_start = re.compile(r"<<[-]?['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")

for number, line in enumerate(lines, start=1):
    stripped = line.strip()
    if heredoc:
        if stripped == heredoc:
            heredoc = None
        continue
    match = heredoc_start.search(line)
    if match:
        heredoc = match.group(1)
        continue
    if not stripped or stripped.startswith('#'):
        continue
    if destructive.search(line):
        violations.append(f"{number}: destructive command in verify script: {line}")
    if fstab_edit.search(line):
        violations.append(f"{number}: fstab edit in verify script: {line}")

if violations:
    print("\n".join(violations))
    sys.exit(1)
PY_CHECK

echo "PASS: prepare-data-disk static validation"
