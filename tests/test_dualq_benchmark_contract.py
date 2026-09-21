"""Closed dual-Q seams only; no host, image, model, HTTP or owner execution."""
import copy
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import accounting, dualq_480k as dual, fixtures, profiles, qwen_launcher
from benchmark.concurrent_cpu_run import TEMPLATES
from tests.test_benchmark_qwen_adapter import fixture


def flag(args, name):
    return args[args.index(name) + 1]


def count(raw, tokens=479487):
    # Synthetic value in an injected callback, not a claimed native observation.
    return {"source": "native_chat_tokenize", "body_sha256": fixtures.digest(raw),
            "configured_context": 480000, "input_tokens": tokens,
            "template_sha256": TEMPLATES["Q1"], "token_ids_sha256": "b" * 64}


class DualQContract(unittest.TestCase):
    def jobs(self):
        return [dual.prepare_job(slot, "fresh-offline-" + slot, count) for slot in dual.SLOTS]

    def test_closed_manifests_distinguish_gpu_port_alias_and_writes(self):
        q0, q1 = [dual.manifest(slot) for slot in dual.SLOTS]
        for index, value in enumerate((q0, q1)):
            args = value["create_argv"]
            self.assertEqual(value["gpu_uuids"], [profiles.read_config()["gpu_uuids"][index]])
            self.assertEqual(value["guest_cpuset"], "0-7")
            self.assertEqual((value["guest_total_vcpus"], value["active_guest_vcpus"]), (72, 8))
            self.assertEqual(flag(args, "--memory"), str(32 * 1024**3))
            self.assertEqual(flag(args, "--memory-swap"), flag(args, "--memory"))
            self.assertEqual(flag(args, "--restart"), "no")
            self.assertEqual(flag(args, "--publish"), f"127.0.0.1:{31002 + index*2}:{31002 + index*2}/tcp")
            self.assertNotIn("--cpuset-mems", args)
            self.assertNotIn("--api-key", args)
            self.assertEqual(flag(value["native_argv"], "--context-length"), "480000")
            self.assertEqual(flag(value["native_argv"], "--max-total-tokens"), "480000")
            self.assertEqual(flag(value["native_argv"], "--tp-size"), "1")
            self.assertEqual(value["resource_policy"]["host_headroom_policy"]["numerator"], 23)
        for field in ("container_name", "gpu_uuids", "registered_paths", "transport"):
            self.assertNotEqual(q0[field], q1[field])
        self.assertEqual(q0["registered_paths"]["source"], q1["registered_paths"]["source"])
        self.assertEqual(q0["model"], q1["model"])
        self.assertEqual(q0["image"], q1["image"])
        self.assertNotIn(dual.SCOPE, profiles.ARM_SCOPES)
        for bad in ("G1", "Q2", "qwen", None):
            with self.assertRaises(ValueError): dual.manifest(bad)

    def test_launcher_binds_raw_and_resolved_physical_tuple(self):
        for slot in dual.SLOTS:
            base = qwen_launcher.pinned_base(profiles.ROOT / "scripts/runtime/sglang38_file_auth.py")
            port, alias = qwen_launcher.endpoint(dual.SCOPE, slot)
            argv = qwen_launcher.bind_variant(base, 480000, 1, scope=dual.SCOPE, slot=slot)
            self.assertEqual(base.parse_options(argv)[1], dual.manifest(slot)["native_argv"])
            args = fixture.args_fixture(base.EXTENSION_CONTEXT)
            args.context_length = args.max_total_tokens = 480000
            args.tp_size, args.port, args.served_model_name = 1, port, alias
            base.validate_server_args(args)
            base.validate_server_args(fixture.resolved_args_fixture(args), resolved=True)
            for name, value in (("port", 30004), ("served_model_name", "qwen3.8-27b"), ("tp_size", 2)):
                bad = copy.deepcopy(args); setattr(bad, name, value)
                with self.assertRaises(base.LaunchError): base.validate_server_args(bad)
        for scope, slot, context, tp in ((dual.SCOPE, None, 480000, 1), (None, "Q0", 4096, 1),
                                        (dual.SCOPE, "Q0", 700160, 1), (dual.SCOPE, "Q0", 480000, 2)):
            with self.assertRaises(ValueError): qwen_launcher.variant(base, context, tp, scope=scope, slot=slot)

    def test_final_body_native_recount_rejects_one_token_overflow(self):
        jobs = self.jobs()
        self.assertEqual(jobs[0]["sample"]["fixture_sha256"], jobs[1]["sample"]["fixture_sha256"])
        for job in jobs:
            self.assertEqual(job["sample"]["body"]["max_tokens"], 512)
            self.assertEqual(job["count"]["input_tokens"] + 512, 479999)
        for tokens in (479488, 480000, 479359):
            with self.assertRaisesRegex(ValueError, "no_refit"):
                dual.prepare_job("Q0", "fresh-offline-Q0", lambda raw: count(raw, tokens))
        with self.assertRaises(ValueError): dual.prepare_job("Q0", "old-prefix", count)

    def test_counter_preserves_alias_template_and_exact_body_binding(self):
        raw = self.jobs()[0]["raw"]
        calls = []
        def native(path, body):
            calls.append((path, body))
            return {"tokens": [1, 2], "count": 2, "max_model_len": 262144}
        counter = accounting.native_counter("bench-qwen3.8-27b-gpu0", 480000, native,
            qwen_template_sha256=TEMPLATES["Q1"], scope=dual.SCOPE)
        result = counter(raw)
        self.assertEqual(result["body_sha256"], fixtures.digest(raw))
        self.assertEqual(calls[0][0], "/v1/tokenize")
        self.assertEqual(calls[0][1]["model"], "bench-qwen3.8-27b-gpu0")
        self.assertNotIn("stream", calls[0][1])
        with self.assertRaises(fixtures.HarnessError): counter(self.jobs()[1]["raw"])
        with self.assertRaises(fixtures.HarnessError):
            accounting.native_counter("bench-qwen3.8-27b-gpu0", 4096, native, qwen_template_sha256=TEMPLATES["Q1"])

    def test_one_barrier_pair_no_300_second_cutoff(self):
        jobs, called, both = self.jobs(), [], threading.Barrier(2)
        def invoke(job, timeout_seconds):
            called.append((job["slot"], timeout_seconds))
            both.wait(timeout=2)
            return {"status": "PASS", "sample": {"request_started_monotonic_s": 10,
                                                   "request_ended_monotonic_s": 371}}
        result = dual.execute_pair(jobs, invoke)
        self.assertEqual(sorted(called), [("Q0", 7200), ("Q1", 7200)])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["request_overlap_seconds"], 361)
        self.assertFalse(dual.trial_plan()["expected_duration_is_limit"])
        self.assertEqual(dual.trial_plan()["measured_requests"], 2)

    def test_failed_lane_drains_peer_and_never_retries(self):
        jobs, called = self.jobs(), []
        def invoke(job, timeout_seconds):
            called.append(job["slot"])
            if job["slot"] == "Q0": raise ValueError("synthetic_failure")
            return {"status": "PASS", "sample": {"request_started_monotonic_s": 1,
                                                   "request_ended_monotonic_s": 2}}
        result = dual.execute_pair(jobs, invoke)
        self.assertEqual(sorted(called), list(dual.SLOTS))
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("Q1", result["slots"])

    def test_duplicate_routing_or_mutated_body_refused_before_dispatch(self):
        jobs = self.jobs()
        for mutate in (lambda j: j[0].update(manifest=j[1]["manifest"]),
                       lambda j: j[0]["sample"]["body"].update(max_tokens=256),
                       lambda j: j[0]["count"].update(input_tokens=479488)):
            bad = copy.deepcopy(jobs); mutate(bad)
            with self.assertRaises(ValueError): dual.execute_pair(bad, lambda *a, **k: self.fail("dispatched"))

    def test_missing_or_nonoverlapping_evidence_cannot_pass(self):
        jobs = self.jobs()
        for rows in ((None, {"status": "PASS"}),
                     ({"status": "PASS"}, {"status": "PASS"}),
                     ({"status": "PASS", "sample": {"request_started_monotonic_s": 1, "request_ended_monotonic_s": 2}},
                      {"status": "PASS", "sample": {"request_started_monotonic_s": 2, "request_ended_monotonic_s": 3}})):
            result = dual.execute_pair(jobs, lambda job, **kw: rows[dual.SLOTS.index(job["slot"])])
            self.assertEqual(result["status"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
