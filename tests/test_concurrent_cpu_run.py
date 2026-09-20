"""Offline scheduling, package and recovery checks; never VM/native acceptance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import concurrent_cpu_run as run, cpu_budget_profiles as profile, cpu_budget_telemetry, fixtures, runner


def row(identifier, status='PASS'):
    return {'id': identifier, 'status': status,
            'sample': {'request_started_monotonic_s': 10., 'request_ended_monotonic_s': 14.,
                       'client_timing': {'ttft_any_output_seconds': 2., 'last_output_seconds': 3.}}}


def native_count(raw):
    body = json.loads(raw)
    glm = body['model'] == 'bench-glm-5.3'
    count = body['messages'][0]['content'].count('record=') * 32 + (112 if glm else 86)
    return {'input_tokens': count, 'body_sha256': fixtures.digest(raw),
            'source': 'native_apply_template_tokenize' if glm else 'native_chat_tokenize',
            'configured_context': 480000, 'template_sha256': run.TEMPLATES['G1' if glm else 'Q1'], 'token_ids_sha256': 'b'*64}


class Scheduling(unittest.TestCase):
    def test_A_common_follows_near_while_G_active_and_each_main_starts(self):
        entered, common_done = threading.Barrier(2), threading.Event()
        calls, conditions = [], []
        def invoke(job):
            calls.append(job['id'])
            if job['id'] in ('g', 'q'):
                entered.wait(timeout=2)
            if job['id'] == 'g':
                self.assertTrue(common_done.wait(2))
            if job['id'] == 'common':
                conditions.append(job['peer_condition_at_admission'])
                common_done.set()
            return row(job['id'])
        result = run.execute_pair({'id': 'g'}, {'id': 'q'}, {'id': 'common'}, invoke)
        self.assertEqual(result['status'], 'COMPLETE', result)
        self.assertEqual(sorted(calls), ['common', 'g', 'q'])
        self.assertLess(calls.index('q'), calls.index('common'))
        self.assertEqual(conditions, ['active_at_dispatch'])
        self.assertEqual(len(result['qwen']), 2)

    def test_A_common_still_runs_after_G_ends_and_B_has_no_common(self):
        # Block near Q until the GLM return has propagated through the lane.
        completed = threading.Event()
        def drain(threads):
            threads[0].join(timeout=2)
            self.assertFalse(threads[0].is_alive())
            completed.set()
            threads[1].join(timeout=2)
            self.assertFalse(threads[1].is_alive())
        for common in ({'id': 'common'}, None):
            completed.clear(); calls = []
            def invoke(job):
                if job['id'] == 'q':
                    self.assertTrue(completed.wait(2))
                calls.append({k: v for k, v in job.items() if k != 'drained_event'})
                return row(job['id'])
            with patch.object(run.prior, 'drain_threads', side_effect=drain):
                result = run.execute_pair({'id': 'g'}, {'id': 'q'}, common, invoke)
            self.assertEqual(result['status'], 'COMPLETE', result)
            self.assertEqual(len(result['qwen']), 2 if common else 1)
            if common:
                self.assertEqual(calls[-1]['peer_condition_at_admission'], 'ended_normally')

    def test_real_failure_stops_common_admission_and_drains_healthy_peer(self):
        entered, qfailed = threading.Barrier(2), threading.Event()
        calls = []
        def invoke(job):
            calls.append(job['id']); entered.wait(timeout=2)
            if job['id'] == 'q':
                qfailed.set()
                return row('q', 'STOP_NATIVE_OR_TRANSPORT')
            self.assertTrue(qfailed.wait(2))
            calls.append('g-drained')
            return row('g')
        result = run.execute_pair({'id': 'g'}, {'id': 'q'}, {'id': 'common'}, invoke)
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('g-drained', calls)
        self.assertNotIn('common', calls)
        self.assertEqual(result['glm']['status'], 'PASS')

    def test_transport_drained_G_is_not_labeled_active_while_result_pending(self):
        entered, qdone = threading.Barrier(2), threading.Event()
        labels = []
        def invoke(job):
            if job['id'] == 'g':
                job['drained_event'].set()
                entered.wait(timeout=2)
                self.assertTrue(qdone.wait(2))
            elif job['id'] == 'q':
                entered.wait(timeout=2)
            else:
                labels.append(job['peer_condition_at_admission'])
                qdone.set()
            return row(job['id'])
        result = run.execute_pair({'id': 'g'}, {'id': 'q'}, {'id': 'common'}, invoke)
        self.assertEqual(result['status'], 'COMPLETE', result)
        self.assertEqual(labels, ['transport_drained_result_pending'])

    def test_request_exception_is_bounded_and_interruption_stops_common_only(self):
        for exceptional in (True, False):
            entered = threading.Barrier(2)
            stop = threading.Event(); stop.set()
            calls = []
            def invoke(job):
                calls.append(job['id']); entered.wait(timeout=2)
                if exceptional and job['id'] == 'q':
                    raise ConnectionError('offline injected transport failure')
                return row(job['id'])
            result = run.execute_pair({'id': 'g'}, {'id': 'q'}, {'id': 'common'}, invoke, interrupted=stop)
            self.assertEqual(sorted(calls), ['g', 'q'])
            self.assertEqual(result['status'], 'FAILED')
            self.assertEqual(len(result['errors']), int(exceptional))


class Clock(unittest.TestCase):
    def test_fresh_75minute_clock_excludes_PREP_and_preserves_request_ceiling(self):
        arm = {'runtime_policy': copy.deepcopy(run.POLICY), 'session_id': 'prep'}
        runtime = {**run.POLICY, 'start_epoch': 100., 'deadline_epoch': 4600.}
        go = {'run_session_id': 'run', 'runtime': runtime}
        self.assertEqual(run.bind_runtime(arm, go, 'run', 101.), runtime)
        self.assertEqual(runtime['request_max_seconds'], 7200)
        self.assertTrue(runtime['excludes_source_prep'])
        self.assertTrue(runtime['restoration_outside_budget'])
        for change in ({'deadline_epoch': 7300.}, {'budget_seconds': 7200},
                       {'start_epoch': float('nan')}, {'extra_clock': 1}):
            bad = {**runtime, **change}
            with self.assertRaises(ValueError): run.validate_clock(arm, bad)
        for extra in ({'continuation_execution': {}}, {'start_epoch': 100.}):
            with self.assertRaises(ValueError): run.validate_clock({**arm, **extra}, runtime)
        for session, now in (('prep', 101.), ('run', 4600.), ('run', 99.), ('wrong', 101.)):
            with self.assertRaises(ValueError): run.bind_runtime(arm, go, session, now)
        old = {**run.POLICY, 'start_epoch': run.prior.ORIGINAL_START, 'deadline_epoch': run.prior.EXTENDED_DEADLINE}
        with self.assertRaises(ValueError): run.validate_clock(arm, old)


class LocalPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name); self.task = self.parent / 'CPU-PREP'; self.task.mkdir()
        self.source_files = {'scripts/offline-example.py': b'# inert source stub\n'}
        self.commit = 'd'*40
        self.patches = [patch.object(run.glmrepair, 'git', side_effect=lambda *a: '' if a[0] == 'status' else self.commit),
                        patch.object(run.runner, 'source_files', return_value=self.source_files)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        (self.task / 'incoming-latest.md').write_text('Bounded source authority; routine note, no STOP directive.\n')
        self.saved = {}
        for name, model, records, seed in [('G1-frozen.json', 'bench-glm-5.3', 2028, run.g1_ladder.SEED),
                                          ('Q256K-frozen.json', 'bench-qwen3.8-27b', 8173, 'historical-qwen-seed')]:
            source = self.parent / ('saved-' + name)
            runner.save(source, fixtures.build_sample(model, records, seed, 'original-frozen-prefix'))
            self.saved[name] = (source.name, fixtures.digest(source.read_bytes()))
        proof = self.parent / 'proof.json'; runner.save(proof, {'evidence': 'synthetic offline fixture only'})
        runner.save(self.task / 'evidence-index.json', {'refs': {'old-proof': {'path': str(proof), 'sha256': fixtures.digest(proof.read_bytes())}},
                    'protected_key_metadata': {'mode': '0o700', 'bytes': 'NOT_READ'}})
        with patch.object(run, 'SAVED', self.saved): self.armed = run.prepare(self.task, 'prep-session')
        self.executed = {**self.armed, 'session_id': 'run-session',
                         'runtime': {**run.POLICY, 'start_epoch': 100., 'deadline_epoch': 4600.}}

    def job(self):
        host = Mock(); host.call.side_effect = AssertionError('unexpected host contact')
        job = run.CPURun(self.task, self.executed, host, 'offline-only-key',
                         transport_factory=Mock(side_effect=AssertionError('unexpected transport')),
                         json_factory=Mock(side_effect=AssertionError('unexpected counting transport')))
        return job

    def test_constructor_checkpoint_and_complete_initial_read_chain_are_offline(self):
        job = self.job()
        run.prior.verify_initial_package(self.task, self.armed)
        run.verify_frozen(self.task, self.armed)
        job.boundary()
        job.record('OFFLINE_CONSTRUCTOR_CHECK')
        self.assertEqual(json.loads((self.task / 'status.json').read_bytes())['phase'], 'OFFLINE_CONSTRUCTOR_CHECK')
        self.assertTrue((self.task / 'incoming-observed.json').is_file())
        self.assertTrue(set(('progress.json', 'incoming-latest.md', 'run-control.json', 'protected-key-metadata.json')) <= set(self.armed['required_package_files']))
        self.assertFalse((self.task / 'execution-arm.json').exists())
        self.assertNotIn('start_epoch', self.armed)
        job.host.call.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'arm_exists_no_reset'): run.prepare(self.task, 'new-prep')
        for note in ('STOP\n', 'PAUSE\n', 'ACTION: STOP\n'):
            (self.task / 'incoming-latest.md').write_text(note)
            with self.assertRaisesRegex(RuntimeError, 'ROOT_EXPLICIT_STOP_OR_PAUSE'): job.boundary()
        (self.task / 'incoming-latest.md').write_text('ordinary observation\n')
        runner.save(self.task / 'run-control.json', {'action': 'PAUSE'})
        with self.assertRaisesRegex(RuntimeError, 'ROOT_CONTROL_PAUSE'): job.boundary()

    def test_missing_package_files_and_changed_frozen_proofs_fail_before_network(self):
        for name in self.armed['required_package_files']:
            path = self.task / name; saved = path.read_bytes(); path.unlink()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'required_package_file_missing'):
                run.prior.verify_initial_package(self.task, self.armed)
            path.write_bytes(saved)
        proof = self.task / 'private/saved/old-proof.json'
        proof.write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'frozen_input_changed'): self.job()

    def test_G_saved_2028_records_schema_exact_recount_and_no_refit(self):
        job = self.job(); job.boundary = Mock(); job.counter = Mock(return_value=native_count)
        job.active['g'] = {'manifest': profile.manifest('A', 'G1')}
        before = json.loads((job.private / 'G1-frozen.json').read_bytes())
        with patch.object(run.time, 'time_ns', side_effect=[111, 222]):
            a = job.prepare_job('g', 'A-G65008')
            job.active['g']['manifest'] = profile.manifest('B', 'G1')
            b = job.prepare_job('g', 'B-G65008')
        for prepared in (a, b):
            self.assertEqual(prepared['count']['input_tokens'], 65008)
            body = json.loads(prepared['raw'])
            self.assertEqual((body['max_tokens'], body['temperature'], body['seed'], body['reasoning_effort']), (256, 1., 1729, 'low'))
            self.assertEqual(body['response_format'], run.g1_ladder.SCHEMA)
            for field in ('records', 'seed', 'fixture_sha256', 'scorer'):
                self.assertEqual(prepared['sample'][field], before[field])
        self.assertNotEqual(a['sample']['nonce'], b['sample']['nonce'])
        bad = lambda raw: {**native_count(raw), 'input_tokens': 65025}
        job.counter = Mock(return_value=bad)
        with self.assertRaisesRegex(ValueError, 'no_refit'): job.prepare_job('g', 'B-G65008')
        self.assertFalse((job.private / 'bad-G-fixture.json').exists())

    def test_exact_five_tuple_guard_rejects_extra_cases_before_native_count(self):
        job = self.job(); job.boundary = Mock()
        job.counter = Mock(side_effect=AssertionError('native count must not be reached'))
        cases = [
            ('A', 'G1', 'A-G480K', {}),
            ('A', 'G1', 'B-G65008', {}),
            ('A', 'Q1', 'A-G65008', {}),
            ('B', 'Q1', 'A-Q256K', {'common': True}),
            ('A', 'Q1', 'A-Q256K', {}),
            ('A', 'Q1', 'A-Qnear480K', {'common': True}),
            ('B', 'Q1', 'B-Qnear480K', {}),
            ('A', 'Q1', 'A-Qnear480K', {'matched': {}}),
            ('A', 'G1', 'A-G65008', {'matched': {}}),
        ]
        for layout, placement, identifier, options in cases:
            job.active['test'] = {'manifest': profile.manifest(layout, placement)}
            with self.subTest(identifier=identifier, options=options), \
                    self.assertRaisesRegex(ValueError, 'exact_five_trial_tuple'):
                job.prepare_job('test', identifier, **options)
        job.counter.assert_not_called()

    def test_Q_near_matched_B_and_common_frozen_261622_keep_pool480000(self):
        job = self.job(); job.boundary = Mock(); job.counter = Mock(return_value=native_count)
        job.active['q'] = {'manifest': profile.manifest('A', 'Q1')}
        with patch.object(run.time, 'time_ns', side_effect=[111, 222, 333]):
            near = job.prepare_job('q', 'A-Qnear480K')
            common = job.prepare_job('q', 'A-Q256K', common=True)
            job.active['q']['manifest'] = profile.manifest('B', 'Q1')
            matched = job.prepare_job('q', 'B-Qnear480K', matched=near['sample'])
        self.assertTrue(479360 <= near['count']['input_tokens'] <= 479488)
        self.assertEqual(common['count']['input_tokens'], 261622)
        self.assertEqual(near['sample']['fixture_sha256'], matched['sample']['fixture_sha256'])
        self.assertEqual(near['sample']['scorer'], matched['sample']['scorer'])
        self.assertNotEqual(near['sample']['nonce'], matched['sample']['nonce'])
        for prepared in (near, common, matched):
            self.assertEqual(prepared['count']['configured_context'], 480000)
            self.assertEqual(prepared['count']['margin_tokens'], 256)
            self.assertEqual(json.loads(prepared['raw'])['max_tokens'], 256)
        self.assertNotEqual(common['sample']['fixture_sha256'], near['sample']['fixture_sha256'])

    def test_output_32_or256_only_and_warmup_counts_final_32_body(self):
        job = self.job()
        with patch.object(run.prior.ConcurrentRun, 'request', return_value={'offline': True}) as parent:
            for cap in (32, 256): self.assertEqual(job.request('g', fixtures.canonical({'max_tokens': cap}), 'x'), {'offline': True})
            with self.assertRaisesRegex(ValueError, 'closed_output'): job.request('g', fixtures.canonical({'max_tokens': 512}), 'bad')
            self.assertEqual(parent.call_count, 2)
        for placement, cid in (('G1', 'g'), ('Q1', 'q')):
            manifest = profile.manifest('A', placement); job.active[cid] = {'manifest': manifest}
            job.counter = Mock(return_value=native_count); job.boundary = Mock(); job.emit = Mock(); job.collect = Mock()
            job.host.call = Mock(return_value={'offline': True})
            calls = []
            def request(cid, raw, identifier, **kwargs):
                calls.append((json.loads(raw), kwargs))
                return {'parsed': {'status': 'COMPLETE'}, 'summary': {'status': 'COMPLETE', 'counters': {
                    'prompt_tokens': native_count(raw)['input_tokens'], 'completion_tokens': 32}}}
            job.request = request
            with patch.object(run, 'prefill_proof', return_value={'offline': True}), \
                    patch.object(cpu_budget_telemetry, 'warmup_gate', return_value={'status': 'PASS'}) as gate:
                job.warm(cid, manifest, {})
            gate.assert_called_once_with([], cid)
            self.assertEqual(job.collect.call_count, 2)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0]['max_tokens'], 32)
            self.assertEqual(calls[0][1], {'timed': False})
            self.assertGreaterEqual(native_count(fixtures.canonical(calls[0][0]))['input_tokens'], 2048)
            if placement == 'G1': self.assertEqual(calls[0][0]['response_format'], run.g1_ladder.SCHEMA)
            self.assertEqual(job.emit.call_args.args[0]['timings'], 'DISCARDED')

    def test_missing_CPU_warmup_evidence_stops_before_long_admission_no_extra_inference(self):
        job = self.job(); job.boundary = Mock(); job.emit = Mock(); job.collect = Mock()
        manifest = profile.manifest('A', 'Q1'); job.active['q'] = {'manifest': manifest}
        job.counter = Mock(return_value=native_count)
        job.request = Mock(return_value={'parsed': {'status': 'COMPLETE'}, 'summary': {
            'status': 'COMPLETE', 'counters': {'prompt_tokens': 2646, 'completion_tokens': 32}}})
        cause = {'status': 'UNAVAILABLE', 'reason': 'per_vcpu_counter_missing'}
        with patch.object(cpu_budget_telemetry, 'warmup_gate', return_value=cause), \
                self.assertRaisesRegex(RuntimeError, 'STOP_CPU_WARMUP_EVIDENCE_UNAVAILABLE'):
            job.warm('q', manifest, {})
        job.request.assert_called_once()
        self.assertEqual(job.request.call_args.kwargs, {'timed': False})
        self.assertEqual(job.counter.call_count, 1)
        self.assertEqual(job.collect.call_count, 2)
        job.boundary.assert_not_called()
        job.host.call.assert_not_called()
        self.assertEqual(json.loads((self.task / 'A-Q1-warmup-cpu-evidence.json').read_bytes()), cause)
        self.assertEqual(job.emit.call_args.args[0]['type'], 'cpu_warmup_UNAVAILABLE')

    def test_sequence_only_A_pair_common_then_B_matched_pair_with_two_retirements(self):
        job = self.job(); job.boundary = Mock(); job.emit = Mock(); rounds, prepared, events = [], [], []
        def host(op, **kwargs):
            events.append(op)
            if op == 'admit_concurrent': return {'manifests': [profile.manifest(kwargs['round'], p) for p in ('G1', 'Q1')]}
            return {}
        job.host.call = host
        def loaded(m):
            cid = m['layout'] + m['placement']; job.active[cid] = {'manifest': m}; return cid
        job.loaded = loaded
        def prepare(cid, identifier, **kwargs):
            value = {'id': identifier, 'cid': cid, 'sample': {'logical_fixture': identifier}, 'options': kwargs}
            prepared.append(value); return value
        job.prepare_job = prepare
        def execute(g, q, common, *args, **kwargs):
            rounds.append((g, q, common)); return {'status': 'COMPLETE'}
        job.retire_all = Mock(side_effect=lambda: job.active.clear())
        with patch.object(run, 'execute_pair', side_effect=execute): job.sequence()
        self.assertEqual([p['id'] for p in prepared], ['A-G65008', 'A-Qnear480K', 'A-Q256K', 'B-G65008', 'B-Qnear480K'])
        self.assertEqual(rounds[0][2]['id'], 'A-Q256K')
        self.assertIsNone(rounds[1][2])
        self.assertEqual(rounds[1][1]['options']['matched'], rounds[0][1]['sample'])
        self.assertEqual(job.retire_all.call_count, 2)
        self.assertEqual(job.progress['phase'], 'MEASUREMENTS_COMPLETE')

    def test_duplicate_measurement_does_not_repeat_inference(self):
        job = self.job(); job.boundary = Mock(); job.counter = Mock(return_value=native_count)
        job.active['g'] = {'manifest': profile.manifest('A', 'G1')}
        prepared = job.prepare_job('g', 'A-G65008')
        job.progress['completed']['A-G65008'] = {'status': 'PASS'}
        job.request = Mock(side_effect=AssertionError('duplicate inference attempted'))
        with self.assertRaisesRegex(RuntimeError, 'no_measurement_retry'):
            job.measure(prepared)
        job.request.assert_not_called()

    def test_RUN_missing_file_or_existing_execution_is_rejected_before_keys_or_host(self):
        receipt = json.loads((self.task / 'arm-receipt.json').read_bytes())
        go = {**receipt, 'decision': 'GO', 'vm_writer_handoff': True, 'run_session_id': 'run-session',
              'runtime': self.executed['runtime']}
        path = self.task / 'GO.json'; runner.save(path, go)
        with patch.object(run.os, 'geteuid', return_value=501), patch.object(run, '_keys') as keys, \
                patch.object(run.glmrepair, 'DiagnosticSSHHost') as host:
            required = self.task / 'progress.json'; raw = required.read_bytes(); required.unlink()
            with self.assertRaisesRegex(ValueError, 'required_package_file_missing'):
                run.run(self.task, path, 'run-session')
            required.write_bytes(raw)
            runner.save(self.task / 'execution-arm.json', {})
            with self.assertRaisesRegex(ValueError, 'no_rerun_or_clock_reset'):
                run.run(self.task, path, 'run-session')
            keys.assert_not_called(); host.assert_not_called()


class Recovery(unittest.TestCase):
    def test_one_diagnostic_then_direct_canonical_recover_and_finalize(self):
        events = []
        class Host:
            def __init__(self, label, phase): self.label, self.phase = label, phase
            def call(self, op, **kwargs):
                events.append((self.label, op))
                if op == 'status': return {'phase': self.phase}
                if op == 'rpc_diagnostics': return {'cause': 'fixed offline recovery cause'}
                if op == 'recover': self.phase = 'POST_RELEASE_LAN_VERIFICATION_PENDING'; return {}
                if op == 'verify_restoration': self.phase = 'RESTORED'; return {}
                raise AssertionError(op)
            def close(self): events.append((self.label, 'close'))
        old, replacement = Host('old', 'RECOVERY_REQUIRED'), Host('new', 'NEW')
        factory = Mock(return_value=replacement)
        with tempfile.TemporaryDirectory() as td:
            actual = run.restore_once(old, {}, Path(td), 'offline-key', 'offline-control', factory=factory,
                                      verify=Mock(return_value={'authenticated': True}))
            self.assertIs(actual, replacement)
            self.assertTrue((Path(td) / 'restoration-rpc-diagnostics.json').is_file())
        self.assertEqual(events.count(('old', 'rpc_diagnostics')), 1)
        self.assertEqual(events.count(('new', 'recover')), 1)
        self.assertNotIn(('old', 'restore'), events)
        factory.assert_called_once_with({}, stage=False)

    def test_diagnostic_failure_does_not_skip_direct_recovery_and_failed_recover_is_not_repeated(self):
        for recovery_fails in (False, True):
            calls = []
            old, new = Mock(), Mock()
            def old_call(op, **kwargs):
                calls.append(('old', op))
                if op == 'status': return {'phase': 'RECOVERY_REQUIRED'}
                if op == 'rpc_diagnostics': raise OSError('offline cause collection failed')
                raise AssertionError(op)
            phase = ['NEW']
            def new_call(op, **kwargs):
                calls.append(('new', op))
                if op == 'status': return {'phase': phase[0]}
                if op == 'recover':
                    if recovery_fails: raise RuntimeError('offline direct recovery failed')
                    phase[0] = 'POST_RELEASE_LAN_VERIFICATION_PENDING'; return {}
                if op == 'verify_restoration': phase[0] = 'RESTORED'; return {}
                raise AssertionError(op)
            old.call.side_effect = old_call; new.call.side_effect = new_call
            factory = Mock(return_value=new)
            with tempfile.TemporaryDirectory() as td:
                if recovery_fails:
                    with self.assertRaisesRegex(run.RecoveryRequired, 'preserve_ledger'):
                        run.restore_once(old, {}, Path(td), 'offline', 'offline', factory=factory, verify=Mock(return_value={}))
                    new.close.assert_not_called()  # Failed recovery keeps its owning session/ledger.
                else:
                    self.assertIs(run.restore_once(old, {}, Path(td), 'offline', 'offline', factory=factory,
                                                  verify=Mock(return_value={})), new)
                diagnostic = json.loads((Path(td) / 'restoration-rpc-diagnostics.json').read_bytes())
                self.assertEqual(diagnostic, {'status': 'UNAVAILABLE', 'error_class': 'OSError'})
            self.assertEqual(calls.count(('old', 'rpc_diagnostics')), 1)
            self.assertEqual(calls.count(('new', 'recover')), 1)
            factory.assert_called_once_with({}, stage=False)


if __name__ == '__main__': unittest.main()
