"""H019 adapter regression fixtures; no live host or inference contact."""
import contextlib
import copy
import datetime
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).parent

def load(name):
    spec = importlib.util.spec_from_file_location('h019_' + name, BASE / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

f, s, d = load('final'), load('short'), load('dispatch')

class CurrentAuthorityTests(unittest.TestCase):
    def authority(self):
        return {'authorized': True, 'purpose': 'H019_DIRECT950K', 'active_cap_seconds': 28800,
            'admit_before_epoch': f.ADMIT_END, 'hard_end_epoch': f.ADMIT_END + 28800,
            'private_api': {'host': '10.156.100.60', 'port': 30012, 'model': 'mimo-v2.6-pro-rl'},
            'frontier_claim_contract': 'ordinary-proxy-single-active-chat-lock-v1',
            'acceptance': {k: {} for k in ('final_native17', 'production')},
            'source_sha256': {'fixture': 'pin'}, 'production_identity': {'launch_id': 'fixture'}}

    def test_direct_one_request_exact_count_and_reserve(self):
        self.assertEqual(f.request_plan(950000), [(f.LABEL, 948975, 1024)])
        for invalid in (950016, 1000000, '950000', True):
            with self.assertRaises(RuntimeError): f.request_plan(invalid)

    def test_current_deadline_and_all_acceptance_are_required(self):
        go = self.authority()
        self.assertEqual(datetime.datetime.fromtimestamp(f.ADMIT_END, datetime.timezone.utc).isoformat(), '2026-09-28T04:10:29+00:00')
        f.validate_go(go, f.ADMIT_END - 1)
        for key, value in [('purpose', 'H018_LAST_NEAR950K'), ('admit_before_epoch', f.ADMIT_END + 1),
                           ('active_cap_seconds', 28801), ('hard_end_epoch', f.ADMIT_END + 28801)]:
            with self.assertRaises(RuntimeError): f.validate_go({**go, key: value}, f.ADMIT_END - 1)
        for key in go['acceptance']:
            candidate = copy.deepcopy(go); del candidate['acceptance'][key]
            with self.assertRaises(RuntimeError): f.validate_go(candidate, f.ADMIT_END - 1)
        with self.assertRaises(RuntimeError): f.validate_go(go, f.ADMIT_END)


    def test_optional_sova_and_unrecognized_proof(self):
        go = self.authority()
        f.validate_go(go, f.ADMIT_END - 1)
        go['acceptance']['sova'] = {}
        f.validate_go(go, f.ADMIT_END - 1)
        go['acceptance']['invented'] = {}
        with self.assertRaises(RuntimeError): f.validate_go(go, f.ADMIT_END - 1)

    def test_dispatch_passes_actual_sample_and_existing_lease(self):
        sample = {'hardware_validation': {'observed_at': 'actual-fresh', 'boot_id': 'same'}}
        owner = types.SimpleNamespace(bounded=lambda _: contextlib.nullcontext(), GPU='gpu',
            run=Mock(return_value='thermal'), temperature_limit=Mock(return_value=85),
            sample_guard=Mock(return_value=sample), latch=Mock(return_value={'hardware_latched': False}))
        state = {'baseline': {'actual': 'baseline'}, 'native': {'pid': 123}, 'boot_id': 'same'}
        lease = object()
        self.assertEqual(d.fresh_latch(owner, object(), {}, state, lease)[0], sample)
        self.assertEqual(owner.sample_guard.call_count, 1)
        self.assertEqual(owner.sample_guard.call_args.kwargs, {'proof_boot': 'same'})
        self.assertIs(owner.latch.call_args.kwargs['lease'], lease)
        self.assertIs(owner.latch.call_args.kwargs['evidence'], sample['hardware_validation'])
        self.assertGreater(owner.latch.call_args.kwargs['deadline'], 0)

    def test_short_expired_authority_never_calls_transport(self):
        transport = Mock()
        with patch.object(s, 'setup', return_value=(Mock(), Mock(), transport, {'admit_before_epoch': 0})):
            with self.assertRaisesRegex(RuntimeError, 'short_admission_closed'): s.run()
        transport.check_identity.assert_not_called()

    def test_final_stages_have_no_hidden_64k_precondition(self):
        # Stop after the actual run persists its initial state, before any reader/network.
        class InitialSaved(Exception): pass
        saved = []
        def write(o, h, name, value):
            saved.append(copy.deepcopy(value)); raise InitialSaved()
        c = types.SimpleNamespace(preflight=lambda *_: (Mock(), {'context': 950000}, {}, {}, Path('/fixture')),
            write=write, check_identity=Mock(), adapter=Mock(), load_module=Mock(), LocalBusyNotSubmitted=RuntimeError)
        with patch.object(f, 'setup', return_value=(Mock(), c, self.authority(), 'go-pin')):
            with self.assertRaises(InitialSaved): f.run()
        self.assertEqual(saved[0]['stages'], {f.LABEL: 'QUEUED'})
        self.assertEqual(saved[0]['completed_rungs'], [])
        c.load_module.assert_not_called()

    def test_final_settlement_reuses_exact_authority_hash(self):
        c = types.SimpleNamespace(settle=Mock())
        o = object(); go = self.authority()
        with patch.object(f, 'setup', return_value=(o, c, go, 'exact-current-hash')): f.settle()
        self.assertEqual(c.read_go(o)[1], 'exact-current-hash')
        self.assertEqual(c.read_go(o)[0]['production_identity'], go['production_identity'])
        self.assertEqual(go['purpose'], 'H019_DIRECT950K')
        c.settle.assert_called_once()

class FinalExecutionTests(unittest.TestCase):
    def exercise(self, complete):
        import io
        import json
        import tempfile
        from scripts.h018.last950k.test_last_ownership import Harness
        snapshots = []
        with tempfile.TemporaryDirectory() as td:
            Harness.writes = []
            h = Harness()
            o = types.SimpleNamespace(read_key=lambda _: b'fixture', native_ready=lambda *_: True,
                BASE=Path('/fixture'), read=lambda _: {'active_requests': 0})
            guard = {'status': 'ok'}
            reader = types.SimpleNamespace(get=lambda *_: (200, [{'n_ctx': 950000, 'is_processing': False}]),
                fixture=Mock(return_value=({'messages': []}, b'', ['a', 'b', 'c'])),
                count=Mock(return_value=(948975, b'')), last_count_seconds=.01,
                fixture_correct=lambda *_: True, record_semantics=Mock())
            row = {'done': True, 'full_http_drain': True,
                   'native_settlement': {'status': 'AUTHENTICATED_SLOT_IDLE_AFTER_FULL_DRAIN'},
                   'owned_stream_disposition': {'status': 'OWN_STREAM_TERMINAL_FULL_DRAIN'}}
            def request(*args, **kwargs):
                if not complete: raise ConnectionResetError('fixture')
                kwargs['on_owned_stream_drained'](row)
                return row
            reader.request = Mock(side_effect=request)
            class Busy(Exception): pass
            def write(o, h, name, value): snapshots.append((name, copy.deepcopy(value)))
            c = types.SimpleNamespace(preflight=lambda *_: (h, {'context': 950000}, {}, guard, Path(td)),
                write=write, check_identity=lambda *_: ({}, {}, guard), adapter=Mock(),
                load_module=lambda *_: reader, LocalBusyNotSubmitted=Busy)
            go = {'hard_end_epoch': f.ADMIT_END + 28800, 'admit_before_epoch': f.ADMIT_END,
                  'production_identity': {'launch_id': 'fixture'}}
            with patch.object(f, 'setup', return_value=(o, c, go, 'authority')),\
                 patch.object(f, 'LOG', td), patch.object(f.time, 'time', return_value=f.ADMIT_END - 1200),\
                 patch.object(f.signal, 'signal'), patch.object(f.signal, 'setitimer'):
                if complete: f.run()
                else:
                    with self.assertRaises(ConnectionResetError): f.run()
            return reader, [v for n,v in snapshots if n == 'CLIENT.json'][-1]

    def test_direct_execution_one_dispatch_full_drain_and_keep_warm(self):
        reader, result = self.exercise(True)
        self.assertEqual(reader.request.call_count, 1)
        self.assertEqual(result['completed_rungs'], [948975])
        self.assertEqual(result['stages'], {f.LABEL: 'PASS'})
        self.assertEqual(result['status'], 'PASS_KEEP_WARM')
        self.assertFalse(result['request_may_be_active'])
        self.assertEqual(result['execution_cap_seconds'], 28800)
        self.assertEqual(reader.fixture.call_args.args[1], 948975)
        self.assertEqual(reader.ADMIT_END, f.ADMIT_END)

    def test_ambiguous_direct_dispatch_retains_ownership_without_replay(self):
        reader, result = self.exercise(False)
        self.assertEqual(reader.request.call_count, 1)
        self.assertEqual(result['status'], 'FAILED_NO_RETRY')
        self.assertTrue(result['request_may_be_active'])
        self.assertEqual(result['completed_rungs'], [])

if __name__ == '__main__': unittest.main()
