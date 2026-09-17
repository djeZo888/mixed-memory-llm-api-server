"""Offline effort-option regressions; no package installs or inference requests."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_bootstrap import snapshot


CLIENT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("a2o_common_tests", CLIENT / "client_common.py")
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)
SPEC = importlib.util.spec_from_file_location("a2o_bootstrap_tests", CLIENT / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(SPEC)
with mock.patch.dict(sys.modules, {"client_common": common}):
    SPEC.loader.exec_module(bootstrap)

INVALID_EFFORTS = (None, True, False, 0, 1, 1.5, [], {}, ("low",), ("none",), "", "LOW", " low",
                   "low ", "low\n", "NONE", "None", " none", "none ", "none\n", "null",
                   "minimal", "medium", "high", "max", "{env:EFFORT}")


class ReasoningEffortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="a2o-effort-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.prefix = self.root / "client with spaces & punctuation"
        self.settings = {
            "version": common.VERSION,
            "base_url": "http://127.0.0.1:30002/v1",
            "model": "synthetic-vendor/model:Q4",
            "auth": {"kind": "file", "reference": str(self.root / "absent protected key")},
            "context_tokens": 16384,
            "output_tokens": 1024,
            "lock_sha256": hashlib.sha256((CLIENT / "package-lock.json").read_bytes()).hexdigest(),
        }

    def args(self, *extra):
        return bootstrap.parser().parse_args([
            "--prefix", str(self.prefix), "--base-url", self.settings["base_url"],
            "--model", self.settings["model"], "--context-tokens", "16384", "--output-tokens", "1024",
            "--api-key-file", self.settings["auth"]["reference"], *extra,
        ])

    def run_bootstrap(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bootstrap.bootstrap(args)
        return output.getvalue()

    def installed_fixture(self, effort=None):
        """Only metadata and copied helpers: deliberately no executable/npm run."""
        settings = dict(self.settings)
        if effort is not None:
            settings["reasoning_effort"] = effort
        self.prefix.mkdir(mode=0o700)
        for name in ("bin", "xdg", "xdg/config", "xdg/data", "xdg/cache", "xdg/state", "xdg/config/opencode",
                     "npm", "npm/cache", "npm/logs", "tmp", "bun-cache", "managed", "discovery-home"):
            (self.prefix / name).mkdir(mode=0o700)
        for filename, data in (("bootstrap.json", settings), ("opencode.json", common.config_for(settings)),
                               ("models.json", {})):
            common.write_new(self.prefix / filename, common.json_bytes(data))
        for package in ("opencode-ai", "@opencode-ai/plugin", common.native_package()):
            directory = common.runtime_dir(self.prefix) / "node_modules" / package
            directory.mkdir(parents=True, mode=0o700)
            common.write_new(directory / "package.json", common.json_bytes({"version": common.VERSION}))
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(CLIENT / name, common.runtime_dir(self.prefix) / name)
        for target, source in (("opencode-client", "launch.py"), ("client_common.py", "client_common.py")):
            shutil.copyfile(CLIENT / source, self.prefix / "bin" / target)
        return settings

    def replace_json(self, filename, value):
        (self.prefix / filename).write_bytes(common.json_bytes(value))

    def test_explicit_effort_requires_exact_none_or_low_string(self):
        for value in ("none", "low"):
            with self.subTest(value=value):
                self.assertEqual(common.reasoning_effort(value), value)
        for value in INVALID_EFFORTS:
            with self.subTest(value=repr(value)), self.assertRaises(common.ClientError):
                common.reasoning_effort(value)

    def test_effort_rejects_string_subclasses(self):
        class Effort(str):
            pass

        for value in (Effort("none"), Effort("low")):
            with self.subTest(value=value), self.assertRaises(common.ClientError):
                common.reasoning_effort(value)

    def test_default_config_preserves_legacy_model_shape(self):
        config = common.config_for(self.settings)
        self.assertEqual(config["provider"]["local"]["models"][self.settings["model"]], {
            "name": self.settings["model"], "limit": {"context": 16384, "output": 1024},
        })
        self.assertNotIn("reasoning", json.dumps(config))

    def test_low_config_uses_pinned_model_option_and_preserves_limits(self):
        settings = dict(self.settings, reasoning_effort="low")
        config = common.config_for(settings)
        model = config["provider"]["local"]["models"][settings["model"]]
        self.assertEqual(model["options"], {"reasoningEffort": "low"})
        self.assertEqual(model["limit"], {"context": 16384, "output": 1024})
        self.assertNotIn("reasoningEffort", config["provider"]["local"]["options"])
        self.assertNotIn("reasoning_effort", config)

    def test_none_config_uses_same_model_option_without_extra_body_fields(self):
        default = common.config_for(self.settings)
        expected = json.loads(json.dumps(default))
        expected["provider"]["local"]["models"][self.settings["model"]]["options"] = {"reasoningEffort": "none"}
        actual = common.config_for(dict(self.settings, reasoning_effort="none"))
        self.assertEqual(actual, expected)
        self.assertNotEqual(actual, default)

    def test_help_distinguishes_explicit_none_from_default_omission(self):
        help_text = " ".join(bootstrap.parser().format_help().split())
        self.assertIn("literal none or low", help_text)
        self.assertIn("none is explicit, omission keeps the default", help_text)
        self.assertIn("new prefix required to change", help_text)

    def test_config_rejects_invalid_present_effort_including_null(self):
        for value in INVALID_EFFORTS:
            with self.subTest(value=repr(value)), self.assertRaises(common.ClientError):
                common.config_for(dict(self.settings, reasoning_effort=value))

    def test_default_plan_omits_effort_without_writes_processes_or_key_reads(self):
        before = snapshot(self.root)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")):
            plan = json.loads(self.run_bootstrap(self.args("--dry-run")))
        self.assertNotIn("reasoning_effort", plan)
        self.assertFalse(plan["mutations"])
        self.assertEqual(before, snapshot(self.root))

    def test_low_plan_reports_effort_without_writes_processes_or_key_reads(self):
        before = snapshot(self.root)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")):
            plan = json.loads(self.run_bootstrap(self.args("--reasoning-effort", "low", "--dry-run")))
        self.assertEqual(plan["reasoning_effort"], "low")
        self.assertFalse(plan["mutations"])
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse(Path(self.settings["auth"]["reference"]).exists())

    def test_none_plan_reports_explicit_effort_without_writes_processes_or_key_reads(self):
        before = snapshot(self.root)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")):
            plan = json.loads(self.run_bootstrap(self.args("--reasoning-effort", "none", "--dry-run")))
        self.assertEqual(plan["reasoning_effort"], "none")
        self.assertFalse(plan["mutations"])
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse(Path(self.settings["auth"]["reference"]).exists())

    def test_cli_rejects_invalid_effort_before_mutation(self):
        before = snapshot(self.root)
        for value in ("", "LOW", " low", "low ", "NONE", "None", " none", "none ", "none\n",
                      "null", "false", "1", "minimal", "medium", "high", "max"):
            with self.subTest(value=value):
                result = subprocess.run([
                    sys.executable, str(CLIENT / "bootstrap.py"),
                    "--prefix", str(self.prefix), "--base-url", self.settings["base_url"],
                    "--model", self.settings["model"], "--context-tokens", "16384", "--output-tokens", "1024",
                    "--auth-disabled", "--reasoning-effort", value, "--dry-run",
                ], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), cwd=self.root,
                    capture_output=True, text=True, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, snapshot(self.root))

    def test_programmatic_bootstrap_rejects_non_string_effort_before_processes(self):
        before = snapshot(self.root)
        for value in (True, False, 0, 1, [], {}, ("low",), ("none",)):
            args = self.args("--dry-run")
            args.reasoning_effort = value
            with self.subTest(value=repr(value)), mock.patch.object(
                bootstrap, "run_capture", side_effect=AssertionError("unexpected process")
            ), self.assertRaises(common.ClientError):
                self.run_bootstrap(args)
            self.assertEqual(before, snapshot(self.root))

    def test_legacy_manifest_verifies_and_default_repeat_remains_unchanged(self):
        settings = self.installed_fixture()
        before = snapshot(self.root)
        self.assertNotIn("reasoning_effort", common.verify_install(self.prefix))
        with mock.patch.object(bootstrap, "run_capture", return_value=common.VERSION) as run:
            self.assertIn("PASS:", self.run_bootstrap(self.args()))
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [str(common.binary_path(self.prefix)), "--version"])
        self.assertEqual(common.verify_install(self.prefix), settings)
        self.assertEqual(before, snapshot(self.root))

    def test_low_manifest_and_identical_repeat_verify_without_reinstall_or_writes(self):
        settings = self.installed_fixture(effort="low")
        before = snapshot(self.root)
        self.assertEqual(common.verify_install(self.prefix), settings)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")):
            plan = json.loads(self.run_bootstrap(self.args("--reasoning-effort", "low", "--dry-run")))
        self.assertEqual(plan["action"], "verify")
        self.assertEqual(plan["reasoning_effort"], "low")
        with mock.patch.object(bootstrap, "run_capture", return_value=common.VERSION) as run:
            self.assertIn("PASS:", self.run_bootstrap(self.args("--reasoning-effort", "low")))
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [str(common.binary_path(self.prefix)), "--version"])
        self.assertEqual(before, snapshot(self.root))

    def test_none_manifest_and_identical_repeat_verify_without_reinstall_or_writes(self):
        settings = self.installed_fixture(effort="none")
        before = snapshot(self.root)
        self.assertEqual(common.verify_install(self.prefix), settings)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")):
            plan = json.loads(self.run_bootstrap(self.args("--reasoning-effort", "none", "--dry-run")))
        self.assertEqual(plan["action"], "verify")
        self.assertEqual(plan["reasoning_effort"], "none")
        with mock.patch.object(bootstrap, "run_capture", return_value=common.VERSION) as run:
            self.assertIn("PASS:", self.run_bootstrap(self.args("--reasoning-effort", "none")))
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [str(common.binary_path(self.prefix)), "--version"])
        self.assertEqual(before, snapshot(self.root))

    def test_default_install_refuses_changed_low_selection_without_mutation(self):
        self.installed_fixture()
        before = snapshot(self.root)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")), \
                self.assertRaises(common.ClientError):
            self.run_bootstrap(self.args("--reasoning-effort", "low", "--dry-run"))
        self.assertEqual(before, snapshot(self.root))

    def test_low_install_refuses_omitted_selection_without_mutation(self):
        self.installed_fixture(effort="low")
        before = snapshot(self.root)
        with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")), \
                self.assertRaises(common.ClientError):
            self.run_bootstrap(self.args("--dry-run"))
        self.assertEqual(before, snapshot(self.root))

    def test_none_transitions_require_new_prefix_without_mutation(self):
        for installed, selected in ((None, "none"), ("low", "none"), ("none", None), ("none", "low")):
            with self.subTest(installed=installed, selected=selected):
                self.installed_fixture(effort=installed)
                before = snapshot(self.root)
                flags = [] if selected is None else ["--reasoning-effort", selected]
                for dry_run in ([], ["--dry-run"]):
                    with mock.patch.object(bootstrap, "run_capture", side_effect=AssertionError("unexpected process")), \
                            self.assertRaisesRegex(common.ClientError, "choose a new prefix"):
                        self.run_bootstrap(self.args(*flags, *dry_run))
                    self.assertEqual(before, snapshot(self.root))
                shutil.rmtree(self.prefix)

    def test_config_effort_tampering_is_refused_without_repair(self):
        settings = self.installed_fixture(effort="low")
        for option in ({}, {"reasoningEffort": "high"}, {"reasoning_effort": "low"}):
            config = common.config_for(settings)
            config["provider"]["local"]["models"][settings["model"]]["options"] = option
            self.replace_json("opencode.json", config)
            before = snapshot(self.root)
            with self.subTest(option=option), self.assertRaises(common.ClientError):
                common.verify_install(self.prefix)
            self.assertEqual(before, snapshot(self.root))

    def test_none_config_or_manifest_tampering_is_refused_without_repair(self):
        settings = self.installed_fixture(effort="none")
        for effort in (None, "low"):
            changed = dict(settings)
            if effort is None:
                del changed["reasoning_effort"]
            else:
                changed["reasoning_effort"] = effort
            for tamper_manifest in (False, True):
                with self.subTest(effort=effort, tamper_manifest=tamper_manifest):
                    self.replace_json("bootstrap.json", changed if tamper_manifest else settings)
                    self.replace_json("opencode.json", common.config_for(settings if tamper_manifest else changed))
                    before = snapshot(self.root)
                    with self.assertRaises(common.ClientError):
                        common.verify_install(self.prefix)
                    self.assertEqual(before, snapshot(self.root))

    def test_manifest_added_or_removed_effort_cannot_diverge_from_config(self):
        settings = self.installed_fixture()
        self.replace_json("bootstrap.json", dict(settings, reasoning_effort="low"))
        before = snapshot(self.root)
        with self.assertRaises(common.ClientError):
            common.verify_install(self.prefix)
        self.assertEqual(before, snapshot(self.root))
        self.replace_json("bootstrap.json", settings)
        self.replace_json("opencode.json", common.config_for(dict(settings, reasoning_effort="low")))
        before = snapshot(self.root)
        with self.assertRaises(common.ClientError):
            common.verify_install(self.prefix)
        self.assertEqual(before, snapshot(self.root))

    def test_manifest_invalid_type_is_rejected_even_with_matching_manual_config(self):
        settings = self.installed_fixture(effort="low")
        for value in INVALID_EFFORTS:
            manifest = dict(settings, reasoning_effort=value)
            config = common.config_for(settings)
            config["provider"]["local"]["models"][settings["model"]]["options"]["reasoningEffort"] = value
            self.replace_json("bootstrap.json", manifest)
            self.replace_json("opencode.json", config)
            before = snapshot(self.root)
            with self.subTest(value=repr(value)), self.assertRaises(common.ClientError):
                common.verify_install(self.prefix)
            self.assertEqual(before, snapshot(self.root))


if __name__ == "__main__":
    unittest.main()
