#!/usr/bin/env python3
"""Private companion to loop_disk_transaction.sh; never accepts physical disks.

Only GPT, ext4, mounts and their recovery are real-device assertions here. The
fixture supplies loop-only topology, a backing-inode-derived serial, and a
synthetic root identity because a disposable container may use overlay root.
Production disk/serial/root exclusion is covered separately by unit fixtures.
There are no production environment overrides and this module is not imported
by the installer.
"""
from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import struct
import sys
import time
import uuid


SIZE = 256 * 1024 * 1024
DEV_BYTES = 1024 * 1024
DEV_INODES = 64
PRODUCERS_UNCERTAIN = False
ROOT_UUID = "00000000-0000-4000-8000-000000000001"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def diagnostic(event, **fields):
    print("I2SF_DIAGNOSTIC: " + json.dumps(dict(event=event, **fields), sort_keys=True), flush=True)


def sanitized_error(value):
    # Only fixed tool errors and task-owned paths are useful evidence. Never dump
    # environment, arbitrary argv, stdout or device contents.
    text = str(value or "")[:2048]
    text = re.sub(r"(?i)(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*\S+",
                  r"\1=[REDACTED]", text)
    return "".join(c if c.isprintable() or c == "\n" else "?" for c in text)


def command_result(argv, **kwargs):
    global PRODUCERS_UNCERTAIN
    process = subprocess.Popen(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, start_new_session=True,
                               env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}, **kwargs)
    try:
        out, err = process.communicate(timeout=30)
    except BaseException:
        # No cleanup while an unaccounted command could still be producing work.
        # The disposable VM is the final containment boundary.
        PRODUCERS_UNCERTAIN = True
        raise
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        pass
    else:
        PRODUCERS_UNCERTAIN = True
        raise RuntimeError("fixture command has surviving producers; preserve scratch")
    require(len(out) <= 262144 and len(err) <= 65536, "fixture command output limit")
    return subprocess.CompletedProcess(argv, process.returncode, out, err)


def execute(argv, **kwargs):
    result = command_result(argv, **kwargs)
    if result.returncode:
        diagnostic("command_failed", tool=Path(argv[0]).name, returncode=result.returncode,
                   stderr=sanitized_error(result.stderr))
        raise RuntimeError("fixture command failed: " + Path(argv[0]).name + ":rc=" + str(result.returncode))
    return result.stdout


def protected(path, directory=False):
    info = path.lstat()
    require(info.st_uid == 0 and not info.st_mode & 0o077,
            "fixture path must be root-owned and private")
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
            "unexpected fixture path type")
    if not directory:
        require(info.st_nlink == 1, "fixture file has multiple links")
    return info


def record_owned(identity_file, backing):
    require(os.geteuid() == 0, "root required")
    root = identity_file.parent
    require(root.parent == Path("/run") and re.fullmatch(r"i1s-loop-[A-Za-z0-9]+", root.name),
            "scratch must be a freshly allocated /run fixture directory")
    require(identity_file.name == "ownership.json" and backing == root / "backing.img",
            "invalid internal fixture layout")
    root_info = protected(root, directory=True)
    backing_info = protected(backing)
    require(backing_info.st_size == SIZE, "unexpected sparse backing size")
    data = {"schema": 1, "token": str(uuid.uuid4()), "root": str(root),
            "root_device": root_info.st_dev, "root_inode": root_info.st_ino,
            "backing": str(backing), "backing_device": backing_info.st_dev,
            "backing_inode": backing_info.st_ino, "size": SIZE}
    with identity_file.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def identity(identity_file):
    require(os.geteuid() == 0, "root required")
    require(identity_file.name == "ownership.json" and identity_file.parent.parent == Path("/run"),
            "invalid ownership record location")
    info = protected(identity_file)
    require(info.st_size < 4096, "oversized ownership record")
    data = json.loads(identity_file.read_text())
    root = Path(data["root"])
    require(identity_file == root / "ownership.json" and
            re.fullmatch(r"i1s-loop-[A-Za-z0-9]+", root.name), "fixture root changed")
    root_info = protected(root, directory=True)
    backing = Path(data["backing"])
    require(backing == root / "backing.img", "backing path changed")
    backing_info = protected(backing)
    require((root_info.st_dev, root_info.st_ino) == (data["root_device"], data["root_inode"]),
            "fixture root identity changed")
    require((backing_info.st_dev, backing_info.st_ino, backing_info.st_size) ==
            (data["backing_device"], data["backing_inode"], SIZE), "backing identity changed")
    return data


