"""Actual candidate launcher import/guards; no native imports or launch."""
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LaunchGuardTests(unittest.TestCase):
    def test_image_native_launch_retains_every_original_argument(self):
        import ast
        import subprocess
        module = load('scripts/image_runtime/native_server.py', 'adaptive_image_native')
        original = subprocess.check_output(['git', 'show', 'deba8af306cb0b3f87ddf8a2ed669d2eae1ac076:scripts/image_runtime/native_server.py'], text=True)
        method = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef) and n.name == 'launch_argv')
        scope = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<original launch argv>', 'exec'), scope)
        self.assertEqual(module.launch_argv(), scope['launch_argv']())

    def test_launchers_pin_verifier_before_import_and_overlay_before_native(self):
        for rel, name, target in [('scripts/image_runtime/native_server.py', 'guard_image', 'image'),
                                  ('scripts/runtime/sglang38_pair_file_auth.py', 'guard_text', 'text')]:
            module = load(rel, name)
            verifier_raw = (ROOT / 'scripts/runtime/verify_adaptive_idle_overlay.py').read_bytes()
            self.assertEqual(module.ADAPTIVE_VERIFIER_SHA256, hashlib.sha256(verifier_raw).hexdigest())
            sentinel = NS(is_symlink=lambda: False, read_bytes=lambda: b'tampered verifier')
            with self.subTest(target=target), patch.object(module, 'Path', return_value=sentinel), \
                    patch.object(module.importlib.util, 'spec_from_file_location') as import_spec:
                with self.assertRaisesRegex((RuntimeError, ValueError), 'verifier_mismatch'):
                    module.verify_adaptive_overlay()
                import_spec.assert_not_called()
            calls = []
            candidate = NS(verify_installed=lambda *args: calls.append(args))
            fake_spec = NS(loader=NS(exec_module=lambda module: None))
            sentinel.read_bytes = lambda: verifier_raw
            with patch.object(module, 'Path', return_value=sentinel), \
                    patch.object(module.importlib.util, 'spec_from_file_location', return_value=fake_spec), \
                    patch.object(module.importlib.util, 'module_from_spec', return_value=candidate):
                module.verify_adaptive_overlay()
            self.assertEqual(calls, [('/opt/llmctl/adaptive-idle/' + target + '.json', module.ADAPTIVE_OVERLAY_SHA256, target)])


if __name__ == '__main__':
    unittest.main()
