"""Offline actual-host batch admission and drain contracts; no VM/tool calls."""
import copy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
import urllib.error
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_profiles as profile, fixtures, postrestart72_batch as batch
from benchmark.host import LinuxHost, RPC_OPERATIONS, BOOT_UNIT, CONTROL_UNIT
from benchmark.postrestart72_budget import PostrestartBudget
from benchmark.postrestart72_run import PostrestartRun


class BatchHostTests(unittest.TestCase):
    def setUp(self):
        h = self.h = LinuxHost.__new__(LinuxHost)
        h.scope, h.campaign, h.mode = profile.POSTRESTART_SCOPE, profile.POSTRESTART_BATCH_CAMPAIGN, profile.POSTRESTART_BATCH_MODE
        h.run_source_commit, h.run_session_id = 'a' * 40, 'batch-offline-session'
        h.requests, h.followup_request, h.followup_admitted = {}, None, set()
        h.batch_state = {'binding': None, 'case': 0, 'counts': {}, 'warmups': [], 'admitted': [], 'ended': []}
        h.load_manifests = {cid: profile.postrestart_manifest(p, h.campaign) for cid, p in (('g', 'G1'), ('q', 'Q1'))}
        h.allocation_proofs = dict.fromkeys(('g', 'q'), {})
        h.concurrent_resource_violations = {}
        h.owner = SimpleNamespace(phase='ACTIVE', warm_hold_resumed=False, pending_create=None,
            lease=Mock(), _lease_check=Mock(), resources=[{'state': 'RUNNING', 'resource': {'id': cid}} for cid in ('g', 'q')],
            original={'services': {BOOT_UNIT: {'active': 'inactive'}}})
        h.identity = Mock(return_value=({}, None, [])); h.concurrent_limits = Mock()
        h.telemetry = Mock(return_value={'concurrent_resource_gate': {'status': 'PASS'}})
        h.hold_checkpoint = Mock(return_value={'status': 'HELD'})
        h.batch_owned_idle = Mock(return_value=True)
        h.guards = Mock(); h.credentials = Mock(); h.held_jobs = Mock(return_value={'status': 'HELD'})
        h.units = Mock(return_value={BOOT_UNIT: {'active': 'inactive'}, CONTROL_UNIT: {'active': 'inactive'}})
        self.saved = {}
        h.write_json = lambda name, data: self.saved.update({name: copy.deepcopy(data)})
        h.read_json = lambda *a, **k: None
        h.log_root = '/synthetic-offline-only'; self.now = [100.0]
        h.budget = PostrestartBudget(h, clock=lambda: self.now[0]); h.budget.start('maintenance')
        resident = patch('benchmark.cpu_budget_host.resident_obligations')
        resident.start(); self.addCleanup(resident.stop)
        self.rows = [{'request_id': identifier, 'placement': batch.REQUEST_PLACEMENTS[identifier],
            'request_sha256': fixtures.digest(identifier.encode()),
            'manifest_sha256': fixtures.digest(fixtures.canonical(h.load_manifests[self.cid(identifier)])),
            'count_sha256': fixtures.digest(('count-' + identifier).encode())} for identifier in batch.REQUEST_IDS]

    @staticmethod
    def cid(identifier):
        return 'q' if 'Q' in identifier else 'g'

    def identity(self, identifier, purpose):
        row = next((row for row in self.rows if row['request_id'] == identifier), None)
        return {'request_id': identifier, 'request_sha256': row['request_sha256'] if row else fixtures.digest(identifier.encode()),
            'manifest_sha256': fixtures.digest(fixtures.canonical(self.h.load_manifests[self.cid(identifier)])), 'purpose': purpose}

    def begin(self, identifier, purpose):
        return self.h.dispatch({'op': 'request_begin', 'id': self.cid(identifier),
            'request_identity': self.identity(identifier, purpose), 'measured': purpose == 'measured',
            'timeout_s': 120 if purpose == 'count' else 7200})

    def end(self, identifier, purpose):
        return self.h.dispatch({'op': 'request_end', 'id': self.cid(identifier),
            'request_identity': self.identity(identifier, purpose),
            'terminal_reason': 'COUNT_DRAINED' if purpose == 'count' else 'DRAINED'})

    def prepare(self):
        for identifier in ('P-G1-warmup', 'P-Q1-warmup', *batch.REQUEST_IDS):
            for _ in range(1 if self.cid(identifier) == 'q' else 3):
                self.begin(identifier, 'count'); self.end(identifier, 'count')
            if identifier.endswith('warmup'):
                self.begin(identifier, 'warmup'); self.end(identifier, 'warmup')
        binding = {'version': 1, 'campaign': self.h.campaign, 'source_commit': self.h.run_source_commit,
            'session_id': self.h.run_session_id, 'batch_plan_sha256': batch.BATCH_PLAN_SHA256, 'requests': self.rows}
        return self.h.dispatch({'op': 'seal_batch', 'binding': binding})

    def case(self, case):
        return self.h.dispatch({'op': 'batch_case_begin', 'case': case})

    def test_actual_dispatch_exact_B3_pair_and_peer_drain(self):
        self.assertTrue(self.prepare()['sealed'])
        self.assertIsNone(self.h.budget.data['started_at'])
        for n, pair in enumerate(batch.CASES, 1):
            self.assertTrue(self.case(n)['admitted'])
            for identifier in reversed(pair):
                self.assertEqual(self.begin(identifier, 'measured')['timeout_s'], 7200)
            with self.assertRaises(ValueError):
                self.case(n + 1)
            for identifier in pair:
                self.assertTrue(self.end(identifier, 'measured')['drained'])
            with self.assertRaises(ValueError):
                self.begin(pair[0], 'measured')
        self.assertEqual(set(self.h.batch_state['admitted']), set(batch.REQUEST_IDS))
        self.assertEqual(len(self.h.batch_state['admitted']), 2)
        self.assertEqual(self.h.batch_state['case'], 1)
        with self.assertRaises(ValueError):
            self.case(2)
        self.assertFalse(self.h.requests)
        self.assertEqual(self.h.owner.phase, 'ACTIVE')  # existing warm_hold owns the final transition
        self.h.hold_checkpoint.assert_called_with(entering=True)
        for operation in ('admit_followup', 'resume_measurements'):
            with self.assertRaisesRegex(ValueError, 'batch_no_extra_followup'):
                self.h.dispatch({'op': operation, 'go': {}})

    def test_bound_count_limit_flag_and_body_cannot_bypass(self):
        identity = self.identity('B3-G65008', 'count')
        args = {'op': 'request_begin', 'id': 'g', 'measured': False, 'timeout_s': 120, 'request_identity': identity}
        self.h.dispatch(args)
        self.end('B3-G65008', 'count')
        for edit in ({'request_sha256': 'f' * 64}, {'purpose': 'measured'}, {'request_id': 'extra'}):
            with self.assertRaises(ValueError):
                self.h.dispatch({**args, 'request_identity': {**identity, **edit}})
        for _ in range(2):
            self.begin('B3-G65008', 'count'); self.end('B3-G65008', 'count')
        with self.assertRaises(ValueError):
            self.begin('B3-G65008', 'count')
        with self.assertRaises(ValueError):
            self.begin('B3-G65008', 'measured')

    def test_admission_expiry_never_clips_inflight_full_timeout(self):
        self.prepare(); self.case(1)
        self.assertEqual(self.begin('B3-G65008', 'measured')['timeout_s'], 7200)
        self.now[0] += 21600
        self.assertEqual(self.h.budget.checkpoint(), 0)
        with self.assertRaisesRegex(ValueError, 'STOP_BUDGET'):
            self.begin('B3-Qnear480K', 'measured')
        self.assertEqual(self.h.requests['g']['timeout_s'], 7200)
        self.assertTrue(self.end('B3-G65008', 'measured')['drained'])

    def test_actual_shared_guard_rejects_B1_B2_before_count_or_measurement(self):
        for identifier in ('B1-G4K','B1-Qnear480K','B2-Gscience'):
            for purpose in ('count','measured'):
                with self.subTest(identifier=identifier,purpose=purpose), self.assertRaisesRegex(ValueError,'batch_closed_request_required'):
                    self.begin(identifier,purpose)
        self.assertFalse(self.h.requests)
        self.assertFalse(self.h.batch_state['counts'])
        self.assertFalse(self.h.batch_state['admitted'])

    def test_B3_transport_uncertainty_keeps_owned_registration_for_recovery(self):
        self.prepare();self.case(1);self.begin('B3-G65008','measured')
        with self.assertRaisesRegex(ValueError,'uncertain_transport'):
            self.h.dispatch({'op':'request_end','id':'g',
                'request_identity':self.identity('B3-G65008','measured'),'terminal_reason':'TRANSPORT_FAILURE'})
        with self.assertRaisesRegex(ValueError,'batch_timeout_exact_science_only'):
            self.h.dispatch({'op':'batch_timeout_drain','id':'g',
                'request_identity':self.identity('B3-G65008','measured'),'request_clock':{}})
        self.assertIn('g',self.h.requests)
        with self.assertRaises(ValueError):self.case(2)

    def test_socket_absence_alone_does_not_prove_native_drain(self):
        with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=b'')), \
                patch('benchmark.host.http_json', return_value=[{'is_processing': True}]):
            self.assertFalse(LinuxHost.batch_owned_idle(self.h, 'g'))

    def test_native_drain_proof_gaps_retry_within_existing_window(self):
        self.prepare();self.case(1);self.begin('B3-G65008','measured')
        self.h.batch_owned_idle.side_effect = lambda cid, **kwargs: LinuxHost.batch_owned_idle(self.h, cid, **kwargs)
        with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=b'')), \
                patch('benchmark.host.http_json', side_effect=[urllib.error.URLError('synthetic-gap'),
                    TimeoutError(), {'malformed': True}, [{'is_processing': False}]]) as native:
            self.assertEqual(self.end('B3-G65008','measured')['status'], 'VERIFIED_DRAIN')
            self.assertEqual(native.call_count, 4)
        self.assertFalse(self.h.requests)

    def test_actual_runner_native_count_routes_use_bound_host_ledger(self):
        runner = PostrestartRun.__new__(PostrestartRun)
        runner.mode, runner.batch_counted, runner.key = profile.POSTRESTART_BATCH_MODE, {}, 'synthetic-only'
        runner.active = {cid: {'manifest': manifest, 'template_sha256': 'b' * 64}
                         for cid, manifest in self.h.load_manifests.items()}
        runner.host = SimpleNamespace(call=lambda op, **args: self.h.dispatch({'op': op, **args}))
        runner.admission = lambda cid, maximum, **kw: self.h.dispatch({'op': 'request_begin', 'id': cid,
            'timeout_s': maximum, 'measured': False, **kw})['timeout_s']
        routes = []
        def factory(*args, **kwargs):
            def call(route, body):
                routes.append(route)
                self.assertEqual(len(self.h.requests), 1)
                if route == '/props':
                    return {'model_alias': 'bench-glm-5.3', 'is_sleeping': False, 'total_slots': 1,
                        'default_generation_settings': {'n_ctx': 480000}, 'chat_template': 'synthetic-template'}
                if route == '/apply-template':
                    return {'prompt': 'synthetic-rendered'}
                return {'tokens': [1, 2], 'count': 2, 'max_model_len': 480000}
            return call
        runner.json_factory = factory
        for cid, identifier, model in (('g', 'B3-G65008', 'bench-glm-5.3'), ('q', 'B3-Qnear480K', 'bench-qwen3.8-27b')):
            raw = fixtures.canonical({'model': model, 'messages': [{'role': 'user', 'content': 'synthetic-count-only'}],
                'max_tokens': 256, 'stream': True})
            self.assertEqual(runner.counter(cid, identifier)(raw)['body_sha256'], fixtures.digest(raw))
            self.assertFalse(self.h.requests)
            with self.assertRaisesRegex(ValueError, 'recount_retry'):
                runner.counter(cid, identifier)(raw)
        self.assertEqual(routes, ['/props', '/apply-template', '/tokenize', '/v1/tokenize'])

    def test_rpc_and_legacy_scope_boundaries(self):
        self.assertTrue({'seal_batch', 'batch_case_begin', 'batch_timeout_drain'} <= RPC_OPERATIONS)
        self.h.campaign, self.h.mode = profile.POSTRESTART_CAMPAIGN, None
        self.h.postrestart_measured_admissions = {'G1': 0, 'Q1': 0}
        with self.assertRaisesRegex(ValueError, 'cpu_operation_outside_scope'):
            self.h.dispatch({'op': 'seal_batch', 'binding': {}})
        self.assertEqual(self.h.dispatch({'op': 'request_begin', 'id': 'g', 'measured': True, 'timeout_s': 7200})['timeout_s'], 7200)
        self.assertNotIn('request_identity', self.h.requests['g'])
        self.h.dispatch({'op': 'request_end', 'id': 'g'})


if __name__ == '__main__':
    unittest.main()
