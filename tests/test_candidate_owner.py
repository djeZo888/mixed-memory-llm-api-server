"""Closed candidate ownership seams; synthetic callbacks and local leases only."""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.test_benchmark_owner import Fixture
from benchmark.host import LinuxHost, command, _COMMAND_DEADLINE
from benchmark.lifecycle import CONTROL_UNIT, digest
from benchmark.owner import CampaignOwner, OwnerError


SCOPE = 'candidate-pair-validation'


class CandidateOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='candidate-owner-')
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name).resolve())
        self.fixture.manifest['placement'] = 'G1'
        self.first = self.fixture.manifest
        self.second = {**self.first, 'placement': 'Q1',
                       'container_name': 'benchrun-offline-q1-700160'}
        self.owner = self.build()
        self.addCleanup(self.release)

    def build(self):
        template = self.fixture.build()
        owner = CampaignOwner(template.campaign, self.fixture, template.host, template.budget,
            reviewed_manifest_hashes=[digest(self.first), digest(self.second)],
            lease_factory=self.fixture.lease_factory, synthetic_offline=True, scope=SCOPE)
        def dispatched_create(manifest):
            owner.mark_create_dispatched()
            return self.fixture.create(manifest)
        owner.host = replace(owner.host, create=dispatched_create)
        self.fixture.owner = owner
        return owner

    def release(self):
        # Local fixture cleanup only. A live unresolved owner retains its lease.
        if self.owner.lease_context is not None:
            self.owner._release()

    def fail_second_create(self):
        self.owner.begin()
        first = self.owner.launch(self.first)
        self.fixture.fail_create = True
        with self.assertRaises(OwnerError):
            self.owner.launch(self.second)
        return first

    def recovery_host(self, ledger):
        self.release()  # Simulate process death, never a live cleanup operation.
        self.owner = self.build()
        host = LinuxHost.__new__(LinuxHost)
        host.scope, host.campaign, host.owner = SCOPE, self.owner.campaign, self.owner
        host.manifests = {digest(m): m for m in (self.first, self.second)}
        host.budget = SimpleNamespace(data={'phase': 'RESTORING'})
        host.read_json = Mock(return_value={**copy.deepcopy(ledger), 'evidence_kind': 'live'})
        host.capture = self.fixture.capture
        host.campaign_containers = Mock(side_effect=lambda: list(self.fixture.containers))
        host.docker_inspect = Mock(side_effect=lambda cid: self.docker(self.fixture.containers[cid]))
        return host

    @staticmethod
    def docker(resource):
        return {'Id': resource['id'], 'Name': '/' + resource['name'], 'Image': resource['image_id'],
                'Config': {'Labels': {'benchmark.campaign': resource['campaign_label'],
                                      'benchmark.owner': resource['owner_label']}},
                'HostConfig': {'RestartPolicy': {'Name': resource['restart_policy']}},
                'State': {'Running': resource['running']}}

    def test_pending_is_durable_before_dispatch_and_blocks_peer_cleanup(self):
        first = self.fail_second_create()
        self.assertEqual(self.owner.phase, 'RECOVERY_REQUIRED')
        pending = self.fixture.writes[-1]['pending_create']
        self.assertEqual((pending['dispatch'], pending['kind']), ('uncertain', 'model'))
        self.assertEqual(self.fixture.writes[-1]['validation_scope'], SCOPE)
        with self.assertRaisesRegex(ValueError, 'unresolved_create_blocks_cleanup'):
            self.owner._retire_row(self.owner.resources[0])
        self.assertTrue(self.fixture.containers[first['id']]['running'])
        self.assertFalse(any(e[0] in {'stop', 'remove'} for e in self.fixture.events))
        self.owner.lease.validate()

    def test_second_start_failure_drains_exact_owned_pair_then_restores(self):
        self.owner.begin()
        first = self.owner.launch(self.first)
        unrelated = {'id': 'f' * 64, 'running': True}
        self.fixture.containers[unrelated['id']] = unrelated
        self.fixture.fail_start = True
        with self.assertRaises(OwnerError):
            self.owner.launch(self.second)
        self.assertEqual(self.owner.phase, 'RESTORED')
        self.assertEqual(self.fixture.containers, {unrelated['id']: unrelated})
        self.assertIn(('stop', first['id']), self.fixture.events)
        self.assertFalse(any(len(e) > 1 and e[1] == unrelated['id'] for e in self.fixture.events))

    def test_failure_waits_for_admitted_peer_drain_before_restore(self):
        self.owner.begin()
        first = self.owner.launch(self.first)
        self.fixture.requests_active = self.fixture.fail_start = True
        with self.assertRaises(OwnerError):
            self.owner.launch(self.second)
        self.assertEqual(self.owner.phase, 'RECOVERY_REQUIRED')
        self.assertTrue(self.fixture.containers[first['id']]['running'])
        self.assertFalse(any(e[0] in {'stop', 'remove'} for e in self.fixture.events))
        self.fixture.requests_active = False
        self.assertTrue(self.owner.restore()['restored'])
        self.assertEqual(self.fixture.containers, {})

    def test_fresh_empty_inventory_never_settles_dispatched_create(self):
        self.fail_second_create()
        ledger = self.owner._ledger()
        # Even multiple empty inventories are not daemon completion evidence.
        self.fixture.containers.clear()
        host = self.recovery_host(ledger)
        self.owner.restore = Mock(wraps=self.owner.restore)
        prior = len(self.fixture.events)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            with self.assertRaisesRegex(ValueError, 'candidate_dispatched_create_unresolved'):
                host.recover()
        self.assertEqual(self.owner.pending_create, ledger['pending_create'])
        self.assertEqual(self.fixture.writes[-1]['pending_create'], ledger['pending_create'])
        self.assertEqual(self.owner.phase, 'RECOVERY_REQUIRED')
        self.owner.lease.validate()
        self.owner.restore.assert_not_called()
        self.assertFalse(any(e[0] in {'stop', 'remove', 'manager', 'control', 'release'}
                             for e in self.fixture.events[prior:]))

    def test_late_exact_identity_settles_then_drains_peer_and_restores(self):
        self.fail_second_create()
        ledger = self.owner._ledger()
        cid = 'd' * 64
        self.fixture.containers[cid] = {'id': cid, 'name': self.second['container_name'],
            'image_id': self.second['expected_image_ids'][0], 'campaign_label': self.owner.campaign,
            'owner_label': 'llm-benchmark', 'restart_policy': 'no', 'running': False}
        host = self.recovery_host(ledger)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            result = host.recover()
        self.assertTrue(result['restored'])
        self.assertIsNone(self.owner.pending_create)
        self.assertEqual(self.fixture.containers, {})
        self.assertIn(('remove', cid), self.fixture.events)

    def test_same_name_wrong_image_cannot_settle_pending(self):
        self.fail_second_create()
        ledger = self.owner._ledger()
        cid = 'd' * 64
        self.fixture.containers[cid] = {'id': cid, 'name': self.second['container_name'],
            'image_id': 'sha256:' + '9' * 64, 'campaign_label': self.owner.campaign,
            'owner_label': 'llm-benchmark', 'restart_policy': 'no', 'running': False}
        host = self.recovery_host(ledger)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            with self.assertRaisesRegex(ValueError, 'created_identity_differs_from_manifest'):
                host.recover()
        self.assertEqual(self.owner.pending_create, ledger['pending_create'])
        self.assertFalse(any(e[0] in {'stop', 'remove'} for e in self.fixture.events))
        self.owner.lease.validate()

    def test_mapping_helper_timeout_retains_before_production_mutation(self):
        for active in (True, False):
            with self.subTest(control_active=active):
                if not active:
                    self.release()
                    self.fixture.events.clear()
                    self.fixture.state['services'][CONTROL_UNIT].update(active='inactive', substate='dead')
                    self.owner = self.build()
                host = LinuxHost.__new__(LinuxHost)
                host.scope, host.campaign, host.owner = SCOPE, self.owner.campaign, self.owner
                host.manifests = {digest(self.first): self.first}
                host.mapping_helpers_verified = False
                host.guards, host.write_json = self.fixture.guards, Mock()
                def gate(stage, lease, original, resources):
                    self.fixture.gate(stage, lease, original, resources)
                    if stage == 'control_frozen':
                        host.verify_mapping_helpers(lease)
                self.owner.host = replace(self.owner.host, gate=gate)
                def dispatched_timeout(argv, timeout, *, candidate_owner):
                    candidate_owner.mark_create_dispatched()
                    raise TimeoutError('synthetic only')
                with patch('benchmark.host.command', side_effect=dispatched_timeout):
                    with self.assertRaises(OwnerError):
                        self.owner.begin()
                self.assertEqual(self.owner.phase, 'RECOVERY_REQUIRED')
                self.assertEqual(self.owner.pending_create['kind'], 'mapping_helper')
                self.assertEqual(self.owner.pending_create['dispatch'], 'uncertain')
                self.assertFalse(self.owner.production_touched)
                self.assertFalse(any(e[0] == 'manager' for e in self.fixture.events))
                self.owner.lease.validate()

    def test_restored_phase_with_pending_never_releases_recovery_lease(self):
        self.fail_second_create()
        ledger = self.owner._ledger()
        ledger['phase'] = 'RESTORED'
        host = self.recovery_host(ledger)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            with self.assertRaisesRegex(ValueError, 'candidate_restored_ownership_unresolved'):
                host.recover()
        self.owner.lease.validate()
        self.assertIsNotNone(self.owner.pending_create)

    def test_fresh_helper_recovery_preserves_uncertainty_then_exact_id_only(self):
        self.owner.begin()
        ledger = self.owner._ledger()
        ledger.update(production_touched=False, resources=[], pending_create={
            'manifest_sha256': digest(self.first), 'name': self.owner.campaign + '-mapping-helper-g',
            'image': self.first['image'], 'campaign': self.owner.campaign,
            'dispatch': 'uncertain', 'kind': 'mapping_helper'})
        # Model is still original/running because this helper precedes retirement.
        self.fixture.state['manager'] = copy.deepcopy(ledger['original']['manager'])
        host = self.recovery_host(ledger)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            with self.assertRaisesRegex(ValueError, 'candidate_dispatched_create_unresolved'):
                host.recover()
        self.assertEqual(self.owner.pending_create, ledger['pending_create'])
        cid = 'e' * 64
        self.fixture.containers[cid] = {'id': cid, 'name': ledger['pending_create']['name'],
            'image_id': self.first['expected_image_ids'][0], 'campaign_label': self.owner.campaign,
            'owner_label': 'llm-benchmark', 'restart_policy': 'no', 'running': False}
        host = self.recovery_host(ledger)
        prior = len(self.fixture.events)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            self.assertTrue(host.recover()['restored'])
        self.assertIn(('remove', cid), self.fixture.events[prior:])
        self.assertFalse(any(e[0] == 'manager' for e in self.fixture.events[prior:]))
        self.assertEqual(self.fixture.containers, {})

    def test_candidate_ledger_cannot_recover_through_historical_scope(self):
        self.fail_second_create()
        host = self.recovery_host(self.owner._ledger())
        host.scope = 'full'
        with patch('common.lifecycle_lease.acquire_lease') as acquire:
            with self.assertRaisesRegex(ValueError, 'recovery_scope_changed'):
                host.recover()
        acquire.assert_not_called()

    def test_host_artifact_refusal_is_proven_undispatched_and_restores(self):
        self.owner.begin()
        host = LinuxHost.__new__(LinuxHost)
        host.scope, host.owner = SCOPE, self.owner
        host.manifests = {digest(self.first): self.first}
        host.manager = Mock()
        host.manager.check_artifacts.side_effect = ValueError('synthetic_missing_receipt')
        self.owner.host = replace(self.owner.host, create=host.create)
        with patch('benchmark.host.command') as command:
            with self.assertRaises(OwnerError):
                self.owner.launch(self.first)
        command.assert_not_called()
        self.assertEqual(self.owner.phase, 'RESTORED')
        self.assertIsNone(self.owner.pending_create)
        self.assertTrue(any((row.get('pending_create') or {}).get('dispatch') == 'not_dispatched'
                            for row in self.fixture.writes))
        self.assertFalse(any(e[0] in {'create', 'stop', 'remove'} for e in self.fixture.events))

    def test_dispatch_marker_write_failure_never_creates_and_durably_settles(self):
        self.owner.begin()
        failed = [False]
        def write(ledger):
            if (ledger.get('pending_create') or {}).get('dispatch') == 'uncertain' and not failed[0]:
                failed[0] = True
                raise ValueError('synthetic_marker_write_failed')
            self.fixture.write(ledger)
        self.owner.host = replace(self.owner.host, write=write)
        with self.assertRaises(OwnerError):
            self.owner.launch(self.first)
        self.assertTrue(failed[0])
        self.assertEqual(self.owner.phase, 'RESTORED')
        self.assertIsNone(self.owner.pending_create)
        self.assertFalse(any(e[0] == 'create' for e in self.fixture.events))

    def test_unsettled_marker_write_failure_retains_uncertainty(self):
        self.owner.begin()
        failed = [False]
        def write(ledger):
            failed[0] |= (ledger.get('pending_create') or {}).get('dispatch') == 'uncertain'
            if failed[0]:
                raise ValueError('synthetic_writer_unavailable')
            self.fixture.write(ledger)
        self.owner.host = replace(self.owner.host, write=write)
        with self.assertRaises(OwnerError):
            self.owner.launch(self.first)
        self.assertEqual(self.owner.phase, 'RECOVERY_REQUIRED')
        self.assertEqual(self.owner.pending_create['dispatch'], 'uncertain')
        self.assertFalse(any(e[0] == 'create' for e in self.fixture.events))
        self.owner.lease.validate()

    def test_fresh_proven_undispatched_empty_inventory_can_settle(self):
        self.owner.begin()
        ledger = self.owner._ledger()
        ledger['pending_create'] = {'manifest_sha256': digest(self.first), 'name': self.first['container_name'],
            'image': self.first['image'], 'campaign': self.owner.campaign,
            'dispatch': 'not_dispatched', 'kind': 'model'}
        host = self.recovery_host(ledger)
        with patch('common.lifecycle_lease.acquire_lease', self.fixture.lease_factory):
            self.assertTrue(host.recover()['restored'])
        self.assertIsNone(self.owner.pending_create)
        self.assertFalse(any(e[0] in {'create', 'stop', 'remove'} for e in self.fixture.events))

    def test_command_deadline_refusal_precedes_dispatch_marker(self):
        self.owner.begin()
        self.owner.host = replace(self.owner.host, create=lambda manifest:
            command(['/usr/bin/docker', 'create', 'synthetic-only'], candidate_owner=self.owner))
        token = _COMMAND_DEADLINE.set(time.monotonic() - 1)
        try:
            with patch('benchmark.host.subprocess.run') as run:
                with self.assertRaises(OwnerError):
                    self.owner.launch(self.first)
            run.assert_not_called()
        finally:
            _COMMAND_DEADLINE.reset(token)
        self.assertEqual(self.owner.phase, 'RESTORED')
        self.assertIsNone(self.owner.pending_create)

    def test_command_marks_before_subprocess_timeout_and_keeps_uncertainty(self):
        self.owner.begin()
        self.owner.host = replace(self.owner.host, create=lambda manifest:
            command(['/usr/bin/docker', 'create', 'synthetic-only'], candidate_owner=self.owner))
        def timeout(*args, **kwargs):
            self.assertEqual(self.fixture.writes[-1]['pending_create']['dispatch'], 'uncertain')
            raise TimeoutError('synthetic-subprocess-timeout')
        with patch('benchmark.host.subprocess.run', side_effect=timeout):
            with self.assertRaises(OwnerError):
                self.owner.launch(self.first)
        self.assertEqual(self.owner.phase, 'RECOVERY_REQUIRED')
        self.assertEqual(self.owner.pending_create['dispatch'], 'uncertain')
        self.owner.lease.validate()


if __name__ == '__main__':
    unittest.main()
