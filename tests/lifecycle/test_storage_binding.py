"""Worker fixtures exercise the actual I1 registry validator, never real mounts."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from storage_fixtures import RegisteredFixture
from lifecycle.storage_binding import BindingError, RegisteredStorageBinding, stable_identity


class StorageBindingTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = RegisteredFixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_registered_single_equal_nested_and_sibling_for_both_models(self):
        for data, models, split in (("/srv/ai", "/srv/ai/models", False),
                                    ("/srv/ai", "/srv/ai", False),
                                    ("/srv/ai", "/srv/ai/models-large", True),
                                    ("/srv/ai", "/mnt/ai-models", True),
                                    ("/data", "/data/models-large", True)):
            with self.subTest(data=data, models=models):
                fixture = self.fixture(data=data, models=models, split=split)
                binding = fixture.binding()
                self.assertEqual(binding.registry["models"]["mount"], models if split else data)
                for model in ("glm-5.3-ud-q4-k-xl", "qwen3-coder-next-fp8"):
                    host = binding.path("models", model)
                    self.assertEqual(host, models + "/" + model)
                    self.assertEqual(binding.validate_path("models", host), fixture.local(host))
                self.assertEqual(binding.path("services", "llm-manager/active/active.json"),
                                 data + "/services/llm-manager/active/active.json")
                self.assertEqual(binding.path("secrets", "llm-api-key"), data + "/services/secrets/llm-api-key")
                self.assertEqual(binding.path("models", "runtime-cache/sglang-qwen-next"),
                                 models + "/runtime-cache/sglang-qwen-next")

    def test_identity_ignores_observations_and_cannot_be_mutated_by_return_value(self):
        fixture = self.fixture()
        binding = fixture.binding()
        original = binding.identity
        registry = binding.registry
        registry["data"]["source"] = "/dev/renumbered"
        registry["data"]["device"] = "259:55"
        registry["data"]["parents"] = ["/dev/renumbered-parent"]
        self.assertEqual(stable_identity(registry), original)
        original["roots"]["docker"] = "/unsafe"
        self.assertEqual(binding.path("docker"), "/srv/ai/docker")
        fixture.runner.blocks[2].update(name="/dev/nvme9n1", path="/dev/nvme9n1", **{"maj:min": "259:9"})
        fixture.runner.blocks[3].update(name="/dev/nvme9n1p1", path="/dev/nvme9n1p1",
                                       pkname="/dev/nvme9n1", **{"maj:min": "259:10"})
        self.assertEqual(binding.verify()["data"]["source"], "/dev/nvme9n1p1")

    def test_offline_reads_registry_without_mount_or_subprocess_observation(self):
        fixture = self.fixture()
        fixture.runner.calls.clear()
        fixture.runner.blocks[3]["mountpoints"] = [None]
        binding = RegisteredStorageBinding.read_registered(fixture.runner, system_root=fixture.root)
        self.assertEqual(binding.path("models"), "/srv/ai/models")
        self.assertEqual(fixture.runner.calls, [])
        with self.assertRaises(BindingError):
            binding.verify()

    def test_environment_cannot_override_path_uuid_or_missing_registration(self):
        fixture = self.fixture()
        with patch.dict(os.environ, {"DATA_ROOT": "/unsafe", "AI_DATA_UUID": "other-uuid", "EXPECTED_UUID": "other-uuid"}):
            self.assertEqual(fixture.binding().path("data"), "/srv/ai")
            fixture.local(fixture.registry_path).unlink()
            with self.assertRaisesRegex(BindingError, "storage_registration_required"):
                fixture.binding()

    def test_bound_identity_rejects_registry_rewrite_or_deletion(self):
        fixture = self.fixture()
        binding = fixture.binding()
        value = copy.deepcopy(fixture.registration)
        value["data"]["uuid"] = "replacement-uuid"
        fixture.jsonfile(fixture.registry_path, value)
        with self.assertRaisesRegex(BindingError, "registration_changed"):
            binding.verify()
        fixture.local(fixture.registry_path).unlink()
        with self.assertRaisesRegex(BindingError, "registration_changed"):
            binding.verify()

    def test_rejects_wrong_uuid_root_alias_and_missing_second_mount(self):
        for mutation in ("uuid", "root_alias", "missing_models", "ambiguous_uuid"):
            with self.subTest(mutation=mutation):
                fixture = self.fixture(models="/mnt/models", split=True)
                binding = fixture.binding()
                if mutation == "uuid":
                    fixture.runner.blocks[3]["uuid"] = "different-uuid"
                elif mutation == "root_alias":
                    fixture.runner.blocks[3]["mountpoints"] = [None]
                    fixture.runner.blocks[1]["mountpoints"].append(fixture.data)
                elif mutation == "missing_models":
                    fixture.runner.blocks[5]["mountpoints"] = [None]
                else:
                    fixture.runner.add_disk("/dev/sdz", "65:0", "/dev/sdz1", "65:1", "data-uuid", "/alias")
                with self.assertRaises(BindingError):
                    binding.verify()

    def test_same_filesystem_registered_at_distinct_role_mounts_rejected(self):
        fixture = self.fixture(models="/mnt/models", split=True)
        # Simulate a registry written before alias handling was closed: both
        # roles point at one dedicated device exposed at two mount targets.
        value = copy.deepcopy(fixture.registration)
        value["models"].update(uuid=value["data"]["uuid"], source=value["data"]["source"],
                                device=value["data"]["device"], parents=value["data"]["parents"])
        fixture.jsonfile(fixture.registry_path, value)
        with self.assertRaisesRegex(BindingError, "ambiguous_registered_mount_alias"):
            RegisteredStorageBinding.read_registered(fixture.runner, system_root=fixture.root)

    def test_shared_verifier_gap_unregistered_duplicate_mount_alias(self):
        """I1b owns this unresolved topology correction; never counted as PASS."""
        fixture = self.fixture()
        binding = fixture.binding()
        fixture.runner.blocks[3]["mountpoints"].append("/unregistered-alias")
        with self.assertRaises(BindingError):
            binding.verify()

    def test_shared_verifier_gap_data_only_allows_missing_model_volume(self):
        """I1b role-aware verification is not implemented in provisional I1."""
        fixture = self.fixture(models="/mnt/models", split=True)
        binding = fixture.binding()
        fixture.runner.blocks[5]["mountpoints"] = [None]
        result = binding.verify(roles=("data",))
        self.assertEqual(result["data"]["uuid"], "data-uuid")

    def test_hidden_submount_rejected_for_existing_and_missing_descendants(self):
        fixture = self.fixture()
        binding = fixture.binding()
        hidden = fixture.data + "/services/llm-manager"
        fixture.local(hidden).mkdir()
        fixture.runner.add_disk("/dev/sdd", "8:48", "/dev/sdd1", "8:49", "hidden-uuid", hidden)
        for suffix in ("llm-manager", "llm-manager/absent/nested/state.json"):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(BindingError, "unregistered_mount"):
                binding.validate_path("services", binding.path("services", suffix))
        self.assertFalse(fixture.local(hidden + "/absent").exists())

    def test_symlink_ancestor_and_unsafe_suffixes_rejected_before_access(self):
        fixture = self.fixture()
        binding = fixture.binding()
        fixture.local(fixture.data + "/services/alias").symlink_to(fixture.local(fixture.data + "/logs"))
        with self.assertRaises(BindingError):
            binding.validate_path("services", binding.path("services", "alias/new.json"))
        for suffix in ("/root", "../other", "a/../b", "a//b", "a/", ".", "a/./b", "a,b", "a\\b", "a%u", "a\nb", "a$b"):
            with self.subTest(suffix=suffix), self.assertRaises(BindingError):
                binding.path("services", suffix)
        with self.assertRaises(BindingError):
            binding.validate_path("services", "/srv/ai/services-other/state.json")

    def test_registry_and_role_permissions_remain_shared_validator_owned(self):
        fixture = self.fixture()
        for path in (fixture.registry_path, fixture.data + "/services"):
            local = fixture.local(path)
            original = local.stat().st_mode & 0o777
            local.chmod(0o666 if local.is_file() else 0o777)
            with self.assertRaises(BindingError):
                fixture.binding()
            local.chmod(original)
        original_stat = Path.stat
        registry = fixture.local(fixture.registry_path)

        def wrong_owner(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == registry:
                values = list(result)
                values[4] = os.geteuid() + 1
                return os.stat_result(values)
            return result

        with patch.object(Path, "stat", wrong_owner), self.assertRaises(BindingError):
            fixture.binding()

    def test_private_json_reader_rejects_fifo_links_modes_and_oversize(self):
        fixture = self.fixture()
        binding = fixture.binding()
        path = binding.path("services", "llm-manager/state.json")
        local = fixture.jsonfile(path, {"safe": True})
        self.assertEqual(binding.read_json("services", path), {"safe": True})
        for mode in (0o400, 0o640, 0o644, 0o700):
            local.chmod(mode)
            with self.assertRaises(BindingError):
                binding.read_json("services", path)
        local.chmod(0o600)
        with self.assertRaises(BindingError):
            binding.read_json("services", path, maximum=2)
        os.link(local, local.with_name("hardlink.json"))
        with self.assertRaises(BindingError):
            binding.read_json("services", path)
        local.unlink()
        os.mkfifo(local, 0o600)
        with self.assertRaises(BindingError):
            binding.read_json("services", path)

    def test_historical_registration_does_not_rewrite_instance_or_evidence(self):
        fixture = self.fixture(data="/data", models="/data/models-large", split=True)
        paths = {
            "/data/services/llm-manager/deployment-instance.json": {"id": "retained-instance", "runtime_evidence": {"kept": True}},
            "/data/services/llm-manager/active/active.json": {"schema_version": 2, "desired": "running", "container": {"id": "retained"}},
            "/data/services/llm-manager/acquisition/complete.json": {"model_root": "/data/models-large/qwen3-coder-next-fp8"},
        }
        before = {path: fixture.jsonfile(path, value).read_bytes() for path, value in paths.items()}
        binding = fixture.binding()
        self.assertEqual(binding.path("models", "qwen3-coder-next-fp8"), "/data/models-large/qwen3-coder-next-fp8")
        self.assertEqual(before, {path: fixture.local(path).read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
