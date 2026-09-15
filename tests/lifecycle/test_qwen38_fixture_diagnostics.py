"""Source-only attach diagnostics: fake Docker plus bounded local CLI helpers."""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.lifecycle import test_qwen38_fixture_lifetime as lifetime_tests
from tests.lifecycle.test_qwen38_fixture_lifetime import (
    DockerDaemon, OWN_ID, SENTINEL_ID, host, response,
)


class Qwen38FixtureDiagnosticTests(unittest.TestCase):
    def failure(self, *, stdout=b"", stderr=b"", code=1, native_exit=None,
                error=None, daemon=None):
        daemon = DockerDaemon() if daemon is None else daemon

        def docker(command, *, timeout):
            if command[1:3] != ["container", "start"]:
                return daemon(command, timeout=timeout)
            daemon.calls.append((command, timeout))
            daemon.attached = True
            daemon.objects[OWN_ID]["State"].update(
                Running=native_exit is None, Pid=100 if native_exit is None else 0,
                Status="running" if native_exit is None else "exited",
                ExitCode=0 if native_exit is None else native_exit)
            if error is not None:
                raise error
            return response(command, code, stdout, stderr)

        with self.assertRaises(host.LifetimeFailure) as caught:
            host.run_disposable_fixture(Path("/reviewed"), {}, 131072, docker=docker)
        evidence = caught.exception.evidence
        self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
        mutations = [cmd for cmd, _ in daemon.calls
                     if cmd[1:3] in (["container", "stop"], ["container", "rm"])]
        self.assertTrue(all(cmd[-1] == OWN_ID and "--force" not in cmd for cmd in mutations))
        self.assertEqual(evidence["container_id"], OWN_ID)
        self.assertEqual(evidence["attach_diagnostic"]["schema_version"], 1)
        self.assertEqual(evidence["attach_diagnostic"]["phase"], "ATTACH")
        self.assertNotEqual(evidence["outcome"], "FIXTURE_EXITED")
        return daemon, evidence

    def assert_redacted(self, evidence, *sensitive):
        rendered = json.dumps(evidence, sort_keys=True)
        for value in sensitive:
            self.assertTrue(value not in rendered, "sensitive diagnostic content escaped")

    def assert_stream(self, diagnostic, name, content, capture="COMPLETE"):
        self.assertEqual(diagnostic[name], {
            "capture": capture, "captured_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })

    def safe_record(self, **origin_changes):
        origin = {"filename": "run_pinned_image.py", "line": 147,
                  "exception_class": "ModuleNotFoundError"}
        origin.update(origin_changes)
        return {"status": "FAIL", "code": "actual_image_fixture_failed",
                "failure_origin": origin}

    def test_nonzero_raw_secret_output_is_hashed_and_owned_running_container_removed(self):
        synthetic = secrets.token_urlsafe(24)
        raw_path = "/untrusted/" + synthetic + "/module.py"
        stdout = ("raw child stdout " + synthetic + "\n").encode()
        stderr = ("Authorization: " + synthetic + "\nFile " + raw_path + "\n").encode()
        daemon, evidence = self.failure(stdout=stdout, stderr=stderr, code=17)
        self.assert_redacted(evidence, synthetic, raw_path, "Authorization", "raw child stdout")
        diagnostic = evidence["attach_diagnostic"]
        self.assertEqual(evidence["outcome"], "ATTACH_FAILED")
        self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertNotIn(OWN_ID, daemon.objects)
        self.assertEqual([cmd[2] for cmd, _ in daemon.calls
                          if cmd[1:3] in (["container", "stop"], ["container", "rm"])],
                         ["stop", "rm"])
        self.assertEqual(diagnostic["failure_kind"], "CLI_NONZERO_EXIT")
        self.assertEqual(diagnostic["operation"], "START_ATTACH")
        self.assertEqual(diagnostic["cli_returncode"], 17)
        self.assertIsNone(diagnostic["cli_signal"])
        self.assertEqual(diagnostic["container_before_cleanup_stop"], {
            "status": "EXIT_NOT_OBSERVED", "exit_code": None, "signal": None})
        self.assertEqual(diagnostic["failure_metadata"]["status"], "REJECTED_OR_UNAVAILABLE")
        self.assert_stream(diagnostic, "stdout", stdout)
        self.assert_stream(diagnostic, "stderr", stderr)

    def test_safe_origin_survives_native_nonzero_without_admitting_raw_stderr(self):
        synthetic = secrets.token_urlsafe(24)
        stdout = json.dumps(self.safe_record()).encode()
        stderr = ("traceback message locals " + synthetic).encode()
        daemon, evidence = self.failure(stdout=stdout, stderr=stderr, code=1, native_exit=1)
        self.assert_redacted(evidence, synthetic, "traceback message locals")
        diagnostic = evidence["attach_diagnostic"]
        self.assertEqual(diagnostic["failure_metadata"], {
            "status": "SAFE_ORIGIN", "code": "actual_image_fixture_failed",
            "origin": self.safe_record()["failure_origin"]})
        self.assertEqual(diagnostic["container_before_cleanup_stop"], {
            "status": "EXITED", "exit_code": 1, "signal": None})
        self.assertEqual(evidence["outcome"], "ATTACH_FAILED")
        self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertNotIn(OWN_ID, daemon.objects)
        self.assertFalse(any(cmd[1:3] == ["container", "stop"] for cmd, _ in daemon.calls))
        self.assert_stream(diagnostic, "stderr", stderr)

    def test_cli_signal_and_native_exit_are_independent_observations(self):
        for native_exit in (None, 137):
            with self.subTest(native_exit=native_exit):
                _, evidence = self.failure(code=-9, native_exit=native_exit)
                diagnostic = evidence["attach_diagnostic"]
                self.assertEqual(diagnostic["cli_returncode"], -9)
                self.assertEqual(diagnostic["cli_signal"], 9)
                self.assertEqual(diagnostic["failure_kind"], "CLI_NONZERO_EXIT")
                self.assertEqual(diagnostic["container_before_cleanup_stop"], {
                    "status": "EXIT_NOT_OBSERVED" if native_exit is None else "EXITED",
                    "exit_code": native_exit, "signal": None})

    def test_cli_zero_does_not_hide_unverified_or_failed_native_exit(self):
        for native_exit in (None, 2):
            with self.subTest(native_exit=native_exit):
                _, evidence = self.failure(code=0, native_exit=native_exit,
                                           stdout=json.dumps(self.safe_record()).encode())
                self.assertEqual(evidence["outcome"], "ATTACH_FAILED")
                self.assertEqual(evidence["attach_diagnostic"]["failure_kind"],
                                 "CONTAINER_EXIT_UNVERIFIED")
                self.assertEqual(evidence["attach_diagnostic"]["cli_returncode"], 0)

    def test_parser_accepts_only_fixed_failure_or_allowlisted_origin(self):
        fixed = {"status": "FAIL", "code": "actual_image_fixture_failed"}
        for record in (fixed, {**fixed, "failure_origin": None}):
            self.assertEqual(host.failure_metadata(json.dumps(record).encode()), {
                "status": "FIXED_FAILURE_ONLY", "code": "actual_image_fixture_failed"})
        for line in (1, 100000):
            result = host.failure_metadata(json.dumps(self.safe_record(line=line)).encode())
            self.assertEqual(result["status"], "SAFE_ORIGIN")
            self.assertEqual(result["origin"]["line"], line)

    def test_parser_rejects_malicious_invalid_truncated_nested_and_extra_output(self):
        synthetic = secrets.token_urlsafe(24)
        valid = json.dumps(self.safe_record()).encode()
        invalid = [
            b"", b"\xff", b"[]", valid[:-1], valid + valid, b"log prefix\n" + valid,
            b" " * 4097, b"[" * 2048 + b"]" * 2048,
            valid.decode(), bytearray(valid),
            json.dumps({**self.safe_record(), "message": synthetic}).encode(),
            json.dumps({**self.safe_record(), "status": "PASS"}).encode(),
            json.dumps({**self.safe_record(), "code": synthetic}).encode(),
            json.dumps(self.safe_record(filename="/untrusted/run_pinned_image.py")).encode(),
            json.dumps(self.safe_record(exception_class=synthetic)).encode(),
            json.dumps(self.safe_record(message=synthetic)).encode(),
            b'{"status":"FAIL","status":"FAIL","code":"actual_image_fixture_failed"}',
            valid.replace(b'"line": 147', b'"line": 147, "line": 147'),
            ("Traceback (most recent call last):\n  File /untrusted/module.py, line 12\n"
             "ValueError: " + synthetic).encode(),
        ]
        for value in (True, False, 0, -1, 100001, 1.5, "147", None, [], {"line": 147}):
            invalid.append(json.dumps(self.safe_record(line=value)).encode())
        for index, raw in enumerate(invalid):
            with self.subTest(case=index):
                result = host.failure_metadata(raw)
                self.assert_redacted(result, synthetic, "/untrusted")
                self.assertEqual(result, {"status": "REJECTED_OR_UNAVAILABLE"})

    def test_bounded_capture_rejects_invalid_returncodes_and_oversized_streams(self):
        for code in (True, False, -65, 256, "17", 1.5):
            with self.subTest(code=code):
                result = host.capture_diagnostic(b"", b"", code, complete=True)
                self.assertIsNone(result["cli_returncode"])
                self.assertIsNone(result["cli_signal"])
        result = host.capture_diagnostic(b"x" * 131073, "untrusted", complete=True)
        for name in ("stdout", "stderr"):
            self.assertEqual(result[name], {
                "capture": "UNAVAILABLE", "captured_bytes": None, "sha256": None})

    def test_timeout_exception_and_cancellation_are_precise_redacted_failures(self):
        synthetic = secrets.token_urlsafe(24)
        errors = [
            (subprocess.TimeoutExpired([synthetic], 1, output=synthetic.encode(),
                                       stderr=synthetic.encode()), "TIMEOUT", "ATTACH_TIMEOUT"),
            (OSError(synthetic), "CLI_EXCEPTION", "ATTACH_FAILED"),
            (KeyboardInterrupt(synthetic), "CANCELLED", "CANCELLED"),
        ]
        for error, kind, outcome in errors:
            with self.subTest(kind=kind):
                daemon, evidence = self.failure(error=error)
                self.assert_redacted(evidence, synthetic)
                diagnostic = evidence["attach_diagnostic"]
                self.assertEqual(diagnostic["failure_kind"], kind)
                self.assertEqual(evidence["outcome"], outcome)
                self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
                self.assertNotIn(OWN_ID, daemon.objects)
                self.assertIsNone(diagnostic["cli_returncode"])

    def test_local_cli_timeout_and_overflow_retain_only_bounded_prefix_evidence(self):
        helper = lifetime_tests.Qwen38FixtureLifetimeTests()
        cases = [
            ("import os,time; os.write(1,b'o'); os.write(2,b'e'); time.sleep(20)",
             0.3, "TIMEOUT"),
            ("import os; os.write(1,b'x'*262144)", 5, "OUTPUT_OVERFLOW"),
        ]
        for source, timeout, kind in cases:
            with self.subTest(kind=kind):
                error = helper.capture_local_cli(source, timeout=timeout)
                diagnostic = error.attach_capture
                self.assertEqual(diagnostic["failure_kind"], kind)
                self.assertEqual(diagnostic["cli_reap"], "VERIFIED")
                self.assertEqual(diagnostic["failure_metadata"], {"status": "INCOMPLETE_CAPTURE"})
                self.assertLessEqual(sum(diagnostic[name]["captured_bytes"]
                                         for name in ("stdout", "stderr")), 131072)
                if kind == "TIMEOUT":
                    self.assert_stream(diagnostic, "stdout", b"o", "PREFIX")
                    self.assert_stream(diagnostic, "stderr", b"e", "PREFIX")
                else:
                    self.assert_stream(diagnostic, "stdout", b"x" * 131072, "PREFIX")
                    self.assert_stream(diagnostic, "stderr", b"", "PREFIX")
                daemon, evidence = self.failure(error=error)
                self.assertEqual(evidence["attach_diagnostic"]["failure_kind"], kind)
                self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
                self.assertNotIn(OWN_ID, daemon.objects)

    def test_exit_inspect_exceptions_preserve_completed_attach_capture(self):
        attach_secret = secrets.token_urlsafe(24)
        inspect_secret = secrets.token_urlsafe(24)
        stdout = json.dumps(self.safe_record()).encode()
        stderr = attach_secret.encode()
        errors = [
            (subprocess.TimeoutExpired([inspect_secret], 1, output=inspect_secret.encode()),
             "TIMEOUT", "ATTACH_TIMEOUT"),
            (KeyboardInterrupt(inspect_secret), "CANCELLED", "CANCELLED"),
            (OSError(inspect_secret), "CLI_EXCEPTION", "ATTACH_FAILED"),
        ]
        for error, kind, outcome in errors:
            with self.subTest(kind=kind):
                daemon = DockerDaemon()
                interrupted = False
                error.attach_capture = host.capture_diagnostic(
                    inspect_secret.encode(), inspect_secret.encode())
                error.attach_capture["failure_kind"] = kind

                def docker(command, *, timeout):
                    nonlocal interrupted
                    if command[1:3] == ["container", "inspect"] and daemon.attached and not interrupted:
                        daemon.calls.append((command, timeout))
                        interrupted = True
                        raise error
                    result = daemon(command, timeout=timeout)
                    if command[1:3] == ["container", "start"]:
                        return response(command, 0, stdout, stderr)
                    return result

                with self.assertRaises(host.LifetimeFailure) as caught:
                    host.run_disposable_fixture(Path("/reviewed"), {}, 131072, docker=docker)
                evidence = caught.exception.evidence
                self.assert_redacted(evidence, attach_secret, inspect_secret)
                diagnostic = evidence["attach_diagnostic"]
                self.assertTrue(interrupted)
                self.assertEqual(diagnostic["operation"], "VERIFY_CONTAINER_EXIT")
                self.assertEqual(diagnostic["failure_kind"], kind)
                self.assertEqual(diagnostic["cli_returncode"], 0)
                self.assertIsNone(diagnostic["cli_signal"])
                self.assert_stream(diagnostic, "stdout", stdout)
                self.assert_stream(diagnostic, "stderr", stderr)
                self.assertEqual(diagnostic["failure_metadata"]["status"], "SAFE_ORIGIN")
                self.assertEqual(evidence["outcome"], outcome)
                self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
                self.assertNotIn(OWN_ID, daemon.objects)
                self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
                mutations = [cmd for cmd, _ in daemon.calls
                             if cmd[1:3] in (["container", "stop"], ["container", "rm"])]
                self.assertEqual(len(mutations), 1)
                self.assertEqual(mutations[0][1:3], ["container", "rm"])
                self.assertEqual(mutations[0][-1], OWN_ID)
                self.assertNotIn("--force", mutations[0])

    def test_cli_reap_timeout_retains_original_redacted_failure_and_prefix(self):
        synthetic = secrets.token_urlsafe(24)
        pipes = [os.pipe(), os.pipe()]
        stdout = synthetic.encode()
        os.write(pipes[0][1], stdout)
        waits, killed = [], []

        def wait(*, timeout):
            waits.append(timeout)
            raise subprocess.TimeoutExpired([synthetic], timeout, output=synthetic.encode())

        child = SimpleNamespace(
            stdout=os.fdopen(pipes[0][0], "rb", buffering=0),
            stderr=os.fdopen(pipes[1][0], "rb", buffering=0),
            poll=lambda: None, kill=lambda: killed.append(True), wait=wait)
        try:
            with patch.object(host.subprocess, "Popen", return_value=child):
                with self.assertRaises(host.FixtureError) as caught:
                    host.docker_call(["controlled-fake-cli"], timeout=0.01)
            diagnostic = caught.exception.attach_capture
            self.assert_redacted(diagnostic, synthetic)
            self.assertEqual(diagnostic["failure_kind"], "TIMEOUT")
            self.assertEqual(diagnostic["cli_reap"], "UNVERIFIED")
            self.assertIsNone(diagnostic["cli_returncode"])
            self.assert_stream(diagnostic, "stdout", stdout, "PREFIX")
            self.assert_stream(diagnostic, "stderr", b"", "PREFIX")
            self.assertEqual(diagnostic["failure_metadata"], {"status": "INCOMPLETE_CAPTURE"})
            self.assertEqual(waits, [host.CLI_DRAIN_TIMEOUT])
            self.assertEqual(killed, [True])
            self.assertTrue(child.stdout.closed and child.stderr.closed)
            daemon, evidence = self.failure(error=caught.exception)
            self.assert_redacted(evidence, synthetic)
            self.assertEqual(evidence["attach_diagnostic"]["failure_kind"], "TIMEOUT")
            self.assertEqual(evidence["attach_diagnostic"]["cli_reap"], "UNVERIFIED")
            self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
            self.assertNotIn(OWN_ID, daemon.objects)
        finally:
            child.stdout.close()
            child.stderr.close()
            for _reader, writer in pipes:
                os.close(writer)

    def test_cleanup_failure_retains_owned_id_and_does_not_remove_running_container(self):
        stdout = json.dumps(self.safe_record()).encode()
        daemon, evidence = self.failure(daemon=DockerDaemon("not_quiescent"), stdout=stdout)
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertTrue(daemon.objects[OWN_ID]["State"]["Running"])
        self.assertEqual(evidence["attach_diagnostic"]["failure_metadata"]["status"], "SAFE_ORIGIN")
        self.assertFalse(any(cmd[1:3] == ["container", "rm"] for cmd, _ in daemon.calls))

    def test_identity_mismatch_preserves_diagnostics_without_arbitrary_deletion(self):
        daemon, evidence = self.failure(daemon=DockerDaemon("mismatch_Id"), code=-9)
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertEqual(evidence["attach_diagnostic"]["cli_signal"], 9)
        self.assertEqual(evidence["attach_diagnostic"]["container_before_cleanup_stop"]["status"],
                         "EXIT_NOT_OBSERVED")
        self.assertFalse(any(cmd[1:3] in (["container", "stop"], ["container", "rm"])
                             for cmd, _ in daemon.calls))

    def test_cleanup_only_failure_retains_successful_cli_capture_without_pass(self):
        daemon = DockerDaemon()

        def docker(command, *, timeout):
            if command[1:3] == ["container", "rm"]:
                daemon.calls.append((command, timeout))
                return response(command, 1)
            return daemon(command, timeout=timeout)

        with self.assertRaises(host.LifetimeFailure) as caught:
            host.run_disposable_fixture(Path("/reviewed"), {}, 131072, docker=docker)
        evidence = caught.exception.evidence
        self.assertEqual(evidence["container_id"], OWN_ID)
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertEqual(evidence["attach_diagnostic"]["failure_kind"], "CLEANUP_UNVERIFIED")
        self.assertEqual(evidence["attach_diagnostic"]["operation"], "CLEANUP")
        self.assertEqual(evidence["attach_diagnostic"]["cli_returncode"], 0)
        self.assert_stream(evidence["attach_diagnostic"], "stdout", b'{"native":"complete"}')
        self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
        self.assertIn(OWN_ID, daemon.objects)
        self.assertTrue(all(cmd[-1] == OWN_ID and "--force" not in cmd
                            for cmd, _ in daemon.calls if cmd[1:3] == ["container", "rm"]))

    def test_diagnostic_in_otherwise_pass_receipt_is_rejected_by_existing_gate(self):
        from tests.lifecycle.test_qwen38 import bound, auth_receipt, q, LifecycleError

        proof, _ = auth_receipt(bound())
        identity = {name: proof[name] for name in (
            "image_id", "image_reference", "source_revision", "launcher_sha256")}
        q._validate_auth_proof(proof, identity)
        _, failure = self.failure(stdout=json.dumps(self.safe_record()).encode(), native_exit=1)
        proof["container_lifetimes"][0]["attach_diagnostic"] = failure["attach_diagnostic"]
        with self.assertRaisesRegex(LifecycleError, "^qwen38_container_lifetime_proof_invalid$"):
            q._validate_auth_proof(proof, identity)

    def test_main_failure_cannot_publish_receipt_or_start_second_context(self):
        synthetic = secrets.token_urlsafe(24)
        _, evidence = self.failure(stdout=json.dumps(self.safe_record()).encode(),
                                   stderr=synthetic.encode(), native_exit=1)
        captured = io.StringIO()
        with patch.object(host, "validate_output_path"), \
                patch.object(host, "read_provenance", return_value=({}, {})), \
                patch.object(host.subprocess, "run", return_value=response([], stdout=b"[]")), \
                patch.object(host, "verify_image", return_value={"image_id": host.IMAGE_ID}), \
                patch.object(host, "run_disposable_fixture", side_effect=host.LifetimeFailure(evidence)) as run, \
                patch.object(host, "check_native_result") as accept, \
                patch.object(host, "write_receipt") as publish, redirect_stdout(captured):
            code = host.main(["--repo", "/reviewed", "--output", "/reviewed/receipt.json"])
        self.assertEqual(code, 1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[2], 131072)
        accept.assert_not_called()
        publish.assert_not_called()
        output = json.loads(captured.getvalue())
        self.assert_redacted(output, synthetic)
        self.assertEqual(output["status"], "FAIL")
        self.assertEqual(output["lifetime"]["attach_diagnostic"]["failure_metadata"]["status"], "SAFE_ORIGIN")


if __name__ == "__main__":
    unittest.main()
