"""Callable BENCHRUN owner seam; no CLI, host adapter or automatic live execution.

The reviewed RUN adapter must load Manager and this module against the SAME
protected common.lifecycle_lease module. Callback contracts below are mandatory:
all host snapshots, guards, exact Docker identity checks and anchored persistence
remain host-specific. Request/report workers do not own this object's lifetime.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Callable

from common.lifecycle_lease import LifecycleLease, acquire_lease
from .lifecycle import (BOOT_UNIT, CONTROL_UNIT, PlanError, cleanup_commands, digest,
                        plan_campaign, require, validate_restored, validate_snapshot)


class OwnerError(RuntimeError):
    """Safe diagnostic code; retain private original exception outside reports."""


@dataclass(frozen=True)
class HostCallbacks:
    """Concrete adapter surface, deliberately no shell/eval or credential values.

    capture(lease): fresh sanitized lifecycle snapshot. The lease is None only
      after ownership has ended. Before any mutation capture checks live control
      operation/request absence; do not derive freshness from saved state.
    guards(lease): current installed registered/root guards, anchored-path checks.
    gate(stage, lease, original, resources): fail closed on source/guard drift,
      pending service jobs, wrong owner/control state or unsafe in-flight work.
      Launch gates verify Qwen OCI ref/config/image binding with the existing
      qwen38_oci.verify_image contract, never equate an OCI ref to image ID.
      'restore' and 'retire' MUST refuse while a healthy request is active;
      'pre_release' proves original readiness/intent, private credential equality,
      boot unchanged, control inactive and every benchmark process absent.
    control(action): exact systemctl stop/start llm-control.service only.
    create(manifest): exact reviewed create_argv; return inspected resource dict.
      A timeout/error must reconcile the exact planned name/image/labels and
      return its identity or raise. It must never blind-retry Docker create.
    inspect(resource): return exact immutable fields plus running bool, or None
      if full ID is absent. Names alone never authorize adoption/removal.
    start/stop/remove(resource): revalidate exact ID/name/image/labels/restart=no,
      execute exact-ID operation once; remove refuses a running resource.
    write(ledger): atomic anchored private registered-log write and fsync. The
      caller also runs guards around it. No root-disk fallback or raw exceptions.
    checks(original, restored): fresh independent booleans for validate_restored,
      including private credential equality and authenticated worker LAN clients.
    """
    capture: Callable
    guards: Callable
    gate: Callable
    control: Callable
    create: Callable
    inspect: Callable
    start: Callable
    stop: Callable
    remove: Callable
    write: Callable
    checks: Callable


class CampaignOwner:
    """Explicit owner separate from request/parsing scopes.

    Serialize calls on the supervisor thread: begin(), launch()/retire(), then
    restore() explicitly. Report workers notify that thread rather than writing
    the ledger concurrently. There is no
    __exit__ that can kill healthy inference when a report parser throws.
    Lifecycle failures attempt restoration ONLY after the adapter's quiescence
    gate. If restoration cannot complete, the object retains its lease and
    RECOVERY_REQUIRED state for scoped recovery; it must remain strongly held by
    the RUN supervisor. Never discard/kill it to clear a failed lock.
    """
    def __init__(self, campaign, manager, host: HostCallbacks, budget, *,
                 reviewed_manifest_hashes, lease_factory=acquire_lease,
                 synthetic_offline=False):
        require(type(synthetic_offline) is bool, "invalid_offline_mode")
        self.campaign, self.manager, self.host, self.budget = campaign, manager, host, budget
        self.reviewed = frozenset(reviewed_manifest_hashes)
        require(bool(self.reviewed) and all(isinstance(item, str) and len(item) == 64 for item in self.reviewed),
                "reviewed_manifests_required")
        self.lease_factory, self.synthetic = lease_factory, synthetic_offline
        self.lease_context = self.lease = self.original = None
        self.phase, self.resources, self.pending_create = "NEW", [], None
        self.production_touched = self.control_touched = False
        self.errors = []
        self.budget_started = False
        self.restoration_started = False

    def _lease_check(self):
        require(type(self.lease) is LifecycleLease, "canonical_capability_required")
        self.lease.validate()

    def _guard(self):
        if self.lease is not None:
            self._lease_check()
        self.host.guards(self.lease)

    def _gate(self, stage):
        self._lease_check()
        self.host.gate(stage, self.lease, copy.deepcopy(self.original), copy.deepcopy(self.resources))

    def _ledger(self):
        return {"schema_version": 1, "campaign": self.campaign, "phase": self.phase,
                "evidence_kind": "synthetic_offline" if self.synthetic else "live",
                "original": copy.deepcopy(self.original), "resources": copy.deepcopy(self.resources),
                "pending_create": copy.deepcopy(self.pending_create), "errors": list(self.errors)}

    def _save(self):
        self._guard()
        self.host.write(self._ledger())
        self._guard()

    def _record_failure(self, code):
        self.errors.append(code)
        try:
            self._save()
        except Exception:
            # No model action in response to a reporting/storage parser failure.
            self.errors.append("evidence_write_failed")

    def _mutate(self, stage, function):
        self._gate(stage)
        self._guard()
        value = function()
        self._guard()
        return value

    def begin(self):
        require(self.phase == "NEW", "owner_already_started")
        try:
            self.lease_context = self.lease_factory(blocking=False)
            self.lease = self.lease_context.__enter__()
            self._lease_check()
            before = self.host.capture(self.lease)
            self.original = validate_snapshot(before, for_run=not self.synthetic)
            require(before["lease"]["held"] and before["lease"]["owned_by_campaign"], "owner_snapshot_required")
            require((before["evidence_kind"] == "synthetic_offline") == self.synthetic, "evidence_mode_mismatch")
            plan_campaign(self.original, self.campaign)  # same validated plan as review
            self._gate("admission")
            self.phase = "SNAPSHOTTED"
            self._save()  # snapshot is durable before first maintenance
            self.budget.start("maintenance")
            self.budget_started = True
            if before["services"][CONTROL_UNIT]["active"] == "active":
                self.control_touched = True
                self._mutate("freeze_control", lambda: self.host.control("stop"))
            self._gate("control_frozen")
            self.production_touched = True
            self._mutate("production_stop", lambda: self.manager.dispatch("boot-stop", lease=self.lease))
            self._gate("production_stopped")
            self.phase = "ACTIVE"
            self._save()
            return self
        except BaseException:
            self._recover_failure("maintenance_failed")
            raise OwnerError("maintenance_failed_inspect_owner_ledger") from None

    def record_harness_failure(self):
        """Owner-thread report-worker notification; never restores or stops models."""
        self._record_failure("HARNESS_FAILURE")
        return {"state": "HARNESS_FAILURE", "healthy_inference_cancelled": False}

    def _resource(self, value, manifest=None):
        require(type(value) is dict and type(value.get("running")) is bool, "invalid_resource_observation")
        resource = {key: value.get(key) for key in ("id", "name", "image_id", "campaign_label", "owner_label", "restart_policy")}
        cleanup_commands(self.campaign, [resource])
        if manifest is not None:
            require(resource["name"] == manifest["container_name"] and resource["image_id"] in manifest.get("expected_image_ids", []),
                    "created_identity_differs_from_manifest")
        return resource

    def launch(self, manifest):
        require(self.phase == "ACTIVE", "owner_not_active")
        require(digest(manifest) in self.reviewed and manifest.get("campaign") == self.campaign,
                "unreviewed_launch_manifest")
        require(self.pending_create is None, "unresolved_create_intent")
        require(all(row["resource"]["name"] != manifest["container_name"] or row["state"] == "REMOVED"
                    for row in self.resources), "container_name_already_owned")
        try:
            require(self.budget.checkpoint() > 0, "STOP_BUDGET")
            self._gate("launch")
            self.pending_create = {"manifest_sha256": digest(manifest), "name": manifest["container_name"],
                                   "image": manifest["image"], "campaign": self.campaign}
            self._save()  # interrupted create remains recoverable by exact planned identity
            self._guard()
            created = self.host.create(copy.deepcopy(manifest))
            resource = self._resource(created, manifest)
            require(created["running"] is False, "create_must_not_start")
            row = {"resource": resource, "state": "CREATED"}
            self.resources.append(row)  # retain returned ID even if persistence/guard then fails
            self.pending_create = None
            self._save()  # exact ID durable before start
            self._mutate("start", lambda: self.host.start(copy.deepcopy(resource)))
            observed = self.host.inspect(copy.deepcopy(resource))
            require(observed is not None and self._resource(observed) == resource and observed["running"] is True,
                    "started_identity_unverified")
            row["state"] = "RUNNING"
            self._save()
            return copy.deepcopy(resource)
        except BaseException:
            self._recover_failure("launch_failed")
            raise OwnerError("launch_failed_inspect_owner_ledger") from None

    def _retire_row(self, row):
        resource = row["resource"]
        if row["state"] == "REMOVED":
            return
        observed = self.host.inspect(copy.deepcopy(resource))
        if observed is not None:
            require(self._resource(observed) == resource, "owned_resource_drift")
            if observed["running"]:
                self._mutate("stop", lambda: self.host.stop(copy.deepcopy(resource)))
            stopped = self.host.inspect(copy.deepcopy(resource))
            require(stopped is not None and self._resource(stopped) == resource and stopped["running"] is False,
                    "owned_resource_not_stopped")
            row["state"] = "STOPPED"
            self._save()
            self._mutate("remove", lambda: self.host.remove(copy.deepcopy(resource)))
            require(self.host.inspect(copy.deepcopy(resource)) is None, "owned_resource_still_present")
        row["state"] = "REMOVED"
        self._save()

    def retire(self, container_id):
        require(self.phase == "ACTIVE", "owner_not_active")
        rows = [row for row in self.resources if row["resource"]["id"] == container_id and row["state"] != "REMOVED"]
        require(len(rows) == 1, "unknown_owned_resource")
        try:
            self._gate("retire")  # cannot stop a healthy in-flight request
            self._retire_row(rows[0])
        except BaseException:
            self._recover_failure("retire_failed")
            raise OwnerError("retire_failed_inspect_owner_ledger") from None

    def _recover_failure(self, code):
        self._record_failure(code)
        if self.lease is None:
            self.phase = "FAILED_BEFORE_OWNERSHIP"
            return
        if self.original is None or not (self.production_touched or self.control_touched):
            self._release()
            self.phase = "FAILED_BEFORE_MUTATION"
            return
        try:
            self.restore()
        except BaseException:
            self.phase = "RECOVERY_REQUIRED" if self.lease is not None else "POST_RELEASE_VERIFICATION_FAILED"
            self._record_failure("restoration_requires_reviewed_recovery")

    def _release(self):
        if self.lease_context is not None:
            self.lease_context.__exit__(None, None, None)
            self.lease_context = self.lease = None

    def _verify_under_lease(self):
        observed = validate_snapshot(self.host.capture(self.lease), for_run=not self.synthetic)
        for key in ("selected", "desired", "observed", "boot_policy", "container_running"):
            require(observed["manager"][key] == self.original["manager"][key], "original_intent_not_restored")
        for key in ("source", "storage", "credentials"):
            require(observed[key] == self.original[key], "preserved_identity_changed")
        require(observed["services"][BOOT_UNIT] == self.original["services"][BOOT_UNIT], "boot_service_changed")
        control = {**self.original["services"][CONTROL_UNIT], "active": "inactive", "substate": "dead"}
        require(observed["services"][CONTROL_UNIT] == control, "control_not_frozen_for_release")
        for key in ("installed_path", "sha256", "dependency_sha256"):
            require(observed["guards"][key] == self.original["guards"][key], "guard_identity_changed")
        self._gate("pre_release")

    def restore(self):
        require(self.lease is not None and self.original is not None, "no_owned_campaign_to_restore")
        try:
            self._gate("restore")  # refusals retain the lease; never stop healthy inference
            require(self.pending_create is None, "unresolved_create_requires_exact_identity_recovery")
            if self.phase != "RESTORING":
                self.phase = "RESTORING"
                if self.budget_started and not self.restoration_started:
                    self.restoration_started = True
                    try:
                        self.budget.begin_restoration()
                    except Exception:
                        self._record_failure("budget_restoration_record_failed")
                self._save()
            for row in reversed(self.resources):
                self._retire_row(row)
            self._gate("benchmarks_absent")
            if self.production_touched:
                self._mutate("restore_production_stop", lambda: self.manager.dispatch("boot-stop", lease=self.lease))
                original = self.original["manager"]
                if original["selected"] is None:
                    self._mutate("restore_deactivate", lambda: self.manager.dispatch("deactivate", lease=self.lease))
                else:
                    self._mutate("restore_select", lambda: self.manager.dispatch("select", deployment_id=original["selected"],
                                 boot_policy=original["boot_policy"], lease=self.lease))
                    if original["desired"] == "running":
                        self._mutate("restore_start", lambda: self.manager.dispatch("start", lease=self.lease))
            self._verify_under_lease()
            self._guard()
            self.phase = "RESTORED_UNDER_LEASE"
            self._save()
            self._release()
            if self.original["services"][CONTROL_UNIT]["active"] == "active":
                self._guard()
                self.host.control("start")
                self._guard()
            after = self.host.capture(None)
            result = validate_restored(self.original, after, self.host.checks(self.original, after))
            self.phase = "RESTORED"
            try:
                if self.budget_started:
                    self.budget.finish_restoration(True)
                self._save()
            except Exception:
                self.errors.append("restored_evidence_write_failed")
                result["evidence_persistence"] = "FAILED_SERVICE_RESTORATION_VERIFIED"
            return result
        except BaseException:
            self.phase = "RECOVERY_REQUIRED" if self.lease is not None else "POST_RELEASE_VERIFICATION_FAILED"
            self._record_failure("restoration_failed")
            raise OwnerError("restoration_failed_preserve_owner_and_ledger") from None
