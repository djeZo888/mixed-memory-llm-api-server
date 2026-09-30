"""Focused R6 configuration/transport/decode contract, no inference."""
import base64
import copy
import datetime
import json
import pathlib
import threading
import unittest
from unittest import mock
import benchmark
import candidate_owner as owner


class ProfileTests(unittest.TestCase):
    def test_native_argv_and_guard_unchanged(self):
        root = pathlib.Path(__file__).parent
        old = json.loads((root.parent / 'r5/LAUNCH.json').read_text())
        new = json.loads((root / 'LAUNCH.json').read_text())
        self.assertEqual(old['native_argv'], new['native_argv'])
        self.assertEqual((root / 'telemetry.py').read_bytes(), (root.parent / 'r5/telemetry.py').read_bytes())
        self.assertEqual(owner.ADMIT_END, datetime.datetime(2026, 9, 27, 15, 15, tzinfo=datetime.timezone.utc).timestamp())
        self.assertEqual(owner.HARD_END, datetime.datetime(2026, 9, 27, 15, 35, tzinfo=datetime.timezone.utc).timestamp())

    def test_raw_sse_timing_and_length_survive_without_normalization(self):
        events = [dict(id='fixed', choices=[dict(delta={'content':'technical '}, finish_reason=None)]),
                  dict(id='fixed', choices=[dict(delta={'content':'details'}, finish_reason='length')],
                       usage={'prompt_tokens':50,'completion_tokens':128},
                       timings={'predicted_n':128,'predicted_ms':139093.771,'prompt_n':50,'prompt_ms':3000.123})]
        chunks = [b'data: '+json.dumps(v).encode()+b'\n\n' for v in events]+[b'data: [DONE]\n\n',b'']
        response=mock.Mock(status=200);response.read1.side_effect=chunks
        connection=mock.Mock(sock=None);connection.getresponse.return_value=response
        h=mock.Mock();h.now.return_value='2026-09-27T14:00:00Z'
        h.require.side_effect=lambda ok, why: None if ok else (_ for _ in ()).throw(RuntimeError(why))
        payload=benchmark.body('technical',False,128)
        with mock.patch.object(benchmark,'count',return_value=(50,b'{}')), mock.patch.object(benchmark,'save'), mock.patch.object(benchmark.http.client,'HTTPConnection',return_value=connection), mock.patch.object(benchmark.time,'time',return_value=owner.ADMIT_END-10):
            row=benchmark.request(h,b'fake-test-only',payload,'TEST',threading.Event())
        self.assertEqual(row['native_timings'],events[-1]['timings'])
        self.assertEqual(row['finish_reason'],'length')
        self.assertEqual(row['correctness'],'UNSCORED')
        self.assertTrue(row['done'] and row['full_http_drain'])
        self.assertEqual(b''.join(base64.b64decode(x['base64']) for x in row['raw_chunks']),b''.join(chunks))
        self.assertLessEqual(row['first_output_monotonic_seconds'],row['last_output_monotonic_seconds'])
        self.assertLessEqual(row['last_output_monotonic_seconds'],row['drained_monotonic_seconds'])


if __name__ == '__main__':
    unittest.main()
