#!/usr/bin/env python3
"""Bounded blank-loop proof for an authorized disposable GitHub Ubuntu VM.

No installer code is imported. Only the loop returned for a newly created,
exclusive regular backing file can become a filesystem candidate. Live use is
guarded; local unit tests exercise refusal paths without running Linux tools.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import time
import uuid


SIZE = 64 * 1024 * 1024
RUN_ID = re.compile(r"i2p-[a-f0-9]{8,64}\Z")
LOOP_NAME = re.compile(r"/dev/loop[0-9]+\Z")
TOOLS = ("losetup", "findmnt", "wipefs", "blkid", "mkfs.ext4", "mount", "umount", "udevadm", "systemd-detect-virt")
COMMAND_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
SYS_BLOCK = Path("/sys/dev/block")


class LoopSafetyError(RuntimeError):
    """A fixed-message refusal, safe to include in the public result."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LoopSafetyError(message)


def _cmd(args: list[str], *, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    """Never forward inherited credentials or return raw command errors."""
    try:
        completed = subprocess.run(args, text=True, capture_output=True, timeout=30, check=False, env=COMMAND_ENV)
    except (OSError, subprocess.TimeoutExpired):
        raise LoopSafetyError("A bounded guest command could not complete") from None
    _require(completed.returncode in allowed, "A bounded guest command returned an unexpected status")
    return completed


def _json_cmd(args: list[str]) -> dict:
    try:
        value = json.loads(_cmd(args).stdout)
    except (ValueError, TypeError):
        raise LoopSafetyError("A guest identity command returned invalid JSON") from None
    _require(isinstance(value, dict), "A guest identity command returned a non-object")
    return value


def _rows(value: dict, key: str) -> list[dict]:
    rows = value.get(key)
    _require(isinstance(rows, list) and all(isinstance(item, dict) for item in rows), "A guest identity result has an unexpected schema")
    return rows


def plan(run_id: str) -> dict:
    """Pure dry run: no filesystem writes or subprocesses."""
    _require(bool(RUN_ID.fullmatch(run_id)), "Run ID must be i2p- followed by 8 to 64 lowercase hex characters")
    return {
        "mode": "DRY_RUN",
        "proof": "capability-primitive-only",
        "run_id": run_id,
        "logical_bytes": SIZE,
        "candidate_policy": "Only a newly allocated loop for this run's exclusive private regular backing file",
        "steps": [
            "Require an authorized GitHub-hosted Ubuntu 24.04 amd64 systemd/cgroup-v2 VM",
            "Create exclusive 0600 sparse backing file inside private job temp",
            "Attach using losetup --find --show --nooverlap; hold returned loop descriptor",
            "Verify backing realpath/inode/device, loop identity, no root ancestry, mounts, partitions, holders, signatures",
            "Format only the verified returned loop with a generated ext4 UUID",
            "Mount the recorded loop in a private new directory; verify UUID and mount identity",
            "Write/read one harmless marker; unmount after rechecking recorded identity",
            "Detach only the still-owned loop; verify detachment; preserve backing file",
        ],
    }


def _mounts() -> list[dict]:
    return _rows(_json_cmd(["findmnt", "--json", "--list", "--output", "SOURCE,TARGET,MAJ:MIN,FSTYPE,UUID"]), "filesystems")


def _environment(workdir: Path) -> Path:
    _require(platform.system() == "Linux" and platform.machine() == "x86_64", "Live loop proof requires Linux amd64")
    _require(os.geteuid() == 0, "Live loop proof requires root inside the disposable runner VM")
    _require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted", "Live loop proof requires the explicitly authorized GitHub-hosted runner")
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    _require(release.get("ID", "").strip('"') == "ubuntu" and release.get("VERSION_ID", "").strip('"') == "24.04", "Live loop proof requires Ubuntu 24.04")
    _require(Path("/proc/1/comm").read_text().strip() == "systemd", "PID 1 must be real systemd")
    _require(any(row.get("target") == "/sys/fs/cgroup" and row.get("fstype") == "cgroup2" for row in _mounts()), "Live loop proof requires a real cgroup-v2 mount")
    _require(all(shutil.which(tool, path=COMMAND_ENV["PATH"]) for tool in TOOLS), "A required guest loop utility is unavailable")
    _require(_cmd(["systemd-detect-virt", "--container"], allowed=(0, 1)).returncode == 1, "Containers are not authorized for live loop proof")
    _require(_cmd(["systemd-detect-virt", "--vm"], allowed=(0, 1)).returncode == 0, "Live loop proof requires a detected virtual machine")
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    _require(bool(runner_temp) and Path(runner_temp).is_absolute(), "RUNNER_TEMP must identify the private hosted job storage parent")
    root = Path(runner_temp).resolve(strict=True)
    _require(workdir.is_absolute() and workdir == workdir.resolve(strict=True), "Work directory must be canonical and free of symlink ancestors")
    _require(root in workdir.parents and workdir != root, "Work directory must be a child of hosted RUNNER_TEMP")
    info = workdir.lstat()
    _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "Work directory must be owned by the running UID with mode 0700")
    _require(shutil.disk_usage(workdir).free >= 256 * 1024 * 1024, "At least 256 MiB free job storage is required")
    return workdir


