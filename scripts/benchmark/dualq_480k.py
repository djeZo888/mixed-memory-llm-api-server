"""Closed Q0/Q1 campaign through the existing canonical benchmark owner.

PREP imports are inert. One load/warmup each, one sealed simultaneous pair, then
canonical STOPPED/manual restoration. RUN requires exact source/arm root GO.
"""
from __future__ import annotations

import json
import shlex
import threading
import math
from pathlib import Path

from agent import protocol

from . import cpu_budget_profiles as cpu, fixtures, profiles, qwen_launcher
from . import accounting, client, concurrent_run, runner
from .warmup import prefill_proof
from .postrestart72_run import POLICY
from .concurrent_run import _interval, drain_threads
from .postrestart72_followup import PRESETS
from .concurrent_cpu_run import TEMPLATES

SCOPE = qwen_launcher.DUALQ_SCOPE
CAMPAIGN = "benchrun-dualq72-20260921"
CAPACITY = 480000
OUTPUT_CAP = 512
SLOTS = ("Q0", "Q1")
# Freeze short, distinct, never-used campaign prefixes before any model load.
PREFIXES = {slot: "fresh-dualq-20260921-" + slot.lower() for slot in SLOTS}
RECORDS = 12148  # two rows fewer than historical12150, approximately79 tokens
INPUT_TARGET = 479423  # deliberately64 below prior479487; actual native count governs
INPUT_MINIMUM = 479360
INPUT_MAXIMUM = 479487
FIXTURE = fixtures.build_sample("bench-qwen3.8-27b", RECORDS,
    PRESETS["P-Qnear480K"]["seed"], PREFIXES["Q1"], output_cap=OUTPUT_CAP)["fixture_sha256"]


def validate_clock(armed, runtime):
    if armed.get("runtime_policy") != POLICY or runtime != POLICY:
        raise ValueError("dualq_independent_dispatch_clock_required")
    return None, None


def resource_policy():
    policy = cpu.resource_policy()
    policy.update(id="dualq72-480k-working-set-estimate-15pct-v1",
                  caps_bytes={slot: 32 * 1024**3 for slot in SLOTS},
                  fresh_initial_host_available_bytes=80 * 1024**3)
    return policy


def manifest(slot):
    """Exactly two distinct GPU/port/alias tuples; no caller tuning fields."""
    if slot not in SLOTS:
        raise ValueError("dualq_exact_physical_slot_required")
    previous = cpu.postrestart_manifest("Q1")
    identifier = f"{CAMPAIGN}-{slot.lower()}-{CAPACITY}"
    encoded = json.dumps(previous).replace(previous["container_name"], identifier)
    encoded = encoded.replace(previous["campaign"], CAMPAIGN)
    encoded = encoded.replace(f"/{CAMPAIGN}/p/q1", f"/{CAMPAIGN}/{slot.lower()}")
    value = json.loads(encoded)
    port, alias = qwen_launcher.endpoint(SCOPE, slot)
    uuid = profiles.read_config()["gpu_uuids"][SLOTS.index(slot)]
    value.update(scope=SCOPE, campaign=CAMPAIGN, layout="QQ", placement=slot,
                 gpu_uuids=[uuid], active_guest_vcpus=8,
                 cpu_comparison="Actual72 guest; both Q8 cpusets0-7 overlap fully; union8, exclusive0; no physical pinning claim",
                 resource_policy=resource_policy())
    args = value["create_argv"]
    cpu._set(args, "--gpus", '"device=' + uuid + '"')
    cpu._set(args, "--publish", f"127.0.0.1:{port}:{port}/tcp")
    cpu._set(args, "--scope", SCOPE)
    args[args.index("benchmark.placement=Q1")] = "benchmark.placement=" + slot
    args += ["--slot", slot]
    base = qwen_launcher.pinned_base(profiles.ROOT / "scripts/runtime/sglang38_file_auth.py")
    value["native_argv"] = qwen_launcher.variant(base, CAPACITY, 1, scope=SCOPE, slot=slot)
    profile_path = "configs/deployments/qwen38-27b-" + slot.lower() + "-480000-yarn4-bf16kv.json"
    profile_raw = (profiles.ROOT / profile_path).read_bytes()
    production = json.loads(profile_raw)
    value["production_profile"] = {"id": production["id"], "path": profile_path,
        "sha256": fixtures.digest(profile_raw), "base_commit": "f130ec46ebd9a27319d84e0d372746e0489a9972",
        "temporary_differences": ["benchmark_container_paths_names", "native_loopback_ports31002_31004", "benchmark_model_aliases"]}
    pair = profiles.candidate_pair_wrapper()
    expected_native = pair.backend_argv(base, "gpu" + str(SLOTS.index(slot)))
    for flag, replacement in (("--port", str(port)), ("--served-model-name", alias)):
        expected_native[expected_native.index(flag) + 1] = replacement
    if (value["native_argv"] != expected_native or production["launch"]["gpus"] != [uuid] or
            production["concurrent_pair"]["guest_cpuset"] != "0-7" or
            production["concurrent_pair"]["memory_bytes"] != value["ram_cap_bytes"]):
        raise ValueError("dualq_frozen_production_profile_mismatch")
    value["transport"].update(port=port, model_alias=alias)
    value["create_shell"] = shlex.join(args)
    value["mandatory_run_gates"] = [
        "root releases predecessor to captured STOPPED/manual before fresh existing canonical owner; PREP never releases",
        "exact source/guard/storage/lease/model/image/key identity; no production acceptance fabricated",
        "actual online CPUs0-71; two Q8 cpusets0-7 shared, union8 exclusive0; no cpuset-mems change",
        "fresh80GiB host available; each32GiB cap/no swap; sampled required working-set estimate*1.15<=cap",
        "each physical GPU UUID separately proven; >=16GiB and >=10pct free GPU reserve",
        "each actual scheduler pool480000/input479994/request479999, current authenticated allocation/native-auth proof",
        "one discarded32-output warmup per load; one exact native-counted512-output retrieval per physical GPU",
        "one barrier pair only; immutable dispatch+7200s deadline; actual overlap required; no retry/filler/300s cutoff",
        "canonical cleanup/restoration to STOPPED/manual before protected reviewed production acceptance and activation",
    ]
    return value


