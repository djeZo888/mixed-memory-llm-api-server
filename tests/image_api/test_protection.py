"""Protected credential/source metadata and fixed privilege wiring; Linux NOT_TESTED."""
import asyncio
import copy
import configparser
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from image_api import backend, protection, protocol


class ProtectedFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve() / 'protected'
        self.directory.mkdir(mode=0o700)
        self.path = self.directory / 'credential'
        self.path.write_bytes(b'fixture-credential-is-not-a-secret-1234\n')
        self.path.chmod(0o400)
        self.original_fstat, self.original_stat = os.fstat, os.stat
        self.bad_owner = self.bad_parent = None
        self.bad_mode = None
        def metadata(s):
            fields = {key: getattr(s, key) for key in dir(s) if key.startswith('st_')}
            # Fixture root ownership map permits macOS temp ancestry. Actual mode
            # violations below are injected at exact tested file/directory inodes.
            fields['st_uid'] = 0
            if stat.S_ISDIR(s.st_mode):
                fields['st_mode'] &= ~0o022
            if s.st_ino == self.bad_owner:
                fields['st_uid'] = 123456
            if s.st_ino == self.bad_parent:
                fields['st_mode'] |= 0o022
            return SimpleNamespace(**fields)
        for target, callback in [('fstat', lambda *a, **kw: metadata(self.original_fstat(*a, **kw))),
                                 ('stat', lambda *a, **kw: metadata(self.original_stat(*a, **kw)))]:
            mocked = patch.object(protection.os, target, callback)
            mocked.start()
            self.addCleanup(mocked.stop)

    def read(self):
        return protection.protected(self.path, modes={0o400}, maximum=257, credential=True)

    def test_valid_metadata_key_and_newline(self):
        self.assertTrue(self.read().startswith(b'fixture-credential'))
        with patch.object(protection, 'CREDENTIAL', self.path):
            self.assertFalse(protection.key().endswith(b'\n'))

    def test_wrong_owner_parent_file_permissions_oversize_symlink_hardlink_fifo(self):
        self.bad_owner = self.original_stat(self.path).st_ino
        with self.assertRaises(protection.ProtectionError):
            self.read()
        self.bad_owner = None
        self.bad_parent = self.original_stat(self.directory).st_ino
        with self.assertRaises(protection.ProtectionError):
            self.read()
        self.bad_parent = None
        self.path.chmod(0o644)
        with self.assertRaises(protection.ProtectionError):
            self.read()
        self.path.chmod(0o400)
        os.link(self.path, self.directory / 'alias')
        with self.assertRaises(protection.ProtectionError):
            self.read()
        (self.directory / 'alias').unlink()
        self.path.unlink()
        self.path.symlink_to('/dev/null')
        with self.assertRaises(protection.ProtectionError):
            self.read()
        self.path.unlink()
        os.mkfifo(self.path, 0o400)
        with self.assertRaises(protection.ProtectionError):
            self.read()
        self.path.unlink()
        self.path.write_bytes(b'x' * 258)
        self.path.chmod(0o400)
        with self.assertRaises(protection.ProtectionError):
            self.read()

    def test_replaced_file_during_read_and_symlink_ancestor(self):
        real_read = os.read
        def replace(fd, size):
            result = real_read(fd, size)
            fresh = self.directory / 'fresh'
            fresh.write_bytes(result)
            fresh.chmod(0o400)
            fresh.replace(self.path)
            return result
        with patch.object(protection.os, 'read', replace), self.assertRaises(protection.ProtectionError):
            self.read()
        target = self.directory.with_name('moved')
        self.directory.rename(target)
        self.directory.symlink_to(target)
        with self.assertRaises(protection.ProtectionError):
            self.read()

    def test_key_syntax_refuses_malformed_secret_without_echo(self):
        for raw in (b'x', b'x' * 32 + b'\n\n', b'x' * 32 + b' ', b'\xff' * 32):
            with patch.object(protection, 'protected', return_value=raw), self.assertRaises(protection.ProtectionError) as caught:
                protection.key()
            self.assertNotIn(repr(raw), str(caught.exception))


