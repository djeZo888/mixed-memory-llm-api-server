"""Control startup source protection only; no installation/composition actions."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from control import installation as protection


class ConcurrentImportProtection(unittest.TestCase):
    def test_runtime_protection_sets_match_reviewed_manifest(self):
        manifest = json.loads((ROOT / 'scripts/control/source-closure.json').read_text())
        self.assertEqual(set(manifest['recovery_files']), set(protection.RECOVERY_FILES))
        self.assertEqual(set(manifest['normal_files']), set(protection.NORMAL_FILES))

    def test_acceptance_source_identity_is_available_in_normal_snapshot(self):
        from lifecycle.concurrent_profiles import source_identity
        manifest = json.loads((ROOT / 'scripts/control/source-closure.json').read_text())
        files = set(manifest['normal_files']) | set(manifest['recovery_files'])
        missing = [name for name in source_identity() if name not in files and
                   not any(name.startswith(directory + '/') for directory in manifest['normal_profile_directories'])]
        self.assertEqual(missing, [])

    def test_new_concurrent_imports_cannot_skip_startup_protected_file_validation(self):
        paths = ('scripts/lifecycle/slot_state.py', 'scripts/lifecycle/concurrent_profiles.py',
                 'scripts/runtime/sglang38_pair_file_auth.py',
                 'scripts/lifecycle/hardware_policy.py', 'scripts/control/hardware_latch.py',
                 'scripts/runtime/verify_adaptive_idle_overlay.py',
                 'scripts/runtime/h005_runtime_binding.py', 'configs/runtimes/h005-runtime-binding.json')
        for relative in paths:
            calls = []
            def protected(path, **kwargs):
                calls.append(path)
                if path == ROOT / relative:
                    self.assertIn('root_device', kwargs)
                    raise protection.InstallationError()
                return b'synthetic-fixture-key-material-32-bytes'
            with self.subTest(relative=relative), \
                 patch.object(protection, 'SOURCE_ROOT', ROOT), \
                 patch.object(protection.os, 'geteuid', return_value=0), \
                 patch.object(protection, 'protected_file', side_effect=protected), \
                 patch.object(protection, '_control_config', return_value={'schema_version': 1}), \
                 self.assertRaises(protection.InstallationError):
                protection.validate_installation()
            self.assertIn(ROOT / relative, calls)
            self.assertNotIn(protection.KEY_SOURCE, calls)

    def test_fresh_complete_control_and_node_imports_include_new_runtime_binding(self):
        from control import node_installation
        manifest = json.loads((ROOT / 'scripts/control/source-closure.json').read_text())
        files = set(protection.RECOVERY_FILES) | set(protection.NORMAL_FILES) | set(node_installation.SOURCE_FILES)
        for directory in manifest['normal_profile_directories']:
            files.update(str(path.relative_to(ROOT)) for path in (ROOT / directory).glob('*.json'))
        with tempfile.TemporaryDirectory(prefix='h005-control-node-closure-') as temporary:
            root = Path(temporary)
            for name in files:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            script = '''
import pathlib, sys
root = pathlib.Path(sys.argv[1])
assert sys.flags.isolated and pathlib.Path.cwd() == pathlib.Path('/')
sys.path.insert(0, str(root / 'scripts'))
from control import adapter, node_serve, node_action_owner, node_observation, node_resources
from lifecycle import concurrent_profiles, hardware_policy
from runtime import h005_runtime_binding, verify_adaptive_idle_overlay
assert concurrent_profiles.source_identity()
assert h005_runtime_binding.load(require_complete=False)['runtime_source_commit'] == 'f9d9b5191534581d854067507922af2b56790710'
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in {'common', 'control', 'install', 'lifecycle', 'runtime'}:
        if getattr(module, '__file__', None):
            assert pathlib.Path(module.__file__).is_relative_to(root), name
print('PASS_DECLARED_CONTROL_NODE_IMPORTS_ONLY')
'''
            result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(root)],
                                    cwd='/', capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'PASS_DECLARED_CONTROL_NODE_IMPORTS_ONLY')


if __name__ == '__main__':
    unittest.main()
