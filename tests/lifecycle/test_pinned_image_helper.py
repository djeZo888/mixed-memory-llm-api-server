"""Worker-only control tests for the strict actual-image fixture launcher.

These tests do not claim execution of the pinned SGLang image. Native source
and framework behavior belongs to run_pinned_image.py --actual-image only.
"""
import asyncio
from contextlib import nullcontext, redirect_stdout
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
HELPER = ROOT / "tests/lifecycle/sglang_fixture/run_pinned_image.py"
spec = importlib.util.spec_from_file_location("f1s_pinned_helper_control", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class PinnedImageHelperControlTests(unittest.TestCase):
    def test_current_helper_provenance_is_exact_and_not_live_evidence(self):
        provenance = json.loads(HELPER.with_name("provenance.json").read_text())
        current = provenance["actual_image_helper"]
        self.assertEqual(current["path"], str(HELPER.relative_to(ROOT)))
        self.assertEqual(current["sha256"], hashlib.sha256(HELPER.read_bytes()).hexdigest())
        self.assertEqual(current["execution_status"], "NOT_TESTED_ACTUAL_IMAGE_F1E2")
        self.assertEqual(provenance["image_id"], helper.IMAGE_ID)

    def test_explicit_actual_image_mode_required(self):
        with self.assertRaises(helper.FixtureFailure):
            helper.parse_options(["--repo", "/fixture"])
        with self.assertRaises(helper.FixtureFailure):
            helper.parse_options(["--actual-image", "--repo", "/fixture", "--fallback"])
        options = helper.parse_options(["--actual-image", "--repo", "/fixture"])
        self.assertTrue(options.actual_image)
        self.assertEqual(options.internal_scenario, "all")

    def test_non_linux_refuses_before_any_native_import_or_key_access(self):
        with patch.object(helper.sys, "platform", "darwin"), \
             patch.object(helper.importlib.util, "find_spec") as find, \
             patch.object(helper.os, "open") as opened:
            with self.assertRaisesRegex(helper.FixtureFailure, "linux_pinned_image_required"):
                helper.verify_sources(Path("/fixture"))
        find.assert_not_called()
        opened.assert_not_called()

    def test_source_version_hash_and_launcher_pins_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            repo, installed = base / "repo", base / "installed"
            evidence = repo / "reports/f1s-contract-evidence"
            evidence.mkdir(parents=True)
            installed.mkdir()
            launcher = repo / "scripts/lifecycle/sglang_file_auth.py"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("# isolated launcher fixture\n")
            source = installed / "native.py"
            source.write_text("# isolated installed-source fixture\n")
            expected = {"packages": {"sglang": "0.5.14"}, "source_files": {
                "native.py": {"bytes": source.stat().st_size,
                              "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}}
            (evidence / "installed-static.json").write_text(json.dumps(expected))
            provenance = {"path": "scripts/lifecycle/sglang_file_auth.py",
                          "image_id": helper.IMAGE_ID,
                          "sha256": hashlib.sha256(launcher.read_bytes()).hexdigest()}
            (evidence / "launcher-provenance.json").write_text(json.dumps(provenance))
            with patch.object(helper.sys, "platform", "linux"), \
                 patch.object(helper.importlib.metadata, "version", return_value="0.5.14") as version, \
                 patch.object(helper.importlib.util, "find_spec",
                              return_value=SimpleNamespace(origin=str(installed / "__init__.py"))):
                self.assertEqual(helper.verify_sources(repo), launcher)
                version.return_value = "different"
                with self.assertRaisesRegex(helper.FixtureFailure, "installed_version_mismatch"):
                    helper.verify_sources(repo)
                version.return_value = "0.5.14"
                source.write_bytes(b"x" * source.stat().st_size)
                with self.assertRaisesRegex(helper.FixtureFailure, "installed_source_hash_mismatch"):
                    helper.verify_sources(repo)

    def test_fixture_key_created_exclusively_and_existing_file_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            key, config = base / "key", base / "config.json"
            with patch.object(helper, "KEY_PATH", key), patch.object(helper, "CONFIG_PATH", config), \
                 patch.object(helper, "require_private_tmpfs"):
                with helper.fixture_files(b"{}") as sentinel:
                    self.assertTrue(key.read_bytes() == sentinel.encode(), "fixture key bytes changed")
                    self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
                    self.assertTrue(all(33 <= b <= 126 for b in key.read_bytes()), "invalid fixture token")
                    self.assertEqual(config.read_bytes(), b"{}")
                self.assertFalse(key.exists())
                self.assertFalse(config.exists())
                original = secrets.token_bytes(48)
                key.write_bytes(original)
                key.chmod(0o600)
                with self.assertRaises(FileExistsError):
                    with helper.fixture_files(b"{}"):
                        self.fail("existing protected key accepted")
                self.assertTrue(key.read_bytes() == original, "existing key overwritten")
                self.assertFalse(config.exists())

    def test_failure_output_never_relays_backend_exception_or_logs(self):
        sentinel = secrets.token_urlsafe(32)
        capture = io.StringIO()

        def fail(_repo, _scenario, logs):
            print(sentinel)
            logs.write(sentinel)
            raise RuntimeError(sentinel)

        with patch.object(helper, "run_actual", side_effect=fail), redirect_stdout(capture):
            result = helper.main(["--actual-image", "--repo", "/fixture"])
        self.assertEqual(result, 2)
        self.assertTrue(sentinel not in capture.getvalue(), "sentinel escaped failure output")
        self.assertEqual(json.loads(capture.getvalue()),
                         {"status": "FAIL", "code": "actual_image_fixture_failed"})

    def test_asgi_driver_preserves_body_and_disconnect_events(self):
        events = []

        async def app(_scope, receive, send):
            events.append(await receive())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
            events.append(await receive())
            await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})

        status, content, _ = asyncio.run(helper.asgi_request(
            app, "/fixture", method="POST", body={"fixture": True}, disconnect=True))
        self.assertEqual(status, 200)
        self.assertEqual(content, b"data: first\n\ndata: [DONE]\n\n")
        self.assertEqual(json.loads(events[0]["body"]), {"fixture": True})
        self.assertEqual(events[1], {"type": "http.disconnect"})

    def test_abort_child_requires_real_abort_exit_not_generic_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            key, config = Path(directory) / "key", Path(directory) / "config"
            with patch.object(helper, "KEY_PATH", key), patch.object(helper, "CONFIG_PATH", config), \
                 patch.object(helper, "disposable_child", return_value=nullcontext(
                     SimpleNamespace(returncode=2))) as child, \
                 patch.object(helper, "read_process_output", return_value=(b'{"status":"FAIL"}', b"")):
                with self.assertRaisesRegex(helper.FixtureFailure, "warmup_failure_subprocess_not_closed"):
                    helper.run_failure_children(Path("/fixture"))
                args = child.call_args.args[0]
                self.assertIn("--actual-image", args)
                self.assertIn("warmup-auth-failure", args)
                self.assertFalse(key.exists())

    def test_cuda_seam_blocks_all_actual_initialization(self):
        cuda = SimpleNamespace(**{name: lambda: None for name in helper.HARDWARE_STUBS},
                               _lazy_init=lambda: None)
        with helper.cuda_discovery_fixture(SimpleNamespace(cuda=cuda)):
            self.assertEqual(cuda.device_count(), 2)
            self.assertEqual(cuda.get_device_capability(), (12, 0))
            with self.assertRaisesRegex(helper.FixtureFailure, "gpu_initialization_refused"):
                cuda._lazy_init()


if __name__ == "__main__":
    unittest.main()
