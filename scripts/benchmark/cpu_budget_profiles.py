"""Closed 480000/480000 CPU-budget experiment; inert source rendering only.

The unchanged 112-vCPU guest runs original-affinity subsets. This is neither a
96-vCPU VM experiment nor physical pinning/locality evidence. The old LONG2 and
candidate declarations are reused by value and remain immutable.
"""
from __future__ import annotations

import json
import shlex

from . import profiles, qwen_launcher

SCOPE = CPU_SCOPE = "concurrent-480k-cpu"
CAMPAIGN = CPU_CAMPAIGN = "benchrun-c480-cpu-cont3-20260920"
CAPACITY = 480000
POSTRESTART_SCOPE = "postrestart72-480k"
POSTRESTART_CAMPAIGN = "benchrun-p72c1-20260920"
LAYOUTS = {
    "A": {"active_guest_vcpus": 112, "G1": {"cpuset": "0-95", "count": 96},
          "Q1": {"cpuset": "96-111", "count": 16}},
    "B": {"active_guest_vcpus": 96, "G1": {"cpuset": "0-87", "count": 88},
          "Q1": {"cpuset": "96-103", "count": 8}},
}
CPU_COMPARISON = ("Unchanged 112-vCPU guest; A G96/Q16, B G88/Q8 original-affinity subsets; "
                  "unused16 emulate reduced budget, not a 96-vCPU VM or physical pinning/locality proof")


def resource_policy():
    """New explicit 15% ESTIMATE policy; historical/absent policy stays 25%."""
    gib = 1024**3
    return {"id": "concurrent-480k-cpu-working-set-estimate-15pct-v1",
            "host_headroom_policy": {"version": "sampled-required-working-set-15pct-v1",
                "numerator": 23, "denominator": 20,
                "basis": "sampled_required_working_set_estimate_bytes"},
            "working_set_basis": "sampled_peak_required_working_set_ESTIMATE",
            "working_set_formula": "estimate*1.15<=cap; raw cache/current/peak separate",
            "caps_bytes": {"G1": 640*gib, "Q1": 32*gib}, "swap_allowed_bytes": 0,
            "fresh_initial_host_available_bytes": 688*gib,
            "os_reserve_bytes": 16*gib, "gpu_reserve_bytes": 16*gib,
            "qwen_gpu_headroom_fraction": 0.10,
            "caps_are": "hard ceilings, not allocation or model minimum"}


def _set(argv, flag, value):
    if argv.count(flag) != 1:
        raise ValueError("cpu_budget_inherited_flag_missing_or_duplicated")
    argv[argv.index(flag) + 1] = str(value)


