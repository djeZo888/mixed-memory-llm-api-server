#!/usr/bin/env python3
"""Pinned SGLang 0.5.14 single-tokenizer launcher with file-backed native auth.

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


LOGGER = logging.getLogger("llmctl.sglang_file_auth")
STARTUP_TIMEOUT = 7200
# Public Config.Env metadata for the exact image recorded in launcher provenance:
# sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3
# Absence remains allowed; never infer/inject defaults. Image identity and exact
# inherited environment are separately enforced by the lifecycle manager.
BUILD_METADATA = {
    "SGLANG_BUILD_COMMIT": "49e384ce9d304648e9959666ecb8ce8cd98d0deb",
    "SGLANG_BUILD_URL": "https://github.com/sgl-project/sglang/actions/runs/28210048245",
    "SGLANG_IMAGE_TAG": "lmsysorg/sglang:v0.5.14",
}
FIXED_FLAGS = {
    "--model-path": "/models",
    "--served-model-name": "qwen3-coder-next",
    "--host": "0.0.0.0",
    "--port": "30003",
    "--context-length": "32768",
    "--tp-size": "2",
    "--tokenizer-worker-num": "1",
    "--tool-call-parser": "qwen3_coder",
    "--mem-fraction-static": "0.75",
    "--max-running-requests": "1",
    "--load-format": "safetensors",
}


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
    for flag in FIXED_FLAGS:
        parser.add_argument(flag, required=True)
    # Reject duplicate options instead of argparse's last-value-wins behavior.
    if len(argv) != len(set(argv[::2])) * 2 and argv not in (["--help"], ["-h"]):
        raise LaunchError("launch_arguments_invalid")
    options = parser.parse_args(argv)
    if (options.key_file != "/run/secrets/llm-api-key"
            or options.warmup_timeout != "600"
            or any(getattr(options, flag[2:].replace("-", "_")) != value
                   for flag, value in FIXED_FLAGS.items())):
        raise LaunchError("launch_arguments_invalid")
    return options, [piece for pair in FIXED_FLAGS.items() for piece in pair]


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


def validate_environment():
    # The pinned image supplies all libraries. Runtime environment switches must
    # not open a second gRPC listener or activate plugin/alternate launch paths.
    if any(name.startswith("SGLANG_")
           and (name not in BUILD_METADATA or value != BUILD_METADATA[name])
           for name, value in os.environ.items()):
        raise LaunchError("launch_environment_invalid")
    if os.environ.get("DISABLE_OPENAPI_DOC") != "1":
        raise LaunchError("launch_environment_invalid")
    try:
        if importlib.metadata.version("sglang") != "0.5.14":
            raise LaunchError("launch_version_invalid")
    except importlib.metadata.PackageNotFoundError:
        raise LaunchError("launch_version_invalid") from None
    points = importlib.metadata.entry_points()
    groups = points.groups if hasattr(points, "groups") else points.keys()
    if any(group.lower().startswith("sglang") for group in groups):
        raise LaunchError("launch_plugins_unsupported")


def validate_server_args(args):
    required = {
        "api_key": None, "admin_api_key": None,
        "tokenizer_worker_num": 1, "host": "0.0.0.0", "port": 30003,
        "model_path": "/models", "served_model_name": "qwen3-coder-next",
        "context_length": 32768, "tp_size": 2, "tool_call_parser": "qwen3_coder",
        "mem_fraction_static": 0.75, "max_running_requests": 1,
        "load_format": "safetensors", "dp_size": 1, "nnodes": 1,
        "node_rank": 0, "base_gpu_id": 0, "gpu_id_step": 1,
        "disaggregation_mode": "null",
    }
    missing = object()
    if any(getattr(args, field, missing) != value for field, value in required.items()):
        raise LaunchError("server_arguments_invalid")
    # Some defaults are optional on patched distributions; any enabled value is
    # refused. Required pin-critical fields above must actually be present.
    disabled = (
        "use_ray", "grpc_mode", "encoder_only", "enable_http2", "enable_ssl_refresh",
        "ssl_certfile", "ssl_keyfile", "ssl_ca_certs", "ssl_keyfile_password",
        "tool_server", "warmups", "skip_server_warmup", "skip_tokenizer_init",
        "trust_remote_code", "enable_trace", "enable_metrics", "reload",
        "fastapi_root_path", "debug_tensor_dump_input_file", "delete_ckpt_after_loading",
        "checkpoint_engine_wait_weights_before_ready", "enable_elastic_expert_backup",
        "remote_instance_weight_loader_start_seed_via_transfer_engine",
    )
    if any(getattr(args, field, None) for field in disabled):
        raise LaunchError("server_mode_unsupported")
    if getattr(args, "quantization", None) not in (None, "fp8"):
        raise LaunchError("server_arguments_invalid")
    if getattr(args, "tokenizer_path", None) not in (None, "/models"):
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
        validate_environment()
        from sglang.srt.server_args import prepare_server_args
        from sglang.srt.entrypoints import http_server
        from sglang.srt.utils import kill_process_tree
        from sglang.srt.utils.auth import add_api_key_middleware

        cleanup = kill_process_tree
        server_args = prepare_server_args(backend_argv)
        validate_server_args(server_args)
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
        # warmup. Never call the stock launcher/plugin/Ray dispatch wrapper.
        http_server.launch_server(server_args, execute_warmup_func=warmup)
        return 0
    except Exception:
        LOGGER.error("sglang_file_auth_launch_failed")
        return 1
    finally:
        if watchdog is not None:
            watchdog.cancel()
            watchdog.join()
        if cleanup is not None:
            try:
                cleanup(os.getpid(), include_parent=False)
            except Exception:
                LOGGER.error("sglang_file_auth_cleanup_failed")


if __name__ == "__main__":
    raise SystemExit(main())
