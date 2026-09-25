"""H005 typed boundary plus synthetic durable-owner behavior, no VM mutation.

The fixture owner is not a canonical production owner or acceptance evidence.
It models its required ordering so the boundary cannot fabricate success,
perform dispatch, invent idempotency, or repair missing durable receipts.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from control.node_actions import ActionRequest, DurableReceipt, NodeActions, NodeActionError

FIXTURES = ROOT / 'tests/fixtures/service_resilience'


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class FixtureOwner:
    """Tiny local file fixture; DOES NOT replace the production lease/journal."""
    def __init__(self, path, clock):
        self.path, self.clock = path, clock
        self.records = json.loads(path.read_text()) if path.exists() else {}
        self.boot = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'
        self.generation = 7
        self.events = []

    def accept(self, request, *, deadline):
        self.events.append('owner_enter')
        if self.clock() >= deadline:
            raise NodeActionError('deadline_exceeded')
        saved = self.records.get(request.idempotency_key)
        if saved:
            if saved['request'] != request.wire():
                raise NodeActionError('idempotency_conflict')
            self.events.append('replay')
            return DurableReceipt(copy.deepcopy(saved['receipt']), True)
        self.events.append('fixture_lease_check')
        if self.boot != request.expected_boot_id or self.generation != request.expected_generation:
            raise NodeActionError('stale_state')
        receipt = json.loads((FIXTURES / 'node-operation-v1.json').read_text())
        receipt.update(action=request.action, service_id=request.service_id,
                       affected_services=[request.service_id])
        self.records[request.idempotency_key] = {'request': request.wire(), 'receipt': receipt}
        self.path.write_text(json.dumps(self.records))
        self.events.append('durable_fixture_write')
        self.events.append('dispatch_once')
        return DurableReceipt(copy.deepcopy(receipt), True)

    def operation(self, operation_id, *, deadline):
        self.events.append('cached_receipt_read')
        for saved in self.records.values():
            if saved['receipt']['operation_id'] == operation_id:
                return DurableReceipt(copy.deepcopy(saved['receipt']), True)
        raise NodeActionError('operation_unknown')


class NodeActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.owner = FixtureOwner(Path(self.temp.name) / 'synthetic-owner.json', self.clock)
        self.actions = NodeActions(self.owner, monotonic=self.clock)
        self.request = json.loads((FIXTURES / 'node-action-v1.json').read_text())

    def test_fixture_envelope_maps_current_placement_without_model_switch(self):
        request = ActionRequest.parse(self.request)
        self.assertEqual(request.lifecycle_target, 'glm')
        self.assertEqual(request.wire(), self.request)
        other = ActionRequest.parse({**self.request, 'service_id': 'qwen-gpu1'})
        self.assertEqual(other.lifecycle_target, 'qwen')
        self.assertNotIn('deployment_id', other.wire())
        code, receipt = self.actions.submit(self.request)
        self.assertEqual(code, 202)
        self.assertEqual(receipt, json.loads((FIXTURES / 'node-operation-v1.json').read_text()))
        self.assertEqual(self.owner.events, ['owner_enter', 'fixture_lease_check',
                                            'durable_fixture_write', 'dispatch_once'])

    def test_default_constructed_boundary_accepts_no_action(self):
        for action in ('service.start', 'service.stop', 'service.restart'):
            code, result = NodeActions().submit({**self.request, 'action': action})
            self.assertEqual((code, result['error']['code']), (422, 'unsupported_action'))
        self.assertEqual(NodeActions().operation('0' * 32)[0], 404)

    def test_reset_reboot_image_control_remain_unsupported_even_with_owner(self):
        payloads = [{**self.request, 'service_id': value} for value in ('image', 'control')]
        for action in ('gpu.reset', 'node.reboot'):
            payload = {name: value for name, value in self.request.items() if name != 'service_id'}
            payload['action'] = action
            if action == 'gpu.reset':
                payload['gpu_uuid'] = 'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'
            payloads.append(payload)
        for payload in payloads:
            self.assertEqual(self.actions.submit(payload), (422, {'error': {'code': 'unsupported_action'}}))
        self.assertEqual(self.owner.events, [])

    def test_rejects_unknown_fields_targets_boolean_impostors_and_arbitrary_commands(self):
        changes = [{'schema_version': True}, {'schema_version': 2}, {'node_id': 'ai-harness'},
                   {'action': 'exec'}, {'service_id': 'glm'}, {'service_id': 'qwen-gpu2'},
                   {'expected_generation': True}, {'expected_generation': -1},
                   {'expected_generation': 2**63}, {'expected_generation': None},
                   {'expected_boot_id': None}, {'expected_boot_id': 'old'},
                   {'allow_interrupt': 1}, {'idempotency_key': ''},
                   {'idempotency_key': 'a' * 129}, {'idempotency_key': 'bad\nkey'},
                   {'command': 'reboot'}, {'unit': 'docker'}, {'path': '/run/a'},
                   {'url': 'http://127.0.0.1'}, {'gpu_uuid': None}, {'deployment_id': 'other'}]
        payloads = [{**self.request, **change} for change in changes]
        payloads += [{key: value for key, value in self.request.items() if key != missing}
                     for missing in self.request]
        payloads += [None, [], 'service.restart', True]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.actions.submit(payload)[0], 400)
        self.assertEqual(self.owner.events, [])

    def test_stop_and_restart_require_explicit_interruption_confirmation(self):
        for action in ('service.stop', 'service.restart'):
            self.assertEqual(self.actions.submit({**self.request, 'action': action, 'allow_interrupt': False}),
                             (409, {'error': {'code': 'interruption_ack_required'}}))
        self.assertEqual(self.owner.events, [])
        code, _ = self.actions.submit({**self.request, 'action': 'service.start', 'allow_interrupt': False})
        self.assertEqual(code, 202)

    def test_owner_exact_repeat_survives_changed_boot_generation_and_restart_without_dispatch(self):
        first = self.actions.submit(self.request)
        self.owner.boot = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        self.owner.generation = 99
        self.assertEqual(self.actions.submit(self.request), first)
        self.assertEqual(self.owner.events.count('dispatch_once'), 1)
        restarted = FixtureOwner(self.owner.path, self.clock)
        restarted.boot, restarted.generation = self.owner.boot, self.owner.generation
        actions = NodeActions(restarted, monotonic=self.clock)
        self.assertEqual(actions.submit(self.request), first)
        self.assertEqual(restarted.events, ['owner_enter', 'replay'])
        code, receipt = actions.operation(first[1]['operation_id'])
        self.assertEqual((code, receipt), (200, first[1]))
        self.assertEqual(restarted.events[-1], 'cached_receipt_read')

    def test_owner_idempotency_mismatch_and_stale_boot_or_generation_fail_before_dispatch(self):
        self.actions.submit(self.request)
        changed = {**self.request, 'action': 'service.stop'}
        self.assertEqual(self.actions.submit(changed), (409, {'error': {'code': 'idempotency_conflict'}}))
        for change in ({'expected_boot_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'},
                       {'expected_generation': 8}):
            payload = {**self.request, 'idempotency_key': 'new-request', **change}
            self.assertEqual(self.actions.submit(payload), (409, {'error': {'code': 'stale_state'}}))
        self.assertEqual(self.owner.events.count('dispatch_once'), 1)

    def test_no_accepted_response_without_owner_attesting_valid_durable_receipt(self):
        valid = json.loads((FIXTURES / 'node-operation-v1.json').read_text())
        variants = [DurableReceipt(valid, False), valid, None]
        for changes in ({'operation_id': 'bad'}, {'poll_url': 'https://external.invalid/'},
                        {'status': 'scheduled'}, {'service_id': 'qwen-gpu1'},
                        {'expected_boot_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'},
                        {'expected_generation': True}, {'affected_services': ['qwen-gpu0', 'qwen-gpu1']},
                        {'reason': 'unreviewed'}, {'created_at': '2026-09-25T16:10:00'},
                        {'credential': 'private-fixture'}):
            variants.append(DurableReceipt({**valid, **changes}, True))
        for result in variants:
            self.owner.accept = lambda request, deadline, result=result: result
            with self.subTest(result=result):
                code, body = self.actions.submit(self.request)
                self.assertEqual(code, 503)
                self.assertNotIn('operation_id', body)
                self.assertNotIn('private-fixture', json.dumps(body))

    def test_deadline_is_forwarded_and_late_reply_never_fabricates_cancellation_or_acceptance(self):
        def late(request, *, deadline):
            self.assertEqual(deadline, 102.0)
            self.clock.now = deadline
            return DurableReceipt(json.loads((FIXTURES / 'node-operation-v1.json').read_text()), True)
        self.owner.accept = late
        self.assertEqual(self.actions.submit(self.request), (503, {'error': {'code': 'deadline_exceeded'}}))
        # A timeout is uncertain, not cancellation. Retry same key or poll the
        # owner receipt; this boundary never starts another execution itself.
        self.assertEqual(self.owner.events, [])

    def test_owner_failure_is_sanitized_and_receipt_get_never_submits(self):
        def fail(request, *, deadline):
            raise RuntimeError('private-fixture-credential')
        self.owner.accept = fail
        self.assertEqual(self.actions.submit(self.request), (503, {'error': {'code': 'owner_unavailable'}}))
        self.assertEqual(self.actions.operation('../receipt')[0], 404)
        self.assertEqual(self.actions.operation('a' * 32)[0], 404)
        self.assertEqual(self.owner.events, ['cached_receipt_read'])


if __name__ == '__main__':
    unittest.main()
