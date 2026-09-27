"""Focused offline R9 transport, exact-count, admission and real-tool checks."""
import base64
import contextlib
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
owner = types.ModuleType('candidate_owner')
owner.ADMIT_END = datetime.datetime(2026, 9, 27, 17, 0, tzinfo=datetime.timezone.utc).timestamp()
owner.HARD_END = owner.ADMIT_END + 1500
owner.BASE = '/unused/build'
owner.LOG = '/unused/log'
owner.get = mock.Mock()
owner.save = mock.Mock()
telemetry = types.ModuleType('telemetry')
telemetry.bounded_placement = mock.Mock()
with mock.patch.dict(sys.modules, {'candidate_owner': owner, 'telemetry': telemetry}):
    spec = importlib.util.spec_from_file_location('r9_benchmark_test_subject', HERE / 'benchmark.py')
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)


class Harness:
    s = None

    @staticmethod
    def require(ok, why):
        if not ok:
            raise RuntimeError(why)

    @staticmethod
    def now():
        return '2026-09-27T16:00:00Z'

    @staticmethod
    def transaction():
        return contextlib.nullcontext(None)

    @staticmethod
    def MountedStorageGuard(_):
        return contextlib.nullcontext(None)

    class AnchoredRoot:
        def __init__(self, root, _):
            self.root = pathlib.Path(root)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def open(self, name, flags=os.O_RDONLY):
            fd = os.open(self.root / name, flags, 0o600)
            return os.fdopen(fd, 'wb' if flags & os.O_WRONLY else 'rb', buffering=0)


class FinalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.h = Harness()
        self.patches = [mock.patch.object(b, 'LOG', self.tmp.name),
                        mock.patch.object(b, 'BASE', self.tmp.name),
                        mock.patch.object(b.time, 'time', return_value=owner.ADMIT_END - 3600),
                        mock.patch.object(b, 'save'),
                        mock.patch.object(b, 'get', return_value=(200, [{'id': 0, 'is_processing': False, 'n_ctx': 1000000}]))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def stream_request(self, events, *, done=True, expected=83, output=128):
        wire = b''.join(b'data: ' + json.dumps(e).encode() + b'\n\n' for e in events)
        if done:
            wire += b'data: [DONE]\n\n'
        # Arbitrary transport chunking must preserve every original wire byte.
        chunks = [wire[:9], wire[9:71], wire[71:], b'']
        response = mock.Mock(status=200)
        response.read1.side_effect = chunks
        connection = mock.Mock(sock=None)
        connection.getresponse.return_value = response
        payload = b.body('technical', False, output)
        raw = json.dumps(payload, separators=(',', ':')).encode()
        with mock.patch.object(b, 'count', return_value=(expected, raw)) as counter, mock.patch.object(b.http.client, 'HTTPConnection', return_value=connection):
            row = b.request(self.h, b'fake-offline-key', payload, 'TEST', threading.Event(), 1000000)
        counter.assert_called_once()
        self.assertEqual(connection.request.call_args.args[2], raw)
        self.assertEqual(pathlib.Path(self.tmp.name, 'TEST-REQUEST.json').read_bytes(), raw)
        return row, wire

    def events(self, finish='length'):
        return [{'id': 'actual-response', 'choices': [{'index': 0, 'delta': {'reasoning_content': 'reason '}}]},
                {'id': 'actual-response', 'choices': [{'index': 0, 'delta': {'content': 'answer'}, 'finish_reason': finish}],
                 'usage': {'prompt_tokens': 83, 'completion_tokens': 128,
                           'prompt_tokens_details': {'cached_tokens': 0}},
                 'timings': {'predicted_n': 128, 'predicted_ms': 20000,
                             'prompt_n': 83, 'prompt_ms': 2000}}]

    def test_split_sse_raw_exact_body_timestamps_and_single_first_write(self):
        row, wire = self.stream_request(self.events())
        self.assertEqual(b''.join(base64.b64decode(x['base64']) for x in row['raw_chunks']), wire)
        raw_saved = [json.loads(x) for x in pathlib.Path(self.tmp.name, 'TEST-RAW.jsonl').read_text().splitlines()]
        self.assertEqual(b''.join(base64.b64decode(x['base64']) for x in raw_saved), wire)
        progress = pathlib.Path(self.tmp.name, 'TEST-PROGRESS.jsonl').read_text().splitlines()
        self.assertEqual(len(progress), 1)
        self.assertEqual(json.loads(progress[0])['event'], 'FIRST_OUTPUT')
        self.assertEqual(row['native_interval_tokens_per_second'], 127 / 20)
        self.assertEqual(row['correctness'], 'UNSCORED')
        self.assertEqual(row['finish_reason'], 'length')
        self.assertTrue(row['done'] and row['full_http_drain'])
        self.assertLessEqual(row['first_output_monotonic_seconds'], row['last_output_monotonic_seconds'])
        self.assertLessEqual(row['last_output_monotonic_seconds'], row['drained_monotonic_seconds'])

    def test_missing_done_is_quarantined_without_replay(self):
        with self.assertRaisesRegex(RuntimeError, 'ambiguous_stream_terminal'):
            self.stream_request(self.events(), done=False)
        receipt = b.save.call_args.args[2]
        self.assertEqual(receipt['status'], 'FAILED_QUARANTINE_NO_RETRY')

    def test_count_mismatch_is_quarantined(self):
        with self.assertRaisesRegex(RuntimeError, 'native_usage_count_or_budget_mismatch'):
            self.stream_request(self.events(), expected=84)

    def test_budget_and_admission_reject_before_count(self):
        with mock.patch.object(b.time, 'time', return_value=owner.ADMIT_END), mock.patch.object(b, 'count') as counter:
            with self.assertRaisesRegex(RuntimeError, 'benchmark_admission_closed'):
                b.request(self.h, b'x', b.body('x'), 'LATE', threading.Event(), 1000000)
            counter.assert_not_called()
        with mock.patch.object(b, 'count') as counter:
            with self.assertRaisesRegex(RuntimeError, 'completion_budget_unavailable'):
                b.request(self.h, b'x', b.body('x'), 'LATE', threading.Event(), 1000000, 100000)
            counter.assert_not_called()

    def test_fixture_has_seed_before_every_exact_count(self):
        observed = []
        def counter(key, payload):
            observed.append(copy.deepcopy(payload))
            return 4096, json.dumps(payload).encode()
        with mock.patch.object(b, 'count', side_effect=counter):
            payload, raw, codes = b.fixture(b'x', 4096, 'fresh-test')
        self.assertEqual(payload['seed'], b.SEED)
        self.assertEqual(payload['temperature'], 0)
        self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(payload['max_tokens'], 256)
        self.assertTrue(all(p['seed'] == b.SEED for p in observed))
        self.assertEqual(len(codes), 3)

    def test_json_semantics_require_normal_finish_order_and_values(self):
        codes = ['EARLY', 'MIDDLE', 'END']
        row = {'finish_reason': 'stop', 'tool_calls': [], 'reasoning_content': '',
               'content': json.dumps({'codes': codes, 'product': 323, 'safe_adc': 4095})}
        self.assertTrue(b.fixture_correct(row, codes))
        row['finish_reason'] = 'length'
        self.assertFalse(b.fixture_correct(row, codes))
        row['finish_reason'] = 'stop'
        self.assertFalse(b.fixture_correct(row, list(reversed(codes))))
        row['reasoning_content'] = 'thinking-only'
        self.assertFalse(b.fixture_correct(row, codes))

    def test_actual_allowlisted_read_and_history_retention(self):
        path = b.prepare_read_fixture(self.h)
        call = {'id': 'ACTUAL-CALL-ID', 'type': 'function', 'function': {'name': 'read', 'arguments': json.dumps({'path': path})}}
        text = b.execute_read(self.h, call, path)
        self.assertEqual(text, pathlib.Path(path).read_text())
        payload = {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'read'}]}], 'tools': [{'preserved': True}]}
        row = {'content': 'actual assistant text', 'reasoning_content': 'actual private reasoning', 'tool_calls': [call]}
        next_body = b.continuation(payload, row, text)
        self.assertEqual(next_body['messages'][-2]['reasoning_content'], row['reasoning_content'])
        self.assertEqual(next_body['messages'][-2]['content'], row['content'])
        self.assertEqual(next_body['messages'][-2]['tool_calls'], row['tool_calls'])
        self.assertEqual(next_body['messages'][-1]['tool_call_id'], call['id'])
        self.assertEqual(next_body['messages'][-1]['content'], text)
        self.assertEqual(len(payload['messages']), 1)
        for wrong in [{'path': path + '.other'}, {'file_path': path}, {'path': path, 'offset': 1}]:
            bad = copy.deepcopy(call)
            bad['function']['arguments'] = json.dumps(wrong)
            with self.assertRaisesRegex(RuntimeError, 'outside_exact_allowlist'):
                b.execute_read(self.h, bad, path)
        pathlib.Path(path).write_text('tampered')
        with self.assertRaisesRegex(RuntimeError, 'fixture_changed'):
            b.execute_read(self.h, call, path)

    def test_actual_private_fixture_identity_and_unchanged_roster(self):
        fixture = HERE.parents[4] / 'H016-BACKEND-02-20260927/private/mimo-production-fixture-65536.json'
        if not fixture.exists():
            self.skipTest('retained private production fixture not staged on this host')
        raw = fixture.read_bytes()
        pathlib.Path(self.tmp.name, fixture.name).write_bytes(raw)
        proxy = types.ModuleType('private_proxy')
        proxy.normalize = lambda body: body
        original_open = Harness.AnchoredRoot.open
        class BoundedReader:
            def __init__(self, file): self.file = file
            def __enter__(self): return self
            def __exit__(self, *_): self.file.close()
            def read(self, size):
                if not 0 <= size <= 1024 * 1024:
                    raise RuntimeError('storage_read_must_be_bounded')
                return self.file.read(size)
        def bounded_open(root, name, flags=os.O_RDONLY):
            return BoundedReader(original_open(root, name, flags))
        with mock.patch.dict(sys.modules, {'private_proxy': proxy}), \
                mock.patch.object(Harness.AnchoredRoot, 'open', bounded_open):
            payload = b.load_production_fixture(self.h)
        self.assertEqual(len(payload['tools']), 17)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), b.FIXTURE_SHA)
        self.assertEqual(hashlib.sha256(json.dumps(payload['tools'], separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(), b.TOOLS_SHA)
        read = next(t['function'] for t in payload['tools'] if t['function']['name'] == 'read')
        self.assertFalse(read['strict'])  # Real roster flags preserved, not invented.
        self.assertEqual(read['parameters']['required'], ['path'])

    def test_cache_and_exact_rung_checks_cannot_claim_pass(self):
        activity = types.ModuleType('profile_activity')
        activity.boundary = lambda *_: {'status': 'AVAILABLE'}
        row = {'expected_input_tokens': 4096, 'usage': {'prompt_tokens': 4096, 'prompt_tokens_details': {'cached_tokens': 1}}}
        state = {'native_pid': 123, 'native_cgroup': '/unused', 'context': 1000000, 'allocated_context': 1000000, 'threads': 16}
        with mock.patch.dict(sys.modules, {'profile_activity': activity}), mock.patch.object(b, 'request', return_value=row):
            with self.assertRaisesRegex(RuntimeError, 'count_or_cache_failed'):
                b.phase_request(self.h, b'x', b.body('x'), 'CACHE', threading.Event(), state, 1, exact_input=4096, require_uncached=True)
        self.assertFalse(row['measurement_checks']['actual_cached_zero'])

    def test_two_turn_pair_uses_actual_read_and_all_original_tools(self):
        fixture = HERE.parents[4] / 'H016-BACKEND-02-20260927/private/mimo-production-fixture-65536.json'
        if not fixture.exists():
            self.skipTest('retained private production fixture not staged on this host')
        original = json.loads(fixture.read_bytes())['canonicalBody']
        received = []
        def phase(h, key, payload, label, failed, state, planning_seconds):
            received.append(copy.deepcopy(payload))
            self.assertEqual(payload['tools'], original['tools'])
            self.assertEqual(payload['max_tokens'], 65536)
            self.assertTrue(payload['chat_template_kwargs']['enable_thinking'])
            self.assertFalse(payload['parallel_tool_calls'])
            self.assertEqual(payload['tool_choice'], 'auto')
            if label == 'FINAL17-TURN1':
                path = str(pathlib.Path(self.tmp.name, b.READ_NAME))
                self.assertEqual(pathlib.Path(path).read_text(), b.READ_TEXT)
                self.assertEqual(payload['messages'][1]['content'][0]['type'], 'text')
                return {'finish_reason': 'tool_calls', 'content': 'real first content',
                        'reasoning_content': 'real first reasoning',
                        'tool_calls': [{'id': 'REAL-ID-123', 'type': 'function', 'function': {'name': 'read', 'arguments': json.dumps({'path': path})}}],
                        'usage': {'prompt_tokens': 8192, 'completion_tokens': 50},
                        'request_sha256': 'first-request-hash'}
            self.assertEqual(label, 'FINAL17-TURN2')
            self.assertEqual(payload['messages'][-2]['reasoning_content'], 'real first reasoning')
            self.assertEqual(payload['messages'][-2]['content'], 'real first content')
            self.assertEqual(payload['messages'][-1]['tool_call_id'], 'REAL-ID-123')
            self.assertEqual(payload['messages'][-1]['content'], pathlib.Path(self.tmp.name, b.READ_NAME).read_text())
            return {'finish_reason': 'stop', 'content': '5 ' + b.READ_MARKER,
                    'tool_calls': [], 'usage': {'prompt_tokens': 8250, 'completion_tokens': 20},
                    'request_sha256': 'second-request-hash'}
        state = {'context': 1000000, 'allocated_context': 1000000, 'threads': 16}
        with mock.patch.object(b, 'load_production_fixture', return_value=copy.deepcopy(original)), mock.patch.object(b, 'phase_request', side_effect=phase):
            b.production_pair(self.h, b'fake-key', threading.Event(), state)
        self.assertEqual(len(received), 2)
        summary = b.save.call_args.args[2]
        self.assertTrue(summary['native_tool_qualification'])
        self.assertEqual(summary['actual_tool_call_id'], 'REAL-ID-123')
        self.assertEqual(summary['actual_completion_tokens'], [50, 20])
        self.assertEqual(summary['output_ceiling_each_turn'], 65536)

    def test_phase_memory_reserve_failure_stops_sequence(self):
        activity = types.ModuleType('profile_activity')
        activity.boundary = lambda *_: {'status': 'AVAILABLE'}
        phase_owner = types.ModuleType('candidate_owner')
        phase_owner.capture_phase = mock.Mock(return_value={
            'capture_status': 'CAPTURED', 'frontier': {'reserve_pass': False},
            'host_reserve_pass': True})
        row = {'expected_input_tokens': 4096, 'usage': {'prompt_tokens': 4096,
               'completion_tokens': 50, 'prompt_tokens_details': {'cached_tokens': 0}}}
        state = {'native_pid': 123, 'native_cgroup': '/unused', 'context': 1000000,
                 'allocated_context': 1000000, 'threads': 16}
        with mock.patch.dict(sys.modules, {'profile_activity': activity, 'candidate_owner': phase_owner}), mock.patch.object(b, 'request', return_value=row):
            with self.assertRaisesRegex(RuntimeError, 'capture_or_reserve_failed'):
                b.phase_request(self.h, b'x', b.body('x'), 'RESERVE', threading.Event(),
                                state, 1, exact_input=4096, require_uncached=True)
        phase_owner.capture_phase.assert_called_once_with(self.h, state, 'RESERVE', occupied=4096)


if __name__ == '__main__':
    unittest.main()