class Configuration(unittest.TestCase):
    def empty(self):
        return json.loads((ROOT / 'scripts/image_api/qualification.empty.json').read_text())

    def test_empty_manifest_claims_no_measured_profiles_and_no_digest(self):
        value = protocol.qualification(self.empty())
        self.assertEqual(value['profiles'], [])
        self.assertIsNone(value['runtime_image_digest'])

    def test_pins_schema_and_conditioned_profile_fail_closed(self):
        for key, value in [('runtime_revision', 'main'), ('model_id', 'other'), ('model_revision', 'main'),
                           ('schema_version', True), ('runtime_image_digest', 'unreviewed'), ('backend_url', 'http://x')]:
            manifest = self.empty()
            manifest[key] = value
            with self.assertRaises(protocol.Refusal):
                protocol.qualification(manifest)
        from test_handlers import profile
        manifest = self.empty()
        manifest['profiles'] = [profile('edit', 1)]
        with self.assertRaises(protocol.Refusal):
            protocol.qualification(manifest)
        manifest['runtime_image_digest'] = 'sha256:' + 'a' * 64
        for key, value in [('size', '4096x4096'), ('references', True), ('operation', 'unknown'),
                           ('transparent', True), ('conditioning', 'unmeasured'), ('evidence_sha256', '')]:
            bad = copy.deepcopy(manifest)
            bad['profiles'][0][key] = value
            with self.assertRaises(protocol.Refusal):
                protocol.qualification(bad)
        manifest['profiles'] *= 2
        with self.assertRaises(protocol.Refusal):
            protocol.qualification(manifest)

    def test_unit_sudo_wiring_and_single_worker_fixed_invocation(self):
        unit = (ROOT / 'scripts/image_api/llm-image-api.service.in').read_text()
        self.assertIn('NoNewPrivileges=no', unit)
        self.assertNotIn('NoNewPrivileges=yes', unit)
        self.assertIn('LoadCredential=inference-key:', unit)
        self.assertIn('IPAddressAllow=127.0.0.1/32', unit)
        self.assertIn('KillMode=control-group', unit)
        self.assertIn('StandardError=null', unit)
        sudo = (ROOT / 'scripts/image_api/sudoers.in').read_text()
        self.assertIn('/usr/local/libexec/llm-image-backend-recover ""', sudo)
        self.assertNotIn('systemctl', sudo)
        serve = (ROOT / 'scripts/image_api/serve.py').read_text()
        self.assertIn("host='127.0.0.1', port=30006, workers=1", serve)
        self.assertIn('singleton()', serve)
        self.assertIn('proxy_headers=False', serve)

    def test_api_is_the_only_image_boot_owner_ordered_after_text_boot(self):
        unit = configparser.ConfigParser(interpolation=None)
        unit.read(ROOT / 'scripts/image_api/llm-image-api.service.in')
        self.assertEqual(unit['Unit']['After'].split(), ['network.target', 'llmctl-boot.service'])
        self.assertNotIn('llmctl-boot.service', unit['Unit'].get('Requires', '').split())
        for dependency in ('Requires', 'Wants'):
            self.assertNotIn('llm-image-backend.service', unit['Unit'].get(dependency, '').split())
        self.assertEqual(unit['Install']['WantedBy'], 'multi-user.target')
        self.assertNotIn('Also', unit['Install'])  # Enabling API cannot enable backend.
        self.assertIn('/scripts/image_api/serve.py', unit['Service']['ExecStart'])
        self.assertEqual(backend.RECOVERY_COMMAND,
                         ('/usr/bin/sudo', '-n', '--', '/usr/local/libexec/llm-image-backend-recover'))

    def test_process_lock_rejects_second_owner_and_unsafe_file(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            parent.chmod(0o700)
            with patch.object(protection, 'LOCK', parent / 'owner.lock'):
                fd = protection.singleton()
                try:
                    with self.assertRaises(BlockingIOError):
                        protection.singleton()
                finally:
                    os.close(fd)
                (parent / 'owner.lock').chmod(0o666)
                with self.assertRaises(protection.ProtectionError):
                    protection.singleton()


class Recovery(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_no_argument_recovery_suppresses_output_environment(self):
        process = SimpleNamespace(wait=AsyncMock(return_value=0), returncode=0)
        with patch.object(backend.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process)) as run:
            self.assertTrue(await backend.recover())
        self.assertEqual(run.call_args.args, ('/usr/bin/sudo', '-n', '--', '/usr/local/libexec/llm-image-backend-recover'))
        self.assertEqual(run.call_args.kwargs['stdout'], asyncio.subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs['stderr'], asyncio.subprocess.DEVNULL)
        self.assertEqual(set(run.call_args.kwargs['env']), {'PATH', 'LANG'})

    async def test_recovery_nonzero_unavailable_and_timeout_fail_closed(self):
        for process in [SimpleNamespace(wait=AsyncMock(return_value=1), returncode=1),
                        SimpleNamespace(wait=AsyncMock(side_effect=TimeoutError), returncode=1)]:
            with patch.object(backend.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process)):
                self.assertFalse(await backend.recover())
        with patch.object(backend.asyncio, 'create_subprocess_exec', AsyncMock(side_effect=OSError('/secret/path'))):
            self.assertFalse(await backend.recover())
