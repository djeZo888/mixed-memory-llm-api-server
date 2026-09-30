"""Local mocked optional profiling regressions; never invoke profiling tools."""
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import profile_activity as activity
import profile_perf as perf


class Child:
    def __init__(self, raw):
        self.stdout = io.BytesIO(raw)
        self.pid, self.returncode = 987, None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class OptionalProfileTests(unittest.TestCase):
    def fixture(self, root):
        proc, cg = pathlib.Path(root, 'proc'), pathlib.Path(root, 'cg')
        proc.mkdir(); cg.mkdir()
        fields = ['0'] * 45
        fields[0], fields[7], fields[9] = 'S', '2', '3'
        fields[11], fields[12], fields[19] = '4', '5', '123'
        (proc / 'stat').write_text('77 (fake name) ' + ' '.join(fields))
        (proc / 'io').write_text('rchar: 22\nwchar: 33\nread_bytes: 44\nwrite_bytes: 55\n')
        for name, value in {'cpu.stat': 'usage_usec 99\n', 'memory.events': 'oom 0\n',
                            'memory.current': '123', 'memory.swap.current': '0',
                            'io.stat': '8:1 rbytes=44 wbytes=55 rios=1 wios=1\n'}.items():
            (cg / name).write_text(value)
        return proc, cg, fields

    def test_boundaries_identity_failure_and_unsupported_gpu_are_optional(self):
        for case in ['normal', 'generation', 'missing_io', 'unsupported']:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                proc, cg, fields = self.fixture(root)
                if case == 'missing_io':
                    (proc / 'io').unlink()
                raw = b'# sm mem rxpci txpci\n20260927 14:00:00 0 10 20 2 3\n'
                if case == 'unsupported':
                    raw = b'# sm mem rxpci txpci\n20260927 14:00:00 0 10 20 - -\n'
                child = Child(raw)
                with mock.patch.object(activity.subprocess, 'Popen', return_value=child):
                    sampler = activity.Activity(77, cg)
                    sampler.proc = proc
                    sampler.start()
                    if case == 'generation':
                        fields[19] = '999'
                        (proc / 'stat').write_text('77 (fake name) ' + ' '.join(fields))
                    result = sampler.finish()
                self.assertEqual(result['status'], 'UNAVAILABLE' if case in ['generation', 'missing_io'] else 'AVAILABLE')
                self.assertEqual(result['gpu_activity_pcie']['raw'], raw.decode())
                self.assertEqual(result['gpu_activity_pcie']['status'], 'UNAVAILABLE' if case == 'unsupported' else 'AVAILABLE')
                self.assertEqual(result['host_dram_gb_s']['status'], 'UNAVAILABLE')
                self.assertEqual(result['gpu_vram_gb_s']['status'], 'UNAVAILABLE')
                self.assertEqual(child.returncode, -15)
                if case == 'normal':
                    self.assertEqual(result['before']['process']['utime_ticks'], 4)
                    self.assertEqual(result['after']['phase'], 'after')

    def test_perf_boundary_failure_never_launches_or_claims_counters(self):
        h = mock.Mock()
        h.transaction.side_effect = PermissionError
        with mock.patch.object(perf.subprocess, 'Popen') as popen:
            profiler = perf.Perf(h, 123, '/test').start()
            self.assertFalse(profiler.available())
            result = profiler.finish()
        popen.assert_not_called()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reason'], 'PermissionError')

    def test_boundary_does_not_start_sampler_or_gpu(self):
        with mock.patch.object(activity.Activity, '_sample', side_effect=FileNotFoundError), \
                mock.patch.object(activity.subprocess, 'Popen') as popen:
            self.assertEqual(activity.boundary(1, '/missing')['status'], 'UNAVAILABLE')
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
