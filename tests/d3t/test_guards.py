"""Focused CPU-only parsing, guard and bounded transport tests; no SSH in tests."""
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
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


def snapshot(context=32768, candidate=False, *, full=True):
    state = log_state(context, native=candidate)
    sample = {'schema_version': 2, 'sample_kind': 'full' if full else 'cheap',
            'sample_elapsed_seconds': .04, 'timestamp': time.time(), 'sampled_only': True,
            'status': 'PASS', 'required_context': context,
            'container': {'id': CID, 'image_id': PATCHED if candidate else guards.BASELINE_IMAGE,
                          'pid': 12345, 'started_at': '2026-09-15T00:48:45Z', 'running': True, 'oom_killed': False,
                          'paused': False, 'restarting': False, 'dead': False, 'restart_count': 0},
            'process_start_ticks': 1000, 'process_state': 'S',
            'mounts': guards.MOUNTS.copy(), 'root_available_bytes': 4 * guards.GIB,
            'gpus': [{'index': i, 'uuid': 'GPU-synthetic-%d' % i, 'free_bytes': 16 * guards.GIB,
                      'total_bytes': 96 * guards.GIB} for i in (0, 1)],
            'host_kib': {'MemTotal': 900000000, 'MemAvailable': 400000000, 'SwapTotal': 3000000, 'SwapFree': 2985920},
            'host_swap_used_kib': 14080, 'cgroup_swap_current_bytes': 0,
            'process_kib': {'VmRSS': 420000000, 'VmSwap': 0},
            'vmstat': {'pswpin': 19045, 'pswpout': 35821, 'oom_kill': 0},
            'vmstat_delta': {'pswpin': 0, 'pswpout': 0, 'oom_kill': 0},
            'errors': state['errors'], 'slot_count': state['slot_count'], 'slot_context': state['slot_context'],
            'n_threads': state['n_threads'], 'native': state.get('native'),
            'placement': 'n_cpu_moe_76' if candidate else 'all_cpu'}
    if full:
        sample['process_kib'].update(Rss=420000000, Pss=412000000, Swap=0)
    return sample


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
                         lambda s: s['vmstat_delta'].update(oom_kill=1),
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

    def test_host_only_swap_activity_remains_diagnostic_with_owned_zero_swap(self):
        for full in (False, True):
            for swapin, swapout, used in ((1, 98, 14081), (0, 3072, 26368), (0, 0, 0)):
                previous = snapshot(); previous['timestamp'] -= 1
                sample = snapshot(full=full)
                sample['vmstat']['pswpin'] += swapin
                sample['vmstat']['pswpout'] += swapout
                sample['vmstat_delta'].update(pswpin=swapin, pswpout=swapout)
                sample['host_kib']['SwapFree'] = sample['host_kib']['SwapTotal'] - used
                sample['host_swap_used_kib'] = used
                sample['host_kib']['MemAvailable'] = 64 * guards.GIB // 1024
                expected = copy.deepcopy(sample)
                with self.subTest(full=full, swapin=swapin, swapout=swapout, used=used):
                    self.assertIs(guards.check_snapshot(sample, previous=previous), sample)
                    self.assertEqual(sample, expected)
                    self.assertEqual(sample['process_kib']['VmSwap'], 0)
                    self.assertEqual(sample['cgroup_swap_current_bytes'], 0)

    def test_oom_counter_change_between_individually_successful_collects_stops(self):
        for full in (False, True):
            previous = snapshot(); previous['timestamp'] -= 1
            sample = snapshot(full=full); sample['vmstat']['oom_kill'] += 1
            with self.subTest(full=full), self.assertRaisesRegex(guards.Error, 'counter_changed'):
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

    def test_single_collect_retains_unavailable_stop_and_refuses_nonstop_wrong_identity(self):
        stop = {'status': 'STOP', 'error': 'telemetry_collection_failed'}
        wrong_container = snapshot(candidate=True)
        wrong_container['container']['id'] = 'c' * 64
        wrong_image = snapshot()
        for result in (stop, wrong_container, wrong_image):
            sampler = mock.Mock()
            sampler.next.return_value = result
            with mock.patch.object(guards, 'Sampler', return_value=sampler) as factory:
                if result is stop:
                    self.assertIs(guards.collect(CID, PATCHED, 32768), stop)
                else:
                    with self.assertRaisesRegex(guards.Error, 'snapshot_identity_unavailable_or_changed'):
                        guards.collect(CID, PATCHED, 32768)
            factory.assert_called_once_with(CID, PATCHED, 32768, 0)
            sampler.next.assert_called_once_with(timeout=30)
            sampler.close.assert_called_once_with()

    def test_proc_metric_parser_uses_required_actual_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'smaps_rollup'
            path.write_text('Rss: 1024 kB\nPss: 900 kB\nSwap: 0 kB\n')
            self.assertEqual(guards._metrics(path, {'Rss', 'Pss', 'Swap'}), {'Rss': 1024, 'Pss': 900, 'Swap': 0})
            with self.assertRaisesRegex(guards.Error, 'required_proc_metric_missing'):
                guards._metrics(path, {'VmSwap'})


