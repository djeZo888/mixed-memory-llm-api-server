"""Optional diagnostic timeout must not become a safety failure or a wait."""
import os
import pathlib
import subprocess
import sys
import time
import unittest
from unittest import mock
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import telemetry


class BoundedPlacementTests(unittest.TestCase):
    def test_real_blocked_child_times_out_unavailable_and_is_settled(self):
        real_popen = subprocess.Popen
        def sleeping_child(*args, **kwargs):
            return real_popen([sys.executable, '-c', 'import time; time.sleep(10)'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        start = time.monotonic()
        with mock.patch.object(telemetry.subprocess, 'Popen', side_effect=sleeping_child):
            result = telemetry.bounded_placement(os.getpid(), timeout=.05)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reason'], 'timeout')
        self.assertTrue(result['diagnostic_settled'])
        self.assertLess(time.monotonic() - start, 1)

    def test_unreaped_child_has_bounded_wait_and_retained_identity(self):
        child = mock.Mock(pid=12345)
        child.communicate.side_effect = subprocess.TimeoutExpired('diagnostic', .01)
        child.wait.side_effect = subprocess.TimeoutExpired('diagnostic', .2)
        with mock.patch.object(telemetry.subprocess, 'Popen', return_value=child):
            result = telemetry.bounded_placement(99, timeout=.01)
        child.kill.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=.2)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['diagnostic_pid'], 12345)
        self.assertFalse(result['diagnostic_settled'])


if __name__ == '__main__':
    unittest.main()
