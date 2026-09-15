"""Local source/safety tests. No real Linux namespace, mount, or device action."""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("i2s_writer_probe",
                                             REPO / "scripts/validation/i2s/writer_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class WriterSafetyTests(unittest.TestCase):
    def record(self):
        return {"target": "/run/i2s-writer-owned/data/alias", "identity": [77, 88],
                "entry": ["44", "1", "0:77", "/source", "/run/i2s-writer-owned/data/alias",
                          "rw", "-", "tmpfs", "owned", "rw"],
                "mount_id": 44, "device": "0:77", "fstype": "tmpfs"}

    def test_plan_is_pure_and_has_no_external_device_or_path(self):
        with patch.object(probe.subprocess, "run", side_effect=AssertionError("command")), \
             patch.object(probe.tempfile, "mkdtemp", side_effect=AssertionError("allocation")):
            plan = probe.plan()
        self.assertEqual(plan["mode"], "DRY_RUN")
        self.assertEqual(plan["disk_backing_bytes"], 0)
        self.assertEqual(plan["max_concurrent_tmpfs_bytes"], 16 * 1024 * 1024)
        self.assertFalse(plan["external_path_or_device_arguments"])

    def test_unapproved_context_refuses_before_fixture_creation(self):
        with patch.dict(probe.os.environ, {}, clear=True), \
             patch.object(probe, "Fixture", side_effect=AssertionError("created fixture")), \
             self.assertRaisesRegex(RuntimeError, "refuse_context:GITHUB_ACTIONS"):
            probe.run_probe()

    def test_unknown_allocation_stops_without_starting_later_fixture(self):
        with patch.object(probe, "_environment"), \
             patch.object(probe.os, "readlink", return_value="mnt:[fixture]"), \
             patch.object(probe, "Fixture", side_effect=RuntimeError("allocation outcome unknown")) as fixture:
            result = probe.run_probe()
        self.assertEqual(fixture.call_count, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["cleanup"]["status"], "INCOMPLETE")
        self.assertEqual(result["stop_reason"], "cleanup_uncertain_no_further_fixture_allocation")

    def test_mac_refuses_before_any_mount_command(self):
        context = SimpleNamespace(validate_context=lambda _value: None)
        with patch.object(probe, "_load", return_value=context), \
             patch.object(probe.platform, "system", return_value="Darwin"), \
             patch.object(probe, "_command", side_effect=AssertionError("command")), \
             patch.object(probe, "Fixture", side_effect=AssertionError("fixture")), \
             self.assertRaisesRegex(probe.ProbeError, "requires_disposable_linux_root"):
            probe.run_probe()

    def test_mount_identity_drift_prevents_unmount(self):
        record = self.record()
        for key, changed in (("mount_id", 45), ("device", "0:78"),
                             ("identity", [77, 89]), ("entry", ["replacement"])):
            actual = copy.deepcopy(record)
            actual[key] = changed
            with self.subTest(key=key), patch.object(probe, "_capture_mount", return_value=actual), \
                 patch.object(probe, "_command", side_effect=AssertionError("unsafe unmount")), \
                 self.assertRaisesRegex(probe.ProbeError, "mount_ownership_changed_preserve_state"):
                probe._unmount_owned(record)

    def test_initial_namespace_refuses_before_capability_or_mutation(self):
        context = SimpleNamespace(validate_context=lambda _value: None,
                                  capability=lambda _path: self.fail("capability reached"))
        with patch.object(probe, "_load", return_value=context), \
             patch.object(probe.platform, "system", return_value="Linux"), \
             patch.object(probe.platform, "machine", return_value="x86_64"), \
             patch.object(probe.os, "geteuid", return_value=0), \
             patch.object(probe.Path, "read_text", return_value="ID=ubuntu\nVERSION_ID=24.04\n"), \
             patch.object(probe.os, "readlink", return_value="mnt:[100]"), \
             self.assertRaisesRegex(probe.ProbeError, "refuse_initial_mount_namespace"):
            probe._environment()

    def test_shared_namespace_refuses_before_capability_or_mutation(self):
        context = SimpleNamespace(validate_context=lambda _value: None,
                                  capability=lambda _path: self.fail("capability reached"))
        with patch.object(probe, "_load", return_value=context), \
             patch.object(probe.platform, "system", return_value="Linux"), \
             patch.object(probe.platform, "machine", return_value="x86_64"), \
             patch.object(probe.os, "geteuid", return_value=0), \
             patch.object(probe.Path, "read_text", return_value="ID=ubuntu\nVERSION_ID=24.04\n"), \
             patch.object(probe.os, "readlink", side_effect=["mnt:[101]", "mnt:[100]"]), \
             patch.object(probe, "_mounts", return_value=[{"propagation": ["shared:1"]}]), \
             self.assertRaisesRegex(probe.ProbeError, "requires_private_mount_propagation"):
            probe._environment()

    def test_exact_unmount_has_bounded_target_and_independent_absence_check(self):
        record = self.record()
        with patch.object(probe, "_capture_mount", return_value=record), \
             patch.object(probe, "_command") as command, \
             patch.object(probe, "_mounts", return_value=[{"id": 99}]):
            result = probe._unmount_owned(record, lazy=True)
        command.assert_called_once_with(["umount", "--internal-only", "--lazy", "--", record["target"]])
        self.assertTrue(result["independently_observed_mount_id_absent"])
        self.assertEqual(result["verified_identity"], [77, 88])

    def test_surviving_mount_id_is_not_cleanup_success(self):
        record = self.record()
        with patch.object(probe, "_capture_mount", return_value=record), \
             patch.object(probe, "_command"), \
             patch.object(probe, "_mounts", return_value=[{"id": 44}]), \
             self.assertRaisesRegex(probe.ProbeError, "owned_mount_id_still_present"):
            probe._unmount_owned(record)

    def test_missing_or_stacked_mount_is_ambiguous_not_owned(self):
        for rows in ([], [{"target": "/owned"}, {"target": "/owned"}]):
            with self.subTest(rows=rows), patch.object(probe, "_mounts", return_value=rows), \
                 patch.object(probe, "_identity", side_effect=AssertionError("identity queried")), \
                 self.assertRaisesRegex(probe.ProbeError, "mount_target_missing_or_ambiguous"):
                probe._capture_mount(Path("/owned"))

    def test_cleanup_preserves_foreign_descendant_mount_and_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            marker = path / "sentinel"
            marker.write_bytes(b"unchanged")
            fixture = probe.Fixture.__new__(probe.Fixture)
            fixture.path, fixture.identity = path, [1, 2]
            fixture.records, fixture.removed, fixture.clean_tree = [], [], {}
            with patch.object(probe, "_identity", return_value=[1, 2]), \
                 patch.object(probe, "_mounts", return_value=[{"target": str(path / "unknown")}]), \
                 patch.object(probe, "_command", side_effect=AssertionError("unsafe cleanup")):
                result = fixture.cleanup()
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertTrue(result["scratch_preserved"])
            self.assertEqual(marker.read_bytes(), b"unchanged")

    def test_changed_cleanup_inventory_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            marker = path / "sentinel"
            marker.write_bytes(b"unchanged")
            fixture = probe.Fixture.__new__(probe.Fixture)
            fixture.path, fixture.identity = path, [1, 2]
            fixture.records, fixture.removed, fixture.clean_tree = [], [], {"sentinel": "original"}
            with patch.object(probe, "_identity", return_value=[1, 2]), \
                 patch.object(probe, "_mounts", return_value=[]), \
                 patch.object(probe, "_snapshot", return_value={"sentinel": "replacement"}):
                result = fixture.cleanup()
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["error_code"], "scratch_identity_or_bytes_changed_preserve_state")
            self.assertEqual(marker.read_bytes(), b"unchanged")

    def test_command_drops_environment_and_output_and_bounds_time(self):
        with patch.dict(probe.os.environ, {"TOKEN": "must-not-inherit"}), \
             patch.object(probe.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as command:
            probe._command(["mount", "--version"])
        kwargs = command.call_args.kwargs
        self.assertEqual(kwargs["env"], {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        self.assertEqual(kwargs["timeout"], 15)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def test_command_timeout_never_becomes_success(self):
        with patch.object(probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("mount", 15)), \
             self.assertRaisesRegex(probe.ProbeError, "command_incomplete:mount:TimeoutExpired"):
            probe._command(["mount"])

    def test_nonzero_tool_code_is_retained_without_tool_output(self):
        with patch.object(probe.subprocess, "run", return_value=SimpleNamespace(returncode=32)), \
             self.assertRaisesRegex(probe.ProbeError, "command_failed:umount:32"):
            probe._command(["umount"])

    def test_accepted_write_is_not_reported_as_refused(self):
        class StorageIOError(RuntimeError):
            code = "fixture_path_refusal"

        io = SimpleNamespace(StorageIOError=StorageIOError)
        self.assertEqual(probe._attempt(io, lambda: None), {"rejected": False, "error_code": None})

        def refused():
            raise StorageIOError()

        self.assertEqual(probe._attempt(io, refused),
                         {"rejected": True, "error_code": "fixture_path_refusal"})
        with self.assertRaises(OSError):
            probe._attempt(io, lambda: (_ for _ in ()).throw(OSError("not a safety refusal")))


if __name__ == "__main__":
    unittest.main()
