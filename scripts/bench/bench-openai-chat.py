#!/usr/bin/env python3
"""Run one local OpenAI-compatible chat benchmark case.

This script intentionally uses only the Python standard library. It targets the
localhost-only M9B SGLang endpoint by default and appends compact JSONL results
under /data/logs, never under the root filesystem.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "http://127.0.0.1:30001/v1/chat/completions"
DEFAULT_MODEL = "qwen3-30b-a3b-instruct-2507"
DEFAULT_OUTPUT_JSONL = "/data/logs/benchmarks/m9c/m9c-results.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_excerpt(text: str, limit: int = 360) -> str:
    compact = " ".join(text.replace("\x00", " ").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def repeated_context(target_chars: int, task: str) -> str:
    block = (
        "Technical note: This VM runs a localhost-only SGLang backend with two "
        "passthrough RTX PRO 6000 Blackwell GPUs. The backend must keep model "
        "weights, cache files, Docker data, containerd data, logs, and benchmark "
        "artifacts under /data. Public API exposure, host 0.0.0.0 binds, model "
        "downloads, Docker image pulls, package installs, and daemon restarts are "
        "outside the benchmark scope. Measurements should focus on latency, "
        "streaming behavior, GPU memory, GPU utilization, power, and dry-run "
        "lifecycle safety. Correctable PCIe AER warnings have been observed in "
        "historical passthrough reset/start activity and should be monitored "
        "during longer load tests.\n"
    )
    pieces: list[str] = []
    while sum(len(part) for part in pieces) < target_chars:
        pieces.append(block)
    context = "".join(pieces)[:target_chars]
    return (
        "You are reviewing a local inference benchmark. Use only the context below.\n\n"
        f"{context}\n\nTask: {task}"
    )


def prompt_for_case(case: str) -> str:
    if case == "tiny_health":
        return "Reply in one short sentence confirming the M9C benchmark health check is working."
    if case == "technical_short":
        return "In one paragraph, explain what PCIe passthrough means for a GPU in a VM."
    if case == "coding_short":
        return (
            "Write a small Python function named chunked that yields fixed-size chunks "
            "from a list, then explain the function in three concise bullet points."
        )
    if case == "streaming_short":
        return (
            "Return a concise five-item checklist for validating that a localhost-only "
            "OpenAI-compatible model endpoint is healthy."
        )
    if case == "context_4k":
        return repeated_context(
            4096,
            "Produce an eight-bullet summary of the operational constraints and checks.",
        )
    if case == "context_8k":
        return repeated_context(
            8192,
            "List the main constraints and risks, grouped into storage, GPU, lifecycle, and exposure categories.",
        )
    if case == "context_16k":
        return repeated_context(
            16384,
            "Identify the benchmark risks, operational guardrails, and tuning candidates without recommending public exposure.",
        )
    raise SystemExit(f"unknown benchmark case: {case}")


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return prompt_for_case(args.case)


def append_jsonl(path: str, entry: dict[str, Any]) -> None:
    out = Path(path)
    if not str(out).startswith("/data/"):
        raise SystemExit(f"refusing to write benchmark JSONL outside /data: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")


def request_payload(args: argparse.Namespace, prompt: str) -> bytes:
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "You are a concise technical assistant."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
    }
    if args.stream:
        payload["stream"] = True
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def open_request(args: argparse.Namespace, body: bytes):
    req = urllib.request.Request(
        args.endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=args.timeout)


def run_non_stream(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    body = request_payload(args, prompt)
    start = time.monotonic()
    status: int | None = None
    raw = b""
    error = ""
    try:
        with open_request(args, body) as resp:
            status = int(resp.status)
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
        error = f"HTTPError: {exc.code}"
    except Exception as exc:  # compact benchmark error capture
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - start

    parsed: dict[str, Any] | None = None
    parse_ok = False
    content = ""
    usage: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
            parse_ok = True
        except Exception as exc:
            error = error or f"JSON parse failed: {exc}"
    if isinstance(parsed, dict):
        choices = parsed.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "")
        usage_obj = parsed.get("usage")
        if isinstance(usage_obj, dict):
            usage = usage_obj
    output_tokens = usage.get("completion_tokens")
    tokens_per_sec = None
    if isinstance(output_tokens, (int, float)) and elapsed > 0:
        tokens_per_sec = float(output_tokens) / elapsed
    ok = status == 200 and parse_ok and bool(content.strip())
    if not ok and not error:
        error = "empty content or non-200 response"
    return {
        "type": "bench_result",
        "timestamp": utc_now(),
        "run_id": os.environ.get("M9C_RUN_ID", "manual"),
        "case": args.case,
        "model": args.model,
        "endpoint": args.endpoint,
        "stream": False,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "prompt_chars": len(prompt),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "http_status": status,
        "ok": ok,
        "error": error,
        "elapsed_sec": round(elapsed, 3),
        "response_bytes": len(raw),
        "json_parse_ok": parse_ok,
        "usage": usage,
        "output_text_chars": len(content),
        "output_excerpt": sanitize_excerpt(content),
        "output_tokens": output_tokens,
        "output_tokens_per_sec": round(tokens_per_sec, 3) if tokens_per_sec is not None else None,
    }


def parse_stream_data(line: str) -> str:
    if not line.startswith("data:"):
        return ""
    return line[5:].strip()


def run_stream(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    body = request_payload(args, prompt)
    start = time.monotonic()
    status: int | None = None
    error = ""
    chunks = 0
    done = False
    first_chunk_sec: float | None = None
    approx_output_bytes = 0
    content_parts: list[str] = []
    try:
        with open_request(args, body) as resp:
            status = int(resp.status)
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                data = parse_stream_data(line)
                if not data:
                    continue
                if first_chunk_sec is None:
                    first_chunk_sec = time.monotonic() - start
                chunks += 1
                if data == "[DONE]":
                    done = True
                    break
                approx_output_bytes += len(data.encode("utf-8"))
                try:
                    obj = json.loads(data)
                    choices = obj.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        piece = delta.get("content")
                        if piece:
                            content_parts.append(str(piece))
                except Exception:
                    pass
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        error = f"HTTPError: {exc.code}"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - start
    content = "".join(content_parts)
    ok = status == 200 and chunks > 0 and bool(content.strip() or done)
    if not ok and not error:
        error = "stream produced no usable SSE data"
    return {
        "type": "bench_result",
        "timestamp": utc_now(),
        "run_id": os.environ.get("M9C_RUN_ID", "manual"),
        "case": args.case,
        "model": args.model,
        "endpoint": args.endpoint,
        "stream": True,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "prompt_chars": len(prompt),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "http_status": status,
        "ok": ok,
        "error": error,
        "ttft_sec": round(first_chunk_sec, 3) if first_chunk_sec is not None else None,
        "elapsed_sec": round(elapsed, 3),
        "sse_chunks": chunks,
        "completion_marker": done,
        "approx_output_bytes": approx_output_bytes,
        "output_text_chars": len(content),
        "output_excerpt": sanitize_excerpt(content),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one local OpenAI-compatible chat benchmark case.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case", default="tiny_health")
    parser.add_argument("--prompt-file")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--output-jsonl", default=DEFAULT_OUTPUT_JSONL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prompt = load_prompt(args)
    result = run_stream(args, prompt) if args.stream else run_non_stream(args, prompt)
    append_jsonl(args.output_jsonl, result)
    if args.stream:
        print(
            f"case={result['case']} ok={result['ok']} status={result['http_status']} "
            f"ttft={result.get('ttft_sec')}s elapsed={result['elapsed_sec']}s "
            f"chunks={result.get('sse_chunks')} prompt_chars={result['prompt_chars']} "
            f"output_chars={result.get('output_text_chars')}"
        )
    else:
        print(
            f"case={result['case']} ok={result['ok']} status={result['http_status']} "
            f"elapsed={result['elapsed_sec']}s prompt_chars={result['prompt_chars']} "
            f"output_chars={result.get('output_text_chars')} tokens={result.get('output_tokens')} "
            f"tok_s={result.get('output_tokens_per_sec')}"
        )
    if result.get("error"):
        print(f"error={result['error']}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
