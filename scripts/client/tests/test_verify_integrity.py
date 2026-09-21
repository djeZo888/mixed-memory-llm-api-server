"""Offline source/cache integrity regressions; no package install or inference."""

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))
import client_common as common
import verify_integrity as integrity


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="client-integrity-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir(mode=0o700)
        self.prefix = self.root / "prefix"
        self.prefix.mkdir(mode=0o700)
        for name in ("bin", "xdg", "xdg/config", "xdg/data", "xdg/cache", "xdg/state", "xdg/config/opencode",
                     "npm", "npm/cache", "npm/logs", "tmp", "bun-cache", "managed", "discovery-home"):
            (self.prefix / name).mkdir(mode=0o700)
        self.runtime = common.runtime_dir(self.prefix)
        self.lock = {"packages": {"": {"version": "0.0.0"}}}
        self.cache_paths = []
        for package in ("opencode-ai", "@opencode-ai/plugin", common.native_package()):
            self.add_package(package)
        self.lock["packages"]["node_modules/absent-optional"] = {"optional": True, "integrity": "unused"}
        self.settings = {"version": common.VERSION, "base_url": "http://127.0.0.1:30002/v1", "model": "glm-5.3",
                         "auth": {"kind": "disabled"}, "context_tokens": 12000, "output_tokens": 1000,
                         "lock_sha256": ""}
        self.source.joinpath("launch.py").write_bytes(b"reviewed launcher\n")
        self.source.joinpath("client_common.py").write_bytes(b"reviewed common\n")
        self.source.joinpath("package.json").write_bytes(b'{"private":true}\n')
        for target, origin in ((self.prefix / "bin/opencode-client", "launch.py"),
                               (self.prefix / "bin/client_common.py", "client_common.py"),
                               (self.runtime / "package.json", "package.json")):
            self.write(target, (self.source / origin).read_bytes())
        self.save_lock()
        self.save_settings()
        patch = mock.patch.object(integrity, "SOURCE", self.source)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(data)
        path.chmod(0o600)

    def add_package(self, name, members=None):
        if members is None:
            members = {"package.json": json.dumps({"version": common.VERSION}).encode(),
                       "bin/opencode" if name == common.native_package() else "lib/index.js": b"reviewed contents\n"}
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for relative, data in members.items():
                header = tarfile.TarInfo("package/" + relative)
                header.size = len(data)
                tar.addfile(header, io.BytesIO(data))
                self.write(self.runtime / "node_modules" / name / relative, data)
        data = buffer.getvalue()
        sha = hashlib.sha512(data).digest()
        digest = sha.hex()
        cache = self.prefix / "npm/cache/_cacache/content-v2/sha512" / digest[:2] / digest[2:4] / digest[4:]
        self.write(cache, data)
        self.cache_paths.append(cache)
        self.lock["packages"]["node_modules/" + name] = {
            "version": common.VERSION, "integrity": "sha512-" + base64.b64encode(sha).decode()}

    def save_lock(self):
        lock = json.dumps(self.lock).encode()
        self.write(self.source / "package-lock.json", lock)
        self.write(self.runtime / "package-lock.json", lock)
        self.settings["lock_sha256"] = hashlib.sha256(lock).hexdigest()

    def save_settings(self):
        self.write(self.prefix / "bootstrap.json", json.dumps(self.settings).encode())
        self.write(self.prefix / "opencode.json", common.json_bytes(common.config_for(self.settings)))
        self.write(self.prefix / "models.json", b"{}\n")

    def check(self):
        return integrity.verify_client(self.prefix)

    def test_valid_bytes_are_verified_without_execution_network_or_mutation(self):
        before = {path: (path.stat().st_mtime_ns, path.read_bytes())
                  for path in self.prefix.rglob("*") if path.is_file()}
        with mock.patch("subprocess.run", side_effect=AssertionError("must never execute")):
            settings, evidence = self.check()
        self.assertEqual(settings, self.settings)
        self.assertEqual(evidence["packages_verified"], 3)
        self.assertEqual(evidence["files_verified"], 6)
        self.assertEqual(evidence["status"], "pass")
        self.assertEqual(before, {path: (path.stat().st_mtime_ns, path.read_bytes())
                                 for path in self.prefix.rglob("*") if path.is_file()})

    def test_installed_code_and_lock_tampering_fail(self):
        for relative in ("bin/opencode-client", "bin/client_common.py", "xdg/config/opencode/package-lock.json",
                         "xdg/config/opencode/package.json", "xdg/config/opencode/node_modules/opencode-ai/lib/index.js",
                         "xdg/config/opencode/node_modules/" + common.native_package() + "/bin/opencode"):
            path = self.prefix / relative
            original = path.read_bytes()
            path.write_bytes(b"tampered")
            with self.subTest(path=relative), self.assertRaises(common.ClientError):
                self.check()
            path.write_bytes(original)

    def test_cache_must_exist_and_match_reviewed_integrity(self):
        path = self.cache_paths[0]
        original = path.read_bytes()
        for data in (None, b"corrupt gzip archive"):
            path.unlink()
            if data is not None:
                self.write(path, data)
            with self.subTest(kind=data is None), self.assertRaises(common.ClientError):
                self.check()
            if not path.exists():
                self.write(path, original)
        self.write(path, original)

    def test_extra_files_packages_and_links_are_refused(self):
        package = self.runtime / "node_modules/opencode-ai"
        extra = package / "injected.js"
        self.write(extra, b"extra")
        with self.assertRaises(common.ClientError):
            self.check()
        extra.unlink()
        extra = self.runtime / "node_modules/unreviewed"
        extra.mkdir(mode=0o700)
        with self.assertRaises(common.ClientError):
            self.check()
        extra.rmdir()
        path = package / "lib/index.js"
        contents = path.read_bytes()
        path.unlink()
        external = self.root / "external.js"
        self.write(external, contents)
        path.symlink_to(external)
        with self.assertRaises(common.ClientError):
            self.check()
        path.unlink()
        os.link(external, path)
        with self.assertRaises(common.ClientError):
            self.check()

    def test_symlink_ancestor_and_writable_installed_file_are_refused(self):
        package = self.runtime / "node_modules/opencode-ai"
        lib = package / "lib"
        lib.rename(package / "moved-lib")
        lib.symlink_to(package / "moved-lib", target_is_directory=True)
        with self.assertRaises(common.ClientError):
            self.check()
        lib.unlink()
        (package / "moved-lib").rename(lib)
        (lib / "index.js").chmod(0o666)
        with self.assertRaises(common.ClientError):
            self.check()

    def test_changed_configuration_cannot_bypass_endpoint_and_schema_checks(self):
        for key, value in (("base_url", "http://192.0.2.1:30002/v1"), ("context_tokens", True),
                           ("output_tokens", 12000), ("lock_sha256", "0" * 64),
                           ("unexpected", "synthetic-secret-never-shown")):
            original = dict(self.settings)
            self.settings[key] = value
            # Tamper after valid setup; config_for correctly refuses invalid input.
            self.write(self.prefix / "bootstrap.json", json.dumps(self.settings).encode())
            with self.subTest(field=key), self.assertRaises(common.ClientError) as result:
                self.check()
            self.assertNotIn("synthetic-secret", str(result.exception))
            self.settings = original
            self.save_settings()

    def test_missing_required_package_and_bounded_work_fail(self):
        missing = self.runtime / "node_modules/required-not-installed"
        self.lock["packages"][str(missing.relative_to(self.runtime))] = {"integrity": "unused"}
        self.save_lock()
        self.save_settings()
        with self.assertRaises(common.ClientError):
            self.check()
        self.lock["packages"].pop(str(missing.relative_to(self.runtime)))
        self.save_lock()
        self.save_settings()
        for field, value in (("MAX_TOTAL", 1), ("MAX_MEMBERS", 1), ("SECONDS", -1)):
            with self.subTest(bound=field), mock.patch.object(integrity, field, value):
                with self.assertRaises(common.ClientError):
                    self.check()

    def test_config_fifo_and_oversized_json_are_refused_before_existing_reader(self):
        path = self.runtime / "node_modules/opencode-ai/package.json"
        original = path.read_bytes()
        path.unlink()
        os.mkfifo(path, 0o600)
        with self.assertRaises(common.ClientError):
            self.check()
        path.unlink()
        self.write(path, b" " * (1024 * 1024 + 1))
        with self.assertRaises(common.ClientError):
            self.check()
        self.write(path, original)

    def test_caller_deadline_cannot_expand_bound_or_be_nonpositive(self):
        for timeout in (0, -1, 31, float("inf"), float("nan"), True):
            with self.subTest(timeout=timeout), self.assertRaises(common.ClientError):
                integrity.verify_client(self.prefix, timeout=timeout)
        self.assertEqual(integrity.verify_client(self.prefix, timeout=5)[1]["status"], "pass")

    def test_cached_tar_never_extracts_traversal_or_links(self):
        package = self.runtime / "node_modules/opencode-ai"
        for kind in ("traversal", "link"):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
                member = tarfile.TarInfo("package/../outside" if kind == "traversal" else "package/link")
                if kind == "link":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "../../outside"
                tar.addfile(member)
            data = buffer.getvalue()
            sha = hashlib.sha512(data).digest()
            digest = sha.hex()
            cache = self.prefix / "npm/cache/_cacache/content-v2/sha512" / digest[:2] / digest[2:4] / digest[4:]
            self.write(cache, data)
            entry = {"integrity": "sha512-" + base64.b64encode(sha).decode()}
            with self.subTest(kind=kind), self.assertRaises(common.ClientError):
                integrity._package(package, entry, self.prefix, [0, float("inf"), 0])
            self.assertFalse((self.runtime / "node_modules/outside").exists())


if __name__ == "__main__":
    unittest.main()
