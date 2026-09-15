"""Synthetic auth behavior with AST-extracted installed source, no GPU/runtime.

The actual installed launch/setup and native middleware bodies run unchanged.
FastAPI/Starlette-compatible small doubles provide middleware ordering, routes,
requests and responses; worker startup and Uvicorn are stubs. F1D must repeat
against the actual pinned Linux image before using a real key.
"""

import asyncio
import ast
import contextlib
import dataclasses
import hashlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import runpy
import secrets
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/lifecycle"))
import sglang_file_auth as launcher
import runtime_io

FIXTURE = Path(__file__).with_name("sglang_fixture")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


native_auth = load_module("f1s_native_auth_fixture", FIXTURE / "auth_native.py")


def args_fixture():
    values = {
        "api_key": None, "admin_api_key": None, "tokenizer_worker_num": 1,
        "host": "0.0.0.0", "port": 30003, "model_path": "/models",
        "served_model_name": "qwen3-coder-next", "context_length": 32768,
        "tp_size": 2, "tool_call_parser": "qwen3_coder", "mem_fraction_static": 0.75,
        "max_running_requests": 1, "load_format": "safetensors", "dp_size": 1,
        "nnodes": 1, "node_rank": 0, "base_gpu_id": 0, "gpu_id_step": 1,
        "disaggregation_mode": "null", "enable_metrics": False,
        "ssl_certfile": None, "ssl_keyfile": None, "ssl_ca_certs": None,
        "ssl_keyfile_password": None, "enable_http2": False,
        "enable_ssl_refresh": False, "fastapi_root_path": "",
        "log_level": "info", "log_level_http": None, "skip_server_warmup": False,
        "delete_ckpt_after_loading": False, "debug_tensor_dump_input_file": None,
        "checkpoint_engine_wait_weights_before_ready": False,
    }
    cls = dataclasses.make_dataclass("FixtureServerArgs", [(k, object, dataclasses.field(default=v))
                                                           for k, v in values.items()])
    cls.describe_kv_events_publisher = lambda self: None
    return cls()


def cli():
    return ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600"] + [
        item for pair in launcher.FIXED_FLAGS.items() for item in pair]


class Response:
    def __init__(self, content, status_code=200):
        self.content, self.status_code = content, status_code

    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": self.status_code, "headers": []})
        await send({"type": "http.response.body", "body": json.dumps(self.content).encode()})


class Request:
    def __init__(self, scope, receive=None):
        self.url = types.SimpleNamespace(path=scope["path"])
        self.method = scope["method"]
        self.headers = {k.decode().title(): v.decode() for k, v in scope["headers"]}


class Route:
    def __init__(self, path, endpoint):
        self.path, self.endpoint = path, endpoint

    def matches(self, scope):
        return (1, {"endpoint": self.endpoint}) if scope["path"] == self.path else (0, {})


