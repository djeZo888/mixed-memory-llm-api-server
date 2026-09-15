"""Real subprocess crash and loopback HTTP recovery with synthetic lifecycle.

The child is killed during an accepted, Event-blocked synthetic startup. The
restarted HTTP application observes the protected fixture identity and reconciles
the original durable operation without replay. This is not an installed systemd
service, machine boot, Docker/backend process, or live inference acceptance.
"""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import secrets
import select
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common.lifecycle_lease import acquire_lease, LeaseBusy  # noqa: E402
from test_control_fixtures import HTTPHarness, SyntheticBackend  # noqa: E402
from test_control_journal import FixtureAtomicJSONStore  # noqa: E402


def _read_protected_key(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.getuid() or info.st_nlink != 1):
            raise RuntimeError("fixture_key_unprotected")
        value = os.read(fd, 257)
        if not 32 <= len(value) <= 256:
            raise RuntimeError("fixture_key_invalid")
        return value
    finally:
        os.close(fd)


def _fixture_child(root, key_path):
    backend = SyntheticBackend(root)
    backend.release_start.clear()
    harness = HTTPHarness(root, backend=backend)
    harness.key = _read_protected_key(key_path)
    harness.server.control_key = harness.key
    try:
        # Only safe fixture metadata crosses stdout, never keys or request data.
        print(json.dumps({"port": harness.address[1]}), flush=True)
        if not backend.start_entered.wait(10):
            raise RuntimeError("fixture_start_not_received")
        with backend.lock:
            print(json.dumps({"start_count": backend.start_count,
                              "blocked": not backend.release_start.is_set(),
                              "container": backend.state["container"],
                              "observed": backend.state["observed"]}), flush=True)
        # The parent must kill this disposable process before fixture startup's
        # existing three-second bounded wait expires.
        threading.Event().wait(10)
    finally:
        harness.close()


def _request(port, key, method="GET", path="/control/v1/status", payload=None, idempotency=None):
    headers = {"Authorization": "Bearer " + key.decode("ascii")}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if idempotency is not None:
        headers["Idempotency-Key"] = idempotency
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _handshake(process, timeout=3):
    deadline = time.monotonic() + timeout
    line = bytearray()
    while len(line) < 4096:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
            raise AssertionError("fixture child handshake timed out")
        part = os.read(process.stdout.fileno(), 1)
        if not part:
            raise AssertionError("fixture child exited before handshake")
        line.extend(part)
        if part == b"\n":
            return json.loads(line)
    raise AssertionError("fixture child handshake exceeded bound")


def _finish_child(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=3)


class SubprocessRestartTests(unittest.TestCase):
    def test_sigkill_after_http_acceptance_reconciles_without_replaying_start(self):
        with tempfile.TemporaryDirectory(prefix="u1-process-crash-") as temporary:
            root = Path(temporary)
            key = secrets.token_urlsafe(36).encode("ascii")
            key_path = root / "disposable-control-key"
            fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, key)
                os.fsync(fd)
            finally:
                os.close(fd)
            child = subprocess.Popen(
                [sys.executable, "-u", str(Path(__file__).resolve()), "--fixture-child", str(root), str(key_path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, close_fds=True,
            )
            self.addCleanup(_finish_child, child)
            port = _handshake(child)["port"]
            code, state = _request(port, key)
            self.assertEqual(code, 200)
            payload = {"deployment_id": "alpha", "expected_active": state["active_identity"],
                       "expected_generation": state["generation"], "allow_interrupt": False}
            code, receipt = _request(port, key, "POST", "/control/v1/switch", payload, "crash-receipt")
            self.assertEqual(code, 202)
            original_id = receipt["operation"]["id"]
            self.assertTrue(receipt["state_persisted"])
            started = _handshake(child)
            self.assertEqual(started["start_count"], 1)
            self.assertTrue(started["blocked"])
            self.assertEqual(started["observed"], "warming")
            code, before_crash = _request(port, key, path=receipt["operation"]["poll_url"])
            self.assertEqual(code, 200)
            self.assertEqual(before_crash["status"], "running")
            with self.assertRaises(LeaseBusy):
                with acquire_lease(blocking=False, system_root=root, trusted_uid=os.getuid()):
                    self.fail("accepted startup must own canonical lease")

            # This is an actual process crash during work, with no graceful
            # close or synthetic journal-only pending-entry substitution.
            child.kill()
            output, errors = child.communicate(timeout=3)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            self.assertEqual(output, b"")
            self.assertEqual(errors, b"")
            with acquire_lease(blocking=False, system_root=root, trusted_uid=os.getuid()) as lease:
                lease.validate()  # The kernel released the killed owner's lock.

            operation_store = FixtureAtomicJSONStore(root / "journal" / "operations.json", expected_uid=os.getuid())
            durable = operation_store.read()
            self.assertEqual(durable["entries"][original_id]["status"], "running")
            recovery_store = FixtureAtomicJSONStore(root / "run" / "llmctl" / "recovery.json", expected_uid=os.getuid())
            saved_identity = recovery_store.read()
            self.assertEqual(saved_identity, {"schema": 1, "container": started["container"]})

            # Initialize fresh fixture bookkeeping in a separate disposable
            # directory, then bind its observations to the original protected
            # immutable fixture journal. No production Manager binding exists.
            backend = SyntheticBackend(root / "restart-fixture")
            backend.root = root
            backend.recovery = recovery_store
            backend.serial = 1
            backend.state.update(selected=saved_identity["container"]["deployment"],
                                 desired="running", observed="warming", container_running=True,
                                 container=saved_identity["container"])
            restarted = HTTPHarness(root, backend=backend)
            self.addCleanup(restarted.close)
            restarted.key = key
            restarted.server.control_key = key
            try:
                code, recovered = restarted.request(path=receipt["operation"]["poll_url"])
                self.assertEqual(code, 200)
                self.assertEqual(recovered["id"], original_id)
                self.assertEqual(recovered["status"], "interrupted")
                self.assertEqual(recovered["failure_code"], "service_interrupted")
                self.assertTrue(recovered["state_persisted"])
                self.assertEqual(recovered["observed"]["observed"], "unknown")
                fresh = restarted.status()
                self.assertEqual(fresh["selected"], "alpha")
                self.assertIsNotNone(fresh["active_identity"])
                self.assertEqual(fresh["observed"], "unknown")
                self.assertIsNone(fresh["current_operation"])
                code, replay = restarted.request("POST", "/control/v1/switch", payload, "crash-receipt")
                self.assertEqual(code, 202)
                self.assertTrue(replay["replayed"])
                self.assertEqual(replay["operation"]["id"], original_id)
                self.assertEqual(replay["operation"]["status"], "interrupted")
                code, conflict = restarted.request("POST", "/control/v1/switch",
                                                    {**payload, "deployment_id": "beta"}, "crash-receipt")
                self.assertEqual(code, 409)
                self.assertEqual(conflict["error"]["code"], "idempotency_conflict")
                self.assertEqual(backend.start_count, 0)
                self.assertEqual(backend.calls, [])
                after_restart = operation_store.read()
                self.assertEqual(set(after_restart["entries"]), {original_id})
                self.assertEqual(after_restart["entries"][original_id]["status"], "interrupted")
                self.assertEqual(after_restart["entries"][original_id]["generation"], fresh["generation"])
                self.assertEqual(after_restart["entries"][original_id]["active_identity"], fresh["active_identity"])
            finally:
                restarted.close()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--fixture-child":
        _fixture_child(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        unittest.main()
