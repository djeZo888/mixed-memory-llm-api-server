"""Synthetic offline synchronization tests; no network or model use."""
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark.workload import execute_mixed


def jobs():
    return [{"id": "g", "model": "glm", "arrival_s": 0, "fixture_sha256": "a" * 64}] + [
        {"id": f"q{i}", "model": "qwen", "arrival_s": 0, "fixture_sha256": "b" * 64} for i in range(4)]


class Workload(unittest.TestCase):
    def test_a_serial_qwen_then_switch_glm(self):
        events = []
        def request(job):
            events.append(job["id"])
            return {"status": "PASS"}
        result = execute_mixed(jobs(), "A", request, lambda: events.append("switch"))
        self.assertEqual(events, ["q0", "q1", "q2", "q3", "switch", "g"])
        self.assertEqual(result["status"], "COMPLETE")

    def test_b_overlaps_models_but_serializes_qwen(self):
        barrier = threading.Barrier(2)
        events = []
        def request(job):
            if job["id"] in ("g", "q0"):
                barrier.wait(timeout=2)
            events.append(job["id"])
            return {"status": "PASS"}
        result = execute_mixed(jobs(), "B", request, lambda: self.fail("B must not switch"))
        self.assertEqual([j for j in events if j.startswith("q")], ["q0", "q1", "q2", "q3"])
        self.assertEqual(result["status"], "COMPLETE")

    def test_b_report_failure_does_not_cancel_other_model(self):
        barrier = threading.Barrier(2)
        drained = []
        def request(job):
            barrier.wait(timeout=2)
            if job["id"] == "q0":
                raise ValueError("synthetic parser error")
            drained.append(job["id"])
            return {"status": "PASS"}
        result = execute_mixed(jobs(), "B", request, lambda: None)
        self.assertEqual(drained, ["g"])
        self.assertEqual(result["skipped_ids"], ["q1", "q2", "q3"])
        self.assertEqual(result["status"], "INCOMPLETE_REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
