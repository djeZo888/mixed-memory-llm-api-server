"""Focused offline GLMREPAIR dispatch/capture checks; no VM or real keys."""
import copy
import json
import io
import signal
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import client, fixtures, glmrepair as g, profiles


def wire(content='{"ok":true}', finish='stop', stream=True):
    usage = {'prompt_tokens': 2391, 'completion_tokens': 32}
    timing = {'prompt_n': 2391, 'cache_n': 0, 'predicted_n': 32, 'prompt_ms': 30, 'predicted_ms': 62}
    if not stream:
        return fixtures.canonical({'model': g.MODEL, 'choices': [{'index': 0, 'finish_reason': finish,
            'message': {'role': 'assistant', 'content': content, 'reasoning_content': 'private reasoning'}}],
            'usage': usage, 'timings': timing})
    rows = [{'model': g.MODEL, 'choices': [{'index': 0, 'delta': {'role': 'assistant',
                'reasoning_content': 'private reasoning', 'content': content}, 'finish_reason': finish}],
                'usage': usage, 'timings': timing}]
    return b''.join(b'data: ' + fixtures.canonical(row) + b'\n\n' for row in rows) + b'data: [DONE]\n\n'


def response(content='{"ok":true}', finish='stop'):
    return {'summary': {'status': 'OUTPUT_LIMIT' if finish == 'length' else 'COMPLETE'},
            'parsed': {'status': 'OUTPUT_LIMIT' if finish == 'length' else 'COMPLETE',
                'finish_reason': finish, 'message': {'role': 'assistant', 'content': content},
                'counters': {'evaluated_prompt_tokens': 2391, 'completion_tokens': 32}}}


class RPCInterruptTests(unittest.TestCase):
    def test_signal_drains_reply_before_restore_and_ends_undispatched_admission(self):
        for operation in ('begin', 'load', 'request_begin'):
            with self.subTest(operation=operation):
                host = g.DiagnosticSSHHost.__new__(g.DiagnosticSSHHost)
                host.lock = threading.RLock()
                count = []
                def readline():
                    count.append(True)
                    if len(count) == 1:
                        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
                        return json.dumps({'result': {'reply_for': operation}}) + '\n'
                    return json.dumps({'result': {'reply_for': 'request_end' if operation == 'request_begin' and len(count) == 2 else 'status'}}) + '\n'
                host.process = SimpleNamespace(stdin=io.StringIO(), stdout=SimpleNamespace(readline=readline))
                with self.assertRaises(KeyboardInterrupt):
                    host.call(operation, id='cid')
                self.assertEqual(host.call('status'), {'reply_for': 'status'})
                sent = [json.loads(line)['op'] for line in host.process.stdin.getvalue().splitlines()]
                self.assertEqual(sent, [operation] + (['request_end'] if operation == 'request_begin' else []) + ['status'])


class CaptureTests(unittest.TestCase):
    def test_complete_and_length_modes_preserve_raw_content(self):
        for streaming in (False, True):
            for finish in ('stop', 'length'):
                with self.subTest(streaming=streaming, finish=finish), tempfile.TemporaryDirectory() as temp:
                    raw = wire('{"ok":true}</think>{"ok":true}', finish, streaming)
                    parts = [raw[:37], raw[37:]]
                    result = client.run_diagnostic_request(fixtures.canonical(g.probe_body(streaming)),
                        lambda *args: iter(parts), sample_id='probe', private_dir=temp,
                        summary_path=Path(temp) / 'summary.jsonl', timeout=23)
                    self.assertEqual(Path(result['private_response_path']).read_bytes(), raw)
                    self.assertEqual(result['parsed']['finish_reason'], finish)
                    self.assertEqual(result['parsed']['message']['content'], '{"ok":true}</think>{"ok":true}')
                    self.assertEqual(g.format_outcome(result)['strict_output_contract']['status'], 'HARNESS_FAILURE')
                    self.assertTrue(result['summary']['response_retained_complete'])

    def test_partial_both_transports_retained_without_retry(self):
        for streaming in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                called = []
                raw = wire(stream=streaming)[:75]
                def fail(*args):
                    called.append(True)
                    yield raw
                    raise TimeoutError('private message')
                result = client.run_diagnostic_request(fixtures.canonical(g.probe_body(streaming)), fail,
                    sample_id='partial', private_dir=temp, summary_path=Path(temp) / 'summary.jsonl', timeout=1)
                self.assertEqual(called, [True])
                self.assertEqual(Path(result['private_response_path']).read_bytes(), raw)
                self.assertEqual(result['summary']['status'], 'TRANSPORT_FAILURE')
                self.assertFalse(result['summary']['response_retained_complete'])
                self.assertNotIn('private message', (Path(temp) / 'summary.jsonl').read_text())

    def test_interrupt_still_saves_partial_receipt_before_reraising(self):
        with tempfile.TemporaryDirectory() as temp:
            def interrupt(*args):
                yield b'partial wire'
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                client.run_diagnostic_request(fixtures.canonical(g.probe_body(False)), interrupt,
                    sample_id='interrupt', private_dir=temp, summary_path=Path(temp) / 'summary.jsonl', timeout=1)
            self.assertEqual(Path(temp, 'interrupt.response.json').read_bytes(), b'partial wire')
            self.assertEqual(json.loads(Path(temp, 'summary.jsonl').read_bytes())['status'], 'TRANSPORT_FAILURE')

    def test_failed_raw_persistence_is_not_claimed_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            real = client._write_private
            def fail_response(path, data):
                if str(path).endswith('response.json'):
                    raise OSError('disk full')
                real(path, data)
            with patch.object(client, '_write_private', side_effect=fail_response):
                result = client.run_diagnostic_request(fixtures.canonical(g.probe_body(False)),
                    lambda *args: iter([wire(stream=False)]), sample_id='disk', private_dir=temp,
                    summary_path=Path(temp) / 'summary.jsonl', timeout=1)
            self.assertFalse(result['summary']['response_retained_complete'])
            with self.assertRaisesRegex(RuntimeError, 'raw_evidence_persistence_failed'):
                g.Diagnostic.persistence_check(result)

    def test_historical_small_cap_still_rejected(self):
        with self.assertRaises(fixtures.HarnessError):
            client.run_request(fixtures.canonical(g.probe_body(True)), Mock(), sample_id='x',
                               private_dir='unused', summary_path='unused')

    def test_short_warmup_32_cap_and_no_schema_or_tool(self):
        body = g.probe_body(True)
        body['max_tokens'] = 32
        with tempfile.TemporaryDirectory() as temp:
            result = client.run_diagnostic_request(fixtures.canonical(body), lambda *args: iter([wire(finish='length')]),
                sample_id='warm', private_dir=temp, summary_path=Path(temp) / 'summary.jsonl', timeout=1)
            self.assertEqual(result['summary']['status'], 'OUTPUT_LIMIT')
        for field in ('tools', 'response_format', 'reasoning_budget'):
            invalid = {**body, field: {}}
            with self.assertRaises(fixtures.HarnessError):
                client.run_diagnostic_request(fixtures.canonical(invalid), Mock())


