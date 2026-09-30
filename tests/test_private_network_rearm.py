"""Finite recovery simulation: no host, firewall, network or service operations."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.control import private_network_rearm as recovery


class RearmTests(unittest.TestCase):
    def setUp(self):
        self.states = {name: {'UnitFileState': 'enabled', 'ActiveState': 'active'}
                       for name in recovery.SOCKETS}
        self.commands = []
        self.refuse = False
        self.disable_on_check = None
        self.pending = False
        self.command_patch = patch.object(recovery, '_command', side_effect=self.command)
        self.command_patch.start()
        self.addCleanup(self.command_patch.stop)

    def command(self, argv, deadline):
        self.commands.append(argv)
        if argv[0] == recovery.SYSTEMCTL and argv[1] == 'show':
            return '\n'.join(f'{key}={value}' for key, value in self.states[argv[2]].items())
        if recovery.NETWORK_HELPER in argv:
            if self.refuse:
                raise recovery.RearmError('simulated guard refusal')
            if argv[-1] == 'check' and self.disable_on_check:
                self.states[self.disable_on_check]['UnitFileState'] = 'disabled'
            return ''
        if argv[:2] == [recovery.SYSTEMCTL, 'reset-failed']:
            self.assertIn(argv[2], recovery.SOCKETS)
            return ''
        if argv[:3] == [recovery.SYSTEMCTL, '--no-block', 'start']:
            self.assertIn(argv[3], recovery.SOCKETS)
            self.states[argv[3]]['ActiveState'] = 'activating' if self.pending else 'active'
            return ''
        self.fail('unexpected mutation or model command: ' + repr(argv))

    def mutations(self):
        return [args for args in self.commands
                if args[0] == recovery.SYSTEMCTL and args[1] != 'show']

    def test_recovered_network_rearms_failed_and_inactive_only(self):
        failed, inactive, disabled = recovery.SOCKETS[:3]
        self.states[failed]['ActiveState'] = 'failed'
        self.states[inactive]['ActiveState'] = 'inactive'
        self.states[disabled] = {'UnitFileState': 'disabled', 'ActiveState': 'inactive'}
        self.assertIn('upstream readiness unknown', recovery.rearm_once(100))
        self.assertEqual(self.mutations(), [
            [recovery.SYSTEMCTL, 'reset-failed', failed],
            [recovery.SYSTEMCTL, '--no-block', 'start', failed],
            [recovery.SYSTEMCTL, '--no-block', 'start', inactive]])
        guards = [args[-1] for args in self.commands if recovery.NETWORK_HELPER in args]
        self.assertEqual(guards, ['apply', 'check'])

    def test_guard_failure_cannot_start_socket_or_model(self):
        self.states[recovery.SOCKETS[0]]['ActiveState'] = 'failed'
        self.refuse = True
        with self.assertRaises(recovery.RearmError):
            recovery.rearm_once(100)
        self.assertEqual(self.mutations(), [])

    def test_disabled_masked_sockets_never_enabled_or_started(self):
        for number, name in enumerate(recovery.SOCKETS):
            self.states[name] = {'UnitFileState': 'disabled' if number % 2 else 'masked',
                                 'ActiveState': 'inactive'}
        recovery.rearm_once(100)
        self.assertEqual(self.mutations(), [])
        self.assertFalse(any(recovery.NETWORK_HELPER in args for args in self.commands))

    def test_operator_disable_before_start_is_respected(self):
        name = recovery.SOCKETS[0]
        self.states[name]['ActiveState'] = 'failed'
        self.disable_on_check = name
        recovery.rearm_once(100)
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.states[name]['UnitFileState'], 'disabled')

    def test_pending_activation_is_not_reported_active(self):
        self.states[recovery.SOCKETS[0]]['ActiveState'] = 'inactive'
        self.pending = True
        with self.assertRaisesRegex(recovery.RearmError, 'pending'):
            recovery.rearm_once(100)

    def test_unavailable_retries_have_finite_backoff_and_no_mutations(self):
        self.states[recovery.SOCKETS[0]]['ActiveState'] = 'failed'
        self.refuse = True
        with patch.object(recovery.time, 'monotonic', return_value=0), \
                patch.object(recovery.time, 'sleep') as sleep, redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(recovery.RearmError, 'next timer observation'):
                recovery.recover()
        self.assertEqual([args.args[0] for args in sleep.call_args_list], list(recovery.DELAYS[1:]))
        self.assertEqual(sum(recovery.NETWORK_HELPER in args for args in self.commands),
                         len(recovery.DELAYS))
        self.assertEqual(self.mutations(), [])

    def test_network_return_ends_retries_immediately_after_rearm(self):
        self.states[recovery.SOCKETS[0]]['ActiveState'] = 'failed'
        self.refuse = True
        def network_returns(_):
            self.refuse = False
        with patch.object(recovery.time, 'monotonic', return_value=0), \
                patch.object(recovery.time, 'sleep', side_effect=network_returns) as sleep, \
                redirect_stderr(io.StringIO()):
            self.assertIn('sockets active', recovery.recover())
        sleep.assert_called_once_with(5)
        self.assertEqual(len(self.mutations()), 2)

    def test_late_network_return_recovers_on_next_timer_run(self):
        self.states[recovery.SOCKETS[0]]['ActiveState'] = 'failed'
        self.refuse = True
        with patch.object(recovery.time, 'monotonic', return_value=0), \
                patch.object(recovery.time, 'sleep'), redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(recovery.RearmError, 'run exhausted'):
                recovery.recover()
            self.assertEqual(self.mutations(), [])
            # Independent later invocation, including long-after-boot NIC repair.
            self.refuse = False
            self.assertIn('sockets active', recovery.recover())
            self.commands.clear()
            self.assertIn('no enabled stopped sockets', recovery.recover())
            self.assertEqual(self.mutations(), [])
            self.assertFalse(any(recovery.NETWORK_HELPER in a for a in self.commands))

    def test_time_budget_stops_before_next_sleep(self):
        with patch.object(recovery, 'rearm_once', side_effect=recovery.RearmError('down')) as attempt, \
                patch.object(recovery.time, 'monotonic', side_effect=[0, 0, 89]), \
                patch.object(recovery.time, 'sleep') as sleep, redirect_stderr(io.StringIO()):
            with self.assertRaises(recovery.RearmError):
                recovery.recover()
        attempt.assert_called_once()
        sleep.assert_not_called()

    def test_source_timer_repeats_after_inactive_without_restart_or_dependency(self):
        self.assertIn('passed', recovery.source_check())
        units = recovery.expected_units()
        service = units['llm-private-network-rearm.service']
        timer = units['llm-private-network-rearm.timer']
        self.assertIn('TimeoutStartSec=120', service)
        self.assertIn('Type=oneshot', service)
        self.assertNotIn('RemainAfterExit', service)
        self.assertIn('Restart=no', service)
        self.assertIn('OnBootSec=45s', timer)
        self.assertIn('OnUnitInactiveSec=60s', timer)
        self.assertIn('Unit=llm-private-network-rearm.service', timer)
        self.assertNotIn('Requires=', service)
        self.assertNotIn('Wants=', service)
        self.assertLess(sum(recovery.DELAYS), recovery.BUDGET_SECONDS)


if __name__ == '__main__':
    unittest.main()