def _exclusive_json(path: Path, value: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _create_backing(path: Path) -> tuple[int, os.stat_result]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.ftruncate(fd, SIZE)
        os.fsync(fd)
        expected = os.fstat(fd)
        _backing_identity(path, expected)
        return fd, expected
    except BaseException:
        os.close(fd)
        raise


def _backing_identity(path: Path, expected: os.stat_result) -> os.stat_result:
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Backing must remain a unique regular file with one link")
    _require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600, "Backing ownership or private mode changed")
    _require((info.st_dev, info.st_ino, info.st_size) == (expected.st_dev, expected.st_ino, SIZE), "Backing inode, filesystem, or size changed")
    _require(path == path.resolve(strict=True), "Backing path must contain no symlinks")
    return info


def _major_minor(number: int) -> str:
    return f"{os.major(number)}:{os.minor(number)}"


def _loop_info(device: str) -> list[dict]:
    _require(bool(LOOP_NAME.fullmatch(device)), "Only the recorded concrete loop device is permitted")
    return _rows(_json_cmd(["losetup", "--json", "--list", "--output", "NAME,BACK-FILE,BACK-INO,BACK-MAJ:MIN,MAJ:MIN,OFFSET,SIZELIMIT,RO,AUTOCLEAR", device]), "loopdevices")


