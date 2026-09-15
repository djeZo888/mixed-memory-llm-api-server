"""Worker-only pre-stop image preflight, using real Manager validation.

Docker metadata, storage, artifact admission and the key metadata check are
explicit fixtures. The canonical borrowed lease and Manager's image evidence,
create_args, prepare_start and stop/start transitions execute their real source.
No container, model, key or live runtime is used.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from common import lifecycle_lease as lease_module  # noqa: E402
from common.lifecycle_lease import acquire_lease  # noqa: E402
from lifecycle import manager as manager_module  # noqa: E402
from lifecycle.manager import Manager, legacy_profile  # noqa: E402
from lifecycle.runtime_io import LifecycleError  # noqa: E402
from tests.lifecycle.test_manager import (  # noqa: E402
    FakeClock, FakeDocker, FixtureManager, IMAGE, MEASURE, PROOF, make_instance,
)


class EvidenceFixtureManager(FixtureManager):
    # Keep the real saved-evidence checks as well as the current image checks.
    def image_evidence(self, deployment):
        return Manager.image_evidence(self, deployment)


class ImageMetadataDocker(FakeDocker):
    def __init__(self):
        super().__init__()
        self.fault = None
        self.fail_from_inspection = 1
        self.image_inspections = 0
        self.owner_check = lambda: None

    def _event(self, event):
        self.owner_check()
        return super()._event(event)

    def run(self, args, timeout=30):
        if args[:2] != ["image", "inspect"]:
            return super().run(args, timeout=timeout)
        self.image_inspections += 1
        self._event(("image_inspect", args[2], self.image_inspections))
        fault = self.fault if self.image_inspections >= self.fail_from_inspection else None
        if fault == "missing":
            # Real Docker.capture propagates this sanitized nonzero-CLI error.
            raise LifecycleError("command_failed")
        image_id = "sha256:" + "c" * 64 if fault == "id" else IMAGE
        entrypoint = ["/unexpected-entrypoint"] if fault == "entrypoint" else ["/opt/llama/llama-server"]
        return json.dumps([{"Id": image_id, "Config": {"Entrypoint": entrypoint}}])


class StartPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="l1b-preflight-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.lease_arguments = {"system_root": self.root, "trusted_uid": os.geteuid()}
        instance = make_instance(self.root)
        for evidence in instance["runtime_evidence"].values():
            evidence["image_id"] = IMAGE
        self.docker = ImageMetadataDocker()
        clock = FakeClock()
        self.manager = EvidenceFixtureManager(
            ROOT / "configs", instance, docker=self.docker, test_paths=True,
            probe_fn=lambda *args, **kwargs: "ready",
            sleep_fn=clock.sleep, monotonic_fn=clock.monotonic,
        )
        key_check = patch.object(manager_module, "validate_key_metadata", return_value=None)
        key_check.start()
        self.addCleanup(key_check.stop)
        with self.borrowed_owner() as lease:
            self.manager.dispatch("select", PROOF, lease=lease)
            initial = self.manager.dispatch("start", lease=lease)
            self.assertEqual(initial["observed"], "ready")
        self.old_id = initial["container"]["id"]
        self.before = copy.deepcopy(initial)
        self.docker.calls.clear()
        self.docker.image_inspections = 0
        self.phases = []

    @contextmanager
    def borrowed_owner(self):
        with acquire_lease(**self.lease_arguments) as lease:
            self.docker.owner_check = lease.validate
            try:
                with patch.object(manager_module, "acquire_lease", side_effect=AssertionError("reacquired borrowed owner")), \
                        patch.object(lease_module.fcntl, "flock", side_effect=AssertionError("relocked borrowed owner")):
                    yield lease
                    lease.validate()
            finally:
                self.docker.owner_check = lambda: None

    def preflight_then_stop(self, lease):
        # This is the narrow consumer contract for U1B, not its switch engine.
        lease.validate()
        target = self.manager.deployment(MEASURE)
        self.phases.append("target_loaded")
        self.manager.prepare_start(target)
        self.phases.append("preflight_passed")
        self.manager.dispatch("stop", lease=lease)
        self.phases.append("old_stopped")

    def image_calls(self):
        return [event for event in self.docker.calls if event[0] == "image_inspect"]

    def stop_calls(self):
        return [event for event in self.docker.calls if event[0] == "stop"]

    def assert_preflight_refuses(self, fault, code):
        self.docker.fault = fault
        with self.borrowed_owner() as lease:
            with self.assertRaisesRegex(LifecycleError, "^" + code + "$"), \
                    patch.object(self.manager, "create_args", wraps=self.manager.create_args) as arguments:
                self.preflight_then_stop(lease)
            arguments.assert_called_once()
            lease.validate()
        self.assertEqual(self.phases, ["target_loaded"])
        self.assertEqual(len(self.image_calls()), 1, "must reach actual current image inspection")
        target = self.manager.deployment(MEASURE)
        self.assertEqual(self.image_calls()[0][1], target["_runtime"]["image_tag"])
        self.assertEqual(self.stop_calls(), [])
        self.assertFalse(any(event[0] in {"create", "start_enter", "remove"} for event in self.docker.calls))
        self.assertEqual(self.manager.read_state(), self.before)
        old = next(record for record in self.docker.records if record["Id"] == self.old_id)
        self.assertTrue(old["State"]["Running"])

    def test_missing_image_refuses_before_old_stop(self):
        self.assert_preflight_refuses("missing", "command_failed")

    def test_retagged_image_refuses_before_old_stop(self):
        self.assert_preflight_refuses("id", "runtime_image_id_mismatch")

    def test_wrong_entrypoint_refuses_before_old_stop(self):
        self.assert_preflight_refuses("entrypoint", "runtime_entrypoint_mismatch")

    def test_usable_image_reaches_stop_and_start_revalidates_under_same_owner(self):
        with self.borrowed_owner() as lease, \
                patch.object(self.manager, "create_args", wraps=self.manager.create_args) as arguments:
            self.preflight_then_stop(lease)
            self.manager.dispatch("select", MEASURE, lease=lease)
            result = self.manager.dispatch("start", lease=lease)
            self.assertEqual(arguments.call_count, 3, "pre-stop, start preflight, and pre-create validation")
        self.assertEqual(self.phases, ["target_loaded", "preflight_passed", "old_stopped"])
        self.assertEqual(self.stop_calls(), [("stop", self.old_id)])
        self.assertEqual(len(self.image_calls()), 3)
        self.assertEqual(result["observed"], "ready")
        self.assertEqual(result["selected"], MEASURE)
        first_image = next(i for i, event in enumerate(self.docker.calls) if event[0] == "image_inspect")
        old_stop = next(i for i, event in enumerate(self.docker.calls) if event[0] == "stop")
        create = next(i for i, event in enumerate(self.docker.calls) if event[0] == "create")
        last_image = max(i for i, event in enumerate(self.docker.calls) if event[0] == "image_inspect")
        self.assertLess(first_image, old_stop)
        self.assertLess(last_image, create)
        self.assertEqual(sum(record["State"]["Running"] for record in self.docker.records), 1)

    def test_image_drift_after_start_preflight_is_rechecked_before_create(self):
        self.docker.fault = "id"
        self.docker.fail_from_inspection = 3
        with self.borrowed_owner() as lease:
            self.preflight_then_stop(lease)
            self.manager.dispatch("select", MEASURE, lease=lease)
            with self.assertRaisesRegex(LifecycleError, "^runtime_image_id_mismatch$"):
                self.manager.dispatch("start", lease=lease)
        self.assertEqual(self.phases, ["target_loaded", "preflight_passed", "old_stopped"])
        self.assertEqual(len(self.image_calls()), 3)
        self.assertEqual(self.stop_calls(), [("stop", self.old_id)])
        self.assertFalse(any(event[0] in {"create", "start_enter", "remove"} for event in self.docker.calls))
        self.assertEqual(self.manager.read_state()["observed"], "failed")

    def test_legacy_preflight_preserves_existing_compose_contract(self):
        with self.borrowed_owner(), \
                patch.object(self.manager, "create_args", side_effect=AssertionError("legacy is not a create_args profile")):
            self.manager.prepare_start(legacy_profile("qwen3-0.6b-smoke"))
        self.assertEqual(self.image_calls(), [])
        self.assertEqual(self.stop_calls(), [])


if __name__ == "__main__":
    unittest.main()
