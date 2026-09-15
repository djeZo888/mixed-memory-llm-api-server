#!/usr/bin/env python3
"""Offline Q38A tests: python3 -B scripts/q38a/test_acquire.py -v.

Linux fixtures default to /data/build/q38a-20260915/tmp; Q38A_TEST_TMPDIR may
select another already approved data filesystem. No network/model imports.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import acquire

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / 'reports/q38s-acquisition-manifest.json'


class Response(io.BytesIO):
    def __init__(self, body, total, offset=0):
        super().__init__(body)
        self.status = 206 if offset else 200
        self.headers = {'Content-Length': str(total - offset)}
        if offset:
            self.headers['Content-Range'] = f'bytes {offset}-{total-1}/{total}'


def artifact(name, body, lfs=False):
    result = dict(path=name, size_bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    if lfs:
        result.update(lfs_sha256=result['sha256'], lfs_pointer_git_blob_sha1='1' * 40)
    else:
        result['git_blob_sha1'] = hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest()
    return result


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def test_exact_manifest_all_rows_empty_dotted_and_hash_domains(self):
        self.assertEqual(hashlib.sha256(MANIFEST.read_bytes()).hexdigest(), acquire.MANIFEST_SHA256)
        rows = acquire.validate_manifest(self.manifest)
        self.assertEqual(len(rows), 81)
        self.assertEqual(sum(row['size_bytes'] for row in rows), 30890049597)
        self.assertEqual(sum('lfs_sha256' in row for row in rows), 67)
        self.assertIn('.gitattributes', [row['path'] for row in rows])
        empty = next(row for row in rows if row['path'] == 'safetensors-md5sum.txt')
        self.assertEqual((empty['size_bytes'], empty['sha256']), (0, acquire.EMPTY_SHA256))

    def test_manifest_wrong_pin_count_path_domain_zero_and_duplicate_refused(self):
        cases = [lambda m: m.update(revision='0' * 40),
            lambda m: m['artifacts'].pop(),
            lambda m: m['artifacts'][0].update(path='../escape'),
            lambda m: m['artifacts'][0].update(path='a//b'),
            lambda m: m['artifacts'][0].update(path='config.json.partial'),
            lambda m: m['artifacts'][0].update(path=m['artifacts'][1]['path']),
            lambda m: m['artifacts'][0].update(size_bytes=-1),
            lambda m: m['artifacts'][0].update(size_bytes=True),
            lambda m: m['artifacts'][0].update(size_bytes=0),
            lambda m: next(r for r in m['artifacts'] if 'lfs_sha256' in r).update(git_blob_sha1='0' * 40),
            lambda m: next(r for r in m['artifacts'] if 'lfs_sha256' in r).update(lfs_sha256='0' * 64)]
        for change in cases:
            altered = deepcopy(self.manifest)
            change(altered)
            with self.assertRaises(acquire.IntegrityError):
                acquire.validate_manifest(altered)

    def test_remote_metadata_exact_lfs_pointer_and_payload_checks(self):
        rows = self.manifest['artifacts']
        remote = dict(id=acquire.REPO_ID, sha=acquire.REV, siblings=[])
        for row in rows:
            value = dict(rfilename=row['path'], size=row['size_bytes'],
                blobId=row.get('git_blob_sha1', row.get('lfs_pointer_git_blob_sha1')))
            if 'lfs_sha256' in row:
                value['lfs'] = dict(sha256=row['sha256'], size=row['size_bytes'])
            remote['siblings'].append(value)
        acquire.compare_metadata(rows, remote)
        for field in ('blobId', 'sha256'):
            altered = deepcopy(remote)
            row = next(value for value in altered['siblings'] if 'lfs' in value)
            if field == 'blobId':
                row[field] = '0' * 40
            else:
                row['lfs'][field] = '0' * 64
            with self.assertRaises(acquire.IntegrityError):
                acquire.compare_metadata(rows, altered)
        remote['siblings'].append(deepcopy(remote['siblings'][0]))
        with self.assertRaises(acquire.IntegrityError):
            acquire.compare_metadata(rows, remote)

    def test_response_rejects_ignored_ranges_encoding_lengths_and_empty_requests(self):
        acquire.validate_response(Response(b'bcd', 4, 1), 1, 4)
        acquire.validate_response(Response(b'abcd', 4), 0, 4)
        cases = [(1, 4, 'Content-Range', 'bytes 0-3/4'),
                 (1, 4, 'Content-Length', '4'),
                 (0, 4, 'Content-Encoding', 'gzip'),
                 (0, 4, 'Content-Range', 'bytes 0-3/4')]
        for offset, size, name, value in cases:
            response = Response(b'', size, offset)
            response.headers[name] = value
            with self.assertRaises(acquire.IntegrityError):
                acquire.validate_response(response, offset, size)
        for offset, size in ((0, 0), (4, 4), (-1, 4)):
            with self.assertRaises(acquire.IntegrityError):
                acquire.validate_response(Response(b'', size, offset), offset, size)
        response = Response(b'', 4, 1)
        response.status = 200
        with self.assertRaises(acquire.IntegrityError):
            acquire.validate_response(response, 1, 4)


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        default = tempfile.gettempdir() if sys.platform == 'darwin' else str(acquire.RUN / 'tmp')
        temporary = tempfile.TemporaryDirectory(prefix='q38a-fixture-',
            dir=os.environ.get('Q38A_TEST_TMPDIR', default))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / 'data'
        self.models = self.data / 'models-large'
        self.models.mkdir(parents=True)
        self.run = self.data / 'build/q38a-20260915'
        (self.run / 'evidence').mkdir(parents=True)
        (self.run / 'tmp').mkdir()
        self.source = self.data / 'services/q38a-20260915/repo'
        (self.source / 'reports').mkdir(parents=True)
        self.manifest = self.source / 'reports/q38s-acquisition-manifest.json'
        self.manifest.write_bytes(MANIFEST.read_bytes())
        self.dest = self.models / 'qwen38-27b-fp8'
        self.addCleanup(patch.stopall)
        for name, value in [('DATA', self.data), ('MODELS', self.models), ('RUN', self.run),
                            ('DEST', self.dest), ('SOURCE', self.source), ('CHUNK', 8), ('RESERVE', 32)]:
            patch.object(acquire, name, value).start()
        self.storage = patch.object(acquire.storage, 'check', return_value={'fixture': True}).start()
        self.capacity = patch.object(acquire.os, 'fstatvfs',
            return_value=SimpleNamespace(f_bavail=10**12, f_frsize=1)).start()
        self.args = SimpleNamespace(run_dir=self.run, manifest=self.manifest,
            manifest_sha256=acquire.MANIFEST_SHA256, workers=3, dry_run=False)
        self.job = acquire.Acquisition(self.args)
        self.addCleanup(self.job.close)

    def prepare(self, name='config.json', body=b'fixture payload', prefix=None, lfs=False):
        row = artifact(name, body, lfs=lfs)
        self.job.artifacts = [row]
        self.job.prepare_destination()
        if prefix is not None:
            (self.dest / (name + '.partial')).write_bytes(prefix)
        return row, self.dest / name, self.dest / (name + '.partial')

    def test_dry_run_never_creates_destination_or_state(self):
        self.job.prepare_destination(dry_run=True)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.run / 'evidence/destination-owner.json').exists())

    def test_prepare_retains_all_81_rows_and_is_resumable_with_marker(self):
        self.job.prepare_destination()
        self.assertEqual(len(self.job.state['files']), 81)
        (self.dest / '.gitattributes.partial').write_bytes(b'preserved')
        original = (self.dest / '.gitattributes.partial').stat()
        self.job.prepare_destination()
        self.assertEqual((self.dest / '.gitattributes.partial').stat().st_ino, original.st_ino)
        self.assertEqual(self.job.state['files']['.gitattributes']['initial_bytes'], 9)

    def test_nonempty_destination_without_owner_refuses_even_expected_name(self):
        self.dest.mkdir(mode=0o700)
        (self.dest / '.gitattributes.partial').write_bytes(b'foreign')
        with self.assertRaisesRegex(acquire.IntegrityError, 'ownership'):
            self.job.prepare_destination()
        self.assertEqual((self.dest / '.gitattributes.partial').read_bytes(), b'foreign')

    def test_owner_marker_bound_to_exact_manifest_and_inode(self):
        self.job.prepare_destination()
        marker = self.run / 'evidence/destination-owner.json'
        value = json.loads(marker.read_text())
        value['manifest_sha256'] = '0' * 64
        marker.write_text(json.dumps(value))
        with self.assertRaisesRegex(acquire.IntegrityError, 'binding'):
            self.job.prepare_destination()

    def test_new_dotted_file_hashes_and_promotes(self):
        body = b'ordinary Git attributes fixture'
        row, final, partial = self.prepare('.gitattributes', body)
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(body, len(body))) as network:
            self.job.one(row)
        self.assertIsNone(network.call_args.args[0].get_header('Range'))
        self.assertEqual(final.read_bytes(), body)
        self.assertFalse(partial.exists())
        result = self.job.state['files'][row['path']]
        self.assertEqual(result['computed_sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(result['computed_git_blob_sha1'], row['git_blob_sha1'])
        self.assertEqual(result['file_stat'], acquire.file_proof(final.stat()))

    def test_empty_new_and_existing_partial_use_no_network_and_actual_hash(self):
        for prefix in (None, b''):
            row, final, partial = self.prepare('safetensors-md5sum.txt', b'', prefix)
            with patch.object(acquire.urllib.request, 'urlopen') as network:
                self.job.one(row)
            network.assert_not_called()
            self.assertEqual(final.read_bytes(), b'')
            self.assertFalse(partial.exists())
            self.assertEqual(self.job.state['files'][row['path']]['computed_sha256'], acquire.EMPTY_SHA256)
            final.unlink()

    def test_lfs_resume_keeps_inode_and_does_not_compare_payload_to_pointer(self):
        body = b'synthetic LFS payload with prefix'
        row, final, partial = self.prepare('weight.safetensors', body, body[:7], lfs=True)
        inode = partial.stat().st_ino
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(body[7:], len(body), 7)) as network:
            self.job.one(row)
        self.assertEqual(network.call_args.args[0].get_header('Range'), 'bytes=7-')
        self.assertEqual(final.stat().st_ino, inode)
        result = self.job.state['files'][row['path']]
        self.assertNotIn('computed_git_blob_sha1', result)
        self.assertTrue(result['verified'])

    def test_bad_range_keeps_prefix_unmodified(self):
        body = b'prefix-fixture-tail'
        row, final, partial = self.prepare(body=body, prefix=body[:6])
        response = Response(body[6:], len(body), 6)
        response.headers['Content-Range'] = 'bytes 0-0/1'
        with patch.object(acquire.urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(acquire.IntegrityError):
                self.job.one(row)
        self.assertEqual(partial.read_bytes(), body[:6])
        self.assertFalse(final.exists())

    def test_hash_mismatch_preserves_complete_partial_and_never_promotes(self):
        row, final, partial = self.prepare(body=b'valid', prefix=b'wrong')
        with patch.object(acquire.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(acquire.IntegrityError, 'SHA256'):
                self.job.one(row)
        network.assert_not_called()
        self.assertEqual(partial.read_bytes(), b'wrong')
        self.assertFalse(final.exists())

    def test_git_hash_mismatch_preserves_sha_correct_partial(self):
        row, final, partial = self.prepare(body=b'valid', prefix=b'valid')
        row['git_blob_sha1'] = '0' * 40
        with self.assertRaisesRegex(acquire.IntegrityError, 'Git payload'):
            self.job.one(row)
        self.assertTrue(partial.exists())
        self.assertFalse(final.exists())

    def test_truncated_response_retries_from_preserved_actual_offset(self):
        body = b'abcdEFGH'
        row, final, partial = self.prepare(body=body)
        responses = [Response(body[:4], 8), Response(body[4:], 8, 4)]
        with patch.object(acquire.urllib.request, 'urlopen', side_effect=responses) as network, \
                patch.object(self.job.cancel, 'wait', return_value=False):
            self.job.one(row)
        self.assertEqual(network.call_args_list[1].args[0].get_header('Range'), 'bytes=4-')
        self.assertEqual(final.read_bytes(), body)

    def test_oversized_body_never_writes_excess_bytes(self):
        row, final, partial = self.prepare(body=b'abcd')
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(b'abcde', 4)):
            with self.assertRaisesRegex(acquire.IntegrityError, 'exceeds'):
                self.job.one(row)
        self.assertEqual(partial.read_bytes(), b'')
        self.assertFalse(final.exists())

    def test_symlink_hardlink_foreign_and_ambiguous_files_refuse(self):
        row, final, partial = self.prepare(body=b'x')
        other = self.root / 'other'
        other.write_bytes(b'x')
        partial.symlink_to(other)
        with self.assertRaises(acquire.IntegrityError):
            self.job.one(row)
        partial.unlink()
        os.link(other, partial)
        with self.assertRaises(acquire.IntegrityError):
            self.job.one(row)
        partial.unlink()
        partial.write_bytes(b'x')
        final.write_bytes(b'x')
        with self.assertRaisesRegex(acquire.IntegrityError, 'ambiguous'):
            self.job.prepare_destination()
        final.unlink()
        (self.dest / 'foreign').write_bytes(b'preserve')
        with self.assertRaisesRegex(acquire.IntegrityError, 'foreign'):
            self.job.prepare_destination()

    def test_same_size_mutation_during_hash_is_refused(self):
        row, final, partial = self.prepare(body=b'12345678', prefix=b'12345678')
        original_read = os.read
        changed = False
        def tamper(fd, count):
            nonlocal changed
            result = original_read(fd, count)
            if result and not changed:
                changed = True
                partial.write_bytes(b'12345678')
            return result
        with patch.object(acquire.os, 'read', side_effect=tamper):
            with self.assertRaisesRegex(acquire.IntegrityError, 'changed during hash'):
                self.job.one(row)
        self.assertFalse(final.exists())

    def test_anchor_symlink_replacement_and_mount_loss_cannot_redirect_write(self):
        row, final, partial = self.prepare(body=b'payload')
        moved = self.models / 'detached'
        self.dest.rename(moved)
        self.dest.mkdir()
        with self.assertRaisesRegex(acquire.IntegrityError, 'changed or mount lost'):
            self.job.one(row)
        self.assertEqual(list(self.dest.iterdir()), [])
        self.dest.rmdir()
        self.dest.symlink_to(moved)
        with self.assertRaises(OSError):
            self.job.guard()

    def test_mount_check_failure_stops_before_write(self):
        row, final, partial = self.prepare(body=b'payload')
        self.storage.side_effect = RuntimeError('fixture UUID mount mismatch')
        with self.assertRaises(RuntimeError), patch.object(acquire.urllib.request, 'urlopen') as network:
            self.job.one(row)
        network.assert_not_called()
        self.assertFalse(partial.exists())

    def test_capacity_accounts_exact_remaining_reserve_and_workers(self):
        self.job.artifacts = [artifact('config.json', b'12345')]
        self.capacity.return_value = SimpleNamespace(f_bavail=5 + 32 + 3 * 8 - 1, f_frsize=1)
        with self.assertRaisesRegex(acquire.IntegrityError, 'insufficient capacity'):
            self.job.prepare_destination(dry_run=True)

    def test_lock_excludes_second_process_and_replacement_is_detected(self):
        probe = 'import fcntl,sys; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
        lock = self.run / 'acquisition.lock'
        with self.job.owner():
            result = subprocess.run([sys.executable, '-B', '-c', probe, str(lock)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            lock.unlink()
            lock.write_bytes(b'')
            with self.assertRaisesRegex(acquire.IntegrityError, 'lock was replaced'):
                self.job.guard()

    def test_source_manifest_tamper_and_alternate_path_refuse(self):
        for path in (self.manifest.with_name('alternate.json'), self.manifest):
            if path == self.manifest:
                path.write_bytes(b'tampered')
            args = SimpleNamespace(**{**vars(self.args), 'manifest': path})
            with self.assertRaises(acquire.IntegrityError), patch.object(acquire.urllib.request, 'urlopen') as network:
                acquire.Acquisition(args)
            network.assert_not_called()

    def test_metadata_transient_failure_then_retry_passes_with_safe_status(self):
        metadata = dict(id=acquire.REPO_ID, sha=acquire.REV, siblings=[])
        self.job.artifacts = []
        body = json.dumps(metadata).encode()
        failure = acquire.urllib.error.URLError('fixture secret must never enter status')
        with patch.object(acquire.urllib.request, 'urlopen', side_effect=[failure, Response(body, len(body))]) as network, \
                patch.object(self.job.cancel, 'wait', return_value=False) as wait:
            self.assertEqual(self.job.pinned_metadata(), metadata)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(wait.call_args.args, (1,))
        self.assertEqual(self.job.state['metadata_attempt'], 2)
        self.assertEqual(self.job.state['metadata_transfer_error_type'], 'URLError')
        self.assertNotIn('fixture secret', json.dumps(self.job.state))

    def test_metadata_persistent_transport_failure_is_bounded_to_four(self):
        with patch.object(acquire.urllib.request, 'urlopen', side_effect=TimeoutError('fixture-secret-text')) as network, \
                patch.object(self.job.cancel, 'wait', return_value=False) as wait:
            with self.assertRaisesRegex(RuntimeError, 'bounded pinned metadata retry limit'):
                self.job.pinned_metadata()
        self.assertEqual(network.call_count, 4)
        self.assertEqual([call.args[0] for call in wait.call_args_list], [1, 2, 4])
        self.assertTrue(all(call.kwargs['timeout'] == 45 for call in network.call_args_list))
        self.assertNotIn('fixture-secret-text', json.dumps(self.job.state))

    def test_metadata_identity_failure_is_never_retried(self):
        body = json.dumps(dict(id='wrong/repository', sha=acquire.REV, siblings=[])).encode()
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(body, len(body))) as network, \
                patch.object(self.job.cancel, 'wait') as wait:
            with self.assertRaisesRegex(acquire.IntegrityError, 'repository/revision'):
                self.job.pinned_metadata()
        self.assertEqual(network.call_count, 1)
        wait.assert_not_called()


if __name__ == '__main__':
    unittest.main()