def trial_plan():
    return {"scope": SCOPE, "measured_pairs": 1, "measured_requests": 2,
            "trials": [{"id": slot + "-near480K", "slot": slot,
                        "historical_input_tokens": 479487, "nominal_input_target": INPUT_TARGET,
                        "records": RECORDS, "prefix": PREFIXES[slot], "output_cap": OUTPUT_CAP} for slot in SLOTS],
            "warmup": {"per_model_per_load": 1, "output_cap": 32, "timing": "discarded"},
            "request_timeout_seconds": 7200, "request_clock_starts": "HTTP_DISPATCH",
            "expected_duration_seconds": [240, 360], "expected_duration_is_limit": False,
            "extra_measured_requests": 0, "retries": 0, "require_actual_request_overlap": True,
            "historical_count_is_live_proof": False, "refit": False,
            "prompt_reduction": "nominal64-token target reduction; two archive rows removed (approximately79 tokens), exact native recount governs",
            "input_count_window": [INPUT_MINIMUM, INPUT_MAXIMUM]}


def prepare_job(slot, nonce, counter):
    """Recount final aliased 512-output bytes; no fitting, inference or writes."""
    declared = manifest(slot)
    preset = PRESETS["P-Qnear480K"]
    if not isinstance(nonce, str) or nonce != PREFIXES[slot]:
        raise ValueError("dualq_fresh_prefix_required")
    sample = fixtures.build_sample(declared["transport"]["model_alias"], RECORDS,
                                   preset["seed"], nonce, output_cap=OUTPUT_CAP)
    if (sample["fixture_sha256"] != FIXTURE or
            fixtures.digest(fixtures.canonical(sample["scorer"])) != preset["scorer_sha256"]):
        raise ValueError("dualq_frozen_logical_fixture_changed")
    raw = fixtures.serialize_validate(sample)
    count = fixtures.validate_count(counter(raw), raw, CAPACITY)
    # Native scheduler request cap is pool-1. Template is included in the actual
    # count; 479488+512 cannot fit, although an old 256-output fixture could.
    if (count["template_sha256"] != TEMPLATES["Q1"] or
            not INPUT_MINIMUM <= count["input_tokens"] <= INPUT_MAXIMUM or
            count["input_tokens"] + OUTPUT_CAP > CAPACITY - 1):
        raise ValueError("dualq_native_template_or_capacity_mismatch_no_refit")
    return {"id": slot + "-near480K", "slot": slot, "manifest": declared,
            "sample": sample, "raw": raw, "count": count}


