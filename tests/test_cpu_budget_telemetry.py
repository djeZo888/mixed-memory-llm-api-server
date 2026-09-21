"""Offline counter fixtures only; no host/model/network/profiler access."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_telemetry as cpu
from benchmark import decode_telemetry as primitive


def stat(pid=44, *, generation=900, user=100, system=10):
    values = ['0'] * 50
    values[0] = 'S'
    values[primitive.STAT_FIELDS['starttime_ticks']] = str(generation)
    values[primitive.STAT_FIELDS['utime_ticks']] = str(user)
    values[primitive.STAT_FIELDS['stime_ticks']] = str(system)
    values[17] = '113'
    return str(pid) + ' (private ) worker) ' + ' '.join(values)


def sample(t, *, scale=1, generation=900, identity=(1, 2)):
    value = int(t * scale * 100)
    psi = {kind: {scope: {'total_usec': int(t * 100000)} for scope in ('some', 'full')}
           for kind in ('cpu', 'memory', 'io')}
    counters = {key: 0 for key in primitive.CPU_FIELDS}
    counters.update(user=value, idle=int(t * 100), steal=int(t * 10), guest=value)
    return {'sample_kind': 'cpu_budget', 'timestamp_monotonic_s': t + 1000,
        'collection_finished_monotonic_s': t + 1000.1, 'collection_duration_s': .1,
        'client_observed_monotonic_s': t, 'clock_ticks_per_second': 100,
        'guest_cpus': {'cpu': counters, 'cpu0': counters}, 'guest_psi': psi,
        'cgroups': {'glm': {'identity': list(identity), 'usage_usec': int(t * scale * 1000000),
            'nr_periods': int(t * 10), 'nr_throttled': int(t), 'throttled_usec': int(t * 1000),
            'quota_usec': 'max', 'period_usec': 100000, 'psi': psi}},
        'processes': {'glm': [{'pid': 44, 'starttime_ticks': generation, 'generation_stable': True,
                              'utime_ticks': value, 'stime_ticks': 0}]}}


class CpuBudgetTelemetryTests(unittest.TestCase):
    def test_collector_all_112_vcpus_and_process_totals_without_thread_or_maps_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'stat').write_text('cpu 100 2 50 900 7 8 9 30 10 1\n' +
                ''.join(f'cpu{i} 1 2 3 4 5 6 7 8 9 10\n' for i in range(112)))
            proc = root / '44'
            proc.mkdir()
            (proc / 'stat').write_text(stat())
            group = root / 'group'
            group.mkdir()
            (group / 'cpu.stat').write_text('usage_usec 900\nuser_usec 800\nsystem_usec 100\n'
                'nr_periods 20\nnr_throttled 1\nthrottled_usec 5\n')
            (group / 'cpu.max').write_text('800000 100000\n')
            (root / 'pressure').mkdir()
            for kind in ('cpu', 'memory', 'io'):
                text = 'some avg10=1.00 avg60=0.10 avg300=0.02 total=500\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n'
                (root / 'pressure' / kind).write_text(text)
                (group / (kind + '.pressure')).write_text(text)
            ticks = iter([1.0, 1.125])
            with mock.patch.object(primitive, '_read', wraps=primitive._read) as read, \
                    mock.patch.object(primitive.os, 'scandir', side_effect=AssertionError('no thread scanning')):
                row = cpu.collect_sample({'glm': group}, pids={'glm': [44]}, proc_root=root,
                                         clock=lambda: next(ticks))
            self.assertEqual(row['observed_vcpu_count'], 112)
            self.assertEqual(row['guest_cpus']['cpu111']['steal'], 8)
            self.assertEqual(row['cgroups']['glm']['quota_usec'], 800000)
            self.assertEqual(row['processes']['glm'][0]['utime_ticks'], 100)
            self.assertEqual(row['processes']['glm'][0]['status'], 'AVAILABLE')
            self.assertEqual(row['processes']['glm'][0]['num_threads'], 113)
            self.assertEqual(row['processes']['glm'][0]['runtime_thread_count_status'], 'AVAILABLE')
            self.assertEqual(row['guest_psi']['cpu']['some']['total_usec'], 500)
            self.assertEqual(row['guest_psi']['cpu']['full']['status'], 'UNAVAILABLE')
            self.assertIsNone(row['guest_psi']['cpu']['full']['total_usec'])
            self.assertEqual(row['guest_psi']['cpu']['full']['raw_compatibility_counters']['total_usec'], 0)
            self.assertEqual(row['collection_duration_s'], .125)
            self.assertEqual(row['missing_reads'], [])
            names = {call.args[0].name for call in read.call_args_list}
            self.assertFalse(names & {'smaps', 'smaps_rollup', 'maps', 'numa_maps', 'environ', 'schedstat', 'status'})
            self.assertNotIn('private', json.dumps(row))
            self.assertEqual(row['scheduler_wait']['status'], 'UNAVAILABLE')

    def test_missing_pressure_and_counters_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            row = cpu.collect_sample({'glm': Path(directory) / 'absent'}, pids={'glm': [44]}, proc_root=Path(directory))
        self.assertIsNone(row['cgroups']['glm']['usage_usec'])
        self.assertIsNone(row['processes']['glm'][0]['utime_ticks'])
        self.assertEqual(row['processes']['glm'][0]['status'], 'UNAVAILABLE')
        self.assertEqual(row['guest_psi']['cpu']['some']['status'], 'UNAVAILABLE')
        self.assertIsNone(row['guest_psi']['cpu']['some']['total_usec'])

    def test_closed_inventory_validation(self):
        for groups, pids in (({}, {}), ({'g': Path('.')}, {'q': [44]}),
                             ({'g': Path('.')}, {'g': [True]}),
                             ({'g': Path('.'), 'q': Path('.')}, {'g': [44], 'q': [44]})):
            with self.assertRaises(ValueError):
                cpu.collect_sample(groups, pids=pids)

    def test_numa_only_outside_timing_and_reused_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '44').mkdir()
            (root / '44/stat').write_text(stat())
            (root / '44/numa_maps').write_text('1234 default file=/private/model N0=30 N1=10\n')
            with mock.patch.object(primitive, '_read', wraps=primitive._read) as read:
                row = cpu.numa_snapshot({'glm': [44]}, proc_root=root)
            self.assertTrue(row['outside_timed_sampling_required'])
            self.assertEqual(row['processes']['glm'][0]['numa']['node_pages'], {'0': 30, '1': 10})
            self.assertNotIn('private', json.dumps(row))
            self.assertEqual({call.args[0].name for call in read.call_args_list}, {'stat', 'numa_maps'})

    def test_weighted_cpu_process_cgroup_steal_psi_without_double_guest_count(self):
        rows = [sample(t) for t in (0, 1, 2, 3)]
        result = cpu.summarize_phase(rows, 0, 3, phase='request')
        self.assertEqual(result['status'], 'AVAILABLE')
        for group in ('cgroups', 'process_group_totals'):
            self.assertAlmostEqual(result[group]['glm']['cpu_time_s'], 3)
            self.assertAlmostEqual(result[group]['glm']['average_core_equivalents'], 1)
            self.assertAlmostEqual(result[group]['glm']['p95_interval_core_equivalents'], 1)
        self.assertAlmostEqual(result['processes']['glm:44']['cpu_time_s'], 3)
        self.assertAlmostEqual(result['guest_cpus']['cpu0']['cpu_time_s'], 3)
        self.assertAlmostEqual(sum(result['guest_cpus']['cpu']['steal_time_s']), .3)
        self.assertAlmostEqual(result['psi']['guest:cpu:some']['average_stall_fraction'], .1)
        self.assertAlmostEqual(result['collection_overhead']['total_s'], .4)
        self.assertEqual(result['sampling_precision']['process_cpu_tick_seconds'], [.01])
        self.assertIn('short decode', result['p95_caveat'])

    def test_nonuniform_intervals_weight_p95_and_average(self):
        rows = [sample(0), sample(1), sample(11)]
        rows[1]['cgroups']['glm']['usage_usec'] = 10000000
        rows[2]['cgroups']['glm']['usage_usec'] = 20000000
        result = cpu.summarize_phase(rows, 0, 11, phase='decode_proxy')['cgroups']['glm']
        self.assertAlmostEqual(result['average_core_equivalents'], 20/11)
        self.assertAlmostEqual(result['p95_interval_core_equivalents'], 10)
        self.assertEqual(result['interval_count'], 2)

    def test_identity_changes_regressions_and_partial_counters_unavailable(self):
        cases = []
        reused = sample(1, generation=901, identity=(1, 3))
        cases.append(reused)
        regressed = sample(1)
        regressed['cgroups']['glm']['usage_usec'] = -1
        regressed['processes']['glm'][0]['utime_ticks'] = -1
        cases.append(regressed)
        missing = sample(1)
        missing['cgroups']['glm']['usage_usec'] = None
        missing['processes']['glm'][0]['utime_ticks'] = None
        cases.append(missing)
        for right in cases:
            with self.subTest(right=right):
                result = cpu.summarize_phase([sample(0), right], 0, 1, phase='request')
                self.assertEqual(result['cgroups']['glm']['status'], 'UNAVAILABLE')
                self.assertIsNone(result['cgroups']['glm']['average_core_equivalents'])
                self.assertEqual(result['process_group_totals']['glm']['status'], 'UNAVAILABLE')
        rows = [sample(0), sample(1), sample(2)]
        rows[-1]['processes']['glm'][0]['utime_ticks'] = None
        result = cpu.summarize_phase(rows, 0, 2, phase='request')
        self.assertEqual(result['process_group_totals']['glm']['status'], 'PARTIAL')
        self.assertEqual(result['process_group_totals']['glm']['unavailable_interval_count'], 1)

    def test_phase_no_partial_prorating_or_cross_host_clock_subtraction(self):
        rows = [sample(t) for t in (0, 1, 2, 3)]
        result = cpu.summarize_phase(rows, .5, 2.5, phase='decode_proxy')
        self.assertEqual(result['interval_count'], 1)
        self.assertEqual(result['selected_sample_count'], 2)
        self.assertAlmostEqual(result['cgroups']['glm']['observed_wall_s'], 1)
        short = cpu.summarize_phase(rows, 1.1, 1.9, phase='decode_proxy')
        self.assertEqual(short['status'], 'UNAVAILABLE')
        self.assertEqual(short['reason'], 'fewer_than_two_usable_phase_samples')
        invalid = copy.deepcopy(rows)
        invalid[1]['timestamp_monotonic_s'] = -100
        invalid[1]['collection_finished_monotonic_s'] = -100
        self.assertEqual(cpu.summarize_phase(invalid[:2], 0, 1, phase='request')['status'], 'UNAVAILABLE')

    def test_throttling_quota_changes_and_recreated_cgroup_psi_are_explicit(self):
        before, after = sample(0), sample(1)
        after['cgroups']['glm']['quota_usec'] = 800000
        result = cpu.summarize_phase([before, after], 0, 1, phase='request')
        self.assertTrue(result['cgroups']['glm']['quota_changed'])
        self.assertEqual(result['cgroups']['glm']['quota_status'], 'AVAILABLE')
        self.assertEqual(result['cgroups']['glm']['throttling']['delta_totals'],
                         {'nr_periods': 10, 'nr_throttled': 1, 'throttled_usec': 1000})
        after['cgroups']['glm']['identity'] = [9, 9]
        result = cpu.summarize_phase([before, after], 0, 1, phase='request')
        self.assertEqual(result['psi']['glm:cpu:some']['status'], 'UNAVAILABLE')
        self.assertEqual(result['cgroups']['glm']['throttling']['status'], 'UNAVAILABLE')
        self.assertEqual(result['status'], 'PARTIAL')

    def test_missing_guest_cpu_and_pressure_remain_unavailable_metrics(self):
        rows = [sample(0), sample(1)]
        for row in rows:
            row['guest_cpus'] = {}
            row['guest_psi'] = {}
        result = cpu.summarize_phase(rows, 0, 1, phase='request')
        self.assertEqual(result['guest_cpus']['cpu']['status'], 'UNAVAILABLE')
        self.assertIsNone(result['guest_cpus']['cpu']['cpu_time_s'])
        self.assertEqual(result['psi']['guest:io:full']['status'], 'UNAVAILABLE')
        self.assertEqual(result['status'], 'PARTIAL')

    def full_measurement(self):
        rows = [sample(t) for t in (0, .5, 1, 1.5, 2, 2.5, 3)]
        for row in rows:
            row['cgroups']['qwen'] = copy.deepcopy(row['cgroups']['glm'])
            row['cgroups']['qwen']['identity'] = [3, 4]
            row['processes']['qwen'] = copy.deepcopy(row['processes']['glm'])
            row['processes']['qwen'][0]['pid'] = 55
            row['guest_cpus'].update({'cpu' + str(i): copy.deepcopy(row['guest_cpus']['cpu0']) for i in range(112)})
            row['guest_psi'] = copy.deepcopy(row['guest_psi'])
            row['guest_psi']['cpu']['full'] = {'status': 'UNAVAILABLE', 'total_usec': None}
        summary = {'request_started_monotonic_s': 0, 'request_ended_monotonic_s': 3,
                   'client_timing': {'ttft_any_output_seconds': 1, 'last_output_seconds': 2},
                   'counters': {'prompt_ms': 999, 'decode_ms': 22}}
        return rows, summary

    def test_required_gate_handles_supported_channels_and_short_decode_gap(self):
        rows, summary = self.full_measurement()
        result = cpu.summarize_measurement(rows, summary)
        self.assertEqual(result['counter_evidence']['status'], 'COMPLETE')
        self.assertEqual(result['counter_evidence']['missing_or_partial'], [])
        self.assertEqual(result['request']['status'], 'PARTIAL')  # excluded global cpu.full
        self.assertIn('glm:44', result['request']['processes'])
        self.assertIn('qwen:55', result['request']['processes'])
        self.assertEqual(result['request']['cgroups']['glm']['ancestor_quota_status'], 'UNAVAILABLE')
        self.assertIn('owned cgroup', result['request']['cgroups']['glm']['quota_scope'])
        summary['client_timing']['last_output_seconds'] = 1.01
        result = cpu.summarize_measurement(rows, summary)
        self.assertEqual(result['counter_evidence']['status'], 'INCOMPLETE')
        self.assertIn('decode_proxy.phase_intervals', result['counter_evidence']['missing_or_partial'])

    def test_required_gate_demands_all112_vcpus_and_individual_process_counters(self):
        rows, summary = self.full_measurement()
        del rows[2]['guest_cpus']['cpu111']
        rows[2]['processes']['qwen'][0]['utime_ticks'] = None
        result = cpu.summarize_measurement(rows, summary)
        self.assertEqual(result['counter_evidence']['status'], 'INCOMPLETE')
        self.assertIn('request.guest_cpus.cpu111', result['counter_evidence']['missing_or_partial'])
        self.assertIn('request.processes.qwen:55', result['counter_evidence']['missing_or_partial'])

    def comparison_rows(self):
        result = {}
        for name in ('A-G65008', 'A-Qnear480K', 'A-Q256K', 'B-G65008', 'B-Qnear480K'):
            value = 65008 if 'G65008' in name else 261622 if '256K' in name else 479480
            result[name] = {'id': name, 'status': 'PASS', 'layout': name[0],
                'common_input': name == 'A-Q256K', 'configured_capacity': 480000,
                'fixture_sha256': name[2:], 'native_count_valid': True,
                'count': {'input_tokens': value, 'body_sha256': 'fresh-' + name},
                'sample': {'request_started_monotonic_s': 0, 'request_ended_monotonic_s': 3,
                    'client_timing': {'ttft_any_output_seconds': 1, 'last_output_seconds': 2},
                    'counters': {'prompt_ms': 1000 if name[0] == 'A' else 1200, 'decode_ms': 22,
                                 'prompt_tokens': value, 'completion_tokens': 12}},
                'cpu_evidence': {'counter_evidence': {'status': 'COMPLETE'}},
                'peer_condition_at_admission': 'barrier_main_pair'}
        return result

    def test_five_case_comparison_preserves_counts_and_only_observed_ratios(self):
        completed = self.comparison_rows()
        completed['B-G65008']['sample']['counters']['completion_tokens'] = 13
        result = cpu.comparison_summary(completed)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertAlmostEqual(result['paired_layouts']['G65008']['observed_ratios']['native_prompt_ms_B_over_A'], 1.2)
        self.assertFalse(result['paired_layouts']['G65008']['same_actual_completion_count'])
        self.assertEqual(result['observations']['B-G65008']['actual_completion_tokens'], 13)
        self.assertEqual(result['observations']['A-Q256K']['native_input_tokens'], 261622)
        self.assertEqual(result['layouts']['A'], {'active_vcpus': 112, 'glm_configured_threads': 96,
            'qwen_permitted_vcpus': 16, 'glm_cpuset': '0-95', 'qwen_cpuset': '96-111'})
        self.assertEqual(result['layouts']['B'], {'active_vcpus': 96, 'glm_configured_threads': 88,
            'qwen_permitted_vcpus': 8, 'glm_cpuset': '0-87', 'qwen_cpuset': '96-103'})
        self.assertNotIn('qwen_threads', json.dumps(result))
        self.assertEqual(result['causal_claim'], 'NOT_ESTABLISHED')
        self.assertEqual(result['cores_needed_from_utilization'], 'NOT_ESTABLISHED')
        self.assertIn('HISTORICAL_ONLY', result['historical_Q700_comparison'])

    def test_comparison_incomplete_missing_rows_cpu_counts_fixture_or_clock(self):
        for mutation in ('row', 'cpu', 'count', 'fixture', 'clock', 'extra'):
            with self.subTest(mutation=mutation):
                completed = self.comparison_rows()
                if mutation == 'row':
                    del completed['A-Q256K']
                elif mutation == 'cpu':
                    completed['B-G65008']['cpu_evidence']['counter_evidence']['status'] = 'INCOMPLETE'
                elif mutation == 'count':
                    completed['B-G65008']['count']['input_tokens'] += 1
                elif mutation == 'fixture':
                    completed['B-G65008']['fixture_sha256'] = 'changed'
                elif mutation == 'clock':
                    del completed['B-G65008']['sample']['request_ended_monotonic_s']
                else:
                    completed['extra-case'] = completed['A-Q256K']
                result = cpu.comparison_summary(completed)
                self.assertEqual(result['status'], 'INCOMPLETE')
                self.assertTrue(result['missing_or_partial'])

    def test_warmup_gate_accepts_same_identity_endpoints_and_labels_isolated_gap(self):
        rows, _ = self.full_measurement()
        receipt = cpu.warmup_gate([rows[0], {'status': 'UNAVAILABLE', 'reason': 'bounded_read_exceeded'}, rows[-1]], 'glm')
        self.assertEqual(receipt['status'], 'PASS')
        self.assertEqual(receipt['positive_model_cpu_interval_count'], 1)
        self.assertEqual(receipt['intervals'][0]['isolated_gap_count'], 1)
        self.assertTrue(receipt['intervals'][0]['all_112_guest_vcpu_deltas_available'])
        self.assertIn('cpu_collector_unavailable:bounded_read_exceeded', receipt['isolated_gaps'][0]['causes'])

    def test_warmup_gate_missing_cpu_stops_before_long_with_exact_fields(self):
        rows, _ = self.full_measurement()
        for row in rows:
            row['cgroups']['glm']['usage_usec'] = None
        receipt = cpu.warmup_gate(rows, 'glm')
        self.assertEqual(receipt['status'], 'UNAVAILABLE')
        self.assertEqual(receipt['cause'], 'cpu_collector_unavailable_throughout_warmup')
        self.assertEqual(receipt['failure_action'], 'STOP_BEFORE_LONG_REQUESTS')
        self.assertIn('owned_cgroup.identity_or_usage_usec_unavailable', receipt['isolated_gaps'][0]['causes'])
        self.assertEqual(cpu.warmup_gate([], 'glm')['status'], 'UNAVAILABLE')

    def test_warmup_gate_requires_positive_model_cpu_stable_pids_and_guest_deltas(self):
        for change in ('identity', 'process', 'guest', 'clock', 'zero'):
            with self.subTest(change=change):
                rows, _ = self.full_measurement()
                before, after = rows[0], rows[-1]
                if change == 'identity':
                    after['cgroups']['glm']['identity'] = [1, 9]
                elif change == 'process':
                    after['processes']['glm'][0]['starttime_ticks'] += 1
                elif change == 'guest':
                    del after['guest_cpus']['cpu111']
                elif change == 'clock':
                    after['client_observed_monotonic_s'] = before['client_observed_monotonic_s']
                else:
                    after['cgroups']['glm']['usage_usec'] = 0
                    after['processes']['glm'][0]['utime_ticks'] = 0
                receipt = cpu.warmup_gate([before, after], 'glm')
                self.assertEqual(receipt['status'], 'UNAVAILABLE')
                self.assertEqual(receipt['failure_action'], 'STOP_BEFORE_LONG_REQUESTS')

    def test_measurement_native_aggregate_is_separate_and_missing_phase_explicit(self):
        summary = {'request_started_monotonic_s': 0, 'request_ended_monotonic_s': 3,
                   'client_timing': {'ttft_any_output_seconds': 1, 'last_output_seconds': 2},
                   'counters': {'prompt_ms': 999, 'decode_ms': 22}}
        result = cpu.summarize_measurement([sample(t) for t in (0, 1, 2, 3)], summary)
        self.assertEqual(result['native_aggregate_timing']['decode_ms'], 22)
        self.assertTrue(result['native_aggregate_is_not_cpu_phase_boundary'])
        self.assertEqual(result['decode_proxy']['interval_count'], 1)
        self.assertEqual(result['prefill_proxy']['interval_count'], 1)
        self.assertEqual(cpu.summarize_measurement([], {})['decode_proxy']['status'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
