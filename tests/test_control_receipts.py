"""Focused receipt races with explicit in-process lifecycle/storage fixtures."""

import contextlib
import copy
import json
from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from control.core import Application, digest, observation, safe_error
from control.journal import Journal
from test_control_journal import MemoryStore, operation, state_with


@contextlib.contextmanager
def fixture_lease(*, blocking):
    assert blocking is False
    yield object()


class StopBackendFixture:
    def __init__(self):
        self.stop_calls = 0

    def open(self, *, recovery=False):
        return self

    def observe(self, deadline):
        deadline.remaining()
        return {"selected": None, "desired": "stopped", "container": None,
                "container_running": False, "observed": "stopped",
                "observation_available": True, "storage_available": True,
                "state_persisted": True}

    def check_admission(self, lease, deadline):
        deadline.remaining()

    def stop(self, lease, deadline):
        self.stop_calls += 1


class BlockingStore(MemoryStore):
    def __init__(self, value):
        super().__init__(value)
        self.entered = threading.Event()
        self.release = threading.Event()

    def write(self, value):
        if any(entry["status"] == "pending" for entry in value["entries"].values()):
            self.entered.set()
            if not self.release.wait(3):
                raise OSError("fixture_block_timeout")
        super().write(value)


class InitiallyUnavailableStore(MemoryStore):
    def __init__(self, value):
        super().__init__(value)
        self.reads = 0
        self.writes = []

    def read(self):
        self.reads += 1
        if self.reads == 1:
            raise OSError("sensitive-fixture-storage-unavailable")
        return super().read()

    def write(self, value):
        self.writes.append(copy.deepcopy(value))
        super().write(value)


