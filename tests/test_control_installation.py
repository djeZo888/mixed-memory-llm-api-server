"""Protected control installation checks using temporary worker files only.

Fixed production paths, effective-root admission and owner/boundary parameters
are patched in-process for validation fixtures. Descriptor reads and metadata
checks remain real. A separate fresh Python process imports the exact recovery
manifest from a temporary copy with cwd=/ and no configs, data or credentials.
This does not install a service or establish Linux boot/mount-loss acceptance.
"""
from __future__ import annotations

from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from control import installation
from control.installation import InstallationError, protected_file


class ProtectedFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='u1b-protected-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'protected.json'
        self.path.write_bytes(b'{"fixture":true}')
        self.path.chmod(0o600)

    def read(self, **kwargs):
        return protected_file(self.path, uid=os.geteuid(), boundary=self.root, **kwargs)

    def test_protected_regular_file_and_exact_device(self):
        self.assertEqual(self.read(modes={0o600}, root_device=self.root.stat().st_dev),
                         b'{"fixture":true}')

    def test_missing_symlink_hardlink_directory_and_writable_file_refused(self):
        self.path.unlink()
        with self.assertRaises(InstallationError):
            self.read()
        other = self.root / 'other'
        other.write_bytes(b'fixture')
        other.chmod(0o600)
        self.path.symlink_to(other)
        with self.assertRaises(InstallationError):
            self.read()
        self.path.unlink()
        os.link(other, self.path)
        with self.assertRaises(InstallationError):
            self.read()
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(InstallationError):
            self.read()
        self.path.rmdir()
        self.path.write_bytes(b'fixture')
        self.path.chmod(0o620)
        with self.assertRaises(InstallationError):
            self.read()

    def test_bounds_owner_mode_and_root_device_refused(self):
        for options in ({'maximum': 1}, {'modes': {0o400}},
                        {'root_device': self.root.stat().st_dev + 1}):
            with self.subTest(options=options), self.assertRaises(InstallationError):
                self.read(**options)
        with self.assertRaises(InstallationError):
            protected_file(self.path, uid=os.geteuid() + 1, boundary=self.root)

    def test_writable_or_symlink_parent_refused(self):
        self.root.chmod(0o720)
        try:
            with self.assertRaises(InstallationError):
                self.read()
        finally:
            self.root.chmod(0o700)
        directory = self.root / 'real'
        directory.mkdir(mode=0o700)
        target = directory / 'file'
        target.write_bytes(b'fixture')
        target.chmod(0o600)
        link = self.root / 'link'
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(InstallationError):
            protected_file(link / 'file', uid=os.geteuid(), boundary=self.root)

    def test_replacement_during_read_refused(self):
        original_read = os.read
        def replace_after_read(fd, size):
            value = original_read(fd, size)
            replacement = self.root / 'replacement'
            replacement.write_bytes(value)
            replacement.chmod(0o600)
            os.replace(replacement, self.path)
            return value
        with patch.object(installation.os, 'read', side_effect=replace_after_read), \
                self.assertRaises(InstallationError):
            self.read()


class InstallationValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='u1b-installation-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / 'source'
        self.config = self.root / 'etc/control.json'
        self.key = self.root / 'etc/control-api-key'
        self.credential = self.root / 'run/credentials/control-api-key'
        self.uid = os.geteuid()
        self.value = b'inert-disposable-control-fixture-key'
        for relative in installation.RECOVERY_FILES:
            self.write(self.source / relative, b'# synthetic protected source\n', mode=0o644)
        self.write(self.config, b'{"schema_version":1}')
        self.write(self.key, self.value)
        self.write(self.credential, self.value, mode=0o400)
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.multiple(installation, SOURCE_ROOT=self.source,
                                          CONFIG_FILE=self.config, KEY_SOURCE=self.key,
                                          CREDENTIAL_FILE=self.credential,
                                          __file__=str(self.source / 'scripts/control/installation.py')))
        stack.enter_context(patch.object(installation.os, 'geteuid', return_value=0))
        # Map only the root-device query to this synthetic filesystem. All
        # protected reads retain actual descriptors, no-follow and mode checks.
        stack.enter_context(patch.object(installation, 'Path',
                                        side_effect=lambda value: self.root if value == '/' else Path(value)))
        def fixture_read(path, **kwargs):
            return protected_file(path, uid=self.uid, boundary=self.root, **kwargs)
        self.reader = stack.enter_context(patch.object(installation, 'protected_file', side_effect=fixture_read))

    def write(self, path, value, mode=0o600):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            path.chmod(0o600)
        path.write_bytes(value)
        path.chmod(mode)

    def test_exact_fixed_config_keys_and_source_closure_validate(self):
        self.assertEqual(installation.validate_installation(), self.value)
        paths = [call.args[0] for call in self.reader.call_args_list]
        self.assertEqual(paths, [self.source / relative for relative in installation.RECOVERY_FILES]
                         + [self.config, self.key, self.credential])
        for call in self.reader.call_args_list[:-1]:
            self.assertEqual(call.kwargs['root_device'], self.root.stat().st_dev)
        self.assertNotIn('root_device', self.reader.call_args_list[-1].kwargs)

    def test_source_missing_writable_or_symlink_refused(self):
        source = self.source / installation.RECOVERY_FILES[0]
        source.unlink()
        with self.assertRaises(InstallationError):
            installation.validate_installation()
        self.write(source, b'# fixture', mode=0o666)
        with self.assertRaises(InstallationError):
            installation.validate_installation()
        source.unlink()
        source.symlink_to(self.config)
        with self.assertRaises(InstallationError):
            installation.validate_installation()

    def test_effective_owner_and_source_location_cannot_be_overridden(self):
        with patch.object(installation.os, 'geteuid', return_value=1234), \
                self.assertRaises(InstallationError):
            installation.validate_installation()
        with patch.object(installation, '__file__', str(self.root / 'other/installation.py')), \
                self.assertRaises(InstallationError):
            installation.validate_installation()

    def test_config_unknown_fields_duplicate_types_and_invalid_json_refused(self):
        for raw in (b'{}', b'{"schema_version":1,"host":"127.0.0.1"}',
                    b'{"schema_version":1,"schema_version":1}', b'{"schema_version":true}',
                    b'{"schema_version":2}', b'[]', b'not-json', b'\xff'):
            with self.subTest(raw=raw):
                self.write(self.config, raw)
                with self.assertRaises(InstallationError):
                    installation.validate_installation()

    def test_config_and_key_protection_and_missing_files_refused(self):
        for path in (self.config, self.key, self.credential):
            original, mode = path.read_bytes(), path.stat().st_mode & 0o777
            with self.subTest(path=path.name):
                path.chmod(0o644)
                with self.assertRaises(InstallationError):
                    installation.validate_installation()
                path.unlink()
                with self.assertRaises(InstallationError):
                    installation.validate_installation()
                self.write(path, original, mode)

    def test_key_length_control_bytes_and_copy_mismatch_refused(self):
        for raw in (b'x' * 31, b'x' * 257, b'x' * 32 + b' ', b'x' * 32 + b'\n\n',
                    b'x' * 32 + b'\r', b'x' * 32 + b'\x7f', b'x' * 32 + b'\xff'):
            with self.subTest(length=len(raw), last=raw[-1:]):
                self.write(self.key, raw)
                self.write(self.credential, raw, mode=0o400)
                with self.assertRaises(InstallationError):
                    installation.validate_installation()
        self.write(self.key, self.value)
        self.write(self.credential, b'a-different-inert-control-fixture-key', mode=0o400)
        with self.assertRaises(InstallationError):
            installation.validate_installation()

    def test_optional_final_newline_and_both_credential_modes_validate(self):
        self.write(self.key, self.value + b'\n')
        for mode in (0o400, 0o600):
            with self.subTest(mode=mode):
                self.write(self.credential, self.value, mode=mode)
                self.assertEqual(installation.validate_installation(), self.value)


