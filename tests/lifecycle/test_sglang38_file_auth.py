"""Bounded source-only auth tests; never evidence of actual-image/inference PASS.

The pinned native middleware source runs on a small ASGI harness. SGLang engine,
resolution and transports in launcher-order tests are explicit synthetic doubles.
The separate actual-image fixture must repeat the gate with native dependencies.
"""
import asyncio
import copy
import dataclasses
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
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


launcher = load("q38_source_launcher", ROOT / "scripts/runtime/sglang38_file_auth.py")
native = load("q38_source_native_auth", Path(__file__).with_name("sglang38_fixture") / "auth_native.py")


def cli(context=131072):
    return ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600"] + launcher.backend_argv(context)


def args_fixture(context=131072):
    values = {
        "api_key": None, "admin_api_key": None, "tokenizer_worker_num": 1,
        "host": "0.0.0.0", "port": 30004, "model_path": "/models",
        "served_model_name": "qwen3.8-27b", "context_length": context,
        "max_total_tokens": context, "tp_size": 1, "tool_call_parser": "qwen3_coder",
        "reasoning_parser": "qwen3", "default_chat_template_kwargs": {"enable_thinking": False},
        "mem_fraction_static": 0.8, "max_running_requests": 1, "load_format": "safetensors",
        "quantization": "fp8", "dtype": "bfloat16", "kv_cache_dtype": "bfloat16",
        "attention_backend": "flashinfer", "linear_attn_backend": "triton",
        "fp8_gemm_runner_backend": "cutlass", "chunked_prefill_size": 2048,
        "max_mamba_cache_size": 1, "mamba_radix_cache_strategy": "no_buffer",
        "disable_radix_cache": True, "disable_overlap_schedule": True,
        "mamba_ssm_dtype": "float32", "download_dir": "/cache/downloads",
        "file_storage_path": "/cache/storage", "dp_size": 1, "pp_size": 1,
        "nnodes": 1, "node_rank": 0, "base_gpu_id": 0, "gpu_id_step": 1,
        "disaggregation_mode": "null", "model_loader_extra_config": "{}",
        "json_model_override_args": "{}", "cuda_graph_backend_decode": "disabled",
        "cuda_graph_backend_prefill": "disabled", "tokenizer_path": "/models",
    }
    for name in (
        "use_ray grpc_mode smg_grpc_mode grpc_port grpc_worker_threads sidecar sidecar_args "
        "encoder_only enable_http2 enable_ssl_refresh ssl_certfile ssl_keyfile ssl_ca_certs "
        "ssl_keyfile_password tool_server warmups skip_server_warmup skip_tokenizer_init "
        "trust_remote_code enable_trace enable_metrics log_requests fastapi_root_path "
        "debug_tensor_dump_input_file delete_ckpt_after_loading checkpoint_engine_wait_weights_before_ready "
        "enable_elastic_expert_backup remote_instance_weight_loader_start_seed_via_transfer_engine "
        "speculative_algorithm speculative_draft_model_path enable_hierarchical_cache hicache_storage_backend "
        "radix_cache_backend enable_session_radix_cache enable_int8_mamba_checkpoint enable_unified_memory "
        "enable_lora lora_paths forward_hooks"
    ).split():
        values[name] = None
    values["cuda_graph_config"] = types.SimpleNamespace(
        decode=types.SimpleNamespace(backend="disabled"), prefill=types.SimpleNamespace(backend="disabled"))
    cls = dataclasses.make_dataclass("SyntheticServerArgs", [(key, object) for key in values])
    cls.resolve_once = lambda self: None
    cls.resolved_dict = lambda self: dataclasses.asdict(self)
    return cls(**values)


class App:
    def __init__(self):
        self.user_middleware = []
        self.middleware_stack = None
        self.routes = []
        self.router = types.SimpleNamespace(routes=self.routes)
        self.events = []
        self.calls = []

    def add_middleware(self, cls, **kwargs):
        self.user_middleware.insert(0, types.SimpleNamespace(cls=cls, kwargs=kwargs))

    async def dispatch(self, scope, receive, send):
        self.calls.append(scope["path"])
        self.events.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"data: synthetic\n\n", "more_body": True})
        self.events.append(await receive())
        await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})

    async def __call__(self, scope, receive, send):
        stack = self.dispatch
        for layer in reversed(self.user_middleware):
            stack = layer.cls(stack, **layer.kwargs)
        await stack(scope, receive, send)