class ReceiptTests(unittest.TestCase):
    def request(self, app, key="fixture-request"):
        return app.handle("POST", "/control/v1/stop",
                          {"content-type": "application/json", "idempotency-key": key},
                          json.dumps({"expected_active": None, "expected_generation": 1}).encode())

    def test_slow_receipt_write_cancels_without_mutation_and_conflict_is_immediate(self):
        backend = StopBackendFixture()
        _, fingerprint = observation(backend.observe(type("Deadline", (), {"remaining": lambda self: 1})()))
        initial = {"schema": 1, "generation": 1, "fingerprint": fingerprint, "entries": {}}
        store = BlockingStore(initial)
        app = Application(backend, Journal(store), lease_factory=fixture_lease,
                          admission_seconds=0.08, transition_seconds=1)
        self.addCleanup(app.close)
        self.addCleanup(store.release.set)
        result = []
        thread = threading.Thread(target=lambda: result.append(self.request(app)))
        thread.start()
        self.assertTrue(store.entered.wait(1))
        before = time.monotonic()
        self.assertEqual(self.request(app, "conflict")[0], 409)
        self.assertLess(time.monotonic() - before, 0.1)
        thread.join(timeout=0.5)
        self.assertFalse(thread.is_alive(), "receipt timeout waited on the storage writer")
        self.assertEqual(result, [(503, {"error": {"code": "admission_timeout"}})])
        self.assertEqual(backend.stop_calls, 0)
        app.close()
        store.release.set()
        app._worker.join(timeout=1)
        self.assertFalse(app._worker.is_alive())
        self.assertEqual(backend.stop_calls, 0)
        recorded = next(iter(store.value["entries"].values()))
        self.assertEqual(recorded["status"], "interrupted")
        self.assertEqual(recorded["failure_code"], "admission_timeout")

    def test_restart_idempotency_receipt_never_claims_owned_running_operation(self):
        request = {"expected_active": None, "expected_generation": 1}
        pending = operation(status="running", completed_at=None)
        pending.update(kind="stop", target=None, request_digest=digest(["stop", request]),
                       idempotency_digest=digest("fixture-request"))
        backend = StopBackendFixture()
        app = Application(backend, Journal(MemoryStore(state_with(pending))), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        status, body = self.request(app)
        self.assertEqual(status, 202)
        self.assertTrue(body["replayed"])
        self.assertEqual(body["operation"]["status"], "interrupted")
        self.assertEqual(body["operation"]["failure_code"], "service_interrupted")
        self.assertFalse(body["operation"]["state_persisted"])
        self.assertFalse(body["state_persisted"])
        self.assertEqual(backend.stop_calls, 0)

    def test_unhashable_exception_code_is_sanitized(self):
        for code in ([], {}, None, "sensitive-fixture-message"):
            error = RuntimeError("sensitive-fixture-message")
            error.code = copy.deepcopy(code)
            self.assertEqual(safe_error(error), "transition_failed")

    def test_initially_unreadable_journal_reloads_retained_keys_and_generation(self):
        backend = StopBackendFixture()
        _, fingerprint = observation(backend.observe(type("Deadline", (), {"remaining": lambda self: 1})()))
        request = {"expected_active": None, "expected_generation": 41}
        now = time.time()
        retained = operation()
        retained.update(kind="stop", target=None, created_at=now - 10, updated_at=now - 1,
                        deadline=now + 100, completed_at=now - 1, generation=41,
                        request_digest=digest(["stop", request]), idempotency_digest=digest("retained-key"))
        initial = {"schema": 1, "generation": 41, "fingerprint": fingerprint,
                   "entries": {retained["id"]: retained}}
        store = InitiallyUnavailableStore(initial)
        app = Application(backend, Journal(store), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        self.assertEqual(app._journal_error, "journal_unavailable")
        status, body = app.handle("POST", "/control/v1/stop",
                                  {"content-type": "application/json", "idempotency-key": "retained-key"},
                                  json.dumps(request).encode())
        self.assertEqual(status, 202)
        self.assertTrue(body["replayed"])
        self.assertEqual(body["operation"]["id"], retained["id"])
        self.assertEqual(app._state["generation"], 41)
        self.assertEqual(set(app._state["entries"]), {retained["id"]})
        self.assertEqual(store.value, initial)
        self.assertEqual(store.reads, 2)
        self.assertEqual(store.writes, [])
        self.assertEqual(backend.stop_calls, 0)

    def test_reloaded_journal_reconciles_new_identity_from_durable_generation(self):
        backend = StopBackendFixture()
        now = time.time()
        retained = operation()
        retained.update(created_at=now - 10, updated_at=now - 1,
                        deadline=now + 100, completed_at=now - 1)
        initial = {"schema": 1, "generation": 41, "fingerprint": "e" * 64,
                   "entries": {retained["id"]: retained}}
        store = InitiallyUnavailableStore(initial)
        app = Application(backend, Journal(store), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        status, body = app.handle("GET", "/control/v1/status", {}, b"")
        self.assertEqual(status, 200)
        self.assertEqual(body["generation"], 42)
        self.assertTrue(body["generation_current"])
        self.assertEqual(set(store.value["entries"]), {retained["id"]})
        self.assertEqual(store.value["generation"], 42)
        self.assertEqual(store.reads, 2)
        self.assertEqual(len(store.writes), 1)
        self.assertEqual(backend.stop_calls, 0)

    def test_corrupt_journal_refuses_normal_mutation_without_overwrite(self):
        backend = StopBackendFixture()
        malformed = {"schema": "sensitive-fixture-corrupt"}
        store = MemoryStore(malformed)
        app = Application(backend, Journal(store), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        request = {"deployment_id": "future-model", "expected_active": None,
                   "expected_generation": 1, "allow_interrupt": True}
        status, body = app.handle("POST", "/control/v1/switch",
                                  {"content-type": "application/json", "idempotency-key": "fixture-key"},
                                  json.dumps(request).encode())
        self.assertEqual((status, body), (503, {"error": {"code": "journal_corrupt"}}))
        self.assertEqual(store.value, malformed)
        self.assertEqual(backend.stop_calls, 0)

    def test_restoring_older_journal_never_rewinds_volatile_generation(self):
        backend = StopBackendFixture()
        _, fingerprint = observation(backend.observe(type("Deadline", (), {"remaining": lambda self: 1})()))
        initial = {"schema": 1, "generation": 4, "fingerprint": fingerprint, "entries": {}}
        store = InitiallyUnavailableStore(initial)
        app = Application(backend, Journal(store), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        # A prior exact recovery stop advanced the in-memory semantic counter.
        app._state.update(generation=7, fingerprint=fingerprint)
        status, body = app.handle("GET", "/control/v1/status", {}, b"")
        self.assertEqual(status, 200)
        self.assertEqual(body["generation"], 7)
        self.assertEqual(store.value["generation"], 7)
        self.assertTrue(body["generation_current"])
        self.assertEqual(backend.stop_calls, 0)

    def test_slow_journal_get_returns_within_bound_while_write_is_blocked(self):
        backend = StopBackendFixture()
        _, fingerprint = observation(backend.observe(type("Deadline", (), {"remaining": lambda self: 1})()))
        initial = {"schema": 1, "generation": 1, "fingerprint": fingerprint, "entries": {}}
        store = BlockingStore(initial)
        app = Application(backend, Journal(store), lease_factory=fixture_lease,
                          admission_seconds=0.08, transition_seconds=1)
        self.addCleanup(app.close)
        self.addCleanup(store.release.set)
        thread = threading.Thread(target=lambda: self.request(app))
        thread.start()
        self.assertTrue(store.entered.wait(1))
        before = time.monotonic()
        status, body = app.handle("GET", "/control/v1/status", {}, b"")
        self.assertLess(time.monotonic() - before, 0.3)
        self.assertEqual((status, body), (503, {"error": {"code": "journal_unavailable"}}))
        self.assertFalse(store.release.is_set())
        thread.join(timeout=0.5)
        self.assertFalse(thread.is_alive())
        app.close()
        store.release.set()
        app._worker.join(timeout=1)
        self.assertFalse(app._worker.is_alive())
        self.assertEqual(backend.stop_calls, 0)

    def test_negative_or_nonfinite_deadlines_cannot_create_an_operation(self):
        backend = StopBackendFixture()
        store = MemoryStore()
        for field in ("transition_seconds", "admission_seconds", "read_seconds"):
            for value in (-1, 0, float("nan"), float("inf")):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "^invalid_deadlines$"):
                        Application(backend, Journal(store), lease_factory=fixture_lease, **{field: value})
        self.assertEqual(backend.stop_calls, 0)
        self.assertIsNone(store.value)
        app = Application(backend, Journal(store), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        request = {"expected_active": None, "expected_generation": 1, "deadline": -1}
        self.assertEqual(app.handle("POST", "/control/v1/stop",
                                    {"content-type": "application/json", "idempotency-key": "fixture-key"},
                                    json.dumps(request).encode()),
                         (400, {"error": {"code": "invalid_request"}}))
        self.assertEqual(backend.stop_calls, 0)
        self.assertIsNone(store.value)

    def test_failed_exact_recovery_after_receipt_failure_does_not_leave_pending_admission(self):
        backend = StopBackendFixture()
        _, fingerprint = observation(backend.observe(type("Deadline", (), {"remaining": lambda self: 1})()))
        initial = {"schema": 1, "generation": 1, "fingerprint": fingerprint, "entries": {}}
        class FailReceiptOnceStore(MemoryStore):
            failed = False
            def write(self, value):
                if not self.failed and any(entry["status"] == "pending" for entry in value["entries"].values()):
                    self.failed = True
                    raise OSError("fixture-first-receipt-write-failed")
                super().write(value)
        store = FailReceiptOnceStore(initial)
        app = Application(backend, Journal(store), lease_factory=fixture_lease)
        self.addCleanup(app.close)
        status, body = self.request(app)
        self.assertEqual((status, body), (503, {"error": {"code": "recovery_identity_unavailable"}}))
        self.assertEqual(backend.stop_calls, 0)
        with app._state_lock:
            interrupted = next(iter(app._state["entries"].values()))
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertFalse(interrupted["state_persisted"])
        status, body = self.request(app, "fresh-key")
        self.assertEqual(status, 202)
        self.assertFalse(body["replayed"])
        app.close()
        app._worker.join(timeout=1)
        self.assertFalse(app._worker.is_alive())
        self.assertEqual(backend.stop_calls, 1)
        persisted = Journal(store).read()
        self.assertEqual(len(persisted["entries"]), 2)
        self.assertEqual({entry["status"] for entry in persisted["entries"].values()},
                         {"interrupted", "succeeded"})


if __name__ == "__main__":
    unittest.main()
