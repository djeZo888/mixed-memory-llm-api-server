"""Pure boundary tests; no claim of native image/auth/HTTP acceptance."""
import importlib.util
import pathlib
import types
import unittest

spec = importlib.util.spec_from_file_location('flash_tokenize', pathlib.Path(__file__).resolve().parents[1] / 'scripts/runtime/flash/tokenize_adapter.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

class FlashTokenize(unittest.TestCase):
    def payload(self):
        return {'model': a.MODEL, 'messages': [{'role': 'user', 'content': 'Hello'}]}

    def test_defaults_and_caller_preservation(self):
        payload = self.payload(); value = a.normalized_text_request(payload)
        self.assertEqual(value['reasoning_effort'], 'high')
        self.assertEqual(value['chat_template_kwargs'], {'clear_thinking': True})
        self.assertNotIn('reasoning_effort', payload)

    def test_multimodal_is_rejected_before_native_count(self):
        for content in [[{'type': 'image_url', 'image_url': {'url': 'example'}}], [{'type': 'audio', 'text': 'unqualified'}], 3]:
            payload = self.payload(); payload['messages'][0]['content'] = content
            with self.assertRaises(a.ContractError): a.normalized_text_request(payload)

    def test_text_arrays_are_preserved_without_inserted_separator(self):
        payload = self.payload()
        payload['messages'][0]['content'] = [{'type':'text','text':'Hello'}, {'type':'text','text':'world'}]
        value = a.normalized_text_request(payload)
        self.assertEqual(value['messages'][0]['content'], payload['messages'][0]['content'])
        self.assertEqual(''.join(x['text'] for x in value['messages'][0]['content']), 'Helloworld')
        for invalid in [[{'type':'unknown','text':'x'}], [{'type':'text','text':3}], [{'type':'text','text':'x','image_url':'x'}]]:
            payload['messages'][0]['content'] = invalid
            with self.assertRaises(a.ContractError): a.normalized_text_request(payload)

    def test_output_alias_template_and_reasoning_gates(self):
        changes = [{'model':'other'}, {'max_tokens':65537}, {'max_tokens':True}, {'reasoning_effort':'low'}, {'chat_template_kwargs':{'clear_thinking':False}}, {'chat_template_kwargs':{'extra':1}}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(a.ContractError):
                a.normalized_text_request(self.payload() | change)

    def test_native_path_owns_exact_token_count_and_tool_history(self):
        calls = []
        class Serving:
            def _process_messages(self, request, *, is_multimodal):
                calls.append((request, is_multimodal))
                return types.SimpleNamespace(prompt_ids=[1,2,3,4])
        payload = self.payload() | {'tools':[{'type':'function','function':{'name':'weather'}}]}
        result = a.count_native(payload, request_type=types.SimpleNamespace, serving_chat=Serving())
        self.assertEqual(result['count'], 4); self.assertEqual(result['context_limit'], 480000)
        self.assertEqual(calls[0][0].tools, payload['tools']); self.assertFalse(calls[0][1])

    def test_no_character_estimate_fallback(self):
        serving = types.SimpleNamespace(_process_messages=lambda *args, **kw: types.SimpleNamespace(prompt_ids='not ids'))
        with self.assertRaisesRegex(a.ContractError, 'native_token_ids_unavailable'):
            a.count_native(self.payload(), request_type=types.SimpleNamespace, serving_chat=serving)

if __name__ == '__main__': unittest.main()
