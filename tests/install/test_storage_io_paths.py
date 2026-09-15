"""Local descriptor tests with synthetic mountinfo, NOT actual Linux mount QA.

Run: python3 -B -m unittest discover -s tests/install -p test_storage_io_paths.py -v
No mounts, host configuration, block devices or external services are used.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install import storage_io as io


class SyntheticMountPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".mount-path-test-", dir=REPO)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.data = self.base / "data"
        self.data.mkdir(mode=0o700)
        for relative in ("services/llm-manager", "models", "docker/containers", "build"):
            (self.data / relative).mkdir(mode=0o700, parents=True)
        device = self.data.stat().st_dev
        self.device = f"{os.major(device)}:{os.minor(device)}"
        data_identity = {"path": str(self.data), "mount": str(self.data),
                         "uuid": "synthetic-data-uuid", "fstype": "ext4", "device": self.device}
        self.value = {
            "schema_version": 1,
            "data": dict(data_identity),
            "models": {**data_identity, "path": str(self.data / "models")},
            "roots": {"state": str(self.data / "services"), "models": str(self.data / "models"),
                      "build": str(self.data / "build"), "docker": str(self.data / "docker")},
        }
        self.registry = self.base / "etc/local-ai-server/storage.json"
        self.registry.parent.mkdir(mode=0o700, parents=True)
        self._write_registry()
        self.mountinfo = ("1 0 0:1 / / rw - ext4 /dev/synthetic-root rw\n"
                          f"2 1 {self.device} / {self.data} rw - ext4 /dev/synthetic-data rw\n")
        self.next_mount_id = 20
        fixture = self

        class StorageFixture:
            owner = os.geteuid()
            system_root = fixture.base

            def guard(self, *, roles=("data", "models")):
                value = copy.deepcopy(fixture.value)
                value["verified_roles"] = list(roles)
                return value

        self.storage = StorageFixture()
        self.guard = self._guard()
        self.root = io.AnchoredRoot(str(self.data), self.guard, uid=os.geteuid())
        self.addCleanup(self.root.close)

    def _write_registry(self):
        self.registry.write_text(json.dumps(self.value))
        self.registry.chmod(0o600)

    def _guard(self, **kwargs):
        guard = io.MountedStorageGuard(self.storage, mountinfo_reader=lambda: self.mountinfo, **kwargs)
        self.addCleanup(guard.close)
        return guard

    def _mount(self, relative, *, parent_id=2):
        """Insert a same-device synthetic mount entry without touching mounts."""
        self.mountinfo += (f"{self.next_mount_id} {parent_id} {self.device} /elsewhere "
                           f"{self.data / relative} rw - ext4 /dev/synthetic-data rw\n")
        self.next_mount_id += 1

    def _write(self, relative, data=b"preserved"):
        path = self.data / relative
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
        return path

    def assert_mount_refused(self, operation):
        with self.assertRaisesRegex(io.StorageIOError, "mount"):
            operation()

    def test_same_device_descendant_inserted_after_preflight_before_mkdir(self):
        self._mount("services/llm-manager")
        self.assert_mount_refused(lambda: self.root.mkdir("services/llm-manager/new/leaf"))
        self.assertFalse((self.data / "services/llm-manager/new").exists())

    def test_same_device_descendant_inserted_after_preflight_before_open(self):
        self._mount("services/llm-manager")

        def create():
            with self.root.open("services/llm-manager/payload", os.O_WRONLY | os.O_CREAT):
                pass

        self.assert_mount_refused(create)
        self.assertFalse((self.data / "services/llm-manager/payload").exists())

    def test_same_device_descendant_inserted_before_atomic_json_creates_nothing(self):
        self._mount("services/llm-manager")
        self.assert_mount_refused(lambda: self.root.atomic_json("services/llm-manager/state.json", {}))
        self.assertEqual(list((self.data / "services/llm-manager").iterdir()), [])

    def test_final_file_mount_refuses_open_before_truncate(self):
        target = self._write("services/llm-manager/state.json")
        self._mount("services/llm-manager/state.json")

        def truncate():
            with self.root.open("services/llm-manager/state.json", os.O_WRONLY | os.O_TRUNC):
                pass

        self.assert_mount_refused(truncate)
        self.assertEqual(target.read_bytes(), b"preserved")

    def test_final_directory_mount_refuses_directory_and_mkdir(self):
        self._mount("services/llm-manager")
        self.assert_mount_refused(lambda: self.root.mkdir("services/llm-manager"))

        def directory():
            with self.root.directory("services/llm-manager"):
                pass

        self.assert_mount_refused(directory)

    def test_held_file_rechecks_final_and_intermediate_paths_between_chunks(self):
        original_mountinfo = self.mountinfo
        actual_write = os.write
        for mounted in ("services/llm-manager/partial", "services/llm-manager"):
            with self.subTest(mounted=mounted):
                self.mountinfo = original_mountinfo
                calls = []
                with self.root.open("services/llm-manager/partial", os.O_CREAT | os.O_WRONLY | os.O_TRUNC) as stream:
                    def insert_after_write(fd, data):
                        calls.append(len(data))
                        count = actual_write(fd, data)
                        self._mount(mounted)
                        return count

                    with patch.object(io.os, "write", side_effect=insert_after_write):
                        self.assert_mount_refused(lambda: stream.write(b"x" * (2 * io.MAX_CHUNK + 9)))
                self.assertEqual(calls, [io.MAX_CHUNK])
                self.assertEqual((self.data / "services/llm-manager/partial").stat().st_size, io.MAX_CHUNK)

    def test_held_file_methods_refuse_new_mount_without_mutating_bytes(self):
        target = self._write("services/llm-manager/partial")
        with self.root.open("services/llm-manager/partial", os.O_RDWR) as stream:
            self._mount("services/llm-manager/partial")
            for operation in (lambda: stream.write(b"forbidden"), lambda: stream.read(1),
                              lambda: stream.truncate(0), stream.fsync, stream.stat, stream.fileno):
                self.assert_mount_refused(operation)
        self.assertEqual(target.read_bytes(), b"preserved")

    def test_path_methods_refuse_final_file_mount(self):
        target = self._write("services/llm-manager/state.json", b"{}")
        self._mount("services/llm-manager/state.json")
        for operation in (lambda: self.root.stat("services/llm-manager/state.json"),
                          lambda: self.root.read_json("services/llm-manager/state.json"),
                          lambda: self.root.unlink("services/llm-manager/state.json"),
                          lambda: self.root.proc_path("services/llm-manager/state.json"),
                          lambda: self.root.check("services/llm-manager/state.json"),
                          lambda: self.root.guard("services/llm-manager/state.json")):
            self.assert_mount_refused(operation)
        self.assertEqual(target.read_bytes(), b"{}")

    def test_replace_refuses_mounts_on_either_final_component(self):
        original_mountinfo = self.mountinfo
        for mounted in ("services/llm-manager/source", "services/llm-manager/destination"):
            with self.subTest(mounted=mounted):
                self.mountinfo = original_mountinfo
                source = self._write("services/llm-manager/source", b"new")
                destination = self._write("services/llm-manager/destination", b"old")
                self._mount(mounted)
                self.assert_mount_refused(lambda: self.root.replace("services/llm-manager/source",
                                                                   "services/llm-manager/destination"))
                self.assertEqual(source.read_bytes(), b"new")
                self.assertEqual(destination.read_bytes(), b"old")

    def test_replace_rechecks_destination_after_destination_stat(self):
        source = self._write("services/llm-manager/source", b"new")
        destination = self._write("services/llm-manager/destination", b"old")
        actual_stat = self.root.stat

        def insert_after_stat(relative, **kwargs):
            result = actual_stat(relative, **kwargs)
            if relative == "services/llm-manager/destination":
                self._mount(relative)
            return result

        with patch.object(self.root, "stat", side_effect=insert_after_stat), patch.object(io.os, "replace") as rename:
            self.assert_mount_refused(lambda: self.root.replace("services/llm-manager/source",
                                                               "services/llm-manager/destination"))
            rename.assert_not_called()
        self.assertEqual(source.read_bytes(), b"new")
        self.assertEqual(destination.read_bytes(), b"old")

    def test_replace_rechecks_destination_mount_inserted_inside_source_fsync(self):
        original_mountinfo = self.mountinfo
        actual_fsync = os.fsync
        for mounted in ("services/destination", "services/destination/final"):
            with self.subTest(mounted=mounted):
                self.mountinfo = original_mountinfo
                source = self._write("services/llm-manager/source", b"new")
                destination = self._write("services/destination/final", b"old")
                inserted = []

                def insert_during_fsync(fd):
                    result = actual_fsync(fd)
                    if not inserted:
                        inserted.append(True)
                        self._mount(mounted)
                    return result

                with patch.object(io.os, "fsync", side_effect=insert_during_fsync), patch.object(io.os, "replace") as rename:
                    self.assert_mount_refused(lambda: self.root.replace("services/llm-manager/source",
                                                                       "services/destination/final"))
                    rename.assert_not_called()
                self.assertEqual(source.read_bytes(), b"new")
                self.assertEqual(destination.read_bytes(), b"old")

    def test_unrelated_docker_mount_under_data_allows_anchored_operation(self):
        self._mount("docker/containers/runtime")
        self.root.atomic_json("services/llm-manager/state.json", {"saved": True})
        self.assertEqual(self.root.read_json("services/llm-manager/state.json"), {"saved": True})
        self.guard()

    def test_explicit_registered_model_mount_is_allowed_by_default_guard(self):
        # Synthetic model entry has its own mount ID; the local directory stays
        # on the same real filesystem. This is API/seam coverage, not a mount.
        self.value["models"]["mount"] = str(self.data / "models")
        self.value["models"]["uuid"] = "synthetic-model-uuid"
        self._write_registry()
        self._mount("models")
        guard = self._guard()
        with io.AnchoredRoot(str(self.data / "models"), guard, uid=os.geteuid()) as models:
            models.atomic_json("manifest.json", {"model": "fixture"})
            self.assertEqual(models.read_json("manifest.json"), {"model": "fixture"})

    def test_shared_filesystem_model_path_is_allowed_by_default_guard(self):
        with self.root.directory("models") as models:
            models.atomic_json("manifest.json", {"model": "fixture"})
            self.assertEqual(models.read_json("manifest.json"), {"model": "fixture"})

    def test_registered_model_mount_does_not_hide_replaced_intermediate_component(self):
        (self.data / "collection/models").mkdir(mode=0o700, parents=True)
        self.value["models"]["path"] = str(self.data / "collection/models")
        self.value["models"]["mount"] = str(self.data / "collection/models")
        self.value["roots"]["models"] = str(self.data / "collection/models")
        self._write_registry()
        self._mount("collection/models")
        guard = self._guard()
        with io.AnchoredRoot(str(self.data / "collection/models"), guard, uid=os.geteuid()) as models:
            self._mount("collection")
            self.assert_mount_refused(lambda: models.atomic_json("manifest.json", {}))
        self.assertEqual(list((self.data / "collection/models").iterdir()), [])

    def test_data_only_guard_tolerates_missing_model_mount_and_denies_model_paths(self):
        self.value["models"]["mount"] = str(self.data / "models")
        self.value["models"].pop("device")
        self._write_registry()
        guard = self._guard(roles=("data",))
        with io.AnchoredRoot(str(self.data), guard, uid=os.geteuid()) as root:
            root.atomic_json("services/llm-manager/state.json", {"saved": True})
            self.assertEqual(root.read_json("services/llm-manager/state.json"), {"saved": True})
            operations = (lambda: root.mkdir("models/forbidden"),
                          lambda: root.atomic_json("models/manifest.json", {}),
                          lambda: root.stat("models/missing", missing_ok=True),
                          lambda: root.proc_path("models/missing"),
                          lambda: guard.check_path(self.data / "models/missing"))
            for operation in operations:
                with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
                    operation()
            with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
                root.directory("models")
        self.assertEqual(list((self.data / "models").iterdir()), [])

    def test_data_only_guard_still_rejects_fixed_unverified_model_registration_tamper(self):
        guard = self._guard(roles=("data",))
        with io.AnchoredRoot(str(self.data), guard, uid=os.geteuid()) as root:
            self.value["models"]["uuid"] = "tampered-unverified-model"
            self._write_registry()
            with self.assertRaisesRegex(io.StorageIOError, "bytes_changed"):
                root.mkdir("services/llm-manager/forbidden")
        self.assertFalse((self.data / "services/llm-manager/forbidden").exists())

    def test_data_only_guard_refuses_ambiguous_equal_root_but_allows_specific_state(self):
        self.value["models"]["path"] = str(self.data)
        self.value["roots"]["models"] = str(self.data)
        self._write_registry()
        guard = self._guard(roles=("data",))
        with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
            io.AnchoredRoot(str(self.data), guard, uid=os.geteuid())
        with io.AnchoredRoot(str(self.data / "services"), guard, uid=os.geteuid()) as state:
            state.atomic_json("llm-manager/state.json", {"saved": True})
            self.assertEqual(state.read_json("llm-manager/state.json"), {"saved": True})

    def test_data_only_more_specific_state_cannot_override_distinct_model_subtree(self):
        installer = self.data / "services/installer"
        installer.mkdir(mode=0o700)
        self.value["models"]["path"] = str(self.data / "services")
        self.value["roots"]["models"] = str(self.data / "services")
        self.value["roots"]["state"] = str(installer)
        self._write_registry()
        guard = self._guard(roles=("data",))
        with io.AnchoredRoot(str(self.data), guard, uid=os.geteuid()) as root:
            for operation in (lambda: guard.check_path(installer / "forbidden"),
                              lambda: root.mkdir("services/installer/forbidden"),
                              lambda: root.atomic_json("services/installer/forbidden.json", {})):
                with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
                    operation()
        with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
            io.AnchoredRoot(str(installer), guard, uid=os.geteuid())
        self.assertEqual(list(installer.iterdir()), [])

    def test_models_only_refuses_unverified_data_ancestry_but_allows_sibling_mount(self):
        nested = self.data / "collection/models"
        nested.mkdir(mode=0o700, parents=True)
        self.value["models"]["path"] = str(nested)
        self.value["models"]["mount"] = str(nested)
        self.value["roots"]["models"] = str(nested)
        self._write_registry()
        self._mount("collection/models")
        guard = self._guard(roles=("models",))
        # The data-role ancestry is unverified before any additional bind is
        # inserted; a verified final model entry cannot attest those parents.
        with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
            guard.check_path(nested / "forbidden")
        with self.assertRaisesRegex(io.StorageIOError, "role_not_verified"):
            io.AnchoredRoot(str(nested), guard, uid=os.geteuid())
        self.assertEqual(list(nested.iterdir()), [])

        sibling = self.base / "model-disk"
        sibling.mkdir(mode=0o700)
        self.value["models"]["path"] = str(sibling)
        self.value["models"]["mount"] = str(sibling)
        self.value["roots"]["models"] = str(sibling)
        self._write_registry()
        self.mountinfo += (f"{self.next_mount_id} 1 {self.device} / {sibling} rw "
                           "- ext4 /dev/synthetic-models rw\n")
        self.next_mount_id += 1
        sibling_guard = self._guard(roles=("models",))
        with io.AnchoredRoot(str(sibling), sibling_guard, uid=os.geteuid()) as models:
            models.atomic_json("manifest.json", {"saved": True})
            self.assertEqual(models.read_json("manifest.json"), {"saved": True})

    def test_wrapper_must_preserve_required_path_capability_and_snapshot_identity(self):
        self.assertIs(self.guard()["path_validation_required"], True)
        with self.assertRaisesRegex(io.StorageIOError, "path"):
            with io.AnchoredRoot(str(self.data), lambda: self.guard(), uid=os.geteuid()) as root:
                root.mkdir("services/llm-manager/forbidden")
        self.assertFalse((self.data / "services/llm-manager/forbidden").exists())
        mounted_guard = self.guard

        class ForwardingGuard:
            changed = False

            def __call__(self):
                return mounted_guard()

            def check_path(self, path):
                value = mounted_guard.check_path(path)
                if self.changed:
                    value["data"]["uuid"] = "changed-wrapper-identity"
                return value

        forwarded = ForwardingGuard()
        with io.AnchoredRoot(str(self.data), forwarded, uid=os.geteuid()) as root:
            root.atomic_json("services/llm-manager/state.json", {"saved": True})
            forwarded.changed = True
            with self.assertRaisesRegex(io.StorageIOError, "identity_changed"):
                root.mkdir("services/llm-manager/forbidden")
            forwarded.changed = False
            self._mount("services/llm-manager")
            self.assert_mount_refused(lambda: root.mkdir("services/llm-manager/forbidden"))
        self.assertFalse((self.data / "services/llm-manager/forbidden").exists())

    def test_registered_mount_id_replacement_refuses_operation(self):
        self.mountinfo = self.mountinfo.replace("2 1 ", "99 1 ")
        self.assert_mount_refused(lambda: self.root.atomic_json("services/llm-manager/state.json", {}))
        self.assertEqual(list((self.data / "services/llm-manager").iterdir()), [])

    def test_mount_loss_refuses_output_and_leaves_existing_content(self):
        target = self._write("services/llm-manager/state.json", b"{}")
        self.mountinfo = self.mountinfo.splitlines()[0] + "\n"
        self.assert_mount_refused(lambda: self.root.atomic_json("services/llm-manager/state.json", {"bad": True}))
        self.assertEqual(target.read_bytes(), b"{}")
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_descendant_directory_replacement_still_checks_held_identity(self):
        with self.root.directory("services/llm-manager") as manager:
            (self.data / "services/llm-manager").rename(self.data / "services/old-manager")
            (self.data / "services/llm-manager").mkdir(mode=0o700)
            with self.assertRaisesRegex(io.StorageIOError, "detached_or_replaced"):
                manager.atomic_json("state.json", {})
        self.assertEqual(list((self.data / "services/llm-manager").iterdir()), [])
        self.assertEqual(list((self.data / "services/old-manager").iterdir()), [])

    def test_fixed_registry_byte_and_inode_tamper_refused_through_operation(self):
        original = self.registry.read_bytes()
        self.registry.write_bytes(original.replace(b"synthetic-data-uuid", b"different-data-uuid"))
        with self.assertRaisesRegex(io.StorageIOError, "bytes_changed"):
            self.root.mkdir("services/llm-manager/forbidden")
        self.registry.write_bytes(original)
        self.registry.rename(self.registry.with_name("old-storage.json"))
        self.registry.write_bytes(original)
        self.registry.chmod(0o600)
        with self.assertRaisesRegex(io.StorageIOError, "file_changed"):
            self.root.mkdir("services/llm-manager/forbidden")
        self.assertFalse((self.data / "services/llm-manager/forbidden").exists())

    def test_bound_guard_alias_preserves_path_check_capability(self):
        with io.AnchoredRoot(str(self.data), self.guard.guard, uid=os.geteuid()) as root:
            self._mount("services/llm-manager")
            self.assert_mount_refused(lambda: root.mkdir("services/llm-manager/forbidden"))
        self.assertFalse((self.data / "services/llm-manager/forbidden").exists())

    def test_check_path_accepts_normalized_missing_absolute_operation(self):
        for path in (str(self.data / "services/llm-manager/missing/file"),
                     self.data / "services/llm-manager/missing/file"):
            self.assertEqual(self.guard.check_path(path)["data"]["uuid"], "synthetic-data-uuid")
        self.assertFalse((self.data / "services/llm-manager/missing").exists())

    def test_check_path_rejects_noncanonical_and_outside_paths(self):
        for path in ("relative", "", str(self.data) + "/services//file", str(self.data) + "/./file",
                     str(self.data) + "/services/../file", str(self.data) + "/file/", str(self.data) + "/bad\x00file",
                     str(self.data) + "-other/file", str(self.base / "outside")):
            with self.subTest(path=repr(path)), self.assertRaises(io.StorageIOError):
                self.guard.check_path(path)

    def test_relative_check_rejects_traversal_before_observation(self):
        for relative in ("../outside", "/absolute", "services//file", "services/./file", "services/../file"):
            with self.subTest(relative=relative), self.assertRaisesRegex(io.StorageIOError, "relative_path"):
                self.root.check(relative)


if __name__ == "__main__":
    unittest.main()
