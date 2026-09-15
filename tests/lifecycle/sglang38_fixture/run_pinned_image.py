#!/usr/bin/env python3
"""Actual-image Q38S authentication fixture, never a substitute for inference.

Run only in the reviewed disposable pinned image with no GPU, no network, a
readonly /fixture checkout, and empty private tmpfs mounts at /models and
/run/secrets. No production secret or model directory may be mounted.

The installed parser, raw ServerArgs, resolve_once/runtime publication, HTTP setup, native auth,
FastAPI/Starlette routes and response serializers run unchanged. Synthetic
collaborators replace CUDA discovery and engine/model/worker startup only.
Uvicorn.run is captured instead of opening an inference listener; the native
lifespan's model-serving initialization is therefore NOT_TESTED. A synthetic
loopback HTTP server exercises the launcher's real authenticated warmup I/O.
Failure subprocesses additionally exercise actual launcher process cleanup.

No source-extracted or replacement-framework fallback exists. Missing native
dependencies or unsupported native preprocessing produce a nonzero FAIL.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import dataclasses
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import importlib.metadata
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import pickle
import runpy
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


IMAGE_ID = "sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813"
SOURCE_REVISION = "0bcd822377da7b5718e674eaf9c870d349424dd1"
IMAGE_REFERENCE = "lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262"
KEY_PATH = Path("/run/secrets/llm-api-key")
CONFIG_PATH = Path("/models/config.json")
ALIAS = "qwen3.8-27b"
HARDWARE_STUBS = (
    "is_available", "device_count", "current_device", "get_device_capability",
    "get_device_properties", "get_device_name", "mem_get_info",
)
SCENARIOS = ("all", "warmup-auth-failure", "warmup-timeout")
FAULT_MARKER = b"Q38S_AUTHENTICATED_WARMUP_FAULT_REACHED\n"


FAILURE_CLASSES = frozenset((
    "FixtureFailure", "LaunchError", "AssertionError", "AttributeError", "ImportError", "ModuleNotFoundError",
    "TypeError", "ValueError", "KeyError", "IndexError", "RuntimeError", "OSError",
    "FileNotFoundError", "PermissionError", "TimeoutError", "TimeoutExpired", "JSONDecodeError",
    "SystemExit", "KeyboardInterrupt", "MemoryError", "RecursionError", "OTHER",
))


class FixtureFailure(Exception):
    """Only fixed diagnostic codes may leave this helper."""


def require(condition, code):
    if not condition:
        raise FixtureFailure(code)


def failure_origin(error):
    """Select a local callsite without messages, locals, source text or paths.

    A deeper cache child or launcher may already have discarded its cause.
    This is only the last approved fixture callsite, never a deepest-cause claim.
    """
    origin = None
    frame = error.__traceback__
    for _ in range(64):
        if frame is None:
            return origin
        code = frame.tb_frame.f_code
        if (code.co_filename == __file__ and code is not require.__code__
                and type(frame.tb_lineno) is int and 1 <= frame.tb_lineno <= 100000):
            kind = type(error).__name__
            origin = {"filename": "run_pinned_image.py", "line": frame.tb_lineno,
                      "exception_class": kind if kind in FAILURE_CLASSES else "OTHER"}
        frame = frame.tb_next
    return None


def checked_launch(launcher, argv, captured, engine_calls, sentinel):
    """Keep the first swallowed exception at the launcher's existing log seam.

    Only the failure operands/class leave via JSON. A bounded, sentinel-redacted
    exception and frame coordinates go to original stderr for Worker1's private
    capture, never captured application logs or a receipt. No locals, source
    lines, arguments, environment or application contents are inspected.
    """
    first_error = None
    original_error = launcher.LOGGER.error

    def remember_error(message, *args, **kwargs):
        nonlocal first_error
        if message in ("sglang38_file_auth_launch_failed", "sglang38_file_auth_cleanup_failed"):
            active = sys.exc_info()[1]
            if first_error is None and active is not None:
                first_error = active
        return original_error(message, *args, **kwargs)

    result = None
    escaped = None
    try:
        # Native resolution sets SGLANG_MAMBA_SSM_DTYPE. Keep that real change
        # throughout this launch, then restore the pre-launch environment for
        # the independent injection-failure case and child fixture processes.
        with patch.dict(os.environ), patch.object(launcher.LOGGER, "error", side_effect=remember_error):
            result = launcher.main(argv)
    except BaseException as error:
        escaped = error
        if first_error is None:
            first_error = error
    operands = {"result": result, "captured": len(captured), "engine_calls": len(engine_calls)}
    if (escaped is not None or first_error is not None
            or not (result == 0 and len(captured) == 1 and len(engine_calls) == 1)):
        kind = type(first_error).__name__ if first_error is not None else None
        safe_kind = kind if kind in FAILURE_CLASSES else "OTHER" if kind else None
        # The real launcher returns 0/1. Unexpected values still fail and cannot
        # carry arbitrary backend objects through the safe metadata boundary.
        failure = {**operands, "result": result if type(result) is int and -255 <= result <= 255 else None,
                   "first_exception_class": safe_kind}
        try:
            frames = []
            frame = first_error.__traceback__ if first_error is not None else None
            for _ in range(32):
                if frame is None:
                    break
                frames.append({"filename": Path(frame.tb_frame.f_code.co_filename).name,
                               "function": frame.tb_frame.f_code.co_name, "line": frame.tb_lineno})
                frame = frame.tb_next
            private = {"marker": "Q38NEXT_PRIVATE_LAUNCH_FAILURE", "source_revision": SOURCE_REVISION,
                       "fixture_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "launcher_sha256": hashlib.sha256(Path(launcher.__file__).read_bytes()).hexdigest(),
                       "operands": failure, "frames": frames,
                       "exception_message": str(first_error).replace(sentinel, "<synthetic-key-redacted>")[:4096]
                           if first_error is not None else None}
            raw = json.dumps(private, sort_keys=True).replace(sentinel, "<synthetic-key-redacted>").encode()
            os.write(2, raw[:16383] + b"\n")
        except BaseException:
            pass  # Diagnostic failure must retain the original CLI failure.
        error = FixtureFailure("actual_native_launch_setup_failed")
        error.launch_failure = failure
        raise error from escaped
    return result


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise FixtureFailure("arguments_invalid")


def parse_options(argv):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--actual-image", action="store_true", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--context", type=int, choices=(131072, 262144), default=131072)
    parser.add_argument("--internal-scenario", choices=SCENARIOS, default="all",
                        help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def no_secret(value, sentinel):
    # Never put a failed comparison or the checked data in an assertion message.
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    require(sentinel.encode("ascii") not in raw, "sentinel_disclosure")


def verify_sources(repo):
    """Verify immutable upstream files before importing the installed runtime.

    Actual image identity is bound only by the outer run_fixture.py host driver.
    This inner runner never asserts that a self-reported image ID is proof.
    """
    require(sys.platform == "linux", "linux_pinned_image_required")
    require(repo.is_absolute() and repo.resolve() == repo, "repository_path_invalid")
    expected = json.loads((repo / "tests/lifecycle/sglang38_fixture/provenance.json").read_text())
    require(expected["source_revision"] == SOURCE_REVISION
            and expected["image_id"] == IMAGE_ID
            and expected["image_reference"] == IMAGE_REFERENCE,
            "source_provenance_identity_mismatch")
    require(importlib.metadata.version("sglang") == "0.5.19", "installed_version_mismatch")
    spec = importlib.util.find_spec("sglang")
    require(spec is not None and spec.origin is not None, "installed_sglang_missing")
    source_root = Path(spec.origin).resolve().parent
    require(not source_root.is_relative_to(repo), "repository_sglang_substitution_refused")
    for name, identity in expected["sources"].items():
        path = source_root / name
        require(path.is_file() and path.stat().st_size == identity["bytes"],
                "installed_source_size_mismatch")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == identity["sha256"],
                "installed_source_hash_mismatch")
    launcher_path = repo / "scripts/runtime/sglang38_file_auth.py"
    require(hashlib.sha256(launcher_path.read_bytes()).hexdigest() == expected["launcher_sha256"],
            "launcher_source_hash_mismatch")
    for name, identity in expected["fixture_sha256"].items():
        require(name not in ("provenance.json", "") and "/" not in name,
                "fixture_provenance_invalid")
        path = repo / "tests/lifecycle/sglang38_fixture" / name
        require(hashlib.sha256(path.read_bytes()).hexdigest() == identity,
                "fixture_source_hash_mismatch")
    for name, digest in expected.get("support_sha256", {}).items():
        require(name == "scripts/runtime/qwen38_oci.py"
                and hashlib.sha256((repo / name).read_bytes()).hexdigest() == digest,
                "support_source_hash_mismatch")
    return launcher_path


def require_private_tmpfs(target):
    """Refuse a real secret/model bind mount before creating any fixture file."""
    rows = Path("/proc/self/mountinfo").read_text().splitlines()
    matches = [row for row in rows if row.split()[4] == str(target)]
    require(len(matches) == 1 and matches[0].split(" - ", 1)[1].split()[0] == "tmpfs",
            "empty_fixture_tmpfs_required")
    meta = target.stat()
    require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == os.geteuid()
            and not meta.st_mode & 0o022, "fixture_directory_permissions_invalid")


@contextmanager
def fixture_files(config_bytes):
    """Create exact fixture bytes exclusively; never overwrite or rotate a key."""
    require_private_tmpfs(KEY_PATH.parent)
    require_private_tmpfs(CONFIG_PATH.parent)
    created = []
    sentinel = secrets.token_urlsafe(32)
    try:
        for path, value, mode in ((KEY_PATH, sentinel.encode("ascii"), 0o600),
                                  (CONFIG_PATH, config_bytes, 0o644)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         mode)
            try:
                os.fchmod(fd, mode)
                meta = os.fstat(fd)
                created.append((path, meta.st_dev, meta.st_ino))
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
        yield sentinel
        require(KEY_PATH.read_bytes() == sentinel.encode("ascii"), "fixture_key_changed")
    finally:
        for path, device, inode in reversed(created):
            try:
                now = path.lstat()
                if (now.st_dev, now.st_ino) == (device, inode):
                    path.unlink()
            except FileNotFoundError:
                pass


@contextmanager
def cuda_discovery_fixture(torch):
    """Discovery-only fake devices; any real CUDA initialization is forbidden.

    This preserves native argument parsing and the full native resolution pipeline.
    The exact mocked public torch.cuda probes are recorded in the final result.
    Their answers describe synthetic 96GiB SM120 devices, not detected hardware.
    """
    properties = SimpleNamespace(name="Q38S synthetic device", total_memory=96 * 2**30,
                                 major=12, minor=0, multi_processor_count=1)
    values = {"is_available": True, "device_count": 1, "current_device": 0,
              "get_device_capability": (12, 0), "get_device_properties": properties,
              "get_device_name": properties.name, "mem_get_info": (90 * 2**30, 96 * 2**30)}
    with ExitStack() as stack:
        for name in HARDWARE_STUBS:
            require(callable(getattr(torch.cuda, name, None)), "hardware_probe_api_mismatch")
            stack.enter_context(patch.object(torch.cuda, name, return_value=values[name]))
        # A discovery-only fixture must fail rather than execute GPU allocation.
        stack.enter_context(patch.object(torch.cuda, "_lazy_init",
                                         side_effect=FixtureFailure("gpu_initialization_refused")))
        yield


async def asgi_request(app, path, token=None, *, method="GET", body=None,
                       websocket=False, disconnect=False, preflight=False):
    payload = json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"127.0.0.1"), (b"content-type", b"application/json")]
    if token is not None:
        headers.append((b"authorization", ("Bearer " + token).encode("ascii")))
    if preflight:
        headers += [(b"origin", b"https://fixture.invalid"),
                    (b"access-control-request-method", b"GET")]
    scope = {"type": "websocket" if websocket else "http",
             "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "scheme": "ws" if websocket else "http",
             "method": method, "path": path, "raw_path": path.encode(),
             "root_path": "", "query_string": b"", "headers": headers,
             "server": ("127.0.0.1", 30004), "client": ("127.0.0.1", 12345)}
    messages = []
    initial = True
    first_chunk = asyncio.Event()

    async def receive():
        nonlocal initial
        if initial:
            initial = False
            return {"type": "http.request", "body": payload, "more_body": False}
        if disconnect:
            await first_chunk.wait()
            return {"type": "http.disconnect"}
        await asyncio.Future()

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_chunk.set()

    await asyncio.wait_for(app(scope, receive, send), timeout=8)
    if websocket:
        return None, b"", messages
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, content, messages


class SyntheticTokenizer:
    """Only engine/model responses are synthetic; native HTTP handlers remain."""

    def __init__(self, server_args, server, context):
        self.server_args = server_args
        self.startup_time = {"fixture": 0.0}
        self.server_status = server.ServerStatus.Starting
        self.gracefully_exit = False
        self.is_generation = True
        self.served_model_name = ALIAS
        self.model_path = "/models"
        self.model_config = SimpleNamespace(context_len=context,
            is_image_understandable_model=False, is_audio_understandable_model=False,
            hf_config=SimpleNamespace(model_type="qwen3_5", architectures=["Qwen3_5ForConditionalGeneration"]))
        self.socket_mapping = SimpleNamespace(clear_all_sockets=lambda: None)
        self.rid_to_state = {}
        self.last_receive_tstamp = 0
        self.disconnect_mode = False
        self.disconnect_seen = False
        self.generation_calls = 0
        self.diagnostic_calls = 0

    def config_value(self, name):
        return self.server_args.resolved_dict()[name]

    async def get_internal_state(self):
        self.diagnostic_calls += 1
        return [{"q38s_fixture_worker": True}]

    async def generate_request(self, obj, request):
        self.generation_calls += 1
        self.last_receive_tstamp = time.time()
        yield {"text": "fixture", "meta_info": {"completion_tokens": 1}}
        if self.disconnect_mode and request is not None:
            event = await request.receive()
            self.disconnect_seen = event["type"] == "http.disconnect"

    def create_abort_task(self, _obj):
        from starlette.background import BackgroundTask
        return BackgroundTask(lambda: None)


@contextmanager
def warmup_http_server(sentinel, mode):
    """No model server: two small authenticated synthetic HTTP responses only."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def respond(self):
            valid = secrets.compare_digest(self.headers.get("Authorization", ""),
                                           "Bearer " + sentinel)
            require(valid or self.path == "/freeze_gc", "warmup_header_missing_or_wrong")
            if mode in ("timeout", "auth-failure"):
                # Fixed nonsecret evidence distinguishes the intended abort
                # from an unrelated native process exiting with the same code.
                os.write(1, FAULT_MARKER)
            if mode == "timeout":
                time.sleep(2)
            if self.path == "/freeze_gc":
                require(not valid, "native_freeze_unexpected_auth")
                status, payload = 401, {"error": "fixture_rejection"}
            elif mode == "auth-failure":
                status, payload = 401, {"error": "fixture_rejection"}
            elif self.path == "/model_info":
                status, payload = 200, {"is_generation": True}
            elif self.path == "/generate":
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                require(data == {"text": "Hello", "sampling_params": {
                    "temperature": 0, "max_new_tokens": 1}, "stream": False}, "warmup_request_changed")
                status, payload = 200, {"text": "fixture", "meta_info": {"completion_tokens": 1}}
            else:
                status, payload = 404, {}
            calls.append((self.command, self.path, valid))
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = respond
        do_POST = respond

    server = ThreadingHTTPServer(("127.0.0.1", 30004), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def check_routes(server, app, tokenizer, sentinel, wrong):
    from starlette.responses import JSONResponse

    class ModelChat:
        calls = 0

        async def handle_request(self, request, _raw):
            require(request.model == ALIAS, "native_chat_request_model_changed")
            self.calls += 1
            return JSONResponse({"id": "q38s-fixture-chat", "object": "chat.completion",
                                 "model": ALIAS, "choices": []})

    chat = ModelChat()
    app.state.openai_serving_chat = chat

    async def checks():
        start_health = await asgi_request(app, "/health", sentinel)
        require(start_health[0] == 503, "starting_health_must_reject")
        model_while_starting = await asgi_request(app, "/v1/models", sentinel)
        require(model_while_starting[0] == 200, "native_models_route_unavailable")
        require(tokenizer.server_status == server.ServerStatus.Starting,
                "models_must_not_mark_server_up")
        for path, method, body in (
            ("/v1/models", "GET", None),
            ("/v1/chat/completions", "POST", {"model": ALIAS, "messages": [{"role": "user", "content": "fixture"}]}),
            ("/server_info", "GET", None), ("/get_server_info", "GET", None),
        ):
            before_chat, before_diagnostics = chat.calls, tokenizer.diagnostic_calls
            for token in (None, wrong):
                status, payload, messages = await asgi_request(app, path, token, method=method, body=body)
                require(status in (401, 403), "native_auth_rejection_failed")
                no_secret(payload, sentinel)
                no_secret(messages, sentinel)
            require(chat.calls == before_chat and tokenizer.diagnostic_calls == before_diagnostics,
                    "unauthorized_request_reached_handler")
            status, payload, messages = await asgi_request(app, path, sentinel, method=method, body=body)
            require(status == 200, "native_authenticated_handler_failed")
            data = json.loads(payload)
            if path == "/v1/models":
                require(len(data["data"]) == 1 and data["data"][0]["id"] == ALIAS,
                        "native_model_identity_failed")
            elif path == "/v1/chat/completions":
                require(data["id"] == "q38s-fixture-chat" and chat.calls == before_chat + 1,
                        "native_chat_handler_not_reached")
            else:
                require(data["api_key"] is None and data["admin_api_key"] is None
                        and data["model_path"] == "/models"
                        and data["internal_states"] == [{"q38s_fixture_worker": True}]
                        and tokenizer.diagnostic_calls == before_diagnostics + 1,
                        "native_diagnostic_handler_not_reached")
            no_secret(payload, sentinel)
            no_secret(messages, sentinel)
        for token in (None, wrong, sentinel):
            status, _, _ = await asgi_request(app, "/__q38s/admin-force", token)
            require(status == 403, "native_admin_force_not_denied")
            for path in ("/health_q38s_probe", "/metrics_q38s_probe"):
                status, _, _ = await asgi_request(app, path, token)
                require(status == 200, "native_prefix_exemption_changed")
            status, _, _ = await asgi_request(app, "/v1/models", token, method="OPTIONS", preflight=True)
            require(status == 200, "native_options_exemption_changed")
            _, _, messages = await asgi_request(app, "/v1/realtime", token, websocket=True)
            require(messages == [{"type": "websocket.close", "code": 1008}], "websocket_not_closed")
        for path in ("/docs", "/redoc", "/openapi.json"):
            status, _, _ = await asgi_request(app, path, sentinel)
            require(status == 404, "documentation_ui_present")
        tokenizer.disconnect_mode = True
        generation_before = tokenizer.generation_calls
        for token in (None, wrong):
            status, payload, _ = await asgi_request(app, "/generate", token, method="POST",
                body={"text": "fixture", "stream": False, "sampling_params": {"max_new_tokens": 1}})
            require(status == 401, "native_generate_auth_rejection_failed")
            no_secret(payload, sentinel)
        require(tokenizer.generation_calls == generation_before,
                "unauthorized_generate_reached_engine")
        status, payload, messages = await asgi_request(app, "/generate", sentinel, method="POST",
            body={"text": "fixture", "stream": True, "sampling_params": {"max_new_tokens": 1}},
            disconnect=True)
        require(status == 200 and tokenizer.disconnect_seen, "native_stream_disconnect_not_preserved")
        chunks = [m.get("body", b"") for m in messages if m["type"] == "http.response.body" and m.get("body")]
        require(len(chunks) == 2 and chunks[0].startswith(b"data: ")
                and json.loads(chunks[0][6:].strip())["text"] == "fixture"
                and chunks[1] == b"data: [DONE]\n\n", "native_sse_chunks_changed")
        no_secret(payload, sentinel)
        tokenizer.disconnect_mode = False

    asyncio.run(checks())


def check_native_parser_template(repo):
    """Actual installed parser/template execution with synthetic text, no model.

    These checks are not a model-generation or client-continuation proof.
    """
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers
    from transformers import PreTrainedTokenizerFast
    from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest, Tool
    from sglang.srt.entrypoints.openai.serving_chat import OpenAIServingChat
    from sglang.srt.parser.template_manager import TemplateManager
    from sglang.srt.function_call.function_call_parser import FunctionCallParser
    from sglang.srt.parser.reasoning_parser import ReasoningParser
    tool_dict = {"type": "function", "function": {"name": "read_fixture", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}, "count": {"type": "integer"}},
        "required": ["path", "count"]}}}
    tools = [Tool(**tool_dict)]
    text = ("<tool_call>\n<function=read_fixture>\n<parameter=path>\nfixture.txt\n</parameter>\n"
            "<parameter=count>\n3\n</parameter>\n</function>\n</tool_call>")
    normal, calls = FunctionCallParser(tools, "qwen3_coder").parse_non_stream(text)
    require(not normal.strip() and len(calls) == 1 and calls[0].name == "read_fixture"
            and json.loads(calls[0].parameters) == {"path": "fixture.txt", "count": 3},
            "native_structured_tool_parser_failed")
    stream = FunctionCallParser(tools, "qwen3_coder")
    fragments = []
    for start in range(0, len(text), 7):
        _, found = stream.parse_stream_chunk(text[start:start + 7])
        fragments.extend(found)
    _, found = stream.parse_stream_end()
    fragments.extend(found)
    require(fragments and all(item.tool_index == 0 for item in fragments)
            and "".join(item.name or "" for item in fragments) == "read_fixture"
            and json.loads("".join(item.parameters or "" for item in fragments)) == {
                "path": "fixture.txt", "count": 3}, "native_fragmented_tool_parser_failed")
    reasoning, final = ReasoningParser("qwen3").parse_non_stream("<think>brief</think>answer")
    require(reasoning.strip() == "brief" and final.strip() == "answer", "native_reasoning_parser_failed")
    reasoning, final = ReasoningParser("qwen3").parse_non_stream("<think>\n\n</think>\n\nanswer")
    require(not (reasoning or "").strip() and final.strip() == "answer"
            and "<think>" not in final and "</think>" not in final,
            "native_empty_think_leaked_to_final")
    template_path = repo / "tests/lifecycle/sglang38_fixture/chat_template.jinja"
    template_bytes = template_path.read_bytes()
    require(len(template_bytes) == 8952 and hashlib.sha256(template_bytes).hexdigest()
            == "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041",
            "checkpoint_template_hash_mismatch")
    # Synthetic character vocabulary only; use native Transformers rendering
    # and encoding through the actual SGLang request-to-prompt helper. No model
    # tokenizer files, normalizer replacements or extracted-source fallback.
    class RecordingTokenizer(PreTrainedTokenizerFast):
        def apply_chat_template(self, *args, **kwargs):
            self.fixture_template_kwargs = dict(kwargs)
            rendered = super().apply_chat_template(*args, **kwargs)
            self.fixture_rendered = rendered
            return rendered

    vocabulary = {token: index for index, token in enumerate(
        ["<unk>", *[chr(value) for value in range(9, 127)]])}
    backend = Tokenizer(models.WordLevel(vocabulary, unk_token="<unk>"))
    backend.pre_tokenizer = pre_tokenizers.Split(pattern="", behavior="isolated")
    backend.decoder = decoders.Fuse()
    tokenizer = RecordingTokenizer(tokenizer_object=backend, unk_token="<unk>",
                                   chat_template=template_bytes.decode())
    configuration = {"tool_call_parser": "qwen3_coder", "reasoning_parser": "qwen3"}
    manager = SimpleNamespace(tokenizer=tokenizer, processor=None,
        served_model_name=ALIAS, model_path="/models", config_value=configuration.__getitem__,
        server_args=SimpleNamespace(default_chat_template_kwargs={"enable_thinking": False}),
        model_config=SimpleNamespace(get_default_sampling_params=lambda: {},
            hf_config=SimpleNamespace(model_type="qwen3_5",
                architectures=["Qwen3_5ForConditionalGeneration"])))
    template_manager = TemplateManager()
    template_manager.load_chat_template(manager, None, "/models")
    serving = OpenAIServingChat(manager, template_manager)
    require(serving.chat_encoding_spec is None and template_manager.chat_template_name is None,
            "native_qwen_jinja_path_not_selected")
    wires = {
        "ordinary": {"model": ALIAS, "reasoning_effort": "none", "stream": True,
            "messages": [{"role": "user", "content": "Say fixture ready"}]},
        "tool_continuation": {"model": ALIAS, "reasoning_effort": "none", "stream": True,
            "tools": [tool_dict], "messages": [
                {"role": "user", "content": "Read the fixture"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "fixture-call-1",
                    "type": "function", "function": {"name": "read_fixture",
                        "arguments": '{"path":"fixture.txt","count":3}'}}]},
                {"role": "tool", "tool_call_id": "fixture-call-1", "content": "fixture read"}]},
    }
    for case, wire in wires.items():
        require("chat_template_kwargs" not in wire and wire["reasoning_effort"] == "none"
                and wire["stream"] is True and wire["model"] == "qwen3.8-27b",
                "observed_q38c_wire_changed")
        request = ChatCompletionRequest.model_validate_json(json.dumps(wire))
        require(request.chat_template_kwargs == {"thinking": False, "enable_thinking": False},
                "native_none_normalization_failed")
        processed = serving._process_messages(request, is_multimodal=False)
        require(request.chat_template_kwargs == {"thinking": False, "enable_thinking": False}
                and request.reasoning_effort == "none" and processed.require_reasoning is False,
                "native_false_default_merge_failed")
        kwargs = tokenizer.fixture_template_kwargs
        require(kwargs.get("thinking") is False and kwargs.get("enable_thinking") is False
                and kwargs.get("reasoning_effort") == "none" and kwargs.get("tokenize") is False
                and kwargs.get("add_generation_prompt") is True,
                "native_none_template_arguments_failed")
        rendered = tokenizer.fixture_rendered
        require(tokenizer.decode(processed.prompt_ids, clean_up_tokenization_spaces=False) == rendered
                and "Reasoning effort is set to" not in rendered
                and rendered.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"),
                "native_none_prompt_prefix_failed")
        if case == "tool_continuation":
            require("<function=read_fixture>" in rendered
                    and "<tool_response>\nfixture read\n</tool_response>" in rendered,
                    "native_no_thinking_tool_continuation_template_failed")