def update_identity(identity_file, data):
    identity(identity_file)
    with identity_file.open("w") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def active_loops():
    result = json.loads(execute(["losetup", "--list", "--json", "--output",
                                "NAME,BACK-FILE,BACK-INO,BACK-MAJ:MIN,MAJ:MIN,OFFSET,SIZELIMIT,RO,AUTOCLEAR"]))
    rows = result.get("loopdevices")
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows),
            "active loop inventory unavailable")
    for row in rows:
        require(re.fullmatch(r"/dev/loop[0-9]+", row.get("name", "")) and
                row.get("back-file") and str(row.get("back-ino", "")).isdigit() and
                re.fullmatch(r"[0-9]+:[0-9]+", row.get("back-maj:min", "")),
                "active loop backing identity unavailable")
    return rows


def backing_matches(data, row):
    return (str(row.get("back-ino")) == str(data["backing_inode"]) and
            row.get("back-maj:min") == f'{os.major(data["backing_device"])}:{os.minor(data["backing_device"])}')


def loop_node(loop):
    require(re.fullmatch(r"/dev/loop[0-9]+", loop), "physical and caller-selected disks are forbidden")
    info = Path(loop).lstat()
    require(stat.S_ISBLK(info.st_mode) and os.major(info.st_rdev) == 7,
            "selected fixture device is not a loop block device")
    sysdir = Path("/sys/class/block") / Path(loop).name
    sysinfo = sysdir.stat()
    key = {"name": loop, "rdev": info.st_rdev, "sysfs": str(sysdir.resolve(strict=True)),
           "sysfs_device": sysinfo.st_dev, "sysfs_inode": sysinfo.st_ino}
    require((sysdir / "dev").read_text().strip() ==
            f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}", "sysfs loop device changed")
    return key, sysdir


def association(data, loop):
    key, sysdir = loop_node(loop)
    if "loop" in data:
        require(key == data["loop"], "recorded loop/sysfs identity changed")
    rows = active_loops()
    matching = [row for row in rows if backing_matches(data, row)]
    selected = [row for row in rows if row.get("name") == loop]
    sysfile = sysdir / "loop/backing_file"
    try:
        backing = sysfile.read_text().strip()
    except FileNotFoundError:
        backing = None
    if not selected:
        require(not matching and backing is None and int((sysdir / "size").read_text()) == 0,
                "detached loop identity or backing association unknown")
        return "unbound", key
    require(len(selected) == 1 and len(matching) == 1 and selected == matching,
            "loop recycled or backing association ambiguous")
    row = selected[0]
    require(row.get("back-file") == data["backing"] and backing == data["backing"] and
            row.get("maj:min") == f'{os.major(key["rdev"])}:{os.minor(key["rdev"])}',
            "kernel/sysfs backing identity changed")
    require(int(row.get("offset", -1)) == 0 and int(row.get("sizelimit", -1)) == 0 and
            row.get("ro") in (False, 0) and row.get("autoclear") in (False, 0),
            "loop geometry or mode changed")
    require(int((sysdir / "size").read_text()) == SIZE // 512 and
            int((sysdir / "queue/logical_block_size").read_text()) == 512,
            "loop size or logical sector changed")
    for child in ("holders", "slaves"):
        require(not any((sysdir / child).iterdir()), "fixture loop acquired " + child)
    return "owned", key


def owned(identity_file, loop):
    data = identity(identity_file)
    state, _ = association(data, loop)
    require(state == "owned", "fixture loop is not actively owned")
    return data


def record_loop(identity_file, loop):
    data = owned(identity_file, loop)
    require("loop" not in data, "loop identity already recorded")
    data["loop"] = loop_node(loop)[0]
    update_identity(identity_file, data)
    diagnostic("loop_identity", loop=data["loop"], backing_inode=data["backing_inode"],
               backing_filesystem=f'{os.major(data["backing_device"])}:{os.minor(data["backing_device"])}',
               backing_bytes=SIZE, logical_sector_bytes=512, offset=0, sizelimit=0)


def mount_rows():
    rows = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        split = fields.index("-")
        rows.append({"id": fields[0], "parent": fields[1], "dev": fields[2], "root": fields[3],
                     "target": fields[4], "options": fields[5], "optional": fields[6:split],
                     "fstype": fields[split + 1], "source": fields[split + 2],
                     "super_options": fields[split + 3]})
    return rows


