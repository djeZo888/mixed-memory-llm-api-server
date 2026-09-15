#!/usr/bin/env bash
# Disposable Linux-only verification. Never accepts a caller-supplied device.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C

usage() {
    cat <<'EOF'
Usage: tests/install/loop_disk_transaction.sh --help | --dry-run | --apply

--dry-run  Print the isolated fixture design and check Linux prerequisites.
--apply    Repeat the preflight, create a private mount namespace and an owned
           sparse file on /run tmpfs, then test only its newly allocated loop.

Requires a disposable Linux environment, root, mount/loop capabilities, Python
3, util-linux, e2fsprogs, udevadm and an existing tmpfs /run with free space.
Does not install packages. Never pass a physical disk or an existing loop device.
All fixture paths are generated internally. A failed ownership check preserves
the scratch directory for investigation rather than detaching an unknown loop.
EOF
}

preflight() {
    local command_name
    [[ $(uname -s) == Linux ]] || { echo 'NOT_TESTED: Linux is required.' >&2; return 1; }
    for command_name in python3 unshare mount umount findmnt lsblk losetup sfdisk \
            wipefs blkid mkfs.ext4 e2fsck tune2fs udevadm truncate mktemp stat readlink mountpoint; do
        command -v "$command_name" >/dev/null || { echo "Missing prerequisite: $command_name" >&2; return 1; }
    done
    [[ $(findmnt --noheadings --output FSTYPE --target /run) == tmpfs ]] || {
        echo 'Refusing: fixture scratch /run must already be tmpfs.' >&2; return 1;
    }
    cat <<'EOF'
DRY_RUN: create a private mount namespace; create a new protected /run scratch
directory and 256 MiB sparse file; allocate its own loop; verify exact backing
inode, size and offsets; exercise GPT/ext4 transaction recovery and idempotency;
unmount private targets, detach only that exact owned loop, and remove scratch.
No physical disk, host fstab, host journal, service, driver or reboot changes.
EOF
}

case ${1:-} in
    --help) [[ $# == 1 ]] || exit 2; usage; exit 0 ;;
    --dry-run) [[ $# == 1 ]] || exit 2; preflight; exit 0 ;;
    --apply)
        [[ $# == 1 ]] || exit 2
        preflight
        [[ $EUID == 0 ]] || { echo '--apply requires root in disposable Linux.' >&2; exit 1; }
        export I1S_FIXTURE_PARENT_NAMESPACE
        I1S_FIXTURE_PARENT_NAMESPACE=$(readlink /proc/self/ns/mnt)
        exec unshare --mount --propagation private "$0" --namespace-apply
        ;;
    --namespace-apply)
        [[ $# == 1 && $EUID == 0 && -n ${I1S_FIXTURE_PARENT_NAMESPACE:-} ]] || exit 2
        preflight
        [[ $(readlink /proc/self/ns/mnt) != "$I1S_FIXTURE_PARENT_NAMESPACE" ]] || {
            echo 'Refusing: fixture mount namespace was not isolated.' >&2; exit 1;
        }
        [[ $(findmnt --raw --noheadings --output PROPAGATION --target /) == private ]] || {
            echo 'Refusing: namespace root mount propagation must be private.' >&2; exit 1;
        }
        ;;
    *) usage >&2; exit 2 ;;
esac

umask 077
fixture_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
fixture_root=$(mktemp -d /run/i1s-loop-XXXXXXXX)
fixture_backing=$fixture_root/backing.img
fixture_loop=
fixture_identity=$fixture_root/ownership.json
fixture_mounted=false

owned_loop() {
    python3 -I -B "$fixture_script_dir/loop_disk_transaction.py" \
        --check-owned "$fixture_identity" "$fixture_loop"
}

cleanup() {
    local result=$? safe=true
    trap - EXIT HUP INT TERM
    if [[ -n "$fixture_loop" ]]; then
        if owned_loop; then
            if mountpoint -q "$fixture_root/root/data"; then
                if python3 -I -B "$fixture_script_dir/loop_disk_transaction.py" \
                        --check-mount "$fixture_identity" "$fixture_loop"; then
                    umount -- "$fixture_root/root/data" || safe=false
                else
                    echo 'Fixture mount identity changed; refusing unmount.' >&2
                    safe=false
                fi
            fi
            if [[ $safe == true ]] && owned_loop; then
                losetup --detach "$fixture_loop" || safe=false
                udevadm settle --timeout=10 || safe=false
                if losetup --list --noheadings --output NAME "$fixture_loop" | read -r _; then
                    echo 'Fixture loop detach has not completed; preserving backing file.' >&2
                    safe=false
                fi
            fi
        else
            echo 'Fixture identity changed; refusing detach and preserving scratch.' >&2
            safe=false
        fi
    fi
    if [[ $fixture_mounted == true ]]; then
        if python3 -I -B "$fixture_script_dir/loop_disk_transaction.py" \
                --check-sysfs "$fixture_identity"; then
            umount -- "$fixture_root/root/sys" || safe=false
        else
            safe=false
        fi
    fi
    if [[ $safe == true ]]; then
        # Python removes only the exact recorded root, without following links.
        python3 -I -B "$fixture_script_dir/loop_disk_transaction.py" \
            --remove-owned "$fixture_identity" || safe=false
    fi
    if [[ $safe != true ]]; then
        echo "CLEANUP_INCOMPLETE: inspect $fixture_root in disposable environment." >&2
        result=1
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

truncate --size 256M "$fixture_backing"
chmod 0600 "$fixture_backing"
python3 -I -B "$fixture_script_dir/loop_disk_transaction.py" \
    --record-owned "$fixture_identity" "$fixture_backing"
fixture_loop=$(losetup --find --show --nooverlap --partscan "$fixture_backing")
[[ $fixture_loop =~ ^/dev/loop[0-9]+$ ]] || { echo 'Unexpected allocated loop name.' >&2; exit 1; }
owned_loop
mkdir -m 0700 -p "$fixture_root/root/sys"
mount --bind /sys "$fixture_root/root/sys"
fixture_mounted=true
mount --make-private "$fixture_root/root/sys"
mount -o remount,bind,ro "$fixture_root/root/sys"
python3 -I -B "$fixture_script_dir/loop_disk_transaction.py" \
    --run "$fixture_identity" "$fixture_loop"
