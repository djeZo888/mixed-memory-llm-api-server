#!/usr/bin/env bash
set -euo pipefail

SCRIPT="scripts/preflight/disk-dry-run.sh"
REPORT="reports/m2-disk-dry-run.md"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$SCRIPT" ]] || fail "$SCRIPT does not exist"
[[ -x "$SCRIPT" ]] || fail "$SCRIPT is not executable"
grep -Fq 'set -euo pipefail' "$SCRIPT" || fail "$SCRIPT does not use set -euo pipefail"
"$SCRIPT" --help >/dev/null || fail "$SCRIPT --help failed"
grep -Fq "$REPORT" "$SCRIPT" || fail "$SCRIPT does not write $REPORT"
grep -Fq 'NOT RUN' "$SCRIPT" || fail "$SCRIPT does not clearly mark future destructive commands as NOT RUN"

python3 - "$SCRIPT" <<'PY_CHECK'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
heredoc = None
triple_report_string = False
violations = []
destructive = re.compile(r"^\s*(sudo\s+)?(mkfs(\.[^\s]+)?|wipefs|sgdisk|parted|fdisk|mount|umount)(\s|$)")
fstab_edit = re.compile(r"(>\s*/etc/fstab|>>\s*/etc/fstab|tee\s+(-a\s+)?/etc/fstab|sed\s+-i[^\n]*/etc/fstab|perl\s+-pi[^\n]*/etc/fstab)")
heredoc_start = re.compile(r"<<[-]?['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")

for number, line in enumerate(lines, start=1):
    stripped = line.strip()
    if triple_report_string:
        if '"""' in line:
            triple_report_string = False
        continue
    if stripped.startswith('future_commands = """') and 'NOT RUN' in stripped:
        triple_report_string = True
        continue
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
        violations.append(f"{number}: executable destructive command: {line}")
    if fstab_edit.search(line):
        violations.append(f"{number}: executable fstab edit: {line}")

if violations:
    print("\n".join(violations))
    sys.exit(1)
PY_CHECK

echo "PASS: disk-dry-run static validation"