class CheckpointSchemaTests(unittest.TestCase):
    def test_fresh_cheap_schema_and_checkpoint_only_pss(self):
        cheap = snapshot(full=False)
        guards.check_snapshot(cheap)
        self.assertEqual(set(cheap['process_kib']), {'VmRSS', 'VmSwap'})
        with self.assertRaises(guards.Error):
            guards.check_snapshot(cheap, require_full=True)
        for field in ('Rss', 'Pss', 'Swap'):
            poisoned = copy.deepcopy(cheap)
            poisoned['process_kib'][field] = snapshot()['process_kib'][field]
            with self.subTest(stale=field), self.assertRaises(guards.Error):
                guards.check_snapshot(poisoned)
        guards.check_snapshot(snapshot(), require_full=True)

    def test_missing_and_malformed_fresh_memory_refuse(self):
        for full in (False, True):
            fields = ('VmRSS', 'VmSwap', 'Rss', 'Pss', 'Swap') if full else ('VmRSS', 'VmSwap')
            for field in fields:
                for value in (None, '0', True, -1, 1.25, float('nan')):
                    sample = snapshot(full=full)
                    if value is None:
                        sample['process_kib'].pop(field)
                    else:
                        sample['process_kib'][field] = value
                    with self.subTest(full=full, field=field, value=value), self.assertRaises(guards.Error):
                        guards.check_snapshot(sample)
            sample = snapshot(full=full)
            sample['process_kib']['VmRSS'] = 0
            with self.assertRaises(guards.Error):
                guards.check_snapshot(sample)
        sample = snapshot(); sample['process_kib']['Pss'] = sample['process_kib']['Rss'] + 1
        with self.assertRaises(guards.Error):
            guards.check_snapshot(sample)

    def test_cheap_resource_state_counter_and_native_refusals_remain(self):
        mutations = {
            'host': lambda s: s['host_kib'].update(MemAvailable=0),
            'root': lambda s: s.update(root_available_bytes=4 * guards.GIB - 1),
            'mount': lambda s: s['mounts'].update({'/data': 'wrong'}),
            'gpu': lambda s: s['gpus'][0].update(free_bytes=16 * guards.GIB - 1),
            'target_swap': lambda s: s['process_kib'].update(VmSwap=1),
            'owned_cgroup_swap': lambda s: s.update(cgroup_swap_current_bytes=1),
            'oom': lambda s: s['vmstat_delta'].update(oom_kill=1),
            'process_stopped': lambda s: s.update(process_state='T'),
            'paused': lambda s: s['container'].update(paused=True),
            'restarting': lambda s: s['container'].update(restarting=True),
            'dead': lambda s: s['container'].update(dead=True),
            'native_missing': lambda s: s.update(native=None),
            'native_graph': lambda s: s['native'].update(lid_nodes=20),
            'native_cache': lambda s: s['native']['cache_bytes'].pop('CUDA1'),
        }
        for key in guards.ERROR_PATTERNS:
            mutations['error_' + key] = lambda s, key=key: s['errors'].update({key: 1})
        for name, mutate in mutations.items():
            sample = snapshot(1048576, True, full=False); mutate(sample)
            with self.subTest(name=name), self.assertRaises(guards.Error):
                guards.check_snapshot(sample, native=True)

    def test_identity_changes_refuse_on_cheap_samples(self):
        for mutate in (lambda s: s.update(process_start_ticks=1001),
                       lambda s: s['container'].update(restart_count=1),
                       lambda s: s['gpus'][0].update(uuid='GPU-other'),
                       lambda s: s['container'].update(pid=12346)):
            previous = snapshot(); previous['timestamp'] -= 1
            sample = snapshot(full=False); mutate(sample)
            with self.assertRaises(guards.Error):
                guards.check_snapshot(sample, previous=previous)

    def test_both_modes_require_fresh_zero_process_and_owned_cgroup_swap(self):
        missing = object()
        for full in (False, True):
            for field in ('VmSwap', 'cgroup_swap_current_bytes'):
                for value in (missing, None, True, False, '0', 0.0, 1.0, [], {}, -1, 1, 4096, float('nan')):
                    sample = snapshot(full=full)
                    parent = sample['process_kib'] if field == 'VmSwap' else sample
                    if value is missing:
                        parent.pop(field)
                    else:
                        parent[field] = value
                    with self.subTest(full=full, field=field, value=value), self.assertRaises(guards.Error):
                        guards.check_snapshot(sample)
            sample = snapshot(full=full)
            self.assertIs(guards.check_snapshot(sample), sample)

    def test_host_available_memory_64gib_boundary_is_kib_in_both_modes(self):
        minimum_kib = 67108864
        for full in (False, True):
            for value in (minimum_kib, minimum_kib + 1):
                sample = snapshot(full=full); sample['host_kib']['MemAvailable'] = value
                with self.subTest(full=full, accepts=value):
                    guards.check_snapshot(sample)
            missing = object()
            for value in (missing, None, True, False, '67108864', float(minimum_kib), [], {},
                          -1, 0, minimum_kib - 1, float('nan'), float('inf')):
                sample = snapshot(full=full)
                if value is missing:
                    sample['host_kib'].pop('MemAvailable')
                else:
                    sample['host_kib']['MemAvailable'] = value
                with self.subTest(full=full, refuses=value), self.assertRaises(guards.Error):
                    guards.check_snapshot(sample)

    def test_host_swap_telemetry_remains_required_nonnegative_integer_diagnostics(self):
        missing = object()
        fields = [('host_swap_used_kib', None)] + [(group, key) for group in ('vmstat', 'vmstat_delta')
                                                  for key in ('pswpin', 'pswpout', 'oom_kill')]
        for full in (False, True):
            for group, key in fields:
                for value in (missing, None, True, False, '0', 0.0, [], {}, -1, float('nan')):
                    sample = snapshot(full=full)
                    parent, field = (sample[group], key) if key else (sample, group)
                    if value is missing:
                        parent.pop(field)
                    else:
                        parent[field] = value
                    with self.subTest(full=full, group=group, key=key, value=value), self.assertRaises(guards.Error):
                        guards.check_snapshot(sample)

    def test_host_swap_telemetry_consistency_and_counter_regression_refuse(self):
        for full in (False, True):
            for mutate in (lambda s: s.update(host_swap_used_kib=14081),
                           lambda s: s['host_kib'].update(SwapFree=3000001),
                           lambda s: s['host_kib'].update(MemTotal=s['host_kib']['MemAvailable'] - 1),
                           lambda s: s['vmstat_delta'].update(pswpin=s['vmstat']['pswpin'] + 1)):
                sample = snapshot(full=full); mutate(sample)
                with self.subTest(full=full, mutate=mutate), self.assertRaises(guards.Error):
                    guards.check_snapshot(sample)
            for key in ('pswpin', 'pswpout'):
                previous = snapshot(); previous['timestamp'] -= 1
                sample = snapshot(full=full); sample['vmstat'][key] -= 1
                with self.subTest(full=full, regresses=key), self.assertRaises(guards.Error):
                    guards.check_snapshot(sample, previous=previous)

    def test_checkpoint_gap_is_explicit_and_does_not_widen_cheap_freshness(self):
        previous = snapshot(full=False); previous['timestamp'] -= 5
        full = snapshot()
        guards.check_snapshot(full, previous=previous, require_full=True, checkpoint=True)
        with self.assertRaises(guards.Error):
            guards.check_snapshot(full, previous=previous)
        with self.assertRaises(guards.Error):
            guards.check_snapshot(snapshot(full=False), previous=previous, checkpoint=True)
        for full, elapsed in ((False, 2.001), (True, 30.001), (False, -1), (True, float('nan'))):
            sample = snapshot(full=full); sample['sample_elapsed_seconds'] = elapsed
            with self.subTest(full=full, elapsed=elapsed), self.assertRaises(guards.Error):
                guards.check_snapshot(sample, checkpoint=full)

    def test_remote_sampler_transitions_full_cheap_terminal_full_without_redispatch(self):
        modes, waits = [], []
        clock = [0.0]
        output = io.StringIO()
        command = io.StringIO('full\n')
        def observe(container, image, context, state, full=True):
            modes.append(full)
            return snapshot(context, True, full=full)
        def select(read, write, errors, timeout):
            clock[0] += timeout
            waits.append(timeout)
            return ([command], [], []) if len(waits) == 4 else ([], [], [])
        with mock.patch.object(guards, '_local_snapshot', side_effect=observe), \
                mock.patch.object(guards.select, 'select', side_effect=select), \
                mock.patch.object(guards.time, 'monotonic', side_effect=lambda: clock[0]), \
                mock.patch.object(guards.sys, 'stdin', command), contextlib.redirect_stdout(output):
            guards._remote_main(CID, PATCHED, 32768, 60)
        self.assertEqual(modes, [True, False, False, False, True])
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r['sample_kind'] for r in rows], ['full', 'cheap', 'cheap', 'cheap', 'full'])
        self.assertTrue(all(row['status'] == 'PASS' for row in rows))
        self.assertTrue(all('Pss' not in row['process_kib'] for row in rows[1:-1]))

    def test_terminal_checkpoint_command_is_once_only_and_eof_or_cap_never_invents_full(self):
        sampler = guards.Sampler.__new__(guards.Sampler)
        sampler.process = mock.Mock(stdin=io.StringIO())
        sampler.full_requested = False
        sampler.request_full_checkpoint()
        self.assertEqual(sampler.process.stdin.getvalue(), 'full\n')
        with self.assertRaises(guards.Error): sampler.request_full_checkpoint()
        self.assertEqual(sampler.process.stdin.getvalue(), 'full\n')
        for mode in ('eof', 'cap', 'single'):
            clock, observed, output = [0.0], [], io.StringIO()
            command = io.StringIO('')
            def observe(container, image, context, state, full=True):
                observed.append(full)
                return snapshot(context, True, full=full)
            def select(read, write, errors, timeout):
                clock[0] += timeout
                return ([command], [], []) if mode == 'eof' else ([], [], [])
            with self.subTest(mode=mode), mock.patch.object(guards, '_local_snapshot', side_effect=observe), \
                    mock.patch.object(guards.select, 'select', side_effect=select), \
                    mock.patch.object(guards.time, 'monotonic', side_effect=lambda: clock[0]), \
                    mock.patch.object(guards.sys, 'stdin', command), contextlib.redirect_stdout(output):
                guards._remote_main(CID, PATCHED, 32768, 0 if mode == 'single' else 1)
            self.assertEqual(observed, [True])
            self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_proc_parser_refuses_duplicates_bad_units_nonintegers_and_missing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status'
            for raw in ('VmRSS: 1024 kB\n', 'VmRSS: 1024 MB\nVmSwap: 0 kB\n',
                        'VmRSS: 1024 kB extra\nVmSwap: 0 kB\n', 'VmRSS: x kB\nVmSwap: 0 kB\n',
                        'VmRSS: -1 kB\nVmSwap: 0 kB\n', 'VmRSS: 1.5 kB\nVmSwap: 0 kB\n',
                        'VmRSS: 1024 kB\nVmRSS: 2048 kB\nVmSwap: 0 kB\n'):
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(guards.Error):
                    guards._metrics(path, {'VmRSS', 'VmSwap'})


