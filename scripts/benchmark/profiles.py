"""Pure command manifests. These functions never start Docker or acquire a lease."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex

from .qwen_launcher import pinned_base, variant

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/benchmarks/gpu-split-20260919.json"
G1_RAM_CAP_BYTES = 640 * 1024**3  # Root-reviewed validation cap; not minimum model RAM.
ARM_SCOPES = ("full", "q1-only", "q1-256k", "g1-only", "glmrepair", "g1-ladder", "glm-decode-diag")
G1_LADDER_CAMPAIGN = "benchrun-glm-g1-ladder-20260920"
GLM_DECODE_DIAG_CAMPAIGN = "benchrun-glm-decode-diag-20260920"
GLM_DECODE_DIAG_CAPACITIES = (1024, 32768, 65536)
GLMREPAIR_CAMPAIGN = "benchrun-glmrepair2-20260919"
GLMREPAIR_POLL_CAMPAIGN = "benchrun-glmrepair-poll-20260919"
GLMREPAIR_G1FIX_CAMPAIGN = "benchrun-glmrepair-g1fix-20260919"
GLMREPAIR_FIX_CAMPAIGN = "benchrun-glmrepair-fix-20260919"
GLMREPAIR_G1_CAMPAIGN = "benchrun-glmrepair-g1-20260919"


def glmrepair_manifest(campaign=GLMREPAIR_CAMPAIGN):
    """Frozen reviewed G2 control or exact saved G1 profile; no tuning."""
    if campaign in (GLMREPAIR_FIX_CAMPAIGN, GLMREPAIR_G1FIX_CAMPAIGN):
        return json.loads(json.dumps(glmrepair_manifest(GLMREPAIR_G1_CAMPAIGN)).replace(GLMREPAIR_G1_CAMPAIGN, campaign))
    if campaign == GLMREPAIR_POLL_CAMPAIGN:
        manifest = json.loads(json.dumps(glmrepair_manifest(GLMREPAIR_G1_CAMPAIGN)).replace(GLMREPAIR_G1_CAMPAIGN, campaign))
        for key in ("native_argv", "create_argv"):
            manifest[key] += ["--poll", "0", "--poll-batch", "50"]
        manifest["create_shell"] = shlex.join(manifest["create_argv"])
        return manifest
    names = {GLMREPAIR_CAMPAIGN: "glmrepair-g2-20260919.json",
             GLMREPAIR_G1_CAMPAIGN: "glmrepair-g1-20260919.json"}
    if campaign not in names:
        raise ValueError("glmrepair_exact_arm_scope_mismatch")
    return json.loads((ROOT / "configs/benchmarks" / names[campaign]).read_text())


def g1_ladder_manifest(capacity):
    """Two scoped loads of the frozen G1 profile; only native context changes."""
    if type(capacity) is not int or capacity not in (16384, 65536):
        raise ValueError("g1_ladder_capacity_outside_scope")
    base = glmrepair_manifest(GLMREPAIR_G1_CAMPAIGN)
    name = f"{G1_LADDER_CAMPAIGN}-g1-{capacity}"
    manifest = json.loads(json.dumps(base).replace(base["container_name"], name)
                          .replace(GLMREPAIR_G1_CAMPAIGN, G1_LADDER_CAMPAIGN))
    manifest["configured_capacity"] = capacity
    for key in ("native_argv", "create_argv"):
        manifest[key][manifest[key].index("--ctx-size") + 1] = str(capacity)
    manifest["create_shell"] = shlex.join(manifest["create_argv"])
    return manifest


def glm_decode_diag_manifest(capacity):
    """Frozen G1 diagnostic loads: context and campaign paths/names only change."""
    if type(capacity) is not int or capacity not in GLM_DECODE_DIAG_CAPACITIES:
        raise ValueError("glm_decode_diag_capacity_outside_scope")
    base = glmrepair_manifest(GLMREPAIR_G1_CAMPAIGN)
    name = f"{GLM_DECODE_DIAG_CAMPAIGN}-g1-{capacity}"
    manifest = json.loads(json.dumps(base).replace(base["container_name"], name)
                          .replace(GLMREPAIR_G1_CAMPAIGN, GLM_DECODE_DIAG_CAMPAIGN))
    manifest["configured_capacity"] = capacity
    for key in ("native_argv", "create_argv"):
        manifest[key][manifest[key].index("--ctx-size") + 1] = str(capacity)
    manifest["create_shell"] = shlex.join(manifest["create_argv"])
    return manifest


def scope_placements(scope):
    if scope not in ARM_SCOPES:
        raise ValueError("unknown_benchmark_arm_scope")
    if scope in {"g1-only", "g1-ladder", "glm-decode-diag"}:
        return ("G1",)
    if scope == "glmrepair":
        return ("G2",)
    return ("Q1",) if scope != "full" else ("Q2", "Q1", "G2", "G1")


def scope_capacities(scope):
    scope_placements(scope)  # Reject unknown scopes before selecting capacities.
    if scope == "glmrepair":
        return (4096,)
    if scope == "g1-ladder":
        return (16384, 65536)
    if scope == "glm-decode-diag":
        return GLM_DECODE_DIAG_CAPACITIES
    return (262144,) if scope == "q1-256k" else (4096, 16384, 65536)


def validate_arm_scope(armed):
    """Legacy arms retain full scope; narrowed arms bind their exact placement and plan."""
    scope = armed.get("scope", "full")
    placements = scope_placements(scope)
    if scope == "glm-decode-diag":
        if (armed.get("campaign") != GLM_DECODE_DIAG_CAMPAIGN
                or armed.get("manifests") != [glm_decode_diag_manifest(n) for n in GLM_DECODE_DIAG_CAPACITIES]
                or armed.get("trial_plan") != trial_order(scope)):
            raise ValueError("glm_decode_diag_exact_arm_scope_mismatch")
        return scope
    if scope == "g1-ladder":
        if (armed.get("campaign") != G1_LADDER_CAMPAIGN
                or armed.get("manifests") != [g1_ladder_manifest(n) for n in (16384, 65536)]
                or armed.get("trial_plan") != trial_order(scope)):
            raise ValueError("g1_ladder_exact_arm_scope_mismatch")
        return scope
    if scope == "glmrepair":
        if (armed.get("campaign") not in (GLMREPAIR_CAMPAIGN, GLMREPAIR_G1_CAMPAIGN, GLMREPAIR_POLL_CAMPAIGN, GLMREPAIR_FIX_CAMPAIGN, GLMREPAIR_G1FIX_CAMPAIGN)
                or armed.get("manifests") != [glmrepair_manifest(armed["campaign"])]
                or armed.get("trial_plan") != trial_order(scope, campaign=armed["campaign"])):
            raise ValueError("glmrepair_exact_arm_scope_mismatch")
        return scope
    if scope != "full":
        expected = [command_manifest(p, n, campaign=armed["campaign"], ram_cap=G1_RAM_CAP_BYTES if scope == "g1-only" else None, log_verbosity=4 if scope == "g1-only" else None)
                    for p in placements for n in scope_capacities(scope)]
        if armed.get("manifests") != expected or armed.get("trial_plan") != trial_order(scope):
            raise ValueError("q1_only_arm_scope_mismatch")
    return scope


def read_config():
    c = json.loads(CONFIG.read_text())
    for name, sha in c["source_pins"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            raise ValueError("benchmark_source_pin_changed")
    return c


def cpu_set(value):
    result = set()
    for part in value.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", part):
            raise ValueError("invalid_cpu_set")
        ends = [int(x) for x in part.split("-")]
        a, b = ends[0], ends[-1]
        if a > b or b > 111:
            raise ValueError("invalid_cpu_set")
        result.update(range(a, b + 1))
    return result


def split_resources(measured_glm, measured_qwen, host_usable_bytes):
    """B caps use measured required components, not cgroup current/file cache.

    Host usable bytes must be freshly sampled AFTER prior benchmark containers
    retire; the caller proves that lifecycle condition. No loaded-model current
    is added blindly to MemAvailable because reclaimable pages may overlap it.
    """
    if type(host_usable_bytes) is not int or host_usable_bytes <= 0:
        raise ValueError("usable_host_after_retirement_required")
    caps = {}
    for placement, evidence in (("G1", measured_glm), ("Q1", measured_qwen)):
        if (not isinstance(evidence, dict) or evidence.get("schema") != 1
                or evidence.get("evidence_status") != "MEASURED_COMPONENTS"
                or type(evidence.get("required_bytes")) is not int or evidence["required_bytes"] <= 0):
            raise ValueError("measured_required_ram_components_required")
        components = [evidence.get(k) for k in ("anon_bytes", "kernel_bytes", "required_file_backed_bytes", "workspace_extra_bytes")]
        if any(type(value) is not int or value < 0 for value in components) or sum(components) != evidence["required_bytes"]:
            raise ValueError("measured_required_ram_components_inconsistent")
        caps[placement] = (evidence["required_bytes"] * 5 + 3) // 4
    if sum(caps.values()) > host_usable_bytes - 16 * 1024**3:
        raise ValueError("split_ram_reserve_unsafe")
    c = read_config()["guest_cpus"]
    g, q = cpu_set(c["glm_mixed"]), cpu_set(c["qwen_mixed"])
    if len(g) != 96 or len(q) != 16 or g & q:
        raise ValueError("split_cpu_contract_invalid")
    return caps


def command_manifest(placement, capacity, *, campaign="benchrun-20260919", mixed=False, ram_cap=None, log_verbosity=None):
    c = read_config()
    q256 = placement == "Q1" and capacity == 262144 and not mixed and ram_cap is None
    if placement not in c["placements"] or type(capacity) is not int or (capacity not in c["capacities"] and not q256):
        raise ValueError("unreviewed_placement_or_capacity")
    if log_verbosity is not None and (type(log_verbosity) is not int or log_verbosity != 4 or placement != "G1" or mixed):
        raise ValueError("unreviewed_observational_logging")
    if not re.fullmatch(r"benchrun-[a-z0-9-]{1,48}", campaign):
        raise ValueError("invalid_campaign_identity")
    if mixed and placement not in ("G1", "Q1"):
        raise ValueError("mixed_requires_single_gpu")
    if mixed and (type(ram_cap) is not int or ram_cap <= 0):
        raise ValueError("mixed_requires_measured_ram_cap")
    p = c["placements"][placement]
    glm = p["model"] == "glm"
    identifier = f"{campaign}-{placement.lower()}-{capacity}"
    uuids = [c["gpu_uuids"][i] for i in p["gpus"]]
    if len(set(uuids)) != len(uuids) or any(not re.fullmatch(r"GPU-[0-9a-f-]{36}", u) for u in uuids):
        raise ValueError("gpu_identity_invalid")
    # Isolated one-GPU controls use exactly B's 96/16 partition. Two-GPU
    # baselines retain all 112 guest CPUs; this is a disclosed CPU difference.
    cpus = c["guest_cpus"]["glm_mixed" if glm else "qwen_mixed"] if placement.endswith("1") else c["guest_cpus"]["all"]
    cpu_count = len(cpu_set(cpus))
    if cpu_count != {"G2": 112, "Q2": 112, "G1": 96, "Q1": 16}[placement]:
        raise ValueError("placement_cpu_contract_invalid")
    model_name = "glm-5.3-ud-q4-k-xl" if glm else "qwen38-27b-fp8"
    runtime_name = "llama-cpp-v0.4.1-d3br" if glm else "sglang-qwen38-0.5.19"
    model = json.loads((ROOT / f"configs/models/{model_name}.json").read_text())
    runtime = json.loads((ROOT / f"configs/runtimes/{runtime_name}.json").read_text())
    image = runtime["validation"]["image_id"] if glm else runtime["image_ref"]
    # All writable AI paths are explicit registered /data descendants. RUN must
    # validate roots with the installed guards and create them via anchored I/O.
    roots = {"cache": f"/data/models-large/runtime-cache/{campaign}/{placement.lower()}",
             "logs": f"/data/logs/{campaign}/{identifier}",
             "service": f"/data/services/{campaign}/{identifier}",
             "source": f"/data/services/{campaign}/source"}
    mounts = [(f"/data/models-large/{model_name}", "/models", True),
              (roots["cache"], "/cache", False), (roots["logs"], "/logs", False),
              (roots["service"], "/service", False),
              ("/data/services/secrets/llm-api-key", "/run/secrets/llm-api-key", True)]
    args = ["docker", "create", "--name", identifier, "--network", "bridge", "--restart", "no",
            "--publish", f"127.0.0.1:{p['port']}:{p['port']}/tcp",
            "--gpus", '"device=' + ",".join(uuids) + '"', "--cpuset-cpus", cpus,
            "--label", f"benchmark.campaign={campaign}", "--label", f"benchmark.placement={placement}",
            "--label", "benchmark.owner=llm-benchmark",
            "--log-driver", "json-file", "--log-opt", "max-size=20m", "--log-opt", "max-file=3",
            "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL", "--pull=never"]
    if ram_cap is not None:
        if type(ram_cap) is not int or ram_cap <= 0:
            raise ValueError("invalid_ram_cap")
        args += ["--memory", str(ram_cap), "--memory-swap", str(ram_cap)]
    if glm:
        env = {**runtime["environment"], "CUDA_VISIBLE_DEVICES": ",".join(uuids)}
        command = ["--model", "/models/" + model["load_entry"], "--host", "0.0.0.0",
                   "--port", str(p["port"]), "--alias", "bench-glm-5.3",
                   "--api-key-file", "/run/secrets/llm-api-key", "--ctx-size", str(capacity),
                   "--parallel", "1", "--n-cpu-moe", "76", "--n-gpu-layers", "999",
                   "--split-mode", p["split_mode"], "--tensor-split", p["tensor_split"],
                   "--main-gpu", "0", "--device", ",".join(p["devices"]),
                   "--load-mode", "none", "--cache-type-k", "f16", "--cache-type-v", "f16",
                   "--fit", "off", "--batch-size", "2048", "--ubatch-size", "512",
                   "--threads", str(cpu_count), "--threads-batch", str(cpu_count), "--jinja", "--no-webui",
                   "--no-cache-prompt", "--chat-template-kwargs", '{"clear_thinking":true}']
        if log_verbosity is not None:
            # Pinned library INFO maps to verbosity4; default3 hides weights/offload.
            command += ["--log-verbosity", str(log_verbosity)]
        args += ["--entrypoint", runtime["entrypoint"][0]]
    else:
        base = pinned_base(ROOT / "scripts/runtime/sglang38_file_auth.py")
        env = {**runtime["environment"], **base.EXTENSION_ENVIRONMENT}
        command = ["/opt/llmctl/benchmark_qwen_launcher.py", "--context", str(capacity), "--tp", str(p["tp_size"])]
        mounts += [("/data/services/llm-manager/adapters/sglang38_file_auth.py", "/opt/llmctl/sglang38_file_auth.py", True),
                   (roots["source"] + "/scripts/benchmark/qwen_launcher.py", "/opt/llmctl/benchmark_qwen_launcher.py", True)]
        args += ["--entrypoint", "python3", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g",
                 "--shm-size", "8g", "--workdir", "/service", "--no-healthcheck", "--user", "0", "--ulimit", "core=1:1"]
    for src, target, ro in mounts:
        args += ["--mount", f"type=bind,source={src},target={target}" + (",readonly" if ro else "")]
    for key, value in env.items():
        args += ["--env", key + "=" + value]
    args += [image, *command]
    return {"status": "DRY_RUN_NOT_EXECUTED", "placement": placement, "configured_capacity": capacity,
            "campaign": campaign, "container_name": identifier, "image": image,
            "expected_image_ids": [image] if glm else [runtime["image_manifest_digest"], runtime["image_id"]],
            "image_identity_gate": "exact GLM image digest" if glm else "runtime.qwen38_oci.verify_image and validate_container_image; preserve manifest/config domains",
            "model": {"repo_id": model["repo_id"], "revision": model["revision"], "quantization": model["quantization"]},
            "gpu_uuids": uuids, "guest_cpuset": cpus, "guest_cpu_count": cpu_count, "ram_cap_bytes": ram_cap,
            "cpu_comparison": "two-GPU baseline 112; isolated and mixed one-GPU GLM 96 / Qwen 16",
            "glm_offload_expectation": c.get("glm_offload_expectation") if glm else None,
            "mixed": mixed, "registered_paths": roots, "create_argv": args,
            "create_shell": shlex.join(args), "start_argv": ["docker", "start", identifier],
            "native_argv": command if glm else variant(base, capacity, p["tp_size"]),
            "native_auth": "existing protected key file; key bytes never in command/environment",
            "transport": {"bind": "127.0.0.1", "port": p["port"], "worker": "reviewed SSH loopback tunnel; no new LAN listener/firewall policy"},
            "mandatory_run_gates": ["canonical lease held; production control frozen and production stopped",
                                    "fresh registered guard/source identity and root guard pass before/after writes",
                                    "root-reviewed exact manifest, image/weights/cache mounts, GPU UUID visibility and idle state",
                                    "runtime logs prove identity, N76/TP, F16/BF16, configured actual allocations and >=16GiB GPU reserve",
                                    "warmup and fixture validation before timed request"],
            "live_allocation": "NOT_TESTED", "gpu_index_is_not_placement_proof": True}


def trial_order(scope="full", campaign=GLMREPAIR_CAMPAIGN):
    if scope == "glm-decode-diag":
        trials = []
        for capacity in GLM_DECODE_DIAG_CAPACITIES:
            trials += [
                {"placement": "G1", "capacity": capacity, "case": "load_warmup", "output_cap": 32, "timing": "discard"},
                {"placement": "G1", "capacity": capacity, "case": "short_control", "output_cap": 128}]
        trials += [
            {"placement": "G1", "capacity": 65536, "case": "near_full_replay", "output_cap": 256},
            {"placement": "G1", "capacity": 65536, "case": "long_answer", "output_cap": 4096,
             "conditional": "after_short_controls_profiles_and_any_separately_reviewed_causal_AB"}]
        return {"trials": trials, "then": [], "mixed_jobs": [], "measurement_budget_seconds": 14400,
                "maximum_request_seconds": 7200, "clock_includes_preparation": True,
                "budget_start": "existing absolute stage clock; never reset for continuation or repair",
                "restoration_outside_budget": True,
                "short_matching": "same logical fixture and sampling; fresh leading prefix and exact native recount",
                "output_policy": "natural stopping with fixed caps; no ignore_eos; report actual counts and finish reason",
                "format_failure_policy": "preserve strict retrieval failures; no automatic retry",
                "additional_trials": "CPU/CUDA samples and one evidence-led causal AB require separate root review"}
    if scope == "g1-ladder":
        return {"trials": [
            {"placement": "G1", "capacity": 16384, "case": "load_warmup", "output_cap": 32, "timing": "discard"},
            {"placement": "G1", "capacity": 16384, "case": "primary", "output_cap": 256},
            {"placement": "G1", "capacity": 16384, "case": "repeat_anchor", "output_cap": 256,
             "conditional": "primary_strict_PASS_uncached_memory_safe"},
            {"placement": "G1", "capacity": 65536, "case": "load_warmup", "output_cap": 32, "timing": "discard",
             "conditional": "both_16k_strict_PASS_uncached_memory_safe"},
            {"placement": "G1", "capacity": 65536, "case": "primary", "output_cap": 256}],
            "then": [], "mixed_jobs": [], "measurement_budget_seconds": 10800,
            "maximum_request_seconds": 7200, "clock_includes_preparation": True,
            "restoration_outside_budget": True, "format_failure_policy": "stop on first strict failure; no retries",
            "repeat_matching": "same fixture, records and expected values; fresh prefix and exact native recount"}
    if scope == "glmrepair" and campaign == GLMREPAIR_G1FIX_CAMPAIGN:
        return {"trials": [
            {"placement": "G1", "capacity": 4096, "case": "load_warmup", "output_cap": 32, "timing": "discard"},
            {"placement": "G1", "capacity": 4096, "case": "native-schema", "output_cap": 256}],
            "then": [], "mixed_jobs": [], "measurement_budget_seconds": 1200,
            "maximum_request_seconds": 7200, "restoration_outside_budget": True,
            "format_failure_policy": "one exact accepted D schema request; no retry or second seed"}
    if scope == "glmrepair" and campaign == GLMREPAIR_FIX_CAMPAIGN:
        return {"trials": [
            {"placement": "G1", "capacity": 4096, "case": "load_warmup", "output_cap": 32, "timing": "discard"},
            {"placement": "G1", "capacity": 4096, "case": "sampling1729", "output_cap": 256},
            {"placement": "G1", "capacity": 4096, "case": "sampling2718", "output_cap": 256, "conditional": "first_strict_PASS"}],
            "then": [], "mixed_jobs": [], "measurement_budget_seconds": 2700,
            "maximum_request_seconds": 7200, "restoration_outside_budget": True,
            "format_failure_policy": "UNFIXED on first strict failure; no grid or schema substitution"}
    if scope == "glmrepair" and campaign == GLMREPAIR_POLL_CAMPAIGN:
        return {"trials": [
            {"placement": "G1", "capacity": 4096, "case": "poll_control", "output_cap": 32, "timing": "measured"},
            {"placement": "G1", "capacity": 4096, "case": "exact_stream", "output_cap": 256,
             "conditional": "healthy_cached0_native_n_minus_one_tps_ge5_remaining_ge180"}],
            "then": [], "mixed_jobs": [], "measurement_budget_seconds": 3600,
            "maximum_request_seconds": 7200, "restoration_outside_budget": True,
            "format_failure_policy": "preserve raw and strict failure separately; no nonstream replay"}
    if scope == "glmrepair" and campaign == GLMREPAIR_G1_CAMPAIGN:
        return {"trials": [
            {"placement": "G1", "capacity": 4096, "case": "load_warmup", "output_cap": 32, "timing": "discard"},
            {"placement": "G1", "capacity": 4096, "case": "exact_stream", "output_cap": 256, "diagnostic": True},
            {"placement": "G1", "capacity": 4096, "case": "raw_nonstream", "output_cap": 256,
             "diagnostic": True, "conditional": "duplicate_json_or_literal_think"}],
            "then": [], "mixed_jobs": [], "measurement_budget_seconds": 3600,
            "maximum_request_seconds": 7200, "restoration_outside_budget": True,
            "format_failure_policy": "record strict failure; optional exact-body nonstream provenance only"}
    if scope == "glmrepair":
        return {"trials": [
            {"placement": "G2", "capacity": 4096, "case": "load_warmup", "output_cap": 32, "timing": "discard"},
            {"placement": "G2", "capacity": 4096, "case": "plain_stream", "output_cap": 128, "diagnostic": True},
            {"placement": "G2", "capacity": 4096, "case": "plain_nonstream", "output_cap": 128, "diagnostic": True},
            {"placement": "G2", "capacity": 4096, "case": "retrieval", "output_cap": 256}],
            "then": [], "mixed_jobs": [], "measurement_budget_seconds": 3600,
            "maximum_request_seconds": 7200, "restoration_outside_budget": True,
            "format_failure_policy": "record strict failure and continue reviewed baseline while resource health is valid"}
    rows = []
    for p in scope_placements(scope):
        for capacity in scope_capacities(scope):
            rows += [{"placement": p, "capacity": capacity, "case": "load_warmup", "timing": "discard"},
                     {"placement": p, "capacity": capacity, "case": "retrieval", "output_cap": 256}]
            if capacity == 16384:
                rows += [{"placement": p, "capacity": capacity, "case": case, "output_cap": cap}
                         for case, cap in [("retrieval_anchor_repeat", 256), ("generation", 512), ("tool_call_and_continuation", 256)]
                         if scope == "full" or case != "tool_call_and_continuation"]
    jobs = [{"id": "glm64k", "model": "glm", "capacity": 65536, "arrival_s": 0,
             "seed": "mixed-glm-v1", "output_cap": 256}] + [
        {"id": f"qwen16k-{i}", "model": "qwen", "capacity": 16384, "arrival_s": 0,
         "seed": f"mixed-qwen-v1-{i}", "output_cap": 256} for i in range(4)]
    return {"trials": rows, "then": ["mixed_A", "mixed_B_if_reserve_and_measured_caps_safe"] if scope == "full" else [],
            "mixed_jobs": jobs if scope == "full" else [], "mixed_matching": "freeze native-fitted fixture_sha256/record count per job across A and B; fresh nonce only",
            "measurement_budget_seconds": 21600, "maximum_request_seconds": 7200,
            "budget_start": "before first maintenance/model trial; persist once", "restoration_outside_budget": True,
            "budget_estimate": "Unknown before load/rate measurements; skip remaining trials explicitly at budget boundary; no blind retries",
            "optional_131072": "disabled_pending_root_decision"}
