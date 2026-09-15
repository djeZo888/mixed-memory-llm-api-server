#!/usr/bin/env python3
"""Prove pinned OpenCode requests against a synthetic loopback server, never an LLM.

Explicit opt-in: creates fresh private installations using the committed npm lock.
Only allowlisted evidence is emitted; raw requests, headers and CLI output are not.
"""

import argparse
import contextlib
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))
from client_common import (VERSION, absolute_path, isolated_env, json_bytes,
                           private_dir, verify_install, write_new)

MAX_REQUESTS = 8  # Per invocation, including OpenCode's own title requests.
MAX_BODY = 2 * 1024 * 1024
RUN_TIMEOUT = 60


class FixtureError(Exception):
    """Messages are fixed classifications, never untrusted response text."""


def require(condition, message):
    if not condition:
        raise FixtureError(message)


def child(argv, cwd, env, timeout, forbidden):
    """Bound the whole process group and keep all child output in memory."""
    require(all(forbidden not in arg.encode() for arg in argv), "credential_in_argv")
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = process.communicate(timeout=timeout)
        require(forbidden not in out and forbidden not in err, "credential_in_child_output")
        require(len(out) + len(err) <= 4 * MAX_BODY, "excessive_child_output")
        require(process.returncode == 0, "child_failed_output_withheld")
        return out
    except subprocess.TimeoutExpired:
        raise FixtureError("child_timeout") from None
    finally:
        # The launcher spawns OpenCode: kill the group even if its parent exited.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)
        for stream in (process.stdout, process.stderr):
            stream.close()
        # communicate() can complete while a descendant with closed stdio is
        # still running. Its lifetime must not depend on the launcher's exit.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        deadline = time.monotonic() + 3
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            require(time.monotonic() < deadline, "process_group_survived_cleanup")
            time.sleep(0.05)


class WireServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True

    def handle_error(self, request, client_address):
        self.failure = "http_handler_failed"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never print headers, URLs, request bodies, or parser errors.

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def do_GET(self):
        self.server.failure = "unexpected_get"
        self.send_error(405)

    def do_POST(self):
        server = self.server
        try:
            with server.lock:
                server.received += 1
                require(server.received <= MAX_REQUESTS, "request_limit")
                require(self.path == "/v1/chat/completions", "unexpected_path")
                length = int(self.headers.get("Content-Length", "0"))
                require(0 < length <= MAX_BODY, "body_limit")
                # Compare in memory; never retain the header or key in evidence.
                authenticated = hmac.compare_digest(
                    self.headers.get("Authorization", "").encode(), b"Bearer " + server.key)
                require(authenticated, "synthetic_auth_failed")
                body = json.loads(self.rfile.read(length))
                require(type(body) is dict, "invalid_body")
                require(body.get("model") == server.model, "model_mismatch")
                present = "reasoning_effort" in body
                require(present == (server.effort is not None), "effort_presence_mismatch")
                if present:
                    require(body["reasoning_effort"] == server.effort, "effort_value_mismatch")
                require("reasoningEffort" not in body, "camelcase_on_wire")
                # This exact OpenCode CLI path uses streamText. Never pretend that
                # replying with nonstream JSON tests a nonstream client request.
                require(body.get("stream") is True, "unexpected_nonstream_request")
                require(type(body.get("max_tokens")) is int and 0 < body["max_tokens"] <= 2048,
                        "invalid_output_limit")
                messages = body.get("messages", [])
                require(type(messages) is list, "invalid_messages")
                results = [m for m in messages if m.get("role") == "tool"]
                calls = [c for m in messages if m.get("role") == "assistant"
                         for c in m.get("tool_calls", [])]
                offered = [t.get("function", {}).get("name") for t in body.get("tools", [])]
                require(not set(offered).intersection({"webfetch", "websearch", "codesearch", "task"}),
                        "network_or_subagent_tool_offered")
                marker_seen = any(server.marker in json.dumps(m.get("content")) for m in results)
                continuation = bool(results)
                kind = "auxiliary" if not offered else server.mode
                if continuation:
                    require(server.mode == "tool" and len(results) == 1 and len(calls) == 1,
                            "unexpected_continuation")
                    require(results[0].get("tool_call_id") == "call_a2o_read", "tool_result_id")
                    require(calls[0].get("id") == "call_a2o_read", "assistant_call_id")
                    require(calls[0].get("function", {}).get("name") == "read", "assistant_call_name")
                    require(marker_seen, "fixture_read_not_replayed")
                    kind = "continuation"
                record = {"kind": kind, "model": body["model"], "stream": body["stream"],
                          "reasoning_effort_present": present,
                          "max_tokens": body.get("max_tokens"), "authenticated": authenticated,
                          "tool_schema_count": len(offered), "tool_result_count": len(results),
                          "assistant_call_count": len(calls), "fixture_marker_seen": marker_seen}
                if present:
                    record["reasoning_effort"] = body["reasoning_effort"]
                server.records.append(record)
                # All requests, including title generation, are checked above.
                if server.mode == "tool" and offered and not continuation:
                    require("read" in offered and server.tool_rounds == 0, "unexpected_tool_round")
                    server.tool_rounds += 1
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_a2o_read",
                             "type": "function", "function": {"name": "read", "arguments": json.dumps(
                                 {"filePath": str(server.workspace / "fixture.txt")})}}]}
                    finish = "tool_calls"
                else:
                    if continuation:
                        require(server.tool_rounds == 1, "continuation_round_limit")
                        server.tool_rounds += 1
                    delta = {"role": "assistant", "content": "A2O_SYNTHETIC_DONE"}
                    finish = "stop"
                envelope = {"id": "a2o-synthetic", "object": "chat.completion.chunk",
                            "created": 1, "model": server.model}
                chunks = [dict(envelope, choices=[{"index": 0, "delta": delta, "finish_reason": None}]),
                          dict(envelope, choices=[{"index": 0, "delta": {}, "finish_reason": finish}]),
                          dict(envelope, choices=[], usage={"prompt_tokens": 16, "completion_tokens": 8,
                                                            "total_tokens": 24})]
                payload = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
                           + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        except (FixtureError, ValueError, KeyError, TypeError, OSError) as error:
            server.failure = str(error) if isinstance(error, FixtureError) else "invalid_http_exchange"
            with contextlib.suppress(OSError):
                self.send_error(400, "Synthetic fixture rejected request")


