#!/usr/bin/env python3
"""Offline tests of the exact task driver functions; never imports its VM setup.

Only selected function ASTs are executed with fake HTTP, timer, clock, and
persistence dependencies. No network connection, credential, VM, or model is
needed. These tests do not establish live inference or native timing quality.
Run: python3 -B reports/h010-flash64k-20260927/driver/test_stream.py
"""
import ast
import copy
import datetime
import hashlib
import json
from pathlib import Path
import types
import unittest


SOURCE = Path(__file__).with_name("qualify-body.py")


def extract_functions(*names):
    tree = ast.parse(SOURCE.read_text())
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("driver function missing")
    return compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec")


def event(delta=None, usage=None, finish=None):
    value = {"choices": [{"delta": delta or {}, "finish_reason": finish}]}
    if usage is not None:
        value["usage"] = usage
    return b"data: " + json.dumps(value).encode() + b"\n"


def usage(count, prompt=65536):
    return {"prompt_tokens": prompt, "completion_tokens": count,
            "total_tokens": prompt + count,
            "prompt_tokens_details": {"cached_tokens": 0}}


class Clock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def time(self):
        return 1790467200.0 + self.value

    def now(self):
        return datetime.datetime.fromtimestamp(
            self.time(), datetime.timezone.utc).isoformat()


class Timer:
    def __init__(self, seconds, callback):
        self.seconds, self.callback = seconds, callback
        self.daemon = False
        self.started = self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class Response:
    def __init__(self, clock, items, status=200, tail=b""):
        self.clock, self.items, self.status = clock, list(items), status
        self.tail = tail
        self.read_started = self.eof = self.closed = False
        self.lines_read = 0
        self.on_read = None

    def readline(self, size):
        self.read_started = True
        self.clock.value += .75
        if self.on_read:
            self.on_read(self)
        if not self.items:
            self.eof = True
            return b""
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert len(item) < size, "mock line must fit bound"
        self.lines_read += 1
        return item

    def read(self, size):
        self.read_started = True
        self.clock.value += .25
        result, self.tail = self.tail[:size], self.tail[size:]
        if not self.tail:
            self.eof = True
        return result

    def isclosed(self):
        return self.eof or self.closed

    def close(self):
        self.closed = True


class Harness:
    def __init__(self, items, status=200, tail=b"", boundary_delay=0):
        self.clock = Clock()
        self.response = Response(self.clock, items, status, tail)
        self.persisted = []
        self.connections = []
        self.timers = []
        self.boundary_delay = boundary_delay
        response, owner = self.response, self

        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout
                self.closed = False
                self.requested = None
                owner.connections.append(self)

            def request(self, method, path, body, headers):
                self.requested = (method, path, body, headers)

            def getresponse(self):
                return response

            def close(self):
                self.closed = True

        def make_timer(seconds, callback):
            timer = Timer(seconds, callback)
            self.timers.append(timer)
            return timer

        def persist():
            # A request boundary may persist before reading, and partial/final
            # state may persist only once the client response has been closed.
            if response.read_started and not response.closed:
                raise AssertionError("persistence occurred inside active stream reader")
            self.persisted.append(copy.deepcopy(self.namespace["result"]))
            self.clock.value += self.boundary_delay

        def cancel(reason):
            self.namespace["cancel_reason"] = reason

        self.namespace = {
            "json": json, "datetime": datetime, "hashlib": hashlib,
            "time": self.clock, "now": self.clock.now,
            "http": types.SimpleNamespace(client=types.SimpleNamespace(HTTPConnection=Connection)),
            "threading": types.SimpleNamespace(Timer=make_timer),
            "result": {"fixtures": {"measured65536": {"expected_result": {
                "early": "EARLY", "middle": "MIDDLE", "end": "END", "aligned_bytes": 256}}}},
            "MODE": "measured65536", "REQUEST_CAP": 4200,
            "remaining": lambda: 5000 - (self.clock.value - 100),
            "persist": persist, "cancel": cancel, "cancel_reason": None,
            "key": "mock-only-not-a-credential", "active_connection": None,
            "active_response": None, "raw_bytes": 0, "raw_batches": {},
        }
        exec(extract_functions("buffer", "stream", "qualify"), self.namespace)

    def run(self, output=256):
        return self.namespace["stream"]({"max_tokens": output, "messages": []})

    @property
    def row(self):
        return self.namespace["result"]["request"]

    @property
    def raw(self):
        return self.namespace["raw_batches"].get("measured65536-SSE.jsonl", [])


