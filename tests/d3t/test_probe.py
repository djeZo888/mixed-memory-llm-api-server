"""Focused CPU-only driver tests; inject external accountant/network/telemetry.

Use real wire parsing, private state, body fitting, A1 JSON/SSE and worker-local
read_file. Synthetic byte tokens are deliberately not native/tokenizer evidence.
No test contacts an endpoint, SSH host, Docker, model, or GPU.
"""
from __future__ import annotations

import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from agent.protocol import AgentError
from d3t import probe
from d3t.accounting import wire_body, canonical, sha256


class SyntheticSampler:
    def __init__(self, *args):
        self.args, self.closed = args, False

    def next(self, timeout):
        container, image, context, _ = self.args
        gib = 1024 ** 3
        return {
            'timestamp': time.time(),
            'container': {'id': container, 'image_id': image, 'pid': 1234,
                          'started_at': 'synthetic-start', 'running': True, 'oom_killed': False},
            'required_context': context, 'slot_context': context, 'slot_count': 1, 'n_threads': 112,
            'placement': 'all_cpu' if image == probe.D1_IMAGE else 'n_cpu_moe_76',
            'mounts': dict(probe.guards.MOUNTS), 'root_available_bytes': 8 * gib,
            'vmstat': {'pswpin': 0, 'pswpout': 0, 'oom_kill': 0},
            'vmstat_delta': {'pswpin': 0, 'pswpout': 0, 'oom_kill': 0},
            'errors': {name: 0 for name in probe.guards.ERROR_PATTERNS},
            'gpus': [{'index': index, 'uuid': 'GPU-synthetic-' + str(index),
                      'free_bytes': 24 * gib, 'total_bytes': 96 * gib} for index in (0, 1)],
            'host_kib': {'MemAvailable': 400 * 1024 ** 2},
            'process_kib': {'Rss': 420 * 1024 ** 2, 'Pss': 412 * 1024 ** 2, 'Swap': 0, 'VmSwap': 0},
            'native': {'n_ctx': context, 'n_ctx_seq': context, 'n_seq_max': 1,
                       'n_batch': 2048, 'n_ubatch': 512, 'flash_attn': 1, 'fused_lid': 1,
                       'lid_nodes': 21, 'fa_nodes': 78, 'no_alloc': 0,
                       'compute_bytes': {'CUDA0': gib, 'CUDA1': gib},
                       'cache_bytes': {'CUDA0': 48 * gib, 'CUDA1': 45 * gib}},
        }

    def close(self):
        self.closed = True


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.run = self.root / 'private-run'
        self.key = 'synthetic-worker-credential-not-a-real-key'
        self.key_file = self.root / 'key.txt'
        self.key_file.write_text(self.key)
        self.key_file.chmod(0o600)
        probe.init_run(self.run, 'http://127.0.0.1:30002/v1', str(self.key_file))
        self.phases = {
            'baseline': {'container_id': 'b' * 64, 'image_id': probe.D1_IMAGE, 'context': 32768},
            'candidate': {'container_id': 'c' * 64, 'image_id': 'sha256:' + 'd' * 64, 'context': 32768},
            'native': {'container_id': 'e' * 64, 'image_id': 'sha256:' + 'd' * 64, 'context': 1048576},
        }
        config = probe.read_json(self.run / 'config.json')
        config['phases'] = copy.deepcopy(self.phases)
        probe.write_json(self.run / 'config.json', config)
        self.account_calls = []
        self.transfers = []
        self.write_admissions()

    def write_admissions(self):
        for name, phase in self.phases.items():
            sample = SyntheticSampler(phase['container_id'], phase['image_id'], phase['context'], 1).next(timeout=1)
            probe.write_json(self.run / (name + '.admission.json'), sample)

    def state(self):
        return probe.read_json(self.run / 'state.json')

    def accountant(self, body, container_id, image_id):
        self.account_calls.append((copy.deepcopy(body), container_id, image_id))
        # An explicit dependency fixture, not a copied native-accounting algorithm.
        prompt = canonical({'tools': body['tools'], 'messages': body['messages']})
        tokens = list(prompt)
        context = 1048576 if container_id == self.phases['native']['container_id'] else 32768
        return {'body_sha256': wire_body(body)[1], 'token_ids': tokens,
                'input_tokens': len(tokens), 'tokens_sha256': sha256(canonical(tokens)),
                'rendered_prompt_sha256': sha256(prompt), 'configured_context': context,
                'template_sha256': '15d2a7176beb599de0a59af8314b4869011e416cff7f65748b314940d3379b0e',
                'container_id': container_id, 'image_id': image_id}

    def response(self, *, echo_key=False, missing_cache=False):
        s = self.state()
        if s['step'] in ('cold', 'warm'):
            message = {'role': 'assistant', 'content': json.dumps(s['stages'][s['stage']]['expected'])}
            finish = 'stop'
        elif s['step'] == 'tool':
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'native-id-' + s['stage'], 'type': 'function',
                'function': {'name': 'read_file', 'arguments': '{"path":"calc.py"}'}}]}
            finish = 'tool_calls'
        else:
            message = {'role': 'assistant', 'content': 'LOCAL_READ_OK: return a - b'}
            finish = 'stop'
        if echo_key:
            message['content'] = self.key
        count = s['accounting']['input_tokens']
        cached = s['accounting']['common_prefix_tokens'] or 0
        if s['step'] == 'cold' and s['stage'] in ('baseline', 'candidate'):
            cached = 0
        usage = {'prompt_tokens': count, 'completion_tokens': 16, 'total_tokens': count + 16}
        if not missing_cache:
            usage['prompt_tokens_details'] = {'cached_tokens': cached}
        body = probe.read_json(self.run / (s['request_name'] + '.body.json'))
        if not body['stream']:
            return canonical({'model': 'glm-5.3', 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}], 'usage': usage})
        delta = copy.deepcopy(message)
        for index, call in enumerate(delta.get('tool_calls', [])):
            call['index'] = index
        # Exercise actual A1 SSE parser, native IDs, and usage-only terminal chunk.
        chunks = [
            {'model': 'glm-5.3', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
            {'model': 'glm-5.3', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
            {'model': 'glm-5.3', 'choices': [], 'usage': usage},
        ]
        return b''.join(b'data: ' + canonical(chunk) + b'\n\n' for chunk in chunks) + b'data: [DONE]\n\n'

    def transport(self, base_url, key, raw, stream, timeout):
        self.assertEqual(self.state()['status'], 'IN_FLIGHT')
        self.assertEqual(key, self.key)
        self.assertEqual(raw, probe.private_read(self.run / (self.state()['request_name'] + '.body.json')))
        self.assertGreater(timeout, 0)
        done = threading.Event()
        done.set()
        transfer = Mock(done=done, error=None, raw=self.response(), status=200)
        self.transfers.append(transfer)
        return transfer

    def dispatch(self, transport=None, sampler=None):
        with patch.object(probe.subprocess, 'Popen') as spawn:
            probe.launch(self.run)
        self.assertEqual(spawn.call_count, 1)
        probe.worker(self.run, transport=transport or self.transport,
                     sampler_factory=sampler or SyntheticSampler)

    def finish_stage(self, stage):
        for step in probe.steps(stage):
            probe.prepare(self.run, stage, accountant=self.accountant)
            self.assertEqual(self.state()['step'], step)
            self.dispatch()
            self.assertEqual(self.state()['status'], 'STAGE_PASS' if step == 'continuation' else 'STEP_PASS', self.state().get('failure_class'))

    def seed_comparison_pass(self):
        s = self.state()
        s['stages'] = {name: {'status': 'PASS', 'results': [], 'records': 64} for name in ('baseline', 'candidate')}
        s['status'] = 'STAGE_PASS'
        s['native_configured_capacity'] = 1048576
        probe.write_json(self.run / 'state.json', s)

    def test_real_prepare_worker_tool_roundtrip_and_comparison_body_hashes(self):
        self.finish_stage('baseline')
        self.finish_stage('candidate')
        self.assertEqual(len(self.transfers), 8)
        extrema = self.state()['stages']['candidate']['results'][-1]['sampled_extrema']
        self.assertEqual(extrema['rss_max_kib'], 420 * 1024 ** 2)
        self.assertEqual(extrema['pss_max_kib'], 412 * 1024 ** 2)
        self.assertEqual(extrema['mem_available_min_kib'], 400 * 1024 ** 2)
        for stage in ('baseline', 'candidate'):
            cold = probe.private_read(self.run / (stage + '.cold.body.json'))
            warm = probe.private_read(self.run / (stage + '.warm.body.json'))
            self.assertEqual(cold, warm)
            tool = probe.read_json(self.run / (stage + '.tool.result.json'))
            self.assertEqual(tool['message']['tool_call_id'], 'native-id-' + stage)
            self.assertIn('return a - b', tool['message']['content'])
            self.assertTrue(tool['evidence']['worker_local'])
            continuation = probe.read_json(self.run / (stage + '.continuation.body.json'))
            self.assertFalse(continuation['stream'])
            self.assertEqual(continuation['reasoning_effort'], 'low')
            self.assertEqual(continuation['messages'][-1], tool['message'])
            self.assertEqual(continuation['messages'][-2]['tool_calls'][0]['id'], tool['message']['tool_call_id'])
            self.assertNotIn('reasoning_content', continuation['messages'][-2])
            self.assertTrue(probe.read_json(self.run / (stage + '.tool.body.json'))['stream'])
        for step in ('cold', 'warm', 'tool'):
            self.assertEqual(probe.private_read(self.run / ('baseline.' + step + '.body.json')),
                             probe.private_read(self.run / ('candidate.' + step + '.body.json')))
        # Exact continuation hashes are retained separately; real native IDs differ.
        self.assertNotEqual(self.state()['stages']['baseline']['results'][-1]['body_sha256'],
                            self.state()['stages']['candidate']['results'][-1]['body_sha256'])
        public = json.dumps(probe.status(self.run))
        self.assertNotIn(self.key, public)
        self.assertNotIn('return a - b', public)
        self.assertNotIn('native-id-', public)
        for path in self.run.iterdir():
            if path.is_file():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600, path.name)

    def test_native_fitted_input_reserve_and_append_only_prefix_under_same_container(self):
        self.seed_comparison_pass()
        self.finish_stage('64k')
        self.assertTrue(probe.read_json(self.run / '64k.continuation.body.json')['stream'])
        cold = probe.read_json(self.run / '64k.cold.tokens.json')
        self.assertGreaterEqual(cold['input_tokens'], 65536 - 8192 - 256)
        self.assertLessEqual(cold['input_tokens'], 65536 - 8192)
        self.assertEqual(self.state()['highest_proven_window'], 65536)
        self.assertEqual(self.state()['native_configured_capacity'], 1048576)
        probe.prepare(self.run, '128k', accountant=self.accountant)
        new = self.state()
        self.assertGreater(new['accounting']['common_prefix_tokens'], 50000)
        self.assertEqual(new['highest_proven_window'], 65536)
        self.assertLessEqual(new['accounting']['input_tokens'], 131072 - 8192)
        self.assertEqual({container for _, container, _ in self.account_calls}, {self.phases['native']['container_id']})
        # At most18 fitting calls plus one final account per occupied cold request.
        self.assertLessEqual(len(self.account_calls), 40)

    def test_occupied_proof_requires_complete_native_stage_and_survives_later_failure(self):
        # These injected byte counts/samples exercise publication rules only;
        # configured capacity and short comparisons are not live occupancy proof.
        state = self.state()
        state['native_configured_capacity'] = 1048576
        probe.write_json(self.run / 'state.json', state)
        for stage in ('baseline', 'candidate'):
            for step in probe.steps(stage):
                with self.subTest(stage=stage, step=step):
                    probe.prepare(self.run, stage, accountant=self.accountant)
                    self.assertEqual(self.state()['step'], step)
                    self.dispatch()
                    self.assertEqual(self.state()['status'], 'STAGE_PASS' if step == 'continuation' else 'STEP_PASS')
                    self.assertIsNone(self.state()['highest_proven_window'])
                    self.assertIsNone(probe.status(self.run)['highest_proven_window'])
            comparison = self.state()['stages'][stage]
            self.assertEqual(comparison['status'], 'PASS')
            self.assertEqual([r['name'] for r in comparison['results']],
                             [stage + '.' + step for step in probe.steps(stage)])
            self.assertTrue(all(r['status'] == 'PASS' for r in comparison['results']))
            self.assertLess(comparison['results'][0]['accounting']['input_tokens'], 32768 - 8192 - 256)
        comparison_evidence = copy.deepcopy(self.state()['stages'])

        for step in probe.steps('64k'):
            with self.subTest(stage='64k', step=step):
                probe.prepare(self.run, '64k', accountant=self.accountant)
                self.assertEqual(self.state()['step'], step)
                self.assertIsNone(self.state()['highest_proven_window'])
                if step == 'cold':
                    count = self.state()['accounting']['input_tokens']
                    self.assertGreaterEqual(count, 65536 - 8192 - 256)
                    self.assertLessEqual(count, 65536 - 8192)
                self.dispatch()
                self.assertEqual(self.state()['status'], 'STAGE_PASS' if step == 'continuation' else 'STEP_PASS')
                expected = 65536 if step == 'continuation' else None
                self.assertEqual(self.state()['highest_proven_window'], expected)
                self.assertEqual(probe.status(self.run)['highest_proven_window'], expected)
        results = self.state()['stages']['64k']['results']
        self.assertEqual([r['name'] for r in results], ['64k.cold', '64k.tool', '64k.continuation'])
        self.assertEqual(results[0]['checks'], {'early': True, 'middle': True, 'late': True})
        self.assertTrue(results[1]['checks']['worker_local'])
        self.assertEqual(results[2]['checks'], {'tool_continuation': True})

        probe.prepare(self.run, '128k', accountant=self.accountant)
        self.assertEqual(self.state()['highest_proven_window'], 65536)
        def missing_cache(*args):
            transfer = self.transport(*args)
            transfer.raw = self.response(missing_cache=True)
            return transfer
        self.dispatch(transport=missing_cache)
        failed = self.state()
        self.assertEqual(failed['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(failed['failure_class'], 'useful_prefix_reuse_NOT_TESTED')
        self.assertEqual(failed['stages']['128k']['results'], [])
        self.assertEqual(failed['highest_proven_window'], 65536)
        self.assertEqual(probe.status(self.run)['highest_proven_window'], 65536)
        self.assertEqual(failed['native_configured_capacity'], 1048576)
        self.assertEqual({stage: failed['stages'][stage] for stage in ('baseline', 'candidate')}, comparison_evidence)
        self.assertEqual(len(self.transfers), 12)

    def test_underoccupied_initial_native_count_cannot_establish_proof(self):
        self.seed_comparison_pass()
        body, _ = probe.cold_body(64, 128)
        with self.assertRaisesRegex(AgentError, 'native_occupied_target_not_reached'):
            probe.checked_account(body, self.phases['native'], '64k', True, accountant=self.accountant)
        self.assertIsNone(self.state()['highest_proven_window'])
        self.assertEqual(self.transfers, [])

    def test_launch_checkpoints_before_spawn_and_status_never_reissues(self):
        probe.prepare(self.run, 'baseline', accountant=self.accountant)
        def spawn(*args, **kwargs):
            # This would fail with the original nonblocking state-lock spawn race.
            with probe.lock(self.run):
                self.assertEqual(self.state()['status'], 'STARTING')
            self.assertNotIn(self.key, repr((args, kwargs)))
            self.assertTrue(kwargs['start_new_session'])
        with patch.object(probe.subprocess, 'Popen', side_effect=spawn) as process:
            probe.launch(self.run)
            before = probe.private_read(self.run / 'state.json')
            for _ in range(3):
                self.assertEqual(probe.status(self.run)['status'], 'IN_FLIGHT_UNKNOWN')
            self.assertEqual(probe.private_read(self.run / 'state.json'), before)
            with self.assertRaises(AgentError):
                probe.launch(self.run)
            self.assertEqual(process.call_count, 1)
        with probe.lock(self.run, 'request.lock'):
            self.assertEqual(probe.status(self.run)['status'], 'STARTING')

    def test_deadline_expiring_in_initial_sampler_never_dispatches(self):
        probe.prepare(self.run, 'baseline', accountant=self.accountant)
        with patch.object(probe.subprocess, 'Popen'):
            probe.launch(self.run)
        now = time.time()
        s = self.state()
        s['request_deadline'] = now + 1
        probe.write_json(self.run / 'state.json', s)
        clock = [now]
        class ExpiringSampler(SyntheticSampler):
            def next(self, timeout):
                clock[0] += 2
                return super().next(timeout)
        transport = Mock()
        with patch.object(probe.time, 'time', side_effect=lambda: clock[0]):
            probe.worker(self.run, transport=transport, sampler_factory=ExpiringSampler)
        transport.assert_not_called()
        self.assertEqual(self.state()['status'], 'NOT_TESTED')
        self.assertEqual(self.state()['failure_class'], 'deadline_before_dispatch')
        self.assertEqual(probe.status(self.run)['stage_status']['candidate'], 'PENDING_NOT_TESTED')

    def test_inflight_timeout_requires_reconciliation_and_blocks_later_stage(self):
        probe.prepare(self.run, 'baseline', accountant=self.accountant)
        def expired_transport(*args):
            transfer = self.transport(*args)
            transfer.done.clear()
            return transfer
        now = time.time()
        clock = [now]
        state = self.state()
        state['deadline'] = now + 1.25
        probe.write_json(self.run / 'state.json', state)
        class AdvancingSampler(SyntheticSampler):
            def next(self, timeout):
                clock[0] += .5
                return super().next(timeout)
        with patch.object(probe.time, 'time', side_effect=lambda: clock[0]):
            self.dispatch(transport=expired_transport, sampler=AdvancingSampler)
        self.assertEqual(self.state()['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(self.state()['failure_class'], 'stage_timeout')
        self.transfers[-1].cancel.assert_called()
        with self.assertRaises(AgentError):
            probe.prepare(self.run, 'candidate', accountant=self.accountant)
        with self.assertRaises(AgentError):
            probe.launch(self.run)
        self.assertEqual(probe.status(self.run)['stage_status']['candidate'], 'PENDING_NOT_TESTED')

    def test_missing_cache_and_credential_echo_fail_without_exposure(self):
        for mode in ('missing_cache', 'echo_key'):
            with self.subTest(mode=mode):
                # Each independent failure gets one task-private run; no retry.
                if mode == 'echo_key':
                    self.run = self.root / 'second-private-run'
                    probe.init_run(self.run, 'http://127.0.0.1:30002/v1', str(self.key_file))
                    config = probe.read_json(self.run / 'config.json')
                    config['phases'] = self.phases
                    probe.write_json(self.run / 'config.json', config)
                    self.write_admissions()
                probe.prepare(self.run, 'baseline', accountant=self.accountant)
                def bad_response(*args):
                    transfer = self.transport(*args)
                    transfer.raw = self.response(**{mode: True})
                    return transfer
                self.dispatch(transport=bad_response)
                self.assertEqual(self.state()['status'], 'PENDING_RECONCILIATION')
                self.assertEqual(self.state()['stages']['baseline']['results'], [])
                self.assertNotIn(self.key, json.dumps(probe.status(self.run)))
                for output in self.run.iterdir():
                    if output.is_file():
                        self.assertNotIn(self.key.encode(), probe.private_read(output), output.name)
                if mode == 'echo_key':
                    self.assertEqual(self.state()['failure_class'], 'credential_echo_response_refused')

    def test_body_tamper_and_oversized_reserve_refuse_before_transport(self):
        body, _ = probe.cold_body(64, 128)
        phase = self.phases['native']
        def overfull(*args):
            value = self.accountant(*args)
            value['token_ids'] = [1] * 57345
            value['input_tokens'] = len(value['token_ids'])
            value['tokens_sha256'] = sha256(canonical(value['token_ids']))
            return value
        with self.assertRaisesRegex(AgentError, 'reserve'):
            probe.checked_account(body, phase, '64k', True, accountant=overfull)
        probe.prepare(self.run, 'baseline', accountant=self.accountant)
        probe.write_bytes(self.run / 'baseline.cold.body.json', b'{}')
        transport = Mock()
        self.dispatch(transport=transport)
        transport.assert_not_called()
        self.assertEqual(self.state()['status'], 'NOT_TESTED')
        self.assertEqual(self.state()['failure_class'], 'body_changed_or_contains_key')

    def test_detached_preparation_is_inspectable_and_does_not_dispatch_generation(self):
        with patch.object(probe.subprocess, 'Popen') as spawn:
            probe.launch_prepare(self.run, 'baseline')
        self.assertEqual(spawn.call_count, 1)
        self.assertIn('_prepare', spawn.call_args.args[0])
        self.assertEqual(self.state()['status'], 'PREPARING')
        self.assertEqual(probe.status(self.run)['status'], 'PREPARATION_UNKNOWN')
        with self.assertRaises(AgentError):
            probe.launch(self.run)
        def inspecting_accountant(*args):
            self.assertEqual(probe.status(self.run)['status'], 'PREPARING')
            return self.accountant(*args)
        probe.prepare(self.run, 'baseline', accountant=inspecting_accountant)
        self.assertEqual(self.state()['status'], 'PREPARED')
        self.assertEqual(self.transfers, [])

    def test_context_tokens_and_loaded_template_changes_refuse(self):
        body, _ = probe.cold_body(64, 256)
        for field, value in (('configured_context', 8192), ('tokens_sha256', '0' * 64)):
            def changed(*args):
                result = self.accountant(*args)
                result[field] = value
                return result
            with self.subTest(field=field), self.assertRaises(AgentError):
                probe.checked_account(body, self.phases['baseline'], 'baseline', True, accountant=changed)
        probe.prepare(self.run, 'baseline', accountant=self.accountant)
        self.dispatch()
        def template_changed(*args):
            result = self.accountant(*args)
            result['template_sha256'] = '0' * 64
            return result
        with self.assertRaisesRegex(AgentError, 'actual_loaded_template_changed'):
            probe.prepare(self.run, 'baseline', accountant=template_changed)

    def test_cooperative_cancel_only_cancels_owned_transfer_and_blocks_retry(self):
        probe.prepare(self.run, 'baseline', accountant=self.accountant)
        def cancellation(*args):
            transfer = self.transport(*args)
            probe.cancel(self.run)
            return transfer
        self.dispatch(transport=cancellation)
        self.assertEqual(self.state()['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(self.state()['failure_class'], 'owner_cancelled')
        self.transfers[-1].cancel.assert_called()
        with self.assertRaises(AgentError):
            probe.launch(self.run)

    def test_private_path_parent_components_symlinks_and_public_files_refuse(self):
        with self.assertRaisesRegex(AgentError, 'parent_path_refused'):
            probe.private_dir(self.root / 'sibling' / '..' / 'bypass', create=True)
        alias = self.root / 'alias'
        alias.symlink_to(self.run, target_is_directory=True)
        with self.assertRaisesRegex(AgentError, 'symlink_directory_refused'):
            probe.private_dir(alias)
        path = self.root / 'public.json'
        path.write_text('{}')
        path.chmod(0o644)
        with self.assertRaisesRegex(AgentError, 'private_file_required'):
            probe.private_read(path)

    def test_real_loopback_transfer_exact_bytes_json_sse_limits_and_socket_cancel(self):
        body, _ = probe.cold_body(64, 256)
        raw, body_hash = wire_body(body)
        control = {'mode': 'json', 'seen': []}
        stall_seen, release_stall = threading.Event(), threading.Event()
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass  # Never print request metadata/headers.
            def do_POST(self):
                request = self.rfile.read(int(self.headers['Content-Length']))
                control['seen'].append((self.path, request, self.headers.get('Authorization')))
                mode = control['mode']
                if mode == 'stall':
                    stall_seen.set()
                    release_stall.wait(2)
                    self.close_connection = True
                    return
                self.send_response(503 if mode == 'error' else 200)
                self.send_header('Content-Type', 'text/event-stream' if mode == 'sse' else 'application/json')
                if mode == 'oversize':
                    self.send_header('Content-Length', str(probe.MAX_RAW + 1))
                elif mode == 'json':
                    self.send_header('Content-Length', '2')
                elif mode == 'error':
                    self.send_header('Content-Length', '0')
                self.end_headers()
                if mode == 'json':
                    self.wfile.write(b'{}')
                elif mode == 'sse':
                    # No Content-Length or close: only [DONE] permits completion.
                    self.wfile.write(b'data: [DONE]\r\n\r\n')
                self.wfile.flush()
        # Avoid stdlib HTTPServer's unrelated reverse-DNS lookup at bind time.
        with patch('socket.getfqdn', return_value='localhost'):
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port) + '/v1'
        transfers = []
        try:
            for mode in ('json', 'sse', 'error', 'oversize', 'stall'):
                with self.subTest(mode=mode):
                    control['mode'] = mode
                    transfer = probe.Transfer(base, self.key, raw, mode == 'sse', 1)
                    transfers.append(transfer)
                    if mode == 'stall':
                        self.assertTrue(stall_seen.wait(1))
                        transfer.cancel()  # Scoped connection only; no process/PID kill.
                    self.assertTrue(transfer.done.wait(2), 'bounded loopback transfer did not finish')
                    if mode in ('json', 'sse'):
                        self.assertIsNone(transfer.error)
                        self.assertEqual(transfer.raw, b'{}' if mode == 'json' else b'data: [DONE]\r\n\r\n')
                    else:
                        self.assertEqual(transfer.error, 'transport_failed')
                        self.assertIsNone(transfer.raw)
            self.assertEqual(len(control['seen']), 5)
            for path, sent, auth in control['seen']:
                self.assertEqual(path, '/v1/chat/completions')
                self.assertEqual(sent, raw)
                self.assertEqual(probe.digest(sent), body_hash)
                self.assertEqual(auth, 'Bearer ' + self.key)
                self.assertNotIn(self.key.encode(), sent)
        finally:
            release_stall.set()
            for transfer in transfers:
                transfer.cancel()
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)


if __name__ == '__main__':
    unittest.main()
