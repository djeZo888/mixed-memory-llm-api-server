"""Offline evidence-contract tests; no request, remote access, or /proc reads."""
import pathlib
import unittest

from decode_affinity import DecodeAffinity, summarize


def samples(cpus):
    return [
        {
            'started_monotonic_seconds': 10.0 + offset,
            'finished_monotonic_seconds': 10.01 + offset,
            'native_starttime_ticks': 100,
            'task_read_errors': [],
            'tasks': [
                {'tid': 200 + index, 'starttime_ticks': 101 + index,
                 'utime_ticks': int(offset * 100), 'stime_ticks': 0,
                 'allowed_cpus': [cpu], 'last_cpu': cpu}
                for index, cpu in enumerate(cpus)
            ],
        }
        for offset in (0.0, 0.5, 1.0, 2.0, 3.0)
    ]


class DecodeAffinityTests(unittest.TestCase):
    def summarize(self, evidence, cpus):
        return summarize(evidence, 10.0, 13.5, cpus, 100)

    def test_configured_two_and_four_candidate_counts(self):
        for cpus in ([0, 40], [0, 24, 40, 56]):
            with self.subTest(cpus=cpus):
                result = self.summarize(samples(cpus), cpus)
                self.assertEqual(result['status'], 'EXPECTED_SINGLETON_CANDIDATES_OBSERVED')
                self.assertEqual(result['expected_decode_candidate_count'], len(cpus))
                self.assertEqual(result['singleton_decode_candidate_count'], len(cpus))
                self.assertTrue(result['exact_configured_substantially_active_tids'])
                self.assertEqual(result['steady_bounded_window']['qualified_snapshot_count'], 4)

    def test_initial_transition_stays_inconclusive_with_separate_steady_proof(self):
        cpus = [0, 24, 40, 56]
        evidence = samples(cpus)
        for task in evidence[0]['tasks']:
            task['allowed_cpus'] = list(cpus)
        result = self.summarize(evidence, cpus)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertEqual(result['qualified_snapshot_count'], 5)
        self.assertEqual(result['all_advancing_tasks'][0]['allowed_cpu_observations'],
                         [[0], cpus])
        steady = result['steady_bounded_window']
        self.assertEqual(steady['status'], 'EXPECTED_SINGLETON_CANDIDATES_OBSERVED')
        self.assertEqual(steady['window_start_offset_seconds'], 0.5)

    def test_later_transition_is_not_discarded_to_manufacture_steady_proof(self):
        cpus = [0, 40]
        evidence = samples(cpus)
        evidence[1]['tasks'][0]['allowed_cpus'] = cpus
        result = self.summarize(evidence, cpus)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertEqual(result['steady_bounded_window']['status'], 'INCONCLUSIVE')

    def test_wrong_mask_and_missing_candidate_are_inconclusive(self):
        for observed in ([0, 24], [0]):
            with self.subTest(observed=observed):
                result = self.summarize(samples(observed), [0, 40])
                self.assertEqual(result['status'], 'INCONCLUSIVE')

    def test_read_error_and_pid_change_cannot_prove_candidates(self):
        for fault in ('read', 'pid'):
            evidence = samples([0, 40])
            if fault == 'read':
                evidence[2]['task_read_errors'] = [{'tid': 999, 'error_type': 'OSError'}]
            else:
                evidence[2]['native_starttime_ticks'] = 999
            result = self.summarize(evidence, [0, 40])
            self.assertEqual(result['status'], 'INCONCLUSIVE')
            self.assertEqual(result['steady_bounded_window']['status'], 'INCONCLUSIVE')

    def test_short_output_cannot_claim_later_steady_proof(self):
        result = summarize(samples([0, 40]), 10.0, 10.75, [0, 40], 100)
        self.assertEqual(result['qualified_snapshot_count'], 2)
        self.assertEqual(result['steady_bounded_window']['status'], 'INCONCLUSIVE')
        self.assertEqual(result['steady_bounded_window']['qualified_snapshot_count'], 1)

    def test_extra_active_task_is_retained_without_exact_count_claim(self):
        evidence = samples([0, 40, 64])
        result = self.summarize(evidence, [0, 40])
        self.assertEqual(result['status'], 'EXPECTED_SINGLETON_CANDIDATES_OBSERVED')
        self.assertEqual(result['substantial_tid_count'], 3)
        self.assertFalse(result['exact_configured_substantially_active_tids'])

    def test_invalid_expected_configuration_fails_closed(self):
        for cpus in ([], [0, 0]):
            self.assertEqual(self.summarize(samples([0, 40]), cpus)['status'], 'INCONCLUSIVE')

    def test_finish_preserves_all_raw_snapshots_and_transition_status(self):
        sampler = DecodeAffinity(999, [0, 40], list(range(64)))
        sampler.first_mono = 10.0
        sampler.first_utc = '2026-09-27T00:00:00Z'
        sampler.snapshots = samples([0, 40])
        sampler.snapshots[0]['tasks'][0]['allowed_cpus'] = [0, 40]
        result = sampler.finish(13.5)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertEqual(result['snapshots'], sampler.snapshots)
        self.assertEqual(result['schema'], 'h016-affinity14-decode-v1')
        self.assertEqual(result['steady_bounded_window']['status'],
                         'EXPECTED_SINGLETON_CANDIDATES_OBSERVED')

    def test_profile_copies_are_identical(self):
        root = pathlib.Path(__file__).parent
        source = (root / 'decode_affinity.py').read_bytes()
        for profile in ('r12-spread4', 'r13-spread2'):
            self.assertEqual((root / profile / 'decode_affinity.py').read_bytes(), source)


if __name__ == '__main__':
    unittest.main()
