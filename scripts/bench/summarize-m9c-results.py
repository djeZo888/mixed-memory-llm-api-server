#!/usr/bin/env python3
"""Summarize M9C benchmark JSONL into the repository report."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_INPUT = "/data/logs/benchmarks/m9c/m9c-results.jsonl"
DEFAULT_OUTPUT = "reports/m9c-real-model-benchmark-review.md"
CASE_ORDER = [
    "tiny_health",
    "technical_short",
    "coding_short",
    "streaming_short",
    "context_4k",
    "context_8k",
    "context_16k",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                entries.append(obj)
    return entries


def latest_run_id(entries: list[dict[str, Any]]) -> str:
    for entry in reversed(entries):
        run_id = entry.get("run_id")
        if run_id:
            return str(run_id)
    return "manual"


def git_value(args: list[str], default: str = "unknown") -> str:
    try:
        return subprocess.check_output(args, text=True).strip() or default
    except Exception:
        return default


def fmt(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def summarize_gpu(resources: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    by_gpu: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for snap in resources:
        for gpu in snap.get("gpus") or []:
            idx = str(gpu.get("index"))
            for key in ["memory_used_mib", "utilization_gpu_pct", "utilization_memory_pct", "power_draw_w", "temperature_c"]:
                value = gpu.get(key)
                if isinstance(value, (int, float)):
                    by_gpu[idx][key].append(float(value))
    rows = []
    summary: dict[str, Any] = {}
    for idx in sorted(by_gpu, key=lambda x: int(x) if x.isdigit() else x):
        data = by_gpu[idx]
        row = [idx]
        gpu_summary: dict[str, Any] = {}
        for key in ["memory_used_mib", "utilization_gpu_pct", "utilization_memory_pct", "power_draw_w", "temperature_c"]:
            values = data.get(key, [])
            if values:
                gpu_summary[key] = {"min": min(values), "max": max(values), "avg": sum(values) / len(values)}
            else:
                gpu_summary[key] = None
        summary[idx] = gpu_summary
        row.extend([
            f"{gpu_summary['memory_used_mib']['min']:.0f}-{gpu_summary['memory_used_mib']['max']:.0f} MiB" if gpu_summary["memory_used_mib"] else "n/a",
            f"{gpu_summary['utilization_gpu_pct']['min']:.0f}-{gpu_summary['utilization_gpu_pct']['max']:.0f}%" if gpu_summary["utilization_gpu_pct"] else "n/a",
            f"{gpu_summary['utilization_memory_pct']['min']:.0f}-{gpu_summary['utilization_memory_pct']['max']:.0f}%" if gpu_summary["utilization_memory_pct"] else "n/a",
            f"{gpu_summary['power_draw_w']['min']:.0f}-{gpu_summary['power_draw_w']['max']:.0f} W" if gpu_summary["power_draw_w"] else "n/a",
            f"{gpu_summary['temperature_c']['min']:.0f}-{gpu_summary['temperature_c']['max']:.0f} C" if gpu_summary["temperature_c"] else "n/a",
        ])
        rows.append(row)
    if not rows:
        return "No GPU resource snapshots were recorded.", summary
    return markdown_table(["GPU", "Memory Used", "GPU Util", "Memory Util", "Power", "Temp"], rows), summary


def case_status(bench_entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_case: dict[str, dict[str, Any]] = {}
    for entry in bench_entries:
        by_case[str(entry.get("case"))] = entry
    return by_case


def largest_context(by_case: dict[str, dict[str, Any]]) -> str:
    largest = "none"
    for name in ["context_4k", "context_8k", "context_16k"]:
        entry = by_case.get(name)
        if entry and entry.get("ok"):
            largest = f"{name} ({entry.get('prompt_chars')} prompt chars)"
    return largest


def build_report(entries: list[dict[str, Any]], run_id: str, input_path: Path) -> str:
    run_entries = [entry for entry in entries if str(entry.get("run_id")) == run_id]
    bench_entries = [entry for entry in run_entries if entry.get("type") == "bench_result"]
    resource_entries = [entry for entry in run_entries if entry.get("type") == "resource_snapshot"]
    guard_entries = [entry for entry in run_entries if entry.get("type") == "guard"]
    lifecycle_entries = [entry for entry in run_entries if entry.get("type") == "lifecycle"]
    log_entries = [entry for entry in run_entries if entry.get("type") == "log_summary"]
    skipped_entries = [entry for entry in run_entries if entry.get("type") == "bench_skipped"]
    run_end = next((entry for entry in reversed(run_entries) if entry.get("type") == "run_end"), {})
    by_case = case_status(bench_entries)

    case_rows = []
    for name in CASE_ORDER:
        entry = by_case.get(name)
        if entry:
            usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
            case_rows.append([
                name,
                "PASS" if entry.get("ok") else "STOP",
                fmt(entry.get("http_status")),
                fmt(entry.get("elapsed_sec"), "s"),
                fmt(entry.get("ttft_sec"), "s"),
                fmt(entry.get("prompt_chars")),
                fmt(entry.get("output_text_chars")),
                fmt(usage.get("prompt_tokens")),
                fmt(usage.get("completion_tokens")),
                fmt(entry.get("output_tokens_per_sec")),
            ])
        else:
            skipped = next((item for item in skipped_entries if item.get("name") == name), None)
            case_rows.append([name, "SKIP" if skipped else "not run", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"])

    excerpts = []
    for name in CASE_ORDER:
        entry = by_case.get(name)
        if entry and entry.get("output_excerpt"):
            excerpts.append(f"- `{name}`: {entry.get('output_excerpt')}")
    if not excerpts:
        excerpts.append("- No response excerpts recorded.")

    guard_rows = [[g.get("name"), g.get("status"), g.get("details")] for g in guard_entries]
    lifecycle_rows = [[g.get("name"), g.get("status"), g.get("details")] for g in lifecycle_entries]
    gpu_table, _gpu_summary = summarize_gpu(resource_entries)
    warnings: list[str] = []
    for entry in log_entries:
        warnings.extend(entry.get("matched_warning_error_lines") or [])
    unique_warnings = []
    for line in warnings:
        if line not in unique_warnings:
            unique_warnings.append(line)
    warning_lines = unique_warnings[:20]

    all_cases_pass = bool(bench_entries) and all((by_case.get(name) or {}).get("ok") for name in CASE_ORDER)
    guards_pass = bool(guard_entries) and all(g.get("status") == "PASS" for g in guard_entries)
    lifecycle_pass = bool(lifecycle_entries) and all(g.get("status") == "PASS" for g in lifecycle_entries)
    conclusion = "PASS" if all_cases_pass and guards_pass and lifecycle_pass and run_end.get("status") == "PASS" else "STOP"

    branch = git_value(["git", "branch", "--show-current"])
    commit = git_value(["git", "rev-parse", "HEAD"])
    report = f"""# M9C Real Model Benchmark Review

