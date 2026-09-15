"""Source-only launch failures through real fixture boundaries; native NOT_TESTED.

All launchers and Docker operations below are synthetic. Private stderr is
intercepted in memory and never printed, written into Git, or treated as native
launch acceptance.
"""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.lifecycle import test_qwen38_fixture_diagnostics as diagnostic_tests
from tests.lifecycle.test_qwen38_image_fixture import ROOT, host, inner


SYNTHETIC_SENTINEL = "Q38NEXT_TEST_SYNTHETIC_SENTINEL_ONLY"
LAUNCHER_SOURCE = ROOT / "scripts/runtime/sglang38_file_auth.py"


def launch_record(**changes):
    operands = {"result": 1, "captured": 0, "engine_calls": 1,
                "first_exception_class": "FixtureFailure"}
    operands.update(changes)
    return {"status": "FAIL", "code": "actual_image_fixture_failed",
            "failure_origin": {"filename": "run_pinned_image.py", "line": 150,
                               "exception_class": "FixtureFailure"},
            "launch_failure": operands}


class Qwen38LaunchDiagnosticTests(unittest.TestCase):
    def launcher(self, action):
        launcher = SimpleNamespace(__file__=str(LAUNCHER_SOURCE),
                                   LOGGER=SimpleNamespace(error=Mock(return_value=None)))
        launcher.main = lambda argv: action(launcher, argv)
        return launcher

    def invoke(self, launcher, captured, engines, sentinel=SYNTHETIC_SENTINEL):
        with patch.object(inner.os, "write", return_value=1) as private:
            with self.assertRaises(inner.FixtureFailure) as caught:
                inner.checked_launch(launcher, ["--fixture-only"], captured, engines, sentinel)
        self.assertEqual(caught.exception.args, ("actual_native_launch_setup_failed",))
        self.assertEqual(private.call_count, 1)
        self.assertEqual(private.call_args.args[0], 2)
        raw = private.call_args.args[1]
        self.assertLessEqual(len(raw), 16384)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertTrue(sentinel.encode() not in raw, "synthetic diagnostic content disclosed")
        return caught.exception, json.loads(raw)

    def main_output(self, action, *, diagnostic_failure=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(inner, "run_actual", side_effect=action), \
                patch.object(inner, "run_failure_children") as later, \
                patch.object(inner.os, "write", side_effect=diagnostic_failure) as private, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = inner.main(["--actual-image", "--repo", str(ROOT), "--context", "131072"])
        self.assertEqual(code, 2)
        self.assertEqual(stderr.getvalue(), "")
        later.assert_not_called()
        self.assertTrue(SYNTHETIC_SENTINEL not in stdout.getvalue(),
                        "synthetic diagnostic content disclosed")
        record = json.loads(stdout.getvalue())
        self.assertEqual(record["status"], "FAIL")
        self.assertEqual(record["code"], "actual_image_fixture_failed")
        self.assertNotIn("frames", record)
        self.assertNotIn("exception_message", record)
        return record, private

    def test_individual_launch_operands_are_preserved_without_inferred_cause(self):
        for result, captured, engines in ((1, 1, 1), (0, 0, 1), (0, 1, 0),
                                          (0, 2, 1), (0, 1, 2), (1, 0, 0)):
            with self.subTest(result=result, captured=captured, engines=engines):
                launcher = self.launcher(lambda _launcher, _argv: result)
                failure, private = self.invoke(launcher, [None] * captured, [None] * engines)
                expected = {"result": result, "captured": captured, "engine_calls": engines,
                            "first_exception_class": None}
                self.assertEqual(failure.launch_failure, expected)
                self.assertEqual(private["operands"], expected)
                self.assertEqual(private["frames"], [])
                self.assertIsNone(private["exception_message"])

    def test_first_swallowed_fixture_or_native_exception_survives_cleanup_error(self):
        for error_type in (inner.FixtureFailure, TypeError, ModuleNotFoundError):
            with self.subTest(error_type=error_type.__name__):
                def action(launcher, _argv):
                    try:
                        raise error_type("original-launch-cause")
                    except BaseException:
                        launcher.LOGGER.error("sglang38_file_auth_launch_failed")
                    try:
                        raise RuntimeError("later-cleanup-cause")
                    except BaseException:
                        launcher.LOGGER.error("sglang38_file_auth_cleanup_failed")
                    return 1

                launcher = self.launcher(action)
                failure, private = self.invoke(launcher, [], [None])
                self.assertEqual(failure.launch_failure["first_exception_class"], error_type.__name__)
                self.assertEqual(private["exception_message"], "original-launch-cause")
                self.assertEqual(launcher.LOGGER.error.call_count, 2)
                self.assertTrue(any(frame["function"] == "action" for frame in private["frames"]))

    def test_swallowed_error_cannot_pass_even_if_all_original_operands_pass(self):
        def action(launcher, _argv):
            try:
                raise inner.FixtureFailure("callback-failed")
            except Exception:
                launcher.LOGGER.error("sglang38_file_auth_launch_failed")
            return 0

        failure, _ = self.invoke(self.launcher(action), [None], [None])
        self.assertEqual(failure.launch_failure, {
            "result": 0, "captured": 1, "engine_calls": 1,
            "first_exception_class": "FixtureFailure"})

    def test_escaped_errors_including_system_exit_zero_retain_cli_failure(self):
        for error in (RuntimeError("native-failure"), SystemExit(0), KeyboardInterrupt()):
            with self.subTest(error_type=type(error).__name__):
                def action(_launcher, _argv):
                    raise error

                failure, _ = self.invoke(self.launcher(action), [None], [None])
                self.assertIs(failure.__cause__, error)
                self.assertEqual(failure.launch_failure, {
                    "result": None, "captured": 1, "engine_calls": 1,
                    "first_exception_class": type(error).__name__})

    def test_success_returns_zero_without_private_diagnostic_and_restores_logger(self):
        launcher = self.launcher(lambda _launcher, _argv: 0)
        original = launcher.LOGGER.error
        with patch.object(inner.os, "write") as private:
            result = inner.checked_launch(launcher, [], [None], [None], SYNTHETIC_SENTINEL)
        self.assertEqual(result, 0)
        private.assert_not_called()
        self.assertIs(launcher.LOGGER.error, original)

    def test_private_failure_is_source_bound_bounded_and_excludes_context_dumps(self):
        local_canary = "Q38NEXT_LOCAL_CONTEXT_NOT_FOR_CAPTURE"
        environment_canary = "Q38NEXT_ENVIRONMENT_NOT_FOR_CAPTURE"

        def action(_launcher, _argv):
            keep_local = local_canary
            self.assertTrue(keep_local)
            raise TypeError("synthetic native error " + SYNTHETIC_SENTINEL + "x" * 20000)

        with patch.dict(inner.os.environ, {"Q38NEXT_TEST_CANARY": environment_canary}):
            failure, private = self.invoke(self.launcher(action), [], [None])
        self.assertEqual(set(private), {"marker", "source_revision", "fixture_sha256",
                                       "launcher_sha256", "operands", "frames", "exception_message"})
        self.assertEqual(private["marker"], "Q38NEXT_PRIVATE_LAUNCH_FAILURE")
        self.assertEqual(private["source_revision"], inner.SOURCE_REVISION)
        self.assertEqual(private["fixture_sha256"], hashlib.sha256(Path(inner.__file__).read_bytes()).hexdigest())
        self.assertEqual(private["launcher_sha256"], hashlib.sha256(LAUNCHER_SOURCE.read_bytes()).hexdigest())
        self.assertLessEqual(len(private["exception_message"]), 4096)
        self.assertLessEqual(len(private["frames"]), 32)
        for frame in private["frames"]:
            self.assertEqual(set(frame), {"filename", "function", "line"})
            self.assertEqual(Path(frame["filename"]).name, frame["filename"])
            self.assertIs(type(frame["line"]), int)
        rendered = json.dumps(private)
        self.assertTrue(local_canary not in rendered, "locals were inspected")
        self.assertTrue(environment_canary not in rendered, "environment was inspected")
        self.assertNotIn("raise TypeError", rendered)
        self.assertEqual(private["operands"], failure.launch_failure)

    def test_private_message_redacts_synthetic_sentinel_before_json_escaping(self):
        sentinel = 'Q38NEXT_SYNTHETIC_"\\_ONLY'

        def action(_launcher, _argv):
            raise TypeError("native error " + sentinel)

        _, private = self.invoke(self.launcher(action), [], [], sentinel)
        self.assertTrue(sentinel not in private["exception_message"],
                        "escaped synthetic diagnostic content disclosed")
        self.assertIn("<synthetic-key-redacted>", private["exception_message"])

    def test_broken_private_stderr_still_returns_cli_two_and_safe_failure(self):
        launcher = self.launcher(lambda _launcher, _argv: 1)
        record, private = self.main_output(
            lambda *_args: inner.checked_launch(launcher, [], [], [None], SYNTHETIC_SENTINEL),
            diagnostic_failure=OSError("private-stderr-unavailable"))
        self.assertEqual(private.call_count, 1)
        self.assertEqual(record["launch_failure"], {
            "result": 1, "captured": 0, "engine_calls": 1, "first_exception_class": None})
        self.assertEqual(host.failure_metadata(json.dumps(record).encode())["launch_failure"],
                         record["launch_failure"])

    def test_private_rendering_baseexception_preserves_original_failure_and_cli_two(self):
        for diagnostic_error in (SystemExit(0), KeyboardInterrupt()):
            with self.subTest(diagnostic_error=type(diagnostic_error).__name__):
                class DiagnosticHostileError(RuntimeError):
                    def __str__(self):
                        raise diagnostic_error

                def action(launcher, _argv):
                    try:
                        raise DiagnosticHostileError()
                    except RuntimeError:
                        launcher.LOGGER.error("sglang38_file_auth_launch_failed")
                    return 1

                launcher = self.launcher(action)
                record, private = self.main_output(
                    lambda *_args: inner.checked_launch(launcher, [], [], [None], SYNTHETIC_SENTINEL))
                private.assert_not_called()
                # The original unallowlisted native subclass maps to OTHER;
                # the diagnostic SystemExit/KeyboardInterrupt must not replace it.
                self.assertEqual(record["launch_failure"], {
                    "result": 1, "captured": 0, "engine_calls": 1,
                    "first_exception_class": "OTHER"})
                self.assertEqual(record["failure_origin"]["exception_class"], "FixtureFailure")

    def test_private_write_baseexception_preserves_cli_two_and_safe_operands(self):
        for diagnostic_error in (SystemExit(0), KeyboardInterrupt()):
            with self.subTest(diagnostic_error=type(diagnostic_error).__name__):
                launcher = self.launcher(lambda _launcher, _argv: 1)
                record, private = self.main_output(
                    lambda *_args: inner.checked_launch(launcher, [], [], [None], SYNTHETIC_SENTINEL),
                    diagnostic_failure=diagnostic_error)
                self.assertEqual(private.call_count, 1)
                self.assertEqual(record["launch_failure"], {
                    "result": 1, "captured": 0, "engine_calls": 1,
                    "first_exception_class": None})

    def test_broken_metadata_import_cannot_escape_cli_two_or_structured_failure(self):
        launcher = self.launcher(lambda _launcher, _argv: 1)
        with patch.object(inner.importlib.util, "spec_from_file_location",
                          side_effect=ImportError("diagnostic-import-unavailable")):
            record, _ = self.main_output(
                lambda *_args: inner.checked_launch(launcher, [], [], [], SYNTHETIC_SENTINEL))
        self.assertNotIn("launch_failure", record)

    def test_broken_metadata_parser_cannot_escape_cli_two_or_structured_failure(self):
        launcher = self.launcher(lambda _launcher, _argv: 1)
        broken_host = SimpleNamespace(failure_metadata=Mock(side_effect=ValueError("diagnostic-parser-failed")))
        with patch.object(inner.importlib.util, "module_from_spec", return_value=broken_host), \
                patch.object(inner.importlib.util, "spec_from_file_location",
                             return_value=SimpleNamespace(loader=SimpleNamespace(exec_module=Mock()))):
            record, _ = self.main_output(
                lambda *_args: inner.checked_launch(launcher, [], [], [], SYNTHETIC_SENTINEL))
        self.assertNotIn("launch_failure", record)

    def test_metadata_import_baseexception_preserves_cli_two_and_structured_failure(self):
        for diagnostic_error in (SystemExit(0), KeyboardInterrupt()):
            with self.subTest(diagnostic_error=type(diagnostic_error).__name__):
                launcher = self.launcher(lambda _launcher, _argv: 1)
                with patch.object(inner.importlib.util, "spec_from_file_location",
                                  side_effect=diagnostic_error):
                    record, _ = self.main_output(
                        lambda *_args: inner.checked_launch(launcher, [], [], [], SYNTHETIC_SENTINEL))
                self.assertNotIn("launch_failure", record)
                self.assertEqual(record["failure_origin"]["exception_class"], "FixtureFailure")

    def test_metadata_parser_baseexception_preserves_cli_two_and_structured_failure(self):
        for diagnostic_error in (SystemExit(0), KeyboardInterrupt()):
            with self.subTest(diagnostic_error=type(diagnostic_error).__name__):
                launcher = self.launcher(lambda _launcher, _argv: 1)
                broken_host = SimpleNamespace(failure_metadata=Mock(side_effect=diagnostic_error))
                with patch.object(inner.importlib.util, "module_from_spec", return_value=broken_host), \
                        patch.object(inner.importlib.util, "spec_from_file_location",
                                     return_value=SimpleNamespace(loader=SimpleNamespace(exec_module=Mock()))):
                    record, _ = self.main_output(
                        lambda *_args: inner.checked_launch(launcher, [], [], [], SYNTHETIC_SENTINEL))
                self.assertNotIn("launch_failure", record)
                self.assertEqual(record["failure_origin"]["exception_class"], "FixtureFailure")

    def test_normal_help_exits_zero_before_launch_without_failure_diagnostic(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(inner, "run_actual") as launch, \
                patch.object(inner.os, "write") as private, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = inner.main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("--actual-image", stdout.getvalue())
        self.assertNotIn('"status": "FAIL"', stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        launch.assert_not_called()
        private.assert_not_called()

    def test_unexpected_launch_system_exit_zero_is_structured_cli_two_failure(self):
        record, private = self.main_output(SystemExit(0))
        self.assertNotIn("launch_failure", record)
        private.assert_not_called()
        self.assertEqual(record["failure_origin"]["exception_class"], "SystemExit")
        self.assertEqual(record["failure_origin"]["filename"], "run_pinned_image.py")

    def test_host_accepts_closed_safe_operands_without_treating_them_as_success(self):
        for result, captured, engines, kind in ((None, 0, 0, None), (0, 1, 1, None),
                                               (1, 0, 1, "FixtureFailure"),
                                               (-9, 2, 0, "TypeError"), (255, 100000, 0, "OTHER")):
            with self.subTest(result=result, captured=captured, engines=engines, kind=kind):
                record = launch_record(result=result, captured=captured, engine_calls=engines,
                                       first_exception_class=kind)
                parsed = host.failure_metadata(json.dumps(record).encode())
                self.assertEqual(parsed["status"], "SAFE_ORIGIN")
                self.assertEqual(parsed["launch_failure"], record["launch_failure"])
                parsed["launch_failure"]["result"] = 99
                self.assertEqual(record["launch_failure"]["result"], result)
                with self.assertRaises(host.FixtureError):
                    host.check_native_result(record, {}, 131072)

    def test_host_rejects_wrong_operand_types_ranges_classes_and_fields(self):
        changes = []
        for value in (False, True, 1.0, "1", [], {}, -256, 256):
            changes.append({"result": value})
        for name in ("captured", "engine_calls"):
            for value in (False, True, 1.0, "1", None, [], {}, -1, 100001):
                changes.append({name: value})
        for value in (False, 1, [], {}, "UntrustedNativeClass", SYNTHETIC_SENTINEL):
            changes.append({"first_exception_class": value})
        for change in changes:
            with self.subTest(field=next(iter(change))):
                self.assertEqual(host.failure_metadata(json.dumps(launch_record(**change)).encode()),
                                 {"status": "REJECTED_OR_UNAVAILABLE"})
        for field in tuple(launch_record()["launch_failure"]):
            record = launch_record()
            del record["launch_failure"][field]
            self.assertEqual(host.failure_metadata(json.dumps(record).encode()),
                             {"status": "REJECTED_OR_UNAVAILABLE"})
        for value in (None, [], "untrusted", {**launch_record()["launch_failure"], "message": SYNTHETIC_SENTINEL}):
            record = launch_record()
            record["launch_failure"] = value
            self.assertEqual(host.failure_metadata(json.dumps(record).encode()),
                             {"status": "REJECTED_OR_UNAVAILABLE"})

    def test_host_rejects_duplicate_nonfinite_extra_truncated_and_untrusted_text(self):
        valid = json.dumps(launch_record()).encode()
        extra = copy.deepcopy(launch_record())
        extra["private_trace"] = SYNTHETIC_SENTINEL
        malformed = (valid[:-1], b"log prefix " + valid, valid + b" trailing",
                     valid.replace(b'"result": 1', b'"result": 1, "result": 0'),
                     valid.replace(b'"result": 1', b'"result": NaN'),
                     valid.replace(b'"result": 1', b'"result": Infinity'),
                     json.dumps(extra).encode(), b"x" * 4097, valid.decode())
        for value in malformed:
            with self.subTest(kind=type(value).__name__):
                self.assertEqual(host.failure_metadata(value), {"status": "REJECTED_OR_UNAVAILABLE"})

    def test_failed_cli_with_safe_operands_stays_failure_and_private_stderr_is_hash_only(self):
        public = json.dumps(launch_record(result=0, captured=1, engine_calls=1,
                                        first_exception_class=None)).encode()
        private = ("private native trace " + SYNTHETIC_SENTINEL).encode()
        _, evidence = diagnostic_tests.Qwen38FixtureDiagnosticTests().failure(
            stdout=public, stderr=private, code=2, native_exit=2)
        diagnostic = evidence["attach_diagnostic"]
        self.assertEqual(evidence["outcome"], "ATTACH_FAILED")
        self.assertEqual(diagnostic["failure_kind"], "CLI_NONZERO_EXIT")
        self.assertEqual(diagnostic["cli_returncode"], 2)
        self.assertEqual(diagnostic["failure_metadata"]["launch_failure"],
                         json.loads(public)["launch_failure"])
        self.assertEqual(diagnostic["stderr"], {"capture": "COMPLETE",
                         "captured_bytes": len(private), "sha256": hashlib.sha256(private).hexdigest()})
        self.assertTrue(SYNTHETIC_SENTINEL not in json.dumps(evidence),
                        "private stream escaped hash-only evidence")


if __name__ == "__main__":
    unittest.main()
