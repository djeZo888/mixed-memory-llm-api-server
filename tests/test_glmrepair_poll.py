"""Bounded offline checks for the one-variable CPU poll control."""
import copy
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import fixtures, glmrepair as g, profiles


class PollControl(unittest.TestCase):
    def summary(self):
        return {'status': 'OUTPUT_LIMIT', 'response_retained_complete': True,
                'counters': {'decode_tokens': 32, 'decode_ms': 6200,
                             'completion_tokens': 32, 'cached_tokens': 0,
                             'prompt_tokens': 2388, 'evaluated_prompt_tokens': 2388}}

    def test_gate_exact_rate_and_remaining_boundaries(self):
        summary = self.summary()
        self.assertTrue(g.poll_gate(summary, 180))
        self.assertFalse(g.poll_gate(summary, 179.999))
        summary['counters']['decode_ms'] = 6200.001
        self.assertFalse(g.poll_gate(summary, 180))
        summary['counters']['decode_ms'] = 6199.999
        self.assertTrue(g.poll_gate(summary, 180))
        summary['status'] = 'COMPLETE'
        self.assertTrue(g.poll_gate(summary, 180))

    def test_gate_rejects_uncached_or_native_counter_failure(self):
        for key, value in (('cached_tokens', 1), ('prompt_tokens', 2387),
                           ('evaluated_prompt_tokens', 2387), ('decode_tokens', 1),
                           ('decode_ms', 0), ('decode_ms', -1)):
            with self.subTest(key=key, value=value):
                summary = self.summary()
                summary['counters'][key] = value
                self.assertFalse(g.poll_gate(summary, 180))
        for status in ('TRANSPORT_FAILURE', 'UNPARSED', None):
            summary = self.summary(); summary['status'] = status
            self.assertFalse(g.poll_gate(summary, 180))

    def test_manifest_changes_only_campaign_identity_and_poll_arguments(self):
        prior = profiles.glmrepair_manifest(profiles.GLMREPAIR_G1_CAMPAIGN)
        expected = json.loads(json.dumps(prior).replace(profiles.GLMREPAIR_G1_CAMPAIGN,
                                                       profiles.GLMREPAIR_POLL_CAMPAIGN))
        for field in ('native_argv', 'create_argv'):
            expected[field].extend(['--poll', '0', '--poll-batch', '50'])
        expected['create_shell'] = shlex.join(expected['create_argv'])
        actual = profiles.glmrepair_manifest(profiles.GLMREPAIR_POLL_CAMPAIGN)
        self.assertEqual(actual, expected)
        plan = profiles.trial_order('glmrepair', campaign=profiles.GLMREPAIR_POLL_CAMPAIGN)
        self.assertEqual(len(plan['trials']), 2)
        self.assertEqual([row['output_cap'] for row in plan['trials']], [32, 256])
        self.assertTrue(plan['trials'][1]['conditional'])
        self.assertEqual(plan['maximum_request_seconds'], 7200)
        self.assertTrue(plan['restoration_outside_budget'])
        arm = {'scope': 'glmrepair', 'campaign': profiles.GLMREPAIR_POLL_CAMPAIGN,
               'manifests': [actual], 'trial_plan': plan}
        self.assertEqual(profiles.validate_arm_scope(arm), 'glmrepair')
        changed = copy.deepcopy(arm)
        changed['manifests'][0]['native_argv'][-3] = '1'
        with self.assertRaises(ValueError):
            profiles.validate_arm_scope(changed)

    def test_notes_remain_noncontrolling_but_explicit_pause_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            note = b'Future STOP/PAUSE notes are historical; current work continues.'
            (task / 'incoming-latest.md').write_bytes(note)
            g.checkpoint(task)
            observed = json.loads((task / 'incoming-observed.json').read_bytes())
            self.assertEqual(observed['sha256'], fixtures.digest(note))
            (task / 'run-control.json').write_text('{"action":"PAUSE"}')
            with self.assertRaisesRegex(RuntimeError, '^ROOT_CONTROL_PAUSE$'):
                g.checkpoint(task)

    def test_exact_control_rejects_different_bytes_without_request(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory); (task / 'private').mkdir()
            (task / 'private' / 'control.request.json').write_bytes(b'{"max_tokens":32}')
            with self.assertRaises(ValueError):
                g.exact_control(task)


if __name__ == '__main__':
    unittest.main()
