"""Synthetic owner callbacks with a real canonical lease in a local fixture root."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common.lifecycle_lease import acquire_lease, transition_in_progress
from benchmark.lifecycle import BOOT_UNIT, CONTROL_UNIT, digest
from benchmark.owner import CampaignOwner, HostCallbacks, OwnerError, WorkerVerificationPending
from tests.test_benchmark_lifecycle import snapshot, checks


class Budget:
    def __init__(self, events):
        self.events, self.phase = events, "NEW"

    def start(self, kind):
        self.phase = "MEASURING"
        self.events.append(("budget_start", kind))

    def checkpoint(self):
        return 21600

    def begin_restoration(self):
        self.phase = "RESTORING"
        self.events.append(("budget_restore",))

    def finish_restoration(self, verified):
        self.phase = "RESTORED"
        self.events.append(("budget_finish", verified))


class Fixture:
    def __init__(self, root, original=None):
        self.root, self.state = root, original or snapshot()
        self.events, self.writes, self.containers = [], [], {}
        self.lease, self.requests_active = None, False
        self.fail_create, self.fail_start, self.fail_write = False, False, False
        self.drift_image, self.owner = False, None
        self.manifest = {"campaign": "benchrun-offline", "container_name": "benchrun-offline-g1-4096",
                         "image": "sha256:" + "2" * 64, "expected_image_ids": ["sha256:" + "2" * 64],
                         "create_argv": ["docker", "create", "offline-only-never-executed"]}

    @contextmanager
    def lease_factory(self, *, blocking):
        assert blocking is False
        with acquire_lease(blocking=False, system_root=self.root, trusted_uid=os.geteuid()) as lease:
            self.lease = lease
            self.events.append(("acquire",))
            yield lease
        self.events.append(("release",))

    def capture(self, lease):
        value = copy.deepcopy(self.state)
        value["lease"].update(held=lease is not None, owned_by_campaign=lease is not None)
        if lease is not None:
            self.assert_lease(lease)
        return value

    def assert_lease(self, lease):
        assert lease is self.lease
        lease.validate()
        assert transition_in_progress(system_root=self.root, trusted_uid=os.geteuid())

    def guards(self, lease):
        if lease is not None:
            self.assert_lease(lease)
        self.events.append(("guard", lease is not None))

    def gate(self, stage, lease, original, resources):
        self.assert_lease(lease)
        self.events.append(("gate", stage))
        if stage in {"restore", "retire", "stop", "remove"} and self.requests_active:
            raise ValueError("synthetic_inference_active")
        if stage not in {"admission", "freeze_control"}:
            assert self.state["services"][CONTROL_UNIT]["active"] == "inactive"
        assert self.state["services"][BOOT_UNIT] == original["services"][BOOT_UNIT]

    def control(self, action):
        self.events.append(("control", action))
        if action == "stop":
            self.assert_lease(self.owner.lease)
        else:
            assert not transition_in_progress(system_root=self.root, trusted_uid=os.geteuid())
        self.state["services"][CONTROL_UNIT].update(active="active" if action == "start" else "inactive",
                                                   substate="running" if action == "start" else "dead")

    def dispatch(self, action, *, lease, **kwargs):
        self.assert_lease(lease)
        self.events.append(("manager", action, copy.deepcopy(kwargs)))
        s = self.state["manager"]
        if action == "boot-stop":
            s.update(observed="stopped", container_running=False)
        elif action == "select":
            s.update(selected=kwargs["deployment_id"], boot_policy=kwargs["boot_policy"], desired="stopped")
        elif action == "start":
            s.update(desired="running", observed="ready", container_running=True)
        elif action == "deactivate":
            s.update(selected=None, boot_policy="manual", desired="stopped", observed="stopped", container_running=False)

    def create(self, manifest):
        self.events.append(("create", manifest["container_name"]))
        assert self.writes[-1]["pending_create"]["name"] == manifest["container_name"]
        if self.fail_create:
            raise ValueError("synthetic_create_uncertain")
        cid = str(len(self.containers) + 1) * 64
        r = {"id": cid, "name": manifest["container_name"], "image_id": manifest["expected_image_ids"][0],
             "campaign_label": manifest["campaign"], "owner_label": "llm-benchmark", "restart_policy": "no", "running": False}
        self.containers[cid] = r
        return copy.deepcopy(r)

    def inspect(self, resource):
        result = copy.deepcopy(self.containers.get(resource["id"]))
        if result and self.drift_image:
            result["image_id"] = "sha256:" + "9" * 64
        return result

    def start(self, resource):
        assert self.writes[-1]["resources"][-1]["resource"]["id"] == resource["id"]
        self.events.append(("start", resource["id"]))
        if self.fail_start:
            raise ValueError("synthetic_start_failure")
        self.containers[resource["id"]]["running"] = True

    def stop(self, resource):
        assert not self.requests_active
        self.events.append(("stop", resource["id"]))
        self.containers[resource["id"]]["running"] = False

    def remove(self, resource):
        assert not self.containers[resource["id"]]["running"]
        self.events.append(("remove", resource["id"]))
        self.containers.pop(resource["id"])

    def write(self, ledger):
        if self.fail_write:
            raise ValueError("synthetic_writer_error")
        self.writes.append(copy.deepcopy(ledger))
        self.events.append(("write", ledger["phase"]))

    def checks(self, original, after):
        result = checks(original["manager"]["desired"] == "running")
        if original["services"][CONTROL_UNIT]["active"] == "inactive":
            result["worker_lan_control_authenticated"] = "NOT_APPLICABLE_CONTROL_INACTIVE"
        return result

    def build(self):
        host = HostCallbacks(**{name: getattr(self, name) for name in HostCallbacks.__dataclass_fields__})
        self.owner = CampaignOwner("benchrun-offline", self, host, Budget(self.events),
                reviewed_manifest_hashes=[digest(self.manifest)], lease_factory=self.lease_factory, synthetic_offline=True)
        return self.owner


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="benchmark-owner-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name).resolve())
        self.owner = self.fixture.build()
        self.addCleanup(self.release_fixture_lease)

    def release_fixture_lease(self):
        # Fixture-only cleanup after an asserted blocked-recovery state, never a
        # production recovery recommendation. No Docker/host callbacks exist.
        if self.owner.lease_context is not None:
            self.owner.lease_context.__exit__(None, None, None)
            self.owner.lease_context = self.owner.lease = None

    def test_exact_same_lease_and_order_and_durable_id_before_start(self):
        self.owner.begin()
        resource = self.owner.launch(self.fixture.manifest)
        result = self.owner.restore()
        self.assertTrue(result["restored"])
        self.assertEqual(self.owner.phase, "RESTORED")
        actions = [e[0:2] for e in self.fixture.events if e[0] in {"acquire", "control", "manager", "create", "start", "stop", "remove", "release", "budget_start", "budget_restore", "budget_finish"}]
        self.assertEqual(actions, [("acquire",), ("budget_start", "maintenance"), ("control", "stop"),
            ("manager", "boot-stop"), ("create", "benchrun-offline-g1-4096"), ("start", resource["id"]),
            ("budget_restore",), ("stop", resource["id"]), ("remove", resource["id"]),
            ("manager", "boot-stop"), ("manager", "select"), ("manager", "start"),
            ("release",), ("control", "start"), ("budget_finish", True)])
        self.assertEqual(self.fixture.containers, {})

    def test_worker_verification_pending_releases_without_false_restored_claim(self):
        def pending(original, after):
            raise WorkerVerificationPending()
        self.owner.host = replace(self.owner.host, checks=pending)
        self.owner.begin()
        result = self.owner.restore()
        self.assertFalse(result["restored"])
        self.assertEqual(result["local_restoration"], "VERIFIED")
        self.assertEqual(self.owner.phase, "POST_RELEASE_LAN_VERIFICATION_PENDING")
        self.assertIsNone(self.owner.lease)
        self.assertFalse(any(event[0] == "budget_finish" for event in self.fixture.events))

    def test_original_glm_restored_not_qwen_default(self):
        self.fixture.state = snapshot("glm-5.3-ud-q4-k-xl-n76-native1m")
        self.fixture.state["manager"]["boot_policy"] = "manual"
        self.owner.begin()
        self.owner.restore()
        select = [e for e in self.fixture.events if e[:2] == ("manager", "select")][0]
        self.assertEqual(select[2], {"deployment_id": "glm-5.3-ud-q4-k-xl-n76-native1m", "boot_policy": "manual"})

    def test_stopped_original_never_started(self):
        self.fixture.state = snapshot(None, False)
        self.owner.begin()
        self.owner.restore()
        self.assertFalse(any(e[:2] == ("manager", "start") for e in self.fixture.events))
        self.assertIn(("manager", "deactivate", {}), self.fixture.events)

    def test_inactive_control_preserved(self):
        self.fixture.state["services"][CONTROL_UNIT].update(active="inactive", substate="dead", enabled="disabled")
        self.owner.begin()
        self.owner.restore()
        self.assertFalse(any(e[0] == "control" for e in self.fixture.events))

    def test_report_error_does_not_stop_or_release_healthy_inference(self):
        self.owner.begin()
        self.owner.launch(self.fixture.manifest)
        self.fixture.requests_active = True
        previous = len(self.fixture.events)
        result = self.owner.record_harness_failure()
        self.assertFalse(result["healthy_inference_cancelled"])
        self.assertFalse(any(e[0] in {"stop", "remove", "release", "manager"} for e in self.fixture.events[previous:]))
        self.owner.lease.validate()
        self.fixture.requests_active = False
        self.owner.restore()

    def test_restore_refuses_active_request_and_retains_lease(self):
        self.owner.begin()
        self.owner.launch(self.fixture.manifest)
        self.fixture.requests_active = True
        with self.assertRaises(OwnerError):
            self.owner.restore()
        self.assertEqual(self.owner.phase, "RECOVERY_REQUIRED")
        self.owner.lease.validate()
        self.assertTrue(next(iter(self.fixture.containers.values()))["running"])
        self.fixture.requests_active = False
        self.owner.restore()

    def test_start_failure_restores_and_removes_only_owned_container(self):
        self.owner.begin()
        self.fixture.fail_start = True
        with self.assertRaises(OwnerError):
            self.owner.launch(self.fixture.manifest)
        self.assertEqual(self.owner.phase, "RESTORED")
        self.assertFalse(self.fixture.containers)
        self.assertEqual(len([e for e in self.fixture.events if e[0] == "create"]), 1)

    def test_ambiguous_create_retains_intent_lease_and_control_freeze(self):
        self.owner.begin()
        self.fixture.fail_create = True
        with self.assertRaises(OwnerError):
            self.owner.launch(self.fixture.manifest)
        self.assertEqual(self.owner.phase, "RECOVERY_REQUIRED")
        self.assertEqual(self.owner.pending_create["name"], self.fixture.manifest["container_name"])
        self.owner.lease.validate()
        self.assertEqual(self.fixture.state["services"][CONTROL_UNIT]["active"], "inactive")
        self.assertEqual(len([e for e in self.fixture.events if e[0] == "create"]), 1)

    def test_resource_identity_drift_never_stopped_or_removed(self):
        self.owner.begin()
        resource = self.owner.launch(self.fixture.manifest)
        self.fixture.drift_image = True
        with self.assertRaises(OwnerError):
            self.owner.retire(resource["id"])
        self.assertFalse(any(e[0] in {"stop", "remove"} for e in self.fixture.events))
        self.owner.lease.validate()
        self.fixture.drift_image = False
        self.owner.restore()

    def test_unreviewed_manifest_never_created(self):
        self.owner.begin()
        changed = {**self.fixture.manifest, "create_argv": ["unsafe"]}
        with self.assertRaises(ValueError):
            self.owner.launch(changed)
        self.assertFalse(any(e[0] == "create" for e in self.fixture.events))
        self.owner.restore()

    def test_live_mode_refuses_synthetic_snapshot_before_mutation(self):
        self.owner.synthetic = False
        with self.assertRaises(OwnerError):
            self.owner.begin()
        self.assertFalse(any(e[0] in {"manager", "control", "create"} for e in self.fixture.events))
        self.assertIsNone(self.owner.lease)

    def test_report_persistence_error_still_does_not_stop(self):
        self.owner.begin()
        self.owner.launch(self.fixture.manifest)
        self.fixture.fail_write = True
        self.owner.record_harness_failure()
        self.assertIn("evidence_write_failed", self.owner.errors)
        self.assertFalse(any(e[0] == "stop" for e in self.fixture.events))
        self.fixture.fail_write = False
        self.owner.restore()


if __name__ == "__main__":
    unittest.main()
