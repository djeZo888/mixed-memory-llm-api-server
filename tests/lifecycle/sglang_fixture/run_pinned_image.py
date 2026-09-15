#!/usr/bin/env python3
"""Actual-image F1S authentication fixture, never a substitute for inference.

Run only in the reviewed disposable pinned image with no GPU, no network, a
readonly /fixture checkout, and empty private tmpfs mounts at /models and
/run/secrets. No production secret or model directory may be mounted.

The installed parser, ServerArgs.__post_init__, HTTP setup, native auth,
FastAPI/Starlette routes and response serializers run unchanged. Synthetic
collaborators replace CUDA discovery and engine/model/worker startup only.
Route cases capture Uvicorn.run; a separate disposable SIGINT case runs real
Uvicorn with lifespan="off" and synthetic engine descendants. Native lifespan
model-serving initialization is NOT_TESTED. A synthetic loopback HTTP server
exercises real authenticated warmup I/O. Abort/signal children use owned sessions,
bounded deadlines and survivor checks before emergency cleanup.

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
import selectors
import signal
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
SCENARIOS = ("all", "warmup-auth-failure", "warmup-timeout", "signal-int")
FAULT_MARKER = b"F1S_AUTHENTICATED_WARMUP_FAULT_REACHED\n"
SIGNAL_READY = b"F1E2_NATIVE_SIGNAL_READY\n"
SIGNAL_DONE = b"F1E2_NATIVE_SIGNAL_CLEANUP_PASS\n"
PROCESS_TIMEOUT = 180
PROCESS_TREE_CODE = """
import subprocess, sys
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(150)'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
print(p.pid, flush=True)
try:
    p.wait(timeout=150)
finally:
    if p.poll() is None:
        p.kill()
    p.wait()
"""


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


def read_process_output(child, *, until=None, timeout=PROCESS_TIMEOUT):
    """Drain private pipes with a deadline and limit; never relay child data."""
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for name in output:
            selector.register(getattr(child, name), selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            require(remaining > 0, "fixture_child_deadline")
            for key, _ in selector.select(min(remaining, 0.1)):
                data = os.read(key.fd, 4096)
                if not data:
                    selector.unregister(key.fileobj)
                else:
                    output[key.data].extend(data)
                    require(sum(map(len, output.values())) <= 65536,
                            "fixture_child_output_limit")
            if until is not None and bytes(output["stdout"]) == until:
                require(not output["stderr"], "fixture_child_unexpected_stderr")
                return bytes(output["stdout"]), bytes(output["stderr"])
    require(until is None, "fixture_child_not_ready")
    child.wait(timeout=max(0.01, deadline - time.monotonic()))
    return bytes(output["stdout"]), bytes(output["stderr"])


def wait_owned_group_gone(group, timeout=5):
    """Reap adopted fixture descendants (helper is container PID1), then check."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            while os.waitpid(-group, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            pass
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return
        require(time.monotonic() < deadline, "fixture_process_group_survived")
        time.sleep(0.02)


@contextmanager
def disposable_child(command):
    """Own a new session; emergency cleanup never establishes a test PASS."""
    child = subprocess.Popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    try:
        require(os.getpgid(child.pid) == child.pid, "fixture_child_session_invalid")
        yield child
    finally:
        # All fixture descendants inherit this group. No host/other test group
        # is signalled. This runs on timeout, unexpected output and exceptions.
        try:
            # Reap an already-exited leader before signalling its group (a
            # zombie-only group can otherwise raise EPERM on Darwin).
            child.poll()
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        finally:
            try:
                child.wait(timeout=5)
            finally:
                child.stdout.close()
                child.stderr.close()
        wait_owned_group_gone(child.pid)


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
        self.model_config_reads = 0
        self._model_config = SimpleNamespace(context_len=32768,
            is_image_understandable_model=False, is_audio_understandable_model=False,
            hf_config=SimpleNamespace(model_type="qwen3_next", architectures=["Qwen3NextForCausalLM"]))
        self.socket_mapping = SimpleNamespace(clear_all_sockets=lambda: None)
        self.rid_to_state = {}
        self.last_receive_tstamp = 0
        self.disconnect_mode = False
        self.disconnect_seen = False
        self.generation_calls = 0
        self.diagnostic_calls = 0

    @property
    def model_config(self):
        # model_info's first native statement reads this collaborator. Counting
        # that access observes handler entry without replacing/wrapping the
        # installed endpoint or FastAPI's generated request handler.
        self.model_config_reads += 1
        return self._model_config

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