class OwnedCgroupPathTests(unittest.TestCase):
    """Only the exact owned Docker PID may select a unified nonroot cgroup."""
    def test_actual_shape_systemd_and_cgroupfs_paths_accept_exact_full_container_id(self):
        for path in ('/system.slice/docker-' + CID + '.scope', '/docker/' + CID):
            with self.subTest(path=path), mock.patch.object(Path, 'read_bytes', autospec=True,
                                                         return_value=('0::' + path + '\n').encode()) as read:
                self.assertEqual(guards._owned_cgroup_path(12345, CID), path)
                self.assertEqual(str(read.call_args.args[0]), '/proc/12345/cgroup')
                read.assert_called_once()

    def test_missing_malformed_escaped_root_or_unowned_paths_refuse(self):
        owned = '/system.slice/docker-' + CID + '.scope'
        other = 'b' * 64
        paths = ('', '/', '.', '..', owned[1:], '/sys/fs/cgroup' + owned,
                 owned + '/', owned + '/child', '/system.slice//docker-' + CID + '.scope',
                 '/system.slice/../system.slice/docker-' + CID + '.scope',
                 '/system.slice/./docker-' + CID + '.scope',
                 '/system.slice/docker-' + other + '.scope',
                 '/docker/' + other, '/user.slice/docker-' + CID + '.scope',
                 '/system.slice/docker-' + CID[:12] + '.scope',
                 '/system.slice/docker-' + CID.upper() + '.scope',
                 '/docker/' + CID + '/../../', '/docker/' + CID + '\x00')
        raw_values = [b'', b'\xff', b'0::\n', b'0::/\n', b'\n',
                      ('1:memory:' + owned + '\n').encode(),
                      ('0:memory:' + owned + '\n').encode(),
                      ('0::' + owned + '\n0::' + owned + '\n').encode(),
                      ('0::' + owned + '\n1:memory:' + owned + '\n').encode(),
                      ('0::' + owned + ' trailing\n').encode(), b'0::/' + b'x' * 131073]
        raw_values.extend(('0::' + path + '\n').encode() for path in paths)
        for raw in raw_values:
            with self.subTest(raw=raw[:140]), mock.patch.object(Path, 'read_bytes', return_value=raw), \
                    self.assertRaises(guards.Error):
                guards._owned_cgroup_path(12345, CID)
        with mock.patch.object(Path, 'read_bytes', side_effect=FileNotFoundError), self.assertRaises(guards.Error):
            guards._owned_cgroup_path(12345, CID)

    def test_invalid_pid_and_container_identity_cannot_select_a_path(self):
        raw = ('0::/system.slice/docker-' + CID + '.scope\n').encode()
        for pid in (None, True, False, '12345', 12345.0, 0, -1, [], {}):
            with self.subTest(pid=pid), mock.patch.object(Path, 'read_bytes', return_value=raw), \
                    self.assertRaises(guards.Error):
                guards._owned_cgroup_path(pid, CID)
        for container_id in (None, True, '', CID[:12], CID.upper(), 'b' * 64,
                             CID + '/..', '/docker/' + CID, [], {}):
            with self.subTest(container_id=container_id), mock.patch.object(Path, 'read_bytes', return_value=raw), \
                    self.assertRaises(guards.Error):
                guards._owned_cgroup_path(12345, container_id)


