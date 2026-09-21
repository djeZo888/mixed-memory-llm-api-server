"""Functional loopback SGLang readiness probes against a synthetic HTTP server.

No SGLang runtime, Docker daemon, real credential, or model is used. Generated
fixture credentials stay in a private temporary file and HTTP request headers;
the fixture records authentication classifications, never header values.
"""
from __future__ import annotations

import contextlib
import copy
from enum import Enum
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lifecycle import runtime_io
from lifecycle import sglang_file_auth as launcher

MODEL = "qwen3-coder-next"


class FixtureServerStatus(Enum):
    Starting = "starting"
    Up = "up"


class QuietHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Deadline tests deliberately disconnect; never dump request internals.
        pass


class SGLangReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = secrets.token_hex(32)
        self.keyfile = Path(self.tmp.name) / "fixture.key"
        self.keyfile.write_bytes(self.key.encode("ascii"))
        self.keyfile.chmod(0o600)
        self.requests = []
        self.generation_requests = []
        self.tokenizer_manager = SimpleNamespace(server_status=FixtureServerStatus.Starting)
        self.http_server = SimpleNamespace(
            ServerStatus=FixtureServerStatus,
            _global_state=SimpleNamespace(tokenizer_manager=self.tokenizer_manager),
        )
        self.policy = {
            "missing_status": 401, "wrong_status": 403,
            "health_status": 200, "models_status": 200,
            "models_payload": {"object": "list", "data": [{"id": MODEL}]},
            "model_info_status": 200, "model_info_payload": {"is_generation": True},
            "generate_status": 200,
            "generate_payload": {"text": "fixture", "meta_info": {"completion_tokens": 1}},
        }
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                policy = copy.deepcopy(fixture.policy)
                header = self.headers.get("Authorization")
                auth = ("missing" if header is None else "correct"
                        if header == "Bearer " + fixture.key else "wrong")
                route = {"/health": "health", "/v1/models": "models",
                         "/model_info": "model_info"}.get(self.path, "other")
                fixture.requests.append((route, auth))
                delay = policy.get("delay_all", 0)
                if policy.get("delay_at") == (route, auth):
                    delay += policy.get("delay_seconds", 0)
                if delay:
                    time.sleep(delay)
                try:
                    if policy.get("trickle_headers_at") == (route, auth):
                        for byte in b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n":
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.02)
                        return
                    if route == "other":
                        status = 404
                    elif auth == "missing" and route == "models":
                        status = policy["missing_status"]
                    elif auth == "wrong" and route == "models":
                        status = policy["wrong_status"]
                    elif route == "model_info" and auth != "correct":
                        status = 401
                    elif route == "health" and policy.get("health_from_warmup"):
                        status = (200 if fixture.tokenizer_manager.server_status is FixtureServerStatus.Up else 503)
                    else:
                        status = policy[route + "_status"]
                    payload = policy.get("raw_models_payload")
                    if payload is None:
                        payload = json.dumps(policy["models_payload"]).encode()
                    body = payload if route == "models" and status == 200 else b""
                    if route == "model_info" and status == 200:
                        body = json.dumps(policy["model_info_payload"]).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    if 300 <= status < 400:
                        self.send_header("Location", "/must-not-follow")
                    self.end_headers()
                    if policy.get("trickle_body_at") == (route, auth):
                        for byte in body:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.02)
                    else:
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    # Expected when the total client deadline shuts its socket.
                    return

            def do_POST(self):
                header = self.headers.get("Authorization")
                auth = ("missing" if header is None else "correct"
                        if header == "Bearer " + fixture.key else "wrong")
                route = "generate" if self.path == "/generate" else "other"
                fixture.requests.append((route, auth))
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 1024:
                        self.send_error(400)
                        return
                    payload = json.loads(self.rfile.read(size))
                    fixture.generation_requests.append(payload)
                    status = (404 if route == "other" else 401 if auth != "correct"
                              else fixture.policy["generate_status"])
                    body = json.dumps(fixture.policy["generate_payload"]).encode() if status == 200 else b""
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                except (OSError, ValueError):
                    return

        with patch.object(socket, "getfqdn", return_value="localhost"):
            self.server = QuietHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/v1"

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def probe(self, **kwargs):
        return runtime_io.probe_sglang(self.endpoint, MODEL, self.keyfile, **kwargs)

    def test_readiness_requires_health_and_correct_missing_and_wrong_key_contracts(self):
        self.assertEqual(self.probe(), "ready")
        self.assertEqual(self.requests, [
            ("models", "missing"), ("models", "wrong"),
            ("health", "correct"), ("models", "correct"),
        ])
        self.assertTrue(self.keyfile.read_bytes() == self.key.encode("ascii"),
                        "protected fixture key was modified")
        self.assertEqual(self.keyfile.stat().st_mode & 0o777, 0o600)

    def test_models_available_while_health_503_is_never_ready(self):
        self.policy["health_status"] = 503
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
        try:
            connection.request("GET", "/v1/models", headers={"Authorization": "Bearer " + self.key})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["data"][0]["id"], MODEL)
        finally:
            connection.close()
        self.requests.clear()
        self.assertEqual(self.probe(), "not_ready")
        self.assertIn(("health", "correct"), self.requests)
        self.assertNotIn(("models", "correct"), self.requests)

    def test_actual_authenticated_warmup_transitions_starting_health_to_ready(self):
        self.policy["health_from_warmup"] = True
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
        try:
            connection.request("GET", "/v1/models", headers={"Authorization": "Bearer " + self.key})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["data"][0]["id"], MODEL)
        finally:
            connection.close()
        self.assertEqual(self.probe(), "not_ready")
        self.assertIs(self.tokenizer_manager.server_status, FixtureServerStatus.Starting)
        self.requests.clear()
        events = []
        args = SimpleNamespace(port=self.server.server_port, api_key=None, admin_api_key=None)
        warmup = launcher.make_warmup(
            self.http_server, launcher.read_key(self.keyfile), lambda: events.append("abort"),
            lambda: events.append("ready"), time.monotonic() + 2, timeout=1)
        self.assertTrue(warmup(args))
        self.assertIs(self.tokenizer_manager.server_status, FixtureServerStatus.Up)
        self.assertEqual(events, ["ready"])
        self.assertEqual(self.requests, [("model_info", "correct"), ("generate", "correct")])
        self.assertTrue(self.key not in repr(self.generation_requests), "generic fixture credential disclosure")
        self.assertEqual(self.generation_requests, [{
            "text": "Hello", "sampling_params": {"temperature": 0, "max_new_tokens": 1}, "stream": False,
        }])
        self.assertIsNone(args.api_key)
        self.assertIsNone(args.admin_api_key)
        self.requests.clear()
        self.assertEqual(self.probe(), "ready")
        self.assertEqual(self.requests, [
            ("models", "missing"), ("models", "wrong"),
            ("health", "correct"), ("models", "correct"),
        ])

    def test_failed_actual_warmup_cannot_transition_health_or_readiness_to_up(self):
        self.policy["health_from_warmup"] = True
        for mode in ("wrong_key", "generation_failure", "empty_generation", "model_timeout"):
            self.tokenizer_manager.server_status = FixtureServerStatus.Starting
            self.policy.update(model_info_status=200, generate_status=200,
                               generate_payload={"text": "fixture", "meta_info": {"completion_tokens": 1}})
            held_key = launcher.read_key(self.keyfile)
            if mode == "wrong_key":
                held_key = held_key + "x"
            elif mode == "generation_failure":
                self.policy["generate_status"] = 500
            elif mode == "empty_generation":
                self.policy["generate_payload"]["meta_info"]["completion_tokens"] = 0
            else:
                self.policy["model_info_status"] = 503
            events = []
            warmup = launcher.make_warmup(
                self.http_server, held_key, lambda: events.append("abort"), lambda: events.append("ready"),
                time.monotonic() + 1, timeout=0.05)
            with self.subTest(mode=mode), self.assertLogs(launcher.LOGGER, level="ERROR") as captured:
                self.assertFalse(warmup(SimpleNamespace(port=self.server.server_port)))
            self.assertTrue(self.key not in repr(captured.output), "generic fixture credential disclosure")
            self.assertEqual(events, ["abort"])
            self.assertIs(self.tokenizer_manager.server_status, FixtureServerStatus.Starting)
            self.assertEqual(self.probe(), "not_ready")

    def test_authentication_cannot_be_disabled_or_key_omitted(self):
        self.assertEqual(self.probe(require_auth=False), "auth_error")
        self.assertEqual(runtime_io.probe_sglang(self.endpoint, MODEL, None), "auth_error")
        self.keyfile.chmod(0o644)
        self.assertEqual(self.probe(), "auth_error")
        self.assertEqual(self.requests, [])

    def test_retained_generic_probe_keeps_its_existing_three_request_contract(self):
        self.assertEqual(runtime_io.probe(self.endpoint, MODEL, self.keyfile), "ready")
        self.assertEqual(self.requests, [
            ("models", "missing"), ("health", "correct"), ("models", "correct"),
        ])

    def test_missing_or_wrong_key_200_fails_authentication_gate(self):
        for field in ("missing_status", "wrong_status"):
            self.policy.update(missing_status=401, wrong_status=403)
            self.policy[field] = 200
            self.requests.clear()
            with self.subTest(field=field):
                self.assertEqual(self.probe(), "auth_error")
                self.assertNotIn(("health", "correct"), self.requests)

    def test_both_401_and_403_are_valid_denials_for_missing_and_wrong_keys(self):
        for denial in (401, 403):
            self.policy.update(missing_status=denial, wrong_status=denial)
            with self.subTest(status=denial):
                self.assertEqual(self.probe(), "ready")

    def test_correct_key_denied_by_health_or_models_is_auth_error(self):
        for field in ("health_status", "models_status"):
            for denial in (401, 403):
                self.policy.update(health_status=200, models_status=200)
                self.policy[field] = denial
                with self.subTest(field=field, status=denial):
                    self.assertEqual(self.probe(), "auth_error")

    def test_exact_single_model_is_required(self):
        payloads = [
            {"data": [{"id": "another-model"}]},
            {"data": [{"id": MODEL}, {"id": "another-model"}]},
            {"data": []},
        ]
        for index, payload in enumerate(payloads):
            self.policy["models_payload"] = payload
            with self.subTest(case=index):
                self.assertEqual(self.probe(), "wrong_model")

    def test_malformed_or_invalid_models_payload_is_not_ready(self):
        payloads = [b"not-json", b"", b"null", b"[]", b"{}", b'{"data":null}',
                    b'{"data":{}}', b"x" * 1048577]
        for index, payload in enumerate(payloads):
            self.policy["raw_models_payload"] = payload
            with self.subTest(case=index):
                self.assertEqual(self.probe(), "not_ready")

    def test_redirects_and_server_errors_on_each_probe_stage_are_not_ready(self):
        original = copy.deepcopy(self.policy)
        for field in ("missing_status", "wrong_status", "health_status", "models_status"):
            for status in (302, 500, 503):
                self.policy = copy.deepcopy(original)
                self.policy[field] = status
                self.requests.clear()
                with self.subTest(field=field, status=status):
                    self.assertEqual(self.probe(), "not_ready")
                    self.assertTrue(all(route != "other" for route, _ in self.requests))

    def test_probe_bypasses_environment_proxies(self):
        with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1",
                                     "HTTP_PROXY": "http://127.0.0.1:1",
                                     "ALL_PROXY": "http://127.0.0.1:1"}):
            self.assertEqual(self.probe(), "ready")

    def test_slow_headers_hit_total_timeout(self):
        self.policy.update(delay_at=("models", "wrong"), delay_seconds=0.5)
        begin = time.monotonic()
        self.assertEqual(self.probe(timeout=0.12), "not_ready")
        self.assertLess(time.monotonic() - begin, 0.4)

    def test_trickled_headers_and_authenticated_body_cannot_extend_deadline(self):
        for field, stage in (("trickle_headers_at", ("models", "missing")),
                             ("trickle_body_at", ("models", "correct"))):
            self.policy.pop("trickle_headers_at", None)
            self.policy.pop("trickle_body_at", None)
            self.policy[field] = stage
            begin = time.monotonic()
            with self.subTest(kind=field):
                self.assertEqual(self.probe(timeout=0.12), "not_ready")
                self.assertLess(time.monotonic() - begin, 0.4)

    def test_one_timeout_budget_covers_all_four_requests(self):
        self.policy["delay_all"] = 0.12
        begin = time.monotonic()
        self.assertEqual(self.probe(timeout=0.3), "not_ready")
        self.assertLess(time.monotonic() - begin, 0.43)

    def test_malformed_key_or_response_never_prints_fixture_sentinel(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.policy["raw_models_payload"] = self.key.encode("ascii")
            self.assertEqual(self.probe(), "not_ready")
            self.keyfile.write_bytes(self.key.encode("ascii") + b"\n")
            self.assertEqual(self.probe(), "auth_error")
        self.assertTrue(self.key not in stdout.getvalue() + stderr.getvalue(),
                        "generic fixture credential disclosure")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
