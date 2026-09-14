#!/usr/bin/env python3
"""Bounded client-side Chat Completions acceptance; never installs server software."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

if __package__:
    from .protocol import AgentError, APIError, Budget, Client, load_api_key, redact
    from .fixture import Fixture
else:
    from protocol import AgentError, APIError, Budget, Client, load_api_key, redact
    from fixture import Fixture


PROMPT = """Fix the bug in this fresh disposable Python fixture using native tools.
First read both calc.py and test_calc.py with read_file. The add(a,b) function must
return the sum; inspect the actual tests. Use write_file to change calc.py, then
request run_tests and inspect its real result. Tests are immutable. calc.py must
contain exactly def add(a, b): returning an arithmetic expression; no imports,
calls, attributes, decorators, or other statements. run_tests takes {} and runs a
fixed command. Only read calls may be batched; send write_file and run_tests each
in a separate response. After the tool reports passing tests, give a short final
answer. Claims without actual reads, an implementation edit, and passing tool-run
tests do not pass acceptance. Never put tool calls in reasoning or prose.
"""


def run_agent(client, report, *, max_rounds, max_tool_calls, workspace_parent,
              max_output_bytes, test_timeout, stream_tools):
    """Record failures as evidence, including partially completed fixture work."""
    run = report["agent"] = {"status": "FAIL", "rounds": [], "evidence": {}}
    started = time.monotonic()
    fixture = None
    try:
        with Fixture(parent=workspace_parent, budget=client.budget,
                     max_output_bytes=max_output_bytes,
                     test_timeout=test_timeout) as fixture:
            messages = [{"role": "system", "content": "You are a bounded coding assistant. Use the supplied native tools."},
                        {"role": "user", "content": PROMPT}]
            count = 0
            for round_number in range(1, max_rounds + 1):
                client.budget.check()
                response = client.chat(messages, tools=fixture.schemas, stream=stream_tools)
                message = response["message"]
                run["rounds"].append({"round": round_number, **response})
                require_model_identity(client, response)
                messages.append(message)
                calls = message.get("tool_calls") or []
                if calls:
                    count += len(calls)
                    if count > max_tool_calls:
                        raise AgentError("Tool-call budget exhausted; increase --max-tool-calls only after reviewing evidence")
                    messages.extend(fixture.execute_calls(calls))
                    continue
                if response["finish_reason"] != "stop" or not (message.get("content") or "").strip():
                    raise AgentError("Agent did not produce a final content answer with stop termination")
                fixture.verify_success()
                run["final_answer"] = message["content"]
                run["status"] = "PASS"
                break
            else:
                raise AgentError("Round budget exhausted before verified final answer")
            run["evidence"] = fixture.evidence()
    except (AgentError, OSError, ValueError) as exc:
        run["status"] = "FAIL"
        run["error"] = safe_error(exc)
        if fixture is not None:
            # Evidence is captured before cleanup when possible (Fixture retains it).
            run["evidence"] = fixture.evidence()
    run["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return run["status"] == "PASS"


def safe_error(exc):
    # Low-level exception text may contain URLs, headers, or unexpected server data.
    if isinstance(exc, AgentError):
        return str(exc)
    return "Local operation failed (" + type(exc).__name__ + ")"


def require_model_identity(client, response):
    if response["model"] != client.model:
        raise AgentError("Returned model differs from requested model; inspect recorded identities and obtain the exact published API alias")


def redact_report(value, key):
    """Mask data without rewriting trusted report field names or outcome enums.

    Only usage and reasoning contain arbitrary provider-supplied mapping keys.
    Tool schemas and protocol messages have already been strictly validated.
    Internal executable messages are never passed through this transformation.
    """
    if isinstance(value, dict):
        result = {}
        for name, item in value.items():
            if name == "status" and isinstance(item, str) and item in {"PASS", "FAIL", "NOT_TESTED"}:
                result[name] = item
            elif name in {"usage", "reasoning"}:
                result[name] = redact(item, key)
            else:
                result[name] = redact_report(item, key)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_report(item, key) for item in value]
    return redact(value, key)


def run_acceptance(client, *, auth="disabled", max_rounds=12, max_tool_calls=32,
                   workspace_parent=None, max_output_bytes=16384,
                   test_timeout=10, stream_tools=False, evidence_kind="live"):
    started = time.monotonic()
    report = {
        "schema_version": 1, "evidence_kind": evidence_kind,
        "status": "FAIL", "requested_model": client.model,
        "base_url": client.base_url, "auth": auth,
        "limits": {"max_rounds": max_rounds, "max_tool_calls": max_tool_calls,
                   "max_output_bytes": max_output_bytes, "test_timeout": test_timeout,
                   "request_timeout": client.request_timeout,
                   "overall_timeout": client.budget.overall_timeout,
                   "max_tokens": client.max_tokens,
                   "max_response_bytes": client.max_response_bytes,
                   "stream_tools": stream_tools},
        "checks": {}, "opencode_e2e": "NOT_TESTED", "clean_linux_install": "NOT_TESTED",
    }

    def check(name, action):
        before = time.monotonic()
        try:
            client.budget.check()
            detail = action()
            report["checks"][name] = {"status": "PASS", "detail": detail}
        except (AgentError, OSError, ValueError) as exc:
            report["checks"][name] = {"status": "FAIL", "error": safe_error(exc)}
        report["checks"][name]["elapsed_seconds"] = round(time.monotonic() - before, 6)

    def models():
        result = client.models()
        ids = [entry["id"] for entry in result["data"]]
        if client.model not in ids:
            raise AgentError("Requested model absent from /models; use the published model ID")
        return {"available_model_ids": ids}

    def chat(stream=False):
        result = client.chat([{"role": "user", "content": "Reply with one short greeting."}], stream=stream)
        require_model_identity(client, result)
        if result["message"].get("tool_calls") or not (result["message"].get("content") or "").strip():
            raise AgentError("Chat probe returned no content-only answer")
        if result["finish_reason"] != "stop":
            raise AgentError("Chat probe did not terminate with stop")
        return result

    check("models", models)
    check("chat", chat)
    check("streaming_end", lambda: chat(True))

    def invalid_model():
        invalid = "__a1_invalid_model_" + uuid.uuid4().hex
        try:
            result = client.chat([{"role": "user", "content": "Reply briefly."}], model=invalid)
        except APIError as exc:
            if exc.status in (400, 404, 422):
                return {"rejected_http_status": exc.status}
            raise AgentError("Invalid model returned unrelated HTTP status " + str(exc.status)) from None
        raise AgentError("Invalid model was accepted; backend returned model " + result["model"])

    check("invalid_model", invalid_model)
    if auth == "enabled":
        def rejected(key, route):
            try:
                if route == "models":
                    client.models(api_key=key)
                else:
                    client.chat([{"role": "user", "content": "Reply briefly."}], api_key=key)
            except APIError as exc:
                if exc.status in (401, 403):
                    return {"rejected_http_status": exc.status}
                raise AgentError("Auth rejection had unexpected HTTP status " + str(exc.status)) from None
            raise AgentError("Unauthenticated or wrong-key request was accepted")

        for label, key in (("missing", None), ("wrong", "a1-intentionally-invalid-" + uuid.uuid4().hex)):
            for route in ("models", "chat"):
                check("auth_" + label + "_" + route, lambda key=key, route=route: rejected(key, route))
        # These fresh requests use the actual configured credential.
        check("auth_correct_models", models)
        check("auth_correct_chat", chat)
    else:
        report["checks"]["auth"] = {"status": "NOT_TESTED", "detail": "Auth disabled by operator for localhost SSH tunnel; enforcement not tested"}

    run_agent(client, report, max_rounds=max_rounds, max_tool_calls=max_tool_calls,
              workspace_parent=workspace_parent, max_output_bytes=max_output_bytes,
              test_timeout=test_timeout, stream_tools=stream_tools)
    report["checks"]["tool_roundtrip"] = {"status": report["agent"]["status"],
                                          "detail": "See actual fixture calls, test results and independent verification in agent.evidence"}
    report["requests"] = client.requests
    report["elapsed_seconds"] = round(time.monotonic() - started, 6)
    statuses = [item["status"] for item in report["checks"].values()]
    report["status"] = "PASS" if "FAIL" not in statuses else "FAIL"
    return redact_report(report, client.api_key)


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 86400:
        raise argparse.ArgumentTypeError("must be finite, positive and at most 86400")
    return number


def bounded_int(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number
    return parse


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:30002/v1")
    p.add_argument("--model", required=True, help="Exact model ID published by the runtime owner")
    p.add_argument("--report", type=Path, required=True, help="New JSON report file; never overwrites")
    keys = p.add_mutually_exclusive_group()
    keys.add_argument("--api-key-file", type=Path, help="Owned regular file, permissions 0600 or stricter")
    keys.add_argument("--api-key-env", help="Name of environment variable containing API key")
    p.add_argument("--auth", choices=("enabled", "disabled"), default="disabled")
    p.add_argument("--request-timeout", type=positive_number, default=120)
    p.add_argument("--overall-timeout", type=positive_number, default=900)
    p.add_argument("--test-timeout", type=positive_number, default=10)
    p.add_argument("--max-rounds", type=bounded_int(1, 64), default=12)
    p.add_argument("--max-tool-calls", type=bounded_int(1, 128), default=32)
    p.add_argument("--max-tokens", type=bounded_int(1, 32768), default=2048)
    p.add_argument("--max-output-bytes", type=bounded_int(1024, 1048576), default=16384)
    p.add_argument("--max-response-bytes", type=bounded_int(1024, 4194304), default=262144)
    p.add_argument("--workspace-parent", type=Path, help="Existing worker temp directory; a fresh child is always created")
    p.add_argument("--stream-tools", action="store_true", help="Also stream native agent tool rounds")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    key = None
    try:
        key = load_api_key(args.api_key_file, args.api_key_env)
        if args.auth == "enabled" and not key:
            raise AgentError("--auth enabled requires --api-key-file or --api-key-env")
        client = Client(args.base_url, args.model, api_key=key,
                        request_timeout=args.request_timeout,
                        budget=Budget(args.overall_timeout),
                        max_response_bytes=args.max_response_bytes, max_tokens=args.max_tokens)
        # Reserve report before inference so path failures do not waste model work.
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            result = run_acceptance(client, auth=args.auth, max_rounds=args.max_rounds,
                                    max_tool_calls=args.max_tool_calls,
                                    workspace_parent=args.workspace_parent,
                                    max_output_bytes=args.max_output_bytes,
                                    test_timeout=args.test_timeout, stream_tools=args.stream_tools)
            json.dump(result, stream, indent=2, ensure_ascii=True, allow_nan=False)
            stream.write("\n")
        print("A1 acceptance: " + result["status"] + "; report written (OpenCode E2E: NOT_TESTED)")
        return 0 if result["status"] == "PASS" else 1
    except (AgentError, OSError, ValueError) as exc:
        print("A1 acceptance: FAIL; " + redact(safe_error(exc), key), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
