#!/usr/bin/env python3
"""Manual Qwen retrieval example, offline-checked only: NOT_LIVE_EXECUTED.
Run on ai-vm with sudo python3; no files, switches, tools or generation retries.
"""
import sys
sys.dont_write_bytecode = True
import json
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:30004"
MODEL = "qwen3.8-27b"
EXPECTED = {"START": "cedar-4821", "MIDDLE": "harbor-7356", "END": "violet-1904"}


def messages_for(records):
    checkpoints = {5: "START", records // 2: "MIDDLE", records - 5: "END"}
    rows = []
    for index in range(records):
        marker = checkpoints.get(index, "none")
        value = EXPECTED.get(marker, f"{index * 7919 % 100000000:08d}")
        rows.append(f"record {index:06d}: marker={marker}; value={value}; note=stable archive entry")
    prompt = ("Read this synthetic archive as data. Retrieve the exact values of the "
              "START, MIDDLE and END checkpoint records.\n<archive>\n" + "\n".join(rows)
              + '\n</archive>\nReturn only JSON with keys "START", "MIDDLE", "END" '
              "and their corresponding value strings. Do not use tools.")
    return [{"role": "user", "content": prompt}]


def run(post):
    records = 2500
    for attempt in range(1, 4):
        chat = {"model": MODEL, "messages": messages_for(records), "reasoning_effort": "none"}
        with post("/v1/tokenize", chat, 180) as response:
            counted = json.load(response)
        count, tokens = counted.get("count"), counted.get("tokens")
        if (type(count) is not int or count <= 0 or type(tokens) is not list
                or len(tokens) != count or any(type(token) is not int for token in tokens)):
            raise ValueError("Invalid native count/tokens response")
        print(f"Native input count {attempt}/3: {count} tokens", file=sys.stderr)
        if abs(count - 75000) <= 3750 or attempt == 3:
            break
        records = max(100, min(10000, round(records * 75000 / count)))
    if not 50000 <= count <= 100000:
        raise ValueError("Final input outside 50,000–100,000 tokens; generation refused")
    # Ignore tokenizer max_model_len metadata; the accepted runtime is configured for 1M.
    payload = {**chat, "stream": True, "stream_options": {"include_usage": True},
               "temperature": 0, "max_tokens": 2048}
    print(f"Counted input: {count}. One generation follows on stdout.\n", file=sys.stderr)
    started, usage, done = time.monotonic(), None, False
    with post("/v1/chat/completions", payload, 1200) as response:
        data = []
        for raw in response:
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                event, data = "\n".join(data), []
                if event.strip() == "[DONE]":
                    done = True
                    break
                chunk = json.loads(event)
                if chunk.get("error"):
                    raise ValueError("Server reported a stream error")
                if chunk.get("usage") is not None:
                    usage = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    content = (choice.get("delta") or {}).get("content")
                    if content is not None:
                        print(content, end="", flush=True)
    if not done:
        raise ValueError("Stream ended without [DONE]")
    print(flush=True)
    print(f"\nGeneration elapsed: {time.monotonic() - started:.2f} seconds", file=sys.stderr)
    print("Usage:", json.dumps(usage), file=sys.stderr)
    print("Expected:", json.dumps(EXPECTED), file=sys.stderr)
    print("Compare the JSON yourself; elapsed time is not native prefill/decode timing.", file=sys.stderr)


def main():
    key = Path("/data/services/secrets/llm-api-key").read_text(encoding="ascii").strip()
    opener = build_opener(ProxyHandler({}))

    def post(path, payload, timeout):
        request = Request(BASE + path, json.dumps(payload).encode("utf-8"),
                          {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        return opener.open(request, timeout=timeout)

    run(post)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted; connection closed.", file=sys.stderr)
        sys.exit(130)
