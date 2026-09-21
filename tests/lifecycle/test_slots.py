"""Actual Manager state/lease/storage-loss paths with synthetic Docker only."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_manager as base
from lifecycle.manager import Manager, atomic_json, empty_state, LABEL
from lifecycle.runtime_io import LifecycleError
from lifecycle import slot_state

GLM = 'glm-5.3-ud-q4-k-xl-fixture-slot'
QWEN = 'qwen38-27b-fixture-slot'


class SlotDocker(base.FakeDocker):
    # Docker IDs are never reused after removal; retain that property in fixtures.
    def __init__(self):
        super().__init__()
        self.serial = 0

    def create(self, args):
        super().create(args)
        self.serial += 1
        self.records[-1]['Id'] = f'{self.serial:064x}'
        return self.records[-1]['Id']


class SlotFixture(base.FixtureManager):
    def validate_slot_deployment(self, deployment, target):
        if deployment['id'] in {GLM, QWEN}:
            if slot_state.deployment_slot(deployment['id']) != target:
                raise LifecycleError('unreviewed_slot_deployment')
            return
        return super().validate_slot_deployment(deployment, target)

    def deployment(self, identifier):
        if identifier not in {GLM, QWEN}:
            return super().deployment(identifier)
        item = super().deployment(base.PROOF)
        item.update(id=identifier, container_name='fixture-' + ('glm' if identifier == GLM else 'qwen'))
        item['endpoint']['port'] = 30002 if identifier == GLM else 30004
        return item


class SlotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'configs'
        shutil.copytree(base.ROOT / 'configs', self.config)
        self.instance = base.make_instance(self.root)
        self.instance['slot_migration'] = {
            'prior_source_revision': 'a' * 40, 'prior_source_manifest_sha256': 'b' * 64,
            'prior_boot_unit_sha256': 'c' * 64, 'approval_reference': 'synthetic-root-review',
            'prior_source_root': '/data/services/rollback-source',
            'prior_recovery_source_root': '/usr/local/lib/local-ai-server'}
        self.docker = SlotDocker()
        clock = base.FakeClock()
        self.manager = SlotFixture(self.config, self.instance, test_paths=True, docker=self.docker,
            run_fn=lambda *a, **k: self.fail('unexpected subprocess'),
            probe_fn=lambda *a, **k: 'ready', sleep_fn=clock.sleep, monotonic_fn=clock.monotonic)
        self.key = patch('lifecycle.manager.validate_key_metadata').start()
        self.addCleanup(patch.stopall)
        # Deliberately synthetic profiles exercise ownership independently of
        # exact candidate resources; candidate admission has separate real tests.
        patch('lifecycle.concurrent_profiles.validate_pair', side_effect=self.compatible).start()

    def compatible(self, left, right):
        if {left['id'], right['id']} != {GLM, QWEN}:
            raise LifecycleError('incompatible_pair_profiles')

    def migrate(self):
        return self.manager.dispatch('migrate-slots')

    def pair(self):
        self.migrate()
        for name, profile in [('glm', GLM), ('qwen', QWEN)]:
            self.manager.dispatch('select', profile, boot_policy='resume', target=name)
            self.manager.dispatch('start', target=name)
        return self.manager.read_state()

    def test_migration_backup_precedes_state_and_keeps_intent_not_readiness(self):
        self.manager.dispatch('select', GLM, boot_policy='resume')
        old = self.manager.dispatch('start')
        migrated = self.migrate()
        backup = json.loads(self.manager.migration_backup().read_text())
        self.assertEqual(backup['state'], old)
        self.assertEqual(migrated['migration']['backup_sha256'], slot_state.digest(backup))
        slot = migrated['slots']['glm']
        self.assertEqual(slot['container'], old['container'])
        self.assertEqual(slot['desired'], 'running')
        self.assertEqual(slot['boot_policy'], 'resume')
        self.assertEqual(slot['observed'], 'unknown')
        self.assertIsNone(slot['container_running'])
        self.assertEqual(self.manager.migration_backup().stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.migrate(), migrated)

    def test_migration_requires_reviewed_source_and_never_overwrites_backup(self):
        self.manager.instance.pop('slot_migration')
        with self.assertRaisesRegex(LifecycleError, 'slot_migration_authority_required'):
            self.migrate()
        self.assertFalse(self.manager.state_file.exists())
        self.manager.instance['slot_migration'] = self.instance['slot_migration']
        path = self.manager.migration_backup()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
        with self.assertRaisesRegex(LifecycleError, 'pre_migration_backup_exists_mismatch'):
            self.migrate()
        self.assertEqual(path.read_text(), '{}')

    def test_failed_backup_write_never_migrates(self):
        with patch.object(self.manager, 'persistent_json', side_effect=LifecycleError('fixture_write_failure')):
            with self.assertRaises(LifecycleError):
                self.migrate()
        self.assertEqual(self.manager.read_state()['schema_version'], 2)

    def test_malformed_unknown_duplicate_slot_state_rejected(self):
        valid = self.pair()
        changes = [lambda s: s['slots'].pop('glm'),
                   lambda s: s['slots'].update(extra=slot_state.empty_slot()),
                   lambda s: s['slots']['glm'].update(generation=True),
                   lambda s: s['slots']['qwen'].update(selected=GLM),
                   lambda s: s['slots']['glm'].update(container_running='yes'),
                   lambda s: s['migration'].update(backup_sha256='bad'),
                   lambda s: s['slots']['glm'].update(arbitrary='raw'),
                   lambda s: s['slots']['qwen']['container'].update(id=s['slots']['glm']['container']['id'])]
        for mutate in changes:
            bad = copy.deepcopy(valid); mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(LifecycleError):
                slot_state.validate(bad, self.manager.validate_identity)

    def test_target_restart_never_stops_or_changes_peer(self):
        before = self.pair()
        peer = copy.deepcopy(before['slots']['qwen'])
        self.docker.calls.clear()
        result = self.manager.dispatch('restart', target='glm', expected_generation=before['slots']['glm']['generation'])
        self.assertEqual(result['slots']['qwen'], peer)
        self.assertTrue(self.manager.running(self.docker.inspect(peer['container']['id'])))
        self.assertEqual([c for c in self.docker.calls if c[0] == 'stop'], [('stop', before['slots']['glm']['container']['id'])])
        journal = json.loads(self.manager.recovery_file.read_text())
        self.assertEqual(journal['slots']['qwen'], peer)

    def test_stale_target_generation_fails_and_peer_generation_survives(self):
        before = self.pair()
        self.manager.dispatch('stop', target='glm', expected_generation=before['slots']['glm']['generation'])
        self.docker.calls.clear()
        with self.assertRaisesRegex(LifecycleError, 'stale_slot_generation'):
            self.manager.dispatch('restart', target='glm', expected_generation=before['slots']['glm']['generation'])
        self.assertEqual(self.docker.calls, [])
        self.manager.dispatch('stop', target='qwen', expected_generation=before['slots']['qwen']['generation'])

    def test_legacy_pair_mutations_are_ambiguous_but_single_selected_retains_behavior(self):
        self.pair()
        for action in ('start', 'stop', 'restart', 'deactivate'):
            with self.subTest(action=action), self.assertRaisesRegex(LifecycleError, 'ambiguous_slot_target_required'):
                self.manager.dispatch(action)
        self.manager.dispatch('deactivate', target='qwen')
        result = self.manager.dispatch('stop')
        self.assertFalse(result['slots']['glm']['container_running'])

    def test_unknown_owned_and_gpu_peer_rejected(self):
        self.pair()
        self.manager.dispatch('stop', target='glm')
        original = self.docker.records.copy()
        for owned in (True, False):
            record = copy.deepcopy(original[1])
            record.update(Id='f' * 64, Name='/unknown')
            record['Config']['Labels'] = {LABEL + 'owner': 'mixed-memory-llm-api-server'} if owned else {}
            self.docker.records = original + [record]
            with self.subTest(owned=owned), self.assertRaisesRegex(LifecycleError, 'conflicting_backend_stop_first|untrusted_concurrent_peer'):
                self.manager.dispatch('start', target='glm')

    def test_incompatible_reserved_selection_rejected(self):
        self.migrate()
        self.manager.dispatch('select', base.PROOF, target='glm')
        with self.assertRaisesRegex(LifecycleError, 'incompatible_pair_profiles'):
            self.manager.dispatch('select', QWEN, target='qwen')
        self.assertEqual(self.manager.read_state()['slots']['glm']['selected'], base.PROOF)

    def test_failed_second_start_retains_both_identities_and_healthy_peer(self):
        self.migrate()
        self.manager.dispatch('select', GLM, target='glm')
        self.manager.dispatch('start', target='glm')
        self.manager.dispatch('select', QWEN, target='qwen')
        self.docker.fail_start = True
        with self.assertRaises(LifecycleError):
            self.manager.dispatch('start', target='qwen')
        saved = self.manager.read_state()
        self.assertEqual(saved['slots']['glm']['observed'], 'ready')
        self.assertTrue(saved['slots']['glm']['container_running'])
        self.assertIsNotNone(saved['slots']['qwen']['container'])
        self.assertEqual(saved['slots']['qwen']['observed'], 'failed')
        self.docker.fail_start = False
        self.manager.dispatch('stop', target='qwen')
        self.assertTrue(self.manager.status('glm')['container_running'])

    def test_boot_order_explicit_intents_and_partial_stop_failure(self):
        saved = self.pair()
        self.manager.dispatch('boot-stop')
        self.docker.calls.clear()
        self.manager.dispatch('boot-start')
        ids = [saved['slots'][n]['container']['id'] for n in ('glm', 'qwen')]
        self.assertEqual([c[1] for c in self.docker.calls if c[0] == 'start_enter'], list(reversed(ids)))
        original = self.docker.stop
        def fail_first(identity, **kwargs):
            if identity == ids[0]:
                raise LifecycleError('synthetic_stop_failed')
            return original(identity, **kwargs)
        with patch.object(self.docker, 'stop', side_effect=fail_first):
            with self.assertRaisesRegex(LifecycleError, 'partial_slot_transition_failed'):
                self.manager.dispatch('boot-stop')
        state = self.manager.read_state()
        self.assertTrue(state['slots']['glm']['container_running'])
        self.assertFalse(state['slots']['qwen']['container_running'])
        self.assertTrue(all(s['desired'] == 'running' for s in state['slots'].values()))
        self.assertTrue(all(s['container'] for s in state['slots'].values()))

    def test_storage_loss_recovery_retains_and_stops_both_exact_identities(self):
        before = self.pair()
        recovery = Manager(self.root/'absent', {'schema_version': 1, 'id': self.instance['id']},
                           recovery_only=True, test_paths=True, lease_system_root=self.root,
                           docker=self.docker, run_fn=lambda *a, **k: self.fail('unexpected subprocess'))
        shutil.rmtree(self.root/'state'); shutil.rmtree(self.config)
        self.docker.calls.clear()
        result = recovery.dispatch('recover-stop')
        self.assertFalse(result['state_persisted'])
        self.assertEqual([c[1] for c in self.docker.calls if c[0] == 'stop'],
                         [before['slots'][n]['container']['id'] for n in ('glm', 'qwen')])
        journal = json.loads(recovery.recovery_file.read_text())
        for name in slot_state.SLOTS:
            self.assertEqual(journal['slots'][name]['container'], before['slots'][name]['container'])
            self.assertFalse(journal['slots'][name]['container_running'])

    def test_create_timeout_retains_planned_owner_and_stop_recovers_exactly(self):
        self.migrate()
        self.manager.dispatch('select', GLM, target='glm')
        create = self.docker.create
        def created_then_timeout(args):
            create(args)
            raise LifecycleError('command_timeout')
        with patch.object(self.docker, 'create', side_effect=created_then_timeout):
            with self.assertRaisesRegex(LifecycleError, 'command_timeout'):
                self.manager.dispatch('start', target='glm')
        saved = self.manager.read_state()['slots']['glm']
        self.assertIsNone(saved['container'])
        self.assertEqual(saved['pending_create']['name'], 'fixture-glm')
        self.assertEqual(saved['pending_create']['dispatch'], 'uncertain')
        self.docker.start(self.docker.records[0]['Id'])
        stopped = self.manager.dispatch('stop', target='glm')['slots']['glm']
        self.assertIsNone(stopped['pending_create'])
        self.assertEqual(stopped['container']['id'], self.docker.records[0]['Id'])
        self.assertFalse(stopped['container_running'])

    def test_proven_precreate_absence_clears_only_owned_pending_and_allows_retry(self):
        before = self.pair()
        self.manager.dispatch('deactivate', target='glm')
        self.manager.dispatch('select', GLM, target='glm')
        check = self.manager.check_sources
        def fail_before_dispatch(deployment):
            if self.manager.state.get('pending_create'):
                self.assertEqual(self.manager.read_state()['slots']['glm']['pending_create']['dispatch'],
                                 'not_dispatched')
                raise LifecycleError('source_changed_before_dispatch')
            return check(deployment)
        with patch.object(self.manager, 'check_sources', side_effect=fail_before_dispatch), \
             patch.object(self.docker, 'create') as create, \
             self.assertRaisesRegex(LifecycleError, 'source_changed_before_dispatch'):
            self.manager.dispatch('start', target='glm')
        create.assert_not_called()
        pending = self.manager.read_state()['slots']['glm']['pending_create']
        self.assertEqual(pending['dispatch'], 'not_dispatched')
        self.assertIsNone(self.docker.inspect(pending['name']))
        result = self.manager.dispatch('stop', target='glm')
        self.assertIsNone(result['slots']['glm']['pending_create'])
        self.assertIsNone(result['slots']['glm']['container'])
        self.assertFalse(result['slots']['glm']['container_running'])
        self.assertEqual(result['slots']['qwen'], before['slots']['qwen'])
        self.manager.dispatch('start', target='glm')
        self.assertTrue(self.manager.status('qwen')['container_running'])

    def test_uncertain_pending_inspection_retains_owner_and_blocks_selection_reset(self):
        self.migrate(); self.manager.dispatch('select', GLM, target='glm')
        self.docker.fail_create = True
        with self.assertRaises(LifecycleError):
            self.manager.dispatch('start', target='glm')
        pending = self.manager.read_state()['slots']['glm']['pending_create']
        self.assertEqual(pending['dispatch'], 'uncertain')
        # Even generic CLI failure followed by successful empty inventories
        # cannot prove that the daemon did not accept the dispatched create.
        for _ in range(2):
            with self.assertRaisesRegex(LifecycleError, 'pending_create_unresolved_use_recovery'):
                self.manager.dispatch('stop', target='glm')
        with patch.object(self.docker, 'inspect', side_effect=LifecycleError('command_timeout')):
            with self.assertRaises(LifecycleError):
                self.manager.dispatch('stop', target='glm')
        self.assertEqual(self.manager.read_state()['slots']['glm']['pending_create'], pending)
        for deployment in (GLM, base.PROOF):
            with self.subTest(deployment=deployment), self.assertRaisesRegex(LifecycleError, 'pending_create_requires_recovery_stop'):
                self.manager.dispatch('select', deployment, target='glm')
            self.assertEqual(self.manager.read_state()['slots']['glm']['pending_create'], pending)

    def test_delayed_create_after_empty_inventories_retains_owner_until_exact_recovery(self):
        before = self.pair()
        self.manager.dispatch('deactivate', target='glm')
        self.manager.dispatch('select', GLM, target='glm')
        deferred = []
        create = self.docker.create
        def timeout(args):
            self.assertEqual(self.manager.read_state()['slots']['glm']['pending_create']['dispatch'], 'uncertain')
            deferred.append(args)
            raise LifecycleError('command_timeout')
        with patch.object(self.docker, 'create', side_effect=timeout), self.assertRaises(LifecycleError):
            self.manager.dispatch('start', target='glm')
        pending = self.manager.read_state()['slots']['glm']['pending_create']
        # A fresh recovery owner reads only the durable journal, not process memory.
        recovery = Manager(self.root/'absent', {'schema_version': 1, 'id': self.instance['id']},
                           recovery_only=True, test_paths=True, lease_system_root=self.root,
                           docker=self.docker, run_fn=lambda *a, **k: self.fail('unexpected subprocess'))
        for _ in range(3):
            self.assertIsNone(self.docker.inspect(pending['name']))
            with self.assertRaisesRegex(LifecycleError, 'pending_create_unresolved_use_recovery'):
                recovery.dispatch('stop', target='glm')
            saved = recovery.read_state(recovery=True)
            self.assertEqual(saved['slots']['glm']['pending_create'], pending)
            self.assertIsNone(saved['slots']['glm']['container_running'])
            self.assertEqual(saved['slots']['qwen'], before['slots']['qwen'])
        with self.assertRaisesRegex(LifecycleError, 'pending_create_requires_recovery_stop'):
            self.manager.dispatch('start', target='glm')
        with self.assertRaisesRegex(LifecycleError, 'pending_create_requires_recovery_stop'):
            self.manager.dispatch('select', GLM, target='glm')
        delayed_id = create(deferred[0])
        self.docker.start(delayed_id)
        self.docker.calls.clear()
        result = recovery.dispatch('stop', target='glm')
        self.assertEqual(result['slots']['glm']['container']['id'], delayed_id)
        self.assertNotIn('dispatch', result['slots']['glm']['container'])
        self.assertIsNone(result['slots']['glm']['pending_create'])
        self.assertFalse(result['slots']['glm']['container_running'])
        self.assertEqual(result['slots']['qwen'], before['slots']['qwen'])
        self.assertEqual([call[1] for call in self.docker.calls if call[0] == 'stop'], [delayed_id])
        self.assertTrue(self.manager.running(self.docker.inspect(before['slots']['qwen']['container']['id'])))

    def test_markerless_pending_is_uncertain_and_invalid_dispatch_rejected(self):
        state = self.pair()
        item = state['slots']['glm']
        self.docker.stop(item['container']['id'])
        self.docker.remove(item['container']['id'])
        pending = {key: item['container'][key] for key in slot_state.PENDING_IDENTITY_FIELDS}
        item.update(container=None, pending_create=pending, container_running=None)
        slot_state.validate(state, self.manager.validate_identity)
        with self.assertRaisesRegex(LifecycleError, 'pending_create_unresolved_use_recovery'):
            self.manager.pending_identity(item)
        for bad in (None, False, {}, [], 'failed', 'absence_verified'):
            with self.subTest(dispatch=bad):
                pending['dispatch'] = bad
                with self.assertRaisesRegex(LifecycleError, 'invalid_pending_create_dispatch'):
                    slot_state.validate(state, self.manager.validate_identity)

    def test_pending_name_identity_mismatch_never_clears_or_adopts(self):
        self.migrate(); self.manager.dispatch('select', GLM, target='glm')
        create = self.docker.create
        def timeout(args):
            result = create(args)
            self.docker.records[0]['Image'] = 'sha256:' + 'f' * 64
            raise LifecycleError('command_timeout')
        with patch.object(self.docker, 'create', side_effect=timeout), self.assertRaises(LifecycleError):
            self.manager.dispatch('start', target='glm')
        pending = self.manager.read_state()['slots']['glm']['pending_create']
        self.docker.calls.clear()
        with self.assertRaisesRegex(LifecycleError, 'container_identity_changed'):
            self.manager.dispatch('stop', target='glm')
        self.assertEqual(self.manager.read_state()['slots']['glm']['pending_create'], pending)
        self.assertFalse(any(c[0] in {'stop', 'remove'} for c in self.docker.calls))

    def test_returned_create_id_retained_before_inspect_failure(self):
        self.migrate(); self.manager.dispatch('select', GLM, target='glm')
        inspect = self.docker.inspect
        def broken(identity):
            if len(identity) == 64:
                raise LifecycleError('command_timeout')
            return inspect(identity)
        with patch.object(self.docker, 'inspect', side_effect=broken):
            with self.assertRaises(LifecycleError):
                self.manager.dispatch('start', target='glm')
        saved = self.manager.read_state()['slots']['glm']
        self.assertEqual(saved['container']['id'], self.docker.records[0]['Id'])
        self.assertIsNone(saved['pending_create'])
        self.manager.dispatch('stop', target='glm')

    def test_migration_retry_repairs_torn_primary_after_verified_backup(self):
        self.manager.dispatch('select', GLM)
        write = self.manager.persistent_json
        def torn(path, value):
            if Path(path) == self.manager.state_file and value.get('schema_version') == 3:
                raise LifecycleError('synthetic_write_failure')
            return write(path, value)
        with patch.object(self.manager, 'persistent_json', side_effect=torn):
            with self.assertRaises(LifecycleError):
                self.migrate()
        self.assertEqual(json.loads(self.manager.state_file.read_text())['schema_version'], 2)
        self.assertFalse(self.manager.read_state()['state_persisted'])
        state = self.migrate()
        self.assertTrue(state['state_persisted'])
        self.assertEqual(json.loads(self.manager.state_file.read_text())['schema_version'], 3)

    def test_incompatible_select_checks_before_removing_target(self):
        before = self.pair()
        self.manager.dispatch('stop', target='glm')
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.manager.dispatch('select', base.PROOF, target='glm')
        self.assertFalse(any(x[0] == 'remove' for x in self.docker.calls))
        self.assertIsNotNone(self.docker.inspect(before['slots']['glm']['container']['id']))

    def test_rollback_may_preserve_exact_untouched_stopped_original(self):
        self.manager.dispatch('select', GLM, boot_policy='resume')
        original = self.manager.dispatch('start')['container']
        self.migrate(); self.manager.dispatch('stop', target='glm')
        result = self.manager.dispatch('rollback-check')
        self.assertEqual(result['retained_original_stopped'], [original])
        self.assertEqual(result['checked_absent'], [])

    def test_migration_captures_singleton_control_journal_and_requires_drain(self):
        from control.journal import empty_state as empty_journal
        local = self.root/'control-operations.json'
        current = empty_journal()
        local.write_text(json.dumps(current))
        original = self.manager.binding.validate_path
        def bound(role, path):
            return local if path.endswith('/llm-control/operations.json') else original(role, path)
        with patch.object(self.manager.binding, 'validate_path', side_effect=bound):
            self.migrate()
        backup = json.loads(self.manager.migration_backup().read_text())
        self.assertEqual(backup['prior_control_journal'], current)
        # Validating live journal grammar and drain status reuses existing owner.
        from unittest.mock import Mock
        with patch.object(self.manager.binding, 'validate_path', return_value=local), \
             patch('control.journal.Journal._validated', return_value={'schema': 1, 'entries': {'fixture': {'status': 'running'}}}):
            with self.assertRaisesRegex(LifecycleError, 'slot_control_operations_must_be_drained'):
                self.manager.migration_control_journal(singleton=True)

    def test_cli_forwards_explicit_target_and_manager_generation(self):
        import argparse
        from contextlib import redirect_stdout
        import io
        from lifecycle.manager import add_commands, cli
        parser = argparse.ArgumentParser()
        add_commands(parser.add_subparsers(dest='command'))
        args = parser.parse_args(['stop', '--yes', '--target', 'qwen', '--expected-generation', '7'])
        with patch('lifecycle.manager.acquire_lease') as lease, \
             patch('lifecycle.manager.load_manager', return_value=self.manager), \
             patch.object(self.manager, 'dispatch', return_value={}) as dispatch, redirect_stdout(io.StringIO()):
            self.assertEqual(cli(args), 0)
        self.assertEqual(dispatch.call_args.kwargs['target'], 'qwen')
        self.assertEqual(dispatch.call_args.kwargs['expected_generation'], 7)

    def test_offline_status_never_reuses_saved_running_as_observation(self):
        self.pair(); self.docker.calls.clear()
        status = self.manager.offline_status()
        self.assertEqual(self.docker.calls, [])
        self.assertTrue(all(s['observed'] is None and s['container_running'] is None for s in status['slots'].values()))

    def test_rollback_prerequisites_check_absence_and_backup_exactly_without_writes(self):
        saved = self.pair()
        with self.assertRaisesRegex(LifecycleError, 'rollback_stop_intent_required'):
            self.manager.dispatch('rollback-check')
        self.manager.dispatch('recover-stop')
        with self.assertRaisesRegex(LifecycleError, 'rollback_owned_container_must_be_absent'):
            self.manager.dispatch('rollback-check')
        for slot in saved['slots'].values():
            self.docker.remove(slot['container']['id'])
        self.docker.calls.clear()
        result = self.manager.dispatch('rollback-check')
        self.assertTrue(result['rollback_ready']); self.assertFalse(result['writes'])
        self.assertFalse(any(x[0] in {'start_enter', 'stop', 'create', 'remove'} for x in self.docker.calls))
        path = self.manager.migration_backup()
        backup = json.loads(path.read_text()); backup['state']['desired'] = 'running'
        path.write_text(json.dumps(backup))
        with self.assertRaisesRegex(LifecycleError, 'slot_backup_mismatch'):
            self.manager.dispatch('rollback-check')


if __name__ == '__main__':
    unittest.main()
