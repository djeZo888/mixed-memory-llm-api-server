"""Worker-safe actual source boundary tests; no systemd, apt or dpkg execution."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("i2r_preparation", ROOT / "scripts/validation/i2r/preparation.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PreparationBoundary(unittest.TestCase):
    def setUp(self):
        # Repository ancestors must be protected, as on the actual hosted path.
        # tempfile's default /tmp ancestry would violate AnchoredRoot's contract.
        self.tmp = tempfile.TemporaryDirectory(prefix=".i2r-preparation-", dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.fixture = MODULE.fixture_packages(self.root)
        self.packages = self.fixture.__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)
        self.options = self.packages._apt_options()

    def test_actual_generator_uses_real_live_anchor_and_exact_sandbox(self):
        self.assertEqual(self.options[-2:], ["-o", "APT::Sandbox::User=root"])
        self.assertTrue(any(item.startswith("Dir::Cache=/proc/") for item in self.options))
        self.assertNotIn(str(self.packages.data), " ".join(self.options))
        self.packages._anchor.check()

    def test_actual_parser_accepts_each_actual_container_preparation_shape(self):
        for name, mode in MODULE.PREPARATION_MODES.items():
            with self.subTest(mode=name):
                self.assertTrue(MODULE.Runner._package_preparation(["apt-get", *self.options, *mode]))

    def test_unsupported_sandbox_and_mode_overrides_refused_without_execution(self):
        with patch("install.core.subprocess.run", side_effect=AssertionError("package execution forbidden locally")) as execute:
            result = MODULE.check_negatives(self.options)
        self.assertEqual(len(result), 12)
        self.assertNotIn("apt_mutation", result)
        self.assertTrue(all(case["status"] == "PASS" for case in result.values()), result)
        execute.assert_not_called()

    def test_unbound_apt_is_source_only_even_if_its_parser_regresses(self):
        for accepted in (False, True):
            with self.subTest(parser_accepted=accepted), \
                    patch.object(MODULE.Runner, "_package_preparation", return_value=accepted) as parser, \
                    patch.object(MODULE.Runner, "run", side_effect=AssertionError("unbound apt Runner call forbidden")) as runner, \
                    patch("install.core.subprocess.run", side_effect=AssertionError("unbound apt execution forbidden")) as execute:
                result = MODULE.check_source_only_negatives()["apt_mutation"]
                self.assertEqual(result["status"], "FAIL" if accepted else "PASS")
                self.assertEqual(result["runner_execution"]["status"], "NOT_TESTED")
                parser.assert_called_once_with(["apt", "install", "i2r-fixture"])
                runner.assert_not_called()
                execute.assert_not_called()

    def test_actual_negative_driver_refuses_any_unbound_executable_before_runner(self):
        with patch.object(MODULE, "negative_commands", return_value={"injected_apt": ["apt", "install", "i2r-fixture"]}), \
                patch.object(MODULE.Runner, "_package_preparation", return_value=True) as parser, \
                patch.object(MODULE.Runner, "run", side_effect=AssertionError("unbound Runner call forbidden")) as runner, \
                patch("install.core.subprocess.run", side_effect=AssertionError("unbound execution forbidden")) as execute:
            result = MODULE.check_negatives(self.options)
        self.assertEqual(result["injected_apt"], {"status": "FAIL", "code": "unbound_negative_executable_refused"})
        parser.assert_not_called()
        runner.assert_not_called()
        execute.assert_not_called()

    def test_runner_calls_actual_argv_and_scrubs_environment_unit_only(self):
        class Result:
            returncode = 0
            stdout = MODULE.FAKE_RESPONSE + "\n"
        argv = ["apt-get", *self.options, *MODULE.PREPARATION_MODES["update"]]
        with patch.dict(os.environ, {"I2R_PRIVATE_TEST_VALUE": "do-not-inherit"}), \
                patch("install.core.subprocess.run", return_value=Result()) as execute:
            self.assertEqual(self.packages.runner.run(argv), MODULE.FAKE_RESPONSE + "\n")
        self.assertEqual(execute.call_args.args[0], argv)
        self.assertNotIn("I2R_PRIVATE_TEST_VALUE", execute.call_args.kwargs["env"])

    def test_actual_container_requires_anchor(self):
        self.packages._anchor = None
        with self.assertRaisesRegex(MODULE.InstallError, "package_storage_anchor_required"):
            self.packages._apt_options()

    def test_canonical_helper_refusals_are_explicit_fixture_unit_coverage(self):
        lease_root = self.root / "canonical-helper-fixture"
        lease_root.mkdir(mode=0o700)
        with MODULE.acquire_lease(system_root=lease_root, trusted_uid=os.geteuid()) as lease:
            result = MODULE.capability_refusals(lease, system_root=lease_root,
                                               trusted_uid=os.geteuid(), wrong_root=self.root)
            self.assertTrue(all(case["status"] == "PASS" for case in result.values()), result)
            lease.validate()
        with MODULE.acquire_lease(blocking=False, system_root=lease_root, trusted_uid=os.geteuid()):
            pass

    def test_manager_source_gap_is_not_promoted_to_success(self):
        self.assertEqual(MODULE.manager_contract()["status"], "NOT_TESTED")

    def test_hosted_run_requires_outer_binding_guard_before_any_fixture(self):
        class Guardian:
            @staticmethod
            def assert_active_bindings(_workdir):
                raise RuntimeError("bindings_required")
        with patch.dict(sys.modules, {"guardian": Guardian}), \
                patch.object(MODULE, "fixture_packages", side_effect=AssertionError("fixture before guard")):
            with self.assertRaisesRegex(RuntimeError, "bindings_required"):
                MODULE.run(self.root)


if __name__ == "__main__":
    unittest.main()
