"""Bounded passive control readiness; local fixtures only, no VM or inference."""

from contextlib import ExitStack
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from control import node_collectors, node_observation as n, serve
from control.core import Application
from control.journal import empty_state
from tests.test_control_http_transport import RunningServer

BOOT = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'
OTHER_BOOT = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
IDENTITY = dict(boot_id=BOOT, invocation_id='a' * 32, main_pid=1234)
RESPONSE = dict(schema_version=1, service_id='control', readiness_kind='process_api',
                ready=True, **IDENTITY)
FIXTURE_KEY = b'local-fixture-control-key-only-123456'


class HandlerTests(unittest.TestCase):
    def application(self, identity=IDENTITY):
        self.backend = Mock()
        self.journal = Mock()
        self.journal.read.return_value = empty_state()
        self.lease = Mock(side_effect=AssertionError('lifecycle forbidden'))
        app = Application(self.backend, self.journal, lease_factory=self.lease,
                          readiness_identity=identity)
        self.addCleanup(app.close)
        self.journal.reset_mock()
        return app

    def test_passive_handler_cached_identity_has_no_owner_or_io_side_effects(self):
        identity = dict(IDENTITY)
        app = self.application(identity)
        identity['main_pid'] = 9876
        with ExitStack() as stack:
            forbidden = []
            for name in ('_read', '_try_refresh', '_reconcile', '_fresh', '_submit'):
                forbidden.append(stack.enter_context(patch.object(app, name,
                    side_effect=AssertionError('owner forbidden'))))
            for name in ('pathlib.Path.read_text', 'pathlib.Path.read_bytes',
                         'builtins.open', 'socket.create_connection',
                         'http.client.HTTPConnection', 'control.adapter.load_manager',
                         'control.adapter.recovery_manager', 'control.node_observation.native_get'):
                forbidden.append(stack.enter_context(patch(name,
                    side_effect=AssertionError('I/O forbidden'))))
            code, body = app.handle('GET', '/control/v1/readiness', {}, b'')
            self.assertEqual((code, body), (200, RESPONSE))
            body['main_pid'] = 7777
            self.assertEqual(app.handle('GET', '/control/v1/readiness', {}, b''), (200, RESPONSE))
            for operation in forbidden:
                operation.assert_not_called()
        self.backend.assert_not_called()
        self.assertEqual(self.backend.mock_calls, [])
        self.assertEqual(self.journal.mock_calls, [])
        self.lease.assert_not_called()

    def test_unavailable_and_closed_are_truthful(self):
        app = self.application(None)
        self.assertEqual(app.handle('GET', '/control/v1/readiness', {}, b''),
                         (503, {'error': {'code': 'observation_unavailable'}}))
        app._closed = True
        self.assertEqual(app.handle('GET', '/control/v1/readiness', {}, b''),
                         (503, {'error': {'code': 'service_closed'}}))

    def test_authenticated_actual_http_route_and_exact_path(self):
        app = self.application()
        app.release = threading.Event()  # Existing local server cleanup seam.
        server = RunningServer(app)
        self.addCleanup(server.close)
        for headers in ({}, {'Authorization': 'Bearer invalid-fixture'}):
            self.assertEqual(server.request(path='/control/v1/readiness', auth=False,
                                            headers=headers)[0], 401)
        status, headers, body = server.request(path='/control/v1/readiness')
        self.assertEqual((status, json.loads(body)), (200, RESPONSE))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        for method, path in (('GET', '/control/v1/readiness?x=1'),
                             ('GET', '/control/v1/readiness/'),
                             ('POST', '/control/v1/readiness')):
            status, _, _ = server.request(method, path, body=b'{}' if method == 'POST' else None)
            self.assertEqual(status, 404)
        self.assertEqual(server.request(path='/control/v1/readiness', body=b'{}')[0], 400)
        self.assertEqual(self.backend.mock_calls, [])
        self.assertEqual(self.journal.mock_calls, [])


