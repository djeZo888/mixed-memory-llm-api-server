"""Synthetic Linux-command fixtures; no real device/mount/package operations."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[2] / "scripts/install/storage.py"
sys.path.insert(0, str(MODULE.parent.parent))
from install import storage
GUARD_SPEC = importlib.util.spec_from_file_location("guard_under_test", MODULE.parent.parent / "common/registered-storage.py")
guard = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(guard)


def disk(name, device, uuid=None, parent=None, mount=None, kind="disk", serial=None):
    return {"name": name, "path": name, "maj:min": device, "type": kind,
            "pkname": parent, "mountpoints": [mount] if mount else [None],
            "fstype": "ext4" if uuid else None, "uuid": uuid, "ro": False,
            "size": 8 * 1024 ** 4, "serial": serial, "wwn": None}


class FakeRunner:
    def __init__(self):
        self.blocks = [disk("/dev/sda", "8:0", serial="root-device"),
                       disk("/dev/sda1", "8:1", "root-uuid", "/dev/sda", "/", "part"),
                       disk("/dev/nvme1n1", "259:0", serial="data-device"),
                       disk("/dev/nvme1n1p1", "259:1", "data-uuid", "/dev/nvme1n1", "/data", "part")]
        self.calls = []
        self.mutations = []
        self.available = {"/": 10 * storage.GIB, "/data": 1000 * storage.GIB}
        self.fail = None
        self.mount_loss = False

    def run(self, argv, *, timeout=30, env=None):
        self.calls.append(argv)
        if argv[0] == self.fail:
            raise RuntimeError("SENSITIVE-RUNNER-OUTPUT")
        if argv[0] == "lsblk":
            return json.dumps({"blockdevices": self.blocks})
        if argv[0] == "findmnt":
            path = argv[-1]
            choices = [(point, row) for row in self.blocks for point in row["mountpoints"]
                       if point and (point == "/" or path == point or path.startswith(point + "/"))]
            point, row = max(choices, key=lambda match: len(match[0]))
            if self.mount_loss and point != "/":
                point, row = "/", self.blocks[1]
            return json.dumps({"filesystems": [{"target": point, "source": row["path"],
                                                "uuid": row["uuid"], "fstype": row["fstype"],
                                                "options": "rw,relatime", "maj:min": row["maj:min"]}]})
        if argv[0] == "df":
            return "Avail\n" + str(self.available[argv[-1]]) + "\n"
        if argv[0] == "mount":
            self.mutations.append(argv)
            uuid = argv[argv.index("--source") + 1].removeprefix("UUID=")
            target = argv[argv.index("--target") + 1]
            for row in self.blocks:
                if row["uuid"] == uuid:
                    row["mountpoints"] = [target]
            return ""
        if argv[0] == "systemctl":
            self.mutations.append(argv)
            return ""
        if argv[0] == "wipefs":
            return json.dumps({"signatures": []})
        raise AssertionError("unexpected command: " + repr(argv))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "etc").mkdir()
        (self.root / "etc/fstab").write_text("# existing admin config\n")
        self.runner = FakeRunner()
        self.config = {"data_dir": "/data", "data_uuid": "data-uuid"}

    def tearDown(self):
        self.tmp.cleanup()

    def subject(self, **updates):
        return storage.Storage(dict(self.config, **updates), self.runner, self.root)

    def test_plan_is_read_only_and_displays_shared_capacity(self):
        before = sorted(str(p) for p in self.root.rglob("*"))
        result = self.subject().plan()
        self.assertEqual(result["data"]["uuid"], "data-uuid")
        self.assertTrue(result["capacity"]["shared_model_filesystem"])
        self.assertEqual(result["roots"]["state"], "/data/services/installer")
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))
        self.assertEqual(self.runner.mutations, [])

    def test_exact_mount_required_no_parent_fallback(self):
        self.runner.mount_loss = True
        with self.assertRaisesRegex(storage.StorageError, "dedicated mount is absent"):
            self.subject().plan()
        self.assertEqual(list((self.root / "data").iterdir()), [])

    def test_existing_adoption_and_identical_rerun_do_not_rewrite(self):
        first = self.subject().adopt()
        path = self.root / storage.REGISTRATION_PATH.lstrip("/")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "data/services/secrets").stat().st_mode & 0o777, 0o700)
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.assertEqual(first, self.subject().adopt())
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        self.assertEqual(self.runner.mutations, [])

    def test_adoption_preserves_existing_credentials_and_data(self):
        self.subject().adopt()
        key = self.root / "data/services/secrets/api.key"
        key.write_bytes(b"fixture-secret-without-newline")
        key.chmod(0o600)
        model = self.root / "data/models/model.partial"
        model.write_bytes(b"partial-download")
        self.subject().adopt()
        self.assertEqual(key.read_bytes(), b"fixture-secret-without-newline")
        self.assertEqual(model.read_bytes(), b"partial-download")

    def test_trusted_uuid_cannot_be_replaced_by_config_or_environment(self):
        self.subject().adopt()
        self.runner.blocks[3]["uuid"] = "different-uuid"
        with patch.dict(os.environ, {"EXPECTED_UUID": "different-uuid", "AI_DATA_UUID": "different-uuid"}):
            with self.assertRaises(storage.StorageError):
                self.subject(data_uuid="different-uuid").verify()

    def test_reboot_device_names_may_change_but_uuid_is_stable(self):
        self.subject().adopt()
        self.runner.blocks[2].update(name="/dev/nvme9n1", path="/dev/nvme9n1", **{"maj:min": "259:9"})
        self.runner.blocks[3].update(name="/dev/nvme9n1p1", path="/dev/nvme9n1p1", pkname="/dev/nvme9n1", **{"maj:min": "259:10"})
        current = self.subject().verify()
        self.assertEqual(current["data"]["source"], "/dev/nvme9n1p1")

    def test_deleted_registered_directory_and_mount_loss_fail(self):
        self.subject().adopt()
        (self.root / "data/models").rmdir()
        with self.assertRaisesRegex(storage.StorageError, "directory disappeared"):
            self.subject().verify()
        (self.root / "data/models").mkdir()
        self.runner.mount_loss = True
        with self.assertRaises(storage.StorageError):
            self.subject().adopt()

    def test_symlink_and_reserved_paths_rejected(self):
        for path in ("/", "/boot/data", "/etc/ai", "/data/../other", "/data//nested", "/data/"):
            with self.subTest(path=path), self.assertRaises(storage.StorageError):
                self.subject(data_dir=path)
        (self.root / "data/models").symlink_to(self.root / "etc", target_is_directory=True)
        with self.assertRaisesRegex(storage.StorageError, "symlink"):
            self.subject().adopt()

    def test_insecure_registration_and_service_dirs_rejected(self):
        self.subject().adopt()
        path = self.root / storage.REGISTRATION_PATH.lstrip("/")
        path.chmod(0o644)
        with self.assertRaises(storage.StorageError):
            self.subject().verify()
        path.chmod(0o600)
        (self.root / "data/services/secrets").chmod(0o755)
        with self.assertRaisesRegex(storage.StorageError, "private service directory"):
            self.subject().verify()

    def test_hardlinked_registration_rejected(self):
        self.subject().adopt()
        path = self.root / storage.REGISTRATION_PATH.lstrip("/")
        os.link(path, self.root / "data/registration-link")
        with self.assertRaises(storage.StorageError):
            self.subject().verify()

    def test_root_boot_parent_and_lvm_raid_rejected(self):
        for change in ({"pkname": "/dev/sda"}, {"type": "lvm"}, {"type": "raid1"}, {"ro": True}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.runner.blocks[3])
                self.runner.blocks[3].update(change)
                with self.assertRaises(storage.StorageError):
                    self.subject().plan()
                self.runner.blocks[3] = original

    def test_uuid_ambiguity_rejected(self):
        self.runner.blocks.append(disk("/dev/sdz", "65:0", "data-uuid"))
        with self.assertRaisesRegex(storage.StorageError, "duplicated"):
            self.subject().plan()

    def test_root_capacity_stop_and_warning_distinct_from_data(self):
        self.runner.available["/"] = 3 * storage.GIB
        with self.assertRaisesRegex(storage.StorageError, "4 GiB"):
            self.subject().plan()
        self.runner.available["/"] = 5 * storage.GIB
        result = self.subject().plan()
        self.assertEqual(len(result["warnings"]), 1)
        self.assertGreater(result["capacity"]["data_available_bytes"], result["capacity"]["root_available_bytes"])

    def test_separate_model_mount_registration(self):
        (self.root / "weights").mkdir()
        self.runner.blocks += [disk("/dev/sdc", "8:32"), disk("/dev/sdc1", "8:33", "model-uuid", "/dev/sdc", "/weights", "part")]
        self.runner.available["/weights"] = 2000 * storage.GIB
        result = self.subject(model_dir="/weights", model_uuid="model-uuid").adopt()
        self.assertFalse(result["capacity"]["shared_model_filesystem"])
        self.assertEqual(result["models"]["mount"], "/weights")

    def test_uuid_mount_preserves_fstab_and_backups_on_data(self):
        self.runner.blocks[3]["mountpoints"] = [None]
        subject = self.subject(storage_mode="mount")
        plan = subject.plan()
        self.assertEqual(plan["mounts"][0]["uuid"], "data-uuid")
        self.assertEqual(self.runner.mutations, [])
        subject.adopt()
        fstab = self.root / "etc/fstab"
        self.assertEqual(fstab.read_text(), "# existing admin config\nUUID=data-uuid /data ext4 defaults 0 2\n")
        backups = list((self.root / "data/backups").glob("fstab.*.backup"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "# existing admin config\n")
        self.assertEqual(self.runner.mutations[0], ["mount", "--source", "UUID=data-uuid", "--target", "/data", "--types", "ext4", "--options", "rw"])
        mutation_count = len(self.runner.mutations)
        subject.adopt()
        self.assertEqual(len(self.runner.mutations), mutation_count)

    def test_mount_refuses_nonempty_target_and_fstab_conflict_before_mutation(self):
        self.runner.blocks[3]["mountpoints"] = [None]
        (self.root / "data/keep.txt").write_text("keep")
        with self.assertRaisesRegex(storage.StorageError, "nonempty"):
            self.subject(storage_mode="mount").adopt()
        (self.root / "data/keep.txt").unlink()
        (self.root / "etc/fstab").write_text("UUID=other-data /data ext4 defaults 0 2\n")
        with self.assertRaisesRegex(storage.StorageError, "conflicting"):
            self.subject(storage_mode="mount").adopt()
        self.assertEqual(self.runner.mutations, [])

    def test_separate_mount_requires_explicit_uuid_before_mutation(self):
        self.runner.blocks[3]["mountpoints"] = [None]
        with self.assertRaisesRegex(storage.StorageError, "own explicit UUID"):
            self.subject(storage_mode="mount", model_dir="/weights").adopt()
        self.assertEqual(self.runner.mutations, [])

    def test_interrupted_layout_creation_resumes_without_overwriting(self):
        subject = self.subject()
        original = subject.verify
        calls = 0

        def interrupt_after_first_directory(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise storage.StorageError("fixture interrupted")
            return original(*args, **kwargs)

        with patch.object(subject, "verify", side_effect=interrupt_after_first_directory):
            with self.assertRaisesRegex(storage.StorageError, "interrupted"):
                subject.adopt()
        self.assertTrue((self.root / "data/hf-cache").is_dir())
        self.assertFalse((self.root / storage.REGISTRATION_PATH.lstrip("/")).exists())
        self.assertEqual(subject.adopt()["data"]["uuid"], "data-uuid")

    def test_mount_loss_during_layout_creation_stops_before_registration(self):
        subject = self.subject()
        original = subject.verify
        calls = 0

        def lose_mount(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                self.runner.mount_loss = True
            return original(*args, **kwargs)

        with patch.object(subject, "verify", side_effect=lose_mount):
            with self.assertRaisesRegex(storage.StorageError, "dedicated mount is absent"):
                subject.adopt()
        self.assertFalse((self.root / storage.REGISTRATION_PATH.lstrip("/")).exists())
        self.assertFalse((self.root / "data/services").exists())

    def test_root_payload_scan_rejects_container_state_and_large_archive(self):
        self.subject().adopt()
        container = self.root / "var/lib/docker"
        container.mkdir(parents=True)
        payload = container / "metadata.db"
        payload.write_bytes(b"container-metadata")
        with self.assertRaisesRegex(storage.StorageError, "container payload"):
            self.subject().root_payload_guard()
        payload.unlink()
        cache = self.root / "root/.cache"
        cache.mkdir(parents=True)
        with (cache / "weights.safetensors").open("wb") as stream:
            stream.truncate(128 * 1024 ** 2)
        with self.assertRaisesRegex(storage.StorageError, "large model/cache/archive"):
            self.subject().root_payload_guard()

    def test_root_payload_scan_excludes_registered_data_and_symlinks(self):
        self.subject().adopt()
        with (self.root / "data/models/weights.gguf").open("wb") as stream:
            stream.truncate(128 * 1024 ** 2)
        srv = self.root / "srv"
        srv.mkdir()
        (srv / "data").symlink_to(self.root / "data", target_is_directory=True)
        self.assertEqual(self.subject().root_payload_guard()["root_payload_scan"]["status"], "pass")

    def test_reports_only_written_below_verified_logs(self):
        subject = self.subject()
        result = subject.adopt()
        for path in ("/tmp/root-report.json", "/data/logs/../services/report.json", "/data/logs"):
            with self.subTest(path=path), self.assertRaises((ValueError, storage.StorageError)):
                guard.write_report(subject, result, path)
        guard.write_report(subject, result, "/data/logs/guard.json")
        self.assertTrue((self.root / "data/logs/guard.json").exists())
        self.runner.mount_loss = True
        with self.assertRaises(storage.StorageError):
            guard.write_report(subject, result, "/data/logs/after-loss.json")
        self.assertFalse((self.root / "data/logs/after-loss.json").exists())

    def test_command_failure_sanitized(self):
        self.runner.fail = "lsblk"
        with self.assertRaises(storage.StorageError) as caught:
            self.subject().adopt()
        self.assertNotIn("SENSITIVE", str(caught.exception))
        self.assertFalse((self.root / storage.REGISTRATION_PATH.lstrip("/")).exists())

    def test_initialize_plan_delegates_readonly_disk_transaction(self):
        with patch("install.disk_init.plan", return_value={"disk_mutation_performed": False}) as helper:
            subject = self.subject(storage_mode="initialize")
            self.assertEqual(subject.plan(), {"disk_mutation_performed": False})
            helper.assert_called_once_with(subject)
        self.assertEqual(self.runner.mutations, [])

    def test_initialize_adopt_returns_helper_registration(self):
        expected = {"data": {"uuid": "fixture"}}
        with patch("install.disk_init.initialize", return_value=expected) as helper:
            subject = self.subject(storage_mode="initialize")
            self.assertIs(subject.adopt(), expected)
            helper.assert_called_once_with(subject)

    def test_existing_adopt_never_calls_disk_initializer(self):
        with patch("install.disk_init.initialize", side_effect=AssertionError("must not initialize")):
            self.subject().adopt()


if __name__ == "__main__":
    unittest.main()
