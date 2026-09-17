#!/usr/bin/env python3
"""Exercise the ordinary verifier with real pinned OpenCode and synthetic HTTP.

Creates a fresh private worker installation using the committed npm lock. The
server is a deterministic test double: this proves client plumbing, never live
model quality, server readiness, or production acceptance. No VM is contacted.
"""

import argparse
import contextlib
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
import sys
import threading

sys.dont_write_bytecode = True
from wire_fixture import CLIENT, FixtureError, WireServer, child, require
from client_common import absolute_path, isolated_env, json_bytes, private_dir, verify_install, write_new

MAX_BODY = 2 * 1024 * 1024
MAX_REQUESTS = 16  # Includes OpenCode's auxiliary/title requests.
FIXED_COMMAND = "python3 -I -B test_text_utils.py"
CALL_NAMES = ("read", "read", "edit", "bash")
CALL_IDS = ("call_verify_read_impl", "call_verify_read_tests", "call_verify_edit", "call_verify_test")


def arguments(workspace):
    """Fixed synthetic model decisions; only OpenCode executes these operations."""
    return (
        {"filePath": str(workspace / "text_utils.py")},
        {"filePath": str(workspace / "test_text_utils.py")},
        {"filePath": str(workspace / "text_utils.py"),
         "oldString": 'return len(text.split(" "))', "newString": "return len(text.split())"},
        {"command": FIXED_COMMAND, "workdir": str(workspace),
         "description": "Run the exact immutable word-count tests"},
    )


