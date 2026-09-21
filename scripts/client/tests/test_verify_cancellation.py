"""Real ordinary-cancellation cleanup regressions; no native client or model."""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))
import verify


HARNESS = r'''
import json, os, signal, sys
from pathlib import Path
from unittest import mock
sys.path.insert(0, sys.argv[1])
import verify
import verify_events
root = Path(sys.argv[2])
mode = sys.argv[3]
def original(signum, frame):
    (root / "unexpected-original-handler").write_text(str(signum))
for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
    signal.signal(sig, original)
settings = {"auth": {"kind": "env", "reference": "V2R_SYNTHETIC_UNUSED"},
            "base_url": "http://127.0.0.1:1/v1", "model": "synthetic"}
env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
bounded = verify.run_bounded
snapshot = verify_events._process_snapshot
cancellation_handler = verify.Cancellation.__call__
observations = 0
def cancelled(self, signum, frame):
    try:
        return cancellation_handler(self, signum, frame)
    finally:
        if self.signum is not None:
            (root / "cancellation-latched").touch()
def observed():
    global observations
    result = snapshot()
    # The second ancestry observation after readiness follows an output-read
    # iteration. The controller thus waits on actual supervisor progress.
    if (root / "ready").exists():
        observations += 1
        if observations >= 2:
            (root / "captured-ready").touch()
    return result
def execute(argv, workspace, child_env, **kwargs):
    if "run" in argv:
        kwargs.pop("input", None)
        kwargs["timeout"] = 0.6 if mode == "timeout-cleanup" else 10
        return bounded([sys.executable, "-I", "-B", str(root / "owned.py"), str(root)],
                       workspace, child_env, **kwargs)
    return bounded(argv, workspace, child_env, **kwargs)
with mock.patch.object(verify, "verify_client", return_value=(settings, {})), \
     mock.patch.object(verify, "versions", return_value={}), \
     mock.patch.object(verify, "isolated_env", return_value=env), \
     mock.patch.object(verify, "load_key", return_value="synthetic-unused"), \
     mock.patch.object(verify, "observe_model", return_value="synthetic"), \
     mock.patch.object(verify, "run_bounded", side_effect=execute), \
     mock.patch.object(verify.Cancellation, "__call__", cancelled), \
     mock.patch.object(verify_events, "_process_snapshot", side_effect=observed):
    report = verify.verify(root / "prefix", root / "output", 15)
(root / "restored.json").write_text(json.dumps({
    "handlers": all(signal.getsignal(sig) is original for sig in
                    (signal.SIGTERM, signal.SIGHUP, signal.SIGALRM)),
    "timer": signal.getitimer(signal.ITIMER_REAL),
    "status": report["status"],
}))
sys.exit(0 if report["status"] == "PASS" else 1)
'''

OWNED = r'''
import os, signal, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[1])
def ignore_term(signum, frame):
    (root / "cleanup-started").touch()
signal.signal(signal.SIGTERM, ignore_term)
(root / "owned-pid").write_text(str(os.getpid()))
child = subprocess.Popen([sys.executable, "-I", "-B", str(root / "descendant.py"), str(root)])
while not (root / "descendant-pid").exists():
    time.sleep(.005)
os.write(1, b'{"type":"step_start","private":"cancelled output"}\n')
os.write(2, b'private cancellation diagnostic\n')
(root / "ready").touch()
time.sleep(60)
'''

DESCENDANT = r'''
import os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
(Path(sys.argv[1]) / "descendant-pid").write_text(str(os.getpid()))
time.sleep(60)
'''


@unittest.skipUnless(os.name == "posix" and os.getuid() > 0,
                     "POSIX ordinary-user verifier cancellation contract")
