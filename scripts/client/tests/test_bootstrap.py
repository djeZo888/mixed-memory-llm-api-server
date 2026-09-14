"""Offline bootstrap regressions; optional installed checks never run inference.

Run with Python's unittest discovery. Set V0_CLIENT_PREFIX to opt into checks
of an already installed task-local CLI; this suite never downloads packages.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


CLIENT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v0_client_common_tests", CLIENT / "client_common.py")
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)


def snapshot(root):
    """Capture names, modes, mtimes and contents without following symlinks."""
    result = {}
    for path in [root] + sorted(root.rglob("*")):
        info = path.lstat()
        contents = None
        if stat.S_ISLNK(info.st_mode):
            contents = os.readlink(path)
        elif stat.S_ISREG(info.st_mode):
            contents = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(root))] = (info.st_mode, info.st_mtime_ns, contents)
    return result


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v0-client-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.prefix = self.root / "client spaces & punctuation {literal}"

    def cli(self, *extra, auth=None, prefix=None, base_url="http://127.0.0.1:30002/v1", model="Qwen/Qwen3.6-35B-A3B"):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, str(CLIENT / "bootstrap.py"),
             "--prefix", str(prefix or self.prefix), "--base-url", base_url,
             "--model", model, "--context-tokens", "32768", "--output-tokens", "2048",
             *(auth if auth is not None else ["--auth-disabled"]), *extra],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=20,
        )

    def assert_rejected_without_mutation(self, **kwargs):
        before = snapshot(self.root)
        result = self.cli("--dry-run", **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, snapshot(self.root))
        return result

    def test_help_is_offline_and_does_not_write(self):
        before = snapshot(self.root)
        result = subprocess.run([sys.executable, str(CLIENT / "bootstrap.py"), "--help"],
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                cwd=self.root, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--api-key-file", result.stdout)
        self.assertEqual(before, snapshot(self.root))

    def test_dry_run_new_prefix_preserves_tree_and_calling_environment(self):
        before = snapshot(self.root)
        environment = dict(os.environ)
        result = self.cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["prefix"], str(self.prefix))
        self.assertEqual(plan["action"], "install")
        self.assertFalse(plan["mutations"])
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(environment, dict(os.environ))
        self.assertFalse(self.prefix.exists())

    def test_existing_empty_private_prefix_remains_empty(self):
        self.prefix.mkdir(mode=0o700)
        before = snapshot(self.root)
        result = self.cli("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, snapshot(self.root))

    def test_nonexistent_key_reference_with_spaces_and_punctuation_is_not_loaded(self):
        reference = self.root / 'private key {file:literal} "quoted" & dollar$'
        before = snapshot(self.root)
        result = self.cli("--dry-run", auth=["--api-key-file", str(reference)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["auth_kind"], "file")
        self.assertNotIn(str(reference), result.stdout + result.stderr)
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse(reference.exists())

    def test_environment_reference_requires_name_and_never_loads_value_for_plan(self):
        secret = "synthetic-value-never-to-be-printed"
        with mock.patch.dict(os.environ, {"V0_TEST_SECRET_REF": secret}):
            result = self.cli("--dry-run", auth=["--api-key-env", "V0_TEST_SECRET_REF"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["auth_kind"], "env")
        for invalid in ("V0_TEST_SECRET_REF=" + secret, "HOME", "CODEX_HOME", "OPENCODE_CONFIG", "XDG_DATA_HOME"):
            with self.subTest(reference=invalid.split("=", 1)[0]):
                rejected = self.assert_rejected_without_mutation(auth=["--api-key-env", invalid])
                self.assertNotIn(secret, rejected.stdout + rejected.stderr)

    def test_localhost_urls_are_exact_and_credential_free(self):
        for value in ("http://localhost:8080/v1", "https://[::1]:30002/v1"):
            with self.subTest(url=value):
                result = self.cli("--dry-run", base_url=value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["base_url"], value)
        for value in ("http://127.0.0.1/v1", "http://127.0.0.1:0/v1", "http://127.0.0.1:65536/v1",
                      "http://0.0.0.0:30002/v1", "https://example.org:443/v1", "ftp://localhost:30002/v1",
                      "http://localhost:30002/v1/", "http://localhost:30002/v1?key=synthetic",
                      "http://localhost:30002/v1#fragment", "http://localhost:30002/{env:OTHER}"):
            with self.subTest(url=value):
                self.assert_rejected_without_mutation(base_url=value)
        rejected = self.assert_rejected_without_mutation(base_url="http://test:synthetic-password@localhost:30002/v1")
        self.assertNotIn("synthetic-password", rejected.stdout + rejected.stderr)

    def test_unmanaged_nonempty_prefix_is_refused(self):
        self.prefix.mkdir(mode=0o700)
        (self.prefix / "important-user-file").write_bytes(b"must remain untouched")
        self.assert_rejected_without_mutation()

    def test_symlink_prefix_is_refused_without_touching_target(self):
        target = self.root / "target"
        target.mkdir(mode=0o700)
        self.prefix.symlink_to(target, target_is_directory=True)
        self.assert_rejected_without_mutation()

    def test_insecure_or_relative_prefix_is_refused(self):
        self.prefix.mkdir(mode=0o755)
        self.prefix.chmod(0o755)
        self.assert_rejected_without_mutation()
        self.assert_rejected_without_mutation(prefix="relative-client")

    def test_relative_key_reference_is_refused(self):
        self.assert_rejected_without_mutation(auth=["--api-key-file", "relative-key"])

    def test_model_interpolation_and_shell_text_are_refused(self):
        for model in ("{env:OTHER_MODEL}", "model with spaces", "model;echo unsafe", "model\nother"):
            with self.subTest(model=model):
                self.assert_rejected_without_mutation(model=model)

    def test_token_limits_must_be_ordered(self):
        before = snapshot(self.root)
        for options in (("--output-tokens", "32768"), ("--context-tokens", "0"), ("--output-tokens", "-1")):
            result = self.cli("--dry-run", *options)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, snapshot(self.root))

    def test_missing_managed_directory_is_refused_without_plan_repair(self):
        # Minimal existing-install fixture: verification must reject incomplete
        # private state before any native executable or network activity occurs.
        self.prefix.mkdir(mode=0o700)
        for name in ("bin", "xdg", "xdg/config", "xdg/data", "xdg/cache", "xdg/state", "xdg/config/opencode",
                     "npm", "npm/cache", "npm/logs", "tmp", "bun-cache", "discovery-home"):
            (self.prefix / name).mkdir(mode=0o700)
        settings = {
            "version": common.VERSION, "base_url": "http://127.0.0.1:30002/v1",
            "model": "Qwen/Qwen3.6-35B-A3B", "auth": {"kind": "disabled"},
            "context_tokens": 32768, "output_tokens": 2048,
            "lock_sha256": hashlib.sha256((CLIENT / "package-lock.json").read_bytes()).hexdigest(),
        }
        for name, data in (("bootstrap.json", settings), ("opencode.json", common.config_for(settings)), ("models.json", {})):
            target = self.prefix / name
            target.write_text(json.dumps(data))
            target.chmod(0o600)
        for package in ("opencode-ai", "@opencode-ai/plugin", common.native_package()):
            directory = common.runtime_dir(self.prefix) / "node_modules" / package
            directory.mkdir(parents=True, mode=0o700)
            (directory / "package.json").write_text(json.dumps({"version": common.VERSION}))
        self.assert_rejected_without_mutation()


class CredentialAndConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v0-key-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)

    def key_file(self, value):
        path = self.root / 'key file & punctuation {literal} "quotes"'
        path.write_bytes(value)
        path.chmod(0o600)
        return path

    def test_key_bytes_survive_json_and_file_interpolation_without_mutation(self):
        raw = b'synthetic-"\\-{file:/never-read-this}-{env:NEVER_READ_THIS}-end'
        path = self.key_file(raw)
        before = snapshot(self.root)
        encoded = common.load_key({"kind": "file", "reference": str(path)})
        self.assertNotIn("{file:", encoded)
        self.assertNotIn("{env:", encoded)
        resolved = json.loads('{"apiKey":"' + encoded + '"}')
        self.assertEqual(resolved["apiKey"].encode("ascii"), raw)
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(path.read_bytes(), raw)

    def test_newlines_whitespace_and_invalid_key_bytes_are_refused_not_trimmed(self):
        for raw in (b"", b"synthetic\n", b"synthetic\r\n", b" synthetic", b"synthetic ", b"a\tb", b"\x00", b"\xff", b"x" * 8193):
            with self.subTest(kind=repr(raw[:12])):
                path = self.key_file(raw)
                with self.assertRaises(common.ClientError):
                    common.load_key({"kind": "file", "reference": str(path)})
                self.assertEqual(path.read_bytes(), raw)

    def test_missing_key_directory_is_not_created_by_key_loading(self):
        before = snapshot(self.root)
        with self.assertRaises((common.ClientError, OSError)):
            common.load_key({"kind": "file", "reference": str(self.root / "absent-parent" / "key")})
        self.assertEqual(before, snapshot(self.root))

    def test_symlink_hardlink_and_public_key_files_are_refused(self):
        path = self.key_file(b"synthetic-key")
        link = self.root / "linked"
        link.symlink_to(path)
        with self.assertRaises(common.ClientError):
            common.load_key({"kind": "file", "reference": str(link)})
        link.unlink()
        os.link(path, link)
        with self.assertRaises(common.ClientError):
            common.load_key({"kind": "file", "reference": str(path)})
        link.unlink()
        path.chmod(0o644)
        with self.assertRaises(common.ClientError):
            common.load_key({"kind": "file", "reference": str(path)})
        self.assertEqual(path.read_bytes(), b"synthetic-key")

    def test_environment_key_preserves_punctuation_and_missing_reference_fails(self):
        with mock.patch.dict(os.environ, {"V0_TEST_REFERENCE": 'synthetic-"\\-{file:literal}'}, clear=True):
            encoded = common.load_key({"kind": "env", "reference": "V0_TEST_REFERENCE"})
            self.assertEqual(json.loads('"' + encoded + '"'), os.environ["V0_TEST_REFERENCE"])
            with self.assertRaises(common.ClientError):
                common.load_key({"kind": "env", "reference": "V0_ABSENT_REFERENCE"})

    def test_config_keeps_one_exact_local_model_and_no_literal_secret(self):
        settings = {"model": "vendor/model:Q4_K_M", "base_url": "http://localhost:30002/v1",
                    "auth": {"kind": "file", "reference": str(self.root / "nonexistent key")},
                    "context_tokens": 16384, "output_tokens": 1024}
        config = json.loads(common.json_bytes(common.config_for(settings)))
        self.assertEqual(config["enabled_providers"], ["local"])
        self.assertEqual(config["model"], "local/vendor/model:Q4_K_M")
        self.assertEqual(config["small_model"], config["model"])
        self.assertEqual(set(config["provider"]), {"local"})
        local = config["provider"]["local"]
        self.assertEqual(local["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(local["options"]["baseURL"], settings["base_url"])
        self.assertEqual(set(local["models"]), {settings["model"]})
        self.assertEqual(local["models"][settings["model"]]["limit"], {"context": 16384, "output": 1024})
        self.assertTrue(local["options"]["apiKey"].startswith("{env:"))
        self.assertNotIn(settings["auth"]["reference"], json.dumps(config))
        self.assertFalse(config["autoupdate"])
        self.assertEqual(config["share"], "disabled")
        self.assertEqual(config["permission"]["external_directory"], "deny")
        self.assertEqual(config["permission"]["bash"], "ask")
        settings["auth"] = {"kind": "disabled"}
        self.assertNotIn("apiKey", common.config_for(settings)["provider"]["local"]["options"])

    def test_child_environment_scrubs_cloud_settings_and_keeps_home_unchanged(self):
        fake = {"OPENAI_API_KEY": "synthetic", "ANTHROPIC_API_KEY": "synthetic",
                "AWS_SECRET_ACCESS_KEY": "synthetic", "GH_TOKEN": "synthetic", "GITHUB_TOKEN": "synthetic",
                "CODEX_HOME": "/synthetic/codex", "OPENCODE_CONFIG_CONTENT": '{"provider":{"cloud":{}}}',
                "npm_config_userconfig": "/synthetic/npm-auth", "NODE_OPTIONS": "--require /synthetic/unsafe",
                "HTTP_PROXY": "http://synthetic-proxy", "BASH_ENV": "/synthetic/shell", "PYTHONPATH": "/synthetic/python"}
        with mock.patch.dict(os.environ, fake):
            before = dict(os.environ)
            child = common.isolated_env(self.root)
            self.assertEqual(before, dict(os.environ))
            self.assertEqual(child.get("HOME"), os.environ.get("HOME"))
            for name in fake:
                if name == "npm_config_userconfig":
                    self.assertEqual(child[name], str(self.root / "npm" / "userconfig"))
                else:
                    self.assertNotIn(name, child)
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "npm_config_cache", "npm_config_logs_dir"):
            self.assertTrue(Path(child[name]).is_relative_to(self.root), name)
        for name in ("OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_MODELS_FETCH", "OPENCODE_DISABLE_EXTERNAL_SKILLS"):
            self.assertEqual(child[name], "1")


@unittest.skipUnless(os.environ.get("V0_CLIENT_PREFIX"), "Set V0_CLIENT_PREFIX only for an existing isolated installation")
class InstalledClientTests(unittest.TestCase):
    def test_installed_cli_version_and_config_without_inference(self):
        prefix = Path(os.environ["V0_CLIENT_PREFIX"])
        launcher = prefix / "bin" / "opencode-client"
        with tempfile.TemporaryDirectory(prefix="v0-installed-workspace-") as directory:
            workspace = Path(directory).resolve()
            for command in ("version", "check"):
                result = subprocess.run([sys.executable, str(launcher), "--workspace", str(workspace), command],
                                        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                        capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, command + ": " + result.stderr)
                if command == "version":
                    self.assertEqual(result.stdout.strip(), common.VERSION)
                else:
                    self.assertIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
