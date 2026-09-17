"""Worker control tests with private synthetic files and synthetic module seams.

These run the repository launcher and helper control flow on the worker. The
fake installed module below is only a test harness: pinned-image native
ServerArgs/source/application execution remains NOT_TESTED by this file.
"""
import dataclasses
import importlib.util
import logging
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load("f1e2_negative_helper_control", ROOT / "tests/lifecycle/sglang_fixture/run_pinned_image.py")
launcher = load("f1e2_negative_launcher_control", ROOT / "scripts/lifecycle/sglang_file_auth.py")


@dataclasses.dataclass
class SyntheticServerArgs:
    """Explicitly synthetic typed parser result, never actual-image evidence."""
    api_key: object = None
    admin_api_key: object = None
    tokenizer_worker_num: int = 1
    host: str = "0.0.0.0"
    port: int = 30003
    model_path: str = "/models"
    served_model_name: str = "qwen3-coder-next"
    context_length: int = 32768
    tp_size: int = 2
    tool_call_parser: str = "qwen3_coder"
    mem_fraction_static: float = 0.75
    max_running_requests: int = 1
    load_format: str = "safetensors"
    dp_size: int = 1
    nnodes: int = 1
    node_rank: int = 0
    base_gpu_id: int = 0
    gpu_id_step: int = 1
    disaggregation_mode: str = "null"
    grpc_mode: bool = False
    use_ray: bool = False
    encoder_only: bool = False
    enable_ssl_refresh: bool = False
    tool_server: object = None
    enable_http2: bool = False
    skip_server_warmup: bool = False
    skip_tokenizer_init: bool = False
    trust_remote_code: bool = False
    enable_metrics: bool = False
    quantization: object = None
    tokenizer_path: object = None


class PrivateSyntheticKeyCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)
        self.key = self.base / "key"
        self.sentinel = secrets.token_urlsafe(32)
        self.key.write_bytes(self.sentinel.encode())
        self.key.chmod(0o600)
        self.original = self.key.stat()
        self.path_patch = patch.object(helper, "KEY_PATH", self.key)
        self.path_patch.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.path_patch.stop)

    def assertRestored(self):
        restored = self.key.stat()
        self.assertEqual((restored.st_dev, restored.st_ino),
                         (self.original.st_dev, self.original.st_ino))
        self.assertTrue(self.key.read_bytes() == self.sentinel.encode(), "synthetic key changed")
        self.assertEqual(stat.S_IMODE(restored.st_mode), 0o600)
        self.assertEqual(list(self.base.iterdir()), [self.key])


