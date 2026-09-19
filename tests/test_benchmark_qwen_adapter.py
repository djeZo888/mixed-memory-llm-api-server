"""Benchmark adapter through the real pinned main; synthetic native seams only.

No model/image/HTTP/GPU process is used. Reuse the existing captured middleware
ASGI harness; actual native preparation/resolution and image acceptance remain
NOT_TESTED. This exercises the shipped main, auth and alias installation paths.
"""
import copy
import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark import profiles, qwen_launcher

spec = importlib.util.spec_from_file_location("benchmark_native_auth_fixture",
    ROOT / "tests/lifecycle/test_sglang38_file_auth.py")
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)


def handler_module(name, class_name):
    module = types.ModuleType(name)
    exec(f"class {class_name}:\n    def _validate_request(self, request):\n        return None\n", module.__dict__)
    return module


class AdapterIntegrationTests(unittest.TestCase):
    def exercise(self, capacity, tp, *, bad_pool=False, bad_environment=False):
        base = qwen_launcher.pinned_base(ROOT / "scripts/runtime/sglang38_file_auth.py")
        manifest = profiles.command_manifest("Q" + str(tp), capacity)
        argv = qwen_launcher.bind_variant(base, capacity, tp)
        self.assertEqual(argv[4:], manifest["native_argv"])
        create = manifest["create_argv"]
        environment = dict(create[index + 1].split("=", 1) for index, value in enumerate(create) if value == "--env")
        self.assertEqual(environment, {**base.CACHE_ENVIRONMENT, **base.EXTENSION_ENVIRONMENT})
        if bad_environment:
            environment.pop("SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN")
        order, captured = [], {}
        key = base._PrivateKey("synthetic-benchmark-auth-key")
        raw = fixture.args_fixture(base.EXTENSION_CONTEXT)

        def prepare(native_argv):
            order.append("prepare")
            captured["argv"] = list(native_argv)
            # Synthetic prepare parses the *actual serialized* argv rather than
            # taking capacity/TP from the test's intended tuple.
            flags = dict(zip(native_argv[:-2:2], native_argv[1:-2:2]))
            for flag, value in flags.items():
                field = flag[2:].replace("-", "_")
                if field == "fp8_gemm_backend":
                    field = "fp8_gemm_runner_backend"
                old = getattr(raw, field)
                if isinstance(old, int):
                    value = int(value)
                elif isinstance(old, float):
                    value = float(value)
                elif isinstance(old, dict):
                    value = json.loads(value)
                setattr(raw, field, value)
            return raw

        def resolve(args):
            order.append("resolve")
            result = fixture.resolved_args_fixture(args)
            if bad_pool:
                result.max_total_tokens += 1
            return result

        app = fixture.App()
        server = types.SimpleNamespace(app=app,
            _global_state=types.SimpleNamespace(tokenizer_manager=types.SimpleNamespace(server_status="Starting")),
            ServerStatus=types.SimpleNamespace(Up="Up"))
        def launch(args, execute_warmup_func):
            order.append("launch")
            captured["args"] = dataclasses.asdict(args)
            self.assertTrue(execute_warmup_func(args))
        server.launch_server = launch
        chat = handler_module("sglang.srt.entrypoints.openai.serving_chat", "OpenAIServingChat")
        completions = handler_module("sglang.srt.entrypoints.openai.serving_completions", "OpenAIServingCompletion")
        cleanup = mock.Mock()
        modules = {
            "sglang.srt.server_args": types.SimpleNamespace(prepare_server_args=prepare),
            "sglang.srt.arg_groups.overrides": types.SimpleNamespace(resolving_view=resolve),
            "sglang.srt.entrypoints": types.SimpleNamespace(http_server=server),
            "sglang.srt.utils": types.SimpleNamespace(kill_process_tree=cleanup),
            "sglang.srt.utils.auth": fixture.native,
            chat.__name__: chat, completions.__name__: completions,
        }
        with fixture.synthetic_dependencies(), mock.patch.dict(sys.modules, modules), \
                mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(base.importlib.metadata, "version", return_value="0.5.19"), \
                mock.patch.object(base.importlib.metadata, "entry_points", return_value={}), \
                mock.patch.object(base, "read_key", side_effect=lambda path: (order.append("key"), key)[1]) as key_read, \
                mock.patch.object(base.threading, "Timer"), \
                mock.patch.object(base, "_request", side_effect=[(200, {"is_generation": True}),
                    (200, {"text": "x", "meta_info": {"completion_tokens": 1}})]) as transport:
            if bad_pool or bad_environment:
                with self.assertLogs(base.LOGGER, "ERROR"):
                    self.assertEqual(base.main(argv), 1)
                key_read.assert_not_called()
                self.assertNotIn("launch", order)
                return
            self.assertEqual(base.main(argv), 0)
            self.assertEqual(order, ["prepare", "resolve", "key", "launch"])
            key_read.assert_called_once_with("/run/secrets/llm-api-key")
            self.assertEqual(captured["argv"], manifest["native_argv"])
            self.assertEqual(captured["args"]["context_length"], capacity)
            self.assertEqual(captured["args"]["max_total_tokens"], capacity)
            self.assertEqual(captured["args"]["tp_size"], tp)
            self.assertEqual(captured["args"]["served_model_name"], "bench-qwen3.8-27b")
            self.assertEqual(captured["args"]["json_model_override_args"], base.EXTENSION_OVERRIDE_JSON)
            rope = json.loads(captured["args"]["json_model_override_args"])["text_config"]["rope_parameters"]
            self.assertEqual((rope["rope_type"], rope["factor"], rope["original_max_position_embeddings"]), ("yarn", 4.0, 262144))
            self.assertIsNone(captured["args"]["api_key"])
            self.assertIsNone(captured["args"]["admin_api_key"])
            self.assertNotIn(str(key), json.dumps(captured, default=vars))
            self.assertEqual([call.args[2] for call in transport.call_args_list], ["/model_info", "/generate"])
            self.assertTrue(all(call.args[3] is key for call in transport.call_args_list))
            self.assertTrue(all(call.args[0] == 31004 for call in transport.call_args_list))
            self.assertEqual(server._global_state.tokenizer_manager.server_status, "Up")
            # Retained native auth is actually exercised on its ASGI harness.
            for supplied, expected in ((None, 401), ("wrong-synthetic-key", 401), (str(key), 200)):
                events = fixture.request(app, "/v1/models", key=supplied)
                self.assertEqual(next(event["status"] for event in events if event["type"] == "http.response.start"), expected)
            for handler in (chat.OpenAIServingChat, completions.OpenAIServingCompletion):
                instance = handler()
                instance.tokenizer_manager = types.SimpleNamespace(served_model_name="bench-qwen3.8-27b")
                self.assertIsNone(instance._validate_request(types.SimpleNamespace(model="bench-qwen3.8-27b")))
                self.assertEqual(instance._validate_request(types.SimpleNamespace(model="qwen3.8-27b")),
                                 "Requested model does not match the active served model.")
        cleanup.assert_called_once_with(os.getpid(), include_parent=False)

    def test_all_closed_tuples_actual_main_serialization_auth_alias_and_rope(self):
        for capacity in qwen_launcher.CAPACITIES:
            for tp in (1, 2):
                with self.subTest(capacity=capacity, tp=tp):
                    self.exercise(capacity, tp)

    def test_resolved_pool_drift_refused_before_key_or_launch(self):
        self.exercise(16384, 1, bad_pool=True)

    def test_missing_yarn_environment_refused_before_prepare_key_or_launch(self):
        self.exercise(16384, 2, bad_environment=True)


if __name__ == "__main__":
    unittest.main()
