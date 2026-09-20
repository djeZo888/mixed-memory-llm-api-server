"""Closed candidate proof before production acceptance. PREP is strictly offline.

Only the two shipped declarations and small fixed request bodies are admitted.
No production receipt, migration, arbitrary launch input, fitter or measurement
retry exists here. Root stamps the <=20 minute clock in a future fresh RUN GO.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import stat
import threading
import time
from types import SimpleNamespace

from . import accounting, client, fixtures, glmrepair, profiles, runner, worker_verify
from .concurrent_run import restore_and_finalize
from .lifecycle import require

SCOPE = 'candidate-pair-validation'
CAMPAIGN = 'benchrun-candidate-pair-20260920'
GIB = 1024**3
POLICY = {'maximum_budget_seconds': 1200, 'clock_starts': 'RUN_DISPATCH',
          'includes_load_warmup_checks': True, 'excludes_source_prep': True,
          'restoration_outside_budget': True, 'maximum_input_tokens': 4096,
          'output_cap': 256, 'retry': False}


def fixed_samples():
    samples = {p + '-' + kind: fixtures.build_sample(alias, 12, 'candidate-fixed-1729',
            'candidate-' + p + '-' + kind, kind='tool' if kind == 'tool' else 'retrieval')
            for p, alias in [('G1', 'glm-5.3'), ('Q1', 'qwen3.8-27b')]
            for kind in ('warmup', 'smoke', 'tool')}
    for placement in ('G1', 'Q1'):
        samples[placement + '-smoke']['body']['response_format'] = {
            'type': 'json_schema', 'json_schema': {'name': 'candidate_retrieval', 'strict': True,
                'schema': {'type': 'object', 'properties': {key: {'type': 'string'} for key in fixtures.MARKERS},
                           'required': list(fixtures.MARKERS), 'additionalProperties': False}}}
    return samples


def serialize_sample(placement, kind, sample):
    require(sample == fixed_samples().get(placement + '-' + kind), 'candidate_fixed_sample_changed')
    scaffold = copy.deepcopy(sample)
    if kind == 'smoke':
        del scaffold['body']['response_format']
    fixtures.serialize_validate(scaffold)
    # Native counting, transport and persisted request all consume THESE bytes,
    # including the exact schema, with no answer constants in its constraints.
    return fixtures.canonical(sample['body'])


def validate_clock(armed, runtime):
    start, end, seconds = (runtime.get(k) for k in ('start_epoch', 'deadline_epoch', 'budget_seconds'))
    require(armed.get('runtime_policy') == POLICY and
            all(type(v) in (int, float) and math.isfinite(v) for v in (start, end)) and
            type(seconds) is int and 0 < seconds <= 1200 and start > 0 and end == start + seconds and
            set(runtime) == {'start_epoch', 'deadline_epoch', 'budget_seconds'}, 'candidate_dispatch_clock_required')
    return start, end


def bind_runtime(armed, go, session, now):
    runtime = go.get('runtime', {})
    start, end = validate_clock(armed, runtime)
    require(start <= now < end and go.get('run_session_id') == session and session and
            session != armed.get('session_id'), 'candidate_fresh_session_clock_required')
    return copy.deepcopy(runtime)


def auth_fixture_module():
    path = profiles.ROOT / 'tests/lifecycle/sglang38_fixture/run_pair_fixture.py'
    spec = importlib.util.spec_from_file_location('candidate_auth_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity_stamp(host, cid):
    container, group, pids = host.identity(cid)
    return {'id': container['Id'], 'name': container['Name'], 'image_id': container['Image'],
            'labels': container['Config']['Labels'], 'pid': container['State']['Pid'],
            'started_at': container['State']['StartedAt'], 'cgroup': str(group),
            'process_generations': {str(pid): Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
                                    for pid in pids}}


def memory_obligations(sample, manifests):
    """Credit resident disjoint anon + no-swap shmem once; retain BOTH full caps."""
    credits = {}
    for cid, group in sample['cgroups'].items():
        m = manifests[cid]
        anon, shmem, file = (group.get(k) for k in ('anon_bytes', 'shmem_bytes', 'file_bytes'))
        require(all(type(v) is int and v >= 0 for v in (anon, shmem, file)) and shmem <= file
                and group.get('swap_bytes') == 0, 'candidate_resident_credit_unavailable')
        placement = m['placement']
        require(placement not in credits, 'candidate_duplicate_resident')
        cap = 640 * GIB if placement == 'G1' else 32 * GIB
        require(anon + shmem <= cap, 'candidate_resident_credit_exceeds_cap')
        credits[placement] = anon + shmem
    required = 16 * GIB + sum(cap - credits.get(p, 0) for p, cap in [('G1', 640 * GIB), ('Q1', 32 * GIB)])
    available = sample['host'].get('available_bytes')
    require(type(available) is int and available >= required, 'candidate_remaining_caps_host_reserve_failed')
    return {'host_available_bytes': available, 'required_host_available_bytes': required,
            'resident_nonreclaimable_bytes': credits, 'basis': 'fixed_caps_minus_resident_anon_plus_shmem_once_plus_16GiB'}


def admission(host, *, sample=None):
    from .host import collect_sample, command
    cp, _ = profiles.candidate_modules()
    require(host.scope == SCOPE and not host.concurrent_resource_violations, 'candidate_resource_failure_latched')
    cp.validate_gpu_inventory(command(['nvidia-smi', '--query-gpu=index,uuid', '--format=csv,noheader,nounits'], 5).stdout.decode())
    ids = [r['resource']['id'] for r in host.owner.resources if r['state'] != 'REMOVED']
    before = {cid: identity_stamp(host, cid) for cid in ids}
    if sample is None:
        identities = {cid: host.identity(cid) for cid in ids}
        sample = collect_sample({cid: v[1] for cid, v in identities.items()},
                                pids={cid: v[2] for cid, v in identities.items()})
    require(set(sample['cgroups']) == set(ids), 'candidate_resident_inventory_mismatch')
    result = memory_obligations(sample, host.load_manifests)
    gpus = {g['uuid']: g for g in sample['gpus']}
    require(set(gpus) == set(cp.GPU_UUIDS), 'candidate_gpu_inventory_unavailable')
    result['gpu'] = {}
    for p, uuid in zip(('G1', 'Q1'), cp.GPU_UUIDS):
        total, free = (gpus[uuid].get(k) for k in ('total_bytes', 'free_bytes'))
        require(type(total) is int and type(free) is int and 16 * GIB <= free <= total,
                'candidate_gpu_reserve_failed')
        require(p != 'Q1' or free * 10 >= total, 'candidate_qwen_ten_percent_reserve_failed')
        result['gpu'][uuid] = {'free_bytes': free, 'total_bytes': total,
                              'reserve_16GiB': True, 'ten_percent_comparison': free * 10 >= total}
    require(before == {cid: identity_stamp(host, cid) for cid in ids}, 'candidate_sampling_identity_changed')
    result['identities'] = before
    return result


def native_proof(host, cid, info=None):
    """Actual native capacity and resolving view; never substitute declared argv."""
    cp, _ = profiles.candidate_modules()
    manifest = host.load_manifests[cid]
    d = profiles.candidate_profile(manifest['placement'], host.binding)
    before = identity_stamp(host, cid)
    result = cp.native_capacity(d, timeout=min(5, host.budget.checkpoint()))
    if manifest['placement'] == 'Q1':
        require(isinstance(info, dict) and isinstance(info.get('server_args'), dict), 'candidate_native_resolving_view_unavailable')
        pair = profiles.candidate_pair_wrapper()
        base = pair.pinned_base(profiles.ROOT / 'scripts/runtime/sglang38_file_auth.py')
        pair.bind_variant(base)
        args = copy.deepcopy(info['server_args'])
        graph = args.get('cuda_graph_config')
        if isinstance(graph, dict):
            args['cuda_graph_config'] = SimpleNamespace(**{k: SimpleNamespace(**v) if isinstance(v, dict) else v for k, v in graph.items()})
        base.validate_server_args(SimpleNamespace(**args), resolved=True)
        result['native_arguments_basis'] = 'actual_native_resolving_view_validated_by_exact_pair_wrapper'
        result['resolved_fields_sha256'] = fixtures.digest(fixtures.canonical(info['server_args']))
    require(before == identity_stamp(host, cid), 'candidate_native_identity_changed')
    result['identity'] = before
    return result


def preserve(host):
    """Private protected copy before lifecycle changes; never a production write."""
    from .host import protected
    paths = {'state': host.manager.state_file, 'recovery': host.manager.recovery_file,
             'instance': host.binding.path('data', 'services/llm-manager/deployment-instance.json'),
             'control_journal': host.binding.path('data', 'services/llm-control/operations.json'),
             'source_closure': '/usr/local/lib/llm-server/control-api.manifest.json',
             'storage': '/etc/local-ai-server/storage.json'}
    receipt = {}
    for name, path in paths.items():
        try:
            raw, metadata = protected(path, private=name != 'source_closure')
        except FileNotFoundError:
            require(name == 'recovery', 'candidate_preservation_required')
            receipt[name] = {'status': 'ABSENT'}
            continue
        host.write_bytes('preserved/' + name + '.json', raw)
        receipt[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'metadata': metadata}
    host.write_json('preserved/receipt.json', receipt)


class Validation(runner.Campaign):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interrupted = threading.Event()
        self.proofs, self.counts = {}, {}

    def boundary(self):
        glmrepair.checkpoint(self.state)
        require(not self.interrupted.is_set(), 'candidate_interrupted_drain_restore')
        self.collect()
        require(not self.safety, 'candidate_resource_or_observation_failure')

    def warm(self, cid, manifest, proof):
        # loaded() invokes this; defer actual warmup until BOTH are resident.
        self.proofs[cid] = proof

    def counter(self, cid):
        m = self.active[cid]['manifest']
        alias = 'glm-5.3' if m['placement'] == 'G1' else 'qwen3.8-27b'
        def call(route, body):
            timeout = self.admission(cid, 120)
            try:
                return self.json_factory('http://127.0.0.1:' + str(m['transport']['port'] + 1000), self.key, timeout=timeout)(route, body)
            finally:
                self.host.call('request_end', id=cid)
        native = accounting.native_counter(alias, m['configured_capacity'], call,
                  qwen_template_sha256=self.active[cid]['template_sha256'], scope=SCOPE)
        def count(raw):
            result = fixtures.validate_count(native(raw), raw, m['configured_capacity'])
            require(result['input_tokens'] <= POLICY['maximum_input_tokens'], 'candidate_short_count_limit')
            self.counts[fixtures.digest(raw)] = result
            return result
        return count

    def request(self, cid, raw, identifier, *, timed=True):
        m = self.active[cid]['manifest']
        body = json.loads(raw)
        counted = self.counts.get(fixtures.digest(raw))
        require(counted is not None and body.get('max_tokens') == 256 and body.get('stream') is True
                and body.get('model') == ('glm-5.3' if m['placement'] == 'G1' else 'qwen3.8-27b'),
                'candidate_exact_counted_body_required')
        timeout = self.admission(cid, min(1200, self.armed['runtime']['budget_seconds']))
        try:
            result = client.run_request(raw, self.transport_factory(
                'http://127.0.0.1:' + str(m['transport']['port'] + 1000), self.key,
                cancel_event=self.active[cid]['cancel_event'], deadline_epoch=self.armed['runtime']['deadline_epoch']),
                sample_id=identifier, private_dir=self.private,
                summary_path=self.state / ('samples.jsonl' if timed else 'warmups.jsonl'), timeout=timeout, clock=self.clock)
            summary = result['summary']; counters = summary.get('counters', {})
            output = counters.get('completion_tokens')
            require(result.get('parsed') and summary.get('status') in {'COMPLETE', 'OUTPUT_LIMIT'}
                    and type(output) is int and 0 < output <= 256
                    and counters.get('prompt_tokens') == counted['input_tokens']
                    and counted['input_tokens'] + output <= m['configured_capacity'], 'candidate_native_count_or_transport_failed')
            if m['placement'] == 'G1':
                require(counters.get('cached_tokens') == 0 and counters.get('evaluated_prompt_tokens') == counted['input_tokens']
                        and counters.get('decode_tokens') == output, 'candidate_uncached_native_count_failed')
                ms = counters.get('decode_ms')
                if type(ms) in (int, float) and ms > 0 and output > 1 and (output - 1) * 1000 / ms < 1:
                    self.emit({'type': 'glm_slow_warning', 'id': identifier, 'stop_condition': False})
            else:
                require(counters.get('cached_tokens') in (None, 0), 'candidate_cache_policy_failed')
            require(not self.active[cid].get('abort_reason'), 'candidate_resource_failure')
            return glmrepair.Diagnostic.persistence_check(result)
        finally:
            self.host.call('request_end', id=cid)

    def prepared(self, cid, kind):
        m = self.active[cid]['manifest'];sample = fixed_samples()[m['placement'] + '-' + kind]
        raw = serialize_sample(m['placement'], kind, sample)
        counted = self.counter(cid)(raw)
        runner.save(self.private / (m['placement'] + '-' + kind + '-count.json'), counted)
        scorer_sample = copy.deepcopy(sample)
        if kind == 'smoke':
            del scorer_sample['body']['response_format']
        return {'sample': scorer_sample, 'raw': raw, 'count': counted, 'placement': m['placement'],
                'capacity': m['configured_capacity'], 'template_sha256': self.active[cid]['template_sha256'],
                'preparation_seconds': 0}

    def sequence(self):
        self.host.call('begin')
        ids = [self.loaded(m) for m in self.armed['manifests']]
        self.boundary()
        self.host.call('candidate_denials')
        for cid in ids:
            p = self.prepared(cid, 'warmup')
            result = self.request(cid, p['raw'], self.active[cid]['manifest']['placement'] + '-warmup', timed=False)
            require(fixtures.score_retrieval(p['sample'], result['parsed']['message'])['status'] == 'PASS', 'candidate_warmup_correctness_failed')
            self.emit({'type': 'warmup', 'count': p['count'], 'timing': 'DISCARDED',
                       'checkpoint': self.host.call('quiescent', id=cid, point='warm_idle')})
            self.boundary()
        for cid in ids:
            for kind in ('smoke', 'tool'):
                self.boundary()
                prepared = self.prepared(cid, kind)
                row = self.trial(cid, self.active[cid]['manifest']['placement'] + '-' + kind,
                                 kind='tool' if kind == 'tool' else 'retrieval', prepared=prepared)
                require(row['status'] == 'PASS' and (kind != 'tool' or row.get('tool', {}).get('worker_local') is True
                        and row.get('continuation') and row.get('continuation_count')), 'candidate_correctness_or_tool_failed')
        self.boundary()
        self.host.call('candidate_evidence', checks=self.progress['completed'])
        self.record('CANDIDATE_CHECKS_COMPLETE_NOT_ACCEPTED')

    def execute(self):
        monitor = threading.Thread(target=self.monitor, daemon=True)
        monitor.start()
        try:
            self.sequence()
        finally:
            self.stop.set();monitor.join()  # all synchronous HTTP calls already drained


def prepare(task, session):
    task = Path(task).resolve()
    require(not (task / 'arm.json').exists(), 'candidate_arm_exists')
    require(isinstance(session, str) and session, 'candidate_preparation_session_required')
    from .host import concurrent_capacity_policy
    armed = {'schema': 1, 'scope': SCOPE, 'campaign': CAMPAIGN, 'session_id': session,
             'source_commit': glmrepair.git('rev-parse', 'HEAD'), 'runtime_policy': POLICY,
             'candidate_capacity_policy': concurrent_capacity_policy(),
             'manifests': profiles.candidate_manifests(), 'trial_plan': profiles.trial_order(SCOPE),
             'fixed_samples': fixed_samples(), 'source_files': {p: fixtures.digest(b) for p, b in runner.source_files(SCOPE).items()},
             'native_auth_fixture': {'status': 'REQUIRED_ACTUAL_IMAGE_NOT_RUN', 'profile': 'qwen38-27b-q1-700160-yarn4-bf16kv'}}
    profiles.validate_arm_scope(armed)
    runner.save(task / 'arm.json', armed)
    receipt = {'arm_sha256': fixtures.digest(fixtures.canonical(armed)), 'source_commit': armed['source_commit'],
               'preparation_session_id': session, 'campaign': CAMPAIGN}
    runner.save(task / 'arm-receipt.json', receipt)
    runner.save(task / 'progress.json', {'phase': 'SOURCE_ONLY_ROOT_REVIEW_REQUIRED', 'completed': {}, 'inflight': {}, 'errors': []})
    runner.save(task / 'GO.template.json', {**receipt, 'decision': 'NOT_AUTHORIZED', 'vm_writer_handoff': False,
        'benchmark_restored': False, 'run_session_id': 'ROOT_FRESH_RUN_SESSION',
        'runtime': {'start_epoch': None, 'deadline_epoch': None, 'budget_seconds': 1200},
        'actual_image_auth_receipt': {'path': None, 'registered_path': None, 'sha256': None}})
    return armed


def check_execution(armed, executed, receipt, go):
    expected = {**armed, 'runtime': go.get('runtime'), 'session_id': go.get('run_session_id'),
                'preparation_arm_sha256': receipt['arm_sha256'],
                'actual_image_auth_receipt': go.get('actual_image_auth_receipt'),
                'actual_image_auth_proof': executed.get('actual_image_auth_proof')}
    require(executed == expected, 'candidate_recovery_arm_changed')
    validate_clock(armed, executed['runtime'])
    auth_fixture_module().check_pair_receipt(executed['actual_image_auth_proof'], profiles.ROOT)


def candidate_outcome(*, restore_only, checks_complete, failed, restored, errors):
    return {'status': ('RESTORATION_ONLY_NO_NEW_CANDIDATE_VERDICT' if restore_only else
                       'CANDIDATE_PASS' if checks_complete and not failed and restored else 'CANDIDATE_FAIL'),
            'production_acceptance': 'NOT_GRANTED', 'checks_complete_this_run': checks_complete,
            'restored': restored, 'errors': errors}


def live_preflight():
    # No I/O: exact reviewed helper policy must be present before credentials or staging.
    from .host import concurrent_capacity_policy
    policy = concurrent_capacity_policy()
    require(policy['headroom_observation'] ==
            '5*sampled_peak_required_working_set_ESTIMATE<=4*cap; raw current/peak separate hard-cap guards'
            and policy['caps_bytes'] == {'G1': 640 * GIB, 'Q1': 32 * GIB},
            'candidate_reviewed_working_set_policy_required')
    runner.run_preflight(SCOPE)


def run(task, go_path, session, *, restore_only=False):
    task = Path(task).resolve();go = json.loads(Path(go_path).read_bytes())
    armed = runner.load_arm(task, go.get('arm_sha256'))
    receipt = json.loads((task / 'arm-receipt.json').read_bytes())
    require(all(go.get(k) == v for k, v in receipt.items()) and go.get('decision') == 'GO'
            and go.get('vm_writer_handoff') is True and go.get('benchmark_restored') is True
            and os.geteuid() != 0, 'candidate_root_source_review_and_restored_handoff_required')
    require(armed['fixed_samples'] == fixed_samples() and armed['runtime_policy'] == POLICY, 'candidate_fixed_inputs_changed')
    execution = task / 'execution-arm.json'
    if restore_only:
        executed = json.loads(execution.read_bytes())
        check_execution(armed, executed, receipt, go)
    else:
        live_preflight()
        require(not execution.exists(), 'candidate_no_retry_or_clock_reset')
        auth = go.get('actual_image_auth_receipt', {})
        path = Path(auth.get('path') or '')
        require(path.is_absolute() and not path.is_symlink() and path.is_file(), 'candidate_actual_image_auth_receipt_required')
        raw = path.read_bytes()
        require(fixtures.digest(raw) == auth.get('sha256'), 'candidate_auth_receipt_hash_changed')
        auth_fixture_module().check_pair_receipt(json.loads(raw), profiles.ROOT)
        executed = {**armed, 'runtime': bind_runtime(armed, go, session, time.time()), 'session_id': session,
                    'preparation_arm_sha256': receipt['arm_sha256'], 'actual_image_auth_receipt': auth,
                    'actual_image_auth_proof': json.loads(raw)}
        runner.save(execution, executed)
    from runtime.sglang38_file_auth import read_key
    credentials = task.parent / 'BENCHRUN-20260919/private-credentials'
    meta = credentials.lstat()
    require(not credentials.is_symlink() and meta.st_uid == os.geteuid() and stat.S_IMODE(meta.st_mode) == 0o700,
            'candidate_protected_worker_credentials_required')
    key, control_key = read_key(credentials / 'inference-key'), read_key(credentials / 'control-key')
    runner.run_preflight(SCOPE)
    host = glmrepair.DiagnosticSSHHost(executed, stage=not restore_only)
    job = Validation(task, executed, host, key)
    failed, restored, checks_complete, errors = False, False, False, []
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, lambda signum, frame: job.interrupted.set())
    try:
        try:
            if not restore_only:
                job.execute()
                checks_complete = True
        except BaseException as error:
            failed = True;errors.append({'stage': 'checks', 'error_class': type(error).__name__})
        try:
            status = host.call('status')
            if status['phase'] == 'RECOVERY_REQUIRED':
                # Auto-restoration already failed; retain its cause and use the
                # existing fresh canonical recover entry, never repeat wrappers.
                try:
                    runner.save(task / 'restoration-rpc-diagnostics.json', host.call('rpc_diagnostics'))
                except Exception:
                    pass
                raise RuntimeError('candidate_canonical_recovery_required')
            if status['phase'] not in {'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'} and (restore_only or status['phase'] != 'NEW'):
                restore_and_finalize(host, key, control_key)
                restored = True
        except BaseException as error:
            failed = True;errors.append({'stage': 'restoration', 'error_class': type(error).__name__})
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        # Pending uncertainty retains the owning host session/ledger for root.
        status = host.call('status')
        if restored or status['phase'] in {'NEW', 'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'}:
            host.close()
            ports = {}
            for port in (31002, 31004):
                with socket.socket() as sock:
                    sock.settimeout(1);ports[str(port)] = 'CLOSED' if sock.connect_ex(('127.0.0.1', port)) else 'OPEN'
            failed |= set(ports.values()) != {'CLOSED'}
            runner.save(task / 'final-restoration-receipt.json', {'status': 'PASS' if restored and set(ports.values()) == {'CLOSED'} else 'FAIL',
                'restored': restored, 'authenticated_worker_LAN': restored, 'local_tunnels': ports})
        runner.save(task / ('recovery-outcome.json' if restore_only else 'candidate-outcome.json'),
                    candidate_outcome(restore_only=restore_only, checks_complete=checks_complete,
                                      failed=failed, restored=restored, errors=errors))
    return 1 if failed or not restored else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'run', 'restore'))
    p.add_argument('--task-dir', type=Path, required=True);p.add_argument('--session-id', required=True)
    p.add_argument('--go', type=Path)
    args = p.parse_args(argv)
    if args.action == 'prepare':
        prepare(args.task_dir, args.session_id);return 0
    if args.go is None:
        p.error('--go is required for live/recovery work')
    return run(args.task_dir, args.go, args.session_id, restore_only=args.action == 'restore')


if __name__ == '__main__':
    raise SystemExit(main())
