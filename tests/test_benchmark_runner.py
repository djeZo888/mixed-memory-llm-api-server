"""Actual integrated worker loop, fake host/runtime; SYNTHETIC OFFLINE ONLY."""
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import fixtures, profiles, runner, telemetry
from benchmark.campaign import CampaignBudget


def synthetic_demand():
    return telemetry.required_host_demand({"anon_bytes": 48 * 1024**3, "kernel_bytes": 1 * 1024**3,
        "file_bytes": 200 * 1024**3, "file_mapped_bytes": 1 * 1024**3, "shmem_bytes": 0,
        "current_bytes": 249 * 1024**3}, required_file_backed_bytes=1 * 1024**3,
        host_workspace_bytes=1024, file_basis="synthetic_offline_mapped_weights")


class Host:
    def __init__(self, manifests, path):
        self.manifests = {fixtures.digest(fixtures.canonical(m)): m for m in manifests}
        self.active, self.events, self.sequence = {}, [], 0
        self.budget = CampaignBudget(path, before_write=lambda: None, after_write=lambda: None)

    def call(self, op, **args):
        self.events.append((op, args))
        if op == "begin":
            if self.budget.data is None:
                self.budget.start("maintenance")
            return {}
        if op == "load":
            m = self.manifests[args["manifest_sha256"]]
            self.sequence += 1;cid = f"{self.sequence:064x}";self.active[cid] = m
            return {"id": cid}
        if op == "readiness":
            return {"ready": True, "allocation": {"status": "ALLOCATION_PROOF_ACCEPTED", "evidence": "synthetic_offline"}, "template_sha256": "a" * 64}
        if op == "quiescent":
            return {"evidence": "synthetic_offline", "point": args["point"], "pss_bytes": 100}
        if op == "telemetry":
            cid = args["id"]
            return {"timestamp_monotonic_s": time.monotonic(), "collection_duration_s": .001,
                    "host": {"available_bytes": 800 * 1024**3}, "vmstat": {},
                    "required_host_demand": synthetic_demand(),
                    "cgroups": {cid: {"swap_bytes": 0, "current_bytes": 50 * 1024**3,
                                     "events": {"oom": 0, "oom_kill": 0, "oom_group_kill": 0}}},
                    "gpus": [{"uuid": u, "free_bytes": 40 * 1024**3} for u in profiles.read_config()["gpu_uuids"]]}
        if op == "request_begin":
            return {"timeout_s": self.budget.request_timeout(args["timeout_s"])}
        if op == "budget":
            return {"remaining_s": self.budget.checkpoint()}
        if op in ("request_end", "status"):
            return {}
        if op == "retire":
            del self.active[args["id"]];return {}
        if op == "admit_mixed":
            caps = profiles.split_resources(synthetic_demand(), synthetic_demand(), 800 * 1024**3)
            manifests = [profiles.command_manifest(p, n, mixed=True, ram_cap=caps[p]) for p, n in (("G1", 65536), ("Q1", 16384))]
            for m in manifests:
                self.manifests[fixtures.digest(fixtures.canonical(m))] = m
            return {"manifests": manifests}
        if op == "restore":
            self.active.clear();return {"phase": "POST_RELEASE_LAN_VERIFICATION_PENDING"}
        raise AssertionError(op)


