#!/usr/bin/env python3
"""Ubuntu 24.04 bounded installer stages. Full installation remains pending I1c."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install.config import DEFAULTS, load, validate
from install.core import InstallError, Pending, Runner, atomic_json, digest, exclusive, private_path, read_private_json
from install.host import budget, model_plan, observe, supported

BOOTSTRAP = Path("/etc/local-ai-server/bootstrap.json")
STAGES = ["preflight", "storage", "base", "driver", "container", "gpu_container", "runtime", "acquisition", "service", "client", "acceptance"]
IMPLEMENTED = {"preflight", "storage", "base", "driver", "container", "gpu_container", "runtime", "acquisition"}
# Coordinator-owned I1R/L1 source is not in this checkout. Only reviewed source
# integration may replace this checkpoint with package admission/lease export;
# method-name detection or an environment switch cannot establish that contract.
PACKAGE_EXECUTION = "PENDING_REVIEWED_I1R_L1_INTEGRATION"


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("plan", "apply", "resume", "status", "verify"))
    p.add_argument("--config", type=Path, help="Strict schema1 JSON config; explicit flags override file")
    for name, choices in (("role", ["server", "client", "combined"]),
                          ("profile", ["flagship-hybrid", "fast-gpu"]),
                          ("model-set", ["glm", "qwen", "glm,qwen"]),
                          ("storage-mode", ["existing", "mount", "initialize"])):
        p.add_argument("--" + name, choices=choices)
    for name in ("data-dir", "data-uuid", "model-dir", "model-uuid", "initialize-empty-disk", "confirm-disk-id", "disk-plan",
                 "client-user", "client-workspace", "client-prefix", "client-base-url", "client-model", "client-key-file", "ssh-host"):
        p.add_argument("--" + name)
    for name in ("expected-gpu-count", "root-min-free-bytes", "root-package-budget-bytes", "context-tokens", "output-tokens"):
        p.add_argument("--" + name, type=int)
    p.add_argument("--yes", action="store_true", help="Authorize selected apply/resume stages")
    p.add_argument("--dry-run", action="store_true", help="Read-only plan, including disk identity inspection")
    p.add_argument("--through", choices=("storage", "base", "driver", "container", "runtime", "acquisition", "models"), help="Explicit bounded stage boundary; models aliases acquisition; never READY")
    p.add_argument("--fixture-host", type=Path, help="Synthetic host JSON, only for read-only plan; cannot enable apply/resume/verify")
    return p


def source_identity():
    paths = list((REPO / "scripts/install").glob("*.py")) + [REPO / "install.sh", REPO / "scripts/common/registered-storage.py", REPO / "scripts/common/require-data-mounted.sh", REPO / "scripts/common/root-disk-guard.sh"]
    paths += [REPO / p for p in ("reports/r2-flagship-artifact.json", "reports/f1a-qwen-manifest.json", "containers/llama-cpp/Dockerfile",
        "configs/runtimes/llama-cpp-v0.4.1-d1.json", "scripts/client/package-lock.json")]
    return digest({str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def version_lock():
    path = REPO / "scripts/install/versions.lock.json"
    if not path.is_file():
        raise Pending("version_lock_unavailable")
    return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()


def applicable(config):
    if config["role"] == "client":
        return ["preflight", "client", "acceptance"]
    return [s for s in STAGES if s != "client" or config["role"] == "combined"]


def config_for(args):
    supplied = load(args.config) if args.config else {}
    if args.command in {"resume", "status", "verify"} and BOOTSTRAP.exists():
        boot = read_private_json(BOOTSTRAP)
        if boot.get("schema_version") != 1:
            raise InstallError("invalid_bootstrap_schema")
        supplied = {**boot["config"], **supplied}
    for key in DEFAULTS:
        if hasattr(args, key) and getattr(args, key) is not None:
            supplied[key] = getattr(args, key)
    return validate(supplied)


def make_plan(config, args, runner):
    if args.fixture_host:
        fixture = load(args.fixture_host)
        if set(fixture) != {"host", "storage"}:
            raise InstallError("invalid_host_fixture")
        host, storage = fixture["host"], fixture["storage"]
    else:
        host = observe(runner)
        if supported(host) and config["role"] != "client":
            from install.storage import Storage
            try:
                storage = Storage(config, runner).plan()
            except Exception:
                storage = {"status": "unverified_or_rejected", "capacity": {}}
        else:
            storage = {"status": "not_inspected", "capacity": {}}
    models = model_plan(config, REPO)
    lock, lock_hash = version_lock()
    disk_budget = budget(config, models, storage) if models else None
    selected = applicable(config)
    pending = [s for s in selected if s not in IMPLEMENTED]
    from install.stage_plan import bounded_plan
    details = bounded_plan(config, REPO, lock)
    remaining = None
    if not args.fixture_host and supported(host) and config["role"] != "client":
        from install.storage import Storage
        current = Storage(config, runner)
        if current.read_registration() is not None:
            from install.acquisition import AcquisitionStage
            from install.runtime import RuntimeStage
            from install.storage_io import MountedStorageGuard
            with MountedStorageGuard(current) as fast_guard:
                acquisition = AcquisitionStage(config, runner, fast_guard)
                if RuntimeStage(config, runner, fast_guard).check():
                    acquisition.runtime_reserve = 0
                remaining = acquisition.plan_remaining()
                disk_budget["space_status"] = remaining["space_status"]
                disk_budget["reservation_basis"] = "actual_remaining_model_bytes_plus_unverified_runtime_reserve"
    return {"schema_version": 1, "evidence_class": "SYNTHETIC_FIXTURE" if args.fixture_host else "READ_ONLY_DISCOVERY",
            "installer_status": "INCOMPLETE_I1C_REQUIRED", "ready": False, "host": host,
            "host_supported": supported(host), "config": config, "storage": storage, "models": models,
            "disk_budget": disk_budget, "remaining_acquisition": remaining, "bounded_stage_plan": details, "version_lock": lock, "lock_hash": lock_hash, "input_hash": source_identity(),
            "stages": [{"name": s, "implementation": "available" if s in IMPLEMENTED else "pending_I1c"} for s in selected],
            "pending_required_stages": pending, "package_execution": PACKAGE_EXECUTION,
            "effects": ["plan writes nothing", "full apply refused before mutation until required stages integrated",
                "explicit --through selects bounded stages only", "driver changes may require manual reboot; exit75 then resume",
                "no automatic reboot", "package/root usage bounded; caches and logs require registered data", "no model fit claim from artifact sizes"],
            "limitations": ["blank disk provisioning pending I1S", "L1 generic lifecycle and F1S safe auth gate required",
                           "I1R Runner process-lifetime and observation interface fix required before production",
                           "server is API-only; real agent tools belong to chosen ordinary client user", "full fresh GPU install/reboot NOT_TESTED"]}


def require_preflight(config, plan):
    if not plan["host_supported"]:
        raise InstallError("unsupported_host_requires_ubuntu_2404_amd64")
    if plan["host"]["root_available_bytes"] < config["root_min_free_bytes"] + config["root_package_budget_bytes"]:
        raise InstallError("insufficient_root_package_headroom")
    if plan["disk_budget"] and plan["disk_budget"]["space_status"] == "insufficient":
        raise InstallError("insufficient_dedicated_data_capacity")


def run_boundary(config, args, runner, plan, lock_hash):
    from install.storage import Storage
    storage = Storage(config, runner)
    require_preflight(config, plan)
    if config["storage_mode"] == "initialize":
        raise Pending("blank_disk_mutation_requires_i1s")
    # Canonical L1 lease/Manager borrowing integration is reserved for I1c.
    # Keep the exact existing global context uninterrupted until it is supplied.
    with exclusive(Path("/run/llmctl/lifecycle.lock")):
        if BOOTSTRAP.exists():
            previous = read_private_json(BOOTSTRAP)
            if (previous.get("config_hash") != digest(config) or previous.get("lock_hash") != lock_hash
                    or previous.get("input_hash") != source_identity()):
                raise InstallError("bootstrap_config_lock_or_source_changed")
        if args.command == "verify":
            storage.guard()
        else:
            storage.adopt()
        storage.guard()
        if args.command != "verify":
            BOOTSTRAP.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_path(BOOTSTRAP.parent, directory=True)
            boot = {"schema_version": 1, "config": config, "config_hash": digest(config), "lock_hash": lock_hash,
                    "input_hash": source_identity(), "state": str(Path(config["data_dir"]) / "services/installer/state.json"),
                    "storage_registry": "/etc/local-ai-server/storage.json"}
            if BOOTSTRAP.exists():
                if read_private_json(BOOTSTRAP) != boot:
                    raise InstallError("bootstrap_config_lock_or_source_changed")
            else:
                storage.guard()
                atomic_json(BOOTSTRAP, boot)
        from install.storage_io import AnchoredRoot, MountedStorageGuard
        from install.stage_state import AnchoredState
        with MountedStorageGuard(storage) as fast_guard, AnchoredRoot(storage.guard()["roots"]["state"], fast_guard) as state_root:
            state = AnchoredState(state_root, "state.json", config, lock_hash, source_identity(), storage.root_payload_guard)
            stages = boundary_stages(config, args, runner, storage, fast_guard)
            results = state.run(stages, verify_only=args.command == "verify")
            fast_guard.verify_full()
        return {"schema_version": 1, "status": "PARTIAL_INSTALLATION", "ready": False, "results": results,
                "pending_required_stages": [s for s in applicable(config) if s not in {x["stage"] for x in results} and s != "preflight"],
                "next_action": "I1c service/control/client/acceptance integration required before full installation"}


def boundary_stages(config, args, runner, storage, fast_guard):
    """Actual stage dispatcher, also exercised with explicit in-process fixtures.

    Caller owns the global lease. I1R owns Runner and package process lifetime;
    no additional subprocess implementation is introduced here.
    """
    from install.prerequisites import Prerequisites
    through = "acquisition" if args.through == "models" else args.through
    stop = STAGES.index(through)
    selected = set(STAGES[:stop + 1])
    prereqs = Prerequisites(config, runner, storage.root_payload_guard)
    if args.command != "verify" and "base" in selected:
        prereqs.recover_policy()
    stages = [("storage", lambda: bool(storage.guard()), lambda: storage.adopt())]
    if "base" in selected:
        stages.append(("base", prereqs.check_base, prereqs.apply_base))
    if "driver" in selected:
        stages.append(("driver", prereqs.check_driver, prereqs.apply_driver))
    if "container" in selected:
        from install.container import ContainerStage
        container = ContainerStage(config, runner, fast_guard)
        stages.append(("container", container.check, container.apply))
    if "gpu_container" in selected:
        stages.append(("gpu_container", container.check_gpu, container.apply_gpu))
    if "runtime" in selected:
        from install.runtime import RuntimeStage
        runtime = RuntimeStage(config, runner, fast_guard)
        stages.append(("runtime", runtime.check, runtime.apply))
    if "acquisition" in selected:
        from install.acquisition import AcquisitionStage
        acquisition = AcquisitionStage(config, runner, fast_guard)
        # Previous runtime stage verifies all selected images before acquisition.
        # Occupied runtime bytes are already excluded from filesystem free space.
        acquisition.runtime_reserve = 0
        stages.append(("acquisition", acquisition.check, acquisition.apply))
    return stages



def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.fixture_host and (args.command != "plan" or args.dry_run):
            raise InstallError("fixture_host_only_allowed_for_plan")
        if args.command in {"resume", "verify"} and not BOOTSTRAP.exists():
            raise InstallError("installation_bootstrap_missing")
        if args.command == "status" and not BOOTSTRAP.exists():
            print(json.dumps({"schema_version": 1, "status": "NOT_INSTALLED", "ready": False, "observation": "no_bootstrap"}, indent=2))
            return 0
        config = config_for(args)
        runner = Runner(writable=False)
        if args.command == "status":
            from install.storage import Storage
            from install.storage_io import AnchoredRoot, MountedStorageGuard
            from install.stage_state import AnchoredState
            current = Storage(config, runner)
            _, lock_hash = version_lock()
            with MountedStorageGuard(current) as fast_guard, AnchoredRoot(current.guard()["roots"]["state"], fast_guard) as state_root:
                if state_root.stat("state.json", missing_ok=True) is None:
                    raise InstallError("installation_state_missing")
                state = AnchoredState(state_root, "state.json", config, lock_hash, source_identity(), fast_guard).value
            print(json.dumps({"schema_version": 1, "ready": False, "status": "PARTIAL_INSTALLATION", "recorded": state,
                              "observation": "storage_verified_only_service_not_observed"}, indent=2))
            return 0
        plan = make_plan(config, args, runner)
        if args.command == "plan" or args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0 if plan["host_supported"] else 1
        selected = applicable(config)
        if not args.through or config["role"] == "client":
            raise Pending("required_deployment_stages_not_implemented_i1c")
        if args.command in {"apply", "resume"} and not args.yes:
            raise InstallError("apply_requires_yes")
        if args.command in {"apply", "resume"} and args.through != "storage":
            raise Pending("reviewed_i1r_l1_package_integration_required")
        if args.command == "verify" and args.through in {"container", "runtime", "acquisition", "models"}:
            if not Runner._readonly(["docker", "info", "--format", "{{json .}}"]):
                raise Pending("reviewed_i1r_observation_interface_required")
        if os.geteuid() != 0:
            raise InstallError("run_server_boundary_with_sudo")
        runner.writable = args.command != "verify"
        result = run_boundary(config, args, runner, plan, plan["lock_hash"])
        print(json.dumps(result, indent=2))
        return 1 if any(x["status"] == "pending" for x in result["results"]) else 0
    except Exception as exc:
        code = exc.code if isinstance(exc, InstallError) else "installer_operation_failed"
        if exc.__class__.__name__ == "StorageError":
            code = "registered_storage_validation_failed"
        if re.fullmatch(r"[a-z0-9_]{1,100}", str(getattr(exc, "code", ""))):
            code = exc.code
        exit_code = getattr(exc, "exit_code", 1)
        payload = {"schema_version": 1, "ready": False, "failure": code,
                   "status": "REBOOT_CHECKPOINT" if exit_code == 75 else "PENDING" if exit_code == 78 else "FAILED"}
        details = getattr(exc, "public_details", None)
        if isinstance(details, dict):
            payload["details"] = {k: v for k, v in details.items() if k in {"package", "version", "target_kernel"}
                                  and isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.:+~-]{1,128}", v)}
        if exit_code == 75:
            payload["target_kernel"] = getattr(exc, "target_kernel", None)
            payload["next_action"] = "Resolve any Secure Boot checkpoint; reboot explicitly, then sudo ./install.sh resume --through driver --yes"
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
