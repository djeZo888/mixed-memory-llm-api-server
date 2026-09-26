"""Real node adapter wiring with local canonical lease and fake external owners.

These are source/offline evidence. No systemd, GPU reset, reboot, VM or native
inference is executed. Production command/owner arguments and safety ordering
are asserted at their actual dispatch boundaries.
"""
import copy
from contextlib import contextmanager
from functools import partial
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from common.lifecycle_lease import acquire_lease, LeaseBusy, LeaseError
from control.node_actions import ActionRequest, DurableReceipt, NodeActions, NodeActionError, SERVICES
from control.node_action_owner import (FixedOwnerDispatcher, ProductionNodeActionOwner,
                                       RegisteredNodeStore, validated_journal)

BOOT = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'
NEXT_BOOT = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
GPU = 'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'


def request(action='service.restart', service='qwen-gpu0', **changes):
    result = dict(schema_version=1, node_id='ai-vm', action=action,
                  idempotency_key='offline-action-1', expected_boot_id=BOOT,
                  expected_generation=7, allow_interrupt=True)
    if action.startswith('service.'):
        result['service_id'] = service
    if action == 'gpu.reset':
        result['gpu_uuid'] = GPU
    return {**result, **changes}


class Store:
    def __init__(self):
        self.value = None
        self.events = []
        self.fail = False
        self.block = None

    def read(self):
        if self.block:
            self.block.wait()
        return copy.deepcopy(self.value)

    def write(self, value):
        if self.fail:
            raise OSError('private fixture message')
        self.value = copy.deepcopy(value)
        for entry in value['operations'].values():
            self.events.append(entry['receipt']['status'])


class Identity:
    def __init__(self):
        self.boot, self.generation = BOOT, 7
        self.calls = 0
        self.latched = False
        self.latch_boot = None
        self.owned = True

    def __call__(self, request, lease, deadline):
        lease.validate()
        self.calls += 1
        return dict(boot_id=self.boot, generation=self.generation,
                    affected_services=[request.service_id] if request.service_id else
                    sorted(SERVICES) if request.action == 'node.reboot' else [],
                    hardware_latched=self.latched, hardware_latched_boot_id=self.latch_boot, ownership_valid=self.owned,
                    canonical_generation=3, selected='installed-current', running=False)


