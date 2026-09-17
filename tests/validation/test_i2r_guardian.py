"""Portable safety tests only; these never bind mounts or invoke packages."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[2] / 'scripts/validation/i2r/guardian.py'
SPEC = importlib.util.spec_from_file_location('i2r_guardian', PATH)
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)


def fixture_module(tool='apt-get'):
    namespace = {'__name__': 'fixture_test_only'}
    exec(compile(G._fake_program('/run/i2r-' + 'a' * 32, tool), 'synthetic-fixture', 'exec'), namespace)
    return namespace


class GuardTests(unittest.TestCase):
    def test_error_exposes_only_sanitized_code(self):
        self.assertEqual(G.GuardianError('guardian_package_database_busy').code, 'guardian_package_database_busy')
        error = G.GuardianError('unexpected sensitive body: omitted')
        self.assertEqual(error.code, 'guardian_failure')
        self.assertEqual(str(error), 'guardian_failure')

    def test_missing_context_refuses_before_creation_or_command(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / 'must-not-exist'
            with patch.object(G, '_command') as command:
                with self.assertRaisesRegex(RuntimeError, 'refuse_context'):
                    with G.fake_packages(path, cleanup=lambda: {'status': 'PASS'}):
                        self.fail('unsafe context admitted')
                command.assert_not_called()
                self.assertFalse(path.exists())

    def test_missing_cleanup_refused_before_guard(self):
        with patch.object(G, '_guard') as guard:
            with self.assertRaisesRegex(G.GuardianError, 'exact_cleanup_required'):
                with G.fake_packages('/irrelevant', cleanup=None):
                    pass
            guard.assert_not_called()

    def test_self_hosted_context_refused(self):
        context = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'self-hosted',
                   'GITHUB_REPOSITORY': 'djeZo888/mixed-memory-llm-api-server'}
        with patch.dict(os.environ, context, clear=True), patch.object(G, 'capability') as capability:
            with self.assertRaisesRegex(RuntimeError, 'RUNNER_ENVIRONMENT'):
                G._guard(Path('/run/i2r-' + 'a' * 32))
            capability.assert_not_called()

    def test_target_paths_are_exact(self):
        self.assertEqual(list(map(str, G.TARGETS)), ['/usr/bin/apt-get', '/usr/bin/dpkg'])

    def test_symlink_target_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_text('unchanged')
            (root / 'link').symlink_to(root / 'real')
            with self.assertRaisesRegex(G.GuardianError, 'unsafe_path'):
                G._private(root / 'link')

    def test_snapshot_records_exact_metadata_and_hash(self):
        value = SimpleNamespace(st_dev=2, st_ino=3, st_mode=stat.S_IFREG | 0o755,
                                st_uid=0, st_gid=0, st_size=3, st_atime_ns=4,
                                st_mtime_ns=5, st_ctime_ns=6)
        with patch.object(G.os, 'fstat', return_value=value), patch.object(G.os, 'pread', return_value=b'abc'):
            snapshot = G._snapshot_fd(999)
        self.assertEqual(snapshot, {'dev': 2, 'ino': 3, 'mode': stat.S_IFREG | 0o755,
                                    'uid': 0, 'gid': 0, 'size': 3, 'atime_ns': 4,
                                    'mtime_ns': 5, 'ctime_ns': 6,
                                    'sha256': 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'})

    def test_snapshot_refuses_change_during_read(self):
        values = [SimpleNamespace(st_dev=2, st_ino=3, st_mode=stat.S_IFREG | 0o755,
                                  st_uid=0, st_gid=0, st_size=3, st_atime_ns=4,
                                  st_mtime_ns=5, st_ctime_ns=ctime) for ctime in (6, 7)]
        with patch.object(G.os, 'fstat', side_effect=values), patch.object(G.os, 'pread', return_value=b'abc'):
            with self.assertRaisesRegex(G.GuardianError, 'file_changed'):
                G._snapshot_fd(999)

    def test_mountinfo_decodes_and_records_mount_identity(self):
        rows = G._mounts('51 20 8:1 /owned\\040source /usr/bin/apt-get ro,relatime - ext4 /dev/root rw\n')
        self.assertEqual(rows[0]['root'], '/owned source')
        self.assertEqual(rows[0]['mount_id'], 51)
        self.assertEqual(rows[0]['options'], ['relatime', 'ro'])

    def test_stacked_target_mounts_refused(self):
        with patch.object(G, '_mounts', return_value=[{'target': '/usr/bin/dpkg'}] * 2):
            with self.assertRaisesRegex(G.GuardianError, 'stacked_mount'):
                G._target_mount(Path('/usr/bin/dpkg'))

    def test_binding_identity_changed_refused(self):
        row = {'target': '/usr/bin/dpkg', 'mount': {'mount_id': 3, 'options': ['ro']},
               'source': {'dev': 1, 'ino': 2}}
        with patch.object(G, '_target_mount', return_value={'mount_id': 4}), \
             patch.object(Path, 'lstat', return_value=SimpleNamespace(st_dev=1, st_ino=2)):
            with self.assertRaisesRegex(G.GuardianError, 'identity_changed'):
                G._assert_binding(row)

    def test_readwrite_binding_refused(self):
        row = {'target': '/usr/bin/dpkg', 'mount': {'mount_id': 3, 'options': ['rw']},
               'source': {'dev': 1, 'ino': 2}}
        with patch.object(G, '_target_mount', return_value=row['mount']), \
             patch.object(Path, 'lstat', return_value=SimpleNamespace(st_dev=1, st_ino=2)):
            with self.assertRaisesRegex(G.GuardianError, 'identity_changed'):
                G._assert_binding(row)


class SyntheticPackageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module()

    def test_all_exact_transaction_pins(self):
        for pin, mode in [('success', 'success'), ('fail', 'fail'),
                          ('descendant', 'descendant'), ('wait', 'sleep')]:
            self.assertEqual(self.fixture['apt_mode'](['--no-download', '--yes',
                '--no-install-recommends', '--no-remove', 'install', 'i2r-' + pin + '=1']), mode)

    def test_real_packages_and_extra_mutations_refused(self):
        for args in (['install', 'curl'], ['install', 'i2r-success=1', 'curl=1'],
                     ['remove', 'i2r-success=1'], ['--allow-unauthenticated', 'install', 'i2r-success=1'],
                     ['update', 'install', 'i2r-success=1'], ['install', 'i2r-success=1', '-o', 'APT::Get::Assume-Yes=true']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.fixture['apt_mode'](args)

    def test_exact_preparation_modes(self):
        for args in (['update'], ['-s', '--no-install-recommends', '--no-remove', 'install', 'i2r-fixture=1.0'],
                     ['--download-only', '--yes', '--no-install-recommends', '--no-remove', 'install', 'i2r-fixture=1.0']):
            self.assertEqual(self.fixture['apt_mode'](['-o', 'APT::Sandbox::User=root', *args]), 'preparation')

    def test_unsupported_option_and_sandbox_values_refused(self):
        for value in ('APT::Sandbox::User=_apt', 'APT::Sandbox::User=root;id',
                      'APT::Get::Download-Only=false', 'DPkg::Pre-Invoke::=anything'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.fixture['apt_mode'](['-o', value, 'update'])

    def test_control_duration_bounded_finite_and_mode_pinned(self):
        for value in ({'mode': 'success', 'duration': 13}, {'mode': 'success', 'duration': -1},
                      {'mode': 'success', 'duration': float('inf')}, {'mode': 'success', 'duration': float('nan')},
                      {'mode': 'success', 'duration': True}, {'mode': 'sleep'},
                      {'mode': 'success', 'command': 'forbidden'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.fixture['control'](value, 'success')
        self.assertEqual(self.fixture['control']({'duration': 12}, 'sleep'), ('sleep', 12))

    def test_dpkg_fixture_contains_no_mutation_route(self):
        namespace = fixture_module('dpkg')
        with patch.object(namespace['os'], 'geteuid', return_value=0), \
             patch.object(namespace['sys'], 'platform', 'linux'), \
             patch.object(namespace['sys'], 'argv', ['dpkg', '--configure', '-a']):
            with self.assertRaisesRegex(ValueError, 'readonly_dpkg_only'):
                namespace['main']()

    def test_generated_scripts_compile(self):
        for tool in ('apt-get', 'dpkg'):
            compile(G._fake_program('/run/i2r-' + 'a' * 32, tool), tool, 'exec')


class CleanupOrderingTests(unittest.TestCase):
    """Simulate mounts entirely in memory; every process command is replaced."""
    def scenario(self, cleanup_result, *, child_error=False, mount_failure=False):
        from contextlib import ExitStack
        order, mounted, snapshots = [], {}, {}
        next_fd = 100000
        original_close = os.close
        original_lstat = Path.lstat
        target_snapshots = {}

        def opened(path, **kwargs):
            nonlocal next_fd
            next_fd += 1
            path = str(path)
            if path in target_snapshots:
                snapshot = target_snapshots[path]
            else:
                snapshot = {'dev': 1, 'ino': next_fd, 'sha256': 'a' * 64}
                if path in map(str, G.TARGETS):
                    target_snapshots[path] = snapshot
            snapshots[next_fd] = snapshot
            return next_fd, snapshot

        def command(argv):
            order.append(tuple(argv))
            target = argv[-1]
            if '--bind' in argv:
                mounted[target] = {'mount_id': len(mounted) + 50, 'options': ['rw'], 'target': target}
                if mount_failure:
                    raise G.GuardianError('guardian_command_failed')
            elif 'remount,bind,ro' in argv:
                mounted[target] = {**mounted[target], 'options': ['ro']}
            elif argv[0] == '/usr/bin/umount':
                del mounted[target]
            return ''

        def lstat(path, *args, **kwargs):
            if str(path) in mounted:
                source = snapshots[max(snapshots)]
                return SimpleNamespace(st_dev=source['dev'], st_ino=source['ino'])
            return original_lstat(path, *args, **kwargs)

        def close(fd):
            if fd >= 100000:
                order.append(('close', fd))
            else:
                original_close(fd)

        def cleanup():
            order.append(('cleanup',))
            return cleanup_result

        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            for name, replacement in [('_guard', lambda _: {'status': 'PASS'}),
                                      ('_open_original', opened), ('_snapshot_fd', lambda fd: snapshots[fd]),
                                      ('_target_mount', lambda target: mounted.get(str(target))),
                                      ('_no_package_activity', lambda _: None), ('_command', command),
                                      ('_assert_binding', lambda *a, **k: None)]:
                stack.enter_context(patch.object(G, name, replacement))
            stack.enter_context(patch.object(G, 'LOCKS', ()))
            stack.enter_context(patch.object(G.os, 'close', close))
            stack.enter_context(patch.object(Path, 'lstat', lstat))
            stack.enter_context(patch.object(G.signal, 'getitimer', return_value=(0.0, 0.0)))
            stack.enter_context(patch.object(G.signal, 'setitimer'))
            stack.enter_context(patch.object(G.signal, 'signal'))
            error = None
            try:
                with G.fake_packages(root, cleanup=cleanup):
                    order.append(('child',))
                    if child_error:
                        raise RuntimeError('deliberate_child_failure')
            except (RuntimeError, G.GuardianError) as exc:
                error = str(exc)
            evidence = __import__('json').loads((root / 'fake-packages/bindings.json').read_text())
            G._PRESERVED.clear()  # Mock descriptor numbers only.
            return order, mounted, evidence, error

    def test_scope_cleanup_precedes_every_unmount(self):
        order, mounted, evidence, error = self.scenario({'status': 'PASS'})
        self.assertIsNone(error)
        cleanup_index = order.index(('cleanup',))
        self.assertTrue(all(index > cleanup_index for index, event in enumerate(order) if event[0] == '/usr/bin/umount'))
        self.assertEqual(mounted, {})
        self.assertEqual(evidence['status'], 'PASS')
        self.assertTrue(evidence['originals_restored'])

    def test_child_exception_still_restores(self):
        order, mounted, evidence, error = self.scenario({'status': 'PASS'}, child_error=True)
        self.assertEqual(error, 'deliberate_child_failure')
        self.assertIn(('cleanup',), order)
        self.assertFalse(mounted)
        self.assertEqual(evidence['state'], 'restored')

    def test_unknown_scope_never_exposes_real_commands(self):
        order, mounted, evidence, error = self.scenario({'status': 'FAIL', 'code': 'identity_unknown'})
        self.assertIn('bindings_preserved', error)
        self.assertEqual(len(mounted), 2)
        self.assertFalse(any(event[0] == '/usr/bin/umount' for event in order))
        self.assertFalse(any(event[0] == 'close' for event in order))
        self.assertEqual(evidence['status'], 'FAIL')

    def test_partial_bind_failure_cleans_exact_attached_mount(self):
        order, mounted, evidence, error = self.scenario({'status': 'PASS'}, mount_failure=True)
        self.assertEqual(error, 'guardian_command_failed')
        self.assertFalse(mounted)
        self.assertNotIn(('child',), order)
        self.assertNotIn(('cleanup',), order)
        self.assertEqual([event[-1] for event in order if event[0] == '/usr/bin/umount'], ['/usr/bin/apt-get'])


if __name__ == '__main__':
    unittest.main()