async def check_model_info_route(server, app, tokenizer, sentinel, wrong):
    routes = [route for route in app.routes if getattr(route, "path", None) == "/model_info"]
    require(len(routes) == 1 and routes[0].methods == {"GET"}
            and routes[0].endpoint is server.model_info
            and routes[0].dependant.call is server.model_info,
            "native_model_info_route_wiring_missing")
    before = tokenizer.model_config_reads
    for token in (None, wrong):
        status, payload, messages = await asgi_request(app, "/model_info", token)
        require(status == 401, "native_model_info_auth_rejection_failed")
        require(tokenizer.model_config_reads == before,
                "unauthorized_model_info_reached_handler")
        no_secret(payload, sentinel)
        no_secret(messages, sentinel)
    status, payload, messages = await asgi_request(app, "/model_info", sentinel)
    require(status == 200 and tokenizer.model_config_reads == before + 1,
            "native_model_info_handler_not_reached")
    require(json.loads(payload) == {
        "model_path": "/models", "tokenizer_path": tokenizer.server_args.tokenizer_path,
        "is_generation": True,
        "preferred_sampling_params": tokenizer.server_args.preferred_sampling_params,
        "weight_version": tokenizer.server_args.weight_version,
        "has_image_understanding": False, "has_audio_understanding": False,
        "model_type": "qwen3_next", "architectures": ["Qwen3NextForCausalLM"],
    }, "native_model_info_response_changed")
    no_secret(payload, sentinel)
    no_secret(messages, sentinel)


@contextmanager
def negative_key_fixture(kind, sentinel):
    """Temporarily replace only our synthetic key; preserve its original inode.

    The enclosing fixture_files() has already verified the private tmpfs. A
    private exclusive directory parks the original; restoration is an exclusive
    link, so an unexpected replacement is never overwritten. Wrong ownership
    is tested only if the isolated container actually permits chown.
    """
    import tempfile

    original = KEY_PATH.lstat()
    require(stat.S_ISREG(original.st_mode) and original.st_uid == os.geteuid()
            and stat.S_IMODE(original.st_mode) == 0o600
            and KEY_PATH.read_bytes() == sentinel.encode("ascii"),
            "negative_fixture_key_identity_invalid")
    staging = Path(tempfile.mkdtemp(prefix=".f1e2-negative-", dir=KEY_PATH.parent))
    saved = staging / "original"
    identity = None
    moved = False
    try:
        os.rename(KEY_PATH, saved)
        moved = True
        require((saved.stat().st_dev, saved.stat().st_ino) ==
                (original.st_dev, original.st_ino), "negative_fixture_key_changed")
        allowed = True
        if kind == "missing":
            pass
        elif kind == "symlink":
            KEY_PATH.symlink_to(saved)
            identity = KEY_PATH.lstat()
        elif kind == "directory":
            KEY_PATH.mkdir(mode=0o700)
            identity = KEY_PATH.lstat()
        elif kind == "fifo":
            os.mkfifo(KEY_PATH, 0o600)
            identity = KEY_PATH.lstat()
        else:
            values = {"mode0644": sentinel.encode(), "mode0400": sentinel.encode(),
                      "mode0000": sentinel.encode(), "wrong-owner": sentinel.encode(),
                      "empty": b"", "newline": sentinel.encode() + b"\n",
                      "crlf": sentinel.encode() + b"\r\n",
                      "space": sentinel.encode() + b" ",
                      "nul": sentinel.encode() + b"\0", "nonascii": b"\xff",
                      "oversized": b"x" * 4097}
            require(kind in values, "negative_fixture_case_invalid")
            fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
            try:
                identity = os.fstat(fd)
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(values[kind])
                    stream.flush()
                mode = {"mode0644": 0o644, "mode0400": 0o400, "mode0000": 0o000}.get(kind, 0o600)
                os.fchmod(fd, mode)
                if kind == "wrong-owner":
                    rejected_uid = 65534 if os.geteuid() != 65534 else 65533
                    try:
                        os.fchown(fd, rejected_uid, -1)
                    except PermissionError:
                        # The reviewed --cap-drop ALL image normally cannot
                        # chown. No fstat mock or ownership PASS is substituted.
                        allowed = False
                    if allowed:
                        require(os.fstat(fd).st_uid not in (0, os.geteuid()),
                                "negative_fixture_owner_not_changed")
            finally:
                os.close(fd)
        yield allowed
    finally:
        if identity is not None:
            current = KEY_PATH.lstat()
            require((current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino),
                    "negative_fixture_case_identity_changed")
            if stat.S_ISDIR(current.st_mode):
                KEY_PATH.rmdir()
            else:
                KEY_PATH.unlink()
        if moved:
            # os.link refuses an existing destination, including a symlink.
            os.link(saved, KEY_PATH, follow_symlinks=False)
            saved.unlink()
        staging.rmdir()
        restored = KEY_PATH.lstat()
        require((restored.st_dev, restored.st_ino) == (original.st_dev, original.st_ino)
                and KEY_PATH.read_bytes() == sentinel.encode("ascii"),
                "negative_fixture_restore_failed")