def cache_probe_module(repo):
    probe_spec = importlib.util.spec_from_file_location("q38b_actual_cache_probe",
        repo / "tests/lifecycle/sglang38_fixture/cache_probe.py")
    cache_probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(cache_probe)
    return cache_probe


def cache_failure_metadata(error):
    """Revalidate the failure-only child hint before the final JSON boundary."""
    if (type(error) is not FixtureFailure or len(error.args) != 1
            or type(error.args[0]) is not str or error.args[0] != "cache_probe_child_failed"):
        return None
    try:
        probe = cache_probe_module(Path(__file__).resolve().parents[3])
        return probe.validate_failure(error.__dict__.get("cache_failure"))
    except Exception:
        # Missing/unavailable diagnostics must leave the original failure intact.
        return None


def run_cache_probe(repo):
    cache_probe = cache_probe_module(repo)
    # Native imports cache platform/architecture discovery. Isolate no-device
    # resolver discovery so it cannot contaminate the auth fixture's later
    # explicitly stubbed hardware setup in this interpreter.
    child = subprocess.run([sys.executable, "-X", "faulthandler", "-B",
        str(repo / "tests/lifecycle/sglang38_fixture/cache_probe.py"),
        "--actual-image", "--repo", str(repo)], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    try:
        require(child.returncode == 0 and child.stderr == b"" and len(child.stdout) <= 131072,
                "cache_probe_child_failed")
    except FixtureFailure as error:
        # This child runs before synthetic key/model files exist. Preserve a
        # bounded native/faulthandler prefix on the original stderr FD for the
        # worker-private capture; redirect_stderr(StringIO) must not swallow it.
        if child.stderr:
            try:
                os.write(2, b"Q38FIX cache_probe stderr prefix (up to 16384 bytes):\n" + child.stderr[:16384])
            except OSError:
                pass  # A broken diagnostic FD must not replace the native failure.
        if child.stderr == b"" and len(child.stdout) <= 131072:
            error.cache_failure = cache_probe.failure_metadata(child.stdout)
        raise
    result = json.loads(child.stdout)
    cache_probe.validate_result(result)
    return result


def run_actual(repo, scenario, captured_logs, context=131072):
    launcher_path = verify_sources(repo)
    # Genuine resolver/device/library checks precede synthetic model/key files
    # and every hardware discovery stub used by the native auth fixture.
    cache_result = run_cache_probe(repo)
    spec = importlib.util.spec_from_file_location("q38s_actual_image_launcher", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher.validate_environment()
    import torch
    with cuda_discovery_fixture(torch):
        from transformers import AutoConfig
        # Native model-config parsing is real. These deliberately tiny metadata
        # values are synthetic and are never mistaken for acquired model files.
        model_config = AutoConfig.for_model("qwen3_5", architectures=["Qwen3_5ForConditionalGeneration"],
            text_config={"model_type": "qwen3_5_text", "max_position_embeddings": 262144})
        config_bytes = model_config.to_json_string().encode()
        from sglang.srt.entrypoints import http_server as server
        from sglang.srt.server_args import PortArgs, ServerArgs, prepare_server_args
        from sglang.srt.utils import auth
        from starlette.responses import JSONResponse
        require(server.app.__class__.__module__.startswith("fastapi"), "actual_fastapi_required")
        require(dataclasses.is_dataclass(ServerArgs), "actual_server_args_required")
        with fixture_files(config_bytes) as sentinel:
            check_native_parser_template(repo)
            wrong = secrets.token_urlsafe(32)
            require(wrong != sentinel, "fixture_randomness_failure")
            argv = ["--key-file", str(KEY_PATH), "--warmup-timeout", "600"] + launcher.backend_argv(context)
            no_secret(argv, sentinel)
            no_secret(os.environ, sentinel)
            no_secret(sys.argv, sentinel)
            for invalid in (("--enable-http2",), ("--grpc-mode",), ("--grpc-port", "30005"),
                            ("--tokenizer-worker-num", "2"), ("--use-ray",),
                            ("--encoder-only",), ("--config", "/cache/unreviewed.json"),
                            ("--tool-call-parser", "python"), ("--context-length", "1048576")):
                try:
                    launcher.parse_options(argv + list(invalid))
                except launcher.LaunchError:
                    pass
                else:
                    raise FixtureFailure("unsupported_cli_mode_accepted")
            for field, value in (("enable_http2", True), ("grpc_mode", True),
                                 ("grpc_port", 30005), ("tokenizer_worker_num", 2),
                                 ("use_ray", True), ("encoder_only", True)):
                raw = prepare_server_args(launcher.backend_argv(context))
                require(hasattr(raw, field), "native_unsupported_mode_field_missing")
                setattr(raw, field, value)
                try:
                    launcher.validate_server_args(raw)
                except launcher.LaunchError:
                    pass
                else:
                    raise FixtureFailure("unsupported_raw_mode_accepted")
            with patch.object(os, "open", side_effect=FixtureFailure("spawn_import_read_file")):
                imported = runpy.run_path(str(launcher_path), run_name="__mp_main__")
            require("main" in imported, "spawn_import_failed")

            @auth.auth_level(auth.AuthLevel.ADMIN_FORCE)
            async def forced():
                raise FixtureFailure("admin_force_handler_reached")

            async def public_probe():
                return JSONResponse({"q38s_fixture_probe": True})

            # Fixture routes exercise the native ADMIN_FORCE layering branch and
            # prefix exemptions without replacing any production route.
            server.app.add_api_route("/__q38s/admin-force", forced, methods=["GET"], include_in_schema=False)
            for path in ("/health_q38s_probe", "/metrics_q38s_probe"):
                server.app.add_api_route(path, public_probe, methods=["GET"], include_in_schema=False)
            engine_calls, captured = [], []

            def engine_start(**kwargs):
                args = kwargs["server_args"]
                launcher.validate_resolved_server_args(args)
                require(type(args) is ServerArgs, "native_server_args_replaced")
                no_secret(repr(args), sentinel)
                no_secret(dataclasses.asdict(args), sentinel)
                no_secret(args._raw_input, sentinel)
                no_secret(args.resolved_dict(), sentinel)
                no_secret(vars(args), sentinel)
                # Native spawned workers receive the same args/PortArgs pickle.
                ports = PortArgs("ipc:///cache/tokenizer", "ipc:///cache/scheduler",
                    "ipc:///cache/detokenizer", 29999, "ipc:///cache/rpc", "ipc:///cache/metrics", None, None)
                from sglang.srt.utils import MultiprocessingSerializer
                workerargs = (args, ports)
                no_secret(pickle.dumps(workerargs), sentinel)
                no_secret(MultiprocessingSerializer.serialize(workerargs), sentinel)
                for snapshot in (dataclasses.asdict(args), args._raw_input, args.resolved_dict()):
                    require(snapshot["api_key"] is None and snapshot["admin_api_key"] is None,
                            "native_raw_resolved_key_fields_not_empty")
                no_secret(pickle.dumps(args), sentinel)
                # Engine/model startup is synthetic; exercise the exact type's
                # repr with the installed engine logger without executing CUDA.
                logging.getLogger("sglang.srt.entrypoints.engine").warning("server_args=%s", args.resolved_dict())
                from sglang.srt.runtime_context import publish
                publish(args, role="tokenizer")
                tokenizer = SyntheticTokenizer(args, server, context)
                engine_calls.append((args, tokenizer))
                return tokenizer, SimpleNamespace(), ports, SimpleNamespace(scheduler_infos=[{}]), None, []

            def capture_uvicorn(app, **kwargs):
                captured.append(app)
                require(app is server.app and app.server_args is engine_calls[-1][0],
                        "native_global_application_not_retained")
                require(kwargs["host"] == launcher.FIXED_FLAGS["--host"] and kwargs["port"] == 30004
                        and "workers" not in kwargs, "unexpected_uvicorn_launch_mode")
                layers = [m for m in app.user_middleware
                          if getattr(m.cls, "__name__", "") == "_ApiKeyASGIMiddleware"]
                require(len(layers) == 2 and sum(m.kwargs.get("api_key") is None for m in layers) == 1,
                        "final_native_auth_layering_missing")
                no_secret(repr(app.user_middleware), sentinel)
                if scenario == "all":
                    callbacks = []
                    server._wait_and_warmup(engine_calls[-1][0],
                        launch_callback=lambda: callbacks.append(True),
                        execute_warmup_func=lambda _args: False)
                    require(not callbacks and engine_calls[-1][1].server_status == server.ServerStatus.Starting,
                            "native_failed_warmup_advertised_ready")
                    check_routes(server, app, engine_calls[-1][1], sentinel, wrong)
                mode = {"all": "success", "warmup-auth-failure": "auth-failure",
                        "warmup-timeout": "timeout"}[scenario]
                with warmup_http_server(sentinel, mode) as calls:
                    server._wait_and_warmup(**app.warmup_thread_kwargs)
                    require(scenario == "all", "failed_warmup_returned_without_process_exit")
                    require(calls == [("GET", "/model_info", True), ("POST", "/generate", True),
                                      ("POST", "/freeze_gc", False)],
                            "authenticated_warmup_not_executed")
                require(engine_calls[-1][1].server_status == server.ServerStatus.Up,
                        "warmup_did_not_mark_up")
                status, payload, _ = asyncio.run(asgi_request(app, "/health", sentinel))
                require(status == 200, "up_health_must_succeed")
                no_secret(payload, sentinel)

            with ExitStack() as stack:
                stack.enter_context(patch.object(server.Engine, "_launch_subprocesses", side_effect=engine_start))
                stack.enter_context(patch.object(server.uvicorn, "run", side_effect=capture_uvicorn))
                if scenario == "warmup-timeout":
                    # Fault injection only: same watchdog/abort path, short deadline.
                    stack.enter_context(patch.object(launcher, "STARTUP_TIMEOUT", 0.4))
                checked_launch(launcher, argv, captured, engine_calls, sentinel)
            no_secret(captured_logs.getvalue(), sentinel)
            require(KEY_PATH.read_bytes() == sentinel.encode(), "existing_fixture_key_changed")

            # Re-import the real installed module to obtain its actual fresh app.
            # Deliberately broken injection must fail before workers/Uvicorn and
            # the launcher's real cleanup must reap a synthetic child process.
            server = importlib.reload(server)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            try:
                with patch.dict(os.environ), \
                     patch.object(auth, "add_api_key_middleware", return_value=None), \
                     patch.object(server.Engine, "_launch_subprocesses") as workers, \
                     patch.object(server.uvicorn, "run") as uvicorn:
                    require(launcher.main(argv) == 1, "no_op_injection_not_refused")
                    require(not workers.called and not uvicorn.called, "injection_failure_started_server")
                child.wait(timeout=5)
                require(child.returncode is not None, "injection_failure_child_not_reaped")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
            no_secret(captured_logs.getvalue(), sentinel)
    return {"native_routes_and_final_chain": "PASS", "native_prepare_and_normalization": "PASS",
            "health_starting_503_up_200": "PASS", "sentinel_absence": "PASS",
            "injection_failure_child_cleanup": "PASS", "spawn_import": "PASS",
            "unsupported_modes": "PASS", "raw_resolved_workerargs_sentinel_absence": "PASS",
            "native_sse_disconnect": "PASS", "ordinary_http_auth": "PASS",
            "server_info_sentinel_absence": "PASS", "websocket_denial": "PASS",
            "native_false_warmup_not_ready": "PASS",
            "native_parser_template_synthetic": "PASS",
            "native_freeze_gc_has_no_key": "PASS", "actual_cache_resolvers": "PASS",
            "no_gpu_driver_libraries": "PASS", "cache_probe": cache_result}


def run_failure_children(repo, context=131072):
    # Each case has an independent exclusively created synthetic key/config.
    # os._exit in the real launcher skips finally; remove only owned fixture
    # files after the child is gone, never accept a preexisting file.
    for scenario in SCENARIOS[1:]:
        require(not KEY_PATH.exists() and not CONFIG_PATH.exists(), "fixture_files_not_clean")
        result = subprocess.run([sys.executable, "-X", "faulthandler", str(Path(__file__).resolve()), "--actual-image",
                                 "--repo", str(repo), "--context", str(context), "--internal-scenario", scenario],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=180, check=False)
        if result.stderr:
            try:
                os.write(2, b"Q38FIX failure fixture stderr prefix (up to 16384 bytes):\n" + result.stderr[:16384])
            except OSError:
                pass  # Preserve the original failed child outcome.
        require(result.returncode == 1 and result.stdout == FAULT_MARKER and result.stderr == b"",
                "warmup_failure_subprocess_not_closed")
        # These files can exist only if the exclusive child created them. Do not
        # use this cleanup for an ordinary helper invocation with existing files.
        for path in (KEY_PATH, CONFIG_PATH):
            meta = path.lstat()
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.geteuid(),
                    "child_fixture_file_identity_invalid")
            path.unlink()
        sock = socket.socket()
        try:
            sock.settimeout(1)
            require(sock.connect_ex(("127.0.0.1", 30004)) != 0,
                    "warmup_failure_listener_survived")
        finally:
            sock.close()


def main(argv=None):
    options = None
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    try:
        options = parse_options(sys.argv[1:] if argv is None else argv)
        with redirect_stdout(log_capture), redirect_stderr(log_capture):
            logging.getLogger().addHandler(handler)
            try:
                result = run_actual(options.repo, options.internal_scenario, log_capture, options.context)
            finally:
                logging.getLogger().removeHandler(handler)
        if options.internal_scenario != "all":
            raise FixtureFailure("expected_abort_not_observed")
        run_failure_children(options.repo, options.context)
        provenance = json.loads((options.repo / "tests/lifecycle/sglang38_fixture/provenance.json").read_text())
        result.update(status="PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE", image_id_pin=IMAGE_ID,
                      source_revision=SOURCE_REVISION, image_reference=IMAGE_REFERENCE,
                      launcher_sha256=provenance["launcher_sha256"],
                      fixture_sha256=provenance["fixture_sha256"],
                      support_sha256=provenance["support_sha256"],
                      source_hashes={name: item["sha256"] for name, item in provenance["sources"].items()},
                      configured_context=options.context,
                      image_identity_verification="HOST_DOCKER_INSPECT_REQUIRED",
                      hardware_discovery_stubs=list(HARDWARE_STUBS),
                      warmup_failure_and_timeout_cleanup="PASS",
                      model_loading="STUBBED_NOT_TESTED", gpu_execution="NOT_TESTED",
                      native_lifespan_model_serving_initialization="NOT_TESTED",
                      live_inference_and_agent_acceptance="NOT_TESTED")
        print(json.dumps(result, sort_keys=True))
        return 0
    except BaseException as error:
        if isinstance(error, SystemExit) and error.code == 0 and options is None:
            return 0
        # Deliberate abort children terminate via os._exit after one fixed marker.
        # An ordinary exception in those children must be distinguishable from
        # that success condition without emitting any captured backend data.
        failure = {"status": "FAIL", "code": "actual_image_fixture_failed",
                   "failure_origin": failure_origin(error)}
        cache_failure = cache_failure_metadata(error)
        if cache_failure is not None:
            failure["cache_failure"] = cache_failure
        if type(error) is FixtureFailure and error.args == ("actual_native_launch_setup_failed",):
            # Reuse the host's closed failure parser before exposing metadata.
            try:
                host_spec = importlib.util.spec_from_file_location("q38next_failure_boundary",
                    Path(__file__).with_name("run_fixture.py"))
                host = importlib.util.module_from_spec(host_spec)
                host_spec.loader.exec_module(host)
                candidate = {**failure, "launch_failure": error.__dict__.get("launch_failure")}
                if "launch_failure" in host.failure_metadata(json.dumps(candidate).encode()):
                    failure = candidate
            except BaseException:
                pass  # Metadata availability cannot replace the original FAIL.
        print(json.dumps(failure, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