def run_fixture(work_root):
    """Fresh private root only. No external endpoint or credential input exists."""
    repo = CLIENT.parents[1]
    require(work_root != repo and repo not in work_root.parents, "work_root_must_be_outside_git")
    require(not any((parent / ".git").exists() for parent in work_root.parents),
            "work_root_must_be_outside_git")
    require(not work_root.exists() and not work_root.is_symlink(), "work_root_must_be_new")
    require(work_root.parent.is_dir(), "work_root_parent_missing")
    os.umask(0o077)
    work_root.mkdir(mode=0o700)
    private_dir(work_root)
    key = secrets.token_hex(32).encode("ascii")
    key_file = work_root / "disposable-key"
    write_new(key_file, key)
    evidence = {"status": "IN_PROGRESS", "client_version": VERSION,
                "claim": "actual_client_to_synthetic_server_only", "live_llm_acceptance": False,
                "nonstream": "NOT_SUPPORTED_BY_PINNED_CLI_AGENT_PATH", "cases": []}
    server = WireServer(("127.0.0.1", 0), Handler)
    server.lock = threading.Lock()
    server.key = key
    server.failure = None
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:" + str(server.server_port) + "/v1"
        for label, effort, model in (("default", None, "glm-5.3"),
                                      ("low-glm", "low", "glm-5.3"),
                                      ("low-generic", "low", "vendor/model:Q4_K_M")):
            prefix = work_root / label
            args = [sys.executable, str(CLIENT / "bootstrap.py"), "--prefix", str(prefix),
                    "--base-url", base, "--model", model, "--context-tokens", "32768",
                    "--output-tokens", "2048", "--api-key-file", str(key_file)]
            if effort is not None:
                args += ["--reasoning-effort", effort]
            env = isolated_env(prefix)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            child(args, work_root, env, 240, key)
            settings = verify_install(prefix)
            require(settings.get("reasoning_effort") == effort, "installed_manifest_mismatch")
            # The idempotent path invokes and checks the real native --version.
            child(args, work_root, env, RUN_TIMEOUT, key)
            for mode in ("ordinary", "tool"):
                workspace = work_root / (label + "-" + mode + " workspace & literal")
                workspace.mkdir(mode=0o700)
                marker = "fixture-content-" + secrets.token_hex(16)
                fixture = workspace / "fixture.txt"
                write_new(fixture, (marker + "\n").encode())
                fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
                prompt = work_root / (label + "-" + mode + "-prompt.txt")
                write_new(prompt, b"Read fixture.txt once, then reply with a short completion.\n"
                          if mode == "tool" else b"Reply with a short greeting without using tools.\n")
                with server.lock:
                    server.model, server.effort, server.mode = model, effort, mode
                    server.workspace, server.marker = workspace, marker
                    server.records, server.tool_rounds, server.failure, server.received = [], 0, None, 0
                launcher = prefix / "bin" / "opencode-client"
                child([sys.executable, str(launcher), "--workspace", str(workspace), "check"],
                      work_root, env, RUN_TIMEOUT, key)
                output = child([sys.executable, str(launcher), "--workspace", str(workspace),
                                "--prompt-file", str(prompt), "run"], work_root, env, RUN_TIMEOUT, key)
                require(server.failure is None, server.failure or "server_failure")
                events = [json.loads(line) for line in output.splitlines() if line.strip()]
                require(not any(e.get("type") == "error" for e in events), "opencode_error_event")
                require(any(e.get("type") == "text" and e.get("part", {}).get("text") == "A2O_SYNTHETIC_DONE"
                            for e in events), "missing_final_text_event")
                tool_events = [e["part"] for e in events if e.get("type") == "tool_use"]
                require(len(tool_events) == (1 if mode == "tool" else 0), "tool_event_count")
                if mode == "tool":
                    part = tool_events[0]
                    require(part.get("tool") == "read" and part.get("state", {}).get("status") == "completed",
                            "read_tool_not_completed")
                    require(marker in part["state"].get("output", ""), "read_tool_output_missing_marker")
                    require(server.tool_rounds == 2, "two_round_loop_missing")
                    require(sum(r["kind"] == "tool" for r in server.records) == 1, "initial_tool_request_count")
                    require(sum(r["kind"] == "continuation" for r in server.records) == 1, "continuation_count")
                else:
                    require(any(r["kind"] == "ordinary" for r in server.records), "ordinary_request_missing")
                require(hashlib.sha256(fixture.read_bytes()).hexdigest() == fixture_hash, "fixture_modified")
                require(len(list(workspace.iterdir())) == 1, "workspace_mutated")
                evidence["cases"].append({"selection": label, "mode": mode, "status": "PASS",
                                          "completed_read_events": len(tool_events),
                                          "tool_rounds": server.tool_rounds, "requests": list(server.records)})
        # Do not retain a key value in OpenCode/npm state, config or logs. Scan
        # bytes without displaying any file contents or matching lines.
        for path in work_root.rglob("*"):
            if path == key_file or not path.is_file() or path.is_symlink():
                continue
            # Stream the scan so native executables do not consume large memory.
            with path.open("rb") as stream:
                tail = b""
                while block := stream.read(1024 * 1024):
                    require(key not in tail + block, "credential_persisted_outside_key_file")
                    tail = block[-len(key):]
        evidence["credential_scan"] = "PASS"
        evidence["status"] = "PASS"
        return evidence
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        key_file.unlink(missing_ok=True)
        # No secret or raw transcript is in this fixed allowlisted report.
        if evidence["status"] != "PASS":
            evidence["status"] = "FAIL"
        write_new(work_root / "wire-evidence.json", json_bytes(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, help="New absolute private directory outside Git; parent must exist")
    args = parser.parse_args()
    try:
        evidence = run_fixture(absolute_path(args.work_root))
        print(json.dumps(evidence, indent=2))
        return 0
    except Exception as error:
        print("FAIL: " + (str(error) if isinstance(error, FixtureError) else "fixture_error_details_withheld"),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
