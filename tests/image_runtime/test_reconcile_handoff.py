"""Exact H032 API-owned handoff; real protected files/flocks, fake native I/O."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_recovery_admission as fixture_module

service = fixture_module.service
Runtime = fixture_module.Runtime
CID = 'd66478c5449611e521af17e918b8929c0d7d2d0a6526788d9ed55386b57cd539'
OLD_INVOCATION = '6e8aa276397a451cb5a480b2c0aa90ea'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


class ReconciliationHandoff(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.RecoveryProtocol(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.wall_time = service.H032_ACTIVATION_DEADLINE - 60
        self.stack.enter_context(patch.object(service.time, 'time', side_effect=lambda: self.wall_time))
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(
            prefix='.image-handoff-', dir=fixture_module.ROOT)))
        info = self.root.stat()
        identity = {'path': str(self.root), 'mount': str(self.root), 'uuid': 'fixture',
                    'fstype': 'ext4', 'device': f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'}
        snapshot = {'schema_version': 1, 'data': identity, 'models': identity,
                    'roots': {'services': str(self.root)}}
        self.anchor = self.stack.enter_context(service.storage_io.AnchoredRoot(
            str(self.root), lambda: copy.deepcopy(snapshot), uid=os.geteuid()))
        self.anchor.mkdir('source')
        self.anchor.mkdir(service.H032_ROOT + 'archive')
        self.old_source, self.new_source = b'# pinned old owner fixture\n', b'# corrected owner fixture\n'
        self.stack.enter_context(patch.object(service, 'H032_OLD_SERVICE', digest(self.old_source)))
        self.config = {'owner': service.OWNER,
                       'source_sha256': {'service.py': digest(self.new_source)}, 'unchanged': ['policy']}
        self.old_config = copy.deepcopy(self.config)
        self.old_config['source_sha256']['service.py'] = digest(self.old_source)
        self.native = {'id': CID, 'pid': 1661054,
                       'cgroup': '/system.slice/docker-' + CID + '.scope'}
        self.pid_present = self.cgroup_present = False
        self.owners_present = set()
        self.unit = {'MainPID': '0', 'ControlPID': '0', 'ActiveState': 'failed',
                     'ControlGroup': '', 'InvocationID': OLD_INVOCATION, 'Job': ''}
        self.stack.enter_context(patch.object(service, 'run', side_effect=self.command))
        original_stat = Path.stat
        def stat(path, *args, **kwargs):
            present = {f'/proc/{self.native["pid"]}': self.pid_present,
                       '/sys/fs/cgroup' + self.native['cgroup']: self.cgroup_present}
            present.update({f'/proc/{pid}': pid in self.owners_present for pid in (9999999, 1656742, 1655508)})
            if str(path) in present:
                if present[str(path)]:
                    return object()
                raise FileNotFoundError()
            return original_stat(path, *args, **kwargs)
        self.stack.enter_context(patch.object(Path, 'stat', stat))
        self.fixture.native = None
        self.fixture.invocation = OLD_INVOCATION
        self.original_make = self.fixture.make_runtime
        self.stack.enter_context(patch.object(self.fixture, 'make_runtime', side_effect=self.make_runtime))
        self.stack.enter_context(patch.object(service, 'Runtime', side_effect=self.make_runtime))
        self.prepare()

    def command(self, argv, **kwargs):
        result = self.fixture.command(argv, **kwargs)
        if argv[:2] == ['systemctl', 'show'] and argv[-1].startswith('MainPID,'):
            return subprocess.CompletedProcess(argv, 0,
                       ''.join(f'{key}={value}\n' for key, value in self.unit.items()), '')
        return result

    def make_runtime(self):
        runtime = self.original_make()
        runtime.config = copy.deepcopy(self.config)
        runtime.anchor = lambda: contextlib.nullcontext(self.anchor)
        @contextlib.contextmanager
        def singleton(name):
            with Runtime.singleton(runtime, name) as stream:
                self.fixture.locks.add(name)
                try:
                    yield stream
                finally:
                    self.fixture.locks.remove(name)
        runtime.singleton = singleton
        return runtime

    def put_raw(self, name, raw):
        with self.anchor.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC) as stream:
            stream.write(raw)
            stream.fsync()

    def put(self, name, value):
        self.anchor.atomic_json(name, value)

    def raw(self, name):
        return service._reconciliation_raw(self.make_runtime(), name)

    def get(self, name):
        return self.anchor.read_json(name)

    def prepare(self):
        # Retained abandoned record shape and exact historical tokens. The
        # helper's cleanup records remain distinct; original failures stay raw.
        old_state = {'schema_version': 1, 'owner': service.OWNER, 'phase': 'warm',
                     'warm': True, 'run_id': OLD_INVOCATION,
                     'container': {'id': CID, 'image_id': 'sha256:' + '5' * 64},
                     'native_actions': {'create': 'received', 'start': 'received', 'warm': 'dispatched'},
                     'failure_code': 'image_operation_changed'}
        old_operation = {'token': '868d9b48784b44f4b702b52c05655a65', 'pid': 1656742,
                         'boot': fixture_module.BOOT, 'action': 'start', 'status': 'active',
                         'gpu_uuid': service.GPU_UUID,
                         'config_sha256': digest(json.dumps(self.old_config, sort_keys=True, separators=(',', ':')).encode()),
                         'invocation_id': OLD_INVOCATION, 'recovery': '83be8882e6374f3fbc3918de6bc5107c'}
        old_recovery = {'token': '83be8882e6374f3fbc3918de6bc5107c', 'pid': 1655508,
                        'boot': fixture_module.BOOT, 'status': 'active', 'phase': 'settle',
                        'gpu_uuid': service.GPU_UUID, 'config_sha256': old_operation['config_sha256'],
                        'process': {'pid': 1655508, 'start_ticks': 3990457},
                        'prior_invocation': '', 'child_start': OLD_INVOCATION}
        originals = {'config.json': encoded(self.old_config), 'service.py': self.old_source,
                     'state.json': encoded(old_state), 'operation.json': encoded(old_operation),
                     'recovery.json': encoded(old_recovery)}
        self.originals = originals
        for name, raw in originals.items():
            self.put_raw(service.H032_ROOT + 'archive/' + name, raw)
        self.put(service.H032_ROOT + 'archive-manifest.json',
                 {'schema_version': 1, 'case': service.H032_CASE, 'boot': fixture_module.BOOT,
                  'files': {name: digest(raw) for name, raw in originals.items()}})
        self.put('config.json', self.config)
        self.put_raw('source/service.py', self.new_source)
        plan = {'schema_version': 1, 'case': service.H032_CASE, 'boot': fixture_module.BOOT,
                'gpu_uuid': service.GPU_UUID, 'native': self.native,
                'old_config_sha256': digest(originals['config.json']),
                'new_config_sha256': digest(self.raw('config.json')),
                'old_service_sha256': digest(self.old_source), 'new_service_sha256': digest(self.new_source),
                'old_raw_sha256': {name: digest(raw) for name, raw in originals.items()},
                'activation_deadline_unix': 1790685900,
                'helper_sha256': 'a' * 64}
        self.put(service.H032_ROOT + 'plan.json', plan)
        reference = {'schema_version': 1, 'case': service.H032_CASE, 'boot': fixture_module.BOOT,
                     'archive_sha256': digest(self.raw(service.H032_ROOT + 'archive-manifest.json')),
                     'plan_sha256': digest(self.raw(service.H032_ROOT + 'plan.json'))}
        self.put(service.H032_ROOT + 'consumed.json', reference)
        self.put(service.H032_ROOT + 'settlement.json', dict(reference,
                 gpu_uuid=service.GPU_UUID, native=self.native, physically_absent=True))
        self.put('state.json', {'schema_version': 1, 'owner': service.OWNER, 'phase': 'stopped',
                 'warm': False, 'run_id': OLD_INVOCATION, 'container': None,
                 'last_native_actions': old_state['native_actions'],
                 'failure_code': 'image_operation_changed'})
        self.put('operation.json', {'token': 'cleanup-stop', 'status': 'complete', 'action': 'stop',
                                   'recovery': 'cleanup-parent'})
        self.put('recovery.json', {'token': 'cleanup-parent', 'boot': fixture_module.BOOT,
                 'pid': 9999999, 'process': {'pid': 9999999, 'start_ticks': 100},
                 'gpu_uuid': service.GPU_UUID, 'config_sha256': self.make_runtime().config_digest(),
                 'status': 'active', 'phase': 'settled_awaiting_reviewed_activation',
                 'prior_invocation': '', 'child_start': OLD_INVOCATION,
                 'reconciliation': {k: reference[k] for k in ('case', 'archive_sha256', 'plan_sha256')}})
        handoff = dict(reference, gpu_uuid=service.GPU_UUID, native=self.native,
                       settlement_sha256=digest(self.raw(service.H032_ROOT + 'settlement.json')),
                       cleanup_consumption_sha256=digest(self.raw(service.H032_ROOT + 'consumed.json')),
                       raw_sha256={name: digest(self.raw(name)) for name in
                                   ('state.json', 'operation.json', 'recovery.json', 'config.json', 'source/service.py')})
        self.put('h032-image-handoff.json', handoff)

    def recover(self):
        service.recover()

    def test_exact_settlement_enters_ordinary_recovery_once_and_preserves_history(self):
        self.recover()
        self.assertEqual(self.get('recovery.json')['status'], 'complete')
        self.assertTrue(self.get('state.json')['warm'])
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.fixture.commands), 1)
        self.assertFalse(any(c[:2] in (['docker', 'stop'], ['docker', 'rm']) for c in self.fixture.commands))
        for name, raw in self.originals.items():
            self.assertEqual(self.raw(service.H032_ROOT + 'archive/' + name), raw)
        receipt = self.get('h032-image-handoff-consumed.json')
        self.assertEqual(receipt['recovery_token'], self.get('recovery.json')['token'])
        gpu_commands = [c for c in self.fixture.commands if c[0] == 'nvidia-smi']
        self.assertEqual(len(gpu_commands), 1)
        self.assertIn('--id=' + service.GPU_UUID, gpu_commands[0])

    def test_wrong_raw_identity_source_or_successor_refuses_before_consumption(self):
        for name in ('state.json', 'operation.json', 'recovery.json', 'config.json', 'source/service.py'):
            with self.subTest(name=name):
                original = self.raw(name)
                self.put_raw(name, original + b' ')
                with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                    self.recover()
                self.put_raw(name, original)
                self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))
                self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in self.fixture.commands))

    def test_wrong_boot_or_owner_is_not_adopted(self):
        original = self.get('recovery.json')
        for updates in ({'boot': 'foreign'}, {'phase': 'settle'}, {'reconciliation': {'case': 'other'}}):
            with self.subTest(updates=updates):
                self.put('recovery.json', dict(original, **updates))
                with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                    self.recover()
        self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in self.fixture.commands))

    def test_later_native_pid_or_cgroup_blocks_handoff(self):
        for field in ('pid_present', 'cgroup_present'):
            with self.subTest(field=field):
                setattr(self, field, True)
                with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                    self.recover()
                setattr(self, field, False)
        self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))

    def test_archive_failure_blocks_all_native_side_effects(self):
        self.put_raw(service.H032_ROOT + 'archive/state.json', b'changed')
        with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
            self.recover()
        self.assertFalse(any(c[0] == 'docker' or c[:2] == ['systemctl', 'restart']
                             for c in self.fixture.commands))

    def test_consumed_before_record_replacement_crash_stays_closed_and_never_replays(self):
        old_recovery = self.raw('recovery.json')
        original_atomic = self.anchor.atomic_json
        def fail(name, value):
            if name == 'recovery.json' and value.get('phase') == 'reset':
                self.assertIsNotNone(self.anchor.stat('h032-image-handoff-consumed.json'))
                raise RuntimeError('lost_publication_acknowledgement')
            return original_atomic(name, value)
        with patch.object(self.anchor, 'atomic_json', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'lost_publication_acknowledgement'):
                self.recover()
        self.assertEqual(self.raw('recovery.json'), old_recovery)
        with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_consumed'):
            self.recover()
        self.assertFalse(any(c[:2] == ['systemctl', 'restart'] for c in self.fixture.commands))

    def test_contending_recovery_cannot_enter_while_handoff_descriptor_is_held(self):
        runtime = self.make_runtime()
        before = self.raw('recovery.json')
        with runtime.singleton('recovery.lock'):
            with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'):
                self.recover()
        self.assertEqual(self.raw('recovery.json'), before)
        self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))

    def test_source_change_after_slow_proof_refuses_before_consumption(self):
        original = service._h032_handoff
        def changed(runtime, prior):
            proof = original(runtime, prior)
            self.put_raw('source/service.py', b'foreign successor')
            return proof
        with patch.object(service, '_h032_handoff', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                self.recover()
        self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))

    def test_expired_case_never_consumes_or_starts(self):
        self.wall_time = service.H032_ACTIVATION_DEADLINE
        with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
            self.recover()
        self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))
        self.assertFalse(any(c[0] == 'docker' for c in self.fixture.commands))

    def test_expiry_after_slow_proof_keeps_active_predecessor(self):
        original = service._h032_handoff
        before = self.raw('recovery.json')
        def expires(runtime, prior):
            proof = original(runtime, prior)
            self.wall_time = service.H032_ACTIVATION_DEADLINE
            return proof
        with patch.object(service, '_h032_handoff', side_effect=expires):
            with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                self.recover()
        self.assertEqual(self.raw('recovery.json'), before)
        self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))

    def test_start_cutoff_does_not_expire_already_admitted_ordinary_recovery(self):
        original = service._consume_h032_handoff
        def admitted(*args):
            result = original(*args)
            self.wall_time = service.H032_ACTIVATION_DEADLINE + 1
            return result
        with patch.object(service, '_consume_h032_handoff', side_effect=admitted):
            self.recover()
        self.assertEqual(self.get('recovery.json')['status'], 'complete')
        self.assertTrue(self.get('state.json')['warm'])
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.fixture.commands), 1)

    def test_successor_named_native_or_daemon_failure_is_never_absence(self):
        original = self.command
        for output, error in ((json.dumps({'ID': 'f' * 64, 'Names': service.NAME}), None),
                              ('', RuntimeError('daemon_unavailable'))):
            with self.subTest(output=output, error=error):
                def command(argv, **kwargs):
                    if argv[:3] == ['docker', 'container', 'ls']:
                        if error:
                            raise error
                        return subprocess.CompletedProcess(argv, 0, output, '')
                    return original(argv, **kwargs)
                with patch.object(service, 'run', side_effect=command):
                    with self.assertRaisesRegex(RuntimeError, 'image_native_absence_unproven|daemon_unavailable'):
                        self.recover()
                self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))

    def test_uncertain_corrected_start_stays_owned_and_never_reconsumes_handoff(self):
        self.fixture.start_child = False
        self.fixture.restart_error = subprocess.TimeoutExpired('fixture-restart', 1)
        with self.assertRaisesRegex(RuntimeError, 'image_native_action_uncertain'):
            self.recover()
        current = self.get('recovery.json')
        self.assertEqual(current['status'], 'active')
        self.assertIsNone(current['child_start'])
        self.assertIsNotNone(self.anchor.stat('h032-image-handoff-consumed.json'))
        with self.assertRaisesRegex(RuntimeError, 'image_operation_unresolved'):
            self.recover()
        self.assertEqual(self.get('recovery.json'), current)
        self.assertEqual(sum(c[:2] == ['systemctl', 'restart'] for c in self.fixture.commands), 1)

    def test_no_inactive_gap_or_competing_admission_during_consumption_and_replacement(self):
        original = self.anchor.atomic_json
        checked = []
        def publication(name, value):
            if name == 'recovery.json' and value.get('phase') == 'reset':
                self.assertEqual(self.get(name)['status'], 'active')
                self.assertIsNotNone(self.anchor.stat('h032-image-handoff-consumed.json'))
                with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'):
                    self.recover()
                checked.append('before')
            result = original(name, value)
            if name == 'recovery.json' and value.get('phase') == 'reset':
                self.assertEqual(self.get(name)['status'], 'active')
                with self.assertRaisesRegex(RuntimeError, 'image_operation_busy'):
                    self.recover()
                checked.append('after')
            return result
        with patch.object(self.anchor, 'atomic_json', side_effect=publication):
            self.recover()
        self.assertEqual(checked, ['before', 'after'])

    def test_live_reused_cleanup_or_original_parent_is_not_adopted(self):
        for pid in (9999999, 1656742, 1655508):
            with self.subTest(pid=pid):
                self.owners_present.add(pid)
                with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                    self.recover()
                self.owners_present.clear()
                self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))

    def test_unit_job_later_invocation_or_owner_refuses_before_consumption(self):
        original = self.unit.copy()
        for change in ({'Job': '1234'}, {'InvocationID': 'f' * 32}, {'MainPID': '1234'},
                       {'ControlPID': '1234'}, {'ActiveState': 'activating'}, {'ControlGroup': '/later'}):
            with self.subTest(change=change):
                self.unit = dict(original, **change)
                with self.assertRaisesRegex(RuntimeError, 'image_reconciliation_refused'):
                    self.recover()
                self.assertIsNone(self.anchor.stat('h032-image-handoff-consumed.json', missing_ok=True))


if __name__ == '__main__':
    unittest.main()
