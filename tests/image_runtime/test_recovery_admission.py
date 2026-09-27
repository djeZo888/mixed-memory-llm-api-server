"""H013 recovery contention: fake clock and commands; no host/live operations."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('h013_image_recovery', ROOT / 'scripts/image_runtime/service.py')
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


class RecoveryAdmission(unittest.TestCase):
    def setUp(self):
        self.clock = 1000.0
        self.held = None
        self.acquired = []
        self.entries = []
        self.waits = []
        self.busy = {}  # successful-scope index -> remaining busy entries; -1 = persistent
        self.commands = []
        self.restart_error = None
        self.restart_elapsed = 0
        self.stop_elapsed = 0
        self.runtime = Mock()
        self.runtime.state.return_value = {'phase': 'warm', 'warm': True, 'run_id': 'c' * 32}
        self.runtime.inspect_owned.return_value = {'Id': 'a' * 64, 'State': {'Running': True}}
        for name in ('guards', 'require_hardware', 'reset_owned', 'verify_resident', 'save', 'inspect_owned'):
            method = getattr(self.runtime, name)
            result = method.return_value
            method.side_effect = lambda *args, result=result, **kwargs: self.under_lease(result)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.addCleanup(setattr, service, 'OPERATION_DEADLINE', None)
        self.stack.enter_context(patch.object(service, 'Runtime', return_value=self.runtime))
        self.acquire = self.stack.enter_context(patch.object(service, 'acquire_lease', side_effect=self.lease))
        self.stack.enter_context(patch.object(service.time, 'monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch.object(service.time, 'sleep', side_effect=self.sleep))
        self.stack.enter_context(patch.object(service.subprocess, 'run', side_effect=self.command))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def sleep(self, seconds):
        self.assertIsNone(self.held)
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 0.2)
        self.waits.append(seconds)
        self.clock += seconds

    @contextlib.contextmanager
    def lease(self, *, blocking):
        self.assertFalse(blocking)
        self.assertIsNone(self.held)
        index = len(self.acquired)
        self.entries.append(index)
        if self.busy.get(index, 0):
            if self.busy[index] > 0:
                self.busy[index] -= 1
            raise service.LeaseBusy()  # __enter__, not factory or yielded body
        lease = object()
        self.acquired.append(lease)
        self.held = lease
        try:
            yield lease
        finally:
            self.held = None

    def under_lease(self, result=None):
        self.assertIsNotNone(self.held)
        self.assertIs(self.runtime.lease, self.held)
        return result

    def command(self, argv, *, timeout, **kwargs):
        self.commands.append((argv, timeout))
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, service.OPERATION_DEADLINE - self.clock)
        if argv[0] == 'systemctl':
            self.assertIsNone(self.held)  # child needs its own canonical lease
        else:
            self.under_lease()
            self.assertEqual(argv, ['docker', 'kill', 'a' * 64])
        if argv[:2] == ['systemctl', 'restart']:
            self.clock += self.restart_elapsed
            if self.restart_error:
                raise self.restart_error
        elif argv[:2] == ['systemctl', 'stop']:
            self.clock += self.stop_elapsed
        return subprocess.CompletedProcess(argv, 0, '', '')

    def recover(self):
        try:
            return service.recover()
        finally:
            self.assertIsNone(self.held)
            self.assertIsNone(service.OPERATION_DEADLINE)

    def test_busy_then_free_preflight_mutation_and_verification_each_run_once(self):
        self.busy = {0: 2, 1: 2, 2: 2}
        self.recover()
        self.assertEqual(self.entries, [0, 0, 0, 1, 1, 1, 2, 2, 2])
        self.assertEqual(len(self.waits), 6)
        self.assertEqual(self.runtime.guards.call_count, 4)
        self.assertEqual(self.runtime.require_hardware.call_count, 2)
        self.runtime.reset_owned.assert_called_once_with()
        self.runtime.verify_resident.assert_called_once_with(self.runtime.state.return_value)
        self.assertEqual([argv for argv, _ in self.commands], [['systemctl', 'restart', service.UNIT]])
        self.runtime.save.assert_not_called()

    def test_preflight_acquisition_deadline_never_mutates_or_cleans_up(self):
        self.busy = {0: -1}
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.assertEqual(self.clock, 1840)
        self.assertEqual(self.acquired, [])
        self.assertEqual(self.runtime.method_calls, [])
        self.assertEqual(self.commands, [])

    def test_mutation_acquisition_uses_remaining_shared_budget_without_cleanup(self):
        def hardware():
            self.under_lease()
            self.clock = 1839.9
        self.runtime.require_hardware.side_effect = hardware
        self.busy = {1: -1}
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.assertEqual(self.clock, 1840)
        self.assertAlmostEqual(sum(self.waits), 0.1)
        self.runtime.reset_owned.assert_not_called()
        self.runtime.save.assert_not_called()
        self.assertEqual(self.commands, [])

    def test_cleanup_busy_then_free_uses_current_lease_and_exact_owner_once(self):
        self.busy = {2: 2}
        self.restart_error = subprocess.TimeoutExpired('synthetic-restart', 840)
        self.restart_elapsed = 840
        self.stop_elapsed = 40
        with self.assertRaises(subprocess.TimeoutExpired):
            self.recover()
        self.assertEqual(self.entries, [0, 1, 2, 2, 2])
        self.assertAlmostEqual(self.clock, 1880.4)
        self.runtime.reset_owned.assert_called_once_with()
        self.runtime.inspect_owned.assert_called_once_with(self.runtime.state.return_value, missing_ok=True)
        self.runtime.save.assert_called_once()
        self.assertEqual(self.runtime.save.call_args.args[0]['phase'], 'failed')
        self.assertEqual([argv for argv, _ in self.commands], [
            ['systemctl', 'restart', service.UNIT], ['systemctl', 'stop', service.UNIT],
            ['docker', 'kill', 'a' * 64]])

    def test_persistent_cleanup_contention_cannot_spend_past_reserved_budget(self):
        self.busy = {2: -1}
        self.restart_error = subprocess.TimeoutExpired('synthetic-restart', 840)
        self.restart_elapsed = 840
        self.stop_elapsed = 40
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.assertEqual(self.clock, 1900)
        self.assertAlmostEqual(sum(self.waits), 20)
        self.runtime.inspect_owned.assert_not_called()
        self.runtime.save.assert_not_called()
        self.assertEqual(len(self.commands), 2)

    def test_verification_contention_spends_only_active_budget_then_bounded_cleanup(self):
        self.restart_elapsed = 839.9
        self.busy = {2: 1}
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.assertEqual(self.clock, 1840)
        self.runtime.verify_resident.assert_not_called()
        self.runtime.save.assert_called_once()
        self.assertEqual([argv[:2] for argv, _ in self.commands], [
            ['systemctl', 'restart'], ['systemctl', 'stop'], ['docker', 'kill']])

    def test_preflight_body_busy_fatal_guard_and_latch_failures_are_not_replayed(self):
        for method, error in (
                ('guards', service.LeaseBusy()),
                ('guards', RuntimeError('registered_storage_guard_failed')),
                ('require_hardware', RuntimeError('hardware_fault'))):
            with self.subTest(method=method, error=type(error).__name__):
                self.runtime.reset_mock()
                self.acquired.clear()
                self.entries.clear()
                self.runtime.guards.side_effect = lambda: self.under_lease()
                self.runtime.require_hardware.side_effect = lambda: self.under_lease()
                getattr(self.runtime, method).side_effect = error
                with self.assertRaises(type(error)) as raised:
                    self.recover()
                self.assertIs(raised.exception, error)
                self.assertEqual(self.entries, [0])
                getattr(self.runtime, method).assert_called_once_with()
                self.runtime.reset_owned.assert_not_called()
                self.assertEqual(self.commands, [])
                self.assertEqual(self.waits, [])

    def test_mutation_body_busy_is_not_replayed_and_cleanup_remains_allowed(self):
        self.runtime.reset_owned.side_effect = service.LeaseBusy()
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.runtime.reset_owned.assert_called_once_with()
        self.runtime.save.assert_called_once()
        self.assertEqual(self.waits, [])
        self.assertEqual([argv[:2] for argv, _ in self.commands], [['systemctl', 'stop'], ['docker', 'kill']])

    def test_verification_body_failure_is_not_replayed(self):
        self.runtime.verify_resident.side_effect = service.LeaseBusy()
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.runtime.verify_resident.assert_called_once()
        self.runtime.save.assert_called_once()
        self.assertEqual(self.waits, [])

    def test_cleanup_ownership_failure_never_replays_kills_or_saves(self):
        self.restart_error = RuntimeError('owned_systemd_restart_warm_failed')
        self.runtime.inspect_owned.side_effect = RuntimeError('owned_backend_identity_mismatch')
        with self.assertRaisesRegex(RuntimeError, 'owned_backend_identity_mismatch'):
            self.recover()
        self.runtime.inspect_owned.assert_called_once()
        self.runtime.save.assert_not_called()
        self.assertEqual(self.waits, [])
        self.assertEqual(len(self.commands), 2)

    def test_cleanup_body_busy_never_replays_kill_or_save(self):
        self.restart_error = RuntimeError('owned_systemd_restart_warm_failed')
        self.runtime.save.side_effect = service.LeaseBusy()
        with self.assertRaises(service.LeaseBusy):
            self.recover()
        self.runtime.save.assert_called_once()
        self.runtime.inspect_owned.assert_called_once()
        self.assertEqual(self.waits, [])
        self.assertEqual([argv[:2] for argv, _ in self.commands], [
            ['systemctl', 'restart'], ['systemctl', 'stop'], ['docker', 'kill']])

    def test_nonbusy_lease_refusal_never_waits_or_mutates(self):
        self.acquire.side_effect = service.LeaseError('lock_path_changed')
        with self.assertRaisesRegex(service.LeaseError, 'lock_path_changed'):
            self.recover()
        self.acquire.assert_called_once_with(blocking=False)
        self.assertEqual(self.waits, [])
        self.assertEqual(self.runtime.method_calls, [])
        self.assertEqual(self.commands, [])

    def test_expired_deadline_never_enters_lease_or_body(self):
        with self.assertRaisesRegex(RuntimeError, 'owned_operation_deadline'):
            with service.lease_admission(self.clock):
                self.fail('expired body')
        self.acquire.assert_not_called()

    def test_acquisition_finishing_at_deadline_releases_without_body(self):
        @contextlib.contextmanager
        def delayed(**kwargs):
            with self.lease(**kwargs) as lease:
                self.clock += 1
                yield lease
        self.acquire.side_effect = delayed
        with self.assertRaisesRegex(RuntimeError, 'owned_operation_deadline'):
            with service.lease_admission(self.clock + 1):
                self.fail('expired body')
        self.assertIsNone(self.held)
        self.acquire.assert_called_once_with(blocking=False)


if __name__ == '__main__':
    unittest.main()
