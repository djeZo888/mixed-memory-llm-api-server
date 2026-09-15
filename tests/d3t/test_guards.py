"""Focused CPU-only parsing, guard and bounded transport tests; no SSH in tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from d3t import guards

CID = 'a' * 64
PATCHED = 'sha256:' + 'b' * 64


def arguments(context=32768, candidate=False):
    args = ['--model', '/models/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf',
            '--host', '0.0.0.0', '--port', '30002', '--alias', 'glm-5.3',
            '--api-key-file', '/run/secrets/llm-api-key', '--ctx-size', str(context),
            '--parallel', '1', '--jinja', '--no-webui', '--n-gpu-layers', '999',
            '--split-mode', 'layer', '--tensor-split', '1,1', '--load-mode', 'none',
            '--device', 'CUDA0,CUDA1', '--chat-template-kwargs', '{"clear_thinking":true}']
    return args + (['--n-cpu-moe', '76'] if candidate else ['--cpu-moe'])


def log_state(context=32768, native=False):
    state = {'log_lines': 0, 'errors': {key: 0 for key in guards.ERROR_PATTERNS}}
    guards.parse_log_line('3.00.386.091 I cmn init: llama threadpool init, n_threads = 112', state)
    guards.parse_log_line('3.02.045.785 I srv load_model: initializing, n_slots = 1, n_ctx_slot = %d' % context, state)
    if native:
        for line in diagnostic(context):
            guards.parse_log_line(line, state)
    return state


def diagnostic(context=1048576):
    yield ('D3T_NATIVE_V1 kind=graph n_ctx=%d n_ctx_seq=%d n_seq_max=1 n_batch=2048 '
           'n_ubatch=512 flash_attn=1 fused_lid=1 lid_nodes=21 fa_nodes=78 no_alloc=0') % (context, context)
    for kind in ('compute', 'cache'):
        for backend in ('CUDA0', 'CUDA1'):
            yield 'D3T_NATIVE_V1 kind=%s backend=%s bytes=4294967296' % (kind, backend)
    yield 'D3T_NATIVE_V1 kind=end'


def snapshot(context=32768, candidate=False):
    state = log_state(context, native=candidate)
    return {'timestamp': time.time(), 'sampled_only': True, 'status': 'PASS', 'required_context': context,
            'container': {'id': CID, 'image_id': PATCHED if candidate else guards.BASELINE_IMAGE,
                          'pid': 12345, 'started_at': '2026-09-15T00:48:45Z', 'running': True, 'oom_killed': False},
            'mounts': guards.MOUNTS.copy(), 'root_available_bytes': 4 * guards.GIB,
            'gpus': [{'index': i, 'uuid': 'GPU-synthetic-%d' % i, 'free_bytes': 16 * guards.GIB,
                      'total_bytes': 96 * guards.GIB} for i in (0, 1)],
            'host_kib': {'MemTotal': 900000000, 'MemAvailable': 400000000, 'SwapTotal': 3000000, 'SwapFree': 2985920},
            'host_swap_used_kib': 14080, 'process_kib': {'Rss': 420000000, 'Pss': 412000000, 'Swap': 0, 'VmSwap': 0},
            'vmstat': {'pswpin': 19045, 'pswpout': 35821, 'oom_kill': 0},
            'vmstat_delta': {'pswpin': 0, 'pswpout': 0, 'oom_kill': 0},
            'errors': state['errors'], 'slot_count': state['slot_count'], 'slot_context': state['slot_context'],
            'n_threads': state['n_threads'], 'native': state.get('native'),
            'placement': 'n_cpu_moe_76' if candidate else 'all_cpu'}


class TelemetryTests(unittest.TestCase):
    def test_real_d3_startup_grammar_and_historic_host_swap_are_reported_honestly(self):
        sample = snapshot()
        self.assertIs(guards.check_snapshot(sample), sample)
        self.assertEqual(sample['host_swap_used_kib'], 14080)
        self.assertIsNone(sample['native'])
        self.assertEqual(sample['n_threads'], 112)

    def test_exact_reviewed_arguments_preserve_baseline_and_one_candidate(self):
        self.assertEqual(guards._reviewed_args(arguments(), guards.BASELINE_IMAGE, 32768), 'all_cpu')
        self.assertEqual(guards._reviewed_args(arguments(1048576, True), PATCHED, 1048576), 'n_cpu_moe_76')
        for args in (arguments() + ['--n-cpu-moe', '76'], arguments() + ['--rope-scale', '2'],
                     arguments() + ['--api-key', 'SYNTHETIC-SECRET-NOT-REAL'], arguments() + ['--tensor-split', '2,1']):
            with self.subTest(args=args[-2:]), self.assertRaises(guards.Error):
                guards._reviewed_args(args, PATCHED, 32768)
        with self.assertRaises(guards.Error):
            guards._reviewed_args(arguments(1048576), guards.BASELINE_IMAGE, 1048576)

    def test_end_commits_complete_group_and_new_partial_invalidates_old_group(self):
        state = log_state()
        records = list(diagnostic())
        for line in records[:-1]:
            guards.parse_log_line(line, state)
        self.assertIsNone(state['native'])
        guards.parse_log_line(records[-1], state)
        first = copy.deepcopy(state['native'])
        guards.parse_log_line(records[0], state)
        self.assertIsNone(state['native'])
        self.assertEqual(first['lid_nodes'], 21)
        self.assertEqual(first['compute_bytes']['CUDA0'], 4294967296)

    def test_diagnostic_spaces_order_and_duplicate_required_backends(self):
        state = log_state()
        guards.parse_log_line(next(diagnostic()), state)
        guards.parse_log_line('D3T_NATIVE_V1 kind=compute backend=CUDA host buffer bytes=1024', state)
        guards.parse_log_line('D3T_NATIVE_V1 kind=compute backend=CUDA0 bytes=1024', state)
        with self.assertRaisesRegex(guards.Error, 'duplicate_native'):
            guards.parse_log_line('D3T_NATIVE_V1 kind=compute backend=CUDA0 bytes=1024', state)
        guards.parse_log_line('D3T_NATIVE_V1 kind=cache backend=CUDA0 bytes=1024', state)
        with self.assertRaisesRegex(guards.Error, 'order'):
            guards.parse_log_line('D3T_NATIVE_V1 kind=compute backend=CUDA1 bytes=1024', state)
        with self.assertRaisesRegex(guards.Error, 'unexpected_native_end'):
            guards.parse_log_line('D3T_NATIVE_V1 kind=end', log_state())

    def test_native_and_patched_32k_require_actual_graph_and_allocations(self):
        for context in (32768, 1048576):
            with self.subTest(context=context):
                sample = snapshot(context, True)
                guards.check_snapshot(sample, native=context == 1048576)
                sample['native'] = None
                with self.assertRaisesRegex(guards.Error, 'NOT_TESTED_native'):
                    guards.check_snapshot(sample)
        sample = snapshot(1048576, True)
        sample['native']['compute_bytes'].pop('CUDA1')
        with self.assertRaisesRegex(guards.Error, 'allocated_buffers'):
            guards.check_snapshot(sample, native=True)

    def test_fusion_fallback_is_an_error_even_before_complete_diagnostic(self):
        state = log_state(1048576, True)
        guards.parse_log_line(next(diagnostic()).replace('fused_lid=1', 'fused_lid=0'), state)
        self.assertGreater(state['errors']['fusion_fallback'], 0)
        guards.parse_log_line('resolve_fused_ops: Lightning Indexer not supported, set to disabled', state)
        self.assertGreater(state['errors']['fusion_fallback'], 1)

    def test_each_gpu_root_process_swap_and_real_error_floors_stop(self):
        modifications = [lambda s: s.update(root_available_bytes=4 * guards.GIB - 1),
                         lambda s: s['gpus'][1].update(free_bytes=16 * guards.GIB - 1),
                         lambda s: s['process_kib'].update(Swap=1),
                         lambda s: s['vmstat_delta'].update(pswpout=1),
                         lambda s: s['errors'].update(storage=1),
                         lambda s: s['errors'].update(cuda=1),
                         lambda s: s['container'].update(oom_killed=True)]
        for mutate in modifications:
            sample = snapshot(); mutate(sample)
            with self.assertRaises(guards.Error):
                guards.check_snapshot(sample)

    def test_missing_measurements_never_become_zero(self):
        sample = snapshot(); del sample['process_kib']['Pss']
        with self.assertRaisesRegex(guards.Error, 'missing_or_invalid'):
            guards.check_snapshot(sample)

    def test_same_container_restart_and_sampling_gaps_are_not_resumption_proof(self):
        previous = snapshot(); previous['timestamp'] -= 1
        sample = snapshot()
        guards.check_snapshot(sample, previous=previous)
        self.assertEqual(guards.stable_identity(sample), guards.stable_identity(previous))
        sample['container']['started_at'] = '2026-09-15T02:00:00Z'
        with self.assertRaisesRegex(guards.Error, 'runtime_changed'):
            guards.check_snapshot(sample, previous=previous)
        sample = snapshot(); previous['timestamp'] -= 3
        with self.assertRaisesRegex(guards.Error, 'sample_gap'):
            guards.check_snapshot(sample, previous=previous)

    def test_counter_increase_between_individually_successful_collects_stops(self):
        previous = snapshot(); previous['timestamp'] -= 1
        sample = snapshot(); sample['vmstat']['pswpin'] += 1
        with self.assertRaisesRegex(guards.Error, 'counter_changed'):
            guards.check_snapshot(sample, previous=previous)

    def test_freshness_allows_measured_tiny_clock_skew_but_not_stale_samples(self):
        sample = snapshot()
        with mock.patch.object(guards.time, 'time', return_value=sample['timestamp'] - 0.025):
            guards.check_snapshot(sample)
        for now in (sample['timestamp'] - 0.251, sample['timestamp'] + 2.001):
            with mock.patch.object(guards.time, 'time', return_value=now), self.assertRaisesRegex(guards.Error, 'stale_or_future'):
                guards.check_snapshot(sample)

    def test_shipped_remote_payload_compiles_and_rejects_unbounded_or_ambiguous_inputs(self):
        source = guards._source(CID, PATCHED, 1048576, 600)
        compile(source, '<d3t-shipped-remote>', 'exec')
        self.assertIn('select.select([sys.stdin]', source)
        self.assertNotIn('SYNTHETIC-SECRET', source)
        for context, cap in ((65536, 600), (1048576, 86401), (True, 600)):
            with self.assertRaises(guards.Error):
                guards._source(CID, PATCHED, context, cap)

    def test_sampler_reader_preserves_buffered_lines_and_has_bounded_partial_read(self):
        read_fd, write_fd = os.pipe()
        sampler = guards.Sampler.__new__(guards.Sampler)
        sampler.process = mock.Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
        sampler.pending = b''
        try:
            os.write(write_fd, b'{"one":1}\n{"two":2}\n')
            self.assertEqual(sampler.next(timeout=1), {'one': 1})
            self.assertEqual(sampler.next(timeout=1), {'two': 2})
            os.write(write_fd, b'{"partial":')
            with self.assertRaisesRegex(guards.Error, 'snapshot_timeout'):
                sampler.next(timeout=0.01)
        finally:
            os.close(write_fd); sampler.process.stdout.close()

    def test_proc_metric_parser_uses_required_actual_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'smaps_rollup'
            path.write_text('Rss: 1024 kB\nPss: 900 kB\nSwap: 0 kB\n')
            self.assertEqual(guards._metrics(path, {'Rss', 'Pss', 'Swap'}), {'Rss': 1024, 'Pss': 900, 'Swap': 0})
            with self.assertRaisesRegex(guards.Error, 'required_proc_metric_missing'):
                guards._metrics(path, {'VmSwap'})


if __name__ == '__main__':
    unittest.main()
