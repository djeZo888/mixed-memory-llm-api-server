"""Concrete D3T worker accounting via installed non-generation native routes.

POST the exact frozen chat body to /apply-template, then tokenize the native
render with the same add_special/parse_special flags as the installed chat path.
Credentials remain inside the protected remote process. Token arrays and request
content returned by these helpers are PRIVATE worker checkpoint data.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import protocol as a1
from agent.fixture import Fixture, INITIAL_SOURCE

Error = a1.AgentError
RESERVE = 8192
NATIVE_CONTEXT = 1048576
OCCUPANCY_TOLERANCE = 256
READ_TOOL = Fixture.schemas[0]


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Error("value is not canonical UTF-8 JSON") from None


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def wire_body(body):
    """Return (bytes, sha256); transport must send these exact bytes unchanged."""
    required = {"model", "messages", "stream", "max_tokens", "temperature", "reasoning_effort"}
    optional = {"tools", "tool_choice", "stream_options"}
    if not isinstance(body, dict) or not required <= body.keys() or body.keys() - required - optional:
        raise Error("request fields differ from bounded D3T chat contract")
    if body["model"] != "glm-5.3" or body["reasoning_effort"] != "low":
        raise Error("D3T requires glm-5.3 and explicit reasoning_effort low")
    if type(body["stream"]) is not bool or type(body["max_tokens"]) is not int or not 1 <= body["max_tokens"] <= RESERVE:
        raise Error("invalid stream or bounded output cap")
    if type(body["temperature"]) not in (int, float) or body["temperature"] != 0:
        raise Error("matched D3T probes require temperature zero")
    a1._validate_messages(body["messages"])
    for message in body["messages"]:
        allowed = {"role", "content"}
        if message["role"] == "assistant":
            allowed.add("tool_calls")
        if message["role"] == "tool":
            allowed.add("tool_call_id")
        if message.keys() - allowed:
            raise Error("request messages contain unsupported or replayed reasoning fields")
    if "tools" in body and body["tools"] != [READ_TOOL]:
        raise Error("only the reviewed A1 read_file schema is allowed")
    if "tool_choice" in body:
        choice = body["tool_choice"]
        if "tools" not in body or choice not in ("auto", "none"):
            raise Error("unsupported tool choice")
    if "stream_options" in body and (not body["stream"] or body["stream_options"] != {"include_usage": True}):
        raise Error("only streaming include_usage is allowed")
    data = canonical(body)
    if len(data) > 64 * 1024 * 1024:
        raise Error("request exceeds 64 MiB source contract")
    return data, sha256(data)


# This code runs only on the task's existing VM, over SSH stdin. It does not
# create remote files, a shell transport/tunnel, service or authorization system.
_NATIVE_HTTP = r'''
import http.client,json,os,signal,stat,subprocess,sys
signal.alarm(50)
def fail():
    print('{"d3t_error":"native accounting route failed"}')
    sys.exit(1)
def run(path,payload,container_id,image_id):
    if path not in ("/props","/apply-template","/tokenize"): fail()
    def identity():
        for mount,uuid in (("/data","8daf56f1-5649-4163-9d87-919c2d271875"),("/data/models-large","a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a")):
            actual=subprocess.check_output(["findmnt","-rn","-o","TARGET,UUID,FSTYPE","-M",mount],text=True).split()
            if actual != [mount,uuid,"ext4"]: fail()
        root=os.statvfs("/")
        if root.f_bavail*root.f_frsize < 4*1024**3: fail()
        info=json.loads(subprocess.check_output(["docker","inspect",container_id]))[0]
        if info["Id"] != container_id or info["Image"] != image_id or not info["State"]["Running"] or info["State"]["OOMKilled"]: fail()
        ports=info["HostConfig"].get("PortBindings",{})
        if ports.get("30002/tcp") != [{"HostIp":"127.0.0.1","HostPort":"30002"}]: fail()
        return info["State"]["Pid"],info["State"]["StartedAt"]
    before=identity()
    fd=os.open("/data/services/secrets/llm-api-key",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077 or info.st_nlink != 1 or not 0 < info.st_size <= 8192: fail()
        key=os.read(fd,8193).decode("ascii")
    finally: os.close(fd)
    if not key or not all(33 <= ord(c) <= 126 for c in key): fail()
    body=None if payload is None else json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    if body is not None and len(body)>64*1024*1024: fail()
    connection=http.client.HTTPConnection("127.0.0.1",30002,timeout=40)
    try:
        connection.request("GET" if payload is None else "POST",path,body=body,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","Accept-Encoding":"identity"})
        response=connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type","").split(";")[0] != "application/json" or response.getheader("Content-Encoding","identity") != "identity": fail()
        data=response.read(64*1024*1024+1)
        if len(data)>64*1024*1024 or key.encode() in data: fail()
    finally: connection.close()
    if identity()!=before: fail()
    sys.stdout.buffer.write(data)
try:
    run(*REQUEST)
except Exception:
    fail()
'''


def _native_http(path, payload, container_id, image_id):
    if path not in ("/props", "/apply-template", "/tokenize") or (path == "/props") != (payload is None):
        raise Error("only the installed non-generation accounting routes are allowed")
    if not isinstance(container_id, str) or not isinstance(image_id, str) or re.fullmatch(r"[0-9a-f]{64}", container_id) is None or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise Error("native accounting requires exact existing container and image IDs")
    # The exact request and program are stdin, never process arguments or files.
    request = (path, payload, container_id, image_id)
    program = "REQUEST = " + repr(request) + "\n" + _NATIVE_HTTP
    try:
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                 "ai-vm", "sudo -n python3 -"], input=program.encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        raise Error("bounded native accounting SSH operation failed") from None
    if result.returncode != 0 or len(result.stdout) > 64 * 1024 * 1024:
        raise Error("native accounting route or identity/storage check failed")
    return a1.strict_json_loads(result.stdout)


def account(body, native_http):
    """Account with an actual native route callable (path, JSON-or-None)->JSON.

    /props verifies the actual loaded template and slot capacity. /apply-template
    receives all exact outgoing body fields; /tokenize uses generation's true,
    true special-token semantics, never endpoint defaults or a local estimate.
    """
    _, body_hash = wire_body(body)
    props = native_http("/props", None)
    if not isinstance(props, dict) or props.get("model_alias") != body["model"] or props.get("is_sleeping") is not False or props.get("total_slots") != 1:
        raise Error("native properties differ from active one-slot GLM contract")
    template = props.get("chat_template_tool_use", props.get("chat_template")) if "tools" in body else props.get("chat_template")
    if not isinstance(template, str) or not template:
        raise Error("native loaded chat template is missing")
    configured = props.get("default_generation_settings", {}).get("n_ctx")
    if type(configured) is not int or configured not in (32768, NATIVE_CONTEXT):
        raise Error("native configured capacity is outside 32K/native-only plan")
    rendered = native_http("/apply-template", body)
    if not isinstance(rendered, dict) or set(rendered) != {"prompt"} or not isinstance(rendered["prompt"], str):
        raise Error("native template returned an invalid text prompt")
    prompt = rendered["prompt"]
    tokenized = native_http("/tokenize", {"content": prompt, "add_special": True,
                                         "parse_special": True, "with_pieces": False})
    tokens = tokenized.get("tokens") if isinstance(tokenized, dict) else None
    if not isinstance(tokens, list) or not 1 <= len(tokens) <= 4 * NATIVE_CONTEXT or any(type(token) is not int or not 0 <= token <= 2**31 - 1 for token in tokens):
        raise Error("native tokenizer returned invalid or oversized token IDs")
    return {"input_tokens": len(tokens), "token_ids": tokens,
            "tokens_sha256": sha256(canonical(tokens)), "body_sha256": body_hash,
            "rendered_prompt_sha256": sha256(prompt.encode("utf-8")),
            "template_sha256": sha256(template.encode("utf-8")),
            "configured_context": configured, "add_special": True, "parse_special": True}


def native_account(body, container_id, image_id):
    """Concrete bounded worker SSH adapter; only native non-generation routes."""
    result = account(body, lambda path, payload: _native_http(path, payload, container_id, image_id))
    result.update({"container_id": container_id, "image_id": image_id})
    return result


def common_prefix(previous, current):
    """Exact token-prefix length; caller still needs exposed backend cached count."""
    result = 0
    for left, right in zip(previous, current):
        if left != right:
            break
        result += 1
    return result


def check_occupancy(accounting, body, target=None, *, initial=True):
    """Check real count, stage occupancy and the 8192-token continuation reserve."""
    _, digest = wire_body(body)
    if not isinstance(accounting.get("token_ids"), list) or accounting.get("body_sha256") != digest or accounting.get("tokens_sha256") != sha256(canonical(accounting.get("token_ids"))):
        raise Error("native accounting is not bound to current body/token checkpoint")
    count = accounting.get("input_tokens")
    if type(count) is not int or count != len(accounting["token_ids"]):
        raise Error("native count disagrees with actual tokens")
    if target is not None and (type(target) is not int or target not in (32768, 65536, 131072, 262144, 524288, NATIVE_CONTEXT)):
        raise Error("occupied target is outside the reviewed sequence")
    window = target if target is not None else 32768
    if accounting.get("configured_context", 0) < window:
        raise Error("occupied target exceeds actually configured context")
    ceiling = window - (RESERVE if initial else body["max_tokens"])
    if count > ceiling or (target is not None and initial and count < ceiling - OCCUPANCY_TOLERANCE):
        raise Error("actual input violates occupied target or continuation reserve")
    return {"input_tokens": count, "context_target": window, "initial_reserve_tokens": RESERVE,
            "input_ceiling_tokens": ceiling, "remaining_context_tokens": window-count}


def _observations(raw, stream):
    if not stream:
        return [a1.strict_json_loads(raw)]
    # A1 already validated framing, completion and [DONE] before this extraction.
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    observations = []
    for event in text.split("\n\n")[:-1]:
        data = "\n".join(line[5:].lstrip(" ") for line in event.split("\n") if line.startswith("data:"))
        if data and data != "[DONE]":
            observations.append(a1.strict_json_loads(data))
    return observations


def _counter(mapping, field, integer=True):
    value = mapping.get(field) if isinstance(mapping, dict) else None
    if value is not None and (type(value) not in ((int,) if integer else (int, float)) or not 0 <= value <= 2**63 - 1 or not math.isfinite(value)):
        raise Error("backend exposed an invalid numeric counter")
    return value


def parse_response(raw: bytes, stream: bool, model: str):
    """Use shipped A1 parsers and retain exact exposed counters; no estimates.

    Raw usage/timing observations are PRIVATE provider data. Callers redact
    credentials before persistence and expose only the compact counter allowlist.
    """
    if not isinstance(raw, bytes) or len(raw) > 16 * 1024 * 1024 or type(stream) is not bool:
        raise Error("invalid or oversized response input")
    parsed = a1._stream(raw) if stream else a1._completion(a1.strict_json_loads(raw))
    if parsed["model"] != model:
        raise Error("returned model differs from exact requested alias")
    observations = _observations(raw, stream)
    usage_observations = [item["usage"] for item in observations if item.get("usage") is not None]
    timing_observations = [item["timings"] for item in observations if item.get("timings") is not None]
    usage = parsed["usage"] or {}
    timing = timing_observations[-1] if timing_observations else {}
    if not isinstance(usage, dict) or not isinstance(timing, dict):
        raise Error("backend usage/timings must be objects when exposed")
    details = usage.get("prompt_tokens_details") or {}
    cached = _counter(details, "cached_tokens")
    cache_source = "usage.prompt_tokens_details.cached_tokens" if cached is not None else None
    if cached is None:
        cached = _counter(timing, "cache_n")
        cache_source = "timings.cache_n" if cached is not None else None
    counters = {"prompt_tokens": _counter(usage, "prompt_tokens"),
                "completion_tokens": _counter(usage, "completion_tokens"),
                "total_tokens": _counter(usage, "total_tokens"),
                "cached_tokens": cached, "cached_tokens_source": cache_source,
                "evaluated_prompt_tokens": _counter(timing, "prompt_n"),
                "decode_tokens": _counter(timing, "predicted_n"),
                "prompt_ms": _counter(timing, "prompt_ms", False),
                "decode_ms": _counter(timing, "predicted_ms", False),
                "elapsed_seconds": None}
    parsed.update({"counters": counters, "timings": timing if timing_observations else None,
                   "usage_observations": usage_observations, "timing_observations": timing_observations})
    return parsed


def check_sentinels(message, expected):
    """Require exact ordered early/middle/late JSON values in final content."""
    parsed, _ = a1._assistant(message)
    if not isinstance(expected, list) or len(expected) != 3 or any(not isinstance(item, str) or not item for item in expected):
        raise Error("three explicit early/middle/late sentinel values are required")
    if parsed.get("tool_calls") or not isinstance(parsed.get("content"), str):
        raise Error("sentinel retrieval requires a content-only response")
    actual = a1.strict_json_loads(parsed["content"])
    if actual != expected:
        raise Error("early/middle/late retrieval content did not match")
    return {"early": True, "middle": True, "late": True,
            "expected_sha256": sha256(canonical(expected))}


def check_tool_continuation(message):
    parsed, _ = a1._assistant(message)
    if parsed.get("tool_calls") or not isinstance(parsed.get("content"), str) or any(line not in parsed["content"] for line in ("def add(a, b):", "return a - b")):
        raise Error("continuation did not report actual deterministic tool content")
    return {"tool_content_reported": True}


def execute_tool(message, workspace_parent=None):
    """Execute exactly one real A1 read_file(calc.py), locally and deterministically.

    Fixture setup/cleanup runs its fixed tiny CPU tests; no model-supplied command
    executes and no server tool exists. Return the real tool-role continuation.
    """
    parsed, _ = a1._assistant(message)
    calls = parsed.get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "read_file" or a1.strict_json_loads(calls[0]["function"]["arguments"]) != {"path": "calc.py"}:
        raise Error("D3T permits exactly one deterministic read_file(calc.py) call")
    with Fixture(parent=workspace_parent) as fixture:
        result = fixture.execute_calls(calls)[0]
        value = a1.strict_json_loads(result["content"])
        if value != {"path": "calc.py", "content": INITIAL_SOURCE}:
            raise Error("local deterministic tool result changed")
        evidence = {"tool": "read_file", "path": "calc.py", "worker_local": True,
                    "content_sha256": sha256(INITIAL_SOURCE.encode("utf-8")),
                    "result_sha256": sha256(result["content"].encode("utf-8"))}
    return result, evidence
