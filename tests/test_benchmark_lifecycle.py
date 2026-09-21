"""Synthetic/offline lifecycle planning; never contacts systemd, Docker or a host."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.lifecycle import (BOOT_UNIT, CANONICAL_LOCK, CONTROL_UNIT, DEPLOYMENTS,
    PlanError, cleanup_commands, plan_campaign, validate_restored, validate_snapshot)


def snapshot(selected="qwen38-27b-1000000-yarn4-tp2-bf16kv", running=True):
    return {"schema_version": 1, "evidence_kind": "synthetic_offline", "captured_at": "2026-09-19T00:00:00Z",
        "manager": {"selected": selected, "desired": "running" if running else "stopped",
                    "observed": "ready" if running else "stopped", "container_running": running,
                    "boot_policy": "resume" if selected else "manual", "state_persisted": True,
                    "recovery_pending": False},
        "control": {"operation": None, "fresh": True}, "pending_systemd_jobs": [],
        "lease": {"path": CANONICAL_LOCK, "held": False, "owned_by_campaign": False},
        "services": {
            CONTROL_UNIT: {"active": "active", "enabled": "enabled", "substate": "running",
                           "masked": False, "unit_sha256": "a" * 64, "exec_stop_uses_lifecycle": False},
            BOOT_UNIT: {"active": "active", "enabled": "enabled", "substate": "exited",
                        "masked": False, "unit_sha256": "b" * 64, "exec_stop_uses_lifecycle": True}},
        "guards": {"storage_passed": True, "root_disk_passed": True,
                   "installed_path": "/usr/local/lib/local-ai-server/scripts/common/registered-storage.py",
                   "sha256": "c" * 64, "dependency_sha256": "d" * 64},
        "storage": {"authority": "/etc/local-ai-server/storage.json", "identity_sha256": "e" * 64,
                    "protected_ancestry_verified": True},
        "source": {"manager_root": "/usr/local/lib/llm-server/control-api",
                   "closure_sha256": "f" * 64, "lease_semantics": "same_process_capability"},
        "credentials": {role: {"uid": 0, "gid": 0, "mode": 0o600, "dev": 1, "ino": ino,
                      "size": 64, "mtime_ns": 42, "ctime_ns": 43}
                      for role, ino in (("inference", 100), ("control", 101))}}


def checks(running=True):
    return {"credentials_private_equality": True, "no_benchmark_processes": True,
            "no_benchmark_containers": True, "no_benchmark_listeners": True,
            "lease_inode_unchanged": True, "worker_lan_control_authenticated": True,
            "worker_lan_inference_authenticated": True if running else "NOT_APPLICABLE_STOPPED_INTENT"}


class LifecyclePlanTests(unittest.TestCase):
    def test_preserves_both_original_models_and_boot_preference(self):
        for selected in DEPLOYMENTS:
            for policy in ("manual", "resume"):
                original = snapshot(selected)
                original["manager"]["boot_policy"] = policy
                plan = plan_campaign(original, "prep-20260919")
                restore = [step for step in plan["restoration"] if step.get("call") == "manager.dispatch"]
                self.assertEqual([step["action"] for step in restore], ["select", "start"])
                self.assertEqual(restore[0]["kwargs"], {"deployment_id": selected, "boot_policy": policy})
                self.assertTrue(all(step["lease_argument"] == "campaign_lease" for step in restore))
                self.assertTrue(plan["dry_run"])
                self.assertFalse(plan["execution_implemented"])

    def test_stopped_intent_never_started(self):
        for selected in list(DEPLOYMENTS) + [None]:
            plan = plan_campaign(snapshot(selected, False), "prep")
            actions = [step["action"] for step in plan["restoration"] if step.get("call") == "manager.dispatch"]
            self.assertEqual(actions, ["select"] if selected else ["deactivate"])

    def test_boot_service_never_stopped_masked_restarted_or_enabled(self):
        plan = plan_campaign(snapshot(), "prep")
        commands = [step["argv"] for phase in ("maintenance", "restoration") for step in plan[phase] if "argv" in step]
        self.assertEqual(commands, [["/usr/bin/systemctl", "stop", CONTROL_UNIT],
                                    ["/usr/bin/systemctl", "start", CONTROL_UNIT]])
        self.assertNotIn(BOOT_UNIT, [part for command in commands for part in command])
        self.assertEqual(plan["maintenance"][0]["lock"], CANONICAL_LOCK)

    def test_control_freezes_after_lock_and_restarts_after_release(self):
        plan = plan_campaign(snapshot(), "prep")
        self.assertEqual(plan["maintenance"][0]["call"], "common.lifecycle_lease.acquire_lease")
        release = next(i for i, step in enumerate(plan["restoration"]) if step.get("call") == "campaign_lease context exit")
        start = next(i for i, step in enumerate(plan["restoration"]) if step.get("argv") == ["/usr/bin/systemctl", "start", CONTROL_UNIT])
        self.assertGreater(start, release)

    def test_preserves_inactive_control(self):
        original = snapshot()
        original["services"][CONTROL_UNIT].update(active="inactive", substate="dead", enabled="disabled")
        plan = plan_campaign(original, "prep")
        self.assertFalse(any("argv" in step for phase in ("maintenance", "restoration") for step in plan[phase]))

    def test_maintenance_stop_preserves_intent(self):
        plan = plan_campaign(snapshot(), "prep")
        actions = [step for step in plan["maintenance"] if step.get("call") == "manager.dispatch"]
        self.assertEqual(actions, [{"kind": "same_process_call", "call": "manager.dispatch",
                                  "action": "boot-stop", "kwargs": {}, "lease_argument": "campaign_lease"}])

    def test_baseline_and_synthetic_cannot_authorize_run(self):
        for original in (snapshot(), {**snapshot(), "evidence_kind": "live_readonly"}):
            with self.assertRaisesRegex(PlanError, "fresh_campaign_owned_snapshot_required"):
                validate_snapshot(original, for_run=True)
        live = snapshot()
        live["evidence_kind"] = "live_readonly"
        live["lease"].update(held=True, owned_by_campaign=True)
        self.assertEqual(validate_snapshot(live, for_run=True), live)

    def test_ambiguity_fails_closed(self):
        changes = [
            ("manager", "desired", "unknown"), ("manager", "selected", "historical-model"),
            ("manager", "state_persisted", False), ("manager", "recovery_pending", True),
            ("manager", "observed", "starting"), ("manager", "container_running", False),
            ("manager", "boot_policy", "default"), ("control", "fresh", False),
            ("control", "operation", {"status": "running"}), ("lease", "held", True),
            ("lease", "path", "/run/benchmark.lock"), ("guards", "storage_passed", False),
            ("guards", "root_disk_passed", False), ("guards", "sha256", "unknown"),
            ("storage", "protected_ancestry_verified", False),
            ("source", "lease_semantics", "LLMCTL_LEASE_FD"),
        ]
        for group, key, value in changes:
            with self.subTest(group=group, key=key):
                original = snapshot()
                original[group][key] = value
                with self.assertRaises(PlanError):
                    plan_campaign(original, "prep")

    def test_pending_jobs_and_preexisting_masks_rejected(self):
        original = snapshot()
        original["pending_systemd_jobs"] = [{"unit": BOOT_UNIT, "type": "stop"}]
        with self.assertRaisesRegex(PlanError, "pending_service_job"):
            plan_campaign(original, "prep")
        original = snapshot()
        original["services"][CONTROL_UNIT]["masked"] = True
        with self.assertRaisesRegex(PlanError, "preexisting_service_mask"):
            plan_campaign(original, "prep")

    def test_secret_content_fields_rejected(self):
        original = snapshot()
        original["credentials"]["inference"]["value"] = "synthetic-secret-not-real"
        with self.assertRaisesRegex(PlanError, "unsafe_credential_identity"):
            plan_campaign(original, "prep")

    def test_campaign_path_and_old_guard_rejected(self):
        for invalid in ("../prep", "prep;echo", "PREP", "", None):
            with self.assertRaises(PlanError):
                plan_campaign(snapshot(), invalid)
        original = snapshot()
        original["guards"]["installed_path"] = "/data/old-checkout/scripts/common/registered-storage.py"
        with self.assertRaisesRegex(PlanError, "invalid_protected_path"):
            plan_campaign(original, "prep")

    def test_restoration_accepts_original_identity_but_new_container(self):
        original = snapshot()
        self.assertEqual(validate_restored(original, copy.deepcopy(original), checks())["original_selected"],
                         original["manager"]["selected"])
        self.assertEqual(validate_restored(snapshot(None, False), snapshot(None, False), checks(False))["original_desired"], "stopped")

    def test_restoration_requires_each_independent_verification(self):
        for key in checks():
            evidence = checks()
            evidence[key] = False
            with self.subTest(key=key), self.assertRaises(PlanError):
                validate_restored(snapshot(), snapshot(), evidence)

    def test_restoration_rejects_model_and_preserved_state_drift(self):
        for group, key, value in (("manager", "selected", "glm-5.3-ud-q4-k-xl-n76-native1m"),
                                  ("manager", "boot_policy", "manual"),
                                  ("storage", "identity_sha256", "a" * 64),
                                  ("guards", "sha256", "b" * 64)):
            after = snapshot()
            after[group][key] = value
            with self.assertRaises(PlanError):
                validate_restored(snapshot(), after, checks())
        after = snapshot()
        after["credentials"]["inference"]["mtime_ns"] += 1
        with self.assertRaises(PlanError):
            validate_restored(snapshot(), after, checks())

    def test_cleanup_uses_exact_ids_and_identity_preconditions(self):
        resource = {"id": "1" * 64, "name": "prep-g1", "campaign_label": "prep",
                    "owner_label": "llm-benchmark", "image_id": "sha256:" + "2" * 64, "restart_policy": "no"}
        commands = cleanup_commands("prep", [resource])
        self.assertEqual(commands[0]["argv"], ["/usr/bin/docker", "stop", "--time", "120", "1" * 64])
        self.assertEqual(commands[1]["argv"], ["/usr/bin/docker", "rm", "1" * 64])
        self.assertTrue(commands[1]["require_stopped"])
        self.assertEqual(commands[0]["require_identity"], resource)
        for key, value in (("name", "production"), ("campaign_label", "foreign"),
                           ("owner_label", "production"), ("restart_policy", "always"), ("id", "short-id")):
            malformed = {**resource, key: value}
            with self.subTest(key=key), self.assertRaises(PlanError):
                cleanup_commands("prep", [malformed])
        with self.assertRaises(PlanError):
            cleanup_commands("prep", [resource, resource])

    def test_manifest_roundtrip_and_no_input_mutation(self):
        original = snapshot()
        saved = copy.deepcopy(original)
        plan = plan_campaign(original, "prep")
        self.assertEqual(json.loads(json.dumps(plan)), plan)
        self.assertEqual(original, saved)
        self.assertEqual(plan["budget"]["seconds"], 21600)
        self.assertTrue(plan["budget"]["restoration_excluded"])


if __name__ == "__main__":
    unittest.main()
