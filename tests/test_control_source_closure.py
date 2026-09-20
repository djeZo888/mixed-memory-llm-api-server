"""Control startup source protection only; no installation/composition actions."""
import json
from pathlib import Path
import sys
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

    def test_new_concurrent_imports_cannot_skip_startup_protected_file_validation(self):
        paths = ('scripts/lifecycle/slot_state.py', 'scripts/lifecycle/concurrent_profiles.py',
                 'scripts/runtime/sglang38_pair_file_auth.py')
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


if __name__ == '__main__':
    unittest.main()
