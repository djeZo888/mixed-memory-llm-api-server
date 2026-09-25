"""Passive route checks with native auth source and explicit ASGI/dependency doubles.

No SGLang process, HTTP listener, GPU, or real inference is exercised. Optional
H005_PINNED_TEXT_SOURCE enables full pinned upstream AST/source checks as well.
"""
import ast
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

from tests.lifecycle import test_sglang38_file_auth as fixture

ROOT = fixture.ROOT
pair = fixture.load("pair_passive_readiness", ROOT / "scripts/runtime/sglang38_pair_file_auth.py")


class ServerStatus(Enum):
    # Public commit 0bcd822377da7b5718e674eaf9c870d349424dd1; exact native names.
    Up = "Up"
    Starting = "Starting"
    UnHealthy = "UnHealthy"


class Route:
    def __init__(self, path, endpoint, methods):
        self.path, self.endpoint, self.methods = path, endpoint, methods

    def matches(self, scope):
        return (1, {"endpoint": self.endpoint}) if (
            scope["path"] == self.path and scope["method"] in self.methods) else (0, {})


class App(fixture.App):
    """Small ASGI router only; middleware is the exact checked-in native source."""
    def add_api_route(self, path, endpoint, *, methods, include_in_schema):
        assert include_in_schema is False
        self.routes.append(Route(path, endpoint, methods))

    async def dispatch(self, scope, receive, send):
        self.calls.append(scope["path"])
        for route in self.routes:
            if route.matches(scope)[0] == 1:
                response = await route.endpoint()
                return await response(scope, receive, send)
        return await fixture.Response({}, status_code=404)(scope, receive, send)


class PairReadinessTests(unittest.TestCase):
    def setUp(self):
        self.dependencies = fixture.synthetic_dependencies()
        self.dependencies.start()
        sys.modules["fastapi.responses"].JSONResponse = fixture.Response
        self.addCleanup(self.dependencies.stop)
        self.key = "synthetic-readiness-key"

    def server(self, slot="gpu1"):
        self.base = pair.pinned_base(ROOT / "scripts/runtime/sglang38_file_auth.py")
        pair.bind_variant(self.base, slot)
        manager = types.SimpleNamespace(server_status=ServerStatus.Starting,
                                       served_model_name=pair.SLOTS[slot]["served_model_name"])
        server = types.SimpleNamespace(app=App(), ServerStatus=ServerStatus,
                                       _global_state=types.SimpleNamespace(tokenizer_manager=manager))
        self.base.install_auth(server, fixture.native.add_api_key_middleware, self.key)
        return server, manager

    def response(self, server, key="synthetic-readiness-key", method="GET"):
        events = fixture.request(server.app, "/v1/readiness", key=key, method=method)
        return events[0]["status"], json.loads(events[1]["body"])

    def warmup(self, server, *, success=True):
        abort, ready = mock.Mock(), mock.Mock()
        generate = {"text": "x", "meta_info": {"completion_tokens": 1 if success else 0}}
        replies = [(200, {"is_generation": True}), (200, generate)]
        with mock.patch.object(self.base, "_request", side_effect=replies) as request:
            warmup = self.base.make_warmup(server, self.key, abort, ready,
                                          self.base.time.monotonic() + 10)
            result = warmup(types.SimpleNamespace(port=30004))
        self.assertEqual([(c.args[1], c.args[2]) for c in request.call_args_list],
                         [("GET", "/model_info"), ("POST", "/generate")])
        self.assertEqual(result, success)
        self.assertEqual(abort.call_count, int(not success))
        self.assertEqual(ready.call_count, int(success))

    def test_slot_alias_and_full_body_before_and_after_authenticated_warmup(self):
        for slot, alias in (("gpu0", "qwen3.8-27b-gpu0"), ("gpu1", "qwen3.8-27b")):
            with self.subTest(slot=slot):
                server, manager = self.server(slot)
                self.assertEqual(self.response(server), (503, {
                    "schema_version": 1, "model_alias": alias, "ready": False,
                    "state": "starting", "admitting": None}))
                # Native health can set Up; that alone cannot bypass warmup.
                manager.server_status = ServerStatus.Up
                self.assertEqual(self.response(server)[1]["state"], "starting")
                self.warmup(server)
                self.assertEqual(self.response(server), (200, {
                    "schema_version": 1, "model_alias": alias, "ready": True,
                    "state": "up", "admitting": None}))

    def test_native_auth_rejects_missing_wrong_keys_before_route(self):
        server, manager = self.server()
        for status in ServerStatus:
            manager.server_status = status
            for key in (None, "wrong-synthetic-key", ""):
                with self.subTest(status=status, key=key):
                    self.assertEqual(self.response(server, key)[0], 401)
        self.assertEqual(server.app.calls, [])
        self.warmup(server)
        self.assertEqual(self.response(server)[0], 200)
        self.assertEqual(self.response(server, method="POST")[0], 404)

    def test_unhealthy_unknown_and_wrong_alias_never_report_ready(self):
        server, manager = self.server()
        self.warmup(server)
        manager.server_status = ServerStatus.UnHealthy
        self.assertEqual(self.response(server)[1]["state"], "unhealthy")
        for bad in (None, "Up", True, 1, Enum("Other", {"Up": "Up"}).Up):
            manager.server_status = bad
            self.assertEqual(self.response(server), (503, {
                "schema_version": 1, "model_alias": "qwen3.8-27b", "ready": False,
                "state": "unknown", "admitting": None}))
        manager.server_status = ServerStatus.Up
        manager.served_model_name = "qwen3.8-27b-gpu0"
        self.assertEqual(self.response(server)[1]["state"], "unknown")
        del server._global_state.tokenizer_manager
        self.assertEqual(self.response(server)[0], 503)
        del server._global_state
        self.assertEqual(self.response(server)[1]["state"], "unknown")

    def test_missing_or_drifted_enum_is_unknown_even_after_warmup(self):
        server, manager = self.server()
        self.warmup(server)
        for enum_type in (None, types.SimpleNamespace(Up=ServerStatus.Up),
                          Enum("Changed", {"New": "new"})):
            server.ServerStatus = enum_type
            self.assertEqual(self.response(server)[1]["state"], "unknown")
        server.ServerStatus = Enum("Changed", {"New": "new"})
        manager.server_status = server.ServerStatus.New
        self.assertEqual(self.response(server)[1]["state"], "unknown")

    def test_failed_warmup_leaves_route_unready(self):
        server, manager = self.server()
        manager.server_status = ServerStatus.Up
        with self.assertLogs(self.base.LOGGER, level="ERROR"):
            self.warmup(server, success=False)
        self.assertEqual(self.response(server)[0], 503)

    def test_passive_reads_do_not_call_health_request_or_manager_work(self):
        server, manager = self.server()
        self.warmup(server)
        manager.generate_request = mock.Mock(side_effect=AssertionError("generation"))
        manager.send_to_scheduler = mock.Mock(side_effect=AssertionError("queue"))
        manager.idle_grace = 123.0  # Sentinel is unrelated to readiness.
        before = dict(vars(manager))
        server.health_generate = mock.Mock(side_effect=AssertionError("health"))
        with mock.patch.object(self.base, "_request", side_effect=AssertionError("HTTP")), \
             mock.patch.object(self.base, "time", types.SimpleNamespace(
                 monotonic=mock.Mock(side_effect=AssertionError("clock")))):
            for _ in range(20):
                self.assertEqual(self.response(server)[0], 200)
        self.assertEqual(vars(manager), before)
        manager.generate_request.assert_not_called()
        manager.send_to_scheduler.assert_not_called()
        server.health_generate.assert_not_called()

    def test_installation_fails_without_auth_duplicate_or_started_middleware(self):
        server, _ = self.server()
        for mutate in (lambda: None,
                       lambda: setattr(server.app, "_llmctl_file_auth_installed", False),
                       lambda: setattr(server.app, "middleware_stack", object())):
            mutate()
            with self.assertRaisesRegex(self.base.LaunchError, "pair_readiness_installation_invalid"):
                pair.install_readiness(self.base, server, "gpu1", mock.Mock())
        self.assertEqual(len(server.app.routes), 1)


