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
from lifecycle.manager import Manager

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
            "health_status": 200, "models_status": 200, "readiness_status": 200,
            "readiness_payload": {"schema_version": 1, "model_alias": MODEL, "ready": True,
                                  "state": "up", "admitting": None},
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
                route = {"/health": "health", "/v1/models": "models", "/v1/readiness": "readiness",
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
                    elif auth == "missing" and route in ("models", "readiness"):
                        status = policy["missing_status"]
                    elif auth == "wrong" and route in ("models", "readiness"):
                        status = policy["wrong_status"]
                    elif route == "model_info" and auth != "correct":
                        status = 401
                    elif route == "readiness" and policy.get("readiness_from_warmup"):
                        status = (200 if fixture.tokenizer_manager.server_status is FixtureServerStatus.Up else 503)
                    else:
                        status = policy[route + "_status"]
                    payload = policy.get("raw_models_payload")
                    if payload is None:
                        payload = json.dumps(policy["models_payload"]).encode()
                    body = payload if route == "models" and status == 200 else b""
                    if route == "readiness" and status == 200:
                        value = policy['readiness_payload']
                        if policy.get('readiness_from_warmup'):
                            value = dict(value, ready=fixture.tokenizer_manager.server_status is FixtureServerStatus.Up,
                                         state=fixture.tokenizer_manager.server_status.value)
                        body = policy.get('raw_readiness_payload', json.dumps(value).encode())
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

    def test_passive_readiness_requires_correct_missing_and_wrong_key_contracts(self):
        self.assertEqual(self.probe(), "ready")
        self.assertEqual(self.requests, [
            ("readiness", "missing"), ("readiness", "wrong"), ("readiness", "correct"),
        ])
        self.assertTrue(self.keyfile.read_bytes() == self.key.encode("ascii"),
                        "protected fixture key was modified")
        self.assertEqual(self.keyfile.stat().st_mode & 0o777, 0o600)

    def test_real_manager_qwen_dispatch_reaches_passive_route_without_generic_probe(self):
        # Constructor recovery mode avoids loading any model/storage while the
        # actual owner dispatch selects and executes its real SGLang HTTP probe.
        manager = Manager(ROOT / 'configs', {'schema_version': 1, 'id': 'passive-fixture'},
                          recovery_only=True)
        deployment = {'id': 'passive-fixture-qwen', '_runtime': {'backend': 'sglang_qwen38'},
                      'endpoint': {'host': '127.0.0.1', 'port': self.server.server_port,
                                   'api_prefix': '/v1', 'served_model': MODEL},
                      'auth': {'key_file': self.keyfile}}
        with patch.object(manager, 'probe', side_effect=AssertionError('generic health probe selected')):
            self.assertEqual(manager.probe_deployment(deployment, 2), 'ready')
        self.assertEqual(self.requests, [('readiness', 'missing'), ('readiness', 'wrong'),
                                        ('readiness', 'correct')])
        self.assertEqual(self.generation_requests, [])

    def test_models_available_while_passive_readiness_503_is_never_ready(self):
        self.policy["readiness_status"] = 503
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
        self.assertIn(("readiness", "correct"), self.requests)
        self.assertNotIn(("models", "correct"), self.requests)

    def test_actual_authenticated_warmup_transitions_passive_starting_to_ready(self):
        self.policy["readiness_from_warmup"] = True
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
            ("readiness", "missing"), ("readiness", "wrong"), ("readiness", "correct"),
        ])

    def test_failed_actual_warmup_cannot_transition_passive_readiness_to_up(self):
        self.policy["readiness_from_warmup"] = True
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
                self.assertNotIn(("readiness", "correct"), self.requests)

    def test_both_401_and_403_are_valid_denials_for_missing_and_wrong_keys(self):
        for denial in (401, 403):
            self.policy.update(missing_status=denial, wrong_status=denial)
            with self.subTest(status=denial):
                self.assertEqual(self.probe(), "ready")

    def test_correct_key_denied_by_passive_readiness_is_auth_error(self):
        for field in ("readiness_status",):
            for denial in (401, 403):
                self.policy.update(readiness_status=200)
                self.policy[field] = denial
                with self.subTest(field=field, status=denial):
                    self.assertEqual(self.probe(), "auth_error")

    def test_exact_alias_is_required(self):
        for alias in ('another-model', MODEL + '-other', None, [MODEL]):
            self.policy['readiness_payload']['model_alias'] = alias
            with self.subTest(alias=alias):
                self.assertEqual(self.probe(), 'wrong_model')

    def test_malformed_or_invalid_readiness_payload_is_not_ready(self):
        payloads = [b'not-json', b'', b'null', b'[]', b'{}', b'{"ready":null}',
                    b'x' * 16385, b'{"schema_version":1,"schema_version":1}',
                    b'{"ready":NaN}']
        for index, payload in enumerate(payloads):
            self.policy['raw_readiness_payload'] = payload
            with self.subTest(case=index):
                self.assertEqual(self.probe(), 'not_ready')

    def test_otherwise_ready_duplicate_json_fields_are_rejected(self):
        valid = json.dumps(self.policy['readiness_payload']).encode()
        self.policy['raw_readiness_payload'] = b'{"schema_version":1,' + valid[1:]
        self.assertEqual(self.probe(), 'not_ready')
        self.assertTrue(all(route == 'readiness' for route, _ in self.requests))

    def test_valid_json_larger_than_body_limit_is_rejected(self):
        valid = json.dumps(self.policy['readiness_payload']).encode()
        self.policy['raw_readiness_payload'] = b' ' * 16385 + valid
        self.assertEqual(self.probe(), 'not_ready')
        self.assertEqual(self.generation_requests, [])

    def test_untrusted_endpoint_is_rejected_before_key_read_or_request(self):
        port = self.server.server_port
        endpoints = [f'https://127.0.0.1:{port}/v1', f'http://localhost:{port}/v1',
                     f'http://0.0.0.0:{port}/v1', f'http://[::1]:{port}/v1',
                     f'http://user@127.0.0.1:{port}/v1', f'http://127.0.0.1:{port}/health',
                     f'http://127.0.0.1:{port}/v1?generate=true', f'http://127.0.0.1:{port}/v1#fragment']
        with patch.object(runtime_io, '_read_key', side_effect=AssertionError('unexpected key read')):
            for endpoint in endpoints:
                with self.subTest(endpoint=endpoint):
                    self.assertEqual(runtime_io.probe_sglang(endpoint, MODEL, self.keyfile), 'not_ready')
        self.assertEqual(self.requests, [])

    def test_only_strict_schema1_boolean_up_and_null_admitting_are_ready(self):
        baseline = copy.deepcopy(self.policy['readiness_payload'])
        for updates in ({'schema_version': True}, {'schema_version': 2}, {'ready': 1},
                        {'ready': False}, {'state': 'starting'}, {'state': 'Up'},
                        {'state': 'unknown'}, {'admitting': False}, {'extra': 1}):
            self.policy['readiness_payload'] = dict(baseline, **updates)
            with self.subTest(updates=updates):
                self.assertEqual(self.probe(), 'not_ready')
        self.assertEqual(self.generation_requests, [])
        self.assertTrue(all(route == 'readiness' for route, _ in self.requests))

    def test_old_runtime_without_route_stays_not_ready_without_health_fallback(self):
        self.policy['readiness_status'] = 404
        self.assertEqual(self.probe(), 'not_ready')
        self.assertTrue(all(route == 'readiness' for route, _ in self.requests))
        self.assertEqual(self.generation_requests, [])

    def test_redirects_and_server_errors_on_each_probe_stage_are_not_ready(self):
        original = copy.deepcopy(self.policy)
        for field in ("missing_status", "wrong_status", "readiness_status"):
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
        self.policy.update(delay_at=("readiness", "wrong"), delay_seconds=0.5)
        begin = time.monotonic()
        self.assertEqual(self.probe(timeout=0.12), "not_ready")
        self.assertLess(time.monotonic() - begin, 0.4)

    def test_trickled_headers_and_authenticated_body_cannot_extend_deadline(self):
        for field, stage in (("trickle_headers_at", ("readiness", "missing")),
                             ("trickle_body_at", ("readiness", "correct"))):
            self.policy.pop("trickle_headers_at", None)
            self.policy.pop("trickle_body_at", None)
            self.policy[field] = stage
            begin = time.monotonic()
            with self.subTest(kind=field):
                self.assertEqual(self.probe(timeout=0.12), "not_ready")
                self.assertLess(time.monotonic() - begin, 0.4)

    def test_one_timeout_budget_covers_all_three_requests(self):
        self.policy["delay_all"] = 0.12
        begin = time.monotonic()
        self.assertEqual(self.probe(timeout=0.3), "not_ready")
        self.assertLess(time.monotonic() - begin, 0.43)

    def test_malformed_key_or_response_never_prints_fixture_sentinel(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.policy["raw_readiness_payload"] = self.key.encode("ascii")
            self.assertEqual(self.probe(), "not_ready")
            self.keyfile.write_bytes(self.key.encode("ascii") + b"\n")
            self.assertEqual(self.probe(), "auth_error")
        self.assertTrue(self.key not in stdout.getvalue() + stderr.getvalue(),
                        "generic fixture credential disclosure")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
