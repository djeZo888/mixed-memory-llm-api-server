"""Bounded, authenticated IPv4-loopback HTTP transport for the control API.

One request is served per connection. No browser, proxy, WebSocket, or chunked
HTTP behavior is implemented. The application owns response field allowlists;
this module never passes authorization headers to it or logs requests/errors.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import re
import socket
import socketserver
import threading
import time

MAX_REQUEST_LINE = 2048
MAX_HEADER_BYTES = 8192
MAX_HEADERS = 32
MAX_BODY_BYTES = 4096
MAX_RESPONSE_BYTES = 256 * 1024
MAX_CONNECTIONS = 16
REQUEST_DEADLINE_SECONDS = 30.0
MAX_JSON_DEPTH = 16
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_LENGTH = re.compile(r"[0-9]{1,10}\Z")
_REASONS = {
    200: "OK", 202: "Accepted", 400: "Bad Request", 401: "Unauthorized",
    403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
    408: "Request Timeout", 409: "Conflict", 411: "Length Required",
    413: "Content Too Large", 414: "URI Too Long", 415: "Unsupported Media Type",
    417: "Expectation Failed", 422: "Unprocessable Content",
    431: "Request Header Fields Too Large", 503: "Service Unavailable",
}


class _Rejected(Exception):
    def __init__(self, status, code):
        self.status = status
        self.code = code


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("nonfinite value")


def _validate_json(body):
    try:
        value = json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if not isinstance(value, dict):
            raise ValueError("object required")
        pending = [(value, 0)]
        while pending:
            current, depth = pending.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError("nesting limit")
            if isinstance(current, dict):
                pending.extend((item, depth + 1) for item in current.values())
            elif isinstance(current, list):
                pending.extend((item, depth + 1) for item in current)
            elif isinstance(current, float) and not math.isfinite(current):
                raise ValueError("nonfinite value")
    except (UnicodeError, ValueError, RecursionError):
        raise _Rejected(400, "invalid_json") from None


def _encode_response(payload):
    if not isinstance(payload, dict):
        raise ValueError("response object required")
    chunks = []
    length = 0
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    for chunk in encoder.iterencode(payload):
        encoded = chunk.encode("ascii")
        length += len(encoded)
        if length > MAX_RESPONSE_BYTES:
            raise ValueError("response limit")
        chunks.append(encoded)
    return b"".join(chunks)


class _Handler(socketserver.BaseRequestHandler):
    def setup(self):
        self._deadline = self.server.connection_deadline(self.request)
        self._buffer = bytearray()
        self._replied = False

    def _time_remaining(self):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.request.settimeout(remaining)

    def _receive(self, size):
        self._time_remaining()
        received = self.request.recv(size)
        if not received:
            raise EOFError
        return received

    def _line(self, limit, too_large):
        while True:
            ending = self._buffer.find(b"\n")
            if ending >= 0:
                if ending + 1 > limit:
                    raise _Rejected(too_large, "request_limit")
                line = bytes(self._buffer[:ending + 1])
                del self._buffer[:ending + 1]
                if not line.endswith(b"\r\n"):
                    raise _Rejected(400, "invalid_request")
                return line
            if len(self._buffer) >= limit:
                raise _Rejected(too_large, "request_limit")
            self._buffer.extend(self._receive(min(4096, limit - len(self._buffer))))

    def _headers(self):
        headers = {}
        length = 0
        count = 0
        while True:
            line = self._line(MAX_HEADER_BYTES - length, 431)
            length += len(line)
            if line == b"\r\n":
                return headers
            count += 1
            if count > MAX_HEADERS or line[:1] in (b" ", b"\t"):
                raise _Rejected(431 if count > MAX_HEADERS else 400, "invalid_headers")
            try:
                name, value = line[:-2].decode("ascii").split(":", 1)
            except (ValueError, UnicodeError):
                raise _Rejected(400, "invalid_headers") from None
            if not _TOKEN.fullmatch(name) or any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value):
                raise _Rejected(400, "invalid_headers")
            name = name.lower()
            if name in headers:
                raise _Rejected(400, "invalid_headers")
            headers[name] = value.strip(" \t")

    def _body(self, size):
        while len(self._buffer) < size:
            self._buffer.extend(self._receive(size - len(self._buffer)))
        return bytes(self._buffer[:size])

    def _respond(self, status, payload):
        if self._replied:
            return
        try:
            if type(status) is not int or status not in _REASONS:
                raise ValueError("response status")
            body = _encode_response(payload)
        except (TypeError, ValueError, OverflowError, RecursionError):
            status = 503
            body = b'{"error":{"code":"service_unavailable"}}'
        extra = b'WWW-Authenticate: Bearer realm="control"\r\n' if status == 401 else b""
        if status == 405:
            extra += b"Allow: GET, POST\r\n"
        header = (
            f"HTTP/1.1 {status} {_REASONS[status]}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\nCache-Control: no-store\r\n"
            "X-Content-Type-Options: nosniff\r\n"
        ).encode("ascii") + extra + b"\r\n"
        self._time_remaining()
        self._replied = True
        self.request.sendall(header + body)

    def handle(self):
        try:
            line = self._line(MAX_REQUEST_LINE, 414)
            try:
                method, path, version = line[:-2].decode("ascii").split(" ")
            except (ValueError, UnicodeError):
                raise _Rejected(400, "invalid_request") from None
            if not _TOKEN.fullmatch(method) or version not in ("HTTP/1.0", "HTTP/1.1"):
                raise _Rejected(400, "invalid_request")
            if not path.startswith("/") or path.startswith("//") or any(ord(c) < 33 or ord(c) == 127 for c in path):
                raise _Rejected(400, "invalid_request")
            headers = self._headers()
            authorization = headers.pop("authorization", "")
            scheme, separator, credential = authorization.partition(" ")
            authenticated = hmac.compare_digest(credential.encode("ascii"), self.server.control_key)
            if scheme.lower() != "bearer" or not separator or not authenticated:
                raise _Rejected(401, "unauthorized")
            if "origin" in headers or any(name.startswith("sec-fetch-") for name in headers):
                raise _Rejected(403, "browser_control_forbidden")
            if ("upgrade" in headers
                    or any(name.startswith("sec-websocket-") for name in headers)
                    or "upgrade" in {part.strip() for part in headers.get("connection", "").lower().split(",")}):
                raise _Rejected(400, "unsupported_protocol")
            if method not in ("GET", "POST"):
                raise _Rejected(405, "method_not_allowed")
            if version == "HTTP/1.1" and not headers.get("host"):
                raise _Rejected(400, "invalid_headers")
            if "transfer-encoding" in headers:
                raise _Rejected(400, "unsupported_transfer_encoding")
            if "expect" in headers:
                raise _Rejected(417, "expectation_failed")
            if method == "POST" and "content-length" not in headers:
                raise _Rejected(411, "length_required")
            raw_size = headers.get("content-length", "0")
            if not _LENGTH.fullmatch(raw_size):
                raise _Rejected(400, "invalid_content_length")
            size = int(raw_size)
            if size > MAX_BODY_BYTES:
                raise _Rejected(413, "body_limit")
            if method == "GET" and size:
                raise _Rejected(400, "unexpected_body")
            if method == "POST":
                content_type = headers.get("content-type", "").lower().replace(" ", "")
                if content_type not in ("application/json", "application/json;charset=utf-8"):
                    raise _Rejected(415, "json_required")
            body = self._body(size)
            if method == "POST":
                _validate_json(body)
            safe_headers = {name: headers[name] for name in ("idempotency-key", "content-type") if name in headers}
            try:
                status, payload = self.server.application.handle(method, path, safe_headers, body)
            except Exception:
                raise _Rejected(503, "service_unavailable") from None
            self._respond(status, payload)
        except _Rejected as rejected:
            try:
                self._respond(rejected.status, {"error": {"code": rejected.code}})
            except (OSError, TimeoutError):
                pass
        except (OSError, EOFError, TimeoutError):
            # At the absolute deadline, close without spending a second budget
            # attempting an error response. Never log partial/untrusted input.
            pass


class _BoundedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    address_family = socket.AF_INET
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, address, application, key):
        self.application = application
        self.control_key = key
        self.request_deadline = REQUEST_DEADLINE_SECONDS
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._active = {}
        self._active_lock = threading.Condition()
        self._closing = False
        super().__init__(address, _Handler)
        # One supervisor closes sockets at their absolute deadline even when a
        # bounded application observation takes too long. It does not execute
        # lifecycle work or create another request executor.
        self._deadline_thread = threading.Thread(target=self._expire_connections, daemon=True)
        self._deadline_thread.start()

    def connection_deadline(self, request):
        with self._active_lock:
            return self._active.get(request) or time.monotonic()

    @staticmethod
    def _close_connection(connection):
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()

    def _expire_connections(self):
        while True:
            with self._active_lock:
                if self._closing:
                    return
                now = time.monotonic()
                deadlines = [(connection, deadline) for connection, deadline in self._active.items() if deadline is not None]
                expired = [connection for connection, deadline in deadlines if deadline <= now]
                if not expired:
                    next_deadline = min((deadline for _, deadline in deadlines), default=None)
                    self._active_lock.wait(None if next_deadline is None else max(0, next_deadline - now))
                    continue
                for connection in expired:
                    self._active[connection] = None
            for connection in expired:
                self._close_connection(connection)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            # Admission overload closes the connection without an unauthenticated
            # application response, or creating another worker/thread.
            self.shutdown_request(request)
            return
        with self._active_lock:
            self._active[request] = time.monotonic() + self.request_deadline
            self._active_lock.notify_all()
        try:
            super().process_request(request, client_address)
        except Exception:
            with self._active_lock:
                self._active.pop(request, None)
                self._active_lock.notify_all()
            self._slots.release()
            self.shutdown_request(request)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._active_lock:
                self._active.pop(request, None)
                self._active_lock.notify_all()
            self._slots.release()

    def handle_error(self, request, client_address):
        # socketserver's default includes traceback text. Never emit untrusted
        # paths, credentials, exception details, or raw application responses.
        pass

    def server_close(self):
        super().server_close()
        with self._active_lock:
            self._closing = True
            active = tuple(self._active)
            self._active_lock.notify_all()
        for connection in active:
            self._close_connection(connection)
        self._deadline_thread.join(1)


def make_server(application, key: bytes, host="127.0.0.1", port=30000):
    """Construct the server; caller runs serve_forever and closes it on exit.

    Keys must be 32..256 printable ASCII bytes without whitespace. The installer
    provisions a separate protected key; this transport never loads a fallback.
    Only literal IPv4 loopback bind addresses are accepted (no DNS resolution).
    """
    try:
        address = ipaddress.IPv4Address(host)
    except (ipaddress.AddressValueError, TypeError):
        raise ValueError("IPv4 loopback address required") from None
    if not address.is_loopback:
        raise ValueError("IPv4 loopback address required")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid port")
    if not isinstance(key, bytes) or not 32 <= len(key) <= 256 or any(c < 33 or c > 126 for c in key):
        raise ValueError("invalid control key")
    if not callable(getattr(application, "handle", None)):
        raise TypeError("application.handle required")
    return _BoundedServer((str(address), port), application, key)