def mock_runtime(host, requests):
    def manifest(url):
        port = int(url.rsplit(":", 1)[1])
        return next(m for m in host.active.values() if m["transport"]["port"] == port)
    def native(url, key, timeout=120):
        def call(path, body):
            m = manifest(url)
            if path == "/props":
                return {"model_alias": "bench-glm-5.3", "is_sleeping": False, "total_slots": 1,
                        "default_generation_settings": {"n_ctx": m["configured_capacity"]}, "chat_template": "synthetic-template", "chat_template_tool_use": "synthetic-tool-template"}
            if path == "/apply-template":
                return {"prompt": json.dumps(body)}
            text = body["content"] if path == "/tokenize" else json.dumps(body)
            count = text.count("record=") * 15 + 80
            return {"tokens": [1] * count, "count": count, "max_model_len": 262144}
        return call
    def transport(url, key):
        def send(raw, timeout):
            body = json.loads(raw);requests.append(body)
            model = body["model"]
            source = body["messages"][0]["content"]
            answer = dict(re.findall(r"marker=(START|MIDDLE|END); value=([a-zA-Z0-9_-]+);", source))
            if body.get("tools") and body.get("tool_choice") == "auto":
                delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "actual-capped-call", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"result.json"}'}}]}
                finish = "length"  # Representative valid capped tool call.
            else:
                if body["messages"][-1]["role"] == "tool":
                    answer.update(json.loads(body["messages"][-1]["content"]))
                if body["max_tokens"] == 512:
                    answer["commentary"] = "Synthetic archive analysis."
                delta = {"role": "assistant", "content": json.dumps(answer)};finish = "stop"
            for event in [{"model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                          {"model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                          {"model": model, "choices": [], "usage": {"prompt_tokens": 3000, "completion_tokens": 32, "prompt_tokens_details": {"cached_tokens": 10}},
                           "timings": {"prompt_n": 2990, "predicted_n": 32, "prompt_ms": 15, "predicted_ms": 20}}]:
                yield b"data: " + fixtures.canonical(event) + b"\n\n"
            yield b"data: [DONE]\n\n"
        return send
    return transport, native


class IntegratedRunner(unittest.TestCase):
    def setup_case(self, path, manifests=None):
        manifests = manifests or [profiles.command_manifest(p, n) for p in ("Q2", "Q1", "G2", "G1") for n in (4096, 16384, 65536)]
        arm = {"manifests": manifests, "trial_plan": profiles.trial_order()}
        runner.save(path / "progress.json", {"phase": "ARMED", "completed": {}, "inflight": {}, "errors": []})
        host = Host(manifests, path / "budget.json");requests = []
        transport, native = mock_runtime(host, requests)
        c = runner.Campaign(path, arm, host, "synthetic-key", transport_factory=transport, json_factory=native)
        return c, host, requests

    def test_actual_full_loop_native_counts_tools_mixed_automatic_paths_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory);c, host, requests = self.setup_case(p)
            c.run()
            state = json.loads((p / "progress.json").read_bytes())
            self.assertEqual(state["phase"], "RESTORED_PENDING_WORKER_VERIFICATION")
            self.assertFalse(state["inflight"])
            self.assertEqual(state["completed"]["mixed-B"]["status"], "COMPLETE")
            tool = state["completed"]["Q2-16384-tool"]
            self.assertEqual(tool["status"], "PASS")
            self.assertEqual(tool["sample"]["status"], "OUTPUT_LIMIT")
            self.assertEqual(tool["sample"]["counters"]["cached_tokens"], 10)
            self.assertEqual(tool["count"]["tokenizer_max_model_len"], 262144)
            self.assertEqual(tool["count"]["configured_context"], 16384)
            self.assertTrue((p / "results.jsonl").exists())
            self.assertTrue((p / "private" / "Q2-16384-tool-continuation.response.sse").exists())
            for r in requests:
                if r["messages"][0]["content"].startswith("trial-prefix=warmup-"):
                    self.assertIn("warmup-prefix-", r["messages"][0]["content"])
            before = len(requests)
            resumed = runner.Campaign(p, c.armed, host, "synthetic-key", transport_factory=c.transport_factory, json_factory=c.json_factory)
            resumed.run(resume=True)
            self.assertEqual(len(requests), before, "completed measurements must never rerun automatically")

    def test_interrupted_trial_refuses_before_any_host_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory))
            c.progress["inflight"]["old-trial"] = {}
            with self.assertRaisesRegex(RuntimeError, "inflight"):
                c.run(resume=True)
            self.assertEqual(host.events, [])

    def test_valid_parsed_answer_with_failed_observer_remains_harness_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory))
            host.call("begin")
            cid = c.loaded(c.armed["manifests"][0])
            original = c.request
            def request(*args, **kwargs):
                response = original(*args, **kwargs)
                self.assertEqual(response["parsed"]["status"], "COMPLETE")
                response["summary"]["status"] = "HARNESS_FAILURE"
                response["summary"]["report_errors"] = ["stream_timing_observer_failed"]
                return response
            c.request = request
            result = c.trial(cid, "synthetic-observer-failure")
            self.assertEqual(result["status"], "HARNESS_FAILURE")
            self.assertEqual(result["sample"]["status"], "HARNESS_FAILURE")
            self.assertIn("synthetic-observer-failure", c.progress["completed"])
            self.assertFalse(any(op == "retire" for op, _ in host.events))
            c.restore()

    def test_failed_or_partial_mixed_resume_refuses_before_host_mutation(self):
        for completed in ({"Q2-4096-retrieval": {"status": "MODEL_INCORRECT"}}, {"mixed-A-qwen16k-0": {"status": "PASS"}}):
            with tempfile.TemporaryDirectory() as directory:
                c, host, requests = self.setup_case(Path(directory))
                c.progress["completed"] = completed
                with self.assertRaises(RuntimeError):
                    c.run(resume=True)
                self.assertEqual(host.events, [])

    def test_mixed_prefits_all_jobs_outside_schedule_and_freezes_matching_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory))
            host.call("begin")
            executing = [False]
            original_prepare, original_dispatch = c.prepare_trial, runner.workload.execute_mixed
            prepared_ids, group_hashes = [], {}
            def prepare(*args, **kwargs):
                self.assertFalse(executing[0], "fixture fitting/counting inside arrival schedule")
                result = original_prepare(*args, **kwargs)
                prepared_ids.append(args[1]);return result
            def dispatch(jobs, mode, run, switch):
                self.assertEqual(len([x for x in prepared_ids if x.startswith("mixed-" + mode + "-")]), 5)
                group_hashes[mode] = {j["id"]: j["fixture_sha256"] for j in jobs}
                executing[0] = True
                try: return original_dispatch(jobs, mode, run, switch)
                finally: executing[0] = False
            c.prepare_trial = prepare
            with patch.object(runner.workload, "execute_mixed", side_effect=dispatch):
                c.mixed()
            self.assertEqual(group_hashes["A"], group_hashes["B"])
            records = [json.loads(line) for line in (Path(directory) / "results.jsonl").read_text().splitlines()]
            self.assertEqual(len([row for row in records if row["type"] == "mixed_admission"]), 1)
            for mode in ("A", "B"):
                self.assertEqual(c.progress["groups"]["mixed-" + mode]["measurement"], "COMPLETE")
            c.restore()

    def test_load_samples_register_before_readiness_and_survive_warm_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory));host.call("begin")
            original = host.call
            ready_calls = []
            def call(op, **args):
                if op == "readiness":
                    cid = args["id"]
                    self.assertIn(cid, c.active)
                    self.assertEqual(c.active[cid]["phase"], "loading")
                    self.assertTrue(c.samples[cid])
                    ready_calls.append(cid)
                return original(op, **args)
            host.call = call
            cid = c.loaded(c.armed["manifests"][0])
            self.assertEqual(ready_calls, [cid])
            self.assertEqual(c.active[cid]["phase"], "ready")
            self.assertGreaterEqual(len(c.samples[cid]), 2)
            c.restore()

    def test_load_readiness_deadline_uses_remaining_budget_and_prompt_failure(self):
        for scenario in ("empty", "load_overrun", "readiness_overrun", "oom"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                c, host, requests = self.setup_case(Path(directory));host.call("begin")
                now = [100.0];c.clock = lambda: now[0]
                original = host.call
                def call(op, **args):
                    if op == "budget": return {"remaining_s": 0 if scenario == "empty" else 2}
                    if op == "load" and scenario == "load_overrun": now[0] += 3
                    if op == "readiness":
                        self.assertLessEqual(args["timeout_s"], 2)
                        if scenario == "readiness_overrun": now[0] += 3
                        if scenario == "oom": return {"ready": False, "failed": True, "status": "STOP_OOM"}
                    return original(op, **args)
                host.call = call
                with self.assertRaisesRegex(RuntimeError, "STOP_OOM" if scenario == "oom" else "STOP_BUDGET"):
                    c.loaded(c.armed["manifests"][0])
                self.assertFalse(requests)
                self.assertLessEqual(len([op for op, _ in host.events if op == "readiness"]), 1)

    def test_warmup_evaluated_prefill_and_output_required(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory));host.call("begin")
            original = c.request
            def insufficient(*args, **kwargs):
                response = original(*args, **kwargs)
                response["parsed"]["counters"]["evaluated_prompt_tokens"] = 1024
                return response
            c.request = insufficient
            with self.assertRaisesRegex(RuntimeError, "WARMUP_PREFILL_UNPROVED"):
                c.loaded(c.armed["manifests"][0])
            self.assertEqual(len(requests), 1)
            self.assertTrue(requests[0]["messages"][0]["content"].startswith("trial-prefix=warmup-"))

    def test_preparing_group_interruption_is_missing_and_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory))
            c.progress["groups"] = {"mixed-A": {"state": "PREPARING", "measurement": "MISSING"}}
            c.record()
            with self.assertRaisesRegex(RuntimeError, "missing_measurement"):
                c.run(resume=True)
            self.assertFalse(host.events)

    def test_sample_safety_oom_blocks_next_admission_without_stopping_healthy_request(self):
        with tempfile.TemporaryDirectory() as directory:
            c, host, requests = self.setup_case(Path(directory))
            host.call("begin");cid = c.loaded(c.armed["manifests"][0])
            original = host.call
            def call(op, **args):
                value = original(op, **args)
                if op == "telemetry":
                    value["cgroups"][cid]["events"]["oom_kill"] = 1
                return value
            host.call = call;c.collect()
            with self.assertRaisesRegex(RuntimeError, "STOP_OOM"):
                c.admission(cid)
            self.assertFalse(any(op == "retire" for op, _ in host.events))
            c.restore()


if __name__ == "__main__":
    unittest.main()
