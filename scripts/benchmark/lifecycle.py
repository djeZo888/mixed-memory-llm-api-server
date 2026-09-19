"""Pure BENCHPREP lifecycle manifests: no host I/O and no mutation executor.

The live owner must use common.lifecycle_lease.acquire_lease(blocking=False)
exactly once and pass that same-process object to Manager.dispatch. There is no
lease environment variable, alternate lock, exported-FD or subprocess CLI bypass.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import PurePosixPath
import re
import sys

CANONICAL_LOCK = "/run/llmctl/lifecycle.lock"
CONTROL_UNIT = "llm-control.service"
BOOT_UNIT = "llmctl-boot.service"
DEPLOYMENTS = frozenset({"glm-5.3-ud-q4-k-xl-n76-native1m",
                        "qwen38-27b-1000000-yarn4-tp2-bf16kv"})
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CAMPAIGN = re.compile(r"[a-z0-9][a-z0-9-]{0,47}\Z")


class PlanError(ValueError):
    """A bounded safe code; never interpolate snapshot content into errors."""


def require(condition, code):
    if not condition:
        raise PlanError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def protected_path(value, prefix):
    require(isinstance(value, str), "invalid_protected_path")
    path = PurePosixPath(value)
    require(path.is_absolute() and ".." not in path.parts and
            str(path) == value and value.startswith(prefix + "/"), "invalid_protected_path")


def validate_snapshot(snapshot, *, for_run=False):
    """Validate sanitized observations; a baseline is not an under-lease snapshot.

    Private capture additionally verifies protected ancestry/stat identities and
    credentials without returning values or content digests. This pure validator
    cannot establish those live facts by itself.
    """
    require(type(snapshot) is dict and snapshot.get("schema_version") == 1,
            "invalid_snapshot_schema")
    require(snapshot.get("evidence_kind") in {"live_readonly", "synthetic_offline"},
            "invalid_evidence_kind")
    require(isinstance(snapshot.get("captured_at"), str) and bool(snapshot["captured_at"]),
            "missing_capture_time")
    state = snapshot.get("manager", {})
    selected = state.get("selected")
    require(selected is None or selected in DEPLOYMENTS, "unknown_original_deployment")
    require(state.get("desired") in {"running", "stopped"}, "ambiguous_original_intent")
    require(state.get("boot_policy") in {"manual", "resume"}, "ambiguous_boot_preference")
    require(state.get("state_persisted") is True and state.get("recovery_pending") is False,
            "unsettled_manager_state")
    if state["desired"] == "running":
        require(selected is not None and state.get("observed") == "ready" and
                state.get("container_running") is True, "original_running_not_ready")
    else:
        require(state.get("observed") == "stopped" and state.get("container_running") is False,
                "original_stopped_not_quiescent")
        require(selected is not None or state["boot_policy"] == "manual", "empty_resume_intent")
    control = snapshot.get("control", {})
    require(control.get("operation") is None and control.get("fresh") is True,
            "control_not_quiescent")
    require(snapshot.get("pending_systemd_jobs") == [], "pending_service_job")
    lease = snapshot.get("lease", {})
    require(lease.get("path") == CANONICAL_LOCK and type(lease.get("held")) is bool,
            "invalid_canonical_lease")
    require(type(lease.get("owned_by_campaign")) is bool and
            lease["held"] == lease["owned_by_campaign"], "foreign_lease_owner")
    if for_run:
        require(snapshot["evidence_kind"] == "live_readonly" and lease["held"] is True,
                "fresh_campaign_owned_snapshot_required")
    services = snapshot.get("services", {})
    require(set(services) == {CONTROL_UNIT, BOOT_UNIT}, "missing_service_state")
    for name, service in services.items():
        require(service.get("active") in {"active", "inactive"} and
                service.get("enabled") in {"enabled", "disabled", "static"},
                "ambiguous_service_state")
        expected_substate = "dead" if service["active"] == "inactive" else ("exited" if name == BOOT_UNIT else "running")
        require(service.get("substate") == expected_substate, "transitional_service_state")
        require(service.get("masked") is False, "preexisting_service_mask")
        require(bool(HEX64.fullmatch(service.get("unit_sha256", ""))), "missing_service_pin")
        require(service.get("exec_stop_uses_lifecycle") is (name == BOOT_UNIT),
                "service_stop_contract_changed")
    guards = snapshot.get("guards", {})
    require(guards.get("storage_passed") is True and guards.get("root_disk_passed") is True,
            "guard_failure")
    protected_path(guards.get("installed_path"), "/usr/local/lib")
    require(bool(HEX64.fullmatch(guards.get("sha256", ""))) and
            bool(HEX64.fullmatch(guards.get("dependency_sha256", ""))), "missing_installed_guard_pin")
    storage = snapshot.get("storage", {})
    require(storage.get("authority") == "/etc/local-ai-server/storage.json" and
            bool(HEX64.fullmatch(storage.get("identity_sha256", ""))) and
            storage.get("protected_ancestry_verified") is True,
            "unverified_registered_storage")
    source = snapshot.get("source", {})
    protected_path(source.get("manager_root"), "/usr/local/lib")
    require(bool(HEX64.fullmatch(source.get("closure_sha256", ""))), "missing_manager_source_pin")
    require(source.get("lease_semantics") == "same_process_capability", "unsupported_lease_semantics")
    credentials = snapshot.get("credentials", {})
    require(set(credentials) == {"inference", "control"}, "missing_credential_identity")
    for value in credentials.values():
        require(type(value) is dict and set(value) == {"uid", "gid", "mode", "dev", "ino", "size", "mtime_ns", "ctime_ns"},
                "unsafe_credential_identity")
        require(all(type(item) is int and item >= 0 for item in value.values()) and
                value["uid"] == 0 and value["mode"] == 0o600, "unprotected_credential")
    return copy.deepcopy(snapshot)


def dispatch(action, **kwargs):
    return {"kind": "same_process_call", "call": "manager.dispatch", "action": action,
            "kwargs": kwargs, "lease_argument": "campaign_lease"}


def plan_campaign(snapshot, campaign_id):
    """Return a reviewable dry-run manifest, never execute its descriptors."""
    before = validate_snapshot(snapshot)
    require(isinstance(campaign_id, str) and bool(CAMPAIGN.fullmatch(campaign_id)), "invalid_campaign_id")
    original = before["manager"]
    guard = before["guards"]["installed_path"]
    guard_commands = [["/usr/bin/python3", "-I", "-B", guard, "--json"],
                      ["/usr/bin/python3", "-I", "-B", guard, "--json", "--root-guard"]]
    maintenance = [
        {"kind": "call", "call": "common.lifecycle_lease.acquire_lease", "kwargs": {"blocking": False},
         "result": "campaign_lease", "lock": CANONICAL_LOCK},
        {"kind": "require", "checks": ["reread protected snapshot under campaign_lease",
         "validate_snapshot(for_run=True)", "compare reviewed source/guard/storage pins",
         "no current request/control operation or systemd job", "durably record budget start before first maintenance"]},
        {"kind": "guard", "argvs": guard_commands, "before_and_after_each_mutation": True},
    ]
    if before["services"][CONTROL_UNIT]["active"] == "active":
        maintenance.append({"kind": "command", "argv": ["/usr/bin/systemctl", "stop", CONTROL_UNIT]})
    maintenance.extend([
        {"kind": "require", "checks": ["control service inactive and no control process",
         "no pending systemd jobs", "boot service and enablement unchanged",
         "lease.validate() before and after every mutation"]},
        dispatch("boot-stop"),  # preserves selected, desired and boot preference
        {"kind": "require", "checks": ["original backend stopped", "no other GPU process",
         "benchmark launch commands match reviewed manifest", "all Docker restart policies are no"]},
    ])
    restoration = [
        {"kind": "require", "checks": ["finish or explicitly cancel current request under campaign owner",
         "stop/remove only exact IDs in owned resource ledger", "verify all owned resources absent",
         "no remaining benchmark GPU process or listener"]},
        {"kind": "guard", "argvs": guard_commands},
    ]
    if original["selected"] is not None:
        restoration.append(dispatch("select", deployment_id=original["selected"], boot_policy=original["boot_policy"]))
        if original["desired"] == "running":
            restoration.append(dispatch("start"))
    else:
        restoration.append(dispatch("deactivate"))
    restoration.extend([
        {"kind": "require", "checks": ["original selected/desired/boot preference restored",
         "original readiness or stopped state restored", "credential private equality check passed",
         "storage/source/guard/lease inode unchanged", "boot service and enablement unchanged",
         "control service remains inactive", "no pending systemd jobs"]},
        {"kind": "guard", "argvs": guard_commands},
        {"kind": "call", "call": "campaign_lease context exit", "condition": "all under-lease restoration checks passed"},
    ])
    if before["services"][CONTROL_UNIT]["active"] == "active":
        restoration.append({"kind": "command", "argv": ["/usr/bin/systemctl", "start", CONTROL_UNIT]})
    restoration.append({"kind": "require", "checks": ["canonical lease not held; lock inode retained",
        "all original service active/enabled states exact", "authenticated worker LAN control/status",
        "authenticated worker LAN inference if originally running; otherwise NOT_APPLICABLE_STOPPED_INTENT",
        "no benchmark processes/containers or pending service jobs", "validate_restored passed"]})
    return {"schema_version": 1, "dry_run": True, "execution_implemented": False,
            "campaign_id": campaign_id, "snapshot_sha256": digest(before),
            "maintenance": maintenance, "restoration": restoration,
            "budget": {"seconds": 21600, "request_timeout_seconds": 7200,
                       "starts_at": "first_maintenance_or_model_trial", "restoration_excluded": True},
            "failure_policy": {"report_or_parser_error": "persist harness failure; do not stop healthy inference",
                "owner_crash": "leave stopped control; reacquire canonical lease with fresh reviewed owner; validate ledger and restore",
                "guard_failure": "stop admitting trials; preserve evidence; scoped recovery only",
                "restoration_failure": "retain owner when possible; no new trials; report concrete recovery blocker"},
            "constraints": ["No CLI lifecycle child while lease held: it reacquires/deadlocks",
                "No environment capability or alternate lock",
                "Never stop/restart boot service under held lease: ExecStop reacquires/deadlocks",
                "Keep boot unit active/enabled state and files untouched; no runtime-mask assumption",
                "Stop control only after canonical acquisition and no in-flight request",
                "No blind retries; guard failure stops new trials and requires scoped recovery",
                "Crash recovery needs fresh reviewed owner; never kill unknown lock holder or remove lock inode"]}


def cleanup_commands(campaign_id, resources):
    """Exact-ID rollback commands; identities must be rechecked live before use."""
    require(isinstance(campaign_id, str) and bool(CAMPAIGN.fullmatch(campaign_id)), "invalid_campaign_id")
    require(type(resources) is list, "invalid_resource_ledger")
    commands, seen = [], set()
    for resource in resources:
        require(type(resource) is dict, "invalid_resource_identity")
        cid = resource.get("id", "")
        require(isinstance(cid, str) and bool(HEX64.fullmatch(cid)) and cid not in seen,
                "ambiguous_container_identity")
        seen.add(cid)
        name = resource.get("name", "")
        require(isinstance(name, str) and re.fullmatch(re.escape(campaign_id) + r"-[a-z0-9-]+", name),
                "unowned_container_name")
        require(resource.get("campaign_label") == campaign_id and
                resource.get("owner_label") == "llm-benchmark" and
                re.fullmatch(r"sha256:[0-9a-f]{64}", resource.get("image_id", "")) and
                resource.get("restart_policy") == "no", "unowned_container_identity")
        commands.append({"require_identity": copy.deepcopy(resource),
                         "argv": ["/usr/bin/docker", "stop", "--time", "120", cid]})
        commands.append({"require_identity": copy.deepcopy(resource), "require_stopped": True,
                         "argv": ["/usr/bin/docker", "rm", cid]})
    return commands


def validate_restored(before, after, checks):
    """Require fresh restoration evidence; parser failure does not stop inference."""
    before, after = validate_snapshot(before), validate_snapshot(after)
    require(after["lease"]["held"] is False, "campaign_lease_still_held")
    for key in ("selected", "desired", "boot_policy", "observed", "container_running"):
        require(before["manager"][key] == after["manager"][key], "original_intent_not_restored")
    for key in ("services", "storage", "source", "credentials"):
        require(before[key] == after[key], "preserved_identity_changed")
    for key in ("installed_path", "sha256", "dependency_sha256"):
        require(before["guards"][key] == after["guards"][key], "guard_identity_changed")
    for key in ("credentials_private_equality", "no_benchmark_processes", "no_benchmark_containers",
                "no_benchmark_listeners", "lease_inode_unchanged"):
        require(checks.get(key) is True, "restoration_verification_incomplete")
    control_expected = True if before["services"][CONTROL_UNIT]["active"] == "active" else "NOT_APPLICABLE_CONTROL_INACTIVE"
    require(checks.get("worker_lan_control_authenticated") == control_expected, "restoration_control_unverified")
    expected = True if before["manager"]["desired"] == "running" else "NOT_APPLICABLE_STOPPED_INTENT"
    require(checks.get("worker_lan_inference_authenticated") == expected, "restoration_inference_unverified")
    return {"restored": True, "evidence_kind": after["evidence_kind"],
            "original_selected": before["manager"]["selected"], "original_desired": before["manager"]["desired"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="sanitized snapshot JSON")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="required; this program has no live execution mode")
    args = parser.parse_args(argv)
    try:
        with open(args.snapshot, encoding="utf-8") as stream:
            snapshot = json.load(stream)
        print(json.dumps(plan_campaign(snapshot, args.campaign), sort_keys=True, indent=2))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        print(str(error) if isinstance(error, PlanError) else "invalid_snapshot_or_io", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
