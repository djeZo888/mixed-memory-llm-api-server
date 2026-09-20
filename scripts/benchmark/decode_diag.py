"""Bounded GLM decode protocol primitives for the existing Ladder/Diagnostic owner.

Import and CLI are offline. This PREP module does not dispatch a live campaign or
launch profilers. A fresh root-reviewed RUN composes these requests with the
existing owner, safety monitor, native counter and restoration path.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from . import fixtures, g1_ladder, profiles

CAPACITIES = (1024, 32768, 65536)
QUESTION = ("Explain in a detailed, self-contained graduate-level tutorial of about 4,000 tokens "
            "how the finite-element method solves Poisson’s equation, covering the weak formulation, "
            "boundary conditions, matrix assembly, a worked one-dimensional example, error estimation "
            "and practical numerical pitfalls.")


def stage_clock(task):
    value = json.loads((Path(task) / 'stage-clock.json').read_bytes())
    start, deadline = value.get('start_epoch'), value.get('deadline_epoch')
    if (type(start) not in (int, float) or type(deadline) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(deadline) or start <= 0
            or deadline != start + 14400 or value.get('budget_seconds') != 14400
            or value.get('request_max_seconds') != 7200
            or value.get('clock_includes_preparation') is not True
            or value.get('restoration_outside_budget') is not True):
        raise ValueError('immutable_four_hour_diagnostic_clock_required')
    return value


def request_timeout(clock, now):
    remaining = clock['deadline_epoch'] - now
    if remaining <= 0:
        raise RuntimeError('STOP_BUDGET')
    return min(clock.get('request_max_seconds', 7200), remaining)


def validate_profile_clock(value):
    """One fresh twenty-minute preparation plus measurement cap, never a reset."""
    start, deadline = value.get('start_epoch'), value.get('deadline_epoch')
    original = value.get('original_clock') or {}
    old_start, old_deadline = original.get('start_epoch'), original.get('deadline_epoch')
    if (value.get('stage') != 'GLM-DECODE-PROFILE-20260920'
            or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                   for v in (start, deadline, old_start, old_deadline))
            or deadline != start + 1200 or value.get('budget_seconds') != 1200
            or value.get('request_max_seconds') != 1200
            or value.get('includes_preparation') is not True
            or value.get('clock_includes_preparation') is not True
            or value.get('restoration_outside_budget') is not True
            or original.get('stage') != 'GLM-DECODE-DIAG-20260920'
            or original.get('budget_seconds') != 14400 or old_deadline != old_start + 14400
            or original.get('request_max_seconds') != 7200
            or original.get('clock_includes_preparation') is not True
            or original.get('restoration_outside_budget') is not True
            or not old_start <= start < deadline <= old_deadline):
        raise ValueError('immutable_profile_twenty_minute_clock_and_original_ceiling_required')
    return start, deadline


def profile_stage_clock(task):
    value = json.loads((Path(task) / 'profile-stage-clock.json').read_bytes())
    if value.get('original_clock') != stage_clock(task):
        raise ValueError('original_campaign_clock_changed')
    value = {**value, 'request_max_seconds': 1200, 'clock_includes_preparation': True}
    validate_profile_clock(value)
    return value


def short_body(sample, output_cap=128):
    if output_cap not in (32, 128, 256) or sample['kind'] != 'generation':
        raise ValueError('diagnostic_short_generation_only')
    body = json.loads(fixtures.serialize_validate(sample))
    body.update(max_tokens=output_cap, temperature=1.0, seed=1729,
                timings_per_token=True)
    # Natural generation with a fixed ceiling. No EOS suppression/grammar makes
    # actual output length a result, never an assumed fixed native token count.
    return fixtures.canonical(body)


def fit_short(capacity, nonce, counter, *, matched=None, warmup=False, synthetic=False):
    """Fit once at 1K; all later controls retain records/seed/kind and recount."""
    if type(capacity) is not int or capacity not in CAPACITIES:
        raise ValueError('diagnostic_capacity_outside_scope')
    if warmup and (capacity != 1024 or matched is not None):
        raise ValueError('small_warmup_only_at_1k')
    if not warmup and matched is None and capacity != 1024:
        raise ValueError('short_control_must_match_1k')
    seed = 'decode-warmup-1729' if warmup else 'decode-short-1729'
    if matched is not None:
        fixtures.serialize_validate(matched)
        if matched['seed'] != seed or matched['nonce'] == nonce or matched['kind'] != 'generation':
            raise ValueError('fresh_matching_fixture_required')
    records = [matched['records']] if matched is not None else range(12, 33)
    for count in records:
        sample = fixtures.build_sample(g1_ladder.MODEL, count, seed, nonce, kind='generation')
        raw = short_body(sample, 32 if warmup else 128)
        counted = fixtures.validate_count(counter(raw), raw, capacity, synthetic=synthetic)
        if 600 <= counted['input_tokens'] <= 750:
            if matched is not None and sample['fixture_sha256'] != matched['fixture_sha256']:
                raise ValueError('matched_logical_input_changed')
            return sample, raw, {**counted, 'output_cap':32 if warmup else 128,
                'input_range':[600,750], 'fixture_sha256':sample['fixture_sha256'],
                'minimum_warmup_prefill_tokens':512 if warmup else None,
                'fixed_output_length':False}
    raise ValueError('short_native_count_outside_600_750_no_refit_matched')


def schema_body(sample, output_cap=256):
    body = json.loads(g1_ladder.body_bytes(sample, output_cap))
    body['timings_per_token'] = True
    return fixtures.canonical(body)


def fit_replay(nonce, counter, prior_sample, *, synthetic=False):
    """Existing accepted fixture/strict scorer, fresh leading nonce, final recount."""
    return g1_ladder.fit(65536, nonce, counter, matched=prior_sample,
                        synthetic=synthetic, body_builder=schema_body)


def fit_warmup(capacity, nonce, counter, *, synthetic=False):
    if capacity == 1024:
        return fit_short(capacity, nonce, counter, warmup=True, synthetic=synthetic)
    if capacity not in (32768, 65536):
        raise ValueError('diagnostic_capacity_outside_scope')
    # Reuse the existing retrieval fixture/schema, but count against the actual
    # configured capacity without rewriting counter provenance.
    low, high = 12, 128
    while low <= high:
        records = (low + high) // 2
        sample = fixtures.build_sample(g1_ladder.MODEL, records, 'warmup-only-seed', nonce)
        raw = schema_body(sample, 32)
        counted = fixtures.validate_count(counter(raw), raw, capacity, synthetic=synthetic)
        actual = counted['input_tokens']
        if 2304 <= actual <= 2432:
            return sample, raw, {**counted, 'output_cap':32, 'minimum_warmup_prefill_tokens':2048,
                'input_ceiling_tokens':2432, 'margin_tokens':capacity-2432-32,
                'fixture_sha256':sample['fixture_sha256']}
        if actual < 2304:
            low = records + 1
        else:
            high = records - 1
    raise ValueError('large_warmup_native_count_outside_target')


def long_body():
    return fixtures.canonical({'model':g1_ladder.MODEL,
        'messages':[{'role':'user','content':QUESTION}], 'max_tokens':4096,
        'temperature':1.0,'seed':1729,'reasoning_effort':'low',
        'stream':True,'stream_options':{'include_usage':True},'timings_per_token':True})


def natural_outcome(result):
    """Separate delivery/length from human review of the actual final answer."""
    summary = result['summary']
    counters = summary.get('counters') or {}
    parsed = result.get('parsed') or {}
    content = (parsed.get('message') or {}).get('content')
    complete = summary.get('status') == 'COMPLETE' and parsed.get('finish_reason') == 'stop'
    return {'status': summary.get('status'), 'finish_reason': parsed.get('finish_reason'),
        'actual_completion_tokens': counters.get('completion_tokens'), 'requested_output_cap':4096,
        'completed_natural_answer': complete,
        'is_4096_token_throughput_sample': counters.get('completion_tokens') == 4096,
        'content_sha256': fixtures.digest(content.encode()) if isinstance(content,str) else None,
        'coherence_and_topic_coverage': 'REQUIRES_PRIVATE_FINAL_CONTENT_REVIEW',
        'reasoning_final_token_split': 'UNAVAILABLE_UNLESS_REPORTED_NATIVELY',
        'partial_response_preserved_by': 'existing private raw capture and bounded event receipts'}


def decode_windows(rows, aggregate=None, *, dropped_events=0):
    """Native count/time differences; event rate is never relabeled tokens/s."""
    if dropped_events != 0:
        return {'status':'UNAVAILABLE','reason':'event_receipt_truncated'}
    points = []
    for row in rows:
        native = row.get('native_timings') or {}
        n, ms = native.get('predicted_n'), native.get('predicted_ms')
        if type(n) is not int or n < 1 or type(ms) not in (int,float) or not math.isfinite(ms) or ms < 0:
            continue
        if points and (n < points[-1][0] or ms < points[-1][1]):
            return {'status':'UNAVAILABLE','reason':'native_counter_regression'}
        if points and n == points[-1][0] and ms != points[-1][1]:
            return {'status':'UNAVAILABLE','reason':'same_count_native_time_changed'}
        if not points or n > points[-1][0]:
            points.append((n,ms,row.get('arrived_monotonic_s')))
    if len(points) < 4:
        return {'status':'UNAVAILABLE','reason':'insufficient_native_progress','sse_events_are_not_tokens':True}
    if aggregate is not None and (points[-1][0] != aggregate.get('decode_tokens')
            or points[-1][1] != aggregate.get('decode_ms')):
        return {'status':'UNAVAILABLE','reason':'final_native_aggregate_mismatch'}
    first,last = points[0][0],points[-1][0]
    indexes = [0] + [min(range(1,len(points)-1), key=lambda i:abs(points[i][0]-(first+(last-first)*f)))
                     for f in (1/3,2/3)] + [len(points)-1]
    if len(set(indexes)) != 4:
        return {'status':'UNAVAILABLE','reason':'insufficient_third_boundaries'}
    windows=[]
    for name,a,b in zip(('beginning','middle','end'),indexes,indexes[1:]):
        left,right=points[a],points[b]; elapsed=right[1]-left[1]
        if elapsed <= 0:
            return {'status':'UNAVAILABLE','reason':'nonpositive_native_interval'}
        windows.append({'part':name,'native_count_start':left[0],'native_count_end':right[0],
            'native_elapsed_ms':elapsed,'native_tokens_per_second':(right[0]-left[0])*1000/elapsed if elapsed>0 else None,
            'client_arrival_start':left[2],'client_arrival_end':right[2]})
    return {'status':'AVAILABLE','windows':windows,'scope':'observed native cumulative counter intervals; aggregate native final timing remains authoritative',
            'sse_events_are_not_tokens':True}


def capture_is_decode(before, after, started, ended):
    """Host-monotonic bracketing only; no phase-label-only acceptance."""
    left, right = before.get('host_finished_monotonic_s'), after.get('host_started_monotonic_s')
    return (all(type(v) in (int,float) and math.isfinite(v) for v in (started,ended,left,right))
        and type(before.get('slot_id')) is int and before.get('slot_id') == after.get('slot_id')
        and type(before.get('task_id')) is int and before['task_id'] == after.get('task_id')
        and before.get('is_processing') is True and after.get('is_processing') is True
        and type(before.get('n_decoded')) is int and type(after.get('n_decoded')) is int
        and 0 < before['n_decoded'] < after['n_decoded']
        and left <= started < ended <= right)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    clock=stage_clock(args.task_dir)
    print(json.dumps({'scope':'glm-decode-diag','clock':clock,
        'campaign':profiles.GLM_DECODE_DIAG_CAMPAIGN,
        'manifests':[profiles.glm_decode_diag_manifest(n) for n in CAPACITIES],
        'trial_plan':profiles.trial_order('glm-decode-diag'),
        'live_dispatch':False,'profiler_dispatch':False},indent=2))


if __name__ == '__main__':
    main()
