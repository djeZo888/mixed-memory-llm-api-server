"""Source-worker alias contracts; extracted native definitions, synthetic I/O.

Requires the explicit pinned public source copy. This is not installed-image,
HTTP transport, generation, or native fixture acceptance.
"""
import ast
import asyncio
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.lifecycle.test_sglang38_file_auth import launcher, ROOT


PREFIX = "sglang.srt.entrypoints.openai."


class Response:
    def __init__(self, content, status_code):
        self.content, self.status_code = content, status_code


class Error:
    def __init__(self, **fields):
        self.fields = fields

    def model_dump(self):
        return self.fields


class HTTPException(Exception):
    pass


class ModelAliasContracts(unittest.TestCase):
    def setUp(self):
        source = Path(os.environ["Q38NEXT_UPSTREAM_ROOT"])
        provenance = json.loads((ROOT / "tests/lifecycle/sglang38_fixture/provenance.json").read_text())
        classes = []
        base = None
        for filename, name, methods in (
            ("serving_base", "OpenAIServingBase", ("handle_request", "create_error_response")),
            ("serving_chat", "OpenAIServingChat", ("_validate_request", "_validate_media_content")),
            ("serving_completions", "OpenAIServingCompletion", ("_validate_request",)),
        ):
            relative = "srt/entrypoints/openai/" + filename + ".py"
            content = (source / relative).read_bytes()
            identity = provenance["sources"][relative]
            self.assertEqual(hashlib.sha256(content).hexdigest(), identity["sha256"])
            self.assertEqual(len(content), identity["bytes"])
            native = next(n for n in ast.parse(content).body if isinstance(n, ast.ClassDef) and n.name == name)
            selected = [copy.deepcopy(n) for n in native.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in methods]
            self.assertEqual(len(selected), len(methods))
            definition = ast.ClassDef(name=name, bases=[ast.Name(id="Base", ctx=ast.Load())] if base else [],
                                      keywords=[], body=selected, decorator_list=[])
            module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                                      definition], type_ignores=[])
            namespace = {"__name__": PREFIX + filename, "Base": base, "monotonic_time": lambda: 0,
                "ORJSONResponse": Response, "ErrorResponse": Error, "GenerateReqInput": SimpleNamespace,
                "EmbeddingReqInput": SimpleNamespace, "HTTPException": HTTPException,
                "DS32EncodingError": type("DS32EncodingError", (Exception,), {}), "logger": Mock(),
                "ChatCompletionMessageGenericParam": type("Message", (), {})}
            exec(compile(ast.fix_missing_locations(module), relative, "exec"), namespace)
            cls = namespace[name]
            if base is None:
                base = cls
            else:
                self.assertFalse(inspect.iscoroutinefunction(cls._validate_request))
                self.assertEqual(tuple(inspect.signature(cls._validate_request).parameters), ("self", "request"))
                classes.append(cls)
        self.chat, self.completion = classes
        self.modules = {PREFIX + "serving_chat": SimpleNamespace(OpenAIServingChat=self.chat),
                        PREFIX + "serving_completions": SimpleNamespace(OpenAIServingCompletion=self.completion)}

    def install(self):
        with patch.dict("sys.modules", self.modules):
            launcher.install_model_validation()

    def handler(self, cls):
        handler = cls()
        handler.tokenizer_manager = SimpleNamespace(served_model_name="qwen3.8-27b",
            request_logger=SimpleNamespace(log_requests=False), model_config=SimpleNamespace(is_multimodal=False),
            server_args=SimpleNamespace(context_length=1000000, allow_auto_truncate=False))
        handler._effective_tools = lambda request: []
        handler._convert_to_internal_request = Mock(side_effect=lambda request, raw: (SimpleNamespace(), request))
        handler._handle_streaming_request = AsyncMock(return_value="stream-dispatch")
        handler._handle_non_streaming_request = AsyncMock(return_value="ordinary-dispatch")
        return handler

    def request(self, *, model="qwen3.8-27b", stream=False):
        return SimpleNamespace(model=model, stream=stream, messages=[SimpleNamespace(content="hello")],
            prompt="hello", return_sampling_mask=False, return_meta_info=False, tool_choice="none",
            max_completion_tokens=None, max_tokens=2048, response_format=None)

    def test_both_paths_reject_before_native_validation_conversion_or_streaming(self):
        self.install()
        for cls in (self.chat, self.completion):
            for stream in (False, True):
                for model in ("unknown", "Qwen3.8-27b", " qwen3.8-27b", "qwen3.8-27b ",
                              "/models", "qwen3.8-27b:adapter", "default", ""):
                    with self.subTest(handler=cls.__name__, stream=stream, model=model):
                        handler = self.handler(cls)
                        # No messages/prompt: original native validation would fail if entered.
                        request = SimpleNamespace(model=model, stream=stream)
                        result = asyncio.run(handler.handle_request(request, None))
                        self.assertEqual(result.status_code, 400)
                        self.assertEqual(result.content, {"object": "error", "message":
                            "Requested model does not match the active served model.",
                            "type": "BadRequestError", "param": None, "code": 400})
                        handler._convert_to_internal_request.assert_not_called()
                        handler._handle_streaming_request.assert_not_awaited()
                        handler._handle_non_streaming_request.assert_not_awaited()

    def test_valid_alias_preserves_native_result_errors_and_both_dispatches(self):
        originals = {cls: cls._validate_request for cls in (self.chat, self.completion)}
        self.install()
        for cls in originals:
            for stream in (False, True):
                handler = self.handler(cls)
                request = self.request(stream=stream)
                self.assertIs(handler._validate_request(request), originals[cls](handler, request))
                self.assertEqual(asyncio.run(handler.handle_request(request, None)),
                                 "stream-dispatch" if stream else "ordinary-dispatch")
                handler._convert_to_internal_request.assert_called_once_with(request, None)
                request.messages, request.prompt = [], ""
                expected = originals[cls](handler, request)
                self.assertIsInstance(expected, str)
                self.assertEqual(handler._validate_request(request), expected)
                handler._convert_to_internal_request.reset_mock()
                result = asyncio.run(handler.handle_request(request, None))
                self.assertEqual(result.status_code, 400)
                self.assertEqual(result.content["message"], expected)
                handler._convert_to_internal_request.assert_not_called()

    def test_original_is_called_once_with_same_objects_and_result_unchanged(self):
        original = self.chat._validate_request
        calls, result = [], object()
        def native(self, request):
            calls.append((self, request))
            return result
        native.__module__, native.__qualname__ = original.__module__, original.__qualname__
        self.chat._validate_request = native
        self.install()
        handler, request = self.handler(self.chat), self.request()
        self.assertIs(handler._validate_request(request), result)
        self.assertEqual(calls, [(handler, request)])
        # Alias authority is the handler's active served name, not a second constant.
        handler.tokenizer_manager.served_model_name = "another-reviewed-alias"
        self.assertIsInstance(handler._validate_request(request), str)
        self.assertEqual(len(calls), 1)

    def test_duplicate_or_async_contract_refused_before_partial_mutation(self):
        self.install()
        installed = self.chat._validate_request, self.completion._validate_request
        with self.assertRaisesRegex(launcher.LaunchError, "model_validation_installation_invalid"):
            self.install()
        self.assertEqual(installed, (self.chat._validate_request, self.completion._validate_request))
        self.setUp()
        unchanged = self.chat._validate_request
        async def incompatible(self, request):
            return None
        self.completion._validate_request = incompatible
        with self.assertRaisesRegex(launcher.LaunchError, "model_validation_installation_invalid"):
            self.install()
        self.assertIs(self.chat._validate_request, unchanged)


if __name__ == "__main__":
    unittest.main()