class StreamTests(unittest.TestCase):
    def assert_closed_and_checkpointed(self, harness):
        self.assertTrue(harness.response.closed)
        self.assertTrue(harness.connections[0].closed)
        self.assertTrue(harness.timers[0].cancelled)
        self.assertEqual(len(harness.persisted), 2)
        self.assertEqual(harness.persisted[-1]["request"], harness.row)
        self.assertIsNone(harness.namespace["result"]["active_request"])
        self.assertIsNone(harness.namespace["active_connection"])
        self.assertIsNone(harness.namespace["active_response"])

    def test_completed_stream_drains_without_persistence_in_hot_loop(self):
        lines = [b": keepalive\n", event({"reasoning_content": "check"}, usage(1)),
                 event({"content": "answer"}, usage(2)), event({}, usage(3), "stop"),
                 b"data: [DONE]\n"]
        harness = Harness(lines)
        row = harness.run()
        self.assertEqual(row["status"], "TRANSPORT_PASS")
        self.assertEqual(row["output"], "answer")
        self.assertEqual(row["reasoning"], "check")
        self.assertEqual(row["usage"], usage(3))
        self.assertEqual(row["input_tokens"], 65536)
        self.assertEqual(row["output_tokens"], 3)
        self.assertEqual(row["nonempty_delta_count"], 2)
        self.assertEqual([x["line"] for x in harness.raw], [x.decode() for x in lines])
        self.assertTrue(row["sse_done"] and row["body_drained"])
        self.assertEqual(row["ttft_seconds"], 1.5)
        self.assertEqual(row["last_nonempty_delta_seconds"], 2.25)
        self.assertIn("first_native_delta_client_utc", row)
        self.assertIn("last_native_delta_client_utc", row)
        self.assertGreater(row["elapsed_seconds"], row["ttft_seconds"])
        self.assertEqual(row["decode_rate_status"], "NATIVE_INCREMENTAL_USAGE_OBSERVED_CLIENT_TIME_WINDOW")
        self.assert_closed_and_checkpointed(harness)

    def test_malformed_line_keeps_raw_and_previous_usage_delta_and_timing(self):
        lines = [event({"reasoning_content": "partial thought"}, usage(7)),
                 event({"content": "partial answer"}, usage(8)), b"data: {invalid\n"]
        harness = Harness(lines)
        with self.assertRaises(json.JSONDecodeError):
            harness.run()
        self.assertEqual(harness.row["status"], "PARTIAL_OR_FAIL")
        self.assertEqual(harness.row["error_type"], "JSONDecodeError")
        self.assertEqual(harness.row["usage"], usage(8))
        self.assertEqual(harness.row["reasoning"], "partial thought")
        self.assertEqual(harness.row["output"], "partial answer")
        self.assertEqual(harness.row["ttft_seconds"], .75)
        self.assertEqual(harness.row["last_nonempty_delta_seconds"], 1.5)
        self.assertEqual([x["line"] for x in harness.raw], [x.decode() for x in lines])
        self.assertFalse(harness.row["body_drained"])
        self.assert_closed_and_checkpointed(harness)

    def test_disconnect_keeps_partial_data_and_error_is_not_native_failure(self):
        line = event({"content": "partial answer"}, usage(9))
        harness = Harness([line, ConnectionResetError("mock disconnect")])
        with self.assertRaises(ConnectionResetError):
            harness.run()
        self.assertEqual(harness.row["status"], "PARTIAL_OR_FAIL")
        self.assertEqual(harness.row["failure_origin"], "request_or_transport")
        self.assertEqual(harness.row["error_type"], "ConnectionResetError")
        self.assertEqual(harness.row["usage"], usage(9))
        self.assertEqual(harness.row["output"], "partial answer")
        self.assertEqual(harness.raw[0]["line"], line.decode())
        self.assertEqual(harness.row["ttft_seconds"], .75)
        self.assertFalse(harness.row["sse_done"] or harness.row["body_drained"])
        self.assert_closed_and_checkpointed(harness)

    def test_cancelled_read_retains_partial_data_and_distinguishes_client_cancel(self):
        harness = Harness([event({"content": "partial"}, usage(4)), b": wake\n"])

        def on_read(response):
            if response.lines_read == 1:
                harness.namespace["cancel"]("whole_request_cap")

        harness.response.on_read = on_read
        with self.assertRaisesRegex(RuntimeError, "whole_request_cap"):
            harness.run()
        self.assertEqual(harness.row["status"], "CLIENT_CANCELLED")
        self.assertEqual(harness.row["output"], "partial")
        self.assertEqual(harness.row["usage"], usage(4))
        self.assertFalse(harness.row["cancellation_is_native_failure_evidence"])
        self.assert_closed_and_checkpointed(harness)

    def test_eof_without_done_is_not_complete(self):
        harness = Harness([event({"content": "partial"}, usage(4), "stop")])
        with self.assertRaisesRegex(AssertionError, "native_stream_incomplete"):
            harness.run()
        self.assertEqual(harness.row["output"], "partial")
        self.assertTrue(harness.row["body_drained"])
        self.assertFalse(harness.row["sse_done"])
        self.assert_closed_and_checkpointed(harness)

    def test_boundary_checkpoint_time_is_deducted_from_global_request_budget(self):
        harness = Harness([event({"content": "answer"}, usage(1), "stop"),
                           b"data: [DONE]\n"], boundary_delay=1000)
        harness.run()
        # Initial global remaining is 5000 s. The first checkpoint costs
        # 1000 s, then the reserved eight seconds leaves a 3992 s request cap.
        self.assertEqual(harness.connections[0].timeout, 3992)
        self.assertEqual(harness.timers[0].seconds, 3992)
        self.assertEqual(harness.row["actual_cap_seconds"], 3992)
        start = datetime.datetime.fromisoformat(harness.row["start_utc"])
        end = datetime.datetime.fromisoformat(harness.row["request_deadline_utc"])
        self.assertEqual((end - start).total_seconds(), 3992)
        # Client elapsed starts after the boundary checkpoint, as documented.
        self.assertLess(harness.row["elapsed_seconds"], 3)
        self.assert_closed_and_checkpointed(harness)

    def test_trailing_body_at_bound_does_not_claim_eof(self):
        tail = b"x" * (8 * 1024 * 1024)
        harness = Harness([event({"content": "answer"}, usage(1), "stop"),
                           b"data: [DONE]\n"], tail=tail)
        with self.assertRaisesRegex(AssertionError, "post_done_body_bound_no_eof_proof"):
            harness.run()
        self.assertTrue(harness.row["sse_done"])
        self.assertFalse(harness.row["body_drained"])
        self.assertEqual(harness.row["status"], "PARTIAL_OR_FAIL")
        self.assertEqual(harness.raw[-1]["post_done_bytes"], tail.decode())
        self.assert_closed_and_checkpointed(harness)

    def test_hot_loop_and_buffer_have_no_filesystem_or_guard_calls(self):
        tree = ast.parse(SOURCE.read_text())
        stream = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "stream")
        hot_loop = next(x for x in ast.walk(stream) if isinstance(x, ast.While))
        buffer = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "buffer")
        forbidden = {"persist", "open", "fsync", "transaction", "acquire_lease", "status",
                     "AnchoredRoot", "MountedStorageGuard", "root_payload_guard", "write_text",
                     "write_bytes", "subprocess", "check_output", "run"}
        for section in (hot_loop, buffer):
            called = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                      for node in ast.walk(section) if isinstance(node, ast.Call)
                      and isinstance(node.func, (ast.Name, ast.Attribute))}
            self.assertEqual(called & forbidden, set())

    def test_output_cap_is_unproven_even_if_json_looks_complete(self):
        harness = Harness([])
        expected = harness.namespace["result"]["fixtures"]["measured65536"]["expected_result"]
        for output in ("", '{"early":"EARLY"}', json.dumps(expected)):
            row = {"input_tokens": 65536, "cached_input_tokens": 0,
                   "output": output, "finish_reason": "length"}
            harness.namespace["qualify"](row, 65536)
            self.assertEqual(row["semantic_status"], "UNPROVEN_OUTPUT_CAP")
            self.assertTrue(row["output_cap_includes_reasoning"])

    def test_completed_correctness_and_wrong_answer_are_distinct(self):
        harness = Harness([])
        expected = harness.namespace["result"]["fixtures"]["measured65536"]["expected_result"]
        for output, wanted in ((json.dumps(expected), "PASS"), ("{}", "FAIL_COMPLETED_ANSWER")):
            row = {"input_tokens": 65536, "cached_input_tokens": 0,
                   "output": output, "finish_reason": "stop"}
            harness.namespace["qualify"](row, 65536)
            self.assertEqual(row["semantic_status"], wanted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
