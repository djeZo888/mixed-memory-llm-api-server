"""Finite image recovery/handoff cases; fake native/systemd I/O, no live access."""
import contextlib
import copy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('h031_image_recovery', ROOT / 'scripts/image_runtime/service.py')
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)
Runtime = service.Runtime
BOOT = '00000000-0000-0000-0000-000000000001'
PRIOR = 'a' * 32
CHILD = 'b' * 32
CID = 'c' * 64


class RecoveryProtocol(unittest.TestCase):
    """Real recovery, operation, admission, publication and settlement methods.

    Only storage, lease descriptors, hardware and external systems are fixture
    adapters. The other protocol test module separately uses real flock/storage.
    """
    def setUp(self):
        self.common = False
        self.locks = set()
        self.commands = []
        self.writes = []
        self.invocation = PRIOR
        self.restart_error = None
        self.start_child = True
        self.restart_execstop_invocations = []
        self.foreign_after_restart = False
        self.hardware_error = None
        self.native = {'Id': CID, 'State': {'StartedAt': 'old-start', 'Pid': 10, 'Running': True}}
        self.records = {'config.json': {}, 'state.json': {
            'schema_version': 1, 'owner': service.OWNER, 'phase': 'warm',
            'warm': True, 'run_id': PRIOR, 'container': {'id': CID, 'image_id': 'fixture'}}}
        self.instances = []
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.addCleanup(setattr, service, 'OPERATION_DEADLINE', None)
        self.addCleanup(setattr, service, 'SETTLEMENT_DEADLINE', None)
        self.stack.enter_context(patch.object(service, 'Runtime', side_effect=self.make_runtime))
        self.stack.enter_context(patch.object(service, 'start_admission', side_effect=self.lease))
        self.stack.enter_context(patch.object(service, 'verify_source_closure'))
        self.stack.enter_context(patch.object(service, 'run', side_effect=self.command))
        self.stack.enter_context(patch.dict(service.os.environ, {}, clear=True))
        self.stack.enter_context(patch.object(service.Path, 'read_text', side_effect=self.read_text))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def read_text(self, *args, **kwargs):
        # Calls used here are boot identity; systemd_identity is independently
        # replaced with a fixed unit-verified invocation at the adapter seam.
        return BOOT

    @contextlib.contextmanager
    def lease(self):
        self.assertFalse(self.common)
        self.common = True
        try:
            yield object()
        finally:
            self.common = False

    def make_runtime(self):
        test = self
        runtime = object.__new__(Runtime)
        runtime.config = {}
        runtime.guards = lambda: self.assertFalse(self.common)
        runtime.probe_hardware = lambda: self.assertFalse(self.common)
        runtime.systemd_identity = lambda: self.invocation
        runtime.process_stamp = lambda pid: {'pid': pid, 'start_ticks': pid * 100}
        runtime.cleanup_tmp = lambda run: {'removed_exact_owned_invocation': True}
        runtime.verify_resident = lambda state: self.assertFalse(self.common)
        runtime.inspect_owned = lambda state, **kw: copy.deepcopy(self.native)
        def hardware():
            self.assertTrue(self.common)
            if self.hardware_error:
                raise self.hardware_error
        runtime.require_hardware = hardware
        class Anchor:
            def check(self):
                return None
            def stat(self, name, *, missing_ok=False):
                return object() if name in test.records else None
            def read_json(self, name):
                return copy.deepcopy(test.records[name])
            def atomic_json(self, name, value):
                test.assertTrue(test.common, 'durable publication requires common lease')
                test.records[name] = copy.deepcopy(value)
                test.writes.append((name, copy.deepcopy(value)))
        anchor = Anchor()
        runtime.anchor = lambda: contextlib.nullcontext(anchor)
        @contextlib.contextmanager
        def singleton(name):
            if name in self.locks:
                raise RuntimeError('image_operation_busy')
            self.locks.add(name)
            try:
                yield anchor
            finally:
                self.locks.remove(name)
        runtime.singleton = singleton
        self.instances.append(runtime)
        return runtime

    def child_start(self):
        child = self.make_runtime()
        self.invocation = CHILD
        with patch.dict(service.os.environ, {'INVOCATION_ID': CHILD}):
            with child.operation('start'):
                self.native = {'Id': CID, 'State': {'StartedAt': 'new-start', 'Pid': 20, 'Running': True}}
                state = copy.deepcopy(child.expected_state)
                state.update(phase='warm', warm=True, run_id=CHILD,
                             container={'id': CID, 'image_id': 'fixture'},
                             native_generation=child.native_generation(self.native))
                child.publish(state)

    def command(self, argv, **kwargs):
        self.assertFalse(self.common, 'external I/O cannot retain common lease')
        self.commands.append(argv)
        if argv[:2] == ['systemctl', 'show']:
            return subprocess.CompletedProcess(argv, 0, 'InvocationID=' + self.invocation + '\n', '')
        if argv[:2] in (['systemctl', 'restart'], ['systemctl', 'stop']):
            self.assertNotIn('operation.lock', self.locks, 'leaf must acquire its own operation lock')
            self.assertIn('recovery.lock', self.locks, 'parent reservation must survive systemctl wait')
        if argv[:2] == ['systemctl', 'restart']:
            # A real restart first runs ExecStop under the prior invocation.
            # The parent has already removed the old native, so this must be
            # admitted without a second Docker stop/remove dispatch.
            old_child = self.make_runtime()
            self.restart_execstop_invocations.append(self.invocation)
            with patch.dict(service.os.environ, {'INVOCATION_ID': self.invocation}):
                old_child.reset_owned()
            if self.start_child:
                self.child_start()
            if self.foreign_after_restart:
                self.invocation = 'd' * 32
            if self.restart_error:
                raise self.restart_error
        elif argv[:2] == ['systemctl', 'stop']:
            child = self.make_runtime()
            with patch.dict(service.os.environ, {'INVOCATION_ID': self.invocation}):
                child.reset_owned()
        elif argv[:2] == ['docker', 'stop']:
            self.assertIn('operation.lock', self.locks)
            self.assertEqual(argv[-1], CID)
            self.native['State'].update(Running=False, Pid=0)
        elif argv[:2] == ['docker', 'rm']:
            self.assertIn('operation.lock', self.locks)
            self.assertEqual(argv[-1], CID)
            self.native = None
        return subprocess.CompletedProcess(argv, 0, '', '')

    def recover(self):
        try:
            service.recover()
        finally:
            self.assertFalse(self.common)
            self.assertIsNone(service.OPERATION_DEADLINE)

    def test_parent_releases_common_and_leaf_lock_for_real_child_handoff(self):
        self.recover()
        self.assertEqual(self.records['recovery.json']['status'], 'complete')
        self.assertEqual(self.records['recovery.json']['child_start'], CHILD)
        self.assertEqual(self.restart_execstop_invocations, [PRIOR])
        self.assertEqual(sum(c[:2] == ['docker', 'stop'] for c in self.commands), 1)
        self.assertEqual(sum(c[:2] == ['docker', 'rm'] for c in self.commands), 1)
        self.assertEqual(self.records['state.json']['run_id'], CHILD)
        self.assertTrue(self.records['state.json']['warm'])
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.commands), 1)
        self.assertEqual(self.locks, set())

    def test_second_systemd_start_cannot_consume_child_handoff_again(self):
        parent = self.make_runtime()
        self.records['recovery.json'] = {'token': 'e' * 32, 'boot': BOOT, 'pid': os.getpid(),
                                        'config_sha256': parent.config_digest(),
                                        'status': 'active', 'phase': 'restart',
                                        'process': {'pid': os.getpid(), 'start_ticks': os.getpid() * 100},
                                        'prior_invocation': PRIOR, 'child_start': CHILD}
        self.invocation = CHILD
        before = copy.deepcopy(self.records)
        with patch.dict(service.os.environ, {'INVOCATION_ID': CHILD}):
            with self.assertRaisesRegex(RuntimeError, 'image_recovery_changed'):
                with parent.operation('start'):
                    self.fail('second child admitted')
        self.assertEqual(self.records, before)
        self.assertEqual(self.commands, [])

    def test_foreign_stop_cannot_join_recovery(self):
        parent = self.make_runtime()
        self.records['recovery.json'] = {'token': 'e' * 32, 'boot': BOOT, 'pid': os.getpid(),
                                        'config_sha256': parent.config_digest(),
                                        'status': 'active', 'phase': 'settle',
                                        'process': {'pid': os.getpid(), 'start_ticks': os.getpid() * 100},
                                        'prior_invocation': PRIOR, 'child_start': CHILD}
        self.invocation = 'f' * 32
        before = copy.deepcopy(self.records)
        with patch.dict(service.os.environ, {'INVOCATION_ID': self.invocation}):
            with self.assertRaisesRegex(RuntimeError, 'image_recovery_changed'):
                parent.reset_owned()
        self.assertEqual(self.records, before)
        self.assertEqual(self.commands, [])

    def test_competing_recover_refuses_before_reservation_or_native_mutation(self):
        self.locks.add('recovery.lock')
        before = copy.deepcopy(self.records)
        with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'):
            self.recover()
        self.assertEqual(self.records, before)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.locks, {'recovery.lock'})

    def test_active_leaf_refuses_recover_without_leaving_recovery_reservation(self):
        self.locks.add('operation.lock')
        self.records['operation.json'] = {'status': 'active', 'token': 'e' * 32}
        before = copy.deepcopy(self.records)
        with self.assertRaisesRegex(RuntimeError, 'image_operation_(busy|unresolved)'):
            self.recover()
        self.assertEqual(self.records, before)
        self.assertFalse(any(c[0] == 'docker' or c[:2] == ['systemctl', 'restart'] for c in self.commands))

    def test_initial_hardware_failure_never_reserves_or_mutates(self):
        self.hardware_error = RuntimeError('hardware_fault')
        before = copy.deepcopy(self.records)
        with self.assertRaisesRegex(RuntimeError, 'hardware_fault'):
            self.recover()
        self.assertEqual(self.records, before)
        self.assertFalse(any(c[0] == 'docker' or c[:2] == ['systemctl', 'restart'] for c in self.commands))

    def test_foreign_invocation_after_uncertain_restart_is_never_stopped(self):
        self.restart_error = subprocess.TimeoutExpired('fixture-restart', 1)
        self.foreign_after_restart = True
        with self.assertRaisesRegex(RuntimeError, 'image_recovery_changed'):
            self.recover()
        self.assertFalse(any(c[:2] == ['systemctl', 'stop'] for c in self.commands))
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.commands), 1)
        self.assertTrue(self.native['State']['Running'])
        self.assertEqual(self.records['recovery.json']['status'], 'active')

    def test_uncertain_restart_without_child_keeps_reservation_and_cannot_replay(self):
        self.start_child = False
        self.restart_error = subprocess.TimeoutExpired('fixture-restart', 1)
        with self.assertRaisesRegex(RuntimeError, 'image_native_action_uncertain'):
            self.recover()
        self.assertEqual(self.records['recovery.json']['status'], 'active')
        self.assertIsNone(self.records['recovery.json']['child_start'])
        before = copy.deepcopy(self.records)
        with self.assertRaisesRegex(RuntimeError, 'image_operation_unresolved'):
            self.recover()
        self.assertEqual(self.records, before)
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.commands), 1)
        self.assertFalse(any(c[:2] == ['systemctl', 'stop'] for c in self.commands))

    def test_dead_parent_identity_cannot_authorize_child(self):
        child = self.make_runtime()
        self.records['recovery.json'] = {'token': 'e' * 32, 'boot': BOOT, 'pid': os.getpid(),
                                        'config_sha256': child.config_digest(),
                                        'status': 'active', 'phase': 'restart',
                                        'process': {'pid': os.getpid(), 'start_ticks': -1},
                                        'prior_invocation': PRIOR, 'child_start': None}
        self.invocation = CHILD
        before = copy.deepcopy(self.records)
        with patch.dict(service.os.environ, {'INVOCATION_ID': CHILD}):
            with self.assertRaisesRegex(RuntimeError, 'image_recovery_changed'):
                with child.operation('start'):
                    self.fail('dead parent handoff admitted')
        self.assertEqual(self.records, before)

    def test_failed_restart_settles_only_exact_child_outside_common_without_replay(self):
        self.restart_error = subprocess.TimeoutExpired('fixture-restart', 1)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.recover()
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.commands), 1)
        self.assertEqual(sum(c[:2] == ['systemctl', 'stop'] for c in self.commands), 1)
        self.assertIsNone(self.native)
        self.assertEqual(self.records['state.json']['phase'], 'stopped')
        self.assertFalse(self.records['state.json']['warm'])
        self.assertEqual(self.records['recovery.json']['status'], 'complete')