def _loop_identity(device: str, path: Path, expected: os.stat_result, loop_fd: int) -> tuple[str, Path]:
    _backing_identity(path, expected)
    info = os.fstat(loop_fd)
    current = os.lstat(device)
    _require(stat.S_ISBLK(info.st_mode) and stat.S_ISBLK(current.st_mode) and info.st_rdev == current.st_rdev and os.major(info.st_rdev) == 7, "Recorded descriptor and loop block device identity differ")
    devnum = _major_minor(info.st_rdev)
    rows = _loop_info(device)
    _require(len(rows) == 1, "Recorded loop association is missing or ambiguous")
    row = rows[0]
    _require(row.get("name") == device and row.get("maj:min") == devnum, "Recorded loop device name or major/minor changed")
    _require(row.get("back-file") == str(path) and str(row.get("back-ino")) == str(expected.st_ino) and row.get("back-maj:min") == _major_minor(expected.st_dev), "Loop backing path, inode, or filesystem does not match the exclusive file")
    _require(str(row.get("offset")) == "0" and str(row.get("sizelimit")) == "0", "Loop offset or size limit is unexpected")
    _require(row.get("ro") in (False, 0) and row.get("autoclear") in (False, 0), "Loop read-only or autoclear state is unexpected")
    sysdir = SYS_BLOCK / devnum
    _require(sysdir.resolve(strict=True).name == Path(device).name, "Loop sysfs name differs from the recorded loop")
    _require((sysdir / "loop/backing_file").read_text().strip() == str(path), "Sysfs backing file differs from the exclusive file")
    _require((sysdir / "size").read_text().strip() == str(SIZE // 512), "Loop size differs from the bounded backing size")
    return devnum, sysdir


def _root_ancestry() -> set[str]:
    roots = [row for row in _mounts() if row.get("target") == "/"]
    _require(len(roots) == 1, "Root mount identity is ambiguous")
    root = str(roots[0].get("maj:min", ""))
    _require(bool(re.fullmatch(r"[1-9][0-9]*:[0-9]+", root)), "Root must have a concrete block-device identity")
    seen: set[str] = set()

    def visit(devnum: str) -> None:
        if devnum in seen:
            return
        seen.add(devnum)
        sysdir = (SYS_BLOCK / devnum).resolve(strict=True)
        if (sysdir / "partition").exists():
            visit((sysdir.parent / "dev").read_text().strip())
        slaves = sysdir / "slaves"
        if slaves.exists():
            for slave in slaves.iterdir():
                visit((slave / "dev").read_text().strip())
        else:
            _require((sysdir / "partition").exists(), "Root block topology lacks the expected sysfs relationships")

    visit(root)
    return seen


def _unmounted_and_unstacked(devnum: str, sysdir: Path) -> None:
    _require(devnum not in _root_ancestry(), "The recorded loop is in root-device ancestry")
    _require(not any(row.get("maj:min") == devnum for row in _mounts()), "The recorded loop is mounted")
    _require(not (sysdir / "partition").exists() and not any((child / "partition").exists() for child in sysdir.iterdir()), "The recorded loop has a partition relationship")
    _require(not any((sysdir / "holders").iterdir()) and not any((sysdir / "slaves").iterdir()), "The recorded loop has holders or slaves")
    swap_lines = Path("/proc/swaps").read_text().splitlines()[1:]
    _require(not any(line.split() and line.split()[0] == f"/dev/{sysdir.resolve().name}" for line in swap_lines), "The recorded loop is active swap")


def _blank(device: str) -> None:
    signatures = _rows(_json_cmd(["wipefs", "--no-act", "--json", "--output", "TYPE,UUID", device]), "signatures")
    _require(not signatures, "The recorded newly allocated loop has existing signatures")


def _uuid(device: str, expected_uuid: str) -> None:
    observed = _cmd(["blkid", "-p", "-s", "UUID", "-o", "value", device]).stdout.strip()
    _require(observed == expected_uuid, "The recorded loop filesystem UUID changed")


def _mount_identity(mountdir: Path, device: str, devnum: str, expected_uuid: str, mount_id: int | None = None) -> int:
    rows = _rows(_json_cmd(["findmnt", "--json", "--list", "--mountpoint", str(mountdir), "--output", "ID,SOURCE,TARGET,MAJ:MIN,FSTYPE,UUID"]), "filesystems")
    _require(len(rows) == 1, "The test mount identity is missing or ambiguous")
    row = rows[0]
    _require(row.get("source") == device and row.get("target") == str(mountdir) and row.get("maj:min") == devnum and row.get("fstype") == "ext4" and row.get("uuid") == expected_uuid, "Test mount device, location, filesystem, or UUID differs")
    observed_id = row.get("id")
    _require(isinstance(observed_id, int) or (isinstance(observed_id, str) and observed_id.isdecimal()), "Test mount ID is invalid")
    observed_id = int(observed_id)
    _require(mount_id is None or observed_id == mount_id, "Test mount ID changed")
    all_mounts = _mounts()
    _require(sum(row.get("maj:min") == devnum for row in all_mounts) == 1, "The recorded loop has additional mounts")
    _require(not any(str(row.get("target", "")).startswith(str(mountdir) + "/") for row in all_mounts), "The test mount has unexpected child mounts")
    return observed_id


def _detached(device: str, path: Path) -> bool:
    # A recycled device is observed but never detached again.
    rows = _loop_info(device)
    return not rows or all(row.get("back-file") != str(path) for row in rows)


def run(workdir: Path, run_id: str) -> dict:
    """Run the live bounded probe; preserve the image and sanitized plan/result.

    Preconditions raise LoopSafetyError before resource creation. Subsequent
    failures return FAIL with cleanup status; callers must check status. No
    exception includes subprocess output, inherited environment, or credentials.
    """
    dry_run = plan(run_id)
    workdir = _environment(workdir)
    _exclusive_json(workdir / f"{run_id}-loop-plan.json", dry_run)
    backing = workdir / f"{run_id}-blank.img"
    mountdir = workdir / f"{run_id}-mount"
    result = {"status": "FAIL", "proof": "capability-primitive-only", "run_id": run_id, "checks": ["dry-run-recorded-before-mutation"], "cleanup": {"unmounted": False, "detached": False, "backing_preserved": True}}
    backing_fd = None
    loop_fd = None
    device = None
    expected = None
    expected_uuid = None
    mount_id = None
    attached = False
    attach_attempted = False
    mount_attempted = False
    try:
        backing_fd, expected = _create_backing(backing)
        result["backing"] = {"file": backing.name, "logical_bytes": SIZE, "allocated_before_format_bytes": expected.st_blocks * 512, "mode": "0600", "unique_link": True}
        result["checks"].append("exclusive-private-sparse-backing")
        mountdir.mkdir(mode=0o700)
        attach_attempted = True
        device = _cmd(["losetup", "--find", "--show", "--nooverlap", str(backing)]).stdout.strip()
        _require(bool(LOOP_NAME.fullmatch(device)), "losetup did not return one concrete loop device")
        attached = True
        loop_fd = os.open(device, os.O_RDWR | os.O_NOFOLLOW)
        devnum, sysdir = _loop_identity(device, backing, expected, loop_fd)
        _unmounted_and_unstacked(devnum, sysdir)
        _blank(device)
        # Recheck identity immediately before the only formatting command.
        _loop_identity(device, backing, expected, loop_fd)
        result["checks"].append("blank-loop-path-inode-device-root-mount-holder-partition-signature-gates")
        expected_uuid = str(uuid.uuid4())
        _cmd(["mkfs.ext4", "-q", "-U", expected_uuid, "-E", "lazy_itable_init=0,lazy_journal_init=0", device])
        _loop_identity(device, backing, expected, loop_fd)
        _uuid(device, expected_uuid)
        result["checks"].append("bounded-loop-ext4-created-and-uuid-verified")
        _require(mountdir.is_dir() and not mountdir.is_symlink() and not any(mountdir.iterdir()), "Test mount directory changed or is not empty")
        _unmounted_and_unstacked(devnum, sysdir)
        mount_attempted = True
        _cmd(["mount", "--no-mtab", "-t", "ext4", "-o", "nodev,nosuid,noexec", "--source", device, "--target", str(mountdir)])
        mount_id = _mount_identity(mountdir, device, devnum, expected_uuid)
        marker = mountdir / "i2p-harmless-marker.txt"
        marker_content = f"{run_id}: guest-only bounded loop primitive\n"
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(marker_content)
            stream.flush()
            os.fsync(stream.fileno())
        _require(marker.read_text() == marker_content, "Harmless loop marker did not round-trip")
        result["checks"].append("real-mount-and-marker-round-trip")
        result["loop"] = {"device": device, "major_minor": devnum, "filesystem_uuid": expected_uuid, "mount_id": mount_id, "root_ancestry_excluded": True}
    except LoopSafetyError as error:
        result["error"] = str(error)
    except (OSError, ValueError, KeyError, TypeError):
        result["error"] = "A guest filesystem operation or identity parse failed; raw details suppressed"
    finally:
        try:
            if attached:
                _require(loop_fd is not None and expected is not None and device is not None, "Loop cleanup lacks a held descriptor; no detach attempted")
                devnum, sysdir = _loop_identity(device, backing, expected, loop_fd)
                if mount_attempted:
                    mounted_here = any(row.get("target") == str(mountdir) for row in _mounts())
                    if mounted_here:
                        _require(expected_uuid is not None, "Mount cleanup lacks the expected UUID")
                        _uuid(device, expected_uuid)
                        _mount_identity(mountdir, device, devnum, expected_uuid, mount_id)
                        _cmd(["umount", "--no-mtab", str(mountdir)])
                _unmounted_and_unstacked(devnum, sysdir)
                result["cleanup"]["unmounted"] = True
                _loop_identity(device, backing, expected, loop_fd)
                if expected_uuid is not None:
                    _uuid(device, expected_uuid)
                _cmd(["losetup", "--detach", device])
                os.close(loop_fd)
                loop_fd = None
                _cmd(["udevadm", "settle", "--timeout=10"])
                for _ in range(20):
                    if _detached(device, backing):
                        result["cleanup"]["detached"] = True
                        break
                    time.sleep(0.1)
                _require(result["cleanup"]["detached"], "Owned backing remains attached after bounded cleanup wait")
            elif not attach_attempted:
                result["cleanup"]["unmounted"] = True
                result["cleanup"]["detached"] = True
            else:
                result["cleanup"]["allocation_identity"] = "UNKNOWN"
                raise LoopSafetyError("Loop allocation did not yield verified ownership; no detach attempted")
            if expected is not None:
                final_info = _backing_identity(backing, expected)
                result["backing"]["allocated_after_format_bytes"] = final_info.st_blocks * 512
            if mountdir.exists():
                _require(not mountdir.is_symlink() and not any(row.get("target") == str(mountdir) for row in _mounts()), "Mount directory cleanup refused due to changed identity")
                mountdir.rmdir()
        except LoopSafetyError as error:
            result["cleanup"]["error"] = str(error)
        except (OSError, ValueError, KeyError, TypeError):
            result["cleanup"]["error"] = "Cleanup could not prove resource identity; no further cleanup attempted"
        finally:
            if loop_fd is not None:
                os.close(loop_fd)
            if backing_fd is not None:
                os.close(backing_fd)
    if "error" not in result and "error" not in result["cleanup"] and result["cleanup"]["detached"] and result["cleanup"]["unmounted"]:
        result["status"] = "PASS"
        result["checks"].append("identity-checked-unmount-detach-and-preserved-backing")
    _exclusive_json(workdir / f"{run_id}-loop-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, help="Existing private canonical directory under hosted RUNNER_TEMP")
    parser.add_argument("--run-id", required=True, help="i2p- plus 8 to 64 lowercase hexadecimal characters")
    parser.add_argument("--dry-run", action="store_true", help="Print the pure plan; do not inspect or change devices")
    args = parser.parse_args()
    try:
        if args.dry_run:
            result = plan(args.run_id)
        else:
            if args.workdir is None:
                parser.error("--workdir is required for a live hosted-VM run")
            result = run(args.workdir, args.run_id)
    except LoopSafetyError as error:
        result = {"status": "FAIL", "error": str(error)}
    except OSError:
        result = {"status": "FAIL", "error": "A live-run precondition could not be inspected"}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" or result.get("mode") == "DRY_RUN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
