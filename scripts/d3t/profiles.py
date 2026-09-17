#!/usr/bin/env python3
"""Immutable, source-only GLM D3T profile proposals; never deploy or bind an image.

The emitted envelope is deliberately not a lifecycle deployment. Its nested
proposals preserve schema-v1 fields but have runtime=null so the existing Manager
refuses them. A later reviewed deployment must supply the measured D3P runtime;
this tool has no bind, apply, process, network, model, or instance-write operation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "glm-5.3-ud-q4-k-xl"
BASELINE_ID = MODEL + "-32k"
D1_RUNTIME = "llama-cpp-v0.4.1-d1"
D1_IMAGE = "sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62"
NATIVE_CONTEXT = 1048576
SOURCE_PINS = {
    f"configs/deployments/{BASELINE_ID}.json": "4f6fe98cb5ed84ece066ac6e544d4764d04c8019f8640353ec6da1ff86c50ef5",
    f"configs/runtimes/{D1_RUNTIME}.json": "cf313fe24894cc640c91b77fa8432cf31224e69fad17050ea58d1ae73139e4bd",
    f"configs/models/{MODEL}.json": "857924551fa83c546bb99f7b524b35c8d79d0cb9ba0a666e0c139bbace0e7e0d",
}
# This is a review plan, not a patch applied by this program. Exact snippets keep
# the llama-only change separate from Q38B-owned imports and backend dispatch.
MANAGER_DIFF_PLAN = [
    {
        "file": "scripts/lifecycle/manager.py",
        "function": "Manager.validate_deployment",
        "location": "llama_cpp branch, after the sglang validate-and-return",
        "before": 'for key, low, high in (("context_size", 512, 131072), ("parallel", 1, 1),',
        "after": 'for key, low, high in (("parallel", 1, 1),',
        "insert_after_launch_assignment": '''context = launch.get("context_size")
require(type(context) is int and (512 <= context <= 131072
        or (d["model"] == "glm-5.3-ud-q4-k-xl" and context == 1048576)),
        "invalid_launch_limit")
cpu_all = launch.get("cpu_moe") is True and "n_cpu_moe" not in launch
cpu_76 = ("cpu_moe" not in launch and type(launch.get("n_cpu_moe")) is int
          and launch["n_cpu_moe"] == 76 and d["model"] == "glm-5.3-ud-q4-k-xl"
          and context in {32768, 1048576})''',
        "insert_before_launch_limit_loop": 'if cpu_76 or context == 1048576:\n    require(launch.get("tensor_split") == "1,1" and launch.get("n_gpu_layers") == 999,\n            "invalid_glm_d3t_baseline")\n    require(d["runtime"] != "llama-cpp-v0.4.1-d1", "d3t_patched_runtime_required")',
        "safety_before": 'require(launch.get("cpu_moe") is True and launch.get("jinja") is True',
        "safety_after": 'require((cpu_all or cpu_76) and launch.get("jinja") is True',
    },
    {
        "file": "scripts/lifecycle/manager.py",
        "function": "Manager.launch_command",
        "location": "llama_cpp branch, after the sglang validate-and-return",
        "insert_after_launch_assignment": 'if "n_cpu_moe" in launch or launch["context_size"] == 1048576:\n    measured = d["_runtime"].get("validation", {}).get("image_id")\n    require(bool(DIGEST_RE.fullmatch(str(measured))) and e.get("image_id") == measured\n            and measured != "sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62",\n            "d3t_patched_image_required")\nmoe = (["--cpu-moe"] if launch.get("cpu_moe") is True\n       else ["--n-cpu-moe", str(launch["n_cpu_moe"])])',
        "before": '"--cpu-moe", "--jinja", "--no-webui",',
        "after": '*moe, "--jinja", "--no-webui",',
    },
]


class ProfileError(ValueError):
    """A reviewed source identity has drifted or an output would be unsafe."""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _read_pinned(root: Path, relative: str) -> dict:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ProfileError("pinned source is absent, nonregular, or a symlink: " + relative)
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCE_PINS[relative]:
        raise ProfileError("reviewed source hash changed: " + relative)
    return json.loads(payload)


def _proposal(baseline: dict, *, cpu_all: bool, context: int) -> dict:
    placement = "cpu" if cpu_all else "n76"
    suffix = "native1m" if context == NATIVE_CONTEXT else "32k"
    identifier = MODEL + "-" + placement + "-" + suffix
    profile = copy.deepcopy(baseline)
    profile.update({
        "id": identifier,
        "runtime": None,
        "container_name": "llmctl-glm-5.3-" + placement + "-" + suffix,
        "purpose": "NOT_TESTED D3T source proposal; D3P runtime binding and live review required",
        "capability_status": "NOT_TESTED",
        "notes": [
            "This unbound proposal is not deployable; no image identity is asserted.",
            "Only a separate reviewed deployment may bind the measured D3P strict-alias runtime.",
            "D1 runtime/image remain the old all-CPU 32K rollback only.",
            "One model/backend/slot; worker-local tools; no server-side tools.",
            "Configured capacity is distinct from actual occupied and correct context.",
            "No reload/fallback during client ownership; no truncation, context shift, or RoPE scaling.",
        ],
    })
    profile["launch"]["context_size"] = context
    if not cpu_all:
        del profile["launch"]["cpu_moe"]
        profile["launch"]["n_cpu_moe"] = 76
    # New nonsecret scratch destinations avoid writing through baseline aliases.
    for role, prefix in (("cache", "runtime-cache"), ("logs", "logs/llmctl"),
                         ("service", "services/llm-manager")):
        profile["paths"][role] = {
            "role": "models" if role == "cache" else "data",
            "suffix": prefix + "/" + identifier,
        }
    by_target = {"/cache": "cache", "/logs": "logs", "/service": "service"}
    for mount in profile["mounts"]:
        if mount["target"] in by_target:
            mount["source"] = copy.deepcopy(profile["paths"][by_target[mount["target"]]])
    return profile


def generate_plan(root: Path = ROOT) -> dict:
    """Return deterministic unbound proposals from exact reviewed source bytes."""
    sources = {name: _read_pinned(root, name) for name in SOURCE_PINS}
    baseline = sources[f"configs/deployments/{BASELINE_ID}.json"]
    runtime = sources[f"configs/runtimes/{D1_RUNTIME}.json"]
    if runtime["validation"]["image_id"] != D1_IMAGE:
        raise ProfileError("baseline image mismatch")
    proposals = [
        _proposal(baseline, cpu_all=False, context=32768),
        _proposal(baseline, cpu_all=False, context=NATIVE_CONTEXT),
        _proposal(baseline, cpu_all=True, context=NATIVE_CONTEXT),
    ]
    return {
        "schema": "d3t.profile-plan.v1",
        "status": "NOT_TESTED",
        "deployable": False,
        "source_sha256": dict(SOURCE_PINS),
        "rollback": {
            "deployment": BASELINE_ID,
            "deployment_sha256": SOURCE_PINS[f"configs/deployments/{BASELINE_ID}.json"],
            "runtime": D1_RUNTIME,
            "image_id": D1_IMAGE,
            "role": "old all-CPU 32768 baseline only; source preserved byte-for-byte",
        },
        "runtime_dependency": {
            "owner": "D3P",
            "runtime_id": None,
            "measured_image_id": None,
            "status": "PENDING_REVIEWED_MEASURED_PATCHED_IMAGE",
            "requires": [
                "Root-reviewed patched source/patch/build-recipe hashes and strict-alias tests",
                "Measured built image ID different from D1 and exact installed CLI/source provenance",
                "New runtime required/supported flags include --n-cpu-moe; native --ctx-size supported",
                "Native capacity, actual fused_lid/indexer and Flash Attention path, allocated workspace evidence",
                "Matched all-CPU32K versus N76-32K body hashes and comparable prompt-cache conditions",
                "Separate deployment and instance runtime evidence through existing reviewed lifecycle",
            ],
            "missing_observable": "Require smallest installed log/source diagnostic seam; never infer actual fusion from source support",
        },
        "preserved_effective_settings_to_verify": {
            "cache_type_k": "f16", "cache_type_v": "f16",
            "batch_size": 2048, "ubatch_size": 512, "flash_attention": "auto",
            "inference_threads": 112, "load_mode": "none", "context_shift": False,
            "cache_reuse": 0, "speculative_mtp": False,
            "embedded_template_sha256": "15d2a7176beb599de0a59af8314b4869011e416cff7f65748b314940d3379b0e",
            "loaded_template_sha256": "347dc716e1e8a9917eb124503836943107686ace6a3848d16bf23ae50964bb49",
            "note": "These are required effective baseline settings, not new lifecycle launch fields or measured D3P claims.",
        },
        "request_contract": {"reasoning_effort": "low", "reserve_tokens": 8192},
        "progression": {
            "configured_contexts": [32768, NATIVE_CONTEXT],
            "native_capacity_loads_after_32k": 1,
            "occupied_windows": [65536, 131072, 262144, 524288, NATIVE_CONTEXT],
            "initial_templated_input_ceilings": [57344, 122880, 253952, 516096, 1040384],
            "stage_elapsed_caps_seconds": [7200, 14400, 28800, 43200, 86400],
            "automatic_fallback_or_reload": False,
            "fallback": "All CPU experts only, explicitly reviewed before client ownership; no tuning grid",
        },
        "manager_integration": {
            "status": "SOURCE_IMPLEMENTED_REVISION2_Q38B_NONOVERLAP_ACK_LIVE_NOT_TESTED",
            "changes_applied": True,
            "diff_plan": MANAGER_DIFF_PLAN,
            "protected": ["Q38B imports/backend dispatch", "control/U1", "installer", "deployment instances"],
            "additional_admission_dependency": "Bind only the reviewed measured D3P runtime identity in a separate deployment; image equality is enforced but does not itself prove strict-alias/patch correctness.",
        },
        "proposals": proposals,
    }


def write_plan(path: Path, value: dict) -> None:
    """Write a new plan file only; refuse configs, overwrite, and symlink parents."""
    absolute = path.absolute()
    if "configs" in absolute.parts or absolute.suffix != ".json":
        raise ProfileError("output must be a .json source plan outside any configs directory")
    if any(parent.is_symlink() for parent in [absolute.parent, *absolute.parents]):
        raise ProfileError("symlink output parent refused")
    if not absolute.parent.is_dir():
        raise ProfileError("output parent must already exist")
    # Exclusive creation protects existing evidence. Mode 0600 also makes the
    # generated source safe to keep alongside private worker probe artifacts.
    import os
    fd = os.open(absolute, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(canonical_bytes(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new .json source-plan file outside configs; default stdout")
    args = parser.parse_args(argv)
    try:
        plan = generate_plan()
        if args.output:
            write_plan(args.output, plan)
        else:
            sys.stdout.buffer.write(canonical_bytes(plan))
    except (OSError, ProfileError, ValueError) as error:
        parser.exit(2, "profile plan refused: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
