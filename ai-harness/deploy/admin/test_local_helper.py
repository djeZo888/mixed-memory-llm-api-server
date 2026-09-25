#!/usr/bin/env python3
"""Offline fixtures only: no systemd, ai-vm, reboot, privileged command or secrets."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("h005_local_helper", Path(__file__).with_name("local_helper.py"))
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)
BOOT_A = "00000000-0000-0000-0000-000000000001"
BOOT_B = "00000000-0000-0000-0000-000000000002"


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ops.db"
        self.boot = BOOT_A
        self.clock = 1000.
        self.identity = {"load": "loaded", "active": "active", "sub": "running", "invocation": "a" * 32}
        self.calls = []
        self.ops = helper.Operations(self.path, lambda: self.boot, lambda _: copy.deepcopy(self.identity),
                                     lambda request: self.calls.append(request), clock=lambda: self.clock)
        for service in helper.SERVICES:
            self.ops.refresh(service)

    def tearDown(self):
        deadline = time.monotonic() + 2
        while self.ops.busy and time.monotonic() < deadline:
            time.sleep(.005)
        self.ops.db.close()
        self.temp.cleanup()

    def request(self, action="service.start", service="harness", key="fixture-0001"):
        snapshot = self.ops.status()
        generation = snapshot["generation"] if action == "node.reboot" else next(v["generation"] for v in snapshot["services"] if v["service_id"] == service)
        result = {"schema_version": 1, "node_id": "ai-harness", "action": action,
                  "idempotency_key": key, "expected_boot_id": snapshot["boot_id"],
                  "expected_generation": generation, "allow_interrupt": True}
        if action != "node.reboot":
            result["service_id"] = service
        return result

    def await_operation(self, op):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            receipt = self.ops.get(op["operation_id"])
            if receipt["status"] not in {"accepted", "running"}:
                return receipt
            time.sleep(.005)
        self.fail("operation did not settle")

    def rejects(self, request, code):
        with self.assertRaises(helper.Rejected) as caught:
            self.ops.submit(request)
        self.assertEqual(code, caught.exception.code)

    def test_only_fixed_registered_commands_no_shell_or_input_paths(self):
        owner = helper.CommandOwner(helper.Identity(1000, 1000, "user", "/home/user"))
        for service, unit in helper.SERVICES.items():
            command = owner.command(self.request(service=service))
            self.assertEqual(command[-2:], ["start", unit])
            self.assertNotIn("sh", command)
            if service != "status":
                self.assertEqual(command[:4], ["/usr/sbin/runuser", "--user", "user", "--"])
        for replacement in ({"service_id": "nginx.service"}, {"path": "/bin/sh"}, {"action": []}, {"service_id": {}}, {"gpu_uuid": "unrequested"}):
            request = self.request()
            request.update(replacement)
            with self.assertRaises(helper.Rejected):
                helper.validate_request(request)
        self.assertEqual(self.calls, [])

    def test_freshness_outage_does_not_fabricate_missing_hardware(self):
        self.clock += 16
        service = self.ops.status()["services"][0]
        self.assertEqual(service["availability"], "unknown")
        self.assertEqual(service["freshness"], "stale")
        self.assertFalse(service["hardware_latched"])
        self.assertIsNone(service["queue_depth"])
        self.rejects(self.request(), "observation_unavailable")

    def test_unknown_work_requires_confirmation_and_destructive_default_is_closed(self):
        request = self.request()
        request["allow_interrupt"] = False
        self.rejects(request, "interrupt_confirmation_required")
        for action in ("service.stop", "service.restart", "node.reboot"):
            self.rejects(self.request(action), "local_admission_interlock_unavailable")
        self.assertEqual(self.calls, [])

    def test_generation_changes_only_when_relevant_identity_changes(self):
        before = self.ops.status()
        self.clock += 2
        self.ops.refresh("harness")
        self.assertEqual(before["generation"], self.ops.status()["generation"])
        request = self.request()
        self.identity["invocation"] = "b" * 32
        self.ops.refresh("harness")
        self.rejects(request, "confirmation_stale")
        self.boot = BOOT_B
        self.ops.refresh("harness")
        self.rejects(request, "confirmation_stale")
        self.assertEqual(self.calls, [])

    def test_durable_idempotency_returns_prior_receipt_after_boot_change(self):
        request = self.request()
        accepted = self.ops.submit(request)
        self.assertEqual(accepted["status"], "accepted")
        done = self.await_operation(accepted)
        self.assertEqual(done["status"], "succeeded")
        self.assertEqual(len(self.calls), 1)
        self.boot = BOOT_B
        self.ops.refresh("harness")
        repeated = self.ops.submit(request)
        self.assertEqual(repeated["operation_id"], accepted["operation_id"])
        changed = self.request()
        self.rejects(changed, "idempotency_conflict")
        self.assertEqual(len(self.calls), 1)
        self.ops.db.close()
        self.ops = helper.Operations(self.path, lambda: self.boot, lambda _: self.identity,
                                     lambda value: self.fail("must not replay"))
        self.assertEqual(self.ops.submit(request)["operation_id"], accepted["operation_id"])

    def test_restart_recovers_inflight_as_unknown_without_replay(self):
        request = self.request()
        with mock.patch.object(threading.Thread, "start"):
            accepted = self.ops.submit(request)
        self.ops.busy = False
        self.ops.db.close()
        self.ops = helper.Operations(self.path, lambda: self.boot, lambda _: self.identity,
                                     lambda value: self.fail("must not replay"))
        receipt = self.ops.get(accepted["operation_id"])
        self.assertEqual(receipt["status"], "unknown")
        self.assertEqual(receipt["reason"], "helper_restarted_no_replay")
        self.assertEqual(self.ops.submit(request), receipt)

    def test_second_confirmation_prevents_dispatch_after_generation_changes(self):
        request = self.request()
        with mock.patch.object(threading.Thread, "start"):
            accepted = self.ops.submit(request)
        self.identity["invocation"] = "b" * 32
        self.ops._run(accepted["operation_id"], request)
        self.assertEqual(self.ops.get(accepted["operation_id"])["status"], "failed")
        self.assertEqual(self.calls, [])

    def test_capped_probe_hang_and_independent_cached_status(self):
        entered, release = threading.Event(), threading.Event()
        def hung(service):
            entered.set()
            release.wait(2)
            return self.identity
        self.ops.observe = hung
        thread = threading.Thread(target=self.ops.refresh, args=("harness",))
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertFalse(self.ops.refresh("harness"))
        start = time.monotonic()
        snapshot = self.ops.status()
        self.assertLess(time.monotonic() - start, .1)
        self.assertEqual(snapshot["node_id"], "ai-harness")
        self.assertEqual(self.ops.probing, {"harness"})
        release.set()
        thread.join(2)

    def test_capacity_one_operation_rejects_second_without_dropping_receipt(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(request):
            entered.set()
            release.wait(2)
        self.ops.execute = blocked
        accepted = self.ops.submit(self.request())
        self.assertTrue(entered.wait(1))
        self.rejects(self.request(key="fixture-0002"), "operation_in_progress")
        self.assertEqual(self.ops.submit(self.request())["operation_id"], accepted["operation_id"])
        release.set()
        self.await_operation(accepted)

    def test_fixture_interlock_precedes_dispatch_and_reboot_is_not_claimed_complete(self):
        events = []
        def freeze(request):
            events.append("freeze")
            return lambda: events.append("release")
        self.ops.freeze = freeze
        self.ops.execute = lambda request: events.append("execute")
        receipt = self.await_operation(self.ops.submit(self.request("node.reboot")))
        self.assertEqual(events, ["freeze", "execute", "release"])
        self.assertEqual(receipt["status"], "unknown")
        self.assertEqual(receipt["reason"], "reboot_awaiting_changed_boot")

    def test_audit_has_no_request_body_idempotency_keys_or_command_output(self):
        self.ops.execute = lambda request: (_ for _ in ()).throw(RuntimeError("private-command-output"))
        receipt = self.await_operation(self.ops.submit(self.request()))
        self.assertEqual(receipt["status"], "unknown")
        audit = json.dumps(self.ops.db.execute("SELECT * FROM audit").fetchall())
        self.assertNotIn("private-command-output", audit)
        self.assertNotIn("fixture-0001", audit)
        self.assertNotIn("/home", audit)
        status = json.dumps(self.ops.status())
        self.assertNotIn("invocation", status)

    def test_http_uds_routes_and_typed_rejection_without_tcp_listener(self):
        path = str(Path(self.temp.name) / "helper.sock")
        server = helper.Server(path, os.getuid(), self.ops)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def fetch(raw):
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(path)
                client.sendall(raw)
                chunks = []
                while data := client.recv(65536):
                    chunks.append(data)
                return b"".join(chunks)
        try:
            with mock.patch.object(helper, "authorized_peer", return_value=True):
                response = fetch(b"GET /control/v1/node/status HTTP/1.0\r\n\r\n")
                self.assertIn(b"200 OK", response)
                self.assertIn(b'"node_id":"ai-harness"', response)
                body = json.dumps({**self.request(), "command": "secret-command-text"}).encode()
                response = fetch(b"POST /control/v1/node/actions HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
                self.assertIn(b"400 Bad Request", response)
                self.assertNotIn(b"secret-command-text", response)
                self.assertEqual(self.calls, [])
            self.assertEqual(server.address_family, socket.AF_UNIX)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_http_status_remains_available_while_single_mutation_admission_blocks(self):
        path = str(Path(self.temp.name) / "concurrent-helper.sock")
        server = helper.Server(path, os.getuid(), self.ops)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        entered, release = threading.Event(), threading.Event()
        admissions = []
        def blocked_submit(value):
            admissions.append(value)
            entered.set()
            release.wait(3)
            raise helper.Rejected("fixture_storage_unavailable", 503)
        def fetch(raw):
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(1)
                client.connect(path)
                client.sendall(raw)
                chunks = []
                while data := client.recv(65536):
                    chunks.append(data)
                return b"".join(chunks)
        body = json.dumps(self.request()).encode()
        post = b"POST /control/v1/node/actions HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        responses = []
        errors = []
        def pending_post():
            try:
                responses.append(fetch(post))
            except Exception as error:
                errors.append(error)
        try:
            with mock.patch.object(helper, "authorized_peer", return_value=True), mock.patch.object(self.ops, "submit", side_effect=blocked_submit):
                pending = threading.Thread(target=pending_post)
                pending.start()
                self.assertTrue(entered.wait(1))
                started = time.monotonic()
                for _ in range(8):
                    rejected = fetch(post)
                    self.assertIn(b"503 Service Unavailable", rejected)
                    self.assertIn(b"operation_admission_busy", rejected)
                status = fetch(b"GET /control/v1/node/status HTTP/1.0\r\n\r\n")
                self.assertIn(b"200 OK", status)
                self.assertIn(b'"node_id":"ai-harness"', status)
                self.assertLess(time.monotonic() - started, .5)
                self.assertEqual(len(admissions), 1)
                self.assertLessEqual(len(server.workers._threads), helper.HTTP_WORKERS)
                self.assertFalse(release.is_set())
                release.set()
                pending.join(2)
                self.assertFalse(errors)
                self.assertIn(b"fixture_storage_unavailable", responses[0])
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            serving.join(2)

    def test_exact_worker1_contract_fixture_keys_and_cached_reads_without_writer_lock(self):
        fixture_dir = Path(__file__).resolve().parents[2] / "server/test/fixtures/h005"
        expected = json.loads((fixture_dir / "node-status-v1.json").read_text())
        snapshot = self.ops.status()
        self.assertTrue(set(expected) <= set(snapshot))
        for component in expected["resources"]:
            self.assertEqual(set(expected["resources"][component]), set(snapshot["resources"][component]))
        self.assertEqual(set(expected["inventory"]), set(snapshot["inventory"]))
        for service in snapshot["services"]:
            self.assertTrue(set(expected["services"][0]) <= set(service))
        receipt = self.await_operation(self.ops.submit(self.request()))
        expected_receipt = json.loads((fixture_dir / "node-operation-v1.json").read_text())
        self.assertTrue(set(expected_receipt) <= set(receipt))
        entered, release = threading.Event(), threading.Event()
        def writer_lock():
            with self.ops.lock:
                entered.set()
                release.wait(2)
        thread = threading.Thread(target=writer_lock)
        thread.start()
        self.assertTrue(entered.wait(1))
        started = time.monotonic()
        self.assertEqual(self.ops.status()["node_id"], "ai-harness")
        self.assertEqual(self.ops.get(receipt["operation_id"]), receipt)
        self.assertLess(time.monotonic() - started, .1)
        release.set()
        thread.join(2)

    def test_audit_capacity_does_not_evict_idempotency_or_dispatch(self):
        request = self.request()
        receipt = self.await_operation(self.ops.submit(request))
        with mock.patch.object(helper, "MAX_OPERATIONS", 1):
            self.rejects(self.request(key="fixture-0002"), "audit_capacity_reached")
            self.assertEqual(self.ops.submit(request)["operation_id"], receipt["operation_id"])
        self.assertEqual(len(self.calls), 1)

    def test_unauthorized_peer_cannot_reach_http_handler(self):
        class Peer:
            def getsockopt(self, *_):
                import struct
                return struct.pack("3i", 1, 1001, 1001)
        with mock.patch.object(socket, "SO_PEERCRED", 17, create=True):
            self.assertFalse(helper.authorized_peer(Peer(), 1000))
            self.assertTrue(helper.authorized_peer(Peer(), 1001))


if __name__ == "__main__":
    unittest.main()
