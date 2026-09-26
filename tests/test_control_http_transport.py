"""Actual loopback HTTP transport tests; no host services or live inference."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from control import http as transport  # noqa: E402


class FixtureApplication:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.response = (200, {"ok": True})
        self.entered = threading.Event()
        self.release = threading.Event()

    def handle(self, method, path, headers, body):
        self.calls.append((method, path, headers, body))
        if self.failure:
            raise RuntimeError(self.failure)
        if path == "/blocked":
            self.entered.set()
            self.release.wait(2)
        return self.response


class RunningServer:
    def __init__(self, app=None, deadline=transport.REQUEST_DEADLINE_SECONDS):
        self.app = app or FixtureApplication()
        self.key = secrets.token_urlsafe(36).encode("ascii")
        with patch.object(transport, "REQUEST_DEADLINE_SECONDS", deadline):
            self.server = transport.make_server(self.app, self.key, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.address = self.server.server_address

    def close(self):
        self.app.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)

    def request(self, method="GET", path="/control/v1/status", body=None, headers=None, auth=True):
        request_headers = dict(headers or {})
        if auth:
            request_headers["Authorization"] = "Bearer " + self.key.decode("ascii")
        if method == "POST":
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(*self.address, timeout=2)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def raw(self, data):
        with socket.create_connection(self.address, timeout=2) as connection:
            connection.sendall(data)
            result = bytearray()
            while True:
                try:
                    chunk = connection.recv(65536)
                except ConnectionResetError:
                    break
                if not chunk:
                    break
                result.extend(chunk)
            return bytes(result)

    def prefix(self, method="GET", path="/control/v1/status"):
        return (
            f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer "
        ).encode("ascii") + self.key + b"\r\n"


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.http = RunningServer()
        self.addCleanup(self.http.close)

    def assert_raw_status(self, request, status):
        result = self.http.raw(request)
        self.assertTrue(result.startswith(f"HTTP/1.1 {status} ".encode()), result[:100])
        return result

    def test_loopback_only_and_key_validation(self):
        for host in ("0.0.0.0", "192.0.2.1", "::1", "localhost", "127.0.0.1.example.invalid"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                transport.make_server(self.http.app, self.http.key, host=host, port=0)
        for key in (b"", b"x" * 31, b"x" * 257, b"x" * 31 + b"\n", "x" * 40):
            with self.subTest(length=len(key)), self.assertRaises(ValueError):
                transport.make_server(self.http.app, key, port=0)
        self.assertEqual(self.http.address[0], "127.0.0.1")
        self.assertEqual(self.http.server.request_deadline, 130)

    def test_all_routes_authenticate_before_application(self):
        for method, path in (
            ("GET", "/control/v1/catalog"), ("GET", "/control/v1/status"),
            ("GET", "/control/v1/readiness"),
            ("GET", "/control/v1/operations/opaque"), ("GET", "/unknown"),
            ("POST", "/control/v1/switch"), ("POST", "/control/v1/stop"),
        ):
            with self.subTest(method=method, path=path):
                status, headers, body = self.http.request(method, path, body=b"{}" if method == "POST" else None, auth=False)
                self.assertEqual(status, 401)
                self.assertEqual(json.loads(body), {"error": {"code": "unauthorized"}})
                self.assertIn("WWW-Authenticate", headers)
        self.assertEqual(self.http.app.calls, [])

    def test_wrong_auth_is_constant_response(self):
        for authorization in ("Bearer wrong", "Basic wrong", "", "Bearer", "Bearer  wrong"):
            with self.subTest(authorization=authorization):
                status, _, body = self.http.request(headers={"Authorization": authorization}, auth=False)
                self.assertEqual(status, 401)
                self.assertNotIn(authorization.encode() if authorization else b"wrong", body)
        self.assertEqual(self.http.app.calls, [])

    def test_authenticated_requests_have_safe_headers_only(self):
        body = b'{"expected_generation":0}'
        status, headers, result = self.http.request(
            "POST", "/control/v1/stop", body,
            {"Idempotency-Key": "opaque-request", "X-Private": "private", "Cookie": "private"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(result), {"ok": True})
        self.assertEqual(self.http.app.calls, [("POST", "/control/v1/stop", {
            "idempotency-key": "opaque-request", "content-type": "application/json",
        }, body)])
        self.assertEqual(headers["Connection"], "close")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Server", headers)

    def test_unsupported_methods_authenticate_first(self):
        for method in ("OPTIONS", "HEAD", "PUT", "PATCH", "DELETE", "TRACE", "CONNECT"):
            with self.subTest(method=method):
                self.assert_raw_status(f"{method} /unknown HTTP/1.1\r\nHost: localhost\r\n\r\n".encode(), 401)
                response = self.assert_raw_status(self.http.prefix(method) + b"\r\n", 405)
                self.assertIn(b"Allow: GET, POST", response)
        self.assertEqual(self.http.app.calls, [])

    def test_browser_origins_are_rejected_without_cors(self):
        for headers in ({"Origin": "http://localhost"}, {"Origin": "null"}, {"Sec-Fetch-Site": "same-origin"}):
            with self.subTest(headers=headers):
                status, response_headers, _ = self.http.request(headers=headers)
                self.assertEqual(status, 403)
                self.assertFalse(any(name.lower().startswith("access-control-") for name in response_headers))
        self.assertEqual(self.http.app.calls, [])

    def test_websocket_and_chunking_are_rejected(self):
        for header in (b"Upgrade: websocket\r\n", b"Connection: upgrade\r\n", b"Connection: keep-alive, Upgrade\r\n", b"Sec-WebSocket-Key: unused\r\n", b"Transfer-Encoding: chunked\r\n"):
            with self.subTest(header=header):
                self.assert_raw_status(self.http.prefix() + header + b"\r\n", 400)
        self.assertEqual(self.http.app.calls, [])

    def test_expect_continue_is_not_supported(self):
        self.assert_raw_status(self.http.prefix("POST") + b"Expect: 100-continue\r\n\r\n", 417)
        self.assertEqual(self.http.app.calls, [])

    def test_request_line_limit(self):
        self.assert_raw_status(self.http.prefix(path="/" + "x" * transport.MAX_REQUEST_LINE) + b"\r\n", 414)
        self.assertEqual(self.http.app.calls, [])

    def test_aggregate_header_limit(self):
        request = self.http.prefix() + b"X-Large: " + b"x" * transport.MAX_HEADER_BYTES + b"\r\n\r\n"
        self.assert_raw_status(request, 431)
        self.assertEqual(self.http.app.calls, [])

    def test_header_count_limit(self):
        request = self.http.prefix() + b"".join(f"X-{index}: x\r\n".encode() for index in range(31)) + b"\r\n"
        self.assert_raw_status(request, 431)
        self.assertEqual(self.http.app.calls, [])

    def test_malformed_or_ambiguous_headers_rejected(self):
        for header in (
            b"X: a\r\nX: b\r\n", b"Authorization: Bearer duplicate\r\n",
            b"Content-Length: 0\r\ncontent-length: 0\r\n", b" Folded: invalid\r\n",
            b"NoColon\r\n", b"Bad Name: x\r\n", b"Bad: \x00\r\n", b"Bad: \xff\r\n",
            b"Bad: invalid\n", b"Content-Length: -1\r\n", b"Content-Length: 1,1\r\n",
        ):
            with self.subTest(header=header):
                self.assert_raw_status(self.http.prefix() + header + b"\r\n", 400)
        self.assertEqual(self.http.app.calls, [])

    def test_nonorigin_and_malformed_request_lines_rejected(self):
        for line in (b"GET http://host/path HTTP/1.1\r\n", b"GET //host/path HTTP/1.1\r\n", b"GET / HTTP/2\r\n", b"GET /bad\x00 HTTP/1.1\r\n", b"GET / HTTP/1.1\n"):
            with self.subTest(line=line):
                self.assert_raw_status(line + b"\r\n", 400)
        self.assertEqual(self.http.app.calls, [])

    def test_body_limit_rejected_without_reading_body(self):
        request = self.http.prefix("POST") + b"Content-Length: 4097\r\nContent-Type: application/json\r\n\r\n"
        self.assert_raw_status(request, 413)
        self.assertEqual(self.http.app.calls, [])

    def test_post_requires_length_and_json_content_type(self):
        self.assert_raw_status(self.http.prefix("POST") + b"\r\n", 411)
        for content_type in ("text/plain", "application/json;charset=latin1", "application/x-www-form-urlencoded"):
            with self.subTest(content_type=content_type):
                status, _, _ = self.http.request("POST", body=b"{}", headers={"Content-Type": content_type})
                self.assertEqual(status, 415)
        self.assertEqual(self.http.app.calls, [])

    def test_get_rejects_body(self):
        status, _, _ = self.http.request(body=b"{}")
        self.assertEqual(status, 400)
        self.assertEqual(self.http.app.calls, [])

    def test_json_boundary_is_enforced(self):
        for body in (b"", b"{", b"{} trailing", b"[]", b"null", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'{"x":' + b"[" * 30 + b"0" + b"]" * 30 + b"}"):
            with self.subTest(body=body[:40]):
                status, _, response = self.http.request("POST", body=body)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(response), {"error": {"code": "invalid_json"}})
        self.assertEqual(self.http.app.calls, [])

    def test_exact_body_bound_accepted(self):
        body = b'{"x":"' + b"x" * (transport.MAX_BODY_BYTES - 8) + b'"}'
        self.assertEqual(len(body), transport.MAX_BODY_BYTES)
        status, _, _ = self.http.request("POST", body=body)
        self.assertEqual(status, 200)
        self.assertEqual(self.http.app.calls[0][3], body)

    def test_application_exceptions_are_generic_and_unlogged(self):
        sensitive = self.http.key.decode() + "/private/path/body-password"
        self.http.app.failure = sensitive
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status, _, response = self.http.request("POST", body=json.dumps({"private": sensitive}).encode())
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(response), {"error": {"code": "service_unavailable"}})
        self.assertNotIn(sensitive.encode(), response)
        self.assertEqual(output.getvalue() + errors.getvalue(), "")

    def test_request_errors_do_not_echo_sensitive_input(self):
        marker = self.http.key + b"-private-credential"
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status, _, response = self.http.request("POST", body=b'{"' + marker + b'":INVALID}')
            raw = self.assert_raw_status(self.http.prefix(path="/" + marker.decode()) + b"Bad: \x00\r\n\r\n", 400)
        self.assertEqual(status, 400)
        self.assertNotIn(marker, response + raw)
        self.assertEqual(output.getvalue() + errors.getvalue(), "")

    def test_oversized_or_invalid_responses_fail_closed(self):
        for response in (
            (200, {"payload": "private" * transport.MAX_RESPONSE_BYTES}),
            (200, {"payload": object()}), (200, {"payload": float("nan")}),
            (200, ["not", "an", "object"]), (999, {"payload": "private"}),
        ):
            with self.subTest(kind=type(response[1])):
                self.http.app.response = response
                status, _, body = self.http.request()
                self.assertEqual(status, 503)
                self.assertEqual(json.loads(body), {"error": {"code": "service_unavailable"}})
                self.assertLess(len(body), transport.MAX_RESPONSE_BYTES)

    def test_exact_response_body_limit(self):
        self.http.app.response = (200, {"x": "x" * (transport.MAX_RESPONSE_BYTES - 8)})
        status, headers, body = self.http.request()
        self.assertEqual(status, 200)
        self.assertEqual(len(body), transport.MAX_RESPONSE_BYTES)
        self.assertEqual(int(headers["Content-Length"]), transport.MAX_RESPONSE_BYTES)
        self.http.app.response[1]["x"] += "x"
        self.assertEqual(self.http.request()[0], 503)

    def test_exact_request_line_limit(self):
        path = "/" + "x" * (transport.MAX_REQUEST_LINE - 16)
        self.assertEqual(len(f"GET {path} HTTP/1.1\r\n"), transport.MAX_REQUEST_LINE)
        self.assert_raw_status(self.http.prefix(path=path) + b"\r\n", 200)

    def test_exact_header_count_limit(self):
        request = self.http.prefix() + b"".join(f"X-{index}: x\r\n".encode() for index in range(30)) + b"\r\n"
        self.assert_raw_status(request, 200)

    def test_exact_header_bytes_limit(self):
        prefix = self.http.prefix()
        existing_size = len(prefix) - len(b"GET /control/v1/status HTTP/1.1\r\n")
        padding = transport.MAX_HEADER_BYTES - existing_size - len(b"X: \r\n\r\n")
        self.assert_raw_status(prefix + b"X: " + b"x" * padding + b"\r\n\r\n", 200)

    def test_one_request_per_connection_prevents_pipeline_work(self):
        request = self.http.prefix() + b"\r\n"
        response = self.http.raw(request + request)
        self.assertEqual(response.count(b"HTTP/1.1 "), 1)
        self.assertEqual(len(self.http.app.calls), 1)

    def test_read_handler_responds_while_other_handler_waits(self):
        result = []
        worker = threading.Thread(target=lambda: result.append(self.http.request(path="/blocked")))
        worker.start()
        self.addCleanup(worker.join, 2)
        self.assertTrue(self.http.app.entered.wait(1))
        before = time.monotonic()
        status, _, _ = self.http.request()
        self.assertEqual(status, 200)
        self.assertLess(time.monotonic() - before, 0.5)
        self.http.app.release.set()
        worker.join(1)
        self.assertEqual(result[0][0], 200)

    def test_absolute_deadline_defeats_drip_feed(self):
        bounded = RunningServer(deadline=0.2)
        self.addCleanup(bounded.close)
        with socket.create_connection(bounded.address, timeout=1) as connection:
            before = time.monotonic()
            for _ in range(20):
                try:
                    connection.sendall(b"G")
                    time.sleep(0.025)
                except (BrokenPipeError, ConnectionResetError):
                    break
            self.assertLess(time.monotonic() - before, 0.4)
            try:
                self.assertEqual(connection.recv(1), b"")
            except ConnectionResetError:
                pass
        self.assertEqual(bounded.app.calls, [])

    def test_absolute_deadline_includes_body(self):
        bounded = RunningServer(deadline=0.2)
        self.addCleanup(bounded.close)
        with socket.create_connection(bounded.address, timeout=1) as connection:
            request = bounded.prefix("POST") + b"Content-Length: 20\r\nContent-Type: application/json\r\n\r\n{"
            connection.sendall(request)
            before = time.monotonic()
            self.assertEqual(connection.recv(1), b"")
            elapsed = time.monotonic() - before
            self.assertGreater(elapsed, 0.12)
            self.assertLess(elapsed, 0.5)
        self.assertEqual(bounded.app.calls, [])

    def test_absolute_deadline_closes_slow_application_socket(self):
        bounded = RunningServer(deadline=0.2)
        self.addCleanup(bounded.close)
        with socket.create_connection(bounded.address, timeout=1) as connection:
            before = time.monotonic()
            connection.sendall(bounded.prefix(path="/blocked") + b"\r\n")
            self.assertTrue(bounded.app.entered.wait(0.1))
            self.assertEqual(connection.recv(1), b"")
            self.assertLess(time.monotonic() - before, 0.5)
            # A timed-out application call retains its worker slot until it
            # returns. The supervisor never dispatches replacement work.
            self.assertEqual(len(bounded.server._active), 1)
            bounded.app.release.set()

    def test_connection_threads_are_bounded_and_slots_recover(self):
        held = []
        self.addCleanup(lambda: [connection.close() for connection in held])
        for _ in range(transport.MAX_CONNECTIONS):
            connection = socket.create_connection(self.http.address, timeout=1)
            held.append(connection)
            connection.sendall(b"GET ")
        deadline = time.monotonic() + 1
        while len(self.http.server._active) < transport.MAX_CONNECTIONS and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(self.http.server._active), 16)
        with socket.create_connection(self.http.address, timeout=1) as extra:
            self.assertEqual(extra.recv(1), b"")
        self.assertEqual(len(self.http.server._active), 16)
        for connection in held:
            connection.close()
        deadline = time.monotonic() + 1
        while self.http.server._active and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(self.http.server._active), 0)
        self.assertEqual(self.http.request()[0], 200)


if __name__ == "__main__":
    unittest.main()
