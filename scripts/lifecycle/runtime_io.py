"""Narrow, secret-safe external I/O for the lifecycle manager.

The caller owns authorization, state locking, deployment identity and storage
guards. This module neither discovers credentials nor prints external output.
Docker operations require explicit arguments and never implicitly pull images.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import stat
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit


class LifecycleError(Exception):
    """An operator-safe error code, never subprocess output or secret data."""

    def __init__(self, code: str):
        self.code = code if re.fullmatch(r"[a-z][a-z0-9_]{0,95}", code) else "operation_failed"
        super().__init__(self.code)


def run(args: list[str], timeout: float = 30) -> str:
    """Run an explicit argv with a minimal environment and sanitized errors."""
    if not args or not all(isinstance(arg, str) and "\0" not in arg for arg in args):
        raise LifecycleError("invalid_command")
    try:
        result = subprocess.run(
            args, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=timeout, text=True,
            env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
    except subprocess.TimeoutExpired:
        raise LifecycleError("command_timeout") from None
    except (OSError, ValueError, UnicodeError):
        raise LifecycleError("command_unavailable") from None
    if result.returncode != 0:
        raise LifecycleError("command_failed")
    return result.stdout


_ID = re.compile(r"[0-9a-f]{64}")


class Docker:
    """Small Docker CLI adapter. Caller must verify ownership before mutations."""

    def __init__(self, binary_prefix: list[str] | None = None):
        self.prefix = binary_prefix if binary_prefix is not None else (
            ["docker"] if os.geteuid() == 0 else ["sudo", "-n", "docker"]
        )

    def run(self, args: list[str], timeout: float = 30) -> str:
        return run(self.prefix + args, timeout=timeout)

    def capture(self, *args: str, timeout: float = 30) -> str:
        """Capture safe metadata commands such as image/network inspect."""
        return self.run(list(args), timeout=timeout)

    def inventory(self) -> list[dict]:
        ids = self.run(["container", "ls", "--all", "--quiet", "--no-trunc"]).split()
        if not all(_ID.fullmatch(identity) for identity in ids) or len(set(ids)) != len(ids):
            raise LifecycleError("docker_inventory_invalid")
        if not ids:
            return []
        # Do not include command output in JSON or schema errors: inspect can
        # contain environment values configured by unrelated container owners.
        try:
            data = json.loads(self.run(["container", "inspect", *ids]))
        except (ValueError, TypeError):
            raise LifecycleError("docker_inspect_invalid") from None
        if (not isinstance(data, list) or len(data) != len(ids)
                or not all(isinstance(item, dict) and item.get("Id") in ids for item in data)
                or len({item["Id"] for item in data}) != len(ids)):
            raise LifecycleError("docker_inspect_invalid")
        return data

    def inspect(self, identity: str) -> dict | None:
        """Return absence only after successful daemon inventory, never on error."""
        if not isinstance(identity, str) or not identity or identity.startswith("-"):
            raise LifecycleError("container_identity_invalid")
        matches = [item for item in self.inventory()
                   if item["Id"] == identity or item.get("Name", "").lstrip("/") == identity.lstrip("/")]
        if len(matches) > 1:
            raise LifecycleError("container_identity_ambiguous")
        return matches[0] if matches else None

    @staticmethod
    def _id(identity: str) -> str:
        if not isinstance(identity, str) or not _ID.fullmatch(identity):
            raise LifecycleError("container_identity_invalid")
        return identity

    def create(self, argv: list[str]) -> str:
        identity = self.run(["container", "create", "--pull", "never", *argv]).strip()
        return self._id(identity)

    def start(self, identity: str) -> None:
        self.run(["container", "start", self._id(identity)])

    def stop(self, identity: str, timeout: int = 120) -> None:
        self._id(identity)
        self.run(["container", "stop", "--time", str(timeout), identity], timeout=timeout + 30)
        item = self.inspect(identity)
        if item is not None and item.get("State", {}).get("Running") is not False:
            raise LifecycleError("container_still_running")

    def remove(self, identity: str) -> None:
        self._id(identity)
        item = self.inspect(identity)
        if item is None:
            return
        if item.get("State", {}).get("Running") is not False:
            raise LifecycleError("container_remove_running")
        self.run(["container", "rm", identity])


def _port(value) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,5}", str(value)):
        raise LifecycleError("network_policy_invalid")
    number = int(value)
    if not 1 <= number <= 65535:
        raise LifecycleError("network_policy_invalid")
    return number


def validate_published(service: dict, target_port: int, host_port: int,
                       allow_host_ipc: bool = False) -> None:
    """Validate every mapping in a rendered Compose service (long syntax)."""
    if not isinstance(service, dict):
        raise LifecycleError("network_policy_invalid")
    if service.get("network_mode") not in (None, "bridge", "default"):
        raise LifecycleError("network_policy_invalid")
    if (service.get("privileged") or service.get("pid") == "host"
            or (service.get("ipc") == "host" and not allow_host_ipc)):
        raise LifecycleError("network_policy_invalid")
    ports = service.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        raise LifecycleError("network_policy_invalid")
    for mapping in ports:
        if (not isinstance(mapping, dict) or mapping.get("host_ip") != "127.0.0.1"
                or mapping.get("protocol", "tcp") != "tcp"
                or _port(mapping.get("target")) != _port(target_port)
                or _port(mapping.get("published")) != _port(host_port)):
            raise LifecycleError("network_policy_invalid")


def validate_container_network(container: dict, host_port: int, target_port: int,
                               allowed_bridge_networks: tuple[str, ...] = (),
                               allow_host_ipc: bool = False) -> None:
    """Check configured and effective Docker publishes; host networking fails.

    Additional network names are accepted only when the caller has independently
    verified their Docker driver is bridge. Direct lifecycle creates use bridge.
    Empty effective bindings are valid for a created/stopped container only.
    """
    try:
        host = container["HostConfig"]
        settings = container["NetworkSettings"]
        state = container["State"]
        mode = host["NetworkMode"]
        if (state.get("Running") not in (True, False)
                or mode in ("host", "none") or ":" in mode
                or mode not in ("bridge", "default", *allowed_bridge_networks)
                or host.get("PublishAllPorts") or host.get("Privileged")
                or host.get("PidMode") == "host"
                or (host.get("IpcMode") == "host" and not allow_host_ipc)):
            raise LifecycleError("network_policy_invalid")
        expected = f"{_port(target_port)}/tcp"

        def validate_bindings(bindings, required):
            if not isinstance(bindings, dict):
                raise LifecycleError("network_policy_invalid")
            actual = {name: values for name, values in bindings.items() if values}
            if not actual and not required:
                return
            if set(actual) != {expected} or not isinstance(actual[expected], list) or len(actual[expected]) != 1:
                raise LifecycleError("network_policy_invalid")
            binding = actual[expected][0]
            if (not isinstance(binding, dict) or binding.get("HostIp") != "127.0.0.1"
                    or _port(binding.get("HostPort")) != _port(host_port)):
                raise LifecycleError("network_policy_invalid")

        validate_bindings(host.get("PortBindings"), True)
        validate_bindings(settings.get("Ports", {}), state.get("Running") is True)
        networks = settings.get("Networks", {})
        if not isinstance(networks, dict) or any(
                name not in ("bridge", "default", *allowed_bridge_networks) for name in networks):
            raise LifecycleError("network_policy_invalid")
    except (KeyError, TypeError, AttributeError):
        raise LifecycleError("network_policy_invalid") from None


def _key_fd(path: str | Path) -> int:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) != 0o600
                or meta.st_uid not in (0, os.geteuid()) or not 1 <= meta.st_size <= 4096):
            raise LifecycleError("key_file_invalid")
        return fd
    except (OSError, ValueError, TypeError, LifecycleError):
        if fd is not None:
            os.close(fd)
        raise LifecycleError("key_file_invalid") from None


def validate_key_metadata(path: str | Path) -> None:
    """Check the key file without reading its contents, including on dry runs."""
    os.close(_key_fd(path))


def _read_key(path: str | Path) -> str:
    fd = _key_fd(path)
    try:
        raw = os.read(fd, 4097)
        value = raw.decode("ascii")
        if not value or len(raw) > 4096 or not all(33 <= ord(char) <= 126 for char in value):
            raise LifecycleError("key_file_invalid")
        return value
    except (OSError, UnicodeError):
        raise LifecycleError("key_file_invalid") from None
    finally:
        os.close(fd)


def probe(endpoint: str, expected_model: str, key_file: str | Path | None,
          require_auth: bool = True, timeout: float = 3,
          check_wrong_key: bool = False) -> str:
    """Return ready/auth_error/wrong_model/not_ready, with no response details.

    Direct HTTP avoids environment proxies and does not follow redirects. The
    health and model checks are liveness/readiness only, not generation proof.
    """
    try:
        url = urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname != "127.0.0.1" or url.username
                or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1"
                or url.port is None or timeout <= 0):
            return "not_ready"
        if require_auth and key_file is None:
            return "auth_error"
        key = _read_key(key_file) if key_file is not None else None
        deadline = time.monotonic() + timeout

        def request(path, authenticated=False, read_json=False, wrong_key=False):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            connection = http.client.HTTPConnection("127.0.0.1", url.port, timeout=remaining)
            # A socket timeout alone is an idle timeout: a trickling response
            # could otherwise exceed the lifecycle deadline indefinitely.
            connection.connect()
            connected_socket = connection.sock

            def expire():
                try:
                    connected_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
            timer.daemon = True
            timer.start()
            try:
                headers = {"Accept": "application/json", "Connection": "close"}
                if authenticated and key is not None:
                    token = key
                    if wrong_key:
                        token = "llmctl-invalid-readiness-key"
                        if token == key:
                            token += "-different"
                    headers["Authorization"] = "Bearer " + token
                connection.request("GET", path, headers=headers)
                response = connection.getresponse()
                payload = b""
                if read_json and response.status == 200:
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError
                        if connection.sock is not None:
                            connection.sock.settimeout(remaining)
                        piece = response.read1(min(65536, 1048577 - len(payload)))
                        if not piece:
                            break
                        payload += piece
                        if len(payload) > 1048576:
                            return response.status, None
                    return response.status, json.loads(payload)
                return response.status, None
            finally:
                timer.cancel()
                timer.join()
                connection.close()

        if require_auth:
            status, _ = request("/v1/models")
            if status == 200:
                return "auth_error"
            if status not in (401, 403):
                return "not_ready"
            if check_wrong_key:
                status, _ = request("/v1/models", authenticated=True, wrong_key=True)
                if status == 200:
                    return "auth_error"
                if status not in (401, 403):
                    return "not_ready"
        status, _ = request("/health", authenticated=True)
        if status in (401, 403):
            return "auth_error"
        if status != 200:
            return "not_ready"
        status, payload = request("/v1/models", authenticated=True, read_json=True)
        if status in (401, 403):
            return "auth_error"
        if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return "not_ready"
        data = payload["data"]
        if (len(data) != 1 or not isinstance(data[0], dict)
                or data[0].get("id") != expected_model):
            return "wrong_model"
        return "ready"
    except LifecycleError:
        return "auth_error"
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        return "not_ready"


def probe_sglang(endpoint: str, expected_model: str, key_file: str | Path | None,
                 require_auth: bool = True, timeout: float = 3) -> str:
    """SGLang readiness: health Up AND exact authenticated alias AND auth denial.

    Native available_models can return metadata while still Starting. Native
    /health returns 503 until the custom authenticated warmup marks Up. Neither
    endpoint suffices alone. All requests share probe's one absolute deadline.
    Keep GLM's existing probe contract unchanged; SGLang additionally rejects a
    wrong key before accepting readiness. No response/key diagnostics are emitted.
    """
    if not require_auth:
        return "auth_error"
    return probe(endpoint, expected_model, key_file, require_auth=True,
                 timeout=timeout, check_wrong_key=True)


def native_capacity_metadata(endpoint: str, key_file: str | Path, *, timeout: float = 3,
                             backend: str | None = None) -> dict:
    """Authenticated bounded native metadata for the two fixed private backends.

    No redirects, environment proxy, arbitrary URL/path or response diagnostics.
    Callers validate the exact capacity fields and return only safe numeric facts.
    This observes allocation metadata; it never sends an inference request.
    """
    paths = {'http://127.0.0.1:30002/v1': '/props',
             'http://127.0.0.1:30004/v1': '/get_server_info'}
    if backend == 'qwen':
        paths['http://127.0.0.1:30002/v1'] = '/get_server_info'
    elif backend not in (None, 'glm'):
        raise LifecycleError('concurrent_native_metadata_unavailable')
    if backend == 'glm' and endpoint != 'http://127.0.0.1:30002/v1':
        raise LifecycleError('concurrent_native_metadata_unavailable')
    if endpoint not in paths or type(timeout) not in (int, float) or not 0 < timeout <= 30:
        raise LifecycleError('concurrent_native_metadata_unavailable')
    connection, timer = None, None
    try:
        key = _read_key(key_file)
        deadline = time.monotonic() + timeout
        port = 30002 if endpoint.endswith('30002/v1') else 30004
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
        connection.connect()
        connected_socket = connection.sock

        def expire():
            try:
                connected_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
        timer.daemon = True
        timer.start()
        connection.request('GET', paths[endpoint], headers={'Accept': 'application/json',
                           'Connection': 'close', 'Authorization': 'Bearer ' + key})
        response = connection.getresponse()
        if response.status in (401, 403):
            raise LifecycleError('concurrent_native_metadata_auth_failed')
        if response.status != 200:
            raise LifecycleError('concurrent_native_metadata_unavailable')
        payload = b''
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            piece = response.read1(min(65536, 1048577 - len(payload)))
            if not piece:
                break
            payload += piece
            if len(payload) > 1048576:
                raise LifecycleError('concurrent_native_metadata_unavailable')

        def pairs(items):
            result = {}
            for name, value in items:
                if name in result:
                    raise ValueError
                result[name] = value
            return result

        value = json.loads(payload, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or time.monotonic() >= deadline:
            raise LifecycleError('concurrent_native_metadata_unavailable')
        return value
    except LifecycleError:
        raise
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
        raise LifecycleError('concurrent_native_metadata_unavailable') from None
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if connection is not None:
            connection.close()