def model_reply(server, body):
    """Validate replay of actual native tool results before issuing the next call."""
    require(type(body) is dict and body.get("model") == server.model, "model_mismatch")
    require(body.get("stream") is True, "unexpected_nonstream_request")
    require(body.get("reasoning_effort") == "low" and "reasoningEffort" not in body,
            "reasoning_effort_mismatch")
    require(type(body.get("max_tokens")) is int and 0 < body["max_tokens"] <= server.output_tokens,
            "output_limit_mismatch")
    messages = body.get("messages")
    require(type(messages) is list and all(type(m) is dict for m in messages), "invalid_messages")
    offered = [t.get("function", {}).get("name") for t in body.get("tools", [])]
    require(not set(offered).intersection({"webfetch", "websearch", "codesearch", "task"}),
            "unexpected_network_or_subagent_tool")
    if not offered:
        server.records.append({"kind": "auxiliary", "authenticated": True,
                               "model": server.model, "reasoning_effort": "low"})
        return {"role": "assistant", "content": "Synthetic verifier fixture"}, "stop"
    require(set(CALL_NAMES).issubset(offered), "required_native_tool_not_offered")
    calls = [call for message in messages if message.get("role") == "assistant"
             for call in message.get("tool_calls", [])]
    results = [message for message in messages if message.get("role") == "tool"]
    stage = server.stage
    require(stage <= 4 and len(calls) == len(results) == stage, "tool_round_order")
    expected = arguments(server.workspace)
    for index, (call, result) in enumerate(zip(calls, results)):
        require(call.get("id") == result.get("tool_call_id") == CALL_IDS[index], "tool_identity_mismatch")
        function = call.get("function", {})
        require(function.get("name") == CALL_NAMES[index], "tool_name_mismatch")
        require(json.loads(function.get("arguments", "null")) == expected[index], "tool_arguments_changed")
    for index, result in enumerate(results):
        content = json.dumps(result.get("content", ""))
        require("Error:" not in content and "denied" not in content.lower(), "tool_result_failed")
        if index == 0:
            require('split(\\" \\")' in content, "implementation_read_not_replayed")
        elif index == 1:
            require("importlib.util" in content and "test_empty_string" in content,
                    "immutable_test_read_not_replayed")
        elif index == 2:
            actual = (server.workspace / "text_utils.py").read_bytes()
            require(actual == server.source.replace(b'split(" ")', b"split()"), "native_edit_not_applied")
        elif index == 3:
            require("Ran 3 tests" in content and "\\nOK" in content, "requested_tests_not_passing")
    if stage >= 2:
        require(hashlib.sha256((server.workspace / "test_text_utils.py").read_bytes()).hexdigest()
                == server.test_sha256, "immutable_tests_changed")
    server.records.append({"kind": "agent", "authenticated": True, "model": server.model,
                           "reasoning_effort": "low", "max_tokens": body["max_tokens"],
                           "actual_tool_results_replayed": stage})
    server.stage += 1
    if stage == 4:
        return {"role": "assistant", "content": "Fixed whitespace word counting; all three tests pass."}, "stop"
    return {"role": "assistant", "tool_calls": [{"index": 0, "id": CALL_IDS[stage],
            "type": "function", "function": {"name": CALL_NAMES[stage],
                                               "arguments": json.dumps(expected[stage])}}]}, "tool_calls"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def authenticate(self):
        require(hmac.compare_digest(self.headers.get("Authorization", "").encode(),
                                    b"Bearer " + self.server.key), "synthetic_auth_failed")

    def reject(self, error):
        self.server.failure = str(error) if isinstance(error, FixtureError) else "invalid_http_exchange"
        with contextlib.suppress(OSError):
            self.send_error(400, "Synthetic verifier fixture rejected request")

    def do_GET(self):
        try:
            with self.server.lock:
                self.authenticate()
                require(self.path == "/v1/models", "unexpected_get_path")
                self.server.model_gets += 1
                require(self.server.model_gets <= 2, "model_get_limit")
                payload = json.dumps({"object": "list", "data": [
                    {"id": self.server.model, "object": "model", "owned_by": "synthetic-fixture"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (FixtureError, OSError) as error:
            self.reject(error)

    def do_POST(self):
        try:
            with self.server.lock:
                self.authenticate()
                self.server.received += 1
                require(self.server.received <= MAX_REQUESTS, "request_limit")
                require(self.path == "/v1/chat/completions", "unexpected_post_path")
                length = int(self.headers.get("Content-Length", "0"))
                require(0 < length <= MAX_BODY, "request_body_limit")
                delta, finish = model_reply(self.server, json.loads(self.rfile.read(length)))
                envelope = {"id": "verifier-synthetic", "object": "chat.completion.chunk",
                            "created": 1, "model": self.server.model}
                chunks = [dict(envelope, choices=[{"index": 0, "delta": delta, "finish_reason": None}]),
                          dict(envelope, choices=[{"index": 0, "delta": {}, "finish_reason": finish}])]
                # Omit usage: the fixture never fabricates usage evidence.
                payload = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                           + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        except (FixtureError, ValueError, KeyError, TypeError, OSError) as error:
            self.reject(error)


def run_fixture(work_root):
    repo = CLIENT.parents[1]
    require(os.getuid() > 0, "ordinary_user_required")
    require(work_root != repo and repo not in work_root.parents
            and not any((parent / ".git").exists() for parent in work_root.parents),
            "work_root_must_be_outside_git")
    require(not work_root.exists() and not work_root.is_symlink(), "work_root_must_be_new")
    require(work_root.parent.is_dir(), "work_root_parent_missing")
    os.umask(0o077)
    work_root.mkdir(mode=0o700)
    private_dir(work_root)
    key = secrets.token_hex(32).encode("ascii")
    key_file = work_root / "disposable-key"
    write_new(key_file, key)
    prefix = work_root / "prefix"
    output = work_root / "verification"
    evidence = {"status": "IN_PROGRESS", "evidence_class": "actual_client_synthetic_http",
                "live_model_acceptance": False, "provider_usage": "NOT_REPORTED"}
    server = WireServer(("127.0.0.1", 0), Handler)
    server.lock, server.key, server.failure = threading.Lock(), key, None
    server.model, server.output_tokens = "glm-5.3", 2048
    server.workspace = output / "workspace"
    server.source = (CLIENT / "verifier_fixture" / "text_utils.py").read_bytes()
    server.test_sha256 = hashlib.sha256((CLIENT / "verifier_fixture" / "test_text_utils.py").read_bytes()).hexdigest()
    server.records, server.stage, server.received, server.model_gets = [], 0, 0, 0
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:" + str(server.server_port) + "/v1"
        env = isolated_env(prefix)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        bootstrap = [sys.executable, "-B", str(CLIENT / "bootstrap.py"), "--prefix", str(prefix),
                     "--base-url", base, "--model", server.model, "--context-tokens", "32768",
                     "--output-tokens", str(server.output_tokens), "--reasoning-effort", "low",
                     "--api-key-file", str(key_file)]
        child(bootstrap, work_root, env, 300, key)
        require(verify_install(prefix).get("reasoning_effort") == "low", "prefix_effort_mismatch")
        child(bootstrap, work_root, env, 60, key)  # Actual native version + idempotency.
        child([sys.executable, "-B", str(CLIENT / "verify.py"), "--prefix", str(prefix),
               "--output-dir", str(output), "--timeout-seconds", "60"], work_root, env, 90, key)
        require(server.failure is None, server.failure or "synthetic_server_failure")
        require(server.stage == 5 and server.model_gets == 2, "incomplete_actual_verification")
        report = json.loads((output / "report.json").read_bytes())
        require(report.get("status") == "PASS", "verifier_report_failed")
        expected_checks = {"file_reads", "implementation_edit", "exact_test_command", "passing_tool_result",
                           "final_response", "immutable_tests", "independent_final_rerun", "process_tree_reaped"}
        require(set(report.get("checks", {})) == expected_checks
                and all(value is True for value in report["checks"].values()), "verifier_checks_missing")
        require(report.get("tests_before_sha256") == report.get("tests_after_sha256") == server.test_sha256,
                "verifier_test_hash_mismatch")
        require(report.get("initial_test") == {"classification": "assertion_failure", "assertion_failures": 5,
                                               "import_errors": 0, "exit_code": 1}, "verifier_baseline_mismatch")
        raw_hash = hashlib.sha256((output / "raw-evidence.json").read_bytes()).hexdigest()
        require(report.get("raw_evidence_sha256") == raw_hash, "raw_evidence_hash_mismatch")
        require(report.get("client_versions", {}).get("opencode_version") == "1.18.31"
                and report["client_versions"].get("plugin_version") == "1.18.31", "client_pin_mismatch")
        require(not (output / "receipt.json").exists(), "unexpected_installer_receipt")
        # The key must not persist in native caches, logs, or artifacts. Scan
        # streams without printing matching filenames or content.
        for path in work_root.rglob("*"):
            if path == key_file or not path.is_file() or path.is_symlink():
                continue
            with path.open("rb") as stream:
                tail = b""
                while block := stream.read(1024 * 1024):
                    require(key not in tail + block, "credential_persisted_outside_key_file")
                    tail = block[-len(key):]
        evidence.update(status="PASS", credential_scan="PASS", client_versions=report["client_versions"],
                        verifier_report_sha256=hashlib.sha256((output / "report.json").read_bytes()).hexdigest(),
                        raw_evidence_sha256=raw_hash,
                        checks=report["checks"], authenticated_model_gets=server.model_gets,
                        requests=list(server.records), immutable_test_sha256=server.test_sha256)
        return evidence
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        key_file.unlink(missing_ok=True)
        if evidence["status"] != "PASS":
            evidence.update(status="FAIL", server_failure=server.failure,
                            requests=list(server.records), authenticated_model_gets=server.model_gets)
        write_new(work_root / "wire-evidence.json", json_bytes(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, help="New absolute private directory outside Git; parent must exist")
    args = parser.parse_args()
    try:
        require(not Path(args.work_root).is_symlink(), "work_root_must_not_be_symlink")
        print(json.dumps(run_fixture(absolute_path(args.work_root)), indent=2))
        return 0
    except Exception as error:
        print("FAIL: " + (str(error) if isinstance(error, FixtureError) else "fixture_error_details_withheld"),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