def manifest(layout, placement):
    """Exactly four reviewed launch manifests; no arbitrary tuning arguments."""
    if layout not in LAYOUTS or placement not in ("G1", "Q1"):
        raise ValueError("cpu_budget_closed_layout_placement_required")
    base = profiles.concurrent_manifest(placement, 65536 if placement == "G1" else 700160)
    identifier = f"{CAMPAIGN}-{layout.lower()}-{placement.lower()}-{CAPACITY}"
    # Replace whole identity first, then common campaign roots. Inherited cache
    # policy is unchanged; each layout gets its own campaign-owned cache path.
    encoded = json.dumps(base).replace(base["container_name"], identifier)
    encoded = encoded.replace(profiles.CONCURRENT_CAMPAIGN, CAMPAIGN)
    cache = f"/data/models-large/runtime-cache/{CAMPAIGN}/{placement.lower()}"
    encoded = encoded.replace(cache, f"/data/models-large/runtime-cache/{CAMPAIGN}/{layout.lower()}/{placement.lower()}")
    value = json.loads(encoded)
    cpu = LAYOUTS[layout][placement]
    value.update(scope=SCOPE, campaign=CAMPAIGN, layout=layout, configured_capacity=CAPACITY,
                 container_name=identifier, guest_cpuset=cpu["cpuset"], guest_cpu_count=cpu["count"],
                 guest_total_vcpus=112, active_guest_vcpus=LAYOUTS[layout]["active_guest_vcpus"],
                 cpu_comparison=CPU_COMPARISON, resource_policy=resource_policy())
    _set(value["create_argv"], "--cpuset-cpus", cpu["cpuset"])
    if placement == "G1":
        for key in ("native_argv", "create_argv"):
            for flag, number in (("--ctx-size", CAPACITY), ("--threads", cpu["count"]),
                                 ("--threads-batch", cpu["count"])):
                _set(value[key], flag, number)
    else:
        _set(value["create_argv"], "--context", CAPACITY)
        _set(value["create_argv"], "--scope", SCOPE)
        base_launcher = qwen_launcher.pinned_base(profiles.ROOT / "scripts/runtime/sglang38_file_auth.py")
        value["native_argv"] = qwen_launcher.variant(base_launcher, CAPACITY, 1, scope=SCOPE)
    value["create_shell"] = shlex.join(value["create_argv"])
    value["live_allocation"] = "NOT_TESTED"
    value["mandatory_run_gates"] += [
        "fresh 688GiB host available admission before initial pair; 640GiB/32GiB no-swap hard caps",
        "sampled required working-set ESTIMATE * 1.15 <= cap; raw cache/current/peak reported separately",
        "GLM480000 remains provisional until actual allocation and free-memory gates pass",
        "Qwen actual pool480000 and native input limit required; no configured-argv inference",
        "one pair per layout and one A common-input Q256K only; no filler or rerun",
    ]
    return value


def manifests():
    return [manifest(layout, placement) for layout in ("A", "B") for placement in ("G1", "Q1")]


def trial_order():
    trials = [
        {"id": "A-G65008", "layout": "A", "placement": "G1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": 65536, "saved_input_tokens": 65008, "frozen_records": 2028, "output_cap": 256},
        {"id": "A-Qnear480K", "layout": "A", "placement": "Q1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": CAPACITY, "output_cap": 256},
        {"id": "A-Q256K", "layout": "A", "placement": "Q1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": 262144, "output_cap": 256},
        {"id": "B-G65008", "layout": "B", "placement": "G1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": 65536, "saved_input_tokens": 65008, "frozen_records": 2028, "output_cap": 256},
        {"id": "B-Qnear480K", "layout": "B", "placement": "Q1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": CAPACITY, "output_cap": 256},
    ]
    return {"trials": trials, "mixed_jobs": [],
            "rounds": [{"id": layout, "layout": layout, "glm_capacity": CAPACITY, "qwen_capacity": CAPACITY,
                        "glm_saved_records": 2028, "glm_saved_input_tokens": 65008,
                        "qwen_target_capacity": CAPACITY, "qwen_max_requests": 1,
                        "pairs": 1} for layout in ("A", "B")],
            "common_input": {"id": "A-Q256K", "layout": "A", "after": "A-Qnear480K-drained",
                             "glm_state": "same_G65K_active_when_possible_else_actual_idle",
                             "wait_for_glm": False, "record_actual_peer_condition": True, "configured_capacity": CAPACITY,
                             "target_capacity": 262144, "requests": 1,
                             "fixture": "frozen_previous_261622ish_native_count_semantics_fresh_prefix"},
            "warmup": {"per_model_per_load": 1, "minimum_input_tokens": 2048,
                       "output_cap": 32, "timing": "discarded"},
            "output_cap": 256, "margin_tokens": 256,
            "glm_sampling": {"temperature": 1, "seed": 1729, "reasoning_effort": "low",
                             "response_format": "schema", "max_tokens": 256},
            "maximum_request_seconds": 7200, "measurement_budget_seconds": 7200,
            "request_deadline": "min(7200s, remaining RUN window)",
            "clock_includes_preparation": True, "budget_start": "original root-reviewed RUN dispatch retained; PREP excluded",
            "restoration_outside_budget": True,
            "additional_cases": "none; no ladders, fillers, tools, profiling, output512, reruns or tuning",
            "format_failure_policy": "retain_strict_and_optional_single_fence_semantic_retrieval_separately",
            "slow_glm_policy": "record_notify_no_speed_stop_no_tuning",
            "historical_q256k_700160": "historical comparison only; not proof all700K slowdown was allocation"}


