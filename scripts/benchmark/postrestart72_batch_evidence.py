"""Pure, text-free evidence augmentation for the sealed REAL72 batch.

No sampling, transport, timeout classification or lifecycle operation occurs
here. The existing owner supplies captured observations and verified outcomes.
Partial native progress never becomes an invented final usage count.
"""
from __future__ import annotations

import math

from . import decode_diag, telemetry


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _native_progress(arrivals):
    latest, previous, reason = None, None, None
    for row in arrivals.get('rows') or []:
        native = row.get('native_timings') or {}
        n, ms = _count(native.get('predicted_n')), native.get('predicted_ms')
        if n is None or not _number(ms):
            continue
        if previous is not None and (n < previous[0] or ms < previous[1]
                or n == previous[0] and ms != previous[1]):
            reason = 'native_progress_regression_or_inconsistent_repeated_count'
        previous = n, ms
        latest = {'decode_tokens': n, 'decode_ms': ms,
            'evaluated_prompt_tokens': _count(native.get('prompt_n')),
            'prompt_ms': native.get('prompt_ms') if _number(native.get('prompt_ms')) else None,
            'last_observed_elapsed_s': row.get('elapsed_s') if _number(row.get('elapsed_s')) else None}
    if reason or latest is None:
        return {'status': 'UNAVAILABLE', 'reason': reason or 'native_progress_fields_absent',
                'final_usage': False}
    return {'status': 'PARTIAL' if arrivals.get('dropped_events', 0) else 'AVAILABLE',
        **latest, 'source': 'last_retained_SSE_native_timings_snapshot', 'final_usage': False,
        'retained_event_rows_truncated': bool(arrivals.get('dropped_events', 0)),
        'native_n_minus_one_decode_tps': (latest['decode_tokens'] - 1) * 1000 / latest['decode_ms']
            if latest['decode_tokens'] > 1 and latest['decode_ms'] > 0 else None,
        'scope': 'observed cumulative progress; completion/reasoning/final-content token counts unavailable'}


def _event_windows(rows, *, dropped_events=0):
    if dropped_events:
        return {'status': 'UNAVAILABLE', 'reason': 'event_receipt_truncated'}
    points = [row for row in rows if any(row.get('has_' + k) is True for k in ('content', 'reasoning', 'tool'))
              and _number(row.get('arrived_monotonic_s'))]
    if len(points) < 4:
        return {'status': 'UNAVAILABLE', 'reason': 'insufficient_output_event_arrivals'}
    if any(right['arrived_monotonic_s'] < left['arrived_monotonic_s'] for left, right in zip(points, points[1:])):
        return {'status': 'UNAVAILABLE', 'reason': 'client_arrival_regression'}
    last = len(points) - 1
    indexes = [0, round(last / 3), round(last * 2 / 3), last]
    windows = []
    for part, a, b in zip(('beginning', 'middle', 'end'), indexes, indexes[1:]):
        elapsed = points[b]['arrived_monotonic_s'] - points[a]['arrived_monotonic_s']
        if elapsed <= 0:
            return {'status': 'UNAVAILABLE', 'reason': 'coalesced_or_insufficient_distinct_arrivals'}
        windows.append({'part': part, 'output_event_transitions': b - a,
            'client_elapsed_s': elapsed, 'output_events_per_second': (b - a) / elapsed,
            'client_arrival_start': points[a]['arrived_monotonic_s'],
            'client_arrival_end': points[b]['arrived_monotonic_s']})
    return {'status': 'AVAILABLE', 'windows': windows,
        'scope': 'SSE events with content/reasoning/tool deltas; batching and client overhead included'}


