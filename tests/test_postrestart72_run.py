"""Offline actual72 adapter/read-chain/gate checks; no VM or network contact.

Archive integration uses exact operator-private SAVED inputs when available;
no bulk private fixtures are embedded in source.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import client, cpu_budget_profiles as profile, fixtures, postrestart72_run as run72, runner
from tests.test_benchmark_client import event, stream

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = ROOT.parent.parent
SOURCES = {'scripts/benchmark/offline-fixture.py': b'# synthetic offline source\n'}


def armed():
    return {'scope': run72.SCOPE, 'campaign': profile.POSTRESTART_CAMPAIGN,
        'session_id': 'fresh-run-session', 'source_commit': run72.BASE,
        'manifests': profile.postrestart_manifests(), 'trial_plan': profile.postrestart_trial_order(),
        'frozen_inputs': {}, 'runtime': copy.deepcopy(run72.POLICY),
        'runtime_policy': copy.deepcopy(run72.POLICY)}


def short_row(prefill=35, total=180, output=145, decode=12.6):
    return {'id': 'P-G4K', 'status': 'PASS', 'strict': {'status': 'PASS'},
        'semantic': {'status': 'PASS'}, 'native_count_valid': True,
        'native_n_minus_one_decode_tps': decode,
        'sample': {'client_elapsed_seconds': total, 'counters': {
            'prompt_tokens': 3546, 'prompt_ms': 3546 / prefill * 1000,
            'completion_tokens': output, 'cached_tokens': 0, 'decode_ms': 11000}}}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'task'; self.state.mkdir(mode=0o700)
        (self.state / 'private').mkdir(mode=0o700)
        runner.save(self.state / 'progress.json', {'phase': 'OFFLINE', 'completed': {}, 'inflight': {}, 'errors': []})
        (self.state / 'incoming-latest.md').write_text('Offline test authority fixture.\n')
        self.host = Mock(); self.host.call.return_value = {'timeout_s': 7200}
        self.job = run72.PostrestartRun(self.state, armed(), self.host, 'synthetic-offline-key', sleep=Mock())
        self.job.hold_ready = True

    def test_constructor_private_contract_precedes_host_and_frozen_read(self):
        self.host.call.assert_not_called()
        (self.state / 'private').chmod(0o755)
        with self.assertRaisesRegex(client.HarnessError, '0700'):
            run72.PostrestartRun(self.state, armed(), self.host, 'synthetic-offline-key')
        (self.state / 'private').rmdir()
        target = self.state / 'other'; target.mkdir(mode=0o700)
        (self.state / 'private').symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(client.HarnessError, '0700'):
            run72.PostrestartRun(self.state, armed(), self.host, 'synthetic-offline-key')
        self.host.call.assert_not_called()

    def test_frozen_read_chain_rejects_mutation_before_any_host_call(self):
        path = self.state / 'private/frozen.json'; runner.save(path, {'synthetic': True})
        arm = armed(); arm['frozen_inputs'] = {'private/frozen.json': fixtures.digest(path.read_bytes())}
        runner.save(path, {'synthetic': False})
        with self.assertRaisesRegex(ValueError, 'frozen_input_changed'):
            run72.PostrestartRun(self.state, arm, self.host, 'synthetic-offline-key')
        self.host.call.assert_not_called()

    def test_fresh_run_session_and_clock_exact_policy(self):
        arm = armed(); arm['session_id'] = 'prep-session'
        go = {'runtime': copy.deepcopy(run72.POLICY), 'run_session_id': 'run-session'}
        actual = run72.bind_runtime(arm, go, 'run-session', now=999999999999)
        self.assertEqual(actual, run72.POLICY)
        self.assertNotIn('start_epoch', actual); self.assertNotIn('deadline_epoch', actual)
        for session in ('', 'prep-session', 'other-session'):
            with self.assertRaisesRegex(ValueError, 'fresh_RUN'):
                run72.bind_runtime(arm, go, session)
        for key, value in (('budget_seconds', 7200), ('request_timeout_seconds', 3600),
                           ('clock_includes_preparation', True), ('deadline_epoch', 99)):
            bad = copy.deepcopy(go); bad['runtime'][key] = value
            with self.assertRaisesRegex(ValueError, 'independent_clock'):
                run72.bind_runtime(arm, bad, 'run-session')

    def test_preliminary_thresholds_strict_uncached_and_decode_flag_only(self):
        self.assertTrue(run72.preliminary(short_row())['long_preauthorized'])
        for row in (short_row(prefill=34.99999), short_row(total=180.00001),
                    short_row(total=float('inf')), short_row(total=float('nan'))):
            self.assertFalse(run72.preliminary(row)['long_preauthorized'])
        for change in ('strict', 'native', 'cached', 'missing_cached', 'status'):
            row = short_row()
            if change == 'strict': row['strict']['status'] = 'FAIL'
            elif change == 'native': row['native_count_valid'] = False
            elif change == 'cached': row['sample']['counters']['cached_tokens'] = 1
            elif change == 'missing_cached': del row['sample']['counters']['cached_tokens']
            else: row['status'] = 'OUTPUT_LIMIT'
            self.assertFalse(run72.preliminary(row)['long_preauthorized'], change)
        flagged = run72.preliminary(short_row(output=64, decode=1.99))
        self.assertTrue(flagged['long_preauthorized'])
        self.assertIn('aggregate_decode_below_2_tps_at_least64_output', flagged['flags'])
        self.assertFalse(flagged['automatic_speed_abort'])
        self.assertNotIn('aggregate_decode_below_2_tps_at_least64_output',
                         run72.preliminary(short_row(output=63, decode=1.99))['flags'])

    def test_preliminary_snapshot_saved_and_emitted_before_conditional_continue(self):
        row = short_row(); row['preliminary_gate'] = run72.preliminary(row)
        runner.save(self.state / 'P-G4K-result.json', row)
        self.job.boundary = Mock(); self.job.emit = Mock(); self.job.hold = Mock()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(self.job.preliminary_checkpoint(row))
        saved = json.loads((self.state / 'preliminary-gate.json').read_bytes())
        self.assertEqual(saved['result_sha256'], fixtures.digest((self.state / 'P-G4K-result.json').read_bytes()))
        self.assertEqual(json.loads(output.getvalue()), saved)
        self.job.emit.assert_called_once_with(saved); self.job.hold.assert_not_called()
        row = short_row(total=181); row['preliminary_gate'] = run72.preliminary(row)
        runner.save(self.state / 'P-G4K-result.json', row)
        self.job.hold.return_value = False
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(self.job.preliminary_checkpoint(row))
        self.job.hold.assert_called_once_with('preliminary_review', fixtures.digest((self.state / 'P-G4K-result.json').read_bytes()))

    def test_complete_hold_ignores_long_go_and_only_bound_release_exits(self):
        self.host.call.return_value = {'phase': 'WARM_HOLD', 'status': 'HELD', 'guarded': True, 'synthetic': True}
        self.job.boundary = Mock()
        runner.save(self.state / 'long-GO.json', {'decision': 'GO'})
        def release_on_sleep(seconds):
            release = json.loads((self.state / 'release.template.json').read_bytes())
            release['decision'] = 'RELEASE'; runner.save(self.state / 'release.json', release)
        self.job.sleep.side_effect = release_on_sleep
        self.assertFalse(self.job.hold('complete'))
        self.assertTrue(self.job.release_requested)
        calls = [c.args[0] for c in self.host.call.call_args_list]
        self.assertEqual(calls.count('warm_hold'), 1); self.assertNotIn('resume_measurements', calls)
        self.assertGreaterEqual(calls.count('hold_checkpoint'), 2)
        self.assertEqual(self.job.progress['phase'], 'EXPLICIT_RELEASE_REQUESTED')

    def test_fallback_pause_or_review_keeps_same_monitor_alive_through_followup_drain(self):
        for error in (run72.AdmissionPaused('pause'), run72.EvidenceReview('gap')):
            started, drained, monitor_done = threading.Event(), threading.Event(), threading.Event()
            self.job.stop.set()  # execute must start its own live monitor lifetime.
            def monitor():
                started.set()
                self.job.stop.wait(2)
                monitor_done.set()
            def held(reason):
                self.assertTrue(started.wait(1))
                self.assertFalse(self.job.stop.is_set())
                self.assertFalse(monitor_done.is_set())
                self.job.in_hold = False  # authorized follow-up transport begins
                self.assertFalse(self.job.stop.is_set())
                drained.set()
                self.job.in_hold = True
                self.assertFalse(monitor_done.is_set())
            self.job.monitor = monitor
            self.job.sequence = Mock(side_effect=error)
            self.job.hold = held
            self.job.execute()
            self.assertTrue(drained.is_set())
            self.assertTrue(self.job.stop.is_set())
            self.assertTrue(monitor_done.is_set())

    def test_aligned_admission_refusal_preserves_hold_but_danger_or_lost_owner_does_not(self):
        self.host.rpc_unavailable = False
        self.host.call.side_effect = [{'phase': 'WARM_HOLD'},
            {'phase': 'WARM_HOLD', 'guarded': True, 'status': 'REVIEW_REQUIRED'}]
        self.assertTrue(self.job.retained_refusal())
        self.assertEqual([c.args[0] for c in self.host.call.call_args_list], ['status', 'hold_checkpoint'])
        self.host.call.reset_mock()
        self.host.call.side_effect = [{'phase': 'WARM_HOLD'}, RuntimeError('STOP_RESOURCE_GATE')]
        with self.assertRaisesRegex(RuntimeError, 'STOP_RESOURCE_GATE'):
            self.job.retained_refusal()
        self.host.call.reset_mock(); self.host.call.side_effect = [{'phase': 'ACTIVE'}]
        self.assertFalse(self.job.retained_refusal())
        self.host.call.assert_called_once_with('status')
        self.host.call.reset_mock(); self.host.rpc_unavailable = True
        self.assertFalse(self.job.retained_refusal()); self.host.call.assert_not_called()

    def test_hold_refuses_inflight_and_propagates_resource_failure(self):
        self.job.progress['inflight']['busy'] = {'container': 'g'}
        with self.assertRaisesRegex(RuntimeError, 'idle_closed_hold'):
            self.job.hold('complete')
        self.host.call.assert_not_called(); self.job.progress['inflight'].clear()
        self.job.boundary = Mock()
        self.host.call.return_value = {'phase': 'WARM_HOLD', 'status': 'HELD', 'guarded': True}
        self.job.boundary.side_effect = RuntimeError('STOP_GPU_RESERVE')
        with self.assertRaisesRegex(RuntimeError, 'STOP_GPU_RESERVE'):
            self.job.hold('complete')
        self.assertFalse(self.job.release_requested)

    def test_preliminary_hold_requires_source_session_and_snapshot_bound_go(self):
        self.job.boundary = Mock()
        self.host.call.return_value = {'phase': 'WARM_HOLD', 'status': 'HELD', 'guarded': True}
        row_sha = 'a' * 64
        value = {'decision': 'GO', 'source_commit': self.job.armed['source_commit'],
                 'run_session_id': self.job.armed['session_id'], 'campaign': self.job.armed['campaign'],
                 'preliminary_result_sha256': row_sha, 'followup_session_id': 'new-followup-session'}
        for followup in ('', None, self.job.armed['session_id']):
            bad = dict(value); bad['followup_session_id'] = followup
            with self.assertRaisesRegex(ValueError, 'fresh_followup_session'):
                run72.validate_long_go(bad, self.job.armed, row_sha)
        for key in set(value) - {'followup_session_id'}:
            bad = dict(value); bad[key] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'snapshot_bound'):
                run72.validate_long_go(bad, self.job.armed, row_sha)
        runner.save(self.state / 'long-GO.json', value)
        self.assertTrue(self.job.hold('preliminary_review', row_sha))
        self.assertIn('resume_measurements', [c.args[0] for c in self.host.call.call_args_list])
        self.assertEqual(self.host.call.call_args.kwargs, {
            'followup_session_id': 'new-followup-session', 'source_commit': run72.BASE,
            'preliminary_result_sha256': row_sha})
        self.assertFalse(self.job.release_requested)

    def test_bad_mailbox_and_missing_proof_retain_models_without_admission(self):
        for fault in ('release', 'long_go', 'proof', 'null_proof', 'review_status'):
            with self.subTest(fault=fault):
                for name in ('release.json', 'long-GO.json'):
                    (self.state / name).unlink(missing_ok=True)
                self.host.reset_mock(); self.job.sleep.reset_mock(); self.job.boundary = Mock()
                self.job.release_requested = False
                receipt = {'phase': 'WARM_HOLD', 'status': 'HELD', 'guarded': True}
                proof_calls = []
                def host_call(method, **kwargs):
                    if method == 'hold_checkpoint':
                        proof_calls.append(method)
                        if fault in {'proof', 'null_proof', 'review_status'} and len(proof_calls) == 1:
                            if fault == 'null_proof': return None
                            if fault == 'review_status': return {'phase': 'WARM_HOLD', 'status': 'REVIEW_REQUIRED', 'guarded': True}
                            return {'phase': 'WARM_HOLD_REVIEW_REQUIRED', 'guarded': False}
                    return receipt
                self.host.call.side_effect = host_call
                if fault not in {'proof', 'null_proof', 'review_status'}:
                    (self.state / ('release.json' if fault == 'release' else 'long-GO.json')).write_text('{bad-json')
                expected_notice = {'release': 'rejected_release_mailbox',
                    'long_go': 'rejected_long_GO_mailbox', 'proof': 'current_safe_proof_UNAVAILABLE',
                    'null_proof': 'current_safe_proof_UNAVAILABLE', 'review_status': 'current_safe_proof_UNAVAILABLE'}[fault]
                def fix_only_after_notice(seconds):
                    self.assertFalse(self.job.release_requested)
                    self.assertEqual(json.loads((self.state / 'hold-review.json').read_bytes())['reason'], expected_notice)
                    release = json.loads((self.state / 'release.template.json').read_bytes())
                    release['decision'] = 'RELEASE'; runner.save(self.state / 'release.json', release)
                self.job.sleep.side_effect = fix_only_after_notice
                self.assertFalse(self.job.hold('preliminary_review', 'a' * 64))
                methods = [call.args[0] for call in self.host.call.call_args_list]
                self.assertNotIn('resume_measurements', methods)
                self.assertNotIn('restore', methods); self.assertNotIn('retire', methods)
                self.assertEqual(proof_calls, ['hold_checkpoint', 'hold_checkpoint'])
                self.job.sleep.assert_called_once()

    def test_complete_hold_one_fixed_followup_uses_retained_host_then_new_bound_release(self):
        from benchmark import postrestart72_followup as followup
        preset = followup.PRESETS['P-G4K']
        sample = fixtures.build_sample('bench-glm-5.3', preset['records'], preset['seed'],
                                       'fresh-one-reviewed-followup')
        raw = run72.g1_ladder.body_bytes(sample)
        request_path = self.state / 'private/followup.request.json'
        request_path.write_bytes(raw); request_path.chmod(0o600)
        runner.save(self.state / 'private/followup.fixture.json', sample)
        original = {'id': 'P-G4K', 'status': 'PASS', 'evidence': 'preserved-original'}
        self.job.progress['completed']['P-G4K'] = copy.deepcopy(original)
        runner.save(self.state / 'P-G4K-result.json', original)
        original_bytes = (self.state / 'P-G4K-result.json').read_bytes()
        manifest = profile.postrestart_manifest('G1')
        self.job.active['retained-g'] = {'manifest': manifest, 'cancel_event': threading.Event()}
        self.job.boundary = Mock(); self.job.ensure_current_proof = Mock()
        self.job.telemetry_window = Mock(return_value={'synthetic': True})
        receipts = [{'phase': 'WARM_HOLD', 'status': 'HELD', 'guarded': True, 'ordinal': n} for n in (1, 2)]
        go = {'decision': 'GO', 'source_commit': run72.BASE,
            'owner_run_session_id': self.job.armed['session_id'],
            'followup_session_id': 'fresh-followup-session', 'campaign': self.job.armed['campaign'],
            'preset': 'P-G4K', 'placement': 'G1',
            'warm_hold_receipt_sha256': fixtures.digest(fixtures.canonical(receipts[0]) + b'\n'),
            'manifest_sha256': fixtures.digest(fixtures.canonical(manifest)),
            'request_sha256': fixtures.digest(raw),
            'fixture_sha256': fixtures.digest((self.state / 'private/followup.fixture.json').read_bytes()),
            'request_id': 'F-reviewed-private-g4k', 'policy': copy.deepcopy(followup.POLICY)}
        invalid = copy.deepcopy(go); invalid['preset'] = 'arbitrary-model-request'
        runner.save(self.state / 'followup-GO.json', invalid)
        events = []; hold_count = [0]; proof_count = [0]
        def host_call(method, **kwargs):
            events.append(method)
            if method == 'warm_hold':
                hold_count[0] += 1
                self.assertLessEqual(hold_count[0], 2, 'unexpected extra hold recursion')
                return receipts[hold_count[0] - 1]
            if method == 'hold_checkpoint':
                proof_count[0] += 1
                if proof_count[0] == 2:
                    return {**receipts[0], 'status': 'REVIEW_REQUIRED'}
                return receipts[hold_count[0] - 1]
            if method == 'admit_followup':
                self.assertEqual(kwargs['go'], go); return {'admitted': True}
            if method == 'request_begin':
                self.assertEqual(kwargs['id'], 'retained-g')
                self.assertEqual(kwargs['request_identity']['request_id'], go['request_id'])
                return {'timeout_s': 7200}
            if method == 'request_end': return {'ended': True}
            raise AssertionError('unexpected host operation ' + method)
        self.host.call.side_effect = host_call
        def count(body):
            events.append('native_count')
            self.assertEqual(body, raw)
            self.assertIn('admit_followup', events)
            return {'source': 'native_apply_template_tokenize', 'body_sha256': fixtures.digest(body),
                'configured_context': 480000, 'input_tokens': 3546,
                'template_sha256': run72.TEMPLATES['G1'], 'token_ids_sha256': 'b' * 64}
        counter = Mock(side_effect=count); self.job.counter = Mock(return_value=counter)
        response = stream([event({'content': json.dumps(sample['scorer']['retrieval'])}, 'stop'),
            {'model': 'bench-glm-5.3', 'choices': [],
             'usage': {'prompt_tokens': 3546, 'completion_tokens': 145,
                       'prompt_tokens_details': {'cached_tokens': 0}},
             'timings': {'prompt_n': 3546, 'predicted_n': 145, 'prompt_ms': 51000, 'predicted_ms': 11000}}])
        transport = Mock(return_value=iter([response])); transport.request_clock = {'synthetic_offline': True}
        self.job.transport_factory = Mock(return_value=transport)
        sleeps = [0]
        def controlled_sleep(seconds):
            sleeps[0] += 1
            self.assertLessEqual(sleeps[0], 3, 'hold did not reach the expected finite checkpoints')
            if sleeps[0] == 1:
                self.assertEqual(json.loads((self.state / 'hold-review.json').read_bytes())['reason'],
                                 'rejected_followup_mailbox')
                counter.assert_not_called(); self.job.counter.assert_not_called()
                self.assertNotIn('admit_followup', events)
                runner.save(self.state / 'followup-GO.json', go)
            elif sleeps[0] == 2:
                self.assertEqual(json.loads((self.state / 'hold-review.json').read_bytes())['reason'],
                                 'current_safe_proof_UNAVAILABLE')
                counter.assert_not_called(); self.job.counter.assert_not_called()
                self.assertNotIn('admit_followup', events)
            else:
                self.assertEqual(hold_count[0], 2)
                release = json.loads((self.state / 'release.template.json').read_bytes())
                self.assertEqual(release['warm_hold_receipt_sha256'],
                                 fixtures.digest(fixtures.canonical(receipts[1]) + b'\n'))
                self.assertNotEqual(release['warm_hold_receipt_sha256'], go['warm_hold_receipt_sha256'])
                release['decision'] = 'RELEASE'; runner.save(self.state / 'release.json', release)
        self.job.sleep.side_effect = controlled_sleep
        with patch.object(run72.cpu, 'summarize_measurement', return_value={'synthetic_offline': True}):
            self.assertFalse(self.job.hold('complete'))
        self.assertTrue(self.job.release_requested)
        self.assertEqual(self.job.followup_sessions, ['fresh-followup-session'])
        self.assertEqual(events.count('admit_followup'), 1)
        self.assertEqual(events.count('request_begin'), 1); self.assertEqual(events.count('request_end'), 1)
        self.assertNotIn('begin', events); self.assertNotIn('load', events)
        counter.assert_called_once_with(raw); transport.assert_called_once_with(raw, 7200)
        self.assertEqual((self.state / 'P-G4K-result.json').read_bytes(), original_bytes)
        self.assertEqual(self.job.progress['completed']['P-G4K'], original)
        result = json.loads((self.state / (go['request_id'] + '-result.json')).read_bytes())
        self.assertEqual(result['status'], 'PASS'); self.assertTrue(result['native_count_valid'])
        self.assertEqual(result['strict']['status'], 'PASS')
        self.assertEqual((self.state / 'private' / (go['request_id'] + '.request.json')).read_bytes(), raw)
        self.assertEqual(self.job.progress['inflight'], {})

    def test_hold_local_reporting_failures_do_not_release_or_admit(self):
        self.job.boundary = Mock()
        self.host.call.return_value = {'phase': 'WARM_HOLD', 'status': 'HELD', 'guarded': True}
        saved = runner.save
        def report_failure(path, value):
            if Path(path).name in {'warm-hold-complete.json', 'warm-hold.json', 'hold-current.json', 'status.json'}:
                raise OSError('synthetic local reporting unavailable')
            return saved(path, value)
        def explicit_release(seconds):
            self.assertFalse(self.job.release_requested)
            self.assertGreater(len(self.job.hold_reporting_errors), 0)
            release = json.loads((self.state / 'release.template.json').read_bytes())
            release['decision'] = 'RELEASE'; saved(self.state / 'release.json', release)
        self.job.sleep.side_effect = explicit_release
        # The explicit-release record is separate from healthy hold reporting.
        self.job.record = Mock()
        with patch.object(runner, 'save', side_effect=report_failure):
            self.assertFalse(self.job.hold('complete'))
        self.assertTrue(self.job.release_requested)
        self.assertLessEqual(len(self.job.hold_reporting_errors), 8)
        self.assertNotIn('resume_measurements', [c.args[0] for c in self.host.call.call_args_list])

    def test_completed_parse_counter_semantic_failures_hold_but_undrained_transport_stops(self):
        self.job.boundary = Mock(); self.job.pending_warmups = [('g', {}, {}), ('q', {}, {})]
        self.job.loaded = Mock(side_effect=lambda manifest: manifest['placement'])
        self.job.discarded_warmup = Mock(); self.job.hold = Mock()
        self.job.prepare_job = Mock(side_effect=lambda cid, identifier: {'cid': cid, 'id': identifier})
        self.job.preliminary_checkpoint = Mock()
        self.host.call.side_effect = lambda method, **kwargs: {
            'manifests': profile.postrestart_manifests()} if method == 'admit_concurrent' else {}
        for status, sample_status in (('STOP_NATIVE_OR_TRANSPORT', 'HARNESS_FAILURE'),
                ('STOP_NATIVE_OR_TRANSPORT', 'COMPLETE'), ('MODEL_INCORRECT', 'COMPLETE'),
                ('REVIEW_EVIDENCE_UNAVAILABLE', 'COMPLETE')):
            self.job.hold.reset_mock()
            self.job.measure = Mock(return_value={'status': status, 'sample': {'status': sample_status}})
            self.job.sequence()
            self.job.hold.assert_called_once_with('quality_review')
            self.job.preliminary_checkpoint.assert_not_called()
        self.job.hold.reset_mock()
        self.job.measure = Mock(return_value={'status': 'STOP_NATIVE_OR_TRANSPORT',
                                             'sample': {'status': 'TRANSPORT_FAILURE'}})
        with self.assertRaisesRegex(RuntimeError, 'UNDRAINED_TRANSPORT_UNCERTAINTY'):
            self.job.sequence()
        self.job.hold.assert_not_called()

    def test_paused_admission_removes_only_undispatched_row_and_preserves_peer(self):
        raw = fixtures.canonical({'max_tokens': 256, 'stream': True})
        manifest = profile.postrestart_manifest('G1')
        self.job.active['g'] = {'manifest': manifest, 'cancel_event': threading.Event()}
        self.job.progress['inflight']['admitted-peer'] = {'container': 'q'}
        job = {'id': 'undispatched', 'cid': 'g', 'raw': raw,
               'manifest_sha256': fixtures.digest(fixtures.canonical(manifest)),
               'count': {'body_sha256': fixtures.digest(raw)}}
        self.job.root_paused = Mock(return_value=True)
        with self.assertRaises(run72.AdmissionPaused):
            self.job.measure(job)
        self.assertEqual(self.job.progress['inflight'], {'admitted-peer': {'container': 'q'}})
        self.assertFalse(self.job.active['g']['cancel_event'].is_set())
        self.host.call.assert_not_called()
        self.assertFalse((self.state / 'private/undispatched.request.json').exists())

    def test_drained_reporting_error_reaches_new_review_but_old_scope_still_refuses(self):
        self.job.ensure_current_proof = Mock()  # Resource composition covered in evidence_policy.
        raw = fixtures.canonical({'max_tokens': 256, 'stream': True})
        manifest = profile.postrestart_manifest('G1')
        self.job.active['g'] = {'manifest': manifest, 'cancel_event': threading.Event()}
        self.job.transport_factory = Mock()
        result = {'summary': {'status': 'COMPLETE', 'report_errors': ['private_response_write_failed']},
                  'parsed': None}
        with patch.object(client, '_capture_request', return_value=result):
            self.assertIs(self.job.request('g', raw, 'report-failure'), result)
            old_arm = armed(); old_arm['scope'] = 'concurrent-480k-cpu'
            old_arm['runtime'] = {'deadline_epoch': 99999999999}
            old = run72.prior.ConcurrentRun(self.state, old_arm, self.host, 'synthetic-offline-key',
                                           transport_factory=Mock())
            old.active['g'] = self.job.active['g']
            with self.assertRaisesRegex(RuntimeError, 'raw_evidence_persistence_failed'):
                old.request('g', raw, 'historical-report-failure')

    def test_pair_admission_pause_holds_only_after_healthy_peer_drain(self):
        self.job.boundary = Mock(); self.job.pending_warmups = [('g', {}, {}), ('q', {}, {})]
        self.job.loaded = Mock(side_effect=lambda manifest: manifest['placement'])
        self.job.discarded_warmup = Mock(); self.job.measure = Mock(return_value=short_row())
        self.job.prepare_job = Mock(side_effect=lambda cid, identifier: {'cid': cid, 'id': identifier})
        self.job.preliminary_checkpoint = Mock(return_value=True); self.job.admission_paused = True
        self.host.call.side_effect = lambda method, **kwargs: {
            'manifests': profile.postrestart_manifests()} if method == 'admit_concurrent' else {}
        result = {'status': 'FAILED', 'glm': {'id': 'P-G65008', 'status': 'HARNESS_FAILURE'},
                  'qwen': [{'id': 'P-Qnear480K', 'status': 'PASS'}],
                  'errors': [{'id': 'P-G65008', 'error_class': 'AdmissionPaused'}]}
        with patch.object(run72.cpu_run, 'execute_pair', return_value=result) as pair:
            with self.assertRaisesRegex(run72.AdmissionPaused, 'DRAINED'):
                self.job.sequence()
            pair.assert_called_once()
        result['qwen'][0]['status'] = 'FAIL'
        with patch.object(run72.cpu_run, 'execute_pair', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'STOP_POSTRESTART_PAIR_GATE'):
                self.job.sequence()


@unittest.skipUnless(all((ARCHIVES / rel).is_file() for rel, _ in run72.SAVED.values()),
                     'operator private archives unavailable; synthetic checks still run')
class ArchivedReadChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.state = self.root / 'task'; self.state.mkdir(mode=0o700)
        for _, (relative, expected) in run72.SAVED.items():
            raw = (ARCHIVES / relative).read_bytes(); self.assertEqual(fixtures.digest(raw), expected)
            dest = self.root / relative; dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            dest.write_bytes(raw); dest.chmod(0o600)
        runner.save(self.state / 'evidence-index.json', {'refs': {}, 'protected_key_metadata': {'synthetic': True}})
        (self.state / 'incoming-latest.md').write_text('Offline test authority fixture.\n')
        self.patches = contextlib.ExitStack(); self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(run72.glmrepair, 'git', side_effect=lambda *args: '' if args[0] == 'status' else run72.BASE))
        self.patches.enter_context(patch.object(runner, 'source_files', return_value=SOURCES))

    def prepared(self):
        arm = run72.prepare(self.state, 'prep-session')
        return {**arm, 'runtime': copy.deepcopy(run72.POLICY), 'session_id': 'run-session'}

    def test_actual_saved_prepare_constructor_all_jobs_and_private_capture_read_chain(self):
        arm = self.prepared()
        self.assertEqual(stat.S_IMODE((self.state / 'private').stat().st_mode), 0o700)
        run72.prior.verify_initial_package(self.state, arm)
        host = Mock(); host.call.return_value = {'timeout_s': 7200}
        response = stream([event({'content': 'offline'}, 'stop')])
        factory = Mock(return_value=lambda raw, timeout: iter([response]))
        job = run72.PostrestartRun(self.state, arm, host, 'synthetic-offline-key', transport_factory=factory)
        host.call.assert_not_called(); job.boundary = Mock(); job.ensure_current_proof = Mock()
        for place in ('G1', 'Q1'):
            job.active[place] = {'manifest': profile.postrestart_manifest(place), 'cancel_event': threading.Event()}
        counts = {'P-G4K': 3546, 'P-G65008': 65008, 'P-Qnear480K': 479487}; requests = {}
        for identifier, tokens in counts.items():
            place = 'Q1' if identifier == 'P-Qnear480K' else 'G1'
            def count(raw, n=tokens, p=place):
                return {'source': 'native_apply_template_tokenize', 'body_sha256': fixtures.digest(raw),
                        'configured_context': 480000, 'input_tokens': n,
                        'template_sha256': run72.TEMPLATES[p], 'token_ids_sha256': 'b' * 64}
            with patch.object(job, 'counter', return_value=count):
                prepared = job.prepare_job(place, identifier)
            self.assertEqual(prepared['count']['input_tokens'], tokens)
            self.assertEqual(prepared['count']['body_sha256'], fixtures.digest(prepared['raw']))
            self.assertEqual(json.loads(prepared['raw'])['max_tokens'], 256)
            self.assertEqual(stat.S_IMODE((self.state / 'private' / (identifier + '-fixture.json')).stat().st_mode), 0o600)
            requests[identifier] = prepared
        short = requests['P-G4K']; actual = json.loads(short['raw'])
        old = json.loads((self.state / 'private/G4K-original.request.json').read_bytes())
        self.assertNotEqual(actual['messages'][0]['content'].split('\n')[0], old['messages'][0]['content'].split('\n')[0])
        actual['messages'] = old['messages']; self.assertEqual(actual, old)
        self.assertEqual((actual['temperature'], actual['seed'], actual['reasoning_effort']), (1, 1729, 'low'))
        self.assertTrue(actual['response_format']['json_schema']['strict'])
        result = job.request('G1', short['raw'], 'P-G4K-offline-capture')
        self.assertEqual(result['summary']['status'], 'COMPLETE')
        self.assertIsNone(factory.call_args.kwargs['deadline_epoch'])
        self.assertEqual((self.state / 'private/P-G4K-offline-capture.request.json').read_bytes(), short['raw'])
        self.assertEqual(stat.S_IMODE((self.state / 'private/P-G4K-offline-capture.response.sse').stat().st_mode), 0o600)
        self.assertEqual(host.call.call_args_list[0].kwargs['measured'], True)

    def test_existing_private_permissions_and_symlink_not_repaired(self):
        private = self.state / 'private'; private.mkdir(mode=0o755); private.chmod(0o755)
        with self.assertRaisesRegex(client.HarnessError, '0700'):
            run72.prepare(self.state, 'prep-session')
        self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o755)
        private.rmdir(); target = self.root / 'external'; target.mkdir(mode=0o700); private.symlink_to(target)
        with self.assertRaisesRegex(client.HarnessError, '0700'):
            run72.prepare(self.state, 'prep-session')
        self.assertFalse((self.state / 'arm.json').exists())

    def test_saved_archive_tamper_fails_before_arm_and_no_rerun_before_host(self):
        relative, _ = next(iter(run72.SAVED.values())); (self.root / relative).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'saved_fixture_identity_changed'):
            self.prepared()
        self.assertFalse((self.state / 'arm.json').exists())
        (self.root / relative).write_bytes((ARCHIVES / relative).read_bytes())
        self.prepared()
        with self.assertRaisesRegex(ValueError, 'clean_source_fresh_arm'):
            run72.prepare(self.state, 'another-prep')
        receipt = json.loads((self.state / 'arm-receipt.json').read_bytes())
        go = {**receipt, 'decision': 'GO', 'vm_writer_handoff': True,
              'runtime': copy.deepcopy(run72.POLICY), 'run_session_id': 'run-session'}
        runner.save(self.state / 'GO.json', go); runner.save(self.state / 'execution-arm.json', {})
        with patch.object(run72.glmrepair, 'DiagnosticSSHHost') as host:
            with self.assertRaisesRegex(ValueError, 'no_rerun_or_clock_reset'):
                run72.run(self.state, self.state / 'GO.json', 'run-session')
            host.assert_not_called()


if __name__ == '__main__':
    unittest.main()
