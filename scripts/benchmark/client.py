"""Drain-first streaming measurement for the temporary benchmark.

Importing this module performs no I/O. BENCHRUN must explicitly supply its
reviewed authenticated transport, owner/budget/storage gates and private output
directory. Parser/report failures never invoke lifecycle or cancel inference.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import time

from agent import protocol
from d3t import accounting
from benchmark.fixtures import HarnessError, canonical, digest


MAX_RESPONSE = 16 * 1024 * 1024


class StreamObserver:
    """Arrival timestamps are client observations, not native token timings.

    Role-only deltas do not count as first token. Content, reasoning, and tool
    argument/name deltas are separately observed. Errors latch and parsing stops,
    while the caller continues draining the network response to healthy EOF.
    """
    def __init__(self, started):
        self.started = started
        self.pending = b""
        self.first_content = self.first_reasoning = self.first_tool = None
        self.first_any = self.last_any = None
        self.done = False
        self.error = False
        self.events = 0

    def feed(self, chunk, arrived):
        if self.error:
            return
        try:
            self.pending += chunk
            trailing = b"\r" if self.pending.endswith(b"\r") else b""
            source = self.pending[:-1] if trailing else self.pending
            parts = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n\n")
            self.pending = parts[-1] + trailing
            if len(self.pending) > MAX_RESPONSE:
                raise HarnessError("oversized event")
            for part in parts[:-1]:
                data = b"\n".join(line[5:].lstrip(b" ") for line in part.split(b"\n") if line.startswith(b"data:"))
                if not data:
                    continue
                if data == b"[DONE]":
                    self.done = True
                    continue
                event = protocol.strict_json_loads(data)
                if not isinstance(event, dict) or event.get("error") is not None:
                    raise HarnessError("invalid stream event")
                self.events += 1
                for choice in event.get("choices", []):
                    delta = choice.get("delta", {})
                    emitted = False
                    for key, field in (("content", "first_content"), ("reasoning_content", "first_reasoning")):
                        value = delta.get(key)
                        if value is not None and not isinstance(value, str):
                            raise HarnessError("invalid delta")
                        if value:
                            emitted = True
                            if getattr(self, field) is None:
                                setattr(self, field, arrived - self.started)
                    for call in delta.get("tool_calls") or []:
                        function = call.get("function") or {}
                        if function.get("arguments") or function.get("name"):
                            emitted = True
                            if self.first_tool is None:
                                self.first_tool = arrived - self.started
                    if emitted:
                        if self.first_any is None:
                            self.first_any = arrived - self.started
                        self.last_any = arrived - self.started
        except Exception:
            # Do not echo parser exceptions (they may contain raw provider text).
            self.error = True

    def summary(self):
        return {"source": "client_event_arrival", "ttft_content_seconds": self.first_content,
                "ttft_reasoning_seconds": self.first_reasoning, "ttft_tool_seconds": self.first_tool,
                "ttft_any_output_seconds": self.first_any, "last_output_seconds": self.last_any,
                "events": self.events, "done_observed": self.done,
                "observer_status": "HARNESS_FAILURE" if self.error else "OK",
                "timing_limit": "event-arrival timestamps; chunk batching and client overhead included"}


def _events(raw):
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    result = []
    for event in text.split("\n\n")[:-1]:
        data = "\n".join(line[5:].lstrip(" ") for line in event.split("\n") if line.startswith("data:"))
        if data and data != "[DONE]":
            result.append(protocol.strict_json_loads(data))
    return result


def parse_response(raw, model):
    """Reuse shipped strict A1 parser/counter extraction after response drain.

    A 256/512 cap may normally produce finish=length. Preserve that verdict as
    OUTPUT_LIMIT, never a correctness regression. A normalized parse copy only
    enables obtaining a structurally complete message/counters for such samples;
    raw evidence and reported finish reason retain the real termination.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
        raise HarnessError("invalid or oversized response")
    try:
        events = _events(raw)
        if any(event.get("model") not in (None, model) for event in events):
            raise HarnessError("returned model differs from requested model")
        finishes = [choice.get("finish_reason") for event in events
                    for choice in event.get("choices", []) if choice.get("finish_reason") is not None]
        capped = finishes == ["length"]
        parse_raw = raw
        if capped:
            normalized = copy.deepcopy(events)
            for event in normalized:
                for choice in event.get("choices", []):
                    if choice.get("finish_reason") == "length":
                        choice["finish_reason"] = "stop"
            # Require the original framing and [DONE], using the existing parser
            # first. Its CompletionError proves length was the only completion
            # objection; malformed/truncated streams still fail here.
            try:
                protocol._stream(raw)
            except protocol.CompletionError as exc:
                if exc.diagnostics.get("parsing_failure"):
                    raise HarnessError("capped stream also contains a schema/parser failure") from exc
            parse_raw = b"".join(b"data: " + canonical(event) + b"\n\n" for event in normalized) + b"data: [DONE]\n\n"
        parsed = accounting.parse_response(parse_raw, True, model)
        return {"status": "OUTPUT_LIMIT" if capped else "COMPLETE",
                "message": parsed["message"], "model": parsed["model"],
                "finish_reason": "length" if capped else parsed["finish_reason"],
                "counters": parsed["counters"], "counter_source": "native_response_fields"}
    except (protocol.AgentError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise HarnessError("response framing/schema/counter parse failed") from exc


def _write_private(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def run_request(raw_body, transport, *, sample_id, private_dir, summary_path,
                timeout=7200, clock=time.monotonic, redact=None,
                observer_factory=StreamObserver):
    """One explicit future request, no retry or lifecycle operations.

    transport(bytes, timeout_seconds) yields byte chunks and owns protected auth,
    private IPv4 URL validation and an absolute wall-clock deadline <= timeout.
    Supply the existing reviewed HTTP client adapter; credentials never enter
    raw_body. redact(bytes) removes credential echoes before private persistence.
    All raw evidence is private; summary JSONL has allowlisted hashes/metrics.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", sample_id) or type(timeout) not in (int, float) or not 0 < timeout <= 7200:
        raise HarnessError("invalid request identity or timeout")
    request = protocol.strict_json_loads(raw_body)
    if request.get("max_tokens") not in (256, 512) or request.get("stream") is not True:
        raise HarnessError("benchmark request requires streaming and 256/512 cap")
    protocol._validate_messages(request.get("messages"))
    if redact is None:
        redact = getattr(transport, "redact", lambda data: data)
    root = Path(private_dir)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode & 0o077:
        raise HarnessError("private artifact directory must exist with mode 0700")
    request_path = root / (sample_id + ".request.json")
    _write_private(request_path, redact(raw_body))
    started = clock()
    observer = observer_factory(started)
    chunks, total, transport_error, oversized = [], 0, False, False
    try:
        for chunk in transport(raw_body, timeout):
            if not isinstance(chunk, bytes):
                transport_error = True
                continue
            total += len(chunk)
            if total <= MAX_RESPONSE:
                chunks.append(chunk)
            else:
                oversized = True
            try:
                observer.feed(chunk, clock())
            except Exception:
                # Even an unexpected observer implementation bug cannot abort
                # healthy inference. The transport still drains to completion.
                observer.error = True
    except Exception:
        transport_error = True
    ended = clock()
    raw = b"".join(chunks)
    raw_path = root / (sample_id + ".response.sse")
    report_errors = []
    try:
        _write_private(raw_path, redact(raw))
    except Exception:
        report_errors.append("private_response_write_failed")
    parsed = None
    status = "TRANSPORT_FAILURE" if transport_error else "HARNESS_FAILURE" if oversized else "COMPLETE"
    if status == "COMPLETE":
        try:
            parsed = parse_response(raw, request["model"])
            status = parsed["status"]
        except Exception:
            status = "HARNESS_FAILURE"
    if observer.error:
        report_errors.append("stream_timing_observer_failed")
        if status == "COMPLETE":
            status = "HARNESS_FAILURE"
    try:
        client_timing = observer.summary()
    except Exception:
        client_timing = {"observer_status": "HARNESS_FAILURE", "source": "client_event_arrival"}
        report_errors.append("stream_timing_summary_failed")
    summary = {"sample_id": sample_id, "status": status, "request_sha256": digest(raw_body),
               "response_sha256": digest(raw), "response_bytes": total,
               "response_retained_complete": not oversized,
               "client_elapsed_seconds": ended - started,
               "client_timing": client_timing, "counters": parsed["counters"] if parsed else {},
               "counter_source": "native_response_fields", "report_errors": report_errors,
               "retry_attempts": 0, "lifecycle_actions": 0}
    try:
        # Append immediately after each request; no prompt, model text, key, raw
        # provider error or arbitrary exception string enters this public record.
        fd = os.open(summary_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write(canonical(summary) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        report_errors.append("summary_write_failed")
    return {"summary": summary, "parsed": parsed,
            "private_request_path": str(request_path), "private_response_path": str(raw_path)}


def http_transport(base_url, api_key, *, clock=time.monotonic):
    """Explicit authenticated loopback/private-IPv4 HTTP transport factory.

    BENCHRUN establishes its reviewed private SSH transport/proxy/firewall policy
    first. No redirect, proxy environment, retry, endpoint discovery, logging or
    credential file read occurs here. Timeout includes header/body transfer;
    native read1 avoids waiting to fill a large client buffer before timestamps.
    """
    import http.client
    import ipaddress
    import socket
    import threading
    from urllib.parse import urlsplit

    url = urlsplit(base_url)
    try:
        address = ipaddress.ip_address(url.hostname)
    except ValueError as exc:
        raise HarnessError("transport requires explicit IPv4 endpoint") from exc
    if (url.scheme != "http" or address.version != 4 or not address.is_private or address.is_unspecified
            or url.username or url.password or url.query or url.fragment or url.path not in ("", "/v1")):
        raise HarnessError("endpoint is outside reviewed private HTTP transport")
    if not isinstance(api_key, str) or not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
        raise HarnessError("invalid protected credential")

    def send(body, timeout):
        if type(timeout) not in (int, float) or not 0 < timeout <= 7200:
            raise HarnessError("invalid absolute request deadline")
        deadline = clock() + timeout
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
        response = None
        def expire():
            # An absolute deadline also covers servers that drip HTTP headers.
            sock = connection.sock
            if sock is None and response is not None:
                sock = getattr(getattr(response.fp, "raw", None), "_sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            connection.request("POST", "/v1/chat/completions", body=body,
                               headers={"Authorization": "Bearer " + api_key,
                                        "Content-Type": "application/json", "Accept": "text/event-stream",
                                        "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status != 200 or response.getheader("Content-Type", "").split(";")[0] != "text/event-stream":
                raise HarnessError("HTTP status/content type failed")
            sock = connection.sock or getattr(getattr(response.fp, "raw", None), "_sock", None)
            if sock is None:
                raise HarnessError("cannot enforce request deadline")
            while True:
                remaining = deadline - clock()
                if remaining <= 0:
                    raise HarnessError("request deadline exhausted")
                sock.settimeout(remaining)
                chunk = response.read1(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()

    # Credential echoes are removed before persistence by run_request. The key
    # stays captured inside this callable; it is not in request bodies or logs.
    send.redact = lambda data: data.replace(api_key.encode("ascii"), b"[REDACTED]")
    return send


def protected_json_client(base_url, api_key, *, timeout=120):
    """Concrete protected native accounting HTTP client, no inference route.

    Constructing this factory makes no request. BENCHRUN wraps the returned
    callable in owner/storage/runtime identity gates, then supplies it to
    accounting.native_counter. Credentials remain in the authenticated header;
    neither request nor returned raw text is logged or persisted here.
    """
    import http.client
    import socket
    import threading
    from urllib.parse import urlsplit

    http_transport(base_url, api_key)  # shared endpoint/key validation, no I/O
    url = urlsplit(base_url)
    if type(timeout) not in (int, float) or not 0 < timeout <= 180:
        raise HarnessError("native accounting timeout must be <=180 seconds")

    def call(path, payload):
        if path not in ("/props", "/apply-template", "/tokenize", "/v1/tokenize") or (path == "/props") != (payload is None):
            raise HarnessError("native accounting route is not permitted")
        body = None if payload is None else canonical(payload)
        if body is not None and len(body) > 64 * 1024 * 1024:
            raise HarnessError("accounting request too large")
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
        response = None
        def expire():
            sock = connection.sock
            if sock is None and response is not None:
                sock = getattr(getattr(response.fp, "raw", None), "_sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            connection.request("GET" if payload is None else "POST", path, body=body,
                               headers={"Authorization": "Bearer " + api_key,
                                        "Content-Type": "application/json", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if (response.status != 200 or response.getheader("Content-Type", "").split(";")[0] != "application/json"
                    or response.getheader("Content-Encoding", "identity") != "identity"):
                raise HarnessError("native accounting HTTP status/format failed")
            data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024 or api_key.encode() in data:
                raise HarnessError("native response oversized or contains credential echo")
            result = protocol.strict_json_loads(data)
            if not isinstance(result, dict):
                raise HarnessError("native accounting result is not an object")
            return result
        except Exception:
            raise HarnessError("protected native accounting request failed") from None
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()

    return call
