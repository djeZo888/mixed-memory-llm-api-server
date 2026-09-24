#!/usr/bin/env python3
"""Normalize existing local Worker2 receipts; no networking or inference."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'worker2-client-evidence'
SAMPLER = ROOT / 'artifacts/worker2-baseline-segment2'
OUTPUT = ROOT / 'artifacts/worker2-baseline'
REPORT = ROOT / 'repo/reports/image21-qualify-20260923/worker2-client'


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size}


def utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def metrics(samples):
    assert samples
    memory = [r['device']['memory_bytes']['value'] for r in samples
              if r['device']['memory_bytes']['code'] == 0]
    assert len(memory) == len(samples)
    totals = {v['total'] for v in memory}; assert len(totals) == 1
    host = [r['host'] for r in samples if 'host' in r]
    mem = [h['meminfo_bytes']['value']['values'] for h in host if h['meminfo_bytes']['status'] == 'ok']
    vm = [h['vmstat_counters']['value']['values'] for h in host if h['vmstat_counters']['status'] == 'ok']
    cg = {name: [h['cgroup_bytes'][name]['value'] for h in host if h['cgroup_bytes'][name]['status'] == 'ok']
          for name in ('memory.current', 'memory.peak', 'memory.swap.current')}
    assert mem and vm and all(cg.values())
    return {
        'device': {'total_bytes': totals.pop(), 'sampled_peak_used_bytes': max(v['used'] for v in memory),
                   'request_window_peak_used_bytes': max(v['used'] for v in memory),
                   'sampled_min_free_bytes': min(v['free'] for v in memory),
                   'minimum_free_fraction': min(v['free'] / v['total'] for v in memory),
                   'first_sample_used_bytes': memory[0]['used'], 'last_sample_used_bytes': memory[-1]['used']},
        'host': {'min_available_bytes': min(v['MemAvailable'] for v in mem),
                 'min_available_fraction': min(v['MemAvailable'] / v['MemTotal'] for v in mem),
                 'max_swap_used_bytes': max(v['SwapTotal'] - v['SwapFree'] for v in mem),
                 'vmstat_counter_deltas': {k: vm[-1][k] - vm[0][k] for k in ('pswpin', 'pswpout', 'oom_kill', 'pgmajfault')}},
        'cgroup': {name: {'min': min(v), 'max': max(v), 'sample_count': len(v)} for name, v in cg.items()},
        'sampling': {'requested_interval_seconds': .2, 'sample_count': len(samples), 'host_sample_count': len(host),
                     'first_sample_utc': samples[0]['utc'], 'last_sample_utc': samples[-1]['utc'],
                     'max_observed_interval_seconds': max(r.get('interval_s') or 0 for r in samples),
                     'max_query_duration_seconds': max(r['query_duration_s'] for r in samples)},
    }


def main():
    release_path = SOURCE / 'LIVE-WINDOW-RELEASE.json'; release = load(release_path)
    generate_path = SOURCE / 'LIVE-generate.json'; generate = load(generate_path)
    attempt_path = SOURCE / 'evidence/baseline-generation.attempt.json'; attempt = load(attempt_path)
    reject_path = SOURCE / 'LIVE-reject-edit.json'; reject = load(reject_path)
    sampler_path = SAMPLER / 'window-result.json'; sampler = load(sampler_path)
    telemetry_path = SAMPLER / 'telemetry.jsonl'
    deployment_path = ROOT / 'DEPLOYMENT-RECEIPT.json'; deployment = load(deployment_path)
    note_path = ROOT / 'ROOT-WORKER2-RESULT.md'
    png = SOURCE / 'evidence/baseline-generation.png'
    assert release['accepted_generation_count'] == 1 and release['accepted_edit_count'] == 0
    assert release['ownership_returned'] is True and release['requests_in_flight'] is False
    assert sha(png) == release['output']['sha256']
    assert sha(telemetry_path) == sampler['telemetry_sha256']
    source_manifest = load(SOURCE / 'SHA256-MANIFEST.json')
    for name, expected in source_manifest.items():
        assert sha(SOURCE / name) == expected, name
    start = utc(release['generation_request_start_utc'])
    end = utc(release['generation_request_end_utc_derived'])
    rows = [json.loads(line) for line in telemetry_path.read_text().splitlines()]
    assert rows[0]['event'] == 'start' and rows[-1]['event'] == 'stop'
    all_samples = [r for r in rows if r['event'] == 'sample']
    assert utc(all_samples[0]['utc']) <= start and utc(all_samples[-1]['utc']) >= end
    samples = [r for r in all_samples if start <= utc(r['utc']) <= end]
    measured = metrics(samples)
    full = sampler['sampling_metrics_entire_window']
    measured['scope'] = 'UTC-intersected actual Worker2 HTTP request; client monotonic clocks are not compared to VM monotonic clocks.'
    measured['sampling']['request_start_to_first_sample_seconds'] = (utc(samples[0]['utc']) - start).total_seconds()
    measured['sampling']['last_sample_to_request_end_seconds'] = (end - utc(samples[-1]['utc'])).total_seconds()
    measured['sampling']['full_window_skipped_schedule_slots'] = rows[-1]['skipped_schedule_slots']
    limits = [
        'Request end UTC is derived from client start UTC plus full-precision local monotonic duration, not a separately sampled UTC end.',
        'Cross-host UTC clock offset was not measured; UTC intersection uses the supplied recorded clocks. Cross-host monotonic values were never compared.',
        'NVML peaks between 200 ms samples are unobserved; query duration is not a synchronized metric timestamp.',
        'Host/cgroup sampling is nominally 1 s. memory.peak is a cgroup lifetime high-water mark.',
        'This independent API baseline uses seed 20260923 and its studio-teapot prompt, unlike the seed 42 ladder. It is not a same-recipe comparison.',
        'No per-request native perf dump was saved. Native log timing and peak are rounded; allocated peak is unavailable. Deployment-warm allocator values were not reused.',
        'Full-window margins include idle time, invalid checks and concurrent tiny text calls; request-window telemetry is separately identified.',
        'Alpha/transparency qualification remains NOT_TESTED. No PSS polling.'
    ]
    measured['limitations'] = limits
    generation_check = next(c for c in generate['checks'] if c['check'] == 'generation')
    readiness_after = next(c for c in reject['checks'] if c['check'] == 'readiness')
    output = {**release['output'], 'fully_decoded': True,
              'decode_evidence': 'Worker2 client png() performed Pillow verify/load; local compiler verified original PNG hash, not an additional decoder run.'}
    criteria = {'correct_decoded_output': output['width'] == output['height'] == 1024 and generation_check['status'] == 'LIVE_PASS',
                'device_free_at_least_5_percent': measured['device']['minimum_free_fraction'] >= .05 and full['device']['minimum_free_fraction'] >= .05,
                'host_available_at_least_15_percent': measured['host']['min_available_fraction'] >= .15 and full['host']['min_available_fraction'] >= .15,
                'container_swap_zero': measured['cgroup']['memory.swap.current']['max'] == full['cgroup']['memory.swap.current']['max'] == 0,
                'no_observed_swap_activity': all(measured['host']['vmstat_counter_deltas'][k] == full['host']['vmstat_counter_deltas'][k] == 0 for k in ('pswpin', 'pswpout')),
                'no_observed_host_oom': measured['host']['vmstat_counter_deltas']['oom_kill'] == full['host']['vmstat_counter_deltas']['oom_kill'] == 0,
                'tmp_cleanup': sampler['tmp_new_entries'] == [],
                'ready_and_owned_after': bool(sampler['residency_after']) and readiness_after['service']['busy'] is False and readiness_after['service']['ready'] is True and release['requests_in_flight'] is False,
                'one_generation': release['accepted_generation_count'] == 1,
                'zero_accepted_edits': release['accepted_edit_count'] == 0,
                'sampler_clean_exit': sampler['sampler_exit'] == 0}
    log_path = ROOT / 'artifacts/worker2-native-log.txt'
    clean_log = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', log_path.read_text())
    time_line = next(line for line in clean_log.splitlines() if '[09-23 04:09:59] Pixel data generated successfully' in line)
    peak_line = next(line for line in clean_log.splitlines() if '[09-23 04:09:59] Peak memory usage:' in line)
    native_seconds = float(re.search(r'successfully in ([0-9.]+) seconds', time_line).group(1))
    peak = float(re.search(r'usage: ([0-9.]+) MB', peak_line).group(1))
    settings = {**attempt['request'], 'num_inference_steps': 40, 'true_cfg_scale': 1, 'guidance_scale': 1, 'generator_device': 'cpu'}
    settings.pop('response_format', None)
    recipe_limit = {'status': 'ACCEPTED_INDEPENDENT_API_RECIPE', 'same_recipe_as_ladder': False,
                    'actual_seed': 20260923, 'ladder_seed': 42,
                    'basis': 'Actual attempt payload and native log; reviewed client defaults supply 40 steps, CFG1 and CPU noise RNG. No rerun authorized.'}
    receipts = [release_path, generate_path, attempt_path, reject_path, sampler_path, telemetry_path, deployment_path, note_path, log_path, SOURCE / 'client.py']
    normalized = {'schema_version': 1, 'campaign_id': deployment['campaign_id'], 'case_id': 'api-baseline-1024x1024',
                  'scope': 'independent_authenticated_api_baseline_not_same_recipe_ladder', 'operation': 'generation', 'references': 0,
                  'source_commit': release['source_commit'], 'session_id': release['session_id'],
                  'measurement_receipt': str(generate_path.relative_to(ROOT)), 'measurement_receipt_sha256': sha(generate_path),
                  'raw_client_status': generate['status'], 'raw_client_visual_status': release['statuses']['visual'],
                  'status': 'PARTIAL' if all(criteria.values()) else 'FAIL', 'numeric_criteria_pass': all(criteria.values()),
                  'profile_eligible': False, 'visual_verification': {'status': 'NOT_TESTED', 'overlay': 'visual-review.json'},
                  'caller': 'Worker2 sole accepted API image caller in authorized window',
                  'request_count': 1, 'accepted_generation_count': 1, 'accepted_edit_count': 0,
                  'request_settings': settings, 'recipe_comparison': recipe_limit,
                  'started_utc': release['generation_request_start_utc'], 'finished_utc': release['generation_request_end_utc_derived'],
                  'request_started_utc': release['generation_request_start_utc'], 'request_finished_utc': release['generation_request_end_utc_derived'],
                  'client_monotonic_bounds': release['generation_monotonic_bounds'],
                  'request_seconds': release['generation_monotonic_bounds'][1] - release['generation_monotonic_bounds'][0],
                  'timing_method': release['generation_end_method'], 'http_status': generation_check['http_status'],
                  'native_inference_seconds': native_seconds,
                  'native_allocator': {'available': False, 'perf_dump_available': False,
                                       'native_inference_seconds': native_seconds,
                                       'after_forward': {}, 'runtime_cumulative_peak': {},
                                       'reported_peak_reserved_mib': peak, 'peak_reserved_mib': peak, 'peak_allocated_mib': None,
                                       'source': 'Rounded current API-call native log, not deployment-warm perf dump.',
                                       'reported_label': 'Peak memory usage: 37406.00 MB',
                                       'interpretation': 'Reserved-memory interpretation follows pinned runtime/receipt semantics; log itself labels generic peak MB. No allocated peak is available.',
                                       'scope': 'Rounded native request log; reserved interpretation inferred from known pinned semantics; no per-request performance dump.',
                                       'log_receipt': ref(log_path), 'log_excerpts': [time_line, peak_line]},
                  'delivered_output': output, 'native_output': None,
                  'metrics': measured, 'metrics_full_shared_window': full, 'criteria': criteria,
                  'runtime_image_digest': deployment['runtime']['image_id'], 'runtime_source_commit': deployment['runtime']['source_commit'],
                  'runtime_config_sha256': deployment['file_sha256']['/data/services/image21-runtime-20260923/config.json'],
                  'checkpoint_revision': deployment['runtime']['checkpoint_revision'],
                  'checkpoint_receipt_sha256': deployment['runtime']['checkpoint_receipt_sha256'],
                  'container_id': sampler['container_id'], 'backend_run_id': sampler['backend_run_id'],
                  'gpu_uuid': sampler['residency_after']['device_current']['uuid'], 'residency_before': sampler['residency_before'], 'residency_after': sampler['residency_after'],
                  'tmp_before': sampler['tmp_before'], 'tmp_after': sampler['tmp_after'], 'tmp_new_entries': sampler['tmp_new_entries'],
                  'telemetry_file': str(telemetry_path.relative_to(ROOT)),
                  'recovery': {'attempted': False, 'required': False},
                  'editing_rejection': next(c for c in reject['checks'] if c['check'] == 'reject_edit'),
                  'concurrency_evidence': release['busy_and_text_evidence'],
                  'ownership_return': {'returned': True, 'requests_in_flight': False, 'released_utc': release['released_utc']},
                  'source_receipts': [ref(p) for p in receipts],
                  'evidence_sha256': {'generation.png': sha(png), 'telemetry.jsonl': sha(telemetry_path)}, 'limitations': limits}
    visual = {'status': 'PASS', 'reviewer': 'Root independent actual Worker2 PNG review',
              'method': 'Reuse exact root visual verdict; no new image call or substituted review.',
              'finding': 'Coherent red teapot/table/soft light; window not visible.',
              'prompt_scope': 'Actual Worker2 prompt requests plain cream background and does not request a window.',
              'sha256': sha(png), 'root_note': str(note_path.relative_to(ROOT)), 'root_note_sha256': sha(note_path),
              'raw_client_visual_status_preserved': 'NOT_TESTED'}
    OUTPUT.mkdir(exist_ok=True, parents=True)
    # Existing first-segment raw files remain intact. The actual request uses segment2.
    shutil.copyfile(png, OUTPUT / 'generation.png')
    write(OUTPUT / 'receipt.json', normalized); write(OUTPUT / 'visual-review.json', visual)
    REPORT.mkdir(parents=True, exist_ok=True)
    copy_names = ['client.py', 'SHA256-MANIFEST.json', 'LIVE-WINDOW-RESULT.md']
    copy_names += sorted(p.name for p in SOURCE.glob('LIVE-*.json'))
    for name in copy_names:
        shutil.copyfile(SOURCE / name, REPORT / name)
    shutil.copyfile(attempt_path, REPORT / 'baseline-generation.attempt.json')
    # Approval originals remain task-local with hashes, not duplicate repo transcripts.
    for omitted in ('COMMANDS.md', 'LIVE-AUTH-HANDOFF.md', 'LIVE-FOLLOWUP.md', 'ROOT-WORKER2-RESULT.md'):
        previous = REPORT / omitted
        if previous.is_file():
            previous.unlink()
    shutil.copyfile(OUTPUT / 'receipt.json', REPORT / 'normalized-baseline.json')
    shutil.copyfile(OUTPUT / 'visual-review.json', REPORT / 'visual-review.json')
    (REPORT / 'README.md').write_text('''# Worker2 independent API baseline

Exactly one authenticated 1024×1024 generation and zero accepted edits. Actual request: seed 20260923, studio red teapot against cream background; the generation ladder uses its separate seed 42 recipe. This is API acceptance, not a same-recipe performance comparison. Original client visual NOT_TESTED remains unchanged; task-local ROOT-WORKER2-RESULT.md supplies root visual PASS bound by filename/hash in visual-review.json.

The normalized receipt intersects the actual request's UTC interval with shared sampler segment2. It does not compare monotonic clocks across hosts. Request-window and full-window metrics are separate; end UTC is derived from the client monotonic duration, and cross-host UTC clock offset was not measured. Rounded native log time is 23.83 s and logged peak 37406.00 MB, interpreted as reserved under pinned runtime semantics. Native allocated peak is unavailable; no deployment-warm allocator result is borrowed.

Raw PNG and telemetry stay task-local outside Git. Their paths/hashes, original receipts, request settings, margins, spool checks, root visual evidence, concurrency checks and refused edit are bound in normalized-baseline.json. Original client SHA256-MANIFEST.json intentionally also references task-local PNG and duplicate timestamp receipts omitted from this compact copy. Optional bridge and delivery history are excluded. No new API/VM/image call was made by this normalization.
''')
    files = sorted(p for p in REPORT.iterdir() if p.is_file() and p.name != 'COPIED-FILES.sha256')
    (REPORT / 'COPIED-FILES.sha256').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files))
    print(json.dumps({'status': 'NORMALIZED_NUMERIC_PASS_ROOT_VISUAL_PASS' if all(criteria.values()) else 'FAIL',
                      'request_device_samples': len(samples), 'request_seconds': normalized['request_seconds'],
                      'native_seconds_rounded': native_seconds, 'sampled_peak_used_bytes': measured['device']['sampled_peak_used_bytes'],
                      'sampled_min_free_bytes': measured['device']['sampled_min_free_bytes'],
                      'minimum_free_fraction': measured['device']['minimum_free_fraction'],
                      'host_min_available_fraction': measured['host']['min_available_fraction'],
                      'receipt_sha256': sha(OUTPUT / 'receipt.json'), 'final_report_builder_run': False}))


if __name__ == '__main__':
    main()
