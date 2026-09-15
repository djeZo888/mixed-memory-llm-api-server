"""Bounded, dependency-free OpenAI Chat Completions transport.

This module executes no tools. HTTP never follows redirects or reads proxy settings.
Streaming responses are bounded and reconstructed before being returned to callers.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import queue
import socket
import stat
import threading
import time
from urllib.parse import urlsplit


class AgentError(Exception):
    """A safe-to-display client or protocol failure."""


class APIError(AgentError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"API returned HTTP {status}; response body omitted")


class CompletionError(AgentError):
    """Incomplete completion with bounded metadata, never response/tool text."""

    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__("token_budget_exhausted: completion ended with length"
                         + ("; assistant message validation failed" if diagnostics.get("parsing_failure") else ""))


REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def _reasoning_effort(value):
    if value is not None and (type(value) is not str or value not in REASONING_EFFORTS):
        raise AgentError("reasoning_effort must be None or one of: " + ", ".join(REASONING_EFFORTS))
    return value


def _usage_diagnostic(value):
    """Only known, nonnegative token counters fit in termination diagnostics."""
    if not isinstance(value, dict):
        return None

    def counts(mapping, names):
        return {name: mapping[name] for name in names
                if type(mapping.get(name)) is int and 0 <= mapping[name] <= 2**63 - 1}

    result = counts(value, ("prompt_tokens", "completion_tokens", "total_tokens"))
    for field, names in (
        ("prompt_tokens_details", ("cached_tokens", "audio_tokens")),
        ("completion_tokens_details", ("reasoning_tokens", "audio_tokens",
                                       "accepted_prediction_tokens", "rejected_prediction_tokens")),
    ):
        if isinstance(value.get(field), dict):
            nested = counts(value[field], names)
            if nested:
                result[field] = nested
    return result or None


def _length_diagnostic(model, usage, stream_done, parsing_failure=False):
    # Also enforce this after credential redaction, which can expand text.
    safe_model = model if (isinstance(model, str) and 0 < len(model) <= 1024
                           and all(32 <= ord(c) < 127 for c in model)) else None
    result = {"classification": "token_budget_exhausted", "finish_reason": "length",
              "model": safe_model, "usage": _usage_diagnostic(usage), "stream_done": stream_done}
    if parsing_failure:
        result["parsing_failure"] = "invalid_assistant_message"
    return result


def redact_diagnostic(diagnostic, key):
    """Rebuild the allowlist without redacting trusted enums or counter names."""
    return _length_diagnostic(redact(diagnostic.get("model"), key), diagnostic.get("usage"),
                              diagnostic.get("stream_done") is True,
                              diagnostic.get("parsing_failure") == "invalid_assistant_message")


def _checked_assistant(message, finish, model, usage, stream_done):
    try:
        parsed = _assistant(message)
    except AgentError:
        if finish == "length":
            raise CompletionError(_length_diagnostic(model, usage, stream_done, True)) from None
        raise
    if finish == "length":
        raise CompletionError(_length_diagnostic(model, usage, stream_done))
    _finish(finish, parsed[0])
    return parsed


class Budget:
    def __init__(self, overall_timeout: float):
        if not isinstance(overall_timeout, (int, float)) or not math.isfinite(overall_timeout) or overall_timeout <= 0:
            raise AgentError("overall timeout must be a positive finite number")
        self.overall_timeout = overall_timeout
        self.deadline = time.monotonic() + overall_timeout

    def remaining(self) -> float:
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise AgentError("overall time budget exhausted")
        return seconds

    def check(self) -> None:
        self.remaining()


def redact(value, key):
    """Remove the configured key recursively, including from mapping keys."""
    if isinstance(value, str):
        if not isinstance(key, str) or not key:
            return value
        # Tool arguments are JSON encoded inside a JSON string. Cover literal and
        # common nested JSON escaping before the outer report is serialized.
        variants = {key}
        escaped = key
        for _ in range(3):
            escaped = json.dumps(escaped, ensure_ascii=True)[1:-1]
            variants.add(escaped)
        for variant in sorted(variants, key=len, reverse=True):
            value = value.replace(variant, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {redact(k, key): redact(v, key) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, key) for item in value]
    return value


def _validate_key(value):
    if not isinstance(value, str) or not value or value.strip() != value or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise AgentError("API key must be a nonempty single-line printable ASCII value without whitespace")
    if len(value) > 8192:
        raise AgentError("API key exceeds the size limit")
    return value


def load_api_key(path=None, env_name=None):
    """Read only an explicitly requested protected file, or a named environment variable."""
    if path is not None:
        fd = None
        try:
            # O_NOFOLLOW closes the final-component symlink race; inspect the same fd read.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise AgentError("API key file must be an owned regular nonsymlink file with mode 0600 or stricter")
            if info.st_size > 8192:
                raise AgentError("API key file exceeds the size limit")
            value = os.read(fd, 8193).decode("ascii")
        except (OSError, UnicodeError):
            raise AgentError("unable to read protected API key file") from None
        finally:
            if fd is not None:
                os.close(fd)
        return _validate_key(value)
    if env_name is not None:
        if not isinstance(env_name, str) or not env_name:
            raise AgentError("API key environment variable name is invalid")
        value = os.environ.get(env_name)
        if value is None:
            raise AgentError("configured API key environment variable is unset")
        return _validate_key(value)
    return None


def strict_json_loads(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise AgentError("JSON contains a duplicate object key")
            result[key] = item
        return result

    def constant(_):
        raise AgentError("JSON contains a non-finite constant")

    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise AgentError("JSON contains a non-finite number")
        return number

    try:
        return json.loads(value, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
    except (ValueError, UnicodeError, RecursionError):
        raise AgentError("malformed JSON response or tool arguments") from None


def _identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and all(32 < ord(c) < 127 for c in value)


def _calls(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise AgentError("tool_calls must contain between 1 and 32 calls")
    seen = set()
    cleaned = []
    for call in value:
        if not isinstance(call, dict) or set(call) - {"id", "type", "function"}:
            raise AgentError("malformed tool call schema")
        call_id = call.get("id")
        if not _identifier(call_id) or call_id in seen:
            raise AgentError("tool call ID is invalid, missing, or duplicated")
        seen.add(call_id)
        fn = call.get("function")
        if call.get("type") != "function" or not isinstance(fn, dict) or set(fn) != {"name", "arguments"} or not _identifier(fn.get("name")) or not isinstance(fn.get("arguments"), str):
            raise AgentError("malformed function tool call schema")
        arguments = strict_json_loads(fn["arguments"])
        if not isinstance(arguments, dict):
            raise AgentError("tool arguments must be a JSON object")
        cleaned.append({"id": call_id, "type": "function", "function": dict(fn)})
    return cleaned


def _validate_messages(messages):
    if not isinstance(messages, list) or not 1 <= len(messages) <= 512:
        raise AgentError("messages must be a nonempty bounded list")
    pending, seen = set(), set()
    for message in messages:
        if not isinstance(message, dict):
            raise AgentError("message must be an object")
        role = message.get("role")
        if role not in {"system", "developer", "user", "assistant", "tool"}:
            raise AgentError("invalid message role")
        if message.get("content") is not None and not isinstance(message["content"], str):
            raise AgentError("message content must be text or null")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if not _identifier(call_id) or call_id not in pending or not isinstance(message.get("content"), str):
                raise AgentError("tool result must have the matching pending tool_call_id and text content")
            if "tool_calls" in message:
                raise AgentError("tool result cannot request more tools")
            pending.remove(call_id)
            continue
        if pending:
            raise AgentError("all pending tool calls require tool-role results before continuation")
        if "tool_call_id" in message:
            raise AgentError("only a tool-role result may carry tool_call_id")
        if "tool_calls" in message:
            if role != "assistant":
                raise AgentError("only assistant messages may request tools")
            for call in _calls(message["tool_calls"]):
                if call["id"] in seen:
                    raise AgentError("tool call ID reused in conversation")
                seen.add(call["id"])
                pending.add(call["id"])
    if pending:
        raise AgentError("tool results are missing before the next API request")


def _assistant(message):
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise AgentError("response message must have assistant role")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise AgentError("assistant content must be text or null")
    result = {"role": "assistant", "content": content}
    if message.get("tool_calls") is not None:
        result["tool_calls"] = _calls(message["tool_calls"])
    if "function_call" in message:
        raise AgentError("legacy function_call is unsupported; configure native tool_calls")
    reasoning = {k: v for k, v in message.items() if k.startswith("reasoning")}
    return result, reasoning


def _finish(reason, message):
    expected = "tool_calls" if message.get("tool_calls") else "stop"
    if reason != expected:
        raise AgentError(f"completion did not terminate with {expected}; check token limit and backend tool support")


def _model(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise AgentError("response lacks a valid model identity")
    return value


def _completion(payload):
    if not isinstance(payload, dict) or payload.get("error") is not None:
        raise AgentError("API returned an error or invalid completion envelope")
    model = _model(payload.get("model"))
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict) or choices[0].get("index", 0) != 0:
        raise AgentError("expected exactly one completion choice with index zero")
    choice = choices[0]
    message, reasoning = _checked_assistant(choice.get("message"), choice.get("finish_reason"),
                                            model, payload.get("usage"), False)
    return {"message": message, "model": model, "finish_reason": choice["finish_reason"], "usage": payload.get("usage"), "reasoning": reasoning, "stream_done": False}


def _stream(payload):
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        raise AgentError("stream contains invalid UTF-8") from None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    content, reasoning, calls = [], {}, {}
    model, finish, usage = None, None, None
    done = False
    # A complete event is blank-line terminated. A final incomplete data event is an error.
    events = text.split("\n\n")
    if events[-1].strip() and any(line.startswith("data:") for line in events[-1].split("\n")):
        raise AgentError("stream ended inside an SSE event")
    for event in events[:-1]:
        data = "\n".join(line[5:].lstrip(" ") for line in event.split("\n") if line.startswith("data:"))
        if not data:
            continue
        if done:
            raise AgentError("stream contains data after [DONE]")
        if data == "[DONE]":
            done = True
            continue
        chunk = strict_json_loads(data)
        if not isinstance(chunk, dict) or chunk.get("error") is not None:
            raise AgentError("stream returned an error or invalid envelope")
        if "model" in chunk:
            this_model = _model(chunk["model"])
            if model is not None and model != this_model:
                raise AgentError("stream changed model identity")
            model = this_model
        if chunk.get("usage") is not None:
            usage = chunk["usage"]
        choices = chunk.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise AgentError("stream must contain at most one choice")
        if not choices:  # Final usage-only chunk.
            continue
        choice = choices[0]
        if not isinstance(choice, dict) or type(choice.get("index")) is not int or choice["index"] != 0:
            raise AgentError("stream choice index must be zero")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise AgentError("stream delta must be an object")
        if finish is not None:
            raise AgentError("stream contains a choice after finish_reason")
        if delta.get("role", "assistant") != "assistant":
            raise AgentError("stream delta has an invalid role")
        if "function_call" in delta:
            raise AgentError("legacy function_call is unsupported; configure native tool_calls")
        if delta.get("content") is not None:
            if not isinstance(delta["content"], str):
                raise AgentError("stream content must be text or null")
            content.append(delta["content"])
        for key, value in delta.items():
            if not key.startswith("reasoning") or value is None:
                continue
            if key not in reasoning:
                reasoning[key] = value
            elif isinstance(value, str) and isinstance(reasoning[key], str):
                reasoning[key] += value
            elif isinstance(value, list) and isinstance(reasoning[key], list):
                reasoning[key].extend(value)
            else:
                raise AgentError("incompatible streaming reasoning fragments")
        if delta.get("tool_calls") is not None:
            if not isinstance(delta["tool_calls"], list):
                raise AgentError("stream tool_calls must be an array")
            for part in delta["tool_calls"]:
                if not isinstance(part, dict) or set(part) - {"index", "id", "type", "function"}:
                    raise AgentError("malformed streaming tool call")
                index = part.get("index")
                if type(index) is not int or not 0 <= index < 32:
                    raise AgentError("stream tool call index is missing or invalid")
                call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if "type" in part and part["type"] != "function":
                    raise AgentError("stream tool call type must be function")
                if "id" in part:
                    if not isinstance(part["id"], str):
                        raise AgentError("stream tool call ID must be text")
                    call["id"] += part["id"]
                if "function" in part:
                    fn = part["function"]
                    if not isinstance(fn, dict) or set(fn) - {"name", "arguments"}:
                        raise AgentError("malformed streaming function schema")
                    for field, value in fn.items():
                        if not isinstance(value, str):
                            raise AgentError("stream function fields must be text")
                        call["function"][field] += value
        if choice.get("finish_reason") is not None:
            if not isinstance(choice["finish_reason"], str):
                raise AgentError("stream finish_reason must be text")
            finish = choice["finish_reason"]
    if not done or finish is None:
        raise AgentError("stream is incomplete: finish_reason and [DONE] are both required")
    message = {"role": "assistant", "content": "".join(content) if content else None}
    if calls:
        if sorted(calls) != list(range(len(calls))):
            raise AgentError("stream tool call indexes must be contiguous from zero")
        message["tool_calls"] = [calls[index] for index in sorted(calls)]
    model = _model(model)
    message, _ = _checked_assistant(message, finish, model, usage, True)
    return {"message": message, "model": model, "finish_reason": finish, "usage": usage, "reasoning": reasoning, "stream_done": True}


_DEFAULT_KEY = object()


class Client:
    """One-request-at-a-time HTTP client, bounded to 128 requests per instance."""

    def __init__(self, base_url, model, api_key=None, request_timeout=60, budget=None, max_response_bytes=262144, max_tokens=1024, reasoning_effort=None):
        self.reasoning_effort = _reasoning_effort(reasoning_effort)
        try:
            url = urlsplit(base_url)
            port = url.port
        except (ValueError, TypeError):
            raise AgentError("invalid API base URL") from None
        if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment:
            raise AgentError("API base URL requires HTTP(S), a host, and no credentials/query/fragment")
        if not url.path.rstrip("/").endswith("/v1"):
            raise AgentError("API base URL must end in /v1")
        if not isinstance(request_timeout, (int, float)) or not math.isfinite(request_timeout) or request_timeout <= 0:
            raise AgentError("request timeout must be positive and finite")
        if type(max_response_bytes) is not int or not 1024 <= max_response_bytes <= 16 * 1024 * 1024:
            raise AgentError("max response bytes must be between 1024 and 16777216")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
            raise AgentError("max_tokens must be between 1 and 32768")
        self.base_url, self.model = base_url.rstrip("/"), _model(model)
        self.api_key = _validate_key(api_key) if api_key is not None else None
        self.request_timeout, self.budget = request_timeout, budget or Budget(600)
        self.max_response_bytes, self.max_tokens = max_response_bytes, max_tokens
        self.requests = []
        self._scheme, self._host, self._port, self._path = url.scheme, url.hostname, port, url.path.rstrip("/")
        self._lock = threading.Lock()

    def _request(self, suffix, payload=None, stream=False, api_key=_DEFAULT_KEY):
        if not self._lock.acquire(blocking=False):
            raise AgentError("concurrent client requests are unsupported; serialize API requests")
        started = time.monotonic()
        key = self.api_key if api_key is _DEFAULT_KEY else api_key
        record = {"path": suffix, "stream": stream, "status": None, "success": False}
        try:
            if key is not None:
                _validate_key(key)
            if len(self.requests) >= 128:
                raise AgentError("client request limit of 128 exhausted")
            timeout = min(self.request_timeout, self.budget.remaining())
            body = None
            if payload is not None:
                try:
                    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                except (ValueError, TypeError, RecursionError, UnicodeError):
                    raise AgentError("request is not valid JSON") from None
                if len(body) > self.max_response_bytes:
                    raise AgentError("request exceeds byte limit; reduce conversation or tool output")
            record["requested_model"] = payload.get("model") if payload else None
            cls = http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
            connection = cls(self._host, port=self._port, timeout=timeout)
            cancelled = threading.Event()
            result = queue.Queue(maxsize=1)
            network_socket = []

            def worker():
                response = None
                try:
                    headers = {"Accept": "text/event-stream" if stream else "application/json", "Content-Type": "application/json", "Accept-Encoding": "identity"}
                    if key is not None:
                        headers["Authorization"] = "Bearer " + key
                    connection.connect()
                    network_socket.append(connection.sock)
                    if cancelled.is_set():
                        return
                    connection.request("POST" if payload is not None else "GET", self._path + suffix, body=body, headers=headers)
                    response = connection.getresponse()
                    if response.status < 200 or response.status >= 300:
                        raise APIError(response.status)
                    content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                    expected = "text/event-stream" if stream else "application/json"
                    if content_type != expected:
                        raise AgentError("API returned an unexpected Content-Type")
                    if response.getheader("Content-Encoding", "identity").lower() != "identity":
                        raise AgentError("compressed API responses are unsupported")
                    length = response.getheader("Content-Length")
                    if length is not None:
                        if not length.isdecimal() or int(length) > self.max_response_bytes:
                            raise AgentError("API response exceeds byte limit or has invalid Content-Length")
                    chunks, total, stream_scan = [], 0, b""
                    while not cancelled.is_set():
                        chunk = response.read1(min(4096, self.max_response_bytes + 1 - total))
                        if not chunk:
                            if response.length is not None and response.length > 0:
                                raise AgentError("API response ended before Content-Length bytes arrived")
                            break
                        total += len(chunk)
                        if total > self.max_response_bytes:
                            raise AgentError("API response exceeds byte limit")
                        chunks.append(chunk)
                        if stream:
                            stream_scan += chunk
                            # Preserve a trailing CR so CRLF split across reads is
                            # normalized exactly once. Retain only an incomplete
                            # event to avoid rescanning the whole response.
                            trailing_cr = b"\r" if stream_scan.endswith(b"\r") else b""
                            scan = stream_scan[:-1] if trailing_cr else stream_scan
                            events = scan.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n\n")
                            stream_scan = events[-1] + trailing_cr
                            complete = False
                            for event in events[:-1]:
                                data = b"\n".join(line[5:].lstrip(b" ") for line in event.split(b"\n") if line.startswith(b"data:"))
                                if data == b"[DONE]":
                                    complete = True
                                    break
                            if complete:
                                break
                    if not cancelled.is_set():
                        result.put((response.status, b"".join(chunks)))
                except (socket.timeout, TimeoutError):
                    result.put(AgentError("API request timed out"))
                except AgentError as exc:
                    result.put(exc)
                except Exception:
                    result.put(AgentError("API transport failed; check endpoint and tunnel"))
                finally:
                    if response is not None:
                        response.close()
                    connection.close()

            thread = threading.Thread(target=worker, name="bounded-api-request", daemon=True)
            thread.start()
            try:
                outcome = result.get(timeout=max(0.001, timeout - (time.monotonic() - started)))
            except queue.Empty:
                cancelled.set()
                # Interrupt header/body reads even if a server drips bytes forever.
                sock = network_socket[0] if network_socket else connection.sock
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                raise AgentError("API request exceeded request or overall time budget") from None
            if isinstance(outcome, Exception):
                if isinstance(outcome, APIError):
                    record["status"] = outcome.status
                raise outcome
            self.budget.check()
            status, data = outcome
            record["status"] = status
            if suffix == "/models":
                parsed = strict_json_loads(data)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list) or parsed.get("error") is not None:
                    raise AgentError("invalid model-list response")
                identities = []
                for item in parsed["data"]:
                    if not isinstance(item, dict):
                        raise AgentError("invalid model-list entry")
                    identities.append(_model(item.get("id")))
                if len(identities) != len(set(identities)):
                    raise AgentError("model list contains duplicate identities")
            else:
                try:
                    parsed = _stream(data) if stream else _completion(strict_json_loads(data))
                except CompletionError as exc:
                    diagnostic = redact_diagnostic(redact_diagnostic(exc.diagnostics, key), self.api_key)
                    record.update(diagnostic)
                    raise CompletionError(diagnostic) from None
                parsed["elapsed_seconds"] = round(time.monotonic() - started, 6)
                record.update({"model": parsed["model"], "usage": parsed["usage"], "finish_reason": parsed["finish_reason"]})
            self.budget.check()
            record["success"] = True
            # Internal protocol data must preserve IDs, arguments, and schema.
            # Callers redact a report copy at the serialization/logging boundary.
            return parsed
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - started, 6)
            if len(self.requests) < 128:
                # Fixed schema keys and status/termination enums are trusted;
                # only external values can echo a credential.
                for field in ("requested_model", "model", "usage"):
                    if field in {"model", "usage"} and record.get("classification") == "token_budget_exhausted":
                        continue  # Already bounded and redacted; diagnostic keys are trusted.
                    if field in record:
                        record[field] = redact(redact(record[field], key), self.api_key)
                self.requests.append(record)
            self._lock.release()

    def models(self, api_key=_DEFAULT_KEY):
        return self._request("/models", api_key=api_key)

    def chat(self, messages, tools=None, stream=False, model=None, api_key=_DEFAULT_KEY):
        effort = _reasoning_effort(self.reasoning_effort)
        _validate_messages(messages)
        payload = {"model": self.model if model is None else _model(model), "messages": messages, "stream": bool(stream), "max_tokens": self.max_tokens}
        if effort is not None:
            payload["reasoning_effort"] = effort
        if tools is not None:
            if not isinstance(tools, list) or not 1 <= len(tools) <= 32:
                raise AgentError("tools must contain between 1 and 32 definitions")
            payload["tools"] = tools
        return self._request("/chat/completions", payload, stream=stream, api_key=api_key)
