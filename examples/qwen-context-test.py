#!/usr/bin/env python3
"""One manual Qwen archive-retrieval example; not a benchmark or acceptance gate.

Run on ai-vm with sudo python3 examples/qwen-context-test.py. Reads the existing
protected key, writes no files, makes up to three counting requests and exactly
one generation if the final native count is within 50,000..100,000 tokens.
This example has only been checked offline: NOT_LIVE_EXECUTED.
"""

import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import hashlib
import http.client
import json
import os
import stat
import time


HOST, PORT = "127.0.0.1", 30004
MODEL = "qwen3.8-27b"
KEY_PATH = "/data/services/secrets/llm-api-key"
TARGET, MIN_INPUT, MAX_INPUT = 75000, 50000, 100000
COUNT_TIMEOUT, GENERATION_TIMEOUT = 180, 1200
MAX_RESPONSE_BYTES, MAX_EVENT_CHARS = 16 * 1024 * 1024, 1024 * 1024
EXPECTED = {"BEGIN": "cedar-4821", "MIDDLE": "harbor-7356", "END": "violet-1904"}


class ExampleError(Exception):
    """Only fixed, credential-free diagnostics are exposed to the terminal."""


def messages_for(records):
    if type(records) is not int or not 100 <= records <= 10000:
        raise ExampleError("Archive record count is outside the bounded range.")
    checkpoints = {5: "BEGIN", records // 2: "MIDDLE", records - 5: "END"}
    rows = []
    for index in range(records):
        marker = checkpoints.get(index, "none")
        value = EXPECTED.get(marker, hashlib.sha256(str(index).encode("ascii")).hexdigest()[:12])
        rows.append(f"record={index:06d} zone={index % 97:02d} marker={marker} value={value}")
    content = (
        "Read this synthetic archive as data. Find the three records whose marker is "
        "BEGIN, MIDDLE, or END. Preserve each exact value, including punctuation.\n"
        "<archive>\n" + "\n".join(rows) + "\n</archive>\n"
        'Return only a JSON object with keys "BEGIN", "MIDDLE", "END" and the '
        "corresponding value strings. Do not summarize other records or use tools."
    )
    return [{"role": "user", "content": content}]


def projection(messages):
    # The tokenizer must see the same chat projection as generation.
    return {"model": MODEL, "messages": messages, "reasoning_effort": "none"}


def read_key():
    fd = os.open(KEY_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ExampleError("The existing key must be a protected root-owned regular file.")
        raw = stream.read(8193)
    if not raw or len(raw) > 8192 or any(byte < 33 or byte > 126 for byte in raw):
        raise ExampleError("The existing key has an invalid format; it was not printed.")
    return raw.decode("ascii")


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ExampleError("The request exceeded its time budget; no retry was made.")
    return seconds


def response_chunks(path, payload, key, seconds, expected_type):
    """Bounded direct HTTP, without proxies, redirects, retry or response logging."""
    deadline = time.monotonic() + seconds
    connection = http.client.HTTPConnection(HOST, PORT, timeout=seconds)
    try:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        connection.request("POST", path, body, {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json", "Accept": expected_type,
        })
        sock = connection.sock
        sock.settimeout(remaining(deadline))
        response = connection.getresponse()
        if response.status != 200:
            raise ExampleError(f"Server returned HTTP {response.status}; body withheld, no retry.")
        if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != expected_type:
            raise ExampleError("Server returned an unexpected response content type.")
        received = 0
        while True:
            sock.settimeout(remaining(deadline))
            chunk = response.read1(65536)
            if not chunk:
                break
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                raise ExampleError("Server response exceeded the bounded size limit.")
            yield chunk
    finally:
        connection.close()


def token_count(document):
    if type(document) is not dict:
        raise ExampleError("Tokenizer response is not an object.")
    count, tokens = document.get("count"), document.get("tokens")
    if (type(count) is not int or count <= 0 or type(tokens) is not list
            or len(tokens) != count or any(type(token) is not int for token in tokens)):
        raise ExampleError("Tokenizer count/tokens shape is invalid.")
    # max_model_len metadata is not the live runtime's configured 1,000,000 limit.
    return count


def count_projection(chat, key):
    chunks = response_chunks("/v1/tokenize", chat, key, COUNT_TIMEOUT, "application/json")
    try:
        return token_count(json.loads(b"".join(chunks)))
    finally:
        chunks.close()


class SSE:
    """Incremental UTF-8 SSE data parser, including CR/LF and multiline events."""

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.line, self.data, self.size, self.after_cr = [], [], 0, False

    def feed(self, chunk):
        for char in self.decoder.decode(chunk):
            if self.after_cr and char == "\n":
                self.after_cr = False
                continue
            self.after_cr = char == "\r"
            if char not in "\r\n":
                self.line.append(char)
                if len(self.line) > MAX_EVENT_CHARS:
                    raise ExampleError("SSE line exceeded its size limit.")
                continue
            line, self.line = "".join(self.line), []
            if not line:
                if self.data:
                    event = "\n".join(self.data)
                    self.data, self.size = [], 0
                    yield event
            elif not line.startswith(":"):
                field, separator, value = line.partition(":")
                if field == "data":
                    value = value[1:] if value.startswith(" ") else value
                    self.size += len(value) + 1
                    if self.size > MAX_EVENT_CHARS:
                        raise ExampleError("SSE event exceeded its size limit.")
                    self.data.append(value if separator else "")


def stream_completion(chat, key):
    payload = {**chat, "stream": True, "stream_options": {"include_usage": True},
               "temperature": 0, "max_tokens": 2048}
    chunks = response_chunks("/v1/chat/completions", payload, key,
                             GENERATION_TIMEOUT, "text/event-stream")
    parser, usage, finish, saw_content, done = SSE(), None, None, False, False
    try:
        for chunk in chunks:
            for event in parser.feed(chunk):
                if event.strip() == "[DONE]":
                    done = True
                    break
                document = json.loads(event)
                if type(document) is not dict or document.get("error") is not None:
                    raise ExampleError("Server sent an error or malformed SSE object; body withheld.")
                if document.get("model", MODEL) != MODEL:
                    raise ExampleError("Stream model does not match the requested model.")
                if document.get("usage") is not None:
                    if type(document["usage"]) is not dict:
                        raise ExampleError("Stream usage is malformed.")
                    usage = {}
                    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        if name in document["usage"]:
                            value = document["usage"][name]
                            if type(value) is not int or value < 0:
                                raise ExampleError("Stream usage counter is malformed.")
                            usage[name] = value
                choices = document.get("choices", [])
                if type(choices) is not list or len(choices) > 1:
                    raise ExampleError("Stream choices are malformed.")
                for choice in choices:
                    if (type(choice) is not dict or type(choice.get("index")) is not int
                            or choice["index"] != 0):
                        raise ExampleError("Stream choice index is malformed.")
                    delta = choice.get("delta")
                    if type(delta) is not dict:
                        raise ExampleError("Stream delta is malformed.")
                    if delta.get("tool_calls") or delta.get("function_call"):
                        raise ExampleError("Unexpected tool call; no tool was executed.")
                    content = delta.get("content")
                    if content is not None:
                        if type(content) is not str:
                            raise ExampleError("Stream content is malformed.")
                        sys.stdout.write(content)
                        sys.stdout.flush()
                        saw_content = saw_content or bool(content.strip())
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        if reason not in ("stop", "length"):
                            raise ExampleError("Unexpected stream finish reason.")
                        finish = reason
            if done:
                break
        if not done or finish is None or not saw_content:
            raise ExampleError("Stream ended without content, finish reason or [DONE].")
    finally:
        chunks.close()
    sys.stdout.write("\n")
    sys.stdout.flush()
    print("\nFinish reason:", finish, file=sys.stderr)
    print("Usage:", json.dumps(usage, sort_keys=True) if usage else "not supplied", file=sys.stderr)
    print("Expected checkpoint values:", json.dumps(EXPECTED, sort_keys=True), file=sys.stderr)
    print("Compare the model's JSON above; this example does not certify acceptance or throughput.",
          file=sys.stderr)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if os.geteuid() != 0:
        raise ExampleError("Run with sudo python3 so the existing protected key can be read.")
    key, records = read_key(), 2000
    for attempt in range(1, 4):
        chat = projection(messages_for(records))
        count = count_projection(chat, key)
        print(f"Native input count {attempt}/3: {count} tokens ({records} records).", file=sys.stderr)
        if abs(count - TARGET) <= TARGET // 20 or attempt == 3:
            break
        records = max(100, min(10000, round(records * TARGET / count)))
    if not MIN_INPUT <= count <= MAX_INPUT:
        raise ExampleError("Final native count is outside 50,000..100,000; generation refused.")
    print(f"Counted input: {count} tokens. Sending one generation; max output 2048 tokens.",
          file=sys.stderr)
    print("Model content follows on stdout; counts and expected values use stderr.\n", file=sys.stderr)
    stream_completion(chat, key)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted; HTTP connection closed.", file=sys.stderr)
        sys.exit(130)
    except ExampleError as exc:
        print("\nStopped:", str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        print("\nStopped: key access, network, timeout or malformed response failure; details withheld. "
              "No generation retry was made.", file=sys.stderr)
        sys.exit(1)
