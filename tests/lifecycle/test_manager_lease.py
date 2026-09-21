"""Manager borrows a real canonical worker lease; Docker/storage remain fixtures."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import copy
import io
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from common import lifecycle_lease as lease_module  # noqa: E402
from common.lifecycle_lease import LifecycleLease, LeaseError, acquire_lease, transition_in_progress  # noqa: E402
from lifecycle import manager as manager_module  # noqa: E402
from lifecycle.manager import Manager, OWNER, LABEL, atomic_json, empty_state, legacy_profile  # noqa: E402
from lifecycle.runtime_io import LifecycleError  # noqa: E402
from lifecycle.storage_binding import BindingError  # noqa: E402
from tests.lifecycle.storage_fixtures import RegisteredFixture  # noqa: E402
from tests.lifecycle.test_lease import _compete  # noqa: E402
from tests.lifecycle.test_manager import FakeDocker, FixtureManager, IMAGE, PROOF, make_instance  # noqa: E402


class ManagerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="manager-lease-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.arguments = {"system_root": self.root, "trusted_uid": os.geteuid()}
        self.instance = make_instance(self.root)
        self.docker = FakeDocker()
        self.manager = FixtureManager(ROOT / "configs", self.instance, docker=self.docker, test_paths=True)

    def observe(self):
        return transition_in_progress(**self.arguments)

    def test_borrowed_dispatch_never_reacquires_and_leaves_owner_active(self):
        with acquire_lease(**self.arguments) as lease:
            owner_fd = lease_module._active[lease].fd
            with patch.object(manager_module, "acquire_lease", side_effect=AssertionError("recursive acquisition")), \
                    patch.object(lease_module.fcntl, "flock", side_effect=AssertionError("recursive flock")):
                result = self.manager.dispatch("stop", lease=lease)
            self.assertEqual(result["desired"], "stopped")
            lease.validate()
            os.fstat(owner_fd)
            self.assertTrue(self.observe())
        self.assertFalse(self.observe())

    def test_competitor_stays_blocked_across_borrow_success_and_error(self):
        context = multiprocessing.get_context("spawn")
        attempted, acquired, results = context.Event(), context.Event(), context.Queue()
        process = context.Process(target=_compete, args=(str(self.root), os.geteuid(), attempted, acquired, results))
        try:
            with acquire_lease(**self.arguments) as lease:
                process.start()
                self.assertTrue(attempted.wait(10))
                self.assertFalse(acquired.wait(0.1))
                with patch.object(manager_module, "acquire_lease", side_effect=AssertionError("recursive acquisition")), \
                        patch.object(lease_module.fcntl, "flock", side_effect=AssertionError("recursive flock")):
                    self.manager.dispatch("stop", lease=lease)
                    with self.assertRaises(LifecycleError):
                        self.manager.dispatch("start", lease=lease)
                lease.validate()
                self.assertFalse(acquired.is_set(), "borrow or error released installer ownership")
                self.assertTrue(self.observe())
            self.assertTrue(acquired.wait(10))
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(results.get(timeout=2), "ok")
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            results.close()
            results.join_thread()

    def assert_rejected_before_admission_or_state(self, lease):
        with patch.object(self.manager, "read_state", side_effect=AssertionError("state before validation")), \
                patch.object(self.manager, "check_package_admission", side_effect=AssertionError("admission before validation")):
            with self.assertRaises((LeaseError, LifecycleError)):
                self.manager.dispatch("stop", lease=lease)
        self.assertEqual(self.docker.calls, [])

    def test_raw_fake_subclass_and_fabricated_borrowed_lease_rejected(self):
        class FakeLease:
            def validate(self):
                return None

        class SubclassLease(LifecycleLease):
            def validate(self):
                return None

        with acquire_lease(**self.arguments) as lease:
            for invalid in (lease_module._active[lease].fd, FakeLease(),
                            object.__new__(SubclassLease), object.__new__(LifecycleLease)):
                with self.subTest(kind=type(invalid).__name__):
                    self.assert_rejected_before_admission_or_state(invalid)
            lease.validate()

    def test_stale_closed_and_replaced_borrow_rejected_before_state(self):
        with acquire_lease(**self.arguments) as lease:
            pass
        self.assert_rejected_before_admission_or_state(lease)
        with acquire_lease(**self.arguments) as lease:
            os.close(lease_module._active[lease].fd)
            self.assert_rejected_before_admission_or_state(lease)
        with acquire_lease(**self.arguments) as lease:
            self.manager.lock_file.rename(self.manager.lock_file.with_suffix(".old"))
            self.manager.lock_file.touch(mode=0o600)
            self.assert_rejected_before_admission_or_state(lease)

    def test_valid_minted_lease_from_other_root_cannot_authorize_manager(self):
        other = self.root / "other"
        other.mkdir(mode=0o700)
        with acquire_lease(system_root=other, trusted_uid=os.geteuid()) as lease:
            self.assert_rejected_before_admission_or_state(lease)
            lease.validate()
        self.assertFalse(self.manager.lock_file.exists())

    def test_standalone_dispatch_acquires_before_state_and_releases_on_error(self):
        original = self.manager.read_state
        reads = []

        def checked_read(*args, **kwargs):
            self.assertTrue(self.observe(), "state read outside canonical lock")
            reads.append(True)
            return original(*args, **kwargs)

        with patch.object(self.manager, "read_state", side_effect=checked_read):
            with self.assertRaises(LifecycleError):
                self.manager.dispatch("start")
        self.assertTrue(reads)
        self.assertFalse(self.observe())

    def test_standalone_cli_acquires_same_context_before_instance_load(self):
        acquired = []

        @contextmanager
        def cli_acquisition():
            with acquire_lease(**self.arguments) as lease:
                acquired.append(lease)
                yield lease

        def loaded(args, config):
            self.assertTrue(self.observe(), "instance loaded before canonical acquisition")
            acquired[0].validate()
            return self.manager

        args = argparse.Namespace(command="stop", yes=True, dry_run=False, instance=None, no_wait=False)
        with patch.object(manager_module, "acquire_lease", side_effect=cli_acquisition), \
                patch.object(manager_module, "load_manager", side_effect=loaded), \
                patch.object(manager_module.signal, "signal"), redirect_stdout(io.StringIO()):
            self.assertEqual(manager_module.cli(args), 0)
        self.assertEqual(len(acquired), 1)
        self.assertFalse(self.observe())
        with self.assertRaises(LeaseError):
            acquired[0].validate()

    def test_nonmutating_status_remains_responsive_under_owner_lease(self):
        with acquire_lease(**self.arguments):
            with patch.object(manager_module, "acquire_lease", side_effect=AssertionError("status waited for lock")):
                status = self.manager.dispatch("status")
            self.assertEqual(status["desired"], "stopped")
            self.assertTrue(self.observe())

    def test_recovery_only_stops_exact_owned_container_without_registry_or_config(self):
        identity = {"id": "c" * 64, "image_id": IMAGE, "name": "fixture-running",
                    "owner": OWNER, "instance": self.instance["id"], "deployment": PROOF, "legacy": False}
        self.docker.records = [{"Id": identity["id"], "Image": IMAGE, "Name": "/fixture-running",
                                "State": {"Running": True, "Status": "running"},
                                "NetworkSettings": {"Ports": {}},
                                "Config": {"Labels": {LABEL + key: identity[key]
                                                       for key in ("owner", "instance", "deployment")}}}]
        manager = Manager(self.root / "absent-config", {"schema_version": 1, "id": self.instance["id"]},
                          docker=self.docker, recovery_only=True, test_paths=True, lease_system_root=self.root)
        state = {**empty_state(), "selected": PROOF, "desired": "running", "observed": "ready",
                 "container_running": True, "container": identity}
        with acquire_lease(**self.arguments) as lease:
            atomic_json(manager.recovery_file, state, **self.arguments)
            with patch.object(manager, "deployment", side_effect=AssertionError("recovery read deployment")), \
                    patch.object(manager_module, "validate_key_metadata", side_effect=AssertionError("recovery read key")):
                stopped = manager.dispatch("stop", lease=lease)
            lease.validate()
            self.assertTrue(self.observe())
        self.assertFalse(stopped["state_persisted"])
        self.assertFalse(stopped["container_running"])
        self.assertEqual(stopped["desired"], "stopped")
        self.assertEqual([call for call in self.docker.calls if call[0] == "stop"], [("stop", identity["id"])])
        self.assertFalse((self.root / "state").exists())
        self.assertFalse((self.root / "absent-config").exists())

    def test_falsy_malformed_primary_identity_recovers_without_erasing_owned_journal(self):
        identity = {"id": "d" * 64, "image_id": IMAGE, "name": "fixture-owned",
                    "owner": OWNER, "instance": self.instance["id"], "deployment": PROOF, "legacy": False}
        record = {"Id": identity["id"], "Image": IMAGE, "Name": "/fixture-owned",
                  "State": {"Running": True, "Status": "running"}, "NetworkSettings": {"Ports": {}},
                  "Config": {"Labels": {LABEL + key: identity[key] for key in ("owner", "instance", "deployment")}}}
        mutations = [("container", invalid) for invalid in ({}, [], 0, False, "")]
        mutations.extend((("missing_container", None), ("desired", [])))
        for field, invalid in mutations:
            with self.subTest(field=field, kind=type(invalid).__name__):
                self.docker.records = [copy.deepcopy(record)]
                self.docker.calls.clear()
                self.manager.state = {**empty_state(), "selected": PROOF, "desired": "running", "observed": "ready",
                                      "container_running": True, "container": copy.deepcopy(identity)}
                with acquire_lease(**self.arguments):
                    self.manager.save()
                primary = json.loads(self.manager.state_file.read_text())
                if field == "missing_container":
                    primary.pop("container")
                else:
                    primary[field] = invalid
                self.manager.state_file.write_text(json.dumps(primary))
                result = self.manager.dispatch("stop")
                self.assertFalse(self.docker.records[0]["State"]["Running"])
                self.assertEqual([call for call in self.docker.calls if call[0] == "stop"], [("stop", identity["id"])])
                self.assertEqual(result["container"], identity)
                self.assertEqual(json.loads(self.manager.recovery_file.read_text())["container"], identity)

    def test_malformed_instance_paths_still_reach_trusted_recovery_cli(self):
        fixture = RegisteredFixture()
        self.addCleanup(fixture.close)
        binding = fixture.binding()
        recovery = Manager(fixture.root / "absent-config", {"schema_version": 1, "id": self.instance["id"]},
                           docker=self.docker, recovery_only=True, test_paths=True, lease_system_root=fixture.root)
        identity = {"id": "e" * 64, "image_id": IMAGE, "name": "recover-owned",
                    "owner": OWNER, "instance": self.instance["id"], "deployment": PROOF, "legacy": False}
        record = {"Id": identity["id"], "Image": IMAGE, "Name": "/recover-owned",
                  "State": {"Running": True, "Status": "running"}, "NetworkSettings": {"Ports": {}},
                  "Config": {"Labels": {LABEL + key: identity[key] for key in ("owner", "instance", "deployment")}}}
        lease_arguments = {"system_root": fixture.root, "trusted_uid": os.geteuid()}
        args = argparse.Namespace(command="recover-stop", yes=True, dry_run=False, instance=None, no_wait=False)
        for malformed in (None, [], "invalid"):
            with self.subTest(kind=type(malformed).__name__):
                fixture.jsonfile(binding.path("data", "services/llm-manager/deployment-instance.json"),
                                 {"schema_version": 1, "id": self.instance["id"],
                                  "storage_identity": binding.identity, "paths": malformed})
                self.docker.records = [copy.deepcopy(record)]
                self.docker.calls.clear()
                state = {**empty_state(), "selected": PROOF, "desired": "running", "observed": "ready",
                         "container_running": True, "container": copy.deepcopy(identity)}
                with acquire_lease(**lease_arguments):
                    atomic_json(recovery.recovery_file, state, **lease_arguments)
                with patch.object(manager_module.RegisteredStorageBinding, "load", return_value=binding), \
                        patch.object(manager_module, "acquire_lease", side_effect=lambda: acquire_lease(**lease_arguments)), \
                        patch.object(manager_module, "recovery_manager", return_value=recovery) as fallback, \
                        patch.object(manager_module.signal, "signal"), redirect_stdout(io.StringIO()):
                    self.assertEqual(manager_module.cli(args), 0)
                fallback.assert_called_once()
                self.assertFalse(self.docker.records[0]["State"]["Running"])
                self.assertEqual([call for call in self.docker.calls if call[0] == "stop"], [("stop", identity["id"])])
                self.assertFalse(json.loads(recovery.recovery_file.read_text())["state_persisted"])

    def test_copied_historical_marker_cannot_exempt_nondefault_completion(self):
        fixture = RegisteredFixture()
        self.addCleanup(fixture.close)
        binding = fixture.binding()
        instance = {"schema_version": 1, "id": "fresh-review-fixture", "storage_identity": binding.identity,
                    "historical_import": True,
                    "paths": {"state": {"role": "data", "suffix": "services/llm-manager/active"}},
                    "model_integrity": {"fixture-model": {"verified": True, "revision": "fixture-revision",
                                                          "evidence": "copied-historical-attestation"}}}
        with self.assertRaisesRegex(LifecycleError, "historical_paths_must_be_preserved"):
            Manager(ROOT / "configs", instance, binding=binding, test_paths=True, lease_system_root=fixture.root)
        instance["historical_import"] = "true"
        with self.assertRaisesRegex(LifecycleError, "invalid_historical_import_marker"):
            Manager(ROOT / "configs", instance, binding=binding, test_paths=True, lease_system_root=fixture.root)

    def test_invalid_direct_dispatch_arguments_fail_before_acquisition_or_io(self):
        cases = []
        for invalid in (None, False, 0, [], {}, "", "unsupported", "start\n"):
            cases.append(({"action": invalid}, "invalid_lifecycle_action"))
        for invalid in (False, 0, [], {}, "", "invalid_policy", "RESUME"):
            cases.append(({"action": "select", "deployment_id": PROOF, "boot_policy": invalid}, "invalid_boot_policy"))
        for invalid in (None, 0, 1, "false", [], {}):
            cases.append(({"action": "stop", "dry_run": invalid}, "invalid_dry_run"))
        for invalid in (False, 0, [], {}, "", "../other", "unsafe/profile", "x" * 129):
            cases.append(({"action": "stop", "deployment_id": invalid}, "invalid_deployment_id"))
        cases.extend([({"action": "select"}, "invalid_deployment_id"),
                      ({"action": "activate"}, "invalid_deployment_id")])
        for arguments, expected in cases:
            with self.subTest(arguments=arguments), \
                    patch.object(manager_module, "acquire_lease", side_effect=AssertionError("invalid call acquired a lease")), \
                    patch.object(self.manager, "read_state", side_effect=AssertionError("invalid call read state")), \
                    patch.object(self.manager, "check_package_admission", side_effect=AssertionError("invalid call entered admission")), \
                    patch.object(self.manager, "deployment", side_effect=AssertionError("invalid call read profile")), \
                    patch.object(self.manager, "save", side_effect=AssertionError("invalid call persisted state")), \
                    patch.object(self.manager, "persistent_json", side_effect=AssertionError("invalid call wrote storage")):
                with self.assertRaisesRegex(LifecycleError, "^" + expected + "$"):
                    self.manager.dispatch(**arguments)
        self.assertEqual(self.docker.calls, [])
        self.assertFalse(self.manager.lock_file.exists())
        self.assertFalse(self.manager.state_file.exists())
        self.assertFalse(self.manager.recovery_file.exists())

    def test_invalid_direct_arguments_do_not_release_borrowed_owner(self):
        with acquire_lease(**self.arguments) as lease:
            with patch.object(self.manager, "read_state", side_effect=AssertionError("invalid call read state")), \
                    patch.object(self.manager, "check_package_admission", side_effect=AssertionError("invalid call entered admission")):
                with self.assertRaisesRegex(LifecycleError, "^invalid_boot_policy$"):
                    self.manager.dispatch("select", PROOF, boot_policy="invalid", lease=lease)
            lease.validate()
            self.assertTrue(self.observe())
            result = self.manager.dispatch("stop", deployment_id="valid-ignored-id", lease=lease)
            self.assertEqual(result["desired"], "stopped")
            lease.validate()
            self.assertTrue(self.observe())
        self.assertFalse(self.observe())


class LegacyMountBindingTests(unittest.TestCase):
    def fixture(self):
        fixture = RegisteredFixture(data="/data", models="/data/models-large", split=True)
        self.addCleanup(fixture.close)
        binding = fixture.binding()
        instance = {"schema_version": 1, "id": "legacy-review-fixture", "storage_identity": binding.identity,
                    "historical_import": True,
                    "paths": {"state": {"role": "data", "suffix": "services/llm-manager/active"}}}
        docker = FakeDocker()
        manager = Manager(ROOT / "configs", instance, binding=binding, test_paths=True,
                          lease_system_root=fixture.root, docker=docker)
        profile = legacy_profile("qwen3-0.6b-smoke")
        fixture.local(profile["paths"]["model"]).mkdir(parents=True)
        fixture.local(profile["compose_file"]).parent.mkdir(parents=True)
        return fixture, binding, manager, profile, docker

    def test_historical_literal_sources_are_verified_without_relocation(self):
        fixture, binding, manager, profile, docker = self.fixture()
        with patch.object(binding, "validate_path", wraps=binding.validate_path) as validate:
            manager.check_sources(profile)
        self.assertEqual([call.args for call in validate.call_args_list], [
            ("data", "/data/models"), ("data", "/data/models/qwen3-0.6b-smoke"),
            ("data", "/data/services/llm-manager/compose/sglang-smoke.compose.yml")])
        self.assertEqual(docker.calls, [])

    def test_hidden_legacy_bind_model_or_compose_mount_refused_before_access(self):
        for hidden in ("/data/models", "/data/models/qwen3-0.6b-smoke",
                       "/data/services/llm-manager/compose"):
            with self.subTest(hidden=hidden):
                fixture, binding, manager, profile, docker = self.fixture()
                fixture.runner.add_disk("/dev/sdd", "8:48", "/dev/sdd1", "8:49", "hidden-uuid", hidden)
                with patch.object(Path, "glob", side_effect=AssertionError("artifacts accessed before source validation")):
                    with self.assertRaisesRegex(LifecycleError, "unregistered_mount_source"):
                        manager.check_artifacts(profile)
                self.assertEqual(docker.calls, [])

    def test_legacy_config_symlink_refused_before_weight_discovery(self):
        fixture, binding, manager, profile, docker = self.fixture()
        outside = fixture.root / "unregistered-config"
        outside.write_text("{}")
        fixture.local(profile["paths"]["model"] + "/config.json").symlink_to(outside)
        with patch.object(Path, "glob", side_effect=AssertionError("weights accessed before config validation")):
            with self.assertRaises(BindingError):
                manager.check_artifacts(profile)
        self.assertEqual(docker.calls, [])


if __name__ == "__main__":
    unittest.main()
