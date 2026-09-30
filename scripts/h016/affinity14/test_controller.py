"""Offline conditional-trial admission tests; no host or inference operations."""
import copy
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).parent
SPEC = importlib.util.spec_from_file_location('affinity14_controller', HERE / 'controller.py')
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)


def sample():
    # Receipt shape checked against the privately retained actual R8 83/128
    # baseline. These values are synthetic and contain no fixture text or SSE.
    return {
        'label': 'BASELINE128', 'status': 'TRANSPORT_COMPLETE',
        'done': True, 'full_http_drain': True, 'expected_input_tokens': 83,
        'output_budget': 128, 'thinking': False, 'seed': 270927,
        'measurement_role': 'UNPROFILED_BASELINE',
        'correctness': 'UNSCORED_NOT_A_QUALITY_TEST', 'finish_reason': 'length',
        'usage': {'prompt_tokens': 83, 'completion_tokens': 128,
                  'total_tokens': 211, 'prompt_tokens_details': {'cached_tokens': 0}},
        'native_timings': {'cache_n': 0, 'prompt_n': 83, 'prompt_ms': 2000.0,
                           'predicted_n': 128, 'predicted_ms': 12700.0,
                           'predicted_per_second': 10.0},
        'native_settlement': {'status': 'AUTHENTICATED_SLOT_IDLE_AFTER_FULL_DRAIN',
                              'is_processing': False, 'slot_id': 0},
        'raw_chunks': [{'base64': 'ZGF0YTogW0RPTkVdCgo='}],
        'terminal_sse_events': [{'data': '[DONE]'}],
        'first_output_utc': '2026-09-27T17:10:01Z',
        'last_output_utc': '2026-09-27T17:10:14Z',
        'first_output_monotonic_seconds': 101.0,
        'last_output_monotonic_seconds': 114.0,
        'ttft_seconds': 1.0, 'total_seconds': 14.0,
    }


class BaselineEvidenceTests(unittest.TestCase):
    def test_native_n_minus_one_rate(self):
        self.assertEqual(controller.baseline_evidence(sample())['native_tps'], 10.0)

    def test_missing_transport_or_idle_evidence_fails_closed(self):
        cases = [('done', False), ('full_http_drain', False),
                 ('status', 'FAILED_QUARANTINE_NO_RETRY'),
                 ('expected_input_tokens', 82), ('output_budget', 8)]
        for key, value in cases:
            with self.subTest(key=key):
                row = sample(); row[key] = value
                with self.assertRaises(RuntimeError):
                    controller.baseline_evidence(row)
        for key, value in [('status', 'UNKNOWN'), ('is_processing', True)]:
            with self.subTest(idle_field=key):
                row = sample(); row['native_settlement'][key] = value
                with self.assertRaises(RuntimeError):
                    controller.baseline_evidence(row)

    def test_exact_count_and_zero_cache_evidence_required(self):
        cases = [('cache_n', 1), ('cache_n', None), ('prompt_n', 82),
                 ('predicted_n', 127), ('predicted_n', True)]
        for key, value in cases:
            with self.subTest(native_field=key, value=value):
                row = sample(); row['native_timings'][key] = value
                with self.assertRaises(RuntimeError):
                    controller.baseline_evidence(row)
        row = sample(); row['usage']['prompt_tokens'] = 82
        with self.assertRaises(RuntimeError):
            controller.baseline_evidence(row)
        row = sample(); row['usage']['prompt_tokens_details']['cached_tokens'] = 1
        with self.assertRaises(RuntimeError):
            controller.baseline_evidence(row)

    def test_nonfinite_or_nonpositive_native_duration_rejected(self):
        for value in [0, -1, None, True, float('nan'), float('inf')]:
            with self.subTest(duration=value):
                row = sample(); row['native_timings']['predicted_ms'] = value
                with self.assertRaises(RuntimeError):
                    controller.baseline_evidence(row)


class SecondAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((HERE / 'PLAN.json').read_text())
        self.cleanup = controller.timestamp(self.plan['pair_cleanup_utc'])
        self.owner = {'status': controller.SETTLED, 'baseline_done_utc': 'fixture',
                      'guard_failure': None, 'error': 'owned_supervisor_interrupted'}
        self.first = {
            'baseline': controller.baseline_evidence(sample()),
            'settlement': {'status': 'PHYSICAL_SETTLEMENT_ORIGINAL_GLM_READY',
                           'original_glm_ready': True,
                           'native_settled': {'pid_zero': True, 'cgroup_empty': True,
                                              'gpu_compute_empty': True}},
        }

    def gate(self, now=None):
        return controller.second_profile_gate(self.first, self.owner,
                    self.cleanup - 901 if now is None else now, self.plan)

    def test_above_threshold_with_budget_admitted(self):
        result = self.gate()
        self.assertIs(result['admitted'], True)

    def test_equality_and_below_threshold_are_skipped(self):
        threshold = self.plan['second_requires_native_tps_gt']
        for rate in [threshold, threshold - 0.01]:
            with self.subTest(rate=rate):
                self.first['baseline']['native_tps'] = rate
                result = self.gate()
                self.assertIs(result['admitted'], False)
                self.assertTrue(result['reason'])

    def test_less_than_900_seconds_is_not_admitted(self):
        self.assertIs(self.gate(self.cleanup - 899.999)['admitted'], False)

    def test_unsettled_first_profile_is_not_admitted(self):
        self.first['settlement']['status'] = 'SETTLING'
        self.assertIs(self.gate()['admitted'], False)

    def test_owner_guard_failure_or_unexpected_error_is_not_admitted(self):
        for field, value in [('guard_failure', 'gpu_temperature_cutoff'),
                             ('error', 'native_http_failure'),
                             ('baseline_done_utc', None)]:
            with self.subTest(field=field):
                before = copy.deepcopy(self.owner)
                self.owner[field] = value
                self.assertIs(self.gate()['admitted'], False)
                self.owner = before


