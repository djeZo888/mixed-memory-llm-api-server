"""Small filesystem tests; no VM, root, downloads, runtime or installer required."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('q38a_seal', Path(__file__).with_name('seal.py'))
seal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seal)


class SealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.dest = self.root / 'model'
        self.dest.mkdir()
        self.payloads = {'.gitattributes': b'attribute\n', 'weight.safetensors': b'weight',
                         'safetensors-md5sum.txt': b''}
        self.rows = []
        for name, content in self.payloads.items():
            (self.dest / name).write_bytes(content)
            row = dict(path=name, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
            if name == 'weight.safetensors':
                row.update(lfs_sha256=row['sha256'], lfs_pointer_git_blob_sha1='a' * 40)
            else:
                row['git_blob_sha1'] = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
            self.rows.append(row)
        self.complete_rows = {row['path']: dict(path=row['path'], size_bytes=row['size_bytes'],
            computed_sha256=row['sha256'], file_stat=seal.acquisition_metadata((self.dest / row['path']).stat()))
            for row in self.rows}

    def tearDown(self):
        for path in self.root.rglob('*'):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o700)
            elif path.is_file() and not path.is_symlink():
                path.chmod(0o600)
        self.temp.cleanup()

    def opened_tree(self, parent, rehash=True):
        opened, proofs = seal.verify_tree(parent, self.rows, self.complete_rows,
                                         rehash=rehash, check_lock=lambda: None)
        self.addCleanup(lambda: [os.close(fd) for fd in opened.values()])
        return opened, proofs

    def test_real_immutable_manifest_preserves_81_dot_and_empty_rows(self):
        path = Path(__file__).resolve().parents[2] / 'reports/q38s-acquisition-manifest.json'
        raw = path.read_bytes()
        rows = seal.validate_manifest(json.loads(raw), raw)
        self.assertEqual(len(rows), 81)
        self.assertEqual(sum(row['size_bytes'] for row in rows), 30890049597)
        self.assertIn('.gitattributes', {row['path'] for row in rows})
        self.assertEqual(next(row for row in rows if row['path'] == 'safetensors-md5sum.txt')['size_bytes'], 0)

    def test_changed_manifest_bytes_refused(self):
        with self.assertRaisesRegex(seal.SealError, 'manifest_sha256_mismatch'):
            seal.validate_manifest({}, b'{}')

    def test_root_rehash_includes_empty_and_git_payload_domains(self):
        with seal.Directory(self.dest) as parent:
            _opened, proofs = self.opened_tree(parent)
            for proof in proofs:
                self.assertEqual(proof['computed_sha256'], self.complete_rows[proof['path']]['computed_sha256'])
            weight = next(row for row in proofs if row['path'] == 'weight.safetensors')
            self.assertEqual(weight['lfs_pointer_git_blob_sha1'], 'a' * 40)
            self.assertNotIn('computed_git_blob_sha1', weight)

    def test_wrong_computed_payload_rejected_even_with_matching_status_stat(self):
        (self.dest / 'weight.safetensors').write_bytes(b'broken')
        self.complete_rows['weight.safetensors']['file_stat'] = seal.acquisition_metadata(
            (self.dest / 'weight.safetensors').stat())
        with seal.Directory(self.dest) as parent, self.assertRaisesRegex(seal.SealError, 'root_payload_sha256_mismatch'):
            seal.verify_tree(parent, self.rows, self.complete_rows, rehash=True, check_lock=lambda: None)

    def test_acquisition_stat_change_refused(self):
        os.utime(self.dest / '.gitattributes', ns=(1, 2))
        with seal.Directory(self.dest) as parent, self.assertRaisesRegex(seal.SealError, 'metadata_changed_since_acquisition'):
            seal.verify_tree(parent, self.rows, self.complete_rows, rehash=False, check_lock=lambda: None)

    def test_unknown_and_partial_entry_refused(self):
        (self.dest / 'weight.safetensors.partial').write_bytes(b'preserve')
        with seal.Directory(self.dest) as parent, self.assertRaisesRegex(seal.SealError, 'unexpected_missing_or_partial'):
            seal.verify_tree(parent, self.rows, self.complete_rows, rehash=False, check_lock=lambda: None)
        self.assertEqual((self.dest / 'weight.safetensors.partial').read_bytes(), b'preserve')

    def test_symlink_payload_refused(self):
        (self.dest / 'weight.safetensors').unlink()
        (self.dest / 'weight.safetensors').symlink_to('/etc/hosts')
        with seal.Directory(self.dest) as parent, self.assertRaises(OSError):
            seal.verify_tree(parent, self.rows, self.complete_rows, rehash=True, check_lock=lambda: None)

    def test_hardlink_payload_refused(self):
        os.link(self.dest / 'weight.safetensors', self.root / 'alias')
        with seal.Directory(self.dest) as parent, self.assertRaisesRegex(seal.SealError, 'hardlinked'):
            seal.verify_tree(parent, self.rows, self.complete_rows, rehash=True, check_lock=lambda: None)

    def test_directory_replacement_refused(self):
        with seal.Directory(self.dest) as parent:
            self.dest.rename(self.root / 'old')
            self.dest.mkdir()
            with self.assertRaisesRegex(seal.SealError, 'directory_path_changed'):
                parent.check()

    def test_guard_failure_refuses_file_open(self):
        armed = False
        def guard():
            if armed:
                raise seal.SealError('mount_identity_changed')
        with seal.Directory(self.dest, guard) as parent:
            armed = True
            with self.assertRaisesRegex(seal.SealError, 'mount_identity_changed'):
                parent.open('.gitattributes')

    def test_dry_run_tree_verification_changes_no_metadata_or_modes(self):
        before = {path.name: seal.metadata(path.stat()) for path in self.dest.iterdir()}
        with seal.Directory(self.dest) as parent:
            _opened, proofs = self.opened_tree(parent, rehash=False)
        self.assertTrue(all('computed_sha256' not in row for row in proofs))
        self.assertEqual(before, {path.name: seal.metadata(path.stat()) for path in self.dest.iterdir()})

    def test_seal_preserves_bytes_inode_mtime_and_sets_nonwritable_modes(self):
        with seal.Directory(self.dest) as parent:
            opened, proofs = self.opened_tree(parent)
            proof = seal.seal_tree(parent, opened, proofs, check_lock=lambda: None, trusted_uid=os.getuid())
            self.assertEqual(stat.S_IMODE(proof['after']['mode']), 0o555)
            for row in proofs:
                self.assertEqual(stat.S_IMODE(row['sealed_stat']['mode']), 0o444)
                self.assertEqual(row['pre_seal']['ino'], row['sealed_stat']['ino'])
                self.assertEqual(row['pre_seal']['mtime_ns'], row['sealed_stat']['mtime_ns'])
                self.assertEqual((self.dest / row['path']).read_bytes(), self.payloads[row['path']])

    def test_payload_change_between_root_hash_and_seal_refused(self):
        with seal.Directory(self.dest) as parent:
            opened, proofs = self.opened_tree(parent)
            # Linux timestamps can share one clock tick; use an observable size change.
            (self.dest / '.gitattributes').write_bytes(b'corruption with a different length')
            with self.assertRaisesRegex(seal.SealError, 'payload_changed_before_seal'):
                seal.seal_tree(parent, opened, proofs, check_lock=lambda: None, trusted_uid=os.getuid())

    def test_completion_requires_all_computed_hashes_and_exact_totals(self):
        complete = dict(schema_version=1, status='COMPLETE_COMPUTED_SHA256', selection='qwen38-27b-fp8',
            repo_id=seal.REPO_ID, revision=seal.REVISION, destination=str(seal.DEST),
            manifest_sha256=seal.MANIFEST_SHA256, artifact_count=3,
            total_bytes=16, verified_bytes=16, artifacts=list(self.complete_rows.values()))
        with mock.patch.object(seal, 'COUNT', 3), mock.patch.object(seal, 'TOTAL', 16):
            self.assertEqual(set(seal.validate_completion(complete, self.rows)), set(self.payloads))
            complete['artifacts'][0]['computed_sha256'] = '0' * 64
            with self.assertRaisesRegex(seal.SealError, 'completion_hash_mismatch'):
                seal.validate_completion(complete, self.rows)

    def test_protected_evidence_written_atomically_and_never_overwrites(self):
        evidence = self.root / 'evidence'
        evidence.mkdir(mode=0o700)
        evidence.chmod(0o700)
        with seal.Directory(evidence) as parent:
            result = seal.atomic_evidence(parent, {'verified': True}, trusted_uid=os.getuid())
            raw = (evidence / 'sealed-evidence.json').read_bytes()
            self.assertEqual(result, hashlib.sha256(raw).hexdigest())
            self.assertEqual(stat.S_IMODE((evidence / 'sealed-evidence.json').stat().st_mode), 0o600)
            self.assertEqual(set(os.listdir(evidence)), {'sealed-evidence.json'})
            with self.assertRaisesRegex(seal.SealError, 'already_exists'):
                seal.atomic_evidence(parent, {'verified': False}, trusted_uid=os.getuid())
            self.assertEqual((evidence / 'sealed-evidence.json').read_bytes(), raw)

    def test_unprotected_evidence_directory_refused(self):
        evidence = self.root / 'evidence'
        evidence.mkdir(mode=0o755)
        evidence.chmod(0o755)
        with seal.Directory(evidence) as parent, self.assertRaisesRegex(seal.SealError, 'unprotected_evidence_directory'):
            seal.atomic_evidence(parent, {}, trusted_uid=os.getuid())

    def test_root_cli_refuses_unprivileged_execution(self):
        with mock.patch.object(seal.os, 'geteuid', return_value=501), self.assertRaisesRegex(seal.SealError, 'root_required'):
            seal.main(['--dry-run'])

    def test_active_acquisition_unit_refused(self):
        result = mock.Mock(stdout='MainPID=123\nActiveState=active\nSubState=running\n')
        with mock.patch.object(seal.subprocess, 'run', return_value=result), self.assertRaisesRegex(
                seal.SealError, 'acquisition_unit_must_be_inactive'):
            seal.require_inactive_unit()

    def test_inactive_acquisition_unit_accepted(self):
        result = mock.Mock(stdout='MainPID=0\nActiveState=inactive\nSubState=dead\n')
        with mock.patch.object(seal.subprocess, 'run', return_value=result):
            seal.require_inactive_unit()

    def test_same_acquisition_lock_refuses_a_second_owner(self):
        (self.root / 'acquisition.lock').write_bytes(b'')
        with seal.acquisition_lock(self.root, lambda: None):
            with self.assertRaisesRegex(seal.SealError, 'acquisition_lock_busy'):
                with seal.acquisition_lock(self.root, lambda: None):
                    self.fail('second owner acquired lock')

    def test_evidence_directory_replacement_never_writes_to_new_fallback(self):
        evidence = self.root / 'evidence'
        evidence.mkdir(mode=0o700)
        evidence.chmod(0o700)
        real_rename = os.rename
        def replace_directory_then_rename(*args, **kwargs):
            real_rename(evidence, self.root / 'detached')
            evidence.mkdir(mode=0o700)
            evidence.chmod(0o700)
            return real_rename(*args, **kwargs)
        with seal.Directory(evidence) as parent, mock.patch.object(seal.os, 'rename', replace_directory_then_rename):
            with self.assertRaisesRegex(seal.SealError, 'directory_path_changed'):
                seal.atomic_evidence(parent, {'verified': True}, trusted_uid=os.getuid())
        self.assertEqual(os.listdir(evidence), [])

    def mount_guard_fixture(self):
        def row(number, path, device):
            return (str(number), '0', device, '/', path, 'rw', '-', 'ext4', '/dev/fixture', 'rw')
        entries = [row(1, '/', '1:1'), row(2, '/data', '2:2'), row(3, '/data/models-large', '3:3')]
        guard = object.__new__(seal.MountGuard)
        guard.expected = {'/data': entries[1], '/data/models-large': entries[2]}
        return guard, entries, row

    def test_guard_exact_root_free_boundary(self):
        guard, entries, _row = self.mount_guard_fixture()
        with mock.patch.object(seal.MountGuard, 'mount_entries', return_value=entries):
            with mock.patch.object(seal.shutil, 'disk_usage', return_value=mock.Mock(free=4 * 1024**3)):
                guard()
            with mock.patch.object(seal.shutil, 'disk_usage', return_value=mock.Mock(free=4 * 1024**3 - 1)):
                with self.assertRaisesRegex(seal.SealError, 'root_free_below_4_gib'):
                    guard()

    def test_guard_changed_mount_id_and_hidden_ancestor_refused(self):
        guard, entries, row = self.mount_guard_fixture()
        with mock.patch.object(seal.shutil, 'disk_usage', return_value=mock.Mock(free=8 * 1024**3)):
            replaced = [*entries[:2], row(99, '/data/models-large', '3:3')]
            with mock.patch.object(seal.MountGuard, 'mount_entries', return_value=replaced):
                with self.assertRaisesRegex(seal.SealError, 'mount_identity_changed'):
                    guard()
            hidden = [*entries, row(100, '/data/build', '2:2')]
            with mock.patch.object(seal.MountGuard, 'mount_entries', return_value=hidden):
                with self.assertRaisesRegex(seal.SealError, 'task_path_crosses_unexpected_mount'):
                    guard()


if __name__ == '__main__':
    unittest.main()
