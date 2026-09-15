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
            'host_swap_used_kib': 14080, 'process_kib': {'VmRSS': 420000000, 'VmSwap': 0},
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
            'swapin': lambda s: s['vmstat_delta'].update(pswpin=1),
            'swapout': lambda s: s['vmstat_delta'].update(pswpout=1),
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

    def test_identity_and_absolute_host_swap_changes_refuse_on_cheap_samples(self):
        for mutate in (lambda s: s.update(process_start_ticks=1001),
                       lambda s: s['container'].update(restart_count=1),
                       lambda s: s['gpus'][0].update(uuid='GPU-other'),
                       lambda s: s['container'].update(pid=12346),
                       lambda s: s.update(host_swap_used_kib=14081)):
            previous = snapshot(); previous['timestamp'] -= 1
            sample = snapshot(full=False); mutate(sample)
            with self.assertRaises(guards.Error):
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
        if path == '/proc/12345/smaps_rollup':
            self.rollup_reads += 1
            return ('Rss: 420000000 kB\nPss: %d kB\nSwap: 0 kB\n'
                    % (412000000 + self.rollup_reads)).encode()
        if path == '/proc/meminfo':
            return b'MemTotal: 900000000 kB\nMemAvailable: 400000000 kB\nSwapTotal: 3000000 kB\nSwapFree: 2985920 kB\n'
        if path == '/proc/vmstat':
            return b'pswpin 19045\npswpout 35821\noom_kill 0\n'
        raise AssertionError('unanticipated synthetic proc path ' + path)

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
