#!/usr/bin/env python3
"""Run the reviewed Q38S auth fixture against an already installed pinned image.

This helper never pulls an image. It accepts no production model/key mounts,
GPUs, network, additional environment, commands, or flags. Run storage guards
before and after this separately authorized worker1 gate. --output must be a
new JSON file beneath an existing protected registered data-root directory on
a filesystem distinct from /. Registration is the caller's L1 responsibility.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import threading
import time


IMAGE_ID = "sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813"
IMAGE_REFERENCE = "lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262"
SOURCE_REVISION = "0bcd822377da7b5718e674eaf9c870d349424dd1"
CHECKS = (
    "native_routes_and_final_chain", "native_prepare_and_normalization",
    "health_starting_503_up_200", "sentinel_absence", "injection_failure_child_cleanup",
    "spawn_import", "unsupported_modes", "raw_resolved_workerargs_sentinel_absence",
    "native_sse_disconnect", "ordinary_http_auth", "server_info_sentinel_absence",
    "websocket_denial", "native_freeze_gc_has_no_key", "warmup_failure_and_timeout_cleanup",
    "native_false_warmup_not_ready", "native_parser_template_synthetic",
    "actual_cache_resolvers", "no_gpu_driver_libraries",
)


def source_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OCI = source_module("q38b_host_oci", Path(__file__).resolve().parents[3] / "scripts/runtime/qwen38_oci.py")
CACHE = source_module("q38b_host_cache", Path(__file__).with_name("cache_probe.py"))


class FixtureError(Exception):
    """Only fixed codes may leave this driver."""


def require(value, code):
    if not value:
        raise FixtureError(code)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise FixtureError("arguments_invalid")


def parse_options(argv):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def read_provenance(repo):
    require(repo.is_absolute() and repo.resolve() == repo and repo.is_dir(),
            "repository_path_invalid")
    require(repo == Path(__file__).resolve().parents[3], "executing_source_repository_mismatch")
    require(re.fullmatch(r"/[A-Za-z0-9_./ -]+", str(repo)) is not None,
            "repository_mount_syntax_invalid")
    root = repo / "tests/lifecycle/sglang38_fixture"
    expected = json.loads((root / "provenance.json").read_text())
    require(expected["image_id"] == IMAGE_ID
            and expected["image_reference"] == IMAGE_REFERENCE
            and expected["source_revision"] == SOURCE_REVISION,
            "provenance_identity_mismatch")
    require(expected["launcher_path"] == "scripts/runtime/sglang38_file_auth.py",
            "launcher_path_invalid")
    launcher_path = repo / expected["launcher_path"]
    require(hashlib.sha256(launcher_path.read_bytes()).hexdigest() == expected["launcher_sha256"],
            "launcher_hash_mismatch")
    require(set(expected["fixture_sha256"]) == {"run_fixture.py", "run_pinned_image.py", "auth_native.py", "chat_template.jinja", "cache_probe.py"},
            "fixture_manifest_invalid")
    for name, identity in expected["fixture_sha256"].items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == identity,
                "fixture_hash_mismatch")
    require(set(expected["support_sha256"]) == {"scripts/runtime/qwen38_oci.py"}, "support_manifest_invalid")
    for name, digest in expected["support_sha256"].items():
        require(hashlib.sha256((repo / name).read_bytes()).hexdigest() == digest, "support_hash_mismatch")
    spec = importlib.util.spec_from_file_location("q38s_fixture_launcher_config", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    return expected, launcher.CACHE_ENVIRONMENT


def verify_image(inspected):
    require(isinstance(inspected, list) and len(inspected) == 1, "image_inspect_invalid")
    try:
        return OCI.verify_image(inspected[0])
    except OCI.Qwen38OCIError:
        raise FixtureError("image_identity_mismatch") from None


def docker_command(repo, cache_environment, context, *, container_name=None, ownership_token=None):
    require(context in (131072, 262144), "context_invalid")
    require(re.fullmatch(r"/[A-Za-z0-9_./ -]+", str(repo)) is not None,
            "repository_mount_syntax_invalid")
    if container_name is None and ownership_token is None:
        ownership_token = secrets.token_hex(16)
        container_name = "q38b-fixture-" + ownership_token
    require(re.fullmatch(r"q38b-fixture-[a-f0-9]{32}", container_name or "") is not None
            and re.fullmatch(r"[a-f0-9]{32}", ownership_token or "") is not None,
            "container_identity_invalid")
    command = ["docker", "create", "--name", container_name,
               "--label", f"{OWNER_LABEL}={ownership_token}", "--pull=never", "--network", "none",
               "--runtime", "nvidia", "--log-driver", "none",
               "--env", "NVIDIA_VISIBLE_DEVICES=none", "--env", "CUDA_VISIBLE_DEVICES=",
               "--env", "NVIDIA_DRIVER_CAPABILITIES=compute,utility",
               "--env", "OPENBLAS_NUM_THREADS=1",
               "--platform", "linux/amd64", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--pids-limit", "128", "--memory", "8g", "--shm-size", "64m",
               # Linux's piped-core recursion guard is exactly one byte; zero
               # does not prevent invoking a core_pattern handler such as Apport.
               "--ulimit", "core=1:1",
               "--user", "0:0", "--workdir", "/cache", "--entrypoint", "python3",
               "--mount", f"type=bind,src={repo},dst=/fixture,readonly",
               "--tmpfs", "/models:rw,nosuid,nodev,noexec,size=8m,mode=0700",
               "--tmpfs", "/run/secrets:rw,nosuid,nodev,noexec,size=1m,mode=0700",
               "--tmpfs", "/cache:rw,nosuid,nodev,size=1g,mode=0700",
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777"]
    # No host environment is forwarded and HOME retains the image default.
    for name, value in sorted(cache_environment.items()):
        command += ["--env", f"{name}={value}"]
    return command + [IMAGE_REFERENCE, "-X", "faulthandler", "-B",
        "/fixture/tests/lifecycle/sglang38_fixture/run_pinned_image.py", "--actual-image",
        "--repo", "/fixture", "--context", str(context)]


OWNER_LABEL = "local-ai-server.q38b-fixture-owner"
CLEANUP_TIMEOUT = 30
CLI_DRAIN_TIMEOUT = 2
FAILURE_CLASSES = frozenset((
    "FixtureFailure", "AssertionError", "AttributeError", "ImportError", "ModuleNotFoundError",
    "TypeError", "ValueError", "KeyError", "IndexError", "RuntimeError", "OSError",
    "FileNotFoundError", "PermissionError", "TimeoutError", "TimeoutExpired", "JSONDecodeError",
    "SystemExit", "KeyboardInterrupt", "MemoryError", "RecursionError", "OTHER",
))


def failure_metadata(stdout):
    """Admit only the small, whole inner FAIL record; never search raw logs.

    Bytes, duplicate keys, nesting, types and every retained field are bounded.
    This untrusted hint is never native-exit proof or receipt acceptance input.
    """
    rejected = {"status": "REJECTED_OR_UNAVAILABLE"}
    if type(stdout) is not bytes or not 0 < len(stdout) <= 4096:
        return rejected

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError()

    try:
        value = json.loads(stdout.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
        if (type(value) is not dict or set(value) not in (
                {"status", "code"}, {"status", "code", "failure_origin"},
                {"status", "code", "failure_origin", "cache_failure"})
                or value["status"] != "FAIL" or value["code"] != "actual_image_fixture_failed"):
            return rejected
        result = {"status": "FIXED_FAILURE_ONLY", "code": "actual_image_fixture_failed"}
        if "cache_failure" in value:
            cache_failure = CACHE.validate_failure(value["cache_failure"])
            if cache_failure is None:
                return rejected
            result["cache_failure"] = cache_failure
        if "failure_origin" not in value or value["failure_origin"] is None:
            return result
        origin = value["failure_origin"]
        if (type(origin) is not dict or set(origin) != {"filename", "line", "exception_class"}
                or origin["filename"] != "run_pinned_image.py"
                or type(origin["line"]) is not int or not 1 <= origin["line"] <= 100000
                or type(origin["exception_class"]) is not str
                or origin["exception_class"] not in FAILURE_CLASSES):
            return rejected
        result.update(status="SAFE_ORIGIN",
                      origin={"filename": "run_pinned_image.py", "line": origin["line"],
                              "exception_class": origin["exception_class"]})
        return result
    except (ValueError, TypeError, RecursionError):
        return rejected


def capture_diagnostic(stdout=None, stderr=None, returncode=None, *, complete=False):
    """Lengths/hashes describe captured bytes only, never total child output."""
    code = returncode if type(returncode) is int and -64 <= returncode <= 255 else None
    def stream(value):
        if type(value) not in (bytes, bytearray) or len(value) > 131072:
            return {"capture": "UNAVAILABLE", "captured_bytes": None, "sha256": None}
        return {"capture": "COMPLETE" if complete else "PREFIX",
                "captured_bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    return {"cli_returncode": code, "cli_signal": -code if code is not None and code < 0 else None,
            "stdout": stream(stdout), "stderr": stream(stderr),
            "failure_metadata": failure_metadata(stdout) if complete else {"status": "INCOMPLETE_CAPTURE"}}


def attach_failure_kind(error):
    if isinstance(error, subprocess.TimeoutExpired):
        return "TIMEOUT"
    if isinstance(error, (FixtureCancelled, KeyboardInterrupt)):
        return "CANCELLED"
    if type(error) is FixtureError and error.args == ("docker_cli_output_limit",):
        return "OUTPUT_OVERFLOW"
    if type(error) is FixtureError and error.args == ("container_fixture_exit_unverified",):
        return "CONTAINER_EXIT_UNVERIFIED"
    return "CLI_EXCEPTION"


def verify_fixture_runtime(container, repo, cache_environment, context):
    """Read actual container inspect before start; no user-controlled modes."""
    config, host = container.get("Config", {}), container.get("HostConfig", {})
    entries = config.get("Env", [])
    require(isinstance(entries, list) and all(isinstance(v, str) and "=" in v for v in entries),
            "fixture_environment_invalid")
    env = dict(v.split("=", 1) for v in entries)
    require(len(env) == len(entries) and all(env.get(k) == v for k, v in
            {**cache_environment, **CACHE.RUNTIME_ENVIRONMENT}.items()), "fixture_environment_invalid")
    require(host.get("Runtime") == "nvidia" and not host.get("DeviceRequests")
            and not host.get("Devices") and not host.get("DeviceCgroupRules")
            and not host.get("Privileged") and not host.get("CapAdd")
            and host.get("CapDrop") == ["ALL"] and host.get("ReadonlyRootfs") is True
            and host.get("NetworkMode") == "none" and not host.get("PortBindings")
            and host.get("SecurityOpt") in (["no-new-privileges"], ["no-new-privileges:true"])
            and host.get("LogConfig") == {"Type": "none", "Config": {}},
            "fixture_runtime_isolation_invalid")
    require(type(host.get("PidsLimit")) is int and host["PidsLimit"] == 128
            and type(host.get("Memory")) is int and host["Memory"] == 8 * 1024**3
            and type(host.get("ShmSize")) is int and host["ShmSize"] == 64 * 1024**2
            and host.get("RestartPolicy") == {"Name": "no", "MaximumRetryCount": 0}
            and host.get("AutoRemove") is False, "fixture_resource_policy_invalid")
    limits = host.get("Ulimits")
    require(type(limits) is list, "fixture_resource_policy_invalid")
    core = [value for value in limits if type(value) is dict and value.get("Name") == "core"]
    require(len(core) == 1 and set(core[0]) == {"Name", "Soft", "Hard"}
            and all(type(core[0][key]) is int and core[0][key] == 1 for key in ("Soft", "Hard")),
            "fixture_resource_policy_invalid")
    require(not any(host.get(k) for k in ("Binds", "VolumesFrom", "PidMode", "UTSMode"))
            and host.get("IpcMode", "private") == "private", "fixture_namespace_invalid")
    require(host.get("Tmpfs") == {
        "/models": "rw,nosuid,nodev,noexec,size=8m,mode=0700",
        "/run/secrets": "rw,nosuid,nodev,noexec,size=1m,mode=0700",
        "/cache": "rw,nosuid,nodev,size=1g,mode=0700", "/tmp": "rw,nosuid,nodev,size=256m,mode=1777"},
        "fixture_tmpfs_invalid")
    mounts = container.get("Mounts", [])
    require(isinstance(mounts, list) and all(isinstance(m, dict) for m in mounts), "fixture_mounts_invalid")
    tmpfs = [m for m in mounts if m.get("Type") == "tmpfs"]
    require(all(m.get("Destination") in host["Tmpfs"] for m in tmpfs)
            and len({m.get("Destination") for m in tmpfs}) == len(tmpfs), "fixture_mounts_invalid")
    binds = [m for m in mounts if m.get("Type") != "tmpfs"]
    require(len(binds) == 1 and binds[0].get("Type") == "bind"
            and binds[0].get("Source") == str(repo) and binds[0].get("Destination") == "/fixture"
            and binds[0].get("RW") is False and binds[0].get("Propagation") in ("rprivate", ""),
            "fixture_mounts_invalid")
    require(config.get("Entrypoint") == ["python3"] and config.get("User") == "0:0"
            and config.get("WorkingDir") == "/cache" and config.get("Cmd") == ["-X", "faulthandler", "-B",
            "/fixture/tests/lifecycle/sglang38_fixture/run_pinned_image.py", "--actual-image",
            "--repo", "/fixture", "--context", str(context)], "fixture_process_invalid")
    return {"runtime": "nvidia", "visible_devices": "none", "driver_capabilities": "compute,utility",
            "device_requests": [], "host_devices": [], "network": "none",
            "root_readonly": True, "model_and_secret_mounts": "EMPTY_PRIVATE_TMPFS",
            "entrypoint": ["python3"], "context": context, "status": "PASS_HOST_INSPECT"}


class FixtureCancelled(BaseException):
    """Enter cleanup on an ordinary interrupt, termination, or hangup."""


class LifetimeFailure(FixtureError):
    def __init__(self, evidence):
        super().__init__("disposable_fixture_failed")
        # Constructed exclusively from fixed codes and validated identities.
        self.evidence = evidence


@contextmanager
def fixture_signals(cleaning=False):
    """Defer repeated signals during bounded cleanup; restore caller handlers.

    SIGKILL/host or daemon loss cannot be trapped: no PASS receipt is emitted
    when cleanup cannot be independently confirmed. A worker must use failure
    evidence to reconcile a retained container before proceeding.
    """
    previous = {}

    def cancelled(_number, _frame):
        raise FixtureCancelled()

    if threading.current_thread() is threading.main_thread():
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, signal.SIG_IGN if cleaning else cancelled)
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def docker_call(command, *, timeout):
    """Bound combined output to 128 KiB, with no disk spool or unbounded drain.

    Pipe EOF and the CLI exit each share the command deadline. On failure, close
    the pipes and reap the CLI under a separate fixed deadline. Neither CLI
    death nor pipe closure substitutes for DisposableContainer cleanup.
    """
    import selectors

    output_limit = 131072
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    captured = [bytearray(), bytearray()]
    try:
        deadline = time.monotonic() + timeout
        total = 0
        with selectors.DefaultSelector() as reader:
            for index, stream in enumerate((child.stdout, child.stderr)):
                os.set_blocking(stream.fileno(), False)
                reader.register(stream, selectors.EVENT_READ, index)
            while reader.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                for key, _events in reader.select(remaining):
                    try:
                        block = os.read(key.fd, min(65536, output_limit - total + 1))
                    except BlockingIOError:
                        continue
                    if not block:
                        reader.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    captured[key.data].extend(block[:output_limit - total])
                    total += len(block)
                    require(total <= output_limit, "docker_cli_output_limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        child.wait(timeout=remaining)
        return subprocess.CompletedProcess(command, child.returncode,
                                           bytes(captured[0]), bytes(captured[1]))
    except BaseException as error:
        diagnostic = capture_diagnostic(*captured, child.poll())
        diagnostic["failure_kind"] = attach_failure_kind(error)
        diagnostic["cli_reap"] = "UNVERIFIED"
        error.attach_capture = diagnostic
        # This reaps the CLI only. DisposableContainer independently stops and
        # verifies the actual container even if this CLI already died.
        with fixture_signals(cleaning=True):
            if child.poll() is None:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass
            # Inherited pipe writers cannot prolong drain or grow memory after
            # failure. Only redacted prefix lengths/hashes survive this boundary.
            for stream in (child.stdout, child.stderr):
                stream.close()
            try:
                child.wait(timeout=CLI_DRAIN_TIMEOUT)
                diagnostic["cli_reap"] = "VERIFIED"
            except subprocess.TimeoutExpired:
                diagnostic["cli_reap"] = "UNVERIFIED"
                failure = FixtureError("docker_cli_not_reaped")
                failure.attach_capture = diagnostic
                raise failure from None
        raise
    finally:
        for stream in (child.stdout, child.stderr):
            stream.close()


class DisposableContainer:
    """Own exactly one container; never mutate a Docker name or a guessed ID."""

    def __init__(self, docker, image_id):
        self.docker = docker
        self.image_id = image_id
        self.token = secrets.token_hex(16)
        self.name = "q38b-fixture-" + self.token
        self.container_id = None
        self.create_attempted = False
        self.create_returned = False
        self.inspected = None
        self.cleanup_initial_state = None
        self.deadline = None
        self.evidence = {"container_name": self.name, "container_id": None,
                         "outcome": "NOT_STARTED", "cleanup": "NOT_ATTEMPTED"}

    def call(self, arguments, timeout=10):
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            require(timeout > 0, "container_cleanup_deadline")
        return self.docker(["docker", "container", *arguments], timeout=timeout)

    def absent(self, target):
        # A failed inspect is not evidence of absence (the daemon may be down).
        selector = "id=" + target if self.container_id else "name=^/" + self.name + "$"
        listed = self.call(["ls", "--all", "--no-trunc", "--filter", selector,
                            "--format", "{{.ID}}"])
        require(listed.returncode == 0 and listed.stderr == b""
                and listed.stdout.strip() == b"", "container_absence_unverified")

    def inspect(self, allow_absent=False):
        target = self.container_id or self.name
        inspected = self.call(["inspect", target])
        if inspected.returncode != 0:
            require(allow_absent, "container_inspect_failed")
            self.absent(target)
            return None
        try:
            values = json.loads(inspected.stdout)
            require(isinstance(values, list) and len(values) == 1
                    and isinstance(values[0], dict), "container_identity_mismatch")
            value = values[0]
            identity = value.get("Id")
            require(isinstance(identity, str) and re.fullmatch(r"[a-f0-9]{64}", identity)
                    and (self.container_id is None or identity == self.container_id)
                    and value.get("Name") == "/" + self.name
                    and value.get("Image") == self.image_id
                    and value.get("Config", {}).get("Image") == IMAGE_REFERENCE
                    and value.get("Config", {}).get("Labels", {}).get(OWNER_LABEL) == self.token,
                    "container_identity_mismatch")
            state = value.get("State", {})
            require(isinstance(state, dict)
                    and all(isinstance(state.get(key), bool)
                            for key in ("Running", "Paused", "Restarting"))
                    and type(state.get("Pid")) is int
                    and type(state.get("ExitCode")) is int
                    and isinstance(state.get("Status"), str), "container_state_invalid")
        except (ValueError, TypeError, AttributeError):
            raise FixtureError("container_identity_mismatch") from None
        self.container_id = identity
        self.evidence["container_id"] = identity
        self.inspected = value
        return state

    def cleanup(self):
        self.deadline = time.monotonic() + CLEANUP_TIMEOUT
        if not self.create_attempted:
            self.evidence["cleanup"] = "NO_CREATE_ATTEMPT"
            return
        state = self.inspect(allow_absent=True)
        # Diagnostic snapshot only: the existing first inspect precedes stop.
        self.cleanup_initial_state = state
        if state is None:
            # A create request interrupted before acknowledgement can still be
            # in flight at the daemon. Current absence cannot prove its drain.
            require(self.container_id is not None or self.create_returned,
                    "container_create_completion_unverified")
            self.evidence["cleanup"] = "ABSENCE_VERIFIED"
            return
        if state["Running"] or state["Paused"] or state["Restarting"]:
            # docker stop applies its own kill deadline. A timed-out stop CLI
            # is followed by state verification, never assumed to have worked.
            try:
                self.call(["stop", "--time", "5", self.container_id])
            except (subprocess.TimeoutExpired, OSError, FixtureError):
                pass
            state = self.inspect(allow_absent=True)
            if state is None:
                self.evidence["cleanup"] = "ABSENCE_VERIFIED"
                return
        require(not state["Running"] and not state["Paused"] and not state["Restarting"]
                and state["Pid"] == 0 and state["Status"] in ("created", "exited"),
                "container_not_quiescent")
        # No --force: a concurrent restart must make removal fail. All mutation
        # targets are the immutable ID, including after the final fresh inspect.
        try:
            self.call(["rm", self.container_id])
        except (subprocess.TimeoutExpired, OSError, FixtureError):
            pass
        require(self.inspect(allow_absent=True) is None, "container_removal_unverified")
        self.evidence["cleanup"] = "QUIESCENT_REMOVAL_VERIFIED"


def run_disposable_fixture(repo, cache_environment, context, *, image_id=IMAGE_ID,
                           docker=None, timeout=600):
    """Return native output only after exact-container cleanup has passed.

    image_id is the host inspect identity already admitted by the reviewed OCI
    relationship check. This internal seam is not a caller-supplied CLI option.
    """
    owned = DisposableContainer(docker_call if docker is None else docker, image_id)
    child = None
    attach_diagnostic = None
    operation = "START_ATTACH"
    failed = False
    phase = "CREATE"
    with fixture_signals():
        try:
            command = docker_command(repo, cache_environment, context,
                                     container_name=owned.name, ownership_token=owned.token)
            owned.create_attempted = True
            created = owned.docker(command, timeout=30)
            owned.create_returned = True
            # Capture stdout only when it is exactly a full Docker container ID.
            identity = created.stdout.strip()
            if re.fullmatch(rb"[a-f0-9]{64}", identity):
                owned.container_id = identity.decode("ascii")
                owned.evidence["container_id"] = owned.container_id
            require(created.returncode == 0 and owned.container_id is not None,
                    "container_create_failed")
            owned.inspect()
            owned.evidence["runtime_inspect"] = verify_fixture_runtime(
                owned.inspected, repo, cache_environment, context)
            phase = "ATTACH"
            child = owned.call(["start", "--attach", owned.container_id], timeout=timeout)
            require(child.returncode == 0, "container_fixture_cli_failed")
            operation = "VERIFY_CONTAINER_EXIT"
            finished = owned.inspect()
            require(not finished["Running"] and not finished["Paused"]
                    and not finished["Restarting"] and finished["Pid"] == 0
                    and finished["Status"] == "exited" and finished["ExitCode"] == 0,
                    "container_fixture_exit_unverified")
            owned.evidence["outcome"] = "FIXTURE_EXITED"
        except (FixtureCancelled, KeyboardInterrupt) as error:
            owned.evidence["outcome"] = "CANCELLED"
            if phase == "ATTACH":
                attach_diagnostic = (capture_diagnostic(child.stdout, child.stderr, child.returncode, complete=True)
                    if child is not None else getattr(error, "attach_capture", None) or capture_diagnostic())
                attach_diagnostic.setdefault("failure_kind", "CANCELLED")
            failed = True
        except subprocess.TimeoutExpired as error:
            owned.evidence["outcome"] = phase + "_TIMEOUT"
            if phase == "ATTACH":
                attach_diagnostic = (capture_diagnostic(child.stdout, child.stderr, child.returncode, complete=True)
                    if child is not None else getattr(error, "attach_capture", None) or capture_diagnostic())
                attach_diagnostic.setdefault("failure_kind", "TIMEOUT")
            failed = True
        except BaseException as error:
            owned.evidence["outcome"] = phase + "_FAILED"
            if phase == "ATTACH":
                if child is not None:
                    attach_diagnostic = capture_diagnostic(
                        child.stdout, child.stderr, child.returncode, complete=True)
                    attach_diagnostic["failure_kind"] = (
                        "CLI_NONZERO_EXIT" if child.returncode != 0 else attach_failure_kind(error))
                else:
                    attach_diagnostic = getattr(error, "attach_capture", None) or capture_diagnostic()
                    attach_diagnostic.setdefault("failure_kind", attach_failure_kind(error))
            failed = True
        finally:
            with fixture_signals(cleaning=True):
                try:
                    owned.cleanup()
                except BaseException:
                    # Fixed failure evidence retains the known ID for operator
                    # reconciliation, without exposing Docker/native output.
                    owned.evidence["cleanup"] = "FAILED_UNVERIFIED"
                    failed = True
    if failed:
        if attach_diagnostic is None and phase == "ATTACH" and child is not None:
            attach_diagnostic = capture_diagnostic(
                child.stdout, child.stderr, child.returncode, complete=True)
            attach_diagnostic["failure_kind"] = "CLEANUP_UNVERIFIED"
            operation = "CLEANUP"
        if attach_diagnostic is not None:
            state = owned.cleanup_initial_state
            exited = (state is not None and not state["Running"] and not state["Paused"]
                      and not state["Restarting"] and state["Pid"] == 0 and state["Status"] == "exited")
            code = state["ExitCode"] if exited else None
            attach_diagnostic.update(schema_version=1, phase="ATTACH", operation=operation,
                container_before_cleanup_stop={
                    "status": "EXITED" if exited else "EXIT_NOT_OBSERVED",
                    "exit_code": code if type(code) is int and 0 <= code <= 255 else None,
                    "signal": None})
            owned.evidence["attach_diagnostic"] = attach_diagnostic
        raise LifetimeFailure(owned.evidence)
    return child, owned.evidence


def check_native_result(result, provenance, context):
    require(result.get("status") == "PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE"
            and result.get("image_identity_verification") == "HOST_DOCKER_INSPECT_REQUIRED"
            and result.get("configured_context") == context, "native_fixture_did_not_pass")
    require(result.get("image_id_pin") == IMAGE_ID
            and result.get("image_reference") == IMAGE_REFERENCE
            and result.get("source_revision") == SOURCE_REVISION
            and result.get("launcher_sha256") == provenance["launcher_sha256"]
            and result.get("fixture_sha256") == provenance["fixture_sha256"]
            and result.get("support_sha256") == provenance["support_sha256"]
            and result.get("source_hashes") == {
                name: item["sha256"] for name, item in provenance["sources"].items()},
            "native_provenance_mismatch")
    require(all(result.get(check) == "PASS" for check in CHECKS), "native_check_failed")
    try:
        CACHE.validate_result(result.get("cache_probe"))
    except CACHE.ProbeError:
        raise FixtureError("native_cache_proof_invalid") from None
    require(result.get("model_loading") == "STUBBED_NOT_TESTED"
            and result.get("gpu_execution") == "NOT_TESTED"
            and result.get("native_lifespan_model_serving_initialization") == "NOT_TESTED"
            and result.get("live_inference_and_agent_acceptance") == "NOT_TESTED",
            "native_evidence_boundary_missing")


def validate_output_path(path):
    require(path.is_absolute() and path.parent.resolve() == path.parent
            and path.suffix == ".json" and not path.exists() and not path.is_symlink(),
            "output_path_invalid")
    require(path.parent.stat().st_dev != Path("/").stat().st_dev,
            "evidence_on_root_filesystem_refused")
    for ancestor in (path.parent, *path.parent.parents):
        meta = ancestor.lstat()
        require(stat.S_ISDIR(meta.st_mode) and not stat.S_ISLNK(meta.st_mode)
                and meta.st_uid in (0, os.geteuid()) and not meta.st_mode & 0o022,
                "output_ancestor_unprotected")


def write_receipt(output, receipt):
    """Anchor publication to one protected directory; fail on detach/rebinding.

    This is fixture evidence output only. The L2 runtime binding must admit this directory using
    L1's actual registered-root binding before calling this helper. Runtime
    receipt import/publication belongs to that canonical anchored storage API.
    """
    validate_output_path(output)
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = False
    identity = None

    def unchanged():
        before, current = os.fstat(directory), output.parent.stat()
        require((before.st_dev, before.st_ino) == (current.st_dev, current.st_ino),
                "evidence_directory_rebound")

    try:
        validate_output_path(output)
        unchanged()
        fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        created = True
        meta = os.fstat(fd)
        identity = (meta.st_dev, meta.st_ino)
        with os.fdopen(fd, "w") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
        unchanged()
    except BaseException:
        if created:
            meta = os.stat(output.name, dir_fd=directory, follow_symlinks=False)
            if (meta.st_dev, meta.st_ino) == identity:
                os.unlink(output.name, dir_fd=directory)
                os.fsync(directory)
        raise
    finally:
        os.close(directory)


def run(repo, output):
    validate_output_path(output)
    provenance, cache_environment = read_provenance(repo)
    inspected = subprocess.run(["docker", "image", "inspect", IMAGE_REFERENCE],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, check=False)
    require(inspected.returncode == 0, "pinned_image_not_installed")
    image = verify_image(json.loads(inspected.stdout))
    results = []
    lifetimes = []
    for context in (131072, 262144):
        child, lifetime = run_disposable_fixture(repo, cache_environment, context, image_id=image["image_id"])
        require(child.returncode == 0 and len(child.stdout) <= 131072
                and child.stderr == b"", "actual_image_fixture_failed")
        result = json.loads(child.stdout)
        check_native_result(result, provenance, context)
        results.append(result)
        lifetimes.append(lifetime)
    receipt = {"schema_version": 2, "kind": "q38b_actual_image_auth", "status": "PASS",
        "image_id": IMAGE_ID, "image_reference": IMAGE_REFERENCE,
        "source_revision": SOURCE_REVISION, "launcher_sha256": provenance["launcher_sha256"],
        "fixture_sha256": provenance["fixture_sha256"],
        "support_sha256": provenance["support_sha256"],
        "source_hashes": {name: item["sha256"] for name, item in provenance["sources"].items()},
        "checks": {check: "PASS" for check in CHECKS}, "contexts": [131072, 262144],
        "image_identity_verification": "HOST_DOCKER_INSPECT_AND_PINNED_RUN",
        "docker_inspect": image, "native_results": results, "container_lifetimes": lifetimes,
        "model_execution": "NOT_TESTED", "native_lifespan": "NOT_TESTED",
        "live_inference_and_agent_acceptance": "NOT_TESTED"}
    write_receipt(output, receipt)
    return receipt


def main(argv=None):
    try:
        options = parse_options(sys.argv[1:] if argv is None else argv)
        receipt = run(options.repo, options.output)
        print(json.dumps({"status": receipt["status"], "kind": receipt["kind"],
                          "model_execution": "NOT_TESTED"}, sort_keys=True))
        return 0
    except Exception as error:
        # Docker/native exception text may contain environment or backend data.
        failure = {"status": "FAIL", "code": "q38s_image_fixture_failed"}
        if isinstance(error, LifetimeFailure):
            failure["lifetime"] = error.evidence
        print(json.dumps(failure, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
