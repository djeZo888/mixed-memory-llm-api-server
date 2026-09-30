"""Offline fixed-profile and transport rejection checks; no native calls."""
import base64
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


class Harness:
    s = None
    @staticmethod
    def require(ok, reason):
        if not ok:
            raise RuntimeError(reason)
    @staticmethod
    def now():
        return '2026-09-27T17:20:00Z'
    @staticmethod
    def MountedStorageGuard(_):
        return contextlib.nullcontext(None)
    class AnchoredRoot:
        def __init__(self, root, _): self.root = Path(root)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def open(self, name, flags=os.O_RDONLY):
            return os.fdopen(os.open(self.root / name, flags, 0o600), 'wb', buffering=0)


class ContractTests(unittest.TestCase):
    def subject(self, profile):
        owner = types.ModuleType('candidate_owner')
        owner.ADMIT_END = owner.CLIENT_END = 1800
        owner.HARD_END = 1920
        owner.BASE = owner.LOG = self.tmp.name
        owner.get = mock.Mock(return_value=(200, [{'id': 0, 'is_processing': False, 'n_ctx': 131072}]))
        owner.save = mock.Mock()
        telemetry = types.ModuleType('telemetry')
        telemetry.bounded_placement = mock.Mock()
        with mock.patch.dict(sys.modules, {'candidate_owner': owner, 'telemetry': telemetry}):
            spec = importlib.util.spec_from_file_location('benchmark_' + profile, HERE.parent / profile / 'benchmark.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def stream(self, module, cached=0, output=128, done=True):
        events = [{'id': 'fixture', 'choices': [{'delta': {'content': 'synthetic'}, 'finish_reason': 'length'}],
                   'usage': {'prompt_tokens': 83, 'completion_tokens': output, 'prompt_tokens_details': {'cached_tokens': cached}},
                   'timings': {'predicted_n': output, 'predicted_ms': 10000, 'predicted_per_second': 12.7, 'prompt_n': 83, 'prompt_ms': 500}}]
        wire = b''.join(b'data: ' + json.dumps(e).encode() + b'\n\n' for e in events)
        if done: wire += b'data: [DONE]\n\n'
        response = mock.Mock(status=200)
        response.read1.side_effect = [wire[:17], wire[17:], b'']
        connection = mock.Mock(sock=None)
        connection.getresponse.return_value = response
        payload = module.body('synthetic fixture', False, 128)
        payload['seed'] = 270927
        with mock.patch.object(module.time, 'time', return_value=1000), \
             mock.patch.object(module, 'count', return_value=(83, json.dumps(payload).encode())), \
             mock.patch.object(module.http.client, 'HTTPConnection', return_value=connection):
            result = module.request(Harness(), b'fixture', payload, 'BASELINE128', threading.Event())
        self.assertEqual(connection.request.call_count, 1)
        return result, wire

    def test_profile_masks_fixed_other_settings(self):
        for profile, cpus in [('r12-spread4', [0,24,40,56]), ('r13-spread2', [0,40])]:
            cfg = json.loads((HERE.parent / profile / 'LAUNCH.json').read_text())
            argv = cfg['native_argv']
            value = lambda flag: argv[argv.index(flag)+1]
            self.assertEqual(int(value('--cpu-mask'), 16), sum(1 << cpu for cpu in cpus))
            self.assertEqual(value('--threads'), str(len(cpus)))
            self.assertEqual(value('--threads-batch'), '64')
            self.assertEqual(value('--cpu-mask-batch'), '0xffffffffffffff00ff')
            self.assertEqual(value('--cpu-strict'), '1')
            self.assertEqual(value('--cpu-strict-batch'), '1')
            self.assertNotIn('--numa', argv)
            self.assertEqual(cfg['ggml_numa'], 'disabled')
            self.assertEqual(cfg['capacity'], 131072)
            self.assertEqual(value('--batch-size'), '2048')
            self.assertEqual(value('--ubatch-size'), '512')

    def test_raw_done_idle_and_n_minus_one(self):
        b = self.subject('r12-spread4')
        row, wire = self.stream(b)
        self.assertEqual(b''.join(base64.b64decode(r['base64']) for r in row['raw_chunks']), wire)
        self.assertEqual(row['native_interval_tokens_per_second'], 12.7)
        self.assertEqual(row['prefill_seconds'], .5)
        self.assertTrue(row['done'] and row['full_http_drain'])
        self.assertEqual(row['actual_cached_tokens'], 0)
        self.assertEqual(row['correctness'], 'UNSCORED')
        self.assertEqual(row['native_settlement']['is_processing'], False)
        self.assertIn('first_output_utc', row)
        self.assertIn('last_output_utc', row)

    def test_cached_input_rejected_no_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'actual_cached_tokens_not_zero'):
            self.stream(self.subject('r13-spread2'), cached=1)

    def test_short_length_rejected_no_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'baseline_native_counts_not_83_in_128_out'):
            self.stream(self.subject('r12-spread4'), output=127)

    def test_missing_done_rejected_no_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'ambiguous_stream_terminal'):
            self.stream(self.subject('r13-spread2'), done=False)

    def test_client_deadline_independent_of_cleanup(self):
        b = self.subject('r12-spread4')
        with mock.patch.object(b.time, 'time', return_value=b.CLIENT_END), mock.patch.object(b, 'count') as count:
            with self.assertRaisesRegex(RuntimeError, 'benchmark_admission_closed'):
                b.request(Harness(), b'fixture', b.body('synthetic'), 'BASELINE128', threading.Event())
            count.assert_not_called()


if __name__ == '__main__': unittest.main()
