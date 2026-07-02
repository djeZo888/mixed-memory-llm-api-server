#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="reports/m2-data-disk-setup.md"
TARGET_DISK="/dev/sdb"
MODE=""
OLD_DATA_PATH=""
PARTITION_PATH=""
FS_UUID=""
FSTAB_LINE=""

usage() {
  cat <<'EOF'
Usage:
  scripts/storage/prepare-data-disk.sh --help
  scripts/storage/prepare-data-disk.sh --dry-run
  scripts/storage/prepare-data-disk.sh --yes-format-verified-data-disk /dev/sdb

Prepare /data on the verified 2 TB data disk.

Actual mode is destructive and is refused unless the exact flag is provided:
  --yes-format-verified-data-disk /dev/sdb

The script re-runs safety checks before destructive actions, uses sudo -n only,
and writes detailed results to reports/m2-data-disk-setup.md.
EOF
}

case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --dry-run)
    MODE="dry-run"
    if [[ "${2:-}" != "" ]]; then
      usage >&2
      exit 2
    fi
    ;;
  --yes-format-verified-data-disk)
    MODE="actual"
    if [[ "${2:-}" != "$TARGET_DISK" || "${3:-}" != "" ]]; then
      echo "STOP: actual mode requires exactly: --yes-format-verified-data-disk /dev/sdb" >&2
      exit 2
    fi
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

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

