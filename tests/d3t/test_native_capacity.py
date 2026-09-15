"""Native-capacity source acceptance through the public probe functions.

All accounting, transport and telemetry are injected CPU fixtures. Byte tokens
exercise checkpoint rules only; these tests provide no occupied model evidence.
The existing response parser, native body builder and worker-local tool execute.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import test_probe as fixtures
import test_probe_locking as locking_fixtures

probe = fixtures.probe
AgentError = fixtures.AgentError
NATIVE_STAGES = ('64k', '128k', '256k', '512k', 'near1m')
RUNTIME = probe.REPO / 'configs/runtimes/llama-cpp-v0.4.1-d3br.json'


class NativeCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        # Compose only the existing synthetic dependencies, never its seeded
        # comparison PASS setup or inherited test cases.
        self.f = fixtures.DriverTests()
        self.f.root = self.root
        self.f.key = 'synthetic-native-capacity-credential-not-a-real-key'
        self.f.key_file = self.root / 'key.txt'
        self.f.key_file.write_text(self.f.key)
        self.f.key_file.chmod(0o600)
        self.image = json.loads(RUNTIME.read_text())['validation']['image_id']
        self.f.phases = {
            'baseline': {'container_id': 'b' * 64, 'image_id': probe.D1_IMAGE, 'context': 32768},
            'candidate': {'container_id': 'c' * 64, 'image_id': self.image, 'context': 32768},
            'native': {'container_id': 'e' * 64, 'image_id': self.image, 'context': 1048576},
        }
        self.f.account_calls, self.f.transfers = [], []
        self.new_run('native-run')

    def new_run(self, name, *, mode='native-capacity'):
        self.run = self.f.run = self.root / name
        args = {} if mode is None else {'trial_mode': mode}
        probe.init_run(self.run, 'http://127.0.0.1:30002/v1', str(self.f.key_file), **args)

    def bind(self, phase='native', *, image=None, sample=None):
        identity = self.f.phases[phase]
        image = identity['image_id'] if image is None else image
        observed = sample if sample is not None else fixtures.SyntheticSampler(
            identity['container_id'], image, identity['context'], 1).next(timeout=1)
        with patch.object(probe.guards, 'collect', return_value=observed) as collect:
            probe.bind(self.run, phase, identity['container_id'], image)
        collect.assert_called_once_with(identity['container_id'], image, identity['context'])
        return observed

    def files(self, run=None):
        return {path.name: path.read_bytes() for path in (run or self.run).iterdir()
                if path.is_file() and not path.name.endswith('.lock')}

    def prepare(self, stage='64k'):
        probe.prepare(self.run, stage, accountant=self.f.accountant)

    def assert_no_comparisons(self):
        self.assertEqual(set(probe.read_json(self.run / 'config.json')['phases']), {'native'})
        self.assertTrue(set(self.f.state()['stages']) <= set(NATIVE_STAGES))
        self.assertFalse(any(p.name.startswith(('baseline.', 'candidate.')) for p in self.run.iterdir()))

    def custom_transport(self, *, cached='keep', evaluated=None, wrong_actual=False):
        def transport(*args):
            transfer = self.f.transport(*args)
            # Used for initial nonstreaming retrieval, with real response parsing.
            response = json.loads(transfer.raw)
            if cached is None:
                response['usage'].pop('prompt_tokens_details', None)
            elif cached != 'keep':
                response['usage']['prompt_tokens_details'] = {'cached_tokens': cached}
            if evaluated is not None:
                response['timings'] = {'prompt_n': evaluated}
            if wrong_actual:
                response['usage']['prompt_tokens'] += 1
                response['usage']['total_tokens'] += 1
            transfer.raw = fixtures.canonical(response)
            return transfer
        return transport

    def test_fresh_public_init_and_native_binding_prepare_without_comparisons(self):
        self.assertEqual(probe.read_json(self.run / 'config.json')['trial_mode'], 'native-capacity')
        admission = self.bind()
        self.assertEqual(probe.read_json(self.run / 'native.admission.json'), admission)
        self.prepare()
        state, public = self.f.state(), probe.status(self.run)
        self.assertEqual((state['status'], state['stage'], state['step']), ('PREPARED', '64k', 'cold'))
        self.assertEqual(public['trial_mode'], 'native-capacity')
        self.assertEqual(public['comparison_status'], 'NOT_RUN_IN_THIS_TRIAL')
        self.assertEqual(tuple(public['stage_status']), NATIVE_STAGES)
        self.assertEqual(public['native_configured_capacity'], 1048576)
        self.assertIsNone(public['highest_proven_window'])
        self.assertIsNone(state['accounting']['common_prefix_tokens'])
        self.assert_no_comparisons()
        for path in self.run.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cli_explicit_mode_and_unknown_mode_refuse_before_new_directory(self):
        target = self.root / 'cli-native'
        argv = ['init', '--run', str(target), '--base-url', 'http://127.0.0.1:30002/v1',
                '--key-file', str(self.f.key_file), '--trial-mode', 'native-capacity']
        # main changes umask by design; preserve the test process setting.
        old_umask = os.umask(0o077)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(probe.main(argv), 0)
            self.assertEqual(json.loads(output.getvalue())['trial_mode'], 'native-capacity')
        finally:
            os.umask(old_umask)
        for mode in ('native', '', None, 0):
            with self.subTest(mode=mode):
                unknown = self.root / ('unknown-' + repr(mode))
                with self.assertRaises(AgentError):
                    probe.init_run(unknown, 'http://127.0.0.1:30002/v1', str(self.f.key_file), trial_mode=mode)
                self.assertFalse(unknown.exists())

    def test_binding_rejects_d1_wrong_image_phase_and_replacement(self):
        before = self.files()
        for phase, image in (('native', probe.D1_IMAGE), ('native', 'sha256:' + 'a' * 64),
                             ('baseline', probe.D1_IMAGE), ('candidate', self.image)):
            with self.subTest(phase=phase, image=image), patch.object(probe.guards, 'collect') as collect:
                with self.assertRaises(AgentError):
                    probe.bind(self.run, phase, 'e' * 64, image)
                collect.assert_not_called()
                self.assertEqual(self.files(), before)
        read_bytes = Path.read_bytes
        def missing_runtime(path):
            if path == RUNTIME:
                raise FileNotFoundError('synthetic missing fixed runtime')
            return read_bytes(path)
        with patch.object(Path, 'read_bytes', missing_runtime), patch.object(probe.guards, 'collect') as collect:
            with self.assertRaises((AgentError, FileNotFoundError)):
                probe.bind(self.run, 'native', 'e' * 64, self.image)
            collect.assert_not_called()
        self.assertEqual(self.files(), before)
        self.assertNotEqual(self.image, probe.D1_IMAGE)
        self.bind()
        before = self.files()
        for container in ('e' * 64, 'f' * 64):
            with self.subTest(container=container), patch.object(probe.guards, 'collect') as collect:
                with self.assertRaises(AgentError):
                    probe.bind(self.run, 'native', container, self.image)
                collect.assert_not_called()
                self.assertEqual(self.files(), before)

    def test_binding_requires_native_context_complete_diagnostics_and_resource_guards(self):
        changes = (
            lambda s: s.update(slot_context=32768),
            lambda s: s.update(required_context=32768, slot_context=32768),
            lambda s: s.update(native=None),
            lambda s: s['native'].update(n_ctx=32768),
            lambda s: s['native'].update(fused_lid=0),
            lambda s: s['native']['compute_bytes'].pop('CUDA1'),
            lambda s: s['native']['cache_bytes'].pop('CUDA0'),
            lambda s: s.update(root_available_bytes=0),
            lambda s: s['process_kib'].update(Swap=1),
            lambda s: s['gpus'][0].update(free_bytes=0),
        )
        before = self.files()
        for index, mutate in enumerate(changes):
            sample = fixtures.SyntheticSampler('e' * 64, self.image, 1048576, 1).next(timeout=1)
            mutate(sample)
            with self.subTest(index=index), self.assertRaises(probe.guards.Error):
                self.bind(sample=sample)
            self.assertEqual(self.files(), before)

    def test_legacy_default_and_absent_field_keep_binding_chain_and_cold_rule(self):
        for absent in (False, True):
            with self.subTest(absent=absent):
                self.new_run('legacy-' + str(absent), mode=None)
                config = probe.read_json(self.run / 'config.json')
                self.assertEqual(config['trial_mode'], 'comparison')
                if absent:
                    config.pop('trial_mode')
                    probe.write_json(self.run / 'config.json', config)
                self.assertEqual(probe.status(self.run)['trial_mode'], 'comparison')
                self.assertEqual(tuple(probe.status(self.run)['stage_status']), probe.STAGES)
                for phase in ('candidate', 'native'):
                    with self.assertRaises(AgentError):
                        self.bind(phase)
                self.bind('baseline')
                with self.assertRaises(AgentError):
                    self.bind('candidate')
                with self.assertRaises(AgentError):
                    self.prepare('64k')
                self.prepare('baseline')
                self.f.dispatch(transport=self.custom_transport(cached=50, evaluated=1320))
                state = self.f.state()
                self.assertEqual(state['failure_class'], 'cold_cache_NOT_TESTED')
                self.assertEqual(state['status'], 'PENDING_RECONCILIATION')
                self.assertIsNone(state['highest_proven_window'])

    def test_old_failed_fixture_is_byte_identical_and_cannot_be_converted(self):
        self.new_run('original-failed-comparison', mode=None)
        self.bind('baseline')
        self.prepare('baseline')
        self.f.dispatch(transport=self.custom_transport(cached=50, evaluated=1320))
        old_run = self.run
        original = {p.name: p.read_bytes() for p in old_run.iterdir()}
        with self.assertRaises((AgentError, FileExistsError)):
            probe.init_run(old_run, 'http://127.0.0.1:30002/v1', str(self.f.key_file), trial_mode='native-capacity')
        for operation in (lambda: self.bind(), lambda: self.prepare('64k'), lambda: probe.launch(self.run)):
            with self.assertRaises(AgentError):
                operation()
        self.new_run('separate-native')
        self.bind()
        self.prepare()
        self.assertEqual({p.name: p.read_bytes() for p in old_run.iterdir()}, original)
        self.assertIsNone(probe.status(self.run)['highest_proven_window'])
        self.assert_no_comparisons()

    def test_direct_and_detached_prepare_reject_foreign_skipped_and_unknown_stages_without_mutation(self):
        self.bind()
        before = self.files()
        for stage in ('baseline', 'candidate', '128k', '256k', '512k', 'near1m', 'not-a-stage'):
            with self.subTest(stage=stage):
                with patch.object(probe.subprocess, 'Popen') as spawn:
                    with self.assertRaises(AgentError):
                        probe.launch_prepare(self.run, stage)
                    spawn.assert_not_called()
                accountant = Mock()
                with self.assertRaises(AgentError):
                    probe.prepare(self.run, stage, accountant=accountant)
                accountant.assert_not_called()
                self.assertEqual(self.files(), before)

    def test_unknown_persisted_mode_refuses_bind_prepare_and_status_without_mutation(self):
        config = probe.read_json(self.run / 'config.json')
        config['trial_mode'] = 'unrecognized-mode'
        probe.write_json(self.run / 'config.json', config)
        before = self.files()
        operations = (lambda: self.bind(), lambda: self.prepare(),
                      lambda: probe.launch_prepare(self.run, '64k'), lambda: probe.status(self.run))
        with patch.object(probe.subprocess, 'Popen') as spawn:
            for operation in operations:
                with self.subTest(operation=operation), self.assertRaises(AgentError):
                    operation()
                self.assertEqual(self.files(), before)
            spawn.assert_not_called()

    def test_three_actual_accounted_checks_alone_advance_proof_then_128k_grows(self):
        self.bind()
        for stage in ('64k', '128k'):
            for step in probe.steps(stage):
                with self.subTest(stage=stage, step=step):
                    previous_proof = None if stage == '64k' else 65536
                    count_before = len(self.f.account_calls)
                    self.prepare(stage)
                    state = self.f.state()
                    self.assertEqual(state['step'], step)
                    self.assertEqual(state['highest_proven_window'], previous_proof)
                    self.assertGreater(len(self.f.account_calls), count_before)
                    name = state['request_name']
                    body = probe.read_json(self.run / (name + '.body.json'))
                    accounted = probe.read_json(self.run / (name + '.tokens.json'))
                    self.assertEqual(accounted['body_sha256'], fixtures.wire_body(body)[1])
                    self.assertEqual(accounted['input_tokens'], len(accounted['token_ids']))
                    self.assertEqual(body['max_tokens'], 128 if step == 'cold' else 256)
                    self.assertEqual(body['stream'], step != 'cold')
                    if step == 'cold':
                        self.assertGreaterEqual(accounted['input_tokens'], probe.WINDOWS[stage] - 8192 - 256)
                        self.assertLessEqual(accounted['input_tokens'], probe.WINDOWS[stage] - 8192)
                    self.f.dispatch()
                    self.assertEqual(self.f.state()['highest_proven_window'],
                                     probe.WINDOWS[stage] if step == 'continuation' else previous_proof)
            results = self.f.state()['stages'][stage]['results']
            self.assertEqual([r['name'] for r in results], [stage + '.' + x for x in probe.steps(stage)])
            self.assertEqual(results[0]['checks'], {'early': True, 'middle': True, 'late': True})
            self.assertTrue(results[1]['checks']['worker_local'])
            self.assertEqual(results[2]['checks'], {'tool_continuation': True})
            with self.assertRaises(AgentError):
                self.prepare(stage)
        state = self.f.state()
        self.assertGreater(state['stages']['128k']['records'], state['stages']['64k']['records'])
        self.assertGreater(state['stages']['128k']['results'][0]['accounting']['common_prefix_tokens'], 50000)
        self.assertEqual({(cid, image) for _, cid, image in self.f.account_calls}, {('e' * 64, self.image)})
        self.assertEqual(probe.status(self.run)['highest_proven_window'], 131072)
        self.assert_no_comparisons()

    def test_initial_occupied_retrieval_preserves_nullable_and_reported_counts(self):
        for cached, evaluated in ((None, None), (50, 1320)):
            with self.subTest(cached=cached):
                self.new_run('observed-' + str(cached))
                self.bind()
                self.prepare()
                self.f.dispatch(transport=self.custom_transport(cached=cached, evaluated=evaluated))
                state = self.f.state()
                self.assertEqual(state['status'], 'STEP_PASS')
                result = state['stages']['64k']['results'][0]
                self.assertEqual(result['counters']['cached_tokens'], cached)
                self.assertEqual(result['counters']['evaluated_prompt_tokens'], evaluated)
                self.assertIsNone(state['highest_proven_window'])

    def test_missing_reuse_evidence_on_each_later_step_blocks_proof(self):
        for failed_step in ('tool', 'continuation'):
            with self.subTest(step=failed_step):
                self.new_run('reuse-' + failed_step)
                self.bind()
                for step in probe.steps('64k'):
                    self.prepare()
                    if step == failed_step:
                        def missing(*args):
                            transfer = self.f.transport(*args)
                            transfer.raw = self.f.response(missing_cache=True)
                            return transfer
                        self.f.dispatch(transport=missing)
                        break
                    self.f.dispatch()
                state = self.f.state()
                self.assertEqual(state['failure_class'], 'useful_prefix_reuse_NOT_TESTED')
                self.assertEqual(state['status'], 'PENDING_RECONCILIATION')
                self.assertIsNone(state['highest_proven_window'])
                self.assertNotEqual(state['stages']['64k']['status'], 'PASS')
                with self.assertRaises(AgentError):
                    self.prepare('128k')

    def test_later_failure_preserves_64k_proof_and_refuses_skip_revisit_rebinding(self):
        self.bind()
        self.f.finish_stage('64k')
        proven = copy.deepcopy(self.f.state()['stages']['64k'])
        before = self.files()
        for stage in ('64k', '256k', '512k', 'near1m', 'candidate'):
            for operation in (lambda: self.prepare(stage), lambda: probe.launch_prepare(self.run, stage)):
                with self.subTest(stage=stage), self.assertRaises(AgentError):
                    operation()
                self.assertEqual(self.files(), before)
        with self.assertRaises(AgentError):
            self.bind()
        self.prepare('128k')
        self.f.dispatch(transport=self.custom_transport(cached=None))
        state = self.f.state()
        self.assertEqual(state['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(state['failure_class'], 'useful_prefix_reuse_NOT_TESTED')
        self.assertEqual(state['highest_proven_window'], 65536)
        self.assertEqual(state['stages']['64k'], proven)
        self.assertEqual(state['stages']['128k']['results'], [])
        self.assertEqual(probe.status(self.run)['highest_proven_window'], 65536)
        with self.assertRaises(AgentError):
            self.prepare('128k')

    def test_native_actual_usage_and_runtime_restart_fail_without_proof(self):
        for failure in ('usage', 'restart'):
            with self.subTest(failure=failure):
                self.new_run('identity-' + failure)
                self.bind()
                self.prepare()
                class Restarted(fixtures.SyntheticSampler):
                    def next(self, timeout):
                        value = super().next(timeout)
                        value['container'].update(pid=4321, started_at='synthetic-reload')
                        return value
                transport = self.custom_transport(wrong_actual=True) if failure == 'usage' else Mock()
                self.f.dispatch(transport=transport, sampler=Restarted if failure == 'restart' else None)
                state = self.f.state()
                self.assertEqual(state['failure_class'], 'actual_usage_vs_native_accounting_NOT_TESTED'
                                 if failure == 'usage' else 'bound_runtime_restarted_or_changed')
                self.assertIsNone(state['highest_proven_window'])
                self.assertEqual(state['stages']['64k']['results'], [])
                if failure == 'restart':
                    transport.assert_not_called()

    def test_detached_prepare_and_start_are_durable_and_duplicate_dispatch_refuses(self):
        self.bind()
        with patch.object(probe.subprocess, 'Popen') as spawn:
            probe.launch_prepare(self.run, '64k')
            self.assertEqual(self.f.state()['status'], 'PREPARING')
            self.assertEqual(probe.status(self.run)['status'], 'PREPARATION_UNKNOWN')
            self.assertIn('_prepare', spawn.call_args.args[0])
        before = self.files()
        with probe.lock(self.run, 'request.lock'):
            old_umask = os.umask(0o077)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(probe.main(['_prepare', '--run', str(self.run), '--stage', '64k']), 2)
            finally:
                os.umask(old_umask)
        self.assertEqual(self.files(), before)
        self.prepare()
        def spawn_worker(*args, **kwargs):
            with probe.lock(self.run):
                self.assertEqual(self.f.state()['status'], 'STARTING')
        with patch.object(probe.subprocess, 'Popen', side_effect=spawn_worker) as spawn:
            probe.launch(self.run)
            before = self.files()
            for _ in range(2):
                self.assertEqual(probe.status(self.run)['status'], 'IN_FLIGHT_UNKNOWN')
            with self.assertRaises(AgentError):
                probe.launch(self.run)
            self.assertEqual(self.files(), before)
            spawn.assert_called_once()
        with probe.lock(self.run, 'request.lock'):
            self.assertEqual(probe.status(self.run)['status'], 'STARTING')
            duplicate = Mock()
            began = time.monotonic()
            with self.assertRaisesRegex(AgentError, 'owned_request_or_state_busy'):
                probe.worker(self.run, transport=duplicate)
            self.assertLess(time.monotonic() - began, 1)
            duplicate.assert_not_called()

    def test_native_active_status_contention_serializes_without_duplicate_dispatch(self):
        self.bind()
        self.prepare()
        with patch.object(probe.subprocess, 'Popen'):
            probe.launch(self.run)
        # Reuse the D3TR real-flock coordination fixture, with this public native
        # run. No synthetic PASS state or mocked lock acquisition is involved.
        locking = locking_fixtures.LockingTests()
        locking.f, locking.run = self.f, self.run
        with locking.status_reader() as (start, _, attempts):
            def transport(*args):
                transfer = self.f.transport(*args)
                transfer.done.clear()
                start()
                duplicate = Mock()
                with self.assertRaisesRegex(AgentError, 'owned_request_or_state_busy'):
                    probe.worker(self.run, transport=duplicate)
                duplicate.assert_not_called()
                return transfer
            owner = self
            class FinishingSampler(fixtures.SyntheticSampler):
                def next(self, timeout):
                    if owner.f.transfers:
                        owner.f.transfers[-1].done.set()
                    return super().next(timeout)
            probe.worker(self.run, transport=transport, sampler_factory=FinishingSampler)
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(len(self.f.transfers), 1)
        self.assertEqual(self.f.state()['status'], 'STEP_PASS')
        self.assertEqual(len(self.f.state()['stages']['64k']['results']), 1)
        self.assertIsNone(self.f.state()['highest_proven_window'])
        with self.assertRaises(AgentError):
            probe.launch(self.run)

    def test_active_unknown_and_failed_states_never_reset_on_prepare_or_cli_error(self):
        self.bind()
        self.prepare()
        with patch.object(probe.subprocess, 'Popen'):
            probe.launch(self.run)
        starting = self.f.state()
        for status in ('STARTING', 'IN_FLIGHT', 'PENDING_RECONCILIATION', 'IN_FLIGHT_UNKNOWN'):
            state = copy.deepcopy(starting)
            state['status'] = status
            state['dispatched_at'] = time.time() if status != 'STARTING' else None
            probe.write_json(self.run / 'state.json', state)
            before = self.files()
            with self.subTest(status=status), patch.object(probe.subprocess, 'Popen') as spawn:
                for stage in ('64k', 'candidate'):
                    for operation in (lambda: self.prepare(stage), lambda: probe.launch_prepare(self.run, stage)):
                        with self.assertRaises(AgentError):
                            operation()
                    old_umask = os.umask(0o077)
                    try:
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(probe.main(['_prepare', '--run', str(self.run), '--stage', stage]), 2)
                    finally:
                        os.umask(old_umask)
                    self.assertEqual(self.files(), before)
                with self.assertRaises(AgentError):
                    probe.launch(self.run)
                spawn.assert_not_called()

    def test_cancel_before_or_after_dispatch_never_retries_or_advances_proof(self):
        for when in ('starting', 'inflight'):
            with self.subTest(when=when):
                self.new_run('cancel-' + when)
                self.bind()
                self.prepare()
                if when == 'starting':
                    with patch.object(probe.subprocess, 'Popen'):
                        probe.launch(self.run)
                    probe.cancel(self.run)
                    transport = Mock()
                    probe.worker(self.run, transport=transport, sampler_factory=fixtures.SyntheticSampler)
                    transport.assert_not_called()
                else:
                    def cancelling(*args):
                        transfer = self.f.transport(*args)
                        probe.cancel(self.run)
                        return transfer
                    self.f.dispatch(transport=cancelling)
                    self.f.transfers[-1].cancel.assert_called()
                self.assertIsNone(self.f.state()['highest_proven_window'])
                self.assertEqual(self.f.state()['stages']['64k']['results'], [])
                before = self.files()
                with self.assertRaises(AgentError):
                    probe.launch(self.run)
                with self.assertRaises(AgentError):
                    self.prepare()
                self.assertEqual(self.files(), before)


if __name__ == '__main__':
    unittest.main()