class OwnedCgroupReadTests(unittest.TestCase):
    """Exercise real anchored open/read logic using a temporary synthetic tree."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = '/system.slice/docker-' + CID + '.scope'
        self.leaf = self.root / 'sys/fs/cgroup' / self.path.lstrip('/')
        self.leaf.mkdir(parents=True)
        (self.leaf / 'cgroup.procs').write_bytes(b'12345\n12346\n')
        (self.leaf / 'memory.swap.current').write_bytes(b'0\n')
        self.mountinfo = b'38 29 0:33 / /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime - cgroup2 cgroup rw\n'
        self.mnt_id = 38
        self.metadata_changes = {}
        self.fd_mount_ids = {}
        self.before_open = None

    def collect(self, helper=None):
        real_open, real_fstat = os.open, os.fstat
        descriptors = {}
        def opened(path, flags, *, dir_fd=None):
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertTrue(flags & os.O_CLOEXEC)
            if path == '/':
                self.assertIsNone(dir_fd)
                actual, logical = str(self.root), '/'
            else:
                self.assertIn(dir_fd, descriptors)
                self.assertNotIn('/', path)
                actual = path
                logical = descriptors[dir_fd].rstrip('/') + '/' + path
            if self.before_open is not None:
                self.before_open(logical)
            fd = real_open(actual, flags, dir_fd=dir_fd)
            descriptors[fd] = logical
            return fd
        def metadata(fd):
            actual = real_fstat(fd)
            result = dict(st_uid=0, st_mode=actual.st_mode, st_dev=actual.st_dev, st_ino=actual.st_ino)
            result.update(self.metadata_changes.get(descriptors[fd], {}))
            return SimpleNamespace(**result)
        def proc(path):
            name = str(path)
            if name == '/proc/12345/cgroup':
                return ('0::' + self.path + '\n').encode()
            if name == '/proc/self/mountinfo':
                return self.mountinfo
            if name.startswith('/proc/self/fdinfo/'):
                fd = int(name.rsplit('/', 1)[1])
                return ('mnt_id:\t%d\n' % self.fd_mount_ids.get(descriptors[fd], self.mnt_id)).encode()
            raise AssertionError('unexpected synthetic proc read ' + name)
        with mock.patch.object(guards.os, 'open', side_effect=opened), \
                mock.patch.object(guards.os, 'fstat', side_effect=metadata), \
                mock.patch.object(Path, 'read_bytes', autospec=True, side_effect=proc):
            return (helper or guards._cgroup_swap)(12345, CID)

    def test_actual_shape_anchored_owned_cgroup_reads_bytes_and_stable_identity(self):
        for raw, expected in ((b'0\n', 0), (b'0', 0), (b'4096\n', 4096)):
            (self.leaf / 'memory.swap.current').write_bytes(raw)
            value, identity = self.collect()
            self.assertEqual(value, expected)
            self.assertEqual(identity, (self.path, 38,
                                       ((self.root / 'sys/fs/cgroup').stat().st_dev,
                                        (self.root / 'sys/fs/cgroup').stat().st_ino),
                                       (self.leaf.stat().st_dev, self.leaf.stat().st_ino)))
            sample = snapshot(); sample['cgroup_swap_current_bytes'] = value
            if expected:
                with self.assertRaises(guards.Error): guards.check_snapshot(sample)
            else:
                guards.check_snapshot(sample)

    def test_cgroupfs_actual_shape_accepts_under_same_protected_v2_root(self):
        self.path = '/docker/' + CID
        self.leaf = self.root / 'sys/fs/cgroup' / self.path.lstrip('/')
        self.leaf.mkdir(parents=True)
        (self.leaf / 'cgroup.procs').write_bytes(b'12345\n')
        (self.leaf / 'memory.swap.current').write_bytes(b'0\n')
        value, identity = self.collect()
        self.assertEqual(value, 0)
        self.assertEqual(identity[0], self.path)

    def test_shipped_payload_executes_owned_cgroup_dependency_closure_without_dispatch(self):
        source = guards._source(CID, PATCHED, 1048576, 600)
        definitions, invocation = source.rsplit('\n_remote_main(', 1)
        self.assertTrue(invocation.startswith(repr(CID)))
        namespace = {}
        exec(compile(definitions, '<synthetic-d3swap-payload>', 'exec'), namespace)
        self.assertEqual(self.collect(helper=namespace['_cgroup_swap']), self.collect())

    def test_missing_malformed_and_oversized_current_never_become_zero(self):
        for raw in (b'', b'\n', b'-1\n', b'0.0\n', b'false\n', b'null\n', b'0 0\n',
                    b'0\n0\n', b'0 kB\n', b' 0\n', b'0\r\n', b'\xff', b'0' * 65537):
            (self.leaf / 'memory.swap.current').write_bytes(raw)
            with self.subTest(raw=raw[:100]), self.assertRaises(guards.Error):
                self.collect()
        (self.leaf / 'memory.swap.current').unlink()
        with self.assertRaises(guards.Error): self.collect()

    def test_only_whole_root_cgroup2_mount_and_exact_fd_mount_identity_accept(self):
        actual = self.mountinfo
        for raw in (b'', b'bad\n', actual + actual, actual.replace(b' - cgroup2 ', b' - cgroup '),
                    actual.replace(b' / /sys/fs/cgroup ', b' /docker /sys/fs/cgroup '),
                    actual.replace(b'38 ', b'x ', 1), actual.replace(b' /sys/fs/cgroup ', b' /sys/fs/other '),
                    actual.replace(b' - ', b' : '), b'x' * 131073, b'\xff'):
            self.mountinfo = raw
            with self.subTest(raw=raw[:100]), self.assertRaises(guards.Error): self.collect()
        self.mountinfo = actual
        for path in ('/sys/fs/cgroup', '/sys/fs/cgroup/system.slice',
                     '/sys/fs/cgroup' + self.path, '/sys/fs/cgroup' + self.path + '/memory.swap.current'):
            self.fd_mount_ids = {path: 39}
            with self.subTest(fd_path=path), self.assertRaises(guards.Error): self.collect()

    def test_unprotected_ancestry_or_file_identity_refuses(self):
        paths = ('/', '/sys', '/sys/fs', '/sys/fs/cgroup', '/sys/fs/cgroup/system.slice',
                 '/sys/fs/cgroup' + self.path,
                 '/sys/fs/cgroup' + self.path + '/memory.swap.current',
                 '/sys/fs/cgroup' + self.path + '/cgroup.procs')
        for path in paths:
            for change in ({'st_uid': 1000}, {'st_mode': 0o40777}):
                self.metadata_changes = {path: change}
                with self.subTest(path=path, change=change), self.assertRaises(guards.Error): self.collect()
        self.metadata_changes = {'/sys/fs/cgroup' + self.path + '/memory.swap.current': {'st_dev': -1}}
        with self.assertRaises(guards.Error): self.collect()

    def test_missing_invalid_or_changed_owned_pid_membership_refuses(self):
        for raw in (b'', b'1\n', b'123450\n', b'12345', b'012345\n', b'12345\ninvalid\n', b'12345 1\n'):
            (self.leaf / 'cgroup.procs').write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(guards.Error): self.collect()
        (self.leaf / 'cgroup.procs').write_bytes(b'12345\n')
        calls = [0]
        def move_after_counter(path):
            if path.endswith('/cgroup.procs'):
                calls[0] += 1
                if calls[0] == 2:
                    (self.leaf / 'cgroup.procs').write_bytes(b'12346\n')
        self.before_open = move_after_counter
        with self.assertRaises(guards.Error): self.collect()
        self.assertEqual(calls[0], 2)

    def test_symlink_metric_or_ancestor_cannot_escape_anchored_root(self):
        outside = self.root / 'unrelated-zero'
        outside.write_bytes(b'0\n')
        metric = self.leaf / 'memory.swap.current'
        metric.unlink(); metric.symlink_to(outside)
        with self.assertRaises(guards.Error): self.collect()
        metric.unlink(); metric.write_bytes(b'0\n')
        ancestor = self.root / 'sys/fs/cgroup/system.slice'
        moved = ancestor.with_name('unrelated.slice')
        ancestor.rename(moved); ancestor.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(guards.Error): self.collect()

    def test_replaced_cgroup_inode_during_sample_cannot_accept_old_open_directory(self):
        calls = [0]
        def replace_after_counter(path):
            if path.endswith('/cgroup.procs'):
                calls[0] += 1
                if calls[0] == 2:
                    self.leaf.rename(self.leaf.with_name('unrelated-old-group'))
                    self.leaf.mkdir()
        self.before_open = replace_after_counter
        with self.assertRaisesRegex(guards.Error, 'owned_cgroup_changed'): self.collect()
        self.assertEqual(calls[0], 2)


class CollectorTests(unittest.TestCase):
    """Run real collection/parsing logic against explicit synthetic proc/CLI IO."""
    def setUp(self):
        self.reads = []
        self.status_reads = 0
        self.rollup_reads = 0
        self.start_ticks = 1000
        self.proc_state = 'S'
        self.uuid = guards.MOUNTS['/data']
        self.filesystem = 'ext4'
        self.kernel = ''
        self.cgroup_swap = 0
        self.cgroup_identity = ('/system.slice/docker-' + CID + '.scope', 38, (10, 20), (10, 21))
        self.host_swap_free = 2985920
        self.swapin = 19045
        self.swapout = 35821
        self.oom_kill = 0
        self.log_path = '/data/docker/containers/' + CID + '/synthetic-json.log'
        lines = ['llama threadpool init, n_threads = 112',
                 'initializing, n_slots = 1, n_ctx_slot = 32768', *diagnostic(32768)]
        self.logs = b''.join(json.dumps({'log': line}).encode() + b'\n' for line in lines)
        self.container = {'Id': CID, 'Image': PATCHED, 'Args': arguments(32768, True),
                          'LogPath': self.log_path, 'RestartCount': 0,
                          'State': {'Pid': 12345, 'StartedAt': '2026-09-15T00:48:45Z',
                                    'Running': True, 'OOMKilled': False, 'Paused': False,
                                    'Restarting': False, 'Dead': False},
                          'NetworkSettings': {'Ports': {'30002/tcp': [
                              {'HostIp': '127.0.0.1', 'HostPort': '30002'}]}}}
        self.state = {'log_lines': 0, 'errors': {key: 0 for key in guards.ERROR_PATTERNS},
                      'log_hash': hashlib.sha256()}
        owner = self
        class VirtualPath:
            def __init__(self, path): self.path = str(path)
            def __str__(self): return self.path
            def stat(self):
                owner.assertEqual(self.path, owner.log_path)
                return SimpleNamespace(st_dev=1, st_ino=2, st_size=len(owner.logs))
            def open(self, mode):
                owner.assertEqual((self.path, mode), (owner.log_path, 'rb'))
                return io.BytesIO(owner.logs)
            def read_bytes(self): return owner.proc_bytes(self.path)
            def read_text(self, *args, **kwargs): return self.read_bytes().decode()
        for patcher in (mock.patch.object(guards, 'Path', VirtualPath),
                        mock.patch.object(guards, '_run', side_effect=self.command),
                        mock.patch.object(guards, '_cgroup_swap', side_effect=self.owned_cgroup, create=True),
                        mock.patch.object(guards.os, 'statvfs', return_value=SimpleNamespace(
                            f_bavail=8 * guards.GIB // 4096, f_frsize=4096))):
            patcher.start(); self.addCleanup(patcher.stop)

    def proc_bytes(self, path):
        self.reads.append(path)
        if path == '/proc/12345/stat':
            return ('12345 (llama ) server) ' + self.proc_state + ' ' + '0 ' * 18
                    + str(self.start_ticks) + ' ' + '0 ' * 30).encode()
        if path == '/proc/12345/status':
            self.status_reads += 1
            return ('Name:\tllama-server\nVmRSS: %d kB\nVmSwap: 0 kB\n'
                    % (420000000 + self.status_reads)).encode()
        if path == '/proc/12345/cgroup':
            return ('0::' + self.cgroup_identity[0] + '\n').encode()
        if path == '/proc/12345/smaps_rollup':
            self.rollup_reads += 1
            return ('Rss: 420000000 kB\nPss: %d kB\nSwap: 0 kB\n'
                    % (412000000 + self.rollup_reads)).encode()
        if path == '/proc/meminfo':
            return ('MemTotal: 900000000 kB\nMemAvailable: 400000000 kB\nSwapTotal: 3000000 kB\nSwapFree: %d kB\n'
                    % self.host_swap_free).encode()
        if path == '/proc/vmstat':
            return ('pswpin %d\npswpout %d\noom_kill %d\n' % (self.swapin, self.swapout, self.oom_kill)).encode()
        raise AssertionError('unanticipated synthetic proc path ' + path)

    def owned_cgroup(self, pid, container_id):
        self.assertEqual((pid, container_id), (12345, CID))
        return self.cgroup_swap, self.cgroup_identity

    def command(self, argv, limit=65536):
        if argv[0] == 'docker':
            return json.dumps(self.container if '--format' in argv else [self.container])
        if argv[0] == 'findmnt':
            target = argv[-1]
            uuid = self.uuid if target == '/data' else guards.MOUNTS[target]
            return json.dumps({'filesystems': [{'target': target, 'uuid': uuid, 'fstype': self.filesystem}]})
        if argv[0] == 'dmesg': return self.kernel
        if argv[0] == 'nvidia-smi':
            return '0, GPU-synthetic-0, 98304, 24576\n1, GPU-synthetic-1, 98304, 24576\n'
        raise AssertionError('unanticipated synthetic command ' + repr(argv))

    def collect(self, full):
        sample = guards._local_snapshot(CID, PATCHED, 32768, self.state, full=full)
        guards.validate_snapshot(sample)
        return sample

    def test_admission_pre_post_read_pss_repeated_inflight_reads_never_do(self):
        admission = self.collect(True)
        pre = self.collect(True)
        read_boundary = len(self.reads)
        cheap = [self.collect(False) for _ in range(4)]
        inflight_reads = self.reads[read_boundary:]
        self.assertNotIn('/proc/12345/smaps_rollup', inflight_reads)
        self.assertEqual(inflight_reads.count('/proc/12345/status'), 4)
        post = self.collect(True)
        self.assertEqual(self.rollup_reads, 3)
        self.assertEqual([s['process_kib']['Pss'] for s in (admission, pre, post)],
                         [412000001, 412000002, 412000003])
        self.assertEqual([s['process_kib']['VmRSS'] for s in cheap],
                         [420000003, 420000004, 420000005, 420000006])
        for sample in cheap:
            self.assertEqual(sample['sample_kind'], 'cheap')
            self.assertEqual(set(sample['process_kib']), {'VmRSS', 'VmSwap'})
            self.assertEqual(sample['native'], admission['native'])
            self.assertEqual(sample['cgroup_swap_current_bytes'], 0)

    def test_collector_preserves_fresh_host_swap_counters_usage_and_deltas(self):
        first = self.collect(True)
        self.swapin += 1
        self.swapout += 98
        self.host_swap_free -= 392
        cheap = self.collect(False)
        self.assertEqual(cheap['vmstat'], {'pswpin': 19046, 'pswpout': 35919, 'oom_kill': 0})
        self.assertEqual(cheap['vmstat_delta'], {'pswpin': 1, 'pswpout': 98, 'oom_kill': 0})
        self.assertEqual(cheap['host_swap_used_kib'], first['host_swap_used_kib'] + 392)
        self.assertEqual(cheap['process_kib']['VmSwap'], 0)
        self.assertEqual(cheap['cgroup_swap_current_bytes'], 0)
        self.assertEqual(self.rollup_reads, 1)

    def test_new_owned_cgroup_swap_refuses_in_both_modes(self):
        self.collect(True)
        self.cgroup_swap = 4096
        for full in (False, True):
            with self.subTest(full=full), self.assertRaises(guards.Error):
                self.collect(full)
        self.assertEqual(self.rollup_reads, 1)
        self.assertEqual(self.status_reads, 1)

    def test_final_cgroup_read_retains_actual_nonzero_and_refuses_in_both_modes(self):
        for full in (False, True):
            with self.subTest(full=full), mock.patch.object(guards, '_cgroup_swap', side_effect=[
                    (0, self.cgroup_identity), (4096, self.cgroup_identity)]) as reads:
                sample = guards._local_snapshot(CID, PATCHED, 32768, self.state, full=full)
                self.assertEqual(reads.call_count, 2)
                self.assertEqual(sample['cgroup_swap_current_bytes'], 4096)
                with self.assertRaisesRegex(guards.Error, 'owned_cgroup_swap_in_use'):
                    guards.validate_snapshot(sample)

    def test_same_path_leaf_or_mount_replacement_during_whole_sample_refuses(self):
        original = self.cgroup_identity
        changed = ((original[0], 39, original[2], original[3]),
                   (original[0], 38, (10, 200), original[3]),
                   (original[0], 38, original[2], (10, 210)))
        for full in (False, True):
            for identity in changed:
                with self.subTest(full=full, identity=identity), mock.patch.object(guards, '_cgroup_swap',
                        side_effect=[(0, original), (0, identity)]) as reads, \
                        self.assertRaisesRegex(guards.Error, 'owned_cgroup_changed'):
                    self.collect(full)
                self.assertEqual(reads.call_count, 2)

    def test_owned_cgroup_identity_change_between_samples_refuses(self):
        self.collect(True)
        self.cgroup_identity = (*self.cgroup_identity[:3], (10, 22))
        with self.assertRaises(guards.Error):
            self.collect(False)

    def test_owned_cgroup_path_change_during_sample_refuses(self):
        for full in (False, True):
            with self.subTest(full=full), mock.patch.object(guards, '_owned_cgroup_path',
                    return_value='/docker/' + CID), self.assertRaises(guards.Error):
                self.collect(full)

    def test_pid_reuse_during_sampling_refuses_even_with_unchanged_container_pid(self):
        for full in (False, True):
            with self.subTest(full=full), mock.patch.object(guards, '_process_identity',
                    side_effect=[(1000, 'S'), (1001, 'S')]), self.assertRaises(guards.Error):
                self.collect(full)

    def test_inspected_container_pid_or_identity_change_during_sample_refuses(self):
        for field, value in (('Id', 'b' * 64), ('Image', guards.BASELINE_IMAGE),
                             ('Pid', 12346), ('StartedAt', '2026-09-15T03:00:00Z'), ('RestartCount', 1)):
            inspected = [0]
            def command(argv, limit=65536):
                if argv[0] != 'docker':
                    return self.command(argv, limit)
                inspected[0] += 1
                container = copy.deepcopy(self.container)
                if inspected[0] > 1:
                    target = container['State'] if field in ('Pid', 'StartedAt') else container
                    target[field] = value
                return json.dumps([container])
            with self.subTest(field=field), mock.patch.object(guards, '_run', side_effect=command), \
                    self.assertRaises(guards.Error):
                self.collect(False)
            self.assertEqual(inspected[0], 2)

    def test_cheap_keeps_exact_mount_process_and_incremental_native_log_refusals(self):
        self.collect(True)
        self.start_ticks += 1
        with self.assertRaises(guards.Error): self.collect(False)
        self.start_ticks -= 1
        self.uuid = 'wrong-uuid'
        with self.assertRaises(guards.Error): self.collect(False)
        self.uuid = guards.MOUNTS['/data']; self.filesystem = 'xfs'
        with self.assertRaises(guards.Error): self.collect(False)
        self.filesystem = 'ext4'
        self.logs += json.dumps({'log': next(diagnostic(32768))}).encode() + b'\n'
        with self.assertRaises(guards.Error): self.collect(False)
        self.assertEqual(self.rollup_reads, 1)

if __name__ == '__main__':
    unittest.main()
