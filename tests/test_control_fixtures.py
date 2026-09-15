"""Explicit synthetic lifecycle ports for HTTP tests; never a production adapter.

No inference, Docker, model reads, host service operations, or VM access occurs.
The fixture borrows the actual canonical lifecycle lease in a disposable root.
Its recovery path reads only that root's protected immutable /run identity file.
"""

from __future__ import annotations

from copy import deepcopy
from functools import partial
import http.client
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common.lifecycle_lease import acquire_lease
from control.core import Application
from control.http import make_server
from control.journal import Journal
from control.protocol import ControlError, PackageBlocked, StorageUnavailable
from test_control_journal import FixtureAtomicJSONStore


def model_record(identifier, port):
    return {
        "deployment_id": identifier, "model_id": "Fixture/" + identifier,
        "display_name": "Synthetic " + identifier, "revision": "a" * 40,
        "backend": "synthetic", "runtime": "synthetic-v1",
        "installed": True, "installed_verified_at": "2026-09-15T01:00:00Z",
        "small_checks_passed": True, "context_limit": 8192,
        "quantization": "fixture", "installed_bytes": 1,
        "endpoint": {"port": port, "served_model": identifier + "-alias",
                     "authentication_required": True},
    }


class SyntheticBackend:
    """Bounded ordinary fixture state shared by fresh per-request sessions."""

    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.calls = []
        self.sessions = 0
        self.serial = 0
        self.start_count = 0
        self.max_running = 0
        self.storage_available = True
        self.package_blocked = False
        self.fail_preflight = False
        self.fail_start = False
        self.fail_stop = False
        self.start_entered = threading.Event()
        self.release_start = threading.Event()
        self.release_start.set()
        self.records = [model_record("alpha", 30001), model_record("beta", 30009),
                        model_record("third-future", 30101),
                        {"deployment_id": "q38-research", "installed": False}]
        self.state = {"selected": None, "desired": "stopped", "observed": "stopped",
                      "container_running": False, "container": None, "failure": None}
        (self.root / "run" / "llmctl").mkdir(parents=True, mode=0o700)
        os.chmod(self.root / "run", 0o700)
        os.chmod(self.root / "run" / "llmctl", 0o700)
        self.recovery = FixtureAtomicJSONStore(self.root / "run" / "llmctl" / "recovery.json",
                                              expected_uid=os.getuid())

    def open(self, *, recovery=False):
        with self.lock:
            self.sessions += 1
            if recovery:
                try:
                    saved = self.recovery.read()
                except Exception:
                    raise ControlError("recovery_identity_unavailable") from None
                if (type(saved) is not dict or set(saved) != {"schema", "container"}
                        or saved["schema"] != 1 or type(saved["container"]) is not dict
                        or set(saved["container"]) != {"instance", "deployment", "id", "generation"}
                        or saved["container"] != self.state["container"]):
                    raise ControlError("recovery_identity_unavailable")
                return SyntheticSession(self, recovery_identity=deepcopy(saved["container"]))
            if not self.storage_available:
                raise StorageUnavailable()
            return SyntheticSession(self)

    def external_restart(self, deployment):
        """Model an external CLI stop/start only while its actual lease is held."""
        with acquire_lease(system_root=self.root, trusted_uid=os.getuid()):
            with self.lock:
                self.serial += 1
                self.state.update(selected=deployment, desired="running", observed="ready",
                                  container_running=True, failure=None,
                                  container={"instance": "fixture-instance", "deployment": deployment,
                                             "id": f"immutable-container-{self.serial}",
                                             "generation": f"start-{self.serial}"})
                self.recovery.write({"schema": 1, "container": self.state["container"]})


