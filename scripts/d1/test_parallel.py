#!/usr/bin/env python3
"""SYNTHETIC parallel acquisition fixtures; never changes live mounts or shards.

Worker command (all fixture bytes remain under /data):
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/d1/test_parallel.py -v
Optional local command: D1_TEST_TMPDIR=/tmp python3 scripts/d1/test_parallel.py -v
Only fixture HTTP responses are used; no model/network request is made.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import acquire


class Response(io.BytesIO):
    def __init__(self, body, size, offset=0, status=None, headers=None, before_read=None):
        super().__init__(body)
        self.status = (206 if offset else 200) if status is None else status
        self.headers = {'Content-Length': str(size - offset)}
        if offset:
            self.headers['Content-Range'] = f'bytes {offset}-{size-1}/{size}'
        if headers:
            self.headers.update(headers)
        self.before_read = before_read

    def read(self, count=-1):
        if self.before_read:
            self.before_read()
        return super().read(count)


class ParallelFixtures(unittest.TestCase):
    def setUp(self):
        base = os.environ.get('D1_TEST_TMPDIR', '/data/build/d1-glm53-20260915/tmp')
        self.temp = tempfile.TemporaryDirectory(prefix='d1b-synthetic-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.dest = self.root / 'models'
        (self.dest / 'UD-Q4_K_XL').mkdir(parents=True)
        self.run = self.root / 'run'
        (self.run / 'evidence').mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(acquire, 'DEST', self.dest).start()
        patch.object(acquire, 'CHUNK', 8).start()
        self.job = acquire.Acquisition(SimpleNamespace(
            run_dir=self.run, workers=4,
            model_uuid='synthetic-model-uuid', storage_ready=self.run / 'ready',
            ready_sha256='0' * 64, manifest=self.run / 'manifest'))
        self.guard = patch.object(self.job, 'guard', return_value={'synthetic': True}).start()
        self.failure_guard = patch.object(self.job, 'failure_guard', return_value=None).start()
        patch.object(acquire, 'common', return_value=None).start()
        patch.object(self.job, 'model_device', return_value=self.dest.stat().st_dev).start()
        self.job.state['status'] = 'DOWNLOADING'

    def artifact(self, index, body, prefix=b''):
        item = {'path': f'UD-Q4_K_XL/synthetic-{index:02d}.gguf',
                'size_bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
        final = self.dest / item['path']
        partial = final.with_name(final.name + '.partial')
        if prefix:
            partial.write_bytes(prefix)
        self.job.state['files'][item['path']] = {
            'bytes_present': len(prefix), 'sha256_verified': False}
        return item, final, partial

    def test_four_distinct_transfers_really_overlap_and_verify(self):
        items = [self.artifact(i, bytes([65 + i]) * 41) for i in range(8)]
        bodies = {a['path']: bytes([65 + i]) * 41 for i, (a, _, _) in enumerate(items)}
        barrier = threading.Barrier(4, timeout=5)
        lock = threading.Lock()
        active = set()
        seen = []
        peak = [0]

        def request(req, timeout):
            key = next(key for key in bodies if req.full_url.endswith(key))
            with lock:
                self.assertNotIn(key, active, 'two workers requested the same shard')
                active.add(key)
                seen.append(key)
                peak[0] = max(peak[0], len(active))
            barrier.wait()

            class ConcurrentResponse(Response):
                def close(inner):
                    with lock:
                        active.discard(key)
                    super().close()

            return ConcurrentResponse(bodies[key], len(bodies[key]))

        with patch.object(acquire.urllib.request, 'urlopen', side_effect=request):
            self.job.run_workers([a for a, _, _ in items])
        self.assertEqual(peak[0], 4)
        self.assertCountEqual(seen, bodies)
        self.assertEqual(self.job.transferred, sum(map(len, bodies.values())))
        for a, final, partial in items:
            self.assertEqual(final.read_bytes(), bodies[a['path']])
            self.assertFalse(partial.exists())
            self.assertTrue(self.job.state['files'][a['path']]['sha256_verified'])
        self.job.status(True)
        self.assertEqual(json.loads((self.run / 'evidence/acquisition-status.json').read_text())['verified_shards'], 8)

    def test_duplicate_shard_is_rejected_before_any_transfer(self):
        a, _, _ = self.artifact(0, b'fixture')
        with patch.object(self.job, 'one') as one:
            with self.assertRaises((RuntimeError, ValueError)):
                self.job.run_workers([a, a])
        one.assert_not_called()

    def test_atomic_status_is_valid_and_consistent_for_concurrent_readers(self):
        artifacts = [self.artifact(i, b'x' * 64)[0] for i in range(4)]
        status_path = self.run / 'evidence/acquisition-status.json'
        self.job.status(True)
        done = threading.Event()
        failures = []
        samples = [0]

        def reader():
            while not done.is_set():
                try:
                    snapshot = json.loads(status_path.read_text())
                    present = sum(row['bytes_present'] for row in snapshot['files'].values())
                    self.assertEqual(snapshot['bytes_present'], present)
                    self.assertEqual(snapshot['session_bytes_downloaded'], present)
                    self.assertEqual(snapshot['verified_bytes'], 0)
                    samples[0] += 1
                except Exception as exc:
                    failures.append(exc)
                    return

        def writer(a):
            for _ in range(32):
                with self.job.mutex:
                    self.job.transferred += 1
                    self.job.state['files'][a['path']]['bytes_present'] += 1
                self.job.status(True)

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(writer, artifacts))
        finally:
            done.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, failures)
        self.assertGreater(samples[0], 0)
        snapshot = json.loads(status_path.read_text())
        self.assertEqual(snapshot['bytes_present'], 128)
        self.assertEqual(snapshot['session_bytes_downloaded'], 128)
        self.assertFalse(list((self.run / 'evidence').glob('*.tmp')))

    def test_resume_preserves_prefix_exact_range_hash_and_fsync_rename(self):
        body = b'original-PREFIX:then-new-fixture-bytes'
        prefix = body[:16]
        a, final, partial = self.artifact(0, body, prefix)
        inode = partial.stat().st_ino
        calls = []
        synced = []
        original_fsync = os.fsync

        def request(req, timeout):
            calls.append(req.get_header('Range'))
            self.assertEqual(partial.read_bytes(), prefix)
            return Response(body[len(prefix):], len(body), len(prefix))

        def fsync(fd):
            synced.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
            return original_fsync(fd)

        with patch.object(acquire.urllib.request, 'urlopen', side_effect=request), patch.object(acquire.os, 'fsync', side_effect=fsync):
            self.job.one(a)
        self.assertEqual(calls, [f'bytes={len(prefix)}-'])
        self.assertEqual(final.stat().st_ino, inode, 'partial must be retained and renamed in place')
        self.assertEqual(final.read_bytes(), body)
        self.assertFalse(partial.exists())
        self.assertEqual(self.job.transferred, len(body) - len(prefix))
        self.assertEqual(self.job.state['files'][a['path']]['computed_sha256'], a['sha256'])
        self.assertIn('file', synced)
        self.assertIn('directory', synced)

    def test_complete_partial_is_hashed_fsynced_then_renamed_without_network(self):
        body = b'complete-synthetic-partial'
        a, final, partial = self.artifact(0, body, body)
        inode = partial.stat().st_ino
        directory_inode = partial.parent.stat().st_ino
        events = []
        original_fsync, original_replace = os.fsync, os.replace

        def fsync(fd):
            current_inode = os.fstat(fd).st_ino
            if current_inode == inode:
                events.append('partial-fsync')
            elif current_inode == directory_inode:
                events.append('directory-fsync')
            return original_fsync(fd)

        def replace(source, destination):
            if Path(source) == partial:
                events.append('rename')
            return original_replace(source, destination)

        with patch.object(acquire.urllib.request, 'urlopen') as network, patch.object(
                acquire.os, 'fsync', side_effect=fsync), patch.object(acquire.os, 'replace', side_effect=replace):
            self.job.one(a)
        network.assert_not_called()
        self.assertEqual(events, ['partial-fsync', 'rename', 'directory-fsync'])
        self.assertEqual(final.stat().st_ino, inode)
        self.assertEqual(final.read_bytes(), body)
        self.assertEqual(self.job.transferred, 0)
        self.assertTrue(self.job.state['files'][a['path']]['sha256_verified'])

    def test_bad_range_preserves_partial_without_writing(self):
        body = b'prefix-good-tail'
        for i, (status, headers) in enumerate([
            (200, {}),
            (206, {'Content-Range': 'bytes 0-14/15'}),
            (206, {'Content-Range': 'bytes 6-14/16'}),
            (206, {'Content-Length': '123'}),
        ]):
            with self.subTest(status=status, headers=headers):
                a, final, partial = self.artifact(i, body, body[:6])
                with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(
                        body[6:], len(body), 6, status=status, headers=headers)):
                    with self.assertRaises(acquire.IntegrityError):
                        self.job.one(a)
                self.assertEqual(partial.read_bytes(), body[:6])
                self.assertFalse(final.exists())
                self.assertFalse(self.job.state['files'][a['path']]['sha256_verified'])

    def test_interrupted_body_retries_from_new_offset_and_keeps_prefix(self):
        body = b'prefix-abcdefghijklmno'
        prefix = body[:7]
        a, final, partial = self.artifact(0, body, prefix)
        inode = partial.stat().st_ino
        requests = []

        def request(req, timeout):
            requests.append(req.get_header('Range'))
            if len(requests) == 1:
                return Response(body[7:15], len(body), 7)
            self.assertEqual(partial.stat().st_ino, inode)
            self.assertEqual(partial.read_bytes(), body[:15])
            return Response(body[15:], len(body), 15)

        with patch.object(acquire.urllib.request, 'urlopen', side_effect=request), patch.object(
                self.job.cancel, 'wait', return_value=False):
            self.job.one(a)
        self.assertEqual(requests, ['bytes=7-', 'bytes=15-'])
        self.assertEqual(final.stat().st_ino, inode)
        self.assertEqual(final.read_bytes(), body)
        self.assertEqual(self.job.transferred, len(body) - len(prefix))
        row = self.job.state['files'][a['path']]
        self.assertEqual(row['first_request_offset'], 7)
        self.assertEqual(row['last_request_offset'], 15)
        self.assertEqual(row['response_status'], 206)
        self.assertTrue(row['sha256_verified'])

    def test_cancellation_before_transfer_preserves_partial(self):
        body = b'prefix-new-tail'
        a, final, partial = self.artifact(0, body, body[:6])
        self.job.cancel.set()
        with patch.object(acquire.urllib.request, 'urlopen') as network:
            with self.assertRaises(acquire.Cancelled):
                self.job.one(a)
        network.assert_not_called()
        self.assertEqual(partial.read_bytes(), body[:6])
        self.assertFalse(final.exists())

    def test_oversize_http_body_is_preserved_and_never_accepted(self):
        body = b'prefix-tail'
        a, final, partial = self.artifact(0, body, body[:6])
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(body[6:] + b'!', len(body), 6)):
            with self.assertRaises(acquire.IntegrityError):
                self.job.one(a)
        self.assertTrue(partial.read_bytes().startswith(body[:6]))
        self.assertLessEqual(partial.stat().st_size, len(body))
        self.assertFalse(final.exists())
        self.assertFalse(self.job.state['files'][a['path']]['sha256_verified'])

    def test_wrong_hash_preserves_all_partial_bytes(self):
        expected = b'prefix-correct-tail'
        actual = b'prefix-corrupt-tail'
        self.assertEqual(len(expected), len(actual))
        a, final, partial = self.artifact(0, expected, expected[:7])
        with patch.object(acquire.urllib.request, 'urlopen', return_value=Response(actual[7:], len(expected), 7)):
            with self.assertRaises(acquire.IntegrityError):
                self.job.one(a)
        self.assertEqual(partial.read_bytes(), actual)
        self.assertFalse(final.exists())
        self.assertFalse(self.job.state['files'][a['path']]['sha256_verified'])

    def test_wrong_partial_device_refuses_before_bulk_write(self):
        body = b'prefix-new-tail'
        a, final, partial = self.artifact(0, body, body[:6])
        with patch.object(self.job, 'model_device', return_value=self.dest.stat().st_dev + 123), patch.object(
                acquire.urllib.request, 'urlopen', return_value=Response(body[6:], len(body), 6)):
            with self.assertRaises(acquire.IntegrityError):
                self.job.one(a)
        self.assertEqual(partial.read_bytes(), body[:6])
        self.assertFalse(final.exists())

    def test_initial_mount_mismatch_never_opens_network_or_changes_partial(self):
        body = b'prefix-new-tail'
        a, final, partial = self.artifact(0, body, body[:6])
        self.guard.side_effect = RuntimeError('synthetic mount UUID mismatch')
        with patch.object(acquire.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(RuntimeError, 'UUID mismatch'):
                self.job.one(a)
        network.assert_not_called()
        self.assertEqual(partial.read_bytes(), body[:6])
        self.assertFalse(final.exists())

    def test_capacity_reserve_boundary_and_continuous_guard(self):
        remaining = self.job.workers * acquire.CHUNK
        for free, fails in [(20 * 1024**3 + remaining - 1, True),
                            (20 * 1024**3 + remaining, False)]:
            with self.subTest(free=free), patch.object(
                    acquire.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)):
                if fails:
                    with self.assertRaisesRegex(acquire.IntegrityError, '20 GiB reserve'):
                        self.job.require_capacity(remaining)
                else:
                    self.job.require_capacity(remaining)
        # Invoke the real guard with only synthetic mount/device observations.
        with patch.object(acquire, 'check', return_value={'synthetic': True}), patch.object(
                acquire, 'no_symlinks'), patch.object(acquire.os, 'stat', return_value=SimpleNamespace(st_dev=7)), patch.object(
                self.job, 'require_capacity') as capacity:
            acquire.Acquisition.guard(self.job)
            capacity.assert_called_once_with(remaining)

    def test_midstream_guard_failure_cancels_peer_without_losing_prefix(self):
        body = b'prefix-abcdefghijklmno'
        entries = [self.artifact(i, body, body[:7]) for i in range(2)]
        barrier = threading.Barrier(2, timeout=5)
        local = threading.local()

        def request(req, timeout):
            key = next(a['path'] for a, _, _ in entries if req.full_url.endswith(a['path']))
            local.bad = key == entries[0][0]['path']
            local.in_read = False

            def before_read():
                barrier.wait()
                if local.bad:
                    local.in_read = True
                elif not self.job.cancel.wait(5):
                    raise AssertionError('peer failure did not signal cancellation')

            return Response(body[7:], len(body), 7, before_read=before_read)

        def guard():
            if getattr(local, 'in_read', False):
                raise RuntimeError('synthetic midstream mount loss')
            return {'synthetic': True}

        self.guard.side_effect = guard
        with patch.object(acquire.urllib.request, 'urlopen', side_effect=request):
            with self.assertRaises(RuntimeError):
                self.job.run_workers([a for a, _, _ in entries])
        self.assertTrue(self.job.cancel.is_set())
        self.assertNotEqual(self.job.state['status'], 'PASS_ALL_11_COMPUTED_SHA256')
        for a, final, partial in entries:
            self.assertEqual(partial.read_bytes(), body[:7])
            self.assertFalse(final.exists())
            self.assertFalse(self.job.state['files'][a['path']]['sha256_verified'])

    def test_one_worker_hash_failure_prevents_group_acceptance(self):
        entries = [self.artifact(i, b'fixture-' + bytes([65 + i])) for i in range(4)]

        def request(req, timeout):
            i = next(i for i, (a, _, _) in enumerate(entries) if req.full_url.endswith(a['path']))
            body = b'fixture-' + bytes([90 if i == 0 else 65 + i])
            return Response(body, len(body))

        with patch.object(acquire.urllib.request, 'urlopen', side_effect=request):
            with self.assertRaises(acquire.IntegrityError):
                self.job.run_workers([a for a, _, _ in entries])
        a, final, partial = entries[0]
        self.assertFalse(final.exists())
        self.assertEqual(partial.read_bytes(), b'fixture-Z')
        self.assertFalse(self.job.state['files'][a['path']]['sha256_verified'])
        self.assertNotEqual(self.job.state['status'], 'PASS_ALL_11_COMPUTED_SHA256')
        self.assertTrue(self.job.cancel.is_set())

    def test_exclusive_owner_lock_is_process_wide_and_released(self):
        probe = (
            "import fcntl, pathlib, sys\n"
            "with pathlib.Path(sys.argv[1]).open('a') as f:\n"
            " try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            " except BlockingIOError: sys.exit(23)\n"
        )
        lock = self.dest / '.d1-acquisition.lock'

        def check_owner(expected):
            result = subprocess.run([sys.executable, '-c', probe, str(lock)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            self.assertEqual(result.returncode, expected, result.stderr.decode())

        with self.job.owner():
            self.assertTrue(self.job.owns_lock)
            check_owner(23)
            self.job.state['status'] = 'STOP'
            self.job.status(True)
            check_owner(23)
        self.assertFalse(self.job.owns_lock)
        check_owner(0)
        # Probe the real flock from a child while owner() publishes terminal state.
        self.failure_guard.side_effect = lambda: check_owner(23)
        with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
            with self.job.owner():
                raise RuntimeError('synthetic failure')
        self.failure_guard.assert_called()
        snapshot = json.loads((self.run / 'evidence/acquisition-status.json').read_text())
        self.assertEqual(snapshot['status'], 'STOP')
        self.assertEqual(snapshot['error_type'], 'RuntimeError')
        self.assertFalse(self.job.owns_lock)
        check_owner(0)


if __name__ == '__main__':
    print('SYNTHETIC FIXTURES: no live network, mounts, services, or model shards are modified.', flush=True)
    unittest.main()
