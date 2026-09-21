"""Synthetic offline final worker receipt contract; no live HTTP or VM use."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import worker_verify as w
from benchmark.fixtures import canonical


def status(*, selected="qwen38-27b-1000000-yarn4-tp2-bf16kv", desired="running", active="active"):
    return {"nonce": "a" * 32, "worker_nonce": "a" * 32, "restored_at": 100,
            "original": {"manager": {"selected": selected, "desired": desired},
                         "services": {"llm-control.service": {"active": active}}}}


class WorkerReceiptTests(unittest.TestCase):
    def test_matching_nonce_checks_schema_and_qwen_private_routes(self):
        state = status()
        calls = []
        def call(port, path, key, payload=None):
            calls.append((port, path, key, payload))
            if port == 30000:
                return {**state["original"]["manager"], "observed": "ready", "current_operation": None}
            return {"model": "qwen3.8-27b", "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]}
        with patch.object(w.time, "time", return_value=123):
            receipt = w.verify(state, "synthetic-inference-key", "synthetic-control-key", call=call)
        self.assertEqual(receipt["nonce"], state["nonce"])
        self.assertEqual(receipt["verified_at"], 123)
        self.assertGreaterEqual(receipt["verified_at"], state["restored_at"])
        self.assertEqual(receipt["original_sha256"], hashlib.sha256(canonical(state["original"])).hexdigest())
        self.assertEqual(receipt["checks"], {"worker_source": "mac-worker1", "transport": "private_lan",
                         "worker_lan_control_authenticated": True, "worker_lan_inference_authenticated": True})
        self.assertEqual([(row[0], row[1]) for row in calls], [(30000, "/control/v1/status"), (30004, "/v1/chat/completions")])
        self.assertEqual(calls[0][2], "synthetic-control-key")
        self.assertEqual(calls[1][2], "synthetic-inference-key")
        self.assertNotIn("synthetic-", str(receipt))
        self.assertEqual(calls[1][3]["model"], "qwen3.8-27b")

    def test_original_glm_selects_glm_route_and_alias(self):
        state = status(selected="glm-5.3-ud-q4-k-xl-n76-native1m")
        calls = []
        def call(port, path, key, payload=None):
            calls.append((port, payload))
            if port == 30000:
                return {**state["original"]["manager"], "observed": "ready", "current_operation": None}
            return {"model": "glm-5.3", "choices": [{"message": {"content": "OK"}}]}
        receipt = w.verify(state, "i", "c", call=call)
        self.assertEqual(calls[-1][0], 30002)
        self.assertEqual(calls[-1][1]["model"], "glm-5.3")
        self.assertEqual(calls[-1][1]["reasoning_effort"], "low")
        self.assertIs(receipt["checks"]["worker_lan_inference_authenticated"], True)

    def test_stopped_original_never_requests_inference_or_inactive_control(self):
        state = status(selected=None, desired="stopped", active="inactive")
        calls = []
        receipt = w.verify(state, "i", "c", call=lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(receipt["checks"]["worker_lan_inference_authenticated"], "NOT_APPLICABLE_STOPPED_INTENT")
        self.assertEqual(receipt["checks"]["worker_lan_control_authenticated"], "NOT_APPLICABLE_CONTROL_INACTIVE")

    def test_intent_drift_not_ready_or_pending_control_operation_refused(self):
        state = status()
        good = {**state["original"]["manager"], "observed": "ready", "current_operation": None}
        for change in ({"selected": "different"}, {"desired": "stopped"}, {"observed": "starting"}, {"current_operation": {"id": "busy"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                w.verify(state, "i", "c", call=lambda *args: {**good, **change})

    def test_wrong_inference_model_or_empty_choices_refused(self):
        state = status(active="inactive")
        for reply in ({"model": "wrong", "choices": [{}]}, {"model": "qwen3.8-27b", "choices": []}):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                w.verify(state, "i", "c", call=lambda *args: reply)

    def test_invalid_nonce_refused_before_network_callback(self):
        for nonce in ("short", None, 42):
            state = status()
            state["nonce"] = nonce
            calls = []
            with self.subTest(nonce=nonce), self.assertRaises(ValueError):
                w.verify(state, "i", "c", call=lambda *args: calls.append(args))
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
