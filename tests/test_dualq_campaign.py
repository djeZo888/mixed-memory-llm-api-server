"""Synthetic controller/transport tests; no host, GPU, fixture image or inference."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import dualq_480k as dual, fixtures


class DualQCampaignTests(unittest.TestCase):
    def job(self, state):
        job = dual.DualQRun.__new__(dual.DualQRun)
        job.state = Path(state)
        job.private = job.state / 'private'; job.private.mkdir(mode=0o700)
        job.key = 'synthetic-offline-key'
        job.clock = __import__('time').monotonic
        job.active = {slot: {'manifest': dual.manifest(slot), 'cancel_event': threading.Event(),
                            'template_sha256': dual.TEMPLATES['Q1']} for slot in dual.SLOTS}
        job.host = Mock(); job.host.call.return_value = {'drained': True}
        job.admission = Mock(return_value=7200)
        job.counted = set()
        job.dispatch_barrier = threading.Barrier(2)
        return job

    def raw(self, slot, warm=False):
        sample = fixtures.build_sample(dual.manifest(slot)['transport']['model_alias'], 80,
                                       'synthetic-test-seed', dual.PREFIXES[slot], output_cap=512)
        sample['body']['max_tokens'] = 32 if warm else 512
        return fixtures.canonical(sample['body'])

    def test_both_owner_admissions_precede_two_http_dispatches(self):
        with tempfile.TemporaryDirectory() as state:
            job = self.job(state)
            admitted, dispatched, terminals = [], [], []
            lock = threading.Lock()
            def admit(cid, **kwargs):
                with lock: admitted.append(cid)
                return 7200
            job.admission = admit
            def factory(url, key, **kwargs):
                self.assertIsNone(kwargs['deadline_epoch'])
                def send(body, timeout):
                    self.assertEqual(timeout, 7200)
                    with lock:
                        self.assertEqual(set(admitted), set(dual.SLOTS))
                        dispatched.append(json.loads(body)['model'])
                    send.request_clock = {'terminal_reason': 'DRAINED'}
                    yield b'offline-body'
                return send
            job.transport_factory = factory
            def capture(raw, transport, **kwargs):
                list(transport(raw, kwargs['timeout']))
                return {'summary': {}}
            def call(slot):
                try: job.request(slot, self.raw(slot), slot+'-near480K')
                except BaseException as exc: terminals.append(exc)
            with patch('benchmark.client._capture_request', side_effect=capture):
                threads = [threading.Thread(target=call, args=(slot,)) for slot in dual.SLOTS]
                for t in threads: t.start()
                for t in threads: t.join(3)
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertFalse(terminals)
            self.assertEqual(len(dispatched), 2)
            self.assertEqual([c.kwargs['terminal_reason'] for c in job.host.call.call_args_list], ['DRAINED']*2)

    def test_timeout_cancel_and_transport_error_never_claim_native_drain(self):
        for native, expected in [('REQUEST_DEADLINE','REQUEST_DEADLINE'),('RESOURCE_CANCEL','CANCELLED'),
                                  ('TRANSPORT_FAILURE','TRANSPORT_ERROR')]:
            with self.subTest(native=native), tempfile.TemporaryDirectory() as state:
                job = self.job(state)
                def factory(*args, **kwargs):
                    def send(*args): pass
                    send.request_clock = {'terminal_reason': native}
                    return send
                job.transport_factory = factory
                with patch('benchmark.client._capture_request', side_effect=TimeoutError):
                    with self.assertRaises(TimeoutError):
                        job.request('Q0', self.raw('Q0', True), 'Q0-warmup', timed=False)
                job.host.call.assert_called_once()
                self.assertEqual(job.host.call.call_args.kwargs['terminal_reason'], expected)

    def test_pre_dispatch_peer_admission_failure_breaks_barrier_and_cleans_registration(self):
        with tempfile.TemporaryDirectory() as state:
            job = self.job(state)
            job.admission.side_effect = lambda cid, **kw: 7200 if cid == 'Q0' else (_ for _ in ()).throw(RuntimeError('proof_missing'))
            job.transport_factory = lambda *a, **kw: (lambda *a: iter(()))
            errors = []
            def call(slot):
                try: job.request(slot, self.raw(slot), slot+'-near480K')
                except BaseException as error: errors.append(type(error).__name__)
            with patch('benchmark.client._capture_request') as capture:
                threads = [threading.Thread(target=call, args=(slot,)) for slot in dual.SLOTS]
                for t in threads:t.start()
                for t in threads:t.join(3)
                capture.assert_not_called()
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertEqual(len(errors),2)
            job.host.call.assert_called_once()
            self.assertEqual(job.host.call.call_args.kwargs['terminal_reason'], 'TRANSPORT_ERROR')

    def test_both_counters_use_Q_native_alias_exact_body_once(self):
        for slot in dual.SLOTS:
            with self.subTest(slot=slot), tempfile.TemporaryDirectory() as state:
                job = self.job(state); job.admission.return_value = 120
                native = Mock(return_value={'tokens':[1,2,3], 'count':3, 'max_model_len':262144})
                job.json_factory = Mock(return_value=native)
                raw = self.raw(slot)
                counter = job.counter(slot, purpose='measured')
                result = counter(raw)
                self.assertEqual(native.call_args.args[0], '/v1/tokenize')
                self.assertEqual(native.call_args.args[1]['model'], dual.manifest(slot)['transport']['model_alias'])
                self.assertEqual(result['body_sha256'], fixtures.digest(raw))
                self.assertEqual(job.host.call.call_args.kwargs['terminal_reason'], 'COUNT_DRAINED')
                with self.assertRaises(RuntimeError):counter(raw)
                self.assertEqual(native.call_count,1)


if __name__ == '__main__':unittest.main()