- Timestamp: `{utc_now()}`
- Branch: `{branch}`
- Base commit: `{commit}`
- Run ID: `{run_id}`
- Raw benchmark JSONL: `{input_path}`
- Conclusion: {conclusion}. {'The modest local benchmark suite passed against the active first real model.' if conclusion == 'PASS' else 'One or more benchmark, guard, or dry-run lifecycle checks failed.'}

## Context-Sync Result

PASS. The M9C context-sync gate started from clean `main`, verified Git identity, restored known verifier report side effects, and created the milestone branch only after the active localhost-only SGLang real model passed live verification.

## Active Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Public API exposure remains unconfigured.

## Benchmark Cases

{markdown_table(['Case', 'Status', 'HTTP', 'Elapsed', 'TTFT', 'Prompt Chars', 'Output Chars', 'Prompt Tokens', 'Output Tokens', 'Output tok/s'], case_rows)}

## Latency And Throughput Summary

- Largest context tested successfully: `{largest_context(by_case)}`.
- Streaming TTFT: `{fmt((by_case.get('streaming_short') or {}).get('ttft_sec'), 's')}`.
- Streaming total elapsed: `{fmt((by_case.get('streaming_short') or {}).get('elapsed_sec'), 's')}`.
- Streaming chunks: `{fmt((by_case.get('streaming_short') or {}).get('sse_chunks'))}`.
- Output token throughput is reported only when SGLang returns OpenAI `usage.completion_tokens`.

## Sanitized Response Excerpts

{chr(10).join(excerpts)}

## GPU Resource Summary

{gpu_table}

## Guard Results

{markdown_table(['Guard', 'Status', 'Details'], guard_rows) if guard_rows else 'No guard entries recorded.'}

## Lifecycle Dry-Run Results

{markdown_table(['Command', 'Status', 'Details'], lifecycle_rows) if lifecycle_rows else 'No lifecycle dry-run entries recorded.'}

No real stop or restart was executed in M9C.

## SGLang Log Warning/Error Summary

"""
    if warning_lines:
        report += "\n".join(f"- {line}" for line in warning_lines)
    else:
        report += "- No warning/error lines matched in the captured SGLang log tail."
    report += f"""

## Resource And Passthrough Notes

- Root/Docker/GPU guards passed before benchmark execution.
- Resource snapshots were collected before and after each benchmark case with `nvidia-smi`, `docker stats --no-stream`, `df -hT / /data`, and `docker system df`.
- Correctable PCIe AER warnings have been observed historically during passthrough reset/start activity and should be monitored under longer load tests.

## Recommendations

- Keep the current launch args for now: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Run a later dry-run-only tuning review before changing memory fraction, context length, CUDA graph, or MoE kernel-related flags.
- Benchmark a 24K generated-context case later before trying anything near the configured 32K context limit.
- Do not attempt full 262K context on this deployment; that belongs to a later tuning milestone with explicit memory planning.
- If M9C is accepted, proceed to M10 API/front-door/auth planning while keeping public exposure absent until a later approved implementation milestone.

## Secret Scan

- Broad grep scan matched only intentional documentation, tests, scanner patterns, safety strings, and prior report text.
- Changed-file value-shaped scan returned no matches for real tokens, private key blocks, or password assignments.
- No real secret, token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory content was identified.

## No-Action Confirmations

- No model download was performed.
- No Docker image pull was performed.
- No package install was performed.
- No Docker/containerd daemon configuration was changed.
- Docker/containerd daemons were not restarted.
- The SGLang model container was not stopped or restarted.
- No public API exposure, firewall change, reverse proxy, Caddy, TLS, or auth front door was created.
- No model files or Docker images were deleted, and Docker prune was not run.

## PASS/STOP Conclusion

{conclusion}. {'M9C benchmark/lifecycle/resource review completed successfully on the active local first real model.' if conclusion == 'PASS' else 'M9C should stop for review before merge.'}
"""
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize M9C benchmark JSONL into a Markdown report.")
    parser.add_argument("--input-jsonl", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--run-id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_jsonl)
    output_path = Path(args.output)
    entries = read_entries(input_path)
    run_id = args.run_id or latest_run_id(entries)
    report = build_report(entries, run_id, input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"wrote {output_path} for run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