class SystemdChildIdentity(unittest.TestCase):
    def test_environment_invocation_without_exact_unit_cgroup_is_refused(self):
        runtime = object.__new__(Runtime)
        with patch.dict(service.os.environ, {'INVOCATION_ID': CHILD}), \
                patch.object(service.Path, 'read_text', return_value='0::/system.slice/foreign.service\n'), \
                patch.object(service, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'image_systemd_owner_required'):
                runtime.systemd_identity()
        command.assert_not_called()

    def test_exact_unit_requires_current_manager_pid_and_invocation(self):
        runtime = object.__new__(Runtime)
        for pid, invocation, accepted in [(os.getpid(), CHILD, True),
                                         (os.getpid() + 1, CHILD, False),
                                         (os.getpid(), PRIOR, False)]:
            unit = f'MainPID={pid}\nControlPID=0\nInvocationID={invocation}\n'
            with self.subTest(pid=pid, invocation=invocation), \
                    patch.dict(service.os.environ, {'INVOCATION_ID': CHILD}), \
                    patch.object(service.Path, 'read_text', return_value='0::/system.slice/' + service.UNIT), \
                    patch.object(service, 'run', return_value=subprocess.CompletedProcess([], 0, unit, '')):
                if accepted:
                    self.assertEqual(runtime.systemd_identity(), CHILD)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'image_systemd_owner_required'):
                        runtime.systemd_identity()


