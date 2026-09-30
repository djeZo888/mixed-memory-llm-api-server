"""Local regression: optional process diagnostics cannot stall mandatory guards."""
import ast
import contextlib
import inspect
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import telemetry


class GuardEvent:
    def __init__(self):
        self.stopped = False
        self.waits = []

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, seconds):
        self.waits.append(seconds)
        if len(self.waits) > 5:
            raise RuntimeError('test_guard_failed_to_stop')
        return self.stopped


class GuardHarness:
    s = object()

    def __init__(self):
        self.successful_checks = []

    def require(self, condition, reason):
        if not condition:
            raise RuntimeError(reason)
        self.successful_checks.append(reason)

    @staticmethod
    def now():
        return '2026-09-27T12:30:00+00:00'

    @staticmethod
    @contextlib.contextmanager
    def MountedStorageGuard(_):
        yield object()

    @staticmethod
    @contextlib.contextmanager
    def AnchoredRoot(root, _):
        class Anchor:
            @staticmethod
            @contextlib.contextmanager
            def open(name, flags):
                fd = os.open(str(pathlib.Path(root, name)), flags, 0o600)
                stream = os.fdopen(fd, 'wb')

                class CheckedStream:
                    @staticmethod
                    def fileno():
                        return stream.fileno()

                    @staticmethod
                    def check():
                        pass

                try:
                    yield CheckedStream()
                finally:
                    stream.close()

        yield Anchor()


