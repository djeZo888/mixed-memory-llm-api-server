"""Deterministic worker tests; no Docker daemon or real credentials needed."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lifecycle"))
import runtime_io as rio


CONTAINER_ID = "a" * 64
OTHER_ID = "b" * 64
FAKE_KEY = "synthetic-fixture-value-never-real"


def container(running=True):
    bindings = {"30002/tcp": [{"HostIp": "127.0.0.1", "HostPort": "30002"}]}
    return {
        "Id": CONTAINER_ID, "Name": "/lifecycle-test",
        "State": {"Running": running},
        "Config": {"Labels": {}},
        "HostConfig": {"NetworkMode": "bridge", "PortBindings": copy.deepcopy(bindings)},
        "NetworkSettings": {"Ports": bindings if running else {}, "Networks": {"bridge": {}}},
    }


class ProcessTests(unittest.TestCase):
    def test_minimal_environment_and_no_stderr(self):
        with mock.patch.dict(os.environ, {"SECRET_TEST_VALUE": FAKE_KEY}), \
                mock.patch.object(rio.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok")) as call:
            self.assertEqual(rio.run(["example", "argument"]), "ok")
        kwargs = call.call_args.kwargs
        self.assertEqual(set(kwargs["env"]), {"PATH", "LANG"})
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(kwargs.get("shell", False))
        self.assertNotIn(FAKE_KEY, repr(call.call_args))

    def test_subprocess_failure_and_timeout_are_sanitized(self):
        cases = [subprocess.TimeoutExpired([FAKE_KEY], 3, output=FAKE_KEY, stderr=FAKE_KEY), OSError(FAKE_KEY)]
        for exception in cases:
            with self.subTest(exception=type(exception).__name__), mock.patch.object(rio.subprocess, "run", side_effect=exception):
                with self.assertRaises(rio.LifecycleError) as raised:
                    rio.run(["example"])
                self.assertNotIn(FAKE_KEY, str(raised.exception))
                self.assertTrue(raised.exception.__suppress_context__)
        with mock.patch.object(rio.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, FAKE_KEY)):
            with self.assertRaisesRegex(rio.LifecycleError, "^command_failed$"):
                rio.run(["example"])

    def test_docker_never_pulls_and_mutations_require_full_id(self):
        docker = rio.Docker(["fixture-docker"])
        with mock.patch.object(docker, "run", return_value=CONTAINER_ID) as call:
            self.assertEqual(docker.create(["--network", "bridge", "fixture-image"]), CONTAINER_ID)
            self.assertEqual(call.call_args.args[0][:4], ["container", "create", "--pull", "never"])
            with self.assertRaisesRegex(rio.LifecycleError, "identity_invalid"):
                docker.start("lifecycle-test")

    def test_docker_inspect_distinguishes_missing_from_failed_daemon(self):
        docker = rio.Docker(["fixture-docker"])
        with mock.patch.object(docker, "run", side_effect=[CONTAINER_ID, json.dumps([container()])]):
            self.assertIsNone(docker.inspect(OTHER_ID))
        with mock.patch.object(docker, "run", side_effect=rio.LifecycleError("command_failed")):
            with self.assertRaisesRegex(rio.LifecycleError, "command_failed"):
                docker.inspect(CONTAINER_ID)
        with mock.patch.object(docker, "run", side_effect=[CONTAINER_ID, json.dumps([container()])]):
            self.assertEqual(docker.inspect("lifecycle-test")["Id"], CONTAINER_ID)

    def test_inventory_rejects_bad_or_partial_json(self):
        docker = rio.Docker(["fixture-docker"])
        for output in (FAKE_KEY, "[]", "{}", json.dumps([container(), container()])):
            with self.subTest(output=output), mock.patch.object(docker, "run", side_effect=[CONTAINER_ID, output]):
                with self.assertRaisesRegex(rio.LifecycleError, "^docker_inspect_invalid$"):
                    docker.inventory()

    def test_stop_verifies_exit_and_remove_refuses_running(self):
        docker = rio.Docker(["fixture-docker"])
        with mock.patch.object(docker, "run", return_value="") as run, \
                mock.patch.object(docker, "inspect", return_value=container(True)):
            with self.assertRaisesRegex(rio.LifecycleError, "container_still_running"):
                docker.stop(CONTAINER_ID, timeout=7)
            self.assertEqual(run.call_args.kwargs["timeout"], 37)
            run.reset_mock()
            with self.assertRaisesRegex(rio.LifecycleError, "container_remove_running"):
                docker.remove(CONTAINER_ID)
            run.assert_not_called()
        with mock.patch.object(docker, "run", return_value="") as run, \
                mock.patch.object(docker, "inspect", return_value=container(False)):
            docker.stop(CONTAINER_ID)
            docker.remove(CONTAINER_ID)
            self.assertEqual(run.call_args.args[0], ["container", "rm", CONTAINER_ID])


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.service = {"ports": [{"host_ip": "127.0.0.1", "target": 30002, "published": "30002", "protocol": "tcp"}]}

    def test_valid_render_and_running_or_stopped_inspect(self):
        rio.validate_published(self.service, 30002, 30002)
        rio.validate_container_network(container(), 30002, 30002)
        rio.validate_container_network(container(False), 30002, 30002)

    def test_every_rendered_address_rejects_wildcard_lan_ipv6_and_extra(self):
        for address in (None, "", "0.0.0.0", "::", "::1", "127.0.0.2", "10.1.2.3", "localhost"):
            with self.subTest(address=address):
                bad = copy.deepcopy(self.service)
                bad["ports"][0]["host_ip"] = address
                with self.assertRaises(rio.LifecycleError):
                    rio.validate_published(bad, 30002, 30002)
        bad = copy.deepcopy(self.service)
        bad["ports"].append({"host_ip": "0.0.0.0", "target": 40000, "published": "40000"})
        with self.assertRaises(rio.LifecycleError):
            rio.validate_published(bad, 30002, 30002)

    def test_render_rejects_network_modes_short_syntax_and_port_ranges(self):
        for mode in ("host", "container:other", "service:other", "none", "unknown"):
            with self.subTest(mode=mode), self.assertRaises(rio.LifecycleError):
                rio.validate_published({**self.service, "network_mode": mode}, 30002, 30002)
        for ports in (["127.0.0.1:30002:30002"], [], None,
                      [{"host_ip": "127.0.0.1", "target": 30002, "published": "30002-30003"}]):
            with self.subTest(ports=ports), self.assertRaises(rio.LifecycleError):
                rio.validate_published({"ports": ports}, 30002, 30002)

    def test_all_configured_and_effective_bindings_are_checked(self):
        for field in ("HostConfig", "NetworkSettings"):
            name = "PortBindings" if field == "HostConfig" else "Ports"
            for address in ("0.0.0.0", "::", "10.1.2.3", ""):
                bad = container()
                bad[field][name]["30002/tcp"][0]["HostIp"] = address
                with self.subTest(field=field, address=address), self.assertRaises(rio.LifecycleError):
                    rio.validate_container_network(bad, 30002, 30002)
            bad = container()
            bad[field][name]["40000/tcp"] = [{"HostIp": "127.0.0.1", "HostPort": "40000"}]
            with self.assertRaises(rio.LifecycleError):
                rio.validate_container_network(bad, 30002, 30002)
            bad = container()
            bad[field][name]["30002/tcp"].append({"HostIp": "127.0.0.1", "HostPort": "30002"})
            with self.assertRaises(rio.LifecycleError):
                rio.validate_container_network(bad, 30002, 30002)

    def test_unpublished_running_and_escape_modes_fail(self):
        for mode in ("host", "none", "container:other", "service:other", "macvlan"):
            bad = container()
            bad["HostConfig"]["NetworkMode"] = mode
            with self.subTest(mode=mode), self.assertRaises(rio.LifecycleError):
                rio.validate_container_network(bad, 30002, 30002)
        for setting in ({"PublishAllPorts": True}, {"Privileged": True}, {"PidMode": "host"}, {"IpcMode": "host"}):
            bad = container()
            bad["HostConfig"].update(setting)
            with self.assertRaises(rio.LifecycleError):
                rio.validate_container_network(bad, 30002, 30002)
        bad = container()
        bad["NetworkSettings"]["Ports"] = {}
        with self.assertRaises(rio.LifecycleError):
            rio.validate_container_network(bad, 30002, 30002)

    def test_compose_bridge_requires_independent_driver_allowlist(self):
        data = container()
        data["HostConfig"]["NetworkMode"] = "old-compose_default"
        data["NetworkSettings"]["Networks"] = {"old-compose_default": {}}
        with self.assertRaises(rio.LifecycleError):
            rio.validate_container_network(data, 30002, 30002)
        rio.validate_container_network(data, 30002, 30002, allowed_bridge_networks={"old-compose_default"})
        data["NetworkSettings"]["Networks"]["another-network"] = {}
        with self.assertRaises(rio.LifecycleError):
            rio.validate_container_network(data, 30002, 30002, allowed_bridge_networks={"old-compose_default"})

    def test_legacy_host_ipc_requires_explicit_opt_in_and_safe_binds(self):
        service = {**self.service, "ipc": "host"}
        data = container()
        data["HostConfig"]["IpcMode"] = "host"
        with self.assertRaises(rio.LifecycleError):
            rio.validate_published(service, 30002, 30002)
        with self.assertRaises(rio.LifecycleError):
            rio.validate_container_network(data, 30002, 30002)
        rio.validate_published(service, 30002, 30002, allow_host_ipc=True)
        rio.validate_container_network(data, 30002, 30002, allow_host_ipc=True)
        service["network_mode"] = "host"
        data["HostConfig"]["NetworkMode"] = "host"
        with self.assertRaises(rio.LifecycleError):
            rio.validate_published(service, 30002, 30002, allow_host_ipc=True)
        with self.assertRaises(rio.LifecycleError):
            rio.validate_container_network(data, 30002, 30002, allow_host_ipc=True)


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.key"
        self.path.write_text(FAKE_KEY + "\n")
        self.path.chmod(0o600)

    def test_metadata_never_reads_value(self):
        with mock.patch.object(rio.os, "read", side_effect=AssertionError("must not read")):
            rio.validate_key_metadata(self.path)

    def test_key_mode_symlink_empty_and_oversized_fail(self):
        for mode in (0o644, 0o400, 0o660):
            self.path.chmod(mode)
            with self.assertRaisesRegex(rio.LifecycleError, "^key_file_invalid$"):
                rio.validate_key_metadata(self.path)
        self.path.chmod(0o600)
        link = self.path.with_name("link")
        link.symlink_to(self.path)
        with self.assertRaises(rio.LifecycleError):
            rio.validate_key_metadata(link)
        for value in ("", "x" * 4097):
            self.path.write_text(value)
            with self.assertRaises(rio.LifecycleError):
                rio.validate_key_metadata(self.path)

    def test_fifo_does_not_block(self):
        fifo = self.path.with_name("fifo")
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(rio.LifecycleError):
            rio.validate_key_metadata(fifo)

    def test_bad_owner_and_multiline_value_fail_without_leak(self):
        actual = os.stat(self.path)
        values = list(actual)
        values[stat.ST_UID] = os.geteuid() + 12345
        with mock.patch.object(rio.os, "fstat", return_value=os.stat_result(values)):
            with self.assertRaises(rio.LifecycleError):
                rio.validate_key_metadata(self.path)
        self.path.write_text(FAKE_KEY + "\nsecond-line")
        with self.assertRaises(rio.LifecycleError) as raised:
            rio._read_key(self.path)
        self.assertNotIn(FAKE_KEY, str(raised.exception))


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mode = "ready"
        cls.requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                authorized = self.headers.get("Authorization") == "Bearer " + FAKE_KEY
                cls.requests.append((self.path, authorized))
                if cls.mode == "slow":
                    time.sleep(0.4)
                if cls.mode == "trickle":
                    try:
                        for byte in b"HTTP/1.1 200 OK\r\n":
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.03)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                if cls.mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "/must-not-follow")
                    self.end_headers()
                    return
                if cls.mode == "auth-error" or (not authorized and cls.mode != "auth-disabled"):
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.path == "/health":
                    self.send_response(503 if cls.mode == "stale" else 200)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {"data": [{"id": "wrong" if cls.mode == "wrong" else "glm-5.3"}]}
                if cls.mode == "multiple":
                    payload["data"].append({"id": "another-model"})
                raw = json.dumps(payload).encode()
                if cls.mode == "malformed":
                    raw = FAKE_KEY.encode()
                if cls.mode == "oversized":
                    raw = b"x" * 1048577
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        # HTTPServer otherwise performs reverse DNS during construction, which
        # depends on the worker's resolver and is irrelevant to loopback tests.
        with mock.patch.object(socket, "getfqdn", return_value="localhost"):
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        type(self).mode = "ready"
        type(self).requests = []
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.key"
        self.path.write_text(FAKE_KEY)
        self.path.chmod(0o600)

    def test_authenticated_health_and_exact_model_required(self):
        self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path), "ready")
        self.assertEqual(self.requests, [("/v1/models", False), ("/health", True), ("/v1/models", True)])

    def test_stale_health_wrong_model_auth_and_bad_responses(self):
        for mode, expected in (("stale", "not_ready"), ("wrong", "wrong_model"),
                               ("multiple", "wrong_model"), ("auth-error", "auth_error"),
                               ("auth-disabled", "auth_error"), ("malformed", "not_ready"),
                               ("oversized", "not_ready")):
            type(self).mode = mode
            with self.subTest(mode=mode):
                self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path), expected)

    def test_redirects_never_follow_and_proxy_env_ignored(self):
        type(self).mode = "redirect"
        self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path), "not_ready")
        self.assertEqual(self.requests, [("/v1/models", False)])
        type(self).mode = "ready"
        with mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1"}):
            self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path), "ready")

    def test_timeout_includes_slow_headers_and_trickling_response(self):
        for mode in ("slow", "trickle"):
            type(self).mode = mode
            begin = time.monotonic()
            with self.subTest(mode=mode):
                self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path, timeout=0.07), "not_ready")
                self.assertLess(time.monotonic() - begin, 0.3)

    def test_bad_key_and_endpoint_fail_without_output(self):
        self.path.chmod(0o644)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path), "auth_error")
            self.assertEqual(rio.probe(self.endpoint, "glm-5.3", None), "auth_error")
            for url in ("http://localhost:30002/v1", "http://10.1.2.3:30002/v1", "http://127.0.0.1:30002/v1?x=1",
                        "http://" + ":".join(("synthetic-user", "synthetic-password")) + "@127.0.0.1:30002/v1",
                        "https://127.0.0.1:30002/v1"):
                self.assertEqual(rio.probe(url, "glm-5.3", self.path), "not_ready")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_key_trailing_newline_is_rejected_without_request_or_leak(self):
        for ending in ("\n", "\r\n", "\r"):
            self.path.write_text(FAKE_KEY + ending)
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(ending=repr(ending)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(rio.probe(self.endpoint, "glm-5.3", self.path), "auth_error")
                self.assertEqual(self.requests, [])
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
