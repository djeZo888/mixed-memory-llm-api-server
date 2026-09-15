"""Fixed cache environment contracts on the worker; no VM, GPU, model or key.

The literal expectations are independent of the production constants so edits
to all production copies cannot silently redefine the reviewed path contract.
These source tests do not prove actual-image resolver or CUDA cache behavior.
"""
from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lifecycle import qwen_next
from lifecycle import sglang_file_auth as launcher


EXPECTED_CACHE_ENVIRONMENT = {
    "HF_HOME": "/cache/huggingface",
    "XDG_CACHE_HOME": "/cache",
    "TRITON_CACHE_DIR": "/cache/triton",
    "TORCHINDUCTOR_CACHE_DIR": "/cache/torchinductor",
    "SGLANG_DG_CACHE_DIR": "/cache/deep_gemm",
    "SGLANG_CACHE_DIR": "/cache/sglang",
    "FLASHINFER_WORKSPACE_BASE": "/cache/flashinfer",
    "CUDA_CACHE_PATH": "/cache/cuda",
    "TORCH_EXTENSIONS_DIR": "/cache/torch_extensions",
}
EXPECTED_RUNTIME_ENVIRONMENT = {
    **EXPECTED_CACHE_ENVIRONMENT,
    "DISABLE_OPENAPI_DOC": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}
PUBLIC_BUILD_METADATA = {
    "SGLANG_BUILD_COMMIT": "49e384ce9d304648e9959666ecb8ce8cd98d0deb",
    "SGLANG_BUILD_URL": "https://github.com/sgl-project/sglang/actions/runs/28210048245",
    "SGLANG_IMAGE_TAG": "lmsysorg/sglang:v0.5.14",
}


def valid_environment():
    return {**EXPECTED_RUNTIME_ENVIRONMENT, **PUBLIC_BUILD_METADATA}


def invalid_cache_environments():
    for name, expected in EXPECTED_CACHE_ENVIRONMENT.items():
        missing = valid_environment()
        del missing[name]
        yield name, "missing", missing
        for kind, value in (
            ("empty", ""),
            ("outside_cache", "/root/.cache"),
            ("prefix_lookalike", "/cache-other/entry"),
            ("parent_escape", "/cache/../root/entry"),
            ("other_cache_directory", "/cache/another"),
            ("trailing_slash", expected + "/"),
            ("leading_space", " " + expected),
            ("newline", expected + "\n"),
            ("home_expression", "~/.cache"),
        ):
            yield name, kind, {**valid_environment(), name: value}


def unknown_sglang_environments():
    for name in (
        "SGLANG_", "SGLANG_UNKNOWN", "SGLANG_CACHE_DIR_EXTRA",
        "SGLANG_DG_CACHE_DIR_EXTRA", "SGLANG_CACHE_DIR_PLUGIN",
        "SGLANG_BUILD_COMMIT_EXTRA", "SGLANG_ENABLE_GRPC", "SGLANG_USE_RAY",
        "SGLANG_PLUGINS", "SGLANG_PLUGIN_PATH", "SGLANG_SKIP_SERVER_WARMUP",
        "SGLANG_ENABLE_TORCH_COMPILE",
    ):
        for value in ("", "0", "1", "/cache/sglang"):
            yield name, value, {**valid_environment(), name: value}


def cli():
    return ["--key-file", "/run/secrets/llm-api-key", "--warmup-timeout", "600"] + [
        item for pair in launcher.FIXED_FLAGS.items() for item in pair
    ]


