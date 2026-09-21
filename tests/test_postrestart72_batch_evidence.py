"""Focused offline checks for sealed-batch partial and sampled evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import client, fixtures, postrestart72_batch_evidence as evidence


def observed(native=True, complete=False):
    observer = client.StreamObserver(10, capture_events=True)
    for index in range(1, 11):
        event = {'choices': [{'index': 0, 'delta': {'reasoning_content': 'PRIVATE-REASONING'}, 'finish_reason': None}]}
        if native:
            event['timings'] = {'predicted_n': index, 'predicted_ms': index * 1000,
                                'prompt_n': 65, 'prompt_ms': 2000}
        observer.feed(b'data: ' + fixtures.canonical(event) + b'\n\n', 10 + index)
    if complete:
        observer.feed(b'data: [DONE]\n\n', 21)
    return {'status': 'TIMEOUT' if not complete else 'COMPLETE', 'counters': {},
        'request_started_monotonic_s': 10, 'request_ended_monotonic_s': 7210 if not complete else 21,
        'client_timing': observer.summary()}


class BatchEvidence(unittest.TestCase):
    def test_partial_native_progress_is_not_final_usage_or_a_quality_gate(self):
        summary = observed()
        row = {'status': 'TIMEOUT', 'sample': summary}
        evidence.augment(row, [], output_cap=4096, placement='G1')
        result = row['output_evidence']
        self.assertEqual(row['status'], 'TIMEOUT')
        self.assertIsNone(result['actual_completion_tokens'])
        self.assertIsNone(result['native_n_minus_one_decode_tps'])
        self.assertEqual(result['requested_output_cap'], 4096)
        self.assertEqual(result['native_progress']['decode_tokens'], 10)
        self.assertEqual(result['native_progress']['native_n_minus_one_decode_tps'], .9)
        self.assertFalse(result['native_progress']['final_usage'])
        self.assertEqual(result['rolling_decode']['rate_kind'], 'native_tokens_per_second')
        self.assertEqual([v['native_tokens_per_second'] for v in result['rolling_decode']['windows']], [1, 1, 1])
        self.assertNotIn('PRIVATE-REASONING', json.dumps(row))

    def test_transport_uncertainty_is_never_reclassified_as_timeout(self):
        summary = observed()
        summary['status'] = 'TRANSPORT_FAILURE'
        result = evidence.output_evidence(summary, output_cap=4096, placement='G1')
        self.assertEqual(result['outcome_status'], 'TRANSPORT_FAILURE')
        self.assertEqual(summary['status'], 'TRANSPORT_FAILURE')

    def test_final_native_n_minus_one_and_caps_are_separate(self):
        summary = observed(complete=True)
        summary['counters'] = {'completion_tokens': 10, 'decode_tokens': 10, 'decode_ms': 10000,
                               'evaluated_prompt_tokens': 65, 'prompt_ms': 2000, 'cached_tokens': 0}
        result = evidence.output_evidence(summary, output_cap=256, placement='G1')
        self.assertEqual(result['actual_completion_tokens'], 10)
        self.assertEqual(result['native_n_minus_one_decode_tps'], .9)
        self.assertEqual(result['native_prefill_tokens_per_second'], 32.5)
        self.assertTrue(result['native_count_availability']['cached_tokens'])
        self.assertIsNone(result['final_answer_token_count'])

    def test_without_native_counters_windows_are_explicit_event_rates(self):
        result = evidence.output_evidence(observed(native=False), output_cap=256, placement='Q1')
        self.assertEqual(result['native_progress']['status'], 'UNAVAILABLE')
        rolling = result['rolling_decode']
        self.assertEqual(rolling['rate_kind'], 'output_events_per_second')
        self.assertEqual([v['output_events_per_second'] for v in rolling['windows']], [1, 1, 1])
        self.assertNotIn('native_tokens_per_second', json.dumps(rolling))
        self.assertTrue(rolling['sse_events_are_not_tokens'])

    def test_regression_truncation_and_coalescing_are_not_invented_token_rates(self):
        summary = observed()
        rows = summary['client_timing']['event_arrivals']['rows']
        rows[-1]['native_timings']['predicted_n'] = 1
        result = evidence.output_evidence(summary, output_cap=4096, placement='G1')
        self.assertEqual(result['native_progress']['status'], 'UNAVAILABLE')
        self.assertEqual(result['rolling_decode']['rate_kind'], 'output_events_per_second')
        summary['client_timing']['event_arrivals']['dropped_events'] = 2
        result = evidence.output_evidence(summary, output_cap=4096, placement='G1')
        self.assertEqual(result['rolling_decode']['status'], 'UNAVAILABLE')
        summary = observed(native=False)
        for row in summary['client_timing']['event_arrivals']['rows']:
            row['arrived_monotonic_s'] = 11
        self.assertEqual(evidence.output_evidence(summary, output_cap=256, placement='G1')['rolling_decode']['status'], 'UNAVAILABLE')

    def test_existing_samples_keep_rss_ram_cache_and_required_estimate_separate(self):
        summary = observed(complete=True)
        samples = [{'timestamp_monotonic_s': second, 'collection_duration_s': .01,
            'cgroups': {'g': {'current_bytes': 1000, 'file_bytes': 300, 'rss_bytes': None}},
            'processes': {'g': {'rss_bytes': 800}},
            'gpus': [{'uuid': 'GPU-reviewed', 'used_bytes': 400, 'utilization_percent': 50, 'power_watts': 200}],
            'required_host_demand': {'evidence_status': 'ESTIMATE', 'required_bytes': 900, 'reclaimable_file_bytes': None},
            'cpu_budget': {'unrelated': 999}} for second in range(10, 22)]
        original = copy.deepcopy(samples)
        result = evidence.sampled_resources(samples, summary)
        metrics = result['request']['metrics']
        self.assertEqual(metrics['cgroups.g.current_bytes']['sampled_peak'], 1000)
        self.assertEqual(metrics['processes.g.rss_bytes']['sampled_peak'], 800)
        self.assertEqual(metrics['required_host_demand.required_bytes']['sampled_peak'], 900)
        self.assertEqual(metrics['cgroups.g.rss_bytes']['available_samples'], 0)
        self.assertEqual(metrics['gpus.GPU-reviewed.power_watts']['sampled_peak'], 200)
        self.assertFalse(any(k.startswith('cpu_budget.') for k in metrics))
        self.assertEqual(samples, original)
        self.assertIn('coverage_fraction_estimate', result['decode_proxy'])
        self.assertEqual(evidence.sampled_resources([], summary)['request']['status'], 'UNAVAILABLE')

    def test_narrow_cap_and_placement_validation(self):
        for cap, placement in ((32, 'G1'), (512, 'G1'), (4096, 'Q1'), (256, 'other')):
            with self.assertRaises(ValueError):
                evidence.output_evidence({}, output_cap=cap, placement=placement)


if __name__ == '__main__':
    unittest.main()
