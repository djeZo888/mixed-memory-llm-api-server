"""Worker-only synthetic/native-POSIX process supervision regressions.

These tests execute real disposable local processes and deliver real signals.
The launcher-finally test runs repository launcher.main with explicit worker
ServerArgs/auth/engine/cleanup doubles. No installed SGLang, Uvicorn, CUDA,
model, container, actual-image gate or real inference is exercised here.
"""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/lifecycle/sglang_fixture/run_pinned_image.py"
spec = importlib.util.spec_from_file_location("f1e2_process_helper_control", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
REAL_DISPOSABLE_CHILD = helper.disposable_child
REAL_READ_PROCESS_OUTPUT = helper.read_process_output


def command(code):
    return [sys.executable, "-u", "-c", code]


@unittest.skipUnless(os.name == "posix", "requires owned POSIX process groups")
class PinnedImageProcessTests(unittest.TestCase):
    def assert_gone(self, pid):
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_process_output_collects_both_private_pipes_without_relay(self):
        with helper.disposable_child(command(
                "import os; os.write(1, b'private-out'); os.write(2, b'private-err')")) as child:
            self.assertEqual(helper.read_process_output(child, timeout=2),
                             (b"private-out", b"private-err"))
            self.assertEqual(child.returncode, 0)
        self.assert_gone(child.pid)

    def test_nonready_child_is_refused_and_reaped(self):
        with self.assertRaisesRegex(helper.FixtureFailure, "fixture_child_not_ready"):
            with helper.disposable_child(command("pass")) as child:
                helper.read_process_output(child, until=helper.SIGNAL_READY, timeout=2)
        self.assertTrue(child.stdout.closed and child.stderr.closed)
        self.assert_gone(child.pid)

    def test_deadline_kills_only_owned_child_and_closes_pipes(self):
        started = time.monotonic()
        with self.assertRaisesRegex(helper.FixtureFailure, "fixture_child_deadline"):
            with helper.disposable_child(command("import time; time.sleep(60)")) as child:
                self.assertEqual(os.getpgid(child.pid), child.pid)
                self.assertNotEqual(os.getpgid(child.pid), os.getpgrp())
                helper.read_process_output(child, until=helper.SIGNAL_READY, timeout=0.1)
        self.assertLess(time.monotonic() - started, 6)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        self.assertTrue(child.stdout.closed and child.stderr.closed)
        self.assert_gone(child.pid)

    def test_output_overflow_fails_without_emitting_child_bytes(self):
        with self.assertRaisesRegex(helper.FixtureFailure, "^fixture_child_output_limit$"):
            with helper.disposable_child(command(
                    "import os, time; os.write(1, b'x' * 70000); time.sleep(60)")) as child:
                helper.read_process_output(child, timeout=2)
        self.assert_gone(child.pid)

    def test_ready_marker_with_stderr_is_refused(self):
        code = ("import os, time; os.write(2, b'unexpected'); time.sleep(0.05); "
                f"os.write(1, {helper.SIGNAL_READY!r}); time.sleep(60)")
        with self.assertRaisesRegex(helper.FixtureFailure, "fixture_child_unexpected_stderr"):
            with helper.disposable_child(command(code)) as child:
                helper.read_process_output(child, until=helper.SIGNAL_READY, timeout=2)
        self.assert_gone(child.pid)

    def test_surviving_owned_group_fails_before_emergency_cleanup(self):
        # A live survivor cannot become PASS merely because context exit kills it.
        with helper.disposable_child(command("import time; time.sleep(60)")) as child:
            with self.assertRaisesRegex(helper.FixtureFailure, "fixture_process_group_survived"):
                helper.wait_owned_group_gone(child.pid, timeout=0.08)
            self.assertIsNone(child.poll())
        self.assertEqual(child.returncode, -signal.SIGKILL)
        self.assert_gone(child.pid)

    @contextmanager
    def controller_fixture(self, scenario, code, base):
        children, invocations = [], []

        @contextmanager
        def local_child(invocation):
            invocations.append(invocation)
            # The controller's exact command is recorded, but never run against
            # the host or installed image. Only this synthetic Python runs.
            with REAL_DISPOSABLE_CHILD(command(code)) as child:
                children.append(child)
                yield child

        def bounded_read(child, **kwargs):
            kwargs["timeout"] = min(kwargs.get("timeout", 2), 2)
            return REAL_READ_PROCESS_OUTPUT(child, **kwargs)

        with patch.object(helper, "SCENARIOS", ("all", scenario)), \
             patch.object(helper, "KEY_PATH", base / "key"), \
             patch.object(helper, "CONFIG_PATH", base / "config"), \
             patch.object(helper, "disposable_child", side_effect=local_child), \
             patch.object(helper, "read_process_output", side_effect=bounded_read), \
             patch.object(helper.socket, "socket") as listener:
            # Worker controller tests make no host-network calls.
            listener.return_value.connect_ex.return_value = 111
            yield children, invocations
        for child in children:
            self.assert_gone(child.pid)

    def test_controller_requires_exact_fault_exit_and_marker(self):
        cases = (
            (2, helper.FAULT_MARKER, b""),
            (1, b"unexpected-output", b""),
            (1, helper.FAULT_MARKER, b"unexpected-error"),
        )
        for exit_code, output, errors in cases:
            with self.subTest(exit_code=exit_code, extra_output=bool(errors)), \
                 tempfile.TemporaryDirectory() as directory:
                code = (f"import os; os.write(1, {output!r}); "
                        f"os.write(2, {errors!r}); os._exit({exit_code})")
                with self.controller_fixture("warmup-auth-failure", code, Path(directory)) as state:
                    with self.assertRaisesRegex(helper.FixtureFailure,
                                                "warmup_failure_subprocess_not_closed"):
                        helper.run_failure_children(Path("/fixture"))
                self.assertIn("--actual-image", state[1][0])
                self.assertEqual(state[1][0][-1], "warmup-auth-failure")

    def test_controller_reaps_nonready_signal_child(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.controller_fixture("signal-int", "pass", Path(directory)):
                with self.assertRaisesRegex(helper.FixtureFailure, "fixture_child_not_ready"):
                    helper.run_failure_children(Path("/fixture"))

    def test_controller_fault_success_removes_only_synthetic_fixture_files(self):
        for scenario in ("warmup-auth-failure", "warmup-timeout"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                code = (f"import os; from pathlib import Path; base = Path({directory!r}); "
                        "(base / 'key').write_bytes(b'fixture'); "
                        "(base / 'config').write_bytes(b'{}'); "
                        f"os.write(1, {helper.FAULT_MARKER!r}); os._exit(1)")
                with self.controller_fixture(scenario, code, base):
                    helper.run_failure_children(Path("/fixture"))
                self.assertFalse((base / "key").exists())
                self.assertFalse((base / "config").exists())

    def test_actual_sigint_reaches_repository_launcher_finally_and_reaps_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            owned = base / "owned.json"
            # The worker owns/reaps its own descendant on TERM. The repository
            # launcher receives SIGINT, runs its genuine finally, and invokes
            # only the synthetic cleanup collaborator supplied below.
            worker_code = r'''
import os, signal, subprocess, sys
descendant = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
def stop(_signum, _frame):
    descendant.kill()
    descendant.wait(timeout=2)
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
print(descendant.pid, flush=True)
signal.pause()
'''
            code = f'''
import json, os, secrets, signal, subprocess, sys, types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, {str(ROOT / "tests/lifecycle")!r})
import test_sglang_file_auth as fixture
launcher = fixture.launcher
args = fixture.args_fixture()
server = fixture.source_server(args)
worker = None
cleanup_calls = []
def synthetic_engine_start(_args, execute_warmup_func):
    global worker
    worker = subprocess.Popen([sys.executable, '-u', '-c', {worker_code!r}],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True)
    descendant_pid = int(worker.stdout.readline())
    Path({str(owned)!r}).write_text(json.dumps([os.getpid(), worker.pid, descendant_pid]))
    os.write(1, {helper.SIGNAL_READY!r})
    signal.pause()
    raise RuntimeError('signal did not interrupt launcher')
def synthetic_cleanup(parent_pid, include_parent):
    assert parent_pid == os.getpid() and include_parent is False
    cleanup_calls.append(parent_pid)
    worker.terminate()
    worker.wait(timeout=2)
    worker.stdout.close()
    assert worker.returncode == 0
server.launch_server = synthetic_engine_start
modules = fixture.native_modules()
modules.update({{
    'sglang.srt.server_args': types.SimpleNamespace(prepare_server_args=lambda _argv: args),
    'sglang.srt.entrypoints': types.SimpleNamespace(http_server=server),
    'sglang.srt.utils': types.SimpleNamespace(kill_process_tree=synthetic_cleanup),
}})
with patch.dict(sys.modules, modules), \
     patch.object(launcher, 'validate_environment'), \
     patch.object(launcher, 'read_key', return_value=launcher._PrivateKey(secrets.token_urlsafe(32))):
    try:
        launcher.main(fixture.cli())
    except KeyboardInterrupt:
        assert cleanup_calls == [os.getpid()]
        os.write(1, {helper.SIGNAL_DONE!r})
    else:
        raise RuntimeError('real SIGINT was not delivered')
'''
            with self.controller_fixture("signal-int", code, base) as state:
                helper.run_failure_children(Path("/fixture"))
            pids = json.loads(owned.read_text())
            self.assertEqual(pids[0], state[0][0].pid)
            for pid in pids:
                self.assert_gone(pid)


if __name__ == "__main__":
    unittest.main()