def check_negative_contracts(launcher, server, ServerArgs, argv, sentinel):
    """Guard main with real native normalization and actual synthetic key files.

    prepare_server_args is only spied through, never replaced by a namespace or
    copied source. Disallowed normalized fields are explicit post-normalization
    fault injection. Auth installation and engine/listener entry are forbidden.
    """
    args_module = importlib.import_module("sglang.srt.server_args")
    native_prepare = args_module.prepare_server_args
    native_read = launcher.read_key
    require(args_module.ServerArgs is ServerArgs and dataclasses.is_dataclass(ServerArgs),
            "negative_native_server_args_required")
    outcomes = {"key_files": [], "cli_modes": [], "normalized_mode_faults": [],
                "wrong_owner": "NOT_TESTED_CAPABILITY_UNAVAILABLE"}

    def run_case(case_argv, *, key_case=False, fault=None):
        prepared, reads, accepted, boundaries, errors = [], [], [], [], []
        evidence = io.StringIO()

        def prepare(values):
            value = native_prepare(values)
            require(type(value) is ServerArgs, "negative_native_server_args_replaced")
            launcher.validate_server_args(value)
            if fault is not None:
                field, invalid = fault
                require(hasattr(value, field), "negative_native_mode_field_missing")
                setattr(value, field, invalid)
            for snapshot in (repr(value), dataclasses.asdict(value), pickle.dumps(value)):
                no_secret(snapshot, sentinel)
            prepared.append(value)
            return value

        def read(path):
            reads.append(True)
            result = native_read(path)
            accepted.append(True)
            return result

        def forbidden(*_args, **_kwargs):
            boundaries.append(True)
            raise FixtureFailure("negative_launch_boundary_reached")

        class Errors(logging.Handler):
            def emit(self, record):
                errors.append(record.getMessage())

        error_handler = Errors()
        native_handler = logging.StreamHandler(evidence)
        launcher.LOGGER.addHandler(error_handler)
        logging.getLogger().addHandler(native_handler)
        try:
            with ExitStack() as stack:
                stack.enter_context(redirect_stdout(evidence))
                stack.enter_context(redirect_stderr(evidence))
                stack.enter_context(patch.object(args_module, "prepare_server_args", side_effect=prepare))
                stack.enter_context(patch.object(launcher, "read_key", side_effect=read))
                stack.enter_context(patch.object(launcher, "install_auth", side_effect=forbidden))
                stack.enter_context(patch.object(server, "launch_server", side_effect=forbidden))
                stack.enter_context(patch.object(server.Engine, "_launch_subprocesses", side_effect=forbidden))
                stack.enter_context(patch.object(server.uvicorn, "run", side_effect=forbidden))
                result = launcher.main(case_argv)
        finally:
            launcher.LOGGER.removeHandler(error_handler)
            logging.getLogger().removeHandler(native_handler)
        require(result == 1 and not accepted and not boundaries,
                "negative_contract_not_refused_before_launch")
        require(len(prepared) == int(key_case or fault is not None)
                and len(reads) == int(key_case), "negative_contract_boundary_order_changed")
        require(errors == ["sglang_file_auth_launch_failed"], "negative_contract_output_changed")
        no_secret(evidence.getvalue(), sentinel)
        no_secret(case_argv, sentinel)
        no_secret(os.environ, sentinel)
        require(not getattr(server.app, "_llmctl_file_auth_installed", False)
                and not getattr(server.app, "middleware_stack", None),
                "negative_contract_modified_application")

    for kind in ("missing", "symlink", "directory", "fifo", "mode0644", "mode0400",
                 "mode0000", "empty", "newline", "crlf", "space", "nul", "nonascii",
                 "oversized", "wrong-owner"):
        with negative_key_fixture(kind, sentinel) as available:
            if available:
                run_case(argv, key_case=True)
                outcomes["key_files"].append(kind)
                if kind == "wrong-owner":
                    outcomes["wrong_owner"] = "PASS_ACTUAL_FILESYSTEM"

    for name, flag, invalid in (
        ("multiple-tokenizers", "--tokenizer-worker-num", "2"),
        ("different-host", "--host", "127.0.0.1"),
        ("different-port", "--port", "30004"),
        ("different-model", "--model-path", "/fixture-invalid-model"),
        ("different-key-path", "--key-file", "/run/secrets/fixture-invalid-key"),
        ("different-warmup-timeout", "--warmup-timeout", "1"),
        ("different-tp", "--tp-size", "1"),
        ("different-load-format", "--load-format", "gguf"),
    ):
        rejected = list(argv)
        rejected[rejected.index(flag) + 1] = invalid
        run_case(rejected)
        outcomes["cli_modes"].append(name)
    for name, extra in (("duplicate-option", ["--port", "30003"]),
                        ("inline-api-key", ["--api-key", "fixture-disallowed-key"]),
                        ("inline-admin-key", ["--admin-api-key", "fixture-disallowed-key"]),
                        ("config-option", ["--config", "/fixture-invalid-config"]),
                        ("ray-option", ["--use-ray"]),
                        ("encoder-option", ["--encoder-only"]),
                        ("http2-option", ["--enable-http2"]),
                        ("reload-option", ["--reload"]),
                        ("tool-server-option", ["--tool-server", "fixture-invalid"]),
                        ("grpc-option", ["--grpc-mode"]),
                        ("unknown-option", ["--fixture-unknown", "1"])):
        run_case(list(argv) + extra)
        outcomes["cli_modes"].append(name)

    for field, invalid in (("api_key", "fixture-disallowed-key"),
                           ("admin_api_key", "fixture-disallowed-key"),
                           ("tokenizer_worker_num", 2), ("dp_size", 2), ("nnodes", 2),
                           ("disaggregation_mode", "prefill"), ("grpc_mode", True),
                           ("use_ray", True), ("enable_http2", True),
                           ("encoder_only", True), ("enable_ssl_refresh", True),
                           ("tool_server", "fixture-invalid"),
                           ("skip_server_warmup", True), ("skip_tokenizer_init", True),
                           ("trust_remote_code", True), ("enable_metrics", True),
                           ("quantization", "fixture-unsupported"),
                           ("tokenizer_path", "/fixture-invalid-tokenizer")):
        run_case(argv, fault=(field, invalid))
        outcomes["normalized_mode_faults"].append(field)
    return outcomes


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
        await check_model_info_route(server, app, tokenizer, sentinel, wrong)
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

            negative_contracts = None
            if scenario == "all":
                negative_contracts = check_negative_contracts(launcher, server, ServerArgs, argv, sentinel)

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
            engine_calls, captured, owned_workers = [], [], []
            native_uvicorn_run = server.uvicorn.run

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
                if scenario == "signal-int":
                    child = subprocess.Popen([sys.executable, "-c", PROCESS_TREE_CODE],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, bufsize=0)
                    owned_workers.append(child)
                    with selectors.DefaultSelector() as selector:
                        selector.register(child.stdout, selectors.EVENT_READ)
                        require(bool(selector.select(5)), "fixture_descendant_not_ready")
                        identity = os.read(child.stdout.fileno(), 64)
                    require(identity.endswith(b"\n") and identity.strip().isdigit(),
                            "fixture_descendant_identity_invalid")
                    descendant = int(identity)
                    require(child.poll() is None and descendant != child.pid
                            and os.getpgid(descendant) == os.getpgrp()
                            and os.getpgid(child.pid) == os.getpgrp(),
                            "fixture_descendant_group_invalid")
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
                if scenario == "signal-int":
                    # Real Uvicorn owns its OS handlers, startup and shutdown.
                    # Only native model lifespan is disabled; no signal callback
                    # or process cleanup function is replaced by this fixture.
                    native_startup = server.uvicorn.Server.startup
                    native_handle_exit = server.uvicorn.Server.handle_exit
                    instances = []

                    async def observe_startup(instance, *args, **options):
                        await native_startup(instance, *args, **options)
                        installed = signal.getsignal(signal.SIGINT)
                        require(instance.started and getattr(installed, "__self__", None) is instance
                                and getattr(installed, "__func__", None) is native_handle_exit,
                                "native_uvicorn_signal_handler_missing")
                        instances.append(instance)
                        os.write(1, SIGNAL_READY)

                    with patch.object(server.uvicorn.Server, "startup", observe_startup):
                        native_uvicorn_run(app, **kwargs, lifespan="off")
                    require(len(instances) == 1 and instances[0].should_exit
                            and instances[0]._captured_signals == [signal.SIGINT],
                            "native_signal_not_observed")
                    return
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
            if scenario == "signal-int":
                require(len(owned_workers) == 1, "signal_fixture_worker_missing")
                for child in owned_workers:
                    child.wait(timeout=5)
                    child.stdout.close()
                    require(child.returncode == -signal.SIGKILL, "native_cleanup_did_not_kill_worker")
                return {"native_sigint_launcher_cleanup": "PASS"}

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
    return {"native_routes_and_final_chain": "PASS", "native_model_info_bearer_cases": "PASS",
            "negative_contracts": negative_contracts, "native_prepare_and_normalization": "PASS",
            "health_starting_503_up_200": "PASS", "sentinel_absence": "PASS",
            "injection_failure_child_cleanup": "PASS", "spawn_import": "PASS"}


