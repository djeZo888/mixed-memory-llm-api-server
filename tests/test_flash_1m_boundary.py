"""Offline 1M admission/allocation gates with ASGI and GPU stubs, no native claims."""
import asyncio
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/runtime/flash'))
import file_auth
import idle


class JsonResponseStub:
    def __init__(self, content, status_code=200):
        self.content, self.status_code = content, status_code

    async def __call__(self, scope, receive, send):
        await send({'type': 'http.response.start', 'status': self.status_code})
        await send({'type': 'http.response.body', 'body': json.dumps(self.content).encode()})


class Admission(unittest.TestCase):
    def request(self, count, *, route='/v1/chat/completions', output=8,
                output_field='max_tokens', auth=True):
        payload = {'model': 'glm-5.3-flash', 'messages': [{'role': 'user', 'content': 'synthetic'}]}
        if output is not None:
            payload[output_field] = output
        sent, admitted = [], []

        async def app(scope, receive, send):
            admitted.append(json.loads((await receive())['body']))
            await send({'type': 'http.response.start', 'status': 200})

        async def receive():
            return {'type': 'http.request', 'body': json.dumps(payload).encode(), 'more_body': False}

        async def send(event):
            sent.append(event)

        middleware = file_auth.ContractMiddleware(app, key=b'fixture-key',
            server=types.SimpleNamespace(app=types.SimpleNamespace(
                state=types.SimpleNamespace(openai_serving_chat=object()))), request_type=object)
        scope = {'type': 'http', 'method': 'POST', 'path': route,
                 'headers': [(b'authorization', b'Bearer fixture-key' if auth else b'Bearer wrong')]}
        # Native token counting is tested separately; this fixture controls only its result.
        with mock.patch.object(file_auth, 'count_native', return_value={'count': count}), \
                mock.patch.dict(sys.modules, {'starlette.responses':
                    types.SimpleNamespace(JSONResponse=JsonResponseStub)}):
            asyncio.run(middleware(scope, receive, send))
        return sent[0]['status'], admitted

    def test_input_and_combined_margins_on_both_routes(self):
        for route in ['/v1/tokenize', '/v1/chat/completions']:
            for count, output, expected in [(1048569, 5, 200), (1048570, 1, 400),
                    (1048569, 6, 400), (1000000, 1024, 200),
                    (983038, 65536, 200), (983039, 65536, 400)]:
                with self.subTest(route=route, count=count, output=output):
                    status, admitted = self.request(count, route=route, output=output)
                    self.assertEqual(status, expected)
                    self.assertEqual(bool(admitted), expected == 200)

    def test_output_ceiling_and_alias_are_unchanged(self):
        for field in ['max_tokens', 'max_completion_tokens']:
            for output, expected in [(65536, 200), (65537, 400), (0, 400), (True, 400)]:
                with self.subTest(field=field, output=output):
                    self.assertEqual(self.request(10, output=output, output_field=field)[0], expected)

    def test_default_output_is_reserved_and_auth_remains_closed(self):
        status, admitted = self.request(983038, output=None)
        self.assertEqual(status, 200)
        self.assertEqual(admitted[0]['max_tokens'], 65536)
        self.assertEqual(self.request(983039, output=None)[0], 400)
        self.assertEqual(self.request(10, auth=False), (401, []))


class Allocation(unittest.TestCase):
    def scheduler(self, native):
        context, pool, req_len, input_len = native

        class Scheduler:
            def __init__(self):
                self.server_args = types.SimpleNamespace(tp_size=1, pp_size=1, dp_size=1,
                    disable_overlap_schedule=True, disaggregation_mode='null')
                self.input_blocker = self.recv_skipper = None
                self.enable_hisparse = self.enable_hierarchical_cache = False
                self.model_config = types.SimpleNamespace(context_len=context)
                self.max_total_num_tokens = pool
                self.max_req_len, self.max_req_input_len = req_len, input_len

            def run_batch(self):
                pass

        idle.install(types.SimpleNamespace(Scheduler=Scheduler))
        return Scheduler

    def test_old_and_partial_allocations_fail_before_device_work(self):
        for native in [(480000, 480000, 479999, 479994),
                (1048576, 480000, 1048575, 1048570),
                (1048576, 1048576, 1048574, 1048570),
                (1048576, 1048576, 1048575, 1048569)]:
            with self.subTest(native=native), \
                    mock.patch.dict(sys.modules, {'torch': types.SimpleNamespace()}):
                with self.assertRaisesRegex(RuntimeError, 'flash_native_allocation_mismatch'):
                    self.scheduler(native)()

    def test_exact_allocation_reaches_existing_device_guard(self):
        # Deliberately stop at the first device check; this is not GPU qualification.
        class DeviceGuardReached(Exception):
            pass
        capability = mock.Mock(side_effect=DeviceGuardReached)
        torch = types.SimpleNamespace(cuda=types.SimpleNamespace(get_device_capability=capability))
        with mock.patch.dict(sys.modules, {'torch': torch}):
            with self.assertRaises(DeviceGuardReached):
                self.scheduler((1048576, 1048576, 1048575, 1048570))()
        capability.assert_called_once_with()


class Profile(unittest.TestCase):
    def test_pending_profile_keeps_pins_policies_and_historical_rollback(self):
        directory = Path(__file__).resolve().parents[1] / 'configs/deployments'
        old = json.loads((directory / 'glm-5.3-flash-480000-fp8-kt.json').read_text())
        new = json.loads((directory / 'glm-5.3-flash-1048576-fp8-kt.json').read_text())
        self.assertEqual(old['launch']['context_length'], 480000)
        self.assertEqual(new['launch']['context_length'], 1048576)
        self.assertEqual(new['launch']['max_total_tokens'], 1048576)
        for key in ('model', 'runtime', 'endpoint', 'gpu_uuid', 'request_policy', 'memory_policy', 'cpu_policy'):
            self.assertEqual(old[key], new[key], key)
        for key, value in old['launch'].items():
            if key not in ('context_length', 'max_total_tokens'):
                self.assertEqual(new['launch'][key], value, key)
        self.assertEqual(new['request_policy']['max_output_tokens'], 65536)
        self.assertEqual(new['native_usable_bounds']['input_tokens_max'], 1048576 - 7)
        self.assertEqual(new['native_usable_bounds']['input_plus_requested_output_max'], 1048576 - 2)
        self.assertEqual(new['acceptance_plan']['qualification'], 'PENDING_ACTUAL_H012_ATTEMPT02_VERIFIED_PASS')
        self.assertEqual(new['acceptance_plan']['required_input_tokens'], 1000000)
        self.assertIn('PENDING', new['status'])


if __name__ == '__main__':
    unittest.main()
