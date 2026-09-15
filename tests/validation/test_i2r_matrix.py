"""Portable safety regressions only; never execute a package, flock, or systemd."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch


PATH = Path(__file__).resolve().parents[2] / "scripts/validation/i2r/matrix.py"
SPEC = importlib.util.spec_from_file_location("i2r_matrix_local_tests", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

IDENTITY = {"kind": "systemd-cgroup-v2", "token": "a" * 32,
            "unit": "local-ai-package-" + "a" * 32 + ".service",
            "boot_id": "b" * 8 + "-bbbb-bbbb-bbbb-" + "b" * 12,
            "invocation_id": "c" * 32, "cgroup_inode": 123,
            "cgroup": "/system.slice/local-ai-package-" + "a" * 32 + ".service"}
PROCESS = {"kind": "installer", "pid": 111, "start_ticks": 444,
           "parent_pid": 222, "observed_parent_pid": 222}


class BoundaryTests(unittest.TestCase):
    def test_child_refuses_before_lease_if_bindings_not_verified(self):
        with patch.object(M, "fixture_guard"), patch.object(M, "assert_active_bindings", side_effect=RuntimeError("denied")), patch.object(M, "acquire_lease") as acquire:
            with self.assertRaisesRegex(RuntimeError, "denied"):
                M.child(Path("/run/i2r-owned/fixture/case"))
            acquire.assert_not_called()

    def test_contender_refuses_before_lock_if_bindings_not_verified(self):
        with patch.object(M, "assert_active_bindings", side_effect=RuntimeError("denied")), patch.object(M, "acquire_lease") as acquire:
            with self.assertRaisesRegex(RuntimeError, "denied"):
                M.contender(Path("/run/i2r-owned/fixture"))
            acquire.assert_not_called()

    def test_competitor_refuses_before_subprocess_if_bindings_not_verified(self):
        with patch.object(M, "assert_active_bindings", side_effect=RuntimeError("denied")), patch.object(M.subprocess, "run") as execute:
            with self.assertRaisesRegex(RuntimeError, "denied"):
                M.compete(Path("/run/i2r-owned/fixture"))
            execute.assert_not_called()

    def test_child_environment_drops_credential_values(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_TOKEN": "example", "API_KEY": "example", "SSH_AUTH_SOCK": "/secret", "HOME": "/private"}, clear=True):
            clean = M.child_env()
        self.assertEqual(clean["GITHUB_ACTIONS"], "true")
        self.assertTrue(set(clean).isdisjoint({"GITHUB_TOKEN", "API_KEY", "SSH_AUTH_SOCK", "HOME"}))

    def test_reused_pid_after_pidfd_open_is_never_signaled(self):
        with patch.object(M, "alive", side_effect=[True, False]), patch.object(M.os, "pidfd_open", return_value=901, create=True), patch.object(M.signal, "pidfd_send_signal", create=True) as send, patch.object(M.os, "close") as close:
            self.assertFalse(M.signal_owned(PROCESS, signal.SIGKILL))
            send.assert_not_called()
            close.assert_called_once_with(901)

    def test_diagnostic_does_not_emit_exception_message(self):
        self.assertEqual(M.safe_code(RuntimeError("sensitive arbitrary response")), "i2r_unexpected_error")


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def journal(self, **updates):
        value = {"schema_version": 1, "units": [], "allocated_units": [], "processes": [], "cases": []}
        value.update(updates)
        M.write_json(self.root / "ownership.json", value)

    def test_missing_journal_with_installer_case_fails_closed(self):
        (self.root / "case").mkdir()
        (self.root / "case/options.json").write_text("{}")
        result = M.cleanup_owned(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["code"], "i2r_ownership_journal_missing")

    def test_producer_killed_before_scope_inspection(self):
        self.journal(units=[IDENTITY], processes=[PROCESS])
        order = []
        with patch.object(M, "signal_owned", side_effect=lambda p, s: order.append("kill_installer")), patch.object(M, "alive", return_value=False), patch.object(M, "inspect_stable", side_effect=lambda i: order.append("inspect_scope") or {"state": "quiescent"}), patch.object(M, "observe", return_value={"recursive_populated": False}), patch.object(M, "compete", return_value="acquired"):
            result = M.cleanup_owned(self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertLess(order.index("kill_installer"), order.index("inspect_scope"))

    def test_surviving_producer_prevents_quiescent_inventory(self):
        self.journal(units=[IDENTITY], processes=[PROCESS])
        with patch.object(M, "signal_owned", side_effect=M.InstallError("i2r_process_ancestry_unverified")), patch.object(M, "inspect_stable") as inspect:
            result = M.cleanup_owned(self.root)
        self.assertEqual(result["status"], "FAIL")
        inspect.assert_not_called()

    def test_latest_trace_prepared_identity_is_absorbed(self):
        self.journal(cases=["case"])
        (self.root / "case").mkdir()
        M.append_event(self.root / "case", {"stage": "prepared", "identity": IDENTITY})
        with patch.object(M, "inspect_stable", return_value={"state": "quiescent"}) as inspect, patch.object(M, "observe", return_value={"recursive_populated": False}), patch.object(M, "compete", return_value="acquired"):
            result = M.cleanup_owned(self.root)
        inspect.assert_called_once_with(IDENTITY)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(M.read_json(self.root / "ownership.json")["units"], [IDENTITY])

    def test_unrecorded_prepared_identity_preserves_binding_fail_closed(self):
        allocated = {key: IDENTITY[key] for key in ("kind", "token", "unit", "boot_id")}
        self.journal(allocated_units=[allocated])
        scope = Mock()
        observed = {"Id": IDENTITY["unit"], "LoadState": "loaded", "InvocationID": "c" * 32}
        with patch.object(M, "SystemdPackageScope", return_value=scope), patch.object(M, "allocated_observation", return_value=observed), patch.object(M, "compete", return_value="acquired"):
            result = M.cleanup_owned(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["units"][0]["code"], "i2r_prepared_identity_unrecorded")
        scope.abort.assert_not_called()
        self.assertEqual(result["units"][0]["observed_properties"], observed)

    def test_valid_owned_marker_supplies_identity_after_allocation_only(self):
        allocated = {key: IDENTITY[key] for key in ("kind", "token", "unit", "boot_id")}
        self.journal(allocated_units=[allocated], cases=["case"])
        state = self.root / "case/data/services/installer"
        state.mkdir(parents=True)
        M.write_json(state / "package-service-policy.json", {"phase": "owned", "transaction": IDENTITY})
        with patch.object(M, "inspect_stable", return_value={"state": "quiescent"}) as inspect, patch.object(M, "observe", return_value={"recursive_populated": False}), patch.object(M, "compete", return_value="acquired"):
            result = M.cleanup_owned(self.root)
        inspect.assert_called_once_with(IDENTITY)
        self.assertEqual(result["status"], "PASS")

    def test_extra_canonical_holder_blocks_cleanup_success(self):
        self.journal()
        with patch.object(M, "compete", return_value="busy"):
            result = M.cleanup_owned(self.root)
        self.assertEqual(result["status"], "FAIL")

    def test_ancestry_disagreement_is_never_signaled(self):
        self.journal(processes=[{**PROCESS, "observed_parent_pid": 333}])
        with patch.object(M, "signal_owned") as send:
            result = M.cleanup_owned(self.root)
        self.assertEqual(result["status"], "FAIL")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
