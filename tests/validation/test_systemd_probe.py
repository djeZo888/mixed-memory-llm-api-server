"""Local fail-closed ownership checks; real Linux behavior is tested in I2P CI."""

import importlib.util
from pathlib import Path
import unittest
from unittest import mock


MODULE = Path(__file__).resolve().parents[2] / "scripts/validation/i2p/systemd_probe.py"
SPEC = importlib.util.spec_from_file_location("systemd_probe", MODULE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.unit = "i2p-12345678-package-exit.service"
        self.group = "/system.slice/" + self.unit
        self.process = {"pid": 4242, "starttime": 70000, "cgroup": "0::" + self.group}
        self.owned = {
            "invocation_id": "1" * 32, "control_group": self.group,
            "main_process": self.process,
        }
        self.state = {
            "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
            "InvocationID": "1" * 32, "ControlGroup": self.group, "MainPID": "4242",
        }

    def assert_refuses_stop(self, state=None, process=None):
        state = self.state if state is None else state
        process = self.process if process is None else process
        with mock.patch.object(probe, "_show", return_value=state), \
                mock.patch.object(probe, "_proc_identity", return_value=process), \
                mock.patch.object(probe, "_command") as command:
            with self.assertRaises(probe.ProbeError):
                probe._stop_owned(self.unit, self.owned, Path("/absent/package.lock"))
            command.assert_not_called()

    def test_same_name_replacement_invocation_refuses_stop(self):
        self.assert_refuses_stop(state={**self.state, "InvocationID": "2" * 32})

    def test_changed_control_group_refuses_stop(self):
        self.assert_refuses_stop(state={**self.state, "ControlGroup": "/system.slice/other.service"})

    def test_changed_main_pid_refuses_stop(self):
        self.assert_refuses_stop(state={**self.state, "MainPID": "4243"})

    def test_recycled_pid_refuses_stop(self):
        self.assert_refuses_stop(process={**self.process, "starttime": 80000})

    def test_process_moved_cgroup_refuses_stop(self):
        self.assert_refuses_stop(process={**self.process, "cgroup": "0::/other"})

    def test_missing_unit_with_live_owned_process_refuses_stop(self):
        self.assert_refuses_stop(state={**self.state, "LoadState": "not-found"})

    def test_verified_identity_stops_exact_unit_and_checks_lock(self):
        with mock.patch.object(probe, "_show", return_value=self.state), \
                mock.patch.object(probe, "_proc_identity", return_value=self.process), \
                mock.patch.object(probe, "_command", return_value="") as command, \
                mock.patch.object(Path, "exists", side_effect=lambda: False), \
                mock.patch.object(probe, "_locked") as locked:
            result = probe._stop_owned(self.unit, self.owned, Path("/absent/package.lock"))
        command.assert_called_once_with(["/usr/bin/systemctl", "stop", self.unit], timeout=10)
        locked.assert_not_called()
        self.assertTrue(result["cgroup_removed"])

    def test_invalid_run_id_refused_before_host_actions(self):
        with mock.patch.object(probe, "_command") as command:
            with self.assertRaisesRegex(probe.ProbeError, "invalid_run_id"):
                probe.run(Path("/tmp/unused"), "other.service;kill")
        command.assert_not_called()

    def test_generated_helper_has_valid_python_syntax(self):
        compile(probe._HELPER, "fake_package.py", "exec")


if __name__ == "__main__":
    unittest.main()
