#!/usr/bin/env python3
"""Offline F1A safety fixtures. Run alongside unchanged D1 helper/parallel suites.

VM: F1A_TEST_TMPDIR=/data/build/f1a-qwen-20260915/tmp python3 scripts/f1a/test_acquire.py -v
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


class Response(io.BytesIO):
    def __init__(self, body, total, offset=0, bad_range=False):
        super().__init__(body)
        self.status = 206 if offset else 200
        self.headers = {'Content-Length': str(total - offset)}
        if offset:
            self.headers['Content-Range'] = f'bytes {offset}-{total-1}/{total}'
        if bad_range:
            self.headers['Content-Range'] = 'bytes 0-1/2'


class ManifestFixtures(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((REPO / 'reports/f1a-qwen-manifest.json').read_text())

    def test_actual_qwen_and_glm_manifests_validate_in_same_private_module(self):
        self.assertEqual(len(acquire.validate_manifest(self.manifest)), 48)
        self.assertEqual(len(acquire.validate_glm_manifest(json.loads(
            (REPO / 'reports/r2-flagship-artifact.json').read_text()))), 11)

    def test_wrong_identity_exact_set_and_hash_domains_refused(self):
        mutations = [lambda m: m.update(revision='0' * 40),
                     lambda m: m['artifacts'].pop(),
                     lambda m: m['artifacts'][0].update(path='../escape'),
                     lambda m: m['artifacts'][0].update(lfs_sha256='0' * 64),
                     lambda m: m.update(total_bytes=m['total_bytes'] + 1)]
        for change in mutations:
            m = deepcopy(self.manifest)
            change(m)
            with self.assertRaises(acquire.IntegrityError):
                acquire.validate_manifest(m)

    def test_pinned_metadata_lfs_and_git_identity_are_independent_gates(self):
        rows = []
        for a in self.manifest['artifacts']:
            row = dict(rfilename=a['path'], size=a['size_bytes'])
            if 'lfs_sha256' in a:
                row['lfs'] = dict(sha256=a['sha256'], size=a['size_bytes'])
            else:
                row['blobId'] = a['git_blob_sha1']
            rows.append(row)
        meta = dict(id=acquire.REPO_ID, sha=acquire.REV, siblings=rows)
        acquire.compare_metadata(self.manifest['artifacts'], meta)
        for row in rows:
            altered = deepcopy(meta)
            candidate = next(r for r in altered['siblings'] if r['rfilename'] == row['rfilename'])
            if 'lfs' in candidate:
                candidate['lfs']['sha256'] = '0' * 64
            else:
                candidate['blobId'] = '0' * 40
            with self.assertRaises(acquire.IntegrityError):
                acquire.compare_metadata(self.manifest['artifacts'], altered)


class AcquisitionFixtures(unittest.TestCase):
    def setUp(self):
        default = tempfile.gettempdir() if sys.platform == 'darwin' else str(acquire.RUN / 'tmp')
        self.temp = tempfile.TemporaryDirectory(prefix='f1a-synthetic-',
            dir=os.environ.get('F1A_TEST_TMPDIR', default))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / 'run'
        (self.run / 'tmp').mkdir(parents=True)
        (self.run / 'evidence').mkdir()
        self.dest, self.glm = self.root / 'qwen', self.root / 'glm'
        self.dest.mkdir()
        self.glm.mkdir()
        self.addCleanup(patch.stopall)
        self.addCleanup(setattr, acquire.base, 'digest', acquire.digest)
        patch.object(acquire, 'RUN', self.run).start()
        patch.object(acquire, 'DEST', self.dest).start()
        patch.object(acquire, 'GLM_DEST', self.glm).start()
        patch.object(acquire.base, 'DEST', self.dest).start()
        patch.object(acquire.base, 'CHUNK', 8).start()
        manifest = REPO / 'reports/f1a-qwen-manifest.json'
        glm = REPO / 'reports/r2-flagship-artifact.json'
        self.args = SimpleNamespace(run_dir=self.run, workers=2,
            model_uuid=acquire.MODEL_UUID, manifest=manifest,
            manifest_sha256=acquire.digest(manifest), glm_manifest=glm,
            glm_manifest_sha256=acquire.digest(glm))
        self.job = acquire.Acquisition(self.args)
        self.guard = patch.object(self.job, 'guard', return_value={'fixture': True}).start()
        patch.object(self.job, 'failure_guard').start()
        patch.object(self.job, 'model_device', return_value=self.dest.stat().st_dev).start()
        patch.object(acquire, 'common').start()

    def artifact(self, name='config.json', body=b'{"fixture":true}', prefix=b'', git=True):
        row = dict(path=name, size_bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        if git:
            row['git_blob_sha1'] = hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest()
        final = self.dest / name
        partial = final.with_name(final.name + '.partial')
        if prefix:
            partial.write_bytes(prefix)
        self.job.artifacts = [row]
        self.job.by_path = {name: row}
        self.job.state['files'][name] = dict(bytes_present=len(prefix), initial_bytes=len(prefix),
            sha256_verified=False, artifact_verified=False, status='PENDING')
        return row, final, partial

    def test_manifest_pin_and_exact_uuid_refuse_before_transfer(self):
        for field, value in [('manifest_sha256', '0' * 64),
                             ('glm_manifest_sha256', '0' * 64), ('model_uuid', acquire.base.DATA_UUID if hasattr(acquire.base, 'DATA_UUID') else 'wrong')]:
            with self.subTest(field=field), patch.object(acquire.urllib.request, 'urlopen') as network:
                args = SimpleNamespace(**{**vars(self.args), field: value})
                with self.assertRaises(acquire.IntegrityError):
                    acquire.Acquisition(args)
                network.assert_not_called()

    def test_small_resume_preserves_inode_and_both_hashes_before_rename(self):
        body = b'small-pinned-fixture-asset'
        a, final, partial = self.artifact(body=body, prefix=body[:7])
        inode = partial.stat().st_ino
        actual_replace = os.replace
        def replace(source, destination):
            if Path(source) == partial:
                self.assertTrue(self.job.state['files'][a['path']]['git_blob_sha1_verified'])
            actual_replace(source, destination)
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(body[7:], len(body), 7)) as request, patch.object(acquire.os, 'replace', side_effect=replace):
            self.job.one(a)
        self.assertEqual(request.call_args[0][0].get_header('Range'), 'bytes=7-')
        self.assertEqual(final.stat().st_ino, inode)
        self.assertFalse(partial.exists())
        state = json.loads((self.run / 'evidence/acquisition-status.json').read_text())
        self.assertEqual(state['fully_verified_artifacts'], 1)
        self.assertEqual(state['verified_weight_shards'], 0)
        self.assertNotIn('verified_shards', state)

    def test_wrong_git_identity_retains_partial_and_never_renames(self):
        body = b'sha-correct-git-wrong'
        a, final, partial = self.artifact(body=body, prefix=body)
        a['git_blob_sha1'] = '0' * 40
        with patch.object(acquire.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(acquire.IntegrityError, 'Git blob'):
                self.job.one(a)
        network.assert_not_called()
        self.assertEqual(partial.read_bytes(), body)
        self.assertFalse(final.exists())
        self.assertFalse(self.job.state['files'][a['path']]['artifact_verified'])

    def test_wrong_range_retains_existing_prefix(self):
        body = b'prefix-synthetic-tail'
        a, final, partial = self.artifact(body=body, prefix=body[:7])
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(body[7:], len(body), 7, True)):
            with self.assertRaises(acquire.IntegrityError):
                self.job.one(a)
        self.assertEqual(partial.read_bytes(), body[:7])
        self.assertFalse(final.exists())

    def test_combined_capacity_accounts_both_remaining_plus_margin_and_buffers(self):
        a, _, _ = self.artifact(body=b'a' * 20, prefix=b'a' * 7)
        self.job.glm_artifacts = [dict(path='fixture.gguf', size_bytes=30)]
        (self.glm / 'fixture.gguf.partial').write_bytes(b'g' * 11)
        need = 13 + 19 + acquire.RESERVE + 16
        for free, fail in ((need - 1, True), (need, False)):
            with patch.object(acquire.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)):
                if fail:
                    with self.assertRaises(acquire.IntegrityError):
                        self.job.require_capacity(16)
                else:
                    self.job.require_capacity(16)
                    self.assertEqual(self.job.state['capacity']['glm_remaining_bytes'], 19)

    def test_reservation_tolerates_partial_renamed_after_lstat(self):
        a, final, partial = self.artifact(body=b'synthetic', prefix=b'synthetic')
        actual_lstat = Path.lstat
        def rename_after_stat(path):
            result = actual_lstat(path)
            if path == partial:
                os.replace(partial, final)
            return result
        with patch.object(Path, 'lstat', rename_after_stat):
            self.assertEqual(acquire.remaining_bytes(self.dest, [a], self.dest.stat().st_dev), 0)
        self.assertTrue(final.exists())

    def test_ambiguous_symlink_and_oversize_artifacts_refuse(self):
        a, final, partial = self.artifact(body=b'x', prefix=b'x')
        final.write_bytes(b'x')
        with self.assertRaises(acquire.IntegrityError):
            acquire.remaining_bytes(self.dest, [a], self.dest.stat().st_dev)
        final.unlink()
        partial.unlink()
        partial.symlink_to(self.root / 'missing')
        with self.assertRaises(acquire.IntegrityError):
            acquire.remaining_bytes(self.dest, [a], self.dest.stat().st_dev)
        partial.unlink()
        partial.write_bytes(b'oversize')
        with self.assertRaises(acquire.IntegrityError):
            acquire.remaining_bytes(self.dest, [a], self.dest.stat().st_dev)

    def test_index_missing_or_extra_shard_never_passes(self):
        (self.dest / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a': 'wrong.safetensors'}}))
        with self.assertRaisesRegex(acquire.IntegrityError, 'index referenced'):
            self.job.asset_contract()

    def test_own_lock_excludes_second_process(self):
        probe = 'import fcntl,sys; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
        lock = self.dest / '.f1a-acquisition.lock'
        with self.job.owner():
            result = subprocess.run([sys.executable, '-c', probe, str(lock)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([sys.executable, '-c', probe, str(lock)], capture_output=True)
        self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
