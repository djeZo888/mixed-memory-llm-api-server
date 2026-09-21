"""L2 root source imports and local startup independent of exposure policy.

Only temporary source/config/key fixtures are used. Production startup's root
bootstrap and listener/application construction are explicit in-process seams;
the protected config reader and policy-error selection execute actual code.
No installed service, model/image/runtime, firewall or Linux mount is exercised.
"""
from __future__ import annotations

from contextlib import ExitStack
from functools import partial
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import test_control_installation as fixtures
from control import adapter, http, installation, serve
from control.core import Application
from control.journal import Journal
from control.protocol import Deadline


class ExactSourceImportTests(unittest.TestCase):
    def test_actual_normal_and_recovery_imports_without_policy_data_or_profiles(self):
        manifest = json.loads((ROOT / 'scripts/control/source-closure.json').read_text())
        self.assertEqual(tuple(manifest['recovery_files']), installation.RECOVERY_FILES)
        self.assertEqual(tuple(manifest['normal_files']), installation.NORMAL_FILES)
        self.assertIn('scripts/control/private_network.py', manifest['recovery_files'])
        for normal in (False, True):
            with self.subTest(normal=normal), tempfile.TemporaryDirectory(prefix='l2-source-import-') as temporary:
                source = Path(temporary).resolve()
                files = manifest['recovery_files'] + (manifest['normal_files'] if normal else [])
                for relative in files:
                    target = source / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / relative, target)
                program = r'''
import inspect, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
normal = sys.argv[2] == 'normal'
assert sys.flags.isolated and sys.flags.dont_write_bytecode
assert pathlib.Path.cwd() == pathlib.Path('/')
for name in ('configs', 'data', 'etc', 'run'):
    assert not (root / name).exists()
def prohibit_host_io(event, args):
    if event in {'subprocess.Popen', 'os.system', 'socket.bind', 'socket.connect'}:
        raise AssertionError('import attempted process or network I/O')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = args[0].decode() if isinstance(args[0], bytes) else args[0]
        if (path == '/data' or path.startswith('/data/') or path.startswith('/etc/llm-server/')
                or path.startswith('/etc/local-ai-server/')):
            raise AssertionError('import attempted policy, credential or data read')
sys.addaudithook(prohibit_host_io)
sys.path.insert(0, str(root / 'scripts'))
from control import adapter, installation, private_network, serve, http
from lifecycle import manager
from install import storage
modules = [adapter, installation, private_network, serve, http, manager, storage]
assert 'roles' in inspect.signature(storage.Storage.verify).parameters
assert 'roles' in inspect.signature(storage.Storage.root_payload_guard).parameters
owner = manager.Manager(root / 'absent-config', {'schema_version': 1, 'id': 'l2-recovery'},
                        docker=object(), recovery_only=True)
assert owner.recovery_only and owner.binding is None and owner.state_file is None
assert owner.state == manager.empty_state()
assert 'lifecycle.qwen38' not in sys.modules
if normal:
    from install import storage_io, prerequisites
    q38 = manager.Manager.sglang_adapter({'_runtime': {'backend': 'sglang_qwen38'}})
    from runtime import qwen38_oci, sglang38_file_auth
    modules.extend([storage_io, prerequisites, q38, qwen38_oci, sglang38_file_auth])
    assert q38.ROOT == root
else:
    assert 'install.storage_io' not in sys.modules
    assert 'install.prerequisites' not in sys.modules
assert all(pathlib.Path(module.__file__).is_relative_to(root) for module in modules)
assert not any(name == 'sglang' or name.startswith('sglang.') for name in sys.modules)
print(json.dumps({'mode': 'normal' if normal else 'recovery', 'source_imports': 'PASS',
                  'recovery_constructor': 'PASS', 'policy_data_profile_access': 'NONE',
                  'native_execution': 'NONE'}))
'''
                result = subprocess.run([sys.executable, '-I', '-B', '-c', program, str(source),
                                         'normal' if normal else 'recovery'], cwd='/',
                                        capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {
                    'mode': 'normal' if normal else 'recovery', 'source_imports': 'PASS',
                    'recovery_constructor': 'PASS', 'policy_data_profile_access': 'NONE',
                    'native_execution': 'NONE'})
                self.assertEqual({str(path.relative_to(source)) for path in source.rglob('*') if path.is_file()},
                                 set(files))


class ExposureIndependentStartupTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InstallationValidationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def configured(self):
        self.fixture.write(self.fixture.config,
                           b'{"schema_version":1,"advertised_endpoint_policy":"private_network"}')

    def startup(self, loader):
        from control import private_network
        application = Mock()
        server = Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        output = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.object(serve, '_trusted_bootstrap'))
            stack.enter_context(patch.object(serve.signal, 'signal'))
            stack.enter_context(patch.object(private_network, 'load_policy', loader))
            construct = stack.enter_context(patch.object(adapter, 'production_application', return_value=application))
            listener = stack.enter_context(patch.object(http, 'make_server', return_value=server))
            stack.enter_context(patch('sys.stdout', output))
            result = serve.main([])
        return result, construct, listener, application, server, output.getvalue()

    def assert_local_start(self, result):
        code, construct, listener, application, server, output = result
        self.assertEqual(code, 0, output)
        construct.assert_called_once_with(serve._ROOT / 'configs', self.fixture.value, advertised_policy=None)
        listener.assert_called_once_with(application, self.fixture.value, host='127.0.0.1', port=30000)
        server.serve_forever.assert_called_once_with(poll_interval=0.25)
        server.server_close.assert_called_once_with()
        application.close.assert_called_once_with()

    def test_absent_setting_starts_authenticated_local_control_without_policy_load(self):
        loader = Mock(side_effect=AssertionError('unexpected policy read'))
        self.assert_local_start(self.startup(loader))
        loader.assert_not_called()

    def test_missing_or_invalid_policy_error_preserves_authenticated_local_startup(self):
        from control.private_network import PrivateNetworkError
        self.configured()
        for failure in ('missing', 'invalid'):
            with self.subTest(failure=failure):
                loader = Mock(side_effect=PrivateNetworkError(failure))
                self.assert_local_start(self.startup(loader))
                loader.assert_called_once_with()

    def test_unrelated_policy_implementation_failure_is_not_swallowed_as_tunnel(self):
        from control import private_network
        self.configured()
        failure = RuntimeError('synthetic unrelated integrity failure')
        with patch.object(private_network, 'load_policy', side_effect=failure):
            with self.assertRaises(RuntimeError) as raised:
                installation.read_advertised_policy()
        self.assertIs(raised.exception, failure)
        result, construct, listener, _, _, output = self.startup(Mock(side_effect=failure))
        self.assertEqual(result, 3)
        construct.assert_not_called()
        listener.assert_not_called()
        self.assertEqual(json.loads(output), {'status': 'unavailable',
                         'code': 'unsafe_or_missing_control_installation', 'listener_started': False})

    def test_bad_protected_control_config_still_refuses_startup_before_policy_read(self):
        self.fixture.write(self.fixture.config, b'{"schema_version":1,"host":"10.156.100.60"}')
        loader = Mock(side_effect=AssertionError('unexpected policy read'))
        result, construct, listener, _, _, output = self.startup(loader)
        self.assertEqual(result, 3)
        loader.assert_not_called()
        construct.assert_not_called()
        listener.assert_not_called()
        self.assertEqual(json.loads(output)['listener_started'], False)

    def test_actual_n1s_protected_loader_and_control_fallback_with_descriptor_uid_seams(self):
        """Real N1S no-follow reader; virtual / descriptor and ownership only.

        No helper function is replaced. Its fixed absolute POLICY remains
        unchanged; opening / maps to the temporary fixture root. Real metadata
        is retained except st_uid, projected to root for this ordinary worker.
        Installation's protected config reader keeps its independent real uid.
        """
        from control import private_network
        from test_l2_advertised_endpoints import POLICY

        self.configured()
        policy = self.fixture.root / 'etc/llm-server/network.json'
        self.fixture.write(policy, json.dumps(POLICY).encode())
        opens = []

        def root_open(path, flags, *args, **kwargs):
            opens.append((path, flags, kwargs.get('dir_fd')))
            return os.open(self.fixture.root if path == '/' else path, flags, *args, **kwargs)

        def root_owner(meta):
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns',
                      'st_mode', 'st_uid', 'st_nlink')
            result = {name: getattr(meta, name) for name in fields}
            self.assertEqual(result['st_uid'], self.fixture.uid)
            result['st_uid'] = 0
            return SimpleNamespace(**result)

        descriptor_os = SimpleNamespace(**{**vars(os), 'open': root_open,
            'fstat': lambda fd: root_owner(os.fstat(fd)),
            'stat': lambda *args, **kwargs: root_owner(os.stat(*args, **kwargs))})
        self.assertEqual(private_network.POLICY, Path('/etc/llm-server/network.json'))
        with patch.object(private_network, 'os', descriptor_os), \
                patch.object(private_network, '_run', side_effect=AssertionError('unexpected host command')):
            first = private_network.load_policy()
            self.assertEqual(first, POLICY)
            first['ports']['glm'] = 1
            self.assertEqual(installation.read_advertised_policy(), POLICY)
            self.assertEqual([item[0] for item in opens[:4]], ['/', 'etc', 'llm-server', 'network.json'])
            self.assertTrue(all(flags & os.O_NOFOLLOW for _, flags, _ in opens[1:4]))
            for failure in ('mode', 'invalid-json', 'missing', 'symlink'):
                with self.subTest(failure=failure):
                    if policy.exists() or policy.is_symlink():
                        policy.unlink()
                    self.fixture.write(policy, json.dumps(POLICY).encode())
                    if failure == 'mode':
                        policy.chmod(0o644)
                    elif failure == 'invalid-json':
                        self.fixture.write(policy, b'{"schema_version":1}')
                    elif failure == 'missing':
                        policy.unlink()
                    else:
                        policy.unlink()
                        policy.symlink_to(self.fixture.config)
                    self.assertIsNone(installation.read_advertised_policy())


