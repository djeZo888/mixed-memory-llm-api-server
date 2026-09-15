"""Actual I1R admission with actual Manager/I1b guard and anchored writer.

Only policy_path is redirected by a partial wrapper to a protected worker file.
LocalStorageFixture injects Linux discovery/mountinfo and ordinary-user UID; its
real I1b descriptors/writer run. No package, systemd, policy on /usr, VM or GPU is
executed. Docker recovery uses the retained inspect-compatible fake.
"""
from __future__ import annotations

import copy
from functools import partial
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.lifecycle_lease import transition_in_progress
from install import prerequisites
from lifecycle.manager import LABEL, OWNER, empty_state
from lifecycle.runtime_io import LifecycleError
from test_real_storage_io import LocalStorageFixture

REAL_ADMISSION = prerequisites.assert_package_admission
ORDINARY = ('select', 'activate', 'start', 'restart', 'boot-start', 'deactivate')
MODEL = 'qwen3-coder-next'


class RealPackageAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = LocalStorageFixture()
        self.addCleanup(self.fixture.close)
        self.manager = self.fixture.manager
        self.policy = self.fixture.base / 'policy-rc.d'
        self.marker = Path(self.fixture.data) / 'services/installer/package-service-policy.json'
        self.gate = self.marker.with_name('package-execution-gate.json')
        # Execute the reviewed author function without touching the real host policy.
        self.admission_patch = patch.object(
            prerequisites, 'assert_package_admission',
            side_effect=partial(REAL_ADMISSION, policy_path=self.policy))
        self.admission = self.admission_patch.start()
        self.addCleanup(self.admission_patch.stop)
        self.manager.run = lambda *a, **kw: self.fail('unexpected external process')
        self.manager.probe = lambda *a, **kw: self.fail('unexpected model API probe')

    def assert_handles_closed(self):
        self.assertTrue(self.fixture.guards)
        self.assertTrue(all(item._closed for item in self.fixture.guards + self.fixture.anchors))

    def write_record(self, path, value):
        with self.fixture.lease() as lease:
            self.manager.persistent_json(str(path), value)
            lease.validate()

    def blocked_ordinary(self):
        # Real flock is available; persisted package admission must still reject.
        self.assertFalse(transition_in_progress(system_root=self.fixture.base, trusted_uid=os.geteuid()))
        records = copy.deepcopy(self.fixture.docker.records)
        for action in ORDINARY:
            with self.subTest(action=action), self.fixture.lease() as lease, \
                    patch.object(self.manager, 'read_state', side_effect=AssertionError('premature state read')) as read, \
                    patch.object(self.manager, 'deployment', side_effect=AssertionError('premature profile read')) as profile:
                with self.assertRaisesRegex(LifecycleError, '^package_transaction_recovery_required$'):
                    self.manager.dispatch(action, deployment_id=MODEL, lease=lease)
                lease.validate()
                read.assert_not_called()
                profile.assert_not_called()
        self.assertEqual(self.admission.call_count, len(ORDINARY))
        for call in self.admission.call_args_list:
            self.assertEqual(call.args[0], self.fixture.data)
            self.assertTrue(callable(call.args[1]))
            self.assertEqual(call.kwargs, {})
        self.assertEqual(self.fixture.docker.calls, [])
        self.assertEqual(self.fixture.docker.records, records)
        self.assertFalse(self.manager.state_file.exists())
        self.assertFalse(self.manager.recovery_file.exists())
        self.assert_handles_closed()

    def test_clear_actual_admission_allows_stopped_tombstone_through_real_writer(self):
        with self.fixture.lease() as lease:
            result = self.manager.dispatch('deactivate', lease=lease)
            lease.validate()
        self.assertEqual(result['desired'], 'stopped')
        self.assertIsNone(result['selected'])
        self.assertTrue(result['state_persisted'])
        self.assertTrue(self.manager.state_file.is_file())
        self.assertTrue(self.manager.recovery_file.is_file())
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.gate.exists())
        self.assertFalse(self.policy.exists())
        self.assertEqual(self.fixture.docker.calls, [])
        self.admission.assert_called_once()
        self.assert_handles_closed()

    def test_pending_marker_blocks_with_free_canonical_lock_without_recovery(self):
        self.write_record(self.marker, {'schema_version': 1, 'terminal': True, 'fixture': 'pending marker'})
        before = self.marker.read_bytes()
        self.blocked_ordinary()
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertFalse(self.policy.exists())

    def test_execution_gate_alone_blocks_all_ordinary_mutations(self):
        self.write_record(self.gate, {'schema_version': 1, 'fixture': 'pending execution gate'})
        before = self.gate.read_bytes()
        self.blocked_ordinary()
        self.assertEqual(self.gate.read_bytes(), before)
        self.assertFalse(self.marker.exists())

    def test_orphan_inhibitor_sentinel_alone_blocks_without_restoring_policy(self):
        self.policy.write_bytes(prerequisites.POLICY_SENTINEL)
        self.policy.chmod(0o755)
        self.blocked_ordinary()
        self.assertEqual(self.policy.read_bytes(), prerequisites.POLICY_SENTINEL)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o755)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.gate.exists())

    def test_unknown_unprotected_policy_state_fails_closed_without_reading_target(self):
        target = self.fixture.base / 'untouched-policy-target'
        target.write_bytes(b'fixture protected target')
        target.chmod(0o600)
        self.policy.symlink_to(target)
        before = target.read_bytes()
        self.blocked_ordinary()
        self.assertTrue(self.policy.is_symlink())
        self.assertEqual(target.read_bytes(), before)

    def test_existing_noninstaller_policy_is_preserved_by_actual_readonly_admission(self):
        content = b'#!/bin/sh\n# protected worker preexisting policy\nexit 101\n'
        self.policy.write_bytes(content)
        self.policy.chmod(0o750)
        with self.fixture.lease() as lease:
            self.manager.check_package_admission()
            lease.validate()
        self.assertEqual(self.policy.read_bytes(), content)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o750)
        self.assertFalse(self.manager.state_file.exists())
        self.assertFalse(self.manager.recovery_file.exists())
        self.assertEqual(self.fixture.docker.calls, [])
        self.admission.assert_called_once()
        self.assert_handles_closed()

    def seed_trusted_journal_and_divergent_primary(self):
        identity = {'id': 'a' * 64, 'image_id': 'sha256:' + 'b' * 64,
                    'name': 'llmctl-admission-fixture', 'owner': OWNER,
                    'instance': self.fixture.instance['id'], 'deployment': MODEL, 'legacy': False}
        other = dict(identity, id='c' * 64, name='llmctl-other-admission-fixture')
        def container(record):
            return {'Id': record['id'], 'Image': record['image_id'], 'Name': '/' + record['name'],
                    'Config': {'Labels': {LABEL + key: record[key] for key in ('owner', 'instance', 'deployment')}},
                    'State': {'Running': True, 'Status': 'running'}, 'NetworkSettings': {'Ports': {}}}
        self.fixture.docker.records = [container(identity), container(other)]
        self.manager.state = {**empty_state(), 'selected': MODEL, 'desired': 'running', 'boot_policy': 'resume',
                              'observed': 'ready', 'container_running': True, 'container': identity}
        with self.fixture.lease():
            self.manager.save()
        primary = dict(self.manager.state, container=other, updated_at=self.manager.state['updated_at'] + 1)
        self.write_record(self.manager.state_file, primary)
        return identity, other

    def stop_from_actual_admission_error(self, action):
        identity, other = self.seed_trusted_journal_and_divergent_primary()
        self.policy.write_bytes(prerequisites.POLICY_SENTINEL)
        self.policy.chmod(0o755)
        with self.fixture.lease() as lease, \
                patch.object(self.manager, 'read_state', wraps=self.manager.read_state) as read, \
                patch.object(self.manager, 'deployment', side_effect=AssertionError('trusted stop parsed config')), \
                patch.object(self.manager, '_start', side_effect=AssertionError('trusted stop started backend')), \
                patch.object(self.manager, '_select', side_effect=AssertionError('trusted stop selected backend')):
            result = self.manager.dispatch(action, lease=lease)
            lease.validate()
        read.assert_called_once_with(recovery=True)
        self.admission.assert_called_once()
        self.assertEqual([c for c in self.fixture.docker.calls if c[0] == 'stop'], [('stop', identity['id'])])
        self.assertTrue(next(c for c in self.fixture.docker.records if c['Id'] == other['id'])['State']['Running'])
        self.assertEqual(result['container'], identity)
        self.assertFalse(result['container_running'])
        self.assertEqual(result['desired'], 'running' if action == 'boot-stop' else 'stopped')
        self.assertTrue(result['state_persisted'])
        self.assertEqual(json.loads(self.manager.recovery_file.read_text())['container'], identity)
        self.assertEqual(self.policy.read_bytes(), prerequisites.POLICY_SENTINEL)
        self.assert_handles_closed()

    def test_actual_orphan_error_stop_uses_only_trusted_journal_identity(self):
        self.stop_from_actual_admission_error('stop')

    def test_actual_orphan_error_boot_stop_keeps_recorded_resume_intent(self):
        self.stop_from_actual_admission_error('boot-stop')

    def test_actual_admission_error_missing_journal_never_uses_primary_container(self):
        self.seed_trusted_journal_and_divergent_primary()
        self.manager.recovery_file.unlink()
        self.write_record(self.gate, {'fixture': 'pending gate'})
        primary = self.manager.state_file.read_bytes()
        with self.fixture.lease() as lease:
            with self.assertRaisesRegex(LifecycleError, '^no_recovery_identity$'):
                self.manager.dispatch('stop', lease=lease)
            lease.validate()
        self.assertEqual(self.fixture.docker.calls, [])
        self.assertTrue(all(c['State']['Running'] for c in self.fixture.docker.records))
        self.assertEqual(self.manager.state_file.read_bytes(), primary)
        self.assertFalse(self.manager.recovery_file.exists())
        self.assertTrue(self.gate.exists())
        self.assert_handles_closed()


if __name__ == '__main__':
    unittest.main()
