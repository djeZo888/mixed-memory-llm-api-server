"""Fan-only retry fixtures: actual storage module, real rename, synthetic mounts."""
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'tests/install'))
import test_storage_io_paths as storage_fixture
from install import storage_io as io
from contract import Refusal
from native import read_fan_mirror


class FanSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = storage_fixture.SyntheticMountPathTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture._write('fan-status.json', b'{"sequence":0,"coherent":"old"}')
        self.adapter = types.SimpleNamespace(
            m={'fan_status_path': str(self.path)}, guard=self.fixture.guard,
            root_cls=lambda path, guard: io.AnchoredRoot(path, guard, uid=os.geteuid()))

    def replacement(self, sequence):
        temporary = self.path.with_name('fan-next.json')
        temporary.write_text(json.dumps({'sequence': sequence, 'coherent': 'fresh'}))
        temporary.chmod(0o600)
        os.replace(temporary, self.path)

    def replacing_check(self, *, every=False, mount_after_failure=False):
        original = io.GuardedFile.check
        calls = []
        def check(stream):
            if stream.name == self.path.name and (every or not calls):
                self.replacement(len(calls) + 1)
                calls.append(os.fstat(stream._fd).st_nlink)
                self.assertEqual(calls[-1], 0)
                try:
                    return original(stream)
                except io.StorageIOError:
                    if mount_after_failure:
                        self.fixture._mount(self.path.name)
                    raise
            return original(stream)
        return check, calls

    def test_original_reader_reproduces_exact_error_after_real_replace(self):
        check, calls = self.replacing_check()
        with patch.object(io.GuardedFile, 'check', check):
            with self.assertRaises(io.StorageIOError) as failure:
                self.fixture.root.read_json(self.path.name)
        self.assertIs(type(failure.exception), io.StorageIOError)
        self.assertEqual(failure.exception.code, 'invalid_storage_file_or_hardlink')
        self.assertEqual(calls, [0])

    def test_corrected_reader_reopens_and_returns_coherent_fresh_snapshot(self):
        check, calls = self.replacing_check()
        with patch.object(io.GuardedFile, 'check', check):
            value = read_fan_mirror(self.adapter)
        self.assertEqual(value, {'sequence': 1, 'coherent': 'fresh'})
        self.assertEqual(calls, [0])

    def test_repeated_real_replacement_exhausts_small_retry_budget(self):
        check, calls = self.replacing_check(every=True)
        with patch.object(io.GuardedFile, 'check', check):
            with self.assertRaises(io.StorageIOError):
                read_fan_mirror(self.adapter)
        self.assertEqual(calls, [0, 0, 0])

    def test_known_error_without_identity_replacement_is_not_retried(self):
        calls = []
        original = io.GuardedFile.check
        def failure(stream):
            if stream.name == self.path.name:
                calls.append(True)
                raise io.StorageIOError('invalid_storage_file_or_hardlink')
            return original(stream)
        with patch.object(io.GuardedFile, 'check', failure):
            with self.assertRaises(io.StorageIOError):
                read_fan_mirror(self.adapter)
        self.assertEqual(len(calls), 1)

    def test_persistent_hardlink_is_rejected(self):
        os.link(self.path, self.path.with_name('fan-link.json'))
        with self.assertRaises(io.StorageIOError) as failure:
            read_fan_mirror(self.adapter)
        self.assertEqual(failure.exception.code, 'invalid_storage_file_or_hardlink')

    def test_nonprivate_mode_is_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises((io.StorageIOError, Refusal)):
            read_fan_mirror(self.adapter)

    def test_symlink_is_rejected(self):
        target = self.path.with_name('target.json')
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaises(io.StorageIOError) as failure:
            read_fan_mirror(self.adapter)
        self.assertEqual(failure.exception.code, 'invalid_storage_file_or_hardlink')

    def test_malformed_json_is_not_retried(self):
        self.path.write_bytes(b'{bad-json')
        original = io.AnchoredRoot.read_json
        calls = []
        def read(root, *args, **kwargs):
            calls.append(True)
            return original(root, *args, **kwargs)
        with patch.object(io.AnchoredRoot, 'read_json', read):
            with self.assertRaises(io.StorageIOError) as failure:
                read_fan_mirror(self.adapter)
        self.assertEqual(failure.exception.code, 'invalid_storage_json')
        self.assertEqual(len(calls), 1)

    def test_invalid_current_replacement_is_not_retried(self):
        original_replace = self.replacement
        for invalid in ('hardlink', 'mode'):
            with self.subTest(invalid=invalid):
                self.path.unlink()
                self.fixture._write(self.path.name, b'{"sequence":0}')
                link = self.path.with_name('invalid-link.json')
                def replace(sequence):
                    original_replace(sequence)
                    if invalid == 'hardlink':
                        os.link(self.path, link)
                    else:
                        self.path.chmod(0o644)
                check, calls = self.replacing_check()
                try:
                    with patch.object(self, 'replacement', replace), patch.object(io.GuardedFile, 'check', check):
                        with self.assertRaises(io.StorageIOError) as failure:
                            read_fan_mirror(self.adapter)
                    self.assertEqual(failure.exception.code, 'invalid_storage_file_or_hardlink'
                                     if invalid == 'hardlink' else 'unprotected_storage_owner_or_mode')
                    self.assertEqual(calls, [0])
                finally:
                    if link.exists():
                        link.unlink()

    def test_missing_name_after_replacement_fails_without_retry(self):
        original_replace = self.replacement
        def replace(sequence):
            original_replace(sequence)
            self.path.unlink()
        check, calls = self.replacing_check()
        with patch.object(self, 'replacement', replace), patch.object(io.GuardedFile, 'check', check):
            with self.assertRaises(FileNotFoundError):
                read_fan_mirror(self.adapter)
        self.assertEqual(calls, [0])

    def test_invalid_owner_uses_actual_guarded_stat_protection(self):
        original_stat = os.stat
        def wrong_owner(path, *args, **kwargs):
            info = original_stat(path, *args, **kwargs)
            if path == self.path.name and kwargs.get('dir_fd') is not None:
                fields = list(info)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return info
        with patch.object(io.os, 'stat', wrong_owner):
            with self.assertRaises(io.StorageIOError) as failure:
                read_fan_mirror(self.adapter)
        self.assertEqual(failure.exception.code, 'unprotected_storage_owner_or_mode')

    def test_mount_fault_during_replacement_recheck_fails_closed(self):
        check, calls = self.replacing_check(mount_after_failure=True)
        with patch.object(io.GuardedFile, 'check', check):
            with self.assertRaises(io.StorageIOError) as failure:
                read_fan_mirror(self.adapter)
        self.assertIn('mount', failure.exception.code)
        self.assertEqual(calls, [0])


if __name__ == '__main__':
    unittest.main()