@unittest.skipUnless(os.environ.get("H005_PINNED_TEXT_SOURCE"), "set H005_PINNED_TEXT_SOURCE for full upstream source checks")
class PinnedReadinessSourceTests(unittest.TestCase):
    def test_exact_upstream_enum_initialization_and_custom_warmup_hook(self):
        root = Path(os.environ["H005_PINNED_TEXT_SOURCE"])
        hashes = {
            "srt/entrypoints/http_server.py": "d8cc81f8d9866957dd4c0aa59917afa3d4d7d0e28eefaff0a9800157ed068a43",
            "srt/managers/tokenizer_manager.py": "bdfaa4f4f214515f2138a3a82e8215882735490dfa85c271d2c41830b682ad33",
        }
        trees = {}
        for name, expected in hashes.items():
            raw = (root / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            trees[name] = ast.parse(raw)
        tokenizer = trees["srt/managers/tokenizer_manager.py"]
        enum = next(n for n in tokenizer.body if isinstance(n, ast.ClassDef) and n.name == "ServerStatus")
        namespace = {"Enum": Enum}
        exec(compile(ast.Module(body=[enum], type_ignores=[]), "pinned-tokenizer-enum", "exec"), namespace)
        self.assertEqual([(s.name, s.value) for s in namespace["ServerStatus"]],
                         [(s.name, s.value) for s in ServerStatus])
        manager = next(n for n in tokenizer.body if isinstance(n, ast.ClassDef) and n.name == "TokenizerManager")
        status_assignments = [n for n in ast.walk(manager) if isinstance(n, ast.Assign)
                              and any(isinstance(t, ast.Attribute) and t.attr == "server_status" for t in n.targets)]
        self.assertEqual([ast.unparse(n.value) for n in status_assignments], ["ServerStatus.Starting"])
        http = trees["srt/entrypoints/http_server.py"]
        hook = next(n for n in http.body if isinstance(n, ast.FunctionDef) and n.name == "_wait_and_warmup")
        self.assertIn("execute_warmup_func", [a.arg for a in hook.args.args])
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "execute_warmup_func" for n in ast.walk(hook)), 1)
        health = next(n for n in http.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_generate")
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and n.func.attr == "generate_request" for n in ast.walk(health)))


if __name__ == "__main__":
    unittest.main()
