"""Closed dual-Q PREP contract; not a runnable campaign or lifecycle owner.

Reuse the pinned actual72 Q8 launch, deterministic archive, native counter and
drain helper. Existing host/owner wiring needs separate exact-source RUN review;
this module is deliberately absent from profiles.ARM_SCOPES and staging.
"""
from __future__ import annotations

import json
import shlex
import threading

from . import cpu_budget_profiles as cpu, fixtures, profiles, qwen_launcher
from .concurrent_run import _interval, drain_threads
from .postrestart72_followup import PRESETS
from .concurrent_cpu_run import TEMPLATES

SCOPE = qwen_launcher.DUALQ_SCOPE
CAMPAIGN = "benchrun-dualq72-20260921"
CAPACITY = 480000
OUTPUT_CAP = 512
SLOTS = ("Q0", "Q1")


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
                        "historical_input_tokens": 479487, "output_cap": OUTPUT_CAP} for slot in SLOTS],
            "warmup": {"per_model_per_load": 1, "output_cap": 32, "timing": "discarded"},
            "request_timeout_seconds": 7200, "request_clock_starts": "HTTP_DISPATCH",
            "expected_duration_seconds": [240, 360], "expected_duration_is_limit": False,
            "extra_measured_requests": 0, "retries": 0, "require_actual_request_overlap": True,
            "historical_count_is_live_proof": False, "refit": False}


def prepare_job(slot, nonce, counter):
    """Recount final aliased 512-output bytes; no fitting, inference or writes."""
    declared = manifest(slot)
    preset = PRESETS["P-Qnear480K"]
    if not isinstance(nonce, str) or not nonce.startswith("fresh-"):
        raise ValueError("dualq_fresh_prefix_required")
    sample = fixtures.build_sample(declared["transport"]["model_alias"], preset["records"],
                                   preset["seed"], nonce, output_cap=OUTPUT_CAP)
    if (sample["fixture_sha256"] != preset["fixture_sha256"] or
            fixtures.digest(fixtures.canonical(sample["scorer"])) != preset["scorer_sha256"]):
        raise ValueError("dualq_frozen_logical_fixture_changed")
    raw = fixtures.serialize_validate(sample)
    count = fixtures.validate_count(counter(raw), raw, CAPACITY)
    # Native scheduler request cap is pool-1. Template is included in the actual
    # count; 479488+512 cannot fit, although an old 256-output fixture could.
    if (count["template_sha256"] != TEMPLATES["Q1"] or
            not preset["input_tokens_minimum"] <= count["input_tokens"] <= 479487 or
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
                not job["sample"]["nonce"].startswith("fresh-") or
                job["sample"]["fixture_sha256"] != PRESETS["P-Qnear480K"]["fixture_sha256"]):
            raise ValueError("dualq_job_changed_before_dispatch")
        count = fixtures.validate_count(job["count"], job["raw"], CAPACITY)
        if (count["template_sha256"] != TEMPLATES["Q1"] or
                not PRESETS["P-Qnear480K"]["input_tokens_minimum"] <= count["input_tokens"] <= 479487):
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
    result.update(request_overlap_seconds=overlap,
                  overlap_basis="worker dispatch/drain intervals; not native simultaneous GPU execution proof",
                  status="PASS" if not result["errors"] and overlap is not None and overlap > 0 and
                         all(result["slots"].get(slot, {}).get("status") == "PASS" for slot in SLOTS) else "REVIEW_REQUIRED")
    return result
