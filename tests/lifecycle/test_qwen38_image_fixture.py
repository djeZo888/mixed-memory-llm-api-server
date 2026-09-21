"""Source-worker controls for Q38S actual-image fixture; native image NOT_TESTED.

These tests exercise refusal/evidence/I/O controls with explicit synthetic
collaborators. Only the separate pinned-image command can mint its auth receipt.
"""
import ast
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/lifecycle/sglang38_fixture"


def load(name):
    spec = importlib.util.spec_from_file_location("q38s_control_" + name, FIXTURE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inner, host = load("run_pinned_image"), load("run_fixture")


def inspected():
    return [{"Id": host.IMAGE_ID, "RepoDigests": [host.IMAGE_REFERENCE], "Os": "linux",
             "Architecture": "amd64", "Config": {
                 "Entrypoint": list(host.OCI.IMAGE_ENTRYPOINT), "Cmd": None,
                 "WorkingDir": host.OCI.IMAGE_WORKDIR, "Labels": {
                 "org.opencontainers.image.revision": host.SOURCE_REVISION,
                 "org.opencontainers.image.source": host.OCI.SOURCE_REPOSITORY}}}]


def native_result(provenance, context):
    value = {check: "PASS" for check in host.CHECKS}
    value.update(status="PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE", image_id_pin=host.IMAGE_ID,
        image_reference=host.IMAGE_REFERENCE, source_revision=host.SOURCE_REVISION,
        image_identity_verification="HOST_DOCKER_INSPECT_REQUIRED", configured_context=context,
        launcher_sha256=provenance["launcher_sha256"], fixture_sha256=provenance["fixture_sha256"],
        support_sha256=provenance["support_sha256"],
        cache_probe=host.CACHE.result_record(dict(host.CACHE.EXPECTED_PATHS), []),
        source_hashes={name: item["sha256"] for name, item in provenance["sources"].items()},
        model_loading="STUBBED_NOT_TESTED", gpu_execution="NOT_TESTED",
        native_lifespan_model_serving_initialization="NOT_TESTED",
        live_inference_and_agent_acceptance="NOT_TESTED")
    return value


def lifetime(context):
    """Synthetic receipt collaborator; never attests a Docker execution."""
    token = ('1' if context == 131072 else '2') * 32
    return {"container_name": "q38b-fixture-" + token, "container_id": token * 2,
        "outcome": "FIXTURE_EXITED", "cleanup": "QUIESCENT_REMOVAL_VERIFIED",
        "runtime_inspect": {"runtime": "nvidia", "visible_devices": "none",
            "driver_capabilities": "compute,utility", "device_requests": [], "host_devices": [],
            "network": "none", "root_readonly": True, "model_and_secret_mounts": "EMPTY_PRIVATE_TMPFS",
            "entrypoint": ["python3"], "context": context, "status": "PASS_HOST_INSPECT"}}


class Qwen38ImageFixtureTests(unittest.TestCase):
    def test_rayon_threads_required_before_fixture_source_or_native_imports(self):
        for context in (131072, 262144, 1000000):
            for value in (None, "", "0", "64", " 1", "1 ", "1.0", "1"):
                env = {"UNRELATED_ENVIRONMENT": "retained"}
                if value is not None:
                    env["RAYON_NUM_THREADS"] = value
                with self.subTest(context=context, value=value), patch.dict(os.environ, env, clear=True), \
                        patch.object(inner, "verify_sources", side_effect=RuntimeError("synthetic_source_boundary")) as source, \
                        patch.object(inner, "run_cache_probe") as cache:
                    expected = "synthetic_source_boundary" if value == "1" else "fixture_rayon_threads_required"
                    with self.assertRaisesRegex(Exception, "^" + expected + "$"):
                        inner.run_actual(ROOT, "all", None, context)
                    self.assertEqual(source.call_count, 1 if value == "1" else 0)
                    cache.assert_not_called()
                    self.assertEqual(dict(os.environ), env)

    def test_rayon_inherited_by_existing_children_spawn_and_launch_snapshot(self):
        launcher = host.source_module("rayon_fixture_launcher", ROOT / "scripts/runtime/sglang38_file_auth.py")
        env = {**launcher.CACHE_ENVIRONMENT, "RAYON_NUM_THREADS": "1", "UNRELATED_ENVIRONMENT": "retained"}
        expected = host.CACHE.result_record(dict(host.CACHE.EXPECTED_PATHS), [])
        observed = []
        def child(command, **kwargs):
            inherited = os.environ if kwargs.get("env") is None else kwargs["env"]
            self.assertEqual(dict(inherited), env)
            if "--internal-scenario" in command:
                observed.append(command[command.index("--internal-scenario") + 1])
                return SimpleNamespace(returncode=1, stdout=inner.FAULT_MARKER, stderr=b"")
            observed.append("cache")
            return SimpleNamespace(returncode=0, stdout=json.dumps(expected).encode(), stderr=b"")
        with patch.dict(os.environ, env, clear=True), \
                patch.object(inner.subprocess, "run", side_effect=child), \
                patch.object(inner.Path, "exists", return_value=False), \
                patch.object(inner.Path, "lstat", return_value=SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o600, st_uid=os.geteuid())), \
                patch.object(inner.Path, "unlink"), patch.object(inner.socket, "socket") as socket:
            socket.return_value.connect_ex.return_value = 1
            self.assertEqual(inner.run_cache_probe(ROOT), expected)
            inner.run_failure_children(ROOT)
            self.assertEqual(dict(os.environ), env)
        self.assertEqual(observed, ["cache", "warmup-auth-failure", "warmup-timeout"])
        # The sole cleanup child has no environment override. This inspects its
        # existing statement only; no process or replacement framework executes.
        tree = ast.parse(Path(inner.__file__).read_text())
        cleanup = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
            and (node.func.value.id, node.func.attr) == ("subprocess", "Popen")]
        self.assertEqual(len(cleanup), 1)
        self.assertNotIn("env", [keyword.arg for keyword in cleanup[0].keywords])
        with patch.dict(os.environ, env, clear=True), \
                patch.object(inner.os, "open", side_effect=AssertionError("spawn read key")):
            imported = inner.runpy.run_path(launcher.__file__, run_name="__mp_main__")
            self.assertIn("main", imported)
            self.assertEqual(dict(os.environ), env)
        captured, engines = [], []
        def launch(_argv):
            launcher.validate_environment()
            self.assertEqual(dict(os.environ), env)
            captured.append(object())
            engines.append(object())
            return 0
        imported_env = {**env, "TRITON_PTXAS_BLACKWELL_PATH": "/synthetic/import-side-effect"}
        with patch.dict(os.environ, imported_env, clear=True), patch.object(launcher, "main", side_effect=launch), \
                patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), \
                patch.object(launcher.importlib.metadata, "entry_points", return_value={}):
            self.assertEqual(inner.checked_launch(launcher, [], captured, engines,
                "synthetic-fixture-key", env), 0)
            self.assertEqual(dict(os.environ), imported_env)

    def test_native_cache_probe_uses_fresh_child_and_validates_result(self):
        expected = host.CACHE.result_record(dict(host.CACHE.EXPECTED_PATHS), [])
        child = SimpleNamespace(returncode=0, stdout=json.dumps(expected).encode(), stderr=b'')
        with patch.object(inner.subprocess, 'run', return_value=child) as process:
            self.assertEqual(inner.run_cache_probe(ROOT), expected)
        command = process.call_args.args[0]
        self.assertEqual(command[1:4], ['-X', 'faulthandler', '-B'])
        self.assertEqual(command[4], str(FIXTURE / 'cache_probe.py'))
        self.assertEqual(process.call_args.kwargs['timeout'], 120)
        for change in ({'returncode': 1}, {'stderr': b'private detail'}, {'stdout': b'{}'}):
            failed = SimpleNamespace(**(vars(child) | change))
            with patch.object(inner.subprocess, 'run', return_value=failed), \
                    patch.object(inner.os, 'write'), self.assertRaises(Exception):
                inner.run_cache_probe(ROOT)

    def test_native_fault_stderr_prefix_reaches_original_fd_and_stays_failure(self):
        for code, raw in ((-11, b'Fatal Python error: Segmentation fault\n  cache_probe.py native import\n'),
                          (-11, b'x' * 20000), (0, b'native stderr remains a failure')):
            child = SimpleNamespace(returncode=code, stdout=b'', stderr=raw)
            with self.subTest(code=code, size=len(raw)), \
                    patch.object(inner.subprocess, 'run', return_value=child), \
                    patch.object(inner.os, 'write') as original_fd, \
                    self.assertRaisesRegex(inner.FixtureFailure, 'cache_probe_child_failed'):
                inner.run_cache_probe(ROOT)
            original_fd.assert_called_once_with(
                2, b'Q38FIX cache_probe stderr prefix (up to 16384 bytes):\n' + raw[:16384])

    def test_successful_cache_probe_does_not_forward_stderr(self):
        expected = host.CACHE.result_record(dict(host.CACHE.EXPECTED_PATHS), [])
        child = SimpleNamespace(returncode=0, stdout=json.dumps(expected).encode(), stderr=b'')
        with patch.object(inner.subprocess, 'run', return_value=child), \
                patch.object(inner.os, 'write') as original_fd:
            self.assertEqual(inner.run_cache_probe(ROOT), expected)
        original_fd.assert_not_called()

    def test_broken_stderr_fd_cannot_replace_native_child_failures(self):
        child = SimpleNamespace(returncode=-11, stdout=b'', stderr=b'fault trace')
        with patch.object(inner.subprocess, 'run', return_value=child), \
                patch.object(inner.os, 'write', side_effect=OSError('closed')), \
                patch.object(inner.Path, 'exists', return_value=False):
            with self.assertRaisesRegex(inner.FixtureFailure, 'cache_probe_child_failed'):
                inner.run_cache_probe(ROOT)
            with self.assertRaisesRegex(inner.FixtureFailure, 'warmup_failure_subprocess_not_closed'):
                inner.run_failure_children(ROOT)

    def test_failure_fixture_children_explicitly_enable_faulthandler(self):
        child = SimpleNamespace(returncode=1, stdout=inner.FAULT_MARKER, stderr=b'')
        with patch.object(inner.subprocess, 'run', return_value=child) as process, \
                patch.object(inner.Path, 'exists', return_value=False), \
                patch.object(inner.Path, 'lstat', return_value=SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o600, st_uid=os.geteuid())), \
                patch.object(inner.Path, 'unlink'), patch.object(inner.socket, 'socket') as socket:
            socket.return_value.connect_ex.return_value = 1
            inner.run_failure_children(ROOT)
        self.assertEqual(process.call_count, 2)
        for call in process.call_args_list:
            self.assertEqual(call.args[0][1:3], ['-X', 'faulthandler'])

    def test_failure_fixture_crash_prefix_survives_without_acceptance(self):
        child = SimpleNamespace(returncode=-11, stdout=b'', stderr=b'x' * 20000)
        with patch.object(inner.subprocess, 'run', return_value=child), \
                patch.object(inner.Path, 'exists', return_value=False), \
                patch.object(inner.os, 'write') as original_fd, \
                self.assertRaisesRegex(inner.FixtureFailure, 'warmup_failure_subprocess_not_closed') as caught:
            inner.run_failure_children(ROOT)
        original_fd.assert_called_once_with(
            2, b'Q38FIX failure fixture stderr prefix (up to 16384 bytes):\n' + child.stderr[:16384])
        self.assertEqual(caught.exception.warmup_child_failure, {
            "scenario": "warmup-auth-failure", "returncode": -11,
            "stdout_bytes": 0, "stderr_bytes": 20000, "marker_exact": False,
            "marker_count": 0, "child_failure": {"status": "REJECTED_OR_UNAVAILABLE"}})

    def test_inner_requires_explicit_actual_mode_and_exact_contexts(self):
        for argv in (["--repo", "/fixture"], ["--actual-image", "--repo", "/fixture", "--fallback"],
                     ["--actual-image", "--repo", "/fixture", "--context", "1048576"]):
            with self.subTest(argv=argv), self.assertRaises(inner.FixtureFailure):
                inner.parse_options(argv)
        for context in (131072, 262144):
            self.assertEqual(inner.parse_options(["--actual-image", "--repo", "/fixture",
                                                   "--context", str(context)]).context, context)

    def test_both_help_paths_work_without_native_import_or_docker(self):
        for module in (inner, host):
            with self.subTest(module=module.__name__), redirect_stdout(io.StringIO()), \
                    self.assertRaises(SystemExit) as result:
                module.parse_options(["--help"])
            self.assertEqual(result.exception.code, 0)

    def test_non_linux_refuses_before_native_import_and_key(self):
        with patch.object(inner.sys, "platform", "darwin"), \
                patch.object(inner.importlib.util, "find_spec") as find, patch.object(inner.os, "open") as opened:
            with self.assertRaisesRegex(inner.FixtureFailure, "linux_pinned_image_required"):
                inner.verify_sources(Path("/fixture"))
        find.assert_not_called()
        opened.assert_not_called()

    def test_manifest_digest_is_not_docker_config_image_id(self):
        self.assertNotEqual(host.IMAGE_ID, host.IMAGE_REFERENCE.split("@", 1)[1])
        self.assertEqual(host.verify_image(inspected())["image_id"], host.IMAGE_ID)
        for field, value in (("Id", host.IMAGE_REFERENCE.split("@", 1)[1]),
                             ("Id", "sha256:" + "0" * 64), ("Architecture", "arm64"),
                             ("Os", "darwin"), ("RepoDigests", []),
                             ("RepoDigests", host.IMAGE_REFERENCE), ("RepoDigests", [3])):
            bad = inspected()
            bad[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(host.FixtureError):
                host.verify_image(bad)
        bad = inspected()
        bad[0]["Config"]["Labels"]["org.opencontainers.image.revision"] = "unreviewed"
        with self.assertRaises(host.FixtureError):
            host.verify_image(bad)

    def test_command_no_pull_gpu_network_models_or_real_key_mount(self):
        command = host.docker_command(Path("/reviewed"), {"HF_HOME": "/cache/huggingface"}, 262144)
        self.assertIn("--pull=never", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertNotIn("--gpus", command)
        self.assertNotIn("--privileged", command)
        self.assertEqual(command[command.index("--runtime") + 1], "nvidia")
        self.assertEqual(command[command.index("--log-driver") + 1], "none")
        self.assertEqual(command.count("--ulimit"), 1)
        self.assertEqual(command[command.index("--ulimit") + 1], "core=1:1")
        self.assertEqual([value for value in command if value.startswith("NVIDIA_VISIBLE_DEVICES=")],
                         ["NVIDIA_VISIBLE_DEVICES=none"])
        self.assertIn("NVIDIA_DRIVER_CAPABILITIES=compute,utility", command)
        self.assertIn("CUDA_VISIBLE_DEVICES=", command)
        self.assertEqual([value for value in command if value.startswith("OPENBLAS_NUM_THREADS=")],
                         ["OPENBLAS_NUM_THREADS=1"])
        self.assertEqual([value for value in command if value.startswith("RAYON_NUM_THREADS=")],
                         ["RAYON_NUM_THREADS=1"])
        self.assertEqual(command.count("--mount"), 1)
        self.assertEqual(command[command.index("--mount") + 1],
                         "type=bind,src=/reviewed,dst=/fixture,readonly")
        self.assertIn("/run/secrets:rw,nosuid,nodev,noexec,size=1m,mode=0700", command)
        self.assertIn(host.IMAGE_REFERENCE, command)
        self.assertEqual(command[command.index(host.IMAGE_REFERENCE) + 1:][:3], ["-X", "faulthandler", "-B"])
        self.assertEqual(command[-2:], ["--context", "262144"])
        self.assertFalse(any(value.startswith("HOME=") for value in command))
        for path in ("/reviewed,src=/etc", "/reviewed\nunsafe"):
            with self.subTest(path=path), self.assertRaises(host.FixtureError):
                host.docker_command(Path(path), {}, 131072)

    def test_native_installed_hash_and_version_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            repo, installed = base / "repo", base / "installed"
            fixture = repo / "tests/lifecycle/sglang38_fixture"
            fixture.mkdir(parents=True)
            installed.mkdir()
            source = installed / "native.py"
            source.write_bytes(b"# native source fixture\n")
            launcher = repo / "scripts/runtime/sglang38_file_auth.py"
            launcher.parent.mkdir(parents=True)
            launcher.write_bytes(b"# reviewed launcher fixture\n")
            provenance = {"source_revision": inner.SOURCE_REVISION, "image_id": inner.IMAGE_ID,
                "image_reference": inner.IMAGE_REFERENCE,
                "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
                "sources": {"native.py": {"bytes": source.stat().st_size,
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}, "fixture_sha256": {}}
            (fixture / "provenance.json").write_text(json.dumps(provenance))
            with patch.object(inner.sys, "platform", "linux"), \
                    patch.object(inner.importlib.metadata, "version", return_value="0.5.19") as version, \
                    patch.object(inner.importlib.util, "find_spec",
                        return_value=SimpleNamespace(origin=str(installed / "__init__.py"))) as find:
                self.assertEqual(inner.verify_sources(repo), launcher)
                version.return_value = "0.5.14"
                with self.assertRaisesRegex(inner.FixtureFailure, "installed_version_mismatch"):
                    inner.verify_sources(repo)
                version.return_value = "0.5.19"
                source.write_bytes(b"x" * source.stat().st_size)
                with self.assertRaisesRegex(inner.FixtureFailure, "installed_source_hash_mismatch"):
                    inner.verify_sources(repo)
                find.return_value = None
                with self.assertRaisesRegex(inner.FixtureFailure, "installed_sglang_missing"):
                    inner.verify_sources(repo)

    def test_repository_hash_binding_matches_source_worker_bytes(self):
        provenance, cache = host.read_provenance(ROOT)
        self.assertEqual(provenance["source_revision"], host.SOURCE_REVISION)
        self.assertEqual(provenance["actual_image_execution"], "NOT_TESTED")
        self.assertEqual(cache["HF_HOME"], "/cache/huggingface")
        self.assertTrue(all(item["status"] == "SOURCE_ONLY" for item in provenance["sources"].values()))
        native_auth = (FIXTURE / "auth_native.py").read_bytes()
        self.assertEqual(hashlib.sha256(native_auth).hexdigest(),
                         provenance["sources"]["srt/utils/auth.py"]["sha256"])

    def test_receipt_rejects_source_only_or_incomplete_evidence(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text())
        correct = native_result(provenance, 131072)
        host.check_native_result(correct, provenance, 131072)
        for key, value in (("status", "SOURCE_ONLY"), ("image_id_pin", host.IMAGE_REFERENCE),
                           ("launcher_sha256", "0" * 64), ("configured_context", 262144),
                           ("source_hashes", {}), ("fixture_sha256", {}),
                           ("model_loading", "PASS"), ("sentinel_absence", "NOT_TESTED")):
            bad = copy.deepcopy(correct)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(host.FixtureError):
                host.check_native_result(bad, provenance, 131072)

    def test_empty_fixture_files_created_exclusively_and_existing_key_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            key, config = base / "key", base / "config.json"
            with patch.object(inner, "KEY_PATH", key), patch.object(inner, "CONFIG_PATH", config), \
                    patch.object(inner, "require_private_tmpfs"):
                with inner.fixture_files(b"{}") as sentinel:
                    self.assertTrue(key.read_bytes() == sentinel.encode(), "fixture token changed")
                    self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
                self.assertFalse(key.exists())
                self.assertFalse(config.exists())
                key.write_bytes(b"existing-synthetic-file")
                with self.assertRaises(FileExistsError):
                    with inner.fixture_files(b"{}"):
                        self.fail("existing key accepted")
                self.assertEqual(key.read_bytes(), b"existing-synthetic-file")

    def test_failure_output_never_relays_synthetic_sentinel(self):
        sentinel = secrets.token_urlsafe(32)
        output = io.StringIO()

        def fail(_repo, _scenario, logs, _context):
            print(sentinel)
            logs.write(sentinel)
            raise RuntimeError(sentinel)

        with patch.object(inner, "run_actual", side_effect=fail), redirect_stdout(output):
            code = inner.main(["--actual-image", "--repo", "/fixture"])
        self.assertEqual(code, 2)
        self.assertTrue(sentinel not in output.getvalue(), "synthetic token disclosure")
        failure = json.loads(output.getvalue())
        self.assertEqual(set(failure), {"status", "code", "failure_origin"})
        self.assertEqual((failure["status"], failure["code"]), ("FAIL", "actual_image_fixture_failed"))
        parsed = host.failure_metadata(output.getvalue().encode())
        self.assertEqual(parsed["status"], "SAFE_ORIGIN")
        self.assertEqual(parsed["origin"]["exception_class"], "RuntimeError")
        output = io.StringIO()
        with patch.object(host, "run", side_effect=RuntimeError(sentinel)), redirect_stdout(output):
            code = host.main(["--repo", "/fixture", "--output", "/data/receipt.json"])
        self.assertEqual(code, 1)
        self.assertTrue(sentinel not in output.getvalue(), "synthetic token disclosure")

    def test_origin_selects_concrete_fixture_callsite_after_opaque_cache_failure(self):
        sentinel = secrets.token_urlsafe(32)
        child = SimpleNamespace(returncode=1, stdout=sentinel.encode(), stderr=sentinel.encode())
        with patch.object(inner.subprocess, "run", return_value=child), patch.object(inner.os, "write"):
            try:
                inner.run_cache_probe(ROOT)
            except inner.FixtureFailure as error:
                origin = inner.failure_origin(error)
                # The failed callsite precedes the generic require frame.
                frame = error.__traceback__
                expected = None
                while frame is not None:
                    if frame.tb_frame.f_code is inner.run_cache_probe.__code__:
                        expected = frame.tb_lineno
                    frame = frame.tb_next
            else:
                self.fail("failed cache child accepted")
        self.assertTrue(sentinel not in json.dumps(origin), "synthetic token disclosure")
        self.assertEqual(origin, {"filename": "run_pinned_image.py", "line": expected,
                                  "exception_class": "FixtureFailure"})
        self.assertEqual(inner.FAILURE_CLASSES, host.FAILURE_CLASSES)

    def test_unknown_exception_class_and_deep_traceback_cannot_disclose(self):
        sentinel = secrets.token_urlsafe(32)
        unknown = type(sentinel, (RuntimeError,), {})
        output = io.StringIO()
        with patch.object(inner, "run_actual", side_effect=unknown(sentinel)), redirect_stdout(output):
            self.assertEqual(inner.main(["--actual-image", "--repo", str(ROOT)]), 2)
        self.assertTrue(sentinel not in output.getvalue(), "synthetic token disclosure")
        self.assertEqual(json.loads(output.getvalue())["failure_origin"]["exception_class"], "OTHER")

        def deep(depth):
            if depth:
                return deep(depth - 1)
            raise RuntimeError(sentinel)

        output = io.StringIO()
        with patch.object(inner, "run_actual", side_effect=lambda *_: deep(70)), redirect_stdout(output):
            self.assertEqual(inner.main(["--actual-image", "--repo", str(ROOT)]), 2)
        self.assertTrue(sentinel not in output.getvalue(), "synthetic token disclosure")
        self.assertIsNone(json.loads(output.getvalue())["failure_origin"])

    def test_root_filesystem_output_refused_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "receipt.json"
            if output.parent.stat().st_dev != Path("/").stat().st_dev:
                self.skipTest("temporary directory is a separate filesystem")
            with patch.object(host.subprocess, "run") as docker:
                with self.assertRaisesRegex(host.FixtureError, "evidence_on_root_filesystem_refused"):
                    host.run(ROOT, output)
            docker.assert_not_called()

    def test_host_writes_receipt_only_after_both_native_context_checks(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text())
        calls = []

        def disposable(repo, cache, context, **kwargs):
            calls.append((context, kwargs['image_id']))
            return SimpleNamespace(returncode=0,
                stdout=json.dumps(native_result(provenance, context)).encode(), stderr=b""), lifetime(context)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            with patch.object(host, "validate_output_path"), patch.object(host.subprocess, "run",
                    return_value=SimpleNamespace(returncode=0, stdout=json.dumps(inspected()).encode(), stderr=b"")), \
                    patch.object(host, "run_disposable_fixture", side_effect=disposable):
                result = host.run(ROOT, output)
            self.assertEqual(result["contexts"], [131072, 262144])
            self.assertEqual(result["model_execution"], "NOT_TESTED")
            self.assertEqual(result["image_identity_verification"], "HOST_DOCKER_INSPECT_AND_PINNED_RUN")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(calls, [(131072, host.IMAGE_ID), (262144, host.IMAGE_ID)])

    def test_host_failure_does_not_write_a_partial_pass_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            inspected_result = SimpleNamespace(returncode=0, stdout=json.dumps(inspected()).encode(), stderr=b"")
            failed_result = SimpleNamespace(returncode=2, stdout=b'{"status":"FAIL"}', stderr=b"")
            with patch.object(host, "validate_output_path"), \
                    patch.object(host.subprocess, "run", return_value=inspected_result), \
                    patch.object(host, "run_disposable_fixture", return_value=(failed_result, lifetime(131072))):
                with self.assertRaisesRegex(host.FixtureError, "actual_image_fixture_failed"):
                    host.run(ROOT, output)
            self.assertFalse(output.exists())

    def test_anchored_output_removes_receipt_if_parent_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            parent = base / "data"
            parent.mkdir()
            original = base / "detached"
            real_fsync = os.fsync
            moved = False

            def detach_after_write(fd):
                nonlocal moved
                real_fsync(fd)
                if stat.S_ISDIR(os.fstat(fd).st_mode) and not moved:
                    moved = True
                    parent.rename(original)
                    parent.mkdir()

            with patch.object(host, "validate_output_path"), patch.object(host.os, "fsync", side_effect=detach_after_write):
                with self.assertRaisesRegex(host.FixtureError, "evidence_directory_rebound"):
                    host.write_receipt(parent / "receipt.json", {"status": "PASS"})
            self.assertFalse((parent / "receipt.json").exists())
            self.assertFalse((original / "receipt.json").exists())

    def test_abort_child_requires_marker_and_actual_abort_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(inner, "KEY_PATH", Path(directory) / "key"), \
                    patch.object(inner, "CONFIG_PATH", Path(directory) / "config"), \
                    patch.object(inner.subprocess, "run", return_value=SimpleNamespace(
                        returncode=2, stdout=b'{"status":"FAIL"}', stderr=b"")):
                with self.assertRaisesRegex(inner.FixtureFailure, "warmup_failure_subprocess_not_closed"):
                    inner.run_failure_children(Path("/fixture"))

    def test_cuda_discovery_seam_refuses_any_real_initialization(self):
        cuda = SimpleNamespace(**{name: lambda: None for name in inner.HARDWARE_STUBS}, _lazy_init=lambda: None)
        with inner.cuda_discovery_fixture(SimpleNamespace(cuda=cuda)):
            self.assertEqual(cuda.device_count(), 1)
            self.assertEqual(cuda.get_device_capability(), (12, 0))
            with self.assertRaisesRegex(inner.FixtureFailure, "gpu_initialization_refused"):
                cuda._lazy_init()

    def test_asgi_stream_driver_preserves_disconnect(self):
        events = []

        async def app(_scope, receive, send):
            events.append(await receive())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
            events.append(await receive())
            await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})

        status, content, _ = asyncio.run(inner.asgi_request(app, "/generate", method="POST",
                                                         body={"fixture": True}, disconnect=True))
        self.assertEqual(status, 200)
        self.assertEqual(content, b"data: first\n\ndata: [DONE]\n\n")
        self.assertEqual(json.loads(events[0]["body"]), {"fixture": True})
        self.assertEqual(events[1], {"type": "http.disconnect"})


class Qwen38WarmupChildFailureTests(unittest.TestCase):
    """Failure-only records under synthetic child/process collaborators."""

    def record(self, child, *, second=False):
        stdout, stderr = io.StringIO(), io.StringIO()
        success = SimpleNamespace(returncode=1, stdout=inner.FAULT_MARKER, stderr=b"")
        with patch.object(inner, "run_actual", return_value={}), \
                patch.object(inner.subprocess, "run", side_effect=([success, child] if second else [child])) as process, \
                patch.object(inner.Path, "exists", return_value=False), \
                patch.object(inner.Path, "lstat", return_value=SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o600, st_uid=os.geteuid())), \
                patch.object(inner.Path, "unlink"), patch.object(inner.socket, "socket") as socket, \
                patch.object(inner.os, "write") as raw_write, redirect_stdout(stdout), redirect_stderr(stderr):
            socket.return_value.connect_ex.return_value = 1
            code = inner.main(["--actual-image", "--repo", str(ROOT)])
        self.assertEqual(code, 2)
        self.assertEqual(stderr.getvalue(), "")
        if not isinstance(child, BaseException) and child.stderr:
            raw_write.assert_called_once_with(
                2, b"Q38FIX failure fixture stderr prefix (up to 16384 bytes):\n" + child.stderr[:16384])
        else:
            raw_write.assert_not_called()
        self.assertEqual(process.call_count, 2 if second else 1)
        self.assertTrue(all(call.kwargs["timeout"] == 180 for call in process.call_args_list))
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["code"], "actual_image_fixture_failed")
        parsed = host.failure_metadata(stdout.getvalue().encode())
        self.assertEqual(parsed["status"], "SAFE_ORIGIN")
        self.assertEqual(parsed["warmup_child_failure"], result["warmup_child_failure"])
        return result

    def test_failed_abort_predicate_reports_each_operand_and_finite_scenario(self):
        secret = "SYNTHETIC_CHILD_SECRET_MUST_NOT_LEAVE"
        for code, stdout, stderr in ((2, b"", b""), (1, b"", b""),
                (1, inner.FAULT_MARKER * 2, b""), (-11, secret.encode(), secret.encode()),
                (1, inner.FAULT_MARKER, secret.encode())):
            for second in (False, True):
                with self.subTest(code=code, length=len(stdout), second=second):
                    result = self.record(SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr), second=second)
                    self.assertNotIn(secret, json.dumps(result))
                    self.assertEqual(result["warmup_child_failure"], {
                        "scenario": "warmup-timeout" if second else "warmup-auth-failure",
                        "returncode": code, "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
                        "marker_exact": stdout == inner.FAULT_MARKER,
                        "marker_count": stdout.count(inner.FAULT_MARKER),
                        "child_failure": {"status": "REJECTED_OR_UNAVAILABLE"}})

    def test_valid_child_cache_failure_survives_one_closed_layer(self):
        cache = {"status": "FAIL", "code": "gpu_device_node_present", "failure_origin": None,
            "device_failure": {"path": "/dev/nvidia-caps", "type": "DIRECTORY", "uid_root": True,
                "gid_root": True, "mode_0755": True, "has_entries": True}}
        child = {"status": "FAIL", "code": "actual_image_fixture_failed", "failure_origin": {
            "filename": "run_pinned_image.py", "line": 678, "exception_class": "FixtureFailure"},
            "cache_failure": cache}
        result = self.record(SimpleNamespace(returncode=2, stdout=json.dumps(child).encode(), stderr=b""), second=True)
        nested = result["warmup_child_failure"]["child_failure"]
        self.assertEqual(nested["status"], "SAFE_ORIGIN")
        self.assertEqual(nested["origin"], child["failure_origin"])
        self.assertEqual(nested["cache_failure"], cache)

    def test_timeout_retains_known_partial_operands_without_child_text(self):
        secret = b"SYNTHETIC_TIMEOUT_PRIVATE_OUTPUT"
        error = inner.subprocess.TimeoutExpired(["private-command"], 180, output=secret,
                                                stderr=secret)
        result = self.record(error, second=True)
        self.assertNotIn(secret.decode(), json.dumps(result))
        self.assertNotIn("private-command", json.dumps(result))
        self.assertEqual(result["warmup_child_failure"], {
            "scenario": "warmup-timeout", "returncode": None, "stdout_bytes": len(secret),
            "stderr_bytes": len(secret), "marker_exact": False, "marker_count": 0,
            "child_failure": {"status": "REJECTED_OR_UNAVAILABLE"}})

    def test_malformed_child_hints_are_rejected_without_replacing_original_failure(self):
        fixed = b'{"status":"FAIL","code":"actual_image_fixture_failed"}'
        for stdout in (b'prefix ' + fixed, fixed + b' trailing', fixed * 2,
                b'{"status":"FAIL","status":"FAIL","code":"actual_image_fixture_failed"}',
                b'{"status":"FAIL","code":"actual_image_fixture_failed","private":"secret"}',
                fixed + b' ' * 4096, b'{"status":NaN}'):
            with self.subTest(length=len(stdout)):
                result = self.record(SimpleNamespace(returncode=2, stdout=stdout, stderr=b""))
                self.assertEqual(result["warmup_child_failure"]["child_failure"],
                                 {"status": "REJECTED_OR_UNAVAILABLE"})

    def test_host_refuses_malformed_recursive_or_success_shaped_child_diagnostics(self):
        good = {"scenario": "warmup-timeout", "returncode": 2, "stdout_bytes": 0,
            "stderr_bytes": 0, "marker_exact": False, "marker_count": 0,
            "child_failure": {"status": "REJECTED_OR_UNAVAILABLE"}}
        rejected = []
        for field, value in (("scenario", "all"), ("returncode", True), ("returncode", 256),
                ("stdout_bytes", True), ("stderr_bytes", -1), ("marker_exact", 0),
                ("marker_count", True), ("marker_count", 1), ("stdout_bytes", None),
                ("child_failure", {"status": "REJECTED_OR_UNAVAILABLE", "private": "secret"})):
            rejected.append({**good, field: value})
        for field in good:
            changed = dict(good)
            del changed[field]
            rejected.append(changed)
        rejected.append({**good, "returncode": 1, "stdout_bytes": len(inner.FAULT_MARKER),
                         "marker_exact": True, "marker_count": 1})
        rejected.append({**good, "child_failure": {"status": "SAFE_ORIGIN",
            "code": "actual_image_fixture_failed", "origin": {"filename": "run_pinned_image.py",
                "line": 1, "exception_class": "FixtureFailure"}, "warmup_child_failure": good}})
        for value in rejected:
            with self.subTest(fields=list(value)):
                self.assertIsNone(host.validate_warmup_child_failure(value))
                outer = {"status": "FAIL", "code": "actual_image_fixture_failed",
                         "failure_origin": None, "warmup_child_failure": value}
                self.assertEqual(host.failure_metadata(json.dumps(outer).encode()),
                                 {"status": "REJECTED_OR_UNAVAILABLE"})
        unknown = {**good, "stdout_bytes": None, "stderr_bytes": None,
                   "marker_exact": None, "marker_count": None, "returncode": None}
        self.assertEqual(host.validate_warmup_child_failure(unknown), unknown)


if __name__ == "__main__":
    unittest.main()
