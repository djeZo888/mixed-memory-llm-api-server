"""Offline caller seams; synthetic proc/native facts and isolated child sampler."""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import decode_capture as capture
from benchmark.host import LinuxHost
from install.storage_io import AnchoredRoot
from tests.test_benchmark_host import HostTests


def progress(n=3, stamp=10):
    return {'monotonic_s': stamp, 'request_started_monotonic_s': 1,
            'first_output_monotonic_s': 2, 'last_output_monotonic_s': stamp,
            'output_event_count': n, 'native_predicted_n': n}


class CaptureTests(unittest.TestCase):
    def host(self):
        host = HostTests().bare()
        host.scope = 'glm-decode-diag'
        host.decode_capture_policy = {'cpu': True}
        host.requests = {'a': {}}
        host.guards = Mock()
        host.budget.checkpoint.return_value = 100
        return host

    def native(self, n, stamp):
        return {'slot_id': 0, 'task_id': 42, 'is_processing': True, 'n_decoded': n,
                'host_started_monotonic_s': stamp, 'host_finished_monotonic_s': stamp}

    def test_slot_object_list_and_unavailable_fail_closed(self):
        host = self.host()
        for value, expected in [({'n_decoded': 4}, 4), ([{'n_decoded': 4}], 4),
                                (None, None), ([], None), ([{}, {}], None),
                                ({'n_decoded': True}, None), ({'n_decoded': -1}, None),
                                ({'n_decoded': '4'}, None), ('secret', None)]:
            with self.subTest(value=value), patch('benchmark.host.http_json', return_value=[
                {'id': 0, 'id_task': 42, 'is_processing': True, 'next_token': value,
                 'prompt': 'private prompt', 'generated': 'private output'}]):
                row = host.decode_progress('a')
                self.assertEqual(row['n_decoded'], expected)
                self.assertEqual(row['counter_status'], 'AVAILABLE' if expected is not None else 'UNAVAILABLE')
                self.assertNotIn('private', json.dumps(row))

    def test_client_bracket_uses_only_client_clock_and_positive_output(self):
        before, after = progress(), progress(10, 30)
        after.update(capture_start_rpc_before_monotonic_s=11,
                     capture_complete_rpc_after_monotonic_s=29)
        self.assertTrue(capture.client_bracket(before, after))
        for key, value in [('last_output_monotonic_s', 29), ('output_event_count', 3),
                           ('native_predicted_n', 3), ('request_started_monotonic_s', 0),
                           ('capture_complete_rpc_after_monotonic_s', float('nan'))]:
            self.assertFalse(capture.client_bracket(before, {**after, key: value}))
        self.assertNotIn('generated', capture.client_progress({**before, 'generated': 'private'}))

    def test_start_rejects_no_output_and_second_attempt(self):
        host = self.host()
        host.decode_capture_policy = {'cpu': False}
        with self.assertRaisesRegex(ValueError, 'not_armed'):
            host.decode_cpu_capture_start('a', progress())
        host.decode_capture_policy = {'cpu': True}
        with self.assertRaises(ValueError):
            host.decode_cpu_capture_start('a', progress(0))
        with patch.object(capture.CpuCapture, 'start', return_value={'capture_complete': False}):
            host.decode_cpu_capture_start('a', progress())
            with self.assertRaisesRegex(ValueError, 'single_sample'):
                host.decode_cpu_capture_start('a', progress())

    @contextmanager
    def storage_host(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            root = Path(directory).resolve()
            host = self.host()
            device = str(os.major(root.stat().st_dev)) + ':' + str(os.minor(root.stat().st_dev))
            registration = {'schema_version': 1, 'roots': {'logs': str(root)},
                'data': {'path': str(root), 'mount': str(root), 'uuid': 'synthetic-data', 'fstype': 'synthetic', 'device': device},
                'models': {'path': str(root), 'mount': str(root), 'uuid': 'synthetic-models', 'fstype': 'synthetic', 'device': device}}
            @contextmanager
            def guard(*args, **kwargs):
                yield lambda: registration
            host.binding = SimpleNamespace(path=lambda role: str(root), mounted_guard=guard)
            host.storage_io = SimpleNamespace(AnchoredRoot=lambda path, guard:
                AnchoredRoot(path, guard, uid=os.geteuid()))
            yield host, root

    def test_guard_failure_is_safety_failure_without_launch(self):
        host = self.host()
        host.guards.side_effect = RuntimeError('private detail')
        sample = capture.CpuCapture(host, 'a', progress())
        with patch.object(capture.subprocess, 'Popen') as popen:
            sample._run()
        row = sample.status()
        self.assertTrue(row['capture_complete'])
        self.assertTrue(row['safety_stop_required'])
        self.assertNotIn('private detail', json.dumps(row))
        popen.assert_not_called()

    def test_missing_counter_does_not_launch_or_stop_model(self):
        with self.storage_host() as (host, root):
            host.decode_progress = Mock(return_value=self.native(None, 1))
            sample = capture.CpuCapture(host, 'a', progress())
            with patch.object(capture, 'target_identity', return_value={'pid': 123, 'starttime_ticks': 5}), \
                 patch.object(capture.subprocess, 'Popen') as popen:
                sample._run()
            row = sample.status()
            self.assertTrue(row['target_alive'])
            self.assertFalse(row['safety_stop_required'])
            self.assertFalse(row['host_valid'])
            popen.assert_not_called()
            host.guards.assert_called()

    def test_sampler_error_leaves_real_child_alive_and_private_files(self):
        actual_popen = subprocess.Popen
        target = actual_popen([sys.executable, '-c', 'import time;time.sleep(30)'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with self.storage_host() as (host, root):
                host.decode_progress = Mock(side_effect=[self.native(3, 0), self.native(8, 1e20)])
                sample = capture.CpuCapture(host, 'a', progress())
                def spawn(argv, **kwargs):
                    self.assertEqual(argv[-2:], ['-o', '-'])
                    self.assertIn('--no-buildid-cache', argv)
                    return actual_popen([sys.executable, '-c',
                        'import sys;sys.stderr.write("PRIVATE TOOL ERROR");sys.exit(2)'], **kwargs)
                identity = {'pid': target.pid, 'starttime_ticks': 5}
                with patch.object(capture, 'target_identity', return_value=identity), \
                     patch.object(capture.subprocess, 'Popen', side_effect=spawn):
                    sample._run()
                row = sample.status()
                self.assertIsNone(target.poll())
                self.assertTrue(row['target_alive'])
                self.assertFalse(row['host_valid'])
                self.assertFalse(row['safety_stop_required'])
                self.assertEqual(row['profiler_returncode'], 2)
                self.assertNotIn('PRIVATE TOOL ERROR', json.dumps(row))
                files = list(root.rglob('perf.*'))
                self.assertEqual(len(files), 2)
                self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in files))
                self.assertLessEqual(sum(path.stat().st_size for path in files), 1024**3)
        finally:
            target.terminate(); target.wait(timeout=5)

    def test_forced_profiler_stop_never_signals_target(self):
        actual_popen = subprocess.Popen
        target = actual_popen([sys.executable, '-c', 'import time;time.sleep(30)'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with self.storage_host() as (host, root):
                host.decode_progress = Mock(side_effect=[self.native(3, 0), self.native(8, 1e20)])
                sample = capture.CpuCapture(host, 'a', progress())
                def spawn(argv, **kwargs):
                    return actual_popen([sys.executable, '-c',
                        'import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);time.sleep(30)'], **kwargs)
                with patch.object(capture, 'target_identity', return_value={'pid': target.pid, 'starttime_ticks': 5}), \
                     patch.object(capture.subprocess, 'Popen', side_effect=spawn), \
                     patch.object(capture, 'SAMPLE_SECONDS', 0.2), patch.object(capture, 'MAX_CAPTURE_SECONDS', 0.4):
                    sample._run()
                self.assertIsNone(target.poll())
                self.assertTrue(sample.status()['profiler_forced_stop'])
                self.assertTrue(sample.status()['target_alive'])
                self.assertFalse(sample.status()['host_valid'])
        finally:
            target.terminate(); target.wait(timeout=5)

    def test_normal_native_host_bracket_client_certification_repeat(self):
        sample = capture.CpuCapture(self.host(), 'a', progress())
        sample.result.update(capture_complete=True, host_valid=True, target_alive=True)
        self.assertFalse(sample.status()['decode_contained'])
        after = {**progress(10, 30), 'capture_start_rpc_before_monotonic_s': 11,
                 'capture_complete_rpc_after_monotonic_s': 29}
        self.assertTrue(sample.status(after)['decode_contained'])
        sample.result['host_valid'] = False
        self.assertFalse(sample.status(after)['decode_contained'])

    def test_successful_profiler_requires_real_interval_and_nonempty_artifact(self):
        actual_popen = subprocess.Popen
        with self.storage_host() as (host, root):
            host.decode_progress = Mock(side_effect=[self.native(3, 0), self.native(8, 1e20)])
            sample = capture.CpuCapture(host, 'a', progress())
            def spawn(argv, **kwargs):
                return actual_popen([sys.executable, '-c',
                    'import signal,time,os;signal.signal(signal.SIGINT,lambda *a:exit(0));'
                    'os.write(1,b"synthetic perf bytes");time.sleep(30)'], **kwargs)
            with patch.object(capture, 'target_identity', return_value={'pid': 123, 'starttime_ticks': 5}), \
                 patch.object(capture.subprocess, 'Popen', side_effect=spawn), \
                 patch.object(capture, 'SAMPLE_SECONDS', 0.2), patch.object(capture, 'MAX_CAPTURE_SECONDS', 0.5):
                sample._run()
            row = sample.status()
            self.assertTrue(row['host_valid'], row)
            self.assertFalse(row['profiler_alive'])
            self.assertFalse(row['safety_stop_required'])
            self.assertEqual(host.decode_progress.call_count, 2)

    def test_request_end_and_restore_stop_profiler_before_owner(self):
        host = self.host()
        calls = []
        sample = SimpleNamespace(cid='a', stop=lambda: calls.append('capture_stopped'))
        host._decode_cpu_captures = {'sample': sample}
        host.write_json = lambda *_: calls.append('request_written')
        host.dispatch({'op': 'request_end', 'args': {'id': 'a'}})
        self.assertEqual(calls, ['capture_stopped', 'request_written'])
        host.owner.restore = lambda: (calls.append('restore') or {})
        host.worker_nonce = host.restored_at = None
        host.dispatch({'op': 'restore'})
        self.assertEqual(calls[-2:], ['capture_stopped', 'restore'])

    def test_optional_cpu_runtimeerror_is_unavailable(self):
        host = self.host(); host.identity.return_value = ({}, Path('/synthetic'), [])
        with patch('benchmark.host.collect_sample', return_value={'cgroups': {}}), \
             patch('benchmark.decode_telemetry.collect_decode_sample', side_effect=RuntimeError('private')):
            row = host.telemetry('a')
        self.assertEqual(row['decode_cpu'], {'status': 'UNAVAILABLE', 'error_class': 'RuntimeError'})

    def test_optional_quiescent_runtimeerror_is_unavailable(self):
        host = self.host(); host.identity.return_value = ({}, Path('/synthetic'), [])
        host.assert_idle = Mock(); host.telemetry = Mock(return_value={})
        with patch('benchmark.decode_telemetry.quiescent_snapshot', side_effect=RuntimeError('private')):
            row = host.quiescent('a', 'readiness')
        self.assertEqual(row['decode_quiescent'], {'status': 'UNAVAILABLE', 'error_class': 'RuntimeError'})


if __name__ == '__main__':
    unittest.main()