class GuardResponsivenessTests(unittest.TestCase):
    def run_guard(self, failure):
        gib = 1024 ** 3
        ids = [telemetry.GPU, 'qwen-a', 'qwen-b',
               'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23']
        xml = '<nvidia_smi_log>' + ''.join(
            '<gpu><uuid>' + uid + '</uuid><temperature>'
            '<gpu_temp_slow_threshold>83 C</gpu_temp_slow_threshold>'
            '<gpu_temp_shutdown_threshold>95 C</gpu_temp_shutdown_threshold>'
            '</temperature></gpu>' for uid in ids) + '</nvidia_smi_log>'
        event, harness = GuardEvent(), GuardHarness()
        release_diagnostic = threading.Event()
        calls = {'gpu': 0, 'memory': 0}
        gpu_timeouts = []

        with tempfile.TemporaryDirectory() as root:
            cg = pathlib.Path(root, 'cgroup')
            cg.mkdir()
            values = {
                'memory.current': str(540 * gib),
                'memory.stat': 'anon 100\nfile 200\npgmajfault 0\n',
                'memory.swap.current': '0',
                'memory.events': 'oom 0\noom_kill 0\n',
                'cpu.stat': 'usage_usec 100\n',
                'cpuset.cpus.effective': '0-7,16-71',
                'cpuset.mems.effective': '0-7',
            }
            for name, value in values.items():
                (cg / name).write_text(value)
            state = {'native_cgroup': str(cg), 'native_pid': 99999999}

            def gpu_rows(timeout=None):
                gpu_timeouts.append(timeout)
                calls['gpu'] += 1
                if calls['gpu'] == 3:
                    if failure == 'swap':
                        (cg / 'memory.swap.current').write_text('4096')
                    elif failure == 'oom':
                        (cg / 'memory.events').write_text('oom 1\noom_kill 0\n')
                rows = [dict(uuid=uid, total_mib=100000, free_mib=50000,
                             used_mib=50000, temp_c=40, util_pct=0, board_w=50)
                        for uid in ids]
                if calls['gpu'] == 3:
                    if failure == 'temperature':
                        rows[0]['temp_c'] = 83  # Respect the lower hardware cutoff.
                    elif failure == 'reserve':
                        rows[0]['free_mib'] = 6999
                    elif failure == 'missing_gpu':
                        rows.pop()
                return rows

            def memory():
                calls['memory'] += 1
                available = 100 * gib if failure == 'host' and calls['gpu'] == 3 else 800 * gib
                return {'MemTotal': 1000 * gib, 'MemAvailable': available,
                        'SwapTotal': 4 * gib, 'SwapFree': 4 * gib}

            def blocked_diagnostic(*_args, **_kwargs):
                release_diagnostic.wait(2)
                return {'status': 'TEST_DIAGNOSTIC_RELEASED'}

            original_read = pathlib.Path.read_text

            def forbid_process_reads(path, *args, **kwargs):
                if str(path).startswith('/proc/'):
                    raise AssertionError('mandatory guard attempted process diagnostics: ' + str(path))
                return original_read(path, *args, **kwargs)

            with mock.patch.object(telemetry, 'LOG', root), \
                    mock.patch.object(telemetry, 'gpu_rows', side_effect=gpu_rows), \
                    mock.patch.object(telemetry, 'memory', side_effect=memory), \
                    mock.patch.object(telemetry, 'run_cmd', return_value=xml), \
                    mock.patch.object(telemetry, 'placement', side_effect=blocked_diagnostic) as placement, \
                    mock.patch.object(telemetry, 'interrupt_owner') as interrupt, \
                    mock.patch.object(pathlib.Path, 'read_text', forbid_process_reads):
                worker = threading.Thread(target=telemetry.monitor,
                                          args=(harness, state, event), daemon=True)
                worker.start()
                worker.join(.5)
                completed_without_diagnostic = not worker.is_alive()
                release_diagnostic.set()
                worker.join(2)
                self.assertTrue(completed_without_diagnostic,
                                'mandatory checks stalled behind optional placement')
                self.assertFalse(worker.is_alive())
                placement.assert_not_called()
                interrupt.assert_called_once_with()

            self.assertEqual(calls, {'gpu': 3, 'memory': 3})
            self.assertEqual(gpu_timeouts, [2, 2, 2])
            self.assertEqual(event.waits, [5, 5])
            self.assertTrue(event.is_set())
            self.assertEqual(harness.successful_checks.count('candidate_swap_or_oom'), 2)
            self.assertEqual(harness.successful_checks.count('host_reserve_breached'),
                             2 if failure in ['host', 'missing_gpu'] else 3)
            samples = [json.loads(line) for line in pathlib.Path(root, 'TELEMETRY.jsonl').read_text().splitlines()]
            self.assertGreaterEqual(len(samples), 2)
            self.assertTrue(all('process_status' not in s and 'placement' not in s for s in samples))
            return state['guard_failure']

    def test_blocked_placement_does_not_stall_periodic_guards_or_cutoff(self):
        self.assertEqual(self.run_guard('temperature'), 'gpu_temperature_cutoff')

    def test_host_reserve_gpu_reserve_swap_oom_and_missing_gpu_fail_closed(self):
        for failure, expected in [
                ('host', 'host_reserve_breached'),
                ('reserve', 'gpu_reserve_breached'),
                ('swap', 'candidate_swap_or_oom'),
                ('oom', 'candidate_swap_or_oom'),
                ('missing_gpu', 'gpu_telemetry_missing')]:
            with self.subTest(failure=failure):
                self.assertEqual(self.run_guard(failure), expected)

    def test_monitor_has_no_process_status_or_maps_diagnostics(self):
        tree = ast.parse(inspect.getsource(telemetry.monitor))
        literals = [node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        for literal in literals:
            for forbidden in ['numa_maps', 'smaps', 'process_status', '/proc']:
                self.assertNotIn(forbidden, literal)
        calls = [node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertNotIn('placement', calls)
        self.assertNotIn('bounded_placement', calls)

    def test_delayed_monitor_failure_does_not_resignal_owner_already_settling(self):
        event = threading.Event()
        event.set()
        state = {'status': 'FAILED_SETTLING'}
        with mock.patch.object(telemetry, 'run_cmd', side_effect=RuntimeError('delayed_failure')), \
                mock.patch.object(telemetry, 'interrupt_owner') as interrupt:
            telemetry.monitor(GuardHarness(), state, event)
        interrupt.assert_not_called()
        self.assertEqual(state, {'status': 'FAILED_SETTLING'})
        self.assertTrue(event.is_set())


if __name__ == '__main__':
    unittest.main()