def execute_pair(jobs, invoke):
    """One pair only through an already authorized caller; drain a healthy peer.

    The existing durable owner must seal one-use admission before calling this
    helper. Local return values cannot authorize replay after failure/interruption.
    """
    if not isinstance(jobs, list) or len(jobs) != 2 or [job.get("slot") for job in jobs] != list(SLOTS):
        raise ValueError("dualq_exact_two_physical_jobs_required")
    for job in jobs:
        if (job["id"] != job["slot"] + "-near480K" or job["manifest"] != manifest(job["slot"]) or
                job["raw"] != fixtures.serialize_validate(job["sample"]) or
                job["sample"]["body"]["model"] != job["manifest"]["transport"]["model_alias"] or
                job["sample"]["body"]["max_tokens"] != OUTPUT_CAP or
                job["sample"]["nonce"] != PREFIXES[job["slot"]] or
                job["sample"]["fixture_sha256"] != FIXTURE):
            raise ValueError("dualq_job_changed_before_dispatch")
        count = fixtures.validate_count(job["count"], job["raw"], CAPACITY)
        if (count["template_sha256"] != TEMPLATES["Q1"] or
                not INPUT_MINIMUM <= count["input_tokens"] <= INPUT_MAXIMUM):
            raise ValueError("dualq_count_changed_before_dispatch")
    if jobs[0]["sample"]["nonce"] == jobs[1]["sample"]["nonce"]:
        raise ValueError("dualq_distinct_fresh_prefixes_required")
    barrier = threading.Barrier(2)
    result = {"slots": {}, "errors": []}
    lock = threading.Lock()

    def lane(job):
        try:
            barrier.wait()
            row = invoke(job, timeout_seconds=7200)
            if not isinstance(row, dict):
                raise ValueError("dualq_request_result_unavailable")
            with lock:
                result["slots"][job["slot"]] = row
        except BaseException as error:
            with lock:
                result["errors"].append({"slot": job["slot"], "error_class": type(error).__name__})

    threads = [threading.Thread(target=lane, args=(job,)) for job in jobs]
    try:
        for thread in threads:
            thread.start()
    except BaseException:
        barrier.abort()
        drain_threads(threads)
        raise
    drain_threads(threads)
    intervals = [_interval(result["slots"].get(slot), "request") for slot in SLOTS]
    overlap = max(0, min(interval[1] for interval in intervals) - max(interval[0] for interval in intervals)) if all(intervals) else None
    result.update(actual_pair_duration_seconds=(max(i[1] for i in intervals)-min(i[0] for i in intervals)) if all(intervals) else None,
                  tail_seconds={slot: max(0, intervals[index][1]-intervals[1-index][1])
                                for index, slot in enumerate(SLOTS)} if all(intervals) else None,
                  request_overlap_seconds=overlap,
                  overlap_basis="worker dispatch/drain intervals; not native simultaneous GPU execution proof",
                  status="PASS" if not result["errors"] and overlap is not None and overlap > 0 and
                         all(result["slots"].get(slot, {}).get("status") == "PASS" for slot in SLOTS) else "REVIEW_REQUIRED")
    return result


