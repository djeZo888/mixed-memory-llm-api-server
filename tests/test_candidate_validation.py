"""Synthetic source checks only: no VM, acceptance receipt or live fixture proof."""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.test_benchmark_runner import Host
from benchmark import accounting, concurrent_validate as candidate, fixtures, profiles, runner


def token_count(body):
    return 160 + 16 * len(body['messages'])


class CandidateHost(Host):
    """Extend the existing synthetic host; do not invent a live proof receipt."""
    def call(self, op, **args):
        if op in {'candidate_evidence', 'candidate_denials'}:
            self.events.append((op, args))
            return {'evidence_kind': 'synthetic_offline'}
        if op == 'quiescent':
            result = super().call(op, **args)
            return {**result, 'telemetry': self.call('telemetry', id=args['id'])}
        result = super().call(op, **args)
        if op == 'telemetry':
            result['concurrent_resource_gate'] = {'status': 'PASS', 'evidence_kind': 'synthetic_offline'}
        return result


def runtime(host, requests):
    def native(url, key, timeout=120):
        def call(route, body):
            if route == '/props':
                return {'model_alias': 'glm-5.3', 'is_sleeping': False, 'total_slots': 1,
                        'default_generation_settings': {'n_ctx': 480000},
                        'chat_template': 'synthetic-template', 'chat_template_tool_use': 'synthetic-tool-template'}
            if route == '/apply-template':
                return {'prompt': json.dumps(body)}
            counted = token_count(json.loads(body['content']) if route == '/tokenize' else body)
            return {'tokens': [1] * counted, 'count': counted, 'max_model_len': 262144}
        return call

    def transport(url, key, **options):
        def send(raw, timeout):
            body = json.loads(raw)
            requests.append({'body': body, 'resident': tuple(host.active), 'url': url})
            content = body['messages'][0]['content']
            answer = dict(re.findall(r'marker=(START|MIDDLE|END); value=([a-zA-Z0-9_-]+);', content))
            if body.get('tools') and body.get('tool_choice') == 'auto':
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'synthetic-call-17',
                    'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"result.json"}'}}]}
                finish = 'tool_calls'
            else:
                if body['messages'][-1]['role'] == 'tool':
                    answer.update(json.loads(body['messages'][-1]['content']))
                delta, finish = {'role': 'assistant', 'content': json.dumps(answer)}, 'stop'
            n = token_count(body)
            for event in [
                {'model': body['model'], 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                {'model': body['model'], 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
                {'model': body['model'], 'choices': [], 'usage': {'prompt_tokens': n, 'completion_tokens': 32,
                    'prompt_tokens_details': {'cached_tokens': 0}},
                    'timings': {'prompt_n': n, 'predicted_n': 32, 'prompt_ms': 15, 'predicted_ms': 100000}}]:
                yield b'data: ' + fixtures.canonical(event) + b'\n\n'
            yield b'data: [DONE]\n\n'
        return send
    return transport, native


class CandidateValidation(unittest.TestCase):
    def setup_job(self, directory):
        task = Path(directory)
        manifests = profiles.candidate_manifests()
        armed = {'scope': candidate.SCOPE, 'manifests': manifests,
                 'runtime': {'budget_seconds': 1200, 'deadline_epoch': 9999999999}}
        runner.save(task / 'progress.json', {'phase': 'SYNTHETIC_OFFLINE', 'completed': {}, 'inflight': {}, 'errors': []})
        host, requests = CandidateHost(manifests, task / 'budget.json'), []
        transport, native = runtime(host, requests)
        job = candidate.Validation(task, armed, host, 'synthetic-key', transport_factory=transport, json_factory=native)
        return job, host, requests

    def test_fixed_small_bodies_only_exact_models_and_fresh_prefixes(self):
        samples = candidate.fixed_samples()
        self.assertEqual(set(samples), {p + '-' + k for p in ('G1', 'Q1') for k in ('warmup', 'smoke', 'tool')})
        hashes = set()
        for name, sample in samples.items():
            placement, kind = name.split('-', 1)
            raw = candidate.serialize_sample(placement, kind, sample)
            self.assertEqual(sample['body']['messages'][0]['content'].count('record='), 12)
            self.assertEqual(sample['body']['max_tokens'], 256)
            self.assertTrue(sample['body']['stream'])
            self.assertEqual(sample['body']['model'], 'glm-5.3' if name.startswith('G') else 'qwen3.8-27b')
            self.assertLess(len(raw), 8192)
            hashes.add(fixtures.digest(raw))
            if kind == 'smoke':
                schema = sample['body']['response_format']['json_schema']['schema']
                self.assertEqual(schema['properties'], {key: {'type': 'string'} for key in ('START', 'MIDDLE', 'END')})
                self.assertEqual(set(schema['required']), {'START', 'MIDDLE', 'END'})
                self.assertIs(schema['additionalProperties'], False)
                for expected in sample['scorer']['retrieval'].values():
                    self.assertNotIn(expected, json.dumps(schema))
                bad = copy.deepcopy(sample);bad['body']['response_format']['json_schema']['schema']['properties']['START']['enum'] = ['answer']
                with self.assertRaises(ValueError):
                    candidate.serialize_sample(placement, kind, bad)
        self.assertEqual(len(hashes), 6)

    def test_real_tool_execution_matching_continuation_timings_and_no_fitter(self):
        with tempfile.TemporaryDirectory() as directory:
            job, host, requests = self.setup_job(directory)
            with patch.object(fixtures, 'fit_sample', side_effect=AssertionError('no capacity fitting')), \
                 patch.object(fixtures, 'warmup_sample', side_effect=AssertionError('no warmup fitting')):
                job.sequence()
            self.assertEqual(len(requests), 8)
            self.assertTrue(all(len(r['resident']) == 2 for r in requests))
            self.assertEqual({r['url'] for r in requests}, {'http://127.0.0.1:31002', 'http://127.0.0.1:31004'})
            self.assertEqual(set(job.progress['completed']), {'G1-smoke', 'G1-tool', 'Q1-smoke', 'Q1-tool'})
            for placement in ('G1', 'Q1'):
                smoke = job.progress['completed'][placement + '-smoke']
                self.assertEqual(smoke['count']['body_sha256'], smoke['sample']['request_sha256'])
                sample_request = next(r['body'] for r in requests
                                      if 'response_format' in r['body'] and
                                      r['body']['model'] == ('glm-5.3' if placement == 'G1' else 'qwen3.8-27b'))
                self.assertEqual(smoke['count']['body_sha256'], fixtures.digest(fixtures.canonical(sample_request)))
                row = job.progress['completed'][placement + '-tool']
                self.assertEqual(row['status'], 'PASS')
                self.assertTrue(row['tool']['worker_local'])
                self.assertLess(row['continuation_count']['input_tokens'], 4096)
                self.assertGreater(row['continuation_count']['input_tokens'], row['count']['input_tokens'])
                self.assertEqual(row['continuation']['counter_source'], 'native_response_fields')
                self.assertIn('client_elapsed_seconds', row['continuation'])
                self.assertIn('client_timing', row['continuation'])
                self.assertEqual(row['continuation_count']['body_sha256'], row['continuation']['request_sha256'])
                self.assertTrue((job.private / (placement + '-tool-tool/result.json')).is_file())
            continued = [r['body'] for r in requests if r['body']['messages'][-1]['role'] == 'tool']
            self.assertEqual(len(continued), 2)
            for body in continued:
                self.assertEqual(body['messages'][-1]['tool_call_id'], body['messages'][-2]['tool_calls'][0]['id'])
                self.assertEqual(body['tool_choice'], 'none')
            events = [json.loads(line) for line in (job.state / 'results.jsonl').read_text().splitlines()]
            self.assertEqual([r['timing'] for r in events if r['type'] == 'warmup'], ['DISCARDED', 'DISCARDED'])
            self.assertTrue(any(r['type'] == 'glm_slow_warning' and not r['stop_condition'] for r in events))
            self.assertFalse(job.safety)
            self.assertEqual(len((job.state / 'warmups.jsonl').read_text().splitlines()), 2)
            self.assertEqual(len((job.state / 'samples.jsonl').read_text().splitlines()), 6)

    def test_changed_body_and_overlong_count_refuse_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            job, host, requests = self.setup_job(directory)
            host.call('begin');cid = job.loaded(job.armed['manifests'][0])
            prepared = job.prepared(cid, 'smoke')
            body = json.loads(prepared['raw']);body['max_tokens'] = 512
            with self.assertRaisesRegex(ValueError, 'candidate_exact_counted_body_required'):
                job.request(cid, fixtures.canonical(body), 'changed')
            native = accounting.native_counter('glm-5.3', 480000,
                runtime(host, requests)[1]('', ''), scope=candidate.SCOPE)
            real_count = native(prepared['raw'])
            with patch.object(accounting, 'native_counter', return_value=lambda raw: {**real_count, 'input_tokens': 4097}):
                with self.assertRaisesRegex(ValueError, 'candidate_short_count_limit'):
                    job.counter(cid)(prepared['raw'])
            self.assertEqual(requests, [])

    def test_native_response_count_mismatch_is_failure_and_request_drains(self):
        with tempfile.TemporaryDirectory() as directory:
            job, host, requests = self.setup_job(directory)
            host.call('begin');cid = job.loaded(job.armed['manifests'][0])
            prepared = job.prepared(cid, 'smoke')
            job.counts[fixtures.digest(prepared['raw'])]['input_tokens'] += 1
            with self.assertRaisesRegex(ValueError, 'candidate_native_count_or_transport_failed'):
                job.request(cid, prepared['raw'], 'count-mismatch')
            self.assertEqual(host.events[-1][0], 'request_end')
            self.assertEqual(len(requests), 1)

    def test_counter_admits_only_fixed_production_alias_capacity_pairs(self):
        call = Mock(return_value={'tokens': [1, 2, 3], 'count': 3, 'max_model_len': 262144})
        raw = candidate.serialize_sample('Q1', 'smoke', candidate.fixed_samples()['Q1-smoke'])
        count = accounting.native_counter('qwen3.8-27b', 700160, call, qwen_template_sha256='a' * 64,
                                         scope=candidate.SCOPE)(raw)
        self.assertEqual(count['configured_context'], 700160)
        self.assertEqual(count['tokenizer_max_model_len'], 262144)
        self.assertEqual(count['configured_context_source'], 'caller_verified_runtime_allocation')
        for model, capacity, scope in [('bench-qwen3.8-27b', 700160, candidate.SCOPE),
            ('qwen3.8-27b', 262144, candidate.SCOPE), ('glm-5.3', 65536, candidate.SCOPE),
            ('glm-5.3', 480000, None), ('qwen3.8-27b', 700160, None)]:
            with self.subTest(model=model, capacity=capacity), self.assertRaises(fixtures.HarnessError):
                accounting.native_counter(model, capacity, call, qwen_template_sha256='a' * 64, scope=scope)

    def test_prepare_has_no_clock_or_contact_or_authorization(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(candidate.glmrepair, 'DiagnosticSSHHost', side_effect=AssertionError('PREP cannot contact VM')), \
             patch.object(candidate.glmrepair, 'git', return_value='a' * 40), \
             patch.object(runner, 'source_files', return_value={'synthetic-source.py': b'offline source'}), \
             patch.object(candidate.time, 'time', side_effect=AssertionError('PREP starts no clock')):
            task = Path(directory)
            armed = candidate.prepare(task, 'synthetic-prep-session')
            self.assertNotIn('runtime', armed)
            self.assertEqual(armed['native_auth_fixture']['status'], 'REQUIRED_ACTUAL_IMAGE_NOT_RUN')
            go = json.loads((task / 'GO.template.json').read_bytes())
            self.assertEqual(go['decision'], 'NOT_AUTHORIZED')
            self.assertFalse(go['benchmark_restored'])
            self.assertIsNone(go['runtime']['start_epoch'])
            self.assertEqual(runner.load_arm(task, go['arm_sha256']), armed)
            with patch.object(runner, 'source_files', return_value={'synthetic-source.py': b'changed'}):
                with self.assertRaisesRegex(ValueError, 'armed_source_changed'):
                    runner.load_arm(task, go['arm_sha256'])
            with self.assertRaisesRegex(ValueError, 'root_reviewed_arm_hash_mismatch'):
                runner.load_arm(task, 'f' * 64)
            with self.assertRaisesRegex(ValueError, 'candidate_root_source_review_and_restored_handoff_required'):
                candidate.run(task, task / 'GO.template.json', 'synthetic-live-session')
            self.assertFalse((task / 'execution-arm.json').exists())

    def test_dispatch_clock_requires_new_session_exact_bounded_future_authority(self):
        armed = {'runtime_policy': candidate.POLICY, 'session_id': 'prep'}
        runtime = {'start_epoch': 1000, 'deadline_epoch': 2200, 'budget_seconds': 1200}
        go = {'runtime': runtime, 'run_session_id': 'fresh'}
        self.assertEqual(candidate.bind_runtime(armed, go, 'fresh', 1001), runtime)
        for changed in ({**runtime, 'budget_seconds': 1201, 'deadline_epoch': 2201},
                        {**runtime, 'clock_includes_preparation': True},
                        {**runtime, 'start_epoch': True}, {**runtime, 'deadline_epoch': 2201}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                candidate.bind_runtime(armed, {**go, 'runtime': changed}, 'fresh', 1001)
        for session, now in (('prep', 1001), ('other', 1001), ('fresh', 999), ('fresh', 2200)):
            with self.subTest(session=session, now=now), self.assertRaises(ValueError):
                candidate.bind_runtime(armed, go, session, now)

    def test_remaining_caps_credit_only_disjoint_resident_anon_and_shmem(self):
        gib = candidate.GIB
        sample = {'host': {'available_bytes': 300 * gib}, 'cgroups': {'g': {
            'anon_bytes': 100 * gib, 'shmem_bytes': 300 * gib, 'file_bytes': 500 * gib, 'swap_bytes': 0}}}
        result = candidate.memory_obligations(sample, {'g': {'placement': 'G1'}})
        self.assertEqual(result['required_host_available_bytes'], 288 * gib)
        self.assertEqual(result['resident_nonreclaimable_bytes'], {'G1': 400 * gib})
        empty = {'host': {'available_bytes': 688 * gib}, 'cgroups': {}}
        self.assertEqual(candidate.memory_obligations(empty, {})['required_host_available_bytes'], 688 * gib)
        for available in (687 * gib, None):
            with self.assertRaisesRegex(ValueError, 'candidate_remaining_caps_host_reserve_failed'):
                candidate.memory_obligations({'host': {'available_bytes': available}, 'cgroups': {}}, {})
        bad = copy.deepcopy(sample);bad['cgroups']['g']['swap_bytes'] = 1
        with self.assertRaisesRegex(ValueError, 'candidate_resident_credit_unavailable'):
            candidate.memory_obligations(bad, {'g': {'placement': 'G1'}})

    def test_saved_execution_cannot_weaken_reviewed_arm_or_go(self):
        armed = {'runtime_policy': candidate.POLICY, 'session_id': 'prep', 'scope': candidate.SCOPE,
                 'source_files': {'synthetic.py': 'a' * 64}, 'manifests': [{'synthetic': 'exact-manifest'}]}
        receipt = {'arm_sha256': 'b' * 64}
        go = {'run_session_id': 'original-run', 'runtime': {
            'start_epoch': 1000, 'deadline_epoch': 2200, 'budget_seconds': 1200},
            'actual_image_auth_receipt': {'path': '/synthetic/receipt', 'sha256': 'c' * 64,
                                         'registered_path': '/data/logs/synthetic/receipt'}}
        executed = {**armed, 'runtime': go['runtime'], 'session_id': go['run_session_id'],
                    'preparation_arm_sha256': receipt['arm_sha256'],
                    'actual_image_auth_receipt': go['actual_image_auth_receipt'],
                    'actual_image_auth_proof': {'evidence_kind': 'synthetic_offline'}}
        # Only the receipt-check callback is stubbed; no actual-image PASS is made.
        checker = Mock()
        with patch.object(candidate, 'auth_fixture_module', return_value=checker):
            candidate.check_execution(armed, executed, receipt, go)
            checker.check_pair_receipt.assert_called_once_with(executed['actual_image_auth_proof'], profiles.ROOT)
            for field, value in [('scope', 'full'), ('source_files', {}), ('manifests', []),
                                 ('session_id', 'prep'), ('actual_image_auth_receipt', {}),
                                 ('runtime', {**go['runtime'], 'deadline_epoch': 2300})]:
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'candidate_recovery_arm_changed'):
                    candidate.check_execution(armed, {**executed, field: value}, receipt, go)
        with self.assertRaises(ValueError):
            candidate.check_execution(armed, executed, receipt, go)

    def test_restore_only_never_promotes_failed_or_missing_checks(self):
        for complete in (False, True):
            value = candidate.candidate_outcome(restore_only=True, checks_complete=complete,
                failed=False, restored=True, errors=[])
            self.assertEqual(value['status'], 'RESTORATION_ONLY_NO_NEW_CANDIDATE_VERDICT')
            self.assertEqual(value['production_acceptance'], 'NOT_GRANTED')
        self.assertEqual(candidate.candidate_outcome(restore_only=False, checks_complete=False,
            failed=False, restored=True, errors=[])['status'], 'CANDIDATE_FAIL')

    def test_live_refuses_before_host_without_actual_image_proof_after_helper_integration(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(candidate.glmrepair, 'git', return_value='a' * 40), \
             patch.object(runner, 'source_files', return_value={'synthetic.py': b'source'}), \
             patch.object(candidate.glmrepair, 'DiagnosticSSHHost', side_effect=AssertionError('no live contact')) as ssh, \
             patch.object(candidate.os, 'geteuid', return_value=1000):
            task = Path(directory)
            candidate.prepare(task, 'prep')
            go = json.loads((task / 'GO.template.json').read_bytes())
            go.update(decision='GO', vm_writer_handoff=True, benchmark_restored=True)
            runner.save(task / 'synthetic-go.json', go)
            with self.assertRaisesRegex(ValueError, 'candidate_actual_image_auth_receipt_required'):
                candidate.run(task, task / 'synthetic-go.json', 'fresh')
            ssh.assert_not_called()
            self.assertFalse((task / 'execution-arm.json').exists())

    def test_adapter_native_proof_requires_actual_pool_and_unchanged_identity(self):
        from tests.lifecycle.test_concurrent_profiles import bound
        from tests.lifecycle.test_sglang38_file_auth import args_fixture
        cp, _ = profiles.candidate_modules()
        runtime_io = importlib.import_module(cp.__package__ + '.runtime_io')
        args = args_fixture(1000000, resolved=True)
        args.context_length = args.max_total_tokens = 700160;args.tp_size = 1
        resolved = json.loads(json.dumps(vars(args), default=vars))
        info = {'server_args': resolved, 'max_total_num_tokens': 700160, 'max_req_input_len': 700154}
        host = SimpleNamespace(load_manifests={'q': {'placement': 'Q1'}}, binding=None,
                               budget=SimpleNamespace(checkpoint=lambda: 60))
        with patch.object(profiles, 'candidate_profile', return_value=bound(cp.QWEN_PROFILE)), \
             patch.object(runtime_io, 'native_capacity_metadata', return_value=info), \
             patch.object(candidate, 'identity_stamp', return_value={'evidence_kind': 'synthetic_offline', 'id': 'q'}):
            result = candidate.native_proof(host, 'q', info)
            self.assertEqual((result['native_pool_tokens'], result['native_input_limit']), (700160, 700154))
            self.assertEqual(result['native_arguments_basis'], 'actual_native_resolving_view_validated_by_exact_pair_wrapper')
            with patch.object(runtime_io, 'native_capacity_metadata', return_value={'server_args': resolved}):
                with self.assertRaises(runtime_io.LifecycleError):
                    candidate.native_proof(host, 'q', info)
            with patch.object(candidate, 'identity_stamp', side_effect=[{'id': 'q'}, {'id': 'other'}]):
                with self.assertRaisesRegex(ValueError, 'candidate_native_identity_changed'):
                    candidate.native_proof(host, 'q', info)


if __name__ == '__main__':
    unittest.main()