class EntrypointAndClosureTests(unittest.TestCase):
    def test_fresh_process_imports_only_manifest_recovery_closure_from_root_cwd(self):
        manifest = json.loads((ROOT / 'scripts/control/source-closure.json').read_text())
        self.assertEqual(tuple(manifest['recovery_files']), installation.RECOVERY_FILES)
        self.assertEqual(len(set(manifest['recovery_files'])), len(manifest['recovery_files']))
        with tempfile.TemporaryDirectory(prefix='u1b-import-closure-') as temporary:
            source = Path(temporary).resolve()
            for relative in manifest['recovery_files']:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            script = """
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path.cwd() == pathlib.Path('/')
assert not (root / 'configs').exists() and not (root / 'data').exists()
sys.path.insert(0, str(root / 'scripts'))
import control.adapter, control.installation, control.serve, control.http
import lifecycle.manager, common.lifecycle_lease, install.storage
modules = [control.adapter, control.installation, control.serve, control.http,
           lifecycle.manager, common.lifecycle_lease, install.storage]
assert all(pathlib.Path(module.__file__).is_relative_to(root) for module in modules)
assert callable(lifecycle.manager.recovery_manager)
assert callable(lifecycle.manager.Manager.read_state)
print(json.dumps({'imported_from_recovery_copy': True, 'configs_present': False,
                  'data_present': False, 'modules_checked': len(modules)}))
"""
            result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(source)],
                                    cwd='/', capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'imported_from_recovery_copy': True,
                             'configs_present': False, 'data_present': False, 'modules_checked': 7})
            self.assertEqual({str(path.relative_to(source)) for path in source.rglob('*') if path.is_file()},
                             set(manifest['recovery_files']))

    def test_worker_cli_help_refusal_and_no_configuration_override(self):
        command = [sys.executable, '-I', '-B', str(ROOT / 'scripts/control/serve.py')]
        environment = dict(os.environ, CONTROL_BACKEND='fixture', LLMCTL_TEST_ROOT='/ignored-worker-override')
        help_result = subprocess.run(command + ['--help'], cwd='/', env=environment,
                                     capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--check-binding', help_result.stdout)
        for arguments in ([], ['--check-binding']):
            with self.subTest(arguments=arguments):
                result = subprocess.run(command + arguments, cwd='/', env=environment,
                                        capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(json.loads(result.stdout), {'status': 'unavailable',
                                 'code': 'unsafe_or_missing_control_installation', 'listener_started': False})
                self.assertEqual(result.stderr, '')
        for arguments in (['--config', '/ignored'], ['--host', '0.0.0.0'], ['--port', '30001'],
                          ['--fixture'], ['--key-file', '/ignored']):
            with self.subTest(arguments=arguments):
                result = subprocess.run(command + arguments, cwd='/', env=environment,
                                        capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(result.returncode, 2)

    def test_validated_check_does_not_construct_application_or_listener(self):
        from control import adapter, http, serve
        output = io.StringIO()
        with patch.object(serve, '_trusted_bootstrap'), \
                patch.object(installation, 'validate_installation', return_value=b'x' * 40), \
                patch.object(adapter, 'production_application', side_effect=AssertionError('unexpected application')), \
                patch.object(http, 'make_server', side_effect=AssertionError('unexpected listener')), \
                patch('sys.stdout', output):
            self.assertEqual(serve.main(['--check-binding']), 0)
        self.assertEqual(json.loads(output.getvalue()), {'status': 'binding_validated',
                         'listener_started': False, 'normal_lifecycle_acceptance': 'not_performed'})


if __name__ == '__main__':
    unittest.main()
