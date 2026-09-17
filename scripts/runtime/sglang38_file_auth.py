#!/usr/bin/env python3
"""Pinned SGLang 0.5.19 raw/resolved single-tokenizer launcher with file-backed native auth.

Only main reads the key, installs middleware or launches workers. Spawn imports
are inert. The separately held key never enters ServerArgs, argv or environment.
This is a deliberately bounded adapter, not an alternative general SGLang CLI.
"""

from __future__ import annotations

import argparse
import http.client
import importlib.metadata
import json
import logging
import os
import socket
import stat
import sys
import threading
import time


LOGGER = logging.getLogger("llmctl.sglang38_file_auth")
STARTUP_TIMEOUT = 7200
SOURCE_COMMIT = "0bcd822377da7b5718e674eaf9c870d349424dd1"
IMAGE_REFERENCE = "lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262"
IMAGE_CONFIG_ID = "sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813"
CONTEXTS = (131072, 262144)
EXTENSION_CONTEXT = 1000000
ACCEPTED_CONTEXTS = (*CONTEXTS, EXTENSION_CONTEXT)
EXTENSION_OVERRIDE_JSON = ('{"text_config":{"rope_parameters":{"mrope_interleaved":true,'
    '"mrope_section":[11,11,10],"rope_type":"yarn","rope_theta":10000000,'
    '"partial_rotary_factor":0.25,"factor":4.0,"original_max_position_embeddings":262144}}}')
EXTENSION_ENVIRONMENT = {"SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN": "1"}
# Public OCI metadata, independently bound to IMAGE_REFERENCE in Q38 provenance.
# Absence is tolerated here for source harnesses; production reuse checks the
# complete exact inherited image environment in the lifecycle adapter.
BUILD_METADATA = {
    "SGLANG_RUST_BUILD_MODE": "never",
    "SGLANG_BUILD_COMMIT": SOURCE_COMMIT,
    "SGLANG_BUILD_URL": "https://github.com/sgl-project/sglang/actions/runs/33912440803",
    "SGLANG_IMAGE_TAG": "lmsysorg/sglang:v0.5.19",
}
CACHE_ENVIRONMENT = {
    "DISABLE_OPENAPI_DOC": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HOME": "/cache/huggingface",
    "XDG_CACHE_HOME": "/cache",
    # Pinned 0.5.19 has independent HOME defaults for these two roots.
    "SGLANG_CACHE_DIR": "/cache/sglang",
    "SGLANG_JIT_CACHE_DIR": "/cache/sglang/jit",
    "TRITON_CACHE_DIR": "/cache/triton",
    "TORCHINDUCTOR_CACHE_DIR": "/cache/torchinductor",
    "FLASHINFER_WORKSPACE_BASE": "/cache/flashinfer",
    "CUDA_CACHE_PATH": "/cache/cuda",
}
FIXED_FLAGS = {
    "--model-path": "/models",
    "--served-model-name": "qwen3.8-27b",
    "--host": "0.0.0.0",
    "--port": "30004",
    "--tp-size": "1",
    "--base-gpu-id": "0",
    "--gpu-id-step": "1",
    "--tokenizer-worker-num": "1",
    "--tool-call-parser": "qwen3_coder",
    "--reasoning-parser": "qwen3",
    "--default-chat-template-kwargs": '{"enable_thinking":false}',
    "--mem-fraction-static": "0.80",
    "--max-running-requests": "1",
    "--load-format": "safetensors",
    "--quantization": "fp8",
    "--dtype": "bfloat16",
    "--kv-cache-dtype": "bfloat16",
    "--attention-backend": "flashinfer",
    "--linear-attn-backend": "triton",
    "--fp8-gemm-backend": "cutlass",
    "--chunked-prefill-size": "2048",
    "--max-mamba-cache-size": "1",
    "--mamba-ssm-dtype": "float32",
    "--mamba-radix-cache-strategy": "no_buffer",
    "--cuda-graph-backend-decode": "disabled",
    "--cuda-graph-backend-prefill": "disabled",
    "--download-dir": "/cache/downloads",
    "--file-storage-path": "/cache/storage",
}
BOOLEAN_FLAGS = ("--disable-radix-cache", "--disable-overlap-schedule")