def validate_arm_scope(armed):
    if (armed.get("scope") != SCOPE or armed.get("campaign") != CAMPAIGN
            or armed.get("manifests") != manifests() or armed.get("trial_plan") != trial_order()):
        raise ValueError("cpu_budget_exact_arm_scope_mismatch")
    return SCOPE


def postrestart_manifest(placement):
    """One reviewed pair in the actual 72-vCPU guest; Q8 shares G72."""
    if placement not in ("G1", "Q1"):
        raise ValueError("postrestart_closed_placement_required")
    previous = manifest("A", placement)
    identifier = f"{POSTRESTART_CAMPAIGN}-p-{placement.lower()}-{CAPACITY}"
    encoded = json.dumps(previous).replace(previous["container_name"], identifier)
    encoded = encoded.replace(CAMPAIGN, POSTRESTART_CAMPAIGN)
    encoded = encoded.replace(f"/{POSTRESTART_CAMPAIGN}/a/", f"/{POSTRESTART_CAMPAIGN}/p/")
    value = json.loads(encoded)
    cpus, count = ("0-71", 72) if placement == "G1" else ("0-7", 8)
    value.update(scope=POSTRESTART_SCOPE, campaign=POSTRESTART_CAMPAIGN, layout="P",
                 container_name=identifier, guest_cpuset=cpus, guest_cpu_count=count,
                 guest_total_vcpus=72, active_guest_vcpus=72, guest_mems_allowed="0-7",
                 cpu_comparison="Actual72 guest CPUs; Q8 shares G72; guest NUMA mapping is not physical pinning or bandwidth proof")
    _set(value["create_argv"], "--cpuset-cpus", cpus)
    if placement == "G1":
        for key in ("native_argv", "create_argv"):
            for flag in ("--threads", "--threads-batch"):
                _set(value[key], flag, 72)
    else:
        _set(value["create_argv"], "--scope", POSTRESTART_SCOPE)
        base = qwen_launcher.pinned_base(profiles.ROOT / "scripts/runtime/sglang38_file_auth.py")
        value["native_argv"] = qwen_launcher.variant(base, CAPACITY, 1, scope=POSTRESTART_SCOPE)
    value["create_shell"] = shlex.join(value["create_argv"])
    value["mandatory_run_gates"] = [
        "fresh registered storage/source/lease/GPU identity and resource guards unchanged",
        "actual online CPUs0-71 and eight guest NUMA nodes; all memory nodes allowed; Q0-7 shares G0-71",
        "fresh 688GiB host available admission; 640GiB/32GiB no-swap hard caps",
        "sampled required working-set ESTIMATE * 1.15 <= cap; raw cache/current/peak separate",
        "GLM480000 actual allocation and free-memory proof; Qwen actual pool480000/input479994 numeric proof",
        "one load pair; discarded warmups; measured G4K; root-reviewed conditional G65008/Q479487 pair only",
        "healthy completion/review pause retains exact owned WARM_HOLD; explicit release restores captured STOPPED/manual",
    ]
    return value


def postrestart_manifests():
    return [postrestart_manifest(placement) for placement in ("G1", "Q1")]


