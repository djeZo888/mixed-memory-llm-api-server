"""Synthetic/native-CPU evidence helpers; no HTTP, model or VM execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from d3t import accounting as a


def body(stream=False):
    return {"model": "glm-5.3", "messages": [{"role": "user", "content": "Read the fixture."}],
            "stream": stream, "max_tokens": 256, "temperature": 0,
            "reasoning_effort": "low", "tools": [a.READ_TOOL]}


class NativeFixture:
    """Synthetic native replies; the real routes were separately exercised."""
    def __init__(self, tokens=None):
        self.tokens = list(range(42)) if tokens is None else tokens
        self.props = {"model_alias": "glm-5.3", "is_sleeping": False, "total_slots": 1,
                      "chat_template": "synthetic loaded template", "default_generation_settings": {"n_ctx": 1048576}}
        self.prompt = "synthetic rendered tools + special tokens"
        self.calls = []

    def __call__(self, path, payload):
        self.calls.append((path, copy.deepcopy(payload)))
        if path == "/props":
            return self.props
        if path == "/apply-template":
            return {"prompt": self.prompt}
        if path == "/tokenize":
            return {"tokens": self.tokens}
        raise AssertionError("unexpected route")


def completion(content="ok", tools=None, **extra):
    message = {"role": "assistant", "content": content}
    if tools:
        message["tool_calls"] = tools
    return {"model": "glm-5.3", "choices": [{"index": 0, "message": message,
             "finish_reason": "tool_calls" if tools else "stop"}], **extra}


def stream(events, done=True):
    text = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
    return (text + ("data: [DONE]\n\n" if done else "")).encode()


def tool_call():
    return {"id": "fixture_read_1", "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"calc.py"}'}}


class AccountingTests(unittest.TestCase):
    def test_exact_body_and_actual_native_route_payloads(self):
        request = body()
        wire, digest = a.wire_body(request)
        self.assertEqual((wire, digest), a.wire_body(dict(reversed(list(request.items())))))
        self.assertEqual(json.loads(wire), request)
        native = NativeFixture()
        result = a.account(request, native)
        self.assertEqual(result["body_sha256"], digest)
        self.assertEqual(native.calls, [("/props", None), ("/apply-template", request),
                         ("/tokenize", {"content": native.prompt, "add_special": True,
                                        "parse_special": True, "with_pieces": False})])
        self.assertEqual(result["input_tokens"], 42)
        changed = {**request, "max_tokens": 128}
        with self.assertRaises(a.Error):
            a.check_occupancy(result, changed)

    def test_reject_unreviewed_request_fields_and_replayed_reasoning(self):
        for field, value in (("reasoning_effort", None), ("model", "GLM"), ("temperature", 1), ("max_tokens", True), ("cache_prompt", True), ("tools", [])):
            with self.subTest(field=field), self.assertRaises(a.Error):
                a.wire_body({**body(), field: value})
        request = body()
        request["messages"].append({"role": "assistant", "content": "hello", "reasoning_content": "private"})
        with self.assertRaises(a.Error):
            a.wire_body(request)

    def test_native_loaded_properties_and_token_results_fail_closed(self):
        for key, value in (("model_alias", "other"), ("is_sleeping", True), ("total_slots", 2),
                           ("chat_template", ""), ("default_generation_settings", {"n_ctx": 65536})):
            native = NativeFixture()
            native.props[key] = value
            with self.subTest(field=key), self.assertRaises(a.Error):
                a.account(body(), native)
            self.assertEqual(len(native.calls), 1)
        for tokens in ([], [True], [-1], [2**31]):
            with self.subTest(tokens=tokens), self.assertRaises(a.Error):
                a.account(body(), NativeFixture(tokens))
        native = NativeFixture()
        native.props["chat_template_tool_use"] = "actual distinct loaded tool template"
        result = a.account(body(), native)
        self.assertEqual(result["template_sha256"], a.sha256(native.props["chat_template_tool_use"].encode()))

    def test_occupancy_and_continuation_use_actual_ids_with_reserve(self):
        request = body()
        target, ceiling = 65536, 65536 - 8192
        previous = a.account(request, NativeFixture([7] * ceiling))
        result = a.check_occupancy(previous, request, target)
        self.assertEqual(result["remaining_context_tokens"], 8192)
        for count in (ceiling - 257, ceiling + 1):
            with self.subTest(count=count), self.assertRaises(a.Error):
                a.check_occupancy(a.account(request, NativeFixture([7] * count)), request, target)
        continued = a.account(request, NativeFixture([7] * ceiling + [8] * 100))
        a.check_occupancy(continued, request, target, initial=False)
        self.assertEqual(a.common_prefix(previous["token_ids"], continued["token_ids"]), ceiling)
        with self.assertRaises(a.Error):
            a.check_occupancy(a.account(request, NativeFixture([7] * (target - 255))), request, target, initial=False)
        previous["configured_context"] = 32768
        with self.assertRaises(a.Error):
            a.check_occupancy(previous, request, target)

    def test_bounded_fit_may_count_over_capacity_but_never_admit_it(self):
        request = body()
        counted = a.account(request, NativeFixture([7] * (a.NATIVE_CONTEXT + 1)))
        self.assertEqual(counted["input_tokens"], a.NATIVE_CONTEXT + 1)
        with self.assertRaises(a.Error):
            a.check_occupancy(counted, request, a.NATIVE_CONTEXT)

    def test_remote_stdin_contract_and_identity_validation_without_ssh(self):
        with patch.object(a.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b'{"tokens":[17]}'
            result = a._native_http("/tokenize", {"content": "private fixture"}, "a" * 64, "sha256:" + "b" * 64)
            self.assertEqual(result, {"tokens": [17]})
            args, kwargs = run.call_args
            self.assertNotIn("private fixture", repr(args[0]))
            self.assertIn(b"private fixture", kwargs["input"])
            self.assertEqual(kwargs["timeout"], 60)
            run.reset_mock()
            with self.assertRaises(a.Error):
                a._native_http("/tokenize", {}, "ambiguous", "sha256:" + "b" * 64)
            with self.assertRaises(a.Error):
                a._native_http("/v1/chat/completions", body(), "a" * 64, "sha256:" + "b" * 64)
            run.assert_not_called()

    def test_missing_wire_counters_remain_unknown_not_inferred(self):
        value = completion(usage={"prompt_tokens": 90, "completion_tokens": 10}, timings={"prompt_n": 40})
        parsed = a.parse_response(json.dumps(value).encode(), False, "glm-5.3")
        self.assertEqual(parsed["counters"]["evaluated_prompt_tokens"], 40)
        for field in ("cached_tokens", "total_tokens", "decode_tokens", "prompt_ms", "decode_ms", "elapsed_seconds"):
            self.assertIsNone(parsed["counters"][field])
        self.assertEqual(parsed["usage_observations"], [value["usage"]])

    def test_stream_parser_preserves_native_timings_and_fragmented_tool_arguments(self):
        events = [
            {"model": "glm-5.3", "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [{"index": 0, "id": "fixture_read_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":'}}]}, "finish_reason": None}]},
            {"model": "glm-5.3", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"calc.py"}'}}]}, "finish_reason": "tool_calls"}]},
            {"model": "glm-5.3", "choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 8, "prompt_tokens_details": {"cached_tokens": 850}}, "timings": {"prompt_n": 50, "predicted_n": 8, "prompt_ms": 99.5, "predicted_ms": 123.25}},
        ]
        parsed = a.parse_response(stream(events), True, "glm-5.3")
        self.assertEqual(parsed["message"]["tool_calls"], [tool_call()])
        self.assertEqual(parsed["timing_observations"], [events[-1]["timings"]])
        self.assertEqual(parsed["counters"]["cached_tokens"], 850)
        self.assertEqual(parsed["counters"]["decode_ms"], 123.25)
        with self.assertRaises(a.Error):
            a.parse_response(stream(events, done=False), True, "glm-5.3")

    def test_native_cache_count_source_is_explicit_without_reconstruction(self):
        value = completion(timings={"cache_n": 81, "prompt_n": 1})
        parsed = a.parse_response(json.dumps(value).encode(), False, "glm-5.3")
        self.assertEqual(parsed["counters"]["cached_tokens"], 81)
        self.assertEqual(parsed["counters"]["cached_tokens_source"], "timings.cache_n")
        self.assertIsNone(parsed["counters"]["prompt_tokens"])

    def test_real_shipped_parser_rejects_alias_length_duplicates_and_bad_counter(self):
        raws = [json.dumps(completion()).encode(), b'{"model":"glm-5.3","model":"other"}',
                json.dumps(completion(usage={"prompt_tokens": -1})).encode()]
        for index, raw in enumerate(raws):
            with self.subTest(index=index), self.assertRaises(a.Error):
                a.parse_response(raw, False, "wrong" if index == 0 else "glm-5.3")
        value = completion()
        value["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(a.a1.CompletionError):
            a.parse_response(json.dumps(value).encode(), False, "glm-5.3")

    def test_retrieval_checks_exact_order_and_middle_content(self):
        expected = ["early-018", "middle-927", "late-664"]
        message = {"role": "assistant", "content": json.dumps(expected)}
        self.assertTrue(a.check_sentinels(message, expected)["middle"])
        for actual in (expected[::-1], [expected[0], "incorrect", expected[2]], expected + ["extra"]):
            with self.subTest(actual=actual), self.assertRaises(a.Error):
                a.check_sentinels({**message, "content": json.dumps(actual)}, expected)

    def test_actual_worker_fixture_read_and_continuation_validation(self):
        message = {"role": "assistant", "content": None, "tool_calls": [tool_call()]}
        with tempfile.TemporaryDirectory() as parent:
            result, evidence = a.execute_tool(message, str(Path(parent).resolve()))
            self.assertEqual(list(Path(parent).iterdir()), [])
        self.assertEqual(result["tool_call_id"], "fixture_read_1")
        content = a.a1.strict_json_loads(result["content"])["content"]
        self.assertTrue(evidence["worker_local"])
        self.assertEqual(content, "def add(a, b):\n    return a - b\n")
        self.assertTrue(a.check_tool_continuation({"role": "assistant", "content": content})["tool_content_reported"])
        continued = body()
        continued["messages"] += [message, result]
        a.wire_body(continued)  # Actual A1 tool-ID/history validator.
        changed = copy.deepcopy(message)
        changed["tool_calls"][0]["function"]["name"] = "write_file"
        with self.assertRaises(a.Error):
            a.execute_tool(changed)
        with self.assertRaises(a.Error):
            a.check_tool_continuation({"role": "assistant", "content": "It adds."})


if __name__ == "__main__":
    unittest.main()
