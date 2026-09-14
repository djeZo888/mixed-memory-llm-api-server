"""Deterministic local-only regression tests for the stdlib protocol client."""

import http.server
import json
import os
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "agent"))
from protocol import APIError, AgentError, Budget, Client, load_api_key, redact, strict_json_loads


def call(call_id="call_1", name="read_file", arguments='{"path":"implementation.py"}'):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def completion(content="hello", calls=None, **extra):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    value = {"model": "served-alias", "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}], "usage": {"completion_tokens": 3}}
    value.update(extra)
    return value


def sse(chunks, done=True):
    data = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
    return (data + ("data: [DONE]\n\n" if done else "")).encode()


def chunk(delta, finish=None, **extra):
    value = {"model": "served-alias", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    value.update(extra)
    return value


class MockServer:
    def __init__(self):
        self.response = completion()
        self.status = 200
        self.content_type = "application/json"
        self.requests = []
        self.delay = 0
        self.trickle = False
        self.headers = {}
        self.api_key = None
        self.http_version = "HTTP/1.1"
        self.keep_open_after_body = False
        self.disconnected = threading.Event()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                self.protocol_version = outer.http_version
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.requests.append({"path": self.path, "body": json.loads(body) if body else None, "authorization": self.headers.get("Authorization")})
                status = outer.status
                if outer.api_key and self.headers.get("Authorization") != "Bearer " + outer.api_key:
                    status = 401
                value = outer.response
                raw = value if isinstance(value, bytes) else json.dumps(value).encode()
                try:
                    if outer.delay:
                        time.sleep(outer.delay)
                    self.send_response(status)
                    self.send_header("Content-Type", outer.content_type)
                    if not outer.keep_open_after_body:
                        self.send_header("Content-Length", str(len(raw)))
                        self.send_header("Connection", "close")
                    for key, val in outer.headers.items():
                        self.send_header(key, val)
                    self.end_headers()
                    if outer.trickle:
                        for byte in raw:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.015)
                    else:
                        self.wfile.write(raw)
                        self.wfile.flush()
                        if outer.keep_open_after_body:
                            time.sleep(0.5)
                except (OSError, ConnectionError):
                    outer.disconnected.set()

        class LocalHTTPServer(http.server.ThreadingHTTPServer):
            def server_bind(self):
                socketserver.TCPServer.server_bind(self)
                self.server_name = "localhost"
                self.server_port = self.server_address[1]

        self.server = LocalHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.backend = MockServer().__enter__()
        self.client = Client(self.backend.url, "requested-name", request_timeout=1, budget=Budget(10))
        self.messages = [{"role": "user", "content": "fix the fixture"}]

    def tearDown(self):
        self.backend.__exit__()

    def test_nonstream_identity_reasoning_usage(self):
        self.backend.response["choices"][0]["message"]["reasoning_content"] = "private analysis"
        result = self.client.chat(self.messages)
        self.assertEqual(result["model"], "served-alias")
        self.assertNotEqual(result["model"], self.client.model)
        self.assertEqual(result["message"], {"role": "assistant", "content": "hello"})
        self.assertEqual(result["reasoning"], {"reasoning_content": "private analysis"})
        self.assertEqual(result["usage"], {"completion_tokens": 3})
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertFalse(result["stream_done"])
        self.assertEqual(self.client.requests[0]["model"], "served-alias")
        self.assertNotIn("messages", self.client.requests[0])

    def test_models_validated(self):
        self.backend.response = {"object": "list", "data": [{"id": "model-a"}, {"id": "model-b"}]}
        self.assertEqual(len(self.client.models()["data"]), 2)
        for data in ({}, {"data": [{}]}, {"data": [{"id": "x"}, {"id": "x"}]}):
            with self.subTest(data=data):
                self.backend.response = data
                with self.assertRaises(AgentError):
                    self.client.models()

    def test_unknown_requested_model_error_is_not_claimed_success(self):
        self.backend.status = 404
        self.backend.response = {"error": {"message": "not found"}}
        with self.assertRaises(APIError) as caught:
            self.client.chat(self.messages, model="deliberately-missing-model")
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(self.backend.requests[-1]["body"]["model"], "deliberately-missing-model")
        self.assertFalse(self.client.requests[-1]["success"])

    def test_invalid_response_identity(self):
        for model in (None, "", 42):
            with self.subTest(model=model):
                self.backend.response = completion(model=model)
                with self.assertRaisesRegex(AgentError, "model identity"):
                    self.client.chat(self.messages)

    def test_nonstream_tool_ids_and_roles_preserved(self):
        calls = [call("read_a"), call("read_b", arguments='{"path":"test_fixture.py"}')]
        self.backend.response = completion(None, calls)
        result = self.client.chat(self.messages)
        self.assertEqual(result["message"]["tool_calls"], calls)
        continuation = self.messages + [result["message"], {"role": "tool", "tool_call_id": "read_b", "content": "test content"}, {"role": "tool", "tool_call_id": "read_a", "content": "implementation content"}]
        self.backend.response = completion("all read")
        self.client.chat(continuation)
        self.assertEqual(self.backend.requests[-1]["body"]["messages"], continuation)

    def test_malformed_tool_arguments(self):
        for arguments in ("{", "[]", '{"path":"a","path":"b"}', '{"x":NaN}', '{"x":1e999}'):
            with self.subTest(arguments=arguments):
                self.backend.response = completion(None, [call(arguments=arguments)])
                with self.assertRaises(AgentError):
                    self.client.chat(self.messages)

    def test_invalid_missing_and_duplicate_ids(self):
        missing = call()
        del missing["id"]
        for calls in ([call("")], [call("with space")], [call(None)], [missing], [call(), call()]):
            with self.subTest(calls=calls):
                self.backend.response = completion(None, calls)
                with self.assertRaisesRegex(AgentError, "ID"):
                    self.client.chat(self.messages)

    def test_malformed_tool_schemas(self):
        variants = [call(), call(), call(), call(), call()]
        variants[0]["type"] = "unknown"
        variants[1]["function"]["arguments"] = {}
        variants[2]["function"]["extra"] = "bad"
        variants[3]["function"]["name"] = ""
        variants[4]["extra"] = "bad"
        for variant in variants:
            with self.subTest(variant=variant):
                self.backend.response = completion(None, [variant])
                with self.assertRaises(AgentError):
                    self.client.chat(self.messages)

    def test_invalid_tool_result_histories_never_send(self):
        assistant = {"role": "assistant", "content": None, "tool_calls": [call()]}
        tool = {"role": "tool", "tool_call_id": "call_1", "content": "actual output"}
        histories = [
            [assistant],
            [tool],
            [assistant, dict(tool, tool_call_id="wrong")],
            [assistant, {"role": "tool", "content": "missing id"}],
            [assistant, dict(tool, role="user")],
            [assistant, tool, tool],
            [assistant, tool, assistant, tool],
        ]
        for history in histories:
            with self.subTest(history=history):
                with self.assertRaises(AgentError):
                    self.client.chat(self.messages + history)
        self.assertEqual(self.backend.requests, [])

    def test_response_role_finish_and_legacy_rejected(self):
        variants = [completion(), completion(), completion(None, [call()]), completion()]
        variants[0]["choices"][0]["message"]["role"] = "tool"
        variants[1]["choices"][0]["finish_reason"] = "length"
        variants[2]["choices"][0]["finish_reason"] = "stop"
        variants[3]["choices"][0]["message"]["function_call"] = {"name": "legacy"}
        for variant in variants:
            with self.subTest(variant=variant):
                self.backend.response = variant
                with self.assertRaises(AgentError):
                    self.client.chat(self.messages)

    def test_split_stream_content_reasoning_and_usage(self):
        self.backend.content_type = "text/event-stream"
        self.backend.response = sse([
            chunk({"role": "assistant", "reasoning_content": "think "}),
            chunk({"reasoning_content": "separately", "content": "hé"}),
            chunk({"content": "llo"}),
            chunk({}, "stop"),
            {"model": "served-alias", "choices": [], "usage": {"completion_tokens": 5}},
        ])
        result = self.client.chat(self.messages, stream=True)
        self.assertEqual(result["message"]["content"], "héllo")
        self.assertEqual(result["reasoning"], {"reasoning_content": "think separately"})
        self.assertTrue(result["stream_done"])
        self.assertEqual(result["usage"]["completion_tokens"], 5)

    def test_stream_split_interleaved_tool_arguments(self):
        self.backend.content_type = "text/event-stream"
        self.backend.response = sse([
            chunk({"tool_calls": [{"index": 1, "id": "second", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"test'}}, {"index": 0, "id": "first", "type": "function", "function": {"name": "read_", "arguments": '{"path":'}}]}),
            chunk({"tool_calls": [{"index": 0, "function": {"name": "file", "arguments": '"implementation.py"}'}}, {"index": 1, "function": {"arguments": '_fixture.py"}'}}], "reasoning_content": "do not mix with args"}),
            chunk({}, "tool_calls"),
        ])
        result = self.client.chat(self.messages, stream=True)
        self.assertEqual(result["message"]["tool_calls"], [call("first"), call("second", arguments='{"path":"test_fixture.py"}')])
        self.assertIsNone(result["message"]["content"])
        self.assertEqual(result["reasoning"], {"reasoning_content": "do not mix with args"})

    def test_stream_done_finishes_without_waiting_for_http_eof(self):
        self.backend.content_type = "text/event-stream"
        self.backend.keep_open_after_body = True
        self.backend.response = sse([chunk({"content": "done"}, "stop")])
        self.client.request_timeout = 0.15
        start = time.monotonic()
        self.assertTrue(self.client.chat(self.messages, stream=True)["stream_done"])
        self.assertLess(time.monotonic() - start, 0.15)

    def test_stream_termination_required(self):
        self.backend.content_type = "text/event-stream"
        variants = [sse([chunk({"content": "x"}, "stop")], done=False), sse([chunk({"content": "x"})]), sse([chunk({"content": "x"}, "length")]), sse([chunk({}, "stop"), chunk({"content": "late"})]), sse([chunk({}, "stop")]) + b'data: {}\n\n', sse([chunk({}, "stop")])[:-1]]
        for response in variants:
            with self.subTest(response=response):
                self.backend.response = response
                with self.assertRaises(AgentError):
                    self.client.chat(self.messages, stream=True)

    def test_stream_invalid_indexes_ids_and_arguments(self):
        self.backend.content_type = "text/event-stream"
        variants = [
            [{"index": 2, **call()}],
            [{"index": True, **call()}],
            [{"index": 0, **call()}, {"index": 1, **call()}],
            [{"index": 0, "function": {"name": "read_file", "arguments": "{}"}}],
            [{"index": 0, **call(arguments="{")}],
            [call()],
        ]
        for calls in variants:
            with self.subTest(calls=calls):
                self.backend.response = sse([chunk({"tool_calls": calls}), chunk({}, "tool_calls")])
                with self.assertRaises(AgentError):
                    self.client.chat(self.messages, stream=True)

    def test_stream_model_identity_consistency(self):
        self.backend.content_type = "text/event-stream"
        self.backend.response = sse([chunk({"content": "hello"}), chunk({}, "stop", model="other")])
        with self.assertRaisesRegex(AgentError, "changed model"):
            self.client.chat(self.messages, stream=True)

    def test_crlf_comments_and_multiline_sse_data(self):
        self.backend.content_type = "text/event-stream; charset=utf-8"
        data = json.dumps(chunk({"content": "hello"}, "stop"))
        split = data.index('"choices"')
        self.backend.response = (": heartbeat\r\n\r\ndata: " + data[:split] + "\r\ndata: " + data[split:] + "\r\n\r\ndata: [DONE]\r\n\r\n").encode()
        self.assertEqual(self.client.chat(self.messages, stream=True)["message"]["content"], "hello")

    def test_api_errors_never_echo_body(self):
        test_key = "synthetic-local-test-token"
        self.client.api_key = test_key
        self.backend.status = 500
        self.backend.response = {"error": "server echoed " + test_key}
        with self.assertRaises(APIError) as caught:
            self.client.chat(self.messages)
        self.assertNotIn(test_key, str(caught.exception))
        self.assertNotIn(test_key, json.dumps(self.client.requests))

    def test_raw_internal_response_redacted_at_report_boundary_and_override(self):
        test_key = "synthetic-local-test-token"
        self.client.api_key = test_key
        self.backend.response = completion(test_key, model="echo-" + test_key, usage={"debug": test_key})
        result = self.client.chat(self.messages)
        self.assertEqual(result["message"]["content"], test_key)
        self.assertNotIn(test_key, json.dumps(redact(result, test_key)))
        self.assertNotIn(test_key, json.dumps(self.client.requests))
        self.assertEqual(self.backend.requests[-1]["authorization"], "Bearer " + test_key)
        self.client.chat(self.messages, api_key=None)
        self.assertIsNone(self.backend.requests[-1]["authorization"])

    def test_key_matching_schema_never_mutates_internal_protocol(self):
        self.client.api_key = "model"
        calls = [call("model", arguments='{"path":"model.py"}')]
        self.backend.response = completion(None, calls)
        result = self.client.chat(self.messages)
        self.assertEqual(result["model"], "served-alias")
        self.assertEqual(result["message"]["tool_calls"], calls)
        self.assertEqual(self.client.requests[0]["model"], "served-alias")
        self.assertTrue(self.client.requests[0]["success"])

    def test_request_records_preserve_trusted_schema_and_redact_usage(self):
        self.client.api_key = "status"
        self.backend.response = completion("hello", usage={"status": "status"})
        self.client.chat(self.messages)
        self.assertEqual(self.client.requests[0]["status"], 200)
        self.assertEqual(self.client.requests[0]["usage"], {"[REDACTED]": "[REDACTED]"})

    def test_auth_missing_wrong_correct_and_models_override(self):
        self.backend.api_key = "synthetic-local-auth-token"
        self.backend.response = {"data": [{"id": "served-alias"}]}
        self.client.api_key = self.backend.api_key
        for key in (None, "deliberately-wrong-token"):
            with self.subTest(key=key):
                with self.assertRaises(APIError) as caught:
                    self.client.models(api_key=key)
                self.assertEqual(caught.exception.status, 401)
        self.assertEqual(self.client.models()["data"][0]["id"], "served-alias")

    def test_content_type_compression_bad_json_and_duplicate_keys(self):
        self.backend.content_type = "text/html"
        with self.assertRaisesRegex(AgentError, "Content-Type"):
            self.client.chat(self.messages)
        self.backend.content_type = "application/json"
        self.backend.headers["Content-Encoding"] = "gzip"
        with self.assertRaisesRegex(AgentError, "compressed"):
            self.client.chat(self.messages)
        self.backend.headers.clear()
        for response in (b"{invalid", b'{"model":"a","model":"b"}', b"\xff"):
            self.backend.response = response
            with self.assertRaises(AgentError):
                self.client.chat(self.messages)

    def test_redirects_never_followed(self):
        with MockServer() as destination:
            self.backend.status = 302
            self.backend.headers["Location"] = destination.url + "/chat/completions"
            self.client.api_key = "synthetic-local-test-token"
            with self.assertRaises(APIError) as caught:
                self.client.chat(self.messages)
            self.assertEqual(caught.exception.status, 302)
            self.assertEqual(destination.requests, [])

    def test_proxy_environment_ignored(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""}):
            self.assertEqual(self.client.chat(self.messages)["message"]["content"], "hello")

    def test_request_and_response_size_limits(self):
        self.client.max_response_bytes = 1024
        with self.assertRaisesRegex(AgentError, "request exceeds"):
            self.client.chat([{"role": "user", "content": "a" * 1500}])
        self.backend.response = completion("a" * 1500)
        with self.assertRaisesRegex(AgentError, "response exceeds"):
            self.client.chat(self.messages)

    def test_request_timeout_with_slow_headers(self):
        self.client.request_timeout = 0.06
        self.backend.delay = 0.3
        start = time.monotonic()
        with self.assertRaisesRegex(AgentError, "time"):
            self.client.chat(self.messages)
        self.assertLess(time.monotonic() - start, 0.25)

    def test_overall_timeout_with_trickled_body_closes_socket(self):
        self.client.budget = Budget(0.08)
        self.backend.trickle = True
        start = time.monotonic()
        with self.assertRaisesRegex(AgentError, "time"):
            self.client.chat(self.messages)
        self.assertLess(time.monotonic() - start, 0.3)
        self.assertTrue(self.backend.disconnected.wait(0.3), "timeout must shut down the active socket")
        before = len(self.backend.requests)
        with self.assertRaisesRegex(AgentError, "budget"):
            self.client.chat(self.messages)
        self.assertEqual(before, len(self.backend.requests))

    def test_http10_trickle_deadline_closes_response_socket(self):
        self.backend.http_version = "HTTP/1.0"
        self.backend.trickle = True
        self.client.request_timeout = 0.06
        start = time.monotonic()
        with self.assertRaisesRegex(AgentError, "time"):
            self.client.chat(self.messages)
        self.assertLess(time.monotonic() - start, 0.3)
        self.assertTrue(self.backend.disconnected.wait(0.3))

    def test_client_request_cap(self):
        self.client.requests = [{"success": True}] * 128
        with self.assertRaisesRegex(AgentError, "128"):
            self.client.chat(self.messages)
        self.assertEqual(len(self.client.requests), 128)
        self.assertEqual(self.backend.requests, [])

    def test_invalid_base_url_and_limits(self):
        for url in ("http://user:password@127.0.0.1/v1", "file:///v1", "http://127.0.0.1/v1?token=bad", "http://127.0.0.1/wrong", "http://127.0.0.1:bad/v1"):
            with self.subTest(url=url):
                with self.assertRaises(AgentError):
                    Client(url, "model")
        for kwargs in ({"request_timeout": float("nan")}, {"request_timeout": 0}, {"max_tokens": 0}, {"max_response_bytes": 5}):
            with self.assertRaises(AgentError):
                Client(self.backend.url, "model", **kwargs)


class KeyAndJSONTests(unittest.TestCase):
    def test_key_file_permissions_symlink_nonregular_and_newlines(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "key"
            path.write_text("synthetic-file-token")
            path.chmod(0o600)
            self.assertEqual(load_api_key(path), "synthetic-file-token")
            path.chmod(0o400)
            self.assertEqual(load_api_key(path), "synthetic-file-token")
            path.chmod(0o644)
            with self.assertRaisesRegex(AgentError, "0600"):
                load_api_key(path)
            path.chmod(0o600)
            link = Path(temp) / "link"
            link.symlink_to(path)
            with self.assertRaises(AgentError):
                load_api_key(link)
            with self.assertRaises(AgentError):
                load_api_key(temp)
            fifo = Path(temp) / "fifo"
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(AgentError):
                load_api_key(fifo)
            for value in ("", "trailing\n", "line\rbreak", " space", "tab\tinside", "nonascii-é"):
                path.write_text(value)
                with self.assertRaises(AgentError) as caught:
                    load_api_key(path)
                if value:
                    self.assertNotIn(value, str(caught.exception))

    def test_key_file_owner_and_size(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "key"
            path.write_text("synthetic-file-token")
            path.chmod(0o600)
            with patch("protocol.os.geteuid", return_value=os.geteuid() + 1):
                with self.assertRaisesRegex(AgentError, "owned"):
                    load_api_key(path)
            path.write_text("a" * 8193)
            with self.assertRaisesRegex(AgentError, "size"):
                load_api_key(path)

    def test_key_environment_and_file_precedence(self):
        name = "A1_SYNTHETIC_TEST_KEY"
        with patch.dict(os.environ, {name: "synthetic-env-token"}):
            self.assertEqual(load_api_key(env_name=name), "synthetic-env-token")
            with self.assertRaises(AgentError):
                load_api_key("/deliberately-missing-key-file", name)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(AgentError, "unset"):
                load_api_key(env_name=name)
        self.assertIsNone(load_api_key())

    def test_redact_recursive_mapping_keys(self):
        self.assertEqual(redact({"token-value": ["a token-value", {"inner": "token-value"}]}, "token-value"), {"[REDACTED]": ["a [REDACTED]", {"inner": "[REDACTED]"}]})

    def test_redact_key_with_json_escapes_in_tool_arguments(self):
        test_key = 'synthetic-"quoted"-\\backslash-token'
        arguments = json.dumps({"content": test_key})
        cleaned = redact({"tool_calls": [call(arguments=arguments)]}, test_key)
        self.assertEqual(json.loads(cleaned["tool_calls"][0]["function"]["arguments"])["content"], "[REDACTED]")
        self.assertNotIn("quoted", json.dumps(cleaned))

    def test_strict_json_duplicate_constants_and_overflow(self):
        for value in ('{"a":1,"a":2}', "NaN", "Infinity", "-Infinity", "1e999", "{" + '"a":[' * 1100):
            with self.subTest(value=value[:40]):
                with self.assertRaises(AgentError):
                    strict_json_loads(value)
        self.assertEqual(strict_json_loads('{"value":1.25}'), {"value": 1.25})

    def test_budget_validation_and_expiration(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(AgentError):
                Budget(value)
        budget = Budget(5)
        self.assertGreater(budget.remaining(), 0)
        budget.deadline = time.monotonic() - 1
        with self.assertRaisesRegex(AgentError, "budget"):
            budget.check()


if __name__ == "__main__":
    unittest.main()
