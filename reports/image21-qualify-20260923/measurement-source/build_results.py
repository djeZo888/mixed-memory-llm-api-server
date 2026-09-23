#!/usr/bin/env python3
"""Compile local IMAGE21 receipts without inference, VM access, or raw-body output.

Run only after the caller freezes final evidence. Default inputs are task-local.
--worker2-receipt can be repeated; unknown schemas are retained by path/hash and
cannot establish PASS. --worker2-baseline optionally supplies a normalized case
using the native receipt fields (criteria, metrics, output, timings), plus
measurement_receipt and measurement_receipt_sha256 pointing to the raw client
receipt. An overlay never replaces or edits the raw receipt.

Root profile review schema:
  {"root_note":"ROOT-....md", "root_note_sha256":"...",
   "approved_generation_sizes":["1024x1024", ...], "editing_supported":false}
Campaign closeout schema (optional, absence keeps campaign PARTIAL):
  {"ended_utc":"...", "stop_reason":"...", "final_source_commit":"...",
   "completion_criteria":{"all_models_warm":true, "lease_free":true, ...},
   "final_verification_receipt":"...", "remaining_work":[...]}
No root review or closing verification is inferred from filenames or prose.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

MIB = 1048576
STATES = {'PASS', 'FAIL', 'PARTIAL', 'NOT_TESTED'}
REQUIRED = ('correct_decoded_output', 'device_free_at_least_5_percent',
            'host_available_at_least_15_percent', 'container_swap_zero',
            'no_observed_swap_activity', 'no_observed_host_oom', 'tmp_cleanup',
            'ready_and_owned_after', 'one_generation')
LIMITS = ['NVML samples are total-device use, not allocator or process peaks.',
          'Peaks between nominal 200 ms device samples remain unobserved.',
          'Host/cgroup observations are nominally 1 s; no PSS polling.',
          'Native runtime peaks and cgroup memory.peak are lifetime high-water marks.',
          'CPU load snapshots and PCIe counters do not prove absence of transient activity.',
          'Missing evidence remains NOT_TESTED/PARTIAL; forecast is not measured support.']
SETTINGS = ('model', 'prompt', 'size', 'n', 'num_inference_steps', 'guidance_scale',
            'true_cfg_scale', 'seed', 'generator_device', 'output_format',
            'background', 'enable_teacache', 'enable_cache_dit')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def get(value, dotted, default=None):
    for key in dotted.split('.'):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def select(value, keys):
    return {k: value[k] for k in keys if k in value}


def status(value):
    value = str(value).upper()
    return value if value in STATES else 'PARTIAL'


def perf_summary(value):
    checkpoints = value.get('memory_checkpoints', {})
    return {'available': bool(checkpoints), 'reported_units': 'MiB (native *_mb uses binary divisor)',
            'native_inference_seconds': value.get('total_duration_ms', 0) / 1000
            if isinstance(value.get('total_duration_ms'), (int, float)) else None,
            'after_forward': select(checkpoints.get('after_forward', {}),
                                    ('allocated_mb', 'reserved_mb', 'peak_allocated_mb', 'peak_reserved_mb')),
            'load_peak': select(checkpoints.get('load_peak', {}), ('peak_allocated_mb', 'peak_reserved_mb')),
            'runtime_cumulative_peak': select(checkpoints.get('runtime_peak', {}),
                                              ('peak_allocated_mb', 'peak_reserved_mb')),
            'scope': 'after_forward is the native request checkpoint; runtime peaks accumulate across requests. Neither is NVML physical-device peak.'}


def qualification_artifacts(cases, runtime, model_id):
    """Stable case bytes exclude campaign/final-recovery headers and self hash."""
    files, profiles = {}, []
    for case in cases:
        if not case['profile_eligible']:
            continue
        if case['status'] != 'PASS' or not case.get('root_profile_review'):
            raise ValueError('Eligible case lacks passing/root-bound evidence')
        encoded = canonical({k: v for k, v in case.items() if k != 'evidence_sha256'})
        if hashlib.sha256(encoded).hexdigest() != case['evidence_sha256']:
            raise ValueError('Canonical case hash mismatch: ' + case['case_id'])
        files[case['case_id'] + '.json'] = encoded
        profiles.append({'operation': 'generation', 'size': case['requested_size'],
                         'native_size': case['planned_native_size'],
                         'crop_bottom': case['planned_crop_bottom'], 'references': 0,
                         'transparent': False, 'conditioning': '',
                         'evidence_sha256': case['evidence_sha256']})
    return files, {'schema_version': 1, 'runtime_revision': runtime['source_commit'],
                   'model_id': model_id, 'model_revision': runtime['checkpoint_revision'],
                   'runtime_image_digest': runtime['image_id'], 'profiles': profiles}


class Builder:
    def __init__(self, root):
        self.root = root.resolve()
        self.inputs = {}
        self.warnings = []
        self.root_profile_binding = None

    def path(self, name):
        path = Path(name)
        path = path if path.is_absolute() else self.root / path
        path = path.resolve()
        path.relative_to(self.root)  # Prevent accidentally reading outside this task.
        return path

    def record(self, path):
        path = self.path(path)
        value = {'path': str(path.relative_to(self.root)), 'sha256': sha(path), 'bytes': path.stat().st_size}
        self.inputs[value['path']] = value
        return value

    def load(self, name, required=False):
        if not name:
            return {}
        path = self.path(name)
        if not path.exists():
            if required:
                raise ValueError('Required local evidence absent: ' + str(path.relative_to(self.root)))
            return {}
        self.record(path)
        return json.loads(path.read_text())

    def bind(self, name, expected):
        if not name or not expected:
            return False
        path = self.path(name)
        if not path.is_file():
            return False
        return self.record(path)['sha256'] == expected

    def visual(self, path, output):
        review = self.load(path)
        if not review:
            return {'status': 'NOT_TESTED', 'hash_bound': False}
        expected = review.get('output_sha256', review.get('sha256'))
        bound = bool(expected and expected == output.get('sha256'))
        return {**select(review, ('status', 'reviewer', 'method', 'finding', 'observation', 'scope', 'root_note', 'root_note_sha256')),
                'hash_bound': bound, 'output_sha256': expected, 'receipt': self.record(path)}

    def case(self, plan, path, approved, override=None):
        case = {'case_id': plan['case_id'], 'rung': plan.get('rung'),
                'scope': plan.get('scope', 'direct_native_ladder'), 'operation': 'generation',
                'references': 0, 'status': 'NOT_TESTED', 'profile_eligible': False,
                'requested_size': f"{plan['delivered_width']}x{plan['delivered_height']}",
                'planned_native_size': f"{plan['native_width']}x{plan['native_height']}",
                'planned_crop_bottom': plan.get('crop_bottom', 0),
                'authorization': plan.get('authorization'),
                'delivered_output': None, 'actual_native_output': None,
                'criteria': {}, 'visual': {'status': 'NOT_TESTED', 'hash_bound': False}}
        raw = override if override is not None else self.load(path)
        if not raw:
            case['not_tested_reason'] = 'No completed measurement receipt supplied.'
            return case
        path = self.path(path)
        receipt = self.record(path)
        if raw.get('case_id') not in (None, plan['case_id']):
            raise ValueError('Case ID mismatch: ' + plan['case_id'])
        case.update({'raw_status': raw.get('status'), 'measurement_receipt': receipt,
                     'caller': raw.get('caller', 'Worker2 independent authenticated API client' if plan.get('scope') == 'api_baseline' else None),
                     'request_count': raw.get('request_count', raw.get('http_call_count')),
                     'request_settings': select(raw.get('request_settings', raw.get('settings', {})), SETTINGS),
                     'recipe_comparison': raw.get('recipe_comparison'),
                     'criteria': dict(raw.get('criteria', {})), 'metrics': raw.get('metrics', {}),
                     'metrics_full_shared_window': raw.get('metrics_full_shared_window'),
                     'source_receipts': raw.get('source_receipts', []),
                     'recovery': raw.get('recovery', {'status': 'NOT_TESTED'}),
                     'predicted_next_demand': raw.get('predicted_next_demand'),
                     'failure': raw.get('failure'),
                     'http_status': raw.get('http_status'),
                     'http_request_seconds': raw.get('request_seconds', raw.get('http_elapsed_seconds')),
                     'native_response_metrics': raw.get('native_response_metrics', {}),
                     'timing': select(raw, ('started_utc', 'finished_utc', 'started_monotonic', 'finished_monotonic',
                                           'request_started_utc', 'request_finished_utc', 'request_started_monotonic', 'request_finished_monotonic')),
                     'runtime_identity': select(raw, ('source_commit', 'runtime_source_commit', 'runtime_image_digest',
                                                       'runtime_config_sha256', 'checkpoint_revision', 'checkpoint_receipt_sha256',
                                                       'container_id', 'backend_run_id', 'gpu_uuid', 'api_state')),
                     'cpu_load_snapshots': select(raw, ('load_average_before', 'load_average_after')),
                     'tmp': {'new_entries': raw.get('tmp_new_entries'),
                             'before_count': len(raw['tmp_before']['entries']) if 'tmp_before' in raw else None,
                             'after_count': len(raw['tmp_after']['entries']) if 'tmp_after' in raw else None},
                     'residency_after': raw.get('residency_after'),
                     'raw_artifact_sha256': raw.get('evidence_sha256', {})})
        output = raw.get('delivered_output', raw.get('output', {})) or {}
        native = raw.get('native_output', {}) or {}
        case['delivered_output'], case['actual_native_output'] = output or None, native or None
        correct_dimensions = output.get('width') == plan['delivered_width'] and output.get('height') == plan['delivered_height']
        if 'size' in output:
            correct_dimensions = output['size'] == [plan['delivered_width'], plan['delivered_height']]
        case['criteria']['correct_decoded_output'] = bool(correct_dimensions and output.get('sha256')
                                                        and output.get('fully_decoded') is True)
        if plan.get('scope') != 'api_baseline':
            case['criteria']['native_dimensions_and_crop_verified'] = (
                native.get('width') == plan['native_width'] and native.get('height') == plan['native_height']
                and native.get('fully_decoded') is True and raw.get('crop_bottom') == plan.get('crop_bottom', 0))
        case['visual'] = self.visual(path.parent / 'visual-review.json', output)
        for name in ('generation.png', 'native.png', 'telemetry.jsonl', 'native-perf.json'):
            artifact = self.path(raw['telemetry_file']) if name == 'telemetry.jsonl' and raw.get('telemetry_file') else path.parent / name
            if artifact.is_file():
                observed = self.record(artifact)
                recorded = raw.get('evidence_sha256', {}).get(name)
                if recorded and recorded != observed['sha256']:
                    raise ValueError('Artifact hash mismatch: ' + observed['path'])
        png = path.parent / 'generation.png'
        if png.is_file() and output.get('sha256') != sha(png):
            raise ValueError('Decoded output hash mismatch: ' + str(png))
        perf_path = path.parent / 'native-perf.json'
        perf = perf_summary(self.load(perf_path))
        if not perf['available'] and raw.get('native_allocator'):
            perf = raw['native_allocator']
        case['native_allocator'] = perf
        case['native_inference_seconds'] = perf.get('native_inference_seconds')
        if case['native_inference_seconds'] is None:
            case['native_inference_seconds'] = raw.get('native_inference_seconds', get(raw, 'native_response_metrics.inference_time_s'))
        numeric = (raw.get('numeric_criteria_pass') is True
                   and all(case['criteria'].get(k) is True for k in REQUIRED)
                   and case['criteria'].get('native_dimensions_and_crop_verified', True) is True)
        case['criteria']['visual_task_success'] = case['visual'].get('status') == 'PASS' and case['visual']['hash_bound']
        case['criteria']['recorded_numeric_criteria_complete'] = numeric
        # An overlay cannot turn an observed failure into a pass.
        failed = status(raw.get('status')) == 'FAIL' or raw.get('numeric_criteria_pass') is False or any(v is False for v in raw.get('criteria', {}).values()) or case['visual'].get('status') == 'FAIL'
        case['status'] = 'FAIL' if failed else ('PASS' if numeric and case['criteria']['visual_task_success'] else 'PARTIAL')
        if plan.get('scope') == 'api_baseline' and override is not None:
            binding = self.bind(raw.get('measurement_receipt'), raw.get('measurement_receipt_sha256'))
            case['criteria']['raw_client_receipt_binding'] = binding
            if not binding and case['status'] == 'PASS':
                case['status'] = 'PARTIAL'
        case['root_approved_size'] = case['requested_size'] in approved
        case['root_profile_review'] = self.root_profile_binding
        case['profile_eligible'] = case['status'] == 'PASS' and case['root_approved_size']
        case['limitations'] = list(dict.fromkeys(LIMITS + raw.get('limitations', []) + raw.get('metrics', {}).get('limitations', [])))
        case['evidence_sha256'] = hashlib.sha256(canonical(case)).hexdigest()
        return case

    def warm(self, deployment, directory, role):
        warm = deployment.get('warm_receipt', {})
        generation = warm.get('generation', {})
        if not generation:
            return {'case_id': role, 'scope': 'required_deployment_recovery_not_benchmark', 'status': 'NOT_TESTED'}
        output = generation.get('output', {})
        visual = self.visual(self.path(directory) / 'visual-review.json', output)
        perf = perf_summary(self.load(self.path(directory) / 'generation-perf.json'))
        for name in ('generation.png', 'telemetry.jsonl'):
            path = self.path(directory) / name
            if path.is_file():
                self.record(path)
        return {'case_id': role, 'scope': 'required_deployment_recovery_not_benchmark',
                'status': 'PASS' if str(generation.get('status')).upper() == 'PASS' and visual.get('status') == 'PASS' and visual['hash_bound'] else 'PARTIAL',
                'profile_eligible': False, 'request_count': generation.get('http_call_count'),
                'requested_size': generation.get('settings', {}).get('size'),
                'started_utc': warm.get('start_utc'), 'finished_utc': warm.get('completed_utc'),
                'native_ready_seconds': warm.get('native_ready_seconds'),
                'http_request_seconds': generation.get('http_elapsed_seconds'),
                'native_inference_seconds': generation.get('native_inference_seconds'),
                'native_allocator': perf, 'delivered_output': output, 'visual': visual,
                'sampled_metrics': select(warm, ('telemetry_summary', 'sampled_max_cgroup_swap_bytes', 'sampled_min_host_available_bytes')),
                'evidence_limit': 'Required recovery plus load/warm sampling; never counted as Worker2 API baseline or a ladder case.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--task-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', default='repo/reports/image21-qualify-20260923')
    parser.add_argument('--worker2-receipt', action='append', default=[])
    parser.add_argument('--worker2-baseline')
    parser.add_argument('--root-review', default='artifacts/root-profile-review.json')
    parser.add_argument('--campaign-closeout')
    parser.add_argument('--final-deployment-receipt')
    parser.add_argument('--final-warm-directory', default='artifacts/final-deployment-warm')
    parser.add_argument('--check-inputs', action='store_true', help='Validate and print compact summary without writing reports.')
    args = parser.parse_args()
    b = Builder(args.task_root)
    deployment = b.load('DEPLOYMENT-RECEIPT.json', required=True)
    source = b.load('SOURCE-RECEIPT.json', required=True)
    frozen = b.load('qualification-tools/frozen-ladder.json', required=True)
    contract = b.load('repo/reports/image21-runtime-20260923/BACKEND-CONTRACT.json', required=True)
    root_review = b.load(args.root_review)
    approved = []
    if root_review:
        if root_review.get('editing_supported') is not False:
            raise ValueError('Root review must preserve editing_supported=false')
        if not b.bind(root_review.get('root_note'), root_review.get('root_note_sha256')):
            raise ValueError('Root review note hash missing or mismatched')
        approved = root_review.get('approved_generation_sizes', [])
        b.root_profile_binding = {'review_receipt': b.record(args.root_review),
                                  'root_note': root_review['root_note'],
                                  'root_note_sha256': root_review['root_note_sha256']}
    closeout = b.load(args.campaign_closeout)
    baseline_plan = {'case_id': 'api-baseline-1024x1024', 'scope': 'api_baseline',
                     'delivered_width': 1024, 'delivered_height': 1024, 'native_width': 1024, 'native_height': 1024}
    client_receipts = []
    for path in args.worker2_receipt:
        value = b.load(path, required=True)
        client_receipts.append({'receipt': b.record(path), 'reported_summary': select(value, ('status', 'session_id', 'started_utc', 'finished_utc', 'editing'))})
    baseline_path = args.worker2_baseline or 'artifacts/worker2-baseline/receipt.json'
    baseline_raw = b.load(baseline_path)
    baseline = b.case(baseline_plan, baseline_path, approved, override=baseline_raw if baseline_raw else None)
    cases = [b.case(plan, f"artifacts/ladder/{plan['case_id']}/receipt.json", approved) for plan in frozen['cases']]
    refinement = None
    refinement_note = b.path('ROOT-FINAL-REFINEMENT.md')
    refinement_path = 'artifacts/ladder/refinement-1920x1088/receipt.json'
    if refinement_note.is_file() or b.path(refinement_path).is_file():
        if not refinement_note.is_file():
            raise ValueError('Additional refinement receipt lacks exact root authorization note')
        refinement_plan = {'case_id': 'refinement-1920x1088', 'scope': 'additional_root_authorized_refinement_beyond_frozen_ladder',
                           'delivered_width': 1920, 'delivered_height': 1088,
                           'native_width': 1920, 'native_height': 1088, 'crop_bottom': 0,
                           'authorization': {'note': b.record(refinement_note),
                                             'boundary': 'Exactly one additional 1920x1088 generation if forecast safe; then stop all tests. Frozen planned r05 remains NOT_TESTED.'}}
        refinement = b.case(refinement_plan, refinement_path, approved)
    recovery = [b.warm(deployment, 'artifacts/deployment-warm', 'initial-deployment-recovery')]
    final_deployment = b.load(args.final_deployment_receipt)
    if final_deployment:
        recovery.append(b.warm(final_deployment, args.final_warm_directory, 'final-deployment-recovery'))
    all_cases = [baseline] + cases + ([refinement] if refinement else [])
    passing = [case for case in all_cases if case['status'] == 'PASS']
    highest = max(passing, key=lambda c: int(c['requested_size'].split('x')[0]) * int(c['requested_size'].split('x')[1]), default=None)
    highest_ladder = max((case for case in cases if case['status'] == 'PASS'), key=lambda c: c['rung'], default=None)
    measured = [case for case in cases if case['status'] != 'NOT_TESTED']
    stop_reason = closeout.get('stop_reason')
    if not stop_reason:
        stop_reason = get(measured[-1], 'predicted_next_demand.decision') if measured else 'NO_LADDER_RECEIPT_SUPPLIED'
        stop_reason = stop_reason or 'CLOSEOUT_NOT_SUPPLIED'
        if refinement and refinement['status'] != 'NOT_TESTED':
            stop_reason = 'ROOT_DIRECTED_STOP_AFTER_SINGLE_REFINEMENT'
    complete = closeout.get('completion_criteria', {})
    campaign_status = 'FAIL' if any(c['status'] == 'FAIL' for c in all_cases) else 'PARTIAL'
    tested_cases = [c for c in all_cases if c['status'] != 'NOT_TESTED']
    if (campaign_status != 'FAIL' and baseline['status'] == 'PASS' and measured
            and all(c['status'] == 'PASS' and c['profile_eligible'] for c in tested_cases)
            and complete and all(v is True for v in complete.values()) and closeout.get('ended_utc')):
        campaign_status = 'PASS'
    runtime = deployment['runtime']
    header = {'schema_version': 1, 'campaign_id': deployment['campaign_id'], 'session_id': deployment['session_id'],
              'source_commit': closeout.get('final_source_commit', deployment['source_commit']),
              'deployed_source_commit': (final_deployment or deployment).get('source_commit'),
              'combined_source': source, 'started_utc': get(deployment, 'warm_receipt.start_utc'),
              'ended_utc': closeout.get('ended_utc'), 'status': campaign_status, 'stop_reason': stop_reason,
              'runtime': runtime, 'runtime_dependency_receipts': {},
              'model': {'id': deployment['capabilities']['model_id'], 'revision': runtime['checkpoint_revision'],
                        'checkpoint_manifest_sha256': runtime['checkpoint_receipt_sha256']},
              'immutable_config_and_unit_helper_hashes': deployment['file_sha256'],
              'resources': {'gpu_uuid': get(deployment, 'residency.device_current.uuid'),
                            'observed_device_total_bytes': get(deployment, 'residency.device_current.total_bytes'),
                            'host_total_bytes': get(deployment, 'residency.host_current.MemTotal'),
                            'accepted_resource_policy': contract['resource_policy'],
                            'resource_policy_evidence': 'Accepted runtime BACKEND-CONTRACT.json; current deployment identities in DEPLOYMENT-RECEIPT.json.',
                            'driver': closeout.get('driver'), 'pcie_bus': closeout.get('pcie_bus'),
                            'numa_policy': closeout.get('numa_policy'),
                            'missing_hardware_fields': 'null means not supplied/currently verified by this aggregation'},
              'settings': {**contract['runtime_policy'], 'prompt': get(deployment, 'warm_receipt.generation.settings.prompt')},
              'telemetry': {'requested_device_interval_seconds': 0.2, 'requested_host_interval_seconds': 1,
                            'native_allocator_source_keys': ['memory_checkpoints.after_forward.peak_allocated_mb', 'memory_checkpoints.after_forward.peak_reserved_mb'],
                            'source_sha256': runtime['source_sha256']['telemetry.py'], 'limitations': LIMITS},
              'contracts': {}, 'endpoints': deployment['endpoints'],
              'caller_windows': {'baseline': 'Worker2 exclusive authenticated API baseline', 'ladder': 'Worker1 sole native caller with API stopped',
                                'final': closeout.get('final_caller_owner', 'NOT_TESTED')},
              'root_profile_review': root_review or {'status': 'NOT_TESTED'},
              'advertised_profiles_at_initial_deployment': deployment['capabilities']['profiles'],
              'advertised_profiles_at_final_deployment': get(final_deployment, 'capabilities.profiles'),
              'measurement_policy': 'No source body, request auth or base64 response is emitted. Raw receipts are unchanged.'}
    for path in ('API-CONTRACT.md', 'QUALIFICATION-HANDOFF-CONTRACT.md', 'ROOT-GO.md'):
        if b.path(path).is_file():
            header['contracts'][path] = b.record(path)
    for name in ('requirements.freeze.txt', 'python-dependency-inventory.json', 'pip-archive-hashes.json', 'build-reproducibility.json', 'derived-image-receipt.json'):
        path = 'repo/reports/image21-runtime-20260923/' + name
        if b.path(path).is_file():
            header['runtime_dependency_receipts'][name] = b.record(path)
    header['runtime_dependency_limit'] = '35 inherited distribution archive hashes unavailable; immutable image and frozen versions retained.'
    if closeout.get('final_verification_receipt'):
        b.load(closeout['final_verification_receipt'], required=True)
    uhd = next(c for c in cases if c['requested_size'] == '3840x2160')
    report = {'header': header, 'separate_api_baseline': baseline, 'ladder_cases': cases,
              'additional_refinement': refinement,
              'required_deployment_recoveries': recovery, 'worker2_receipts': client_receipts,
              'highest_passing_generation_size': highest['requested_size'] if highest else None,
              'highest_passing_ladder_size': highest_ladder['requested_size'] if highest_ladder else None,
              'eligible_generation_sizes': [c['requested_size'] for c in all_cases if c['profile_eligible']],
              'unmeasured_rungs': [c['requested_size'] for c in cases if c['status'] == 'NOT_TESTED'],
              'uhd_mapping': {'status': 'NOT_TESTED'} if uhd['status'] == 'NOT_TESTED' else
              {'status': uhd['status'], 'planned_native': '3840x2176', 'delivered': uhd['delivered_output'],
               'actual_native': uhd['actual_native_output'], 'crop_bottom_rows': 16},
              'editing': {'status': 'UNSUPPORTED_AFTER_FAILED_FIDELITY', 'qualified_profiles': [],
                          'two_reference': 'UNSUPPORTED_NOT_TESTED', 'transparency': 'UNSUPPORTED_NOT_TESTED',
                          'evidence': 'reference/REJECTED-EDITING.json'},
              'completion': closeout or {'status': 'NOT_TESTED', 'remaining_work': ['Final closeout and service verification not supplied.']},
              'artifact_manifest': sorted(b.inputs.values(), key=lambda v: v['path'])}
    case_files, qualification = qualification_artifacts(all_cases, runtime, deployment['capabilities']['model_id'])
    if args.check_inputs:
        print(json.dumps({'status': campaign_status, 'measured_ladder_cases': len(measured),
                          'highest_passing_generation_size': report['highest_passing_generation_size'],
                          'writes': 0, 'root_review_supplied': bool(root_review)}))
        return
    out = b.path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    qualified_dir = out / 'qualified-cases'
    for name, encoded in case_files.items():
        previous = qualified_dir / name
        if previous.exists() and previous.read_bytes() != encoded:
            raise ValueError('Previously finalized case changed; preserve/review before replacement: ' + name)
    qualified_dir.mkdir(exist_ok=True)
    for name, encoded in case_files.items():
        (qualified_dir / name).write_bytes(encoded)
    (out / 'qualification.json').write_bytes(canonical(qualification) + b'\n')
    (out / 'resolution-results.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    fields = ('case_id', 'scope', 'status', 'requested_size', 'planned_native_size', 'http_request_seconds',
              'native_inference_seconds', 'sampled_peak_used_bytes', 'sampled_min_free_bytes',
              'native_peak_allocated_mib', 'native_peak_reserved_mib', 'visual_status', 'profile_eligible', 'output_sha256')
    with (out / 'resolution-results.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); writer.writeheader()
        for case in recovery + all_cases:
            row = {k: case.get(k) for k in fields}
            row.update(sampled_peak_used_bytes=get(case, 'metrics.device.sampled_peak_used_bytes', get(case, 'sampled_metrics.telemetry_summary.sampled_max_used_bytes')),
                       sampled_min_free_bytes=get(case, 'metrics.device.sampled_min_free_bytes', get(case, 'sampled_metrics.telemetry_summary.sampled_min_free_bytes')),
                       native_peak_allocated_mib=get(case, 'native_allocator.after_forward.peak_allocated_mb', get(case, 'native_allocator.peak_allocated_mib')),
                       native_peak_reserved_mib=get(case, 'native_allocator.after_forward.peak_reserved_mb', get(case, 'native_allocator.peak_reserved_mib')),
                       visual_status=get(case, 'visual.status'), output_sha256=get(case, 'delivered_output.sha256'))
            writer.writerow(row)
    text = [f"# {header['campaign_id']} — {campaign_status}", '',
            f"Highest passing generation: **{report['highest_passing_generation_size'] or 'none recorded'}**. Editing remains **unsupported after failed fidelity**.", '',
            f"Stop reason: `{stop_reason}`. Unmeasured rungs: {', '.join(report['unmeasured_rungs']) or 'none'}.", '',
            '| Case | Delivered | Native | Status | Request s | Native s | Device peak MiB | Min free MiB | Min free % |',
            '|---|---|---|---|---:|---:|---:|---:|---:|']
    def number(value): return f'{value:.3f}' if isinstance(value, (int, float)) else 'N/A'
    for case in all_cases:
        peak = get(case, 'metrics.device.sampled_peak_used_bytes')
        free = get(case, 'metrics.device.sampled_min_free_bytes')
        fraction = get(case, 'metrics.device.minimum_free_fraction')
        text.append(f"| {case['case_id']} | {case['requested_size']} | {case['planned_native_size']} | {case['status']} | {number(case.get('http_request_seconds'))} | {number(case.get('native_inference_seconds'))} | {number(peak / MIB if peak is not None else None)} | {number(free / MIB if free is not None else None)} | {number(fraction * 100 if fraction is not None else None)} |")
    text += ['', 'Dimensions on NOT_TESTED rows are frozen targets, not decoded outputs. MiB = 2²⁰ bytes; GiB = 2³⁰ bytes.']
    prediction = get(measured[-1], 'predicted_next_demand') if measured else None
    if prediction and prediction.get('predicted_device_used_bytes') is not None:
        text += ['', f"Next-rung forecast for {prediction.get('next_public_size')} (native {prediction.get('next_native_size')}): **{prediction['predicted_device_used_bytes'] / 2**30:.3f} GiB** device use versus **{prediction['maximum_allowed_used_bytes'] / 2**30:.3f} GiB** allowed; `{prediction.get('decision')}`. This is a forecast, not measured support."]
    text += ['', f"Root-approved eligible sizes: {', '.join(report['eligible_generation_sizes']) or 'none recorded'}.", '',
             f"Deployed code `{header['deployed_source_commit'] or header['source_commit']}`; runtime `{runtime['source_commit']}`; image `{runtime['image_id']}`; checkpoint `{runtime['checkpoint_revision']}`.", '',
             'The Worker2 square API baseline is separate from the native ladder. Required deployment recoveries are recorded separately and excluded from benchmark case counts. Device samples are physical-device totals; native allocated and reserved peaks are separate, with lifetime limits retained. Missing final checks are not claimed.', '',
             'Worker2 used its reviewed studio-teapot prompt and seed 20260923; the ladder and deployment warm use seed 42. Baseline native time 23.83 s and reserved peak 37406 MiB come from a rounded backend log; allocated peak is unavailable. This is not a same-recipe benchmark comparison.', '',
             f"API: `{deployment['endpoints']['private']}`; authenticated `POST /v1/images/generations` and `GET /v1/image-capabilities`. Clients read the existing protected key through the approved loader, keeping its value out of argv/environment/logs. Exact client and acceptance evidence: [worker2-client/client.py](worker2-client/client.py), [worker2-client/README.md](worker2-client/README.md); API contract: [image API](../../docs/image-api.md). Valid edits are refused as unqualified; no edit or transparency profile is enabled.", '',
             'Exact criteria, hashes, host/cgroup/swap evidence, forecasts, root review, native/delivered dimensions and remaining work: [resolution-results.json](resolution-results.json). Rejected editing findings: [reference/README.md](reference/README.md).', '']
    if refinement:
        text += ['The separate 1920×1088 case is the single root-authorized refinement beyond the frozen ladder. It does not replace planned r05 (2112×1184); all tests stop after this bounded refinement, regardless of outcome.', '']
    (out / 'RESULT.md').write_text('\n'.join(text))
    # Reproducibility copies only: these are task measurement tools, not deployed runtime source.
    repro = out / 'measurement-source'; repro.mkdir(exist_ok=True)
    for name in ('native_rung.py', 'worker2_sampler.py', 'frozen-ladder.json'):
        path = b.path('qualification-tools/' + name)
        shutil.copyfile(path, repro / name)
    shutil.copyfile(Path(__file__), repro / 'build_results.py')
    normalizer = b.path('reporting/normalize_worker2.py')
    if normalizer.is_file():
        shutil.copyfile(normalizer, repro / normalizer.name)
    (out / 'artifact-manifest.json').write_text(json.dumps({'schema_version': 1, 'files': report['artifact_manifest']}, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': campaign_status, 'output_directory': str(out),
                      'highest_passing_generation_size': report['highest_passing_generation_size'],
                      'measured_ladder_cases': len(measured)}))


if __name__ == '__main__':
    main()
