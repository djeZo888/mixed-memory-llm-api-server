"""Synthetic transaction/recovery fixtures. Never opens or formats a real device.

These tests exercise discovery/policy, protected journals, adoption, and command
lifetime. GPT/ext4 behavior requires the separate disposable Linux loop fixture.
"""
import contextlib
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from install import disk_init as disk
from install.storage import Storage, StorageError, REGISTRATION_PATH


def block(path, dev, *, parent=None, serial=None, size=128 * disk.MIB,
          fs_uuid=None, target=None, kind="disk"):
    return {"name": path, "path": path, "maj:min": dev, "pkname": parent,
            "type": kind, "serial": serial, "wwn": None, "size": size,
            "uuid": fs_uuid, "fstype": "ext4" if fs_uuid else None,
            "mountpoints": [target], "ro": False}


class FixtureRunner:
    writable = True

    def __init__(self):
        self.blocks = [block("/dev/rootfixture", "8:0", serial="synthetic-root"),
                       block("/dev/rootfixture1", "8:1", parent="/dev/rootfixture",
                             fs_uuid="synthetic-root-uuid", target="/", kind="part"),
                       block("/dev/nvme9n1", "259:0", serial="synthetic-data")]
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[0] == "lsblk":
            return json.dumps({"blockdevices": self.blocks})
        if argv[0] == "findmnt":
            path = argv[-1]
            choices = [(mount, row) for row in self.blocks for mount in row["mountpoints"]
                       if mount and (mount == "/" or path == mount or path.startswith(mount + "/"))]
            mount, row = max(choices, key=lambda item: len(item[0]))
            return json.dumps({"filesystems": [{"target": mount, "source": row["path"],
                "uuid": row["uuid"], "fstype": row["fstype"], "options": "rw,relatime",
                "maj:min": row["maj:min"]}]})
        if argv[0] == "df":
            return "Avail\n10737418240\n"
        raise AssertionError("unexpected command in synthetic fixture: " + repr(argv))


class Interrupted(RuntimeError):
    pass


