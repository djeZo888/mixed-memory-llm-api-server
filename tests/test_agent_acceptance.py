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
            records.append({"method": "POST", "path": self.path, "body": body})
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
                elif scenario == "loop":
                    sequence = [[call("loop-" + str(round_no), "read_file", {"path": "calc.py"})]] * (round_no + 1)
                calls = sequence[min(round_no - 1, len(sequence) - 1)]
                result = completion("I fixed the bug and all tests passed.", calls=calls)
            if scenario == "wrong_response_model":
                result["model"] = "unrequested-synthetic-model"
            if body.get("stream"):
                self.send_data(200, events_for(result), "text/event-stream")
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
    def run_case(self, scenario="success", auth=False, **kwargs):
        with backend(scenario, auth) as (url, records):
            client = Client(url, MODEL, api_key=SYNTHETIC_KEY if auth or scenario == "echo_key" else None,
                            budget=Budget(20), request_timeout=3)
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
