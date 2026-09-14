#!/usr/bin/env python3
"""Synthetic, offline metadata hash and bounded-response checks.

Run: PYTHONDONTWRITEBYTECODE=1 python3 scripts/f1a/test_prepare_manifest.py -v
No model, network request, mount operation, or real filesystem write is performed.
"""
from contextlib import redirect_stderr
import hashlib
import io
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('f1a_prepare_manifest', Path(__file__).with_name('prepare_manifest.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetadataVerification(unittest.TestCase):
    def setUp(self):
        self.content = b'{"synthetic":true}\n'
        self.sha = hashlib.sha256(self.content).hexdigest()
        self.blob = hashlib.sha1(b'blob ' + str(len(self.content)).encode() + b'\0' + self.content).hexdigest()
        self.row = {'rfilename': 'config.json', 'size': len(self.content), 'blobId': self.blob}

    def test_git_blob_identity_returns_computed_sha256(self):
        self.assertEqual(MODULE.verify_asset(self.row, self.content), self.sha)

    def test_git_blob_identity_rejects_same_size_substitution(self):
        with self.assertRaisesRegex(RuntimeError, 'Git blob mismatch'):
            MODULE.verify_asset(self.row, self.content.replace(b'true', b'null'))

    def test_git_blob_uses_git_header_not_raw_file_sha1(self):
        self.row['blobId'] = hashlib.sha1(self.content).hexdigest()
        with self.assertRaisesRegex(RuntimeError, 'Git blob mismatch'):
            MODULE.verify_asset(self.row, self.content)

    def test_small_asset_size_mismatch_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'size mismatch'):
            MODULE.verify_asset(self.row, self.content + b' ')

    def test_lfs_small_asset_requires_published_size_and_sha(self):
        self.row['lfs'] = {'sha256': self.sha, 'size': len(self.content)}
        self.assertEqual(MODULE.verify_asset(self.row, self.content), self.sha)
        for field, wrong in [('sha256', '0' * 64), ('size', len(self.content) + 1)]:
            with self.subTest(field=field):
                bad = dict(self.row, lfs={**self.row['lfs'], field: wrong})
                with self.assertRaisesRegex(RuntimeError, 'LFS hash mismatch'):
                    MODULE.verify_asset(bad, self.content)

    def test_missing_git_identity_cannot_pass(self):
        del self.row['blobId']
        with self.assertRaises(KeyError):
            MODULE.verify_asset(self.row, self.content)

    def test_run_path_rejects_escape_and_unrelated_paths_before_any_storage_action(self):
        for run in ('/data/build/f1a-x/../other', '/data/build/other', '/data/build/f1a-x/nested', '/tmp/f1a-x', 'relative'):
            with self.subTest(run=run), patch.object(MODULE.sys, 'argv', ['prepare_manifest.py', '--run-dir', run]), patch.object(MODULE, 'check') as guard:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                    MODULE.main()
                self.assertEqual(stopped.exception.code, 2)
                guard.assert_not_called()

    def test_metadata_fetch_accepts_only_exact_200_and_bounded_body(self):
        class Response:
            def __init__(self, status, body):
                self.status, self.body = status, body
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return self.body[:limit]
        with patch.object(MODULE.urllib.request, 'urlopen', return_value=Response(200, b'abc')) as request:
            self.assertEqual(MODULE.fetch('https://example.invalid/fixture', limit=3), b'abc')
            request.assert_called_once_with('https://example.invalid/fixture', timeout=90)
        for status, content, message in [(206, b'abc', 'HTTP status'), (200, b'abcd', 'size limit')]:
            with self.subTest(status=status, body_bytes=len(content)):
                with patch.object(MODULE.urllib.request, 'urlopen', return_value=Response(status, content)):
                    with self.assertRaisesRegex(RuntimeError, message):
                        MODULE.fetch('https://example.invalid/fixture', limit=3)


if __name__ == '__main__':
    unittest.main()