def containing_mount(path):
    candidates = [r for r in mount_rows() if str(path) == r["target"] or
                  str(path).startswith(r["target"].rstrip("/") + "/")]
    require(candidates, "containing mount unavailable")
    length = max(len(r["target"]) for r in candidates)
    matches = [r for r in candidates if len(r["target"]) == length]
    require(len(matches) == 1, "ambiguous containing mount")
    return matches[0]


def exact_mount(target, expected):
    rows = [r for r in mount_rows() if r["target"] == str(target)]
    require(rows == [expected], "owned mount ID or flags changed")


def record_sysfs(identity_file):
    data = identity(identity_file)
    check_sysfs(identity_file, require_record=False)
    data["sys_mount"] = containing_mount(Path(data["root"]) / "root/sys")
    update_identity(identity_file, data)


def detach_descriptor(identity_file, loop):
    # Linux LOOP_CLR_FD waits for the last opener. Pinning this descriptor across
    # final status/sysfs checks prevents detach/rebind by another name opener.
    # It is acquired only during cleanup, never across production busy probes.
    data = owned(identity_file, loop)
    fd = os.open(loop, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISBLK(info.st_mode) and info.st_rdev == data["loop"]["rdev"],
                "cleanup descriptor differs from recorded loop")
        owned(identity_file, loop)
        layout = "=QQQQQIIII64s64s32sQQ"  # Linux uapi struct loop_info64, 232 bytes
        raw = fcntl.ioctl(fd, 0x4C05, bytes(struct.calcsize(layout)))  # LOOP_GET_STATUS64
        fields = struct.unpack(layout, raw)
        require(fields[:5] == (data["backing_device"], data["backing_inode"], 0, 0, 0) and
                fields[5] == int(Path(loop).name[4:]) and fields[6:8] == (0, 0) and fields[8] in (0, 8),
                "cleanup descriptor backing identity or geometry changed")
        fcntl.ioctl(fd, 0x4C01, 0)  # LOOP_CLR_FD: exactly once, on the verified fd
        diagnostic("detach_request", interface="LOOP_CLR_FD", descriptor_identity_checked=True)
    finally:
        os.close(fd)


def detach_owned(identity_file, loop):
    data = identity(identity_file)
    require("loop" in data, "recorded loop identity unavailable")
    require(not (Path(data["root"]) / "producer.pending").exists(), "producer lifetime unresolved")
    # No unknown or data mounts may remain when detaching. Never try to unmount
    # an unexpected resource to make this check pass.
    for row in mount_rows():
        if row["target"].startswith(data["root"] + "/"):
            require(row in [data.get("sys_mount"), data.get("dev_mount")], "unexpected fixture mount before detach")
    state, _ = association(data, loop)
    if state == "owned":
        detach_descriptor(identity_file, loop)
    for _ in range(30):
        state, _ = association(data, loop)
        if state == "unbound":
            diagnostic("detach", status="PASS", active_backing_absent=True,
                       original_sysfs_backing_absent=True, detach_retries=0)
            return
        time.sleep(0.1)
    raise RuntimeError("exact owned loop remains active; preserve scratch")


def remove_owned(identity_file):
    data = identity(identity_file)
    require(not (Path(data["root"]) / "producer.pending").exists(), "producer lifetime unresolved")
    require(not any(backing_matches(data, row) or row.get("back-file") == data["backing"]
                    for row in active_loops()), "backing remains associated; refusing cleanup")
    if "loop" in data:
        require(association(data, data["loop"]["name"])[0] == "unbound", "loop detach not verified")
    root = data["root"]
    for row in mount_rows():
        require(row["target"] != root and not row["target"].startswith(root + "/"),
                "fixture still has mounted paths; refusing cleanup")
    require(shutil.rmtree.avoids_symlink_attacks, "platform lacks anchored safe cleanup")
    shutil.rmtree(root)
    diagnostic("scratch_cleanup", status="PASS")


def check_mount(identity_file, loop):
    data = owned(identity_file, loop)
    root = Path(data["root"]) / "root"
    target = root / "data"
    rows = json.loads(execute(["findmnt", "--json", "--mountpoint", str(target), "--output",
                               "TARGET,MAJ:MIN,FSTYPE,UUID"])).get("filesystems", [])
    require(len(rows) == 1 and rows[0].get("target") == str(target) and rows[0].get("fstype") == "ext4",
            "cleanup target is not the exact owned ext4 mount")
    sysdisk = Path("/sys/class/block") / Path(loop).name
    partitions = [p for p in sysdisk.glob(Path(loop).name + "p*") if (p / "partition").exists()]
    require(len(partitions) == 1 and (partitions[0] / "dev").read_text().strip() == rows[0].get("maj:min"),
            "cleanup mount is not on the exact owned loop partition")
    journal_path = root / "etc/local-ai-server/disk-initialization.json"
    protected(journal_path)
    require(rows[0].get("uuid") == json.loads(journal_path.read_text())["ids"]["filesystem_uuid"],
            "cleanup mount UUID differs from the protected journal")