class ActualManagerAdvertisementTests(unittest.TestCase):
    def test_selected_profile_model_identity_only_changes_public_status_origin(self):
        import test_control_production as production
        from test_l2_advertised_endpoints import POLICY

        fixture = production.ActualManagerFixture()
        self.addCleanup(fixture.close)
        model = fixture.configs / 'models' / (production.MODEL + '.json')
        declaration = json.loads(model.read_text())
        declaration['repo_id'] = 'unsloth/GLM-5.3-GGUF'
        fixture.write_json(model, declaration)
        receipt = json.loads(fixture.completion_path.read_text())
        receipt['repo_id'] = declaration['repo_id']
        fixture.write_json(fixture.completion_path, receipt)
        profile = fixture.configs / 'deployments' / (production.OLD + '.json')
        deployment = json.loads(profile.read_text())
        deployment['endpoint']['port'] = deployment['container_port'] = 30002
        fixture.write_json(profile, deployment)

        with patch.object(production.prerequisites, 'assert_package_admission',
                          side_effect=partial(production.REAL_ADMISSION, policy_path=fixture.policy)):
            owner = fixture.load()
            with fixture.lease() as lease:
                owner.dispatch('select', production.OLD, boot_policy='resume', lease=lease)
                owner.dispatch('start', lease=lease)
            fixture.docker.calls.clear()
            backend = adapter.ProductionBackend(fixture.configs, manager_loader=fixture.load,
                                                recovery_loader=fixture.recovery,
                                                control_key=b'inert-disposable-separate-control-credential')
            raw = backend.open().observe(Deadline.after(2))
            self.assertEqual(raw['model_id'], declaration['repo_id'])
            self.assertEqual(raw['endpoint']['host'], '127.0.0.1')
            self.assertEqual(raw['endpoint']['port'], 30002)
            self.assertEqual(raw['observed'], 'ready')
            application = Application(backend, Journal(adapter.ManagerJournalStore(fixture.load)),
                                      lease_factory=fixture.lease, advertised_policy=POLICY)
            try:
                code, status = application.handle('GET', '/control/v1/status', {}, b'')
                self.assertEqual(code, 200)
                self.assertEqual(status['endpoint'], {
                    'base_url': 'http://10.156.100.60:30002/v1',
                    'served_model': deployment['endpoint']['served_model'],
                    'authentication_required': True, 'address_scope': 'private_network',
                    'server_relative': False, 'ready': True})
                self.assertNotIn('model_id', status)
                self.assertEqual(owner.deployment(production.OLD)['endpoint']['host'], '127.0.0.1')
                self.assertFalse(any(call[0] in {'stop', 'remove', 'create', 'start_enter'}
                                     for call in fixture.docker.calls))
            finally:
                self.assertTrue(application.close())


if __name__ == '__main__':
    unittest.main()
