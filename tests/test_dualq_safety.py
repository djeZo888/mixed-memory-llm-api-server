"""Actual inherited dual-Q collection/admission; synthetic host observations only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import dualq_480k as dual, runner

GIB = 1024 ** 3


def sample():
    return {
        'timestamp_monotonic_s': 1.0, 'errors': [],
        'host': {'available_bytes': 100 * GIB},
        'gpus': [{'uuid': 'GPU-offline-' + slot, 'free_bytes': 32 * GIB}
                 for slot in dual.SLOTS],
        'cgroups': {slot: {'swap_bytes': 0,
                          'events': {'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0}}
                   for slot in dual.SLOTS},
        'concurrent_resource_gate': {
            'status': 'PASS', 'reasons': [], 'unavailable_reasons': [],
            'latched_violations': {},
            'charges': {slot: {'required_bytes': 20 * GIB} for slot in dual.SLOTS}},
    }


class DualQSafety(unittest.TestCase):
    def case(self, row):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        state = Path(directory.name)
        runner.save(state / 'progress.json', {
            'phase': 'OFFLINE', 'completed': {}, 'inflight': {}, 'errors': []})
        rows, calls = {'current': row}, []

        def call(op, **args):
            calls.append(op)
            if op == 'telemetry':
                return copy.deepcopy(rows['current'])
            if op == 'request_begin':
                return {'timeout_s': args['timeout_s']}
            self.fail('Unexpected host operation: ' + op)

        remote = Mock()
        remote.call.side_effect = call
        # Exercise the real subclass's collect/admission with an inert host;
        # the unrelated full arm read-chain has its separate focused tests.
        job = dual.DualQRun.__new__(dual.DualQRun)
        runner.Campaign.__init__(job, state, {'scope': dual.SCOPE}, remote,
                                 'synthetic-nonsecret')
        job.interrupted = threading.Event()
        for slot in dual.SLOTS:
            job.active[slot] = {
                'manifest': {'placement': slot, 'gpu_uuids': ['GPU-offline-' + slot]},
                'phase': 'ready', 'baseline': copy.deepcopy(sample()['cgroups'][slot]),
                'cancel_event': threading.Event()}
        return job, rows, calls

    def assert_healthy_peer_not_cancelled(self, job):
        self.assertEqual(job.safety, {})
        self.assertFalse(any(v['cancel_event'].is_set() for v in job.active.values()))
        self.assertFalse(any(v.get('abort_reason') for v in job.active.values()))

    def test_missing_or_nonnumeric_safety_proof_blocks_new_admission_without_cancelling_peer(self):
        for value in (None, False, '0'):
            for field in ('host', 'gpu'):
                with self.subTest(value=value, field=field):
                    row = sample()
                    if field == 'host':
                        row['host']['available_bytes'] = value
                    else:
                        row['gpus'][0]['free_bytes'] = value
                    row['concurrent_resource_gate'].update(
                        status='UNAVAILABLE', unavailable_reasons=['offline_missing_' + field])
                    job, _, calls = self.case(row)
                    job.collect()
                    self.assertTrue(job.proof_pending)
                    self.assert_healthy_peer_not_cancelled(job)
                    with patch('benchmark.g1_ladder.checkpoint'):
                        with self.assertRaisesRegex(RuntimeError, 'CURRENT_RESOURCE_PROOF_UNAVAILABLE'):
                            job.admission('Q0', measured=True)
                    self.assertNotIn('request_begin', calls)
                    self.assert_healthy_peer_not_cancelled(job)

    def test_fresh_complete_proof_clears_gap_preserving_prior_unknown_samples(self):
        row = sample()
        row['errors'] = ['gpu_TimeoutExpired']
        row['gpus'] = []
        row['concurrent_resource_gate'].update(
            status='UNAVAILABLE', unavailable_reasons=['concurrent_gpu_free_unavailable'])
        job, rows, calls = self.case(row)
        job.collect()
        self.assertTrue(job.proof_pending)
        raw = (job.state / 'results.jsonl').read_bytes()
        rows['current'] = sample()
        with patch('benchmark.g1_ladder.checkpoint'):
            self.assertEqual(job.admission('Q1', measured=True), 7200)
        self.assertIsNone(job.proof_pending)
        self.assertEqual(calls.count('request_begin'), 1)
        self.assertTrue((job.state / 'results.jsonl').read_bytes().startswith(raw))
        self.assertEqual(json.loads(raw.splitlines()[0])['sample']['gpus'], [])
        self.assert_healthy_peer_not_cancelled(job)

    def test_numeric_danger_cancels_both_and_latches_after_later_good_sample(self):
        for fault in ('oom', 'gpu_low', 'host_low', 'required_working_set'):
            with self.subTest(fault=fault):
                row = sample()
                if fault == 'oom':
                    row['cgroups']['Q0']['events']['oom_kill'] = 1
                elif fault == 'gpu_low':
                    row['gpus'][0]['free_bytes'] = 15 * GIB
                elif fault == 'host_low':
                    row['host']['available_bytes'] = 15 * GIB
                else:
                    row['concurrent_resource_gate'].update(
                        status='STOP_RESOURCE_GATE', reasons=['concurrent_cap_15_percent_headroom_failed'],
                        latched_violations={'Q0': {'reasons': ['concurrent_cap_15_percent_headroom_failed']}})
                if fault in ('gpu_low', 'host_low'):
                    row['concurrent_resource_gate'].update(
                        status='STOP_RESOURCE_GATE', reasons=['offline_numeric_' + fault],
                        latched_violations={'Q0': {'reasons': ['offline_numeric_' + fault]}})
                job, rows, calls = self.case(row)
                job.collect()
                self.assertTrue(job.safety)
                self.assertTrue(all(v['cancel_event'].is_set() for v in job.active.values()))
                self.assertTrue(all(v.get('abort_reason') for v in job.active.values()))
                reasons = copy.deepcopy(job.safety)
                rows['current'] = sample()
                job.collect()
                self.assertEqual(job.safety, reasons)
                self.assertTrue(all(v['cancel_event'].is_set() for v in job.active.values()))
                with patch('benchmark.g1_ladder.checkpoint'):
                    with self.assertRaises(RuntimeError):
                        job.admission('Q1', measured=True)
                self.assertNotIn('request_begin', calls)


if __name__ == '__main__':
    unittest.main()
