"""Closed actual72 PREP / fresh reviewed RUN: short G gate, then one G/Q pair.

Imports/prepare are offline. Scoped owned hold; no old clock, retry or tuning.
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
import threading
import time

from agent import protocol
from . import client, concurrent_run as prior, concurrent_cpu_run as cpu_run
from . import cpu_budget_profiles as profile, cpu_budget_telemetry as cpu
from . import fixtures, g1_ladder, glmrepair, runner
from .warmup import prefill_proof

SCOPE = 'postrestart72-480k'
BASE = '59aeef68640986082d6e6b431be3d86386e64168'
POLICY = {'budget_seconds': 21600, 'preparation_seconds': 7200, 'request_timeout_seconds': 7200,
          'clock_starts': 'FIRST_MEASURED_REQUEST_ADMISSION', 'clock_includes_preparation': False,
          'admission_deadline_refuses_new_only': True, 'request_clock_starts': 'HTTP_DISPATCH',
          'restoration_outside_budget': True}
TEMPLATES = cpu_run.TEMPLATES
SAVED = {
    'G4K-original-fixtures.json': ('GLMREPAIR-G1FIX-20260919/private/fixtures.json',
        'aec926dc8271299d6c597b6cd612695a1dd4229a080dc3e1181b1eb789159212'),
    'G4K-original.request.json': ('GLMREPAIR-G1FIX-20260919/private/native-schema.request.json',
        'a05f432488fbb789ea8e82b2f8645a1b78b2b0cc10adb6a7a8e7b6adb8db9776'),
    'G1-frozen.json': cpu_run.SAVED['G1-frozen.json'],
    'Q480-frozen.json': ('CONCURRENT-480K-CPU-FINAL-20260920/private/A-Qnear480K-fixture.json',
        '666e5b0397e5c2e10dcfa5b2efe9b089cfeea831af9680f44ad3981e5aa4db34'),
}
TRIAL_IDS = ('P-G4K', 'P-G65008', 'P-Qnear480K')


class EvidenceReview(RuntimeError):
    """Reporting or observation gap, not a proven resource violation."""


class AdmissionPaused(RuntimeError):
    """Scoped STOP/PAUSE drains requests and holds an already warm safe pair."""


def validate_clock(armed, runtime):
    if armed.get('runtime_policy') != POLICY or runtime != POLICY:
        raise ValueError('postrestart_independent_clock_policy_required')
    return None, None


def bind_runtime(armed, go, session, now=None):
    runtime = copy.deepcopy(go.get('runtime', {}))
    validate_clock(armed, runtime)
    if not session or session == armed.get('session_id') or go.get('run_session_id') != session:
        raise ValueError('postrestart_fresh_RUN_session_required')
    return runtime


def preliminary(row):
    counters = row.get('sample', {}).get('counters', {})
    n, prompt_ms = counters.get('prompt_tokens'), counters.get('prompt_ms')
    prefill = n * 1000 / prompt_ms if type(n) is int and type(prompt_ms) in (int, float) and prompt_ms > 0 else None
    output, decode = counters.get('completion_tokens'), row.get('native_n_minus_one_decode_tps')
    flags = []
    if prefill is None:
        flags.append('prefill_UNAVAILABLE')
    elif prefill < 35:
        flags.append('prefill_below_35_tps')
    if type(output) is int and output >= 64 and type(decode) in (int, float) and decode < 2:
        flags.append('aggregate_decode_below_2_tps_at_least64_output')
    total = row.get('sample', {}).get('client_elapsed_seconds')
    preauthorized = (row.get('status') == 'PASS' and row.get('strict', {}).get('status') == 'PASS'
        and row.get('native_count_valid') is True and counters.get('cached_tokens') == 0
        and prefill is not None and math.isfinite(prefill) and prefill >= 35
        and type(total) in (int, float) and math.isfinite(total) and 0 <= total <= 180)
    return {'status': 'PREAUTHORIZED_LONG' if preauthorized else 'ROOT_REVIEW_REQUIRED', 'flags': flags,
            'long_preauthorized': preauthorized,
            'prefill_tps': prefill, 'native_n_minus_one_decode_tps': decode,
            'output_tokens': output, 'prompt_seconds': prompt_ms / 1000 if type(prompt_ms) in (int, float) else None,
            'decode_seconds': counters.get('decode_ms', 0) / 1000 if type(counters.get('decode_ms')) in (int, float) else None,
            'total_seconds': row.get('sample', {}).get('client_elapsed_seconds'),
            'historical': {'input': 3546, 'output': 145, 'cached': 0, 'prompt_seconds': 51.750817,
                'decode_seconds': 11.391151, 'total_seconds': 63.222480, 'native_n_minus_one_decode_tps': 12.641392},
            'confounds': ['configured480000_vs4096', 'actual72_eightnodes_vs112_sevennodes',
                          'Qwen_resident_idle', 'single_ordered_sample_known_decode_variability'],
            'automatic_speed_abort': False, 'long_admission': 'strict_uncached_prefill35_total180_else_root_snapshot_bound_GO'}


def validate_long_go(value, armed, row_sha):
    followup = value.get('followup_session_id') if isinstance(value, dict) else None
    if not isinstance(followup, str) or not followup or followup == armed['session_id']:
        raise ValueError('postrestart_fresh_followup_session_required')
    expected = {'decision': 'GO', 'source_commit': armed['source_commit'],
                'followup_session_id': followup,
                'run_session_id': armed['session_id'], 'campaign': armed['campaign'],
                'preliminary_result_sha256': row_sha}
    if value != expected:
        raise ValueError('postrestart_root_snapshot_bound_long_GO_required')


class PostrestartRun(prior.ConcurrentRun):
    def __init__(self, state, *args, **kwargs):
        client.private_artifact_directory(Path(state) / 'private')
        super().__init__(state, *args, **kwargs)
        profile.validate_postrestart_arm_scope(self.armed)
        cpu_run.verify_frozen(self.state, self.armed)
        self.pending_warmups = []
        self.release_requested = False
        self.hold_ready = False
        self.in_hold = False
        self.admission_paused = False
        self.quality_review = False
        self.hold_reporting_errors = []
        self.followup_sessions = []

    def root_paused(self):
        try:
            g1_ladder.checkpoint(self.state)
        except RuntimeError as error:
            if str(error) in {'ROOT_CONTROL_STOP', 'ROOT_CONTROL_PAUSE', 'ROOT_EXPLICIT_STOP_OR_PAUSE'}:
                self.admission_paused = True
                return True
            raise
        return self.admission_paused

    def boundary(self):
        if self.interrupted.is_set():
            raise RuntimeError('ROOT_INTERRUPTED_DRAIN_AND_RESTORE')
        try:
            paused = self.root_paused()
        except (OSError, ValueError, protocol.AgentError):
            if not self.in_hold:
                raise
            self.hold_notice('root_control_report_or_input_UNAVAILABLE')
            paused = True
        if not self.in_hold:
            self.ensure_current_proof()
        if paused and not self.in_hold:
            raise AdmissionPaused('ROOT_STOP_PAUSE_HEALTHY_HOLD')

    def require_no_faults(self):
        with self.lock:
            if self.safety:
                raise RuntimeError(next(iter(self.safety.values())))
            for entry in self.active.values():
                if entry.get('abort_reason') or (entry.get('cancel_event') is not None and entry['cancel_event'].is_set()):
                    raise RuntimeError(entry.get('abort_reason') or 'STOP_CANCELLED')

    def ensure_current_proof(self):
        """At most three fresh whole-pair observations; never retry inference."""
        for attempt in range(3):
            self.require_no_faults()
            try:
                remaining = self.host.call('budget').get('remaining_s', 0) if self.active else 1
            except Exception as error:
                self.safety.setdefault('host', 'HARNESS_FAILURE')
                raise RuntimeError('HARNESS_FAILURE') from error
            if remaining <= 0:
                raise EvidenceReview('CURRENT_PROOF_PREPARATION_OR_ADMISSION_WINDOW_EXPIRED')
            started = self.clock()
            self.collect()
            self.require_no_faults()
            with self.lock:
                if self.proof_pending is None:
                    return
            # Existing preparation/admission clock only; never reset it or
            # shorten the independent deadline of an admitted HTTP request.
            remaining -= self.clock() - started
            if remaining <= 0 or attempt == 2:
                break
            self.sleep(min(0.1, remaining))
        raise EvidenceReview('CURRENT_RESOURCE_PROOF_UNAVAILABLE')

    def admission(self, cid, maximum=7200, *, measured=False, request_identity=None):
        # Freeze this admission's identity. Only an explicit pre-registration
        # proof gap can repeat request_begin; HTTP inference is never retried.
        arguments = {'id': cid, 'timeout_s': maximum, 'measured': measured,
            **({'request_identity': copy.deepcopy(request_identity)} if request_identity is not None else {})}
        for attempt in range(3):
            if self.interrupted.is_set():
                raise RuntimeError('ROOT_INTERRUPTED_DRAIN_AND_RESTORE')
            if self.root_paused():
                raise AdmissionPaused('ROOT_STOP_PAUSE_NO_NEW_REQUEST')
            self.ensure_current_proof()  # same existing preparation/admission clock
            with self.lock:
                self.require_no_faults()
                try:
                    grant = self.host.call('request_begin', **arguments)
                    if type(grant) is not dict:
                        raise RuntimeError('INVALID_ADMISSION_RESPONSE')
                    if 'proof_pending' not in grant and 'admitted' not in grant:
                        timeout = grant.get('timeout_s')
                        if (set(grant) - {'timeout_s', 'budget'} or type(timeout) not in (int, float)
                                or not math.isfinite(timeout) or not 0 < timeout <= maximum):
                            raise RuntimeError('INVALID_ADMISSION_RESPONSE')
                        return timeout
                    if (set(grant) != {'proof_pending', 'admitted', 'resource_gate', 'sample'}
                            or grant['proof_pending'] is not True or grant['admitted'] is not False
                            or type(grant['resource_gate']) is not dict
                            or grant['resource_gate'].get('status') != 'UNAVAILABLE'
                            or grant['resource_gate'].get('reasons') != []
                            or grant['resource_gate'].get('latched_violations') != {}
                            or type(grant['sample']) is not dict
                            or grant['sample'].get('concurrent_resource_gate') != grant['resource_gate']):
                        raise RuntimeError('INVALID_ADMISSION_RESPONSE')
                except Exception:
                    self.safety.setdefault(cid, 'HARNESS_FAILURE')
                    raise  # uncertain/admitted/malformed responses cannot retry
                self.proof_pending = grant['resource_gate']
                self.emit({'type': 'admission_proof_pending', 'container': cid, 'proof': grant,
                           'attempt': attempt + 1, 'attempt_limit': 3})
        raise EvidenceReview('CURRENT_RESOURCE_PROOF_UNAVAILABLE')

    def monitor(self):
        # A held runner has no timed phase: no unbounded worker interval arrays.
        while not self.stop.is_set():
            if not self.in_hold:
                self.collect()
            self.stop.wait(1)

    def hold_save(self, path, value):
        try:
            runner.save(path, value)
            return True
        except OSError as error:
            self.hold_reporting_errors = (self.hold_reporting_errors + [type(error).__name__])[-8:]
            return False

    def hold_notice(self, code):
        self.hold_save(self.state / 'hold-review.json', {'phase': 'WARM_HOLD_REVIEW_REQUIRED',
            'reason': code, 'updated_epoch': time.time(), 'model_disposition': 'retained_no_admission'})

    def request(self, cid, raw, identifier, **kwargs):
        if protocol.strict_json_loads(raw).get('max_tokens') not in (32, 256):
            raise ValueError('postrestart_closed_output_policy')
        return super().request(cid, raw, identifier, **kwargs)

    def short_sample(self, nonce):
        frozen = json.loads((self.private / 'G4K-original-fixtures.json').read_bytes())['bench-glm-5.3-4096-retrieval']
        sample = fixtures.build_sample('bench-glm-5.3', frozen['records'], frozen['seed'], nonce)
        if frozen['records'] != 108 or any(sample[k] != frozen[k] for k in ('fixture_sha256', 'scorer')):
            raise ValueError('postrestart_historical_short_fixture_changed')
        # The historical schema body is authoritative: change the leading prefix only.
        body = protocol.strict_json_loads((self.private / 'G4K-original.request.json').read_bytes())
        old = body['messages'][0]['content']
        if old.split('\n', 1)[1] != sample['body']['messages'][0]['content'].split('\n', 1)[1]:
            raise ValueError('postrestart_historical_short_archive_changed')
        body['messages'][0]['content'] = sample['body']['messages'][0]['content']
        return sample, fixtures.canonical(body)

    def warm(self, cid, manifest, proof):
        # loaded() retains its reviewed ready/resource proof. Warm both only once
        # both validated480K allocations are resident.
        self.pending_warmups.append((cid, manifest, proof))

    def discarded_warmup(self, cid, manifest, proof):
        nonce = 'warmup-' + str(time.time_ns())
        if manifest['placement'] == 'G1':
            sample, raw = self.short_sample(nonce)
            body = protocol.strict_json_loads(raw)
        else:
            sample = fixtures.build_sample('bench-qwen3.8-27b', 80, 'warmup-only-seed', nonce)
            body = copy.deepcopy(sample['body'])
        body['max_tokens'] = 32
        raw = fixtures.canonical(body)
        count = fixtures.validate_count(self.counter(cid)(raw), raw, 480000)
        if not 2048 <= count['input_tokens'] <= 4096 or count['template_sha256'] != TEMPLATES[manifest['placement']]:
            raise ValueError('postrestart_warmup_native_count_or_template')
        identifier = 'P-' + manifest['placement'] + '-warmup'
        runner.save(self.private / (identifier + '-count.json'), count)
        start = self.clock(); self.collect()
        response = self.request(cid, raw, identifier, timed=False)
        self.collect(); end = self.clock()
        counters = response['summary'].get('counters', {})
        if (not response.get('parsed') or response['summary']['status'] not in {'COMPLETE', 'OUTPUT_LIMIT'}
                or counters.get('prompt_tokens') != count['input_tokens']
                or type(counters.get('completion_tokens')) is not int or not 0 < counters['completion_tokens'] <= 32):
            raise RuntimeError('STOP_WARMUP_NATIVE_COUNT')
        evidence = prefill_proof(counters, manifest, proof)
        with self.lock:
            samples = [v['cpu_budget'] for v in self.samples.get(cid, []) if 'cpu_budget' in v
                       and start <= v['cpu_budget'].get('client_observed_monotonic_s', -1) <= end]
        cpu_proof = cpu.warmup_gate(samples, cid, scope=SCOPE)
        runner.save(self.state / (identifier + '-cpu-evidence.json'), cpu_proof)
        self.emit({'type': 'warmup', 'id': identifier, 'count': count, 'prefill_proof': evidence,
                   'timings': 'DISCARDED_NEVER_SPEED_GATE', 'sample': response['summary'], 'cpu_evidence': cpu_proof,
                   'checkpoint': self.host.call('quiescent', id=cid, point='warm_idle')})
        if cpu_proof['status'] != 'PASS':
            raise RuntimeError('STOP_CPU_WARMUP_EVIDENCE_UNAVAILABLE')

    def prepare_job(self, cid, identifier):
        self.boundary(); started = self.clock()
        manifest = self.active[cid]['manifest']
        expected = {'P-G4K': 'G1', 'P-G65008': 'G1', 'P-Qnear480K': 'Q1'}
        if identifier not in expected or manifest != profile.postrestart_manifest(expected[identifier]):
            raise ValueError('postrestart_exact_trial_tuple_required')
        nonce = 'fresh-' + str(time.time_ns())
        if identifier == 'P-G4K':
            sample, raw = self.short_sample(nonce)
            count = fixtures.validate_count(self.counter(cid)(raw), raw, 480000)
            if not 3420 <= count['input_tokens'] <= 3674:
                raise ValueError('postrestart_short_count_changed_no_refit')
        elif identifier == 'P-G65008':
            frozen = json.loads((self.private / 'G1-frozen.json').read_bytes())
            sample = fixtures.build_sample('bench-glm-5.3', frozen['records'], frozen['seed'], nonce)
            if frozen['records'] != 2028 or any(sample[k] != frozen[k] for k in ('fixture_sha256', 'scorer')):
                raise ValueError('postrestart_long_G_fixture_changed')
            raw = g1_ladder.body_bytes(sample)
            count = fixtures.validate_count(self.counter(cid)(raw), raw, 480000)
            if not 64896 <= count['input_tokens'] <= 65024:
                raise ValueError('postrestart_long_G_count_changed_no_refit')
        else:
            frozen = json.loads((self.private / 'Q480-frozen.json').read_bytes())
            sample, count = fixtures.matched_sample(frozen, nonce, self.counter(cid), 480000,
                                                    scope=SCOPE, target_capacity=480000)
            raw = fixtures.serialize_validate(sample)
        if count['template_sha256'] != TEMPLATES[manifest['placement']] or count['input_tokens'] + 512 > 480000:
            raise ValueError('postrestart_template_or_capacity_mismatch')
        runner.save(self.private / (identifier + '-fixture.json'), sample)
        runner.save(self.private / (identifier + '-count.json'), count)
        return {'id': identifier, 'cid': cid, 'sample': sample, 'raw': raw, 'count': count,
                'manifest_sha256': fixtures.digest(fixtures.canonical(manifest)), 'generation': False,
                'preparation_seconds': self.clock() - started}

    def persist_measurement(self, row):
        try:
            super().persist_measurement(row)
        except OSError:
            row['status'] = 'REVIEW_EVIDENCE_UNAVAILABLE'
            self.quality_review = True
            self.hold_notice('measurement_report_write_failed')

    def measure(self, job, **kwargs):
        try:
            row = super().measure(job, **kwargs)
        except (AdmissionPaused, EvidenceReview):
            # admission() raises this before host registration/HTTP dispatch.
            # Remove only this undispatched request, never an admitted peer.
            with self.lock:
                self.progress['inflight'].pop(job['id'], None)
                self.record()
            raise
        with self.lock:
            samples = [v['cpu_budget'] for v in self.samples.get(job['cid'], []) if 'cpu_budget' in v]
            row.update(layout='P', cpu_evidence=cpu.summarize_measurement(samples, row['sample'], scope=SCOPE),
                       peer_condition_at_admission='other_model_resident_idle_followup' if job.get('followup_session_id') else
                           'Qwen_resident_idle' if job['id'] == 'P-G4K' else 'barrier_main_pair')
            if row['sample'].get('report_errors'):
                row['status'] = 'REVIEW_EVIDENCE_UNAVAILABLE'
            if job['id'] == 'P-G4K':
                row['preliminary_gate'] = preliminary(row)
            self.progress['completed'][job['id']] = row
            self.persist_measurement(row)
        return row

    def retained_refusal(self):
        """Aligned refusal is not RELEASE; reprove retained ownership/safety."""
        if getattr(self.host, 'rpc_unavailable', False):
            return False
        if self.host.call('status').get('phase') != 'WARM_HOLD':
            return False
        proof = self.host.call('hold_checkpoint')  # proven danger still raises
        self.hold_save(self.state / 'hold-current.json', proof)
        self.hold_notice('rejected_or_temporarily_unavailable_admission')
        return True

    def hold(self, reason, row_sha=None):
        """Keep the existing detached owner/lease alive; no request service."""
        if reason not in {'complete', 'preliminary_review', 'paused', 'quality_review'} or self.progress['inflight'] or not self.hold_ready:
            raise RuntimeError('postrestart_idle_closed_hold_required')
        self.require_no_faults()
        self.in_hold = True
        receipt = self.host.call('warm_hold', reason=reason,
            **({'preliminary_result_sha256': row_sha} if reason == 'preliminary_review' else {}))
        hold_sha = fixtures.digest(fixtures.canonical(receipt) + b'\n')
        name = 'warm-hold-' + reason + '-' + hold_sha[:16] + '.json'
        self.hold_save(self.state / name, receipt)
        self.hold_save(self.state / 'warm-hold.json', receipt)
        release = {'decision': 'RELEASE', 'source_commit': self.armed['source_commit'],
                   'run_session_id': self.armed['session_id'], 'campaign': self.armed['campaign'],
                   'warm_hold_receipt_sha256': hold_sha}
        self.hold_save(self.state / 'release.template.json', {**release, 'decision': 'NOT_AUTHORIZED'})
        self.progress['phase'] = 'WARM_HOLD_' + reason.upper()
        self.hold_save(self.state / 'status.json', {'phase': self.progress['phase'],
            'receipt_sha256': hold_sha, 'source_commit': self.armed['source_commit'],
            'session_id': self.armed['session_id'], 'original_restore_intent': 'STOPPED/manual', 'active_requests': 0})
        while True:
            self.require_no_faults()
            self.boundary()  # resource danger/interruption still cleans up canonically
            proof = self.host.call('hold_checkpoint')
            self.hold_save(self.state / 'hold-current.json', proof)
            release_path = self.state / 'release.json'
            if release_path.exists():
                try:
                    if protocol.strict_json_loads(release_path.read_bytes()) != release:
                        raise ValueError('postrestart_bound_release_required')
                except (ValueError, OSError, protocol.AgentError):
                    self.hold_notice('rejected_release_mailbox')
                    self.sleep(5)
                    continue
                self.release_requested = True
                self.progress['phase'] = 'EXPLICIT_RELEASE_REQUESTED'
                self.hold_save(self.state / 'status.json', {'phase': self.progress['phase'], 'receipt_sha256': hold_sha})
                return False
            if (not isinstance(proof, dict) or proof.get('phase') != 'WARM_HOLD'
                    or proof.get('guarded') is not True or proof.get('status') != 'HELD'):
                self.hold_notice('current_safe_proof_UNAVAILABLE')
                self.sleep(5)
                continue
            path = self.state / 'long-GO.json'
            if reason == 'preliminary_review' and path.exists():
                try:
                    go = protocol.strict_json_loads(path.read_bytes())
                    validate_long_go(go, self.armed, row_sha)
                    g1_ladder.checkpoint(self.state)
                except (ValueError, OSError, protocol.AgentError, RuntimeError):
                    self.hold_notice('rejected_long_GO_mailbox')
                    self.sleep(5)
                    continue
                # STOP/PAUSE remains admission-stopping until explicit CONTINUE.
                try:
                    grant = self.host.call('resume_measurements', followup_session_id=go['followup_session_id'],
                                   source_commit=go['source_commit'], preliminary_result_sha256=row_sha)
                except Exception:
                    self.safety.setdefault('host', 'HARNESS_FAILURE')
                    raise
                if grant.get('proof_pending') is True and grant.get('admitted') is False:
                    if not self.retained_refusal():
                        raise RuntimeError('STOP_RETAINED_OWNER_UNAVAILABLE')
                    self.sleep(5)
                    continue
                self.admission_paused = False
                self.in_hold = False
                self.record('ROOT_APPROVED_LONG_PAIR')
                return True
            followup_path = self.state / 'followup-GO.json'
            if reason in {'complete', 'quality_review', 'paused'} and followup_path.exists() and not self.followup_sessions:
                from . import postrestart72_followup as followup
                try:
                    candidate = followup.read_candidate(self.state, self.armed, hold_sha,
                        completed_ids=self.progress['completed'], used_sessions=self.followup_sessions)
                    g1_ladder.checkpoint(self.state)
                    # Retain exact accepted authority before asking the live owner.
                    runner.save(self.state / (candidate['go']['request_id'] + '-GO.json'), candidate['go'])
                except (ValueError, OSError, protocol.AgentError, RuntimeError):
                    self.hold_notice('rejected_followup_mailbox')
                    self.sleep(5)
                    continue
                try:
                    grant = self.host.call('admit_followup', go=candidate['go'])
                except Exception:
                    self.safety.setdefault('host', 'HARNESS_FAILURE')
                    raise
                if grant.get('proof_pending') is True and grant.get('admitted') is False:
                    if not self.retained_refusal():
                        raise RuntimeError('STOP_RETAINED_OWNER_UNAVAILABLE')
                    self.sleep(5)
                    continue
                self.followup_sessions.append(candidate['go']['followup_session_id'])
                self.admission_paused = False
                self.in_hold = False
                cid = next(cid for cid, row in self.active.items()
                           if row['manifest']['placement'] == candidate['go']['placement'])
                try:
                    job = followup.prepare_job(candidate, cid, self.counter(cid), templates=TEMPLATES, clock=self.clock)
                    runner.save(self.private / (job['id'] + '-fixture.json'), job['sample'])
                    runner.save(self.private / (job['id'] + '-count.json'), job['count'])
                    row = self.measure(job)
                except AdmissionPaused:
                    self.progress['inflight'].pop(candidate['go']['request_id'], None)
                    return self.hold('paused')
                except (fixtures.HarnessError, ValueError, OSError, EvidenceReview):
                    self.quality_review = True
                    self.progress['inflight'].pop(candidate['go']['request_id'], None)
                    return self.hold('quality_review')
                if row['sample']['status'] == 'TRANSPORT_FAILURE':
                    raise RuntimeError('STOP_UNDRAINED_TRANSPORT_UNCERTAINTY')
                self.quality_review |= row['status'] != 'PASS'
                return self.hold('quality_review' if self.quality_review else 'complete')
            self.sleep(5)

    def preliminary_checkpoint(self, row):
        row_sha = fixtures.digest((self.state / 'P-G4K-result.json').read_bytes())
        snapshot = {'type': 'preliminary_result_before_long_dispatch', 'id': 'P-G4K',
                    'result_sha256': row_sha, 'gate': row['preliminary_gate'],
                    'strict': row['strict'], 'semantic': row['semantic']}
        runner.save(self.state / 'preliminary-gate.json', snapshot)
        self.emit(snapshot)
        print(json.dumps(snapshot, separators=(',', ':')), flush=True)
        self.boundary()
        if row['preliminary_gate']['long_preauthorized']:
            self.record('PREAUTHORIZED_LONG_PAIR')
            return True
        runner.save(self.state / 'long-GO.template.json', {'decision': 'NOT_AUTHORIZED',
            'source_commit': self.armed['source_commit'], 'run_session_id': self.armed['session_id'],
            'campaign': self.armed['campaign'], 'preliminary_result_sha256': row_sha,
            'followup_session_id': 'FRESH_FOLLOWUP_SESSION_REQUIRED'})
        return self.hold('preliminary_review', row_sha)

    def execute(self):
        # Keep fallback review/pause holds inside the same monitor lifetime.
        # The monitor skips idle holds and resumes for a reviewed follow-up;
        # it cannot be stopped before a later admitted HTTP request drains.
        self.stop.clear()
        monitor = threading.Thread(target=self.monitor, daemon=True)
        monitor.start()
        try:
            try:
                self.sequence()
            except (EvidenceReview, OSError):
                if not self.hold_ready:
                    raise
                self.quality_review = True
                self.hold('quality_review')
            except AdmissionPaused:
                if not self.hold_ready:
                    raise RuntimeError('STOP_BEFORE_SAFE_WARM_PAIR')
                self.hold('paused')
        finally:
            self.stop.set()
            monitor.join()

    def sequence(self):
        self.boundary(); self.host.call('begin'); self.record('PREPARING_P')
        admission = self.host.call('admit_concurrent', round='P')
        ids = {m['placement']: self.loaded(m) for m in admission['manifests']}
        if len(self.pending_warmups) != 2:
            raise RuntimeError('postrestart_exact_two_loads_required')
        for index, args in enumerate(self.pending_warmups):
            self.discarded_warmup(*args)
            # Both validated discarded warmups precede retention readiness;
            # current missing resource proof may now retain a guarded review.
            if index == 1:
                self.hold_ready = True
            self.boundary()
        self.emit({'type': 'preparation_complete', 'clock': self.host.call('budget')})
        row = self.measure(self.prepare_job(ids['G1'], 'P-G4K'))
        if row['status'] != 'PASS':
            if row['sample']['status'] == 'TRANSPORT_FAILURE':
                raise RuntimeError('STOP_UNDRAINED_TRANSPORT_UNCERTAINTY')
            self.quality_review = True
            self.hold('quality_review')
            return
        if not self.preliminary_checkpoint(row):
            return
        g, q = self.prepare_job(ids['G1'], 'P-G65008'), self.prepare_job(ids['Q1'], 'P-Qnear480K')
        self.boundary(); self.record('DISPATCHING_P')
        result = cpu_run.execute_pair(g, q, None, self.measure, interrupted=self.interrupted)
        runner.save(self.state / 'P-pair.json', result); self.emit({'type': 'postrestart_pair', **result})
        if result['status'] != 'COMPLETE':
            completed = [v for v in [result['glm'], *result['qwen']] if v is not None
                         and v['id'] not in {e['id'] for e in result['errors']}]
            if (self.admission_paused and result['errors']
                    and all(v['error_class'] == 'AdmissionPaused' for v in result['errors'])
                    and all(v['status'] == 'PASS' for v in completed)):
                # Requests not dispatched by STOP/PAUSE are not quality failures.
                # Each healthy admitted peer has drained through execute_pair.
                raise AdmissionPaused('ROOT_STOP_PAUSE_DRAINED')
            if (any(v['error_class'] == 'EvidenceReview' for v in result['errors'])
                    and all(v['error_class'] in {'EvidenceReview', 'AdmissionPaused'}
                    for v in result['errors']) and all(v.get('sample', {}).get('status') != 'TRANSPORT_FAILURE'
                    for v in completed)):
                # execute_pair has joined every registered peer before review.
                raise EvidenceReview('CURRENT_PROOF_UNAVAILABLE_PEER_DRAINED')
            rows = [v for v in [result['glm'], *result['qwen']] if v is not None]
            if not result['errors'] and all(v.get('sample', {}).get('status') != 'TRANSPORT_FAILURE' for v in rows):
                self.quality_review = True
                self.hold('quality_review')
                return
            raise RuntimeError('STOP_POSTRESTART_PAIR_GATE')
        self.boundary()
        for cid in ids.values():
            self.emit({'type': 'post_pair_quiescent', 'checkpoint': self.host.call('quiescent', id=cid, point='warm_idle')})
        self.record('MEASUREMENTS_COMPLETE')
        self.hold('complete')


def prepare(task, session):
    task = Path(task).resolve()
    if (task / 'arm.json').exists() or not session or glmrepair.git('status', '--porcelain'):
        raise ValueError('postrestart_clean_source_fresh_arm_session_required')
    (task / 'private').mkdir(mode=0o700, exist_ok=True)
    client.private_artifact_directory(task / 'private')
    g1_ladder.checkpoint(task)
    frozen = {}
    for name, (relative, sha) in SAVED.items():
        raw = (task.parent / relative).read_bytes()
        if fixtures.digest(raw) != sha:
            raise ValueError('postrestart_saved_fixture_identity_changed')
        runner.save(task / 'private' / name, protocol.strict_json_loads(raw))
        frozen['private/' + name] = fixtures.digest((task / 'private' / name).read_bytes())
    evidence = protocol.strict_json_loads((task / 'evidence-index.json').read_bytes())
    for label, ref in evidence['refs'].items():
        raw = Path(ref['path']).read_bytes()
        if fixtures.digest(raw) != ref['sha256']:
            raise ValueError('postrestart_saved_evidence_changed')
        name = 'private/saved/' + label + '.json'
        runner.save(task / name, protocol.strict_json_loads(raw)); frozen[name] = fixtures.digest((task / name).read_bytes())
    runner.save(task / 'protected-key-metadata.json', evidence['protected_key_metadata'])
    runner.save(task / 'progress.json', {'phase': 'INITIAL', 'completed': {}, 'inflight': {}, 'errors': []})
    if not (task / 'run-control.json').exists():
        runner.save(task / 'run-control.json', {'action': 'CONTINUE'})
    from .host import concurrent_capacity_policy
    inputs = ['progress.json', 'evidence-index.json', 'protected-key-metadata.json', *frozen]
    armed = {'schema': 1, 'scope': SCOPE, 'campaign': profile.POSTRESTART_CAMPAIGN, 'session_id': session,
        'base_commit': BASE, 'source_commit': glmrepair.git('rev-parse', 'HEAD'), 'runtime_policy': POLICY,
        'runtime_source_path': '/data/services/' + profile.POSTRESTART_CAMPAIGN + '/source',
        'manifests': profile.postrestart_manifests(), 'trial_plan': profile.postrestart_trial_order(),
        'concurrent_capacity_policy': concurrent_capacity_policy(SCOPE), 'frozen_inputs': frozen,
        'source_files': {p: fixtures.digest(b) for p, b in runner.source_files().items()},
        'required_package_files': ['arm.json', 'arm-receipt.json', 'GO.template.json', 'incoming-latest.md', 'run-control.json', *inputs],
        'initial_package_sha256': {name: fixtures.digest((task / name).read_bytes()) for name in inputs},
        'authority_at_prepare_sha256': fixtures.digest((task / 'incoming-latest.md').read_bytes()),
        'production_acceptance': 'NOT_GRANTED', 'measurement_clock': 'NOT_STARTED_PREP_EXCLUDED'}
    profile.validate_postrestart_arm_scope(armed); runner.save(task / 'arm.json', armed)
    receipt = {'source_commit': armed['source_commit'], 'preparation_session_id': session,
               'campaign': armed['campaign'], 'arm_sha256': fixtures.digest((task / 'arm.json').read_bytes())}
    runner.save(task / 'arm-receipt.json', receipt)
    runner.save(task / 'GO.template.json', {**receipt, 'decision': 'NOT_AUTHORIZED', 'vm_writer_handoff': False,
                                          'run_session_id': 'FRESH_RUN_SESSION_REQUIRED', 'runtime': POLICY})
    return armed


def run(task, go_path, session, *, restore_only=False):
    task = Path(task).resolve(); client.private_artifact_directory(task / 'private')
    armed, receipt = [protocol.strict_json_loads((task / name).read_bytes()) for name in ('arm.json', 'arm-receipt.json')]
    go = protocol.strict_json_loads(Path(go_path).read_bytes())
    profile.validate_postrestart_arm_scope(armed)
    if (os.geteuid() == 0 or go.get('decision') != 'GO' or go.get('vm_writer_handoff') is not True
            or any(go.get(k) != v for k, v in receipt.items())
            or receipt['arm_sha256'] != fixtures.digest((task / 'arm.json').read_bytes())
            or armed['source_commit'] != glmrepair.git('rev-parse', 'HEAD') or glmrepair.git('status', '--porcelain')
            or {p: fixtures.digest(b) for p, b in runner.source_files().items()} != armed['source_files']):
        raise ValueError('postrestart_root_source_arm_GO_required')
    cpu_run.verify_frozen(task, armed)
    executed = {**armed, 'runtime': bind_runtime(armed, go, session), 'session_id': session,
                'preparation_arm_sha256': receipt['arm_sha256']}
    execution = task / 'execution-arm.json'
    if restore_only:
        if protocol.strict_json_loads(execution.read_bytes()) != executed:
            raise ValueError('postrestart_recovery_execution_changed')
    else:
        if execution.exists():
            raise ValueError('postrestart_no_rerun_or_clock_reset')
        prior.verify_initial_package(task, armed); g1_ladder.checkpoint(task); runner.save(execution, executed)
    runner.run_preflight(SCOPE)
    key, control = cpu_run._keys(task)
    job = PostrestartRun(task, executed, None, key)  # Full private read-chain BEFORE SSH/staging.
    host = glmrepair.DiagnosticSSHHost(executed, stage=not restore_only); job.host = host
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
                if job.in_hold:
                    safe_save(task / 'hold-current.json', {'phase': 'RECOVERY_REQUIRED',
                        'reason': type(error).__name__, 'current_held_proof': False, 'updated_epoch': time.time()})
                from .host import rpc_diagnostic
                errors.append({'phase': 'measurement', **rpc_diagnostic('measurement', error)})
        try:
            phase = host.call('status')['phase']
            if phase not in {'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'} and (restore_only or phase != 'NEW'):
                host = cpu_run.restore_once(host, executed, task, key, control); restored = True
        except BaseException as error:
            failed = True
            if isinstance(error, cpu_run.RecoveryRequired):
                host = error.recovery_host
            errors.append({'phase': 'restoration', 'error_class': type(error).__name__})
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        try:
            terminal = 'RESTORED' if restored else host.call('status')['phase']
            if terminal in {'RESTORED', 'NEW', 'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'}:
                host.close(); ports = {}
                for port in (31002, 31004):
                    with socket.socket() as sock:
                        sock.settimeout(1); ports[str(port)] = 'CLOSED' if sock.connect_ex(('127.0.0.1', port)) else 'OPEN'
                failed |= set(ports.values()) != {'CLOSED'}
                safe_save(task / 'final-restoration-receipt.json', {'restored': restored,
                    'status': 'RESTORED_WITH_MEASUREMENT_FAILURE' if restored and failed else 'RESTORED' if restored else 'FAIL',
                    'authenticated_worker_LAN': restored, 'local_tunnels': ports, 'original_endstate': 'STOPPED/manual'})
        except BaseException as error:
            failed = True; errors.append({'phase': 'host_close', 'error_class': type(error).__name__})
        outcome = {'measurement_failed': failed, 'restored': restored, 'errors': errors,
            'source_commit': armed['source_commit'], 'session_id': session, 'clock_policy': POLICY,
            'completed': list(job.progress['completed']), 'missing': [v for v in TRIAL_IDS if v not in job.progress['completed']],
            'measurement_status': 'NOT_RUN_RECOVERY_ONLY' if restore_only else 'FAILED' if failed else
                'QUALITY_REVIEW_REQUIRED' if job.quality_review else
                'COMPLETE' if all(v in job.progress['completed'] for v in TRIAL_IDS) else 'RELEASED_PARTIAL',
            'production_acceptance': 'NOT_GRANTED'}
        safe_save(task / ('recovery-outcome.json' if restore_only else 'run-outcome.json'), outcome)
        safe_save(task / 'status.json', {**outcome, 'phase': 'RESTORED' if restored else 'RECOVERY_REQUIRED'})
    return 1 if failed or not restored or errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'run', 'restore'))
    parser.add_argument('--task-dir', type=Path, required=True); parser.add_argument('--session-id', required=True)
    parser.add_argument('--go', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        prepare(args.task_dir, args.session_id); return 0
    if args.go is None:
        parser.error('--go is required for RUN or recovery')
    return run(args.task_dir, args.go, args.session_id, restore_only=args.action == 'restore')

if __name__ == '__main__':
    raise SystemExit(main())
