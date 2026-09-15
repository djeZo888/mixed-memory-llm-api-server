"""Worker-local I2S guards/refusals only; these are not actual Linux evidence."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

MODULE = Path(__file__).resolve().parents[2] / "scripts/validation/i2s/loop_matrix.py"
SPEC = importlib.util.spec_from_file_location("i2s_loop_matrix", MODULE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class SafetyTests(unittest.TestCase):
    def fixture(self):
        guard = SimpleNamespace(owned=Mock(return_value={"backing": "/run/i1s-loop-owned/backing.img", "backing_inode": 123,
                                                       "backing_device": os.makedev(0, 40)}))
        fixture = probe.Fixture(guard, None, SimpleNamespace(StorageError=RuntimeError), "local_safety")
        fixture.loop = "/dev/loop9"
        return fixture

    def check_patches(self, fixture, updates=None, sector=512):
        row = {"name": fixture.loop, "back-file": "/run/i1s-loop-owned/backing.img", "back-ino": 123,
               "back-maj:min": "0:40", "maj:min": "7:9", "offset": 0, "sizelimit": 0, "ro": False, "autoclear": False}
        row.update(updates or {})
        info = SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_rdev=os.makedev(7, 9))
        def read(path):
            return str(sector if path.name == "logical_block_size" else probe.SIZE // 512)
        return (patch.object(probe, "execute", return_value=json.dumps({"loopdevices": [row]})),
                patch.object(probe.Path, "lstat", return_value=info),
                patch.object(probe.Path, "read_text", read),
                patch.object(probe.Path, "iterdir", return_value=iter([])))

    def test_pure_plan_never_executes_or_writes(self):
        with patch.object(probe.subprocess, "run", side_effect=AssertionError("command")), patch.object(probe.os, "open", side_effect=AssertionError("write")):
            result = probe.plan()
        self.assertEqual(result["fixture_bytes"], 256 * 1024 * 1024)
        self.assertLessEqual(result["aggregate_backing_bytes_including_shipped"], 2 * 1024**3)
        self.assertIn("canonical global admission", result["not_tested"])
        self.assertIn("production disk discovery/root exclusion", result["not_tested"])

    def test_apply_without_hosted_context_refuses_before_commands_or_writes(self):
        with patch.dict(probe.os.environ, {}, clear=True), patch.object(probe.subprocess, "run", side_effect=AssertionError("command")), patch.object(probe.os, "open", side_effect=AssertionError("write")):
            with self.assertRaisesRegex(RuntimeError, "refuse_context"):
                probe.apply_preflight(Path("/tmp/untrusted-output"))

    def test_external_device_argument_not_exposed(self):
        result = subprocess.run(["python3", "-I", "-B", str(MODULE), "--dry-run", "--device", "/dev/sdb"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_dry_run_output_argument_refuses_without_creating(self):
        with patch.object(probe.sys, "argv", [str(MODULE), "--dry-run", "--output", "/tmp/must-not-exist"]), patch.object(probe.os, "open", side_effect=AssertionError("write")):
            with self.assertRaisesRegex(RuntimeError, "dry_run_does_not_write"):
                probe.main()

    def test_real_identity_requires_reviewed_guard_first(self):
        fixture = self.fixture()
        fixture.guard.owned.side_effect = RuntimeError("ownership unknown")
        with patch.object(probe, "execute", side_effect=AssertionError("must not run tool")):
            with self.assertRaisesRegex(RuntimeError, "ownership unknown"):
                fixture.check()

    def test_kernel_identity_valid(self):
        fixture = self.fixture()
        p1, p2, p3, p4 = self.check_patches(fixture)
        with p1, p2, p3, p4:
            self.assertEqual(fixture.check()["backing_inode"], 123)

    def test_kernel_backing_identity_mismatch_refuses(self):
        for field, value in (("back-ino", 999), ("back-maj:min", "8:1"), ("back-file", "/unrelated.img"),
                             ("maj:min", "7:10"), ("name", "/dev/loop10")):
            with self.subTest(field=field):
                fixture = self.fixture()
                p1, p2, p3, p4 = self.check_patches(fixture, {field: value})
                with p1, p2, p3, p4, self.assertRaisesRegex(RuntimeError, "kernel_backing_identity_changed"):
                    fixture.check()

    def test_geometry_and_mode_change_refuses(self):
        for field, value in (("offset", 512), ("sizelimit", 100), ("ro", True), ("autoclear", True)):
            with self.subTest(field=field):
                fixture = self.fixture()
                p1, p2, p3, p4 = self.check_patches(fixture, {field: value})
                with p1, p2, p3, p4, self.assertRaisesRegex(RuntimeError, "loop_geometry_changed"):
                    fixture.check()

    def test_non512_sector_not_claimed_tested(self):
        fixture = self.fixture()
        p1, p2, p3, p4 = self.check_patches(fixture, sector=4096)
        with p1, p2, p3, p4, self.assertRaisesRegex(RuntimeError, "loop_size_or_sector_changed"):
            fixture.check()

    def test_unknown_ownership_cleanup_does_not_run_unmount_or_detach(self):
        fixture = self.fixture()
        with patch.object(fixture, "check", side_effect=RuntimeError("kernel identity unknown")), patch.object(probe, "execute", side_effect=AssertionError("cleanup mutation")):
            result = fixture.cleanup()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["detached"])
        self.assertFalse(result["removed"])
        self.assertEqual(result["error"], "kernel identity unknown")

    def test_replaced_mount_id_refuses_before_unmount(self):
        fixture = self.fixture()
        target = Path("/run/i1s-loop-owned/root/data")
        previous = {"id": "100", "target": str(target), "dev": "7:10"}
        current = dict(previous, id="101")
        with patch.object(fixture, "check"), patch.object(probe, "mount_rows", return_value=[current]), patch.object(probe, "execute", side_effect=AssertionError("unmount")):
            with self.assertRaisesRegex(RuntimeError, "owned_mount_identity_changed"):
                fixture.exact_mount(target, previous)

    def test_duplicate_mount_targets_refuse(self):
        fixture = self.fixture()
        target = Path("/run/i1s-loop-owned/root/data")
        row = {"id": "100", "target": str(target), "dev": "7:10"}
        with patch.object(fixture, "check"), patch.object(probe, "mount_rows", return_value=[row, row]):
            with self.assertRaisesRegex(RuntimeError, "owned_mount_identity_changed"):
                fixture.exact_mount(target, row)

    def test_refusal_requires_exact_before_after_state(self):
        fixture = self.fixture()
        with patch.object(fixture, "snapshot", side_effect=[{"disk_sha256": "a"}, {"disk_sha256": "b"}]):
            with self.assertRaisesRegex(RuntimeError, "refusal_changed_owned_state"):
                fixture.refusal("changed", Mock(side_effect=RuntimeError("safe refusal")))
        self.assertEqual(fixture.results, [])

    def test_no_exception_cannot_be_promoted_to_refusal_pass(self):
        fixture = self.fixture()
        with patch.object(fixture, "snapshot", return_value={"disk_sha256": "a"}):
            with self.assertRaisesRegex(RuntimeError, "refusal_missing"):
                fixture.refusal("silently accepted", lambda: None)
        self.assertEqual(fixture.results, [])

    def test_os_error_records_actual_errno(self):
        fixture = self.fixture()
        with patch.object(fixture, "snapshot", return_value={"disk_sha256": "a"}):
            result = fixture.refusal("exclusive claim", Mock(side_effect=OSError(16, "Device or resource busy")))
        self.assertEqual(result["errno"], 16)
        self.assertEqual(result["before"], result["after"])

    def test_corruption_bounds_refuse_before_open(self):
        fixture = self.fixture()
        with patch.object(fixture, "check"), patch.object(probe.os, "open", side_effect=AssertionError("device open")):
            for offset, payload in ((-1, b"x"), (probe.SIZE, b"x"), (0, bytes(4097))):
                with self.subTest(offset=offset), self.assertRaisesRegex(RuntimeError, "invalid_fixture_corruption_range"):
                    fixture.corrupt(offset, payload)

    def test_corruption_refuses_mounted_fixture(self):
        fixture = self.fixture()
        with patch.object(fixture, "check"), patch.object(probe, "mount_rows", return_value=[{"target": str(fixture.root / "data")}]), patch.object(probe.os, "open", side_effect=AssertionError("device open")):
            with self.assertRaisesRegex(RuntimeError, "corruption_requires_unmounted"):
                fixture.corrupt(512, b"FOREIGN!")

    def test_command_scrubs_environment_and_preserves_exact_exit_code(self):
        completed = subprocess.CompletedProcess(["sfdisk"], 42, "private stdout", "private stderr")
        with patch.object(probe.subprocess, "run", return_value=completed) as call:
            with self.assertRaisesRegex(RuntimeError, "fixture_command_failed:sfdisk:exit=42") as failure:
                probe.execute(["sfdisk", "--version"])
        self.assertEqual(call.call_args.kwargs["env"], probe.ENV)
        self.assertEqual(call.call_args.kwargs["timeout"], 30)
        self.assertNotIn("private", str(failure.exception))

    def test_output_limit_is_enforced(self):
        result = subprocess.CompletedProcess([], 0, "x" * 262145, "")
        with patch.object(probe.subprocess, "run", return_value=result), self.assertRaisesRegex(RuntimeError, "output_limit"):
            probe.execute(["owned-tool"])


if __name__ == "__main__":
    unittest.main()
