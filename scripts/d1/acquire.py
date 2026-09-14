#!/usr/bin/env python3
"""Acquire only pinned R2 shards; partials stay on the distinct new model disk.

Run only after human/orchestrator D0B final gates are PASS. --ready-sha256 pins
that reviewed handoff; no approval is inferred from its mere existence.
Use a transient systemd job with file logs, RuntimeMaxSec=36h, MemoryMax=2G.
Existing partials resume in place. Corrupt/ambiguous artifacts are preserved.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time
import threading
import urllib.error
import urllib.request
from storage_guard import check, common

REPO_ID = 'unsloth/GLM-5.3-GGUF'
REV = '346b3591c7f28d1a23716f97a065ecf12ec14771'
TOTAL = 467289116837
DEST = Path('/data/models-large/glm-5.3-ud-q4-k-xl')
CHUNK = 16 * 1024**2

class IntegrityError(RuntimeError):
    pass

class Cancelled(RuntimeError):
    pass

def digest(path, cancel=None):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(CHUNK), b''):
            if cancel is not None and cancel.is_set():
                raise Cancelled("acquisition cancelled")
            h.update(b)
    return h.hexdigest()

def validate_manifest(m):
    expected = [f'UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-{i:05d}-of-00011.gguf' for i in range(1, 12)]
    if (m['repo_id'], m['revision'], m['quantization'], m['artifact_count'], m['total_bytes']) != (REPO_ID, REV, 'UD-Q4_K_XL', 11, TOTAL):
        raise IntegrityError('manifest identity mismatch')
    a = m['artifacts']
    if [x['path'] for x in a] != expected or sum(x['size_bytes'] for x in a) != TOTAL:
        raise IntegrityError('manifest selected file set mismatch')
    if any(not re.fullmatch('[0-9a-f]{64}', x['sha256']) or x['size_bytes'] <= 0 for x in a):
        raise IntegrityError('invalid size/hash')
    return a

def compare_metadata(artifacts, rows):
    actual = {r['path']: (r['size'], r.get('lfs', {}).get('oid'), r.get('lfs', {}).get('size')) for r in rows if r['type'] == 'file'}
    expected = {a['path']: (a['size_bytes'], a['sha256'], a['size_bytes']) for a in artifacts}
    if actual != expected or len(rows) != 11:
        raise IntegrityError('pinned HF file count/names/sizes/SHA256 metadata mismatch')

def validate_response(response, offset, size):
    if offset:
        expected = f'bytes {offset}-{size-1}/{size}'
        if response.status != 206 or response.headers.get('Content-Range') != expected:
            raise IntegrityError('resume Range response mismatch')
    elif response.status != 200:
        raise IntegrityError('unexpected initial HTTP status')
    if int(response.headers.get('Content-Length', -1)) != size - offset:
        raise IntegrityError('HTTP content length mismatch')

def no_symlinks(path):
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise IntegrityError('symlinked artifact/state path')
    if path.exists() and not (path.is_dir() or path.is_file()):
        raise IntegrityError('nonregular path')

class Acquisition:
    def __init__(self, args):
        self.args = args
        self.run = args.run_dir.resolve(strict=True)
        self.state = {'status': 'STARTING', 'pid': os.getpid(), 'repo_id': REPO_ID, 'revision': REV,
                      'destination': str(DEST), 'total_bytes': TOTAL, 'files': {},
                      'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      'glm_inference': 'NOT_TESTED', 'tool_calls': 'NOT_TESTED'}
        self.start = time.monotonic()
        self.transferred = 0
        self.last_status = 0
        self.owns_lock = False
        self.workers = getattr(args, 'workers', 4)
        if self.workers not in (1, 3, 4):
            raise ValueError('workers must be 1, 3 or 4')
        self.mutex = threading.RLock()
        self.cancel = threading.Event()
        self.state['workers'] = self.workers
        self.state['helper_sha256'] = digest(Path(__file__))

    def guard(self):
        result = check(self.args.model_uuid)
        for path, device in [(self.run, '/data'), (self.run / 'evidence', '/data'),
                             (DEST, '/data/models-large'), (DEST / 'UD-Q4_K_XL', '/data/models-large')]:
            no_symlinks(path)
            if path.exists() and os.stat(path).st_dev != os.stat(device).st_dev:
                raise IntegrityError('nested mount redirects run/artifact path')
        self.require_capacity(self.workers * CHUNK)
        return result

    def require_capacity(self, remaining=0):
        location = DEST if DEST.exists() else Path('/data/models-large')
        if shutil.disk_usage(location).free < remaining + 20 * 1024**3:
            raise IntegrityError('insufficient model-disk free space including 20 GiB reserve')

    def model_device(self):
        return os.stat('/data/models-large').st_dev

    def cancelled(self):
        if self.cancel.is_set():
            raise Cancelled('acquisition cancelled')

    def failure_guard(self):
        # Model mount loss may still be reported on independently verified /data.
        check()
        for path in (self.run, self.run / 'evidence'):
            no_symlinks(path)
            if os.stat(path).st_dev != os.stat('/data').st_dev:
                raise IntegrityError('unsafe failure status path')

    def status(self, force=False, failure=False):
        with self.mutex:
            now = time.monotonic()
            if not force and now - self.last_status < 15:
                return
            self.state['updated_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            self.state['session_bytes_downloaded'] = self.transferred
            self.state['session_average_bytes_per_second'] = int(self.transferred / max(now-self.start, 1))
            rows = self.state['files']
            self.state['bytes_present'] = sum(f.get('bytes_present', 0) for f in rows.values())
            self.state['verified_bytes'] = sum(f.get('bytes_present', 0) for f in rows.values() if f.get('sha256_verified'))
            self.state['verified_shards'] = sum(bool(f.get('sha256_verified')) for f in rows.values())
            self.state['active_shards'] = [p for p, f in rows.items() if f.get('status') in ('DOWNLOADING', 'HASHING')]
            self.atomic_json('acquisition-status.json', self.state, failure=failure)
            self.last_status = now

    def atomic_json(self, name, value, failure=False):
        with self.mutex:
            (self.failure_guard if failure else self.guard)()
            final = self.run / 'evidence' / name
            tmp = final.with_suffix('.tmp')
            no_symlinks(final)
            no_symlinks(tmp)
            with tmp.open('w') as f:
                json.dump(value, f, indent=2)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, final)
            directory = os.open(str(final.parent), os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    @contextmanager
    def owner(self):
        lock = DEST / '.d1-acquisition.lock'
        no_symlinks(lock)
        with lock.open('a') as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.owns_lock = True
            try:
                yield
            except BaseException as exc:
                self.cancel.set()
                with self.mutex:
                    self.state.update(status='CANCELLED' if isinstance(exc, Cancelled) else 'STOP',
                                      error_type=type(exc).__name__)
                    for row in self.state['files'].values():
                        if row.get('status') in ('PENDING', 'DOWNLOADING', 'HASHING'):
                            row['status'] = 'CANCELLED'
                try:
                    self.status(True, failure=True)
                    common(self.run / 'evidence/root-acquisition-stopped.md')
                except Exception:
                    # Never fall back to root or an unverified status filesystem.
                    print('STOP: final status write/guard unavailable; previous JSON may be stale', file=sys.stderr)
                raise
            finally:
                self.owns_lock = False
                fcntl.flock(lockfile, fcntl.LOCK_UN)

    def run_workers(self, artifacts):
        if len({a['path'] for a in artifacts}) != len(artifacts):
            raise IntegrityError('duplicate shard task')
        errors = []
        def worker(a):
            try:
                self.cancelled()
                self.one(a)
            except BaseException as exc:
                self.cancel.set()
                with self.mutex:
                    self.state['files'][a['path']].update(
                        status='CANCELLED' if isinstance(exc, Cancelled) else 'FAILED',
                        error_type=type(exc).__name__)
                raise
        # Only eleven futures and at most four CHUNK buffers; no unbounded queues/logs.
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='d1-shard') as pool:
            futures = [pool.submit(worker, a) for a in artifacts]
            for future in as_completed(futures):
                try:
                    future.result()
                except BaseException as exc:
                    errors.append(exc)
                    self.cancel.set()
        if errors:
            # Do not hide the original failure behind a peer's cancellation.
            raise next((e for e in errors if not isinstance(e, Cancelled)), errors[0])
        self.cancelled()

    def acquire(self):
        identity = self.guard()
        no_symlinks(self.run)
        if not str(self.run).startswith('/data/build/d1-') or os.stat(self.run).st_dev != os.stat('/data').st_dev:
            raise IntegrityError('run path must reside on existing /data')
        if digest(self.args.storage_ready) != self.args.ready_sha256 or self.args.model_uuid not in self.args.storage_ready.read_text():
            raise IntegrityError('reviewed D0B handoff missing/changed or UUID absent')
        self.state.update(mounts=identity, ready_sha256=self.args.ready_sha256, manifest_sha256=digest(self.args.manifest))
        artifacts = validate_manifest(json.loads(self.args.manifest.read_text()))
        self.guard()
        no_symlinks(DEST)
        DEST.mkdir(exist_ok=True)
        self.guard()
        with self.owner():
            common(self.run / 'evidence/root-acquisition-before.md')
            self.guard()
            # Pin metadata again on every resume; no signed URLs/headers are recorded.
            url = f'https://huggingface.co/api/models/{REPO_ID}/tree/{REV}/UD-Q4_K_XL'
            with urllib.request.urlopen(url, timeout=60) as response:
                if response.headers.get('Link'):
                    raise IntegrityError('unexpected metadata pagination')
                rows = json.load(response)
            compare_metadata(artifacts, rows)
            self.atomic_json('hf-pinned-metadata.json', rows)
            selected = DEST / 'UD-Q4_K_XL'
            no_symlinks(selected)
            self.guard()
            selected.mkdir(exist_ok=True)
            allowed = {Path(a['path']).name + suffix for a in artifacts for suffix in ('', '.partial')}
            if any(p.name not in allowed for p in selected.iterdir()):
                raise IntegrityError('unexpected file in selected shard directory')
            remaining = TOTAL
            for a in artifacts:
                final = DEST / a['path']
                partial = final.with_name(final.name + '.partial')
                for p in (final, partial):
                    no_symlinks(p)
                    if p.exists() and (not p.is_file() or p.stat().st_dev != os.stat('/data/models-large').st_dev):
                        raise IntegrityError('artifact path is not a file')
                if final.exists() and partial.exists():
                    raise IntegrityError('ambiguous final plus partial')
                existing = final if final.exists() else partial
                n = existing.stat().st_size if existing.exists() else 0
                if n > a['size_bytes']:
                    raise IntegrityError('oversize partial/final')
                remaining -= n
                self.state['files'][a['path']] = {'bytes_present': n, 'initial_bytes': n, 'sha256_verified': False, 'status': 'PENDING'}
            self.require_capacity(remaining)
            self.state['status'] = 'DOWNLOADING'
            self.status(True)
            self.run_workers(artifacts)
            # Final acceptance reads all exact filesystem sizes; each SHA was computed above.
            if ({p.name for p in selected.iterdir()} != {Path(a['path']).name for a in artifacts}
                    or any((DEST/a['path']).stat().st_size != a['size_bytes'] for a in artifacts)
                    or not all(self.state['files'][a['path']].get('sha256_verified') for a in artifacts)):
                raise IntegrityError('final artifact set mismatch')
            self.guard()
            common(self.run / 'evidence/root-acquisition-after.md')
            self.cancelled()
            self.state['status'] = 'PASS_ALL_11_COMPUTED_SHA256'
            self.status(True)

    def one(self, a):
        final = DEST / a['path']
        partial = final.with_name(final.name + '.partial')
        row = self.state['files'][a['path']]
        if not final.exists():
            for attempt in range(6):
                self.cancelled()
                self.guard()  # immediately before each transfer/resume
                no_symlinks(partial)
                offset = partial.stat().st_size if partial.exists() else 0
                if offset > a['size_bytes']:
                    raise IntegrityError('oversize partial')
                if offset == a['size_bytes']:
                    break
                url = f'https://huggingface.co/{REPO_ID}/resolve/{REV}/{a["path"]}'
                headers = {'Accept-Encoding': 'identity'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
                        validate_response(response, offset, a['size_bytes'])
                        self.cancelled()
                        self.guard()
                        no_symlinks(partial)
                        with self.mutex:
                            row.update(status='DOWNLOADING', last_request_offset=offset,
                                       response_status=response.status,
                                       content_range=response.headers.get('Content-Range'),
                                       attempt=attempt + 1)
                            row.setdefault('first_request_offset', offset)
                            self.status(True)
                        # Unbuffered append preserves existing offsets; fsync even on cancellation.
                        with partial.open('ab', buffering=0) as f:
                            if os.fstat(f.fileno()).st_dev != self.model_device() or os.fstat(f.fileno()).st_size != offset:
                                raise IntegrityError('partial file device/offset changed')
                            try:
                                while True:
                                    self.cancelled()
                                    block = response.read(min(CHUNK, a['size_bytes'] - offset + 1))
                                    if not block:
                                        break
                                    if offset + len(block) > a['size_bytes']:
                                        raise IntegrityError('HTTP body exceeds expected size')
                                    self.guard()  # mid-stream UUID/root guard before every bulk write
                                    self.cancelled()
                                    n = f.write(block)
                                    offset += n
                                    with self.mutex:
                                        self.transferred += n
                                        row['bytes_present'] = offset
                                        self.status()
                                    if n != len(block):
                                        raise OSError('short file write')
                            finally:
                                os.fsync(f.fileno())
                    if offset != a['size_bytes']:
                        raise OSError('incomplete transfer')
                    break
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    # Only exception class; never URLs, headers containing credentials, or bodies.
                    with self.mutex:
                        row['last_transfer_error'] = type(exc).__name__
                        self.status(True)
                    if attempt == 5:
                        raise RuntimeError('bounded download retry limit') from None
                    if self.cancel.wait(min(2**attempt, 30)):
                        raise Cancelled('acquisition cancelled')
        target = final if final.exists() else partial
        self.cancelled()
        self.guard()
        no_symlinks(target)
        with self.mutex:
            row['status'] = 'HASHING'
            self.status(True)
        if target.stat().st_size != a['size_bytes'] or digest(target, self.cancel) != a['sha256']:
            raise IntegrityError('computed SHA256/size mismatch: artifact preserved')
        self.cancelled()
        if target == partial:
            self.guard()
            no_symlinks(final)
            if final.exists():
                raise IntegrityError('final appeared during transfer')
            # A complete partial from an interrupted owner may not have been fsynced.
            with partial.open('rb') as f:
                os.fsync(f.fileno())
            self.cancelled()
            os.replace(partial, final)
            directory = os.open(str(final.parent), os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        with self.mutex:
            row.update(bytes_present=a['size_bytes'], sha256_verified=True,
                       computed_sha256=a['sha256'], status='VERIFIED')
            self.status(True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--model-uuid', required=True)
    p.add_argument('--storage-ready', type=Path, required=True)
    p.add_argument('--ready-sha256', required=True)
    p.add_argument('--workers', type=int, choices=(1, 3, 4), default=4,
                   help='distinct shard workers; 1 is the sequential fallback (default: 4)')
    args = p.parse_args()
    job = Acquisition(args)
    def request_stop(signum, frame):
        job.cancel.set()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        job.acquire()
    except Exception as exc:
        # owner() records terminal state before releasing its global flock.
        print('STOP acquisition: ' + type(exc).__name__, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
