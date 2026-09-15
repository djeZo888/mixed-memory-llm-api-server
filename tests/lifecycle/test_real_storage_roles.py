"""Actual Storage + reviewed writer role integration; worker discovery is synthetic.

No Storage verifier, topology method or role attestation is replaced. A local
path mapping, synthetic read-only command responses, injected mountinfo and the
writer's ordinary-user uid seam keep all filesystem operations in worker temp
directories. These tests do not establish actual Linux mount acceptance.

The role integration class intentionally fails once at setup until published
I1c Storage provides its frozen roles API. A preparation fixture is not a PASS
for that missing source. Run with unittest discover using this file's name.
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.lifecycle_lease import acquire_lease
from install.storage import Storage, StorageError
from install import storage_io as real_io
from lifecycle.manager import LABEL, OWNER, Manager, empty_state
from lifecycle.runtime_io import LifecycleError
from lifecycle.storage_binding import BindingError, RegisteredStorageBinding
from test_manager import FakeDocker


class LocalPathStorage(Storage):
    """Only map fixed registry paths; verification/discovery stays inherited."""

    def _local(self, path):
        candidate = Path(path)
        if candidate == self.system_root or self.system_root in candidate.parents:
            return candidate
        return super()._local(path)


class DiscoveryRunner:
    """Read-only command responses with distinct synthetic block ancestry."""

    def __init__(self, fixture, device):
        self.fixture, self.calls, self.blocks = fixture, [], []
        self.disk("root", "65000:1", "65000:2", "/", "fixture-root-uuid")
        self.disk("data", "65000:3", device, fixture.data, "fixture-data-uuid")
        if fixture.split:
            self.disk("models", "65000:4", "65000:5", fixture.models, "fixture-model-uuid")

    def disk(self, name, parent_device, device, mount, uuid):
        parent, child = "/dev/fixture-" + name, "/dev/fixture-" + name + "1"
        self.blocks.extend([
            {"path": parent, "type": "disk", "ro": False, "maj:min": parent_device,
             "mountpoints": [None], "uuid": None},
            {"path": child, "type": "part", "pkname": parent, "ro": False,
             "maj:min": device, "mountpoints": [mount], "uuid": uuid, "fstype": "ext4"},
        ])

    def run(self, argv, *, timeout=30):
        self.calls.append(list(argv))
        if argv[0] == "lsblk":
            return json.dumps({"blockdevices": self.blocks})
        if argv[0] == "df":
            return "Avail\n107374182400\n"
        if argv[0] == "findmnt":
            path = argv[-1]
            # Binding.validate_path emits a path relative to system_root; the
            # Storage verifier itself uses the actual registered absolute path.
            if path not in {"/", "/boot", "/boot/efi"} and not path.startswith(str(self.fixture.base) + "/"):
                path = str(self.fixture.base / path.lstrip("/"))
            candidates = [(mount, block) for block in self.blocks
                          for mount in block["mountpoints"] if mount
                          and (mount == "/" or path == mount or path.startswith(mount + "/"))]
            mount, block = max(candidates, key=lambda item: len(item[0]))
            return json.dumps({"filesystems": [{"target": mount, "source": block["path"],
                "uuid": block["uuid"], "fstype": block["fstype"], "options": "rw,relatime",
                "maj:min": block["maj:min"]}]})
        raise AssertionError("unexpected synthetic discovery command: " + argv[0])


class RealRoleFixture:
    def __init__(self, *, layout="equal"):
        self.temp = tempfile.TemporaryDirectory(prefix=".l1b-real-roles-", dir=ROOT)
        self.base = Path(self.temp.name).resolve()
        self.data = str(self.base / "srv/ai-server")
        self.split = layout in {"nested", "sibling"}
        self.models = (str(self.base / "mnt/model-volume") if layout == "sibling"
                       else self.data + "/models-large" if layout == "nested" else self.data)
        self.guards, self.anchors, self.host_commands = [], [], []
        self.storage = LocalPathStorage({"data_dir": self.data, "model_dir": self.models,
            "data_uuid": "fixture-data-uuid",
            "model_uuid": "fixture-model-uuid" if self.split else "fixture-data-uuid"},
            None, system_root=self.base)
        for role, path in self.storage._roots().items():
            Path(path).mkdir(parents=True, exist_ok=True)
            Path(path).chmod(0o700 if role in {"secrets", "state"} else 0o755)
        st_dev = Path(self.data).stat().st_dev
        device = f"{os.major(st_dev)}:{os.minor(st_dev)}"
        self.runner = DiscoveryRunner(self, device)
        self.storage.runner = self.runner
        # Registration is produced by actual full verification; no snapshot or
        # verified_roles attestation is manufactured by this fixture.
        self.registration = self.storage.verify()
        registry = self.base / "etc/local-ai-server/storage.json"
        registry.parent.mkdir(parents=True, mode=0o700)
        registry.write_text(json.dumps(self.registration))
        registry.chmod(0o600)
        self.storage.verify(registration=self.registration)
        self.mountinfo = ("1 0 65000:2 / / rw - ext4 /dev/fixture-root1 rw\n"
            + f"2 1 {device} / {self.data} rw - ext4 /dev/fixture-data1 rw\n")
        if self.split:
            self.mountinfo += f"3 2 65000:5 / {self.models} rw - ext4 /dev/fixture-models1 rw\n"
        self.binding = RegisteredStorageBinding(self.storage, self.registration)
        self.api = SimpleNamespace(MountedStorageGuard=self.mounted_guard, AnchoredRoot=self.anchored_root)
        self.instance = {"schema_version": 1, "id": "real-role-fixture",
            "storage_identity": self.binding.identity,
            "paths": {"state": {"role": "data", "suffix": "services/llm-manager/active"}}}
        self.docker = FakeDocker()
        self.manager = Manager(ROOT / "configs", self.instance, binding=self.binding,
            storage_io=self.api, test_paths=True, lease_system_root=self.base,
            docker=self.docker, run_fn=self.host_command)

    def close(self):
        for resource in self.guards + self.anchors:
            resource.close()
        self.temp.cleanup()

    def mounted_guard(self, storage, *, roles=("data", "models")):
        guard = real_io.MountedStorageGuard(storage, roles=roles, mountinfo_reader=lambda: self.mountinfo)
        self.guards.append(guard)
        return guard

    def anchored_root(self, path, guard):
        anchor = real_io.AnchoredRoot(path, guard, uid=os.geteuid())
        self.anchors.append(anchor)
        return anchor

    def host_command(self, argv, *, timeout):
        self.host_commands.append(list(argv))
        if Path(argv[0]).name == "require-data-mounted.sh":
            return json.dumps(self.storage.verify())
        if argv[-2:] == ["--json", "--root-guard"]:
            return json.dumps(self.storage.root_payload_guard())
        raise AssertionError("unexpected synthetic host command")

    def lease(self):
        return acquire_lease(system_root=self.base, trusted_uid=os.geteuid())

    def remove_model_mount(self):
        for block in self.runner.blocks:
            if block["uuid"] == "fixture-model-uuid":
                block["mountpoints"] = [None]
        self.mountinfo = "\n".join(line for line in self.mountinfo.splitlines() if not line.startswith("3 ")) + "\n"

    def running_state(self):
        identity = {"id": "a" * 64, "image_id": "sha256:" + "b" * 64,
            "name": "llmctl-real-role-fixture", "owner": OWNER, "instance": self.instance["id"],
            "deployment": "qwen3-coder-next", "legacy": False}
        self.docker.records = [{"Id": identity["id"], "Image": identity["image_id"],
            "Name": "/" + identity["name"], "State": {"Running": True, "Status": "running"},
            "Config": {"Labels": {LABEL + key: identity[key] for key in ("owner", "instance", "deployment")}},
            "NetworkSettings": {"Ports": {}}}]
        self.manager.state = {**empty_state(), "selected": identity["deployment"], "desired": "running",
            "observed": "ready", "container_running": True, "container": identity}
        return identity


class RealStorageDiscoveryFixtureTests(unittest.TestCase):
    def test_preparation_uses_actual_full_verifier_and_real_writer(self):
        """A full-role fixture smoke test does not close pending role acceptance."""
        for layout in ("equal", "nested", "sibling"):
            with self.subTest(layout=layout):
                fixture = RealRoleFixture(layout=layout)
                self.addCleanup(fixture.close)
                for method in ("verify", "guard", "_snapshot", "_mount", "_capacity"):
                    self.assertIs(getattr(LocalPathStorage, method), getattr(Storage, method))
                self.assertEqual(fixture.storage.verify()["roots"], fixture.registration["roots"])
                with fixture.lease(), fixture.binding.mounted_guard(fixture.api) as guard:
                    with fixture.anchored_root(fixture.binding.path("services"), guard) as anchor:
                        anchor.atomic_json("fixture-smoke.json", {"fixture": "full-role-only"})
                self.assertEqual(json.loads(Path(fixture.binding.path("services", "fixture-smoke.json")).read_text()),
                                 {"fixture": "full-role-only"})


class RealStorageRoleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [name for name in ("verify", "guard", "root_payload_guard")
                   if "roles" not in inspect.signature(getattr(Storage, name)).parameters]
        if missing:
            raise AssertionError("I1c published role-capable Storage dependency pending: missing roles= on "
                + ", ".join(missing) + "; real Storage role integration is NOT PASSED")

    def fixture(self, **kwargs):
        value = RealRoleFixture(**kwargs)
        self.addCleanup(value.close)
        return value

    def assert_persisted(self, fixture, observed):
        state = json.loads(fixture.manager.state_file.read_text())
        recovery = json.loads(fixture.manager.recovery_file.read_text())
        self.assertTrue(state["state_persisted"])
        self.assertTrue(recovery["state_persisted"])
        self.assertEqual(state["observed"], observed)
        self.assertEqual(state, recovery)

    def test_equal_roots_normal_state_host_guard_report_and_trusted_stop(self):
        fixture = self.fixture()
        identity = fixture.running_state()
        with fixture.lease() as lease:
            fixture.manager.save()
            self.assert_persisted(fixture, "ready")
            fixture.manager.host_guards()
            report = json.loads(Path(fixture.binding.path("logs", "llmctl-root-disk-guard.json")).read_text())
            self.assertEqual(report["root_payload_scan"]["status"], "pass")
            self.assertEqual(len(fixture.host_commands), 2)
            result = fixture.manager.dispatch("stop", lease=lease)
            lease.validate()
        self.assertEqual(result["observed"], "stopped")
        self.assertTrue(result["state_persisted"])
        self.assertIn(("stop", identity["id"]), fixture.docker.calls)
        self.assert_persisted(fixture, "stopped")
        self.assertTrue(fixture.anchors)
        self.assertNotIn(Path(fixture.data), [anchor.path for anchor in fixture.anchors])

    def test_split_models_absent_preserves_data_state_report_and_trusted_stop(self):
        for layout in ("nested", "sibling"):
            with self.subTest(layout=layout):
                fixture = self.fixture(layout=layout)
                identity = fixture.running_state()
                fixture.remove_model_mount()
                snapshot = fixture.storage.verify(roles=("data",))
                self.assertEqual(snapshot["verified_roles"], ["data"])
                self.assertEqual(snapshot["roots"], fixture.registration["roots"])
                for field in ("path", "mount", "uuid", "fstype"):
                    self.assertEqual(snapshot["models"][field], fixture.registration["models"][field])
                for field in ("device", "source", "parents"):
                    self.assertNotIn(field, snapshot["models"])
                self.assertIsNone(snapshot["capacity"]["model_available_bytes"])
                with self.assertRaises(StorageError):
                    fixture.storage.verify()
                with fixture.lease() as lease:
                    fixture.manager.save()
                    self.assert_persisted(fixture, "ready")
                    report = fixture.storage.root_payload_guard(roles=("data",))
                    fixture.manager.persistent_json(fixture.binding.path("logs", "data-only-guard.json"), report)
                    self.assertEqual(json.loads(Path(fixture.binding.path("logs", "data-only-guard.json")).read_text()), report)
                    # The existing full host/start guard remains a full-role gate.
                    with self.assertRaisesRegex(LifecycleError, "registered_storage_verification_failed"):
                        fixture.manager.host_guards()
                    with fixture.binding.mounted_guard(fixture.api, roles=("data",)) as guard:
                        with self.assertRaisesRegex(BindingError, "^mounted_storage_guard_failed$"):
                            guard.check_path(fixture.models + "/unavailable-model.bin")
                    result = fixture.manager.dispatch("stop", lease=lease)
                    lease.validate()
                self.assertTrue(result["state_persisted"])
                self.assertIn(("stop", identity["id"]), fixture.docker.calls)
                self.assert_persisted(fixture, "stopped")

    def test_data_only_guard_denies_model_anchor_and_path_even_when_mounted(self):
        for layout in ("equal", "nested", "sibling"):
            with self.subTest(layout=layout):
                fixture = self.fixture(layout=layout)
                with fixture.lease(), fixture.binding.mounted_guard(fixture.api, roles=("data",)) as guard:
                    with self.assertRaises(real_io.StorageIOError):
                        fixture.anchored_root(fixture.models, guard)
                    with self.assertRaisesRegex(BindingError, "^mounted_storage_guard_failed$"):
                        guard.check_path(fixture.models + "/denied-model.json")
                self.assertFalse(Path(fixture.models + "/denied-model.json").exists())


if __name__ == "__main__":
    unittest.main()
