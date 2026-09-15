"""Portable source/safety tests; no Linux process, namespace or disk operation."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[2] / "scripts/validation/i2s/process_probe.py"
SPEC = importlib.util.spec_from_file_location("i2s_process_probe_test", MODULE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def identity(pid=123, starttime=9876, state="S"):
    return {"pid": pid, "starttime": starttime, "state": state, "ppid": 12, "pgrp": 123, "session": 123}


class ProcessSafetyTests(unittest.TestCase):
    def test_plan_is_pure_and_honestly_scoped(self):
        with patch.object(probe.os, "open", side_effect=AssertionError("plan wrote")), patch.object(probe.subprocess, "Popen", side_effect=AssertionError("plan launched")):
            result = probe.plan()
        self.assertEqual(result["fixture_devices"], 0)
        self.assertIn("canonical_global_admission", result["not_tested"])
        self.assertIn("production_autonomous_child_deadline", result["not_tested"])
        self.assertIn("real_disk_tool_hard_parent_death", result["not_tested"])

    def test_mac_refuses_before_scratch_or_process_creation(self):
        with patch.object(probe.platform, "system", return_value="Darwin"), patch.object(probe.tempfile, "mkdtemp", side_effect=AssertionError("created scratch")), patch.object(probe.subprocess, "Popen", side_effect=AssertionError("launched process")):
            with self.assertRaisesRegex(RuntimeError, "requires_disposable_linux_root"):
                probe.run_probe()

    def test_nonroot_linux_refuses_before_context_or_namespace_read(self):
        with patch.object(probe.platform, "system", return_value="Linux"), patch.object(probe.os, "geteuid", return_value=502), patch.object(probe.os, "readlink", side_effect=AssertionError("read namespace")):
            with self.assertRaisesRegex(RuntimeError, "requires_disposable_linux_root"):
                probe._guard()

    def test_hidden_worker_refuses_mac_before_reading_intent(self):
        with patch.object(probe.platform, "system", return_value="Darwin"), patch.object(probe, "_read", side_effect=AssertionError("read intent")):
            with self.assertRaisesRegex(RuntimeError, "requires_disposable_linux_root"):
                probe._worker(Path("/run/arbitrary"), "sentinel", "token")

    def test_proc_parser_handles_spaces_and_parentheses_in_name(self):
        # Fields after comm begin with state; starttime is index 19 of this tail.
        fields = ["S", "12", "123", "123"] + ["0"] * 15 + ["9876"] + ["0"] * 8
        result = probe._parse_proc_stat("123 (space ) and (paren)) " + " ".join(fields))
        self.assertEqual(result, identity())

    def test_nonfixture_pid_refused_before_proc_read(self):
        for value in (0, 1, -1, "123", True):
            with self.subTest(pid=value), patch.object(probe.Path, "read_text", side_effect=AssertionError("read proc")):
                with self.assertRaisesRegex(RuntimeError, "unsafe_process_pid"):
                    probe._identity(value)

    def test_changed_starttime_never_opens_pidfd_or_signals(self):
        with patch.object(probe, "_identity", return_value=identity(starttime=9877)), patch.object(probe.os, "pidfd_open", create=True, side_effect=AssertionError("opened recycled PID")), patch.object(probe.signal, "pidfd_send_signal", create=True, side_effect=AssertionError("signaled recycled PID")):
            with self.assertRaisesRegex(RuntimeError, "ownership_changed"):
                probe._signal_exact(identity(), signal.SIGTERM)

    def test_identity_change_after_pidfd_open_never_signals(self):
        with patch.object(probe, "_identity", side_effect=[identity(), identity(starttime=9877)]), patch.object(probe.os, "pidfd_open", create=True, return_value=77) as opening, patch.object(probe.os, "close") as closing, patch.object(probe.signal, "pidfd_send_signal", create=True) as signaling:
            with self.assertRaisesRegex(RuntimeError, "ownership_changed"):
                probe._signal_exact(identity(), signal.SIGTERM)
        opening.assert_called_once_with(123, 0)
        closing.assert_called_once_with(77)
        signaling.assert_not_called()

    def test_exact_process_signal_uses_pidfd_and_closes_it(self):
        with patch.object(probe, "_identity", return_value=identity()), patch.object(probe.os, "pidfd_open", create=True, return_value=77), patch.object(probe.os, "close") as closing, patch.object(probe.signal, "pidfd_send_signal", create=True) as signaling:
            self.assertTrue(probe._signal_exact(identity(), signal.SIGKILL))
        signaling.assert_called_once_with(77, signal.SIGKILL, None, 0)
        closing.assert_called_once_with(77)

    def test_absent_or_zombie_process_is_not_signaled(self):
        for state in (None, identity(state="Z")):
            with self.subTest(state=state), patch.object(probe, "_identity", return_value=state), patch.object(probe.os, "pidfd_open", create=True, side_effect=AssertionError("opened gone process")):
                self.assertFalse(probe._signal_exact(identity(), signal.SIGTERM))

    def test_unknown_ownership_does_not_become_gone(self):
        with patch.object(probe, "_identity", return_value=identity(starttime=9877)):
            with self.assertRaisesRegex(RuntimeError, "ownership_changed"):
                probe._wait_gone(identity(), timeout=0.01)

    def test_records_are_exclusive_private_and_hardlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            probe._write(path, identity())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(probe._read(path), identity())
            with self.assertRaises(FileExistsError):
                probe._write(path, identity(starttime=1))
            os.link(path, Path(directory) / "alias")
            with self.assertRaisesRegex(RuntimeError, "unsafe_process_record"):
                probe._read(path)

    def test_record_symlink_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            target = Path(directory) / "target.json"
            target.write_text(json.dumps(identity()))
            path.symlink_to(target)
            with self.assertRaises(OSError):
                probe._read(path)

    def test_root_path_cannot_select_existing_or_external_scratch(self):
        for root in (Path("/tmp/i2s-process-" + "a" * 32 + "-x"), Path("/run/i2s-process-invalid"), Path("/run"), Path("/data")):
            with self.subTest(root=root), patch.object(probe.Path, "lstat", side_effect=AssertionError("external scratch stat")):
                with self.assertRaisesRegex(RuntimeError, "unsafe_process_root"):
                    probe._protected_root(root)

    def test_harness_has_no_numeric_pid_or_group_signal(self):
        source = MODULE.read_text()
        self.assertNotIn("os.kill(", source)
        self.assertNotIn("os.killpg(", source)
        self.assertNotIn("pkill", source)
        self.assertNotIn("killall", source)


if __name__ == "__main__":
    unittest.main()