class FirstAdmissionTests(unittest.TestCase):
    def test_901_seconds_budget_admits_first_without_reserving_two_profiles(self):
        plan = json.loads((HERE / 'PLAN.json').read_text())
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td) / 'worker1-affinity14'; base.mkdir()
            (base / 'PLAN.json').write_text(json.dumps(plan))
            names = {'controller.py', 'PLAN.json'} | {
                profile + '/' + name for profile in controller.PROFILES for name in
                ('candidate_owner.py', 'launch_profile.py', 'benchmark.py',
                 'verify_retained.py', 'telemetry.py')}
            hashes = {}
            for name in names:
                parts = pathlib.Path(name).parts
                path = base / name if len(parts) == 1 else base.parent / ('worker1-' + parts[0]) / parts[1]
                path.parent.mkdir(exist_ok=True)
                if name != 'PLAN.json':
                    path.write_text('# synthetic source closure\n')
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            (base / 'SOURCE-SHA256.json').write_text(json.dumps(hashes))
            go = dict(plan, authorized=True, expires_utc='2026-09-27T17:35:00Z', source_sha256=hashes)
            (base / 'ROOT-AFFINITY14-GO.json').write_text(json.dumps(go))
            with mock.patch.object(controller, 'BASE', base):
                accepted, _ = controller.approved(controller.timestamp('2026-09-27T17:34:59Z'))
                self.assertEqual(accepted, plan)
                with self.assertRaises(RuntimeError):
                    controller.approved(controller.timestamp('2026-09-27T17:35:01Z'))


class SettlementStateTests(unittest.TestCase):
    def test_exec_stop_post_preserves_explicit_second_skip(self):
        state = {'status': 'FOUR_COMPLETE_SECOND_NOT_TESTED_ORIGINAL_GLM_READY',
                 'current_profile': None,
                 'profiles': {controller.PROFILES[1]: {'status': 'NOT_TESTED',
                              'reason': 'four_decode_did_not_exceed_reference'}}}
        with tempfile.TemporaryDirectory() as td:
            log = pathlib.Path(td)
            (log / 'PAIR.json').write_text(json.dumps(state))
            with mock.patch.object(controller, 'LOG', log), \
                 mock.patch.object(controller, 'approved'), \
                 mock.patch.object(controller, 'dependency'), \
                 mock.patch.object(controller, 'settle_profile') as settle, \
                 mock.patch.object(controller, 'save') as save:
                controller.settle_pair()
                settle.assert_not_called()
                save.assert_not_called()
            self.assertEqual(json.loads((log / 'PAIR.json').read_text()), state)

    def test_first_transport_failure_settles_and_never_dispatches_second(self):
        plan = json.loads((HERE / 'PLAN.json').read_text())
        first = controller.PROFILES[0]
        saved = []
        props = [{'MainPID': str(controller.os.getpid()), 'InvocationID': 'controller'},
                 {'LoadState': 'not-found'},
                 {'MainPID': '123', 'InvocationID': 'first-profile',
                  'ExecStart': str(controller.profile_base(first) / 'candidate_owner.py')}]
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(controller, 'LOG', pathlib.Path(td)), \
             mock.patch.object(controller, 'approved', return_value=(plan, 'synthetic-go')), \
             mock.patch.object(controller, 'dependency'), \
             mock.patch.object(controller, 'save', side_effect=lambda h, s: saved.append(copy.deepcopy(s))), \
             mock.patch.object(controller, 'properties', side_effect=props), \
             mock.patch.object(controller, 'read_owner', return_value=None), \
             mock.patch.object(controller.time, 'time', return_value=controller.timestamp('2026-09-27T17:25:00Z')), \
             mock.patch.object(controller, 'command', return_value=json.dumps({'status': 'SYSTEMD_DISPATCHED_READBACK_REQUIRED'})) as launch, \
             mock.patch.object(controller, 'wait_baseline', side_effect=RuntimeError('baseline_stream_not_complete')), \
             mock.patch.object(controller, 'settle_profile') as settle:
            with self.assertRaisesRegex(RuntimeError, 'baseline_stream_not_complete'):
                controller.run_pair()
            self.assertEqual(launch.call_count, 1)
            self.assertIn(first, launch.call_args.args[0][2])
            self.assertEqual(settle.call_count, 1)
            self.assertEqual(settle.call_args.args[2], first)
            self.assertEqual(saved[-1]['profiles'][controller.PROFILES[1]]['status'], 'NOT_TESTED')
            self.assertEqual(saved[-1]['status'], 'PAIR_STOPPED_ORIGINAL_GLM_READY_NO_REPLAY')


if __name__ == '__main__':
    unittest.main()
