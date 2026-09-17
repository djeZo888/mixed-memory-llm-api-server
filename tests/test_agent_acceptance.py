"""End-to-end synthetic HTTP evidence; never contacts inference services."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "agent"))
from acceptance import redact_report, run_acceptance
from protocol import Budget, Client

SYNTHETIC_KEY = "synthetic-fixture-credential"
MODEL = "synthetic-add-model"
FIX = "def add(a, b):\n    return a + b\n"


def call(identity, name, args):
    return {"id": identity, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def completion(content="Hello", calls=None, model=MODEL):
    message = {"role": "assistant", "content": None if calls else content,
               "reasoning_content": "Synthetic reasoning, distinct from content and tools."}
    if calls:
        message["tool_calls"] = calls
    return {"id": "synthetic-completion", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}}


def events_for(result):
    message = result["choices"][0]["message"]
    chunks = [{"role": "assistant"}, {"reasoning_content": message["reasoning_content"]}]
    calls = message.get("tool_calls")
    if calls:
        # Interleave two calls and split every argument string across deltas.
        for i, item in enumerate(calls):
            chunks.append({"tool_calls": [{"index": i, "id": item["id"], "type": "function",
                                           "function": {"name": item["function"]["name"], "arguments": ""}}]})
        longest = max(len(item["function"]["arguments"]) for item in calls)
        for pos in range(0, longest, 4):
            for i, item in enumerate(calls):
                fragment = item["function"]["arguments"][pos:pos + 4]
                if fragment:
                    chunks.append({"tool_calls": [{"index": i, "function": {"arguments": fragment}}]})
    else:
        for word in message["content"].split():
            chunks.append({"content": word + " "})
    packets = []
    for delta in chunks:
        packets.append({"id": "synthetic-completion", "model": result["model"],
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
    packets.append({"id": "synthetic-completion", "model": result["model"],
                    "choices": [{"index": 0, "delta": {}, "finish_reason": result["choices"][0]["finish_reason"]}]})
    packets.append({"id": "synthetic-completion", "model": result["model"], "choices": [], "usage": result["usage"]})
    return ("".join("data: " + json.dumps(packet) + "\r\n\r\n" for packet in packets) + "data: [DONE]\r\n\r\n").encode()


@contextlib.contextmanager
def backend(scenario="success", auth=False):
    records = []
    state = {"round": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_data(self, status, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if auth and self.headers.get("Authorization") != "Bearer " + SYNTHETIC_KEY:
                self.send_data(401, {"error": {"message": "unauthorized"}})
                return False
            return True

        def do_GET(self):
            records.append({"method": "GET", "path": self.path})
            if self.authorized():
                self.send_data(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            header = self.headers.get("Authorization")
            auth_kind = "missing" if header is None else "correct" if header == "Bearer " + SYNTHETIC_KEY else "wrong"
            records.append({"method": "POST", "path": self.path, "body": body,
                            "auth_kind": auth_kind})
            if not self.authorized():
                return
            if body["model"] != MODEL and scenario != "accept_invalid_model":
                self.send_data(404, {"error": {"message": "Unknown model"}})
                return
            if not body.get("tools"):
                result = completion(content="Hello " + (SYNTHETIC_KEY if scenario == "echo_key" else "worker"))
            else:
                state["round"] += 1
                round_no = state["round"]
                reads = [call("read-code", "read_file", {"path": "calc.py"}),
                         call("read-test", "read_file", {"path": "test_calc.py"})]
                write = [call("edit-code", "write_file", {"path": "calc.py", "content": FIX})]
                test = [call("test-code", "run_tests", {})]
                sequence = [reads, write, test, None]
                if scenario == "claim_only":
                    sequence = [None]
                elif scenario == "no_read":
                    sequence = [write, test, None]
                elif scenario == "no_write":
                    sequence = [reads, test, None]
                elif scenario == "no_test":
                    sequence = [reads, write, None]
                elif scenario == "bad_fix":
                    sequence = [reads, [call("edit-code", "write_file", {"path": "calc.py", "content": "def add(a, b):\n    return a * b\n"})], test, None]
                elif scenario == "edit_after_test":
                    sequence = [reads, write, test,
                                [call("second-edit", "write_file", {"path": "calc.py", "content": "def add(a, b):\n    return b + a\n"})], None]
                elif scenario == "test_tampering":
                    sequence = [reads, [call("edit-tests", "write_file", {"path": "test_calc.py", "content": "pass\n"})]]
                elif scenario == "reused_id":
                    sequence = [reads, [call("read-code", "write_file", {"path": "calc.py", "content": FIX})]]
                elif scenario == "malformed_json":
                    broken = call("broken", "read_file", {})
                    broken["function"]["arguments"] = "{bad"
                    sequence = [[broken]]
                elif scenario == "length_content":
                    sequence = [None]
                elif scenario == "length_partial_json":
                    broken = call("broken", "write_file", {})
                    broken["function"]["arguments"] = '{"path":"calc.py","content":"' + SYNTHETIC_KEY
                    sequence = [[broken]]
                elif scenario == "loop":
                    sequence = [[call("loop-" + str(round_no), "read_file", {"path": "calc.py"})]] * (round_no + 1)
                calls = sequence[min(round_no - 1, len(sequence) - 1)]
                result = completion("I fixed the bug and all tests passed.", calls=calls)
            if scenario == "length_content" or (body.get("tools") and
                    (scenario.startswith("length_") or scenario == "missing_done_length")):
                result["choices"][0]["finish_reason"] = "length"
                result["choices"][0]["message"]["reasoning_content"] = SYNTHETIC_KEY
                result["usage"] = {"prompt_tokens": 7, "completion_tokens": 2048,
                                   "total_tokens": 2055, "provider_debug": SYNTHETIC_KEY}
                if scenario == "length_secret_model":
                    result["model"] = "synthetic-" + SYNTHETIC_KEY
            if scenario == "wrong_response_model":
                result["model"] = "unrequested-synthetic-model"
            if body.get("stream"):
                data = events_for(result)
                if body.get("tools") and scenario in {"missing_done", "missing_done_length", "truncated_sse"}:
                    data = data.removesuffix(b"data: [DONE]\r\n\r\n")
                    if scenario == "truncated_sse":
                        data += b'data: {"unfinished":'
                self.send_data(200, data, "text/event-stream")
            else:
                self.send_data(200, result)

    class LocalServer(ThreadingHTTPServer):
        def server_bind(self):
            # HTTPServer otherwise performs unnecessary reverse-DNS discovery.
            socketserver.TCPServer.server_bind(self)
            self.server_name = "localhost"
            self.server_port = self.server_address[1]

    server = LocalServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port) + "/v1", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class AcceptanceTests(unittest.TestCase):
    def run_case(self, scenario="success", auth=False, reasoning_effort=None, **kwargs):
        with backend(scenario, auth) as (url, records):
            client = Client(url, MODEL, api_key=SYNTHETIC_KEY if auth or scenario == "echo_key" else None,
                            budget=Budget(20), request_timeout=3, reasoning_effort=reasoning_effort)
            report = run_acceptance(client, auth="enabled" if auth else "disabled",
                                    evidence_kind="synthetic", **kwargs)
        return report, records

    def test_actual_fix_and_tool_result_id_continuation(self):
        report, records = self.run_case()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["checks"]["auth"]["status"], "NOT_TESTED")
        self.assertEqual(report["opencode_e2e"], "NOT_TESTED")
        self.assertEqual(report["clean_linux_install"], "NOT_TESTED")
        final_request = [r["body"] for r in records if r.get("body", {}).get("tools")][-1]
        tool_results = [m for m in final_request["messages"] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_results], ["read-code", "read-test", "edit-code", "test-code"])
        for message in final_request["messages"]:
            self.assertNotIn("reasoning_content", message)
        evidence = report["agent"]["evidence"]
        self.assertTrue(evidence["implementation_changed"])
        self.assertTrue(evidence["tests_unchanged"])
        self.assertIn("return a + b", evidence["diff"])
        self.assertIn("return a - b", evidence["diff"])
        self.assertNotEqual(evidence["initial_test"]["exit_code"], 0)
        self.assertEqual(evidence["final_test"]["exit_code"], 0)
        self.assertTrue(report["requests"])

    def test_streaming_agent_with_interleaved_read_calls(self):
        report, _ = self.run_case(stream_tools=True)
        self.assertEqual(report["status"], "PASS", report)
        self.assertTrue(all(item["stream_done"] for item in report["agent"]["rounds"]))

    def test_auth_missing_wrong_correct(self):
        report, _ = self.run_case(auth=True)
        self.assertEqual(report["status"], "PASS", report)
        for route in ("models", "chat"):
            for label in ("missing", "wrong", "correct"):
                self.assertEqual(report["checks"]["auth_" + label + "_" + route]["status"], "PASS")

    def assert_effort_capture(self, report, records, effort, stream_tools):
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["limits"]["reasoning_effort"], effort)
        posts = [item for item in records if item["method"] == "POST"]
        # Three ordinary/invalid-model probes, three auth probes and four agent rounds.
        self.assertEqual(len(posts), 10)
        self.assertEqual({item["auth_kind"] for item in posts}, {"missing", "wrong", "correct"})
        self.assertEqual(sum(item["body"]["model"] != MODEL for item in posts), 1)
        probes = [item["body"] for item in posts if "tools" not in item["body"]]
        self.assertEqual(len(probes), 6)
        self.assertEqual(sum(bool(item["stream"]) for item in probes), 1)
        rounds = [item["body"] for item in posts if "tools" in item["body"]]
        self.assertEqual(len(rounds), 4)
        self.assertEqual([item["stream"] for item in rounds], [stream_tools] * 4)
        for item in posts:
            body = item["body"]
            expected_fields = {"model", "messages", "stream", "max_tokens"}
            if "tools" in body:
                expected_fields.add("tools")
            if effort is None:
                self.assertNotIn("reasoning_effort", body)
            else:
                expected_fields.add("reasoning_effort")
                self.assertEqual(body["reasoning_effort"], effort)
            self.assertEqual(set(body), expected_fields)
            for message in body["messages"]:
                self.assertFalse(any(field.startswith("reasoning") for field in message))
        for body, expected in zip(rounds, ([], ["read-code", "read-test"],
                                           ["read-code", "read-test", "edit-code"],
                                           ["read-code", "read-test", "edit-code", "test-code"])):
            self.assertEqual([message["tool_call_id"] for message in body["messages"]
                              if message["role"] == "tool"], expected)
        self.assertTrue(report["agent"]["evidence"]["tests_unchanged"])
        self.assertEqual(report["agent"]["evidence"]["final_test"]["exit_code"], 0)

    def test_default_effort_omitted_on_every_chat_probe_and_continuation(self):
        for stream_tools in (False, True):
            with self.subTest(stream_tools=stream_tools):
                report, records = self.run_case(auth=True, stream_tools=stream_tools)
                self.assert_effort_capture(report, records, None, stream_tools)

    def test_low_effort_on_every_chat_probe_and_continuation(self):
        for stream_tools in (False, True):
            with self.subTest(stream_tools=stream_tools):
                report, records = self.run_case(auth=True, reasoning_effort="low", stream_tools=stream_tools)
                self.assert_effort_capture(report, records, "low", stream_tools)

    def test_length_is_failed_with_safe_metadata_and_no_tools_executed(self):
        for scenario in ("length_content", "length_tools", "length_partial_json"):
            for stream_tools in (False, True):
                with self.subTest(scenario=scenario, stream_tools=stream_tools):
                    report, _ = self.run_case(scenario, auth=True, reasoning_effort="low",
                                              stream_tools=stream_tools)
                    self.assertEqual(report["status"], "FAIL", report)
                    agent = report["agent"]
                    self.assertEqual(agent["status"], "FAIL")
                    self.assertEqual(agent["rounds"], [])
                    self.assertEqual(agent["evidence"]["calls"], [])
                    self.assertFalse(agent["evidence"]["implementation_changed"])
                    request = report["requests"][-1]
                    self.assertEqual(request["status"], 200)
                    self.assertFalse(request["success"])
                    self.assertEqual(request["classification"], "token_budget_exhausted")
                    self.assertEqual(request["finish_reason"], "length")
                    self.assertEqual(request["model"], MODEL)
                    self.assertEqual(request["usage"], {"prompt_tokens": 7, "completion_tokens": 2048,
                                                       "total_tokens": 2055})
                    self.assertEqual(request["stream_done"], stream_tools)
                    if scenario == "length_partial_json":
                        self.assertEqual(request["parsing_failure"], "invalid_assistant_message")
                    else:
                        self.assertNotIn("parsing_failure", request)
                    diagnostics = {field: request[field] for field in
                                   ("classification", "finish_reason", "model", "usage", "stream_done")}
                    if scenario == "length_partial_json":
                        diagnostics["parsing_failure"] = "invalid_assistant_message"
                    self.assertEqual(agent["diagnostics"], diagnostics)
                    if scenario == "length_content":
                        for name, streamed in (("chat", False), ("streaming_end", True),
                                               ("auth_correct_chat", False)):
                            self.assertEqual(report["checks"][name]["status"], "FAIL")
                            self.assertEqual(report["checks"][name]["diagnostics"],
                                             {**diagnostics, "stream_done": streamed})
                    self.assertNotIn(SYNTHETIC_KEY, json.dumps(report))
                    self.assertNotIn("provider_debug", json.dumps(report))

    def test_length_diagnostic_model_is_redacted_at_report_boundary(self):
        for stream_tools in (False, True):
            with self.subTest(stream_tools=stream_tools):
                report, _ = self.run_case("length_secret_model", auth=True, stream_tools=stream_tools)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["agent"]["evidence"]["calls"], [])
                request = report["requests"][-1]
                self.assertEqual(request["classification"], "token_budget_exhausted")
                self.assertEqual(request["model"], "synthetic-[REDACTED]")
                self.assertNotIn(SYNTHETIC_KEY, json.dumps(report))

    def test_malformed_arguments_without_length_are_not_token_exhaustion(self):
        for stream_tools in (False, True):
            with self.subTest(stream_tools=stream_tools):
                report, _ = self.run_case("malformed_json", stream_tools=stream_tools)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["agent"]["status"], "FAIL")
                self.assertEqual(report["agent"]["evidence"]["calls"], [])
                self.assertIn("malformed JSON", report["agent"]["error"])
                self.assertNotEqual(report["requests"][-1].get("classification"), "token_budget_exhausted")

    def test_incomplete_sse_is_not_complete_token_exhaustion(self):
        for scenario in ("missing_done", "missing_done_length", "truncated_sse"):
            with self.subTest(scenario=scenario):
                report, _ = self.run_case(scenario, stream_tools=True)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["agent"]["status"], "FAIL")
                self.assertEqual(report["agent"]["evidence"]["calls"], [])
                self.assertNotEqual(report["requests"][-1].get("classification"), "token_budget_exhausted")
                self.assertNotIn("token_budget_exhausted", json.dumps(report))
                self.assertIn("SSE event" if scenario == "truncated_sse" else "[DONE]",
                              report["agent"]["error"])

    def test_echoed_key_redacted_from_all_evidence(self):
        report, _ = self.run_case("echo_key")
        self.assertEqual(report["status"], "PASS", report)
        self.assertNotIn(SYNTHETIC_KEY, json.dumps(report))

    def test_key_matching_schema_does_not_change_protocol_or_report_outcome(self):
        for key in ("model", "status", "PASS", "read-code"):
            with self.subTest(key=key), backend() as (url, records):
                client = Client(url, MODEL, api_key=key, budget=Budget(20), request_timeout=3)
                report = run_acceptance(client, evidence_kind="synthetic")
                self.assertEqual(report["status"], "PASS", report)
                self.assertEqual(report["agent"]["status"], "PASS")
                final_request = [r["body"] for r in records if r.get("body", {}).get("tools")][-1]
                self.assertEqual([m["tool_call_id"] for m in final_request["messages"] if m["role"] == "tool"],
                                 ["read-code", "read-test", "edit-code", "test-code"])
        masked = redact_report({"status": "PASS", "usage": {"model": "model"}, "reasoning": {"model": "model"}}, "model")
        self.assertEqual(masked["status"], "PASS")
        self.assertNotIn("model", json.dumps(masked))

    def test_diagnostic_redaction_preserves_trusted_fields_and_bounds_model(self):
        diagnostic = {"classification": "token_budget_exhausted", "finish_reason": "length",
                      "model": MODEL, "usage": {"prompt_tokens": 7, "completion_tokens": 2048,
                                                "total_tokens": 2055,
                                                "completion_tokens_details": {"reasoning_tokens": 1900}},
                      "stream_done": True}
        for key in ("completion_tokens", "reasoning_tokens", "length", "token_budget_exhausted", "x"):
            for expanded in (False, True):
                with self.subTest(key=key, expanded=expanded):
                    model = key * (1024 // len(key)) if expanded else "synthetic-" + key
                    original = {**diagnostic, "model": model}
                    redacted_model = "[REDACTED]" * (1024 // len(key)) if expanded else "synthetic-[REDACTED]"
                    expected = {**diagnostic, "model": None if len(redacted_model) > 1024 else redacted_model}
                    self.assertEqual(redact_report(original, key), expected)
                    wrapped = {"checks": {"chat": {"status": "FAIL", "diagnostics": original}},
                               "agent": {"status": "FAIL", "diagnostics": original},
                               "requests": [{"status": 200, "success": False, **original}]}
                    masked = redact_report(wrapped, key)
                    self.assertEqual(masked["checks"]["chat"], {"status": "FAIL", "diagnostics": expected})
                    self.assertEqual(masked["agent"], {"status": "FAIL", "diagnostics": expected})
                    self.assertEqual(masked["requests"], [{"status": 200, "success": False, **expected}])

    def test_invalid_model_silent_alias_is_failure(self):
        report, _ = self.run_case("accept_invalid_model")
        self.assertEqual(report["checks"]["invalid_model"]["status"], "FAIL")
        self.assertEqual(report["status"], "FAIL")

    def test_unrequested_response_identity_is_failure(self):
        report, _ = self.run_case("wrong_response_model")
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["checks"]["chat"]["status"], "FAIL")
        self.assertEqual(report["agent"]["rounds"][0]["model"], "unrequested-synthetic-model")

    def test_claims_do_not_establish_success(self):
        for scenario in ("claim_only", "no_read", "no_write", "no_test", "bad_fix", "edit_after_test", "test_tampering", "reused_id", "malformed_json"):
            with self.subTest(scenario=scenario):
                report, _ = self.run_case(scenario)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["agent"]["status"], "FAIL")
                self.assertNotEqual(report["agent"]["evidence"]["initial_test"]["exit_code"], 0)

    def test_round_budget(self):
        report, _ = self.run_case("loop", max_rounds=2)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(len(report["agent"]["rounds"]), 2)
        self.assertIn("Round budget", report["agent"]["error"])

    def test_call_budget_rejects_whole_batch(self):
        report, _ = self.run_case(max_tool_calls=1)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("Tool-call budget", report["agent"]["error"])
        self.assertEqual(report["agent"]["evidence"]["calls"], [])

    def test_cli_writes_private_report_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, backend() as (url, _):
            destination = Path(directory) / "result.json"
            command = [sys.executable, "scripts/agent/acceptance.py", "--base-url", url, "--model", MODEL,
                       "--report", str(destination), "--overall-timeout", "20", "--request-timeout", "3"]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(destination.read_text())["status"], "PASS")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            original = destination.read_bytes()
            proc = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(destination.read_bytes(), original)

    def test_cli_selected_effort_is_reported_and_sent(self):
        with tempfile.TemporaryDirectory() as directory, backend() as (url, records):
            destination = Path(directory) / "result.json"
            command = [sys.executable, "scripts/agent/acceptance.py", "--base-url", url, "--model", MODEL,
                       "--report", str(destination), "--overall-timeout", "20", "--request-timeout", "3",
                       "--reasoning-effort", "low", "--stream-tools"]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads(destination.read_text())
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["limits"]["reasoning_effort"], "low")
            posts = [item["body"] for item in records if item["method"] == "POST"]
            self.assertEqual(len(posts), 7)
            self.assertTrue(all(body.get("reasoning_effort") == "low" for body in posts))
            self.assertEqual(len([body for body in posts if body.get("tools")]), 4)

    def test_cli_invalid_effort_fails_before_http_or_report_creation(self):
        with tempfile.TemporaryDirectory() as directory, backend() as (url, records):
            destination = Path(directory) / "result.json"
            for value in ("", "LOW", "unsupported", '{"reasoning_effort":"low"}'):
                with self.subTest(value=value):
                    command = [sys.executable, "scripts/agent/acceptance.py", "--base-url", url,
                               "--model", MODEL, "--report", str(destination), "--reasoning-effort", value]
                    proc = subprocess.run(command, capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn("--reasoning-effort", proc.stderr)
                    self.assertFalse(destination.exists())
                    self.assertEqual(records, [])


def write_synthetic_evidence(destination):
    """Reproduce committed evidence entirely against this in-process mock."""
    with backend(auth=True) as (url, _):
        client = Client(url, MODEL, api_key=SYNTHETIC_KEY,
                        budget=Budget(20), request_timeout=3)
        report = run_acceptance(client, auth="enabled", stream_tools=True,
                                evidence_kind="synthetic")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print("Synthetic HTTP evidence: " + report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-evidence":
        raise SystemExit(write_synthetic_evidence(sys.argv[2]))
    unittest.main()