class App:
    """Minimal ASGI stack with Starlette add_middleware insert(0) ordering."""

    def __init__(self):
        self.routes, self.user_middleware = [], []
        self.router = types.SimpleNamespace(routes=self.routes)
        self.state = types.SimpleNamespace()
        self.middleware_stack = None
        self.calls = []
        self.events = []

    def add_middleware(self, cls, **kwargs):
        if self.middleware_stack is not None:
            raise RuntimeError("already_started")
        self.user_middleware.insert(0, types.SimpleNamespace(cls=cls, kwargs=kwargs))

    async def dispatch(self, scope, receive, send):
        self.calls.append(scope["path"])
        route = next((r for r in self.routes if r.path == scope["path"]), None)
        if route is None:
            return await Response({"error": "not_found"}, 404)(scope, receive, send)
        if scope["path"] == "/stream":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            self.events.append(await receive())
            await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
            self.events.append(await receive())
            await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})
            return
        result = await route.endpoint()
        await Response(result)(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if self.middleware_stack is None:
            current = self.dispatch
            for layer in reversed(self.user_middleware):
                current = layer.cls(current, **layer.kwargs)
            self.middleware_stack = current
        await self.middleware_stack(scope, receive, send)


def native_modules():
    return {
        "fastapi": types.ModuleType("fastapi"),
        "fastapi.responses": types.SimpleNamespace(ORJSONResponse=Response),
        "starlette": types.ModuleType("starlette"),
        "starlette.requests": types.SimpleNamespace(Request=Request),
        "starlette.routing": types.SimpleNamespace(Match=types.SimpleNamespace(FULL=1)),
        "sglang.srt.utils.auth": native_auth,
    }


def source_server(args):
    """Run installed launch_server -> _setup_and_run_http_server -> Uvicorn capture."""
    server = types.ModuleType("f1s_http_fixture")
    app = App()
    token_manager = types.SimpleNamespace(server_args=args, server_status="Starting")

    async def internal_state():
        return [{"synthetic": True}]

    token_manager.get_internal_state = internal_state
    captured, worker_args = [], []

    def start_workers(**kwargs):
        worker_args.append(dataclasses.asdict(kwargs["server_args"]))
        logging.getLogger("fixture_engine").info("server_args=%r", kwargs["server_args"])
        return token_manager, object(), object(), types.SimpleNamespace(scheduler_infos=[{}]), object()

    server.__dict__.update({
        "app": app, "dataclasses": dataclasses, "__version__": "0.5.14",
        "logger": logging.getLogger("fixture_http"),
        "_GlobalState": lambda **kwargs: types.SimpleNamespace(**kwargs),
        "set_global_state": lambda value: setattr(server, "_global_state", value),
        "app_has_admin_force_endpoints": native_auth.app_has_admin_force_endpoints,
        "set_uvicorn_logging_configs": lambda value: None,
        "envs": types.SimpleNamespace(SGLANG_TIMEOUT_KEEP_ALIVE=types.SimpleNamespace(get=lambda: 5)),
        "uvicorn": types.SimpleNamespace(run=lambda app, **kwargs: captured.append((app, kwargs))),
        "Engine": types.SimpleNamespace(_launch_subprocesses=start_workers),
        "init_tokenizer_manager": None, "run_scheduler_process": None,
        "run_detokenizer_process": None, "_execute_server_warmup": lambda value: None,
        "ServerStatus": types.SimpleNamespace(Up="Up"),
    })
    exec(compile((FIXTURE / "http_native.py").read_text(), "installed_source_http_fixture", "exec"), server.__dict__)

    async def ordinary():
        return {"routed": True, "model": args.served_model_name}

    @native_auth.auth_level(native_auth.AuthLevel.ADMIN_FORCE)
    async def admin():
        return {"should_not_run": True}

    for path in ("/v1/models", "/v1/chat/completions", "/health", "/health_generate",
                 "/health_extra", "/metrics", "/metrics_extra", "/stream", "/v1/realtime"):
        app.routes.append(Route(path, ordinary))
    app.routes.extend([Route("/admin", admin), Route("/server_info", server.server_info),
                       Route("/get_server_info", server.get_server_info)])
    server.captured, server.worker_args = captured, worker_args
    return server


async def request(app, path, key=None, method="GET", websocket=False, events=None):
    scope = {"type": "websocket" if websocket else "http", "path": path, "method": method,
             "headers": [] if key is None else [(b"authorization", ("Bearer " + key).encode())]}
    queued = list(events or [{"type": "http.request", "body": b""}])
    received = []

    async def receive():
        return queued.pop(0)

    async def send(message):
        received.append(message)

    await app(scope, receive, send)
    return received


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.sentinel = secrets.token_hex(32)
        self.logs = io.StringIO()
        self.handler = logging.StreamHandler(self.logs)
        logging.getLogger().addHandler(self.handler)
        self.old_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.INFO)
        self.module_patch = mock.patch.dict(sys.modules, native_modules())
        self.module_patch.start()

    def tearDown(self):
        self.module_patch.stop()
        logging.getLogger().removeHandler(self.handler)
        logging.getLogger().setLevel(self.old_level)
        self.assertTrue(self.sentinel not in self.logs.getvalue(), "generated key leaked in logs")

    def no_leak(self, value):
        self.assertTrue(self.sentinel not in str(value), "generated key leaked")

    def launch_fixture(self):
        args = args_fixture()
        server = source_server(args)
        launcher.install_auth(server, native_auth.add_api_key_middleware, launcher._PrivateKey(self.sentinel))
        callback = object()
        server.launch_server(args, execute_warmup_func=callback)
        self.assertIs(server.captured[0][0], server.app)
        self.assertIs(server.app.warmup_thread_kwargs["execute_warmup_func"], callback)
        self.assertIs(server.app.server_args, args)
        self.assertEqual(len(server.app.user_middleware), 3)
        self.no_leak(repr(args))
        self.no_leak(dataclasses.asdict(args))
        self.no_leak(server.worker_args)
        return server

    def test_final_native_chain_routes_and_server_info(self):
        server = self.launch_fixture()
        for path in ("/v1/models", "/v1/chat/completions", "/server_info", "/get_server_info"):
            for kind, key in (("missing", None), ("wrong", "incorrect"), ("correct", self.sentinel)):
                with self.subTest(path=path, kind=kind):
                    before = len(server.app.calls)
                    messages = asyncio.run(request(server.app, path, key, "POST" if "chat" in path else "GET"))
                    self.assertEqual(messages[0]["status"], 200 if kind == "correct" else 401)
                    self.assertEqual(len(server.app.calls) - before, 1 if kind == "correct" else 0)
                    self.no_leak(messages)
                    if kind == "correct":
                        payload = json.loads(messages[1]["body"])
                        if "server_info" in path:
                            self.assertIsNone(payload["api_key"])
                            self.assertIsNone(payload["admin_api_key"])
                            self.assertEqual(payload["model_path"], "/models")
                        else:
                            self.assertIs(payload["routed"], True)

    def test_native_probe_exemptions_admin_force_and_websockets(self):
        server = self.launch_fixture()
        for path in ("/health", "/health_generate", "/health_extra", "/metrics", "/metrics_extra"):
            self.assertEqual(asyncio.run(request(server.app, path))[0]["status"], 200)
        for path in ("/v1/models", "/admin"):
            self.assertEqual(asyncio.run(request(server.app, path, method="OPTIONS"))[0]["status"], 200)
        for key in (None, "incorrect", self.sentinel):
            self.assertEqual(asyncio.run(request(server.app, "/admin", key))[0]["status"], 403)
            self.assertEqual(asyncio.run(request(server.app, "/v1/realtime", key, websocket=True)),
                             [{"type": "websocket.close", "code": 1008}])

    def test_native_sse_disconnect_events_unchanged(self):
        server = self.launch_fixture()
        events = [{"type": "http.request", "body": b"", "more_body": False}, {"type": "http.disconnect"}]
        messages = asyncio.run(request(server.app, "/stream", self.sentinel, events=events))
        self.assertEqual(server.app.events, events)
        self.assertEqual([m["body"] for m in messages[1:]], [b"data: first\n\n", b"data: [DONE]\n\n"])
        self.no_leak(messages)

    def test_duplicate_and_started_app_refusal(self):
        server = self.launch_fixture()
        for mode in ("duplicate", "started"):
            if mode == "started":
                server.app = App()
                server.app.middleware_stack = object()
            with self.assertRaisesRegex(launcher.LaunchError, "auth_installation_invalid"):
                launcher.install_auth(server, native_auth.add_api_key_middleware, self.sentinel)

    def test_noop_wrong_key_app_and_missing_websocket_registration_refused(self):
        for mode in ("noop", "wrong_key", "wrong_app", "missing_websocket", "ui"):
            with self.subTest(mode=mode):
                server = source_server(args_fixture())
                key = launcher._PrivateKey(self.sentinel)

                def inject(app, **kwargs):
                    if mode == "noop":
                        return
                    if mode == "wrong_key":
                        kwargs["api_key"] = "incorrect"
                    native_auth.add_api_key_middleware(app, **kwargs)
                    if mode == "wrong_app":
                        app.user_middleware[0].kwargs["fastapi_app"] = App()

                inject.__module__ = native_auth.add_api_key_middleware.__module__
                if mode == "missing_websocket":
                    original_add = server.app.add_middleware
                    server.app.add_middleware = lambda cls, **kw: None if cls is launcher.RejectWebSockets else original_add(cls, **kw)
                if mode == "ui":
                    server.app.routes.append(Route("/docs", lambda: None))
                with self.assertRaises(launcher.LaunchError):
                    launcher.install_auth(server, inject, key)
                self.assertFalse(server.captured)

    def test_key_exact_bytes_match_d2_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key"
            for raw in (self.sentinel.encode(), b"a", b"x" * 4096, b"", b"a\n", b"a\r\n", b"a b", b"a\0", b"\xff", b"x" * 4097):
                path.write_bytes(raw)
                path.chmod(0o600)
                original = path.read_bytes()
                valid = bool(raw) and len(raw) <= 4096 and all(33 <= byte <= 126 for byte in raw)
                if valid:
                    self.assertTrue(launcher.read_key(path) == runtime_io._read_key(path), "key contract differs")
                else:
                    for reader, error in ((launcher.read_key, launcher.LaunchError), (runtime_io._read_key, runtime_io.LifecycleError)):
                        with self.assertRaises(error) as raised:
                            reader(path)
                        self.no_leak(str(raised.exception))
                self.assertTrue(path.read_bytes() == original, "protected file changed")
            path.write_bytes(self.sentinel.encode())
            path.chmod(0o644)
            with self.assertRaises(launcher.LaunchError):
                launcher.read_key(path)
            path.chmod(0o600)
            link = Path(directory) / "link"
            link.symlink_to(path)
            for invalid in (link, Path(directory)):
                with self.assertRaises(launcher.LaunchError):
                    launcher.read_key(invalid)
            meta = path.stat()
            with mock.patch.object(launcher.os, "fstat", return_value=types.SimpleNamespace(
                    st_mode=meta.st_mode, st_size=meta.st_size, st_uid=987654321)):
                with self.assertRaises(launcher.LaunchError):
                    launcher.read_key(path)
            self.no_leak(repr(launcher.read_key(path)))

    def test_strict_options_and_sanitized_unknown_values(self):
        self.assertEqual(launcher.parse_options(cli())[1], cli()[4:])
        for flag in ("--api-key", "--config", "--admin-api-key", "--tool-server", "--grpc-mode", "--use-ray", "--reload"):
            with self.assertRaises(launcher.LaunchError) as raised:
                launcher.parse_options(cli() + [flag, self.sentinel])
            self.no_leak(str(raised.exception))
        for flag in launcher.FIXED_FLAGS:
            changed = cli()
            changed[changed.index(flag) + 1] = "unsupported"
            with self.assertRaises(launcher.LaunchError):
                launcher.parse_options(changed)
        with self.assertRaises(launcher.LaunchError):
            launcher.parse_options(cli() + ["--host", "0.0.0.0"])

    def test_postparse_modes_and_secret_fields_refused(self):
        launcher.validate_server_args(args_fixture())
        for field, value in (("api_key", self.sentinel), ("admin_api_key", self.sentinel),
                             ("tokenizer_worker_num", 2), ("use_ray", True), ("grpc_mode", True),
                             ("encoder_only", True), ("enable_http2", True), ("enable_ssl_refresh", True),
                             ("tool_server", "demo"), ("reload", True), ("skip_server_warmup", True),
                             ("trust_remote_code", True), ("nnodes", 2), ("base_gpu_id", 1)):
            with self.subTest(field=field):
                args = args_fixture()
                setattr(args, field, value)
                with self.assertRaises(launcher.LaunchError):
                    launcher.validate_server_args(args)

    def test_secondary_listener_environment_and_plugins_refused(self):
        with mock.patch.dict(os.environ, {"SGLANG_ENABLE_GRPC": "1"}):
            with self.assertRaises(launcher.LaunchError):
                launcher.validate_environment()
        with mock.patch.dict(os.environ, {"DISABLE_OPENAPI_DOC": "1"}, clear=True), mock.patch.object(launcher.importlib.metadata, "version", return_value="0.5.14"), mock.patch.object(launcher.importlib.metadata, "entry_points", return_value={"sglang_plugins": []}):
            with self.assertRaises(launcher.LaunchError):
                launcher.validate_environment()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(launcher.LaunchError):
                launcher.validate_environment()
        with mock.patch.dict(os.environ, {"DISABLE_OPENAPI_DOC": "1"}, clear=True), mock.patch.object(launcher.importlib.metadata, "version", return_value="other"):
            with self.assertRaises(launcher.LaunchError):
                launcher.validate_environment()

    def test_spawn_import_is_inert(self):
        with mock.patch.object(launcher.os, "open", side_effect=AssertionError("key read during import")), mock.patch.dict(os.environ, {}, clear=True):
            child = runpy.run_path(str(ROOT / "scripts/lifecycle/sglang_file_auth.py"), run_name="__mp_main__")
        self.assertIn("main", child)
        self.no_leak(cli())
        self.no_leak(os.environ)

    def test_warmup_success_only_up_and_stock_callback_preserved(self):
        server = self.launch_fixture()
        abort, ready = mock.Mock(), mock.Mock()
        responses = [(200, {"is_generation": True}), (200, {"text": "ok", "meta_info": {"completion_tokens": 1}})]
        warmup = launcher.make_warmup(server, self.sentinel, abort, ready, time.monotonic() + 5)
        with mock.patch.object(launcher, "_request", side_effect=responses) as calls:
            server._wait_and_warmup(server.app.server_args, execute_warmup_func=warmup)
        self.assertEqual(server._global_state.tokenizer_manager.server_status, "Up")
        self.assertEqual([c.args[2] for c in calls.call_args_list], ["/model_info", "/generate"])
        self.assertEqual(calls.call_args_list[1].args[-1]["sampling_params"]["max_new_tokens"], 1)
        self.assertTrue(all(c.args[3] == self.sentinel for c in calls.call_args_list), "warmup not authenticated")
        abort.assert_not_called()
        ready.assert_called_once()

    def test_warmup_failure_timeout_and_no_ready_callback(self):
        for mode in ("auth", "generation", "exception", "timeout"):
            with self.subTest(mode=mode):
                server = self.launch_fixture()
                abort, ready, launch_callback = mock.Mock(), mock.Mock(), mock.Mock()
                responses = {"auth": [(401, None)], "generation": [(200, {"is_generation": True}), (500, None)],
                             "exception": [RuntimeError(self.sentinel)], "timeout": []}[mode]
                deadline = time.monotonic() - 1 if mode == "timeout" else time.monotonic() + 5
                warmup = launcher.make_warmup(server, self.sentinel, abort, ready, deadline)
                with mock.patch.object(launcher, "_request", side_effect=responses):
                    server._wait_and_warmup(server.app.server_args, launch_callback=launch_callback, execute_warmup_func=warmup)
                self.assertEqual(server._global_state.tokenizer_manager.server_status, "Starting")
                abort.assert_called_once()
                ready.assert_not_called()
                launch_callback.assert_not_called()

    def test_http_helper_auth_no_proxy_redirect_and_bounded_payload_and_time(self):
        verified = []
        expected = self.sentinel

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                verified.append((self.path, self.headers.get("Authorization") == "Bearer " + expected))
                status = 302 if self.path == "/redirect" else 200
                body = (b"x" * 65537) if self.path == "/large" else b'{"is_generation":true}'
                if self.path == "/slow":
                    time.sleep(0.15)
                try:
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    if status == 302:
                        self.send_header("Location", "/must-not-follow")
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass

        # HTTPServer otherwise performs reverse-DNS even on a literal address.
        with mock.patch("socket.getfqdn", return_value="localhost"):
            http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1"}):
                self.assertEqual(launcher._request(http.server_port, "GET", "/model_info", expected, time.monotonic() + 2),
                                 (200, {"is_generation": True}))
                self.assertEqual(launcher._request(http.server_port, "GET", "/redirect", expected, time.monotonic() + 2), (302, None))
                with self.assertRaises(launcher.LaunchError):
                    launcher._request(http.server_port, "GET", "/large", expected, time.monotonic() + 2)
                start = time.monotonic()
                with self.assertRaises(Exception):
                    launcher._request(http.server_port, "GET", "/slow", expected, start + 0.03)
                self.assertLess(time.monotonic() - start, 0.3)
            self.assertTrue(all(authenticated for path, authenticated in verified), "request authentication missing")
            self.assertFalse(any(path == "/must-not-follow" for path, authenticated in verified))
        finally:
            http.shutdown()
            http.server_close()
            worker.join()

    def test_main_injection_failure_closes_children_without_launch(self):
        server = source_server(args_fixture())
        cleanup = mock.Mock()
        modules = {
            "sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"),
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=lambda argv: args_fixture()),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
            "sglang.srt.utils.auth": types.SimpleNamespace(add_api_key_middleware=mock.Mock(side_effect=RuntimeError(self.sentinel))),
        }
        with mock.patch.dict(sys.modules, modules), mock.patch.object(launcher, "validate_environment"), mock.patch.object(launcher, "read_key", return_value=launcher._PrivateKey(self.sentinel)):
            self.assertEqual(launcher.main(cli()), 1)
        cleanup.assert_called_once_with(os.getpid(), include_parent=False)
        self.assertFalse(server.captured)

    def test_main_noop_injection_closes_children_without_launch(self):
        server = source_server(args_fixture())
        cleanup = mock.Mock()
        modules = {
            "sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"),
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=lambda argv: args_fixture()),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
            "sglang.srt.utils.auth": types.SimpleNamespace(add_api_key_middleware=lambda app, **kwargs: None),
        }
        with mock.patch.dict(sys.modules, modules), mock.patch.object(launcher, "validate_environment"), mock.patch.object(launcher, "read_key", return_value=launcher._PrivateKey(self.sentinel)):
            self.assertEqual(launcher.main(cli()), 1)
        cleanup.assert_called_once_with(os.getpid(), include_parent=False)
        self.assertFalse(server.captured)

    def test_startup_watchdog_fails_closed(self):
        class SimulatedExit(BaseException):
            pass

        timers, alive = [], []

        class Timer:
            def __init__(self, interval, callback):
                self.interval, self.callback = interval, callback
                timers.append(self)

            def start(self):
                pass

            def cancel(self):
                pass

            def join(self):
                pass

        server = source_server(args_fixture())

        def launch(*args, **kwargs):
            alive.append("worker")
            timers[0].callback()

        server.launch_server = launch
        cleanup = mock.Mock(side_effect=lambda *args, **kwargs: alive.clear())
        modules = {
            "sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"),
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=lambda argv: args_fixture()),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
        }
        with mock.patch.dict(sys.modules, modules), mock.patch.object(launcher, "validate_environment"), mock.patch.object(launcher, "read_key", return_value=launcher._PrivateKey(self.sentinel)), mock.patch.object(launcher.threading, "Timer", Timer), mock.patch.object(launcher.os, "_exit", side_effect=SimulatedExit) as exit_call:
            with self.assertRaises(SimulatedExit):
                launcher.main(cli())
        self.assertEqual(timers[0].interval, 7200)
        self.assertFalse(alive)
        exit_call.assert_called_once_with(1)
        self.assertEqual(cleanup.call_count, 2)

    def test_main_direct_launch_finally_cleans_up_and_canonical_args(self):
        server = source_server(args_fixture())
        cleanup, prepared = mock.Mock(), []

        def prepare(argv):
            prepared.append(argv)
            return args_fixture()

        modules = {
            "sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"),
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=prepare),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
        }
        with mock.patch.dict(sys.modules, modules), mock.patch.object(launcher, "validate_environment"), mock.patch.object(launcher, "read_key", return_value=launcher._PrivateKey(self.sentinel)):
            self.assertEqual(launcher.main(cli()), 0)
        self.assertIs(server.captured[0][0], server.app)
        self.no_leak(prepared)
        self.no_leak(server.worker_args)
        cleanup.assert_called_once_with(os.getpid(), include_parent=False)

    def test_fixture_provenance_hashes(self):
        manifest = json.loads((FIXTURE / "provenance.json").read_text())
        self.assertEqual(manifest["version"], "0.5.14")
        for name, source in manifest["sources"].items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), source["fixture_sha256"])
            installed = ROOT.parent / "sglang-source" / source["installed_path"].replace("/", "__")
            if installed.exists():
                self.assertEqual(hashlib.sha256(installed.read_bytes()).hexdigest(), source["source_sha256"])
                original_nodes = {node.name: node for node in ast.parse(installed.read_text()).body
                                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                fixture_nodes = {node.name: node for node in ast.parse((FIXTURE / name).read_text()).body
                                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                for selected in source["names"]:
                    original, extracted = original_nodes[selected], fixture_nodes[selected]
                    # Route decorators are wired by fixture App, function bodies
                    # and all control flow must remain exact installed-source AST.
                    original.decorator_list = []
                    extracted.decorator_list = []
                    self.assertEqual(ast.dump(original), ast.dump(extracted))


if __name__ == "__main__":
    unittest.main()
