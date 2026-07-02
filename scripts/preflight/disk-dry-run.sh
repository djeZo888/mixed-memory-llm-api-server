#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="reports/m2-disk-dry-run.md"

usage() {
  cat <<'HELP_EOF'
Usage: scripts/preflight/disk-dry-run.sh [--help]

Run a non-destructive M2 data disk dry-run and write reports/m2-disk-dry-run.md.

This script only collects read-only evidence and evaluates whether exactly one
safe future /data candidate disk exists. It does not partition, format, wipe,
mount, unmount, edit fstab, install packages, configure services, configure
Docker, configure NVIDIA drivers, download models, or expose APIs.

Required behavior:
- exits nonzero if sudo -k && sudo -n true fails
- outputs PASS only when exactly one safe candidate disk is found
- outputs STOP otherwise
HELP_EOF
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

HOSTNAME_VALUE=$(hostname 2>/dev/null || printf 'unknown')
USER_VALUE=$(whoami 2>/dev/null || printf 'unknown')
PWD_VALUE=$(pwd 2>/dev/null || printf 'unknown')
BRANCH_VALUE=$(git branch --show-current 2>/dev/null || printf 'unknown')
REMOTE_VALUE=$(git remote -v 2>/dev/null || printf 'unknown')
COMMIT_VALUE=$(git rev-parse HEAD 2>/dev/null || printf 'unknown')
TIMESTAMP_VALUE=$(date -Is)

cat > "$REPORT_PATH" <<REPORT_HEADER
# M2 Data Disk Dry-Run Report

## Milestone

- Milestone ID: M2 dry-run
- Name: Data disk dry-run
- Timestamp: ${TIMESTAMP_VALUE}
- Hostname: ${HOSTNAME_VALUE}
- User: ${USER_VALUE}
- Working directory: ${PWD_VALUE}
- Branch name: ${BRANCH_VALUE}
- Git commit hash: ${COMMIT_VALUE}

## Git Remote

\`\`\`text
${REMOTE_VALUE}
\`\`\`
REPORT_HEADER

if git remote -v 2>/dev/null | grep -Eq '(://[^[:space:]]*:[^[:space:]@]*@|token|password|passwd|GITHUB_TOKEN)'; then
  cat >> "$REPORT_PATH" <<'REPORT_STOP'

## Conclusion

STOP

Reason for STOP: git remote appears to contain credentials.
REPORT_STOP
  echo "STOP: git remote appears to contain credentials"
  exit 1
fi

cat >> "$REPORT_PATH" <<'REPORT_SUDO'

## Sudo Gate
REPORT_SUDO
run_capture "sudo -k" sudo -k
if ! sudo -n true >/dev/null 2>&1; then
  run_capture "sudo -n true" sudo -n true
  cat >> "$REPORT_PATH" <<'REPORT_STOP'

## Conclusion

STOP

Reason for STOP: sudo -n true failed after sudo -k. No password was requested or read.

## Scope Confirmation

No destructive changes were made.
REPORT_STOP
  echo "STOP: sudo -n true failed after sudo -k"
  exit 1
fi
run_capture "sudo -n true" sudo -n true
run_capture "sudo -n id" sudo -n id

ROOT_FS_SUMMARY=$(capture_value "findmnt -n -o SOURCE,FSTYPE,SIZE,USED,AVAIL,TARGET /")
ROOT_DISK_SUMMARY=$(capture_value "lsblk -ndo PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL /dev/sda 2>/dev/null || true")
if findmnt -n /data >/dev/null 2>&1; then
  DATA_STATE_SUMMARY="mounted: $(findmnt -n -o SOURCE,FSTYPE,OPTIONS /data 2>/dev/null | tr -s ' ')"
elif [[ -e /data ]]; then
  DATA_STATE_SUMMARY="exists but is not mounted; root-disk directory until M2 actual setup"
else
  DATA_STATE_SUMMARY="does not exist"
fi
if [[ -e /data ]]; then
  DATA_CONTENTS_SUMMARY=$(capture_value "sudo -n find /data -maxdepth 4 -mindepth 1 -print | wc -l")
  DATA_CONTENTS_SUMMARY="${DATA_CONTENTS_SUMMARY} entries below /data within depth 4"
else
  DATA_CONTENTS_SUMMARY="/data does not exist"
fi

cat >> "$REPORT_PATH" <<REPORT_SUMMARY

## Initial Summary

- Root filesystem summary: ${ROOT_FS_SUMMARY}
- Root disk summary: ${ROOT_DISK_SUMMARY}
- /data state: ${DATA_STATE_SUMMARY}
- Existing /data contents summary: ${DATA_CONTENTS_SUMMARY}
REPORT_SUMMARY

cat >> "$REPORT_PATH" <<'REPORT_IDENTITY'

## Identity
REPORT_IDENTITY
run_capture "hostname" hostname
run_capture "whoami" whoami
run_capture "date -Is" date -Is
run_capture "pwd" pwd

cat >> "$REPORT_PATH" <<'REPORT_GIT'

## Git
REPORT_GIT
run_capture_shell "current branch" 'git branch --show-current'
run_capture_shell "git remote -v" 'git remote -v'
run_capture_shell "latest commit hash" 'git rev-parse HEAD'

cat >> "$REPORT_PATH" <<'REPORT_ROOT'

## Root Mount
REPORT_ROOT
run_capture "df -hT /" df -hT /
run_capture "findmnt /" findmnt /
run_capture "lsblk full inventory" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL

cat >> "$REPORT_PATH" <<'REPORT_BLKID'

## Existing Filesystem Signatures
REPORT_BLKID
run_capture "sudo -n blkid" sudo -n blkid

cat >> "$REPORT_PATH" <<'REPORT_DATA'

## /data State
REPORT_DATA
run_capture_shell "findmnt /data" 'findmnt /data || true'
run_capture_shell "ls -ld /data" 'if [ -e /data ]; then ls -ld /data; else echo "/data does not exist"; fi'
run_capture_shell "sudo -n find /data -maxdepth 4 -ls" 'if [ -e /data ]; then sudo -n find /data -maxdepth 4 -ls; else echo "/data does not exist"; fi'
run_capture_shell "existing /data contents summary" 'if [ -e /data ]; then count=$(sudo -n find /data -maxdepth 4 -mindepth 1 -print | wc -l); echo "$count entries below /data within depth 4"; else echo "/data does not exist"; fi'

cat >> "$REPORT_PATH" <<'REPORT_INVENTORY'

## Disk Inventory
REPORT_INVENTORY
run_capture "all disks, partitions, filesystems, labels, UUIDs, mounts, model, serial" lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
run_capture_shell "all top-level disks" "lsblk -dn -o PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL"
run_capture_shell "all partitions" "lsblk -rno NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL | awk '\$4 == \"part\" {print}' || true"
run_capture_shell "all LVM members and logical volumes" "lsblk -rno NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL | awk '\$4 == \"lvm\" || \$5 == \"LVM2_member\" {print}' || true"
run_capture_shell "devices participating in root, boot, and EFI mounts" 'for target in / /boot /boot/efi; do echo "## $target"; source=$(findmnt -n -o SOURCE "$target" 2>/dev/null || true); if [ -n "$source" ]; then findmnt -n -o TARGET,SOURCE,FSTYPE,OPTIONS "$target" || true; lsblk -s -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS "$source" || true; else echo "not mounted"; fi; done'

set +e
python3 - "$REPORT_PATH" <<'PY_EVAL'
import json
import subprocess
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
LSBLK_COLUMNS = "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,PKNAME"


def cmd_output(args):
    completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout.rstrip()

status, lsblk_json_text = cmd_output(["lsblk", "-J", "-b", "-o", LSBLK_COLUMNS])
if status != 0:
    with report_path.open("a", encoding="utf-8") as report:
        report.write("\n## Candidate Disk Evaluation\n\nSTOP: lsblk JSON inventory failed.\n")
        report.write("\n## Conclusion\n\nSTOP\n")
    sys.exit(1)

_, blkid_text = cmd_output(["sudo", "-n", "blkid"])
_, root_source = cmd_output(["findmnt", "-n", "-o", "SOURCE", "/"])
_, boot_source = cmd_output(["findmnt", "-n", "-o", "SOURCE", "/boot"])
_, efi_source = cmd_output(["findmnt", "-n", "-o", "SOURCE", "/boot/efi"])
_, root_findmnt = cmd_output(["findmnt", "-n", "-o", "SOURCE,FSTYPE,SIZE,USED,AVAIL,TARGET", "/"])
_, data_findmnt = cmd_output(["findmnt", "-n", "-o", "SOURCE,FSTYPE,OPTIONS", "/data"])

data = json.loads(lsblk_json_text)
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


def bool_text(value):
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
    disk_fstype = bool(disk.get("fstype") or disk.get("label") or disk.get("uuid") or has_blkid_signature(path))
    partition_fs = [node.get("path") for node in disk_descendants if node.get("type") == "part" and (node.get("fstype") or node.get("label") or node.get("uuid") or has_blkid_signature(node.get("path") or ""))]
    lvm_pv = bool((disk.get("fstype") == "LVM2_member") or any(node.get("fstype") == "LVM2_member" for node in disk_descendants))
    stack_types = {node.get("type") for node in [disk] + disk_descendants if node.get("type") in {"lvm", "crypt", "raid0", "raid1", "raid5", "raid6", "raid10", "md"}}
    approx_2tb = 1_800_000_000_000 <= size <= 2_300_000_000_000
    is_root_disk = path == root_disk
    is_protected_ancestor = path in protected_ancestors
    used_by_boot = path == boot_disk or path == efi_disk or path in boot_ancestors or path in efi_ancestors
    safe = all([
        disk.get("type") == "disk",
        approx_2tb,
        not is_root_disk,
        path not in root_ancestors,
        not used_by_boot,
        not disk_mounts,
        not child_mounts,
        not disk_fstype,
        not partition_fs,
        not lvm_pv,
        not stack_types,
    ])
    reasons = []
    if disk.get("type") != "disk":
        reasons.append("not disk")
    if not approx_2tb:
        reasons.append("size not approximately 2 TB")
    if is_root_disk or path in root_ancestors or is_protected_ancestor:
        reasons.append("root disk, root ancestor, or protected boot ancestor")
    if used_by_boot:
        reasons.append("used by /boot or /boot/efi")
    if disk_mounts:
        reasons.append("disk mounted")
    if child_mounts:
        reasons.append("mounted children: " + ", ".join(child_mounts))
    if disk_fstype:
        reasons.append("filesystem/signature on disk")
    if partition_fs:
        reasons.append("partition filesystem/signature: " + ", ".join(partition_fs))
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
        "approx_2tb": approx_2tb,
        "not_root": not (is_root_disk or path in root_ancestors or is_protected_ancestor),
        "not_boot": not used_by_boot,
        "unmounted": not disk_mounts and not child_mounts,
        "no_signature": not disk_fstype,
        "no_partition_fs": not partition_fs,
        "not_lvm": not lvm_pv,
        "not_stack": not stack_types,
        "safe": safe,
        "reasons": "; ".join(reasons),
    }
    rows.append(row)
    if safe:
        candidates.append(row)

if len(candidates) == 1:
    conclusion = "PASS"
    selected = candidates[0]["path"]
    stop_reason = ""
else:
    conclusion = "STOP"
    selected = "none"
    if len(candidates) == 0:
        stop_reason = "No safe candidate disk found."
    else:
        stop_reason = f"More than one safe candidate disk found: {', '.join(row['path'] for row in candidates)}."

data_state = "mounted: " + data_findmnt if data_findmnt else "/data is not mounted"

future_commands = """# NOT RUN - documentation for future M2 actual setup only.
# Preconditions: human review of this dry-run report, exact target disk confirmed,
# and a fresh dry-run immediately before destructive commands.

# 1. If existing root-disk /data contains only safe bootstrap/test files, move it aside.
sudo mv /data /data.root-disk-pre-m2.$(date -u +%Y%m%dT%H%M%SZ)

# 2. Create a GPT partition table and one data partition on the verified disk.
sudo parted --script /dev/VERIFIED_DATA_DISK mklabel gpt
sudo parted --script /dev/VERIFIED_DATA_DISK mkpart AI_DATA ext4 0% 100%
sudo partprobe /dev/VERIFIED_DATA_DISK

# 3. Format ext4 with label AI_DATA.
sudo mkfs.ext4 -L AI_DATA /dev/VERIFIED_DATA_PARTITION

# 4. Get UUID and create mountpoint.
sudo blkid /dev/VERIFIED_DATA_PARTITION
sudo mkdir -p /data

# 5. Add /etc/fstab line by UUID, then mount.
echo 'UUID=VERIFIED_UUID /data ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount /data

# 6. Create required data directories.
sudo mkdir -p /data/models /data/hf-cache /data/docker /data/containerd
sudo mkdir -p /data/services /data/build /data/logs /data/backups /data/services/secrets

# 7. Create AI data environment file.
sudo tee /etc/profile.d/ai-data-paths.sh >/dev/null <<'PROFILE_EOF'
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
PROFILE_EOF

# 8. Verify before reboot.
findmnt /data
df -hT / /data
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL

# 9. Reboot and verify again.
sudo reboot
findmnt /data
df -hT / /data
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
"""

with report_path.open("a", encoding="utf-8") as report:
    report.write("\n## Candidate Disk Evaluation\n\n")
    report.write(f"- Root filesystem summary: `{root_findmnt or 'unknown'}`\n")
    report.write(f"- Root disk summary: `{root_disk or 'unknown'}`\n")
    report.write(f"- /boot disk summary: `{boot_disk or 'not mounted'}`\n")
    report.write(f"- /boot/efi disk summary: `{efi_disk or 'not mounted'}`\n")
    report.write(f"- /data state: {data_state}\n")
    report.write("\n| Disk | Size bytes | Model | Serial | Approx 2 TB | Not root | Not boot | Unmounted | No disk signature | No partition filesystems | Not LVM PV | Not stack member | Safe | Reason |\n")
    report.write("| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for row in rows:
        report.write(
            f"| `{row['path']}` | {row['size']} | {row['model']} | {row['serial']} | "
            f"{bool_text(row['approx_2tb'])} | {bool_text(row['not_root'])} | {bool_text(row['not_boot'])} | "
            f"{bool_text(row['unmounted'])} | {bool_text(row['no_signature'])} | {bool_text(row['no_partition_fs'])} | "
            f"{bool_text(row['not_lvm'])} | {bool_text(row['not_stack'])} | {bool_text(row['safe'])} | {row['reasons']} |\n"
        )
    if conclusion == "PASS":
        report.write(f"\n## Selected Future Data Disk\n\n`{selected}`\n")
        report.write("\n## Reason Selected Disk Is Safe\n\n")
        report.write("Exactly one candidate disk passed all dry-run checks: disk type, approximately 2 TB, not root, not a root ancestor, not used by /boot or /boot/efi, unmounted, no mounted children, no disk filesystem signature, no partition filesystem signatures, not an LVM physical volume, and not part of mdraid/dmcrypt/LVM stack.\n")
    else:
        report.write("\n## Reason For STOP\n\n")
        report.write(stop_reason + "\n")
    report.write("\n## Proposed Future Commands - NOT RUN\n\n")
    report.write("The following commands document the intended future M2 actual setup shape only. They were not run by this dry-run script.\n\n")
    report.write("```bash\n")
    report.write(future_commands)
    report.write("```\n")
    report.write("\n## Scope Confirmation\n\n")
    report.write("- No partition commands were run.\n")
    report.write("- No format commands were run.\n")
    report.write("- No wipe commands were run.\n")
    report.write("- No filesystem was mounted or unmounted.\n")
    report.write("- /etc/fstab was not edited.\n")
    report.write("- /data was not created, moved, deleted, mounted, or modified.\n")
    report.write("- /dev/sdb was not initialized or modified.\n")
    report.write("- No packages were installed.\n")
    report.write("- Docker was not configured.\n")
    report.write("- NVIDIA drivers were not configured.\n")
    report.write("- systemd was not configured.\n")
    report.write("- No models were downloaded.\n")
    report.write("- No API was exposed.\n")
    report.write("\n## Conclusion\n\n")
    report.write(conclusion + "\n")
    if conclusion == "PASS":
        report.write(f"\nSelected future data disk: `{selected}`.\n")
    else:
        report.write(f"\nReason for STOP: {stop_reason}\n")
    report.write("\n## Next Recommended Milestone\n\nM2 actual /data setup after human review.\n")

print(conclusion)
if conclusion == "PASS":
    print(selected)
    sys.exit(0)
print(stop_reason)
sys.exit(1)
PY_EVAL
EVAL_STATUS=$?
set -e

if [[ $EVAL_STATUS -eq 0 ]]; then
  echo "PASS: wrote ${REPORT_PATH}"
else
  echo "STOP: wrote ${REPORT_PATH}"
fi
exit "$EVAL_STATUS"
