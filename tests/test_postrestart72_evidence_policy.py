"""REAL72 current proof and immutable faults through actual offline runner/host gates.

The reused sanitized fixture is RUN1 evidence, not a reconstruction of RUN3's
unretained raw error. Mutations below are explicitly synthetic policy cases.
"""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import fixtures, postrestart72_run as run72
from tests.test_benchmark_client import event, stream
from tests import test_postrestart72_loading_gap as loading_gap
from tests import test_postrestart72_clocks as clocks
from tests.test_postrestart72_run import armed, short_row

GIB = 1024 ** 3


class EvidencePolicyTests(unittest.TestCase):
    def setup_case(self, *, ready=True):
        base, host, rows, saved = loading_gap.LoadingAccountingGapTests.setup_case(self)
        job = run72.PostrestartRun(base.state, armed(), base.host,
                                  'synthetic-nonsecret', sleep=Mock())
        job.active = base.active
        job.root_paused = Mock(return_value=False)
        if ready:
            host.allocation_proofs['q'] = {}
            job.active['q']['phase'] = 'ready'
        host.postrestart_measured_admissions = {'G1': 0, 'Q1': 0}
        return job, host, rows, saved

    def test_pre_and_post_readiness_gaps_are_current_proof_not_faults(self):
        for ready in (False, True):
            with self.subTest(ready=ready):
                job, _, rows, _ = self.setup_case(ready=ready)
                job.collect()
                self.assertTrue(job.proof_pending)
                self.assertEqual(job.safety, {})
                self.assertFalse(any(v['cancel_event'].is_set() for v in job.active.values()))
                self.assertFalse(any(v.get('abort_reason') for v in job.active.values()))
                raw = (job.state / 'results.jsonl').read_bytes()
                historical = [json.loads(v) for v in raw.splitlines()]
                self.assertTrue(all(v['sample']['concurrent_resource_gate']['status'] == 'UNAVAILABLE'
                                    for v in historical))
                rows['current'] = rows['good']
                job.collect()
                self.assertIsNone(job.proof_pending)
                self.assertTrue((job.state / 'results.jsonl').read_bytes().startswith(raw))
                self.assertIsNone(historical[0]['sample']['processes']['q']['rss_bytes'])
                self.assertEqual(historical[0]['sample']['errors'], rows['gap']['errors'])

    def test_every_required_safety_field_is_full_proof_not_missing_zero(self):
        fields = [
            ('cgroups', 'q', 'swap_bytes'), ('cgroups', 'g', 'current_bytes'),
            ('cgroups', 'q', 'peak_since_cgroup_creation_bytes'),
            ('cgroups', 'q', 'events', 'oom'), ('cgroups', 'q', 'events', 'oom_kill'),
            ('cgroups', 'q', 'events', 'oom_group_kill'),
            ('processes', 'q', 'rss_bytes'), ('processes', 'q', 'swap_bytes'),
            ('processes', 'q', 'known_process_count'),
            ('host', 'available_bytes'), ('vmstat', 'oom_kill'), ('vmstat', 'pswpin'),
            ('gpus', 1, 'free_bytes'), ('gpus', 1, 'total_bytes'),
        ]
        for field in fields:
            for unavailable in (None, False, '0'):
                with self.subTest(field=field, unavailable=unavailable):
                    job, host, rows, _ = self.setup_case()
                    row = copy.deepcopy(rows['good'])
                    parent = row
                    for component in field[:-1]:
                        parent = parent[component]
                    parent[field[-1]] = unavailable
                    rows['current'] = row
                    job.collect()
                    self.assertEqual(host.concurrent_pressure(row)['status'], 'UNAVAILABLE')
                    self.assertTrue(job.proof_pending)
                    self.assertEqual(job.safety, {})
                    self.assertFalse(any(v['cancel_event'].is_set() for v in job.active.values()))
        for error in ('read_PermissionError', 'gpu_TimeoutExpired', 'read_FileNotFoundError'):
            with self.subTest(error=error):
                job, host, rows, _ = self.setup_case()
                rows['current'] = copy.deepcopy(rows['good'])
                rows['current']['errors'] = [error]
                job.collect()
                self.assertEqual(host.concurrent_pressure(rows['current'])['status'], 'UNAVAILABLE')
                self.assertTrue(job.proof_pending)
                self.assertEqual(job.safety, {})

    def test_isolated_gap_fresh_full_pass_then_actual_host_admission(self):
        job, host, rows, _ = self.setup_case()
        job.collect()
        raw_gap = (job.state / 'results.jsonl').read_bytes()
        self.assertTrue(job.proof_pending)
        rows['current'] = rows['good']
        self.assertEqual(job.admission('q'), 7200)
        self.assertIsNone(job.proof_pending)
        self.assertEqual(host.requests['q']['timeout_s'], 7200)
        self.assertEqual(rows['calls'].count('request_begin'), 1)
        self.assertTrue((job.state / 'results.jsonl').read_bytes().startswith(raw_gap))
        job.host.call('request_end', id='q')
        self.assertEqual(host.requests, {})

    def test_persistent_gap_bounded_resampling_blocks_new_registration(self):
        job, host, rows, _ = self.setup_case()
        job.collect(); rows['calls'].clear()
        with self.assertRaises(run72.EvidenceReview):
            job.admission('q')
        self.assertLessEqual(rows['calls'].count('telemetry'), 3 * len(job.active))
        self.assertGreater(rows['calls'].count('telemetry'), 0)
        self.assertNotIn('request_begin', rows['calls'])
        self.assertEqual(host.requests, {})
        self.assertTrue(job.proof_pending)
        self.assertEqual(job.safety, {})
        self.assertFalse(any(v['cancel_event'].is_set() for v in job.active.values()))

    def test_host_fresh_gap_refusal_cannot_reuse_old_pass_or_start_request_clock(self):
        job, host, rows, _ = self.setup_case()
        rows['current'] = rows['good']; job.collect()
        self.assertIsNone(job.proof_pending)
        rows['current'] = rows['gap']
        response = job.host.call('request_begin', id='q', timeout_s=7200, measured=True)
        self.assertIs(response['proof_pending'], True)
        self.assertEqual(host.requests, {})
        self.assertEqual(host.postrestart_measured_admissions, {'G1': 0, 'Q1': 0})
        host.budget.request_timeout.assert_not_called()

    def test_readiness_resamples_only_explicit_gap_three_times_within_existing_budget(self):
        gap = {'ready': False, 'failed': True, 'resource_proof_unavailable_only': True,
               'allocation': {'status': 'ALLOCATION_PROOF_REJECTED'}}
        good = {'ready': True, 'allocation': {'status': 'ALLOCATION_PROOF_ACCEPTED'}}
        for responses, expected_calls, expected in (([gap, good], 2, good),
                ([gap, gap, gap], 3, gap), ([{'ready': False, 'failed': True}], 1, {'ready': False, 'failed': True})):
            with self.subTest(expected_calls=expected_calls):
                _, host, _, _ = self.setup_case()
                host.budget.checkpoint.return_value = 100
                host._readiness = Mock(side_effect=copy.deepcopy(responses))
                result = host.readiness('q', timeout_s=50)
                self.assertEqual(result, expected)
                self.assertEqual(host._readiness.call_count, expected_calls)
                if expected_calls > 1:
                    receipt = host.write_json.call_args.args[1]
                    self.assertEqual(receipt['attempt_limit'], 3)
                    self.assertEqual(len(receipt['attempts']), expected_calls)
                else:
                    host.write_json.assert_not_called()
        _, host, _, _ = self.setup_case()
        host.budget.checkpoint.return_value = 100
        host._readiness = Mock(side_effect=[gap, {'ready': False}, gap, good])
        host.readiness('q')
        first_path, first_receipt = host.write_json.call_args.args
        host.readiness('q')
        second_path, second_receipt = host.write_json.call_args.args
        self.assertNotEqual(first_path, second_path)
        self.assertFalse(first_receipt['attempts'][-1]['ready'])
        self.assertTrue(second_receipt['attempts'][-1]['ready'])
        job, host, rows, _ = self.setup_case()
        host.budget.checkpoint.return_value = 0
        host._readiness = Mock()
        with self.assertRaisesRegex(ValueError, 'STOP_BUDGET'):
            host.readiness('q')
        host._readiness.assert_not_called()
        original = job.host.call.side_effect
        job.host.call.side_effect = lambda op, **args: {'remaining_s': 0} if op == 'budget' else original(op, **args)
        with self.assertRaises(run72.EvidenceReview):
            job.ensure_current_proof()
        self.assertLessEqual(rows['calls'].count('telemetry'), len(job.active))

    def test_real_guarded_hold_checkpoint_distinguishes_incomplete_proof_from_admission(self):
        for missing, expected in ((False, 'HELD'), (True, 'REVIEW_REQUIRED')):
            with self.subTest(missing=missing):
                _, original, rows, _ = self.setup_case()
                host = clocks.HostIntegrationTests.held_host(self)
                host.config = original.config
                host.load_manifests = original.load_manifests
                sample = copy.deepcopy(rows['good'])
                if missing:
                    sample['cgroups']['q']['events']['oom_kill'] = None
                def native(port, route, **kwargs):
                    if route == '/v1/models':
                        return {'data': [{'id': 'bench-glm-5.3' if port == 31002 else 'bench-qwen3.8-27b'}]}
                    return {'context_length': 480000, 'tp_size': 1,
                            'max_total_num_tokens': 480000, 'max_req_input_len': 479994}
                with patch('benchmark.host.collect_sample', return_value=sample), \
                     patch('benchmark.host.http_json', side_effect=native):
                    result = host.dispatch({'op': 'hold_checkpoint'})
                self.assertEqual(result['status'], expected)
                self.assertIs(result['guarded'], True)
                self.assertIs(result['no_active_inference'], True)
                self.assertEqual(host.owner.phase, 'WARM_HOLD')
                self.assertEqual(host.requests, {})

    def test_missing_gpu_proof_can_recover_but_foreign_identity_stays_latched(self):
        for foreign in (False, True):
            with self.subTest(foreign=foreign):
                job, host, rows, _ = self.setup_case()
                rows['current'] = copy.deepcopy(rows['good'])
                if foreign:
                    rows['current']['gpus'][1]['uuid'] = 'GPU-foreign-synthetic'
                else:
                    rows['current']['gpus'].pop()
                job.collect()
                self.assertEqual(bool(job.safety), foreign)
                if not foreign:
                    self.assertTrue(job.proof_pending)
                rows['current'] = rows['good']; job.collect()
                if foreign:
                    self.assertTrue(job.safety)
                    with self.assertRaises(RuntimeError):
                        job.admission('q')
                    self.assertEqual(host.requests, {})
                else:
                    self.assertIsNone(job.proof_pending)
                    self.assertEqual(job.admission('q'), 7200)

    def test_numeric_fault_on_incomplete_sample_stays_latched_after_full_pass(self):
        for fault in ('cap', 'hostreserve', 'vram', 'oom', 'cgroup_swap', 'process_swap'):
            with self.subTest(fault=fault):
                job, host, rows, _ = self.setup_case()
                group = rows['gap']['cgroups']['q']
                if fault == 'cap': group['anon_bytes'] = 32 * GIB
                elif fault == 'hostreserve': rows['gap']['host']['available_bytes'] = 0
                elif fault == 'vram': rows['gap']['gpus'][1]['free_bytes'] = 0
                elif fault == 'oom': group['events']['oom'] = 1
                elif fault == 'cgroup_swap': group['swap_bytes'] = 4096
                else: rows['gap']['processes']['q']['swap_bytes'] = 4096
                job.collect()
                first_safety = dict(job.safety)
                self.assertTrue(first_safety)
                self.assertTrue(host.concurrent_resource_violations)
                self.assertTrue(job.active['q']['cancel_event'].is_set())
                abort = job.active['q']['abort_reason']
                rows['current'] = rows['good']; job.collect()
                self.assertEqual(job.safety, first_safety)
                self.assertEqual(job.active['q']['abort_reason'], abort)
                self.assertTrue(job.active['q']['cancel_event'].is_set())
                with self.assertRaises(RuntimeError) as raised:
                    job.admission('q')
                self.assertNotIsInstance(raised.exception, run72.EvidenceReview)
                self.assertEqual(host.requests, {})

    def test_identity_storage_or_rpc_admission_fault_latches_before_later_pass(self):
        for failure in ('rpc_unavailable', 'container_identity_changed', 'registered_storage_guard_failed'):
            with self.subTest(failure=failure):
                job, host, rows, _ = self.setup_case()
                rows['current'] = rows['good']
                original = job.host.call.side_effect
                def call(op, **args):
                    if op == 'request_begin':
                        raise RuntimeError(failure)
                    return original(op, **args)
                job.host.call.side_effect = call
                with self.assertRaisesRegex(RuntimeError, failure):
                    job.admission('q')
                self.assertTrue(job.safety)
                latched = dict(job.safety)
                job.host.call.side_effect = original
                job.collect()
                self.assertEqual(job.safety, latched)
                with self.assertRaises(RuntimeError) as raised:
                    job.admission('q')
                self.assertNotIsInstance(raised.exception, run72.EvidenceReview)
                self.assertEqual(host.requests, {})

    def test_fresh_host_gap_after_client_pass_returns_to_review_without_fault(self):
        job, host, rows, _ = self.setup_case()
        rows['current'] = rows['good']
        original = job.host.call.side_effect
        def call(op, **args):
            if op == 'request_begin':
                rows['current'] = rows['gap']
            return original(op, **args)
        job.host.call.side_effect = call
        with self.assertRaises(run72.EvidenceReview):
            job.admission('q')
        self.assertTrue(job.proof_pending)
        self.assertEqual(job.safety, {})
        self.assertEqual(host.requests, {})
        self.assertEqual(rows['calls'].count('request_begin'), 1)

    def test_final_host_pending_has_three_total_attempts_and_at_most_one_dispatch(self):
        for pending_count in (1, 3):
            with self.subTest(pending_count=pending_count):
                job, host, rows, _ = self.setup_case()
                rows['current'] = rows['good']
                original = job.host.call.side_effect
                attempts, replies, registrations = [], [], []
                def write(name, value):
                    if name == 'requests.json' and value:
                        registrations.append(copy.deepcopy(value))
                host.write_json.side_effect = write
                def call(op, **args):
                    if op != 'request_begin':
                        return original(op, **args)
                    attempts.append(copy.deepcopy(args))
                    rows['current'] = rows['gap'] if len(attempts) <= pending_count else rows['good']
                    try:
                        reply = original(op, **args)
                        replies.append(copy.deepcopy(reply))
                        return reply
                    finally:
                        # A fresh coherent monitor sample can succeed while
                        # the subsequent authoritative final gate races again.
                        rows['current'] = rows['good']
                job.host.call.side_effect = call
                dispatched = []
                def transport(body, seconds):
                    dispatched.append((body, seconds))
                    self.assertEqual(set(host.requests), {'g'})
                    yield stream([event({'role': 'assistant', 'content': 'ok'}, 'stop')])
                job.transport_factory = Mock(return_value=transport)
                raw = fixtures.canonical({'model': 'bench-glm-5.3', 'messages': [{'role': 'user', 'content': 'offline'}],
                                          'max_tokens': 32, 'stream': True})
                if pending_count == 1:
                    response = job.request('g', raw, 'offline-final-gate', timed=True)
                    self.assertEqual(response['summary']['status'], 'COMPLETE')
                else:
                    with self.assertRaises(run72.EvidenceReview):
                        job.request('g', raw, 'offline-final-gate', timed=True)
                expected = {'id': 'g', 'timeout_s': 7200, 'measured': True,
                    'request_identity': {'request_id': 'offline-final-gate', 'request_sha256': fixtures.digest(raw),
                        'manifest_sha256': fixtures.digest(fixtures.canonical(job.active['g']['manifest']))}}
                self.assertEqual(attempts, [expected] * (2 if pending_count == 1 else 3))
                granted = int(pending_count == 1)
                self.assertEqual(len(dispatched), granted)
                self.assertEqual(len(registrations), granted)
                self.assertEqual(job.transport_factory.call_count, granted)
                self.assertEqual(host.budget.request_timeout.call_count, granted)
                self.assertEqual(host.postrestart_measured_admissions['G1'], granted)
                self.assertEqual(sum('timeout_s' in reply for reply in replies), granted)
                self.assertEqual(rows['calls'].count('request_end'), granted)
                self.assertEqual(host.requests, {})
                self.assertEqual(job.safety, {})
                journal = [json.loads(line) for line in (job.state / 'results.jsonl').read_bytes().splitlines()]
                pending = [row for row in journal if row.get('type') == 'admission_proof_pending']
                self.assertEqual(len(pending), pending_count)
                self.assertTrue(all(row['proof']['sample']['errors'] == rows['gap']['errors'] for row in pending))

    def test_final_gate_retry_freezes_caller_request_identity(self):
        job, host, rows, _ = self.setup_case()
        rows['current'] = rows['good']
        identity = {'request_id': 'offline-bound', 'request_sha256': 'a' * 64,
                    'manifest_sha256': 'b' * 64}
        original_identity = copy.deepcopy(identity)
        original = job.host.call.side_effect
        attempts = []
        def call(op, **args):
            if op != 'request_begin':
                return original(op, **args)
            attempts.append(copy.deepcopy(args))
            if len(attempts) == 1:
                rows['current'] = rows['gap']
                reply = original(op, **args)
                identity['request_id'] = 'caller-changed-after-entry'
                rows['current'] = rows['good']
                return reply
            return original(op, **args)
        job.host.call.side_effect = call
        self.assertEqual(job.admission('g', measured=True, request_identity=identity), 7200)
        self.assertEqual([args['request_identity'] for args in attempts], [original_identity] * 2)
        job.host.call('request_end', id='g')

    def test_final_gate_nonpending_or_ambiguous_responses_never_retry(self):
        variants = ('exception', 'none', 'list', 'empty', 'missing_sample', 'sample_not_object',
                    'admitted', 'untyped_admitted', 'untyped_pending', 'wrong_status', 'timeout', 'budget',
                    'extra_key', 'gate_sample_disagree', 'numeric_fault')
        for variant in variants:
            with self.subTest(variant=variant):
                job, host, rows, _ = self.setup_case()
                pending = job.host.call('request_begin', id='g', timeout_s=7200, measured=True)
                rows['current'] = rows['good']; rows['calls'].clear()
                response = copy.deepcopy(pending)
                if variant == 'none': response = None
                elif variant == 'list': response = []
                elif variant == 'empty': response = {}
                elif variant == 'missing_sample': response.pop('sample')
                elif variant == 'sample_not_object': response['sample'] = None
                elif variant == 'admitted': response['admitted'] = True
                elif variant == 'untyped_admitted': response['admitted'] = 0
                elif variant == 'untyped_pending': response['proof_pending'] = 1
                elif variant == 'wrong_status': response['resource_gate']['status'] = 'PASS'
                elif variant == 'timeout': response['timeout_s'] = 7200
                elif variant == 'budget': response['budget'] = {}
                elif variant == 'extra_key': response['unexpected'] = True
                elif variant == 'gate_sample_disagree': response['sample']['concurrent_resource_gate'] = {}
                elif variant == 'numeric_fault': response['resource_gate']['reasons'] = ['numeric_fault']
                original = job.host.call.side_effect
                attempts = []
                def call(op, **args):
                    if op == 'request_begin':
                        attempts.append(copy.deepcopy(args))
                        if variant == 'exception':
                            raise RuntimeError('synthetic_final_rpc_failure')
                        return response
                    return original(op, **args)
                job.host.call.side_effect = call
                job.transport_factory = Mock()
                raw = fixtures.canonical({'model': 'bench-glm-5.3', 'messages': [{'role': 'user', 'content': 'offline'}],
                                          'max_tokens': 32, 'stream': True})
                with self.assertRaises(RuntimeError) as raised:
                    job.request('g', raw, 'offline-no-retry', timed=True)
                self.assertNotIsInstance(raised.exception, run72.EvidenceReview)
                self.assertEqual(len(attempts), 1)
                self.assertTrue(job.safety)
                job.transport_factory.assert_not_called()
                host.budget.request_timeout.assert_not_called()
                self.assertEqual(host.requests, {})
                self.assertNotIn('request_end', rows['calls'])

    def test_undispatched_measurement_gap_removes_only_its_inflight_entry(self):
        job, host, rows, _ = self.setup_case()
        rows['current'] = rows['good']
        self.assertEqual(job.admission('g'), 7200)
        job.progress['inflight']['P-G65008'] = {'container': 'g'}
        sample = fixtures.build_sample('bench-qwen3.8-27b', 20, 'offline-seed', 'offline-nonce')
        raw = fixtures.canonical(sample['body'])
        prepared = {'id': 'P-Qnear480K', 'cid': 'q', 'raw': raw, 'sample': sample,
                    'count': {'body_sha256': fixtures.digest(raw), 'input_tokens': 3000},
                    'manifest_sha256': fixtures.digest(fixtures.canonical(job.active['q']['manifest'])),
                    'generation': False, 'preparation_seconds': 0}
        rows['current'] = rows['gap']
        with self.assertRaises(run72.EvidenceReview):
            job.measure(prepared)
        self.assertEqual(job.progress['inflight'], {'P-G65008': {'container': 'g'}})
        self.assertEqual(set(host.requests), {'g'})
        self.assertFalse(job.active['g']['cancel_event'].is_set())
        job.hold_ready = True
        with self.assertRaisesRegex(RuntimeError, 'idle_closed_hold'):
            job.hold('quality_review')
        job.host.call('request_end', id='g')

    def test_generic_rpc_identity_and_storage_failures_are_not_proof_gaps(self):
        for failure in ('rpc_unavailable', 'container_identity_changed', 'registered_storage_guard_failed'):
            with self.subTest(failure=failure):
                job, _, rows, _ = self.setup_case()
                original = job.host.call.side_effect
                job.host.call.side_effect = RuntimeError(failure)
                job.collect()
                self.assertEqual(set(job.safety.values()), {'HARNESS_FAILURE'})
                latched = dict(job.safety)
                job.host.call.side_effect = original
                rows['current'] = rows['good']; job.collect()
                self.assertEqual(job.safety, latched)
                job.hold_ready = True
                with self.assertRaises(RuntimeError) as raised:
                    job.boundary()
                self.assertNotIsInstance(raised.exception, run72.EvidenceReview)

    def test_abort_reason_and_cancel_event_are_never_reset_by_fresh_pass(self):
        job, host, rows, _ = self.setup_case()
        job.active['q']['abort_reason'] = 'STOP_PRIOR_RESOURCE'
        job.active['q']['cancel_event'].set()
        rows['current'] = rows['good']
        job.collect()
        self.assertEqual(job.active['q']['abort_reason'], 'STOP_PRIOR_RESOURCE')
        self.assertTrue(job.active['q']['cancel_event'].is_set())
        with self.assertRaises(RuntimeError):
            job.admission('q')
        self.assertEqual(host.requests, {})

    def test_inflight_gap_keeps_full_dispatch_timeout_and_drains_registered_work(self):
        job, host, rows, _ = self.setup_case()
        rows['current'] = rows['good']
        drained = threading.Event()
        observed = {}

        def factory(url, key, *, cancel_event, deadline_epoch):
            self.assertIsNone(deadline_epoch)
            def transport(body, seconds):
                observed['timeout_s'] = seconds
                self.assertIn('g', host.requests)
                rows['current'] = rows['gap']; job.collect()
                self.assertTrue(job.proof_pending)
                self.assertFalse(cancel_event.is_set())
                with self.assertRaises(run72.EvidenceReview):
                    job.admission('q')
                self.assertEqual(set(host.requests), {'g'})
                yield stream([event({'role': 'assistant', 'content': 'ok'}, 'stop')])
            return transport

        job.transport_factory = factory
        raw = fixtures.canonical({'model': 'bench-glm-5.3', 'messages': [{'role': 'user', 'content': 'offline'}],
                                  'max_tokens': 32, 'stream': True})
        response = job.request('g', raw, 'offline-warm', timed=False, drained_event=drained)
        self.assertEqual(observed['timeout_s'], 7200)
        self.assertTrue(drained.is_set())
        self.assertEqual(response['summary']['status'], 'COMPLETE')
        self.assertEqual(host.requests, {})
        self.assertEqual(rows['calls'].count('request_end'), 1)
        self.assertTrue(job.proof_pending)
        self.assertEqual(job.safety, {})

    def test_actual_pair_gap_drains_admitted_peer_before_execute_enters_hold(self):
        job, host, rows, _ = self.setup_case()
        rows['current'] = rows['good']
        prepared = {}
        for cid, identifier, model in (('g', 'P-G65008', 'bench-glm-5.3'),
                                       ('q', 'P-Qnear480K', 'bench-qwen3.8-27b')):
            sample = fixtures.build_sample(model, 20, 'offline-seed', 'offline-' + cid)
            raw = fixtures.canonical(sample['body'])
            prepared[identifier] = {'id': identifier, 'cid': cid, 'sample': sample, 'raw': raw,
                'count': {'body_sha256': fixtures.digest(raw), 'input_tokens': 3000},
                'manifest_sha256': fixtures.digest(fixtures.canonical(job.active[cid]['manifest'])),
                'generation': False, 'preparation_seconds': 0}
        original_call = job.host.call.side_effect
        def call(op, **args):
            if op == 'begin': return {}
            if op == 'admit_concurrent': return {'manifests': list(host.load_manifests.values())}
            return original_call(op, **args)
        job.host.call.side_effect = call
        def loaded(manifest):
            cid = 'g' if manifest['placement'] == 'G1' else 'q'
            job.pending_warmups.append((cid, manifest, {}))
            return cid
        job.loaded = loaded
        job.discarded_warmup, job.boundary, job.monitor = Mock(), Mock(), Mock()
        job.prepare_job = lambda cid, identifier: prepared.get(identifier, {'id': identifier})
        job.preliminary_checkpoint = Mock(return_value=True)
        job.measure = lambda item, **kw: short_row() if item['id'] == 'P-G4K' else run72.PostrestartRun.measure(job, item, **kw)
        started, refused = threading.Event(), threading.Event()
        admission = job.admission
        def admit(cid, *args, **kwargs):
            if cid == 'q':
                self.assertTrue(started.wait(2))
                rows['current'] = rows['gap']
                try:
                    return admission(cid, *args, **kwargs)
                finally:
                    refused.set()
            return admission(cid, *args, **kwargs)
        job.admission = admit
        def factory(url, key, *, cancel_event, deadline_epoch):
            self.assertTrue(url.endswith(':31002'))
            self.assertIsNone(deadline_epoch)
            def transport(body, seconds):
                self.assertEqual(seconds, 7200)
                self.assertIn('g', host.requests)
                started.set()
                self.assertTrue(refused.wait(2))
                self.assertFalse(cancel_event.is_set())
                yield stream([event({'role': 'assistant', 'content': json.dumps(prepared['P-G65008']['sample']['scorer']['retrieval'])},
                    'stop', usage={'prompt_tokens': 3000, 'completion_tokens': 3,
                                  'prompt_tokens_details': {'cached_tokens': 0}},
                    timings={'prompt_n': 3000, 'predicted_n': 3, 'prompt_ms': 100, 'predicted_ms': 10})])
            return transport
        job.transport_factory = factory
        def held(reason):
            self.assertEqual(reason, 'quality_review')
            self.assertEqual(host.requests, {})
            self.assertEqual(job.progress['inflight'], {})
            self.assertEqual(job.progress['completed']['P-G65008']['status'], 'PASS')
            self.assertNotIn('P-Qnear480K', job.progress['completed'])
            self.assertTrue(job.proof_pending)
            self.assertEqual(job.safety, {})
        job.hold = Mock(side_effect=held)
        job.execute()
        job.hold.assert_called_once_with('quality_review')
        pair = json.loads((job.state / 'P-pair.json').read_bytes())
        self.assertEqual(pair['errors'], [{'id': 'P-Qnear480K', 'error_class': 'EvidenceReview'}])

    def test_second_validated_warmup_marks_retention_before_review_boundary(self):
        job, host, _, _ = self.setup_case()
        job.hold_ready = False
        manifests = list(host.load_manifests.values())
        validated = []
        job.host.call.side_effect = lambda op, **kw: {'manifests': manifests} if op == 'admit_concurrent' else {}

        def loaded(manifest):
            cid = 'g' if manifest['placement'] == 'G1' else 'q'
            job.pending_warmups.append((cid, manifest, {}))
            return cid

        def warm(cid, *_):
            self.assertFalse(job.hold_ready)
            validated.append(cid)

        def boundary():
            if len(validated) == 2:
                self.assertTrue(job.hold_ready)
                raise run72.EvidenceReview('synthetic_post_warmup_gap')

        job.loaded, job.discarded_warmup = loaded, warm
        job.boundary, job.monitor = boundary, Mock()
        job.hold, job.measure = Mock(), Mock()
        job.execute()
        self.assertEqual(validated, ['g', 'q'])
        job.hold.assert_called_once_with('quality_review')
        job.measure.assert_not_called()

    def test_first_or_invalid_second_warmup_cannot_mark_retention_ready(self):
        job, host, _, _ = self.setup_case()
        job.hold_ready = False
        manifests = list(host.load_manifests.values())
        job.host.call.side_effect = lambda op, **kw: {'manifests': manifests} if op == 'admit_concurrent' else {}
        def loaded(manifest):
            cid = 'g' if manifest['placement'] == 'G1' else 'q'
            job.pending_warmups.append((cid, manifest, {}))
            return cid
        job.loaded = loaded
        job.boundary, job.monitor, job.hold = Mock(), Mock(), Mock()
        job.discarded_warmup = Mock(side_effect=[None, RuntimeError('STOP_WARMUP_NATIVE_COUNT')])
        with self.assertRaisesRegex(RuntimeError, 'STOP_WARMUP_NATIVE_COUNT'):
            job.execute()
        self.assertFalse(job.hold_ready)
        job.hold.assert_not_called()


if __name__ == '__main__':
    unittest.main()
