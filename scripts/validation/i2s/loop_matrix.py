#!/usr/bin/env python3
"""Extended I1S loop tests; apply only inside an I2P-guarded hosted namespace.

FixtureRunner/FixtureDiskIO below are explicit bounded adaptations of
 tests/install/loop_disk_transaction.py (reviewed I1S source). They retain real
DiskIO commands, descriptors, exclusive probes, raw metadata validators and
fsck. Only fixture paths, loop topology/serial and synthetic root discovery are
adapted. No production source is rewritten or dynamically transformed.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[3]
SIZE = 256 * 1024 * 1024
MAX_FIXTURES = 6  # Plus the separately executed shipped fixture: 1792 MiB total.
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
ROOT_UUID = "00000000-0000-4000-8000-000000000001"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def execute(argv):
    result = subprocess.run(argv, check=False, text=True, capture_output=True,
                            timeout=30, env=ENV)
    if result.returncode:
        raise RuntimeError("fixture_command_failed:" + Path(argv[0]).name + ":exit=" + str(result.returncode))
    require(len(result.stdout) <= 262144, "fixture_command_output_limit")
    return result.stdout


def plan():
    return {"mode": "DRY_RUN", "fixture_bytes": SIZE, "maximum_fixtures": MAX_FIXTURES,
            "aggregate_backing_bytes_including_shipped": SIZE * (MAX_FIXTURES + 1),
            "allocation": "sequential exclusive /run/i1s-loop-*/backing.img; no external device argument",
            "guard": "I2P context and Ubuntu VM capability; private mount namespace; exact kernel backing inode",
            "cases": ["pre-receipt sfdisk/mkfs/mount/registration interruptions", "complete payload replay",
                      "completed missing/conflicting metadata refusal", "nonblank-middle refusal",
                      "discovery-adapter identity/root/boot/holder/UUID drift", "real in-use owned bind mount",
                      "corrupt primary GPT", "corrupt backup GPT", "partial ext4", "ownership uncertainty refusal"],
            "cleanup": "only exact recorded mount IDs and owned loop/backing; uncertainty preserves state",
            "not_tested": ["canonical global admission", "autonomous child deadline", "4096 logical sector loop",
                           "physical 4Kn hardware", "production disk discovery/root exclusion", "whole installer",
                           "role-aware data-only persistence", "packages", "GPU", "models", "reboot"]}


def checked_output(path):
    require(path.is_absolute() and path.name == "loop-matrix.json", "output_must_be_loop_matrix_json")
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    require(runner_temp and Path(runner_temp).is_absolute(), "runner_temp_unavailable")
    expected = Path(runner_temp).resolve(strict=True) / "i2s-evidence"
    require(path.parent == expected, "output_must_be_in_guarded_runner_evidence_directory")
    require(path.parent.resolve(strict=True) == path.parent, "output_parent_symlink")
    info = path.parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
            "output_parent_not_root_private")
    require(not path.exists() and not path.is_symlink(), "output_already_exists")


def apply_preflight(path):
    # Check context before any command or filesystem mutation, including output.
    i2p = load("i2s_i2p_guard", "scripts/validation/i2p/run.py")
    i2p.validate_context(dict(os.environ))
    require(sys.platform == "linux" and os.geteuid() == 0, "requires_disposable_linux_root")
    parent = os.environ.get("I2S_PARENT_NAMESPACE", "")
    require(parent and parent != os.readlink("/proc/self/ns/mnt"), "requires_private_namespace")
    checked_output(path)
    capability = i2p.capability(Path("/run"))
    require(execute(["findmnt", "--raw", "--noheadings", "--output", "PROPAGATION", "--target", "/"]).strip() == "private",
            "namespace_propagation_not_private")
    require(execute(["findmnt", "--noheadings", "--output", "FSTYPE", "--target", "/run"]).strip() == "tmpfs",
            "run_not_existing_tmpfs")
    for name in ("sfdisk", "mkfs.ext4", "e2fsck", "udevadm", "tune2fs", "blockdev", "dumpe2fs"):
        require(shutil.which(name, path=ENV["PATH"]), "missing_prerequisite:" + name)
    return capability


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mount_rows():
    rows = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        rows.append({"id": fields[0], "parent": fields[1], "dev": fields[2], "root": fields[3], "target": fields[4]})
    return rows


class Interrupted(RuntimeError):
    """Python exception after a real effect; never evidence of parent SIGKILL."""


class Fixture:
    def __init__(self, guard, disk_init, storage_module, name):
        self.guard, self.disk, self.storage = guard, disk_init, storage_module
        self.name = name
        self.scratch = Path("/run/i1s-loop-" + uuid.uuid4().hex)
        self.root = self.scratch / "root"
        self.record = self.scratch / "ownership.json"
        self.backing = self.scratch / "backing.img"
        self.loop = None
        self.sys_mount = None
        self.data_mount = None
        self.extra_mount = None
        self.metadata = None
        self.observed_loop = None
        self.commands = []
        self.mutations = []
        self.interrupt_after = None
        self.drift = None
        self.results = []
        self.cleanup_result = {"status": "NOT_ATTEMPTED"}

    def check(self):
        data = self.guard.owned(self.record, self.loop)
        rows = json.loads(execute(["losetup", "--list", "--json", "--output",
                                 "NAME,BACK-FILE,BACK-INO,BACK-MAJ:MIN,MAJ:MIN,OFFSET,SIZELIMIT,RO,AUTOCLEAR", self.loop]))["loopdevices"]
        require(len(rows) == 1, "ambiguous_kernel_loop_identity")
        row = rows[0]
        info = Path(self.loop).lstat()
        require(stat.S_ISBLK(info.st_mode) and os.major(info.st_rdev) == 7, "not_owned_loop_block")
        require(row.get("name") == self.loop and row.get("back-file") == data["backing"]
                and str(row.get("back-ino")) == str(data["backing_inode"])
                and row.get("back-maj:min") == f'{os.major(data["backing_device"])}:{os.minor(data["backing_device"])}'
                and row.get("maj:min") == f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}',
                "kernel_backing_identity_changed")
        require(int(row.get("offset", -1)) == 0 and int(row.get("sizelimit", -1)) == 0
                and row.get("ro") in (False, 0) and row.get("autoclear") in (False, 0), "loop_geometry_changed")
        sysdir = Path("/sys/class/block") / Path(self.loop).name
        require(int((sysdir / "size").read_text()) == SIZE // 512
                and int((sysdir / "queue/logical_block_size").read_text()) == 512, "loop_size_or_sector_changed")
        require(not any((sysdir / "slaves").iterdir()), "loop_has_slaves")
        self.observed_loop = dict(row, logical_sector_bytes=512, backing_bytes=SIZE)
        return data

    def exact_mount(self, target, expected):
        self.check()
        rows = [row for row in mount_rows() if row["target"] == str(target)]
        require(len(rows) == 1 and rows[0] == expected, "owned_mount_identity_changed")
        return rows[0]

    def capture_mount(self, target):
        rows = [row for row in mount_rows() if row["target"] == str(target)]
        require(len(rows) == 1, "owned_mount_not_exact")
        return rows[0]

    def setup(self):
        self.scratch.mkdir(mode=0o700)
        fd = os.open(self.backing, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.truncate(SIZE)
            stream.flush()
            os.fsync(stream.fileno())
        self.guard.record_owned(self.record, self.backing)
        self.guard.identity(self.record)
        self.loop = execute(["losetup", "--find", "--show", "--nooverlap", "--partscan", str(self.backing)]).strip()
        self.metadata = self.check()
        for path in (self.root / "dev/disk/by-id", self.root / "etc", self.root / "data", self.root / "sys", self.root / "boot/efi"):
            self.check()
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.check()
        execute(["mount", "--bind", "/sys", str(self.root / "sys")])
        self.sys_mount = self.capture_mount(self.root / "sys")
        self.exact_mount(self.root / "sys", self.sys_mount)
        execute(["mount", "--make-private", str(self.root / "sys")])
        self.exact_mount(self.root / "sys", self.sys_mount)
        execute(["mount", "-o", "remount,bind,ro", str(self.root / "sys")])
        self.by_id = "scsi-i1s-fixture-" + self.metadata["token"]
        self.check()
        (self.root / "dev/disk/by-id" / self.by_id).symlink_to("../../" + Path(self.loop).name)
        self.old_fstab = b"# I2S owned fixture; preserve CRLF\r\nUUID=old-root / ext4 defaults 0 1\n\n\n"
        self.check()
        (self.root / "etc/fstab").write_bytes(self.old_fstab)
        (self.root / "etc/fstab").chmod(0o600)
        self.sync_nodes()
        self.subject = self.storage.Storage({"storage_mode": "initialize", "initialize_empty_disk": "/dev/disk/by-id/" + self.by_id,
                       "confirm_disk_id": self.by_id, "data_dir": "/data", "model_dir": "/data/models"}, FixtureRunner(self), self.root)
        self.io = fixture_disk_io(self)
        self.saved_plan = self.disk.plan(self.subject, io=self.io)
        self.plan_path = self.scratch / "plan.json"
        self.check()
        self.plan_path.write_text(json.dumps(self.saved_plan, sort_keys=True) + "\n")
        self.plan_path.chmod(0o600)
        self.subject.config["disk_plan"] = str(self.plan_path)

    def sync_nodes(self):
        self.check()
        name = Path(self.loop).name
        sysdisk = Path("/sys/class/block") / name
        nodes = [sysdisk] + [p for p in sysdisk.glob(name + "p*") if (p / "partition").exists()]
        for sysnode in nodes:
            self.check()
            major, minor = map(int, (sysnode / "dev").read_text().strip().split(":"))
            require(major == 7 or ((sysnode / "partition").exists() and sysnode.parent == sysdisk), "foreign_partition_node")
            node = self.root / "dev" / sysnode.name
            if node.exists():
                info = node.lstat()
                require(stat.S_ISBLK(info.st_mode) and info.st_rdev == os.makedev(major, minor), "fixture_node_changed")
            else:
                os.mknod(node, stat.S_IFBLK | 0o600, os.makedev(major, minor))

    @property
    def journal(self):
        return self.root / "etc/local-ai-server/disk-initialization.json"

    def initialize(self):
        self.check()
        return self.disk.initialize(self.subject, io=self.io)

    def snapshot(self, disk=True):
        self.check()
        paths = {"journal": self.journal, "registration": self.root / "etc/local-ai-server/storage.json",
                 "fstab": self.root / "etc/fstab", "plan": self.plan_path}
        value = {name: sha(path) if path.exists() else None for name, path in paths.items()}
        if disk:
            require(not any(row["target"] == str(self.root / "data") for row in mount_rows()), "raw_snapshot_requires_unmounted_fixture")
            value["disk_sha256"] = sha(Path(self.loop))
        value["mutations"] = list(self.mutations)
        return value

    def refusal(self, name, action, disk=True, expected=None):
        before = self.snapshot(disk=disk)
        try:
            action()
        except (self.storage.StorageError, OSError) as error:
            error_type = type(error).__name__
            error_errno = getattr(error, "errno", None)
            message = str(error)
            require(expected is None or expected in message, "unexpected_refusal:" + message)
        else:
            raise RuntimeError("refusal_missing:" + name)
        after = self.snapshot(disk=disk)
        require(before == after, "refusal_changed_owned_state:" + name)
        item = {"case": name, "status": "PASS", "kind": "actual Linux plus discovery adapter" if self.drift else "actual Linux",
                "error_type": error_type, "errno": error_errno, "error": message, "before": before, "after": after}
        self.results.append(item)
        return item

    def interrupt(self, command, expected_stage):
        self.interrupt_after = command
        try:
            self.initialize()
        except Interrupted as error:
            stage = json.loads(self.journal.read_text())["stage"]
            require(stage == expected_stage, "unexpected_interruption_stage:" + stage)
            self.results.append({"case": "after_" + command, "status": "PASS", "kind": "Python exception after real tool completion",
                                 "journal_stage": stage, "error": str(error), "mutations": list(self.mutations)})
        else:
            raise RuntimeError("missing_interruption:" + command)

    def corrupt(self, offset, value):
        self.check()
        require(0 <= offset < SIZE and len(value) <= 4096 and offset + len(value) <= SIZE, "invalid_fixture_corruption_range")
        require(not any(row["target"].startswith(str(self.root) + "/") and row["target"] != str(self.root / "sys") for row in mount_rows()),
                "corruption_requires_unmounted_fixture")
        fd = os.open(self.loop, os.O_RDWR | os.O_NOFOLLOW | os.O_EXCL)
        try:
            self.check()
            require(os.fstat(fd).st_rdev == Path(self.loop).stat().st_rdev, "corruption_descriptor_changed")
            require(os.pwrite(fd, value, offset) == len(value), "short_fixture_corruption")
            os.fsync(fd)
        finally:
            os.close(fd)

    def cleanup(self):
        # Unknown allocation/identity is not inferred safe from path spelling.
        result = {"status": "INCOMPLETE", "scratch": str(self.scratch), "detached": False, "removed": False}
        self.cleanup_result = result
        try:
            if self.loop is None:
                if self.record.exists():
                    self.guard.remove_owned(self.record)
                    result.update(status="PASS", detached=True, removed=True)
                else:
                    result["error"] = "allocation_identity_unavailable_preserved"
                return result
            self.check()
            if self.extra_mount:
                target, expected = self.extra_mount
                self.exact_mount(target, expected)
                execute(["umount", "--", str(target)])
                self.extra_mount = None
            mounted = [row for row in mount_rows() if row["target"] == str(self.root / "data")]
            if mounted:
                self.guard.check_mount(self.record, self.loop)
                require(self.data_mount is not None, "data_mount_was_not_recorded")
                self.exact_mount(self.root / "data", self.data_mount)
                execute(["umount", "--", str(self.root / "data")])
            self.check()
            require(not any(row["target"].startswith(str(self.root) + "/") and row["target"] != str(self.root / "sys") for row in mount_rows()),
                    "unknown_fixture_mount_preserved")
            execute(["losetup", "--detach", self.loop])
            execute(["udevadm", "settle", "--timeout=10"])
            rows = json.loads(execute(["losetup", "--list", "--json", "--associated", str(self.backing), "--output", "NAME"]))["loopdevices"]
            require(not rows, "owned_backing_still_associated")
            result["detached"] = True
            if self.sys_mount:
                self.guard.check_sysfs(self.record)
                require(self.capture_mount(self.root / "sys") == self.sys_mount, "sys_mount_id_changed")
                execute(["umount", "--", str(self.root / "sys")])
            result["remaining_owned_mounts"] = [row for row in mount_rows() if row["target"] == str(self.scratch) or row["target"].startswith(str(self.scratch) + "/")]
            require(not result["remaining_owned_mounts"], "owned_mounts_remaining")
            self.guard.remove_owned(self.record)
            result.update(status="PASS", removed=not self.scratch.exists())
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
            result["error"] = str(error)
        return result


class FixtureRunner:
    """Reviewed I1S path/root adapter; drift data are explicitly labelled."""
    writable = True

    def __init__(self, fixture):
        self.f = fixture

    def run(self, argv, timeout=30):
        f = self.f
        f.check()
        argv = list(argv)
        if argv[0] == "lsblk":
            rows = json.loads(execute(argv + [f.loop]))
            require(len(rows.get("blockdevices", [])) == 1, "fixture_topology_ambiguous")
            top = rows["blockdevices"][0]
            require((top.get("path") or top.get("name")) == f.loop and top.get("type") == "loop", "not_fixture_loop_topology")
            top.update(type="disk", serial="fixture-inode-" + str(f.metadata["backing_inode"]), wwn=None)
            def translate(row):
                row["mountpoints"] = [str(p)[len(str(f.root)):] if str(p).startswith(str(f.root) + "/") else p for p in (row.get("mountpoints") or [])]
                for child in row.get("children", []):
                    translate(child)
            translate(top)
            if f.drift == "serial":
                top["serial"] += "-drift"
            elif f.drift == "size":
                top["size"] -= 512
            elif f.drift == "readonly":
                top["ro"] = True
            root_row = {"name": "/dev/i1s-fixture-root", "path": "/dev/i1s-fixture-root", "type": "disk", "pkname": None,
                        "mountpoints": ["/"], "fstype": "ext4", "uuid": ROOT_UUID, "size": 1, "wwn": None,
                        "serial": "synthetic-root", "ro": False, "maj:min": "0:65535"}
            if f.drift == "root_ancestry":
                root_row["pkname"] = f.loop
            if f.drift == "root_evidence":
                root_row["serial"] += "-drift"
            rows["blockdevices"].append(root_row)
            return json.dumps(rows)
        if argv[0] == "findmnt":
            index = argv.index("--target") + 1
            target = argv[index]
            if target in ("/", "/boot", "/boot/efi"):
                if (f.drift, target) in (("boot_ancestry", "/boot"), ("efi_ancestry", "/boot/efi")):
                    info = Path(f.loop).stat()
                    return json.dumps({"filesystems": [{"target": target, "source": f.loop, "uuid": ROOT_UUID,
                                                        "fstype": "ext4", "options": "rw",
                                                        "maj:min": f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"}]})
                return json.dumps({"filesystems": [{"target": "/", "source": "/dev/i1s-fixture-root", "uuid": ROOT_UUID,
                                                   "fstype": "ext4", "options": "rw", "maj:min": "0:65535"}]})
            argv[index] = str(f.root / target.lstrip("/"))
            answer = json.loads(execute(argv))
            for row in answer.get("filesystems", []):
                target = row.get("target", "")
                if target == str(f.root) or target.startswith(str(f.root) + "/"):
                    row["target"] = target[len(str(f.root)):] or "/"
            return json.dumps(answer)
        if argv[0] == "df":
            if argv[-1] != "/":
                argv[-1] = str(f.root / argv[-1].lstrip("/"))
            return execute(argv)
        if argv[0] == "wipefs":
            require(argv[-1] == f.loop or re.fullmatch(re.escape(f.loop) + r"p[0-9]+", argv[-1]), "foreign_signature_probe")
            require("--no-act" in argv, "signature_probe_not_read_only")
            argv[-1] = str(f.root / argv[-1].lstrip("/"))
            return execute(argv)
        raise RuntimeError("unexpected_storage_fixture_command:" + argv[0])


def fixture_disk_io(f):
    class FixtureDiskIO(f.disk.DiskIO):
        def observe(self):
            f.sync_nodes()
            return super().observe()

        def refresh(self, fd):
            f.check()
            return super().refresh(fd)

        def holders(self, source):
            super().holders(source)
            if f.drift == "holders":
                raise f.storage.StorageError("disk/partition holders present or unavailable")

        @contextlib.contextmanager
        def open_device(self, source, row, write=False):
            f.check()
            require(source == f.loop or re.fullmatch(re.escape(f.loop) + r"p[0-9]+", source), "foreign_device_open")
            with super().open_device(source, row, write=write) as fd:
                yield fd

        def command(self, argv, timeout=30, input_text=None, pass_fds=()):
            f.check()
            name = Path(argv[0]).name
            allowed = {"sfdisk", "mkfs.ext4", "wipefs", "blkid", "mount", "udevadm", "blockdev", "lsblk", "findmnt", "dumpe2fs", "tune2fs", "e2fsck"}
            require(name in allowed, "unexpected_disk_fixture_command:" + name)
            if name == "lsblk":
                argv = list(argv) + [f.loop]
            for fd in pass_fds:
                info = os.fstat(fd)
                if stat.S_ISBLK(info.st_mode):
                    require(any(node.stat().st_rdev == info.st_rdev for node in (f.root / "dev").iterdir()
                                if re.fullmatch(re.escape(Path(f.loop).name) + r"(?:p[0-9]+)?", node.name)), "foreign_inherited_block_fd")
            event = {"tool": name, "argv": list(argv), "timeout_seconds": timeout, "inherited_block_fds": len(pass_fds)}
            f.commands.append(event)
            try:
                result = super().command(argv, timeout=timeout, input_text=input_text, pass_fds=pass_fds)
            except f.storage.StorageError as error:
                event.update(status="FAIL", error=str(error), exit_code="not exposed by unchanged production DiskIO.command")
                raise
            event.update(status="PASS", exit_code=0)
            if name == "lsblk" and f.drift == "duplicate_uuid":
                rows = json.loads(result)
                ids = json.loads(f.journal.read_text())["ids"]
                rows["blockdevices"].append({"path": "/dev/i1s-synthetic-duplicate", "type": "part", "uuid": ids["filesystem_uuid"]})
                result = json.dumps(rows)
            if name in {"sfdisk", "mkfs.ext4", "mount"} and not any(x in argv for x in ("--json", "--dump", "--verify", "--list")):
                f.mutations.append(name)
                if name == "sfdisk":
                    f.check()
                    execute(["udevadm", "settle", "--timeout=10"])
                    f.sync_nodes()
                elif name == "mount":
                    f.guard.check_mount(f.record, f.loop)
                    f.data_mount = f.capture_mount(f.root / "data")
                if f.interrupt_after == name:
                    f.interrupt_after = None
                    raise Interrupted("after successful " + name + " before durable receipt")
            return result
    return FixtureDiskIO(f.subject)


def transaction_case(f):
    for command, stage in (("sfdisk", "gpt_intent"), ("mkfs.ext4", "fs_intent"), ("mount", "mount_intent")):
        f.interrupt(command, stage)
    base = f.disk.Storage
    class RegistrationInterruptStorage(base):
        def _atomic_write(self, path, text, mode=0o600):
            f.check()
            super()._atomic_write(path, text, mode)
            if path == f.storage.REGISTRATION_PATH:
                raise Interrupted("after actual registration write before fstab/complete receipts")
    f.disk.Storage = RegistrationInterruptStorage
    try:
        try:
            f.initialize()
        except Interrupted as error:
            require(json.loads(f.journal.read_text())["stage"] == "mounted", "registration_interruption_stage")
            require((f.root / "etc/local-ai-server/storage.json").is_file(), "registration_effect_absent")
            f.results.append({"case": "after_registration", "status": "PASS", "kind": "explicit Storage subclass after real write",
                              "journal_stage": "mounted", "error": str(error)})
        else:
            raise RuntimeError("registration_interruption_absent")
    finally:
        f.disk.Storage = base
    registration = f.initialize()
    journal = json.loads(f.journal.read_text())
    require(journal["stage"] == "complete", "transaction_not_complete")
    require(f.mutations == ["sfdisk", "mkfs.ext4", "mount"], "effect_repeated_after_interruption")
    marker = f.root / "data/i2s-payload.txt"
    f.check()
    marker.write_bytes(b"I2S payload survives complete replay\n" * 97)
    with marker.open("rb") as stream:
        os.fsync(stream.fileno())
    before = f.snapshot(disk=False)
    before["payload_sha256"] = sha(marker)
    second = f.initialize()
    after = f.snapshot(disk=False)
    after["payload_sha256"] = sha(marker)
    require(before == after, "complete_replay_changed_payload_or_metadata")
    require(registration["data"]["uuid"] == second["data"]["uuid"] == journal["ids"]["filesystem_uuid"], "registration_identity_mismatch")
    require((f.root / "etc/fstab").read_bytes().startswith(f.old_fstab), "fstab_prefix_changed")
    f.check()
    table = json.loads(execute(["sfdisk", "--json", f.loop]))["partitiontable"]
    part = table["partitions"][0]
    require(table["label"] == "gpt" and len(table["partitions"]) == 1 and table["id"].lower() == journal["ids"]["disk_guid"], "gpt_identity_mismatch")
    require((part["start"], part["size"]) == (f.saved_plan["shape"]["start_sector"], f.saved_plan["shape"]["size_sectors"])
            and part["uuid"].lower() == journal["ids"]["partition_uuid"], "partition_geometry_mismatch")
    details = execute(["tune2fs", "-l", str(f.root / "dev" / Path(part["node"]).name)])
    fields = {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in details.splitlines() if ":" in line}
    require(fields.get("Reserved block count") == "0" and fields.get("Block size") == "4096"
            and fields.get("Filesystem UUID") == journal["ids"]["filesystem_uuid"]
            and fields.get("Filesystem volume name") == journal["ids"]["filesystem_label"], "ext4_identity_mismatch")
    f.results.append({"case": "complete_payload_replay", "status": "PASS", "before": before, "after": after,
                      "logical_sector_bytes": 512, "plan": f.saved_plan, "ids": journal["ids"], "gpt": table,
                      "ext4": {key: fields[key] for key in ("Reserved block count", "Block size", "Block count", "Filesystem UUID", "Filesystem volume name")},
                      "raw_gpt_copies_crc_geometry": "unchanged DiskIO.gpt validated both copies on every resume",
                      "readonly_fsck": [event for event in f.commands if event["tool"] == "e2fsck"]})
    for name, path, mutate in (("missing_registration", f.root / "etc/local-ai-server/storage.json", lambda _: None),
                              ("missing_fstab", f.root / "etc/fstab", lambda _: f.old_fstab),
                              ("conflicting_fstab", f.root / "etc/fstab", lambda b: b + b"UUID=foreign /data ext4 defaults 0 2\n")):
        f.check()
        old = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        replacement = mutate(old)
        if replacement is None:
            path.unlink()
        else:
            path.write_bytes(replacement)
        try:
            f.refusal(name, f.initialize, disk=False)
        finally:
            f.check()
            path.write_bytes(old)
            path.chmod(mode)
    alias = f.root / "in-use-alias"
    f.check()
    alias.mkdir(mode=0o700)
    f.guard.check_mount(f.record, f.loop)
    f.exact_mount(f.root / "data", f.data_mount)
    execute(["mount", "--bind", str(f.root / "data"), str(alias)])
    f.extra_mount = (alias, f.capture_mount(alias))
    try:
        require(f.extra_mount[1]["dev"] == f.data_mount["dev"], "alias_not_same_device")
        f.refusal("partition_mounted_elsewhere", f.initialize, disk=False, expected="partition is mounted or in use")
    finally:
        f.exact_mount(*f.extra_mount)
        execute(["umount", "--", str(alias)])
        f.extra_mount = None
    f.exact_mount(f.root / "data", f.data_mount)
    execute(["umount", "--", str(f.root / "data")])
    f.data_mount = None
    f.refusal("completed_mount_missing", f.initialize, expected="completed filesystem lost its mount")


def independent_case(f):
    original_partition = f.io.partition
    def stop_before_partition(fd, previous, ids):
        raise Interrupted("source adapter stops before first partition effect")
    f.io.partition = stop_before_partition
    try:
        try:
            f.initialize()
        except Interrupted:
            require(json.loads(f.journal.read_text())["stage"] == "gpt_intent", "blank_drift_setup_wrong_stage")
        else:
            raise RuntimeError("blank_drift_setup_did_not_stop")
    finally:
        f.io.partition = original_partition
    for drift in ("serial", "size", "readonly", "root_ancestry", "root_evidence", "boot_ancestry", "efi_ancestry", "holders", "duplicate_uuid"):
        f.drift = drift
        try:
            f.refusal("discovery_adapter_" + drift, f.initialize)
        finally:
            f.drift = None
    original = f.plan_path.read_bytes()
    changed = json.loads(original)
    changed["shape"]["size_sectors"] -= 1
    f.check()
    f.plan_path.write_text(json.dumps(changed))
    try:
        f.refusal("saved_plan_drift", f.initialize)
    finally:
        f.check()
        f.plan_path.write_bytes(original)
    link = f.root / "dev/disk/by-id" / f.by_id
    f.check()
    link.unlink()
    try:
        f.refusal("stable_by_id_disappeared", f.initialize, expected="root-owned by-id symlink")
    finally:
        f.check()
        link.symlink_to("../../" + Path(f.loop).name)
    f.check()
    claim = os.open(f.loop, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW)
    try:
        f.check()
        require(os.fstat(claim).st_rdev == Path(f.loop).stat().st_rdev, "exclusive_claim_identity_changed")
        item = f.refusal("kernel_exclusive_claim_in_use", f.initialize)
        require(item["errno"] == 16, "exclusive_claim_did_not_report_EBUSY")
    finally:
        os.close(claim)
    f.corrupt(SIZE // 2, b"I2S nonblank middle fixture\n")
    f.refusal("nonblank_middle", f.initialize, expected="nonblank or partially initialized")


def corrupt_case(f, kind):
    f.interrupt("sfdisk", "gpt_intent")
    if kind == "partial_ext4":
        # Stop before formatting through the documented IO seam; no tool effect is faked as success.
        original = f.io.format
        def stop_before_format(fd, ids):
            raise Interrupted("before mkfs; retain fs_intent for owned partial-byte fixture")
        f.io.format = stop_before_format
        try:
            try:
                f.initialize()
            except Interrupted:
                require(json.loads(f.journal.read_text())["stage"] == "fs_intent", "partial_ext4_wrong_stage")
            else:
                raise RuntimeError("pre_format_stop_missing")
        finally:
            f.io.format = original
        offset = f.saved_plan["shape"]["start_sector"] * 512 + 1024
        f.corrupt(offset, b"I2S foreign partial ext4 header\n")
    else:
        offset = 512 if kind == "primary_gpt" else SIZE - 512
        f.corrupt(offset, b"FOREIGN!")
    f.refusal("foreign_" + kind, f.initialize)


def uncertainty_case(f):
    # A test-owned extra hard link invalidates the trusted record without changing
    # any disk data. While invalid, cleanup must report incomplete and do nothing.
    alias = f.scratch / "injected-extra-link"
    f.check()
    before = f.snapshot()
    original = f.backing.stat()
    original_root = f.scratch.stat()
    loop_observation = execute(["losetup", "--list", "--json", "--output", "NAME,BACK-FILE,BACK-INO,BACK-MAJ:MIN,OFFSET,SIZELIMIT", f.loop])
    sys_observation = f.capture_mount(f.root / "sys")
    os.link(f.backing, alias)
    refused = f.cleanup()
    require(refused["status"] == "INCOMPLETE" and not refused["detached"] and f.backing.exists(), "unknown_ownership_cleanup_claimed_success")
    require(sha(Path(f.loop)) == before["disk_sha256"], "unknown_ownership_changed_disk")
    require(f.capture_mount(f.root / "sys") == sys_observation, "uncertain_cleanup_mount_changed")
    require(execute(["losetup", "--list", "--json", "--output", "NAME,BACK-FILE,BACK-INO,BACK-MAJ:MIN,OFFSET,SIZELIMIT", f.loop]) == loop_observation,
            "uncertain_cleanup_loop_association_changed")
    # Reverse ONLY the injected hardlink after independent exact-inode checks.
    # This is test fixture restoration, not automatic production ownership repair.
    directory = os.open(f.scratch, os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY)
    try:
        directory_info = os.fstat(directory)
        require((directory_info.st_dev, directory_info.st_ino, directory_info.st_uid, stat.S_IMODE(directory_info.st_mode)) ==
                (original_root.st_dev, original_root.st_ino, 0, 0o700), "injected_link_root_identity_changed")
        for name in (alias.name, f.backing.name):
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                    and (info.st_dev, info.st_ino, info.st_size, info.st_uid, info.st_nlink) ==
                    (original.st_dev, original.st_ino, SIZE, 0, 2), "injected_link_identity_changed_preserve")
        os.unlink(alias.name, dir_fd=directory)
    finally:
        os.close(directory)
    f.check()
    after = f.snapshot()
    require(before == after, "ownership_fixture_state_changed")
    f.results.append({"case": "unknown_ownership_preserves_state", "status": "PASS", "before": before, "after": after,
                      "refused_cleanup": dict(refused), "loop_before_after": json.loads(loop_observation), "sys_mount_before_after": sys_observation,
                      "fixture_restoration": "removed exact independently inode-checked injected hardlink"})


def run_matrix(capability):
    guard = load("i2s_reviewed_loop_guard", "tests/install/loop_disk_transaction.py")
    sys.path.insert(0, str(REPO / "scripts"))
    from install import disk_init, storage
    evidence = {"schema": 1, "status": "FAIL", "plan": plan(), "source_sha": os.environ["GITHUB_SHA"],
                "capability": capability, "fixtures": [], "not_tested": plan()["not_tested"],
                "adapter_limit": "real loop metadata/tools/mounts; synthetic loop type, serial, root and selected drift observations",
                "sources": {str(path.relative_to(REPO)): sha(path) for path in (Path(__file__).resolve(),
                            REPO / "tests/install/loop_disk_transaction.py", REPO / "scripts/install/disk_init.py",
                            REPO / "scripts/install/storage.py", REPO / "scripts/validation/i2p/run.py")}}
    versions = {}
    for tool, args in (("sfdisk", ["--version"]), ("losetup", ["--version"]), ("mount", ["--version"]),
                       ("udevadm", ["--version"]), ("e2fsprogs", [])):
        if tool == "e2fsprogs":
            versions[tool] = execute(["dpkg-query", "--show", "--showformat=${Version}", "e2fsprogs"]).strip()
        else:
            versions[tool] = execute([tool] + args).splitlines()[0]
    evidence["tool_versions"] = versions
    baseline = False
    allocated = 0
    cases = [("transaction", transaction_case, False), ("independent_refusals", independent_case, False),
             ("primary_gpt", lambda f: corrupt_case(f, "primary_gpt"), True),
             ("backup_gpt", lambda f: corrupt_case(f, "backup_gpt"), True),
             ("partial_ext4", lambda f: corrupt_case(f, "partial_ext4"), True),
             ("unknown_ownership", uncertainty_case, False)]
    for name, action, dependent in cases:
        if dependent and not baseline:
            evidence["fixtures"].append({"name": name, "status": "NOT_TESTED", "reason": "transaction prerequisite failed; no unsafe bypass"})
            continue
        require(allocated < MAX_FIXTURES, "fixture_allocation_budget_exceeded")
        allocated += 1
        f = Fixture(guard, disk_init, storage, name)
        outcome = {"name": name, "status": "FAIL"}
        started = time.monotonic()
        try:
            f.setup()
            action(f)
            outcome["status"] = "PASS"
            if name == "transaction":
                baseline = True
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            outcome.update(error=str(error), error_type=type(error).__name__)
        finally:
            outcome.update(cases=f.results, commands=f.commands, cleanup=f.cleanup(), duration_seconds=round(time.monotonic() - started, 3),
                           allocation=f.metadata, validated_kernel_loop=f.observed_loop, saved_plan=getattr(f, "saved_plan", None))
            if outcome["cleanup"]["status"] != "PASS":
                outcome["status"] = "FAIL"
            evidence["fixtures"].append(outcome)
        if outcome["cleanup"]["status"] != "PASS":
            evidence["stop_reason"] = "cleanup uncertainty; preserve fixture and stop allocating"
            break
    evidence["aggregate_extension_backing_bytes"] = allocated * SIZE
    evidence["aggregate_backing_bytes_including_shipped_allocated_once"] = (allocated + 1) * SIZE
    evidence["status"] = "PASS" if all(item["status"] == "PASS" for item in evidence["fixtures"]) and len(evidence["fixtures"]) == len(cases) else "FAIL"
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--dry-run", action="store_true")
    operation.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, help="new $RUNNER_TEMP/i2s-evidence/loop-matrix.json")
    args = parser.parse_args()
    if args.dry_run:
        require(args.output is None, "dry_run_does_not_write_output")
        print(json.dumps(plan(), sort_keys=True, indent=2))
        return 0
    require(args.output is not None, "apply_requires_output")
    capability = apply_preflight(args.output)
    os.umask(0o077)
    evidence = run_matrix(capability)
    checked_output(args.output)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(evidence, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": evidence["status"], "output": str(args.output), "fixtures": len(evidence["fixtures"])}))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        raise SystemExit(1) from None
