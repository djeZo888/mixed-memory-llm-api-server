"""Real local HTTP + actual canonical flock + durable synthetic lifecycle tests.

These tests do not establish live inference, installed-service readiness, actual
model switching, OpenCode acceptance, or deployment hardening.
"""

from copy import deepcopy
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_control_fixtures import HTTPHarness, ROOT


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        os.chmod(self.root, 0o700)
        self.http = HTTPHarness(self.root)
        self.addCleanup(self.http.close)

    def assert_error(self, response, status, code):
        self.assertEqual(response, (status, {"error": {"code": code}}))

    def test_all_contract_routes_authenticate_with_real_application(self):
        for method, path in (("GET", "/control/v1/catalog"), ("GET", "/control/v1/status"),
                             ("POST", "/control/v1/switch"), ("POST", "/control/v1/stop"),
                             ("GET", "/control/v1/operations/" + "a" * 32)):
            self.assert_error(self.http.request(method, path, {} if method == "POST" else None, auth=False),
                              401, "unauthorized")
        self.assertEqual(self.http.backend.sessions, 0)
        self.assertEqual(self.http.backend.calls, [])

    def test_authenticated_catalog_generic_third_model_and_discovery(self):
        code, catalog = self.http.request(path="/control/v1/catalog")
        self.assertEqual(code, 200)
        self.assertEqual([entry["deployment_id"] for entry in catalog["entries"]], ["alpha", "beta", "third-future"])
        self.assertTrue(all(entry["state"] == "available" for entry in catalog["entries"]))
        self.assertEqual(self.http.switch("third-future", "future")["status"], "succeeded")
        code, catalog = self.http.request(path="/control/v1/catalog")
        entry = next(entry for entry in catalog["entries"] if entry["deployment_id"] == "third-future")
        self.assertEqual(entry["state"], "ready")
        self.assertEqual(entry["endpoint"]["base_url"], "http://127.0.0.1:30101/v1")
        self.assertEqual(entry["endpoint"]["served_model"], "third-future-alias")
        self.assertTrue(entry["endpoint"]["server_relative"])
        self.assertEqual(entry["capabilities"]["tool_calling"]["status"], "unknown")

    def test_simultaneous_switches_admit_exactly_one_and_reads_stay_responsive(self):
        self.http.backend.release_start.clear()
        payload = self.http.payload("alpha")
        gate = threading.Barrier(3)
        responses = []
        def send(key):
            gate.wait(1)
            responses.append(self.http.request("POST", "/control/v1/switch", payload, key))
        workers = [threading.Thread(target=send, args=(f"concurrent-{n}",)) for n in range(2)]
        for worker in workers:
            worker.start()
        gate.wait(1)
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(sorted(response[0] for response in responses), [202, 409])
        rejected = next(response for response in responses if response[0] == 409)
        self.assert_error(rejected, 409, "lifecycle_busy")
        self.assertTrue(self.http.backend.start_entered.wait(1))
        before = time.monotonic()
        status = self.http.status()
        self.assertLess(time.monotonic() - before, 0.5)
        self.assertEqual(status["observed"], "loading")
        code, catalog = self.http.request(path="/control/v1/catalog")
        self.assertEqual(code, 200)
        self.assertEqual(catalog["entries"][0]["state"], "loading")
        self.assertFalse(catalog["entries"][0]["endpoint"]["ready"])
        self.http.backend.release_start.set()
        receipt = next(response[1] for response in responses if response[0] == 202)
        self.assertEqual(self.http.finish(receipt)["status"], "succeeded")
        self.assertEqual(self.http.backend.start_count, 1)
        self.assertEqual(self.http.backend.max_running, 1)
        identities = {(call[2], call[3]) for call in self.http.backend.calls}
        self.assertEqual(len(identities), 1)
        self.assertNotEqual(next(iter(identities))[1], threading.get_ident())

    def test_external_process_actual_canonical_lease_contention(self):
        payload = self.http.payload("alpha")
        program = """import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from common.lifecycle_lease import acquire_lease
with acquire_lease(system_root=Path(sys.argv[2]), trusted_uid=os.getuid()):
    print('held', flush=True)
    sys.stdin.readline()
"""
        process = subprocess.Popen([sys.executable, "-c", program, str(ROOT / "scripts"), str(self.root)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(select.select([process.stdout], [], [], 2)[0])
            self.assertEqual(process.stdout.readline().strip(), "held")
            self.assert_error(self.http.request("POST", "/control/v1/switch", payload, "external-busy"),
                              409, "lifecycle_busy")
            self.assertEqual(self.http.backend.calls, [])
            self.assertEqual(self.http.backend.start_count, 0)
        finally:
            process.communicate("release\n", timeout=2)
        code, receipt = self.http.request("POST", "/control/v1/switch", payload, "after-external")
        self.assertEqual(code, 202)
        self.assertEqual(self.http.finish(receipt)["status"], "succeeded")

    def test_stale_generation_and_identity_rejected(self):
        state = self.http.status()
        bad_generation = {"deployment_id": "alpha", "allow_interrupt": False,
                          "expected_active": None, "expected_generation": state["generation"] + 1}
        self.assert_error(self.http.request("POST", "/control/v1/switch", bad_generation, "stale-gen"), 409, "stale_state")
        self.assertEqual(self.http.switch("alpha", "first")["status"], "succeeded")
        payload = self.http.payload("beta", True)
        payload["expected_active"] = "f" * 64
        self.assert_error(self.http.request("POST", "/control/v1/switch", payload, "stale-id"), 409, "stale_state")
        self.assertEqual(self.http.backend.start_count, 1)

    def test_same_profile_external_restart_changes_identity_and_generation(self):
        self.http.switch("alpha", "first")
        payload = self.http.payload("beta", True)
        before = self.http.status()
        self.http.backend.external_restart("alpha")
        self.assert_error(self.http.request("POST", "/control/v1/switch", payload, "external-stale"), 409, "stale_state")
        after = self.http.status()
        self.assertEqual(after["selected"], "alpha")
        self.assertNotEqual(before["active_identity"], after["active_identity"])
        self.assertGreater(after["generation"], before["generation"])
        generation = after["generation"]
        self.assertEqual(self.http.status()["generation"], generation)
        self.assertEqual(self.http.status()["generation"], generation)

    def test_interruption_acknowledgment_required_before_work(self):
        self.http.switch("alpha", "first")
        old = deepcopy(self.http.backend.state)
        calls = len(self.http.backend.calls)
        self.assert_error(self.http.request("POST", "/control/v1/switch", self.http.payload("beta"), "no-ack"),
                          409, "interruption_ack_required")
        self.assertEqual(self.http.backend.state, old)
        self.assertEqual([call[0] for call in self.http.backend.calls[calls:]], ["admission"])

    def test_target_full_preflight_precedes_old_stop_and_one_lease(self):
        self.http.switch("alpha", "first")
        offset = len(self.http.backend.calls)
        outcome = self.http.switch("beta", "second", True)
        self.assertEqual(outcome["status"], "succeeded")
        calls = self.http.backend.calls[offset:]
        self.assertEqual([call[0] for call in calls], ["admission", "preflight", "stop", "select", "start"])
        self.assertEqual(len({(call[2], call[3]) for call in calls}), 1)
        self.assertEqual(self.http.backend.state["selected"], "beta")
        self.assertEqual(self.http.backend.max_running, 1)

    def test_failed_target_preflight_leaves_old_backend_running(self):
        self.http.switch("alpha", "first")
        old = deepcopy(self.http.backend.state)
        self.http.backend.fail_preflight = True
        offset = len(self.http.backend.calls)
        outcome = self.http.switch("beta", "bad-preflight", True)
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["failure_code"], "preflight_failed")
        self.assertEqual(self.http.backend.state, old)
        self.assertEqual([call[0] for call in self.http.backend.calls[offset:]], ["admission", "preflight"])

    def test_failed_stop_proof_prevents_second_start(self):
        self.http.switch("alpha", "first")
        self.http.backend.fail_stop = True
        outcome = self.http.switch("beta", "bad-stop", True)
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["failure_code"], "stop_not_proven")
        self.assertEqual(self.http.backend.start_count, 1)
        self.assertEqual(self.http.backend.state["selected"], "alpha")

    def test_failed_start_reports_actual_outcome_without_resurrection(self):
        self.http.switch("alpha", "first")
        self.http.backend.fail_start = True
        offset = len(self.http.backend.calls)
        outcome = self.http.switch("beta", "failed-start", True)
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["failure_code"], "start_failed")
        self.assertEqual(outcome["observed"]["selected"], "beta")
        self.assertFalse(outcome["observed"]["container_running"])
        self.assertIsNone(outcome["observed"]["active_identity"])
        self.assertEqual([call[0] for call in self.http.backend.calls[offset:]], ["admission", "preflight", "stop", "select", "start"])
        self.assertEqual(self.http.backend.start_count, 2)

    def test_idempotency_replay_during_loading_and_after_completion(self):
        self.http.backend.release_start.clear()
        payload = self.http.payload("alpha")
        code, receipt = self.http.request("POST", "/control/v1/switch", payload, "same-key")
        self.assertEqual(code, 202)
        self.assertTrue(self.http.backend.start_entered.wait(1))
        code, replay = self.http.request("POST", "/control/v1/switch", payload, "same-key")
        self.assertEqual(code, 202)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation"]["id"], receipt["operation"]["id"])
        changed = dict(payload, deployment_id="beta")
        self.assert_error(self.http.request("POST", "/control/v1/switch", changed, "same-key"), 409, "idempotency_conflict")
        self.http.backend.release_start.set()
        self.assertEqual(self.http.finish(receipt)["status"], "succeeded")
        code, replay = self.http.request("POST", "/control/v1/switch", payload, "same-key")
        self.assertEqual(code, 202)
        self.assertEqual(replay["operation"]["id"], receipt["operation"]["id"])
        self.assertEqual(self.http.backend.start_count, 1)

    def test_journal_restart_reconciles_interrupted_without_replay(self):
        self.http.switch("alpha", "first")
        backend = self.http.backend
        self.http.close()
        saved = self.http.store.read()
        previous = next(iter(saved["entries"].values()))
        interrupted = deepcopy(previous)
        opid = "b" * 32
        interrupted.update(id=opid, status="running", target="beta", completed_at=None,
                           request_digest="c" * 64, idempotency_digest="d" * 64,
                           poll_url="/control/v1/operations/" + opid)
        saved["entries"][opid] = interrupted
        self.http.store.write(saved)
        resumed = HTTPHarness(self.root, backend=backend)
        self.addCleanup(resumed.close)
        code, operation = resumed.request(path=interrupted["poll_url"])
        self.assertEqual(code, 200)
        self.assertEqual(operation["status"], "interrupted")
        self.assertEqual(operation["failure_code"], "service_interrupted")
        self.assertEqual(operation["observed"]["selected"], "alpha")
        self.assertEqual(resumed.store.read()["entries"][opid]["status"], "interrupted")
        self.assertEqual(backend.start_count, 1)

    def test_idempotency_survives_real_journal_restart(self):
        payload = self.http.payload("alpha")
        code, receipt = self.http.request("POST", "/control/v1/switch", payload, "durable-key")
        self.assertEqual(code, 202)
        self.http.finish(receipt)
        backend = self.http.backend
        self.http.close()
        resumed = HTTPHarness(self.root, backend=backend)
        self.addCleanup(resumed.close)
        code, replay = resumed.request("POST", "/control/v1/switch", payload, "durable-key")
        self.assertEqual(code, 202)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation"]["id"], receipt["operation"]["id"])
        self.assertEqual(backend.start_count, 1)

    def test_storage_loss_blocks_normal_mutation_but_exact_trusted_stop_succeeds(self):
        self.http.switch("alpha", "first")
        payload = self.http.payload()
        before = self.http.store.read()
        self.http.backend.storage_available = False
        state = self.http.status()
        self.assertEqual(state["observed"], "unavailable")
        self.assertFalse(state["state_persisted"])
        switch = dict(payload, deployment_id="beta", allow_interrupt=True)
        self.assert_error(self.http.request("POST", "/control/v1/switch", switch, "no-storage-start"), 503, "storage_unavailable")
        code, receipt = self.http.request("POST", "/control/v1/stop", payload, "trusted-stop")
        self.assertEqual(code, 202)
        self.assertFalse(receipt["state_persisted"])
        operation = self.http.finish(receipt)
        self.assertEqual(operation["status"], "succeeded")
        self.assertFalse(operation["state_persisted"])
        self.assertFalse(operation["observed"]["container_running"])
        self.assertFalse(operation["observed"]["state_persisted"])
        self.assertEqual(self.http.store.read(), before)
        self.assertEqual(self.http.backend.calls[-1][0], "recover-stop")
        self.assertEqual(self.http.backend.start_count, 1)

    def test_restart_during_storage_loss_exposes_exact_trusted_stop_identity(self):
        self.http.switch("alpha", "first")
        original_identity = self.http.status()["active_identity"]
        backend = self.http.backend
        self.http.close()
        backend.storage_available = False
        resumed = HTTPHarness(self.root, backend=backend)
        self.addCleanup(resumed.close)
        status = resumed.status()
        self.assertEqual(status["observed"], "unavailable")
        self.assertEqual(status["active_identity"], original_identity)
        self.assertIsInstance(status["generation"], int)
        self.assertGreater(status["generation"], 0)
        self.assertFalse(status["state_persisted"])
        self.assertFalse(status["storage_available"])
        payload = {"expected_active": status["active_identity"], "expected_generation": status["generation"]}
        code, receipt = resumed.request("POST", "/control/v1/stop", payload, "restart-trusted-stop")
        self.assertEqual(code, 202)
        self.assertFalse(receipt["state_persisted"])
        operation = resumed.finish(receipt)
        self.assertEqual(operation["status"], "succeeded")
        self.assertFalse(operation["state_persisted"])
        self.assertFalse(operation["observed"]["container_running"])
        self.assertEqual(backend.calls[-1][0], "recover-stop")
        self.assertEqual(backend.start_count, 1)

    def test_storage_loss_recovery_rejects_changed_immutable_identity(self):
        self.http.switch("alpha", "first")
        payload = self.http.payload()
        saved = self.http.backend.recovery.read()
        saved["container"]["id"] = "different-immutable-container"
        self.http.backend.recovery.write(saved)
        self.http.backend.storage_available = False
        offset = len(self.http.backend.calls)
        self.assert_error(self.http.request("POST", "/control/v1/stop", payload, "bad-recovery"),
                          503, "recovery_identity_unavailable")
        self.assertEqual(len(self.http.backend.calls), offset)
        self.assertTrue(self.http.backend.state["container_running"])

    def test_storage_loss_recovery_rejects_symlink_and_missing_identity_journal(self):
        self.http.switch("alpha", "first")
        payload = self.http.payload()
        self.http.backend.storage_available = False
        recovery = self.http.backend.recovery.path
        recovery.unlink()
        self.assert_error(self.http.request("POST", "/control/v1/stop", payload, "missing-recovery"),
                          503, "recovery_identity_unavailable")
        recovery.symlink_to(self.http.store.path)
        self.assert_error(self.http.request("POST", "/control/v1/stop", payload, "symlink-recovery"),
                          503, "recovery_identity_unavailable")
        self.assertTrue(self.http.backend.state["container_running"])

    def test_full_journal_still_allows_volatile_exact_trusted_stop(self):
        self.http.close()
        self.http = HTTPHarness(self.root, backend=self.http.backend, max_entries=1)
        self.addCleanup(self.http.close)
        self.http.switch("alpha", "fill-journal")
        payload = self.http.payload()
        original_entries = self.http.store.read()["entries"]
        self.assertEqual(len(original_entries), 1)
        switch = dict(payload, deployment_id="beta", allow_interrupt=True)
        self.assert_error(self.http.request("POST", "/control/v1/switch", switch, "journal-full"), 503, "journal_full")
        self.http.backend.storage_available = False
        code, receipt = self.http.request("POST", "/control/v1/stop", payload, "full-trusted-stop")
        self.assertEqual(code, 202)
        self.assertFalse(receipt["state_persisted"])
        operation = self.http.finish(receipt)
        self.assertEqual(operation["status"], "succeeded")
        self.assertFalse(operation["state_persisted"])
        self.assertEqual(self.http.store.read()["entries"], original_entries)
        self.assertEqual(self.http.backend.start_count, 1)

    def test_full_durable_journal_stop_preserves_keys_with_storage_still_available(self):
        self.http.close()
        self.http = HTTPHarness(self.root, backend=self.http.backend, max_entries=1)
        self.addCleanup(self.http.close)
        self.http.switch("alpha", "fill-journal")
        payload = self.http.payload()
        original_entries = self.http.store.read()["entries"]
        self.assertTrue(self.http.backend.storage_available)
        code, receipt = self.http.request("POST", "/control/v1/stop", payload, "capacity-trusted-stop")
        self.assertEqual(code, 202)
        self.assertFalse(receipt["state_persisted"])
        operation = self.http.finish(receipt)
        self.assertEqual(operation["status"], "succeeded")
        self.assertFalse(operation["state_persisted"])
        self.assertFalse(operation["observed"]["container_running"])
        self.assertEqual(self.http.store.read()["entries"], original_entries)
        self.assertEqual(self.http.backend.calls[-1][0], "recover-stop")

    def _stop_write_failure(self, phase):
        self.http.switch("alpha", "first")
        payload = self.http.payload()
        original_write = self.http.store.write
        failures = []
        def fail_phase(value):
            if any(op["kind"] == "stop" and op["status"] == phase for op in value["entries"].values()):
                failures.append(phase)
                raise OSError("synthetic operation-write failure")
            original_write(value)
        self.assertTrue(self.http.backend.storage_available)
        with patch.object(self.http.store, "write", side_effect=fail_phase):
            code, receipt = self.http.request("POST", "/control/v1/stop", payload, "write-failure-stop")
            self.assertEqual(code, 202)
            if phase == "pending":
                self.assertFalse(receipt["state_persisted"])
            operation = self.http.finish(receipt)
        self.assertTrue(failures)
        self.assertEqual(operation["status"], "succeeded")
        self.assertFalse(operation["state_persisted"])
        self.assertFalse(operation["observed"]["container_running"])
        self.assertEqual(self.http.backend.calls[-1][0], "recover-stop")
        self.assertEqual(self.http.backend.start_count, 1)

    def test_stop_pending_receipt_write_failure_uses_exact_volatile_recovery(self):
        self._stop_write_failure("pending")

    def test_stop_running_update_write_failure_uses_exact_volatile_recovery(self):
        self._stop_write_failure("running")

    def test_unknown_uninstalled_and_arbitrary_inputs_rejected(self):
        payload = self.http.payload("alpha")
        for field, value in (("path", "/arbitrary"), ("command", "arbitrary-command"),
                             ("env", {"ANY": "value"}), ("flags", ["--anything"]),
                             ("image", "arbitrary-image"), ("config", {"unsafe": True}),
                             ("profile", "untrusted"), ("bootstrap", True)):
            self.assert_error(self.http.request("POST", "/control/v1/switch", dict(payload, **{field: value}), "forbidden-" + field),
                              400, "invalid_request")
        for deployment in ("../secret", "/etc/passwd", "alpha;command", "x" * 100):
            self.assert_error(self.http.request("POST", "/control/v1/switch", dict(payload, deployment_id=deployment), "bad-id"),
                              400, "invalid_request")
        self.assert_error(self.http.request("POST", "/control/v1/switch", dict(payload, deployment_id="unknown"), "unknown"),
                          404, "unknown_deployment")
        self.assert_error(self.http.request("POST", "/control/v1/switch", dict(payload, deployment_id="q38-research"), "research"),
                          409, "target_unavailable")
        self.assertEqual(self.http.backend.start_count, 0)

    def test_stop_receipt_reports_stopped_and_generation_advances(self):
        self.http.switch("alpha", "first")
        payload = self.http.payload()
        code, receipt = self.http.request("POST", "/control/v1/stop", payload, "ordinary-stop")
        self.assertEqual(code, 202)
        operation = self.http.finish(receipt)
        self.assertEqual(operation["status"], "succeeded")
        self.assertIsNone(operation["active_identity"])
        self.assertFalse(operation["observed"]["container_running"])
        self.assertGreater(operation["generation"], payload["expected_generation"])
        self.assertTrue(operation["state_persisted"])


if __name__ == "__main__":
    unittest.main()
