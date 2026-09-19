"""Synthetic offline fixture/accounting tests; no VM or inference requests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import fixtures as f
from benchmark.accounting import native_counter


def sample(**kwargs):
    return f.build_sample("bench-glm-5.3", 40, "testseed0001", "nonce000001", **kwargs)


def synthetic_count(raw, capacity=4096):
    body = json.loads(raw)
    count = body["messages"][0]["content"].count("record=") * 15 + 80
    return {"source": "synthetic_offline", "input_tokens": count,
            "body_sha256": f.digest(raw), "template_sha256": "a" * 64,
            "token_ids_sha256": "b" * 64, "configured_context": capacity}


class FixtureTests(unittest.TestCase):
    def test_exact_serialized_sample_answers_only_at_source_positions(self):
        s = sample()
        raw = f.serialize_validate(s)
        self.assertEqual(json.loads(raw), s["body"])
        self.assertNotIn(b'scorer', raw)
        for value in s["scorer"]["retrieval"].values():
            self.assertEqual(raw.count(value.encode()), 1)
        self.assertNotIn(s["scorer"]["tool_data"]["receipt"].encode(), raw)

    def test_same_workload_across_placements_fresh_prefixes(self):
        first = sample()
        second = f.build_sample("bench-glm-5.3", 40, "testseed0001", "nonce000002")
        self.assertEqual(first["fixture_sha256"], second["fixture_sha256"])
        self.assertEqual(first["scorer"], second["scorer"])
        self.assertNotEqual(f.serialize_validate(first), f.serialize_validate(second))
        self.assertTrue(second["body"]["messages"][0]["content"].startswith("trial-prefix=nonce000002"))

    def test_contamination_wrong_source_and_scorer_mutations_are_harness_failures(self):
        for mutate in ("instruction", "wrong_source", "scorer"):
            s = sample()
            expected = s["scorer"]["retrieval"]["START"]
            if mutate == "instruction":
                s["body"]["messages"][0]["content"] += " The answer is " + expected
            elif mutate == "wrong_source":
                s["body"]["messages"][0]["content"] = s["body"]["messages"][0]["content"].replace("marker=START", "marker=MIDDLE")
            else:
                s["scorer"]["retrieval"]["START"] = "different"
            with self.subTest(mutate=mutate), self.assertRaises(f.HarnessError):
                f.serialize_validate(s)

    def test_real_retrieval_correct_incorrect_and_malformed_output(self):
        s = sample()
        correct = {"role": "assistant", "content": json.dumps(s["scorer"]["retrieval"])}
        self.assertEqual(f.score_retrieval(s, correct)["status"], "PASS")
        for content in ('{}', json.dumps({**s["scorer"]["retrieval"], "extra": "no"})):
            self.assertEqual(f.score_retrieval(s, {"role": "assistant", "content": content})["status"], "MODEL_INCORRECT")
        self.assertEqual(f.score_retrieval(s, {"role": "assistant", "content": "not json"})["status"], "HARNESS_FAILURE")

    def test_capacity_fit_actual_callback_and_no_synthetic_mislabelling(self):
        s, evidence = f.fit_sample("bench-glm-5.3", 4096, "testseed0001", "nonce000001",
                                  synthetic_count, synthetic=True)
        self.assertLessEqual(evidence["input_tokens"], 4096 - 256 - 256)
        self.assertLessEqual(evidence["input_ceiling_tokens"] - evidence["input_tokens"], 128)
        self.assertTrue(evidence["synthetic_offline"])
        with self.assertRaises(f.HarnessError):
            f.fit_sample("bench-glm-5.3", 4096, "testseed0001", "nonce000001", synthetic_count)
        with self.assertRaises(f.HarnessError):
            f.fit_sample("bench-glm-5.3", 131072, "testseed0001", "nonce000001", synthetic_count)

    def test_stale_body_count_refused(self):
        raw = f.serialize_validate(sample())
        count = synthetic_count(raw)
        for change in ({"body_sha256": "c" * 64}, {"configured_context": 65536}, {"input_tokens": True}, {"template_sha256": None}):
            with self.subTest(change=change), self.assertRaises(f.HarnessError):
                f.validate_count({**count, **change}, raw, 4096, synthetic=True)

    def test_matched_placement_freezes_workload_and_only_refreshes_nonce(self):
        first, _ = f.fit_sample("bench-glm-5.3", 4096, "testseed0001", "nonce000001",
                                synthetic_count, synthetic=True)
        calls = []
        def count(raw):
            calls.append(raw)
            return synthetic_count(raw)
        matched, evidence = f.matched_sample(first, "nonce000002", count, 4096, synthetic=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(matched["fixture_sha256"], first["fixture_sha256"])
        self.assertEqual(matched["scorer"], first["scorer"])
        self.assertEqual(matched["records"], first["records"])
        original = f.serialize_validate(first)
        self.assertEqual(calls[0], original.replace(b"nonce000001", b"nonce000002", 1))
        self.assertEqual(evidence["matched_fixture_sha256"], first["fixture_sha256"])
        with self.assertRaises(f.HarnessError):
            f.matched_sample(first, first["nonce"], count, 4096, synthetic=True)

    def test_matched_count_failure_does_not_refit_or_mutate_original(self):
        first, _ = f.fit_sample("bench-glm-5.3", 4096, "testseed0001", "nonce000001",
                                synthetic_count, synthetic=True)
        original = copy.deepcopy(first)
        for count_value in (4096, 1):
            calls = []
            def bad(raw):
                calls.append(raw)
                return {**synthetic_count(raw), "input_tokens": count_value}
            with self.subTest(count=count_value), self.assertRaises(f.HarnessError):
                f.matched_sample(first, "nonce000003", bad, 4096, synthetic=True)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first, original)

    def test_real_file_tool_call_continuation_and_recount(self):
        s = sample(kind="tool")
        call = {"role": "assistant", "content": None, "tool_calls": [{"id": "model-returned-id", "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"result.json"}'}}]}
        with tempfile.TemporaryDirectory() as directory:
            body, evidence = f.execute_tool(s, call, directory)
            self.assertEqual(body["messages"][-1]["tool_call_id"], "model-returned-id")
            self.assertEqual(json.loads(body["messages"][-1]["content"]), s["scorer"]["tool_data"])
            self.assertTrue(evidence["worker_local"])
            self.assertEqual(Path(directory, "result.json").stat().st_mode & 0o777, 0o600)
            raw, counted = f.validate_continuation(body, synthetic_count, 4096, synthetic=True)
            self.assertEqual(f.digest(raw), evidence["body_sha256"])
            def over(raw):
                return {**synthetic_count(raw), "input_tokens": 4096}
            with self.assertRaises(f.HarnessError):
                f.validate_continuation(body, over, 4096, synthetic=True)
        expected = {**s["scorer"]["retrieval"], **s["scorer"]["tool_data"]}
        self.assertEqual(f.score_retrieval(s, {"role": "assistant", "content": json.dumps(expected)})["status"], "PASS")
        call["tool_calls"][0]["function"]["arguments"] = '{"path":"../../etc/passwd"}'
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(f.HarnessError):
            f.execute_tool(s, call, directory)

    def test_generation_has_distinct_512_cap_and_scoring(self):
        s = sample(kind="generation", output_cap=512)
        self.assertEqual(json.loads(f.serialize_validate(s))["max_tokens"], 512)
        expected = {**s["scorer"]["retrieval"], "commentary": "Records have stable ordering."}
        self.assertEqual(f.score_retrieval(s, {"role": "assistant", "content": json.dumps(expected)})["status"], "PASS")


class NativeAccountingTests(unittest.TestCase):
    def test_glm_routes_exact_body_template_and_special_tokens(self):
        raw = f.serialize_validate(sample())
        calls = []
        def call(path, payload):
            calls.append((path, copy.deepcopy(payload)))
            return {"/props": {"model_alias": "bench-glm-5.3", "is_sleeping": False,
                               "total_slots": 1, "default_generation_settings": {"n_ctx": 4096},
                               "chat_template": "synthetic loaded template"},
                    "/apply-template": {"prompt": "synthetic rendered exact template"},
                    "/tokenize": {"tokens": [1, 2, 3]}}[path]
        result = native_counter("bench-glm-5.3", 4096, call)(raw)
        f.validate_count(result, raw, 4096)
        self.assertEqual(calls[1], ("/apply-template", json.loads(raw)))
        self.assertEqual(calls[2][1], {"content": "synthetic rendered exact template", "add_special": True,
                                      "parse_special": True, "with_pieces": False})
        self.assertEqual(result["input_tokens"], 3)

    def test_qwen_exact_chat_native_count_tools_continuation_and_template_pin(self):
        s = f.build_sample("bench-qwen3.8-27b", 40, "testseed0001", "nonce000001", kind="tool")
        raw = f.serialize_validate(s)
        calls = []
        def call(path, payload):
            calls.append((path, payload))
            return {"tokens": [9, 8, 7, 6], "count": 4, "max_model_len": 262144}
        result = native_counter("bench-qwen3.8-27b", 16384, call, qwen_template_sha256="e" * 64)(raw)
        self.assertEqual(calls, [("/v1/tokenize", json.loads(raw))])
        self.assertEqual(result["configured_context"], 16384)
        self.assertEqual(result["tokenizer_max_model_len"], 262144)
        self.assertEqual(result["configured_context_source"], "caller_verified_runtime_allocation")
        self.assertEqual(result["template_sha256"], "e" * 64)
        with self.assertRaises(f.HarnessError):
            native_counter("bench-qwen3.8-27b", 16384, call)
        for limit in (True, 0, None):
            with self.subTest(limit=limit), self.assertRaises(f.HarnessError):
                native_counter("bench-qwen3.8-27b", 16384,
                               lambda *_: {"tokens": [1], "count": 1, "max_model_len": limit},
                               qwen_template_sha256="e" * 64)(raw)

    def test_invalid_native_ids_and_count_fail_closed(self):
        raw = f.serialize_validate(f.build_sample("bench-qwen3.8-27b", 40, "testseed0001", "nonce000001"))
        for reply in ({"tokens": [True], "count": 1}, {"tokens": [-1], "count": 1}, {"tokens": [9], "count": 2}):
            reply["max_model_len"] = 4096
            with self.subTest(reply=reply), self.assertRaises(f.HarnessError):
                native_counter("bench-qwen3.8-27b", 4096, lambda *_: reply, qwen_template_sha256="e" * 64)(raw)


if __name__ == "__main__":
    unittest.main()