class NegativeKeyFileControlTests(PrivateSyntheticKeyCase):
    def test_actual_local_synthetic_files_refuse_and_preserve_original_inode(self):
        for kind in ("missing", "symlink", "directory", "fifo", "mode0644", "mode0400",
                     "mode0000", "empty", "newline", "crlf", "space", "nul", "nonascii",
                     "oversized"):
            with self.subTest(kind=kind):
                with helper.negative_key_fixture(kind, self.sentinel) as available:
                    self.assertTrue(available)
                    with self.assertRaises(launcher.LaunchError) as failure:
                        launcher.read_key(self.key)
                    self.assertEqual(str(failure.exception), "key_file_invalid")
                self.assertRestored()

    def test_symlink_refused_without_reading_original_target(self):
        with helper.negative_key_fixture("symlink", self.sentinel):
            self.assertTrue(self.key.is_symlink())
            target = self.key.resolve()
            self.assertEqual(target.stat().st_ino, self.original.st_ino)
            with patch.object(launcher.os, "read", side_effect=AssertionError("symlink target read")):
                with self.assertRaises(launcher.LaunchError):
                    launcher.read_key(self.key)
        self.assertRestored()

    def test_missing_key_and_injected_body_failure_restore_original(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with helper.negative_key_fixture("missing", self.sentinel):
                self.assertFalse(self.key.exists())
                raise RuntimeError("synthetic failure")
        self.assertRestored()

    def test_wrong_owner_unavailable_is_reported_without_stat_fallback(self):
        # Only this worker control test simulates unavailable chown capability.
        with patch.object(helper.os, "fchown", side_effect=PermissionError) as chown:
            with helper.negative_key_fixture("wrong-owner", self.sentinel) as available:
                self.assertFalse(available)
                self.assertEqual(self.key.stat().st_uid, os.geteuid())
        chown.assert_called_once()
        self.assertRestored()

    def test_invalid_original_is_preserved_before_any_staging(self):
        self.key.chmod(0o644)
        with self.assertRaisesRegex(helper.FixtureFailure, "negative_fixture_key_identity_invalid"):
            with helper.negative_key_fixture("missing", self.sentinel):
                self.fail("unsafe original accepted")
        self.assertTrue(self.key.read_bytes() == self.sentinel.encode(), "synthetic key changed")
        self.assertEqual(list(self.base.iterdir()), [self.key])
        self.assertEqual(self.key.stat().st_ino, self.original.st_ino)


class NegativeBoundaryControlTests(PrivateSyntheticKeyCase):
    """Synthetic module wiring tests; real installed normalization NOT_TESTED."""

    def setUp(self):
        super().setUp()
        self.prepared = []
        self.cleanup_calls = []
        self.server = SimpleNamespace(
            app=SimpleNamespace(middleware_stack=None),
            launch_server=lambda *_a, **_k: None,
            Engine=SimpleNamespace(_launch_subprocesses=lambda **_k: None),
            uvicorn=SimpleNamespace(run=lambda *_a, **_k: None))
        self.args_module = ModuleType("sglang.srt.server_args")
        self.args_module.ServerArgs = SyntheticServerArgs
        self.args_module.prepare_server_args = self.prepare
        entrypoints = ModuleType("sglang.srt.entrypoints")
        entrypoints.http_server = self.server
        utils = ModuleType("sglang.srt.utils")
        utils.kill_process_tree = lambda *a, **k: self.cleanup_calls.append((a, k))
        auth = ModuleType("sglang.srt.utils.auth")
        auth.add_api_key_middleware = lambda *_a, **_k: None
        self.module_patch = patch.dict(sys.modules, {
            "sglang": ModuleType("sglang"), "sglang.srt": ModuleType("sglang.srt"),
            "sglang.srt.server_args": self.args_module,
            "sglang.srt.entrypoints": entrypoints,
            "sglang.srt.utils": utils, "sglang.srt.utils.auth": auth})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.env_patch = patch.object(launcher, "validate_environment")
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.chown_patch = patch.object(helper.os, "fchown", side_effect=PermissionError)
        self.chown_patch.start()
        self.addCleanup(self.chown_patch.stop)
        # Launcher parse_options intentionally keeps its exact production path.
        # The read seam maps only that path to this private synthetic worker key.
        self.real_read = launcher.read_key
        self.reader_patch = patch.object(launcher, "read_key", side_effect=self.read)
        self.reader_patch.start()
        self.addCleanup(self.reader_patch.stop)
        self.argv = ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600"] + [
            piece for pair in launcher.FIXED_FLAGS.items() for piece in pair]

    def prepare(self, argv):
        self.assertEqual(argv, [piece for pair in launcher.FIXED_FLAGS.items() for piece in pair])
        value = SyntheticServerArgs()
        self.prepared.append(value)
        return value

    def read(self, path):
        self.assertEqual(path, "/run/secrets/llm-api-key")
        return self.real_read(self.key)

    def run_matrix(self):
        return helper.check_negative_contracts(
            launcher, self.server, SyntheticServerArgs, self.argv, self.sentinel)

    def test_control_matrix_delegates_typed_prepare_and_enforces_order(self):
        result = self.run_matrix()
        self.assertEqual(len(result["key_files"]), 14)
        self.assertEqual(len(result["cli_modes"]), 19)
        self.assertEqual(len(result["normalized_mode_faults"]), 18)
        self.assertEqual(result["wrong_owner"], "NOT_TESTED_CAPABILITY_UNAVAILABLE")
        self.assertNotIn("wrong-owner", result["key_files"])
        self.assertEqual(len(self.prepared), 32)
        self.assertEqual(len({id(value) for value in self.prepared}), 32)
        self.assertTrue(all(type(value) is SyntheticServerArgs for value in self.prepared))
        self.assertEqual(len(self.cleanup_calls), 32)
        self.assertRestored()

    def test_normalization_failure_cannot_count_as_contract_refusal(self):
        with patch.object(self.args_module, "prepare_server_args", side_effect=ValueError("synthetic fault")):
            with self.assertRaisesRegex(helper.FixtureFailure, "negative_contract_boundary_order_changed"):
                self.run_matrix()
        self.assertRestored()

    def test_untyped_prepare_result_cannot_count_as_native_normalization(self):
        with patch.object(self.args_module, "prepare_server_args", return_value=SimpleNamespace()):
            with self.assertRaisesRegex(helper.FixtureFailure, "negative_contract_boundary_order_changed"):
                self.run_matrix()
        self.assertRestored()

    def test_unapplied_native_mode_fault_cannot_count_as_a_refusal(self):
        def missing_field(value, name):
            return False if name == "grpc_mode" else hasattr(value, name)

        with patch.object(helper, "hasattr", side_effect=missing_field, create=True):
            with self.assertRaisesRegex(helper.FixtureFailure, "negative_contract_boundary_order_changed"):
                self.run_matrix()
        self.assertRestored()

    def test_unexpected_key_acceptance_fails_even_if_auth_guard_rejects(self):
        with patch.object(launcher, "read_key", return_value=launcher._PrivateKey(self.sentinel)):
            with self.assertRaisesRegex(helper.FixtureFailure, "negative_contract_not_refused_before_launch"):
                self.run_matrix()
        self.assertRestored()

    def test_guarded_engine_entry_cannot_be_counted_as_safe_refusal(self):
        original_main = launcher.main

        def cross_boundary(argv):
            result = original_main(argv)
            try:
                self.server.Engine._launch_subprocesses()
            except helper.FixtureFailure:
                pass
            return result

        with patch.object(launcher, "main", side_effect=cross_boundary):
            with self.assertRaisesRegex(helper.FixtureFailure, "negative_contract_not_refused_before_launch"):
                self.run_matrix()
        self.assertRestored()

    def test_normalizer_log_disclosure_is_not_hidden_by_fixed_launcher_error(self):
        original_prepare = self.args_module.prepare_server_args

        def leaking_prepare(argv):
            logging.getLogger("f1e2.synthetic.normalizer").warning(self.sentinel)
            return original_prepare(argv)

        with patch.object(self.args_module, "prepare_server_args", side_effect=leaking_prepare):
            with self.assertRaisesRegex(helper.FixtureFailure, "sentinel_disclosure"):
                self.run_matrix()
        self.assertRestored()


if __name__ == "__main__":
    unittest.main()
