"""Synthetic/offline scheduling/budget/memory checks; no live operations."""
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts/benchmark/campaign.py"
spec = importlib.util.spec_from_file_location("benchmark_campaign", SOURCE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CampaignTests(unittest.TestCase):
    def budget(self, path, now, guards=None):
        guards = guards if guards is not None else []
        return c.CampaignBudget(path, clock=lambda: now[0],
                                before_write=lambda: guards.append("before"), after_write=lambda: guards.append("after"))

    def test_budget_durable_start_resume_request_limit_restoration_outside(self):
        with tempfile.TemporaryDirectory() as directory:
            path, now, guards = Path(directory) / "budget.json", [1000.0], []
            ledger = self.budget(path, now, guards)
            self.assertFalse(path.exists())
            ledger.start("maintenance")
            self.assertEqual(ledger.request_timeout(), 7200)
            with self.assertRaisesRegex(ValueError, "out_of_bounds"):
                ledger.request_timeout(7201)
            now[0] += c.BUDGET_SECONDS - 100
            resumed = self.budget(path, now)
            self.assertEqual(resumed.request_timeout(), 100)
            resumed.begin_restoration()
            now[0] += 10000
            self.assertEqual(resumed.checkpoint(), 100)
            with self.assertRaisesRegex(ValueError, "STOP_BUDGET"):
                resumed.request_timeout()
            resumed.finish_restoration(True)
            self.assertEqual(json.loads(path.read_text())["phase"], "RESTORED")
            self.assertEqual(guards, ["before", "after", "before", "after"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_budget_failure_closed_expiry_clock_and_invalid_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            path, now = Path(directory) / "budget.json", [1000.0]
            ledger = self.budget(path, now)
            with self.assertRaisesRegex(ValueError, "not_started"):
                ledger.request_timeout()
            with self.assertRaises(ValueError):
                ledger.start("preparation")
            ledger.start("model_trial")
            with self.assertRaisesRegex(ValueError, "already_started"):
                ledger.start("maintenance")
            now[0] = 999
            with self.assertRaisesRegex(ValueError, "regressed"):
                ledger.checkpoint()
            now[0] = 1000 + c.BUDGET_SECONDS
            with self.assertRaisesRegex(ValueError, "STOP_BUDGET"):
                ledger.request_timeout()
            ledger.begin_restoration()  # restoration remains allowed after expiry
            path.write_text('{"schema":1}')
            with self.assertRaisesRegex(ValueError, "invalid_budget"):
                self.budget(path, now)

    def test_guard_failure_prevents_budget_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            def refuse():
                raise RuntimeError("synthetic guard rejected")
            ledger = c.CampaignBudget(path, before_write=refuse, after_write=lambda: None)
            with self.assertRaises(RuntimeError):
                ledger.start("maintenance")
            self.assertFalse(path.exists())

    def test_anchored_callbacks_receive_payload_resume_without_local_io(self):
        storage, calls, now = {}, [], [1000.0]
        path = Path("/data/logs/benchmark-synthetic/budget.json")
        def read(target):
            calls.append(("read", target))
            return storage.get(target)
        def persist(target, payload):
            calls.append(("persist", target))
            self.assertIsInstance(payload, bytes)
            self.assertEqual(json.loads(payload)["budget_seconds"], c.BUDGET_SECONDS)
            storage[target] = payload
        options = dict(before_write=lambda: calls.append(("before", path)),
                       after_write=lambda: calls.append(("after", path)),
                       read=read, persist=persist, storage_scope="ai-vm", clock=lambda: now[0])
        # Any direct filesystem access in callback mode is a bug; these mocks
        # establish that the helpers only hand bytes to the reviewed adapter.
        with mock.patch.object(Path, "exists", side_effect=AssertionError("unanchored exists")), \
             mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unanchored read")), \
             mock.patch.object(Path, "mkdir", side_effect=AssertionError("unanchored mkdir")), \
             mock.patch.object(c.os, "open", side_effect=AssertionError("unanchored open")), \
             mock.patch.object(c.os, "replace", side_effect=AssertionError("unanchored replace")):
            ledger = c.CampaignBudget(path, **options)
            ledger.start("maintenance")
            now[0] += 10
            resumed = c.CampaignBudget(path, **options)
            self.assertEqual(resumed.checkpoint(), c.BUDGET_SECONDS - 10)
        self.assertEqual([kind for kind, target in calls],
                         ["read", "before", "persist", "after", "read", "before", "persist", "after"])
        self.assertTrue(all(target == path for kind, target in calls))

    def test_vm_scope_or_registered_path_refuses_unanchored_writer(self):
        guards = dict(before_write=lambda: None, after_write=lambda: None)
        for path, scope in [(Path("/tmp/budget.json"), "ai-vm"),
                            (Path("/data/logs/budget.json"), "worker-local")]:
            with self.assertRaisesRegex(ValueError, "requires_anchored"):
                c.CampaignBudget(path, storage_scope=scope, **guards)
        with self.assertRaisesRegex(ValueError, "paired_anchored"):
            c.CampaignBudget(Path("unused"), persist=lambda path, payload: None, **guards)

    def test_mixed_schedule_same_jobs_queue_switch_and_restore_separate(self):
        jobs = [{"id": "g", "model": "glm", "arrival_s": 0, "fixture_sha256": "a" * 64}]
        jobs += [{"id": "q" + str(i), "model": "qwen", "arrival_s": i * 2, "fixture_sha256": str(i) * 64}
                 for i in range(4)]
        durations = {"g": 30, **{"q" + str(i): 5 for i in range(4)}}
        a = c.mixed_schedule(jobs, durations, "A", switch_s=10, restore_s=7)
        b = c.mixed_schedule(jobs, durations, "B", switch_s=10, restore_s=7)
        self.assertEqual(a["makespan_s"], 60)
        self.assertEqual(b["makespan_s"], 30)
        self.assertEqual(a["return_to_original_model_s"], 7)
        self.assertEqual(a["completion_including_restoration_from_ready_s"], 67)
        self.assertEqual(b["switch_s"], 0)
        ag = next(j for j in a["timeline"] if j["id"] == "g")
        bg = next(j for j in b["timeline"] if j["id"] == "g")
        self.assertEqual(ag["queue_delay_s"], 30)
        self.assertEqual(bg["queue_delay_s"], 0)
        self.assertEqual(next(j for j in b["timeline"] if j["id"] == "q3")["queue_delay_s"], 9)
        self.assertEqual({j["id"]: j["fixture_sha256"] for j in a["timeline"]},
                         {j["id"]: j["fixture_sha256"] for j in b["timeline"]})
        with self.assertRaises(ValueError):
            c.mixed_schedule(jobs[:-1], durations, "A")

    def test_harness_failure_never_model_regression_or_retry(self):
        state = c.trial_decision(harness_valid=False, correctness_passed=False)
        self.assertEqual(state["state"], "HARNESS_FAILURE")
        self.assertFalse(state["model_correctness_attributable"])
        self.assertFalse(state["automatic_retry"])
        self.assertFalse(state["cancel_healthy_inference_for_report_error"])
        self.assertEqual(c.trial_decision(correctness_passed=False)["state"], "STOP_CORRECTNESS_REGRESSION")
        for args, expected in [({"unsafe": True}, "SKIP_UNSAFE_PLACEMENT"),
                               ({"allocation_failed": True}, "STOP_ALLOCATION_FAILURE"),
                               ({"oom": True, "harness_valid": False}, "STOP_OOM"),
                               ({"swap_growth": True}, "STOP_SUSTAINED_MODEL_SWAP_GROWTH"),
                               ({"budget_expired": True}, "STOP_BUDGET")]:
            self.assertEqual(c.trial_decision(**args)["state"], expected)

    def test_memory_model_aggregate_hypothesis_reserve_and_ram(self):
        components = {"weights_bytes": 100 * c.GIB, "runtime_bytes": 2 * c.GIB,
                      "workspace_bytes": 3 * c.GIB, "measured_host_demand_bytes": 200 * c.GIB,
                      "gpu_count": 2}
        result = c.memory_projection("glm", 65536, components,
                                      target_tokens=[131072, 262144, 524288, 1048576], published_max_tokens=1048576)
        self.assertEqual(result["projection_basis"], "unverified_cache_hypothesis")
        self.assertEqual(result["projections"][0]["cache_bytes_aggregate"], 95232 * 131072)
        self.assertEqual(result["minimum_reserve_bytes_per_gpu"], 16 * c.GIB)
        self.assertEqual(result["recommended_ram_bytes_at_measured_configuration"], 250 * c.GIB)
        self.assertEqual(result["projections"][0]["total_bytes_aggregate_including_gpu_reserve"], 137 * c.GIB + 95232 * 131072)
        observed = c.memory_projection("qwen", 16384, components, target_tokens=[131072],
                                        published_max_tokens=1000000, observed_cache_bytes=16384 * 65536)
        self.assertEqual(observed["hypothesis_relative_error"], 0)
        self.assertEqual(observed["projections"][0]["per_gpu_fit"], "NOT_ESTABLISHED")
        self.assertIsNone(observed["projections"][0]["host_ram_at_target"])
        with self.assertRaises(ValueError):
            c.memory_projection("glm", 65536, components, target_tokens=[2000000], published_max_tokens=1048576)


if __name__ == "__main__":
    unittest.main()
