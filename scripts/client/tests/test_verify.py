"""Offline negative/report and real fixed-test regressions; no model requests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))
import verify


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v2-verifier-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)

    def test_actual_v1g2_bytes_and_baseline_no_import_errors(self):
        workspace = self.root / "workspace"
        workspace.mkdir(mode=0o700)
        for name in ("text_utils.py", "test_text_utils.py"):
            source = CLIENT / "verifier_fixture" / name
            original = CLIENT.parent / "validation/v1g2" / name
            self.assertEqual(source.read_bytes(), original.read_bytes())
            shutil.copyfile(source, workspace / name)
        result = verify.run_bounded(list(verify.FIXED_ARGV), workspace, dict(os.environ), timeout=10)
        self.assertEqual(verify.initial_classification(result), {
            "classification": "assertion_failure", "assertion_failures": 5,
            "import_errors": 0, "exit_code": 1})
        self.assertFalse(verify.passing_test(result))

    def test_import_error_or_fabricated_partial_baseline_not_accepted(self):
        base = {"stdout": b"", "stderr": b"Ran 3 tests\nFAILED (failures=5)\n",
                "exit_code": 1, "timed_out": False, "output_limited": False, "process_tree_reaped": True}
        for changes in ({"stderr": b"ModuleNotFoundError: missing\nRan 3 tests\nFAILED (failures=5)\n"},
                        {"timed_out": True}, {"output_limited": True}, {"process_tree_reaped": False},
                        {"exit_code": 0}, {"stderr": b"FAILED (failures=1)\n"}):
            with self.subTest(changes=tuple(changes)):
                self.assertEqual(verify.initial_classification(dict(base, **changes))["classification"], "unexpected_baseline")

    def test_no_overwrite_symlink_hardlink_or_public_workspace_read(self):
        path = self.root / "existing"
        path.write_bytes(b"unchanged")
        with self.assertRaises(verify.VerifyError):
            verify.safe_path(path, fresh=True)
        link = self.root / "link"
        link.symlink_to(path)
        with self.assertRaises(verify.VerifyError):
            verify.safe_path(link)
        path.chmod(0o600)
        os.link(path, self.root / "hard")
        with self.assertRaises(verify.VerifyError):
            verify.read_owned(path)
        path2 = self.root / "public"
        path2.write_bytes(b"data")
        path2.chmod(0o644)
        with self.assertRaises(verify.VerifyError):
            verify.read_owned(path2)
        self.assertEqual(path.read_bytes(), b"unchanged")

    def test_refuse_relative_traversal_git_or_writable_ancestor(self):
        for path in ("relative", str(self.root / ".." / "new")):
            with self.assertRaises(verify.VerifyError):
                verify.safe_path(path, fresh=True)
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(verify.VerifyError, "repository"):
            verify.safe_path(self.root / "new", fresh=True)
        (self.root / ".git").rmdir()
        self.root.chmod(0o777)
        with self.assertRaises(verify.VerifyError):
            verify.safe_path(self.root / "new", fresh=True)
        self.root.chmod(0o700)

    def test_failed_integrity_produces_private_hashbound_diagnostic_only(self):
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        output = self.root / "run"
        with mock.patch.object(verify, "verify_client", side_effect=ValueError("secret-detail-do-not-copy")):
            report = verify.verify(prefix, output, 10)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failures"], ["client_verification_failed"])
        self.assertFalse(any(report["checks"].values()))
        self.assertEqual(set(p.name for p in output.iterdir()), {"raw-evidence.json", "report.json"})
        self.assertEqual(report["raw_evidence_sha256"], hashlib.sha256((output / "raw-evidence.json").read_bytes()).hexdigest())
        self.assertNotIn("secret-detail", (output / "report.json").read_text())
        self.assertNotIn("receipt", report)
        for path in output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(verify.VerifyError):
            verify.verify(prefix, output, 10)

    def test_recursive_secret_redaction_and_exact_canonical_hash(self):
        secret = 'synthetic-"\\-{file:secret}'
        encoded = json.dumps(secret)[1:-1].replace("{", "\\u007b")
        value = {"out": (secret + encoded).encode(), "nested": [secret]}
        clean = verify.scrub(value, [secret, encoded])
        self.assertNotIn(secret, str(clean))
        self.assertNotIn(encoded, str(clean))
        self.assertEqual(clean["nested"], ["[REDACTED]"])
        expected = hashlib.sha256(b'["python3","-I","-B","test_text_utils.py"]').hexdigest()
        self.assertEqual(verify.source_manifest()["test_command_sha256"], expected)
        manifest = verify.source_manifest()
        self.assertEqual(manifest["source_sha256"], verify.digest(manifest["files"]))
        self.assertNotIn("reports/v2-source-manifest.json", manifest["files"])

    def test_root_and_unsafe_budgets_refused_without_writes(self):
        with mock.patch.object(os, "getuid", return_value=0):
            with self.assertRaisesRegex(verify.VerifyError, "ordinary_user"):
                verify.verify(self.root, self.root / "new")
        for timeout in (0, 1801, True, 1.5):
            with self.assertRaisesRegex(verify.VerifyError, "timeout"):
                verify.verify(self.root, self.root / "new", timeout)
        self.assertFalse((self.root / "new").exists())

    def test_hard_overall_deadline_preserves_diagnostic_and_restores_timer(self):
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        with mock.patch.object(verify, "verify_client", side_effect=lambda *a, **k: time.sleep(3)):
            started = time.monotonic()
            report = verify.verify(prefix, self.root / "timeout", 1)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("overall_timeout", report["failures"])
        self.assertEqual(verify.signal.getitimer(verify.signal.ITIMER_REAL), (0.0, 0.0))

    def test_test_mutation_during_independent_rerun_never_passes(self):
        # Synthetic negative unit seam only. The real native PASS is exercised
        # separately by verify_wire_fixture.py using the pinned executable.
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        output = self.root / "run"
        settings = {"auth": {"kind": "env", "reference": "V2_TEST_KEY"},
                    "base_url": "http://127.0.0.1:1/v1", "model": "synthetic"}
        result = {"stdout": b"", "stderr": b"Ran 3 tests in 0.001s\nOK\n", "exit_code": 0,
                  "timed_out": False, "output_limited": False, "process_tree_reaped": True}
        calls = []
        def execute(argv, workspace, *args, **kwargs):
            calls.append(argv)
            if len(calls) == 1:
                return dict(result, stderr=b"Ran 3 tests in 0.001s\nFAILED (failures=5)\n", exit_code=1)
            if len(calls) == 2:
                (workspace / "text_utils.py").write_text("# synthetic event negative fixture\n")
                return result
            self.assertNotIn(verify.KEY_ENV, args[0])
            (workspace / "test_text_utils.py").write_text("# forbidden change during independent run\n")
            return result
        native = {"checks": {k: True for k in ("file_reads", "implementation_edit", "exact_test_command",
                                               "passing_tool_result", "final_response")},
                  "failures": [], "result": "pass"}
        with mock.patch.object(verify, "verify_client", return_value=(settings, {})), \
             mock.patch.object(verify, "versions", return_value={}), \
             mock.patch.object(verify, "load_key", return_value="synthetic-key"), \
             mock.patch.object(verify, "observe_model", return_value="synthetic"), \
             mock.patch.object(verify, "run_bounded", side_effect=execute), \
             mock.patch.object(verify, "parse_events", return_value=native):
            report = verify.verify(prefix, output, 10)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["checks"]["immutable_tests"])
        self.assertIn("immutable_tests_changed_during_final_test", report["failures"])
        self.assertFalse((output / "receipt.json").exists())

    def test_cli_no_arbitrary_command_challenge_body_or_pin(self):
        parser = verify.parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertEqual(options, {"-h", "--help", "--prefix", "--output-dir", "--timeout-seconds"})
        result = subprocess.run([sys.executable, "-B", str(CLIENT / "verify.py"), "--help"],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
