#!/usr/bin/env python3
"""Actual-image F1S authentication fixture, never a substitute for inference.

Run only in the reviewed disposable pinned image with no GPU, no network, a
readonly /fixture checkout, and empty private tmpfs mounts at /models and
/run/secrets. No production secret or model directory may be mounted.

The installed parser, ServerArgs.__post_init__, HTTP setup, native auth,
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


IMAGE_ID = "sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3"
KEY_PATH = Path("/run/secrets/llm-api-key")
CONFIG_PATH = Path("/models/config.json")
ALIAS = "qwen3-coder-next"
HARDWARE_STUBS = (
    "is_available", "device_count", "current_device", "get_device_capability",
    "get_device_properties", "get_device_name", "mem_get_info",
)
SCENARIOS = ("all", "warmup-auth-failure", "warmup-timeout")
FAULT_MARKER = b"F1S_AUTHENTICATED_WARMUP_FAULT_REACHED\n"


class FixtureFailure(Exception):
    """Only fixed diagnostic codes may leave this helper."""


def require(condition, code):
    if not condition:
        raise FixtureFailure(code)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise FixtureFailure("arguments_invalid")


def parse_options(argv):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--actual-image", action="store_true", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--internal-scenario", choices=SCENARIOS, default="all",
                        help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def no_secret(value, sentinel):
    # Never put a failed comparison or the checked data in an assertion message.
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    require(sentinel.encode("ascii") not in raw, "sentinel_disclosure")


def verify_sources(repo):
    require(sys.platform == "linux", "linux_pinned_image_required")
    require(repo.is_absolute() and repo.resolve() == repo, "repository_path_invalid")
    evidence = repo / "reports/f1s-contract-evidence"
    expected = json.loads((evidence / "installed-static.json").read_text())
    for package, version in expected["packages"].items():
        require(importlib.metadata.version(package) == version, "installed_version_mismatch")
    spec = importlib.util.find_spec("sglang")
    require(spec is not None and spec.origin is not None, "installed_sglang_missing")
    source_root = Path(spec.origin).resolve().parent
    require(not source_root.is_relative_to(repo), "repository_sglang_substitution_refused")
    for name, identity in expected["source_files"].items():
        path = source_root / name
        require(path.is_file() and path.stat().st_size == identity["bytes"],
                "installed_source_size_mismatch")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == identity["sha256"],
                "installed_source_hash_mismatch")
    provenance = json.loads((evidence / "launcher-provenance.json").read_text())
    require(provenance["path"] == "scripts/lifecycle/sglang_file_auth.py"
            and provenance["image_id"] == IMAGE_ID, "launcher_provenance_invalid")
    launcher_path = repo / provenance["path"]
    require(hashlib.sha256(launcher_path.read_bytes()).hexdigest() == provenance["sha256"],
            "launcher_source_hash_mismatch")
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

    This preserves native argument parsing and all ServerArgs normalization.
    The exact mocked public torch.cuda probes are recorded in the final result.
    Their answers describe synthetic 96GiB SM120 devices, not detected hardware.
    """
    properties = SimpleNamespace(name="F1S synthetic device", total_memory=96 * 2**30,
                                 major=12, minor=0, multi_processor_count=1)
    values = {"is_available": True, "device_count": 2, "current_device": 0,
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
             "server": ("127.0.0.1", 30003), "client": ("127.0.0.1", 12345)}
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

    def __init__(self, server_args, server):
        self.server_args = server_args
        self.server_status = server.ServerStatus.Starting
        self.gracefully_exit = False
        self.is_generation = True
        self.served_model_name = ALIAS
        self.model_path = "/models"
        self.model_config = SimpleNamespace(context_len=32768,
            is_image_understandable_model=False, is_audio_understandable_model=False,
            hf_config=SimpleNamespace(model_type="qwen3_next", architectures=["Qwen3NextForCausalLM"]))
        self.socket_mapping = SimpleNamespace(clear_all_sockets=lambda: None)
        self.rid_to_state = {}
        self.last_receive_tstamp = 0
        self.disconnect_mode = False
        self.disconnect_seen = False
        self.generation_calls = 0
        self.diagnostic_calls = 0

    async def get_internal_state(self):
        self.diagnostic_calls += 1
        return [{"f1s_fixture_worker": True}]

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
            require(valid, "warmup_header_missing_or_wrong")
            if mode in ("timeout", "auth-failure"):
                # Fixed nonsecret evidence distinguishes the intended abort
                # from an unrelated native process exiting with the same code.
                os.write(1, FAULT_MARKER)
            if mode == "timeout":
                time.sleep(2)
            if mode == "auth-failure":
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

    server = ThreadingHTTPServer(("127.0.0.1", 30003), Handler)
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
            return JSONResponse({"id": "f1s-fixture-chat", "object": "chat.completion",
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
                require(data["id"] == "f1s-fixture-chat" and chat.calls == before_chat + 1,
                        "native_chat_handler_not_reached")
            else:
                require(data["api_key"] is None and data["admin_api_key"] is None
                        and data["model_path"] == "/models"
                        and data["internal_states"] == [{"f1s_fixture_worker": True}]
                        and tokenizer.diagnostic_calls == before_diagnostics + 1,
                        "native_diagnostic_handler_not_reached")
            no_secret(payload, sentinel)
            no_secret(messages, sentinel)
        for token in (None, wrong, sentinel):
            status, _, _ = await asgi_request(app, "/__f1s/admin-force", token)
            require(status == 403, "native_admin_force_not_denied")
            for path in ("/health_f1s_probe", "/metrics_f1s_probe"):
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


def run_actual(repo, scenario, captured_logs):
    launcher_path = verify_sources(repo)
    spec = importlib.util.spec_from_file_location("f1s_actual_image_launcher", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher.validate_environment()
    import torch
    with cuda_discovery_fixture(torch):
        from transformers import AutoConfig
        # Native model-config parsing is real. These deliberately tiny metadata
        # values are synthetic and are never mistaken for acquired model files.
        model_config = AutoConfig.for_model("qwen3_next", architectures=["Qwen3NextForCausalLM"],
                                            max_position_embeddings=32768)
        config_bytes = model_config.to_json_string().encode()
        from sglang.srt.entrypoints import http_server as server
        from sglang.srt.server_args import ServerArgs
        from sglang.srt.utils import auth
        from starlette.responses import JSONResponse
        require(server.app.__class__.__module__.startswith("fastapi"), "actual_fastapi_required")
        require(dataclasses.is_dataclass(ServerArgs), "actual_server_args_required")
        with fixture_files(config_bytes) as sentinel:
            wrong = secrets.token_urlsafe(32)
            require(wrong != sentinel, "fixture_randomness_failure")
            argv = ["--key-file", str(KEY_PATH), "--warmup-timeout", "600"] + [
                item for pair in launcher.FIXED_FLAGS.items() for item in pair]
            no_secret(argv, sentinel)
            no_secret(os.environ, sentinel)
            no_secret(sys.argv, sentinel)
            with patch.object(os, "open", side_effect=FixtureFailure("spawn_import_read_file")):
                imported = runpy.run_path(str(launcher_path), run_name="__mp_main__")
            require("main" in imported, "spawn_import_failed")

            @auth.auth_level(auth.AuthLevel.ADMIN_FORCE)
            async def forced():
                raise FixtureFailure("admin_force_handler_reached")

            async def public_probe():
                return JSONResponse({"f1s_fixture_probe": True})

            # Fixture routes exercise the native ADMIN_FORCE layering branch and
            # prefix exemptions without replacing any production route.
            server.app.add_api_route("/__f1s/admin-force", forced, methods=["GET"], include_in_schema=False)
            for path in ("/health_f1s_probe", "/metrics_f1s_probe"):
                server.app.add_api_route(path, public_probe, methods=["GET"], include_in_schema=False)
            engine_calls, captured = [], []

            def engine_start(**kwargs):
                args = kwargs["server_args"]
                launcher.validate_server_args(args)
                require(type(args) is ServerArgs, "native_server_args_replaced")
                no_secret(repr(args), sentinel)
                no_secret(dataclasses.asdict(args), sentinel)
                no_secret(pickle.dumps(args), sentinel)
                # Engine/model startup is synthetic; exercise the exact type's
                # repr with the installed engine logger without executing CUDA.
                logging.getLogger("sglang.srt.entrypoints.engine").warning("server_args=%r", args)
                tokenizer = SyntheticTokenizer(args, server)
                engine_calls.append((args, tokenizer))
                return tokenizer, SimpleNamespace(), SimpleNamespace(), SimpleNamespace(scheduler_infos=[{}]), None

            def capture_uvicorn(app, **kwargs):
                captured.append(app)
                require(app is server.app and app.server_args is engine_calls[-1][0],
                        "native_global_application_not_retained")
                require(kwargs["host"] == "0.0.0.0" and kwargs["port"] == 30003
                        and "workers" not in kwargs, "unexpected_uvicorn_launch_mode")
                layers = [m for m in app.user_middleware
                          if getattr(m.cls, "__name__", "") == "_ApiKeyASGIMiddleware"]
                require(len(layers) == 2 and sum(m.kwargs.get("api_key") is None for m in layers) == 1,
                        "final_native_auth_layering_missing")
                no_secret(repr(app.user_middleware), sentinel)
                if scenario == "all":
                    check_routes(server, app, engine_calls[-1][1], sentinel, wrong)
                mode = {"all": "success", "warmup-auth-failure": "auth-failure",
                        "warmup-timeout": "timeout"}[scenario]
                with warmup_http_server(sentinel, mode) as calls:
                    server._wait_and_warmup(**app.warmup_thread_kwargs)
                    require(scenario == "all", "failed_warmup_returned_without_process_exit")
                    require(calls == [("GET", "/model_info", True), ("POST", "/generate", True)],
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
                result = launcher.main(argv)
            require(result == 0 and len(captured) == 1 and len(engine_calls) == 1,
                    "actual_native_launch_setup_failed")
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
                with patch.object(auth, "add_api_key_middleware", return_value=None), \
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
            "injection_failure_child_cleanup": "PASS", "spawn_import": "PASS"}


def run_failure_children(repo):
    # Each case has an independent exclusively created synthetic key/config.
    # os._exit in the real launcher skips finally; remove only owned fixture
    # files after the child is gone, never accept a preexisting file.
    for scenario in SCENARIOS[1:]:
        require(not KEY_PATH.exists() and not CONFIG_PATH.exists(), "fixture_files_not_clean")
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--actual-image",
                                 "--repo", str(repo), "--internal-scenario", scenario],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=180, check=False)
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
            require(sock.connect_ex(("127.0.0.1", 30003)) != 0,
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
                result = run_actual(options.repo, options.internal_scenario, log_capture)
            finally:
                logging.getLogger().removeHandler(handler)
        if options.internal_scenario != "all":
            raise FixtureFailure("expected_abort_not_observed")
        run_failure_children(options.repo)
        result.update(status="PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE", image_id_pin=IMAGE_ID,
                      image_identity_verification="HOST_DOCKER_INSPECT_REQUIRED",
                      hardware_discovery_stubs=list(HARDWARE_STUBS),
                      warmup_failure_and_timeout_cleanup="PASS",
                      model_loading="STUBBED_NOT_TESTED", gpu_execution="NOT_TESTED",
                      native_lifespan_model_serving_initialization="NOT_TESTED",
                      live_inference_and_agent_acceptance="NOT_TESTED")
        print(json.dumps(result, sort_keys=True))
        return 0
    except BaseException as error:
        if isinstance(error, SystemExit) and error.code == 0:
            return 0
        # Deliberate abort children terminate via os._exit after one fixed marker.
        # An ordinary exception in those children must be distinguishable from
        # that success condition without emitting any captured backend data.
        print(json.dumps({"status": "FAIL", "code": "actual_image_fixture_failed"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