def output_evidence(summary, *, output_cap, placement):
    """Preserve output caps, final native usage and partial progress separately."""
    if output_cap not in (256, 4096) or placement not in ('G1', 'Q1') or output_cap == 4096 and placement != 'G1':
        raise ValueError('closed_batch_evidence_cap_and_placement_required')
    counters = summary.get('counters') or {}
    n, ms = _count(counters.get('decode_tokens')), counters.get('decode_ms')
    prompt_n, prompt_ms = _count(counters.get('evaluated_prompt_tokens')), counters.get('prompt_ms')
    arrivals = (summary.get('client_timing') or {}).get('event_arrivals') or {}
    rows, dropped = arrivals.get('rows') or [], arrivals.get('dropped_events', 0)
    native = decode_diag.decode_windows(rows,
        {'decode_tokens': n, 'decode_ms': ms} if n is not None and _number(ms) else None,
        dropped_events=dropped)
    rolling = ({'rate_kind': 'native_tokens_per_second', **native} if native['status'] == 'AVAILABLE' else
        {'rate_kind': 'output_events_per_second', **_event_windows(rows, dropped_events=dropped),
         'native_window_status': native['status'], 'native_window_unavailable_reason': native.get('reason')})
    rolling['sse_events_are_not_tokens'] = True
    return {'requested_output_cap': output_cap,
        'actual_completion_tokens': _count(counters.get('completion_tokens')),
        'actual_native_decode_tokens': n, 'native_decode_ms': ms if _number(ms) else None,
        'native_n_minus_one_decode_tps': (n - 1) * 1000 / ms if n is not None and n > 1 and _number(ms) and ms > 0 else None,
        'native_prefill_tokens_per_second': prompt_n * 1000 / prompt_ms
            if prompt_n is not None and _number(prompt_ms) and prompt_ms > 0 else None,
        'native_count_availability': {key: counters.get(key) is not None for key in
            ('prompt_tokens', 'evaluated_prompt_tokens', 'cached_tokens', 'completion_tokens', 'decode_tokens')},
        'native_progress': _native_progress(arrivals), 'rolling_decode': rolling,
        'captured_event_count': len(rows), 'dropped_event_rows': dropped,
        'event_capture_complete': arrivals.get('complete') is True,
        'outcome_status': summary.get('status'),
        'output_cap_includes_reasoning': True, 'final_answer_token_count': None,
        'quality_and_transport_are_separate': True}


def sampled_resources(samples, summary):
    """Reuse 1 s samples for phase resource peaks and coverage; no new reads."""
    start, end = summary.get('request_started_monotonic_s'), summary.get('request_ended_monotonic_s')
    timing = summary.get('client_timing') or {}
    first, last = timing.get('ttft_any_output_seconds'), timing.get('last_output_seconds')
    first = start + first if _number(start) and _number(first) else None
    last = start + last if _number(start) and _number(last) else None
    # CPU counters are summarized independently by cpu_budget_telemetry. Keep
    # raw RAM/cache/estimated working-set charges separate in this projection.
    keys = ('timestamp_monotonic_s', 'collection_duration_s', 'host', 'cgroups', 'processes',
            'gpus', 'required_host_demand', 'concurrent_resource_gate')
    rows = [{key: sample[key] for key in keys if key in sample} for sample in samples
            if _number(sample.get('timestamp_monotonic_s'))]
    result = {}
    for phase, a, b in (('request', start, end), ('prefill_proxy', start, first), ('decode_proxy', first, last)):
        result[phase] = ({'status': 'AVAILABLE', **telemetry.summarize_samples(rows, a, b)}
            if _number(a) and _number(b) and b > a else
            {'status': 'UNAVAILABLE', 'reason': 'missing_or_empty_client_phase_interval'})
        if result[phase].get('sample_count') == 0:
            result[phase]['status'] = 'UNAVAILABLE'
            result[phase]['reason'] = 'no_samples_in_phase'
    result['scope'] = ('sampled GPU utilization/power/VRAM, summed process RSS (shared pages may double count), '
        'cgroup RAM and charged file cache, required working-set ESTIMATE kept separate; no instant cache reclaim claim')
    result['phase_boundary'] = 'client output arrival proxy; native aggregate timings are separate'
    result['cpu_evidence'] = 'existing cpu_evidence; core-equivalents include spin and do not prove useful work'
    return result


def augment(row, samples, *, output_cap, placement):
    """Add safe summaries to the caller-owned result; preserve original verdict."""
    row['output_evidence'] = output_evidence(row['sample'], output_cap=output_cap, placement=placement)
    row['sampled_resources'] = sampled_resources(samples, row['sample'])
    return row
