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

    def test_present_q38_normal_dependencies_require_protected_files(self):
        q38_files = [relative for relative in installation.NORMAL_FILES
                     if any(name in relative for name in ('q38', 'qwen38', 'sglang38'))]
        self.assertEqual(len(q38_files), 11)
        for relative in q38_files:
            self.write(self.source / relative, b'# inert source closure fixture\n', mode=0o644)
        self.reader.reset_mock()
        self.assertEqual(installation.validate_installation(), self.value)
        checked = [call.args[0] for call in self.reader.call_args_list]
        self.assertEqual(checked, [self.source / relative for relative in installation.RECOVERY_FILES]
                         + [self.source / relative for relative in q38_files]
                         + [self.config, self.key, self.credential])
        for relative in q38_files:
            source = self.source / relative
            for kind in ('writable', 'symlink', 'hardlink'):
                with self.subTest(relative=relative, kind=kind):
                    source.unlink()
                    if kind == 'writable':
                        self.write(source, b'# inert fixture', mode=0o666)
                    elif kind == 'symlink':
                        source.symlink_to(self.config)
                    else:
                        os.link(self.config, source)
                    self.reader.reset_mock()
                    with self.assertRaises(InstallationError):
                        installation.validate_installation()
                    self.assertNotIn(self.key, [call.args[0] for call in self.reader.call_args_list])
                    source.unlink()
                    self.write(source, b'# inert source closure fixture\n', mode=0o644)

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
    def test_fresh_normal_closure_q38_source_proof_and_drift_checks(self):
        """Only copied manifest files and four Q38 profile declarations exist.

        This checks the installed layout's import/source closure. It does not
        call validate_installation, establish file protection, read a key, or
        execute any native/image fixture. Synthetic proof stays in memory.
        """
        manifest = json.loads((ROOT / 'scripts/control/source-closure.json').read_text())
        files = manifest['recovery_files'] + manifest['normal_files']
        profiles = {
            'configs/deployments/qwen38-27b-128k.json',
            'configs/deployments/qwen38-27b-256k.json',
            'configs/models/qwen38-27b-fp8.json',
            'configs/runtimes/sglang-qwen38-0.5.19.json',
        }
        self.assertEqual(len(files), len(set(files)))
        self.assertEqual(tuple(manifest['recovery_files']), installation.RECOVERY_FILES)
        self.assertEqual(tuple(manifest['normal_files']), installation.NORMAL_FILES)
        self.assertTrue(all(str(Path(relative).parent) in manifest['normal_profile_directories']
                            for relative in profiles))
        with tempfile.TemporaryDirectory(prefix='q38b-normal-closure-') as temporary:
            source = Path(temporary).resolve()
            for relative in set(files) | profiles:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            script = """
import copy, importlib.util, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path.cwd() == pathlib.Path('/') and sys.flags.isolated
assert not (root / 'data').exists()
assert not (root / 'tests/lifecycle/test_qwen38.py').exists()
sys.path.insert(0, str(root / 'scripts'))
import control.adapter, control.installation, lifecycle.manager
assert 'lifecycle.qwen38' not in sys.modules
q = lifecycle.manager.Manager.sglang_adapter({'_runtime': {'backend': 'sglang_qwen38'}})
from runtime import qwen38_oci, sglang38_file_auth
assert q.ROOT == root
assert {p.name for p in (root / 'configs/models').glob('*.json')} == {'qwen38-27b-fp8.json'}
assert {p.name for p in (root / 'configs/runtimes').glob('*.json')} == {'sglang-qwen38-0.5.19.json'}
assert {p.name for p in (root / 'configs/deployments').glob('*.json')} == {
    'qwen38-27b-128k.json', 'qwen38-27b-256k.json'}
for identifier, context in q.VARIANTS.items():
    declaration = q.declared_profile(identifier)
    assert declaration['launch']['context_size'] == context
    assert declaration['launch']['gpus'] == ['0']
for relative in q.PROFILE_HASHES:
    q._pinned_json(relative)
assert q.expected_manifest()['artifact_count'] == 81
fixture_root = root / 'tests/lifecycle/sglang38_fixture'
spec = importlib.util.spec_from_file_location('q38_closure_host', fixture_root / 'run_fixture.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
native_module = host.source_module('q38_closure_inner', fixture_root / 'run_pinned_image.py')
assert callable(native_module.parse_options)
provenance, cache_environment = host.read_provenance(root)
assert cache_environment == sglang38_file_auth.CACHE_ENVIRONMENT
modules = [control.adapter, control.installation, lifecycle.manager, q,
           qwen38_oci, sglang38_file_auth, host, host.CACHE, native_module]
assert all(pathlib.Path(module.__file__).is_relative_to(root) for module in modules)
assert not any(name == 'sglang' or name.startswith('sglang.') for name in sys.modules)
identity = {'image_id': q.IMAGE_ID, 'image_reference': q.IMAGE_REFERENCE,
            'source_revision': q.SOURCE_REVISION, 'launcher_sha256': q.launcher_hash()}
source_hashes = {name: item['sha256'] for name, item in provenance['sources'].items()}
native_results, lifetimes = [], []
for index, context in enumerate((131072, 262144), 1):
    native = {check: 'PASS' for check in q.AUTH_CHECKS}
    native.update(status='PASS_ACTUAL_INSTALLED_SOURCE_FIXTURE', image_id_pin=q.IMAGE_ID,
        image_reference=q.IMAGE_REFERENCE, source_revision=q.SOURCE_REVISION,
        image_identity_verification='HOST_DOCKER_INSPECT_REQUIRED', configured_context=context,
        launcher_sha256=provenance['launcher_sha256'], fixture_sha256=provenance['fixture_sha256'],
        support_sha256=provenance['support_sha256'], source_hashes=source_hashes,
        cache_probe=host.CACHE.result_record(dict(host.CACHE.EXPECTED_PATHS), []),
        model_loading='STUBBED_NOT_TESTED', gpu_execution='NOT_TESTED',
        native_lifespan_model_serving_initialization='NOT_TESTED',
        live_inference_and_agent_acceptance='NOT_TESTED')
    host.check_native_result(native, provenance, context)
    native_results.append(native)
    token = str(index) * 32
    lifetimes.append({'container_name': 'q38b-fixture-' + token, 'container_id': token * 2,
        'outcome': 'FIXTURE_EXITED', 'cleanup': 'QUIESCENT_REMOVAL_VERIFIED',
        'runtime_inspect': {'runtime': 'nvidia', 'visible_devices': 'none',
            'driver_capabilities': 'compute,utility', 'device_requests': [], 'host_devices': [],
            'network': 'none', 'root_readonly': True, 'model_and_secret_mounts': 'EMPTY_PRIVATE_TMPFS',
            'entrypoint': ['python3'], 'context': context, 'status': 'PASS_HOST_INSPECT'}})
# In-memory synthetic receipt validates the copied source schema only.
proof = dict(identity, schema_version=2, kind='q38b_actual_image_auth', status='PASS',
    fixture_sha256=provenance['fixture_sha256'], support_sha256=provenance['support_sha256'],
    source_hashes=source_hashes, checks={check: 'PASS' for check in q.AUTH_CHECKS},
    contexts=[131072, 262144], image_identity_verification='HOST_DOCKER_INSPECT_AND_PINNED_RUN',
    docker_inspect=qwen38_oci.expected_evidence(qwen38_oci.CONFIG_DIGEST),
    native_results=native_results, container_lifetimes=lifetimes, model_execution='NOT_TESTED',
    native_lifespan='NOT_TESTED', live_inference_and_agent_acceptance='NOT_TESTED')
q._validate_auth_proof(proof, identity)
def refused(call):
    try:
        call()
    except Exception:
        return
    raise AssertionError('drift admitted')
bad = copy.deepcopy(proof)
bad['docker_inspect']['image_id_domain'] = 'oci_platform_manifest'
refused(lambda: q._validate_auth_proof(bad, identity))
bad = copy.deepcopy(proof)
bad['container_lifetimes'][0]['cleanup'] = 'UNVERIFIED'
refused(lambda: q._validate_auth_proof(bad, identity))
drifts = 2
for relative in ('tests/lifecycle/sglang38_fixture/provenance.json',
                 'tests/lifecycle/sglang38_fixture/cache_probe.py',
                 'scripts/runtime/qwen38_oci.py'):
    path = root / relative
    original = path.read_bytes()
    try:
        path.write_bytes(original + b' ')
        refused(lambda: q._validate_auth_proof(proof, identity))
        drifts += 1
    finally:
        path.write_bytes(original)
path = root / 'configs/runtimes/sglang-qwen38-0.5.19.json'
original = path.read_bytes()
try:
    path.write_bytes(original + b' ')
    refused(lambda: q.declared_profile('qwen38-27b-128k'))
    drifts += 1
finally:
    path.write_bytes(original)
q._validate_auth_proof(proof, identity)
host.read_provenance(root)
print(json.dumps({'source_closure': 'PASS', 'synthetic_receipt_schema': 'PASS',
                  'drift_rejections': drifts, 'published_q38_declarations': 2,
                  'actual_image': 'NOT_TESTED', 'key_access': 'NONE'}))
"""
            result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(source)],
                                    cwd='/', capture_output=True, text=True, timeout=20, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'source_closure': 'PASS',
                'synthetic_receipt_schema': 'PASS', 'drift_rejections': 6,
                'published_q38_declarations': 2, 'actual_image': 'NOT_TESTED', 'key_access': 'NONE'})
            self.assertEqual({str(path.relative_to(source)) for path in source.rglob('*') if path.is_file()},
                             set(files) | profiles)

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
                patch.object(installation, 'read_advertised_policy', return_value=None), \
                patch.object(adapter, 'production_application', side_effect=AssertionError('unexpected application')), \
                patch.object(http, 'make_server', side_effect=AssertionError('unexpected listener')), \
                patch('sys.stdout', output):
            self.assertEqual(serve.main(['--check-binding']), 0)
        self.assertEqual(json.loads(output.getvalue()), {'status': 'binding_validated',
                         'listener_started': False, 'normal_lifecycle_acceptance': 'not_performed'})


if __name__ == '__main__':
    unittest.main()
