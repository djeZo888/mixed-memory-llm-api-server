"""Offline guards and real subprocess cleanup for the synthetic wire runner."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_bootstrap import snapshot


SPEC = importlib.util.spec_from_file_location("a2o_wire_tests", Path(__file__).with_name("wire_fixture.py"))
wire = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wire)


class WireFixtureGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="a2o-wire-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.forbidden = secrets.token_hex(24).encode("ascii")
        self.env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}

    def test_http_guard_rejects_lost_none_on_every_request_kind(self):
        # Deliberately malformed HTTP requests test the guard, not the CLI.
        server = wire.WireServer(("127.0.0.1", 0), wire.Handler)
        server.lock = threading.Lock()
        server.key = self.forbidden
        server.model, server.effort, server.mode = "qwen3.8-27b", "none", "tool"
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            for kind in ("title", "ordinary", "tool", "continuation"):
                for change, expected in (({}, "effort_presence_mismatch"),
                                         ({"reasoning_effort": "low"}, "effort_value_mismatch"),
                                         ({"reasoning_effort": None}, "effort_value_mismatch"),
                                         ({"reasoning_effort": "none", "chat_template_kwargs":
                                           {"enable_thinking": True}}, "unexpected_template_or_body_override")):
                    messages = [{"role": "user", "content": "Generate a title for this conversation:\n"}]
                    if kind == "continuation":
                        messages += [{"role": "tool", "tool_call_id": "call_a2o_read", "content": "marker"}]
                    body = {"model": server.model, "stream": True, "max_tokens": 2048, "messages": messages}
                    if kind != "title":
                        body["tools"] = [{"type": "function", "function": {"name": "read"}}]
                    body.update(change)
                    with server.lock:
                        server.received, server.records, server.failure = 0, [], None
                    request = Request("http://127.0.0.1:" + str(server.server_port) + "/v1/chat/completions",
                                      data=json.dumps(body).encode(),
                                      headers={"Authorization": "Bearer " + self.forbidden.decode(),
                                               "Content-Type": "application/json"})
                    with self.subTest(kind=kind, change=change):
                        with self.assertRaises(HTTPError) as caught:
                            urlopen(request, timeout=5)
                        self.assertEqual(caught.exception.code, 400)
                        caught.exception.close()
                        self.assertEqual(server.failure, expected)
                        self.assertEqual(server.received, 1)
                        self.assertEqual(server.records, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_unsupported_http_methods_are_counted_and_fail_closed(self):
        server = wire.WireServer(("127.0.0.1", 0), wire.Handler)
        server.lock = threading.Lock()
        server.received, server.failure = 0, None
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            for count, method in enumerate(("GET", "OPTIONS", "PUT"), 1):
                request = Request("http://127.0.0.1:" + str(server.server_port) + "/v1/chat/completions",
                                  method=method)
                with self.subTest(method=method), self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                caught.exception.close()
                self.assertEqual(server.received, count)
                self.assertIsNotNone(server.failure)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_fresh_roots_inside_other_git_directories_or_worktrees_are_refused(self):
        for kind in ("directory", "file"):
            checkout = self.root / kind
            checkout.mkdir(mode=0o700)
            marker = checkout / ".git"
            if kind == "directory":
                marker.mkdir(mode=0o700)
            else:
                marker.write_text("gitdir: /synthetic/not-opened\n")
            parent = checkout / "nested"
            parent.mkdir(mode=0o700)
            before = snapshot(self.root)
            with self.subTest(kind=kind), self.assertRaisesRegex(wire.FixtureError, "work_root_must_be_outside_git"):
                wire.run_fixture(parent / "fresh-private-root")
            self.assertEqual(before, snapshot(self.root))

    def test_existing_work_root_is_refused_without_touching_contents(self):
        existing = self.root / "existing"
        existing.mkdir(mode=0o700)
        (existing / "keep.txt").write_text("Keep this existing state.\n")
        before = snapshot(self.root)
        with self.assertRaisesRegex(wire.FixtureError, "work_root_must_be_new"):
            wire.run_fixture(existing)
        self.assertEqual(before, snapshot(self.root))

    def test_forbidden_argv_is_refused_before_execution_without_echo(self):
        output, errors = io.StringIO(), io.StringIO()
        marker = self.root / "must-not-run"
        argv = [sys.executable, "-c", "from pathlib import Path; Path('must-not-run').touch()",
                self.forbidden.decode("ascii")]
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with self.assertRaises(wire.FixtureError) as caught:
                wire.child(argv, self.root, self.env, 5, self.forbidden)
        self.assertEqual(str(caught.exception), "credential_in_argv")
        self.assertFalse(marker.exists())
        self.assertEqual(output.getvalue() + errors.getvalue(), "")
        self.assertNotIn(self.forbidden.decode(), str(caught.exception))

    def test_forbidden_stdout_and_stderr_are_withheld(self):
        env = dict(self.env, A2O_SYNTHETIC_FORBIDDEN=self.forbidden.decode("ascii"))
        for descriptor in (1, 2):
            output, errors = io.StringIO(), io.StringIO()
            code = "import os; os.write(" + str(descriptor) + ", os.environ['A2O_SYNTHETIC_FORBIDDEN'].encode())"
            with self.subTest(descriptor=descriptor), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                with self.assertRaises(wire.FixtureError) as caught:
                    wire.child([sys.executable, "-c", code], self.root, env, 5, self.forbidden)
            self.assertEqual(str(caught.exception), "credential_in_child_output")
            self.assertEqual(output.getvalue() + errors.getvalue(), "")
            self.assertNotIn(self.forbidden.decode(), str(caught.exception))

    @unittest.skipUnless(os.name == "posix", "Process-group runner targets macOS/glibc Linux")
    def test_timeout_is_bounded_and_child_is_reaped(self):
        pid_file = self.root / "child-pid"
        code = "import os,time; from pathlib import Path; Path('child-pid').write_text(str(os.getpid())); time.sleep(60)"
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(wire.FixtureError, "child_timeout"):
                wire.child([sys.executable, "-c", code], self.root, self.env, 0.5, self.forbidden)
            self.assertLess(time.monotonic() - started, 8)
            self.assertTrue(pid_file.exists(), "The actual timeout child must have started")
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)
        finally:
            if pid_file.exists():
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(int(pid_file.read_text()), signal.SIGKILL)

    @unittest.skipUnless(os.name == "posix", "Process-group runner targets macOS/glibc Linux")
    def test_successful_parent_cannot_leave_term_ignoring_descendant(self):
        descendant = self.root / "descendant.py"
        descendant.write_text(
            "import os,signal,time\n"
            "from pathlib import Path\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "Path('descendant-pid').write_text(str(os.getpid()))\n"
            "while True: time.sleep(60)\n"
        )
        code = (
            "import os,subprocess,sys,time\n"
            "from pathlib import Path\n"
            "Path('parent-pid').write_text(str(os.getpid()))\n"
            "subprocess.Popen([sys.executable, 'descendant.py'], stdin=subprocess.DEVNULL, "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "deadline = time.monotonic() + 3\n"
            "while not Path('descendant-pid').exists():\n"
            "    if time.monotonic() > deadline: raise SystemExit(2)\n"
            "    time.sleep(0.01)\n"
        )
        parent_pid_file = self.root / "parent-pid"
        descendant_pid_file = self.root / "descendant-pid"
        started = time.monotonic()
        try:
            self.assertEqual(wire.child([sys.executable, "-c", code], self.root, self.env, 5, self.forbidden), b"")
            self.assertLess(time.monotonic() - started, 8)
            self.assertTrue(descendant_pid_file.exists(), "The actual descendant must have started")
            for pid_file in (parent_pid_file, descendant_pid_file):
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)
        finally:
            if parent_pid_file.exists():
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(int(parent_pid_file.read_text()), signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