def check_sysfs(identity_file, require_record=True):
    data = identity(identity_file)
    target = Path(data["root"]) / "root/sys"
    require(not require_record or "sys_mount" in data, "sysfs mount ownership unavailable")
    if "sys_mount" in data:
        exact_mount(target, data["sys_mount"])
    rows = json.loads(execute(["findmnt", "--json", "--mountpoint", str(target), "--output",
                               "TARGET,FSTYPE"])).get("filesystems", [])
    require(len(rows) == 1 and rows[0].get("target") == str(target) and rows[0].get("fstype") == "sysfs"
            and target.stat().st_dev == Path("/sys").stat().st_dev,
            "cleanup sysfs bind identity changed")


def expected_nodes(data, loop):
    owned(Path(data["root"]) / "ownership.json", loop)
    sysdisk = Path("/sys/class/block") / Path(loop).name
    nodes = [sysdisk] + [p for p in sysdisk.glob(Path(loop).name + "p*") if (p / "partition").exists()]
    require(len(nodes) <= 2, "fixture has unexpected partitions")
    result = {}
    for sysnode in nodes:
        require(sysnode == sysdisk or (sysnode.parent == sysdisk and
                (sysnode / "partition").read_text().strip() == "1"), "foreign partition node")
        major, minor = map(int, (sysnode / "dev").read_text().strip().split(":"))
        require(major == 7 or sysnode.parent == sysdisk, "foreign fixture device major")
        result[sysnode.name] = os.makedev(major, minor)
    return result


def sync_nodes(identity_file, loop):
    data = owned(identity_file, loop)
    dev = Path(data["root"]) / "root/dev"
    if "dev_mount" in data:
        check_dev_mount(identity_file)
    nodes = expected_nodes(data, loop)
    for name, rdev in nodes.items():
        node = dev / name
        if node.exists() or node.is_symlink():
            info = node.lstat()
            require(stat.S_ISBLK(info.st_mode) and info.st_rdev == rdev and
                    info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                    "fixture block node identity changed")
        else:
            os.mknod(node, stat.S_IFBLK | 0o600, rdev)
    data["private_nodes"] = nodes
    update_identity(identity_file, data)


def probe_node(identity_file, loop, phase):
    data = owned(identity_file, loop)
    node = Path(data["root"]) / "root/dev" / Path(loop).name
    info = node.lstat()
    require(stat.S_ISBLK(info.st_mode) and info.st_rdev == data["loop"]["rdev"], "probe node changed")
    mount = containing_mount(node)
    error_number = None
    try:
        fd = os.open(node, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        error_number = exc.errno
    else:
        try:
            require(os.fstat(fd).st_rdev == info.st_rdev, "probe descriptor changed")
        finally:
            os.close(fd)
    result = command_result(["wipefs", "--no-act", "--json", "--output", "DEVICE,OFFSET,TYPE,UUID,LABEL", str(node)])
    observation = {"phase": phase, "node": str(node), "major": os.major(info.st_rdev),
                   "minor": os.minor(info.st_rdev), "containing_mount": mount,
                   "open_errno": error_number, "open_errno_name": errno.errorcode.get(error_number),
                   "wipefs_returncode": result.returncode, "wipefs_stderr": sanitized_error(result.stderr)}
    diagnostic("node_probe", **observation)
    if result.returncode == 0:
        signatures = json.loads(result.stdout).get("signatures")
        require(isinstance(signatures, list), "signature discovery incomplete")
        require(not signatures, "new fixture backing unexpectedly has signatures")
    return observation


def nodev_confirmed(observation):
    return ("nodev" in observation["containing_mount"]["options"].split(",") and
            observation["open_errno"] == errno.EACCES and observation["wipefs_returncode"] != 0)


def validate_dev_mount(row, target, usage):
    require(row["target"] == str(target) and row["root"] == "/" and row["fstype"] == "tmpfs" and
            row["source"] == "i2sf-owned-dev" and not row["optional"], "private device mount identity invalid")
    options = set(row["options"].split(","))
    require({"rw", "nosuid", "noexec"} <= options and "nodev" not in options,
            "private device mount flags invalid")
    require(0 < usage.f_blocks * usage.f_frsize <= DEV_BYTES and 0 < usage.f_files <= DEV_INODES,
            "private device mount size or inode limit invalid")
    info = target.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
            "private device directory protection changed")


