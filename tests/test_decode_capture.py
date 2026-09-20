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
                    self.assertEqual(argv[-2], '-o')
                    self.assertRegex(argv[-1], r'^/proc/self/fd/[0-9]+/perf.data$')
                    self.assertNotIn('--per-thread', argv)
                    self.assertEqual(len(kwargs['pass_fds']), 2)
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
        sample.result.update(symbol_resolution='LEAF_REPORT_SAVED_UNRESOLVED_ROWS_RETAINED',
                             symbol_report_resolved_samples=0)
        self.assertFalse(sample.status(after)['profile_usable'])
        sample.result['symbol_report_resolved_samples'] = 1
        self.assertTrue(sample.status(after)['profile_usable'])
        sample.result['host_valid'] = False
        self.assertFalse(sample.status(after)['decode_contained'])
        self.assertFalse(sample.status(after)['profile_usable'])

    def test_successful_profiler_requires_real_interval_and_nonempty_artifact(self):
        actual_popen = subprocess.Popen
        with self.storage_host() as (host, root):
            host.decode_progress = Mock(side_effect=[self.native(3, 0), self.native(8, 1e20)])
            sample = capture.CpuCapture(host, 'a', progress())
            def spawn(argv, **kwargs):
                return actual_popen([sys.executable, '-c',
                    'import signal,time,os;signal.signal(signal.SIGINT,lambda *a:exit(0));'
                    'fd=os.open("perf.data",os.O_WRONLY,dir_fd=int(__import__("sys").argv[1]));'
                    'os.write(fd,b"synthetic perf bytes");os.lseek(fd,0,os.SEEK_SET);'
                    'os.write(fd,b"PERF");os.close(fd);time.sleep(30)', str(kwargs['pass_fds'][0])], **kwargs)
            with patch.object(capture, 'target_identity', return_value={'pid': 123, 'starttime_ticks': 5}), \
                 patch.object(capture.subprocess, 'Popen', side_effect=spawn), \
                 patch.object(capture, 'SAMPLE_SECONDS', 0.2), patch.object(capture, 'MAX_CAPTURE_SECONDS', 0.5), \
                 patch.object(capture, 'leaf_report') as report:
                sample._run()
            row = sample.status()
            self.assertTrue(row['host_valid'], row)
            self.assertFalse(row['profiler_alive'])
            self.assertFalse(row['safety_stop_required'])
            self.assertEqual(host.decode_progress.call_count, 2)
            report.assert_called_once()
            self.assertEqual(next(root.rglob('perf.data')).read_bytes(), b'PERFhetic perf bytes')

    def test_named_output_inherited_descriptors_seek_and_cleanup(self):
        # Exercise the production launcher's exact private inode checks and a
        # real exec boundary. macOS lacks prctl/procfs: only prctl is stubbed,
        # and the child uses the identical dirfd-relative open there. Linux
        # exercises the literal /proc/self/fd named path.
        shim = 'import ctypes,types;ctypes.CDLL=lambda _:types.SimpleNamespace(prctl=lambda *a:0);'
        child = ('import os,sys;d=int(sys.argv[1]);p=sys.argv[2];'
                 'f=os.open(p,os.O_WRONLY) if os.path.isdir("/proc/self/fd") '
                 'else os.open("perf.data",os.O_WRONLY,dir_fd=d);'
                 'os.write(f,b"payload");os.lseek(f,0,os.SEEK_SET);os.write(f,b"HEADER!");os.close(f)')
        with self.storage_host() as (host, root):
            with host.binding.mounted_guard(None) as guard, \
                 host.storage_io.AnchoredRoot(str(root), guard) as anchor:
                anchor.mkdir('private', mode=0o700)
                with anchor.directory('private') as directory, \
                     directory.open('perf.data', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600) as out:
                    d, f = directory.fileno(), out.fileno()
                    argv = capture.perf_argv(123, d, f)
                    self.assertEqual(argv[-1], f'/proc/self/fd/{d}/perf.data')
                    self.assertNotIn('--per-thread', argv)
                    real = [sys.executable, '-c', shim + 'exec(' + repr(capture.LAUNCHER) + ')',
                            str(capture.TRACE_LIMIT), str(d), str(f), sys.executable, '-c', child,
                            str(d), argv[-1]]
                    result = subprocess.run(real, pass_fds=(d, f), capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    out.seek(0)
                    self.assertEqual(out.read(7), b'HEADER!')
                for fd in (d, f):
                    with self.assertRaises(OSError):
                        os.fstat(fd)

    def test_named_launcher_rejects_symlink_replacement(self):
        shim = 'import ctypes,types;ctypes.CDLL=lambda _:types.SimpleNamespace(prctl=lambda *a:0);'
        with self.storage_host() as (host, root):
            with host.binding.mounted_guard(None) as guard, \
                 host.storage_io.AnchoredRoot(str(root), guard) as anchor:
                anchor.mkdir('private', mode=0o700)
                with anchor.directory('private') as directory, \
                     directory.open('perf.data', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600) as out:
                    d, f = directory.fileno(), out.fileno()
                    (root / 'private/perf.data').unlink()
                    (root / 'private/perf.data').symlink_to('/dev/null')
                    result = subprocess.run([sys.executable, '-c',
                        shim + 'exec(' + repr(capture.LAUNCHER) + ')', str(capture.TRACE_LIMIT),
                        str(d), str(f), sys.executable, '-c', 'raise Exception("must not run")'],
                        pass_fds=(d, f), capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 125, result.stderr)

    def test_leaf_report_retains_unknowns_and_requires_positive_samples(self):
        actual_popen = subprocess.Popen
        for report_text, expected in [('37.50\t3\tlibggml-cpu.so\t[.] ggml_vec_dot_q4_K_q8_K\n'
            '12.50\t1\t[unknown]\t[.] 0x123\n'
            '25.00\t2\tlibgomp.so.1\t[.] gomp_barrier_wait_end\n'
            '25.00\t2\tllama-server\t[.] llama_decode\n', 8), ('# no samples\n', 0)]:
            with self.subTest(expected=expected), self.storage_host() as (host, root):
                with host.binding.mounted_guard(None) as guard, \
                     host.storage_io.AnchoredRoot(str(root), guard) as anchor:
                    anchor.mkdir('private', mode=0o700)
                    with anchor.directory('private') as directory:
                        with directory.open('perf.data', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600):
                            pass
                        def spawn(argv, **kwargs):
                            self.assertIn('--no-children', argv)
                            self.assertIn('/proc/123/root', argv)
                            self.assertEqual(kwargs['env']['DEBUGINFOD_URLS'], '')
                            return actual_popen([sys.executable, '-c',
                                'import sys;sys.stdout.write(' + repr(report_text) + ')'], **kwargs)
                        result = {}
                        identity = {'pid': 123, 'starttime_ticks': 5}
                        with patch.object(capture, 'target_identity', return_value=identity), \
                             patch.object(capture.subprocess, 'Popen', side_effect=spawn):
                            capture.leaf_report(host, 'a', identity, directory, result)
                        self.assertEqual(result['symbol_report_sample_count'], expected)
                        self.assertEqual(result['symbol_resolution'],
                            'LEAF_REPORT_SAVED_UNRESOLVED_ROWS_RETAINED' if expected else 'UNAVAILABLE')
                        self.assertEqual((root / 'private/leaf-symbols.txt').read_text(), report_text)
                        self.assertNotIn('ggml_vec_dot', json.dumps(result))
                        if expected:
                            self.assertEqual(result['symbol_report_unresolved_samples'], 1)
                            self.assertEqual(result['symbol_report_resolved_samples'], 7)
                            self.assertEqual(result['leaf_sample_categories'], dict(quant_kernel=3,
                                resolved_libgomp=2, runtime_other=2, unresolved=1))

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