class Dispatch:
    def __init__(self, store):
        self.store = store
        self.calls = []
        self.preflights = []
        self.block = None

    def preflight(self, request, identity, lease, deadline):
        lease.validate()
        self.preflights.append(request)

    def dispatch(self, request, identity, lease, deadline):
        lease.validate()
        assert self.store.value is not None
        entry = next(iter(self.store.value['operations'].values()))
        assert entry['receipt']['status'] == 'running'
        assert entry['dispatch_recorded'] is True
        assert [a['event'] for a in entry['audit']] == ['accepted', 'dispatch']
        self.calls.append(request)
        if self.block:
            self.block.wait()
        return None

    def complete(self, request, result, deadline):
        pass


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.path.chmod(0o700)
        self.lease = partial(acquire_lease, system_root=self.path, trusted_uid=os.geteuid())
        self.store, self.identity = Store(), Identity()
        self.dispatcher = Dispatch(self.store)
        self.owners = []
        self.owner = self.make_owner()
        self.actions = NodeActions(self.owner)

    def make_owner(self, **kwargs):
        owner = ProductionNodeActionOwner(self.store, self.identity, self.dispatcher,
                    lease_factory=self.lease, boot_reader=lambda: self.identity.boot, **kwargs)
        self.owners.append(owner)
        self.addCleanup(owner.close)
        self.wait(lambda: owner._loaded and not owner._busy)
        return owner

    def wait(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.005)
        self.fail('adapter did not reach expected offline fixture state')

    def finished(self, operation_id):
        self.wait(lambda: self.owner.operation(operation_id, deadline=time.monotonic()+1).receipt['status']
                  in {'succeeded', 'failed', 'interrupted', 'unknown'})
        return self.actions.operation(operation_id)[1]

    def test_real_owner_orders_lease_cas_durable_audit_dispatch_and_exact_replay(self):
        status, first = self.actions.submit(request())
        self.assertEqual(status, 202)
        done = self.finished(first['operation_id'])
        self.assertEqual(done['status'], 'succeeded')
        self.assertGreaterEqual(self.identity.calls, 3)
        self.identity.boot, self.identity.generation = NEXT_BOOT, 99
        status, repeated = self.actions.submit(request())
        self.assertEqual((status, repeated['operation_id']), (202, first['operation_id']))
        self.assertEqual(len(self.dispatcher.calls), 1)
        self.assertEqual(self.actions.submit(request(action='service.stop'))[0], 409)
        encoded = json.dumps(self.store.value)
        self.assertNotIn('offline-action-1', encoded)
        self.assertNotIn('allow_interrupt', encoded)

    def terminal_lease(self, *, busy=0, entry_error=None, validate_error=None, exit_error=None):
        """Contend on the real canonical fixture lock only after one dispatch."""
        attempts = []
        @contextmanager
        def lease_factory(*, blocking):
            terminal = bool(self.dispatcher.calls)
            if terminal:
                attempts.append(blocking)
                if len(attempts) <= busy:
                    with self.lease(blocking=False):
                        # Real flock contention at context entry, no body entered.
                        with self.lease(blocking=blocking):
                            self.fail('contended lease unexpectedly admitted')
                if entry_error is not None:
                    raise entry_error
            with self.lease(blocking=blocking) as lease:
                if terminal and validate_error is not None:
                    def validate():
                        raise validate_error
                    yield SimpleNamespace(validate=validate)
                else:
                    yield lease
                if terminal and exit_error is not None:
                    raise exit_error
        self.owner.lease_factory = lease_factory
        return attempts

    def terminal_done(self, body=None):
        status, receipt = self.actions.submit(body or request())
        self.assertEqual(status, 202)
        self.wait(lambda: bool(self.dispatcher.calls) and not self.owner._busy)
        self.assertEqual(len(self.dispatcher.calls), 1)
        return receipt['operation_id'], self.store.value['operations'][receipt['operation_id']]

    def test_terminal_transient_contention_commits_selected_success_once(self):
        attempts = self.terminal_lease(busy=2)
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            operation_id, entry = self.terminal_done()
        self.assertEqual(attempts, [False] * 3)
        self.assertEqual(entry['receipt']['status'], 'succeeded')
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch', 'succeeded'])
        self.assertEqual(self.store.events.count('succeeded'), 1)
        self.assertEqual(self.actions.submit(request())[1]['operation_id'], operation_id)
        self.assertEqual(len(self.dispatcher.calls), 1)
        diagnostic.assert_not_called()

    def test_terminal_persistent_contention_retains_running_then_startup_interrupts_without_replay(self):
        attempts = self.terminal_lease(busy=float('inf'))
        with patch('control.node_action_owner.TERMINAL_LEASE_SECONDS', .03), \
             patch('control.node_action_owner.TERMINAL_LEASE_POLL_SECONDS', .01), \
             patch('control.node_action_owner.syslog.syslog') as diagnostic:
            operation_id, entry = self.terminal_done(request(service='image'))
        self.assertTrue(1 <= len(attempts) <= 3)
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch'])
        audit = copy.deepcopy(entry['audit'])
        diagnostic.assert_called_once()
        message = diagnostic.call_args.args[1]
        self.assertIn('terminal_metadata_uncertain', message)
        self.assertIn('selected_status=succeeded selected_reason=none diagnostic=lease_busy_deadline', message)
        self.assertIn('operation_id=' + operation_id, message)
        self.assertEqual(self.actions.operation(operation_id)[1]['status'], 'running')
        self.assertEqual(self.actions.submit(request(service='image'))[1]['status'], 'running')
        self.owner.close()
        restarted = self.make_owner()
        result = NodeActions(restarted).submit(request(service='image'))[1]
        self.assertEqual((result['operation_id'], result['status'], result['reason']),
                         (operation_id, 'interrupted', 'operation_interrupted'))
        saved = self.store.value['operations'][operation_id]
        self.assertEqual(saved['audit'][:2], audit)
        self.assertEqual([a['event'] for a in saved['audit']], ['accepted', 'dispatch', 'interrupted'])
        self.assertTrue(saved['dispatch_recorded'])
        self.assertEqual(len(self.dispatcher.calls), 1)

    def test_terminal_unsafe_lease_entry_does_not_retry_or_relabel_success(self):
        attempts = self.terminal_lease(entry_error=LeaseError('untrusted_lock_file'))
        self.owner.sleep = Mock()
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(attempts, [False])
        self.owner.sleep.assert_not_called()
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertIn('selected_status=succeeded selected_reason=none diagnostic=lease_invalid',
                      diagnostic.call_args.args[1])
        self.assertNotIn('untrusted_lock_file', diagnostic.call_args.args[1])

    def test_terminal_post_entry_leasebusy_validation_is_not_retried(self):
        attempts = self.terminal_lease(validate_error=LeaseBusy())
        self.owner.sleep = Mock()
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(attempts, [False])
        self.owner.sleep.assert_not_called()
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertIn('diagnostic=lease_invalid', diagnostic.call_args.args[1])

    def test_terminal_diagnostic_transport_failure_keeps_owner_available_and_uncertainty(self):
        attempts = self.terminal_lease(entry_error=LeaseError('untrusted_lock_file'))
        with patch('control.node_action_owner.syslog.syslog', side_effect=OSError('sink unavailable')) as diagnostic:
            operation_id, entry = self.terminal_done()
        diagnostic.assert_called_once()
        self.assertEqual(attempts, [False])
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch'])
        self.assertTrue(self.owner._thread.is_alive())
        self.assertEqual(self.actions.submit(request())[1]['operation_id'], operation_id)
        self.assertEqual(len(self.dispatcher.calls), 1)
        self.owner.lease_factory = self.lease
        code, later = self.actions.submit(request(idempotency_key='independent-action-2'))
        self.assertEqual(code, 202)
        self.assertEqual(self.finished(later['operation_id'])['status'], 'succeeded')
        self.assertEqual(len(self.dispatcher.calls), 2)
        self.assertEqual(self.actions.operation(operation_id)[1]['status'], 'running')

    def test_terminal_actual_action_failure_keeps_own_reason_after_contention(self):
        attempts = self.terminal_lease(busy=1)
        def failed(*args):
            raise NodeActionError('observation_unavailable')
        self.dispatcher.complete = failed
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(attempts, [False, False])
        self.assertEqual((entry['receipt']['status'], entry['receipt']['reason']),
                         ('failed', 'observation_unavailable'))
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch', 'failed'])
        self.assertEqual(entry['audit'][-1]['reason'], 'observation_unavailable')
        diagnostic.assert_not_called()

    def test_terminal_actual_action_failure_retained_in_deadline_diagnostic(self):
        self.terminal_lease(busy=float('inf'))
        def failed(*args):
            raise NodeActionError('deadline_exceeded')
        self.dispatcher.complete = failed
        with patch('control.node_action_owner.TERMINAL_LEASE_SECONDS', .01), \
             patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertIn('selected_status=failed selected_reason=deadline_exceeded diagnostic=lease_busy_deadline',
                      diagnostic.call_args.args[1])

    def test_terminal_reboot_unknown_outcome_survives_contention(self):
        self.terminal_lease(busy=1)
        _, entry = self.terminal_done(request('node.reboot'))
        self.assertEqual((entry['receipt']['status'], entry['receipt']['reason']), ('unknown', 'reboot_pending'))
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch', 'unknown'])

    def test_terminal_post_admission_write_error_is_not_retried(self):
        attempts = self.terminal_lease()
        write = self.store.write
        writes = []
        def failure(value):
            status = next(iter(value['operations'].values()))['receipt']['status']
            if status == 'succeeded':
                writes.append(status)
                raise OSError('private storage path or credential')
            return write(value)
        self.store.write = failure
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(attempts, [False])
        self.assertEqual(writes, ['succeeded'])
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertFalse(self.owner._loaded)
        self.assertIn('selected_status=succeeded selected_reason=none diagnostic=storage_unavailable',
                      diagnostic.call_args.args[1])
        self.assertNotIn('private', diagnostic.call_args.args[1])

    def test_terminal_post_commit_error_never_overwrites_success_or_replays(self):
        attempts = self.terminal_lease()
        write = self.store.write
        writes = []
        def uncertain(value):
            write(value)
            if next(iter(value['operations'].values()))['receipt']['status'] == 'succeeded':
                writes.append('succeeded')
                raise OSError('private post-rename fsync failure')
        self.store.write = uncertain
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            operation_id, entry = self.terminal_done()
        self.assertEqual(attempts, [False])
        self.assertEqual(writes, ['succeeded'])
        self.assertEqual(entry['receipt']['status'], 'succeeded')
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch', 'succeeded'])
        self.assertIn('diagnostic=storage_unavailable', diagnostic.call_args.args[1])
        self.assertFalse(self.owner._loaded)
        self.store.write = write
        self.assertEqual(self.actions.submit(request())[1]['operation_id'], operation_id)
        self.assertEqual(self.actions.operation(operation_id)[1]['status'], 'succeeded')
        self.assertEqual(len(self.dispatcher.calls), 1)

    def test_terminal_update_leasebusy_is_not_an_entry_retry(self):
        attempts = self.terminal_lease()
        update = self.owner._update
        updates = []
        def failure(operation_id, status, reason=None, **kwargs):
            if status == 'succeeded':
                updates.append(status)
                raise LeaseBusy()
            return update(operation_id, status, reason, **kwargs)
        self.owner._update = failure
        self.owner.sleep = Mock()
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(attempts, [False])
        self.assertEqual(updates, ['succeeded'])
        self.owner.sleep.assert_not_called()
        self.assertEqual(entry['receipt']['status'], 'running')
        self.assertIn('selected_status=succeeded selected_reason=none diagnostic=lease_invalid',
                      diagnostic.call_args.args[1])

    def test_terminal_release_error_is_not_an_entry_retry(self):
        attempts = self.terminal_lease(exit_error=LeaseBusy())
        self.owner.sleep = Mock()
        with patch('control.node_action_owner.syslog.syslog') as diagnostic:
            _, entry = self.terminal_done()
        self.assertEqual(attempts, [False])
        self.owner.sleep.assert_not_called()
        self.assertEqual(entry['receipt']['status'], 'succeeded')
        self.assertEqual([a['event'] for a in entry['audit']], ['accepted', 'dispatch', 'succeeded'])
        self.assertIn('diagnostic=lease_invalid', diagnostic.call_args.args[1])

    def test_new_stale_latch_or_unknown_owner_cannot_dispatch(self):
        for field, value, reason in [('generation', 8, 'stale_state'), ('boot', NEXT_BOOT, 'stale_state'),
                                     ('latched', True, 'hardware_unavailable'),
                                     ('latched', None, 'hardware_unavailable'),
                                     ('owned', False, 'observation_unavailable')]:
            old = getattr(self.identity, field)
            setattr(self.identity, field, value)
            with self.subTest(field=field, value=value):
                status, body = self.actions.submit(request())
                self.assertEqual((status, body['error']['code']), (409 if reason != 'observation_unavailable' else 503, reason))
            setattr(self.identity, field, old)
        self.assertEqual(self.dispatcher.calls, [])
        self.assertIsNone(self.store.value)

    def test_storage_write_failure_prevents_owner_mutation(self):
        self.store.fail = True
        self.assertEqual(self.actions.submit(request()), (503, {'error': {'code': 'storage_unavailable'}}))
        self.assertEqual(self.dispatcher.calls, [])

    def test_uncertain_post_rename_write_is_reloaded_before_same_key_retry(self):
        write = self.store.write
        first = True
        def uncertain(value):
            nonlocal first
            write(value)
            if first:
                first = False
                raise OSError('fsync uncertain')
        self.store.write = uncertain
        self.assertEqual(self.actions.submit(request())[0], 503)
        self.wait(lambda: not self.owner._busy)
        code, receipt = self.actions.submit(request())
        self.assertEqual((code, receipt['status']), (202, 'interrupted'))
        self.assertEqual(len(self.store.value['operations']), 1)
        self.assertEqual(self.dispatcher.calls, [])

    def test_stale_cas_rechecked_after_journal_and_before_dispatch(self):
        write = self.store.write
        def changed(value):
            write(value)
            self.identity.generation += 1
        self.store.write = changed
        status, receipt = self.actions.submit(request())
        self.assertEqual(status, 202)
        self.assertEqual(self.finished(receipt['operation_id'])['reason'], 'stale_state')
        self.assertEqual(self.dispatcher.calls, [])

    def test_pending_restart_is_interrupted_and_never_replayed_after_owner_restart(self):
        code, receipt = self.actions.submit(request())
        self.finished(receipt['operation_id'])
        self.owner.close()
        entry = self.store.value['operations'][receipt['operation_id']]
        entry['receipt']['status'] = 'running'
        entry['audit'] = entry['audit'][:2]
        restarted = self.make_owner()
        result = NodeActions(restarted).submit(request())
        self.assertEqual(result[0], 202)
        self.assertEqual(result[1]['status'], 'interrupted')
        self.assertEqual(len(self.dispatcher.calls), 1)

    def test_reboot_unknown_until_later_changed_boot_proof(self):
        status, receipt = self.actions.submit(request('node.reboot'))
        self.assertEqual(status, 202)
        self.assertEqual(self.finished(receipt['operation_id'])['status'], 'unknown')
        self.owner.close()
        self.identity.boot = NEXT_BOOT
        restarted = self.make_owner()
        result = NodeActions(restarted).operation(receipt['operation_id'])
        self.assertEqual(result[1]['status'], 'succeeded')
        self.assertEqual(len(self.dispatcher.calls), 1)

    def test_reboot_same_boot_restart_does_not_succeed_or_replay(self):
        status, receipt = self.actions.submit(request('node.reboot'))
        self.finished(receipt['operation_id'])
        self.owner.close()
        restarted = self.make_owner()
        self.assertEqual(NodeActions(restarted).operation(receipt['operation_id'])[1]['status'], 'unknown')
        restarted.close()
        self.identity.boot = NEXT_BOOT
        later = self.make_owner()
        self.assertEqual(NodeActions(later).operation(receipt['operation_id'])[1]['status'], 'succeeded')
        self.assertEqual(len(self.dispatcher.calls), 1)

    def test_one_outstanding_action_slot_receipt_get_and_replay_stay_cached(self):
        event = self.dispatcher.block = threading.Event()
        self.addCleanup(event.set)
        status, receipt = self.actions.submit(request())
        self.assertEqual(status, 202)
        self.wait(lambda: bool(self.dispatcher.calls))
        calls = self.identity.calls
        self.assertEqual(self.actions.operation(receipt['operation_id'])[0], 200)
        self.assertEqual(self.actions.submit(request())[0], 202)
        self.assertEqual(self.actions.submit(request(idempotency_key='other'))[0], 409)
        self.assertEqual(self.identity.calls, calls)
        event.set()
        self.finished(receipt['operation_id'])

    def test_timed_out_admission_does_not_dispatch_after_slow_journal(self):
        write = self.store.write
        def slow(value):
            time.sleep(.08)
            write(value)
        self.store.write = slow
        with self.assertRaises(NodeActionError) as raised:
            self.owner.accept(ActionRequest.parse(request()), deadline=time.monotonic()+.03)
        self.assertEqual(raised.exception.code, 'deadline_exceeded')
        self.wait(lambda: not self.owner._busy)
        self.assertEqual(self.dispatcher.calls, [])

    def test_inherited_boot_validation_is_audited_then_stale_cas_blocks_service_start(self):
        self.identity.latched, self.identity.latch_boot = True, NEXT_BOOT
        commands = []
        def command(argv, seconds):
            commands.append(argv)
            return 'LoadState=loaded\nActiveState=active\nSubState=running\nInvocationID='+('a'*32)+'\nMainPID=222\nJob=\n'
        dispatcher = FixedOwnerDispatcher(lambda: None, command=command, identity_reader=self.identity)
        def validate_inherited(request_, identity, lease, deadline):
            lease.validate()
            saved = next(iter(self.store.value['operations'].values()))
            self.assertEqual(saved['receipt']['status'], 'running')
            self.assertTrue(saved['dispatch_recorded'])
            self.identity.latched, self.identity.latch_boot = False, None
            self.identity.generation += 1
        dispatcher._validate_inherited_image = validate_inherited
        self.owner.dispatcher = dispatcher
        code, receipt = self.actions.submit(request('service.start', 'image'))
        self.assertEqual(code, 202)
        done = self.finished(receipt['operation_id'])
        self.assertEqual((done['status'], done['reason']), ('failed', 'stale_state'))
        self.assertTrue(all('show' in argv for argv in commands))
        # Same key remains the failed audited validation, never a service retry.
        self.assertEqual(self.actions.submit(request('service.start', 'image'))[1]['operation_id'], receipt['operation_id'])
        self.assertTrue(all('show' in argv for argv in commands))

    def test_same_boot_positive_never_reaches_hardware_prevalidation(self):
        self.identity.latched, self.identity.latch_boot = True, BOOT
        code, body = self.actions.submit(request('service.start'))
        self.assertEqual((code, body['error']['code']), (409, 'hardware_unavailable'))
        self.assertEqual(self.dispatcher.preflights, [])
        self.assertIsNone(self.store.value)

    def test_node_actions_require_allow_interrupt_even_for_reset_and_reboot(self):
        for action in ('service.stop', 'service.restart', 'gpu.reset', 'node.reboot'):
            self.assertEqual(self.actions.submit(request(action, allow_interrupt=False))[0], 409)
        self.assertEqual(self.dispatcher.calls, [])