def run_failure_children(repo):
    # Each case has an independent exclusively created synthetic key/config.
    # os._exit in the real launcher skips finally; remove only owned fixture
    # files after the child is gone, never accept a preexisting file.
    for scenario in SCENARIOS[1:]:
        require(not os.path.lexists(KEY_PATH) and not os.path.lexists(CONFIG_PATH),
                "fixture_files_not_clean")
        command = [sys.executable, str(Path(__file__).resolve()), "--actual-image",
                   "--repo", str(repo), "--internal-scenario", scenario]
        with disposable_child(command) as child:
            if scenario == "signal-int":
                read_process_output(child, until=SIGNAL_READY)
                # Delivery is to the launcher process only. Native launcher
                # cleanup must remove its workers; the controller does not
                # signal the group to make this success condition pass.
                os.kill(child.pid, signal.SIGINT)
                output, errors = read_process_output(child, timeout=15)
                require(child.returncode == 0 and output == SIGNAL_DONE and not errors,
                        "native_signal_subprocess_not_closed")
            else:
                output, errors = read_process_output(child)
                require(child.returncode == 1 and output == FAULT_MARKER and not errors,
                        "warmup_failure_subprocess_not_closed")
            # Check before the emergency finally cleanup: a survivor is FAIL.
            wait_owned_group_gone(child.pid)
        # These files can exist only if the exclusive child created them. Do not
        # use this cleanup for an ordinary helper invocation with existing files.
        for path in (KEY_PATH, CONFIG_PATH):
            if scenario == "signal-int":
                require(not os.path.lexists(path), "signal_fixture_file_survived")
                continue
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
        if options.internal_scenario == "signal-int":
            require(result == {"native_sigint_launcher_cleanup": "PASS"},
                    "native_signal_result_invalid")
            os.write(1, SIGNAL_DONE)
            return 0
        if options.internal_scenario != "all":
            raise FixtureFailure("expected_abort_not_observed")
        run_failure_children(options.repo)
        result.update(status="PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE", image_id_pin=IMAGE_ID,
                      image_identity_verification="HOST_DOCKER_INSPECT_REQUIRED",
                      helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      launcher_sha256=hashlib.sha256((options.repo /
                          "scripts/lifecycle/sglang_file_auth.py").read_bytes()).hexdigest(),
                      native_http_dependency_versions={name: importlib.metadata.version(name)
                          for name in ("fastapi", "starlette", "uvicorn")},
                      hardware_discovery_stubs=list(HARDWARE_STUBS),
                      warmup_failure_and_timeout_cleanup="PASS",
                      actual_sigint_native_uvicorn_launcher_cleanup="PASS",
                      sigterm_sigquit="NOT_TESTED",
                      signal_native_uvicorn_lifespan="DISABLED_MODEL_INITIALIZATION_NOT_TESTED",
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