class LeaseAdmissionDeadlines(unittest.TestCase):
    def setUp(self):
        self.clock = 1000.0
        self.held = False
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.acquire = self.stack.enter_context(patch.object(service, 'acquire_lease', side_effect=self.lease))
        self.stack.enter_context(patch.object(service.time, 'monotonic', side_effect=lambda: self.clock))
        self.sleep = self.stack.enter_context(patch.object(service.time, 'sleep', side_effect=self.advance))

    def advance(self, seconds):
        self.assertFalse(self.held)
        self.clock += seconds

    @contextlib.contextmanager
    def lease(self, *, blocking):
        self.assertFalse(blocking)
        self.assertFalse(self.held)
        self.held = True
        try:
            yield object()
        finally:
            self.held = False

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
        self.assertFalse(self.held)
        self.acquire.assert_called_once_with(blocking=False)

    def test_body_busy_is_not_replayed(self):
        with self.assertRaises(service.LeaseBusy):
            with service.lease_admission(self.clock + 1):
                raise service.LeaseBusy()
        self.acquire.assert_called_once_with(blocking=False)
        self.sleep.assert_not_called()

    def test_busy_acquisition_retries_only_until_original_deadline(self):
        self.acquire.side_effect = service.LeaseBusy()
        with self.assertRaises(service.LeaseBusy):
            with service.lease_admission(self.clock + 0.5):
                self.fail('never acquired')
        self.assertAlmostEqual(self.clock, 1000.5)
        self.assertFalse(self.held)


if __name__ == '__main__':
    unittest.main()
