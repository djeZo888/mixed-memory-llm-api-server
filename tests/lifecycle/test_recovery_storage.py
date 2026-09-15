"""Actual Manager emergency recovery with real volatile journal and fake Docker.

Only worker temporary files are used. The post-write writer is an injected API
contract, not the I1b AnchoredRoot implementation or mount-loss race proof.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.lifecycle_lease import acquire_lease, transition_in_progress
from lifecycle.manager import Manager, LABEL, atomic_json, empty_state
from lifecycle.runtime_io import LifecycleError
from lifecycle.storage_binding import BindingError
from install.prerequisites import PrerequisiteError
from fixture_storage import HistoricalBinding
import test_manager as retained


class RecoveryWithoutStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.configs = self.root / 'configs'
        shutil.copytree(ROOT / 'configs', self.configs)
        self.instance = retained.make_instance(self.root)
        self.docker = retained.FakeDocker()
        clock = retained.FakeClock()
        starter = retained.FixtureManager(
            self.configs, self.instance, docker=self.docker, test_paths=True,
            probe_fn=lambda *a, **kw: 'ready',
            run_fn=lambda *a, **kw: self.fail('unexpected worker subprocess'),
            monotonic_fn=clock.monotonic, sleep_fn=clock.sleep)
        with patch('lifecycle.manager.validate_key_metadata'):
            starter.dispatch('select', retained.PROOF, boot_policy='resume')
            self.started = starter.dispatch('start')
        self.identity = copy.deepcopy(self.started['container'])
        self.journal = self.root / 'run/llmctl/recovery.json'
        self.assertTrue(self.started['state_persisted'])
        self.assertEqual(self.started['observed'], 'ready')
        # Represent unavailable registered volumes, protected registry, profiles,
        # and primary state by removing all their temporary fixture paths.
        for name in ('data', 'models', 'etc/local-ai-server'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        registry = self.root / 'etc/local-ai-server/storage.json'
        registry.write_text(json.dumps({'fixture': True}))
        for path in (self.root / 'data', self.root / 'models', self.root / 'etc',
                     self.root / 'state', self.configs):
            shutil.rmtree(path)
        unrelated = copy.deepcopy(self.docker.records[0])
        unrelated.update(Id='f' * 64, Name='/unrelated-fixture')
        unrelated['Config']['Labels'] = {'external-owner': 'fixture'}
        self.docker.records.append(unrelated)
        self.unrelated = copy.deepcopy(unrelated)
        self.docker.calls.clear()
        self.manager = Manager(
            self.configs, {'schema_version': 1, 'id': self.instance['id']},
            recovery_only=True, binding=None, test_paths=True,
            lease_system_root=self.root, docker=self.docker,
            run_fn=lambda *a, **kw: self.fail('recovery attempted subprocess'),
            probe_fn=lambda *a, **kw: self.fail('recovery attempted API probe'))

    def lease(self):
        return acquire_lease(system_root=self.root, trusted_uid=os.geteuid())

    def no_fallback(self):
        self.assertEqual({str(p.relative_to(self.root)) for p in self.root.rglob('*')},
                         {'run', 'run/llmctl', 'run/llmctl/lifecycle.lock', 'run/llmctl/recovery.json'})
        self.assertIsNone(self.manager.state_file)
        self.assertIsNone(self.manager.binding)
        self.assertIsNone(self.manager.storage_io)

    def stop_and_assert(self, action):
        with self.lease() as lease, \
                patch.object(self.manager, 'deployment', side_effect=AssertionError('recovery read deployment')), \
                patch('lifecycle.manager.validate_key_metadata', side_effect=AssertionError('recovery read key')):
            result = self.manager.dispatch(action, lease=lease)
            lease.validate()
            self.assertTrue(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
        self.assertFalse(transition_in_progress(system_root=self.root, trusted_uid=os.geteuid()))
        self.assertEqual([c for c in self.docker.calls if c[0] == 'stop'], [('stop', self.identity['id'])])
        self.assertFalse(any(c[0] in {'create', 'start_enter', 'remove', 'run', 'inventory'} for c in self.docker.calls))
        self.assertEqual(next(c for c in self.docker.records if c['Id'] == self.unrelated['Id']), self.unrelated)
        self.assertEqual(result['container'], self.identity)
        self.assertFalse(result['container_running'])
        self.assertFalse(result['state_persisted'])
        self.assertEqual(result['observed'], 'stopped')
        self.assertEqual(result['warning'], 'restore_registered_storage_and_repeat_stop_before_reboot')
        self.assertEqual(result['desired'], 'running' if action == 'boot-stop' else 'stopped')
        self.assertEqual(result['boot_policy'], 'resume')
        saved = json.loads(self.journal.read_text())
        self.assertFalse(saved['state_persisted'])
        self.assertEqual(saved['desired'], result['desired'])
        self.assertEqual(saved['container'], self.identity)
        self.no_fallback()

    def test_stop_without_registry_data_models_config_or_key(self):
        records = copy.deepcopy(self.docker.records)
        # Existing profile names are identity labels only. No final context,
        # image or acceptance claim, and neither model's profiles are read.
        for deployment in (retained.PROOF, 'qwen38-27b-128k'):
            with self.subTest(deployment=deployment):
                self.identity['deployment'] = deployment
                state = copy.deepcopy(self.started)
                state.update(selected=deployment, container=copy.deepcopy(self.identity))
                self.docker.records = copy.deepcopy(records)
                self.docker.records[0]['Config']['Labels'][LABEL + 'deployment'] = deployment
                self.docker.calls.clear()
                atomic_json(self.journal, state, system_root=self.root, trusted_uid=os.geteuid())
                self.stop_and_assert('stop')

    def test_recover_stop_without_registry_data_models_config_or_key(self):
        self.stop_and_assert('recover-stop')

    def test_boot_stop_preserves_resume_intent_without_claiming_durability(self):
        self.stop_and_assert('boot-stop')

    def test_stop_failure_records_running_identity_and_retry_recovers(self):
        self.docker.fail_stop = True
        with self.lease() as lease:
            with self.assertRaises(LifecycleError):
                self.manager.dispatch('stop', lease=lease)
            lease.validate()
            failed = json.loads(self.journal.read_text())
            self.assertEqual(failed['observed'], 'failed')
            self.assertEqual(failed['failure'], 'stop_failed_container_may_be_running')
            self.assertTrue(failed['container_running'])
            self.assertFalse(failed['state_persisted'])
            self.assertEqual(failed['desired'], 'stopped')
            self.assertEqual(failed['container'], self.identity)
            self.assertTrue(next(c for c in self.docker.records if c['Id'] == self.identity['id'])['State']['Running'])
            self.docker.fail_stop = False
            result = self.manager.dispatch('recover-stop', lease=lease)
            self.assertFalse(result['container_running'])
            self.assertFalse(result['state_persisted'])
            self.assertIsNone(result['failure'])
        self.no_fallback()

    def test_unrelated_or_raw_identity_never_targets_an_untrusted_container(self):
        original = json.loads(self.journal.read_text())
        for identity in [{'id': '--all'},
                         {'id': self.unrelated['Id'], 'name': self.unrelated['Name'].lstrip('/')}]:
            with self.subTest(identity=identity['id']), self.lease() as lease:
                journal = copy.deepcopy(original)
                journal['container'].update(identity)
                atomic_json(self.journal, journal, system_root=self.root, trusted_uid=os.geteuid())
                self.docker.calls.clear()
                with self.assertRaises(LifecycleError):
                    self.manager.dispatch('recover-stop', lease=lease)
                lease.validate()
                self.assertFalse(any(c[0] in {'stop', 'create', 'start_enter', 'remove'} for c in self.docker.calls))
                self.assertTrue(all(c['State']['Running'] for c in self.docker.records))
        self.no_fallback()

    def test_recovery_only_cannot_start_or_select_when_configuration_is_absent(self):
        for action in ('start', 'select', 'restart', 'boot-start'):
            with self.subTest(action=action), self.lease() as lease:
                with self.assertRaisesRegex(LifecycleError, 'recovery_stop_only'):
                    self.manager.dispatch(action, deployment_id=retained.PROOF, lease=lease)
        self.assertEqual(self.docker.calls, [])
        self.no_fallback()

    def test_missing_recovery_journal_refuses_without_fallback_or_docker_mutation(self):
        self.journal.unlink()
        with self.lease() as lease, self.assertRaises(LifecycleError):
            self.manager.dispatch('recover-stop', lease=lease)
        self.assertEqual(self.docker.calls, [])
        self.assertFalse(self.journal.exists())
        self.assertFalse((self.root / 'state').exists())
        self.assertFalse((self.root / 'data').exists())


class PostWriteFailureTests(unittest.TestCase):
    def test_false_journal_wins_over_same_timestamp_primary_after_failed_commit_check(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            data = root / 'registered-data'
            data.mkdir()
            binding = HistoricalBinding()
            binding.registry['data'].update(path=str(data), mount=str(data))
            binding.registry['models'].update(path=str(data / 'models'), mount=str(data))
            binding.registry['roots'] = {role: str(data) + path[len('/data'):]
                                         for role, path in binding.registry['roots'].items()}
            binding.identity = copy.deepcopy(binding.registry)
            available = [True]
            def verify(roles=('data', 'models')):
                if not available[0]:
                    raise BindingError('synthetic_mount_lost')
                return copy.deepcopy(binding.registry)
            binding.verify = verify
            events = []

            class AnchoredRoot:
                """Injected post-write failure; this does not implement safe anchoring."""
                def __init__(self, path, guard):
                    self.path, self.guard = Path(path), guard
                def __enter__(self):
                    self.guard()
                    return self
                def __exit__(self, *args):
                    return False
                def mkdir(self, relative, mode=0o700, parents=True):
                    (self.path / relative).mkdir(mode=mode, parents=parents, exist_ok=True)
                def atomic_json(self, relative, value):
                    events.append(('write', relative))
                    target = self.path / relative
                    target.write_text(json.dumps(value))
                    target.chmod(0o600)
                    available[0] = False
                def check(self):
                    events.append(('check',))
                    self.guard()

            instance = {'schema_version': 1, 'id': 'postwrite-fixture', 'storage_identity': binding.identity,
                        'paths': {'state': {'role': 'data', 'suffix': 'services/llm-manager/active'}}}
            manager = Manager(root / 'no-config', instance, binding=binding, test_paths=True,
                              lease_system_root=root, storage_io=SimpleNamespace(AnchoredRoot=AnchoredRoot))
            manager.state = {**empty_state(), 'selected': retained.PROOF}
            with acquire_lease(system_root=root, trusted_uid=os.geteuid()) as lease, \
                    patch('lifecycle.manager.time.time_ns', return_value=987654321):
                with self.assertRaisesRegex(LifecycleError, 'persistent_state_write_failed'):
                    manager.save()
                lease.validate()
            primary = json.loads(manager.state_file.read_text())
            journal = json.loads(manager.recovery_file.read_text())
            self.assertTrue(primary['state_persisted'])
            self.assertFalse(journal['state_persisted'])
            self.assertEqual(primary['updated_at'], journal['updated_at'])
            self.assertEqual(events, [('write', 'llm-manager/active/active.json'), ('check',)])
            available[0] = True  # Simulated restoration, not an actual remount.
            self.assertFalse(manager.read_state()['state_persisted'])
            self.assertEqual(manager.read_state()['updated_at'], 987654321)


class PackageAdmissionTests(unittest.TestCase):
    """Production dispatch with injected authoritative I1R admission API.

    This is interface/ordering evidence, not actual I1R policy/gate inspection.
    """
    lease = RecoveryWithoutStorageTests.lease

    def setUp(self):
        RecoveryWithoutStorageTests.setUp(self)
        self.data = self.root / 'registered-data'
        self.data.mkdir()
        binding = HistoricalBinding()
        binding.registry['data'].update(path=str(self.data), mount=str(self.data))
        binding.registry['models'].update(path=str(self.data / 'models'), mount=str(self.data))
        binding.registry['roots'] = {role: str(self.data) + path[len('/data'):]
                                     for role, path in binding.registry['roots'].items()}
        binding.identity = copy.deepcopy(binding.registry)
        self.admission = 'pending_marker'
        self.events = []
        outer = self

        class AnchoredRoot:
            """Tiny worker stand-in; no descriptor anchoring or mount race claim."""
            def __init__(self, path, guard):
                if path != str(outer.data / 'services'):
                    raise AssertionError('persistence anchor outside registered services')
                self.path, self.guard = Path(path), guard
                outer.events.append(('open', path))
            def __enter__(self):
                self.guard()
                return self
            def __exit__(self, *args):
                return False
            def check(self):
                outer.events.append(('check',))
                self.guard()
            def mkdir(self, relative, mode=0o700, parents=True):
                (self.path / relative).mkdir(mode=mode, parents=parents, exist_ok=True)
            def atomic_json(self, relative, value):
                outer.events.append(('write', relative))
                target = self.path / relative
                target.write_text(json.dumps(value))
                target.chmod(0o600)

        instance = {'schema_version': 1, 'id': self.instance['id'], 'storage_identity': binding.identity,
                    'paths': {'state': {'role': 'data', 'suffix': 'services/llm-manager/active'}}}
        self.manager = Manager(self.configs, instance, binding=binding, test_paths=True,
                               lease_system_root=self.root, docker=self.docker,
                               storage_io=SimpleNamespace(AnchoredRoot=AnchoredRoot),
                               run_fn=lambda *a, **kw: self.fail('admission attempted subprocess'))
        # The primary selects a different container. Unknown package admission
        # must choose the already trusted /run identity, never this stale primary.
        self.primary = copy.deepcopy(self.started)
        self.primary['container'].update(id=self.unrelated['Id'], name=self.unrelated['Name'].lstrip('/'))
        self.primary['updated_at'] = self.started['updated_at'] + 1
        self.manager.state_file.parent.mkdir(parents=True)
        self.manager.state_file.write_text(json.dumps(self.primary))
        self.manager.state_file.chmod(0o600)

        def assert_package_admission(data_dir, storage_guard, *, policy_path=None):
            self.events.append(('admit', data_dir, policy_path))
            self.assertEqual(data_dir, str(self.data))
            self.assertIsNone(policy_path)  # Never redirect the production policy path.
            self.assertTrue(callable(storage_guard))
            storage_guard()
            if self.admission == 'unknown':
                raise OSError('synthetic unknown admission state')
            if self.admission != 'clear':
                raise PrerequisiteError('synthetic pending package state',
                                        code='package_transaction_recovery_required')

        self.admission_patch = patch('install.prerequisites.assert_package_admission',
                                     side_effect=assert_package_admission, create=True)
        self.authoritative = self.admission_patch.start()
        self.addCleanup(self.admission_patch.stop)

    def test_clear_admission_uses_exact_readonly_authoritative_contract(self):
        self.admission = 'clear'
        self.manager.check_package_admission()
        self.assertEqual(self.events, [('admit', str(self.data), None)])
        self.authoritative.assert_called_once()
        self.assertEqual(self.docker.calls, [])
        self.assertFalse(any(event[0] == 'write' for event in self.events))

    def test_pending_or_unknown_marker_blocks_all_ordinary_mutations_before_state_read(self):
        original = copy.deepcopy(self.manager.instance)
        primary_bytes, journal_bytes = self.manager.state_file.read_bytes(), self.journal.read_bytes()
        for admission in ('pending_marker', 'pending_gate', 'orphan_inhibitor', 'unknown'):
            self.admission = admission
            for action in ('select', 'activate', 'start', 'restart', 'boot-start', 'deactivate'):
                with self.subTest(admission=admission, action=action), self.lease() as lease, \
                        patch.object(self.manager, 'read_state', side_effect=AssertionError('state read before package admission')) as read, \
                        patch.object(self.manager, 'deployment', side_effect=AssertionError('profile read before package admission')) as profile:
                    with self.assertRaisesRegex(LifecycleError, '^package_transaction_recovery_required$'):
                        self.manager.dispatch(action, deployment_id=retained.PROOF, lease=lease)
                    lease.validate()
                    read.assert_not_called()
                    profile.assert_not_called()
                self.assertEqual(self.docker.calls, [])
                self.assertFalse(any(event[0] == 'write' for event in self.events))
        self.assertEqual(self.manager.instance, original)
        self.assertEqual(self.manager.state_file.read_bytes(), primary_bytes)
        self.assertEqual(self.journal.read_bytes(), journal_bytes)

    def test_missing_authoritative_callable_or_module_fails_closed_before_state_read(self):
        cases = [patch('install.prerequisites.assert_package_admission', None, create=True),
                 patch('lifecycle.manager.importlib.import_module', side_effect=ImportError('synthetic missing I1R module'))]
        for index, missing in enumerate(cases):
            with self.subTest(case=index), missing, self.lease() as lease, \
                    patch.object(self.manager, 'read_state', side_effect=AssertionError('admission source absent')) as read:
                with self.assertRaisesRegex(LifecycleError, '^package_transaction_recovery_required$'):
                    self.manager.dispatch('deactivate', lease=lease)
                lease.validate()
                read.assert_not_called()
        self.assertEqual(self.docker.calls, [])
        self.assertFalse(any(event[0] == 'write' for event in self.events))

    def test_pending_or_unknown_admission_stop_uses_run_identity_instead_of_primary(self):
        originals = copy.deepcopy(self.docker.records)
        original_instance = copy.deepcopy(self.manager.instance)
        original_journal = json.loads(self.journal.read_text())
        for admission in ('pending_marker', 'pending_gate', 'orphan_inhibitor', 'unknown'):
            self.admission = admission
            for action in ('stop', 'recover-stop', 'boot-stop'):
                with self.subTest(admission=admission, action=action), self.lease() as lease:
                    self.docker.records = copy.deepcopy(originals)
                    self.docker.calls.clear()
                    self.manager.state_file.write_text(json.dumps(self.primary))
                    atomic_json(self.journal, original_journal, system_root=self.root, trusted_uid=os.geteuid())
                    with patch.object(self.manager, 'read_state', wraps=self.manager.read_state) as read, \
                            patch.object(self.manager, 'deployment', side_effect=AssertionError('stop parsed profile')), \
                            patch.object(self.manager, '_start', side_effect=AssertionError('stop started backend')), \
                            patch.object(self.manager, '_select', side_effect=AssertionError('stop changed selection')):
                        result = self.manager.dispatch(action, lease=lease)
                    lease.validate()
                    read.assert_called_once_with(recovery=True)
                    self.assertEqual([call for call in self.docker.calls if call[0] == 'stop'], [('stop', self.identity['id'])])
                    self.assertFalse(any(call[0] in {'create', 'remove', 'start_enter', 'inventory', 'run'} for call in self.docker.calls))
                    self.assertEqual(next(c for c in self.docker.records if c['Id'] == self.unrelated['Id']), self.unrelated)
                    self.assertEqual(result['container'], self.identity)
                    self.assertEqual(result['selected'], original_journal['selected'])
                    self.assertEqual(result['desired'], 'running' if action == 'boot-stop' else 'stopped')
                    self.assertEqual(self.manager.instance, original_instance)
        self.assertFalse(self.configs.exists())

    def test_unknown_admission_without_run_identity_cannot_fall_back_to_primary(self):
        primary_bytes = self.manager.state_file.read_bytes()
        self.journal.unlink()
        for admission in ('pending_marker', 'pending_gate', 'orphan_inhibitor', 'unknown'):
            self.admission = admission
            for action in ('stop', 'recover-stop', 'boot-stop'):
                with self.subTest(admission=admission, action=action), self.lease() as lease:
                    with self.assertRaisesRegex(LifecycleError, '^no_recovery_identity$'):
                        self.manager.dispatch(action, lease=lease)
                    lease.validate()
        self.assertEqual(self.docker.calls, [])
        self.assertEqual(self.manager.state_file.read_bytes(), primary_bytes)
        self.assertFalse(self.journal.exists())
        self.assertFalse(any(event[0] == 'write' for event in self.events))


if __name__ == '__main__':
    unittest.main()
