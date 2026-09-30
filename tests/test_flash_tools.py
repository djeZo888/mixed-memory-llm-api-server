"""Focused tool-runtime regression tests; optional exact pinned tokenizer proof.

Set FLASH_TOOL_TOKENIZER_JSON to the pinned tokenizer.json and provide pinned
llguidance 0.7.30 plus tokenizers to execute the native CPU-only grammar test.
"""
import importlib.util
import json
import os
from pathlib import Path
import types
import unittest

spec = importlib.util.spec_from_file_location('flash_tools', Path(__file__).resolve().parents[1] / 'scripts/runtime/flash/tool_runtime.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class CompletionGuard(unittest.TestCase):
    def setUp(self):
        class Serving:
            tool_call_parser = 'glm47'
            def _check_for_unstreamed_tool_args(self, *args):
                return 'native-flush'
        a.install_completion_patch(Serving)
        a.install_completion_patch(Serving)
        self.serving = Serving()

    def check(self, calls):
        parser = types.SimpleNamespace(detector=types.SimpleNamespace(prev_tool_call_arr=calls))
        return self.serving._check_for_unstreamed_tool_args(parser, {}, None, 0)

    def test_lone_open_marker_is_error_instead_of_phantom_empty_arguments(self):
        with self.assertRaisesRegex(ValueError, 'flash_incomplete_tool_call_without_name'):
            self.check([{}])

    def test_valid_named_and_no_call_states_retain_native_flush(self):
        self.assertEqual(self.check([]), 'native-flush')
        self.assertEqual(self.check([{'name': 'weather', 'arguments': {'city': 'Ljubljana'}}]), 'native-flush')
        self.assertEqual(self.check([{'name': 'noargs', 'arguments': {}}]), 'native-flush')


@unittest.skipUnless(os.environ.get('FLASH_TOOL_TOKENIZER_JSON'), 'exact pinned tokenizer fixture not provided')
class ExactNativeGrammar(unittest.TestCase):
    def test_added_tool_tokens_and_complete_weather_grammar(self):
        import importlib.metadata
        from llguidance import LLMatcher, LLTokenizer, grammar_from
        from tokenizers import Tokenizer
        self.assertEqual(importlib.metadata.version('llguidance'), '0.7.30')
        raw = Path(os.environ['FLASH_TOOL_TOKENIZER_JSON']).read_text()
        tokenizer = Tokenizer.from_str(raw)
        source = json.loads(raw)
        hf = types.SimpleNamespace(
            added_tokens_decoder={x['id']: types.SimpleNamespace(special=x['special']) for x in source['added_tokens']},
            bos_token_id=None,
            encode=lambda value, add_special_tokens: tokenizer.encode(value, add_special_tokens=add_special_tokens).ids)
        native = LLTokenizer(raw, n_vocab=155136, eos_token=154820)
        self.assertTrue(native.is_special_token(154843))
        grammar = grammar_from('ebnf', 'root ::= "<tool_call>weather<arg_key>city</arg_key><arg_value>" value "</arg_value></tool_call>"\nvalue ::= [^<]*')
        broken = LLMatcher(native, grammar, log_level=0)
        self.assertFalse(broken.consume_token(154843))
        self.assertIn('154843', broken.get_error())
        fixed = a.repair_llguidance_tokenizer(native, hf, n_vocab=155136)
        self.assertFalse(fixed.is_special_token(154843))
        self.assertTrue(fixed.is_special_token(154820))
        self.assertEqual(fixed.vocab_size, native.vocab_size)
        for i in range(native.vocab_size):
            self.assertEqual(fixed.decode_bytes([i]), native.decode_bytes([i]))
            expected_special = native.is_special_token(i) and not (
                i in hf.added_tokens_decoder and not hf.added_tokens_decoder[i].special)
            self.assertEqual(fixed.is_special_token(i), expected_special)
        wire = '<tool_call>weather<arg_key>city</arg_key><arg_value>Ljubljana</arg_value></tool_call>'
        ids = hf.encode(wire, add_special_tokens=False)
        self.assertEqual(fixed.tokenize_str(wire), ids)
        self.assertEqual(fixed.decode_str(ids), wire)
        matcher = LLMatcher(fixed, grammar, log_level=0)
        for token in ids:
            self.assertTrue(matcher.consume_token(token), matcher.get_error())
        self.assertTrue(matcher.is_accepting())
        self.assertTrue(matcher.consume_token(154820))
        self.assertFalse(matcher.is_error())


if __name__ == '__main__':
    unittest.main()
