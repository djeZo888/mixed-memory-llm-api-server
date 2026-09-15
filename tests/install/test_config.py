"""Strict user input and role boundaries; no network, mounts or package changes."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install.config import absolute, load, validate
from install.core import InstallError

SERVER = {"role": "server", "profile": "flagship-hybrid", "model_set": "glm", "data_dir": "/srv/ai"}
CLIENT = {"role": "client", "client_user": "developer", "client_workspace": "/home/developer/work",
          "client_prefix": "/home/developer/.local/local-ai", "client_base_url": "http://127.0.0.1:30000/v1",
          "client_model": "local/glm-5.3", "client_key_file": "/home/developer/.config/local-ai/api-key"}


class ConfigTests(unittest.TestCase):
    def test_server_requires_explicit_profile_and_matching_model_set(self):
        for config in ({}, {**SERVER, "profile": None}, {**SERVER, "model_set": None},
                       {**SERVER, "model_set": "qwen"}, {**SERVER, "profile": "fast-gpu", "model_set": "glm"}):
            with self.subTest(config=config), self.assertRaises(InstallError):
                validate(config)
        self.assertEqual(validate(SERVER)["model_dir"], "/srv/ai/models")
        self.assertEqual(validate({**SERVER, "model_set": "glm,qwen"})["model_set"], "glm,qwen")

    def test_roles_and_combined_require_all_selected_inputs(self):
        self.assertEqual(validate(CLIENT)["role"], "client")
        combined = {**SERVER, **CLIENT, "role": "combined"}
        self.assertEqual(validate(combined)["role"], "combined")
        for config in ({**SERVER, "role": "unknown"}, {**SERVER, "role": "combined"},
                       {**CLIENT, "role": "combined"}):
            with self.assertRaises(InstallError):
                validate(config)

    def test_ordinary_client_user_and_explicit_workspace_required(self):
        for user in ("root", "", "-developer", "developer;id", "0", None):
            with self.subTest(user=user), self.assertRaises(InstallError):
                validate({**CLIENT, "client_user": user})
        for key in ("client_workspace", "client_prefix", "client_base_url", "client_model", "client_key_file"):
            with self.subTest(key=key), self.assertRaises(InstallError):
                validate({**CLIENT, key: None})

    def test_client_urls_are_explicit_loopback_without_embedded_secrets(self):
        for url in ("http://127.0.0.1:30000/v1", "http://[::1]:30000/v1"):
            self.assertEqual(validate({**CLIENT, "client_base_url": url})["client_base_url"], url)
        for url in ("https://127.0.0.1:30000/v1", "http://example.org:30000/v1", "http://0.0.0.0:30000/v1",
                    "http://127.0.0.1/v1", "http://127.0.0.1:0/v1", "http://127.0.0.1:70000/v1",
                    "http://127.0.0.1:30000/v1/", "http://user:fixture_private_sentinel@127.0.0.1:30000/v1",
                    "http://127.0.0.1:30000/v1?api_key=fixture_private_sentinel", "http://127.0.0.1:30000/v1#secret",
                    "http://127.0.0.1.example.org:30000/v1", "http://2130706433:30000/v1"):
            with self.subTest(url=url), self.assertRaises(InstallError) as caught:
                validate({**CLIENT, "client_base_url": url})
            self.assertNotIn("fixture_private_sentinel", str(caught.exception))

    def test_paths_reject_traversal_shell_text_and_reserved_data_roots(self):
        for path in ("relative", "/", "/data/../root", "/data//models", "/data/", "/data/./models",
                     "/data;touch", "/data/$(id)", "/data with spaces", "//data"):
            self.assertFalse(absolute(path), path)
        for path in ("/etc", "/usr/data", "/home/developer/data", "/root/data", "/var/lib/ai", "/tmp/data", "/dev/storage"):
            with self.subTest(path=path), self.assertRaises(InstallError):
                validate({**SERVER, "data_dir": path})

    def test_numeric_budgets_are_bounded_and_bool_is_not_integer(self):
        for key, value in (("schema_version", True), ("schema_version", 2), ("expected_gpu_count", True),
                           ("expected_gpu_count", 0), ("expected_gpu_count", 17), ("root_min_free_bytes", 1),
                           ("root_package_budget_bytes", -1), ("root_package_budget_bytes", 2**40),
                           ("context_tokens", 512), ("output_tokens", 32769), ("output_tokens", 8192)):
            with self.subTest(key=key, value=value), self.assertRaises(InstallError):
                validate({**SERVER, key: value})

    def test_storage_mount_uuid_and_destructive_identity_are_explicit(self):
        for config in ({**SERVER, "storage_mode": "mount"},
                       {**SERVER, "data_uuid": "UUID=invalid"},
                       {**SERVER, "storage_mode": "initialize", "initialize_empty_disk": "/dev/sdb", "confirm_disk_id": "sdb"},
                       {**SERVER, "storage_mode": "initialize", "initialize_empty_disk": "/dev/disk/by-id/fixture", "confirm_disk_id": "other"},
                       {**SERVER, "initialize_empty_disk": "/dev/disk/by-id/fixture", "confirm_disk_id": "fixture"},
                       {**SERVER, "disk_plan": "/srv/ai/plan.json"}):
            with self.subTest(config=config), self.assertRaises(InstallError):
                validate(config)
        self.assertEqual(validate({**SERVER, "storage_mode": "mount", "data_uuid": "10000000-0000-4000-8000-000000000001"})["storage_mode"], "mount")
        self.assertEqual(validate({**SERVER, "storage_mode": "initialize", "initialize_empty_disk": "/dev/disk/by-id/fixture", "confirm_disk_id": "fixture"})["storage_mode"], "initialize")

    def test_unknown_secret_and_execution_hook_fields_rejected(self):
        for field in ("api_key", "hf_token", "shell_command", "after_install", "env", "data_uuid_override"):
            with self.subTest(field=field), self.assertRaises(InstallError) as caught:
                validate({**SERVER, field: "fixture_private_sentinel"})
            self.assertNotIn("fixture_private_sentinel", str(caught.exception))

    def test_wrong_types_fail_with_sanitized_install_error(self):
        for config in (None, [], "secret", {**SERVER, "role": []}, {**SERVER, "profile": {}},
                       {**SERVER, "model_set": []}, {**SERVER, "data_dir": None},
                       {**SERVER, "storage_mode": []}, {**SERVER, "ssh_host": []},
                       {**CLIENT, "client_model": 17}, {**CLIENT, "client_base_url": 17}):
            with self.subTest(config=config), self.assertRaises(InstallError):
                validate(config)

    def test_ssh_host_rejects_options_commands_and_credentials(self):
        for host in ("-oProxyCommand=bad", "vm;id", "user@vm password", "vm\n-oProxyCommand=bad"):
            with self.subTest(host=host), self.assertRaises(InstallError):
                validate({**CLIENT, "ssh_host": host})
        self.assertEqual(validate({**CLIENT, "ssh_host": "developer@vm.example.org"})["ssh_host"], "developer@vm.example.org")


class ConfigFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".install-config-test-", dir=REPO)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"

    def test_duplicate_top_level_and_nested_keys_rejected(self):
        for text in ('{"role":"server","role":"client"}', '{"unknown":{"value":1,"value":2}}'):
            self.path.write_text(text)
            with self.assertRaisesRegex(InstallError, "invalid_config_file"):
                load(self.path)

    def test_size_invalid_json_and_missing_file_rejected_without_content(self):
        for text in ('{"bad":fixture_private_sentinel}', ' ' * 65537):
            self.path.write_text(text)
            with self.assertRaises(InstallError) as caught:
                load(self.path)
            self.assertNotIn("fixture_private_sentinel", str(caught.exception))
        self.path.unlink()
        with self.assertRaises(InstallError):
            load(self.path)

    def test_valid_config_roundtrip_does_not_write(self):
        self.path.write_text(json.dumps(SERVER))
        before, mtime = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.assertEqual(load(self.path), SERVER)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)


if __name__ == "__main__":
    unittest.main()