append_report() {
  printf '%s\n' "$*" >> "$REPORT_PATH"
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

stop_now() {
  local reason="$1"
  append_report ""
  append_report "## Conclusion"
  append_report ""
  append_report "STOP"
  append_report ""
  append_report "Reason for STOP: ${reason}"
  echo "STOP: ${reason}" >&2
  exit 1
}

require_tool() {
  local tool="$1"
  command -v "$tool" >/dev/null 2>&1 || stop_now "required base tool missing: ${tool}; no packages were installed"
}

start_report() {
  local timestamp hostname user pwd_value branch remote commit title
  timestamp=$(date -Is)
  hostname=$(hostname 2>/dev/null || printf unknown)
  user=$(whoami 2>/dev/null || printf unknown)
  pwd_value=$(pwd 2>/dev/null || printf unknown)
  branch=$(git branch --show-current 2>/dev/null || printf unknown)
  remote=$(git remote -v 2>/dev/null || printf unknown)
  commit=$(git rev-parse HEAD 2>/dev/null || printf unknown)
  if [[ "$MODE" == "actual" && -f "$REPORT_PATH" ]]; then
    title="M2A Data Disk Setup Resume"
    cat >> "$REPORT_PATH" <<EOF_REPORT

---

# ${title}

## Milestone

- Milestone ID: M2A actual /data setup
- Timestamp: ${timestamp}
- Hostname: ${hostname}
- User: ${user}
- Working directory: ${pwd_value}
- Branch name: ${branch}
- Git commit hash at run start: ${commit}
- Mode: ${MODE}
- Target disk: ${TARGET_DISK}

## Git Remote

\`\`\`text
${remote}
\`\`\`
EOF_REPORT
  else
    title="M2A Data Disk Setup Report"
    cat > "$REPORT_PATH" <<EOF_REPORT
# ${title}

## Milestone

- Milestone ID: M2A actual /data setup
- Timestamp: ${timestamp}
- Hostname: ${hostname}
- User: ${user}
- Working directory: ${pwd_value}
- Branch name: ${branch}
- Git commit hash at run start: ${commit}
- Mode: ${MODE}
- Target disk: ${TARGET_DISK}

## Git Remote

\`\`\`text
${remote}
\`\`\`
EOF_REPORT
  fi
}
sudo_gate() {
  append_report ""
  append_report "## Sudo Gate"
  run_capture "sudo -k" sudo -k || stop_now "sudo -k failed"
  run_capture "sudo -n true" sudo -n true || stop_now "sudo -n true failed after sudo -k"
  run_capture "sudo -n id" sudo -n id || stop_now "sudo -n id failed"
}

check_remote() {
  if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
    stop_now "git remote appears to contain credentials"
  fi
}

check_required_tools() {
  append_report ""
  append_report "## Required Tool Check"
  local tools=(lsblk findmnt blkid sfdisk partprobe mkfs.ext4 systemctl stat awk sed grep sudo)
  for tool in "${tools[@]}"; do
    require_tool "$tool"
    run_capture_shell "command -v ${tool}" "command -v ${tool}"
  done
}

assert_safe_disk() {
  local phase="$1"
  python3 - "$TARGET_DISK" "$REPORT_PATH" "$phase" <<'PY_SAFE'
import json
import subprocess
import sys
from pathlib import Path

target = sys.argv[1]
report_path = Path(sys.argv[2])
phase = sys.argv[3]
columns = "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,PKNAME"


def cmd(args):
    completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout.rstrip()

status, lsblk_text = cmd(["lsblk", "-J", "-b", "-o", columns])
_, blkid_text = cmd(["sudo", "-n", "blkid"])
_, root_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/"])
_, boot_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/boot"])
_, efi_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/boot/efi"])

if status != 0:
    with report_path.open("a", encoding="utf-8") as report:
        report.write(f"\n### Safety Gate: {phase}\n\nSTOP: lsblk JSON inventory failed.\n")
    print("STOP: lsblk JSON inventory failed")
    sys.exit(1)

data = json.loads(lsblk_text)
roots = data.get("blockdevices", [])
all_nodes = []
parent_by_path = {}
node_by_path = {}


def walk(node, parent=None):
    path = node.get("path")
    if path:
        all_nodes.append(node)
        node_by_path[path] = node
        if parent and parent.get("path"):
            parent_by_path[path] = parent.get("path")
    for child in node.get("children") or []:
        walk(child, node)

for root in roots:
    walk(root)

name_to_path = {node.get("name"): node.get("path") for node in all_nodes if node.get("name") and node.get("path")}
for node in all_nodes:
    pkname = node.get("pkname")
    path = node.get("path")
    if pkname and path and path not in parent_by_path and pkname in name_to_path:
        parent_by_path[path] = name_to_path[pkname]


def ancestors(path):
    result = []
    seen = set()
    current = path.strip()
    while current and current not in seen:
        seen.add(current)
        result.append(current)
        current = parent_by_path.get(current, "")
    return result


def top_disk_for(path):
    result = None
    for item in ancestors(path):
        node = node_by_path.get(item)
        if node and node.get("type") == "disk":
            result = item
    return result


def mountpoints(node):
    values = node.get("mountpoints") or []
    if isinstance(values, str):
        values = [values]
    return [value for value in values if value]


def descendants(node):
    output = []
    for child in node.get("children") or []:
        output.append(child)
        output.extend(descendants(child))
    return output


def has_blkid_signature(path):
    prefix = path + ":"
    return any(line.startswith(prefix) for line in blkid_text.splitlines())


def yesno(value):
    return "yes" if value else "no"

root_ancestors = set(ancestors(root_source)) if root_source else set()
boot_ancestors = set(ancestors(boot_source)) if boot_source else set()
efi_ancestors = set(ancestors(efi_source)) if efi_source else set()
root_disk = top_disk_for(root_source) if root_source else None
boot_disk = top_disk_for(boot_source) if boot_source else None
efi_disk = top_disk_for(efi_source) if efi_source else None
protected_ancestors = root_ancestors | boot_ancestors | efi_ancestors

rows = []
candidates = []
for disk in [node for node in roots if node.get("type") == "disk"]:
    path = disk.get("path") or "unknown"
    size = int(disk.get("size") or 0)
    disk_descendants = descendants(disk)
    disk_mounts = mountpoints(disk)
    child_mounts = []
    for node in disk_descendants:
        child_mounts.extend(mountpoints(node))
    disk_signature = bool(disk.get("fstype") or disk.get("label") or disk.get("uuid") or has_blkid_signature(path))
    partition_nodes = [node for node in disk_descendants if node.get("type") == "part"]
    partition_fs = [node.get("path") for node in partition_nodes if node.get("fstype") or node.get("label") or node.get("uuid") or has_blkid_signature(node.get("path") or "")]
    lvm_pv = bool((disk.get("fstype") == "LVM2_member") or any(node.get("fstype") == "LVM2_member" for node in disk_descendants))
    stack_types = {node.get("type") for node in [disk] + disk_descendants if node.get("type") in {"lvm", "crypt", "raid0", "raid1", "raid5", "raid6", "raid10", "md"}}
    approx_2tb = 1_800_000_000_000 <= size <= 2_300_000_000_000
    used_by_boot = path == boot_disk or path == efi_disk or path in boot_ancestors or path in efi_ancestors
    root_related = path == root_disk or path in root_ancestors or path in protected_ancestors
    safe = all([
        disk.get("type") == "disk",
        approx_2tb,
        not root_related,
        not used_by_boot,
        not disk_mounts,
        not child_mounts,
        not disk_signature,
        not partition_nodes,
        not partition_fs,
        not lvm_pv,
        not stack_types,
    ])
    reasons = []
    if not approx_2tb:
        reasons.append("size not approximately 2 TB")
    if root_related:
        reasons.append("root disk, root ancestor, or protected boot ancestor")
    if used_by_boot:
        reasons.append("used by /boot or /boot/efi")
    if disk_mounts:
        reasons.append("disk mounted")
    if child_mounts:
        reasons.append("mounted children: " + ", ".join(child_mounts))
    if disk_signature:
        reasons.append("filesystem signature on disk")
    if partition_nodes:
        reasons.append("existing partitions: " + ", ".join(node.get("path") or "unknown" for node in partition_nodes))
    if partition_fs:
        reasons.append("partition filesystem signatures: " + ", ".join(partition_fs))
    if lvm_pv:
        reasons.append("LVM physical volume present")
    if stack_types:
        reasons.append("stack member/type: " + ", ".join(sorted(stack_types)))
    if not reasons:
        reasons.append("all safety checks passed")
    row = {
        "path": path,
        "size": str(size),
        "model": disk.get("model") or "",
        "serial": disk.get("serial") or "",
        "approx": approx_2tb,
        "not_root": not root_related,
        "not_boot": not used_by_boot,
        "unmounted": not disk_mounts and not child_mounts,
        "no_sig": not disk_signature,
        "no_parts": not partition_nodes,
        "not_lvm": not lvm_pv,
        "not_stack": not stack_types,
        "safe": safe,
        "reason": "; ".join(reasons),
    }
    rows.append(row)
    if safe:
        candidates.append(row)

if len(candidates) != 1:
    ok = False
    if len(candidates) == 0:
        stop_reason = "No safe candidate disk found."
    else:
        stop_reason = "Multiple possible 2 TB data-disk candidates found: " + ", ".join(row["path"] for row in candidates)
else:
    selected = candidates[0]["path"]
    ok = selected == target
    stop_reason = "" if ok else f"Safe candidate is {selected}, not required target {target}."

with report_path.open("a", encoding="utf-8") as report:
    report.write(f"\n### Safety Gate: {phase}\n\n")
    report.write(f"- Required target: `{target}`\n")
    report.write(f"- Root disk: `{root_disk or 'unknown'}`\n")
    report.write(f"- /boot disk: `{boot_disk or 'not mounted'}`\n")
    report.write(f"- /boot/efi disk: `{efi_disk or 'not mounted'}`\n")
    report.write("\n| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No filesystem signatures | No existing partitions | Not LVM | Not stack member | Safe | Reason |\n")
    report.write("| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for row in rows:
        report.write(
            f"| `{row['path']}` | {row['size']} | {row['model']} | {row['serial']} | "
            f"{yesno(row['approx'])} | {yesno(row['not_root'])} | {yesno(row['not_boot'])} | "
            f"{yesno(row['unmounted'])} | {yesno(row['no_sig'])} | {yesno(row['no_parts'])} | "
            f"{yesno(row['not_lvm'])} | {yesno(row['not_stack'])} | {yesno(row['safe'])} | {row['reason']} |\n"
        )
    if ok:
        report.write(f"\nPASS: exactly one safe candidate exists and it is `{target}`.\n")
    else:
        report.write(f"\nSTOP: {stop_reason}\n")

if ok:
    print(target)
    sys.exit(0)
print(stop_reason)
sys.exit(1)
PY_SAFE
}

assert_partition_safe_for_format() {
  local part="$1"
  local parent="$2"
  python3 - "$part" "$parent" "$REPORT_PATH" <<'PY_PART'
import json
import subprocess
import sys
from pathlib import Path

part = sys.argv[1]
parent = sys.argv[2]
report_path = Path(sys.argv[3])
columns = "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,PKNAME"


def cmd(args):
    completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout.rstrip()

status, text = cmd(["lsblk", "-J", "-b", "-o", columns, parent])
_, blkid_text = cmd(["sudo", "-n", "blkid"])
_, root_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/"])
_, boot_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/boot"])
_, efi_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/boot/efi"])

if status != 0:
    print("lsblk failed for partition safety")
    sys.exit(1)

data = json.loads(text)
all_nodes = []
parent_by_path = {}
node_by_path = {}

def walk(node, parent_node=None):
    path = node.get("path")
    if path:
        all_nodes.append(node)
        node_by_path[path] = node
        if parent_node and parent_node.get("path"):
            parent_by_path[path] = parent_node.get("path")
    for child in node.get("children") or []:
        walk(child, node)

for root in data.get("blockdevices", []):
    walk(root)


def ancestors(path):
    result = []
    seen = set()
    current = path.strip()
    while current and current not in seen:
        seen.add(current)
        result.append(current)
        current = parent_by_path.get(current, "")
    return result


def mountpoints(node):
    values = node.get("mountpoints") or []
    if isinstance(values, str):
        values = [values]
    return [value for value in values if value]


def has_filesystem_signature(path):
    for line in blkid_text.splitlines():
        if line.startswith(path + ":") and (" TYPE=" in line or " UUID=" in line):
            return True
    return False

node = node_by_path.get(part)
reasons = []
if not node:
    reasons.append(f"{part} not found")
else:
    if node.get("type") != "part":
        reasons.append("target is not a partition")
    if parent_by_path.get(part) != parent:
        reasons.append(f"partition parent is {parent_by_path.get(part)}, expected {parent}")
    if mountpoints(node):
        reasons.append("partition is mounted")
    if node.get("fstype") or node.get("label") or node.get("uuid") or has_filesystem_signature(part):
        reasons.append("partition already has filesystem signature")
    if set(ancestors(part)) & set(ancestors(root_source) + ancestors(boot_source) + ancestors(efi_source)):
        reasons.append("partition participates in root, /boot, or /boot/efi stack")

with report_path.open("a", encoding="utf-8") as report:
    report.write("\n### Safety Gate: before mkfs.ext4\n\n")
    if reasons:
        report.write("STOP: " + "; ".join(reasons) + "\n")
    else:
        report.write(f"PASS: `{part}` exists, belongs to `{parent}`, is unmounted, has no filesystem signature, and is not in the root/boot stack.\n")

if reasons:
    print("; ".join(reasons))
    sys.exit(1)
print(part)
PY_PART
}

assert_resume_partition_state() {
  local phase="$1"
  python3 - "$TARGET_DISK" "${TARGET_DISK}1" "$REPORT_PATH" "$phase" <<'PY_RESUME'
import json
import subprocess
import sys
from pathlib import Path

target = sys.argv[1]
partition = sys.argv[2]
report_path = Path(sys.argv[3])
phase = sys.argv[4]
columns = "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,PKNAME"


def cmd(args):
    completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout.rstrip()

status, text = cmd(["lsblk", "-J", "-b", "-o", columns])
_, blkid_text = cmd(["sudo", "-n", "blkid"])
_, root_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/"])
_, boot_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/boot"])
_, efi_source = cmd(["findmnt", "-n", "-o", "SOURCE", "/boot/efi"])

if status != 0:
    print("lsblk failed")
    sys.exit(1)

data = json.loads(text)
roots = data.get("blockdevices", [])
all_nodes = []
parent_by_path = {}
node_by_path = {}


def walk(node, parent=None):
    path = node.get("path")
    if path:
        all_nodes.append(node)
        node_by_path[path] = node
        if parent and parent.get("path"):
            parent_by_path[path] = parent.get("path")
    for child in node.get("children") or []:
        walk(child, node)

for root in roots:
    walk(root)

name_to_path = {node.get("name"): node.get("path") for node in all_nodes if node.get("name") and node.get("path")}
for node in all_nodes:
    pkname = node.get("pkname")
    path = node.get("path")
    if pkname and path and path not in parent_by_path and pkname in name_to_path:
        parent_by_path[path] = name_to_path[pkname]


def ancestors(path):
    result = []
    seen = set()
    current = path.strip()
    while current and current not in seen:
        seen.add(current)
        result.append(current)
        current = parent_by_path.get(current, "")
    return result


def top_disk_for(path):
    result = None
    for item in ancestors(path):
        node = node_by_path.get(item)
        if node and node.get("type") == "disk":
            result = item
    return result


def mountpoints(node):
    values = node.get("mountpoints") or []
    if isinstance(values, str):
        values = [values]
    return [value for value in values if value]


def descendants(node):
    output = []
    for child in node.get("children") or []:
        output.append(child)
        output.extend(descendants(child))
    return output


def has_filesystem_signature(path):
    for line in blkid_text.splitlines():
        if line.startswith(path + ":") and (" TYPE=" in line or " UUID=" in line):
            return True
    return False

root_ancestors = set(ancestors(root_source)) if root_source else set()
boot_ancestors = set(ancestors(boot_source)) if boot_source else set()
efi_ancestors = set(ancestors(efi_source)) if efi_source else set()
root_disk = top_disk_for(root_source) if root_source else None
boot_disk = top_disk_for(boot_source) if boot_source else None
efi_disk = top_disk_for(efi_source) if efi_source else None
protected = root_ancestors | boot_ancestors | efi_ancestors

resume_candidates = []
rows = []
for disk in [node for node in roots if node.get("type") == "disk"]:
    path = disk.get("path") or "unknown"
    size = int(disk.get("size") or 0)
    children = descendants(disk)
    parts = [node for node in children if node.get("type") == "part"]
    child_mounts = [mp for node in children for mp in mountpoints(node)]
    disk_signature = bool(disk.get("fstype") or disk.get("label") or disk.get("uuid") or has_filesystem_signature(path))
    approx = 1_800_000_000_000 <= size <= 2_300_000_000_000
    root_related = path == root_disk or path in root_ancestors or path in protected
    boot_related = path == boot_disk or path == efi_disk or path in boot_ancestors or path in efi_ancestors
    part_reasons = []
    if len(parts) != 1:
        part_reasons.append(f"expected exactly one partition, found {len(parts)}")
    else:
        part = parts[0]
        if part.get("path") != partition:
            part_reasons.append(f"partition is {part.get('path')}, expected {partition}")
        if mountpoints(part):
            part_reasons.append("partition mounted")
        if part.get("fstype") or part.get("label") or part.get("uuid") or has_filesystem_signature(part.get("path") or ""):
            part_reasons.append("partition has filesystem signature")
    reasons = []
    if not approx:
        reasons.append("size not approximately 2 TB")
    if root_related:
        reasons.append("root disk, root ancestor, or protected boot ancestor")
    if boot_related:
        reasons.append("used by /boot or /boot/efi")
    if mountpoints(disk) or child_mounts:
        reasons.append("disk or child mounted")
    if disk_signature:
        reasons.append("filesystem signature on disk")
    reasons.extend(part_reasons)
    ok = not reasons
    rows.append((path, ok, "; ".join(reasons) if reasons else "resume partition state is safe"))
    if ok:
        resume_candidates.append(path)

ok = len(resume_candidates) == 1 and resume_candidates[0] == target
if len(resume_candidates) == 0:
    stop = "No safe resume partition state found."
elif len(resume_candidates) > 1:
    stop = "Multiple safe resume candidates found: " + ", ".join(resume_candidates)
else:
    stop = f"Safe resume candidate is {resume_candidates[0]}, not required target {target}." if resume_candidates[0] != target else ""

with report_path.open("a", encoding="utf-8") as report:
    report.write(f"\n### Safety Gate: {phase}\n\n")
    report.write("This gate is only for resuming after a prior STOP where the GPT partition was created but no filesystem was written.\n\n")
    report.write("| Disk | Resume safe | Reason |\n| --- | --- | --- |\n")
    for row in rows:
        report.write(f"| `{row[0]}` | {'yes' if row[1] else 'no'} | {row[2]} |\n")
    if ok:
        report.write(f"\nPASS: exactly one safe resume candidate exists and it is `{target}` with unformatted `{partition}`.\n")
    else:
        report.write(f"\nSTOP: {stop}\n")

if ok:
    print(target)
    sys.exit(0)
print(stop)
sys.exit(1)
PY_RESUME
}

move_existing_data_aside() {
  append_report ""
  append_report "## Move Existing Root-Disk /data Aside"
  if findmnt -n /data >/dev/null 2>&1; then
    stop_now "/data is already mounted; refusing to move or overwrite it"
  fi
  if [[ -e /data ]]; then
    run_capture_shell "existing /data before move" "sudo -n find /data -maxdepth 4 -ls"
    local stamp base candidate n
    stamp=$(date -u +%Y%m%d-%H%M%S)
    base="/data.pre-mount-root-${stamp}"
    candidate="$base"
    n=0
    while sudo -n test -e "$candidate"; do
      n=$((n + 1))
      candidate="${base}.${n}"
    done
    OLD_DATA_PATH="$candidate"
    run_capture "move /data aside" sudo -n mv /data "$OLD_DATA_PATH" || stop_now "failed to move existing /data aside"
    append_report ""
    append_report "Moved old root-disk /data aside to: \`${OLD_DATA_PATH}\`"
  else
    OLD_DATA_PATH="none; /data did not exist before setup"
    append_report "No existing /data path was present before setup."
  fi
  run_capture "create fresh /data mountpoint" sudo -n mkdir -p /data || stop_now "failed to create /data mountpoint"
  run_capture "set /data mountpoint permissions before mount" sudo -n chmod 0755 /data || stop_now "failed to chmod /data mountpoint"
}

partition_disk() {
  append_report ""
  append_report "## Partition Disk"
  assert_safe_disk "immediately before partition table creation" >/dev/null || stop_now "target disk failed safety check immediately before partitioning"
  run_capture_shell "create GPT partition table and one Linux filesystem partition" "printf 'label: gpt\n, , L\n' | sudo -n sfdisk ${TARGET_DISK}" || stop_now "sfdisk failed"
  run_capture "notify kernel of partition table" sudo -n partprobe "$TARGET_DISK" || stop_now "partprobe failed"
  if command -v udevadm >/dev/null 2>&1; then
    run_capture "udevadm settle" sudo -n udevadm settle || stop_now "udevadm settle failed"
  fi
  PARTITION_PATH="${TARGET_DISK}1"
  local i
  for i in {1..20}; do
    if [[ -b "$PARTITION_PATH" ]]; then
      break
    fi
    sleep 1
  done
  [[ -b "$PARTITION_PATH" ]] || stop_now "${PARTITION_PATH} did not appear"
  run_capture "lsblk after partition" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
}

format_partition() {
  append_report ""
  append_report "## Format Partition"
  assert_partition_safe_for_format "$PARTITION_PATH" "$TARGET_DISK" >/dev/null || stop_now "partition failed safety check immediately before mkfs.ext4"
  run_capture "format /dev/sdb1 as ext4 AI_DATA" sudo -n mkfs.ext4 -F -L AI_DATA "$PARTITION_PATH" || stop_now "mkfs.ext4 failed"
  FS_UUID=$(sudo -n blkid -s UUID -o value "$PARTITION_PATH")
  [[ -n "$FS_UUID" ]] || stop_now "failed to read filesystem UUID from ${PARTITION_PATH}"
  append_report ""
  append_report "Filesystem UUID: \`${FS_UUID}\`"
}

configure_fstab_and_mount() {
  append_report ""
  append_report "## Configure fstab And Mount /data"
  if grep -Eq '^[^#][[:space:]]*[^[:space:]]+[[:space:]]+/data[[:space:]]+' /etc/fstab; then
    stop_now "/etc/fstab already contains an active /data entry"
  fi
  FSTAB_LINE="UUID=${FS_UUID} /data ext4 defaults,nofail,x-systemd.device-timeout=30 0 2"
  append_report "fstab line added: \`${FSTAB_LINE}\`"
  run_capture_shell "append /data UUID entry to /etc/fstab" "printf '%s\n' '${FSTAB_LINE}' | sudo -n tee -a /etc/fstab >/dev/null" || stop_now "failed to append fstab entry"
  run_capture "systemctl daemon-reload" sudo -n systemctl daemon-reload || stop_now "systemctl daemon-reload failed"
  if findmnt --help 2>/dev/null | grep -q -- '--verify'; then
    run_capture "findmnt --verify --verbose" sudo -n findmnt --verify --verbose || stop_now "findmnt --verify failed"
  else
    append_report "findmnt --verify is unavailable; skipped."
  fi
  run_capture "mount /data from fstab" sudo -n mount /data || stop_now "mount /data failed"
  run_capture "findmnt /data" findmnt /data || stop_now "findmnt /data failed after mount"
  run_capture "df -hT / /data" df -hT / /data || stop_now "df verification failed"
  run_capture "lsblk after mount" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
  run_capture_shell "grep /data /etc/fstab" "grep -E '[[:space:]]/data[[:space:]]' /etc/fstab"
}

create_dirs_and_permissions() {
  append_report ""
  append_report "## Directory And Permission Setup"
  run_capture_shell "create ai group if missing" "getent group ai >/dev/null || sudo -n groupadd ai" || stop_now "failed to create ai group"
  run_capture_shell "add user to ai group" "id -nG user | tr ' ' '\n' | grep -qx ai || sudo -n usermod -aG ai user" || stop_now "failed to add user to ai group"
  append_report "Note: group membership changes may require a new login or reboot to become visible in existing sessions."
  run_capture "create required /data directories" sudo -n mkdir -p \
    /data/models \
    /data/hf-cache/hub \
    /data/hf-cache/xet \
    /data/hf-cache/assets \
    /data/hf-cache/datasets \
    /data/hf-cache/transformers \
    /data/hf-cache/xdg \
    /data/docker \
    /data/containerd \
    /data/services/secrets \
    /data/build \
    /data/logs \
    /data/backups || stop_now "failed to create required /data directories"
  run_capture "set /data ownership" sudo -n chown root:root /data || stop_now "failed to chown /data"
  run_capture "set /data mode" sudo -n chmod 0755 /data || stop_now "failed to chmod /data"
  run_capture "set user writable data ownership" sudo -n chown -R user:ai /data/models /data/hf-cache /data/services /data/build /data/logs /data/backups || stop_now "failed to chown user data dirs"
  run_capture_shell "set setgid modes on user data directories" "sudo -n find /data/models /data/hf-cache /data/services /data/build /data/logs /data/backups -type d -exec chmod 2775 {} +" || stop_now "failed to chmod user data dirs"
  run_capture "set secrets ownership" sudo -n chown user:ai /data/services/secrets || stop_now "failed to chown secrets dir"
  run_capture "set secrets mode" sudo -n chmod 2770 /data/services/secrets || stop_now "failed to chmod secrets dir"
  # These are initial bootstrap placeholders. Docker and containerd may tighten
  # permissions later after they own/manage their data roots.
  run_capture "set docker ownership" sudo -n chown root:root /data/docker || stop_now "failed to chown docker dir"
  run_capture "set docker mode" sudo -n chmod 0711 /data/docker || stop_now "failed to chmod docker dir"
  run_capture "set containerd ownership" sudo -n chown root:root /data/containerd || stop_now "failed to chown containerd dir"
  run_capture "set containerd mode" sudo -n chmod 0711 /data/containerd || stop_now "failed to chmod containerd dir"
  run_capture_shell "directory permission summary" "stat -c '%A %a %U:%G %n' /data /data/models /data/hf-cache /data/hf-cache/hub /data/hf-cache/xet /data/hf-cache/assets /data/hf-cache/datasets /data/hf-cache/transformers /data/hf-cache/xdg /data/docker /data/containerd /data/services /data/build /data/logs /data/backups /data/services/secrets"
}

create_profile() {
  append_report ""
  append_report "## AI Data Environment"
  run_capture_shell "write /etc/profile.d/ai-data-paths.sh" "sudo -n tee /etc/profile.d/ai-data-paths.sh >/dev/null <<'PROFILE_EOF'
export AI_DATA=/data
export HF_HOME=/data/hf-cache
export HF_HUB_CACHE=/data/hf-cache/hub
export HF_XET_CACHE=/data/hf-cache/xet
export HF_ASSETS_CACHE=/data/hf-cache/assets
export HF_DATASETS_CACHE=/data/hf-cache/datasets
export TRANSFORMERS_CACHE=/data/hf-cache/transformers
export XDG_CACHE_HOME=/data/hf-cache/xdg
export AI_BUILD_DIR=/data/build
export AI_LOG_DIR=/data/logs
PROFILE_EOF" || stop_now "failed to write ai-data-paths profile"
  run_capture "set profile ownership" sudo -n chown root:root /etc/profile.d/ai-data-paths.sh || stop_now "failed to chown profile"
  run_capture "set profile mode" sudo -n chmod 0644 /etc/profile.d/ai-data-paths.sh || stop_now "failed to chmod profile"
  run_capture "profile file contents" sudo -n cat /etc/profile.d/ai-data-paths.sh
}

final_verification() {
  append_report ""
  append_report "## Final Setup Verification"
  run_capture "findmnt /data" findmnt /data || stop_now "final findmnt /data failed"
  run_capture "df -hT / /data" df -hT / /data || stop_now "final df failed"
  run_capture "lsblk final" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
  run_capture_shell "fstab /data entry" "grep -E '[[:space:]]/data[[:space:]]' /etc/fstab"
  append_report ""
  append_report "## Scope Confirmation"
  append_report ""
  append_report "- Partitioned and formatted only the verified safe disk: \`${TARGET_DISK}\`."
  append_report "- Created partition path: \`${PARTITION_PATH}\`."
  append_report "- Filesystem UUID: \`${FS_UUID}\`."
  append_report "- fstab line added: \`${FSTAB_LINE}\`."
  append_report "- Old root-disk /data path moved aside to: \`${OLD_DATA_PATH}\`."
  append_report "- Docker was not installed or configured."
  append_report "- NVIDIA drivers or toolkit were not installed or configured."
  append_report "- No models were downloaded."
  append_report "- No API was exposed."
  append_report "- VM was not rebooted automatically."
  append_report ""
  append_report "## Conclusion"
  append_report ""
  append_report "PASS"
  append_report ""
  append_report "## Next Recommended Task"
  append_report ""
  append_report "Reboot VM 120 only, then run M2B post-reboot verification."
}

run_dry_run() {
  start_report
  check_remote
  sudo_gate
  check_required_tools
  append_report ""
  append_report "## Read-Only Inventory"
  run_capture "df -hT /" df -hT /
  run_capture "findmnt /" findmnt /
  run_capture_shell "findmnt /data" "findmnt /data || true"
  run_capture_shell "ls -ld /data" "if [ -e /data ]; then ls -ld /data; else echo '/data does not exist'; fi"
  run_capture_shell "sudo -n find /data -maxdepth 4 -ls" "if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo '/data does not exist'; fi"
  run_capture "lsblk inventory" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
  run_capture "sudo -n blkid" sudo -n blkid
  assert_safe_disk "dry-run before actual setup" >/dev/null || stop_now "dry-run safety check failed"
  append_report ""
  append_report "## Conclusion"
  append_report ""
  append_report "PASS"
  append_report ""
  append_report "Dry-run only. No destructive changes were made."
  echo "PASS: dry-run wrote ${REPORT_PATH}"
}

run_actual() {
  start_report
  check_remote
  sudo_gate
  check_required_tools
  append_report ""
  append_report "## Initial Read-Only Inventory"
  run_capture "df -hT /" df -hT /
  run_capture "findmnt /" findmnt /
  run_capture_shell "findmnt /data" "findmnt /data || true"
  run_capture_shell "ls -ld /data" "if [ -e /data ]; then ls -ld /data; else echo '/data does not exist'; fi"
  run_capture_shell "sudo -n find /data -maxdepth 4 -ls" "if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo '/data does not exist'; fi"
  run_capture "lsblk inventory before setup" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
  run_capture "sudo -n blkid before setup" sudo -n blkid
  if grep -Eq '^[^#][[:space:]]*[^[:space:]]+[[:space:]]+/data[[:space:]]+' /etc/fstab; then
    stop_now "/etc/fstab already contains an active /data entry before setup"
  fi
  if assert_safe_disk "actual preflight before any destructive command" >/dev/null; then
    assert_safe_disk "immediately before moving root-disk /data aside" >/dev/null || stop_now "target disk failed safety check immediately before moving /data"
    move_existing_data_aside
    partition_disk
  else
    append_report ""
    append_report "Full unpartitioned-disk setup path is not available; checking for a safe resume state."
    assert_resume_partition_state "resume preflight before formatting existing unformatted partition" >/dev/null || stop_now "target disk is neither pristine nor in a safe unformatted resume state"
    if findmnt -n /data >/dev/null 2>&1; then
      stop_now "/data is already mounted during resume preflight"
    fi
    [[ -d /data ]] || stop_now "/data mountpoint is missing during resume preflight"
    PARTITION_PATH="${TARGET_DISK}1"
    OLD_DATA_PATH=$(ls -dt /data.pre-mount-root-* 2>/dev/null | head -n 1 || true)
    [[ -n "$OLD_DATA_PATH" ]] || OLD_DATA_PATH="unknown; no /data.pre-mount-root-* path found during resume"
    append_report "Resume old root-disk /data path: \`${OLD_DATA_PATH}\`"
  fi
  format_partition
  configure_fstab_and_mount
  create_dirs_and_permissions
  create_profile
  final_verification
  echo "PASS: actual setup wrote ${REPORT_PATH}"
}

if [[ "$MODE" == "dry-run" ]]; then
  run_dry_run
else
  run_actual
fi