class SyntheticIO(disk.DiskIO):
    """All operations which could touch a device are replaced with state changes."""
    def __init__(self, storage):
        super().__init__(storage)
        self.events = []
        self.gpt_ids = None
        self.fs_ids = None
        self.crash_after = None
        self.extra_signatures = {}
        self.dirty = set()

    def prerequisites(self):
        if not self.s.runner.writable:
            raise StorageError("read-only fixture runner")

    def unique_ids(self, ids, source, part):
        # General UUID/topology conflicts remain exercised in check_live.
        pass

    def command(self, argv, **kwargs):
        raise AssertionError("synthetic fixture attempted a real process: " + repr(argv))

    @contextlib.contextmanager
    def open_device(self, source, row, write=False):
        # Strings deliberately cannot serve as OS descriptors.
        yield source

    def signatures(self, source):
        if source in self.extra_signatures:
            return self.extra_signatures[source]
        if source.endswith("p1"):
            return ([{"type": "ext4", "uuid": self.fs_ids["filesystem_uuid"]}]
                    if self.fs_ids else [])
        return [{"type": "gpt"}, {"type": "PMBR"}] if self.gpt_ids else []

    def blank(self, fd, identity):
        if fd in self.dirty or (fd.endswith("p1") and self.fs_ids):
            raise StorageError("nonblank synthetic disk metadata")

    def journal(self):
        return json.loads(self.s._local(disk.JOURNAL).read_text())

    def partition(self, fd, plan, ids):
        current = self.journal()
        assert current["stage"] == "gpt_intent"
        assert current["ids"] == ids
        assert current["plan"] == plan
        assert not self.gpt_ids
        self.events.append("partition")
        self.gpt_ids = copy.deepcopy(ids)
        self.effect("partition")

    def gpt(self, fd, plan, ids):
        if self.gpt_ids != ids:
            raise StorageError("GPT differs from intended identity/layout")

    def refresh(self, fd):
        if any(row["pkname"] == fd for row in self.s.runner.blocks):
            return
        shape = self.journal()["plan"]["shape"]
        part = fd + "p1"
        self.s.runner.blocks.append(block(part, "259:1", parent=fd, kind="part",
            size=shape["size_sectors"] * shape["sector_bytes"]))
        sysdir = self.s._local("/sys/class/block/" + Path(part).name)
        (sysdir / "holders").mkdir(parents=True)
        (sysdir / "start").write_text(str(shape["start_sector"] * shape["sector_bytes"] // 512))

    def filesystem(self, fd, plan, ids):
        if self.fs_ids is not None and self.fs_ids != ids:
            raise StorageError("foreign filesystem UUID/label")
        return self.fs_ids is not None

    def format(self, fd, ids):
        current = self.journal()
        assert current["stage"] == "fs_intent"
        assert current["ids"] == ids
        assert self.fs_ids is None
        self.events.append("format")
        self.fs_ids = copy.deepcopy(ids)
        for row in self.s.runner.blocks:
            if row["path"] == fd:
                row.update(uuid=ids["filesystem_uuid"], fstype="ext4")
        self.effect("format")

    def check_fs(self, fd):
        self.events.append("check_fs")
        self.effect("check_fs")

    def mount(self, fd, fs_uuid):
        assert self.journal()["stage"] == "mount_intent"
        assert self.fs_ids["filesystem_uuid"] == fs_uuid
        assert self.s._local(self.s.data_dir).stat().st_mode & 0o777 == 0o700
        self.events.append("mount")
        for row in self.s.runner.blocks:
            if row["path"] == fd:
                row["mountpoints"] = [self.s.data_dir]
        self.effect("mount")

    def effect(self, name):
        if self.crash_after == name:
            self.crash_after = None
            raise Interrupted("synthetic interruption after " + name)


class DiskTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="disk-transaction-unit-")
        self.root = Path(self.tmp.name)
        (self.root / "etc").mkdir()
        self.old_fstab = b"# original admin bytes\r\nUUID=root / ext4 defaults 0 1\r\n# no final newline"
        (self.root / "etc/fstab").write_bytes(self.old_fstab)
        (self.root / "dev/disk/by-id").mkdir(parents=True)
        (self.root / "dev/nvme9n1").touch()
        (self.root / "dev/disk/by-id/nvme-synthetic-data").symlink_to("../../nvme9n1")
        sysdir = self.root / "sys/class/block/nvme9n1"
        (sysdir / "holders").mkdir(parents=True)
        (sysdir / "queue").mkdir()
        (sysdir / "queue/logical_block_size").write_text("512")
        self.runner = FixtureRunner()
        self.config = {"storage_mode": "initialize", "data_dir": "/data",
                       "initialize_empty_disk": "/dev/disk/by-id/nvme-synthetic-data",
                       "confirm_disk_id": "nvme-synthetic-data"}
        self.s = Storage(self.config, self.runner, self.root)
        self.io = SyntheticIO(self.s)

    def tearDown(self):
        self.tmp.cleanup()

    def saved_plan(self):
        result = disk.plan(self.s, io=self.io)
        path = self.root / "saved-plan.json"
        path.write_text(json.dumps(result))
        self.s.config["disk_plan"] = str(path)
        return result

    def initialize(self):
        return disk.initialize(self.s, io=self.io)

    def stop_at(self, stage):
        original = disk.save
        def save_then_interrupt(s, journal, current):
            original(s, journal, current)
            if current == stage:
                raise Interrupted("synthetic interruption at " + stage)
        with patch.object(disk, "save", side_effect=save_then_interrupt):
            with self.assertRaises(Interrupted):
                self.initialize()
        self.assertEqual(self.io.journal()["stage"], stage)

    def assert_no_mutation(self):
        self.assertEqual(self.io.events, [])
        self.assertFalse(self.s._local(disk.JOURNAL).exists())

    def test_plan_read_only_and_binds_concrete_shape(self):
        before = {str(p): p.stat().st_mtime_ns for p in self.root.rglob("*")}
        result = disk.plan(self.s, io=self.io)
        self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in self.root.rglob("*")})
        self.assertEqual(result["shape"], {"table": "gpt", "partitions": 1, "sector_bytes": 512,
            "start_sector": 2048, "size_sectors": 258048, "fstype": "ext4", "block_bytes": 4096,
            "reserved_percent": 0, "data_mount": "/data", "models": "/data/models",
            "partition_name": "local-ai-data"})
        self.assertEqual(result["identity"]["serial"], "synthetic-data")
        self.assertTrue(result["precondition"]["protected"])
        self.assert_no_mutation()

    def test_each_persisted_stage_resumes_once(self):
        # Each iteration receives an independent blank in-memory fixture.
        for stage in disk.STAGES:
            with self.subTest(stage=stage):
                if stage != disk.STAGES[0]:
                    self.tearDown(); self.setUp()
                self.saved_plan()
                self.stop_at(stage)
                ids = self.io.journal()["ids"]
                result = self.initialize()
                self.assertEqual(result["data"]["uuid"], ids["filesystem_uuid"])
                self.assertEqual(result["models"]["uuid"], ids["filesystem_uuid"])
                self.assertEqual(self.io.journal()["stage"], "complete")
                for operation in ("partition", "format", "mount"):
                    self.assertEqual(self.io.events.count(operation), 1)

    def test_crashes_after_irreversible_effect_before_receipt_reconcile(self):
        for operation, stage in (("partition", "gpt_intent"), ("format", "fs_intent"),
                                 ("mount", "mount_intent")):
            with self.subTest(operation=operation):
                if operation != "partition":
                    self.tearDown(); self.setUp()
                self.saved_plan()
                self.io.crash_after = operation
                with self.assertRaises(Interrupted):
                    self.initialize()
                self.assertEqual(self.io.journal()["stage"], stage)
                identities = self.io.journal()["ids"]
                self.initialize()
                self.assertEqual(self.io.journal()["ids"], identities)
                for command in ("partition", "format", "mount"):
                    self.assertEqual(self.io.events.count(command), 1)

    def test_completed_identical_run_preserves_fstab_registration_journal_and_data(self):
        self.saved_plan()
        self.initialize()
        fstab = self.root / "etc/fstab"
        self.assertTrue(fstab.read_bytes().startswith(self.old_fstab))
        self.assertEqual(fstab.read_bytes().count(b" /data ext4 defaults 0 2"), 1)
        payload = self.root / "data/models/preserved.partial"
        payload.write_bytes(b"synthetic preserved model bytes")
        paths = [fstab, self.s._local(disk.JOURNAL), self.s._local(REGISTRATION_PATH), payload]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
        events = list(self.io.events)
        self.initialize()
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])
        self.assertEqual(events, self.io.events)

    def test_explicit_filesystem_uuid_is_used_and_nested_models_share_it(self):
        wanted = "11111111-2222-4333-8444-555555555555"
        self.s.config["data_uuid"] = wanted
        self.saved_plan()
        result = self.initialize()
        self.assertEqual(result["data"]["uuid"], wanted)
        self.assertEqual(result["models"]["uuid"], wanted)
        self.assertEqual((self.root / "data/services/secrets").stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.s._local(disk.JOURNAL).stat().st_mode & 0o777, 0o600)

    def test_storage_adopt_dispatches_helper_and_returns_registration(self):
        self.saved_plan()
        original = disk.initialize
        with patch.object(disk, "initialize", side_effect=lambda s: original(s, io=self.io)) as called:
            result = self.s.adopt()
        called.assert_called_once_with(self.s)
        self.assertEqual(result["data"]["uuid"], self.io.journal()["ids"]["filesystem_uuid"])

    def test_scsi_stable_id_and_reassigned_kernel_name_are_supported(self):
        self.s.config.update(initialize_empty_disk="/dev/disk/by-id/scsi-synthetic-data",
                             confirm_disk_id="scsi-synthetic-data")
        link = self.root / "dev/disk/by-id/scsi-synthetic-data"
        link.symlink_to("../../nvme9n1")
        self.saved_plan()
        self.stop_at("prepared")
        link.unlink(); link.symlink_to("../../fixture-scsi")
        (self.root / "dev/fixture-scsi").touch()
        (self.root / "sys/class/block/nvme9n1").rename(self.root / "sys/class/block/fixture-scsi")
        self.runner.blocks[2].update(path="/dev/fixture-scsi", name="/dev/fixture-scsi",
                                     **{"maj:min": "8:48"})
        result = self.initialize()
        self.assertEqual(result["data"]["source"], "/dev/fixture-scsip1")
        self.assertEqual(self.io.events.count("format"), 1)

    def test_completed_missing_fstab_mount_or_registration_refuse_without_reformat(self):
        self.saved_plan()
        self.initialize()
        events = list(self.io.events)
        fstab = self.root / "etc/fstab"
        contents = fstab.read_bytes()
        fstab.write_bytes(self.old_fstab)
        with self.assertRaisesRegex(StorageError, "fstab"):
            self.initialize()
        fstab.write_bytes(contents)
        registration = self.s._local(REGISTRATION_PATH)
        registration_bytes = registration.read_bytes()
        registration.unlink()
        with self.assertRaisesRegex(StorageError, "registration"):
            self.initialize()
        disk.atomic_bytes(self.s, REGISTRATION_PATH, registration_bytes)
        self.runner.blocks[-1]["mountpoints"] = [None]
        with self.assertRaises(StorageError):
            self.initialize()
        for operation in ("partition", "format", "mount"):
            self.assertEqual(self.io.events.count(operation), events.count(operation))

    def test_missing_confirmation_and_non_initialize_mode_refuse(self):
        for updates in ({"confirm_disk_id": "different"}, {"storage_mode": "existing"},
                        {"initialize_empty_disk": "/dev/nvme9n1"},
                        {"initialize_empty_disk": "/dev/disk/by-id/nvme-synthetic-data-part1",
                         "confirm_disk_id": "nvme-synthetic-data-part1"}):
            with self.subTest(updates=updates):
                s = Storage(dict(self.config, **updates), self.runner, self.root)
                with self.assertRaises(StorageError):
                    disk.plan(s, io=SyntheticIO(s))
        self.assert_no_mutation()

    def test_unsafe_mount_and_separate_models_require_existing_mode(self):
        for updates in ({"data_dir": "/usr"}, {"data_dir": "/var/lib/ai"},
                        {"data_dir": "/opt"}, {"model_dir": "/models"},
                        {"model_uuid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}):
            with self.subTest(updates=updates):
                s = Storage(dict(self.config, **updates), self.runner, self.root)
                with self.assertRaises(StorageError):
                    disk.plan(s, io=SyntheticIO(s))
        self.assert_no_mutation()

    def test_unknown_signatures_blank_edges_and_foreign_filesystem_refuse_without_journal(self):
        for bad in ([{"type": "ext4", "uuid": "foreign"}], [{"type": "gpt"}], [{"type": "unknown"}]):
            self.io.extra_signatures["/dev/nvme9n1"] = bad
            with self.assertRaisesRegex(StorageError, "signatures"):
                disk.plan(self.s, io=self.io)
        self.io.extra_signatures.clear()
        self.io.dirty.add("/dev/nvme9n1")
        with self.assertRaisesRegex(StorageError, "nonblank"):
            disk.plan(self.s, io=self.io)
        self.assert_no_mutation()

    def test_serial_size_and_saved_shape_drift_refuse_before_mutation(self):
        self.saved_plan()
        original = copy.deepcopy(self.runner.blocks[2])
        for key, value in (("serial", "changed-serial"), ("size", 256 * disk.MIB)):
            with self.subTest(key=key):
                self.runner.blocks[2][key] = value
                with self.assertRaises(StorageError):
                    self.initialize()
                self.runner.blocks[2] = copy.deepcopy(original)
        plan_path = Path(self.s.config["disk_plan"])
        changed = json.loads(plan_path.read_text())
        changed["shape"]["size_sectors"] -= 2048
        plan_path.write_text(json.dumps(changed))
        with self.assertRaises(StorageError):
            self.initialize()
        self.assert_no_mutation()

    def test_config_and_confirmation_drift_on_resume_refuse(self):
        self.saved_plan()
        self.stop_at("prepared")
        self.s.config["model_dir"] = "/data/other-models"
        with self.assertRaisesRegex(StorageError, "plan/config"):
            self.initialize()
        self.assertEqual(self.io.events, [])

    def test_journal_ids_hardware_and_protected_root_drift_refuse_on_resume(self):
        self.saved_plan()
        self.stop_at("gpt_done")
        events = list(self.io.events)
        original = copy.deepcopy(self.runner.blocks)
        for index, key, value in ((2, "serial", "changed"), (2, "size", 256 * disk.MIB),
                                  (0, "serial", "replacement-root")):
            with self.subTest(key=key, index=index):
                self.runner.blocks[index][key] = value
                with self.assertRaisesRegex(StorageError, "identity changed|evidence drifted"):
                    self.initialize()
                self.runner.blocks = copy.deepcopy(original)
        journal = self.io.journal()
        journal["ids"]["partition_uuid"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        disk.atomic_bytes(self.s, disk.JOURNAL, json.dumps(journal).encode())
        with self.assertRaisesRegex(StorageError, "GPT differs"):
            self.initialize()
        self.assertEqual(events, self.io.events)

    def test_foreign_fs_after_intent_and_unknown_partition_signature_refuse(self):
        self.saved_plan()
        self.io.crash_after = "format"
        with self.assertRaises(Interrupted):
            self.initialize()
        events = list(self.io.events)
        original = copy.deepcopy(self.io.fs_ids)
        self.io.fs_ids["filesystem_uuid"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        with self.assertRaisesRegex(StorageError, "foreign filesystem"):
            self.initialize()
        self.io.fs_ids = original
        self.io.extra_signatures["/dev/nvme9n1p1"] = [{"type": "unknown"}]
        with self.assertRaisesRegex(StorageError, "foreign filesystem signatures"):
            self.initialize()
        self.assertEqual(events, self.io.events)

    def test_owned_partition_geometry_holders_mount_and_duplicate_uuid_refuse(self):
        self.saved_plan()
        self.stop_at("fs_done")
        events = list(self.io.events)
        part = self.runner.blocks[-1]
        original = copy.deepcopy(part)
        for key, value in (("size", 12345), ("pkname", "/dev/rootfixture"),
                           ("mountpoints", ["/foreign"]), ("type", "lvm")):
            with self.subTest(key=key):
                part[key] = value
                with self.assertRaises(StorageError):
                    self.initialize()
                part.clear(); part.update(copy.deepcopy(original))
        holders = self.root / "sys/class/block/nvme9n1p1/holders/foreign"
        holders.touch()
        with self.assertRaisesRegex(StorageError, "holders"):
            self.initialize()
        holders.unlink()
        self.runner.blocks.append(block("/dev/foreign", "8:99", fs_uuid=part["uuid"]))
        with self.assertRaisesRegex(StorageError, "duplicated or foreign"):
            self.initialize()
        self.assertEqual(events, self.io.events)

    def test_partial_partition_payload_at_fs_intent_never_reformats(self):
        self.saved_plan()
        self.stop_at("fs_intent")
        self.io.dirty.add("/dev/nvme9n1p1")
        events = list(self.io.events)
        with self.assertRaisesRegex(StorageError, "nonblank"):
            self.initialize()
        self.assertEqual(events, self.io.events)

    def test_global_disk_partition_and_filesystem_identity_collision_rejected(self):
        ids = {"disk_guid": "11111111-2222-4333-8444-555555555555",
               "partition_uuid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
               "filesystem_uuid": "cccccccc-dddd-4eee-8fff-111111111111"}
        io = disk.DiskIO(self.s)
        for key, field in (("disk_guid", "ptuuid"), ("partition_uuid", "partuuid"),
                           ("filesystem_uuid", "uuid")):
            rows = [{"path": "/dev/foreign", field: ids[key]}]
            with self.subTest(field=field), patch.object(io, "command", return_value=json.dumps({"blockdevices": rows})):
                with self.assertRaisesRegex(StorageError, "foreign or duplicated"):
                    io.unique_ids(ids, "/dev/nvme9n1", "/dev/nvme9n1p1")
        owned = [{"path": "/dev/nvme9n1", "ptuuid": ids["disk_guid"], "children": [
            {"path": "/dev/nvme9n1p1", "ptuuid": ids["disk_guid"],
             "partuuid": ids["partition_uuid"], "uuid": ids["filesystem_uuid"]}]}]
        with patch.object(io, "command", return_value=json.dumps({"blockdevices": owned})):
            io.unique_ids(ids, "/dev/nvme9n1", "/dev/nvme9n1p1")

    def test_future_state_not_allowed_at_earlier_journal_stage(self):
        self.saved_plan()
        self.io.crash_after = "format"
        with self.assertRaises(Interrupted):
            self.initialize()
        journal = self.io.journal()
        disk.save(self.s, journal, "gpt_done")
        events = list(self.io.events)
        with self.assertRaisesRegex(StorageError, "filesystem inconsistent"):
            self.initialize()
        self.assertEqual(events, self.io.events)

    def test_missing_owned_journal_never_adopts_formatted_disk(self):
        self.saved_plan()
        self.io.crash_after = "format"
        with self.assertRaises(Interrupted):
            self.initialize()
        self.s._local(disk.JOURNAL).unlink()
        events = list(self.io.events)
        with self.assertRaises(StorageError):
            self.initialize()
        self.assertEqual(events, self.io.events)

    def test_mountpoint_payload_symlink_and_insecure_parent_refuse(self):
        data = self.root / "data"
        data.mkdir()
        (data / "must-preserve").write_bytes(b"existing")
        with self.assertRaisesRegex(StorageError, "nonempty"):
            disk.plan(self.s, io=self.io)
        (data / "must-preserve").unlink(); data.rmdir()
        data.symlink_to(self.root / "etc", target_is_directory=True)
        with self.assertRaisesRegex(StorageError, "symlink"):
            disk.plan(self.s, io=self.io)
        data.unlink()
        (self.root / "dev/disk").chmod(0o777)
        with self.assertRaisesRegex(StorageError, "protected"):
            disk.plan(self.s, io=self.io)
        self.assert_no_mutation()

    def test_holders_mounted_lvm_raid_root_and_ambiguous_identity_refuse(self):
        holders = self.root / "sys/class/block/nvme9n1/holders"
        (holders / "dm-fixture").touch()
        with self.assertRaisesRegex(StorageError, "holders"):
            disk.plan(self.s, io=self.io)
        (holders / "dm-fixture").unlink()
        original = copy.deepcopy(self.runner.blocks)
        for key, value in (("mountpoints", ["/other"]), ("type", "lvm"), ("type", "raid1"),
                           ("ro", True), ("serial", None)):
            with self.subTest(key=key, value=value):
                self.runner.blocks[2][key] = value
                with self.assertRaises(StorageError):
                    disk.plan(self.s, io=self.io)
                self.runner.blocks = copy.deepcopy(original)
        self.runner.blocks.append(block("/dev/duplicate", "259:9", serial="synthetic-data"))
        with self.assertRaisesRegex(StorageError, "ambiguous disk"):
            disk.plan(self.s, io=self.io)
        self.runner.blocks = original
        self.runner.blocks[1]["pkname"] = "/dev/nvme9n1"
        with self.assertRaisesRegex(StorageError, "root or boot"):
            disk.plan(self.s, io=self.io)
        self.assert_no_mutation()

    def test_unsafe_symlink_targets_refused(self):
        link = self.root / "dev/disk/by-id/nvme-synthetic-data"
        for target in ("/dev/nvme9n1", "../../../outside", "../../disk/nested", "../nvme9n1"):
            with self.subTest(target=target):
                link.unlink(); link.symlink_to(target)
                with self.assertRaisesRegex(StorageError, "unsafe stable disk symlink"):
                    disk.plan(self.s, io=self.io)
        self.assert_no_mutation()

    def test_fstab_conflicts_duplicates_and_escaped_target_refused(self):
        fs_uuid = "11111111-2222-4333-8444-555555555555"
        self.s.config["data_uuid"] = fs_uuid
        good = f"UUID={fs_uuid} /data ext4 defaults 0 2\n".encode()
        for contents in (b"UUID=foreign /data ext4 defaults 0 2\n", good * 2,
                         b"UUID=foreign /da\\164a ext4 defaults 0 2\n",
                         f"UUID={fs_uuid} /foreign ext4 defaults 0 2\n".encode()):
            with self.subTest(contents=contents):
                (self.root / "etc/fstab").write_bytes(contents)
                with self.assertRaisesRegex(StorageError, "fstab"):
                    disk.plan(self.s, io=self.io)
                self.assertEqual((self.root / "etc/fstab").read_bytes(), contents)
        self.assert_no_mutation()

    def test_journal_permissions_hardlink_symlink_unknown_stage_and_duplicate_json_refuse(self):
        self.saved_plan()
        self.stop_at("prepared")
        path = self.s._local(disk.JOURNAL)
        original = path.read_bytes()
        path.chmod(0o644)
        with self.assertRaises(StorageError):
            self.initialize()
        path.chmod(0o600)
        alias = self.root / "journal-alias"
        os.link(path, alias)
        with self.assertRaises(StorageError):
            self.initialize()
        alias.unlink()
        journal = self.io.journal()
        journal["stage"] = "unknown"
        path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(StorageError, "stage changed"):
            self.initialize()
        path.write_bytes(b'{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(StorageError, "duplicate JSON"):
            self.initialize()
        path.unlink(); alias.write_bytes(original); path.symlink_to(alias)
        with self.assertRaisesRegex(StorageError, "symlink"):
            self.initialize()
        self.assertEqual(self.io.events, [])

    def test_existing_mode_has_no_formatting_dispatch(self):
        with patch.object(disk, "initialize", side_effect=AssertionError("must not format")):
            with self.assertRaises(StorageError):
                Storage(dict(self.config, storage_mode="existing"), self.runner, self.root).adopt()
        self.assert_no_mutation()

    def test_nonzero_command_is_accounted_for_and_output_is_redacted(self):
        with self.assertRaisesRegex(StorageError, "disk command failed") as error:
            disk.DiskIO(self.s).command([sys.executable, "-c", "print('PRIVATE OUTPUT'); raise SystemExit(3)"])
        self.assertNotIn("PRIVATE OUTPUT", str(error.exception))

    def test_timed_out_child_is_killed_and_waited_before_return(self):
        processes = []
        real_popen = subprocess.Popen
        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process
        with patch.object(disk.subprocess, "Popen", side_effect=record):
            with self.assertRaisesRegex(StorageError, "timed out"):
                disk.DiskIO(self.s).command([sys.executable, "-c", "import time; time.sleep(20)"], timeout=0.05)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].returncode)
        self.assertLess(processes[0].returncode, 0)

    def test_transaction_lock_excludes_second_owner(self):
        second = SyntheticIO(self.s)
        with disk.transaction_lock(self.s, self.io):
            with self.assertRaisesRegex(StorageError, "active"):
                with disk.transaction_lock(self.s, second):
                    self.fail("second transaction obtained an active lock")
        with disk.transaction_lock(self.s, second):
            self.assertIsNotNone(second.lock_fd)

    def test_inherited_child_lock_survives_parent_context_close(self):
        child = None
        second = SyntheticIO(self.s)
        try:
            with disk.transaction_lock(self.s, self.io):
                child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read(1)"],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    pass_fds=(self.io.lock_fd,))
            with self.assertRaisesRegex(StorageError, "active"):
                with disk.transaction_lock(self.s, second):
                    self.fail("surviving child lost its inherited lock")
            child.communicate(b"x", timeout=5)
            self.assertEqual(child.returncode, 0)
            with disk.transaction_lock(self.s, second):
                self.assertIsNotNone(second.lock_fd)
        finally:
            if child is not None and child.poll() is None:
                child.kill(); child.wait(timeout=5)

    def test_timeout_accounts_for_descendant_after_process_leader_exits(self):
        """An exited leader cannot hide a live grandchild holding pipe and lock."""
        io = disk.DiskIO(self.s)
        second = SyntheticIO(self.s)
        real_popen = subprocess.Popen
        leaders = []
        marker = self.root / "grandchild-started"
        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            leaders.append(process)
            return process
        try:
            with disk.transaction_lock(self.s, io):
                script = ("import pathlib, subprocess, sys; "
                          "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], "
                          "pass_fds=(int(sys.argv[1]),)); "
                          "pathlib.Path(sys.argv[2]).write_text(str(p.pid))")
                with patch.object(disk.subprocess, "Popen", side_effect=record):
                    with self.assertRaisesRegex(StorageError, "timed out"):
                        io.command([sys.executable, "-c", script, str(io.lock_fd), str(marker)], timeout=0.25)
            self.assertTrue(marker.exists(), "fixture leader did not spawn its child")
            self.assertEqual(len(leaders), 1)
            self.assertEqual(leaders[0].returncode, 0)
            # If the grandchild survives, the same file-description lock survives.
            with disk.transaction_lock(self.s, second):
                self.assertIsNotNone(second.lock_fd)
        finally:
            for leader in leaders:
                try:
                    os.killpg(leader.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if leader.poll() is None:
                    leader.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
