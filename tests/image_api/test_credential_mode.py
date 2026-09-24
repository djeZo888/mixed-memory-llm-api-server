"""Focused systemd credential metadata regression; no Linux service activation."""
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from image_api import protection


class SystemdCredentialMode(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve() / 'credentials'
        directory.mkdir(mode=0o700)
        self.path = directory / 'inference-key'
        self.value = b'fixture-credential-is-not-a-secret-1234'
        self.path.write_bytes(self.value + b'\n')
        self.path.chmod(0o440)
        directory.chmod(0o550)
        original_fstat, original_stat = os.fstat, os.stat
        file_inode = original_stat(self.path).st_ino
        self.uid = self.gid = 0

        def metadata(result):
            fields = {key: getattr(result, key) for key in dir(result) if key.startswith('st_')}
            # As in test_protection.py, map local temporary ancestry to protected
            # root ownership; preserve actual file mode and inode/race metadata.
            fields['st_uid'] = fields['st_gid'] = 0
            if stat.S_ISDIR(result.st_mode):
                fields['st_mode'] &= ~0o022
            if result.st_ino == file_inode:
                fields['st_uid'], fields['st_gid'] = self.uid, self.gid
            return SimpleNamespace(**fields)

        for target, replacement in [
            ('fstat', lambda *args, **kwargs: metadata(original_fstat(*args, **kwargs))),
            ('stat', lambda *args, **kwargs: metadata(original_stat(*args, **kwargs))),
            ('geteuid', lambda: 123456),
        ]:
            mocked = patch.object(protection.os, target, replacement)
            mocked.start()
            self.addCleanup(mocked.stop)
        credential = patch.object(protection, 'CREDENTIAL', self.path)
        credential.start()
        self.addCleanup(credential.stop)

    def test_root_root_0440_systemd_credential_is_accepted(self):
        self.assertEqual(protection.key(), self.value)

    def test_0440_requires_root_owner_and_root_group(self):
        # The current service UID is otherwise an allowed credential owner;
        # this exercises the added 0440 restriction, not the older owner check.
        for self.uid, self.gid in [(123456, 0), (0, 123456), (123456, 123456)]:
            with self.subTest(uid=self.uid, gid=self.gid):
                with self.assertRaises(protection.ProtectionError):
                    protection.key()

    def test_existing_private_credential_modes_remain_accepted(self):
        for mode in (0o400, 0o600):
            self.path.chmod(mode)
            for self.uid, self.gid in [(0, 0), (123456, 123456)]:
                with self.subTest(mode=oct(mode), uid=self.uid):
                    self.assertEqual(protection.key(), self.value)

    def test_root_root_group_writable_credentials_are_rejected(self):
        for mode in (0o460, 0o660):
            with self.subTest(mode=oct(mode)):
                self.path.chmod(mode)
                with self.assertRaises(protection.ProtectionError):
                    protection.key()


if __name__ == '__main__':
    unittest.main()