def check_dev_mount(identity_file):
    data = identity(identity_file)
    require("dev_mount" in data, "device mount ownership unavailable")
    target = Path(data["root"]) / "root/dev"
    exact_mount(target, data["dev_mount"])
    validate_dev_mount(data["dev_mount"], target, os.statvfs(target))
    return data


def prepare_devices(identity_file, loop):
    data = owned(identity_file, loop)
    root = Path(data["root"]) / "root"
    target = root / "dev"
    target.mkdir(mode=0o700, exist_ok=True)
    require(not list(target.iterdir()), "device scratch must start empty")
    sync_nodes(identity_file, loop)
    observation = probe_node(identity_file, loop, "original_before_transaction")
    if nodev_confirmed(observation):
        parent = os.environ.get("I1S_FIXTURE_PARENT_NAMESPACE")
        require(parent and os.readlink("/proc/self/ns/mnt") != parent,
                "private namespace required for device mount")
        require(execute(["findmnt", "--raw", "--noheadings", "--output", "PROPAGATION", "--target", "/"]).strip() == "private",
                "namespace propagation not private")
        require(not any(r["target"] == str(target) or r["target"].startswith(str(target) + "/")
                        for r in mount_rows()), "device target already mounted")
        owned(identity_file, loop)
        execute(["mount", "-t", "tmpfs", "-o", "rw,nosuid,noexec,mode=0700,size=1M,nr_inodes=64",
                 "i2sf-owned-dev", str(target)])
        # Record immediately; any failure to capture or validate preserves scratch.
        data["dev_mount"] = containing_mount(target)
        update_identity(identity_file, data)
        check_dev_mount(identity_file)
        diagnostic("device_tmpfs", mount=data["dev_mount"], size_limit_bytes=DEV_BYTES, inode_limit=DEV_INODES)
        sync_nodes(identity_file, loop)
        observation = probe_node(identity_file, loop, "private_dev_before_transaction")
    require(observation["open_errno"] is None and observation["wipefs_returncode"] == 0,
            "read-only device/signature diagnostic failed; no transaction")


def remove_dev_mount(identity_file):
    data = identity(identity_file)
    require(not (Path(data["root"]) / "producer.pending").exists(), "producer lifetime unresolved")
    target = Path(data["root"]) / "root/dev"
    if "dev_mount" not in data:
        require(not any(r["target"] == str(target) or r["target"].startswith(str(target) + "/")
                        for r in mount_rows()), "unrecorded device mount; preserve scratch")
        return
    check_dev_mount(identity_file)
    # Device nodes remain after detach; validate against the inventory saved
    # while association ownership was live. No arbitrary /dev content allowed.
    nodes = data.get("private_nodes", {})
    allowed_dirs = {target / "disk", target / "disk/by-id"}
    link = target / "disk/by-id" / ("scsi-i1s-fixture-" + data["token"])
    for path in target.rglob("*"):
        info = path.lstat()
        if path in allowed_dirs:
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                    "private device directory changed")
        elif path == link:
            require(stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and
                    os.readlink(path) == "../../" + Path(data["loop"]["name"]).name, "fixture by-id changed")
        else:
            require(path.parent == target and path.name in nodes and stat.S_ISBLK(info.st_mode) and
                    info.st_rdev == nodes[path.name] and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                    "unexpected private device content")
    for row in mount_rows():
        require(not row["target"].startswith(str(target) + "/"), "unexpected device descendant mount")
    exact_mount(target, data["dev_mount"])
    execute(["umount", "--", str(target)])
    require(not any(r["target"] == str(target) or r["target"].startswith(str(target) + "/") for r in mount_rows()),
            "device mount remains after unmount")
    diagnostic("device_tmpfs_cleanup", status="PASS", removed_mount_id=data["dev_mount"]["id"])


class SimulatedInterruption(RuntimeError):
    """Command succeeded; deliberately prevent its durable stage receipt."""


