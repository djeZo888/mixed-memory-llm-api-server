"""Synthetic local proc fixtures; no VM, model, or live readiness evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_telemetry as cpu
from benchmark import decode_telemetry as primitive
from benchmark.lifecycle import PlanError


def stat(pid, generation=900):
    fields = ['0'] * 50
    fields[0] = 'S'
    fields[primitive.STAT_FIELDS['starttime_ticks']] = str(generation)
    fields[17] = '1'
    return str(pid) + ' (private process) ' + ' '.join(fields)


class StrictNumaLifetimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for pid in (44, 55):
            (self.root / str(pid)).mkdir()
            (self.root / str(pid) / 'stat').write_text(stat(pid))
            (self.root / str(pid) / 'numa_maps').write_text(
                '1234 default file=/private/model N0=30 N7=10\n')

    def snapshot(self, **kwargs):
        return cpu.numa_snapshot({'glm': [44, 55]}, proc_root=self.root,
                                 strict_lifetime=True, **kwargs)

    def test_stable_actual_files_and_historical_output_unchanged(self):
        strict = self.snapshot(clock=lambda: 1)
        historical = cpu.numa_snapshot({'glm': [44, 55]}, proc_root=self.root, clock=lambda: 1)
        self.assertEqual(strict, historical)
        self.assertEqual([row['pid'] for row in strict['processes']['glm']], [44, 55])
        self.assertTrue(all(row['status'] == 'AVAILABLE' for row in strict['processes']['glm']))
        self.assertEqual(strict['processes']['glm'][0]['numa']['node_pages'], {'0': 30, '7': 10})
        self.assertNotIn('private', json.dumps(strict))

    def test_missing_read_at_each_stage_retains_unavailable_pid_and_full_cohort(self):
        original = cpu._strict_numa_read
        for stage in (1, 2, 3):
            with self.subTest(stage=stage):
                calls = 0
                def read(path, maximum):
                    nonlocal calls
                    calls += 1
                    if calls == stage:
                        raise FileNotFoundError('/private/secret/model')
                    return original(path, maximum)
                with mock.patch.object(cpu, '_strict_numa_read', side_effect=read):
                    result = self.snapshot()
                rows = result['processes']['glm']
                self.assertEqual([row['pid'] for row in rows], [44, 55])
                self.assertEqual(rows[0]['status'], 'UNAVAILABLE')
                self.assertEqual(rows[0]['reason'], 'proc_observation_missing')
                self.assertIsNone(rows[0]['numa'])
                self.assertEqual(rows[0]['process_starttime_ticks'], None if stage == 1 else 900)
                self.assertEqual(rows[1]['status'], 'AVAILABLE')
                self.assertEqual(len(result['missing_reads']), 1)
                self.assertNotIn('secret', json.dumps(result))

    def test_actual_missing_file_and_process_lookup_classification_without_retry(self):
        (self.root / '44/stat').unlink()
        self.assertEqual(self.snapshot()['processes']['glm'][0]['reason'], 'proc_observation_missing')
        with mock.patch.object(Path, 'open', side_effect=ProcessLookupError('private')) as read:
            result = self.snapshot()
        self.assertEqual(read.call_count, 2)
        self.assertTrue(all(row['reason'] == 'proc_observation_missing'
                            for row in result['processes']['glm']))

    def test_strict_deadline_checked_before_every_read_and_failure_propagates(self):
        deadline = mock.Mock()
        self.snapshot(check_deadline=deadline)
        self.assertEqual(deadline.call_count, 6)
        deadline = mock.Mock(side_effect=[None, PlanError('postrestart_preparation_deadline')])
        with mock.patch.object(cpu, '_strict_numa_read', wraps=cpu._strict_numa_read) as read:
            with self.assertRaisesRegex(PlanError, '^postrestart_preparation_deadline$'):
                self.snapshot(check_deadline=deadline)
        self.assertEqual(read.call_count, 1)
        deadline = mock.Mock(side_effect=AssertionError('historical callback must not run'))
        cpu.numa_snapshot({'glm': [44]}, proc_root=self.root, check_deadline=deadline)
        deadline.assert_not_called()

    def test_valid_generation_change_then_fresh_stable_actual_files(self):
        original = cpu._strict_numa_read
        def read(path, maximum):
            text = original(path, maximum)
            if path == self.root / '44/numa_maps':
                (self.root / '44/stat').write_text(stat(44, 901))
            return text
        before = self.snapshot()
        with mock.patch.object(cpu, '_strict_numa_read', side_effect=read):
            transient = self.snapshot()
        after = self.snapshot()
        self.assertEqual(before['processes']['glm'][0]['status'], 'AVAILABLE')
        row = transient['processes']['glm'][0]
        self.assertEqual(row['reason'], 'proc_generation_changed')
        self.assertEqual(row['status'], 'UNAVAILABLE')
        self.assertFalse(row['generation_stable'])
        self.assertIsNone(row['numa'])
        self.assertEqual(after['processes']['glm'][0]['process_starttime_ticks'], 901)
        self.assertEqual(after['processes']['glm'][0]['status'], 'AVAILABLE')

    def test_non_lifetime_read_failures_are_fixed_safe_hard_failures(self):
        for error in (PermissionError('/private/key'), OSError('/private/key'), ValueError('/private/key')):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(Path, 'open', side_effect=error) as read:
                with self.assertRaisesRegex(PlanError, '^postrestart_numa_proc_read_failed$'):
                    self.snapshot()
                self.assertEqual(read.call_count, 1)

    def test_incomplete_maps_with_final_lifetime_race_retains_unavailable_cohort(self):
        original = cpu._strict_numa_read
        for raw in ('', 'malformed private maps'):
            for race in ('changed', 'missing'):
                with self.subTest(raw=raw, race=race):
                    (self.root / '44/stat').write_text(stat(44))
                    (self.root / '44/numa_maps').write_text(raw)
                    def read(path, maximum):
                        text = original(path, maximum)
                        if path == self.root / '44/numa_maps':
                            if race == 'changed':
                                (self.root / '44/stat').write_text(stat(44, 901))
                            else:
                                (self.root / '44/stat').unlink()
                        return text
                    with mock.patch.object(cpu, '_strict_numa_read', side_effect=read):
                        result = self.snapshot()
                    rows = result['processes']['glm']
                    self.assertEqual([row['pid'] for row in rows], [44, 55])
                    self.assertEqual(rows[0]['status'], 'UNAVAILABLE')
                    self.assertEqual(rows[0]['reason'], 'proc_generation_changed' if race == 'changed'
                                     else 'proc_observation_missing')
                    self.assertEqual(rows[0]['process_starttime_ticks'], 900)
                    self.assertFalse(rows[0]['generation_stable'])
                    self.assertIsNone(rows[0]['numa'])
                    self.assertEqual(rows[1]['status'], 'AVAILABLE')
                    self.assertEqual(result['missing_reads'], [] if race == 'changed' else ['44.stat_after'])
                    self.assertNotIn('private', json.dumps(result))

    def test_malformed_stat_encoding_and_limit_fail_without_lifetime_classification(self):
        cases = ((b'', 'stat_malformed'),
                 (b'private malformed', 'stat_malformed'),
                 (stat(55).encode(), 'stat_malformed'),
                 (stat(44).replace('900', 'notnumeric').encode(), 'stat_malformed'),
                 (b'\xff', 'encoding_invalid'),
                 (b'0' * 262145, 'read_limit'))
        for raw, code in cases:
            with self.subTest(code=code):
                (self.root / '44/stat').write_bytes(raw)
                with self.assertRaisesRegex(PlanError, '^postrestart_numa_proc_' + code + '$'):
                    self.snapshot()

    def test_empty_or_structurally_malformed_numa_hard_fails(self):
        for raw in ('', '\n', 'not-a-map', 'xyz default N0=1\n',
                    '1234 default N0=-1\n', '1234 default N7=notnumeric\n'):
            with self.subTest(raw=raw):
                (self.root / '44/numa_maps').write_text(raw)
                with self.assertRaisesRegex(PlanError, '^postrestart_numa_maps_malformed$'):
                    self.snapshot()

    def test_default_missing_or_denied_remains_historical_unavailable(self):
        for error in (FileNotFoundError('private'), PermissionError('private')):
            with self.subTest(error=type(error).__name__), mock.patch.object(Path, 'open', side_effect=error):
                result = cpu.numa_snapshot({'glm': [44]}, proc_root=self.root)
            row = result['processes']['glm'][0]
            self.assertEqual(row['status'], 'UNAVAILABLE')
            self.assertNotIn('reason', row)
            self.assertEqual(len(result['missing_reads']), 3)


if __name__ == '__main__':
    unittest.main()
