import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import types

spec = importlib.util.spec_from_file_location('long_client', Path(__file__).with_name('client.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class SourceGates(unittest.TestCase):
    def go(self):
        return {'authorized': True, 'purpose': 'H018_LAST_NEAR950K', 'active_cap_seconds': 28800,
                'admit_before_epoch': 100, 'hard_end_epoch': 28900,
                'private_api': {'host': c.HOST, 'port': c.PORT, 'model': 'mimo-v2.6-pro-rl'},
                'frontier_claim_contract': c.LANE_CONTRACT,
                'acceptance': {k: {} for k in ('final_native17', 'production', 'sova')},
                'source_sha256': {'some': 'pin'}, 'production_identity': {'actual': 'identity'}}

    def test_each_real_slot_keeps_output_and_native_reserve(self):
        self.assertEqual(c.token_target(950000), 948975)
        for n in (950000,):
            self.assertEqual(c.token_target(n) + 1024, n - 1)

    def test_no_rounded_or_fallback_capacity_invention(self):
        for n in (950016, 1000000, 1000192, 917504, 1048576, 949999, True, '950000'):
            with self.assertRaises(RuntimeError):
                c.token_target(n)

    def test_authority_requires_every_acceptance(self):
        c.validate_go(self.go(), 0)
        for name in ('final_native17', 'production', 'sova'):
            go = self.go()
            del go['acceptance'][name]
            with self.assertRaises(RuntimeError):
                c.validate_go(go, 0)

    def test_h018_absolute_last_window_cannot_be_extended(self):
        go = self.go()
        go.update(admit_before_epoch=1790558701, hard_end_epoch=1790558701 + 28800)
        with self.assertRaisesRegex(RuntimeError, 'finite_admission_required'):
            c.validate_go(go, 1790550000)

    def test_eight_hours_and_proxy_claim_are_mandatory(self):
        for key, value in [('authorized', False), ('purpose', 'H017_LAST_NEAR950K'), ('active_cap_seconds', 28801),
                           ('frontier_claim_contract', 'unproven'), ('admit_before_epoch', 101)]:
            go = self.go()
            go[key] = value
            with self.assertRaises(RuntimeError):
                c.validate_go(go, 0)

    def test_closed_admission(self):
        with self.assertRaises(RuntimeError):
            c.validate_go(self.go(), 100)

    def test_reader_deadlines_and_private_endpoint_are_rebound(self):
        seen = []
        class FakeConnection:
            def __init__(self, host, port, *args, **kwargs):
                seen.append((host, port))
            def request(self, *args, **kwargs):
                return None
        reader = types.SimpleNamespace(utc_now=lambda: 'now', count=lambda *_: (12, b'body'))
        with patch.object(c.http.client, 'HTTPConnection', FakeConnection), patch.object(c, 'write') as saved:
            c.adapter(reader, object(), object(), 123456)
            self.assertEqual(reader.CLIENT_END, 123456)
            self.assertEqual(reader.ADMIT_END, 123456)
            connection = reader.http.client.HTTPConnection('127.0.0.1', 30012)
            connection.request('POST', '/v1/chat/completions', b'private')
            self.assertEqual(seen, [(c.HOST, c.PORT)])
            self.assertEqual(saved.call_args.args[2], 'LAST-near950K-BODY-SENT.json')
            self.assertNotIn('private', str(saved.call_args))
            with self.assertRaises(RuntimeError):
                reader.http.client.HTTPConnection('127.0.0.1', 9999)

    def test_64k_precedes_near_with_distinct_output_reserves(self):
        self.assertEqual(c.request_plan(950000), [('LAST-64K', 65536, 256), ('LAST-near950K', 948975, 1024)])

    def test_count_over_15_seconds_refuses_before_dispatch(self):
        reader = types.SimpleNamespace(count=lambda *_: (12, b'body'))
        c.adapter(reader, object(), object(), 123456)
        with patch.object(c.time, 'monotonic', side_effect=[0, 15.01]):
            with self.assertRaisesRegex(RuntimeError, 'count_exceeded_15s'):
                reader.count(b'key', {})
        with patch.object(c.time, 'monotonic', side_effect=[0, 14.99]):
            self.assertEqual(reader.count(b'key', {}), (12, b'body'))

    def test_source_has_no_launch_or_restart(self):
        source = Path(c.__file__).read_text()
        self.assertNotIn("['systemctl', 'start'", source)
        self.assertNotIn("['systemctl', 'restart'", source)
        unit = Path(c.__file__).with_name('h018-last950k.service').read_text()
        self.assertIn('RuntimeMaxSec=8h', unit)
        self.assertIn('Restart=no', unit)
        self.assertIn('ExecStopPost=', unit)
        for dependency in ('BindsTo=', 'Requires=', 'After='):
            self.assertNotIn(dependency + 'llm-frontier-mimo.service', unit)
        self.assertIn('RequiresMountsFor=/data /data/models-large', unit)


if __name__ == '__main__':
    unittest.main()