class DualQRun(concurrent_run.ConcurrentRun):
    """Only the closed two-role experiment; ownership stays in CampaignOwner."""

    def __init__(self, state, *args, **kwargs):
        client.private_artifact_directory(Path(state) / 'private')
        super().__init__(state, *args, **kwargs)
        profiles.validate_arm_scope(self.armed)
        self.counted = set()
        self.dispatch_barrier = threading.Barrier(2)

    def boundary(self):
        super().boundary()
        if self.proof_pending is not None:
            raise RuntimeError('CURRENT_RESOURCE_PROOF_UNAVAILABLE')

    def admission(self, cid, maximum=7200, *, measured=False, request_identity=None):
        self.boundary()
        with self.lock:
            if self.safety or self.active[cid]['cancel_event'].is_set():
                raise RuntimeError('STOP_RESOURCE_OR_CANCEL')
            grant = self.host.call('request_begin', id=cid, timeout_s=maximum,
                                   measured=measured, request_identity=request_identity)
        if grant.get('proof_pending') or grant.get('timeout_s') != maximum:
            raise RuntimeError('CURRENT_RESOURCE_PROOF_OR_FULL_REQUEST_WINDOW_UNAVAILABLE')
        return maximum

    def counter(self, cid, *, purpose):
        m = self.active[cid]['manifest']
        slot = m['placement']
        if purpose not in ('warmup', 'measured'):
            raise ValueError('dualq_closed_count_purpose')

        def count(raw):
            marker = (slot, purpose)
            if marker in self.counted:
                raise RuntimeError('dualq_no_count_refit_or_retry')
            self.counted.add(marker)
            identity = {'purpose': 'count', 'request_id': slot + '-count-' + purpose,
                        'request_sha256': fixtures.digest(raw),
                        'manifest_sha256': fixtures.digest(fixtures.canonical(m))}
            timeout = self.admission(cid, 120, request_identity=identity)
            terminal = 'COUNT_FAILED'
            try:
                call = self.json_factory('http://127.0.0.1:' + str(m['transport']['port']),
                                         self.key, timeout=timeout)
                native = accounting.native_counter(m['transport']['model_alias'], CAPACITY, call,
                    qwen_template_sha256=self.active[cid]['template_sha256'], scope=SCOPE)
                value = native(raw)
                terminal = 'COUNT_DRAINED'
                return value
            finally:
                self.host.call('request_end', id=cid, request_identity=identity, terminal_reason=terminal)
        return count

    def request(self, cid, raw, identifier, *, timed=True, **kwargs):
        m = self.active[cid]['manifest']
        slot = m['placement']
        body = protocol.strict_json_loads(raw)
        expected_id = slot + ('-near480K' if timed else '-warmup')
        if (identifier != expected_id or body.get('model') != m['transport']['model_alias'] or
                body.get('max_tokens') != (OUTPUT_CAP if timed else 32) or body.get('stream') is not True):
            raise ValueError('dualq_closed_request_identity')
        identity = {'purpose': 'measured' if timed else 'warmup', 'request_id': identifier,
                    'request_sha256': fixtures.digest(raw),
                    'manifest_sha256': fixtures.digest(fixtures.canonical(m))}
        try:
            timeout = self.admission(cid, measured=timed, request_identity=identity)
        except BaseException:
            if timed:
                self.dispatch_barrier.abort()
            raise
        terminal = 'TRANSPORT_ERROR'
        transport = None
        crossed = False
        try:
            transport = self.transport_factory('http://127.0.0.1:' + str(m['transport']['port']), self.key,
                cancel_event=self.active[cid]['cancel_event'], deadline_epoch=None)
            transport.redact = lambda data: data.replace(self.key.encode('ascii'), b'[REDACTED]')
            if timed:
                # Both current owner admissions complete before either HTTP dispatch.
                # This wait occurs before each independent7200s transport clock.
                self.dispatch_barrier.wait(timeout=180)
                crossed = True
            result = client._capture_request(raw, transport, sample_id=identifier, private_dir=self.private,
                summary_path=self.state / ('samples.jsonl' if timed else 'warmups.jsonl'),
                timeout=timeout, clock=self.clock)
            request_clock = getattr(transport, 'request_clock', {})
            result['summary']['request_clock'] = request_clock
            raw_terminal = request_clock.get('terminal_reason')
            terminal = {'DRAINED': 'DRAINED', 'REQUEST_DEADLINE': 'REQUEST_DEADLINE',
                        'RESOURCE_CANCEL': 'CANCELLED'}.get(raw_terminal, 'TRANSPORT_ERROR')
            if self.active[cid].get('abort_reason'):
                raise RuntimeError(self.active[cid]['abort_reason'])
            return result
        finally:
            if timed and not crossed:
                self.dispatch_barrier.abort()
            # Timeout/cancel is not native idle. Host retains unresolved registry
            # until both lanes drain and canonical restoration stops exact owners.
            if transport is not None:
                raw_terminal = getattr(transport, 'request_clock', {}).get('terminal_reason')
                terminal = {'DRAINED': 'DRAINED', 'REQUEST_DEADLINE': 'REQUEST_DEADLINE',
                            'RESOURCE_CANCEL': 'CANCELLED'}.get(raw_terminal, terminal)
            self.host.call('request_end', id=cid, request_identity=identity, terminal_reason=terminal)

    def warm(self, cid, m, proof):
        sample = fixtures.build_sample(m['transport']['model_alias'], 80, 'warmup-only-seed',
                                       'warmup-dualq-' + m['placement'].lower())
        body = dict(sample['body'], max_tokens=32)
        raw = fixtures.canonical(body)
        count = fixtures.validate_count(self.counter(cid, purpose='warmup')(raw), raw, CAPACITY)
        if count['template_sha256'] != TEMPLATES['Q1'] or not 2048 <= count['input_tokens'] <= 4096:
            raise RuntimeError('dualq_bounded_warmup_count_required')
        identifier = m['placement'] + '-warmup'
        runner.save(self.private / (identifier + '-count.json'), count)
        response = self.request(cid, raw, identifier, timed=False)
        counters = response['summary'].get('counters', {})
        if (not response.get('parsed') or response['summary']['status'] not in {'COMPLETE', 'OUTPUT_LIMIT'} or
                counters.get('prompt_tokens') != count['input_tokens'] or
                type(counters.get('completion_tokens')) is not int or not 0 < counters['completion_tokens'] <= 32):
            raise RuntimeError('STOP_WARMUP_NATIVE_COUNT')
        evidence = prefill_proof(counters, m, proof)
        self.emit({'type': 'warmup', 'id': identifier, 'family': 'Qwen', 'count': count,
                   'prefill_proof': evidence, 'timings': 'DISCARDED', 'sample': response['summary'],
                   'checkpoint': self.host.call('quiescent', id=cid, point='warm_idle')})
        self.boundary()

    def prepared(self, cid, slot):
        self.boundary()
        started = self.clock()
        job = prepare_job(slot, PREFIXES[slot], self.counter(cid, purpose='measured'))
        job.update(cid=cid, manifest_sha256=fixtures.digest(fixtures.canonical(job['manifest'])),
                   generation=False, preparation_seconds=self.clock()-started)
        runner.save(self.private / (job['id'] + '-fixture.json'), job['sample'])
        runner.save(self.private / (job['id'] + '-count.json'), job['count'])
        return job

    def persist_measurement(self, row):
        """Keep actual Q counters unknown when absent; label client proxies."""
        from .cpu_budget_telemetry import summarize_measurement
        slot = row['id'].split('-')[0]
        cid = next(cid for cid, entry in self.active.items() if entry['manifest']['placement'] == slot)
        summary = row['sample']
        counters, timing = summary.get('counters', {}), summary.get('client_timing', {})
        prompt, output = counters.get('prompt_tokens'), counters.get('completion_tokens')
        first, last = timing.get('ttft_any_output_seconds'), timing.get('last_output_seconds')
        finite = lambda n: type(n) in (int, float) and math.isfinite(n)
        samples = [v['cpu_budget'] for v in self.samples.get(cid, []) if 'cpu_budget' in v]
        row.update(slot=slot, model_family='Qwen', configured_capacity=CAPACITY, output_cap=OUTPUT_CAP,
            actual_output_tokens=output, nominal_input_target=INPUT_TARGET,
            input_target_policy=trial_plan()['prompt_reduction'],
            cpu_evidence=summarize_measurement(samples, summary, scope=SCOPE),
            native_cache_policy={'disable_radix_cache': True, 'basis': 'validated_native_argv_and_readiness',
                                 'cached_tokens': counters.get('cached_tokens')},
            client_proxies={'basis': 'client_output_event_arrival; not native prefill/decode timing',
                'prefill_tokens_per_second': prompt/first if type(prompt) is int and finite(first) and first > 0 else None,
                'decode_tokens_per_second': (output-1)/(last-first) if type(output) is int and output > 1 and
                    finite(first) and finite(last) and last > first else None},
            limitations=['one_pair_only', 'sampled_peaks_not_absolute', 'output_cap_is_not_actual_output',
                         'native_Qwen_timing_and_cache_may_be_unavailable', 'shared_Q8_affinity_not_exclusive_CPU'])
        super().persist_measurement(row)

    def sequence(self):
        self.host.call('begin')
        self.boundary()
        self.record('PREPARING_QQ')
        admission = self.host.call('admit_concurrent', round='QQ')
        if admission['manifests'] != [manifest(slot) for slot in SLOTS]:
            raise RuntimeError('dualq_exact_physical_manifests_required')
        ids = {m['placement']: self.loaded(m) for m in admission['manifests']}
        jobs = [self.prepared(ids[slot], slot) for slot in SLOTS]
        self.boundary()
        self.host.call('seal_dualq', binding={job['slot']: {
            'request_id': job['id'], 'request_sha256': fixtures.digest(job['raw']),
            'manifest_sha256': job['manifest_sha256']} for job in jobs})
        self.record('DISPATCHING_QQ')
        result = execute_pair(jobs, lambda job, timeout_seconds: self.measure(job))
        self.emit({'type': 'dualq_pair', **result})
        runner.save(self.state / 'dualq-pair.json', result)
        self.record('MEASUREMENTS_COMPLETE' if result['status'] == 'PASS' else 'MEASUREMENTS_REVIEW_REQUIRED')
        if result['status'] != 'PASS':
            raise RuntimeError('dualq_pair_requires_root_review')