class Request:
    def __init__(self, scope, receive=None):
        self.url = types.SimpleNamespace(path=scope["path"])
        self.method = scope["method"]
        self.headers = {key.decode().title(): value.decode() for key, value in scope["headers"]}


class Response:
    def __init__(self, content, status_code=200):
        self.content, self.status_code = content, status_code

    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": self.status_code, "headers": []})
        await send({"type": "http.response.body", "body": json.dumps(self.content).encode()})


def synthetic_dependencies():
    return mock.patch.dict(sys.modules, {
        "fastapi.responses": types.SimpleNamespace(ORJSONResponse=Response),
        "starlette.requests": types.SimpleNamespace(Request=Request),
        "starlette.routing": types.SimpleNamespace(Match=types.SimpleNamespace(FULL=1)),
    })


def request(app, path, key=None, method="GET", scope_type="http"):
    events = []
    scope = {"type": scope_type, "path": path, "method": method,
             "headers": [] if key is None else [(b"authorization", ("Bearer " + key).encode())]}
    pending = [{"type": "http.request", "body": b"", "more_body": False}, {"type": "http.disconnect"}]

    async def receive():
        return pending.pop(0)

    async def send(event):
        events.append(event)

    asyncio.run(app(scope, receive, send))
    return events


class Q38LauncherSourceTests(unittest.TestCase):
    def setUp(self):
        self.key = launcher._PrivateKey(secrets.token_urlsafe(32))

    def test_exact_context_variants_share_fixed_identity(self):
        for context in (131072, 262144):
            options, actual = launcher.parse_options(cli(context))
            self.assertEqual(actual, launcher.backend_argv(context))
            self.assertEqual(options.max_total_tokens, str(context))
            self.assertEqual(options.served_model_name, "qwen3.8-27b")
            self.assertEqual(options.default_chat_template_kwargs, '{"enable_thinking":false}')
            launcher.validate_server_args(args_fixture(context))

    def test_other_contexts_and_wrong_types_fail(self):
        for context in (0, 32768, 131071, 262145, "131072", True):
            with self.subTest(context=context), self.assertRaises(launcher.LaunchError):
                launcher.backend_argv(context)

    def test_every_fixed_value_rejects_mutation(self):
        for flag in launcher.FIXED_FLAGS:
            changed = cli()
            changed[changed.index(flag) + 1] = "unreviewed"
            with self.subTest(flag=flag), self.assertRaises(launcher.LaunchError):
                launcher.parse_options(changed)

    def test_context_and_pool_must_match(self):
        changed = cli()
        changed[changed.index("--max-total-tokens") + 1] = "262144"
        with self.assertRaises(launcher.LaunchError):
            launcher.parse_options(changed)

    def test_unknown_duplicate_missing_abbreviated_equals_modes_refused(self):
        for suffix in (["--api-key", str(self.key)], ["--grpc-port", "30005"], ["--tool-server", "demo"],
                       ["--config", "/tmp/a"], ["--context-length", "131072"],
                       ["--disable-radix-cache"], ["--port=30004"], ["--po", "30004"]):
            with self.subTest(suffix=suffix[:1]), self.assertRaises(launcher.LaunchError):
                launcher.parse_options(cli() + suffix)
        with self.assertRaises(launcher.LaunchError):
            launcher.parse_options(cli()[:-1])
        with self.assertRaises(launcher.LaunchError):
            launcher.parse_options(cli() + ["--host"])

    def test_help_is_available_without_runtime(self):
        with mock.patch("sys.stdout", new=io.StringIO()) as output, self.assertRaises(SystemExit) as stopped:
            launcher.parse_options(["--help"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn("--context-length", output.getvalue())

    def test_native_environment_exact_cache_and_build_values(self):
        env = {**launcher.CACHE_ENVIRONMENT, **launcher.BUILD_METADATA, "HOME": "/root", "FLASHINFER_VERSION": "0.6.18"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), mock.patch.object(launcher.importlib.metadata, "entry_points", return_value={}):
            launcher.validate_environment()
            self.assertEqual(os.environ["HOME"], "/root")
            self.assertEqual(dict(os.environ), env)

    def test_each_cache_missing_or_changed_refused(self):
        for name in launcher.CACHE_ENVIRONMENT:
            for value in (None, "/tmp/escape"):
                env = dict(launcher.CACHE_ENVIRONMENT)
                if value is None:
                    env.pop(name)
                else:
                    env[name] = value
                with self.subTest(name=name, value=value), mock.patch.dict(os.environ, env, clear=True), self.assertRaises(launcher.LaunchError):
                    launcher.validate_environment()

    def test_unknown_environment_and_metadata_changes_fail_before_imports(self):
        bad = {"SGLANG_GRPC_PORT": "30005", "SGLANG_PLUGINS": "demo", "SGLANG_RUST_SERVER": "1",
               "HF_TOKEN": "synthetic", "HF_ENDPOINT": "https://example.invalid", "XDG_CONFIG_HOME": "/tmp",
               "FLASHINFER_WORKSPACE_BASE": "/tmp", "FLASHINFER_JIT_DIR": "/tmp", "CUDA_CACHE_PATH": "/tmp",
               "TRITON_CACHE_DIR": "/root", "PYTHONPATH": "/tmp", "LD_PRELOAD": "/tmp/a", "API_KEY": "synthetic",
               "FLASHINFER_VERSION": "wrong", **{name: "changed" for name in launcher.BUILD_METADATA}}
        for name, value in bad.items():
            with self.subTest(name=name), mock.patch.dict(os.environ, {**launcher.CACHE_ENVIRONMENT, name: value}, clear=True), self.assertRaises(launcher.LaunchError):
                launcher.validate_environment()

    def test_runtime_version_and_installed_plugins_refused(self):
        with mock.patch.dict(os.environ, launcher.CACHE_ENVIRONMENT, clear=True):
            for version, groups in (("0.5.14", {}), ("0.5.19", {"sglang.srt.plugins": [object()]}), ("0.5.19", {"sglang.srt.platforms": [object()]})):
                with self.subTest(version=version, groups=list(groups)), mock.patch.object(launcher.importlib.metadata, "version", return_value=version), mock.patch.object(launcher.importlib.metadata, "entry_points", return_value=groups), self.assertRaises(launcher.LaunchError):
                    launcher.validate_environment()

    def test_raw_identity_and_unsafe_modes_fail(self):
        bad = {"api_key": self.key, "admin_api_key": self.key, "context_length": 32768, "max_total_tokens": 262144,
               "tp_size": 2, "base_gpu_id": 1, "host": "127.0.0.1", "port": 30003,
               "tool_call_parser": "generic", "reasoning_parser": None, "tokenizer_worker_num": 2,
               "grpc_port": 30005, "smg_grpc_mode": True, "sidecar": "example", "use_ray": True,
               "enable_http2": True, "tool_server": "demo", "skip_server_warmup": True,
               "enable_trace": True, "log_requests": True, "trust_remote_code": True,
               "default_chat_template_kwargs": {"enable_thinking": True}, "download_dir": "/tmp",
               "file_storage_path": "relative", "max_mamba_cache_size": 2, "kv_cache_dtype": "fp8_e4m3",
               "disable_radix_cache": False, "disable_overlap_schedule": False, "speculative_algorithm": "EAGLE",
               "model_loader_extra_config": '{"plugin":"example"}', "json_model_override_args": '{"rope_scaling":{}}'}
        for name, value in bad.items():
            args = args_fixture()
            setattr(args, name, value)
            with self.subTest(name=name), self.assertRaises(launcher.LaunchError):
                launcher.validate_server_args(args)

    def test_missing_mode_field_fails_closed(self):
        args = args_fixture()
        del args.grpc_port
        with self.assertRaises(launcher.LaunchError):
            launcher.validate_server_args(args)

    def test_resolved_graphs_validated_separately(self):
        args = args_fixture()
        launcher.validate_server_args(args, resolved=True)
        for phase in ("decode", "prefill"):
            bad = copy.deepcopy(args)
            getattr(bad.cuda_graph_config, phase).backend = "full"
            with self.subTest(phase=phase), self.assertRaises(launcher.LaunchError):
                launcher.validate_server_args(bad, resolved=True)

    def test_resolution_cannot_introduce_key_or_change_identity(self):
        raw = args_fixture()
        for field, value in (("api_key", self.key), ("admin_api_key", self.key), ("context_length", 262144), ("grpc_port", 30005)):
            projected = copy.deepcopy(raw)
            setattr(projected, field, value)
            with self.subTest(field=field), mock.patch.dict(sys.modules, {"sglang.srt.arg_groups.overrides": types.SimpleNamespace(resolving_view=lambda args: projected)}), self.assertRaises(launcher.LaunchError):
                launcher.validate_resolved_server_args(raw)
        projected = copy.deepcopy(raw)
        raw.resolved_dict = lambda: {"api_key": self.key, "admin_api_key": None}
        with mock.patch.dict(sys.modules, {"sglang.srt.arg_groups.overrides": types.SimpleNamespace(resolving_view=lambda args: projected)}), self.assertRaises(launcher.LaunchError):
            launcher.validate_resolved_server_args(raw)

    def test_protected_file_and_safe_repr(self):
        with tempfile.TemporaryDirectory() as temp:
            keyfile = Path(temp, "key")
            keyfile.write_text(str(self.key))
            keyfile.chmod(0o600)
            result = launcher.read_key(keyfile)
            self.assertEqual(str(result), str(self.key))
            self.assertNotIn(str(self.key), repr(result))
            self.assertNotIn(str(self.key), repr({"key": result}))

    def test_key_file_modes_symlink_fifo_empty_whitespace_oversize_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "key")
            for payload, mode in ((b"", 0o600), (b"a\n", 0o600), (b"a b", 0o600), (b"\xff", 0o600), (b"a" * 4097, 0o600), (b"safe", 0o644)):
                path.write_bytes(payload)
                path.chmod(mode)
                with self.subTest(length=len(payload), mode=mode), self.assertRaises(launcher.LaunchError):
                    launcher.read_key(path)
            link = Path(temp, "link")
            link.symlink_to(path)
            with self.assertRaises(launcher.LaunchError):
                launcher.read_key(link)
            fifo = Path(temp, "fifo")
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(launcher.LaunchError):
                launcher.read_key(fifo)

    def test_spawn_import_is_inert(self):
        with mock.patch("os.open", side_effect=AssertionError("key read on import")):
            values = runpy.run_path(str(ROOT / "scripts/runtime/sglang38_file_auth.py"), run_name="__mp_main__")
        self.assertIn("main", values)

    def test_native_auth_ordinary_routes_missing_wrong_correct(self):
        app = App()
        server = types.SimpleNamespace(app=app)
        with synthetic_dependencies():
            launcher.install_auth(server, native.add_api_key_middleware, self.key)
            # Native setup installs this second empty-key layer on same app.
            native.add_api_key_middleware(app, api_key=None, admin_api_key=None)
            for path in ("/v1/models", "/v1/chat/completions", "/model_info", "/generate", "/server_info", "/get_server_info"):
                for key, expected in ((None, 401), ("wrong", 401), (self.key, 200)):
                    with self.subTest(path=path, authenticated=key is self.key):
                        events = request(app, path, key)
                        self.assertEqual(events[0]["status"], expected)
                        self.assertNotIn(str(self.key), repr(events))

    def test_native_probe_prefix_and_options_exceptions_explicit(self):
        app = App()
        with synthetic_dependencies():
            launcher.install_auth(types.SimpleNamespace(app=app), native.add_api_key_middleware, self.key)
            for path, method in (("/health", "GET"), ("/health_generate", "GET"), ("/metrics", "GET"), ("/metrics_anything", "GET"), ("/server_info", "OPTIONS")):
                self.assertEqual(request(app, path, method=method)[0]["status"], 200)

    def test_native_admin_force_denied(self):
        @native.auth_level(native.AuthLevel.ADMIN_FORCE)
        def sensitive():
            pass
        app = App()
        app.routes.append(types.SimpleNamespace(endpoint=sensitive, matches=lambda scope: (1, {"endpoint": sensitive})))
        with synthetic_dependencies():
            launcher.install_auth(types.SimpleNamespace(app=app), native.add_api_key_middleware, self.key)
            for key in (None, "wrong", self.key):
                self.assertEqual(request(app, "/sensitive", key)[0]["status"], 403)

    def test_websocket_rejected_even_with_correct_key(self):
        app = App()
        with synthetic_dependencies():
            launcher.install_auth(types.SimpleNamespace(app=app), native.add_api_key_middleware, self.key)
            for key in (None, self.key):
                self.assertEqual(request(app, "/v1/realtime", key, scope_type="websocket"), [{"type": "websocket.close", "code": 1008}])
        self.assertEqual(app.calls, [])

    def test_sse_body_and_disconnect_preserved(self):
        app = App()
        with synthetic_dependencies():
            launcher.install_auth(types.SimpleNamespace(app=app), native.add_api_key_middleware, self.key)
            events = request(app, "/v1/chat/completions", self.key, method="POST")
        self.assertEqual([event["body"] for event in events[1:]], [b"data: synthetic\n\n", b"data: [DONE]\n\n"])
        self.assertEqual(app.events[-1], {"type": "http.disconnect"})

    def test_already_started_installed_or_documentation_app_refused(self):
        for mode in ("started", "installed", "docs"):
            app = App()
            if mode == "started":
                app.middleware_stack = object()
            elif mode == "installed":
                app._llmctl_file_auth_installed = True
            else:
                app.routes.append(types.SimpleNamespace(path="/openapi.json"))
            with self.subTest(mode=mode), self.assertRaises(launcher.LaunchError):
                launcher.install_auth(types.SimpleNamespace(app=app), native.add_api_key_middleware, self.key)

    def test_wrong_native_middleware_identity_refused(self):
        app = App()
        with self.assertRaises(launcher.LaunchError):
            launcher.install_auth(types.SimpleNamespace(app=app), lambda app, **kwargs: None, self.key)
        self.assertTrue(app._llmctl_file_auth_installed)

    def test_warmup_authenticates_both_calls_then_marks_ready(self):
        state = types.SimpleNamespace(server_status="Starting")
        server = types.SimpleNamespace(_global_state=types.SimpleNamespace(tokenizer_manager=state), ServerStatus=types.SimpleNamespace(Up="Up"))
        ready, abort = mock.Mock(), mock.Mock()
        with mock.patch.object(launcher, "_request", side_effect=[(200, {"is_generation": True}), (200, {"text": "x", "meta_info": {"completion_tokens": 1}})]) as transport:
            call = launcher.make_warmup(server, self.key, abort, ready, time.monotonic() + 5)
            self.assertTrue(call(args_fixture()))
        self.assertEqual(state.server_status, "Up")
        ready.assert_called_once_with()
        abort.assert_not_called()
        self.assertEqual([c.args[2] for c in transport.call_args_list], ["/model_info", "/generate"])
        self.assertTrue(all(c.args[3] is self.key for c in transport.call_args_list))

    def test_warmup_failure_keeps_starting_and_emits_only_safe_log(self):
        cases = [[(401, None)], [(403, None)], [(200, {"is_generation": False})],
                 [(200, {"is_generation": True}), (200, {"text": "", "meta_info": {"completion_tokens": 0}})],
                 [RuntimeError(str(self.key))]]
        for responses in cases:
            state = types.SimpleNamespace(server_status="Starting")
            server = types.SimpleNamespace(_global_state=types.SimpleNamespace(tokenizer_manager=state), ServerStatus=types.SimpleNamespace(Up="Up"))
            ready, abort = mock.Mock(), mock.Mock()
            with self.subTest(kind=str(type(responses[0]))), mock.patch.object(launcher, "_request", side_effect=responses), self.assertLogs(launcher.LOGGER, logging.ERROR) as logs:
                self.assertFalse(launcher.make_warmup(server, self.key, abort, ready, time.monotonic() + 5)(args_fixture()))
            self.assertEqual(state.server_status, "Starting")
            ready.assert_not_called()
            abort.assert_called_once_with()
            self.assertNotIn(str(self.key), repr(logs.output))

    def test_warmup_expired_before_first_request_does_not_mark_ready(self):
        ready, abort = mock.Mock(), mock.Mock()
        with mock.patch.object(launcher, "_request") as transport, self.assertLogs(launcher.LOGGER, logging.ERROR):
            self.assertFalse(launcher.make_warmup(None, self.key, abort, ready, time.monotonic() - 1)(args_fixture()))
        ready.assert_not_called()
        abort.assert_called_once_with()
        transport.assert_not_called()

    def test_startup_validates_raw_and_resolved_before_key_and_cleans_up(self):
        order = []
        raw = args_fixture()
        server = types.SimpleNamespace(app=App())
        server.launch_server = lambda args, **kwargs: order.append(("launch", args, kwargs))
        cleanup = mock.Mock()
        modules = {
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=lambda argv: (order.append("prepare"), raw)[1]),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
            "sglang.srt.utils.auth": native,
        }
        with synthetic_dependencies(), mock.patch.dict(sys.modules, modules), mock.patch.object(launcher, "validate_environment", side_effect=lambda: order.append("environment")), mock.patch.object(launcher, "validate_server_args", side_effect=lambda args: order.append("raw")), mock.patch.object(launcher, "validate_resolved_server_args", side_effect=lambda args: order.append("resolved")), mock.patch.object(launcher, "read_key", side_effect=lambda path: (order.append("key"), self.key)[1]):
            self.assertEqual(launcher.main(cli()), 0)
        self.assertEqual(order[:5], ["environment", "prepare", "raw", "resolved", "key"])
        self.assertIs(order[5][1], raw)
        self.assertIs(server.app, server.app.user_middleware[-1].kwargs["fastapi_app"])
        self.assertNotIn(str(self.key), repr(raw))
        self.assertNotIn(str(self.key), repr(dataclasses.asdict(raw)))
        self.assertNotIn(str(self.key), repr(raw.resolved_dict()))
        cleanup.assert_called_once_with(os.getpid(), include_parent=False)

    def test_watchdog_aborts_children_and_parent_with_safe_cleanup(self):
        class SimulatedExit(BaseException):
            pass

        timers = []

        class Timer:
            def __init__(self, seconds, callback):
                self.seconds, self.callback = seconds, callback
                self.cancelled = False
                timers.append(self)

            def start(self):
                pass

            def cancel(self):
                self.cancelled = True

            def join(self):
                pass

        cleanup = mock.Mock()
        server = types.SimpleNamespace(app=App(), launch_server=lambda *args, **kwargs: timers[0].callback())
        modules = {
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=lambda argv: args_fixture()),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
            "sglang.srt.utils.auth": native,
        }
        with synthetic_dependencies(), mock.patch.dict(sys.modules, modules), mock.patch.object(launcher, "validate_environment"), mock.patch.object(launcher, "validate_resolved_server_args"), mock.patch.object(launcher, "read_key", return_value=self.key), mock.patch.object(launcher.threading, "Timer", Timer), mock.patch.object(launcher.os, "_exit", side_effect=SimulatedExit) as stopped:
            with self.assertRaises(SimulatedExit):
                launcher.main(cli())
        self.assertEqual(timers[0].seconds, 7200)
        self.assertTrue(timers[0].cancelled)
        stopped.assert_called_once_with(1)
        self.assertEqual(cleanup.call_args_list, [mock.call(os.getpid(), include_parent=False)] * 2)

    def test_startup_error_logs_do_not_include_sentinel(self):
        with mock.patch.object(launcher, "validate_environment", side_effect=RuntimeError(str(self.key))), self.assertLogs(launcher.LOGGER, logging.ERROR) as logs:
            self.assertEqual(launcher.main(cli()), 1)
        self.assertNotIn(str(self.key), repr(logs.output))
        self.assertEqual(logs.output, ["ERROR:llmctl.sglang38_file_auth:sglang38_file_auth_launch_failed"])


if __name__ == "__main__":
    unittest.main()