def postrestart_trial_order():
    return {"trials": [
        {"id": "P-G4K", "layout": "P", "placement": "G1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": 4096, "saved_input_tokens": 3546, "output_cap": 256,
         "fixture": "glmrepair-combined-20260919 exact logical fixture, fresh leading prefix/native count",
         "peer_condition": "Qwen_loaded_idle"},
        {"id": "P-G65008", "layout": "P", "placement": "G1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": 65536, "saved_input_tokens": 65008, "frozen_records": 2028,
         "output_cap": 256, "conditional": "preauthorized_P-G4K_gate_or_explicit_root_long_GO"},
        {"id": "P-Qnear480K", "layout": "P", "placement": "Q1", "configured_capacity": CAPACITY,
         "occupied_target_capacity": CAPACITY, "saved_input_tokens": 479487,
         "output_cap": 256, "conditional": "preauthorized_P-G4K_gate_or_explicit_root_long_GO"}],
        "rounds": [{"id": "P", "layout": "P", "glm_capacity": CAPACITY, "qwen_capacity": CAPACITY,
                    "pairs": 1, "qwen_max_requests": 1}],
        "mixed_jobs": [], "warmup": {"per_model_per_load": 1, "output_cap": 32,
            "glm_occupied_target": "approximately4K", "qwen_occupied_target": "approximately3251",
            "timing": "discarded", "performance_gate": False},
        "output_cap": 256, "margin_tokens": 256,
        "glm_sampling": {"temperature": 1, "seed": 1729, "reasoning_effort": "low",
                         "response_format": "schema", "max_tokens": 256},
        "preliminary_gate": {"action": "preauthorized_long_pair_if_strict_correct_uncached_prefill_at_least35_tps_total_at_most180s",
            "strict_correct_required": True, "cached_tokens_required": 0,
            "native_prefill_tps_minimum": 35, "client_total_seconds_maximum": 180,
            "outside_heuristic": "guarded_WARM_HOLD_no_NEW_requests_until_explicit_root_review",
            "decode_minimum_output_tokens": 64,
            "aggregate_decode_tps_flag_below": 2, "isolated_decode_stall": "record_notify_only",
            "long_admission": "save_and_send_P-G4K_snapshot_before_dispatch; preauthorized_gate_or_explicit_root_GO",
            "historical_baseline": "glmrepair-combined-20260919:3546input/145output/cache0",
            "confounds": "configured pool480000 versus historical4096; whole configuration comparison; no causal proof"},
        "maximum_request_seconds": 7200, "measurement_budget_seconds": 21600,
        "request_deadline": "immutable actual HTTP dispatch +7200s; never clipped by admission deadline",
        "clock_includes_preparation": False, "budget_start": "first_measurement_admission",
        "admission_deadline": "refuses NEW measured requests only; admitted requests drain to own deadline",
        "loading": "separately bounded and reported", "restoration_outside_budget": True,
        "format_failure_policy": "retain_strict_and_optional_single_fence_semantic_retrieval_separately",
        "additional_cases": "none initially; one separately root-GO-bound retained-owner preset after hold; no Q256K, CPU-only, output512, profiling or tuning",
        "slow_glm_policy": "record_notify; root_review_before_long_pair; resource_and_correctness_stops_preserved",
        "endstate": "healthy_completion_or_preliminary_review_pause_guarded_owned_WARM_HOLD",
        "warm_hold": {"owner": "retained_detached_Worker1_RUN_same_SSHHost_remote_PID_and_canonical_lease",
            "active_requests": 0, "resource_monitoring": True,
            "control": "private_source_campaign_bound_status_followup_GO_release_mailbox",
            "followup": "one additional G4K/G65008/Qnear480K preset, exact body/fixture/profile/source/fresh-session GO; own6h admission/full2h HTTP; no automatic retry",
            "release": "canonical_restore_captured_STOPPED_manual",
            "proven_unsafe_or_undrained_transport": "canonical_cleanup_or_recovery",
            "completed_quality_failure_or_proof_gap": "REVIEW_REQUIRED_hold_no_new_initial_admissions",
            "worker_or_SSH_death": "RECOVERY_REQUIRED_no_auto_resurrection_or_adoption"}}


def validate_postrestart_arm_scope(armed):
    if (armed.get("scope") != POSTRESTART_SCOPE or armed.get("campaign") != POSTRESTART_CAMPAIGN
            or armed.get("manifests") != postrestart_manifests()
            or armed.get("trial_plan") != postrestart_trial_order()):
        raise ValueError("postrestart_exact_arm_scope_mismatch")
    return POSTRESTART_SCOPE
