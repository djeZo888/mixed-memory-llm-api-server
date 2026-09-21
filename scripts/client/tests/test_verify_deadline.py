"""Real regression for an overall alarm expiring during owned-child cleanup."""

import contextlib
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify


@unittest.skipUnless(os.name == "posix", "POSIX client process/alarm contract")
class DeadlineOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v2-deadline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        self.old_handler = signal.getsignal(signal.SIGALRM)
        self.old_timer = signal.getitimer(signal.ITIMER_REAL)
        self.assertEqual(self.old_timer, (0.0, 0.0), "Tests must not consume another owner's active timer")
        signal.signal(signal.SIGALRM, self.expired)
        self.addCleanup(self.restore)

    @staticmethod
    def expired(*unused):
        raise AssertionError("An outer deadline interrupted process cleanup")

    def restore(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.old_handler)
        signal.setitimer(signal.ITIMER_REAL, *self.old_timer)
        path = self.root / "pid"
        if path.exists():
            pid = int(path.read_text())
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, 0)

    def test_expired_outer_alarm_cannot_interrupt_kill_and_diagnostics(self):
        # The child ignores TERM. Its runner reaches the .15s timeout, then
        # needs the .3s grace period before KILL. The outer .3s alarm would
        # formerly interrupt that grace period and leave this real child alive.
        code = ("import os,signal,time\nfrom pathlib import Path\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "Path('pid').write_text(str(os.getpid()))\n"
                "os.write(1,b'{\"type\":\"step_start\"}\\n')\n"
                "os.write(2,b'private timeout diagnostic\\n')\n"
                "time.sleep(60)\n")
        signal.setitimer(signal.ITIMER_REAL, 0.3)
        result = verify.run_process([sys.executable, "-I", "-B", "-c", code],
                                    self.root, self.env, timeout=0.15)
        self.assertTrue(result["timed_out"])
        self.assertTrue(result["process_tree_reaped"])
        self.assertEqual(result["stdout"], b'{"type":"step_start"}\n')
        self.assertEqual(result["stderr"], b"private timeout diagnostic\n")
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertLess(result["elapsed_seconds"], 4)
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.root / "pid").read_text()), 0)

    def test_unexpired_overall_alarm_is_rearmed_after_success(self):
        signal.setitimer(signal.ITIMER_REAL, 3)
        result = verify.run_process([sys.executable, "-I", "-B", "-c", "print('done')"],
                                    self.root, self.env, timeout=1)
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["process_tree_reaped"])
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreater(remaining, 0)
        self.assertLess(remaining, 3)
        self.assertEqual(interval, 0)
        self.assertEqual(signal.getsignal(signal.SIGALRM), self.expired)


if __name__ == "__main__":
    unittest.main()
