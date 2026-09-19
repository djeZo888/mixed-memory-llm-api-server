"""Exact-body and raw-provenance seams, synthetic offline transport only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import client, fixtures, glmrepair as g
from tests.test_glmrepair_driver import wire, SequenceTests

class ExactG1(unittest.TestCase):
    def test_provenance_changes_only_authorized_fields(self):
        body = fixtures.build_sample(g.MODEL, 108, '53fedfbaa93f687629b4e742', 'original-nonce')['body']
        changed = json.loads(g.provenance_body(fixtures.canonical(body)))
        expected = copy.deepcopy(body)
        expected.update(stream=False, return_tokens=True, verbose=True)
        del expected['stream_options']
        self.assertEqual(changed, expected)
        with tempfile.TemporaryDirectory() as directory:
            raw = json.loads(wire(stream=False))
            raw['__verbose'] = {'content': 'reason</think>{"ok":true}</think>{"ok":true}', 'tokens': [5, 6, 7]}
            response = fixtures.canonical(raw)
            result = client.run_diagnostic_request(fixtures.canonical(changed), lambda *a: iter([response]),
                sample_id='raw', private_dir=directory, summary_path=Path(directory)/'summary.jsonl', timeout=1)
            self.assertEqual(Path(result['private_response_path']).read_bytes(), response)
            comparison = g.provenance_comparison(result)
            self.assertEqual(comparison['generated_token_ids'], [5, 6, 7])
            self.assertEqual(len(comparison['native_text']['think_close_offsets']), 2)
        for key, value in [('stream', True), ('verbose', False), ('max_tokens', 512), ('tools', [])]:
            bad = {**changed, key: value}
            with self.assertRaises(fixtures.HarnessError): client.run_diagnostic_request(fixtures.canonical(bad), Mock())

    def test_duplicate_condition_preserves_strict_failure(self):
        for content in ['{"a":1}</think>{"a":1}', '{"a":1} {"a":1}']:
            self.assertTrue(g.duplicate_json(content))
        for content in ['{"a":1}', '{"a":1}{"a":2}', 'partial']:
            self.assertFalse(g.duplicate_json(content))

    def test_sequence_has_one_load_and_conditional_second_only(self):
        for duplicate in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                d, host = SequenceTests().create(directory)
                d.armed['campaign'] = g.CAMPAIGN
                sample = fixtures.build_sample(g.MODEL, 108, '53fedfbaa93f687629b4e742', 'original-nonce')
                raw = fixtures.serialize_validate(sample)
                d.fixture_cache[g.FIXTURE_KEY] = sample
                d.loaded = Mock(return_value='cid')
                d.counter = Mock(return_value=lambda raw: {'input_tokens': 3546})
                d.telemetry_window = Mock(return_value={})
                seen = []
                def req(cid, body, name):
                    seen.append((body, name))
                    content = fixtures.canonical(sample['scorer']['retrieval']).decode()
                    if duplicate: content += '</think>' + content
                    return {'summary': {'status': 'COMPLETE', 'counters': {'cached_tokens': 0}, 'response_retained_complete': False},
                            'parsed': {'message': {'content': content}, 'finish_reason': 'stop'}}
                d.request = req
                with patch.object(g, 'exact_body', return_value=(raw, sample)), patch.object(fixtures, 'validate_count', side_effect=lambda x,*a:x):
                    d.sequence()
                d.loaded.assert_called_once()
                self.assertEqual(seen[0], (raw, 'exact-stream'))
                self.assertEqual(len(seen), 2 if duplicate else 1)
                self.assertTrue(Path(directory, 'first-result.json').exists())

if __name__ == '__main__': unittest.main()