class ActualManagerIntegrationTests(unittest.TestCase):
    """Actual Manager slot transitions; only Docker/storage/host I/O are fixtures."""
    def setUp(self):
        sys.path.insert(0, str(ROOT / 'tests/lifecycle'))
        from test_slots import SlotTests
        self.fixture = SlotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.initial = self.fixture.pair()
        for index, record in enumerate(self.fixture.docker.records):
            record['State'].update(Pid=111 + index, StartedAt='fixture-start-' + str(index))
        original_stop = self.fixture.docker.stop
        def stop(identity, *args, **kwargs):
            prior = self.fixture.docker.inspect(identity)['State']['StartedAt']
            original_stop(identity, *args, **kwargs)
            for record in self.fixture.docker.records:
                if record['Id'] == identity:
                    record['State'].update(Pid=0, StartedAt=prior)
        self.fixture.docker.stop = stop
        original_start = self.fixture.docker.start
        self.fixture_pid = 200
        def start(identity, *args, **kwargs):
            original_start(identity, *args, **kwargs)
            self.fixture_pid += 1
            for record in self.fixture.docker.records:
                if record['Id'] == identity:
                    record['State'].update(Pid=self.fixture_pid, StartedAt='restart-' + str(self.fixture_pid))
        self.fixture.docker.start = start
        self.store = Store()
        self.manager = self.fixture.manager
        self.lease_factory = partial(acquire_lease, system_root=self.fixture.root, trusted_uid=os.geteuid())
        def identity(request_, lease, deadline):
            lease.validate()
            slot = self.manager.read_state()['slots'][request_.lifecycle_target]
            return dict(boot_id=BOOT, generation=slot['generation'], canonical_generation=slot['generation'],
                        selected=slot['selected'], hardware_latched=False, ownership_valid=True,
                        affected_services=[request_.service_id],
                        owner_identity=service(request_.service_id)['owner_identity'])
        def service(service_id, seconds=2):
            slot = self.manager.read_state()['slots']['glm' if service_id == 'qwen-gpu0' else 'qwen']
            saved = slot.get('container')
            c = self.fixture.docker.inspect(saved['id']) if saved else None
            owner = None if c is None else dict(container_id=c['Id'], pid=c['State']['Pid'],
                                              started_at=c['State']['StartedAt'])
            return dict(boot_id=BOOT, ownership_valid=True, owner_identity=owner,
                        running=c['State']['Running'] if c else False)
        def settled(service_id, old, seconds):
            if old is None:
                return service(service_id)['owner_identity'] is None
            c = self.fixture.docker.inspect(old['container_id'])
            return (c is None or (c['State']['Running'] is False and c['State']['Pid'] == 0)
                    or (c['State']['StartedAt'] != old['started_at'] and c['State']['Pid'] != old['pid']))
        identity.service, identity.old_owner_settled = service, settled
        self.owner = ProductionNodeActionOwner(self.store, identity, FixedOwnerDispatcher(lambda: self.manager, identity_reader=identity),
                    lease_factory=self.lease_factory, boot_reader=lambda: BOOT)
        self.addCleanup(self.owner.close)
        self.wait(lambda: self.owner._loaded and not self.owner._busy)
        self.actions = NodeActions(self.owner)

    def wait(self, condition):
        until = time.monotonic() + 3
        while time.monotonic() < until:
            if condition():
                return
            time.sleep(.005)
        self.fail('actual Manager adapter fixture did not settle')

    def finished(self, receipt):
        operation_id = receipt['operation_id']
        self.wait(lambda: self.actions.operation(operation_id)[1]['status'] in {'failed', 'succeeded'})
        return self.actions.operation(operation_id)[1]

    def test_real_node_owner_fixed_adapter_manager_stop_borrows_lease_and_preserves_peer(self):
        from unittest.mock import patch
        payload = request('service.stop', expected_generation=self.initial['slots']['glm']['generation'])
        with patch('lifecycle.manager.acquire_lease', side_effect=AssertionError('second lifecycle lock')):
            code, receipt = self.actions.submit(payload)
            self.assertEqual(code, 202, receipt)
            done = self.finished(receipt)
        self.assertEqual(done['status'], 'succeeded', done)
        state = self.manager.read_state()
        self.assertEqual(state['slots']['glm']['desired'], 'stopped')
        self.assertEqual(state['slots']['qwen'], self.initial['slots']['qwen'])
        self.assertEqual(self.store.events, ['accepted', 'running', 'succeeded'])

    def test_real_manager_restart_success_proves_new_pid_start_and_preserves_peer(self):
        from unittest.mock import patch
        old_id = self.initial['slots']['glm']['container']['id']
        old = copy.deepcopy(self.fixture.docker.inspect(old_id)['State'])
        payload = request(expected_generation=self.initial['slots']['glm']['generation'])
        with patch('lifecycle.manager.acquire_lease', side_effect=AssertionError('second lifecycle lock')):
            code, receipt = self.actions.submit(payload)
            self.assertEqual(code, 202, receipt)
            done = self.finished(receipt)
        self.assertEqual(done['status'], 'succeeded', done)
        state = self.manager.read_state()
        self.assertEqual(state['slots']['qwen'], self.initial['slots']['qwen'])
        current = self.fixture.docker.inspect(state['slots']['glm']['container']['id'])['State']
        self.assertNotEqual((current['Pid'], current['StartedAt']), (old['Pid'], old['StartedAt']))
        self.assertEqual(self.store.events, ['accepted', 'running', 'succeeded'])

    def test_restart_preflight_source_failure_preserves_existing_running_target_and_peer(self):
        from unittest.mock import patch
        from lifecycle.runtime_io import LifecycleError
        payload = request(expected_generation=self.initial['slots']['glm']['generation'])
        with patch.object(self.manager, 'prepare_start', side_effect=LifecycleError('source_pin_changed')), \
                patch.object(self.manager, '_stop', wraps=self.manager._stop) as stop:
            code, receipt = self.actions.submit(payload)
            self.assertEqual(code, 202, receipt)
            done = self.finished(receipt)
            stop.assert_not_called()
        self.assertEqual(done['status'], 'failed')
        self.assertEqual(self.manager.read_state(), self.initial)


class FixedDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.lease = SimpleNamespace(validate=lambda: self.events.append('lease'))
        self.identity = Identity()(ActionRequest.parse(request()), self.lease, time.monotonic()+2)
        self.commands = []
        self.invocation = 'a' * 32
        self.state = 'failed'
        self.pid = 0
        self.job = ''
        self.dispatcher = FixedOwnerDispatcher(lambda: None, command=self.command)

    def command(self, argv, seconds):
        self.assertGreater(seconds, 0)
        self.commands.append(argv)
        if 'show' in argv:
            return 'LoadState=loaded\nActiveState='+self.state+'\nSubState=running\nInvocationID='+self.invocation+'\nMainPID='+str(self.pid)+'\nJob='+self.job+'\n'
        self.invocation = 'b' * 32
        self.state = 'inactive' if 'stop' in argv else 'active'
        self.pid = 0 if self.state == 'inactive' else 222
        return ''

    def test_failed_control_restart_uses_fixed_systemd_owner_no_control_http(self):
        request_ = ActionRequest.parse(request(service='control'))
        self.dispatcher.preflight(request_, self.identity, self.lease, time.monotonic()+2)
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertIn(['/usr/bin/systemctl', '--no-block', 'restart', 'llm-control.service'], self.commands)
        self.assertEqual(result['old']['llm-control.service']['ActiveState'], 'failed')
        self.assertFalse(any('llm-node.service' in command for command in self.commands))

    def test_image_stop_delegates_both_units_and_requires_backend_absence(self):
        request_ = ActionRequest.parse(request('service.stop', 'image'))
        self.dispatcher.identity_reader = lambda *a: self.identity
        self.dispatcher.identity_reader.old_owner_settled = lambda *a: True
        self.dispatcher.identity_reader.observe = lambda *a: dict(
            boot_id=BOOT, ownership_valid=True, running=False, backend_running=True, owner_identity=None)
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        with self.assertRaises(NodeActionError):
            self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertIn(['/usr/bin/systemctl', '--no-block', 'stop', 'llm-image-api.service', 'llm-image-backend.service'], self.commands)
        self.dispatcher.identity_reader.observe = lambda *a: dict(boot_id=BOOT, ownership_valid=True, running=False, backend_running=False, owner_identity=None)
        self.dispatcher.complete(request_, result, time.monotonic()+2)

    def test_image_start_waits_for_passive_owner_readiness_without_replaying_job(self):
        request_ = ActionRequest.parse(request('service.start', 'image'))
        self.dispatcher.identity_reader = lambda *a: self.identity
        observations = []
        def observe(*args):
            observations.append(args)
            if len(observations) == 1:
                raise ValueError('owner publication in progress')
            return dict(ownership_valid=True, running=True, ready=True)
        self.dispatcher.identity_reader.observe = observe
        self.dispatcher.sleep = lambda _: None
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertEqual(len(observations), 2)
        self.assertEqual(sum('start' in argv for argv in self.commands), 1)

    def image_restart_fixture(self, *, old_settled=True, current=None):
        old = dict(container_id='a' * 64, pid=111, started_at='old-start', run_id='a' * 32)
        self.identity = {**self.identity, 'owner_identity': old}
        self.dispatcher.identity_reader = lambda *a: self.identity
        proofs = []
        def settled(service_id, owner, seconds):
            proofs.append((service_id, owner))
            return old_settled
        self.dispatcher.identity_reader.old_owner_settled = settled
        self.dispatcher.identity_reader.observe = lambda *a: dict(boot_id=BOOT, ownership_valid=True,
            running=True, backend_running=True, ready=True, owner_identity=current or dict(
                container_id='b' * 64, pid=222, started_at='new-start', run_id='b' * 32))
        request_ = ActionRequest.parse(request('service.restart', 'image'))
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        return request_, result, proofs

    def test_image_api_restart_and_ready_replacement_cannot_hide_old_live_backend(self):
        request_, result, proofs = self.image_restart_fixture(old_settled=False)
        with self.assertRaises(NodeActionError) as raised:
            self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertEqual(raised.exception.code, 'observation_unavailable')
        self.assertEqual(proofs[0][1]['container_id'], 'a' * 64)
        self.assertEqual(sum('restart' in argv for argv in self.commands), 1)

    def test_image_restart_success_requires_independent_old_settlement_and_new_backend_invocation(self):
        request_, result, proofs = self.image_restart_fixture()
        self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertEqual(proofs, [('image', self.identity['owner_identity'])])
        self.assertEqual(sum('restart' in argv for argv in self.commands), 1)

    def test_restart_previously_absent_backend_captures_absence_before_start(self):
        self.identity = {**self.identity, 'owner_identity': None}
        self.dispatcher.identity_reader = lambda *a: self.identity
        proofs = []
        def settled(service_id, old, seconds):
            # The registered name becomes occupied once systemd restart runs.
            proofs.append((service_id, old))
            return not any('restart' in argv for argv in self.commands)
        self.dispatcher.identity_reader.old_owner_settled = settled
        self.dispatcher.identity_reader.observe = lambda *a: dict(boot_id=BOOT, ownership_valid=True,
            running=True, backend_running=True, ready=True, owner_identity=dict(
                container_id='b' * 64, pid=222, started_at='new-start', run_id='b' * 32))
        request_ = ActionRequest.parse(request('service.restart', 'image'))
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        self.assertTrue(result['old_absence_proven'])
        self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertEqual(proofs, [('image', None)])

    def test_restart_absent_metadata_but_nonempty_registered_names_refuses_before_dispatch(self):
        self.identity = {**self.identity, 'owner_identity': None}
        self.dispatcher.identity_reader = lambda *a: self.identity
        self.dispatcher.identity_reader.old_owner_settled = lambda *a: False
        with self.assertRaises(NodeActionError):
            self.dispatcher.dispatch(ActionRequest.parse(request('service.restart', 'image')),
                                     self.identity, self.lease, time.monotonic()+2)
        self.assertTrue(all('show' in argv for argv in self.commands))

    def test_image_restart_rejects_same_backend_pid_starttime_or_owner_invocation(self):
        variants = [dict(container_id='a' * 64, pid=111, started_at='new-start', run_id='b' * 32),
                    dict(container_id='a' * 64, pid=222, started_at='old-start', run_id='b' * 32),
                    dict(container_id='b' * 64, pid=222, started_at='new-start', run_id='a' * 32)]
        for current in variants:
            self.invocation, self.state, self.pid = 'a' * 32, 'active', 111
            request_, result, _ = self.image_restart_fixture(current=current)
            with self.assertRaises(NodeActionError):
                self.dispatcher.complete(request_, result, time.monotonic()+2)

    def test_control_stop_waits_for_main_pid_zero(self):
        request_ = ActionRequest.parse(request('service.stop', 'control'))
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        self.pid = 111  # unit status alone is insufficient settlement
        waits = []
        def settle(_):
            waits.append(True)
            self.pid = 0
        self.dispatcher.sleep = settle
        self.dispatcher.complete(request_, result, time.monotonic()+2)
        self.assertEqual(waits, [True])

    def test_image_inherited_validation_maps_collector_boot_age_to_owner_uptime(self):
        from unittest.mock import patch
        self.dispatcher.identity_reader = SimpleNamespace(binding=lambda seconds: object(),
            boot=lambda: dict(boot_id=BOOT, boot_age_seconds=150.25))
        identity = {**self.identity, 'hardware_latched': True, 'hardware_latched_boot_id': NEXT_BOOT}
        with patch('lifecycle.hardware_policy.HardwarePolicy') as policy:
            self.dispatcher._validate_inherited_image(ActionRequest.parse(request('service.start', 'image')),
                                                     identity, self.lease, time.monotonic()+2)
            self.assertEqual(policy.call_args.kwargs['boot'](), dict(boot_id=BOOT, uptime_seconds=150.25))

    def test_real_text_adapter_borrows_lease_and_preserves_canonical_slot_generation(self):
        calls = []
        manager = SimpleNamespace(run=lambda *a, **k: None, probe=lambda *a, **k: None,
            sglang_probe=lambda *a, **k: None, sleep=lambda _: None, docker=SimpleNamespace(),
            dispatch=lambda action, **kwargs: calls.append((action, kwargs)))
        self.dispatcher.manager_loader = lambda: manager
        self.dispatcher.identity_reader = lambda *a: self.identity
        self.dispatcher.identity_reader.service = lambda *a: dict(boot_id=BOOT, ownership_valid=True,
            running=False, owner_identity=None)
        self.dispatcher.identity_reader.old_owner_settled = lambda *a: True
        request_ = ActionRequest.parse(request('service.stop'))
        result = self.dispatcher.dispatch(request_, self.identity, self.lease, time.monotonic()+2)
        self.assertEqual(calls, [('stop', {'lease': self.lease, 'target': 'glm', 'expected_generation': 3})])
        self.assertEqual(result['kind'], 'manager')

    def test_reset_production_rejects_unproven_vm_scope_without_command(self):
        request_ = ActionRequest.parse(request('gpu.reset'))
        with self.assertRaises(NodeActionError) as raised:
            self.dispatcher.preflight(request_, self.identity, self.lease, time.monotonic()+2)
        self.assertEqual(raised.exception.code, 'reset_scope_unproven')
        self.assertEqual(self.commands, [])

    def proof(self):
        return dict(boot_id=BOOT, gpu_uuid=GPU, dedicated_scope=[GPU], supported=True,
                    os_consumers_complete=True, os_consumers=[], all_affected_services_stopped=True,
                    affected_services=[])

    def test_reset_requires_os_consumers_absent_all_affected_stopped_and_rechecks_scope(self):
        request_ = ActionRequest.parse(request('gpu.reset'))
        identity = {**self.identity, 'affected_services': []}
        for change in ({'os_consumers': [55]}, {'all_affected_services_stopped': False},
                       {'os_consumers_complete': False}, {'supported': False},
                       {'dedicated_scope': [GPU, 'peer']}, {'boot_id': NEXT_BOOT}):
            self.dispatcher.reset_proof = lambda *a, change=change: {**self.proof(), **change}
            with self.assertRaises(NodeActionError):
                self.dispatcher.dispatch(request_, identity, self.lease, time.monotonic()+2)
        self.assertEqual(self.commands, [])
        self.dispatcher.reset_proof = lambda *a: self.proof()
        self.dispatcher.dispatch(request_, identity, self.lease, time.monotonic()+2)
        self.assertEqual(self.commands, [['/usr/bin/nvidia-smi', '--gpu-reset', '-i', GPU]])

    def test_reset_error_never_retries_globally(self):
        self.dispatcher.reset_proof = lambda *a: self.proof()
        def fail(argv, seconds):
            self.commands.append(argv)
            raise ValueError('driver requires peer reset')
        self.dispatcher.command = fail
        with self.assertRaises(ValueError):
            self.dispatcher.dispatch(ActionRequest.parse(request('gpu.reset')),
                    {**self.identity, 'affected_services': []}, self.lease, time.monotonic()+2)
        self.assertEqual(self.commands, [['/usr/bin/nvidia-smi', '--gpu-reset', '-i', GPU]])

    def test_final_systemd_dispatch_rechecks_generation_after_observation(self):
        self.dispatcher.identity_reader = lambda *a: {**self.identity, 'generation': 8}
        with self.assertRaises(NodeActionError) as raised:
            self.dispatcher.dispatch(ActionRequest.parse(request(service='control')),
                                     self.identity, self.lease, time.monotonic()+2)
        self.assertEqual(raised.exception.code, 'stale_state')
        self.assertTrue(all('show' in command for command in self.commands))

    def test_reboot_only_fixed_orderly_self_command(self):
        result = self.dispatcher.dispatch(ActionRequest.parse(request('node.reboot')),
                                         self.identity, self.lease, time.monotonic()+2)
        self.assertEqual(self.commands, [['/usr/bin/systemctl', '--no-block', 'reboot']])
        self.assertEqual(result['kind'], 'reboot')

    def test_registered_journal_never_falls_back_when_registered_storage_unavailable(self):
        def missing():
            raise OSError('model mount misbound')
        store = RegisteredNodeStore(missing)
        with self.assertRaises(OSError):
            store.read()
        with self.assertRaises(OSError):
            store.write({})

    def test_journal_rejects_unknown_schema_and_secret_fields(self):
        for value in ({'schema_version': True, 'operations': {}},
                      {'schema_version': 1, 'operations': {}, 'api_key': 'secret'},
                      {'schema_version': 1, 'operations': {'x': {'command': 'arbitrary'}}}):
            with self.assertRaises(NodeActionError):
                validated_journal(value)


if __name__ == '__main__':
    unittest.main()
