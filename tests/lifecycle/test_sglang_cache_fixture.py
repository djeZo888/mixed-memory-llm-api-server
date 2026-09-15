"""Worker-only safety tests for the deferred actual-image cache helper.

Temporary files live under a worker temporary directory. Installed resolvers,
Linux isolation and /cache are never used as real probe targets in this suite.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "f1c_cache_helper_tests", ROOT / "tests/lifecycle/sglang_fixture/check_cache_paths.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class TemporaryCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="f1c-cache-test-", dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.cache = self.directory / "cache"
        self.cache.mkdir(mode=0o700)
        self.outside = self.directory / "outside"
        self.outside.mkdir()
        self.sentinel = self.outside / "preserved"
        self.sentinel.write_bytes(b"outside content must survive")
        self.token = "0123456789abcdef"
        self.probe_name = ".f1c-cache-probe-" + self.token

    def assert_outside_preserved(self):
        self.assertEqual(self.sentinel.read_bytes(), b"outside content must survive")
        self.assertEqual(list(self.outside.iterdir()), [self.sentinel])

    def test_checked_path_accepts_canonical_root_and_descendants(self):
        for value in (self.cache, str(self.cache / "new" / "child")):
            self.assertEqual(helper.checked_path(value, root=self.cache), Path(value))
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_lexical_escapes_sibling_prefixes_and_symlinks_refused_without_writes(self):
        link = self.cache / "escape"
        link.symlink_to(self.outside, target_is_directory=True)
        local_link = self.cache / "local-link"
        local_link.symlink_to(self.cache, target_is_directory=True)
        invalid = (
            "relative/path", "", str(self.cache) + "/../outside/new",
            str(self.cache) + "-sibling/new", str(self.cache) + "/./new",
            str(self.cache) + "//new", str(self.cache) + "/new/",
            str(self.cache) + "/new\n", self.outside / "new",
            link / "new", local_link / "new",
        )
        for value in invalid:
            with self.subTest(value=value), mock.patch.object(helper.os, "open") as opened, \
                 mock.patch.object(helper.os, "mkdir") as mkdir:
                with self.assertRaises(helper.CacheFailure):
                    helper.probe_directory(value, root=self.cache)
                opened.assert_not_called()
                mkdir.assert_not_called()
            self.assert_outside_preserved()
        self.assertEqual(set(self.cache.iterdir()), {link, local_link})

    def test_probe_creates_fsyncs_reads_and_removes_one_bounded_owned_file(self):
        target = self.cache / "nested" / "resolver"
        real_open, real_write = os.open, os.write
        real_fsync, real_read = os.fsync, os.read
        with mock.patch.object(helper.secrets, "token_hex", return_value=self.token), \
             mock.patch.object(helper.os, "open", wraps=real_open) as opened, \
             mock.patch.object(helper.os, "write", wraps=real_write) as written, \
             mock.patch.object(helper.os, "fsync", wraps=real_fsync) as synced, \
             mock.patch.object(helper.os, "read", wraps=real_read) as read:
            helper.probe_directory(target, root=self.cache)
        self.assertTrue(target.is_dir())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
        self.assertEqual(list(target.iterdir()), [])
        written.assert_called_once()
        self.assertEqual(written.call_args.args[1], helper.PROBE_BYTES)
        self.assertLessEqual(len(helper.PROBE_BYTES), 128)
        synced.assert_called_once_with(written.call_args.args[0])
        read.assert_called_once_with(written.call_args.args[0], len(helper.PROBE_BYTES) + 1)
        file_calls = [call for call in opened.call_args_list if call.args[0] == self.probe_name]
        self.assertEqual(len(file_calls), 1)
        self.assertEqual(file_calls[0].args[1], os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW)
        self.assertEqual(file_calls[0].args[2], 0o600)
        self.assertIn("dir_fd", file_calls[0].kwargs)
        self.assert_outside_preserved()

    def test_existing_filename_collision_is_preserved(self):
        collision = self.cache / self.probe_name
        collision.write_bytes(b"preexisting collision")
        with mock.patch.object(helper.secrets, "token_hex", return_value=self.token), \
             mock.patch.object(helper.os, "write") as write, \
             mock.patch.object(helper.os, "fsync") as fsync, \
             mock.patch.object(helper.os, "unlink") as unlink:
            with self.assertRaises(FileExistsError):
                helper.probe_directory(self.cache, root=self.cache)
            write.assert_not_called()
            fsync.assert_not_called()
            unlink.assert_not_called()
        self.assertEqual(collision.read_bytes(), b"preexisting collision")
        self.assertEqual(list(self.cache.iterdir()), [collision])
        self.assert_outside_preserved()

    def test_replaced_probe_is_refused_and_replacement_preserved(self):
        path = self.cache / self.probe_name
        moved = self.cache / "moved-original"

        def replace_before_cleanup(_fd, _limit):
            path.rename(moved)
            path.symlink_to(self.sentinel)
            return helper.PROBE_BYTES

        with mock.patch.object(helper.secrets, "token_hex", return_value=self.token), \
             mock.patch.object(helper.os, "read", side_effect=replace_before_cleanup), \
             mock.patch.object(helper.os, "unlink") as unlink:
            with self.assertRaisesRegex(helper.CacheFailure, "^probe_file_replaced$"):
                helper.probe_directory(self.cache, root=self.cache)
            unlink.assert_not_called()
        self.assertTrue(path.is_symlink())
        self.assertEqual(moved.read_bytes(), helper.PROBE_BYTES)
        self.assert_outside_preserved()

    def test_read_failure_or_mismatch_removes_only_the_owned_probe(self):
        sibling = self.cache / "unrelated"
        sibling.write_bytes(b"keep")
        for failure in (OSError("synthetic read failure"), b"mismatch"):
            options = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=type(failure).__name__), \
                 mock.patch.object(helper.secrets, "token_hex", return_value=self.token), \
                 mock.patch.object(helper.os, "read", **options):
                with self.assertRaises((OSError, helper.CacheFailure)):
                    helper.probe_directory(self.cache, root=self.cache)
            self.assertEqual(list(self.cache.iterdir()), [sibling])
            self.assertEqual(sibling.read_bytes(), b"keep")
            self.assert_outside_preserved()

    def test_resolved_modules_use_declared_paths_and_reject_escapes(self):
        configured = {
            "SGLANG_DG_CACHE_DIR": str(self.cache / "deep_gemm"),
            "SGLANG_CACHE_DIR": str(self.cache / "sglang"),
            "FLASHINFER_WORKSPACE_BASE": str(self.cache / "flashinfer"),
            "TORCH_EXTENSIONS_DIR": str(self.cache / "torch_extensions"),
        }
        launcher = types.SimpleNamespace(FIXED_CACHE_ENVIRONMENT=configured)
        envs = types.SimpleNamespace(**{
            name: types.SimpleNamespace(get=mock.Mock(return_value=configured[name]))
            for name in ("SGLANG_DG_CACHE_DIR", "SGLANG_CACHE_DIR")
        })
        names = ("sglang.srt.environ", "flashinfer.jit.env", "torch.utils.cpp_extension")
        sources = {name: self.directory / (name.replace(".", "_") + ".py") for name in names}
        modules = {name: types.SimpleNamespace(__name__=name, __file__=str(path))
                   for name, path in sources.items()}
        modules[names[0]].envs = envs
        flash = modules[names[1]]
        flash.flashinfer_version = "0.6.12"
        flash.FLASHINFER_BASE_DIR = Path(configured["FLASHINFER_WORKSPACE_BASE"])
        fields = ("FLASHINFER_CACHE_DIR", "FLASHINFER_WORKSPACE_DIR", "FLASHINFER_JIT_DIR", "FLASHINFER_GEN_SRC_DIR")
        for field in fields:
            setattr(flash, field, self.cache / "flashinfer" / field.lower())
        cpp = modules[names[2]]
        cpp._get_build_directory = mock.Mock(return_value=configured["TORCH_EXTENSIONS_DIR"] + "/f1c_cache_probe")
        check = helper.checked_path
        with mock.patch.object(helper.importlib, "import_module", side_effect=modules.__getitem__) as imported, \
             mock.patch.dict(helper.sys.modules, {
                 "torch": types.SimpleNamespace(__version__="2.11.0+cu130"),
                 "sglang": types.SimpleNamespace(__version__="0.5.14"),
             }), \
             mock.patch.object(helper, "checked_path", side_effect=lambda value: check(value, root=self.cache)):
            paths = helper.resolved_directories(launcher, sources)
            self.assertTrue(all(path.is_relative_to(self.cache) for path in paths.values()))
            self.assertEqual([call.args[0] for call in imported.call_args_list], list(names))
            cpp._get_build_directory.assert_called_once_with("f1c_cache_probe", False)
            for field in fields:
                original = getattr(flash, field)
                setattr(flash, field, self.outside / "escape")
                with self.subTest(field=field), self.assertRaises(helper.CacheFailure):
                    helper.resolved_directories(launcher, sources)
                setattr(flash, field, original)
            envs.SGLANG_CACHE_DIR.get.return_value = str(self.outside / "escape")
            with self.assertRaisesRegex(helper.CacheFailure, "^sglang_resolver_mismatch$"):
                helper.resolved_directories(launcher, sources)
            envs.SGLANG_CACHE_DIR.get.return_value = configured["SGLANG_CACHE_DIR"]
            flash.flashinfer_version = "other"
            with self.assertRaisesRegex(helper.CacheFailure, "^imported_version_mismatch$"):
                helper.resolved_directories(launcher, sources)
            flash.flashinfer_version = "0.6.12"
            modules[names[0]].__file__ = str(self.outside / "substitute.py")
            with self.assertRaisesRegex(helper.CacheFailure, "^imported_module_mismatch$"):
                helper.resolved_directories(launcher, sources)
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assert_outside_preserved()

    def stage_launcher_repo(self):
        launcher_path = "scripts/lifecycle/sglang_file_auth.py"
        launcher_bytes = (ROOT / launcher_path).read_bytes()
        repo = self.directory / "repo"
        (repo / launcher_path).parent.mkdir(parents=True)
        (repo / launcher_path).write_bytes(launcher_bytes)
        provenance = repo / "reports/f1s-contract-evidence/launcher-provenance.json"
        provenance.parent.mkdir(parents=True)
        provenance.write_text(json.dumps({"path": launcher_path, "image_id": helper.IMAGE_ID,
                                          "sha256": hashlib.sha256(launcher_bytes).hexdigest()}))
        runtime_path = "configs/runtimes/sglang-qwen-next-0.5.14.json"
        runtime = json.loads((ROOT / runtime_path).read_text())
        (repo / runtime_path).parent.mkdir(parents=True)
        (repo / runtime_path).write_text(json.dumps(runtime))
        return repo, runtime["environment"]

    def test_real_launcher_validation_rejects_missing_cache_without_defaults(self):
        repo, environment = self.stage_launcher_repo()
        cache_names = [name for name, value in environment.items() if value.startswith("/cache")]
        self.assertEqual(len(cache_names), 9)
        for name in cache_names:
            env = {**environment, "HOME": "/home/fixture-operator"}
            del env[name]
            with self.subTest(name=name), mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(helper.importlib.metadata, "version") as version, \
                 mock.patch.object(helper.importlib.metadata, "entry_points") as entry_points, \
                 mock.patch.object(helper.importlib, "import_module") as imported, \
                 mock.patch.object(helper, "checked_path") as checked, \
                 mock.patch.object(helper, "probe_directory") as probe:
                with self.assertRaisesRegex(Exception, "^launch_environment_invalid$"):
                    helper.load_launcher(repo)
                version.assert_not_called()
                entry_points.assert_not_called()
                imported.assert_not_called()
                checked.assert_not_called()
                probe.assert_not_called()
                self.assertEqual(dict(os.environ), env)

    def test_installed_source_preflight_checks_versions_hashes_and_no_native_imports(self):
        repo = self.directory / "repo"
        evidence_path = repo / "reports/f1c-cache-source-evidence.json"
        evidence_path.parent.mkdir(parents=True)
        installed = self.directory / "installed" / "sglang"
        (installed / "srt").mkdir(parents=True)
        source = installed / "srt" / "environ.py"
        content = b"# synthetic public resolver source for preflight tests\n"
        source.write_bytes(content)
        evidence = {"image_id": helper.IMAGE_ID, "packages": {"sglang": "0.5.14"},
                    "resolver_sources": [{"module": "sglang.srt.environ", "relative_path": "sglang/srt/environ.py",
                                          "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}]}
        evidence_path.write_text(json.dumps(evidence))
        with mock.patch.object(helper.importlib.metadata, "version", return_value="0.5.14") as version, \
             mock.patch.object(helper.importlib.util, "find_spec", return_value=types.SimpleNamespace(origin=str(installed / "__init__.py"))) as find_spec, \
             mock.patch.object(helper.importlib, "import_module") as imported:
            self.assertEqual(helper.verify_installed_sources(repo), {"sglang.srt.environ": source})
            version.assert_called_once_with("sglang")
            find_spec.assert_called_once_with("sglang")
            imported.assert_not_called()
            source.write_bytes(b"altered installed source")
            with self.assertRaisesRegex(helper.CacheFailure, "^installed_source_mismatch$"):
                helper.verify_installed_sources(repo)
            source.write_bytes(content)
            version.return_value = "other"
            find_spec.reset_mock()
            with self.assertRaisesRegex(helper.CacheFailure, "^installed_version_mismatch$"):
                helper.verify_installed_sources(repo)
            find_spec.assert_not_called()
            imported.assert_not_called()
            version.return_value = "0.5.14"
            source.unlink()
            source.symlink_to(self.sentinel)
            with self.assertRaisesRegex(helper.CacheFailure, "^installed_module_path_invalid$"):
                helper.verify_installed_sources(repo)
        self.assert_outside_preserved()


class PreflightAndCliTests(unittest.TestCase):
    def test_run_actual_orders_preflight_validation_sources_resolvers_then_probes(self):
        order = []
        repo = Path("/fixture")
        launcher = object()
        paths = {"a": Path("/worker-fixture/cache/a"), "duplicate": Path("/worker-fixture/cache/a"),
                 "b": Path("/worker-fixture/cache/b")}
        with mock.patch.dict(os.environ, {"HOME": "/home/fixture-operator"}, clear=True), \
             mock.patch.object(helper, "verify_isolation", side_effect=lambda value: order.append("isolation")), \
             mock.patch.object(helper, "load_launcher", side_effect=lambda value: order.append("environment") or launcher), \
             mock.patch.object(helper, "verify_installed_sources", side_effect=lambda value: order.append("sources") or {}), \
             mock.patch.object(helper, "resolved_directories", side_effect=lambda value, sources: order.append("resolvers") or paths), \
             mock.patch.object(helper, "probe_directory", side_effect=lambda path: order.append(str(path))):
            result = helper.run_actual(repo)
            self.assertEqual(os.environ["HOME"], "/home/fixture-operator")
        self.assertEqual(order, ["isolation", "environment", "sources", "resolvers",
                                 "/worker-fixture/cache/a", "/worker-fixture/cache/b"])
        self.assertEqual(result["status"], "PASS_RESOLVERS_AND_FILESYSTEM_ONLY")
        self.assertEqual(result["gpu_driver_jit_cache"], "NOT_TESTED")
        self.assertEqual(result["model_cache_behavior"], "NOT_TESTED")
        self.assertTrue(result["home_unchanged"])

    def test_preflight_failure_stops_later_imports_and_probes_with_generic_cli_output(self):
        stages = ("verify_isolation", "load_launcher", "verify_installed_sources", "resolved_directories", "probe_directory")
        for fail_index in range(3):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(stage=stages[fail_index]), ExitStack() as stack:
                mocked = [stack.enter_context(mock.patch.object(helper, name)) for name in stages]
                mocked[fail_index].side_effect = RuntimeError("private synthetic exception detail")
                imported = stack.enter_context(mock.patch.object(helper.importlib, "import_module"))
                stack.enter_context(redirect_stdout(stdout))
                stack.enter_context(redirect_stderr(stderr))
                self.assertEqual(helper.main(["--actual-image", "--repo", "/fixture"]), 2)
                for later in mocked[fail_index + 1:]:
                    later.assert_not_called()
                imported.assert_not_called()
            self.assertEqual(json.loads(stdout.getvalue()), {"status": "FAIL", "code": "actual_cache_fixture_failed"})
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn("Traceback", stdout.getvalue())
            self.assertNotIn("private synthetic", stdout.getvalue())

    def test_cli_requires_frozen_explicit_actual_mode_and_repo(self):
        for argv in ([], ["--repo", "/fixture"], ["--actual-image"],
                     ["--actual", "--repo", "/fixture"],
                     ["--actual-image", "--repo", "/fixture", "--gpu"]):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(argv=argv), mock.patch.object(helper, "run_actual") as run, \
                 redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(helper.main(argv), 2)
                run.assert_not_called()
            self.assertEqual(json.loads(stdout.getvalue())["code"], "actual_cache_fixture_failed")
            self.assertEqual(stderr.getvalue(), "")

    def test_isolation_checks_use_readonly_mounts_private_empty_tmpfs_and_no_gpu(self):
        rows = [
            "1 0 0:1 / / ro - overlay overlay ro",
            "2 1 0:2 / /fixture ro - ext4 worker ro",
            "3 1 0:3 / /cache rw,nosuid,nodev - tmpfs tmpfs rw",
            "4 1 0:4 / /tmp rw,nosuid,nodev - tmpfs tmpfs rw",
        ]
        cases = [("valid", rows, True),
                 ("writable_root", [rows[0].replace("/ ro -", "/ rw -"), *rows[1:]], False),
                 ("nonprivate_cache", [*rows[:2], rows[2].replace("rw,nosuid,nodev", "rw"), rows[3]], False),
                 ("disk_cache", [*rows[:2], rows[2].replace("- tmpfs", "- ext4"), rows[3]], False),
                 ("duplicate_cache", [*rows, rows[2]], False),
                 ("mounted_model", [*rows, "5 1 0:5 / /models ro - ext4 worker ro"], False),
                 ("nested_cache_mount", [*rows, "5 3 0:5 / /cache/other rw - ext4 worker rw"], False)]
        for kind, mount_rows, valid in cases:
            with self.subTest(kind=kind), mock.patch.object(helper.sys, "platform", "linux"), \
                 mock.patch.object(helper.sys, "dont_write_bytecode", True), \
                 mock.patch.dict(os.environ, {"TMPDIR": "/tmp"}, clear=True), \
                 mock.patch.object(helper.Path, "resolve", autospec=True, side_effect=lambda path: path), \
                 mock.patch.object(helper.Path, "read_text", return_value="\n".join(mount_rows)), \
                 mock.patch.object(helper.Path, "lstat", return_value=types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=os.geteuid())), \
                 mock.patch.object(helper.Path, "iterdir", side_effect=lambda: iter(())), \
                 mock.patch.object(helper.Path, "glob", return_value=[]):
                if valid:
                    helper.verify_isolation(Path("/fixture"))
                else:
                    with self.assertRaises(helper.CacheFailure):
                        helper.verify_isolation(Path("/fixture"))


if __name__ == "__main__":
    unittest.main()
