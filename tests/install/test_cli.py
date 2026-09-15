"""Exercise public CLI/read-only boundary on the worker; no host mutations."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install import main
from install.config import validate
from install.core import InstallError
from install.host import budget, model_plan

FLAGS = ["--profile", "flagship-hybrid", "--model-set", "glm,qwen"]
FIXTURE = ["--fixture-host", str(REPO / "tests/install/fixtures/ubuntu-host.json")]


class CliTests(unittest.TestCase):
    def invoke(self, args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = main.main(args)
        return status, output.getvalue(), error.getvalue()

    def test_help_actual_wrapper(self):
        result = subprocess.run([str(REPO / "install.sh"), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("plan", "apply", "resume", "status", "verify", "--through", "--model-set"):
            self.assertIn(name, result.stdout)

    def test_plan_fixture_actual_wrapper_no_mutating_entry(self):
        result = subprocess.run([str(REPO / "install.sh"), "plan", *FLAGS, *FIXTURE], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["evidence_class"], "SYNTHETIC_FIXTURE")
        self.assertEqual(plan["disk_budget"]["model_download_bytes"], 547696839790)
        self.assertIn("acceptance", plan["pending_required_stages"])
        self.assertTrue(plan["version_lock"])
        self.assertTrue(all(x["measured_ram_vram_minimum"] is None for x in plan["models"]))

    def test_fixture_apply_resume_verify_cannot_reach_actions(self):
        with patch.object(main, "run_boundary") as action:
            for command in ("apply", "resume", "verify"):
                code, _, error = self.invoke([command, *FLAGS, *FIXTURE, "--yes", "--through", "driver"])
                self.assertNotEqual(code, 0)
                self.assertIn("fixture_host_only_allowed_for_plan", error)
            action.assert_not_called()

    def test_full_apply_fails_before_mutation(self):
        with patch.object(main, "make_plan", return_value={}), patch.object(main, "run_boundary") as action:
            code, _, error = self.invoke(["apply", *FLAGS, "--yes"])
            self.assertEqual(code, 78)
            self.assertIn("required_deployment_stages_not_implemented_i1c", error)
            action.assert_not_called()

    def test_bounded_package_apply_waits_for_reviewed_i1r_l1_before_mutation(self):
        with patch.object(main, "make_plan", return_value={}), patch.object(main, "run_boundary") as action:
            for through in ("base", "driver", "container", "runtime", "acquisition"):
                code, _, error = self.invoke(["apply", *FLAGS, "--yes", "--through", through])
                self.assertEqual(code, 78)
                self.assertIn("reviewed_i1r_l1_package_integration_required", error)
            action.assert_not_called()

    def test_unsupported_host_and_small_root_rejected(self):
        config = validate({"profile": "flagship-hybrid", "model_set": "glm"})
        with self.assertRaisesRegex(InstallError, "unsupported_host"):
            main.require_preflight(config, {"host_supported": False})
        with self.assertRaisesRegex(InstallError, "insufficient_root"):
            main.require_preflight(config, {"host_supported": True, "host": {"root_available_bytes": 5 * 1024**3}})
        with self.assertRaisesRegex(InstallError, "insufficient_dedicated"):
            main.require_preflight(config, {"host_supported": True, "host": {"root_available_bytes": 10 * 1024**3}, "disk_budget": {"space_status": "insufficient"}})

    def test_shared_vs_distinct_capacity_not_ram(self):
        config = validate({"profile": "fast-gpu", "model_set": "qwen"})
        models = model_plan(config, REPO)
        shared = budget(config, models, {"capacity": {"shared_model_filesystem": True, "data_available_bytes": 1024**4, "model_available_bytes": 1024**4}})
        separate = budget(config, models, {"capacity": {"shared_model_filesystem": False, "data_available_bytes": 1024**4, "model_available_bytes": 1024**4}})
        self.assertEqual(shared["data_required_bytes"] - separate["data_required_bytes"], models[0]["download_bytes"])
        self.assertIsNone(models[0]["measured_ram_vram_minimum"])

    def test_resume_verify_require_existing_bootstrap(self):
        with patch.object(main, "BOOTSTRAP", REPO / "tests/install/nonexistent-bootstrap.json"):
            for command in ("resume", "verify"):
                code, _, error = self.invoke([command, *FLAGS, "--through", "driver", "--yes"])
                self.assertEqual(code, 1)
                self.assertIn("installation_bootstrap_missing", error)

    def test_unknown_settings_do_not_leak(self):
        code, _, error = self.invoke(["apply", "--role", "server", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("explicit_profile_and_model_set_required", error)


if __name__ == "__main__":
    unittest.main()
