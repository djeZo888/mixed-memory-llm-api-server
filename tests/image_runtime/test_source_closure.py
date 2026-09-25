"""Protected image source binding fixtures; no host/service/image operations."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('h005_image_source_closure', ROOT / 'scripts/image_runtime/service.py')
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


class ImageSourceClosure(unittest.TestCase):
    def config(self):
        return {
            'source_sha256': {name: hashlib.sha256((ROOT / 'scripts/image_runtime' / name).read_bytes()).hexdigest()
                              for name in service.RUNTIME_SOURCE_FILES},
            'release_source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                      for name in service.RELEASE_SOURCE_FILES},
        }

    def protected(self, path):
        path = Path(path)
        if path.is_relative_to(service.RELEASE):
            return (ROOT / path.relative_to(service.RELEASE)).read_bytes()
        return (ROOT / 'scripts/image_runtime' / path.relative_to(service.BASE / 'source')).read_bytes()

    def test_exact_manifest_and_every_required_protected_source_is_read(self):
        manifest = json.loads((ROOT / 'scripts/image_runtime/source-closure.json').read_text())
        self.assertEqual(manifest['release_root'], str(service.RELEASE))
        self.assertEqual(manifest['runtime_root'], str(service.BASE))
        self.assertEqual(manifest['release_files'], list(service.RELEASE_SOURCE_FILES))
        self.assertEqual(manifest['runtime_files'], list(service.RUNTIME_SOURCE_FILES))
        self.assertEqual(len(service.RELEASE_SOURCE_FILES), len(set(service.RELEASE_SOURCE_FILES)))
        with patch.object(service, 'protected_file', side_effect=self.protected) as read:
            service.verify_source_closure(self.config())
        self.assertEqual([call.args[0] for call in read.call_args_list],
                         [service.BASE / 'source' / name for name in service.RUNTIME_SOURCE_FILES] +
                         [service.RELEASE / name for name in service.RELEASE_SOURCE_FILES])

    def test_old_partial_extra_or_wrong_source_map_stays_closed(self):
        original = self.config()
        for field in original:
            for defect in ('missing_map', 'missing_dependency', 'extra_path', 'invalid_digest', 'drift'):
                config = copy.deepcopy(original)
                name = next(iter(config[field]))
                if defect == 'missing_map':
                    del config[field]
                elif defect == 'missing_dependency':
                    del config[field][name]
                elif defect == 'extra_path':
                    config[field]['../unreviewed.py'] = '0' * 64
                elif defect == 'invalid_digest':
                    config[field][name] = None
                else:
                    config[field][name] = '0' * 64
                with self.subTest(field=field, defect=defect), \
                        patch.object(service, 'protected_file', side_effect=self.protected), \
                        self.assertRaises(RuntimeError):
                    service.verify_source_closure(config)

    def test_each_new_dependency_failure_aborts_source_check(self):
        config = self.config()
        for name in ('scripts/control/hardware_latch.py', 'scripts/lifecycle/hardware_policy.py',
                     'scripts/runtime/h005_runtime_binding.py', 'scripts/runtime/qwen38_oci.py',
                     'scripts/runtime/verify_adaptive_idle_overlay.py'):
            def read(path):
                if path == service.RELEASE / name:
                    raise RuntimeError('synthetic_unprotected_dependency')
                return self.protected(path)
            with self.subTest(name=name), patch.object(service, 'protected_file', side_effect=read), \
                    self.assertRaisesRegex(RuntimeError, 'synthetic_unprotected_dependency'):
                service.verify_source_closure(config)

    def test_runtime_refuses_old_image_or_incomplete_build_before_checkpoint_access(self):
        binding = Mock()
        binding.path.return_value = str(service.BASE)
        binding.read_json.return_value = {'schema_version': 1, 'owner': service.OWNER,
                                          'image_id': 'sha256:' + 'a' * 64}
        with patch.object(service.os, 'geteuid', return_value=0), \
                patch.object(service.RegisteredStorageBinding, 'load', return_value=binding), \
                patch.object(service, 'load_runtime_binding', return_value={'image': {'image_id': 'sha256:' + 'b' * 64}}), \
                self.assertRaisesRegex(RuntimeError, 'runtime_image_binding_mismatch'):
            service.Runtime()
        self.assertEqual(binding.read_json.call_count, 1)
        binding.read_json.reset_mock()
        with patch.object(service.os, 'geteuid', return_value=0), \
                patch.object(service.RegisteredStorageBinding, 'load', return_value=binding), \
                patch.object(service, 'load_runtime_binding', side_effect=ValueError('h005_runtime_blocked_by_build')), \
                self.assertRaisesRegex(ValueError, 'h005_runtime_blocked_by_build'):
            service.Runtime()
        self.assertEqual(binding.read_json.call_count, 1)

    def test_fresh_isolated_image_owner_import_uses_only_declared_release(self):
        # Actual checked-in modules are imported without GPU/native packages.
        # This is dependency closure evidence, not installed protection or build.
        with tempfile.TemporaryDirectory(prefix='h005-image-closure-') as temporary:
            root = Path(temporary)
            for name in service.RELEASE_SOURCE_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            owner = root / 'service.py'
            shutil.copyfile(ROOT / 'scripts/image_runtime/service.py', owner)
            script = '''
import importlib.util, pathlib, sys
root = pathlib.Path(sys.argv[1])
assert sys.flags.isolated and pathlib.Path.cwd() == pathlib.Path('/')
sys.path.insert(0, str(root / 'scripts'))
spec = importlib.util.spec_from_file_location('image_owner', root / 'service.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for name, loaded in list(sys.modules.items()):
    if name.split('.')[0] in {'common', 'control', 'install', 'lifecycle', 'runtime'}:
        if getattr(loaded, '__file__', None):
            assert pathlib.Path(loaded.__file__).is_relative_to(root), name
assert 'lifecycle.hardware_policy' in sys.modules
assert 'control.hardware_latch' in sys.modules
assert 'runtime.h005_runtime_binding' in sys.modules
assert 'runtime.qwen38_oci' in sys.modules
print('PASS_DECLARED_DEPENDENCY_IMPORTS_ONLY')
'''
            result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(root)],
                                    cwd='/', capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'PASS_DECLARED_DEPENDENCY_IMPORTS_ONLY')


if __name__ == '__main__':
    unittest.main()
