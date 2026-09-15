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
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid


SIZE = 256 * 1024 * 1024
ROOT_UUID = "00000000-0000-4000-8000-000000000001"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def execute(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, capture_output=True,
                          timeout=30, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
                          **kwargs).stdout


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


def owned(identity_file, loop):
    data = identity(identity_file)
    require(re.fullmatch(r"/dev/loop[0-9]+", loop), "physical and caller-selected disks are forbidden")
    info = Path(loop).stat()
    require(stat.S_ISBLK(info.st_mode) and os.major(info.st_rdev) == 7,
            "selected fixture device is not a loop block device")
    listing = json.loads(execute(["losetup", "--list", "--json", "--output",
                                 "NAME,BACK-FILE,OFFSET,SIZELIMIT", loop]))
    rows = listing.get("loopdevices", [])
    require(len(rows) == 1 and rows[0].get("name") == loop, "ambiguous loop allocation")
    row = rows[0]
    require(row.get("back-file") == data["backing"] and
            int(row.get("offset", -1)) == 0 and int(row.get("sizelimit", -1)) == 0,
            "loop backing file or geometry changed")
    sysfile = Path("/sys/class/block") / Path(loop).name / "loop/backing_file"
    require(sysfile.read_text().strip() == data["backing"], "sysfs loop backing identity changed")
    require(not any((sysfile.parent.parent / "holders").iterdir()), "fixture loop acquired a holder")
    return data


def remove_owned(identity_file):
    data = identity(identity_file)
    rows = json.loads(execute(["losetup", "--list", "--json", "--associated", data["backing"],
                               "--output", "NAME"])).get("loopdevices", [])
    require(not rows, "backing remains associated with a loop; refusing cleanup")
    root = data["root"]
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        target = line.split()[4]
        require(target != root and not target.startswith(root + "/"),
                "fixture still has mounted paths; refusing cleanup")
    require(shutil.rmtree.avoids_symlink_attacks, "platform lacks anchored safe cleanup")
    shutil.rmtree(root)


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


def check_sysfs(identity_file):
    data = identity(identity_file)
    target = Path(data["root"]) / "root/sys"
    rows = json.loads(execute(["findmnt", "--json", "--mountpoint", str(target), "--output",
                               "TARGET,FSTYPE"])).get("filesystems", [])
    require(len(rows) == 1 and rows[0].get("target") == str(target) and rows[0].get("fstype") == "sysfs"
            and target.stat().st_dev == Path("/sys").stat().st_dev,
            "cleanup sysfs bind identity changed")


class SimulatedInterruption(RuntimeError):
    """Command succeeded; deliberately prevent its durable stage receipt."""


def run_fixture(identity_file, loop):
    parent_namespace = os.environ.get("I1S_FIXTURE_PARENT_NAMESPACE")
    require(parent_namespace and os.readlink("/proc/self/ns/mnt") != parent_namespace,
            "run the shell wrapper to create a private mount namespace first")
    metadata = owned(identity_file, loop)
    root = Path(metadata["root"]) / "root"
    root.mkdir(mode=0o700, exist_ok=True)
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

    def sync_nodes():
        owned(identity_file, loop)
        names = [Path(loop).name]
        sysdisk = Path("/sys/class/block") / names[0]
        names.extend(p.name for p in sysdisk.glob(names[0] + "p*") if (p / "partition").exists())
        for name in names:
            sysnode = Path("/sys/class/block") / name
            major, minor = map(int, (sysnode / "dev").read_text().strip().split(":"))
            require(major == 7 or (sysnode / "partition").exists(), "foreign fixture device major")
            node = root / "dev" / name
            if node.exists():
                info = node.lstat()
                require(stat.S_ISBLK(info.st_mode) and info.st_rdev == os.makedev(major, minor),
                        "fixture block node identity changed")
            else:
                os.mknod(node, stat.S_IFBLK | 0o600, os.makedev(major, minor))

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
            sync_nodes()
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
            result = super().command(argv, timeout=timeout, input_text=input_text, pass_fds=pass_fds)
            if name in {"sfdisk", "mkfs.ext4", "mount"} and not any(x in argv for x in ("--json", "--dump", "--verify", "--list")):
                self.mutations.append(name)
                if name == "sfdisk":
                    execute(["udevadm", "settle", "--timeout=10"])
                    sync_nodes()
                if self.interrupt_after == name:
                    self.interrupt_after = None
                    raise SimulatedInterruption("injected after successful " + name + " before receipt")
            return result

    sync_nodes()
    config = {"storage_mode": "initialize", "initialize_empty_disk": "/dev/disk/by-id/" + by_id,
              "confirm_disk_id": by_id, "data_dir": "/data", "model_dir": "/data/models"}
    subject = storage_module.Storage(config, FixtureRunner(), root)
    io = FixtureDiskIO(subject)
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
    elif args.check_owned:
        owned(Path(args.check_owned[0]), args.check_owned[1])
    elif args.check_mount:
        check_mount(Path(args.check_mount[0]), args.check_mount[1])
    elif args.check_sysfs:
        check_sysfs(Path(args.check_sysfs))
    elif args.remove_owned:
        remove_owned(Path(args.remove_owned))
    else:
        run_fixture(Path(args.run[0]), args.run[1])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        raise SystemExit(1) from None
