"""Closed two-layout 480K CPU comparison. PREP is offline; fresh root GO only.

Five measurements, four discarded warmups, no retries, filler or tuning. Reuses
concurrent capture/scoring/safety, canonical lifecycle/storage and restoration.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import signal
import socket
import stat
import threading
import time

from agent import protocol
from . import concurrent_run as prior, cpu_budget_profiles as profile
from . import fixtures, g1_ladder, glmrepair, runner, worker_verify
from .warmup import prefill_proof

SCOPE = profile.SCOPE
POLICY = {**prior.POLICY, 'budget_seconds': 4500}
BASE = '46e7f29c6edd98c156006736b999e6c858a0c9ab'
TEMPLATES = {'G1': '347dc716e1e8a9917eb124503836943107686ace6a3848d16bf23ae50964bb49',
             'Q1': 'c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041'}
SAVED = {
    'G1-frozen.json': ('CONCURRENT-G1Q1-RUN-LONG2-20260920/private/G1-65536-saved-fixture.json',
                       'fe9e7a80ae6ce7c41f9acacca1fc46cf2978e6ba2fbc8232a7f069dab13e5ef2'),
    'Q256K-frozen.json': ('CONCURRENT-G1Q1-RUN-CONT1B-20260920/private/short-Q1-0-fixture.json',
                         '9f18c8d2697b68096de2e4ce8d7966aff535823f4c00c0aaac1683bd542b3706'),
}


def validate_clock(armed, runtime):
    start, end = runtime.get('start_epoch'), runtime.get('deadline_epoch')
    if (armed.get('runtime_policy') != POLICY or set(runtime) != set(POLICY) | {'start_epoch', 'deadline_epoch'}
            or any(runtime.get(k) != v for k, v in POLICY.items())
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
            or start <= 0 or end != start + 4500 or 'continuation_execution' in armed or 'start_epoch' in armed):
        raise ValueError('cpu_fresh_4500s_dispatch_clock_required')
    return start, end


def bind_runtime(armed, go, session, now):
    runtime = copy.deepcopy(go.get('runtime', {}))
    start, end = validate_clock(armed, runtime)
    if (not start <= now < end or not session or session == armed.get('session_id')
            or go.get('run_session_id') != session):
        raise ValueError('cpu_fresh_RUN_session_required')
    return runtime


def execute_pair(g, q, common, invoke, *, interrupted=None):
    """Barrier-start main pair; A's sole common Q follows near Q immediately.

    A real failure stops new admission; a healthy admitted peer always drains.
    Completion alone does not suppress the authorized common Q measurement.
    """
    barrier, done, failed = threading.Barrier(2), threading.Event(), threading.Event()
    drained = threading.Event()
    result = {'glm': None, 'qwen': [], 'errors': []}
    def call(job):
        try:
            row = invoke(job)
            if row.get('status') != 'PASS':
                failed.set()
            return row
        except BaseException as error:
            failed.set()
            result['errors'].append({'id': job['id'], 'error_class': type(error).__name__})
            return {'id': job['id'], 'status': 'HARNESS_FAILURE'}
    def glane():
        try:
            barrier.wait()
            result['glm'] = call({**g, 'drained_event': drained})
        finally:
            done.set()
    def qlane():
        barrier.wait()
        result['qwen'].append(call(q))
        if common is not None and not failed.is_set() and not (interrupted and interrupted.is_set()):
            state = ('ended_normally' if done.is_set() else 'transport_drained_result_pending' if drained.is_set()
                     else 'active_at_dispatch')
            result['qwen'].append(call({**common, 'peer_condition_at_admission': state}))
    threads = [threading.Thread(target=glane), threading.Thread(target=qlane)]
    try:
        for thread in threads:
            thread.start()
    except BaseException:
        barrier.abort()
        prior.drain_threads(threads)
        raise
    prior.drain_threads(threads)
    result['overlap'] = prior.summarize_overlap(result['glm'], result['qwen'])
    expected = 2 if common is not None else 1
    result['status'] = 'COMPLETE' if not failed.is_set() and len(result['qwen']) == expected else 'FAILED'
    return result


class CPURun(prior.ConcurrentRun):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile.validate_arm_scope(self.armed)
        verify_frozen(self.state, self.armed)

    def request(self, cid, raw, identifier, **kwargs):
        if protocol.strict_json_loads(raw).get('max_tokens') not in (32, 256):
            raise ValueError('cpu_closed_output_policy')
        return super().request(cid, raw, identifier, **kwargs)

    def warm(self, cid, manifest, proof):
        # One bounded prebuilt representative body; count FINAL 32-output bytes.
        # No capacity fitter or extra inference is admitted for warmup.
        model = 'bench-glm-5.3' if manifest['placement'] == 'G1' else 'bench-qwen3.8-27b'
        sample = fixtures.build_sample(model, 80, 'warmup-only-seed', 'warmup-' + str(time.time_ns()))
        body = protocol.strict_json_loads(g1_ladder.body_bytes(sample, 32)) if manifest['placement'] == 'G1' else copy.deepcopy(sample['body'])
        body['max_tokens'] = 32
        raw = fixtures.canonical(body)
        count = fixtures.validate_count(self.counter(cid)(raw), raw, profile.CAPACITY)
        if not 2048 <= count['input_tokens'] <= 4096:
            raise ValueError('cpu_representative_warmup_count_required')
        identifier = manifest['layout'] + '-' + manifest['placement'] + '-warmup'
        runner.save(self.private / (identifier + '-count.json'), count)
        cpu_start = self.clock()
        self.collect()  # Cheap before/after samples also bound a short Q warmup.
        response = self.request(cid, raw, identifier, timed=False)
        self.collect()
        cpu_end = self.clock()
        from .cpu_budget_telemetry import warmup_gate
        with self.lock:
            cpu_samples = [v['cpu_budget'] for v in self.samples.get(cid, []) if 'cpu_budget' in v
                           and cpu_start <= v['cpu_budget'].get('client_observed_monotonic_s', -1) <= cpu_end]
        cpu_proof = warmup_gate(cpu_samples, cid)
        runner.save(self.state / (identifier + '-cpu-evidence.json'), cpu_proof)
        if cpu_proof['status'] != 'PASS':
            self.emit({'type': 'cpu_warmup_UNAVAILABLE', 'id': identifier, 'evidence': cpu_proof})
            raise RuntimeError('STOP_CPU_WARMUP_EVIDENCE_UNAVAILABLE')
        counters = response['summary'].get('counters', {})
        if (not response.get('parsed') or response['summary']['status'] not in {'COMPLETE', 'OUTPUT_LIMIT'}
                or counters.get('prompt_tokens') != count['input_tokens']
                or type(counters.get('completion_tokens')) is not int or not 0 < counters['completion_tokens'] <= 32):
            raise RuntimeError('STOP_WARMUP_NATIVE_COUNT')
        evidence = prefill_proof(counters, manifest, proof)
        self.emit({'type': 'warmup', 'id': identifier, 'count': count, 'prefill_proof': evidence,
                   'timings': 'DISCARDED', 'sample': response['summary'], 'cpu_warmup_gate': cpu_proof,
                   'checkpoint': self.host.call('quiescent', id=cid, point='warm_idle')})
        self.boundary()

    def prepare_job(self, cid, identifier, *, common=False, matched=None):
        self.boundary()
        started = self.clock()
        m = self.active[cid]['manifest']
        plan = next((v for v in profile.trial_order()['trials'] if v['id'] == identifier), None)
        if (plan is None or plan['layout'] != m['layout'] or plan['placement'] != m['placement']
                or bool(common) != (identifier == 'A-Q256K')
                or (identifier == 'B-Qnear480K') != (matched is not None)):
            raise ValueError('cpu_exact_five_trial_tuple_required')
        nonce = 'fresh-' + str(time.time_ns())
        if m['placement'] == 'G1':
            if common or matched is not None:
                raise ValueError('cpu_G_fixed_fixture_only')
            frozen = json.loads((self.private / 'G1-frozen.json').read_bytes())
            sample = fixtures.build_sample('bench-glm-5.3', frozen['records'], frozen['seed'], nonce)
            if (frozen['records'] != 2028 or sample['fixture_sha256'] != frozen['fixture_sha256']
                    or sample['scorer'] != frozen['scorer']):
                raise ValueError('cpu_frozen_G_logical_values_changed')
            raw = g1_ladder.body_bytes(sample)
            count = fixtures.validate_count(self.counter(cid)(raw), raw, profile.CAPACITY)
            if not 64896 <= count['input_tokens'] <= 65024:
                raise ValueError('cpu_G_native_65008ish_changed_no_refit')
            count = {**count, 'occupied_input_target': 65008, 'output_cap': 256,
                     'records': 2028, 'matched_fixture_sha256': frozen['fixture_sha256']}
        else:
            target = 262144 if common else profile.CAPACITY
            frozen = json.loads((self.private / 'Q256K-frozen.json').read_bytes()) if common else matched
            if frozen is not None:
                sample, count = fixtures.matched_sample(frozen, nonce, self.counter(cid), profile.CAPACITY,
                                                       scope=SCOPE, target_capacity=target)
            else:
                sample, count = fixtures.fit_sample('bench-qwen3.8-27b', profile.CAPACITY,
                    'concurrent-qwen-fixture-1729', nonce, self.counter(cid), scope=SCOPE, target_capacity=target)
            raw = fixtures.serialize_validate(sample)
        if count['template_sha256'] != TEMPLATES[m['placement']]:
            raise ValueError('cpu_saved_native_template_changed')
        if count['input_tokens'] + 256 + 256 > profile.CAPACITY:
            raise ValueError('cpu_exact_count_output_margin_exceeds_pool')
        runner.save(self.private / (identifier + '-fixture.json'), sample)
        runner.save(self.private / (identifier + '-count.json'), count)
        return {'id': identifier, 'cid': cid, 'sample': sample, 'raw': raw, 'count': count,
            'manifest_sha256': fixtures.digest(fixtures.canonical(m)), 'generation': False,
            'common_input': common, 'preparation_seconds': self.clock() - started}

    def measure(self, job, **kwargs):
        row = super().measure(job, **kwargs)
        from .cpu_budget_telemetry import summarize_measurement
        cid = job['cid']
        with self.lock:
            samples = [v['cpu_budget'] for v in self.samples.get(cid, []) if 'cpu_budget' in v]
        row.update(layout=self.active[cid]['manifest']['layout'],
                   peer_condition_at_admission=job.get('peer_condition_at_admission', 'barrier_main_pair'),
                   common_input=job['common_input'],
                   cpu_evidence=summarize_measurement(samples, row['sample']))
        # Native totals are not phase-aligned per-vCPU measurements. CPU evidence
        # missing/disabled stays UNAVAILABLE and prevents a CPU-comparison claim.
        with self.lock:
            self.progress['completed'][job['id']] = row
            runner.save(self.state / (job['id'] + '-result.json'), row)
            self.emit({'type': 'cpu_measurement', **row})
            self.record()
        return row

    def sequence(self):
        self.boundary()
        self.host.call('begin')
        near = None
        for layout in ('A', 'B'):
            self.boundary(); self.record('PREPARING_' + layout)
            admission = self.host.call('admit_concurrent', round=layout)
            ids = {m['placement']: self.loaded(m) for m in admission['manifests']}
            g = self.prepare_job(ids['G1'], layout + '-G65008')
            q = self.prepare_job(ids['Q1'], layout + '-Qnear480K', matched=near)
            near = q['sample']
            common = self.prepare_job(ids['Q1'], 'A-Q256K', common=True) if layout == 'A' else None
            self.boundary(); self.record('DISPATCHING_' + layout)
            result = execute_pair(g, q, common, self.measure, interrupted=self.interrupted)
            runner.save(self.state / (layout + '-round.json'), result)
            self.emit({'type': 'cpu_round', 'layout': layout, **result})
            if result['status'] != 'COMPLETE':
                raise RuntimeError('STOP_CPU_PAIR_GATE')
            self.boundary()
            for cid in ids.values():
                self.emit({'type': 'post_round_quiescent', 'layout': layout,
                    'checkpoint': self.host.call('quiescent', id=cid, point='warm_idle')})
            self.retire_all()
        from .cpu_budget_telemetry import comparison_summary
        runner.save(self.state / 'cpu-comparison.json', comparison_summary(self.progress['completed']))
        self.record('MEASUREMENTS_COMPLETE')


def verify_frozen(task, armed):
    for name, expected in armed['frozen_inputs'].items():
        if fixtures.digest((task / name).read_bytes()) != expected:
            raise ValueError('cpu_frozen_input_changed')


def prepare(task, session):
    task = Path(task).resolve()
    if (task / 'arm.json').exists():
        raise ValueError('cpu_arm_exists_no_reset')
    if not session or glmrepair.git('status', '--porcelain'):
        raise ValueError('cpu_clean_source_and_session_required')
    g1_ladder.checkpoint(task)
    evidence = json.loads((task / 'evidence-index.json').read_bytes())
    frozen = {}
    for name, (relative, sha) in SAVED.items():
        source = task.parent / relative
        raw = source.read_bytes()
        if fixtures.digest(raw) != sha:
            raise ValueError('cpu_saved_fixture_identity_changed')
        fixtures.serialize_validate(json.loads(raw))
        target = task / 'private' / name
        runner.save(target, json.loads(raw))
        frozen[str(target.relative_to(task))] = fixtures.digest(target.read_bytes())
    # Preserve content-bound immutable proof refs inside the transport package;
    # private raw artifacts remain outside source/public output.
    for label, reference in evidence['refs'].items():
        raw = Path(reference['path']).read_bytes()
        if fixtures.digest(raw) != reference['sha256']:
            raise ValueError('cpu_saved_evidence_changed')
        target = task / 'private' / 'saved' / (label + '.json')
        runner.save(target, json.loads(raw))
        frozen[str(target.relative_to(task))] = fixtures.digest(target.read_bytes())
    runner.save(task / 'protected-key-metadata.json', evidence['protected_key_metadata'])
    if not (task / 'run-control.json').exists():
        runner.save(task / 'run-control.json', {'action': 'CONTINUE'})
    runner.save(task / 'progress.json', {'phase': 'INITIAL', 'completed': {}, 'inflight': {}, 'errors': []})
    from .host import concurrent_capacity_policy
    inputs = ['progress.json', 'evidence-index.json', 'protected-key-metadata.json', *frozen]
    armed = {'schema': 1, 'scope': SCOPE, 'campaign': profile.CAMPAIGN, 'session_id': session,
        'base_commit': BASE, 'source_commit': glmrepair.git('rev-parse', 'HEAD'), 'runtime_policy': POLICY,
        'runtime_source_path': '/data/services/' + profile.CAMPAIGN + '/source',
        'manifests': profile.manifests(), 'trial_plan': profile.trial_order(),
        'concurrent_capacity_policy': concurrent_capacity_policy(SCOPE), 'frozen_inputs': frozen,
        'source_files': {p: fixtures.digest(b) for p, b in runner.source_files().items()},
        'required_package_files': ['arm.json', 'arm-receipt.json', 'GO.template.json', 'incoming-latest.md', 'run-control.json', *inputs],
        'initial_package_sha256': {name: fixtures.digest((task / name).read_bytes()) for name in inputs},
        'authority_at_prepare_sha256': fixtures.digest((task / 'incoming-latest.md').read_bytes()),
        'production_acceptance': 'NOT_GRANTED', 'measurement_clock': 'ROOT_DISPATCH_ONLY'}
    profile.validate_arm_scope(armed)
    runner.save(task / 'arm.json', armed)
    receipt = {'source_commit': armed['source_commit'], 'preparation_session_id': session,
        'campaign': profile.CAMPAIGN, 'arm_sha256': fixtures.digest((task / 'arm.json').read_bytes())}
    runner.save(task / 'arm-receipt.json', receipt)
    runner.save(task / 'GO.template.json', {**receipt, 'decision': 'NOT_AUTHORIZED', 'vm_writer_handoff': False,
        'run_session_id': None, 'runtime': {**POLICY, 'start_epoch': None, 'deadline_epoch': None}})
    return armed


def _keys(task):
    from runtime.sglang38_file_auth import read_key
    directory = task.parent / 'BENCHRUN-20260919/private-credentials'
    meta = directory.lstat()
    if directory.is_symlink() or meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
        raise ValueError('cpu_protected_credentials_required')
    return read_key(directory / 'inference-key'), read_key(directory / 'control-key')


class RecoveryRequired(RuntimeError):
    def __init__(self, host):
        super().__init__('cpu_canonical_recovery_failed_preserve_ledger')
        self.recovery_host = host


def restore_once(host, executed, task, key, control, *, factory=glmrepair.DiagnosticSSHHost,
                 verify=worker_verify.verify):
    """One normal restore; one safe diagnostic and direct canonical recover.

    Called only after all request lanes drained. A fresh host process reacquires
    the canonical lease from the durable ledger; no failed-wrapper retry loop.
    """
    initial_phase = host.call('status')['phase']
    try:
        if initial_phase == 'RECOVERY_REQUIRED':
            raise RuntimeError('cpu_existing_recovery_required')
        prior.restore_and_finalize(host, key, control, verify=verify)
        return host
    except BaseException:
        if host.call('status')['phase'] != 'RECOVERY_REQUIRED':
            raise
        try:
            diagnostic = host.call('rpc_diagnostics')
        except BaseException as error:
            diagnostic = {'status': 'UNAVAILABLE', 'error_class': type(error).__name__}
        try:
            runner.save(task / 'restoration-rpc-diagnostics.json', diagnostic)
        except BaseException:
            pass  # Evidence-write failure must never bypass canonical recovery.
        if initial_phase == 'NEW':
            raise RecoveryRequired(host) from None  # A recovery-only call already attempted recover once.
        host.close()
        replacement = factory(executed, stage=False)
        try:
            replacement.call('recover')
            prior.restore_and_finalize(replacement, key, control, verify=verify)
            return replacement
        except BaseException:
            # Do not repeat or close the owning session after failed recovery.
            raise RecoveryRequired(replacement) from None


def run(task, go_path, session, *, restore_only=False):
    task = Path(task).resolve()
    armed, receipt = [json.loads((task / name).read_bytes()) for name in ('arm.json', 'arm-receipt.json')]
    go = json.loads(Path(go_path).read_bytes())
    profile.validate_arm_scope(armed)
    if (os.geteuid() == 0 or go.get('decision') != 'GO' or go.get('vm_writer_handoff') is not True
            or any(go.get(k) != v for k, v in receipt.items())
            or receipt['arm_sha256'] != fixtures.digest((task / 'arm.json').read_bytes())
            or armed['source_commit'] != glmrepair.git('rev-parse', 'HEAD')
            or glmrepair.git('status', '--porcelain')
            or {p: fixtures.digest(b) for p, b in runner.source_files().items()} != armed['source_files']):
        raise ValueError('cpu_root_source_arm_GO_required')
    verify_frozen(task, armed)
    execution = task / 'execution-arm.json'
    if restore_only:
        executed = json.loads(execution.read_bytes())
        if (executed.get('preparation_arm_sha256') != receipt['arm_sha256']
                or executed != {**armed, 'runtime': go['runtime'], 'session_id': go['run_session_id'],
                                'preparation_arm_sha256': receipt['arm_sha256']}):
            raise ValueError('cpu_recovery_execution_changed')
        validate_clock(armed, executed['runtime'])
    else:
        if execution.exists():
            raise ValueError('cpu_no_rerun_or_clock_reset')
        prior.verify_initial_package(task, armed)
        g1_ladder.checkpoint(task)
        executed = {**armed, 'runtime': bind_runtime(armed, go, session, time.time()), 'session_id': session,
                    'preparation_arm_sha256': receipt['arm_sha256']}
        runner.save(execution, executed)
    runner.run_preflight(SCOPE)
    key, control = _keys(task)
    job = CPURun(task, executed, None, key)  # Complete local read-chain before staging/SSH.
    host = glmrepair.DiagnosticSSHHost(executed, stage=not restore_only)
    job.host = host
    failed, restored, errors = False, False, []
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in handlers:
        signal.signal(sig, lambda signum, frame: job.interrupted.set())
    def safe_save(path, value):
        try:
            runner.save(path, value)
        except BaseException as error:
            errors.append({'phase': 'evidence_write', 'error_class': type(error).__name__})
    try:
        if not restore_only:
            try:
                job.execute()
            except BaseException as error:
                failed = True
                from .host import rpc_diagnostic
                errors.append({'phase': 'measurement', **rpc_diagnostic('measurement', error)})
        try:
            phase = host.call('status')['phase']
            if phase not in {'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'} and (restore_only or phase != 'NEW'):
                host = restore_once(host, executed, task, key, control)
                restored = True
        except BaseException as error:
            failed = True
            if isinstance(error, RecoveryRequired):
                host = error.recovery_host
            errors.append({'phase': 'restoration', 'error_class': type(error).__name__})
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        try:
            terminal = 'RESTORED' if restored else host.call('status')['phase']
            if terminal in {'RESTORED', 'NEW', 'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'}:
                host.close()
                ports = {}
                for port in (31002, 31004):
                    with socket.socket() as sock:
                        sock.settimeout(1)
                        ports[str(port)] = 'CLOSED' if sock.connect_ex(('127.0.0.1', port)) else 'OPEN'
                failed |= set(ports.values()) != {'CLOSED'}
                safe_save(task / 'final-restoration-receipt.json', {'status': 'PASS' if restored and not failed and not errors else 'RESTORED_WITH_MEASUREMENT_FAILURE' if restored else 'FAIL',
                    'restored': restored, 'authenticated_worker_LAN': restored, 'local_tunnels': ports})
        except BaseException as error:
            failed = True
            errors.append({'phase': 'host_close', 'error_class': type(error).__name__})
        safe_save(task / 'status.json', {'phase': 'RESTORED' if restored else 'RECOVERY_REQUIRED',
            'source_commit': armed['source_commit'], 'session_id': session, 'errors': errors,
            'clock': executed['runtime'], 'completed': list(job.progress['completed'])})
        safe_save(task / ('recovery-outcome.json' if restore_only else 'run-outcome.json'),
            {'measurement_failed': failed, 'restored': restored, 'errors': errors,
             'measurement_status': 'NOT_RUN_RECOVERY_ONLY' if restore_only else 'FAILED' if failed else 'COMPLETE',
             'completed': list(job.progress['completed']),
             'missing': [name for name in ('A-G65008', 'A-Qnear480K', 'A-Q256K', 'B-G65008', 'B-Qnear480K')
                         if name not in job.progress['completed']], 'production_acceptance': 'NOT_GRANTED'})
    return 1 if failed or not restored or errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'run', 'restore'))
    parser.add_argument('--task-dir', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--go', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        prepare(args.task_dir, args.session_id)
        return 0
    if args.go is None:
        parser.error('--go is required for RUN or recovery')
    return run(args.task_dir, args.go, args.session_id, restore_only=args.action == 'restore')


if __name__ == '__main__':
    raise SystemExit(main())