def run_fixture(identity_file, loop):
    parent_namespace = os.environ.get("I1S_FIXTURE_PARENT_NAMESPACE")
    require(parent_namespace and os.readlink("/proc/self/ns/mnt") != parent_namespace,
            "run the shell wrapper to create a private mount namespace first")
    metadata = owned(identity_file, loop)
    root = Path(metadata["root"]) / "root"
    root.mkdir(mode=0o700, exist_ok=True)
    prepare_devices(identity_file, loop)
    for path in (root / "dev/disk/by-id", root / "etc", root / "data"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    by_id = "scsi-i1s-fixture-" + metadata["token"]
    link = root / "dev/disk/by-id" / by_id
    link.symlink_to("../../" + Path(loop).name)
    old_fstab = b"# I1S fixture keeps exact bytes, including CRLF\r\nUUID=old-root / ext4 defaults 0 1\n\n\n"
    (root / "etc/fstab").write_bytes(old_fstab)
    os.chmod(root / "etc/fstab", 0o600)

    install_parent = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(install_parent))
    disk_init = importlib.import_module("install.disk_init")
    storage_module = importlib.import_module("install.storage")

    def sync_fixture_nodes():
        sync_nodes(identity_file, loop)

    class FixtureRunner:
        """Translate fixture paths; real loop data, synthetic container root only."""
        writable = True

        def run(self, argv, timeout=30):
            owned(identity_file, loop)
            argv = list(argv)
            if argv[0] == "lsblk":
                rows = json.loads(execute(argv + [loop]))
                require(len(rows.get("blockdevices", [])) == 1, "fixture loop topology is ambiguous")
                top = rows["blockdevices"][0]
                require((top.get("path") or top.get("name")) == loop and top.get("type") == "loop",
                        "unexpected fixture loop topology")
                top["type"] = "disk"
                top["serial"] = "fixture-inode-" + str(metadata["backing_inode"])
                top["wwn"] = None
                def logical_mounts(row):
                    row["mountpoints"] = [str(p)[len(str(root)):] if str(p).startswith(str(root) + "/") else p
                                          for p in (row.get("mountpoints") or [])]
                    for child in row.get("children", []):
                        logical_mounts(child)
                logical_mounts(top)
                rows["blockdevices"].append({"name": "/dev/i1s-fixture-root", "path": "/dev/i1s-fixture-root",
                    "type": "disk", "pkname": None, "mountpoints": ["/"], "fstype": "ext4",
                    "uuid": ROOT_UUID, "size": 1, "wwn": None, "serial": "synthetic-root",
                    "ro": False, "maj:min": "0:65535"})
                return json.dumps(rows)
            if argv[0] == "findmnt":
                position = argv.index("--target") + 1
                target = argv[position]
                if target in ("/", "/boot", "/boot/efi"):
                    return json.dumps({"filesystems": [{"target": "/", "source": "/dev/i1s-fixture-root",
                        "uuid": ROOT_UUID, "fstype": "ext4", "options": "rw", "maj:min": "0:65535"}]})
                argv[position] = str(root / target.lstrip("/"))
                answer = json.loads(execute(argv))
                for row in answer.get("filesystems", []):
                    mount = row.get("target", "")
                    if mount == str(root) or mount.startswith(str(root) + "/"):
                        row["target"] = mount[len(str(root)):] or "/"
                return json.dumps(answer)
            if argv[0] == "df":
                if argv[-1] != "/":
                    argv[-1] = str(root / argv[-1].lstrip("/"))
                return execute(argv)
            if argv[0] == "wipefs":
                require(argv[-1] == loop or re.fullmatch(re.escape(loop) + r"p[0-9]+", argv[-1]),
                        "signature probe escaped the owned loop")
                require("--no-act" in argv, "fixture signature probe is not read-only")
                argv[-1] = str(root / argv[-1].lstrip("/"))
                return execute(argv)
            raise RuntimeError("unexpected Storage fixture command: " + argv[0])

    class FixtureDiskIO(disk_init.DiskIO):
        def __init__(self, subject):
            super().__init__(subject)
            self.interrupt_after = None
            self.mutations = []

        def observe(self):
            owned(identity_file, loop)
            sync_fixture_nodes()
            return super().observe()

        @contextlib.contextmanager
        def open_device(self, source, row, write=False):
            owned(identity_file, loop)
            require(source == loop or re.fullmatch(re.escape(loop) + r"p[0-9]+", source),
                    "fixture attempted to open another device")
            with super().open_device(source, row, write=write) as fd:
                yield fd

        def command(self, argv, timeout=30, input_text=None, pass_fds=()):
            owned(identity_file, loop)
            allowed = {"sfdisk", "mkfs.ext4", "wipefs", "blkid", "mount", "udevadm",
                       "blockdev", "lsblk", "findmnt", "dumpe2fs", "tune2fs", "e2fsck"}
            name = Path(argv[0]).name
            require(name in allowed, "unexpected disk fixture command: " + name)
            if name == "lsblk":
                # The fixture never probes a physical disk. Global duplicate-ID
                # exclusion remains a separate production/unit assertion.
                argv = list(argv) + [loop]
            for fd in pass_fds:
                info = os.fstat(fd)
                if stat.S_ISBLK(info.st_mode):
                    require(any((root / "dev" / n).stat().st_rdev == info.st_rdev
                                for n in os.listdir(root / "dev")
                                if re.fullmatch(re.escape(Path(loop).name) + r"(?:p[0-9]+)?", n)),
                            "foreign block descriptor passed to fixture command")
            diagnostic("production_command_start", tool=name)
            try:
                result = super().command(argv, timeout=timeout, input_text=input_text, pass_fds=pass_fds)
            except Exception as exc:
                global PRODUCERS_UNCERTAIN
                PRODUCERS_UNCERTAIN = True
                diagnostic("production_command_failed", tool=name, error_type=type(exc).__name__,
                           error=sanitized_error(exc), returncode="not_exposed_by_production_DiskIO")
                raise
            diagnostic("production_command_complete", tool=name)
            if name in {"sfdisk", "mkfs.ext4", "mount"} and not any(x in argv for x in ("--json", "--dump", "--verify", "--list")):
                self.mutations.append(name)
                if name == "sfdisk":
                    execute(["udevadm", "settle", "--timeout=10"])
                    sync_fixture_nodes()
                if self.interrupt_after == name:
                    self.interrupt_after = None
                    raise SimulatedInterruption("injected after successful " + name + " before receipt")
            return result

    sync_fixture_nodes()
    config = {"storage_mode": "initialize", "initialize_empty_disk": "/dev/disk/by-id/" + by_id,
              "confirm_disk_id": by_id, "data_dir": "/data", "model_dir": "/data/models"}
    subject = storage_module.Storage(config, FixtureRunner(), root)
    io = FixtureDiskIO(subject)
    diagnostic("transaction_start", source="scripts/install/disk_init.py",
               production_source_sha256=hashlib.sha256(Path(disk_init.__file__).read_bytes()).hexdigest())
    saved_plan = disk_init.plan(subject, io=io)
    plan_file = Path(metadata["root"]) / "plan.json"
    plan_file.write_text(json.dumps(saved_plan, sort_keys=True) + "\n")
    os.chmod(plan_file, 0o600)
    subject.config["disk_plan"] = str(plan_file)
    journal_file = root / "etc/local-ai-server/disk-initialization.json"
    for command, expected_stage in (("sfdisk", "gpt_intent"), ("mkfs.ext4", "fs_intent")):
        io.interrupt_after = command
        try:
            disk_init.initialize(subject, io=io)
        except SimulatedInterruption:
            pass
        else:
            raise RuntimeError("expected pre-receipt interruption did not happen")
        require(json.loads(journal_file.read_text())["stage"] == expected_stage,
                "interrupted journal does not retain the intended stage")

    registration = disk_init.initialize(subject, io=io)
    journal = json.loads(journal_file.read_text())
    require(journal["stage"] == "complete", "transaction did not complete")
    require(io.mutations.count("sfdisk") == 1 and io.mutations.count("mkfs.ext4") == 1,
            "recovery repeated partitioning or formatting")
    before = (journal_file.read_bytes(), (root / "etc/fstab").read_bytes(), list(io.mutations))
    second = disk_init.initialize(subject, io=io)
    require(before == (journal_file.read_bytes(), (root / "etc/fstab").read_bytes(), io.mutations),
            "completed replay mutated journal/fstab/disk")
    require(registration["data"]["uuid"] == second["data"]["uuid"] == journal["ids"]["filesystem_uuid"],
            "returned registration does not match owned filesystem")
    fstab = (root / "etc/fstab").read_bytes()
    require(fstab.startswith(old_fstab) and fstab.count(b"UUID=" + journal["ids"]["filesystem_uuid"].encode()) == 1,
            "fstab bytes were changed or owned entry was duplicated")
    owned(identity_file, loop)
    table = json.loads(execute(["sfdisk", "--json", loop]))["partitiontable"]
    require(table["label"] == "gpt" and len(table["partitions"]) == 1,
            "real GPT is not the declared single-partition layout")
    require(table["id"].lower() == journal["ids"]["disk_guid"].lower(),
            "real GPT disk GUID differs from intended identity")
    partition = table["partitions"][0]
    require((partition["start"], partition["size"]) ==
            (saved_plan["shape"]["start_sector"], saved_plan["shape"]["size_sectors"]),
            "real partition alignment or size differs from saved plan")
    require(partition["uuid"].lower() == journal["ids"]["partition_uuid"].lower(),
            "real GPT partition UUID differs from journal")
    partition_node = root / "dev" / Path(partition["node"]).name
    require(partition_node.exists(), "owned partition node is absent")
    details = dict(line.split("=", 1) for line in execute(["blkid", "--probe", "--output", "export",
                                                          str(partition_node)]).splitlines() if "=" in line)
    require(details.get("TYPE") == "ext4" and details.get("UUID") == journal["ids"]["filesystem_uuid"]
            and details.get("LABEL") == journal["ids"]["filesystem_label"],
            "real ext4 UUID/label/type differ from intended identities")
    tuning = execute(["tune2fs", "-l", str(partition_node)])
    require(re.search(r"^Reserved block count:\s+0$", tuning, re.MULTILINE),
            "real ext4 reserved block count is not zero")
    check_mount(identity_file, loop)
    print("PASS: real loop GPT/ext4, exact intended UUIDs/label/-m0, pre-receipt recovery,")
    print("private mount/registration, byte-preserving fstab, and completed no-op replay.")
    print("Fixture-only loop type/serial/root adapters do not prove production hardware exclusion.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_mutually_exclusive_group(required=True)
    operations.add_argument("--dry-run", action="store_true", help="print the companion's bounded operations without writing")
    operations.add_argument("--record-owned", nargs=2, metavar=("RECORD", "BACKING"))
    operations.add_argument("--record-loop", nargs=2, metavar=("RECORD", "LOOP"))
    operations.add_argument("--detach-owned", nargs=2, metavar=("RECORD", "LOOP"))
    operations.add_argument("--record-sysfs", metavar="RECORD")
    operations.add_argument("--remove-dev-mount", metavar="RECORD")
    operations.add_argument("--check-owned", nargs=2, metavar=("RECORD", "LOOP"))
    operations.add_argument("--check-mount", nargs=2, metavar=("RECORD", "LOOP"))
    operations.add_argument("--check-sysfs", metavar="RECORD")
    operations.add_argument("--remove-owned", metavar="RECORD")
    operations.add_argument("--run", nargs=2, metavar=("RECORD", "LOOP"))
    args = parser.parse_args()
    if args.dry_run:
        print("DRY_RUN: private wrapper creates its own sparse backing and loop; this companion")
        print("checks exact ownership, runs only the owned loop transaction, and guards cleanup.")
        print("Invoke loop_disk_transaction.sh --dry-run for Linux prerequisite verification.")
        return
    require(sys.platform == "linux", "NOT_TESTED: Linux loop fixture requires Linux")
    if args.record_owned:
        record_owned(*(Path(x) for x in args.record_owned))
    elif args.record_loop:
        record_loop(Path(args.record_loop[0]), args.record_loop[1])
    elif args.detach_owned:
        detach_owned(Path(args.detach_owned[0]), args.detach_owned[1])
    elif args.record_sysfs:
        record_sysfs(Path(args.record_sysfs))
    elif args.remove_dev_mount:
        remove_dev_mount(Path(args.remove_dev_mount))
    elif args.check_owned:
        owned(Path(args.check_owned[0]), args.check_owned[1])
    elif args.check_mount:
        check_mount(Path(args.check_mount[0]), args.check_mount[1])
    elif args.check_sysfs:
        check_sysfs(Path(args.check_sysfs))
    elif args.remove_owned:
        remove_owned(Path(args.remove_owned))
    else:
        record = Path(args.run[0])
        data = identity(record)
        pending = Path(data["root"]) / "producer.pending"
        require(pending.is_file() and not pending.is_symlink(), "producer marker required")
        try:
            run_fixture(record, args.run[1])
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError):
            if not PRODUCERS_UNCERTAIN:
                pending.unlink()
            raise
        else:
            require(not PRODUCERS_UNCERTAIN, "producer lifetime unresolved")
            pending.unlink()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        raise SystemExit(1) from None