class CacheEnvironmentTests(unittest.TestCase):
    def test_runtime_profile_adapter_and_launcher_agree_with_reviewed_literal(self):
        profile = json.loads((ROOT / "configs/runtimes/sglang-qwen-next-0.5.14.json").read_text())
        self.assertEqual(launcher.FIXED_CACHE_ENVIRONMENT, EXPECTED_CACHE_ENVIRONMENT)
        self.assertEqual(qwen_next.ENVIRONMENT, EXPECTED_RUNTIME_ENVIRONMENT)
        self.assertEqual(profile["environment"], EXPECTED_RUNTIME_ENVIRONMENT)
        self.assertEqual(profile["environment"], qwen_next.ENVIRONMENT)
        self.assertNotIn("HOME", profile["environment"])
        self.assertNotIn("FLASHINFER_WORKSPACE_DIR", profile["environment"])

    def test_reviewed_environment_accepts_without_changes_or_home_injection(self):
        for home in (None, "/root", "/home/fixture-operator"):
            env = valid_environment()
            if home is not None:
                env["HOME"] = home
            with self.subTest(home=home), mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(launcher.importlib.metadata, "version", return_value="0.5.14") as version, \
                 mock.patch.object(launcher.importlib.metadata, "entry_points", return_value={}):
                launcher.validate_environment()
                version.assert_called_once_with("sglang")
                self.assertEqual(dict(os.environ), env)

    def test_adapter_preserves_inherited_home(self):
        for home in (None, "/root", "/home/fixture-operator"):
            inherited = {"PATH": "/usr/local/bin:/usr/bin"}
            if home is not None:
                inherited["HOME"] = home
            image = {"Config": {"Env": [name + "=" + value for name, value in inherited.items()]}}
            result = qwen_next.image_environment(image, {"_runtime": {"environment": EXPECTED_RUNTIME_ENVIRONMENT}})
            self.assertEqual(result, {**inherited, **EXPECTED_RUNTIME_ENVIRONMENT})
            self.assertEqual(result.get("HOME"), home)
            if home is None:
                self.assertNotIn("HOME", result)

    def assert_environment_refused(self, env):
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(launcher.importlib.metadata, "version") as version, \
             mock.patch.object(launcher.importlib.metadata, "entry_points") as points:
            with self.assertRaisesRegex(launcher.LaunchError, "^launch_environment_invalid$"):
                launcher.validate_environment()
            version.assert_not_called()
            points.assert_not_called()
            self.assertEqual(dict(os.environ), env)

    def test_every_required_cache_is_exact_and_never_defaulted(self):
        for name, kind, env in invalid_cache_environments():
            with self.subTest(name=name, kind=kind):
                self.assert_environment_refused(env)

    def test_cache_exceptions_do_not_admit_unknown_or_control_sglang_names(self):
        for name, value, env in unknown_sglang_environments():
            with self.subTest(name=name, value=value):
                self.assert_environment_refused(env)

    def test_missing_or_altered_cache_main_stops_before_native_imports_and_key(self):
        self.assert_main_refusals(invalid_cache_environments())

    def test_unknown_sglang_main_stops_before_native_imports_and_key(self):
        self.assert_main_refusals(unknown_sglang_environments())

    def assert_main_refusals(self, cases):
        original_import = __import__
        native_imports = []

        def guarded_import(name, *args, **kwargs):
            if name == "sglang" or name.startswith("sglang."):
                native_imports.append(name)
                raise AssertionError("native import before environment refusal")
            return original_import(name, *args, **kwargs)

        for name, kind, env in cases:
            with self.subTest(name=name, kind=kind), mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(launcher, "read_key") as read_key, \
                 mock.patch.object(launcher, "validate_environment", wraps=launcher.validate_environment) as validate, \
                 mock.patch.object(launcher.importlib.metadata, "version") as version, \
                 mock.patch.object(launcher.LOGGER, "error") as log, \
                 mock.patch("builtins.__import__", side_effect=guarded_import):
                self.assertEqual(launcher.main(cli()), 1)
                validate.assert_called_once_with()
                version.assert_not_called()
                read_key.assert_not_called()
                self.assertEqual(native_imports, [])
                log.assert_called_once_with("sglang_file_auth_launch_failed")
                self.assertEqual(dict(os.environ), env)

    def test_cache_exceptions_preserve_optional_exact_build_metadata(self):
        self.assertEqual(launcher.BUILD_METADATA, PUBLIC_BUILD_METADATA)
        for count in range(4):
            for names in itertools.combinations(PUBLIC_BUILD_METADATA, count):
                env = {**EXPECTED_RUNTIME_ENVIRONMENT, **{name: PUBLIC_BUILD_METADATA[name] for name in names}}
                with self.subTest(names=names), mock.patch.dict(os.environ, env, clear=True), \
                     mock.patch.object(launcher.importlib.metadata, "version", return_value="0.5.14"), \
                     mock.patch.object(launcher.importlib.metadata, "entry_points", return_value={}):
                    launcher.validate_environment()
                    self.assertEqual(dict(os.environ), env)
        for name, expected in PUBLIC_BUILD_METADATA.items():
            for value in ("", expected + "-altered", " " + expected, expected + "\n"):
                with self.subTest(name=name, value=value):
                    self.assert_environment_refused({**valid_environment(), name: value})

    def test_valid_caches_cannot_bypass_docs_version_or_plugin_guards(self):
        for docs in (None, "", "0", "true"):
            env = valid_environment()
            if docs is None:
                del env["DISABLE_OPENAPI_DOC"]
            else:
                env["DISABLE_OPENAPI_DOC"] = docs
            with self.subTest(docs=docs):
                self.assert_environment_refused(env)
        with mock.patch.dict(os.environ, valid_environment(), clear=True), \
             mock.patch.object(launcher.importlib.metadata, "version", return_value="other") as version, \
             mock.patch.object(launcher.importlib.metadata, "entry_points", return_value={}) as points:
            with self.assertRaisesRegex(launcher.LaunchError, "^launch_version_invalid$"):
                launcher.validate_environment()
            points.assert_not_called()
            version.side_effect = launcher.importlib.metadata.PackageNotFoundError
            with self.assertRaisesRegex(launcher.LaunchError, "^launch_version_invalid$"):
                launcher.validate_environment()
            version.side_effect, version.return_value = None, "0.5.14"
            for group in ("sglang", "sglang_plugins", "SGLANG_plugins"):
                for entry_points in ({group: []}, types.SimpleNamespace(groups={group})):
                    points.return_value = entry_points
                    with self.subTest(group=group, points=entry_points), \
                         self.assertRaisesRegex(launcher.LaunchError, "^launch_plugins_unsupported$"):
                        launcher.validate_environment()


if __name__ == "__main__":
    unittest.main()