def backend_argv(context):
    """The three closed tuples; native defaults retain their exact argv."""
    if type(context) is not int or context not in ACCEPTED_CONTEXTS:
        raise LaunchError("launch_context_invalid")
    flags = dict(FIXED_FLAGS)
    if context == EXTENSION_CONTEXT:
        flags["--tp-size"] = "2"
        flags["--json-model-override-args"] = EXTENSION_OVERRIDE_JSON
    return ([piece for pair in flags.items() for piece in pair]
            + ["--context-length", str(context), "--max-total-tokens", str(context)]
            + list(BOOLEAN_FLAGS))


class LaunchError(Exception):
    """Generic operator-safe failure; never attach backend exception details."""


class _PrivateKey(str):
    def __repr__(self):
        return "<protected-key>"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LaunchError("launch_arguments_invalid") from None


def parse_options(argv):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--warmup-timeout", required=True)
    for flag in (*FIXED_FLAGS, "--context-length", "--max-total-tokens"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--json-model-override-args")
    for flag in BOOLEAN_FLAGS:
        parser.add_argument(flag, action="store_true", required=True)
    if argv not in (["--help"], ["-h"]):
        # Parse canonical token pairs ourselves first: --x=y, duplicate flags,
        # abbreviation, and positionals are deliberately outside this surface.
        seen = set()
        i = 0
        while i < len(argv):
            flag = argv[i]
            if flag in seen or flag not in (*FIXED_FLAGS, *BOOLEAN_FLAGS,
                    "--key-file", "--warmup-timeout", "--context-length", "--max-total-tokens",
                    "--json-model-override-args"):
                raise LaunchError("launch_arguments_invalid")
            seen.add(flag)
            i += 1 if flag in BOOLEAN_FLAGS else 2
        if i != len(argv):
            raise LaunchError("launch_arguments_invalid")
    options = parser.parse_args(argv)
    extension = options.context_length == str(EXTENSION_CONTEXT)
    expected_flags = {**FIXED_FLAGS, "--tp-size": "2" if extension else "1"}
    if (options.key_file != "/run/secrets/llm-api-key"
            or options.warmup_timeout != "600"
            or options.context_length not in tuple(str(value) for value in ACCEPTED_CONTEXTS)
            or options.max_total_tokens != options.context_length
            or options.json_model_override_args != (EXTENSION_OVERRIDE_JSON if extension else None)
            or any(getattr(options, flag[2:].replace("-", "_")) != value
                   for flag, value in expected_flags.items())):
        raise LaunchError("launch_arguments_invalid")
    return options, backend_argv(int(options.context_length))


def read_key(path):
    """Match A1/D2's owned mode0600 regular-file exact printable ASCII contract."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | getattr(os, "O_CLOEXEC", 0))
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) != 0o600
                or meta.st_uid not in (0, os.geteuid()) or not 1 <= meta.st_size <= 4096):
            raise LaunchError("key_file_invalid")
        raw = os.read(fd, 4097)
        if not 1 <= len(raw) <= 4096 or not all(33 <= byte <= 126 for byte in raw):
            raise LaunchError("key_file_invalid")
        return _PrivateKey(raw.decode("ascii"))
    except (OSError, ValueError, TypeError):
        raise LaunchError("key_file_invalid") from None
    finally:
        if fd is not None:
            os.close(fd)


def validate_environment(context=None):
    # Image metadata is not a runtime switch. Every other SGLANG name, plugin
    # group and cache/token override is refused before importing serving code.
    if context is not None and (type(context) is not int or context not in ACCEPTED_CONTEXTS):
        raise LaunchError("launch_context_invalid")
    extension = EXTENSION_ENVIRONMENT if context == EXTENSION_CONTEXT else {}
    for name, value in os.environ.items():
        if (name.startswith("SGLANG_") and BUILD_METADATA.get(name) != value
                and CACHE_ENVIRONMENT.get(name) != value and extension.get(name) != value):
            raise LaunchError("launch_environment_invalid")
        if (name.startswith(("HF_", "HUGGINGFACE_", "TRANSFORMERS_", "TRITON_",
                             "TORCHINDUCTOR_", "XDG_"))
                and CACHE_ENVIRONMENT.get(name) != value):
            raise LaunchError("launch_environment_invalid")
        if name.startswith("FLASHINFER_") and name != "FLASHINFER_VERSION" and CACHE_ENVIRONMENT.get(name) != value:
            raise LaunchError("launch_environment_invalid")
        if name.startswith("CUDA_CACHE_") and CACHE_ENVIRONMENT.get(name) != value:
            raise LaunchError("launch_environment_invalid")
        if name == "FLASHINFER_VERSION" and value != "0.6.18":
            raise LaunchError("launch_environment_invalid")
        if name in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "API_KEY",
                    "OPENAI_API_KEY", "ADMIN_API_KEY", "TOOL_SERVER"):
            raise LaunchError("launch_environment_invalid")
    if any(os.environ.get(name) != value for name, value in CACHE_ENVIRONMENT.items()):
        raise LaunchError("launch_environment_invalid")
    if any(os.environ.get(name) != value for name, value in extension.items()):
        raise LaunchError("launch_environment_invalid")
    try:
        if importlib.metadata.version("sglang") != "0.5.19":
            raise LaunchError("launch_version_invalid")
    except importlib.metadata.PackageNotFoundError:
        raise LaunchError("launch_version_invalid") from None
    points = importlib.metadata.entry_points()
    groups = points.groups if hasattr(points, "groups") else points.keys()
    if any(group.lower().startswith("sglang") for group in groups):
        raise LaunchError("launch_plugins_unsupported")


def validate_server_args(args, *, resolved=False):
    """Check raw input and independently check the exact resolved serving view."""
    context = getattr(args, "context_length", None)
    if (type(context) is not int or context not in ACCEPTED_CONTEXTS
            or getattr(args, "max_total_tokens", None) != context):
        raise LaunchError("server_arguments_invalid")
    extension = context == EXTENSION_CONTEXT
    required = {
        "api_key": None, "admin_api_key": None,
        "tokenizer_worker_num": 1, "host": "0.0.0.0", "port": 30004,
        "model_path": "/models", "served_model_name": "qwen3.8-27b",
        "tp_size": 2 if extension else 1, "tool_call_parser": "qwen3_coder", "reasoning_parser": "qwen3",
        "default_chat_template_kwargs": {"enable_thinking": False},
        "mem_fraction_static": 0.80, "max_running_requests": 1,
        "load_format": "safetensors", "quantization": "fp8", "dtype": "bfloat16",
        "kv_cache_dtype": "bfloat16", "attention_backend": "flashinfer",
        "linear_attn_backend": "triton", "fp8_gemm_runner_backend": "cutlass",
        "chunked_prefill_size": 2048, "max_mamba_cache_size": 1,
        "mamba_radix_cache_strategy": "no_buffer", "disable_radix_cache": True,
        "disable_overlap_schedule": True, "mamba_ssm_dtype": "float32",
        "download_dir": "/cache/downloads", "file_storage_path": "/cache/storage",
        "dp_size": 1, "pp_size": 1, "nnodes": 1, "node_rank": 0,
        "base_gpu_id": 0, "gpu_id_step": 1, "disaggregation_mode": "null",
        "model_loader_extra_config": "{}",
        "json_model_override_args": EXTENSION_OVERRIDE_JSON if extension else "{}",
    }
    if not resolved:
        required.update(cuda_graph_backend_decode="disabled", cuda_graph_backend_prefill="disabled")
    missing = object()
    if any(getattr(args, field, missing) != value for field, value in required.items()):
        raise LaunchError("server_arguments_invalid")
    # Required presence prevents a differently shaped/patched build silently
    # treating an unsupported launch mode as a default.
    disabled = (
        "use_ray", "grpc_mode", "smg_grpc_mode", "grpc_port",
        "sidecar", "sidecar_args", "encoder_only", "enable_http2", "enable_ssl_refresh",
        "ssl_certfile", "ssl_keyfile", "ssl_ca_certs", "ssl_keyfile_password",
        "tool_server", "warmups", "skip_server_warmup", "skip_tokenizer_init",
        "trust_remote_code", "enable_trace", "enable_metrics", "log_requests",
        "fastapi_root_path", "debug_tensor_dump_input_file", "delete_ckpt_after_loading",
        "checkpoint_engine_wait_weights_before_ready", "enable_elastic_expert_backup",
        "remote_instance_weight_loader_start_seed_via_transfer_engine", "speculative_algorithm",
        "speculative_draft_model_path", "enable_hierarchical_cache", "hicache_storage_backend",
        "radix_cache_backend", "enable_session_radix_cache", "enable_int8_mamba_checkpoint",
        "enable_unified_memory", "enable_lora", "lora_paths", "forward_hooks",
    )
    if any(getattr(args, field, missing) is missing or getattr(args, field) for field in disabled):
        raise LaunchError("server_mode_unsupported")
    # Pinned serving_hook always resolves the env-only worker count to 4,
    # including HTTP-only launches. It does not enable a gRPC mode or port.
    grpc_threads = getattr(args, "grpc_worker_threads", missing)
    if ((resolved and (type(grpc_threads) is not int or grpc_threads != 4))
            or (not resolved and grpc_threads is not None)):
        raise LaunchError("server_mode_unsupported")
    if getattr(args, "tokenizer_path", None) not in (None, "/models"):
        raise LaunchError("server_arguments_invalid")
    if resolved:
        graph = getattr(args, "cuda_graph_config", None)
        if any(getattr(getattr(graph, phase, None), "backend", None) != "disabled"
               for phase in ("decode", "prefill")):
            raise LaunchError("server_graph_invalid")


def validate_resolved_server_args(args):
    # prepare_server_args(0.5.19) returns raw input. Never insert secrets into the
    # record before OR after resolution: _raw_input, declarations, worker pickle,
    # dataclasses.asdict and /server_info's resolved_dict all retain configuration.
    from sglang.srt.arg_groups.overrides import resolving_view
    tuple_fields = ("context_length", "max_total_tokens", "tp_size", "base_gpu_id",
                    "gpu_id_step", "dtype", "kv_cache_dtype", "json_model_override_args")
    selected_tuple = tuple(getattr(args, field, None) for field in tuple_fields)
    args.resolve_once()
    validate_server_args(args)
    resolved = resolving_view(args)
    validate_server_args(resolved, resolved=True)
    if any(tuple(getattr(view, field, None) for field in tuple_fields) != selected_tuple
           for view in (args, resolved)):
        raise LaunchError("server_arguments_invalid")
    projected = args.resolved_dict()
    if not isinstance(projected, dict) or any(projected.get(name, "missing") is not None
            for name in ("api_key", "admin_api_key")):
        raise LaunchError("server_arguments_invalid")


class RejectWebSockets:
    """Do not expose the native auth helper's non-HTTP pass-through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)


def install_auth(http_server, add_api_key_middleware, key):
    app = http_server.app
    if getattr(app, "_llmctl_file_auth_installed", False) or getattr(app, "middleware_stack", None):
        raise LaunchError("auth_installation_invalid")
    if any(getattr(route, "path", None) in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")
           for route in app.routes):
        raise LaunchError("chat_only_application_invalid")
    before = list(app.user_middleware)
    if any(getattr(getattr(layer, "cls", None), "__name__", "") == "_ApiKeyASGIMiddleware"
           for layer in before):
        raise LaunchError("auth_installation_invalid")
    # Mark before injection: a partial failure must never be retried in-process.
    app._llmctl_file_auth_installed = True
    add_api_key_middleware(app, api_key=key, admin_api_key=None)
    after = app.user_middleware
    if len(after) != len(before) + 1 or after[1:] != before:
        raise LaunchError("auth_installation_invalid")
    layer = after[0]
    cls, kwargs = getattr(layer, "cls", None), getattr(layer, "kwargs", {})
    if (getattr(cls, "__qualname__", "") != "add_api_key_middleware.<locals>._ApiKeyASGIMiddleware"
            or getattr(cls, "__module__", None) != add_api_key_middleware.__module__
            or set(kwargs) != {"api_key", "admin_api_key", "fastapi_app"}
            or kwargs.get("api_key") is not key or kwargs.get("admin_api_key") is not None
            or kwargs.get("fastapi_app") is not app):
        raise LaunchError("auth_installation_invalid")
    before = list(after)
    app.add_middleware(RejectWebSockets)
    if (http_server.app is not app or len(app.user_middleware) != len(before) + 1
            or app.user_middleware[1:] != before
            or getattr(app.user_middleware[0], "cls", None) is not RejectWebSockets
            or getattr(app.user_middleware[0], "kwargs", None) != {}):
        raise LaunchError("auth_installation_invalid")


def _request(port, method, path, key, deadline, body=None):
    """Bound total response time/size; no proxies, redirects or diagnostic bodies."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LaunchError("warmup_timeout")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=min(5, remaining))
    timer = None
    try:
        conn.connect()
        connected = conn.sock

        def expire():
            try:
                connected.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
        timer.daemon = True
        timer.start()
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
                   "Connection": "close"}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        if conn.sock is not None:
            conn.sock.settimeout(max(0.001, deadline - time.monotonic()))
        response = conn.getresponse()
        if response.status != 200:
            return response.status, None
        payload = response.read(65537)
        if len(payload) > 65536 or time.monotonic() >= deadline:
            raise LaunchError("warmup_response_invalid")
        return response.status, json.loads(payload)
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        conn.close()


def make_warmup(http_server, key, abort, ready, startup_deadline, timeout=600):
    def execute_warmup(server_args):
        deadline = min(startup_deadline, time.monotonic() + timeout)
        try:
            while time.monotonic() < deadline:
                try:
                    status, info = _request(server_args.port, "GET", "/model_info", key, deadline)
                except (OSError, http.client.HTTPException):
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
                    continue
                if status in (401, 403):
                    raise LaunchError("warmup_auth_failed")
                if status == 200:
                    if not isinstance(info, dict) or info.get("is_generation") is not True:
                        raise LaunchError("warmup_model_invalid")
                    break
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            else:
                raise LaunchError("warmup_timeout")
            status, result = _request(server_args.port, "POST", "/generate", key, deadline,
                                      {"text": "Hello", "sampling_params": {
                                          "temperature": 0, "max_new_tokens": 1}, "stream": False})
            if (status != 200 or not isinstance(result, dict)
                    or not isinstance(result.get("text"), str)
                    or not isinstance(result.get("meta_info"), dict)
                    or result["meta_info"].get("completion_tokens", 0) < 1
                    or time.monotonic() >= deadline):
                raise LaunchError("warmup_generation_failed")
            http_server._global_state.tokenizer_manager.server_status = http_server.ServerStatus.Up
            ready()
            return True
        except Exception:
            LOGGER.error("authenticated_warmup_failed")
            abort()
            return False
    return execute_warmup


def main(argv=None):
    """Only guarded execution enters this function, including in spawn children."""
    cleanup = None
    watchdog = None
    try:
        options, backend_argv = parse_options(sys.argv[1:] if argv is None else argv)
        if int(options.context_length) == EXTENSION_CONTEXT:
            validate_environment(EXTENSION_CONTEXT)
        else:
            validate_environment()
        from sglang.srt.server_args import prepare_server_args
        from sglang.srt.entrypoints import http_server
        from sglang.srt.utils import kill_process_tree
        from sglang.srt.utils.auth import add_api_key_middleware

        cleanup = kill_process_tree
        server_args = prepare_server_args(backend_argv)
        validate_server_args(server_args)
        validate_resolved_server_args(server_args)
        key = read_key(options.key_file)
        install_auth(http_server, add_api_key_middleware, key)

        def abort():
            # Called from the warmup/watchdog thread: returning would leave an
            # unhealthy listener alive. Parent-process exit also stops container.
            try:
                cleanup(os.getpid(), include_parent=False)
            finally:
                os._exit(1)

        deadline = time.monotonic() + STARTUP_TIMEOUT
        watchdog = threading.Timer(STARTUP_TIMEOUT, abort)
        watchdog.daemon = True
        warmup = make_warmup(http_server, key, abort, watchdog.cancel, deadline,
                             timeout=int(options.warmup_timeout))
        watchdog.start()
        # This direct pinned hook retains the module-global app and custom
        # warmup. Never call the stock launcher/Ray dispatch wrapper. The
        # engine also calls load_plugins; preflight forbids every plugin group.
        http_server.launch_server(server_args, execute_warmup_func=warmup)
        return 0
    except Exception:
        LOGGER.error("sglang38_file_auth_launch_failed")
        return 1
    finally:
        if watchdog is not None:
            watchdog.cancel()
            watchdog.join()
        if cleanup is not None:
            try:
                cleanup(os.getpid(), include_parent=False)
            except Exception:
                LOGGER.error("sglang38_file_auth_cleanup_failed")


if __name__ == "__main__":
    raise SystemExit(main())
