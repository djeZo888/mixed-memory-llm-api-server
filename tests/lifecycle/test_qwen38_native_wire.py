"""Source controls for the native Q38C wire gate; actual native image NOT_TESTED.

These tests inspect fixture wiring and literal payloads. They never extract or
execute an upstream normalizer, import SGLang, or manufacture native evidence.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/lifecycle/sglang38_fixture/run_pinned_image.py"
TREE = ast.parse(FIXTURE.read_text())
FUNCTION = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
                and node.name == "check_native_parser_template")


def assigned(name):
    return next(node.value for node in ast.walk(FUNCTION) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


def wires():
    tool = ast.literal_eval(assigned("tool_dict"))

    class LiteralNames(ast.NodeTransformer):
        def visit_Name(self, node):
            value = {"ALIAS": "qwen3.8-27b", "tool_dict": tool}[node.id]
            return ast.parse(repr(value), mode="eval").body

    return ast.literal_eval(LiteralNames().visit(ast.parse(ast.unparse(assigned("wires")), mode="eval")))


class NativeWireSourceTests(unittest.TestCase):
    def test_exact_ordinary_and_continuation_wire_has_none_and_no_template_override(self):
        payloads = wires()
        self.assertEqual(set(payloads), {"ordinary", "tool_continuation"})
        for name, wire in payloads.items():
            with self.subTest(case=name):
                self.assertEqual(wire["model"], "qwen3.8-27b")
                self.assertEqual(wire["reasoning_effort"], "none")
                self.assertIs(wire["stream"], True)
                self.assertNotIn("chat_template_kwargs", wire)
                self.assertNotIn("reasoning", wire)
                self.assertNotIn("input_ids", wire)
        self.assertEqual(set(payloads["ordinary"]), {"model", "reasoning_effort", "stream", "messages"})

    def test_tool_history_contains_correlated_call_and_result_with_wire_json_arguments(self):
        wire = wires()["tool_continuation"]
        self.assertEqual([message["role"] for message in wire["messages"]], ["user", "assistant", "tool"])
        call = wire["messages"][1]["tool_calls"][0]
        self.assertEqual(call["id"], wire["messages"][2]["tool_call_id"])
        self.assertEqual(call["type"], "function")
        self.assertEqual(call["function"]["name"], wire["tools"][0]["function"]["name"])
        self.assertIsInstance(call["function"]["arguments"], str)
        self.assertEqual(json.loads(call["function"]["arguments"]), {"path": "fixture.txt", "count": 3})

    def test_real_native_request_constructor_and_full_prompt_helper_are_called(self):
        calls = {ast.unparse(node.func): node for node in ast.walk(FUNCTION) if isinstance(node, ast.Call)}
        for name in ("ChatCompletionRequest.model_validate_json", "OpenAIServingChat",
                     "template_manager.load_chat_template", "serving._process_messages"):
            self.assertIn(name, calls)
        self.assertLess(calls["ChatCompletionRequest.model_validate_json"].lineno,
                        calls["serving._process_messages"].lineno)
        self.assertEqual(ast.unparse(calls["ChatCompletionRequest.model_validate_json"].args[0]), "json.dumps(wire)")
        self.assertEqual(ast.unparse(calls["serving._process_messages"].args[0]), "request")
        self.assertEqual(ast.literal_eval(calls["serving._process_messages"].keywords[0].value), False)
        self.assertNotIn("normalize_reasoning_inputs", ast.unparse(FUNCTION))

    def test_server_default_is_false_and_native_normalization_is_observed_before_merge(self):
        calls = [node for node in ast.walk(FUNCTION) if isinstance(node, ast.Call)]
        defaults = [keyword.value for node in calls for keyword in node.keywords
                    if keyword.arg == "default_chat_template_kwargs"]
        self.assertEqual([ast.literal_eval(value) for value in defaults], [{"enable_thinking": False}])
        required = {node.args[1].value: node for node in calls
                    if isinstance(node.func, ast.Name) and node.func.id == "require"
                    and len(node.args) == 2 and isinstance(node.args[1], ast.Constant)}
        normalization = required["native_none_normalization_failed"]
        merge = required["native_false_default_merge_failed"]
        self.assertLess(normalization.lineno, merge.lineno)
        for node in (normalization, merge):
            expected = [item for item in ast.walk(node.args[0]) if isinstance(item, ast.Dict)]
            self.assertEqual(ast.literal_eval(expected[0]), {"thinking": False, "enable_thinking": False})
        self.assertIn("processed.require_reasoning is False", ast.unparse(merge))

    def test_native_transformers_template_rendering_is_used_without_direct_jinja_fallback(self):
        text = ast.unparse(FUNCTION)
        self.assertIn("class RecordingTokenizer(PreTrainedTokenizerFast)", text)
        self.assertIn("super().apply_chat_template(*args, **kwargs)", text)
        self.assertIn("tokenizer.decode(processed.prompt_ids", text)
        for forbidden in ("ImmutableSandboxedEnvironment", ".render(", "from_pretrained(", "patch.object("):
            self.assertNotIn(forbidden, text)

    def test_both_cases_require_closed_empty_think_prefix_and_native_parser_checks_remain(self):
        text = ast.unparse(FUNCTION)
        strings = [node.value for node in ast.walk(FUNCTION)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertIn("<|im_start|>assistant\n<think>\n\n</think>\n\n", strings)
        for code in ("native_none_template_arguments_failed", "native_none_prompt_prefix_failed",
                     "native_no_thinking_tool_continuation_template_failed",
                     "native_structured_tool_parser_failed", "native_fragmented_tool_parser_failed",
                     "native_empty_think_leaked_to_final"):
            self.assertIn(code, strings)
        self.assertIn("for case, wire in wires.items()", text)

    def test_template_and_upstream_prompt_sources_remain_pinned(self):
        root = FIXTURE.parent
        provenance = json.loads((root / "provenance.json").read_text())
        self.assertEqual(hashlib.sha256((root / "chat_template.jinja").read_bytes()).hexdigest(),
                         "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041")
        self.assertEqual(provenance["sources"]["srt/entrypoints/openai/protocol.py"]["sha256"],
                         "a7cf91c1db5d076b9ad647248351f10b0249153998b974ed4d00610306b01653")
        self.assertEqual(provenance["sources"]["srt/entrypoints/openai/serving_chat.py"]["sha256"],
                         "7b05e6ab1d09a71ce253040c9cd62ea7c55a52020b44cf9b76d91c8df9e23240")

    def test_fixture_import_keeps_native_execution_lazy(self):
        spec = importlib.util.spec_from_file_location("q38b_wire_fixture_source_control", FIXTURE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.check_native_parser_template))
        top_imports = [node for node in TREE.body if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any((node.module or "").startswith(("sglang", "transformers", "tokenizers"))
                             for node in top_imports))


if __name__ == "__main__":
    unittest.main()
