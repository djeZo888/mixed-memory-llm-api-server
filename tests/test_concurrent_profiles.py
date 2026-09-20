"""Closed concurrent profile/fixture contracts; synthetic offline, no VM contact."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark import accounting, fixtures, profiles, qwen_launcher


def flag(argv, name):
    return argv[argv.index(name) + 1]


def counter(capacity):
    def count(raw):
        body = json.loads(raw)
        n = body["messages"][0]["content"].count("record=") * 32 + 80
        return {"source": "synthetic_offline", "input_tokens": n,
                "body_sha256": fixtures.digest(raw), "template_sha256": "a" * 64,
                "token_ids_sha256": "b" * 64, "configured_context": capacity}
    return count


class ConcurrentProfiles(unittest.TestCase):
    def test_four_exact_tuples_and_fixed_resources(self):
        manifests = profiles.concurrent_manifests()
        self.assertEqual([(m["placement"], m["configured_capacity"]) for m in manifests],
                         list(profiles.CONCURRENT_TUPLES))
        for m in manifests:
            glm = m["placement"] == "G1"
            args, native = m["create_argv"], m["native_argv"]
            self.assertEqual(flag(args, "--memory"), str((640 if glm else 32) * 1024**3))
            self.assertEqual(flag(args, "--memory-swap"), flag(args, "--memory"))
            self.assertEqual(flag(args, "--cpuset-cpus"), "0-95" if glm else "96-111")
            self.assertEqual(m["gpu_uuids"], [profiles.read_config()["gpu_uuids"][0 if glm else 1]])
            self.assertTrue(flag(args, "--publish").startswith("127.0.0.1:"))
            self.assertEqual(m["campaign"], profiles.CONCURRENT_CAMPAIGN)
            self.assertTrue(m["mixed"])
            if glm:
                for key, value in (("--ctx-size", str(m["configured_capacity"])), ("--n-cpu-moe", "76"),
                                   ("--threads", "96"), ("--threads-batch", "96"), ("--cache-type-k", "f16"),
                                   ("--cache-type-v", "f16"), ("--load-mode", "none"), ("--fit", "off")):
                    self.assertEqual(flag(native, key), value)
            else:
                for key, value in (("--context-length", str(m["configured_capacity"])),
                                   ("--max-total-tokens", str(m["configured_capacity"])),
                                   ("--tp-size", "1"), ("--mem-fraction-static", "0.80"),
                                   ("--kv-cache-dtype", "bfloat16"), ("--dtype", "bfloat16"),
                                   ("--quantization", "fp8"), ("--chunked-prefill-size", "2048")):
                    self.assertEqual(flag(native, key), value)
                self.assertEqual(flag(args, "--scope"), profiles.CONCURRENT_SCOPE)

    def test_closed_arm_rejects_changed_capacity_or_cap_or_plan(self):
        armed = {"scope": profiles.CONCURRENT_SCOPE, "campaign": profiles.CONCURRENT_CAMPAIGN,
                 "manifests": profiles.concurrent_manifests(),
                 "trial_plan": profiles.trial_order(profiles.CONCURRENT_SCOPE)}
        self.assertEqual(profiles.validate_arm_scope(armed), profiles.CONCURRENT_SCOPE)
        for kind in ("capacity", "ram", "plan", "campaign"):
            bad = copy.deepcopy(armed)
            if kind == "capacity": bad["manifests"][-1]["configured_capacity"] = 700000
            if kind == "ram": bad["manifests"][1]["ram_cap_bytes"] += 1
            if kind == "plan": bad["trial_plan"]["rounds"][1]["qwen_max_requests"] = 9
            if kind == "campaign": bad["campaign"] = "benchrun-20260919"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                profiles.validate_arm_scope(bad)
        for placement, capacity in (("G2", 16384), ("G1", 262144), ("Q2", 700160), ("Q1", 700000)):
            with self.assertRaises(ValueError): profiles.concurrent_manifest(placement, capacity)

    def test_legacy_profile_behavior_and_new_launcher_scope_are_closed(self):
        base = qwen_launcher.pinned_base(ROOT / "scripts/runtime/sglang38_file_auth.py")
        old = profiles.command_manifest("Q1", 262144)
        self.assertFalse(old["mixed"])
        self.assertNotIn("--memory", old["create_argv"])
        self.assertNotIn("--scope", old["create_argv"])
        self.assertEqual(old["native_argv"], qwen_launcher.variant(base, 262144, 1))
        for capacity, tp, scope in ((700160, 1, None), (700160, 2, profiles.CONCURRENT_SCOPE),
                                    (65536, 1, profiles.CONCURRENT_SCOPE), (700000, 1, profiles.CONCURRENT_SCOPE)):
            with self.assertRaises(ValueError): qwen_launcher.variant(base, capacity, tp, scope=scope)
        with self.assertRaises(ValueError): profiles.command_manifest("Q1", 700160)
        with self.assertRaises(ValueError): profiles.command_manifest("Q1", 262144, mixed=True, ram_cap=32*1024**3)

    def test_frozen_rounds_and_clock(self):
        plan = profiles.trial_order(profiles.CONCURRENT_SCOPE)
        self.assertEqual([(r["glm_capacity"], r["qwen_capacity"], r["qwen_max_requests"])
                          for r in plan["rounds"]], [(16384, 262144, 3), (65536, 700160, 8)])
        self.assertEqual(plan["rounds"][1]["qwen_filler_target_capacity"], 262144)
        self.assertEqual((plan["measurement_budget_seconds"], plan["maximum_request_seconds"]), (5400, 7200))
        self.assertTrue(plan["clock_includes_preparation"])
        self.assertTrue(plan["restoration_outside_budget"])

    def test_large_launcher_projects_only_closed_tuple_into_pinned_validator(self):
        from tests.test_benchmark_qwen_adapter import fixture
        base = qwen_launcher.pinned_base(ROOT / "scripts/runtime/sglang38_file_auth.py")
        argv = qwen_launcher.bind_variant(base, 700160, 1, scope=profiles.CONCURRENT_SCOPE)
        options, native = base.parse_options(argv)
        self.assertEqual(options.context_length, "700160")
        self.assertEqual(native, profiles.concurrent_manifest("Q1", 700160)["native_argv"])
        args = fixture.args_fixture(base.EXTENSION_CONTEXT)
        args.context_length = args.max_total_tokens = 700160
        args.tp_size, args.port, args.served_model_name = 1, 31004, "bench-qwen3.8-27b"
        base.validate_server_args(args)
        base.validate_server_args(fixture.resolved_args_fixture(args), resolved=True)
        for field, value in (("max_total_tokens", 699904), ("mem_fraction_static", 0.81),
                             ("tp_size", 2), ("kv_cache_dtype", "fp8_e4m3")):
            bad = copy.deepcopy(args)
            setattr(bad, field, value)
            with self.subTest(field=field), self.assertRaises(base.LaunchError):
                base.validate_server_args(bad)


class ConcurrentFixtures(unittest.TestCase):
    def test_large_pool_and_smaller_occupied_target_remain_distinct(self):
        for target in (700160, 262144):
            sample, counted = fixtures.fit_sample("bench-qwen3.8-27b", 700160,
                "concurrent-qwen-seed", "fresh-prefix-first", counter(700160),
                scope=profiles.CONCURRENT_SCOPE, target_capacity=target, synthetic=True)
            self.assertEqual(counted["configured_context"], 700160)
            self.assertTrue(target-640 <= counted["input_tokens"] <= target-512)
            matched, recounted = fixtures.matched_sample(sample, "fresh-prefix-second", counter(700160),
                700160, scope=profiles.CONCURRENT_SCOPE, target_capacity=target, synthetic=True)
            self.assertEqual(matched["fixture_sha256"], sample["fixture_sha256"])
            self.assertNotEqual(fixtures.serialize_validate(matched), fixtures.serialize_validate(sample))
            self.assertEqual(recounted["configured_context"], 700160)
        with self.assertRaises(fixtures.HarnessError):
            fixtures.fit_sample("bench-qwen3.8-27b", 700160, "qwen-seed", "qwen-prefix", counter(700160))

    def test_large_warmup_and_scoped_native_counter(self):
        sample, count = fixtures.warmup_sample("bench-qwen3.8-27b", 700160,
            "warmup-concurrent-first", counter(700160), scope=profiles.CONCURRENT_SCOPE, synthetic=True)
        self.assertTrue(2304 <= count["input_tokens"] <= 2432)
        calls = []
        def native(route, payload):
            calls.append((route, payload))
            return {"tokens": [1, 2, 3], "count": 3, "max_model_len": 262144}
        c = accounting.native_counter("bench-qwen3.8-27b", 700160, native,
            qwen_template_sha256="a"*64, scope=profiles.CONCURRENT_SCOPE)
        counted = c(fixtures.serialize_validate(sample))
        self.assertEqual(counted["configured_context"], 700160)
        self.assertEqual(counted["tokenizer_max_model_len"], 262144)
        self.assertEqual(calls[0][0], "/v1/tokenize")
        for model, capacity, scope in (("bench-qwen3.8-27b", 700160, None),
                                       ("bench-glm-5.3", 700160, profiles.CONCURRENT_SCOPE),
                                       ("bench-qwen3.8-27b", 65536, profiles.CONCURRENT_SCOPE)):
            with self.assertRaises(fixtures.HarnessError):
                accounting.native_counter(model, capacity, native, qwen_template_sha256="a"*64, scope=scope)

    def test_semantic_fence_does_not_rewrite_strict_or_accept_extra_content(self):
        sample = fixtures.build_sample("bench-qwen3.8-27b", 20, "qwen-scorer-seed", "qwen-scorer-prefix")
        answer = json.dumps(sample["scorer"]["retrieval"])
        message = {"role": "assistant", "content": "```json\n" + answer + "\n```"}
        original = copy.deepcopy(message)
        self.assertEqual(fixtures.score_retrieval(sample, message)["status"], "HARNESS_FAILURE")
        self.assertEqual(fixtures.score_retrieval_semantic(sample, message)["status"], "PASS")
        self.assertEqual(message, original)
        self.assertEqual(fixtures.score_retrieval(sample, message)["status"], "HARNESS_FAILURE")
        for content in ("explanation\n"+message["content"], message["content"]+"\nmore", "```json\n{}\n```",
                        "```json\n"+json.dumps({**sample["scorer"]["retrieval"], "extra": "x"})+"\n```",
                        "```json\n"+answer+"\n```\n```json\n"+answer+"\n```"):
            with self.subTest(content=content):
                self.assertNotEqual(fixtures.score_retrieval_semantic(sample, {"role":"assistant", "content":content})["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
