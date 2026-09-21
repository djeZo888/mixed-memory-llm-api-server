#!/usr/bin/env python3
"""Publish an allowlisted V1G summary of a private A1 acceptance report.

Verification commands (use synthetic inputs for development):
  python3 -B scripts/validation/v1g/summarize_a1.py --help
  python3 -B scripts/validation/v1g/summarize_a1.py --report PRIVATE/report.json \
      --api-key-file PRIVATE/key --output NEW-summary.json

The output must not exist. The key is read only from an owned, single-link,
regular file with mode 0600 or stricter. No network access occurs. Before writing,
the entire serialized candidate is scanned for the exact key and JSON-escaped
forms. A match fails closed and prints only the destination filename. Missing
usage is NOT_REPORTED; usage is listed once per request and is never totaled.
Text lengths describe decoded strings in the A1 report, after A1 redaction;
they are not raw wire lengths. Bodies, reasoning text, arguments and provider
error strings are never copied to the summary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys


MISSING = "NOT_REPORTED"
MODEL = "glm-5.3"
TOOLS = {"read_file", "write_file", "run_tests"}
CHECKS = ("models", "chat", "streaming_end", "invalid_model",
          "auth_missing_models", "auth_missing_chat", "auth_wrong_models",
          "auth_wrong_chat", "auth_correct_models", "auth_correct_chat",
          "tool_roundtrip")
EXPECTED_INITIAL_HASH = hashlib.sha256(
    b"def add(a, b):\n    return a - b\n").hexdigest()


def mapping(value):
    return value if isinstance(value, dict) else {}


def sequence(value):
    return value if isinstance(value, list) else []


def integer(value):
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else MISSING


def seconds(value):
    return value if type(value) in {float, int} and math.isfinite(value) and value >= 0 else MISSING


def boolean(value):
    return value if type(value) is bool else MISSING


def status(value):
    return value if isinstance(value, str) and value in {"PASS", "FAIL", "NOT_TESTED"} else MISSING


def digest(value):
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else MISSING


def identity(value):
    if value == MODEL:
        return MODEL
    if isinstance(value, str) and re.fullmatch(r"__a1_invalid_model_[0-9a-f]{32}", value):
        return "INVALID_MODEL_PROBE"
    return MISSING if value is None else "OTHER_MODEL_ID_OMITTED"


def finish(value):
    return value if isinstance(value, str) and value in {"stop", "tool_calls", "length"} else MISSING


def http_status(value):
    return value if type(value) is int and 100 <= value <= 599 else MISSING


def usage(value):
    value = mapping(value)
    result = {name: integer(value.get(name)) for name in
              ("prompt_tokens", "completion_tokens", "total_tokens")}
    for group, fields in (
        ("prompt_tokens_details", ("cached_tokens", "audio_tokens")),
        ("completion_tokens_details", ("reasoning_tokens", "audio_tokens",
                                      "accepted_prediction_tokens", "rejected_prediction_tokens")),
    ):
        group_value = mapping(value.get(group))
        result[group] = {name: integer(group_value.get(name)) for name in fields}
    return result


def text_lengths(value):
    if not isinstance(value, str):
        return {"characters": MISSING, "utf8_bytes": MISSING}
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        size = MISSING
    return {"characters": len(value), "utf8_bytes": size}


def reasoning_lengths(value):
    # Count string values only; never publish arbitrary provider field names.
    strings = []

    def collect(item):
        if isinstance(item, str):
            strings.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    if not strings:
        return {"string_values": 0, "characters": MISSING, "utf8_bytes": MISSING}
    result = text_lengths("".join(strings))
    return {"string_values": len(strings), **result}


def failure_category(value):
    value = mapping(value)
    diagnostic = mapping(value.get("diagnostics"))
    if value.get("classification") == "token_budget_exhausted" or diagnostic.get("classification") == "token_budget_exhausted":
        return "TOKEN_BUDGET_EXHAUSTED"
    error = value.get("error")
    if not isinstance(error, str):
        return "NONE" if value.get("status") == "PASS" else MISSING
    error = error.lower()
    if "token_budget_exhausted" in error:
        return "TOKEN_BUDGET_EXHAUSTED"
    if any(term in error for term in ("timed out", "timeout", "time budget", "overall time")):
        return "TIMEOUT"
    if any(term in error for term in ("model differs", "model absent", "invalid model")):
        return "model_identity_contract"
    if any(term in error for term in ("unauthenticated", "wrong-key", "auth rejection")):
        return "AUTHENTICATION"
    if "api returned http" in error or "api transport failed" in error:
        return "HTTP_OR_TRANSPORT"
    if any(term in error for term in ("fixture", "tool", "arithmetic", "calc.py", "run_tests", "round budget")):
        return "FIXTURE_OR_TOOL_CONTRACT"
    if "local operation failed" in error:
        return "LOCAL_OPERATION"
    return "PROTOCOL_OR_ACCEPTANCE"


def diagnostic(value):
    value = mapping(value)
    if value.get("classification") != "token_budget_exhausted":
        return MISSING
    return {"classification": "token_budget_exhausted",
            "finish_reason": finish(value.get("finish_reason")),
            "model": identity(value.get("model")),
            "stream_done": boolean(value.get("stream_done")),
            "parsing_failure": ("invalid_assistant_message" if value.get("parsing_failure") == "invalid_assistant_message" else MISSING)}


def test_summary(value, *, initial=False):
    value = mapping(value)
    inferred_status = "PASS" if value.get("passed") is True else "FAIL" if value.get("passed") is False else "NOT_TESTED"
    result = {"status": status(value.get("status", inferred_status)), "passed": boolean(value.get("passed")),
              "exit_code": (value.get("exit_code") if type(value.get("exit_code")) is int else MISSING),
              "elapsed_seconds": seconds(value.get("elapsed_seconds")),
              "command": (["python3", "-I", "-B", "test_calc.py"] if value.get("command") == ["python3", "-I", "-B", "test_calc.py"] else MISSING),
              "implementation_sha256": digest(value.get("implementation_sha256")),
              "tests_sha256": digest(value.get("tests_sha256")),
              "output_lengths": text_lengths(value.get("output"))}
    if initial:
        output = value.get("output")
        classification = MISSING
        if isinstance(output, str):
            if "ImportError" in output or "ModuleNotFoundError" in output:
                classification = "IMPORT_FAILURE"
            elif "AssertionError" in output and value.get("exit_code") != 0:
                classification = "ASSERTION_FAILURE_OBSERVED"
            elif value.get("exit_code") == 0:
                classification = "UNEXPECTED_PASS"
            else:
                classification = "OTHER_FAILURE"
        result["failure_classification"] = classification
        result["assertion_error_occurrences"] = output.count("AssertionError") if isinstance(output, str) else MISSING
        result["expected_initial_source_hash_matches"] = (value.get("implementation_sha256") == EXPECTED_INITIAL_HASH
                                                          if digest(value.get("implementation_sha256")) != MISSING else MISSING)
    return result


def summarize(report):
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("unsupported report")
    limits = mapping(report.get("limits"))
    checks = mapping(report.get("checks"))
    agent = mapping(report.get("agent"))
    evidence = mapping(agent.get("evidence"))
    result = {
        "schema_version": 1, "source_schema": "A1_ACCEPTANCE_SCHEMA_1",
        "evidence_kind": (report.get("evidence_kind") if report.get("evidence_kind") in {"live", "synthetic"} else MISSING),
        "requested_model": identity(report.get("requested_model")),
        "status": status(report.get("status")),
        "elapsed_seconds": seconds(report.get("elapsed_seconds")),
        "text_length_basis": "DECODED_A1_REPORT_STRINGS_AFTER_A1_REDACTION_NOT_RAW_WIRE",
        "usage_accounting": "PER_REQUEST_ONLY_NO_TOTALS; MISSING_COUNTERS_ARE_NOT_REPORTED",
        "opencode_e2e": status(report.get("opencode_e2e", "NOT_TESTED")),
        "clean_linux_install": status(report.get("clean_linux_install", "NOT_TESTED")),
        "limits": {name: integer(limits.get(name)) for name in
                   ("max_rounds", "max_tool_calls", "max_tokens", "max_output_bytes", "max_response_bytes")},
        "checks": {}, "requests": [], "agent": {"status": status(agent.get("status", "NOT_TESTED")),
        "elapsed_seconds": seconds(agent.get("elapsed_seconds")),
        "failure_category": failure_category(agent), "diagnostics": diagnostic(agent.get("diagnostics")),
        "final_answer_lengths": text_lengths(agent.get("final_answer")), "rounds": [], "tools": []},
    }
    result["limits"].update({name: seconds(limits.get(name)) for name in ("request_timeout", "overall_timeout", "test_timeout")})
    result["limits"].update({"reasoning_effort": "low" if limits.get("reasoning_effort") == "low" else MISSING,
                              "stream_tools": boolean(limits.get("stream_tools"))})
    for name in CHECKS:
        item = mapping(checks.get(name))
        detail = mapping(item.get("detail"))
        message = mapping(detail.get("message"))
        result["checks"][name] = {"status": status(item.get("status", "NOT_TESTED")),
            "elapsed_seconds": seconds(item.get("elapsed_seconds")),
            "rejected_http_status": http_status(detail.get("rejected_http_status")),
            "returned_model": identity(detail.get("model")),
            "finish_reason": finish(detail.get("finish_reason")),
            "stream_done": boolean(detail.get("stream_done")),
            "content_lengths": text_lengths(message.get("content")),
            "reasoning_lengths": reasoning_lengths(detail.get("reasoning")),
            "failure_category": failure_category(item), "diagnostics": diagnostic(item.get("diagnostics"))}
    for index, raw in enumerate(sequence(report.get("requests")), 1):
        item = mapping(raw)
        result["requests"].append({"sequence": index,
            "path": item.get("path") if item.get("path") in {"/models", "/chat/completions"} else MISSING,
            "stream": boolean(item.get("stream")), "http_status": http_status(item.get("status")),
            "request_success": boolean(item.get("success")),
            "requested_model": identity(item.get("requested_model")), "returned_model": identity(item.get("model")),
            "finish_reason": finish(item.get("finish_reason")), "usage": usage(item.get("usage")),
            "elapsed_seconds": seconds(item.get("elapsed_seconds")), "diagnostics": diagnostic(item)})
    for raw in sequence(agent.get("rounds")):
        item = mapping(raw)
        message = mapping(item.get("message"))
        result["agent"]["rounds"].append({"round": integer(item.get("round")),
            "returned_model": identity(item.get("model")), "finish_reason": finish(item.get("finish_reason")),
            "stream_done": boolean(item.get("stream_done")), "elapsed_seconds": seconds(item.get("elapsed_seconds")),
            "requested_tool_call_count": len(sequence(message.get("tool_calls"))),
            "content_lengths": text_lengths(message.get("content")),
            "reasoning_lengths": reasoning_lengths(item.get("reasoning"))})
    counts = Counter()
    for index, raw in enumerate(sequence(evidence.get("calls")), 1):
        item = mapping(raw)
        tool_result = mapping(item.get("result"))
        name = item.get("name") if item.get("name") in TOOLS else "UNKNOWN_TOOL_OMITTED"
        counts[name] += 1
        ident = item.get("id")
        event = {"sequence": index, "name": name,
            "id": ident if isinstance(ident, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", ident) else MISSING,
            "result_recorded": "result" in item, "error_recorded": "error" in item,
            "elapsed_seconds": seconds(item.get("elapsed_seconds")),
            "version_before": integer(item.get("version_before")), "version_after": integer(item.get("version_after")),
            "implementation_before_sha256": digest(item.get("implementation_before_sha256")),
            "implementation_after_sha256": digest(item.get("implementation_after_sha256"))}
        if name == "read_file":
            path = tool_result.get("path")
            event["result_path"] = path if path in {"calc.py", "test_calc.py"} else MISSING
            event["result_content_lengths"] = text_lengths(tool_result.get("content"))
        elif name == "write_file":
            event["written_bytes"] = integer(tool_result.get("written_bytes"))
        elif name == "run_tests":
            event["test"] = test_summary(tool_result)
        result["agent"]["tools"].append(event)
    result["agent"]["tool_counts"] = dict(sorted(counts.items()))
    result["agent"]["model_tool_rounds_observed"] = len(result["agent"]["rounds"])
    result["agent"]["tool_calls_observed"] = len(result["agent"]["tools"])
    result["agent"]["tool_result_count"] = sum("result" in mapping(item) for item in sequence(evidence.get("calls")))
    result["agent"]["evidence"] = {
        "initial_test": test_summary(evidence.get("initial_test"), initial=True),
        "final_test": test_summary(evidence.get("final_test")),
        "implementation_changed": boolean(evidence.get("implementation_changed")),
        "implementation_sha256": digest(evidence.get("implementation_sha256")),
        "tests_unchanged": boolean(evidence.get("tests_unchanged")),
        "tests_sha256": digest(evidence.get("tests_sha256")),
        "expected_tests_sha256": digest(evidence.get("expected_tests_sha256")),
        "success": boolean(evidence.get("success")), "diff_lengths": text_lengths(evidence.get("diff")),
    }
    return result


def protected_key(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o077 or not 0 < info.st_size <= 8192:
            raise ValueError("invalid key file")
        key = os.read(fd, 8193)
        if not key or len(key) > 8192 or any(char < 33 or char > 126 for char in key):
            raise ValueError("invalid key")
        return key
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", type=Path, required=True, help="Private A1 JSON report")
    parser.add_argument("--api-key-file", type=Path, required=True, help="Existing protected actual key file; never printed")
    parser.add_argument("--output", type=Path, required=True, help="New allowlisted JSON file; never overwrites")
    args = parser.parse_args(argv)
    try:
        key = protected_key(args.api_key_file)
        with args.report.open("rb") as source:
            raw = source.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("report too large")
        report = json.loads(raw)
        candidate = (json.dumps(summarize(report), indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
        variants = {key}
        escaped = key.decode("ascii")
        for _ in range(3):
            escaped = json.dumps(escaped, ensure_ascii=True)[1:-1]
            variants.add(escaped.encode("ascii"))
        if any(variant in candidate for variant in variants):
            print(args.output.name, file=sys.stderr)
            return 1
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as target:
            target.write(candidate)
        print("A1 sanitized summary written")
        return 0
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        print("A1 summary failed; no report content printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