class SequenceTests(unittest.TestCase):
    def create(self, directory):
        from benchmark.runner import save
        save(Path(directory) / 'progress.json', {'phase': 'CODE_READY', 'completed': {}, 'inflight': {}, 'errors': []})
        host = Mock()
        armed = {'scope': 'glmrepair', 'session_id': 'offline', 'source_commit': 'offline',
                 'manifests': [profiles.glmrepair_manifest()]}
        d = g.Diagnostic(directory, armed, host, 'synthetic-key')
        d.emit = Mock()
        d.record = Mock()
        d.boundary = Mock()
        return d, host

    def test_format_and_length_failures_still_reach_exact_one_baseline(self):
        for finish in ('stop', 'length'):
            with tempfile.TemporaryDirectory() as temp:
                d, host = self.create(temp)
                order = []
                d.loaded = lambda manifest: order.append('load+warmup32') or 'cid'
                def request(cid, raw, name):
                    order.append(name)
                    self.assertEqual(json.loads(raw)['max_tokens'], 128)
                    return response('{"ok":true}</think>{"ok":true}', finish)
                d.request = request
                sample = fixtures.build_sample(g.MODEL, 108, '53fedfbaa93f687629b4e742', 'freshnonce')
                d.prepare_trial = Mock(return_value={'sample': sample, 'count': {}})
                d.trial = lambda *args, **kwargs: order.append('baseline256') or {'status': 'HARNESS_FAILURE'}
                d.sequence()
                self.assertEqual(order, ['load+warmup32', 'stream', 'nonstream', 'baseline256'])
                self.assertEqual(host.call.call_args_list[0].args, ('begin',))

    def test_resource_stop_restores_and_skips_following_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            d, host = self.create(temp)
            d.monitor = lambda: None
            d.sequence = Mock(side_effect=RuntimeError('STOP_OOM'))
            d.restore = Mock()
            host.call.return_value = {'phase': 'ACTIVE'}
            with self.assertRaisesRegex(RuntimeError, 'STOP_OOM'):
                d.execute()
            d.restore.assert_called_once()

    def test_request_resource_cancel_preserves_owner_end(self):
        with tempfile.TemporaryDirectory() as temp:
            d, host = self.create(temp)
            d.active['cid'] = {'cancel_event': threading.Event(), 'abort_reason': 'STOP_OOM'}
            d.admission = Mock(return_value=7)
            d.transport_factory = Mock(return_value=lambda *args: iter([wire()]))
            with self.assertRaisesRegex(RuntimeError, 'STOP_OOM'):
                d.request('cid', fixtures.canonical(g.probe_body(False)), 'cancelled')
            self.assertEqual(host.call.call_args.args, ('request_end',))
            self.assertTrue(Path(temp, 'private', 'cancelled.response.json').exists())

    def test_admission_reclamps_after_guard_latency_and_unregisters_expiry(self):
        with tempfile.TemporaryDirectory() as temp:
            d, host = self.create(temp)
            d.armed['runtime'] = {'deadline_epoch': 100}
            host.call.return_value = {'timeout_s': 15}
            with patch('benchmark.glmrepair.time.time', return_value=97):
                self.assertEqual(d.admission('cid'), 3)
            with patch('benchmark.glmrepair.time.time', return_value=101):
                with self.assertRaisesRegex(RuntimeError, 'STOP_BUDGET'):
                    d.admission('cid')
            self.assertEqual(host.call.call_args.args, ('request_end',))

    def test_warmup_actual_outgoing_cap32_and_native_prefill_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            d, host = self.create(temp)
            seen = []
            def count(raw):
                seen.append(json.loads(raw)['max_tokens'])
                return {'source': 'native_apply_template_tokenize', 'input_tokens': 2391,
                    'body_sha256': fixtures.digest(raw), 'configured_context': 4096,
                    'template_sha256': 'a'*64, 'token_ids_sha256': 'b'*64}
            d.counter = lambda cid: count
            def req(cid, raw, name, **kwargs):
                self.assertEqual(json.loads(raw)['max_tokens'], 32)
                return response(finish='length')
            d.request = req
            d.warm('cid', profiles.glmrepair_manifest(), {})
            self.assertIn(256, seen)  # historical fitter preserved
            self.assertEqual(seen[-1], 32)  # actual body recounted


if __name__ == '__main__':
    unittest.main()