class SyntheticSession:
    def __init__(self, backend, recovery_identity=None):
        self.backend = backend
        self.recovery_identity = recovery_identity
        self.lease_identity = None
        self.thread_identity = None

    def _borrow(self, action, lease, deadline, target=None):
        deadline.remaining()
        lease.validate()
        identity, thread = id(lease), threading.get_ident()
        if self.lease_identity is None:
            self.lease_identity, self.thread_identity = identity, thread
        if self.lease_identity != identity or self.thread_identity != thread:
            raise AssertionError("fixture requires one same-thread borrowed lease")
        with self.backend.lock:
            self.backend.calls.append((action, target, identity, thread))
        return self.backend

    def observe(self, deadline):
        deadline.remaining()
        with self.backend.lock:
            if self.recovery_identity is not None and self.backend.state["container"] != self.recovery_identity:
                raise ControlError("recovery_identity_unavailable")
            value = deepcopy(self.backend.state)
            value.update(observation_available=True, storage_available=self.backend.storage_available,
                         state_persisted=self.backend.storage_available,
                         recovery_trusted=self.recovery_identity is not None,
                         ready_proof={name: value["observed"] == "ready" for name in
                             ("trusted_identity", "safe_network", "authenticated_model", "runtime_health")})
            return value

    def catalog(self, deadline):
        deadline.remaining()
        if self.recovery_identity is not None:
            raise AssertionError("recovery must not read profiles")
        with self.backend.lock:
            return deepcopy(self.backend.records)

    def check_admission(self, lease, deadline):
        backend = self._borrow("admission", lease, deadline)
        if not backend.storage_available:
            raise StorageUnavailable()
        if backend.package_blocked:
            raise PackageBlocked()

    def preflight(self, target, lease, deadline):
        backend = self._borrow("preflight", lease, deadline, target)
        if self.recovery_identity is not None:
            raise AssertionError("recovery must not preflight")
        if backend.fail_preflight:
            raise ControlError("preflight_failed")

    def stop(self, lease, deadline):
        backend = self._borrow("recover-stop" if self.recovery_identity else "stop", lease, deadline)
        with backend.lock:
            if self.recovery_identity is not None and backend.state["container"] != self.recovery_identity:
                raise ControlError("recovery_identity_unavailable")
            if not backend.fail_stop:
                backend.state.update(desired="stopped", observed="stopped", container_running=False, failure=None)

    def select(self, target, lease, deadline):
        backend = self._borrow("select", lease, deadline, target)
        if self.recovery_identity is not None:
            raise AssertionError("recovery must not select")
        with backend.lock:
            backend.state.update(selected=target, desired="stopped", observed="stopped")

    def start(self, lease, deadline):
        backend = self._borrow("start", lease, deadline)
        if self.recovery_identity is not None:
            raise AssertionError("recovery must not start")
        with backend.lock:
            if backend.state["container_running"]:
                raise AssertionError("fixture single-active violation")
            backend.start_count += 1
            backend.serial += 1
            backend.state.update(desired="running", observed="warming", container_running=True,
                                 container={"instance": "fixture-instance", "deployment": backend.state["selected"],
                                            "id": f"immutable-container-{backend.serial}",
                                            "generation": f"start-{backend.serial}"})
            backend.max_running = max(backend.max_running, 1)
            backend.recovery.write({"schema": 1, "container": backend.state["container"]})
        backend.start_entered.set()
        if not backend.release_start.wait(min(deadline.remaining(), 3)):
            raise ControlError("deadline_exceeded")
        deadline.remaining()
        with backend.lock:
            if backend.fail_start:
                backend.state.update(observed="failed", container_running=False, failure="start_failed")
                raise ControlError("start_failed")
            backend.state.update(observed="ready", failure=None)


class AvailableStore:
    """Keep disk writes real while exposing explicit storage-loss injection."""

    def __init__(self, store, backend):
        self.store, self.backend = store, backend

    def read(self):
        if not self.backend.storage_available:
            raise OSError("synthetic storage unavailable")
        return self.store.read()

    def write(self, value):
        if not self.backend.storage_available:
            raise OSError("synthetic storage unavailable")
        return self.store.write(value)


class HTTPHarness:
    def __init__(self, root, *, max_entries=128, backend=None):
        self.root = Path(root)
        self.backend = backend or SyntheticBackend(self.root)
        state_dir = self.root / "journal"
        state_dir.mkdir(mode=0o700, exist_ok=True)
        self.store = FixtureAtomicJSONStore(state_dir / "operations.json", expected_uid=os.getuid())
        self.journal = Journal(AvailableStore(self.store, self.backend), max_entries=max_entries)
        self.app = Application(self.backend, self.journal,
                               lease_factory=partial(acquire_lease, system_root=self.root, trusted_uid=os.getuid()),
                               transition_seconds=4, admission_seconds=1, read_seconds=1)
        self.key = secrets.token_urlsafe(36).encode("ascii")
        self.server = make_server(self.app, self.key, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.address = self.server.server_address

    def request(self, method="GET", path="/control/v1/status", body=None, key=None, auth=True, headers=None):
        headers = dict(headers or {})
        if auth:
            headers["Authorization"] = "Bearer " + self.key.decode("ascii")
        if body is not None:
            body = json.dumps(body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        if key is not None:
            headers["Idempotency-Key"] = key
        connection = http.client.HTTPConnection(*self.address, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def status(self):
        code, state = self.request()
        if code != 200:
            raise AssertionError((code, state))
        return state

    def payload(self, target=None, interrupt=False):
        state = self.status()
        value = {"expected_active": state["active_identity"], "expected_generation": state["generation"]}
        if target is not None:
            value.update(deployment_id=target, allow_interrupt=interrupt)
        return value

    def finish(self, receipt):
        until = time.monotonic() + 3
        while time.monotonic() < until:
            code, operation = self.request(path=receipt["operation"]["poll_url"])
            if code != 200:
                raise AssertionError((code, operation))
            if operation["status"] in ("succeeded", "failed", "interrupted"):
                return operation
            threading.Event().wait(0.005)
        raise AssertionError("synthetic operation did not finish")

    def switch(self, target, key, interrupt=False):
        code, receipt = self.request("POST", "/control/v1/switch", self.payload(target, interrupt), key)
        if code != 202:
            raise AssertionError((code, receipt))
        return self.finish(receipt)

    def close(self):
        if getattr(self, "closed", False):
            return
        self.closed = True
        self.backend.release_start.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        deadline = time.monotonic() + 4
        while not self.app.close() and time.monotonic() < deadline:
            threading.Event().wait(0.01)