class StartupIdentityTests(unittest.TestCase):
    def test_identity_is_read_once_at_startup(self):
        with patch.object(serve.Path, 'read_text', return_value=BOOT + '\n') as read, \
                patch.dict(serve.os.environ, {'INVOCATION_ID': IDENTITY['invocation_id']}), \
                patch.object(serve.os, 'getpid', return_value=1234) as pid:
            self.assertEqual(serve.startup_identity(), IDENTITY)
            read.assert_called_once_with()
            pid.assert_called_once_with()

    def test_missing_or_malformed_startup_identity_fails_closed(self):
        for boot, invocation, pid in ((OTHER_BOOT.upper(), 'a' * 32, 1234),
                ('not-a-boot', 'a' * 32, 1234), (BOOT, '', 1234),
                (BOOT, 'A' * 32, 1234), (BOOT, 'a' * 31, 1234),
                (BOOT, 'a' * 32, 0), (BOOT, 'a' * 32, True)):
            with self.subTest(boot=boot, invocation=invocation, pid=pid), \
                    patch.object(serve.Path, 'read_text', return_value=boot), \
                    patch.dict(serve.os.environ, {'INVOCATION_ID': invocation}), \
                    patch.object(serve.os, 'getpid', return_value=pid), \
                    self.assertRaises(ValueError):
                serve.startup_identity()


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.unit = dict(Id='llm-control.service', ActiveState='active', SubState='running',
                         InvocationID=IDENTITY['invocation_id'], MainPID='1234')
        self.run = Mock(side_effect=lambda *_: '\n'.join(f'{k}={v}' for k, v in self.unit.items()))
        self.boot = Mock(return_value={'boot_id': BOOT})
        self.storage = Mock(side_effect=AssertionError('storage or secret read forbidden'))
        self.reader = n.CanonicalIdentityReader(run=self.run, boot=self.boot,
                binding=self.storage, read=self.storage, latch=self.storage)
        self.get = Mock(return_value=(200, copy.deepcopy(RESPONSE)))

    def collect(self, **kwargs):
        return n.PassiveServiceCollector('control', self.reader, get=self.get,
                                         control_key=FIXTURE_KEY, **kwargs)(2)

    def assert_unknown(self, row):
        self.assertIsNone(row['ready'])
        self.assertIsNone(row['admitting'])
        self.assertEqual(row['activity'], 'unknown')
        self.assertIsNone(row['queue_depth'])
        self.assertIsNone(row['active_requests'])
        self.storage.assert_not_called()

    def test_valid_authenticated_response_rechecks_native_identity_without_storage(self):
        row = self.collect()
        self.assertIs(row['ready'], True)
        self.assertIsNone(row['admitting'])
        self.assertIsNone(row['queue_depth'])
        self.assertIsNone(row['active_requests'])
        self.assertEqual(row['activity'], 'unknown')
        self.assertEqual(self.get.call_args.args[:2], (30000, '/control/v1/readiness'))
        self.assertIs(self.get.call_args.args[2], FIXTURE_KEY)
        self.assertGreater(self.get.call_args.args[3], 0)
        self.assertLessEqual(self.get.call_args.args[3], 2)
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(self.boot.call_count, 2)
        self.storage.assert_not_called()

    def test_refused_timeout_malformed_and_unauthorized_are_unknown(self):
        for failure in (ConnectionRefusedError(), TimeoutError(), ValueError('malformed')):
            with self.subTest(failure=type(failure).__name__):
                self.get.side_effect = failure
                self.assert_unknown(self.collect())
        self.get.side_effect = None
        for status, body in ((401, {}), (503, {'error': {'code': 'service_closed'}}),
                             (200, None), (200, {'ready': True}), (200, [])):
            with self.subTest(status=status, body=body):
                self.get.return_value = status, body
                self.assert_unknown(self.collect())

    def test_exact_schema_marker_types_and_stale_response_rejected(self):
        changes = ({'schema_version': True}, {'schema_version': 2}, {'ready': None},
            {'ready': False}, {'ready': 1}, {'service_id': 'node'},
            {'readiness_kind': 'model'}, {'main_pid': True}, {'main_pid': '1234'},
            {'main_pid': 0}, {'main_pid': 2345}, {'boot_id': OTHER_BOOT},
            {'invocation_id': 'b' * 32}, {'invocation_id': ''}, {'extra': True})
        for update in changes:
            with self.subTest(update=update):
                self.get.return_value = 200, {**RESPONSE, **update}
                self.assert_unknown(self.collect())
        for missing in RESPONSE:
            with self.subTest(missing=missing):
                value = dict(RESPONSE)
                del value[missing]
                self.get.return_value = 200, value
                self.assert_unknown(self.collect())

    def test_changed_unit_or_boot_after_success_remains_unknown(self):
        for change in ({'InvocationID': 'b' * 32}, {'MainPID': '2345'},
                       {'ActiveState': 'inactive'}):
            original = dict(self.unit)
            def change_during_get(*_):
                self.unit.update(change)
                return 200, dict(RESPONSE)
            with self.subTest(change=change):
                self.get.side_effect = change_during_get
                self.assert_unknown(self.collect())
            self.unit = original
        self.get.side_effect = None
        self.boot.side_effect = [{'boot_id': BOOT}, {'boot_id': OTHER_BOOT}]
        self.assert_unknown(self.collect())

    def test_stopped_control_is_false_without_probe(self):
        self.unit.update(ActiveState='inactive', MainPID='0', InvocationID='')
        row = self.collect()
        self.assertIs(row['ready'], False)
        self.get.assert_not_called()
        self.storage.assert_not_called()

    def test_missing_key_and_unknown_unit_cannot_be_ready(self):
        row = n.PassiveServiceCollector('control', self.reader, get=self.get)(2)
        self.assert_unknown(row)
        self.get.assert_not_called()
        self.run.side_effect = TimeoutError()
        self.assert_unknown(self.collect())
        self.get.assert_not_called()

    def test_node_special_case_does_not_probe(self):
        self.unit['Id'] = 'llm-node.service'
        row = n.PassiveServiceCollector('node', self.reader, get=self.get,
                                       control_key=FIXTURE_KEY)(2)
        self.assert_unknown(row)
        self.get.assert_not_called()

    def test_probe_and_post_identity_share_one_budget(self):
        now = [0.0]
        self.reader.clock = lambda: now[0]
        def get(*_):
            now[0] = 0.75
            return 200, dict(RESPONSE)
        self.get.side_effect = get
        row = self.collect(clock=lambda: now[0])
        self.assertIs(row['ready'], True)
        self.assertEqual(self.get.call_args.args[3], 2)
        self.assertEqual(self.run.call_args.args[1], 1.25)
        now[0] = 0.0
        self.run.reset_mock()
        def expire(*_):
            now[0] = 2.01
            return 200, dict(RESPONSE)
        self.get.side_effect = expire
        self.assert_unknown(self.collect(clock=lambda: now[0]))
        self.assertEqual(self.run.call_count, 1)

    def test_production_callbacks_pass_validated_key_only_to_control(self):
        with patch.object(n, 'PassiveServiceCollector') as collector:
            node_collectors.production_callbacks(self.reader, control_key=FIXTURE_KEY)
        calls = {call.args[0]: call for call in collector.call_args_list}
        self.assertIs(calls['control'].kwargs['control_key'], FIXTURE_KEY)
        for service, call in calls.items():
            if service != 'control':
                self.assertIsNone(call.kwargs.get('control_key'))


if __name__ == '__main__':
    unittest.main()
