"""Finite offline ownership tests using real anchored files and canonical flock.

No Docker, systemd, protected VM reads, GPU work or model loading occurs here.
Only native commands and external guard producers are substituted.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
SPEC = importlib.util.spec_from_file_location('image_operation_protocol_review', REPO / 'scripts/image_runtime/service.py')
service = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = service
SPEC.loader.exec_module(service)
from common.lifecycle_lease import acquire_lease, LeaseBusy
from install import storage_io

CID = 'a' * 64
IMAGE = 'sha256:' + 'b' * 64
BOOT = '11111111-2222-3333-4444-555555555555'


class OperationProtocol(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='.image-operation-', dir=REPO))
        self.root = Path(self.tmp)
        info = self.root.stat()
        identity = {'path': str(self.root), 'mount': str(self.root), 'uuid': 'fixture',
                    'fstype': 'ext4', 'device': f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'}
        self.snapshot = {'schema_version': 1, 'data': identity.copy(), 'models': identity.copy(),
                         'roots': {'services': str(self.root)}}
        self.storage_valid, self.source_valid, self.hardware_valid = True, True, True
        self.boot = BOOT
        self.lease_durations = []
        self.anchor = self.stack.enter_context(storage_io.AnchoredRoot(
            str(self.root), self.storage_guard, uid=os.geteuid()))
        self.runtime = self.make_runtime()
        self.anchor.atomic_json('config.json', self.runtime.config)
        original_read_text = Path.read_text
        def read_text(path, *args, **kwargs):
            if str(path) == '/proc/sys/kernel/random/boot_id':
                return self.boot + '\n'
            return original_read_text(path, *args, **kwargs)
        self.stack.enter_context(patch.object(Path, 'read_text', read_text))
        self.stack.enter_context(patch.object(service, 'acquire_lease', side_effect=self.lease))
        self.stack.enter_context(patch.object(service, 'verify_source_closure', side_effect=self.source_guard))
        self.stack.enter_context(patch.dict(os.environ, {'INVOCATION_ID': ''}))
        self.addCleanup(self.clear_deadlines)

    def clear_deadlines(self):
        service.OPERATION_DEADLINE = service.SETTLEMENT_DEADLINE = None

    def make_runtime(self):
        runtime = object.__new__(service.Runtime)
        runtime.config = {'owner': service.OWNER, 'image_id': IMAGE, 'gpu_uuid': service.GPU_UUID}
        runtime.storage_anchor = self.anchor
        runtime.services_anchor = self.anchor
        runtime.guards = self.full_guards
        runtime.require_hardware = self.hardware_guard
        runtime.probe_hardware = self.probe_guard
        runtime.inspect_owned = Mock(return_value=None)
        runtime.process_stamp = Mock(return_value={'pid': 42, 'start_ticks': 123})
        return runtime

    @contextlib.contextmanager
    def lease(self, *, blocking=False):
        with acquire_lease(blocking=blocking, system_root=self.root, trusted_uid=os.geteuid()) as lease:
            started = time.perf_counter()
            try:
                yield lease
            finally:
                self.lease_durations.append(time.perf_counter() - started)

    def assert_common_available(self):
        with self.lease() as lease:
            lease.validate()

    def full_guards(self):
        # A full external storage check must itself run outside the common lease.
        self.assert_common_available()
        self.storage_guard()

    def storage_guard(self):
        if not self.storage_valid:
            raise storage_io.StorageIOError('fixture_mount_lost')
        return copy.deepcopy(self.snapshot)

    def source_guard(self, _config):
        service.require(self.source_valid, 'runtime_source_changed')

    def probe_guard(self):
        self.assert_common_available()
        return {'boot': self.boot, 'observed_at': service.now(), 'observation_id': 'fixture'}

    def hardware_guard(self):
        service.require(self.hardware_valid, 'hardware_validation_stale')

    def owned_state(self):
        return {'schema_version': 1, 'owner': service.OWNER, 'phase': 'loading', 'warm': False,
                'run_id': 'c' * 32, 'container': {'id': CID, 'image_id': IMAGE},
                'native_generation': {'StartedAt': '2026-09-29T08:00:00Z', 'Pid': 42,
                                      'pid': 42, 'start_ticks': 123}}

    def container(self, running=True, *, pid=None, started='2026-09-29T08:00:00Z'):
        return {'Id': CID, 'State': {'Running': running,
                'Pid': (42 if running else 0) if pid is None else pid, 'StartedAt': started}}

    def blocked_command(self, action):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def command(argv, **_kwargs):
            self.assert_common_available()
            self.assertEqual(argv, ['fake-native', action])
            entered.set()
            if not release.wait(3):
                raise AssertionError('finite fake command deadline')
            return subprocess.CompletedProcess(argv, 0, '', '')
        def worker():
            try:
                with self.runtime.operation('start'):
                    state = copy.deepcopy(self.runtime.expected_state)
                    self.runtime.dispatch(state, action, ['fake-native', action], hardware=True)
            except BaseException as error:
                errors.append(error)
        with patch.object(service, 'run', side_effect=command):
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(2), errors)
                self.assert_common_available()
                contender = self.make_runtime()
                with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'):
                    with contender.operation('stop'):
                        self.fail('a second image operation entered')
            finally:
                release.set()
                thread.join(3)
            self.assertFalse(thread.is_alive(), 'fake native command did not settle')
            self.assertEqual(errors, [])

    def test_common_lease_available_during_blocked_load_and_warm(self):
        for action in ('start', 'warm'):
            with self.subTest(action=action):
                self.blocked_command(action)

    def test_invalidated_identity_cannot_publish_late_ready(self):
        cases = ('operation_token', 'state_owner', 'state_generation', 'config', 'boot',
                 'source', 'native_process', 'operation_lock')
        for case in cases:
            with self.subTest(case=case):
                # Each invalidation leaves an unresolved operation; use a fresh
                # protected fixture rather than clearing evidence for a retry.
                fixture = OperationProtocol()
                fixture.setUp()
                try:
                    runtime = fixture.runtime
                    if case == 'native_process':
                        fixture.anchor.atomic_json('state.json', fixture.owned_state())
                    with self.assertRaises((RuntimeError, storage_io.StorageIOError)):
                        with runtime.operation('start'):
                            ready = copy.deepcopy(runtime.expected_state)
                            ready.update(phase='warm', warm=True)
                            if case == 'operation_token':
                                record = runtime.record('operation.json')
                                record['token'] = 'd' * 32
                                fixture.anchor.atomic_json('operation.json', record)
                            elif case.startswith('state_'):
                                state = runtime.state()
                                state['owner' if case == 'state_owner' else 'run_id'] = 'replacement'
                                fixture.anchor.atomic_json('state.json', state)
                            elif case == 'config':
                                fixture.anchor.atomic_json('config.json', {'image_id': 'replaced'})
                            elif case == 'boot':
                                fixture.boot = 'replacement-boot'
                            elif case == 'native_process':
                                runtime.process_stamp.return_value = {'pid': 42, 'start_ticks': 124}
                            elif case == 'operation_lock':
                                (fixture.root / 'operation.lock').unlink()
                                (fixture.root / 'operation.lock').touch(mode=0o600)
                            else:
                                fixture.source_valid = False
                            runtime.publish(ready, hardware=True)
                    state = fixture.anchor.read_json('state.json') if fixture.anchor.stat('state.json', missing_ok=True) else {}
                    self.assertIsNot(state.get('warm'), True)
                    self.assertNotEqual(runtime.record('operation.json')['status'], 'complete')
                finally:
                    fixture.doCleanups()

    def retained_residency(self):
        # The retained 09:57:40 capture contains this GPU process row. Restore
        # verify_resident()'s tuple type before exercising real save/finally;
        # this finite source fixture is not a historical or live recovery claim.
        return {'container_id': CID, 'started_at': '2026-09-29T09:55:35.757660444Z',
                'gpu_processes': [(service.GPU_UUID, '1664791', '32224')],
                'device_current': {'free_bytes': 17064525824, 'total_bytes': 51527024640,
                                   'uuid': service.GPU_UUID},
                'host_current': {'MemAvailable': 916447969280, 'MemTotal': 946820820992,
                                 'SwapFree': 922480640, 'SwapTotal': 3157258240}}

    def test_warm_tuple_residency_publishes_and_operation_finally_completes(self):
        self.anchor.atomic_json('state.json', self.owned_state())
        with self.runtime.operation('start'):
            state = copy.deepcopy(self.runtime.expected_state)
            state.update(phase='warm', warm=True, residency=self.retained_residency())
            self.assertIsInstance(state['residency']['gpu_processes'][0], tuple)
            self.runtime.publish(state, hardware=True)
            durable = self.runtime.state()
            self.assertIsInstance(durable['residency']['gpu_processes'][0], list)
            self.assertEqual(self.runtime.expected_state, durable)
        self.assertEqual(self.runtime.record('operation.json')['status'], 'complete')
        self.assertTrue(self.runtime.state()['warm'])

    def test_tuple_normalization_does_not_accept_changed_persisted_fields(self):
        for case in ('residency', 'container', 'native_generation', 'run_id', 'warm', 'new_field'):
            with self.subTest(case=case):
                fixture = OperationProtocol()
                fixture.setUp()
                try:
                    runtime = fixture.runtime
                    fixture.anchor.atomic_json('state.json', fixture.owned_state())
                    with self.assertRaisesRegex(RuntimeError, 'image_operation_changed'):
                        with runtime.operation('start'):
                            state = copy.deepcopy(runtime.expected_state)
                            state.update(phase='warm', warm=True, residency=fixture.retained_residency())
                            runtime.publish(state, hardware=True)
                            # This assertion prevents the original tuple mismatch
                            # from masquerading as a successful negative control.
                            self.assertEqual(runtime.expected_state, runtime.state())
                            changed = runtime.state()
                            if case == 'residency':
                                changed['residency']['gpu_processes'][0][2] = '32225'
                            elif case == 'container':
                                changed['container']['id'] = 'd' * 64
                            elif case == 'native_generation':
                                changed['native_generation']['start_ticks'] += 1
                            elif case == 'run_id':
                                changed['run_id'] = 'd' * 32
                            elif case == 'warm':
                                changed['warm'] = False
                            else:
                                changed['unexpected'] = True
                            fixture.anchor.atomic_json('state.json', changed)
                    self.assertEqual(runtime.record('operation.json')['status'], 'active')
                finally:
                    fixture.doCleanups()

    def test_unknown_hardware_and_lost_storage_cannot_publish_ready(self):
        for case in ('hardware', 'storage'):
            with self.subTest(case=case):
                fixture = OperationProtocol()
                fixture.setUp()
                try:
                    with self.assertRaises((RuntimeError, storage_io.StorageIOError)):
                        with fixture.runtime.operation('start'):
                            state = copy.deepcopy(fixture.runtime.expected_state)
                            state.update(phase='warm', warm=True)
                            if case == 'hardware':
                                fixture.hardware_valid = False
                            else:
                                fixture.storage_valid = False
                            fixture.runtime.publish(state, hardware=True)
                    fixture.storage_valid = True
                    state = fixture.runtime.state()
                    self.assertIsNot(state.get('warm'), True)
                finally:
                    fixture.storage_valid = True
                    fixture.doCleanups()

    def test_uncertain_native_dispatch_is_durable_and_never_replayed(self):
        argv = ['docker', 'start', CID]
        with self.runtime.operation('start'):
            state = copy.deepcopy(self.runtime.expected_state)
            with patch.object(service, 'run', side_effect=subprocess.TimeoutExpired(argv, 1)) as command:
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.runtime.dispatch(state, 'start', argv)
                self.assertEqual(self.runtime.state()['native_actions']['start'], 'dispatched')
                for candidate in (state, self.runtime.state()):
                    with self.assertRaisesRegex(RuntimeError, 'image_native_action_uncertain'):
                        self.runtime.dispatch(candidate, 'start', argv)
                self.assertEqual(command.call_count, 1)

    def test_active_or_unresolved_operation_cannot_be_replayed_after_owner_exit(self):
        self.anchor.atomic_json('operation.json', {'status': 'active', 'token': 'old-uncertain'})
        with self.assertRaisesRegex(RuntimeError, 'image_operation_unresolved'):
            with self.runtime.operation('start'):
                self.fail('unsettled operation was replayed')
        self.assertEqual(self.runtime.record('operation.json')['token'], 'old-uncertain')

    def test_stop_wait_is_outside_common_lease_and_requires_exact_physical_absence(self):
        self.anchor.atomic_json('state.json', self.owned_state())
        entered, release = threading.Event(), threading.Event()
        errors, calls = [], []
        running = [True]
        def inspect(_state, **_kwargs):
            return self.container(running[0])
        def command(argv, **_kwargs):
            self.assert_common_available()
            calls.append(argv)
            self.assertEqual(argv, ['docker', 'stop', '--time', '30', CID])
            entered.set()
            if not release.wait(3):
                raise AssertionError('finite fake stop deadline')
            running[0] = False
            return subprocess.CompletedProcess(argv, 0, '', '')
        def worker():
            try:
                with self.runtime.operation('stop'):
                    self.runtime.settle_native(copy.deepcopy(self.runtime.expected_state))
            except BaseException as error:
                errors.append(error)
        with patch.object(self.runtime, 'inspect_owned', side_effect=inspect), patch.object(service, 'run', side_effect=command):
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(2), errors)
                self.assert_common_available()
                during = self.runtime.state()
                self.assertEqual(during['container']['id'], CID)
                self.assertEqual(during['native_actions']['stop'], 'dispatched')
            finally:
                release.set()
                thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.runtime.state()['native_actions']['stop'], 'observed_stopped')

    def test_stop_command_success_does_not_fabricate_settlement(self):
        self.anchor.atomic_json('state.json', self.owned_state())
        with self.runtime.operation('stop'):
            state = copy.deepcopy(self.runtime.expected_state)
            with patch.object(self.runtime, 'inspect_owned', return_value=self.container()), \
                    patch.object(service, 'run', return_value=subprocess.CompletedProcess([], 0)) as command:
                with self.assertRaisesRegex(RuntimeError, 'owned_backend_not_settled'):
                    self.runtime.settle_native(state, remove=True)
                self.assertEqual(command.call_count, 1)
                self.assertEqual(self.runtime.state()['container']['id'], CID)
                self.assertEqual(self.runtime.state()['native_actions']['stop'], 'dispatched')
                with self.assertRaisesRegex(RuntimeError, 'image_native_action_uncertain'):
                    self.runtime.settle_native(state, remove=True)
                self.assertEqual(command.call_count, 1)

    def test_changed_native_generation_is_not_stopped(self):
        self.anchor.atomic_json('state.json', self.owned_state())
        with self.runtime.operation('stop'):
            for container in (self.container(pid=43), self.container(started='replacement')):
                with self.subTest(container=container), \
                        patch.object(self.runtime, 'inspect_owned', return_value=container), \
                        patch.object(service, 'run') as command:
                    with self.assertRaisesRegex(RuntimeError, 'image_native_generation_changed'):
                        self.runtime.settle_native(copy.deepcopy(self.runtime.expected_state))
                    command.assert_not_called()

    def test_uncertain_create_without_identity_never_becomes_absent(self):
        state = self.owned_state()
        state.update(container=None, native_actions={'create': 'dispatched'})
        self.anchor.atomic_json('state.json', state)
        with self.runtime.operation('stop'), patch.object(self.runtime, 'inspect_owned', return_value=None), \
                patch.object(service, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'image_native_action_uncertain'):
                self.runtime.settle_native(copy.deepcopy(self.runtime.expected_state), remove=True)
            command.assert_not_called()
            self.assertEqual(self.runtime.state()['native_actions']['create'], 'dispatched')

    def test_cancellation_retains_uncertain_action_for_next_owner(self):
        argv = ['docker', 'start', CID]
        with patch.object(service, 'run', side_effect=KeyboardInterrupt) as command:
            with self.assertRaises(KeyboardInterrupt):
                with self.runtime.operation('start'):
                    state = copy.deepcopy(self.runtime.expected_state)
                    self.runtime.dispatch(state, 'start', argv)
            self.assertEqual(self.runtime.record('operation.json')['status'], 'failed')
            self.assertEqual(self.runtime.state()['native_actions']['start'], 'dispatched')
            with self.runtime.operation('start'):
                with self.assertRaisesRegex(RuntimeError, 'image_native_action_uncertain'):
                    self.runtime.dispatch(copy.deepcopy(self.runtime.expected_state), 'start', argv)
            self.assertEqual(command.call_count, 1)

    def test_removal_publishes_absence_only_after_exact_native_disappears(self):
        self.anchor.atomic_json('state.json', self.owned_state())
        removed = [False]
        def inspect(_state, **_kwargs):
            return None if removed[0] else self.container(False)
        def command(argv, **_kwargs):
            self.assert_common_available()
            self.assertEqual(argv, ['docker', 'rm', CID])
            self.assertEqual(self.runtime.state()['container']['id'], CID)
            removed[0] = True
            return subprocess.CompletedProcess(argv, 0)
        with self.runtime.operation('stop'), \
                patch.object(self.runtime, 'inspect_owned', side_effect=inspect), \
                patch.object(self.runtime, 'cleanup_tmp', return_value={'exists': False}), \
                patch.object(service, 'run', side_effect=command) as native:
            self.runtime.settle_native(copy.deepcopy(self.runtime.expected_state), remove=True)
            state = self.runtime.state()
            self.assertIsNone(state['container'])
            self.assertEqual(state['phase'], 'stopped')
            self.assertNotIn('native_actions', state)
            self.assertEqual(state['last_native_actions']['stop'], 'observed_stopped')
            native.assert_called_once()

    def test_real_hardware_producer_fresh_positive_unknown_stale_and_boot_changed(self):
        from lifecycle.hardware_policy import HardwarePolicy, STATE_SUFFIX
        from lifecycle.runtime_io import LifecycleError
        from control.hardware_latch import HardwareLatch
        runtime = self.runtime
        runtime.boot = BOOT
        runtime.require_hardware = service.Runtime.require_hardware.__get__(runtime)
        runtime.probe_hardware = service.Runtime.probe_hardware.__get__(runtime)
        self.anchor.mkdir('llm-manager', mode=0o700)
        wall = 1790668800.0
        def stamp(age):
            return datetime.datetime.fromtimestamp(wall - age, datetime.timezone.utc).isoformat()
        empty = {'schema_version': 1, 'targets': {}}
        positive = {'schema_version': 1, 'targets': {service.GPU_UUID: {
            'boot_id': BOOT, 'hardware_latched': True, 'reason': 'hardware_fault',
            'hardware_fault_code': 'gpu_fallen_off_bus',
            'evidence': [{'observed_at': stamp(0), 'observation_id': 'positive-proof'}]}}}
        cases = [('fresh', empty, 0, service.GPU_UUID, False, None),
                 ('last_valid', empty, 15, service.GPU_UUID, False, None),
                 ('stale', empty, 15.001, service.GPU_UUID, False, 'hardware_validation_stale'),
                 ('future', empty, -1, service.GPU_UUID, False, 'hardware_validation_stale'),
                 ('unknown', empty, 0, '', False, 'hardware_target_unknown'),
                 ('wrong_target', empty, 0, 'GPU-foreign', False, 'hardware_target_unknown'),
                 ('changed_boot', empty, 0, service.GPU_UUID, True, 'image_boot_changed'),
                 ('positive', positive, 0, service.GPU_UUID, False, 'hardware_fault')]
        for name, value, age, output, boot_change, error in cases:
            with self.subTest(proof=name):
                self.boot = BOOT
                HardwareLatch(value)
                self.anchor.atomic_json(STATE_SUFFIX, value)
                def command(argv, **kwargs):
                    self.assert_common_available()
                    self.assertEqual(argv, ['/usr/bin/nvidia-smi', '--id=' + service.GPU_UUID,
                                            '--query-gpu=uuid', '--format=csv,noheader,nounits'])
                    self.assertEqual(kwargs['timeout'], 2)
                    if boot_change:
                        self.boot = '99999999-2222-3333-4444-555555555555'
                    return subprocess.CompletedProcess(argv, 0, output, '')
                def policy(store, **kwargs):
                    return HardwarePolicy(store, system_root=self.root, trusted_uid=os.geteuid(),
                                          boot=lambda: {'boot_id': self.boot, 'uptime_seconds': 300},
                                          wall=lambda: wall, **kwargs)
                with patch.object(service, 'HardwarePolicy', side_effect=policy), \
                        patch.object(service, 'now', return_value=stamp(age)), \
                        patch.object(service, 'run', side_effect=command) as native:
                    if error:
                        with self.assertRaisesRegex((RuntimeError, LifecycleError), error):
                            with runtime.critical(hardware=True):
                                self.fail('invalid hardware proof entered mutation section')
                        self.assertEqual(self.anchor.read_json(STATE_SUFFIX), value)
                    else:
                        with runtime.critical(hardware=True):
                            pass
                        saved = self.anchor.read_json(STATE_SUFFIX)
                        self.assertEqual(saved['validated'][service.GPU_UUID]['observed_at'], stamp(age))
                    native.assert_called_once()
        self.boot = BOOT

    def test_missing_daemon_never_becomes_stopped_or_absent(self):
        self.anchor.atomic_json('state.json', self.owned_state())
        self.runtime.inspect_owned = service.Runtime.inspect_owned.__get__(self.runtime)
        calls = []
        def command(argv, **kwargs):
            self.assert_common_available()
            calls.append(argv)
            if argv[:2] == ['docker', 'inspect']:
                return subprocess.CompletedProcess(argv, 1, '', 'synthetic daemon unavailable')
            self.assertEqual(argv[:3], ['docker', 'container', 'ls'])
            raise RuntimeError('owned_command_failed')
        with patch.object(service, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'owned_command_failed'):
                self.runtime.reset_owned()
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.runtime.state()['container']['id'], CID)
        self.assertNotEqual(self.runtime.state()['phase'], 'stopped')
        self.assertNotIn('last_native_actions', self.runtime.state())

    def exercise_full_start(self, outcome):
        runtime = self.runtime
        invocation = 'c' * 32
        runtime.systemd_identity = Mock(return_value=invocation)
        runtime.check_network = Mock()
        runtime.check_ports = Mock()
        runtime.require_ada_idle = Mock()
        runtime.host_headroom = Mock(return_value={'MemTotal': 1000, 'MemAvailable': 900})
        runtime.current_device = Mock(return_value={'uuid': service.GPU_UUID,
            'total_bytes': 49 * 1024**3, 'free_bytes': 45 * 1024**3})
        runtime.make_work = Mock()
        runtime.create_argv = Mock(return_value=['docker', 'create', 'fixture'])
        runtime.tmp_snapshot = Mock(return_value={'entries': []})
        runtime.verify_resident = Mock(return_value=self.retained_residency())
        self.anchor.mkdir('receipts', mode=0o700)
        physical = {'created': False, 'running': False, 'pid': 42,
                    'started': '2026-09-29T08:00:00Z'}
        calls, observed_phases = [], []
        def inspect(state, **_kwargs):
            self.assert_common_available()
            if not physical['created']:
                return None
            self.assertEqual(state['container']['id'], CID)
            return self.container(physical['running'],
                pid=physical['pid'] if physical['running'] else 0, started=physical['started'])
        runtime.inspect_owned = Mock(side_effect=inspect)
        health_calls = [0]
        def health():
            self.assert_common_available()
            health_calls[0] += 1
            observed_phases.append(runtime.state()['phase'])
            return health_calls[0] >= 2
        runtime.native_health = Mock(side_effect=health)
        def native(argv, **_kwargs):
            self.assert_common_available()
            calls.append(argv)
            if argv[:2] == ['docker', 'create']:
                physical['created'] = True
                return subprocess.CompletedProcess(argv, 0, CID, '')
            if argv[:2] == ['docker', 'start']:
                self.assertEqual(argv[-1], CID)
                physical['running'] = True
                return subprocess.CompletedProcess(argv, 0, '', '')
            if argv[:2] == ['docker', 'exec']:
                self.assertEqual(argv[2], CID)
                self.assertEqual(runtime.state()['phase'], 'warming')
                self.assertEqual(runtime.state()['native_actions']['warm'], 'dispatched')
                if outcome == 'source_changed':
                    self.source_valid = False
                elif outcome == 'native_changed':
                    physical.update(pid=43, started='replacement-started-at')
                return subprocess.CompletedProcess(argv, 0,
                    json.dumps({'status': 'fail' if outcome == 'warm_error' else 'pass'}), '')
            self.assertEqual(argv, ['docker', 'stop', '--time', '30', CID])
            self.assertEqual(outcome, 'warm_error', 'changed ownership must refuse cleanup')
            physical['running'] = False
            return subprocess.CompletedProcess(argv, 0, '', '')
        sampler = Mock()
        sampler.poll.return_value = None
        sampler.wait.return_value = 0
        def telemetry(_argv, **kwargs):
            self.assert_common_available()
            sample = {'sampled_min_free_bytes': 10 * 1024**3,
                      'host': {'meminfo_bytes': {'status': 'ok', 'value': {'values': {
                                'MemTotal': 1000, 'MemAvailable': 900}}},
                               'cgroup_bytes': {'memory.swap.current': {'status': 'ok', 'value': 0}}}}
            os.write(kwargs['pass_fds'][0], (json.dumps(sample) + '\n').encode())
            return sampler
        def sleep(_seconds):
            self.assert_common_available()
        with patch.dict(os.environ, {'INVOCATION_ID': invocation}), \
                patch.object(service, 'BASE', self.root), \
                patch.object(service, 'Runtime', return_value=runtime), \
                patch.object(service.sys, 'argv', ['service.py', 'start']), \
                patch.object(service, 'run', side_effect=native), \
                patch.object(service.subprocess, 'Popen', side_effect=telemetry), \
                patch.object(service.time, 'sleep', side_effect=sleep), \
                contextlib.redirect_stdout(io.StringIO()):
            if outcome == 'success':
                service.main()
            else:
                expected = {'warm_error': 'deterministic_warm_failed',
                            'source_changed': 'runtime_source_changed',
                            'native_changed': 'image_native_generation_changed'}[outcome]
                with self.assertRaisesRegex(RuntimeError, expected):
                    service.main()
        state = runtime.state()
        self.assertEqual(health_calls[0], 2)
        self.assertEqual(observed_phases, ['loading', 'loading'])
        self.assertEqual([argv[1] for argv in calls[:3]], ['create', 'start', 'exec'])
        if outcome == 'success':
            self.assertTrue(state['warm'])
            self.assertEqual(state['phase'], 'warm')
            self.assertEqual(state['container']['id'], CID)
            self.assertEqual(runtime.record('operation.json')['status'], 'complete')
        else:
            self.assertIsNot(state.get('warm'), True)
            self.assertNotEqual(state['phase'], 'warm')
            if outcome == 'warm_error':
                self.assertFalse(physical['running'])
                self.assertTrue(state['cleanup']['backend_stopped'])
                self.assertEqual(state['native_actions']['stop'], 'observed_stopped')
                self.assertEqual(len(calls), 4)
            else:
                self.assertTrue(physical['running'])
                self.assertEqual(len(calls), 3)
        self.assertTrue(self.lease_durations)
        # Fixture measurement only. No wall-clock performance gate or live claim.
        self.full_start_max_lease_seconds = max(self.lease_durations)

    def test_actual_main_start_load_warm_and_ready_publication(self):
        self.exercise_full_start('success')

    def test_actual_start_warm_error_settles_exact_native_outside_common_lease(self):
        self.exercise_full_start('warm_error')

    def test_actual_start_source_changed_during_warm_refuses_ready_and_cleanup(self):
        self.exercise_full_start('source_changed')

    def test_actual_start_native_changed_during_warm_refuses_ready_and_cleanup(self):
        self.exercise_full_start('native_changed')

    def test_main_start_does_not_hold_common_lease_over_native_start(self):
        """Regression: exact baseline main() holds the real lease and fails here."""
        runtime = Mock()
        runtime.operation.side_effect = lambda _action: contextlib.nullcontext()
        runtime.start.side_effect = self.assert_common_available
        with patch.object(service, 'Runtime', return_value=runtime), \
                patch.object(service.sys, 'argv', ['service.py', 'start']):
            service.main()
        runtime.start.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
