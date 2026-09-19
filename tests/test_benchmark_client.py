"""Synthetic offline SSE timing and persistence tests. No network use."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import client as c, fixtures as f


MODEL = "bench-glm-5.3"


def event(delta=None, finish=None, **extra):
    return {"model": MODEL, "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}], **extra}


def stream(events, done=True):
    return b"".join(b"data: " + f.canonical(item) + b"\r\n\r\n" for item in events) + (b"data: [DONE]\r\n\r\n" if done else b"")


class Clock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        self.value += .125
        return self.value


class ClientTests(unittest.TestCase):
    def test_segmentation_every_byte_role_does_not_set_ttft(self):
        observer = c.StreamObserver(10)
        for part in stream([event({"role": "assistant"})], done=False):
            observer.feed(bytes([part]), 11)
        self.assertIsNone(observer.first_any)
        for part in stream([event({"content": "hello"}), event(finish="stop")]):
            observer.feed(bytes([part]), 13)
        self.assertEqual(observer.first_content, 3)
        self.assertTrue(observer.done)
        self.assertFalse(observer.error)

    def test_reasoning_content_and_tool_ttft_distinct(self):
        observer = c.StreamObserver(0)
        observer.feed(stream([event({"reasoning_content": "think"})], False), 1)
        observer.feed(stream([event({"tool_calls": [{"index": 0, "function": {"name": "read_file", "arguments": "{"}}]})], False), 2)
        observer.feed(stream([event({"content": "answer"})], False), 3)
        self.assertEqual((observer.first_reasoning, observer.first_tool, observer.first_content), (1, 2, 3))

    def test_native_counters_cached_evaluated_and_missing_not_zero(self):
        raw = stream([event({"role": "assistant", "content": "ok"}), event(finish="stop"),
                      {"model": MODEL, "choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 3,
                       "prompt_tokens_details": {"cached_tokens": 20}},
                       "timings": {"prompt_n": 80, "predicted_n": 3, "prompt_ms": 120.5, "predicted_ms": 10}}])
        result = c.parse_response(raw, MODEL)
        self.assertEqual(result["counters"]["evaluated_prompt_tokens"], 80)
        self.assertEqual(result["counters"]["cached_tokens"], 20)
        self.assertIsNone(result["counters"]["total_tokens"])
        self.assertEqual(result["counter_source"], "native_response_fields")

    def test_fragmented_tool_call_roundtrip(self):
        raw = stream([event({"role": "assistant", "tool_calls": [{"index": 0, "id": "returned-1", "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":'}}]}),
                    event({"tool_calls": [{"index": 0, "function": {"arguments": '"result.json"}'}}]}, "tool_calls")])
        parsed = c.parse_response(raw, MODEL)
        self.assertEqual(parsed["message"]["tool_calls"][0]["id"], "returned-1")
        self.assertEqual(json.loads(parsed["message"]["tool_calls"][0]["function"]["arguments"]), {"path": "result.json"})

    def test_truncation_alias_duplicate_json_and_bad_counter_are_harness_failures(self):
        cases = [stream([event({"content": "ok"}, "stop")], False),
                 stream([event({"content": "ok"}, "stop", usage={"prompt_tokens": -1})]),
                 b'data: {"model":"x","model":"y"}\n\ndata: [DONE]\n\n']
        for raw in cases:
            with self.subTest(raw=raw[:50]), self.assertRaises(f.HarnessError):
                c.parse_response(raw, MODEL)
        with self.assertRaises(f.HarnessError):
            c.parse_response(stream([event({"content": "ok"}, "stop")]), "different")

    def test_cap_termination_is_not_correctness_failure(self):
        result = c.parse_response(stream([event({"content": "partial"}, "length", usage={"completion_tokens": 256})]), MODEL)
        self.assertEqual(result["status"], "OUTPUT_LIMIT")
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["counters"]["completion_tokens"], 256)
        incomplete = stream([event({"tool_calls": [{"index": 0, "id": "broken", "type": "function",
                               "function": {"name": "read_file", "arguments": "{"}}]}, "length")])
        with self.assertRaises(f.HarnessError):
            c.parse_response(incomplete, MODEL)
        with self.assertRaises(f.HarnessError):
            c.parse_response(stream([event({"content": "partial"}, "length")], done=False), MODEL)

    def test_parser_failure_drains_healthy_request_and_persists_no_raw_public(self):
        chunks = [b'data: {invalid}\n\n', stream([event({"content": "private answer"}, "stop")])]
        yielded = []
        def transport(body, timeout):
            self.assertEqual(timeout, 7200)
            for index, chunk in enumerate(chunks):
                yielded.append(index)
                yield chunk
        body = f.serialize_validate(f.build_sample(MODEL, 20, "seed000001", "nonce00001"))
        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory, "summary.jsonl")
            result = c.run_request(body, transport, sample_id="synthetic-1", private_dir=directory,
                                   summary_path=summary_path, clock=Clock())
            self.assertEqual(yielded, [0, 1])
            self.assertEqual(result["summary"]["status"], "HARNESS_FAILURE")
            self.assertEqual(Path(result["private_response_path"]).read_bytes(), b"".join(chunks))
            self.assertNotIn("private answer", summary_path.read_text())
            self.assertNotIn("archive", summary_path.read_text())
            self.assertEqual(result["summary"]["lifecycle_actions"], 0)
            self.assertEqual(result["summary"]["retry_attempts"], 0)

    def test_transport_failure_no_retry_and_valid_summary(self):
        called = []
        def transport(*args):
            called.append(True)
            yield stream([event({"role": "assistant"})], False)
            raise OSError("private provider error must not be recorded")
        body = f.serialize_validate(f.build_sample(MODEL, 20, "seed000001", "nonce00001"))
        with tempfile.TemporaryDirectory() as directory:
            result = c.run_request(body, transport, sample_id="failed", private_dir=directory,
                                   summary_path=Path(directory, "summary.jsonl"), clock=Clock())
            self.assertEqual(result["summary"]["status"], "TRANSPORT_FAILURE")
            self.assertEqual(len(called), 1)
            self.assertNotIn("provider", json.dumps(result["summary"]))

    def test_unexpected_observer_bug_still_drains_and_returns_parsed_answer(self):
        class Broken(c.StreamObserver):
            def feed(self, *args):
                raise RuntimeError("synthetic observer fault")
            def summary(self):
                raise RuntimeError("synthetic report fault")
        chunks = [stream([event({"content": "ok"})], False), stream([event(finish="stop")])]
        seen = []
        def transport(*args):
            for chunk in chunks:
                seen.append(True)
                yield chunk
        body = f.serialize_validate(f.build_sample(MODEL, 20, "seed000001", "nonce00001"))
        with tempfile.TemporaryDirectory() as directory:
            result = c.run_request(body, transport, sample_id="observer-fail", private_dir=directory,
                                   summary_path=Path(directory, "summary.jsonl"), clock=Clock(), observer_factory=Broken)
            self.assertEqual(len(seen), 2)
            self.assertEqual(result["parsed"]["message"]["content"], "ok")
            self.assertEqual(result["summary"]["status"], "HARNESS_FAILURE")

    def test_summary_error_does_not_destroy_success(self):
        raw = stream([event({"content": "ok"}, "stop")])
        body = f.serialize_validate(f.build_sample(MODEL, 20, "seed000001", "nonce00001"))
        with tempfile.TemporaryDirectory() as directory:
            result = c.run_request(body, lambda *_: iter([raw]), sample_id="report-fail", private_dir=directory,
                                   summary_path=Path(directory, "missing", "summary.jsonl"), clock=Clock())
            self.assertEqual(result["summary"]["status"], "COMPLETE")
            self.assertIn("summary_write_failed", result["summary"]["report_errors"])
            self.assertEqual(result["parsed"]["message"]["content"], "ok")

    def test_protected_transport_redactor_removes_echo_before_persistence(self):
        raw = stream([event({"content": "synthetic-key-echo"}, "stop")])
        def transport(*_):
            yield raw
        transport.redact = lambda data: data.replace(b"synthetic-key-echo", b"[REDACTED]")
        body = f.serialize_validate(f.build_sample(MODEL, 20, "seed000001", "nonce00001"))
        with tempfile.TemporaryDirectory() as directory:
            result = c.run_request(body, transport, sample_id="redacted", private_dir=directory,
                                   summary_path=Path(directory, "summary.jsonl"), clock=Clock())
            self.assertNotIn(b"synthetic-key-echo", Path(result["private_response_path"]).read_bytes())
            self.assertNotIn("synthetic-key-echo", json.dumps(result["summary"]))

    def test_endpoint_factory_rejects_public_wildcard_ipv6_and_auth_url_offline(self):
        for endpoint in ("http://8.8.8.8:30002", "http://0.0.0.0:30002", "http://[::1]:30002", "http://user:pass@127.0.0.1:30002", "http://localhost:30002"):
            with self.subTest(endpoint=endpoint), self.assertRaises(f.HarnessError):
                c.http_transport(endpoint, "synthetic-test-key")
        self.assertTrue(callable(c.http_transport("http://127.0.0.1:31002/v1", "synthetic-test-key")))

    def test_protected_json_adapter_routes_headers_strict_result_no_network(self):
        with patch("http.client.HTTPConnection") as constructor:
            connection = constructor.return_value
            response = connection.getresponse.return_value
            response.status = 200
            response.getheader.side_effect = lambda name, default: "application/json" if name == "Content-Type" else default
            response.read.return_value = b'{"tokens":[1,2],"count":2,"max_model_len":4096}'
            call = c.protected_json_client("http://127.0.0.1:31004", "synthetic-test-key")
            constructor.assert_not_called()
            body = {"model": "bench-qwen3.8-27b", "messages": [{"role": "user", "content": "synthetic"}]}
            result = call("/v1/tokenize", body)
            self.assertEqual(result["count"], 2)
            args, kwargs = connection.request.call_args
            self.assertEqual(args, ("POST", "/v1/tokenize"))
            self.assertEqual(json.loads(kwargs["body"]), body)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer synthetic-test-key")
            with self.assertRaises(f.HarnessError):
                call("/v1/chat/completions", body)
            self.assertEqual(constructor.call_count, 1)
            response.read.return_value = b'{"error":"synthetic-test-key"}'
            with self.assertRaises(f.HarnessError):
                call("/props", None)


if __name__ == "__main__":
    unittest.main()
