"""Closed REAL72 B3-only two-request contract; no transport, lifecycle or import I/O.

The fresh reviewed owner counts and registers every exact body. Historical
retrieval and diagnostic validators remain unchanged; this sealed mode admits
only the final concurrent B3 retrieval pair at configured480000.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import time

from agent import protocol
from . import cpu_budget_profiles as profile, decode_diag, fixtures, g1_ladder
from . import postrestart72_followup as followup

CASES = (("B3-G65008", "B3-Qnear480K"),)
REQUEST_IDS = tuple(identifier for case in CASES for identifier in case)
REQUEST_PLACEMENTS = dict(zip(REQUEST_IDS, ("G1", "Q1")))
PRESETS = {"B1-G4K": "P-G4K", "B1-Qnear480K": "P-Qnear480K",
           "B3-G65008": "P-G65008", "B3-Qnear480K": "P-Qnear480K"}
SCIENCE_ID = "B2-Gscience"
SCIENCE_BODY_SHA256 = "adfc0b6c1225ac5dc1f7e8ddb5c8022911c9a4551e48fd201d2228bc3abe86fe"
POLICY = {"measurement_admission_seconds": 21600, "request_timeout_seconds": 7200,
          "request_clock_starts": "HTTP_DISPATCH", "admission_deadline_refuses_new_only": True}


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def trial_order():
    """The arm seals this exact sequence; no speed or quality retry gate."""
    trials = []
    for identifier in REQUEST_IDS:
        science = identifier == SCIENCE_ID
        preset = followup.PRESETS[PRESETS[identifier]] if not science else None
        row = {"id": identifier, "layout": "P", "case": identifier[:2],
               "placement": REQUEST_PLACEMENTS[identifier], "configured_capacity": 480000,
               "output_cap": 4096 if science else 256, "kind": "scientific" if science else "retrieval",
               "peer_condition": "Qwen_loaded_idle" if science else "simultaneous_pair_actual_overlap_reported"}
        if science:
            row.update(request_sha256=SCIENCE_BODY_SHA256,
                       input_policy="exact decode_diag.long_body bytes, native recount input+4096<=480000")
        else:
            row.update(preset=PRESETS[identifier], frozen_records=preset["records"],
                       fixture_sha256=preset["fixture_sha256"],
                       saved_input_tokens={"P-G4K": 3546, "P-G65008": 65008, "P-Qnear480K": 479487}[PRESETS[identifier]],
                       input_range=[preset["input_tokens_minimum"], preset["input_tokens_maximum"]],
                       input_policy="historical logical fixture, unique fresh leading prefix, exact native count, no refit")
        trials.append(row)
    return {"mode": profile.POSTRESTART_BATCH_MODE, "trials": trials, "mixed_jobs": [],
            "cases": [{"id": case[0].split("-", 1)[0], "request_ids": list(case),
                       "dispatch": "simultaneous" if len(case) == 2 else "single_Qwen_resident_idle",
                       "next_case": "only after all entered requests confirmed drained and fresh current proof"}
                      for case in CASES],
            "rounds": [{"id": "P", "layout": "P", "glm_capacity": 480000, "qwen_capacity": 480000,
                        "pairs": 1, "qwen_max_requests": 1}],
            "loads": 2, "initial_measured_requests": 2,
            "warmup": {"per_model_per_load": 1, "output_cap": 32,
                       "glm_occupied_target": "approximately4K", "qwen_occupied_target": "approximately3251",
                       "timing": "discarded", "performance_gate": False},
            "maximum_request_seconds": 7200, "preparation_seconds": 7200,
            "measurement_budget_seconds": 21600, "clock_includes_preparation": False,
            "budget_start": "first_measurement_admission",
            "request_deadline": "immutable actual HTTP dispatch +7200s; never clipped by admission deadline",
            "admission_deadline": "refuses NEW measured requests only; admitted requests drain to own deadline",
            "science_timeout": "retain partial TIMEOUT; cancel/drain exact owned request; continue only after verified quiescence and fresh proof",
            "transport_uncertainty": "not a healthy timeout; no next case before confirmed drain",
            "format_failure_policy": "retain correctness, strict format and completion separately; no retry or later-case speed gate",
            "slow_glm_policy": "finish authorized cases unless proven safety or identity danger or unresolvable undrained transport",
            "output_length": "caps include native reasoning; actual output and final answer length are outcomes",
            "additional_cases": "none; exactly one GLM and one Qwen measured request in B3 only, no fillers or repeats",
            "restoration_outside_budget": True, "endstate": "safely drained complete or partial outcomes retain guarded_owned_WARM_HOLD"}


BATCH_PLAN_SHA256 = fixtures.digest(fixtures.canonical(trial_order()))


def science_sample():
    return {"kind": "generation", "fixture_sha256": SCIENCE_BODY_SHA256,
            "body": protocol.strict_json_loads(decode_diag.long_body()), "scorer": None}


def validate_body(identifier, raw, sample=None):
    """Validate fixed body policy locally or at the existing registered count seam."""
    _require(identifier in REQUEST_IDS and isinstance(raw, bytes), "batch_exact_request_required")
    if identifier == SCIENCE_ID:
        _require((sample is None or sample == science_sample()) and raw == decode_diag.long_body() and
                 fixtures.digest(raw) == SCIENCE_BODY_SHA256, "batch_exact_scientific_body_required")
        return science_sample()
    body = protocol.strict_json_loads(raw)
    _require(isinstance(body, dict), "batch_exact_retrieval_body_required")
    if sample is None:
        messages = body.get("messages")
        _require(isinstance(messages, list) and len(messages) == 1 and isinstance(messages[0], dict)
                 and isinstance(messages[0].get("content"), str), "batch_retrieval_message_required")
        first = messages[0]["content"].split("\n", 1)[0]
        _require(first.startswith("trial-prefix=fresh-"), "batch_fresh_leading_prefix_required")
        preset = followup.PRESETS[PRESETS[identifier]]
        sample = fixtures.build_sample("bench-glm-5.3" if REQUEST_PLACEMENTS[identifier] == "G1" else
                                       "bench-qwen3.8-27b", preset["records"], preset["seed"], first[len("trial-prefix="):])
    fixture_raw = fixtures.canonical(sample)
    go = {"preset": PRESETS[identifier], "placement": REQUEST_PLACEMENTS[identifier],
          "request_sha256": fixtures.digest(raw), "fixture_sha256": fixtures.digest(fixture_raw)}
    return followup.validate_payload(go, raw, fixture_raw)


def build_body(identifier, private_dir, nonce=None):
    """Reuse hash-verified private historical inputs; scientific bytes have no nonce."""
    _require(identifier in REQUEST_IDS, "batch_exact_request_required")
    if identifier == SCIENCE_ID:
        raw = decode_diag.long_body()
        return validate_body(identifier, raw), raw
    private = Path(private_dir)
    preset = followup.PRESETS[PRESETS[identifier]]
    model = "bench-glm-5.3" if REQUEST_PLACEMENTS[identifier] == "G1" else "bench-qwen3.8-27b"
    if identifier == "B1-G4K":
        frozen = protocol.strict_json_loads(followup._private_read(private / "G4K-original-fixtures.json", 64*1024*1024))["bench-glm-5.3-4096-retrieval"]
    else:
        frozen = protocol.strict_json_loads(followup._private_read(private / ("G1-frozen.json" if model == "bench-glm-5.3" else "Q480-frozen.json"), 64*1024*1024))
    sample = fixtures.build_sample(model, preset["records"], preset["seed"], nonce)
    _require(all(sample[k] == frozen[k] for k in ("seed", "records", "fixture_sha256", "scorer")),
             "batch_historical_logical_fixture_changed")
    if identifier == "B1-G4K":
        body = protocol.strict_json_loads(followup._private_read(private / "G4K-original.request.json", 64*1024*1024))
        _require(body["messages"][0]["content"].split("\n", 1)[1] ==
                 sample["body"]["messages"][0]["content"].split("\n", 1)[1], "batch_historical_short_archive_changed")
        body["messages"][0]["content"] = sample["body"]["messages"][0]["content"]
        raw = fixtures.canonical(body)
    else:
        raw = g1_ladder.body_bytes(sample) if model == "bench-glm-5.3" else fixtures.serialize_validate(sample)
    validate_body(identifier, raw, sample)
    return sample, raw


def validate_count(identifier, raw, count, *, template_sha256):
    """One exact native recount, preserving current retrieval ranges and reserve."""
    validate_body(identifier, raw)
    checked = fixtures.validate_count(count, raw, 480000)
    _require(checked["template_sha256"] == template_sha256, "batch_native_template_mismatch")
    if identifier == SCIENCE_ID:
        _require(checked["input_tokens"] + 4096 <= 480000, "batch_scientific_capacity_exceeded")
        body = protocol.strict_json_loads(raw)
        normalized = {k: v for k, v in body.items() if k not in ("stream", "stream_options")}
        _require(checked.get("count_body_sha256") == fixtures.digest(fixtures.canonical(normalized)) and
                 checked.get("count_transport_normalization") == {"removed_fields": ["stream", "stream_options"]},
                 "batch_scientific_count_normalization_mismatch")
    else:
        preset = followup.PRESETS[PRESETS[identifier]]
        _require(preset["input_tokens_minimum"] <= checked["input_tokens"] <= preset["input_tokens_maximum"] and
                 checked["input_tokens"] + 512 <= 480000, "batch_native_count_outside_fixed_range_no_refit")
    return checked


def prepare_job(identifier, raw, sample, cid, counter, *, campaign, templates, session_id, clock=time.monotonic):
    started = clock()
    _require(campaign == profile.POSTRESTART_BATCH_CAMPAIGN and isinstance(session_id, str) and
             bool(re.fullmatch(r"[A-Za-z0-9_-]{8,96}", session_id)), "batch_campaign_session_required")
    sample = validate_body(identifier, raw, sample)
    placement = REQUEST_PLACEMENTS[identifier]
    manifest = profile.postrestart_manifest(placement, campaign)
    count = validate_count(identifier, raw, counter(raw), template_sha256=templates[placement])
    return {"id": identifier, "cid": cid, "sample": sample, "raw": raw, "count": count,
            "manifest_sha256": fixtures.digest(fixtures.canonical(manifest)),
            "generation": identifier == SCIENCE_ID, "preparation_seconds": clock() - started,
            "batch_plan_sha256": BATCH_PLAN_SHA256, "batch_session_id": session_id}


def bind_jobs(jobs, *, source_commit, session_id):
    """Small public identity envelope; raw prompt/scorer bytes stay private."""
    _require([job["id"] for job in jobs] == list(REQUEST_IDS), "batch_exact_two_jobs_required")
    prefixes = []
    requests = []
    for job in jobs:
        sample = validate_body(job["id"], job["raw"], job["sample"])
        _require(job.get("batch_plan_sha256") == BATCH_PLAN_SHA256 and
                 job.get("batch_session_id") == session_id and
                 job["count"].get("body_sha256") == fixtures.digest(job["raw"]), "batch_job_binding_changed")
        if job["id"] != SCIENCE_ID:
            prefixes.append(sample["nonce"])
        requests.append({"request_id": job["id"], "placement": REQUEST_PLACEMENTS[job["id"]],
                         "request_sha256": fixtures.digest(job["raw"]), "manifest_sha256": job["manifest_sha256"],
                         "count_sha256": fixtures.digest(fixtures.canonical(job["count"]))})
    _require(len(prefixes) == len(set(prefixes)) == 2, "batch_unique_fresh_prefixes_required")
    value = {"version": 1, "campaign": profile.POSTRESTART_BATCH_CAMPAIGN,
             "source_commit": source_commit, "session_id": session_id,
             "batch_plan_sha256": BATCH_PLAN_SHA256, "requests": requests}
    return validate_binding(value, source_commit=source_commit, session_id=session_id)


def validate_binding(value, *, source_commit, session_id):
    fields = {"version", "campaign", "source_commit", "session_id", "batch_plan_sha256", "requests"}
    _require(type(value) is dict and set(value) == fields and type(value["version"]) is int and value["version"] == 1 and
             value["campaign"] == profile.POSTRESTART_BATCH_CAMPAIGN and
             value["source_commit"] == source_commit and isinstance(source_commit, str) and
             bool(re.fullmatch(r"[0-9a-f]{40}", source_commit)) and value["session_id"] == session_id and
             isinstance(session_id, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{8,96}", session_id)) and
             value["batch_plan_sha256"] == BATCH_PLAN_SHA256, "batch_exact_source_session_plan_required")
    rows = value["requests"]
    _require(isinstance(rows, list) and len(rows) == 2, "batch_exact_two_requests_required")
    for identifier, row in zip(REQUEST_IDS, rows):
        _require(type(row) is dict and set(row) == {"request_id", "placement", "request_sha256", "manifest_sha256", "count_sha256"} and
                 row["request_id"] == identifier and row["placement"] == REQUEST_PLACEMENTS[identifier] and
                 all(isinstance(row[k], str) and bool(re.fullmatch(r"[0-9a-f]{64}", row[k]))
                     for k in ("request_sha256", "manifest_sha256", "count_sha256")), "batch_exact_request_identity_required")
        manifest = profile.postrestart_manifest(row["placement"], profile.POSTRESTART_BATCH_CAMPAIGN)
        _require(row["manifest_sha256"] == fixtures.digest(fixtures.canonical(manifest)), "batch_exact_manifest_required")
        if identifier == SCIENCE_ID:
            _require(row["request_sha256"] == SCIENCE_BODY_SHA256, "batch_exact_scientific_hash_required")
    _require(len({row["request_sha256"] for row in rows}) == 2, "batch_distinct_bodies_required")
    return copy.deepcopy(value)
