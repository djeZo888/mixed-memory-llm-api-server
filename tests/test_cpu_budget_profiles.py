"""Closed CPU-layout profiles and count/fixture adapters; all offline."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark import accounting, cpu_budget_profiles as cpu, fixtures, profiles, qwen_launcher, runner


def flag(argv, name):
    return argv[argv.index(name) + 1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def counter(capacity):
    def count(raw):
        body = json.loads(raw)
        return {"source": "synthetic_offline", "input_tokens": body["messages"][0]["content"].count("record=")*32+80,
                "body_sha256": fixtures.digest(raw), "template_sha256": "a"*64,
                "token_ids_sha256": "b"*64, "configured_context": capacity}
    return count


class CpuBudgetProfiles(unittest.TestCase):
    def test_campaign_against_actual_shared_stage_contract(self):
        contracts = [node for node in ast.walk(ast.parse(runner.STAGE))
                     if isinstance(node, ast.Assert)
                     and any(isinstance(part, ast.Name) and part.id == "campaign"
                             for part in ast.walk(node))]
        self.assertEqual(len(contracts), 1)
        contract = compile(ast.Module(body=contracts, type_ignores=[]),
                           "runner.STAGE campaign assertion", "exec")
        with self.assertRaises(AssertionError):
            exec(contract, {"campaign": "benchrun-concurrent-480k-cpu-cont1-20260920"})
        self.assertEqual(cpu.CAMPAIGN, "benchrun-c480-cpu-cont2-20260920")
        exec(contract, {"campaign": cpu.CAMPAIGN})

    def test_only_four_manifests_with_fixed_pins_caps_and_affinity_subsets(self):
        manifests = cpu.manifests()
        self.assertEqual([(m["layout"], m["placement"], m["configured_capacity"]) for m in manifests],
                         [(layout, placement, 480000) for layout in ("A", "B") for placement in ("G1", "Q1")])
        self.assertEqual(len({m["container_name"] for m in manifests}), 4)
        self.assertEqual(profiles.scope_capacities(cpu.SCOPE), (480000,))
        self.assertEqual(profiles.scope_placements(cpu.SCOPE), ("G1", "Q1"))
        for m in manifests:
            old = profiles.concurrent_manifest(m["placement"], 65536 if m["placement"] == "G1" else 700160)
            glm, native, args = m["placement"] == "G1", m["native_argv"], m["create_argv"]
            cpu_set = profiles.cpu_set(m["guest_cpuset"])
            self.assertTrue(cpu_set <= profiles.cpu_set(old["guest_cpuset"]))
            self.assertEqual(len(cpu_set), m["guest_cpu_count"])
            self.assertEqual(m["guest_total_vcpus"], 112)
            self.assertEqual(flag(args, "--memory"), str((640 if glm else 32)*1024**3))
            self.assertEqual(flag(args, "--memory-swap"), flag(args, "--memory"))
            self.assertEqual(flag(args, "--cpuset-cpus"), m["guest_cpuset"])
            self.assertEqual(m["gpu_uuids"], old["gpu_uuids"])
            self.assertEqual(m["image"], old["image"])
            self.assertEqual(m["model"], old["model"])
            self.assertEqual(m["live_allocation"], "NOT_TESTED")
            gates = " ".join(m["mandatory_run_gates"])
            self.assertIn("1.15", gates)
            self.assertNotIn("25%", gates)
            self.assertNotIn("65536", gates)
            self.assertNotIn("700160", gates)
            self.assertNotIn("GOMP", json.dumps(m))
            self.assertNotIn("OMP_NUM_THREADS", json.dumps(m))
            self.assertTrue(flag(args, "--publish").startswith("127.0.0.1:"))
            expected_native = copy.deepcopy(old["native_argv"])
            expected_changes = (("--ctx-size", "480000"), ("--threads", str(len(cpu_set))),
                                ("--threads-batch", str(len(cpu_set)))) if glm else (
                                ("--context-length", "480000"), ("--max-total-tokens", "480000"))
            for key, value in expected_changes:
                expected_native[expected_native.index(key) + 1] = value
            self.assertEqual(native, expected_native)
            old_env = [old["create_argv"][i+1] for i, v in enumerate(old["create_argv"]) if v == "--env"]
            current_env = [args[i+1] for i, v in enumerate(args) if v == "--env"]
            self.assertEqual(current_env, old_env)
            if glm:
                for key, value in (("--ctx-size", "480000"), ("--threads", str(len(cpu_set))),
                                   ("--threads-batch", str(len(cpu_set))), ("--n-cpu-moe", "76"),
                                   ("--cache-type-k", "f16"), ("--cache-type-v", "f16")):
                    self.assertEqual(flag(native, key), value)
            else:
                for key, value in (("--context-length", "480000"), ("--max-total-tokens", "480000"),
                                   ("--tp-size", "1"), ("--mem-fraction-static", "0.80"),
                                   ("--kv-cache-dtype", "bfloat16"), ("--quantization", "fp8"),
                                   ("--chunked-prefill-size", "2048")):
                    self.assertEqual(flag(native, key), value)
                self.assertEqual(flag(args, "--scope"), cpu.SCOPE)
        self.assertEqual(cpu.manifest("A", "Q1")["native_argv"], cpu.manifest("B", "Q1")["native_argv"])
        for layout in ("A", "B"):
            self.assertFalse(profiles.cpu_set(cpu.manifest(layout, "G1")["guest_cpuset"]) &
                             profiles.cpu_set(cpu.manifest(layout, "Q1")["guest_cpuset"]))
        for layout, placement in (("C", "G1"), ("A", "G2"), ("B", "Q2"), (96, "G1")):
            with self.assertRaises(ValueError): cpu.manifest(layout, placement)

    def test_closed_arm_plan_and_explicit_fifteen_percent_policy(self):
        arm = {"scope": cpu.SCOPE, "campaign": cpu.CAMPAIGN, "manifests": cpu.manifests(),
               "trial_plan": cpu.trial_order()}
        self.assertEqual(profiles.validate_arm_scope(arm), cpu.SCOPE)
        p = arm["trial_plan"]
        self.assertEqual([(t["id"], t["placement"], t["configured_capacity"], t["occupied_target_capacity"])
                          for t in p["trials"]], [
            ("A-G65008", "G1", 480000, 65536), ("A-Qnear480K", "Q1", 480000, 480000),
            ("A-Q256K", "Q1", 480000, 262144), ("B-G65008", "G1", 480000, 65536),
            ("B-Qnear480K", "Q1", 480000, 480000)])
        self.assertEqual([(r["id"], r["pairs"], r["qwen_max_requests"]) for r in p["rounds"]], [("A", 1, 1), ("B", 1, 1)])
        self.assertEqual(p["common_input"]["layout"], "A")
        self.assertEqual(p["common_input"]["requests"], 1)
        self.assertEqual(p["common_input"]["after"], "A-Qnear480K-drained")
        self.assertFalse(p["common_input"]["wait_for_glm"])
        self.assertTrue(p["common_input"]["record_actual_peer_condition"])
        self.assertEqual((p["measurement_budget_seconds"], p["maximum_request_seconds"]), (7200, 7200))
        policy = cpu.resource_policy()
        self.assertEqual(policy["host_headroom_policy"], {"version": "sampled-required-working-set-15pct-v1",
                         "numerator": 23, "denominator": 20, "basis": "sampled_required_working_set_estimate_bytes"})
        self.assertEqual(policy["fresh_initial_host_available_bytes"], 688*1024**3)
        mutations = [lambda a: a["manifests"][0].update(guest_cpu_count=80),
                     lambda a: a["manifests"][1].update(configured_capacity=700160),
                     lambda a: a["manifests"][2]["resource_policy"].update(swap_allowed_bytes=1),
                     lambda a: a["trial_plan"]["rounds"][0].update(qwen_max_requests=8),
                     lambda a: a["trial_plan"]["common_input"].update(requests=2),
                     lambda a: a.update(campaign=profiles.CONCURRENT_CAMPAIGN)]
        for mutate in mutations:
            bad = copy.deepcopy(arm); mutate(bad)
            with self.assertRaises(ValueError): profiles.validate_arm_scope(bad)

    def test_historical_manifests_and_plans_are_byte_identical(self):
        # Hashes of canonical declarations at reviewed clean46e7f29, captured
        # before this adapter. These include native argv and all runtime knobs.
        for actual, expected in [
            (profiles.concurrent_manifests(), "9a195626a72e1e39afcb427350ae26280c9f8ab8d73dc78372cd009bc989de1d"),
            (profiles.candidate_manifests(), "414254391e1c1e14b5aeadf3579f71153ec8002253c268033ff4093ef011b07e"),
            (profiles.trial_order(profiles.CONCURRENT_SCOPE), "82656f214735105777130972f52b1b36f683848a2d3d0e4c5fc7d0a783f87ba3"),
            (profiles.trial_order(profiles.CANDIDATE_SCOPE), "f5b2226d2507c9931ad57d1d250e44d95776c2144c16214cb2b381a643a7e746")]:
            self.assertEqual(digest(actual), expected)

    def test_launcher_closed_tuple_and_existing_resolved_validator(self):
        from tests.test_benchmark_qwen_adapter import fixture
        base = qwen_launcher.pinned_base(ROOT / "scripts/runtime/sglang38_file_auth.py")
        argv = qwen_launcher.bind_variant(base, 480000, 1, scope=cpu.SCOPE)
        options, native = base.parse_options(argv)
        self.assertEqual(options.context_length, "480000")
        self.assertEqual(native, cpu.manifest("A", "Q1")["native_argv"])
        args = fixture.args_fixture(base.EXTENSION_CONTEXT)
        args.context_length = args.max_total_tokens = 480000
        args.tp_size, args.port, args.served_model_name = 1, 31004, "bench-qwen3.8-27b"
        base.validate_server_args(args)
        base.validate_server_args(fixture.resolved_args_fixture(args), resolved=True)
        for context, tp, scope in ((480000, 1, None), (480000, 2, cpu.SCOPE),
                                    (700160, 1, cpu.SCOPE), (480000, 1, profiles.CONCURRENT_SCOPE),
                                    (262144, 1, cpu.SCOPE)):
            with self.assertRaises(ValueError): qwen_launcher.variant(base, context, tp, scope=scope)
        for key, value in (("max_total_tokens", 479744), ("mem_fraction_static", 0.81), ("tp_size", 2)):
            bad = copy.deepcopy(args); setattr(bad, key, value)
            with self.assertRaises(base.LaunchError): base.validate_server_args(bad)

    def test_G480_occupied_fitting_is_rejected_before_native_counter(self):
        from unittest.mock import Mock
        count = Mock(side_effect=AssertionError("native counter must not be called"))
        for target in (None, 480000, 262144):
            with self.subTest(target=target), self.assertRaises(fixtures.HarnessError):
                fixtures.fit_sample("bench-glm-5.3", 480000, "frozen-glm-seed", "fresh-glm-prefix",
                                    count, scope=cpu.SCOPE, target_capacity=target)
        count.assert_not_called()
        self.assertEqual(fixtures._fit_target("bench-glm-5.3", 480000, cpu.SCOPE, 65536,
                                             "retrieval", 256, False), 65536)

    def test_fixtures_preserve_configured_pool_vs_exact_native_occupied_count(self):
        for target in (480000, 262144):
            sample, count = fixtures.fit_sample("bench-qwen3.8-27b", 480000, "frozen-qwen-seed", "fresh-qwen-prefix-a",
                counter(480000), scope=cpu.SCOPE, target_capacity=target, synthetic=True)
            matched, recounted = fixtures.matched_sample(sample, "fresh-qwen-prefix-b", counter(480000),
                480000, scope=cpu.SCOPE, target_capacity=target, synthetic=True)
            self.assertEqual(count["configured_context"], 480000)
            self.assertTrue(target-640 <= count["input_tokens"] <= target-512)
            self.assertEqual(sample["fixture_sha256"], matched["fixture_sha256"])
            self.assertEqual(count["input_tokens"], recounted["input_tokens"])
        for model in ("bench-qwen3.8-27b",):
            _, counted = fixtures.warmup_sample(model, 480000, "warmup-cpu-prefix", counter(480000),
                                               scope=cpu.SCOPE, synthetic=True)
            self.assertGreaterEqual(counted["input_tokens"], 2048)
        with self.assertRaises(fixtures.HarnessError):
            fixtures.fit_sample("bench-qwen3.8-27b", 480000, "frozen-qwen-seed", "fresh-qwen-prefix", counter(480000))
        calls = []
        def native(route, body):
            calls.append(route)
            return {"tokens": [1, 2], "count": 2, "max_model_len": 262144}
        sample = fixtures.build_sample("bench-qwen3.8-27b", 12, "count-seed", "count-prefix")
        counted = accounting.native_counter("bench-qwen3.8-27b", 480000, native,
            qwen_template_sha256="a"*64, scope=cpu.SCOPE)(fixtures.serialize_validate(sample))
        self.assertEqual(counted["configured_context"], 480000)
        self.assertEqual(counted["tokenizer_max_model_len"], 262144)
        self.assertEqual(calls, ["/v1/tokenize"])


if __name__ == "__main__":
    unittest.main()