class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.home().resolve(), prefix="v2r-cancellation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def wait_for(self, path, process, timeout=5):
        deadline = time.monotonic() + timeout
        while not path.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail("Verifier exited before " + path.name + ": " + repr((stdout, stderr)))
            if time.monotonic() >= deadline:
                self.fail("No bounded readiness marker: " + path.name)
            time.sleep(.005)

    def cancellation_case(self, first_signal, *, mode="running"):
        root = self.root / (mode + "-" + signal.Signals(first_signal).name)
        root.mkdir(mode=0o700)
        (root / "prefix").mkdir(mode=0o700)
        for name, content in (("harness.py", HARNESS), ("owned.py", OWNED),
                              ("descendant.py", DESCENDANT)):
            (root / name).write_text(content)
        process = subprocess.Popen([sys.executable, "-I", "-B", str(root / "harness.py"),
                                    str(CLIENT), str(root), mode], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            self.wait_for(root / "captured-ready", process)
            if mode == "timeout-cleanup":
                # The child has already received the supervisor's TERM. First
                # cancellation now must not interrupt an existing finally.
                self.wait_for(root / "cleanup-started", process)
            started = time.monotonic()
            os.kill(process.pid, first_signal)
            self.wait_for(root / "cancellation-latched", process)
            self.wait_for(root / "cleanup-started", process)
            for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGHUP, signal.SIGTERM):
                os.kill(process.pid, sig)
                time.sleep(.02)
            stdout, stderr = process.communicate(timeout=6)
            self.assertEqual(process.returncode, 1, (stdout, stderr))
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, b"")
            report_path = root / "output/report.json"
            raw_path = root / "output/raw-evidence.json"
            report = json.loads(report_path.read_bytes())
            raw = json.loads(raw_path.read_bytes())
            expected_signal = signal.Signals(first_signal).name
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["cancellation_signal"], expected_signal)
            self.assertIn("cancelled_" + expected_signal.lower(), report["failures"])
            self.assertEqual(report["phase"], "opencode_agent")
            self.assertTrue(report["process"]["process_tree_reaped"])
            self.assertTrue(raw["opencode"]["process_tree_reaped"])
            self.assertEqual(raw["opencode"]["cancelled_signal"], expected_signal)
            self.assertEqual(raw["opencode"]["timed_out"], mode == "timeout-cleanup")
            self.assertEqual(raw["opencode"]["stdout"],
                             '{"type":"step_start","private":"cancelled output"}\n')
            self.assertEqual(raw["opencode"]["stderr"], "private cancellation diagnostic\n")
            self.assertEqual(report["raw_evidence_sha256"], hashlib.sha256(raw_path.read_bytes()).hexdigest())
            self.assertEqual(json.loads((root / "restored.json").read_bytes()),
                             {"handlers": True, "timer": [0.0, 0.0], "status": "FAIL"})
            self.assertFalse((root / "unexpected-original-handler").exists())
            self.assertFalse((root / "output/receipt.json").exists())
            for path in (report_path, raw_path):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for name in ("owned-pid", "descendant-pid"):
                with self.assertRaises(ProcessLookupError):
                    os.kill(int((root / name).read_text()), 0)
            with self.assertRaises(ProcessLookupError):
                os.killpg(int((root / "owned-pid").read_text()), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)
            # Failure-only cleanup is confined to the fresh child session this
            # regression owns; never enumerate or terminate unrelated PIDs.
            pid_path = root / "owned-pid"
            if pid_path.exists():
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(int(pid_path.read_text()), signal.SIGKILL)

    def test_repeated_term_and_hup_reap_real_owned_tree(self):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(first_signal=signal.Signals(sig).name):
                self.cancellation_case(sig)

    def test_first_cancellation_during_timeout_cleanup_preserves_diagnostics(self):
        self.cancellation_case(signal.SIGTERM, mode="timeout-cleanup")

    def test_cancellation_outside_process_writes_failed_report_and_restores_handlers(self):
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGALRM)}
        def cancel(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGHUP)
        with mock.patch.object(verify, "verify_client", side_effect=cancel):
            report = verify.verify(prefix, self.root / "outside", 10)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["cancellation_signal"], "SIGHUP")
        self.assertIn("cancelled_sighup", report["failures"])
        self.assertEqual(json.loads((self.root / "outside/raw-evidence.json").read_bytes()), {})
        for sig, handler in previous.items():
            self.assertEqual(signal.getsignal(sig), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_artifact_cancellation_and_write_error_restore_original_handlers(self):
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGALRM)}
        original_write = verify.write_new
        for failure in (False, True):
            with self.subTest(write_failure=failure):
                def write(path, data):
                    if path.name == "raw-evidence.json":
                        os.kill(os.getpid(), signal.SIGTERM)
                        os.kill(os.getpid(), signal.SIGHUP)
                        if failure:
                            raise OSError("synthetic artifact failure")
                    return original_write(path, data)
                with mock.patch.object(verify, "verify_client", side_effect=ValueError("synthetic refusal")), \
                     mock.patch.object(verify, "write_new", side_effect=write):
                    if failure:
                        with self.assertRaises(OSError):
                            verify.verify(prefix, self.root / "artifact-error", 10)
                    else:
                        report = verify.verify(prefix, self.root / "artifact-cancel", 10)
                        self.assertEqual(report["status"], "FAIL")
                        self.assertEqual(report["cancellation_signal"], "SIGTERM")
                        self.assertIn("cancelled_sigterm", report["failures"])
                for sig, handler in previous.items():
                    self.assertEqual(signal.getsignal(sig), handler)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_first_cancellation_during_final_report_write_replaces_serialized_pass(self):
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        output = self.root / "report-write"
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGALRM)}
        settings = {"auth": {"kind": "env", "reference": "V2R_SYNTHETIC_UNUSED"},
                    "base_url": "http://127.0.0.1:1/v1", "model": "synthetic"}
        result = {"stdout": b"", "stderr": b"Ran 3 tests in 0.001s\nOK\n", "exit_code": 0,
                  "timed_out": False, "output_limited": False, "process_tree_reaped": True}
        calls, serialized_statuses = [], []
        original_write = verify.write_new
        def execute(argv, workspace, *args, **kwargs):
            calls.append(argv)
            if len(calls) == 1:
                return dict(result, stderr=b"Ran 3 tests in 0.001s\nFAILED (failures=5)\n", exit_code=1)
            if len(calls) == 2:
                (workspace / "text_utils.py").write_text("def word_count(text):\n    return len(text.split())\n")
            return dict(result)
        def write(path, data):
            if path.name == "report.json":
                serialized_statuses.append(json.loads(data)["status"])
                if len(serialized_statuses) == 1:
                    os.kill(os.getpid(), signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGHUP)
            return original_write(path, data)
        native = {"checks": {name: True for name in ("file_reads", "implementation_edit", "exact_test_command",
                                                      "passing_tool_result", "final_response")},
                  "failures": [], "result": "pass"}
        with mock.patch.object(verify, "verify_client", return_value=(settings, {})), \
             mock.patch.object(verify, "versions", return_value={}), \
             mock.patch.object(verify, "load_key", return_value="synthetic-unused"), \
             mock.patch.object(verify, "observe_model", return_value="synthetic"), \
             mock.patch.object(verify, "run_bounded", side_effect=execute), \
             mock.patch.object(verify, "parse_events", return_value=native), \
             mock.patch.object(verify, "write_new", side_effect=write):
            report = verify.verify(prefix, output, 10)
        self.assertEqual(serialized_statuses, ["PASS", "FAIL"])
        saved = json.loads((output / "report.json").read_bytes())
        self.assertEqual(saved, report)
        self.assertEqual(saved["status"], "FAIL")
        self.assertEqual(saved["cancellation_signal"], "SIGTERM")
        self.assertIn("cancelled_sigterm", saved["failures"])
        self.assertEqual(saved["raw_evidence_sha256"],
                         hashlib.sha256((output / "raw-evidence.json").read_bytes()).hexdigest())
        for sig, handler in previous.items():
            self.assertEqual(signal.getsignal(sig), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
