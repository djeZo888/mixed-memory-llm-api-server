"""Local synthetic safety cases only; no VM, real model path, or external calls."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('c1_cleanup', HERE / 'c1_scoped_cleanup.py')
c1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c1)


class CleanupSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.c1-synthetic-', dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'obsolete'
        self.root.mkdir()
        (self.root / 'payload').write_bytes(b'synthetic\n')
        self.retained = self.base / 'retained'
        self.retained.mkdir()
        (self.retained / 'sentinel').write_bytes(b'KEEP\n')
        self.mounts = [{'id': '11', 'parent': '1', 'device': '1:2', 'fsroot': '/',
                        'path': str(self.base), 'fstype': 'ext4', 'source': 'synthetic'}]
        for mocked in (patch.object(c1, 'OWNER_UID', os.geteuid()),
                       patch.object(c1, 'ALLOWLIST', {str(self.root): str(self.base)}),
                       patch.object(c1, 'read_mounts', lambda: list(self.mounts))):
            mocked.start()
            self.addCleanup(mocked.stop)

    def snap(self):
        return c1.dry_run(str(self.root))

    def apply(self, before, gate=lambda _: True):
        return c1.apply_reviewed(str(self.root), before, gate)

    def test_dry_run_no_mutation_then_exact_delete_retains_neighbor(self):
        before = self.snap()
        self.assertEqual(before, self.snap())
        self.assertEqual((self.root / 'payload').read_bytes(), b'synthetic\n')
        result = self.apply(before)
        self.assertTrue(result['absence_verified'])
        self.assertFalse(self.root.exists())
        self.assertEqual((self.retained / 'sentinel').read_bytes(), b'KEEP\n')

    def test_parent_and_unknown_roots_refused(self):
        for root in [str(self.base), str(self.retained), str(self.root) + '/',
                     str(self.root) + '/../retained']:
            with self.assertRaises(c1.Refused):
                c1.dry_run(root)

    def test_symlink_target_and_descendant_refused(self):
        (self.root / 'escape').symlink_to(self.retained, target_is_directory=True)
        with self.assertRaises(c1.Refused): self.snap()
        (self.root / 'escape').unlink()
        shutil.rmtree(self.root)
        self.root.symlink_to(self.retained, target_is_directory=True)
        with self.assertRaises(c1.Refused): self.snap()
        self.assertTrue((self.retained / 'sentinel').exists())

    def test_external_hardlink_refused(self):
        os.link(self.root / 'payload', self.retained / 'linked')
        with self.assertRaises(c1.Refused): self.snap()

    def test_special_entry_refused(self):
        os.mkfifo(self.root / 'pipe')
        with self.assertRaises(c1.Refused): self.snap()

    def test_same_device_nested_mount_and_wrong_mount_refused(self):
        self.mounts.append({**self.mounts[0], 'id': '12', 'path': str(self.root / 'bound')})
        with self.assertRaises(c1.Refused): self.snap()
        self.mounts.pop()
        self.mounts[0]['fsroot'] = '/some-bind'
        with self.assertRaises(c1.Refused): self.snap()

    def test_unsafe_parent_refused(self):
        self.base.chmod(0o777)
        try:
            with self.assertRaises(c1.Refused): self.snap()
        finally:
            self.base.chmod(0o700)

    def test_unknown_use_or_missing_gate_refused(self):
        before = self.snap()
        for gate in (None, lambda _: False, lambda _: None):
            with self.assertRaises(c1.Refused): self.apply(before, gate)
        self.assertTrue(self.root.exists())

    def test_root_replacement_during_gate_refused(self):
        before = self.snap()
        def gate(_):
            self.root.rename(self.base / 'previous')
            self.root.mkdir()
            (self.root / 'new').write_bytes(b'KEEP')
            return True
        with self.assertRaises(c1.Refused): self.apply(before, gate)
        self.assertEqual((self.root / 'new').read_bytes(), b'KEEP')
        self.assertTrue((self.base / 'previous' / 'payload').exists())

    def test_content_metadata_drift_during_gate_refused(self):
        before = self.snap()
        def gate(_):
            (self.root / 'payload').write_bytes(b'changed payload')
            return True
        with self.assertRaises(c1.Refused): self.apply(before, gate)
        self.assertTrue(self.root.exists())

    def test_rmtree_failure_remains_partial(self):
        before = self.snap()
        def partial(name, *, dir_fd):
            directory = os.open(name, c1.DIR_FLAGS, dir_fd=dir_fd)
            try: os.unlink('payload', dir_fd=directory)
            finally: os.close(directory)
            raise OSError('synthetic partial failure')
        partial.avoids_symlink_attacks = True
        with patch.object(c1.shutil, 'rmtree', partial):
            with self.assertRaises(OSError): self.apply(before)
        self.assertTrue(self.root.exists())
        self.assertFalse((self.root / 'payload').exists())
        self.assertTrue((self.retained / 'sentinel').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
