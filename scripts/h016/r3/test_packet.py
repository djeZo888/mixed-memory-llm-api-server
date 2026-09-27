"""Focused H016 canonical payload, deadline and blocking-guard tests; no VM access."""
import copy
import json
import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import private_proxy as proxy
import benchmark


class PacketTests(unittest.TestCase):
    def canonical(self):
        p = benchmark.body('Test', output=65536)
        p['messages'] = [{'role': 'developer', 'content': 'Keep rules'}, {'role': 'user', 'content': [{'type': 'text', 'text': 'Call tool'}]}, {'role': 'assistant', 'content': None, 'reasoning_content': 'reason', 'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': 'nested', 'arguments': '{"a":{"b":3}}'}}]}, {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'ok'}]
        p['tools'] = [{'type': 'function', 'function': {'name': 'nested', 'description': 'nested input', 'strict': True, 'parameters': {'type': 'object', 'properties': {'a': {'type': 'object', 'properties': {'b': {'type': 'integer'}}, 'additionalProperties': False}}, 'required': ['a'], 'additionalProperties': False}}}]
        return p

    def test_canonical_deep_structure_unchanged(self):
        p = self.canonical()
        before = json.dumps(p, separators=(',', ':'), ensure_ascii=False)
        self.assertIs(proxy.normalize(p), p)
        self.assertEqual(before, json.dumps(p, separators=(',', ':'), ensure_ascii=False))
        self.assertTrue(p['tools'][0]['function']['strict'])

    def test_65536_ceiling_and_tool2048_and_benchmark256(self):
        for cap in [256, 2048, 65536]:
            self.assertEqual(proxy.normalize(benchmark.body('x', output=cap))['max_tokens'], cap)
        for cap in [0, -1, True, 65537]:
            with self.assertRaises(ValueError):
                proxy.normalize(benchmark.body('x', output=cap))

    def test_no_unknown_renderer_or_media(self):
        for change in [{'reasoning_format': 'none'}, {'add_generation_prompt': False}, {'model': 'glm-5.3-flash'}, {'store': False}, {'reasoning_effort': 'none'}, {'max_completion_tokens': 100}, {'chat_template_kwargs': {'enable_thinking': False, 'clear_thinking': True}}]:
            with self.assertRaises(ValueError):
                proxy.normalize({**benchmark.body('x'), **change})
        p = benchmark.body('x')
        p['messages'][0]['content'] = [{'type': 'image_url', 'image_url': 'file:///x'}]
        with self.assertRaises(ValueError):
            proxy.normalize(p)

    def test_fixed_route_allowlist(self):
        self.assertEqual(proxy.ROUTES, {('POST', '/v1/chat/completions'), ('POST', '/v1/chat/completions/input_tokens'), ('GET', '/props'), ('GET', '/slots'), ('GET', '/v1/readiness')})
        self.assertNotIn(('GET', '/slots?debug=1'), proxy.ROUTES)

    def test_guard_interrupts_blocked_socket_without_stream_bytes(self):
        code = '''import socket,signal,threading,time,json
from candidate_owner import interrupted
from telemetry import interrupt_owner
signal.signal(signal.SIGTERM, interrupted)
a,b=socket.socketpair(); a.settimeout(7200)
threading.Timer(.1,interrupt_owner).start()
start=time.monotonic(); settled=False
try:
 a.recv(1)
except RuntimeError as e:
 assert str(e)=='owned_supervisor_interrupted'
finally:
 # The production same-owner finally invokes exact-container settle(), not socket inference.
 settled=True; a.close();b.close()
print(json.dumps({'elapsed':time.monotonic()-start,'same_owner_finally':settled}))
'''
        r = subprocess.run([sys.executable, '-c', code], cwd=pathlib.Path(__file__).parent, text=True, capture_output=True, timeout=3)
        self.assertEqual(r.returncode, 0, r.stderr)
        result = json.loads(r.stdout)
        self.assertTrue(result['same_owner_finally'])
        self.assertLess(result['elapsed'], 1)

    def test_fixture_does_not_repeat_answers_and_varies_material(self):
        def fake_count(key, payload):
            text = payload['messages'][0]['content']
            return len(text.split()), json.dumps(payload).encode()
        with mock.patch.object(benchmark, 'count', side_effect=fake_count):
            payload, _, codes = benchmark.fixture(b'', 4096, 'deterministic-case')
        text = payload['messages'][0]['content']
        self.assertEqual(len(text.split()), 4096)
        self.assertTrue(all(text.count(c) == 1 for c in codes))
        self.assertIn('uint32_t', text)
        self.assertIn('calibration pending', text)
        self.assertIn('open-drain', text)
        self.assertTrue(text.index(codes[0]) < text.index(codes[1]) < text.index(codes[2]))

    def test_actual_minimax_canonical_fixture_private(self):
        import hashlib
        path = pathlib.Path(__file__).resolve().parents[4] / 'private/mimo-native-fixture.json'
        if not path.exists():
            self.skipTest('Private W2 fixture is not committed')
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'c95f3c09ed1201edf3c27c9d48beabd00c3d1851925e1f9d4ad02c2d57fdb6d6')
        body = json.loads(raw)['canonicalBody']
        before = copy.deepcopy(body)
        self.assertEqual(proxy.normalize(body), before)
        self.assertEqual(len(body['tools']), 17)

    def test_cleanup_proxy_timeout_still_invokes_single_settlement(self):
        import candidate_owner as owner
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('owned-proxy', 3), RuntimeError('kill-wait-failed')]
        with mock.patch.object(owner, 'settle') as settle:
            with self.assertRaises(RuntimeError):
                owner.cleanup_proxy_and_settle(object(), process)
        process.kill.assert_called_once()
        settle.assert_called_once()

    def test_thermal_settlement_exact_id_short_stop_pid_and_cgroup(self):
        import candidate_owner as owner
        import tempfile
        import contextlib
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, 'OWNER.json').write_text(json.dumps({'candidate_id': 'exact-cid', 'native_started_at': 'exact-start', 'guard_failure': 'gpu_temperature_cutoff'}))
            before = {'Id': 'exact-cid', 'Image': owner.IMAGE, 'Name': '/' + owner.NAME, 'Config': {'Labels': {'io.h016.owner': 'H016-20260927'}}, 'State': {'Running': True, 'Pid': 1234, 'StartedAt': 'exact-start'}}
            after = copy.deepcopy(before)
            after['State'].update(Running=False, Pid=0)
            h = mock.Mock()
            h.transaction.side_effect = lambda: contextlib.nullcontext()
            h.require.side_effect = lambda v, reason: None if v else (_ for _ in ()).throw(RuntimeError(reason))
            with mock.patch.object(owner, 'LOG', d), mock.patch.object(owner, 'inspect', side_effect=[before, after]), mock.patch.object(owner, 'cgpath', return_value=pathlib.Path(d, 'absent-cgroup')), mock.patch.object(owner, 'run_cmd', return_value='') as run, mock.patch.object(owner, 'save') as save:
                owner.settle(h)
                run.assert_any_call(['docker', 'stop', '--time', '3', 'exact-cid'], 10)
                self.assertTrue(save.call_args[0][2]['native_settled']['cgroup_empty'])


if __name__ == '__main__':
    unittest.main()
