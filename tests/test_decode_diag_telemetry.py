"""Offline proc fixtures; no SSH, profiler attachment or live model access."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import decode_telemetry as t


def stat(pid=44, *, start=900, name='worker (busy) x', **values):
    fields = ['0'] * 50
    fields[0] = 'S'
    fields[t.STAT_FIELDS['starttime_ticks']] = str(start)
    for key, value in values.items():
        fields[t.STAT_FIELDS[key]] = str(value)
    return f'{pid} ({name}) ' + ' '.join(fields)


class DecodeTelemetryTests(unittest.TestCase):
    def test_stat_spaces_and_parentheses_preserve_numeric_identity_only(self):
        row = t.parse_stat(stat(name='secret worker ) (busy)', minflt=3, majflt=1,
                               utime_ticks=150, stime_ticks=10, processor=95))
        self.assertEqual(row, {'minflt': 3, 'majflt': 1, 'utime_ticks': 150,
                              'stime_ticks': 10, 'starttime_ticks': 900, 'processor': 95})
        self.assertNotIn('secret', json.dumps(row))
        self.assertTrue(all(value is None for value in t.parse_stat('malformed').values()))
        self.assertIsNone(t.parse_stat(stat(utime_ticks='bad'))['utime_ticks'])

    def test_status_missing_is_not_zero_and_masks_are_sanitized(self):
        row = t.parse_status('voluntary_ctxt_switches: 10\nnonvoluntary_ctxt_switches: 0\n'
                             'Cpus_allowed_list: 0-15,32-47\nMems_allowed_list: 0-6\nName: private\n')
        self.assertEqual(row['nonvoluntary_ctxt_switches'], 0)
        self.assertEqual(row['Cpus_allowed_list'], '0-15,32-47')
        self.assertEqual(row['Mems_allowed_list'], '0-6')
        self.assertIsNone(t.parse_status('Cpus_allowed_list: private-value')['Cpus_allowed_list'])
        self.assertTrue(all(value is None for value in t.parse_status('').values()))

    def test_policy_environment_is_strictly_allowlisted(self):
        env = ('API_KEY=private-key\0PATH=/private/path\0OMP_WAIT_POLICY=PASSIVE\0'
               'GOMP_SPINCOUNT=0\0OMP_PROC_BIND=spread,close\0OMP_PLACES={0:16},{32:16}\0'
               'OMP_NUM_THREADS=96\0OMP_DYNAMIC=FALSE\0OMP_THREAD_LIMIT=112\0'
               'GGML_CUDA_DISABLE_GRAPHS=1\0')
        row = t.parse_policy_environment(env)
        self.assertEqual(set(row), set(t.ENV_PATTERNS))
        self.assertEqual(row['OMP_PLACES'], '{0:16},{32:16}')
        self.assertNotIn('private', json.dumps(row))
        self.assertTrue(all(value is None for value in t.parse_policy_environment('').values()))
        for value in ('private-secret', 'ACTIVE\nTOKEN=secret', 'a' * 257):
            self.assertEqual(t.parse_policy_environment('OMP_WAIT_POLICY=' + value)['OMP_WAIT_POLICY'], 'REDACTED')
        self.assertEqual(t.parse_policy_environment('GOMP_SPINCOUNT=private-secret')['GOMP_SPINCOUNT'], 'REDACTED')

    def test_numa_sums_pages_without_returning_addresses_or_paths(self):
        row = t.parse_numa_maps('1234 default file=/private/model N0=100 N6=20 kernelpagesize_kB=4\n'
                               '9876 bind:0 anon=40 dirty=40 N0=30 N1=10\n')
        self.assertEqual(row['node_pages'], {'0': 130, '6': 20, '1': 10})
        self.assertEqual(row['total_reported_node_pages'], 160)
        self.assertNotIn('private', json.dumps(row))
        self.assertNotIn('1234', json.dumps(row))

    def fixture(self, root, tids=(44, 45)):
        (root / 'stat').write_text('cpu 100 2 50 900 7 8 9 30 10 1\ncpu0 1 2 3\n')
        (root / 'loadavg').write_text('1.0 2.0 3.0 12/1000 20\n')
        (root / 'sys/kernel').mkdir(parents=True)
        (root / 'sys/kernel/sched_schedstats').write_text('1\n')
        cg = root / 'group'
        cg.mkdir()
        (cg / 'cpu.stat').write_text('usage_usec 90\nuser_usec 80\nsystem_usec 10\nnr_periods 20\n'
                                     'nr_throttled 1\nthrottled_usec 5\nprivate_data private\n')
        (cg / 'cpu.max').write_text('max 100000\n')
        base = root / '44'
        base.mkdir()
        (base / 'stat').write_text(stat())
        for tid in tids:
            task = base / 'task' / str(tid)
            task.mkdir(parents=True)
            (task / 'stat').write_text(stat(tid, start=tid * 100, utime_ticks=100))
            (task / 'status').write_text('voluntary_ctxt_switches: 5\nnonvoluntary_ctxt_switches: 2\n'
                                       'Cpus_allowed_list: 0-95\nMems_allowed_list: 0-6\n')
            (task / 'schedstat').write_text('15000000 1000000 4\n')
        return cg, base

    def test_timed_snapshot_is_bounded_with_no_smaps_maps_numa_or_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cg, _ = self.fixture(root)
            ticks = iter((1.0, 1.125))
            with mock.patch.object(t, '_read', wraps=t._read) as reader:
                row = t.collect_decode_sample({'model': cg}, pids={'model': [44]},
                    proc_root=root, clock=lambda: next(ticks))
            self.assertEqual(row['host_cpu']['steal'], 30)
            self.assertEqual(row['host_cpu']['runnable_tasks'], 12)
            self.assertEqual(row['cgroups']['model']['quota_usec'], 'max')
            self.assertEqual(row['cgroups']['model']['throttled_usec'], 5)
            self.assertEqual(row['collection_duration_s'], 0.125)
            process = row['processes']['model'][0]
            self.assertTrue(process['generation_stable'])
            self.assertEqual(process['process_starttime_ticks'], 900)
            self.assertEqual(process['threads'][1]['runtime_ns'], 15000000)
            self.assertTrue(all(thread['generation_stable'] for thread in process['threads']))
            self.assertEqual(row['missing_reads'], [])
            names = {call.args[0].name for call in reader.call_args_list}
            self.assertFalse(names & {'smaps', 'smaps_rollup', 'maps', 'numa_maps', 'environ'})
            self.assertEqual(sum(call.args[0].name == 'sched_schedstats' for call in reader.call_args_list), 1)
            bounded = t.collect_decode_sample({'model': cg}, pids={'model': [44]}, proc_root=root, max_threads=1)
            self.assertTrue(bounded['processes']['model'][0]['threads_truncated'])
            self.assertEqual(len(bounded['processes']['model'][0]['threads']), 1)

    def test_disabled_or_unknown_schedstats_never_claims_measured_zero_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cg, base = self.fixture(root, tids=(44,))
            (base / 'task/44/schedstat').write_text('15000000 0 0\n')
            flag = root / 'sys/kernel/sched_schedstats'
            for setting, status in (('0', 'DISABLED'), ('1', 'ENABLED'), ('invalid', 'UNAVAILABLE'),
                                    (None, 'UNAVAILABLE')):
                with self.subTest(setting=setting):
                    flag.unlink() if setting is None else flag.write_text(setting + '\n')
                    row = t.collect_decode_sample({'model': cg}, pids={'model': [44]}, proc_root=root)
                    thread = row['processes']['model'][0]['threads'][0]
                    available = setting == '1'
                    self.assertEqual(row['scheduler_wait_status'], status)
                    self.assertEqual(row['scheduler_wait_available'], available)
                    self.assertEqual(thread['scheduler_wait_available'], available)
                    self.assertEqual(thread['raw_schedstat'], {'runtime_ns': 15000000, 'runqueue_ns': 0, 'timeslices': 0})
                    self.assertEqual(thread['runtime_ns'], 15000000 if available else None)
                    self.assertEqual(thread['runqueue_ns'], 0 if available else None)
                    self.assertEqual(thread['timeslices'], 0 if available else None)
                    if not available:
                        self.assertIn('runqueue_ns', thread['missing_fields'])
                    if setting is None:
                        self.assertIn('host.sched_schedstats', row['missing_reads'])

    def test_unavailable_fields_and_process_reuse_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cg, base = self.fixture(root, tids=(44,))
            (base / 'task/44/schedstat').unlink()
            original = t._read
            seen = 0
            def changing(path, *args, **kwargs):
                nonlocal seen
                if path == base / 'stat':
                    seen += 1
                    return stat(start=100 if seen == 1 else 200)
                return original(path, *args, **kwargs)
            with mock.patch.object(t, '_read', side_effect=changing):
                row = t.collect_decode_sample({'model': cg}, pids={'model': [44]}, proc_root=root)
            process = row['processes']['model'][0]
            self.assertFalse(process['generation_stable'])
            self.assertIsNone(process['threads'][0]['runqueue_ns'])
            self.assertIn('runqueue_ns', process['threads'][0]['missing_fields'])
            self.assertIn('44.44.schedstat', row['missing_reads'])
            missing = t.collect_decode_sample({'missing': root / 'absent'}, pids={'missing': [999]}, proc_root=root)
            self.assertIsNone(missing['cgroups']['missing']['quota_usec'])
            self.assertFalse(missing['processes']['missing'][0]['generation_stable'])

    def test_pid_inventory_refuses_duplicates_bool_and_unbounded_thread_requests(self):
        for pids, limit in (({'x': [44, 44]}, 2), ({'x': [True]}, 2), ({'x': [44]}, 2049)):
            with self.assertRaisesRegex(ValueError, 'invalid_owned'):
                t.collect_decode_sample({}, pids=pids, max_threads=limit)

    def test_quiescent_reports_real_mapped_inode_elf_metadata_and_policy_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, base = self.fixture(root)
            (base / 'numa_maps').write_text('1234 default file=/private/weights N0=2 N6=3\n')
            (base / 'environ').write_bytes(b'API_KEY=private-key\0OMP_WAIT_POLICY=PASSIVE\0')
            library = base / 'root/usr/lib/libgomp.so.1'
            library.parent.mkdir(parents=True)
            library.write_bytes(b'synthetic ELF fixture')
            info = library.stat()
            mapping = f'1234-5678 r-xp 0000 {os.major(info.st_dev):x}:{os.minor(info.st_dev):x} {info.st_ino} /usr/lib/libgomp.so.1\n'
            (base / 'maps').write_text(mapping + mapping)
            output = b' Build ID: aBcD0123\n 0 (NEEDED) Shared library: [libc.so.6]\n 0 (RPATH) [private-secret]\n'
            with mock.patch.object(t.shutil, 'which', return_value='/usr/bin/readelf'), mock.patch.object(
                    t.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=output)) as run:
                row = t.quiescent_snapshot({'model': [44]}, proc_root=root)
            process = row['processes']['model'][0]
            self.assertTrue(process['generation_stable'])
            self.assertEqual(process['libraries'], [{'name': 'libgomp.so.1', 'build_id': 'abcd0123',
                                                     'needed': ['libc.so.6'], 'status': 'OK'}])
            self.assertEqual(process['numa']['total_reported_node_pages'], 5)
            self.assertEqual(process['policy_environment']['OMP_WAIT_POLICY'], 'PASSIVE')
            self.assertNotIn('private', json.dumps(row))
            self.assertEqual(run.call_count, 1)
            self.assertLessEqual(run.call_args.kwargs['timeout'], 2)
            self.assertEqual(run.call_args.kwargs['env'], {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            self.assertTrue(run.call_args.args[0][-1].startswith('/proc/self/fd/'))
            with mock.patch.object(t.subprocess, 'run') as run:
                changed = t._library_identity(library, (os.major(info.st_dev), os.minor(info.st_dev)),
                                              info.st_ino + 1, '/usr/bin/readelf', 2)
            self.assertEqual(changed['status'], 'MAPPED_INODE_CHANGED_OR_FILE_TOO_LARGE')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
