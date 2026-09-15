#!/usr/bin/env python3
"""Bounded Q38A byte acquisition. No model import, load, sealing, or lifecycle mutation.

Run with python3 -B, TMPDIR and all output below the exact task run directory.
Reuses reviewed D1 UUID/root checks and its Range/retry/streaming design; directory
file descriptors additionally anchor every task write against mount/path loss.
The immutable Q38S manifest is the complete artifact list, including empty/dot files.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('_q38a_reviewed_storage', REPO / 'scripts/d1/storage_guard.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
REPO_ID = 'Qwen/Qwen3.8-27B-FP8'
REV = '017b9c7af6b5689d5dd426a76e0bc077eb5ca20a'
MANIFEST_SHA256 = '726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2'
MODEL_UUID = 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
DATA = Path('/data')
MODELS = DATA / 'models-large'
DEST = MODELS / 'qwen38-27b-fp8'
RUN = DATA / 'build/q38a-20260915'
SOURCE = DATA / 'services/q38a-20260915/repo'
TOTAL = 30890049597
RESERVE = 20 * 1024**3
CHUNK = 16 * 1024**2
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()


class IntegrityError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def safe_name(name):
    # This pinned source has only flat paths. A leading dot is safe; dot and
    # dotdot, slash, reserved partial names, and normalization aliases are not.
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name)
            or name in ('.', '..')):
        raise IntegrityError('noncanonical artifact name')
    return name


def validate_manifest(manifest):
    if (manifest.get('schema_version'), manifest.get('repo_id'), manifest.get('revision'),
            manifest.get('artifact_count'), manifest.get('total_bytes'),
            manifest.get('weight_count'), manifest.get('weight_bytes')) != (
            1, REPO_ID, REV, 81, TOTAL, 66, 30866866928):
        raise IntegrityError('manifest identity/totals mismatch')
    rows = manifest['artifacts']
    if len(rows) != 81:
        raise IntegrityError('manifest artifact count mismatch')
    seen = set()
    for row in rows:
        name = safe_name(row['path'])
        if name.endswith(('.partial', '.tmp', '.pending')):
            raise IntegrityError('reserved acquisition artifact name')
        if name in seen:
            raise IntegrityError('duplicate artifact')
        seen.add(name)
        if (type(row['size_bytes']) is not int or row['size_bytes'] < 0
                or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or row.get('revision') != REV or not row.get('role')):
            raise IntegrityError('invalid artifact size/hash/revision/role')
        if row['size_bytes'] == 0 and row['sha256'] != EMPTY_SHA256:
            raise IntegrityError('empty artifact SHA256 mismatch')
        if 'lfs_sha256' in row:
            if (row['lfs_sha256'] != row['sha256'] or 'git_blob_sha1' in row
                    or not re.fullmatch('[0-9a-f]{40}', row.get('lfs_pointer_git_blob_sha1', ''))
                    or row.get('metadata_identity') != 'lfs_sha256'):
                raise IntegrityError('LFS pointer/payload hash-domain mismatch')
        elif (not re.fullmatch('[0-9a-f]{40}', row.get('git_blob_sha1', ''))
                or 'lfs_pointer_git_blob_sha1' in row
                or row.get('metadata_identity') != 'git_blob_sha1'):
            raise IntegrityError('ordinary Git payload hash-domain mismatch')
    if (sum(row['size_bytes'] for row in rows) != TOTAL
            or sum(row['role'] == 'weight' for row in rows) != 66
            or sum(row['size_bytes'] for row in rows if row['role'] == 'weight') != 30866866928
            or sum('lfs_sha256' in row for row in rows) != 67
            or '.gitattributes' not in seen or 'safetensors-md5sum.txt' not in seen):
        raise IntegrityError('manifest exact byte/hash-domain totals mismatch')
    return rows


def compare_metadata(artifacts, metadata):
    if (metadata.get('id'), metadata.get('sha')) != (REPO_ID, REV):
        raise IntegrityError('pinned remote repository/revision mismatch')
    siblings = metadata['siblings']
    actual = {row['rfilename']: row for row in siblings}
    if len(actual) != len(siblings) or set(actual) != {row['path'] for row in artifacts}:
        raise IntegrityError('pinned remote complete artifact set mismatch')
    for expected in artifacts:
        row = actual[expected['path']]
        if row.get('size') != expected['size_bytes']:
            raise IntegrityError('pinned remote artifact size mismatch')
        if 'lfs_sha256' in expected:
            if ((row.get('lfs', {}).get('sha256'), row.get('lfs', {}).get('size'), row.get('blobId'))
                    != (expected['sha256'], expected['size_bytes'], expected['lfs_pointer_git_blob_sha1'])):
                raise IntegrityError('pinned remote LFS payload/pointer mismatch')
        elif row.get('lfs') or row.get('blobId') != expected['git_blob_sha1']:
            raise IntegrityError('pinned remote Git payload mismatch')


def validate_response(response, offset, size):
    if size <= 0 or offset < 0 or offset >= size:
        raise IntegrityError('invalid transfer bounds')
    if offset:
        if (response.status != 206 or response.headers.get('Content-Range')
                != f'bytes {offset}-{size-1}/{size}'):
            raise IntegrityError('resume Range response mismatch')
    elif response.status != 200 or response.headers.get('Content-Range'):
        raise IntegrityError('unexpected initial HTTP response')
    if response.headers.get('Content-Length') != str(size - offset):
        raise IntegrityError('HTTP content length mismatch')
    if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
        raise IntegrityError('encoded HTTP body refused')


def identity(value):
    return value.st_dev, value.st_ino


def file_proof(value):
    return dict(device=value.st_dev, inode=value.st_ino, size_bytes=value.st_size,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns,
                uid=value.st_uid, gid=value.st_gid,
                mode=stat.S_IMODE(value.st_mode), nlink=value.st_nlink)


class Anchor:
    """Open each absolute path component with O_NOFOLLOW, retain the final fd."""
    def __init__(self, path, device=None):
        self.path = Path(path)
        if not self.path.is_absolute() or '..' in self.path.parts:
            raise IntegrityError('absolute canonical anchor required')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.path.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            if device is not None and os.fstat(fd).st_dev != device:
                raise IntegrityError('anchor redirected to another filesystem')
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def verify(self):
        current = Anchor(self.path)
        try:
            if identity(os.fstat(current.fd)) != identity(os.fstat(self.fd)):
                raise IntegrityError('anchored directory changed or mount lost')
        finally:
            current.close()

    def entry(self, name):
        safe_name(name)
        try:
            value = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
                or value.st_dev != os.fstat(self.fd).st_dev):
            raise IntegrityError('artifact/state is not a single-link same-device regular file')
        return value

    def open_file(self, name, flags, mode=0o600):
        # State names may end in .tmp; generated temporary names use .pending.
        safe_name(name)
        self.verify()
        prior = self.entry(name)
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode, dir_fd=self.fd)
        try:
            value = os.fstat(fd)
            visible = self.entry(name)
            if (visible is None or identity(value) != identity(visible)
                    or (prior is not None and identity(value) != identity(prior))):
                raise IntegrityError('file identity changed during anchored open')
            return fd
        except BaseException:
            os.close(fd)
            raise


class Acquisition:
    def __init__(self, args):
        if args.run_dir != RUN or args.manifest_sha256 != MANIFEST_SHA256:
            raise IntegrityError('exact task run path and immutable manifest pin required')
        if args.workers not in (1, 2, 3):
            raise IntegrityError('workers must be bounded to 1 through 3')
        self.args = args
        self.cancel = threading.Event()
        self.mutex = threading.RLock()
        self.anchors = []
        self.lock_fd = None
        self.last_status = 0
        self.start = time.monotonic()
        self.transferred = 0
        self.storage_identity = storage.check(MODEL_UUID)
        self.data = self.anchor(DATA)
        self.models = self.anchor(MODELS)
        self.run = self.anchor(RUN, os.fstat(self.data.fd).st_dev)
        self.evidence = self.anchor(RUN / 'evidence', os.fstat(self.data.fd).st_dev)
        self.anchor(RUN / 'tmp', os.fstat(self.data.fd).st_dev)
        if args.manifest != SOURCE / 'reports/q38s-acquisition-manifest.json':
            raise IntegrityError('manifest must be the exact task-private staged source')
        source = self.anchor(args.manifest.parent, os.fstat(self.data.fd).st_dev)
        fd = source.open_file(args.manifest.name, os.O_RDONLY)
        with os.fdopen(fd, 'rb') as stream:
            payload = stream.read(1024 * 1024)
            if stream.read(1):
                raise IntegrityError('oversized manifest')
        if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
            raise IntegrityError('immutable source manifest SHA256 mismatch')
        self.manifest = json.loads(payload)
        self.artifacts = validate_manifest(self.manifest)
        self.dest = None
        self.state = dict(schema_version=1, status='STARTING', pid=os.getpid(),
            selection='qwen38-27b-fp8', repo_id=REPO_ID, revision=REV,
            destination=str(DEST), manifest_sha256=MANIFEST_SHA256,
            artifact_count=81, total_bytes=TOTAL, workers=args.workers,
            storage=self.storage_identity, files={}, started=stamp(),
            inference='NOT_TESTED', authentication='NOT_TESTED', tool_calls='NOT_TESTED')

    def anchor(self, path, device=None):
        result = Anchor(path, device)
        self.anchors.append(result)
        return result

    def close(self):
        for anchor in reversed(self.anchors):
            anchor.close()

    def cancelled(self):
        if self.cancel.is_set():
            raise Cancelled('acquisition cancelled')

    def guard(self, failure=False):
        current = storage.check(None if failure else MODEL_UUID)
        for anchor in self.anchors:
            if not failure or anchor.path == DATA or RUN == anchor.path or RUN in anchor.path.parents:
                anchor.verify()
        if self.lock_fd is not None:
            visible = self.run.entry('acquisition.lock')
            if visible is None or identity(visible) != identity(os.fstat(self.lock_fd)):
                raise IntegrityError('task lock was replaced')
        if not failure:
            free = os.fstatvfs(self.models.fd)
            if free.f_bavail * free.f_frsize < RESERVE + self.args.workers * CHUNK:
                raise IntegrityError('model disk below 20 GiB reserve plus write buffers')
        return current

    def atomic_json(self, name, value, failure=False):
        with self.mutex:
            self.guard(failure=failure)
            temporary = name + '.' + uuid.uuid4().hex + '.pending'
            self.evidence.entry(name)
            fd = self.evidence.open_file(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, indent=2, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
                written_proof = file_proof(os.fstat(stream.fileno()))
            self.guard(failure=failure)
            candidate = self.evidence.entry(temporary)
            if candidate is None or file_proof(candidate) != written_proof:
                raise IntegrityError('atomic state temporary identity changed')
            self.evidence.entry(name)
            os.replace(temporary, name, src_dir_fd=self.evidence.fd, dst_dir_fd=self.evidence.fd)
            os.fsync(self.evidence.fd)

    def status(self, force=False, failure=False):
        with self.mutex:
            now = time.monotonic()
            if not force and now - self.last_status < 15:
                return
            rows = self.state['files'].values()
            self.state.update(updated=stamp(), session_bytes_downloaded=self.transferred,
                session_average_bytes_per_second=int(self.transferred / max(1, now - self.start)),
                bytes_present=sum(row.get('bytes_present', 0) for row in rows),
                verified_bytes=sum(row.get('bytes_present', 0) for row in rows if row.get('verified')),
                verified_artifacts=sum(bool(row.get('verified')) for row in rows))
            self.atomic_json('acquisition-status.json', self.state, failure=failure)
            self.last_status = now

    def common_guards(self, phase):
        """Legacy guard report goes through an inherited anchored fd, never a pathname reopen.

        Registered guard supports stdout without a report; its own canonical
        registration checks are left intact. This wrapper does not override them.
        """
        self.guard()
        output = self.evidence.open_file('data-acquisition-' + phase + '.md',
            os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            subprocess.run([str(REPO / 'scripts/common/require-data-mounted.sh')],
                check=True, stdout=output, stderr=subprocess.STDOUT)
            os.fsync(output)
        finally:
            os.close(output)
        output = self.evidence.open_file('root-acquisition-' + phase + '.md',
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL)
        try:
            self.guard()
            command = [str(REPO / 'scripts/common/root-disk-guard.sh')]
            if not os.path.lexists('/etc/local-ai-server'):
                command += ['--report', '/proc/self/fd/' + str(output)]
            subprocess.run(command, check=True, stdout=output, stderr=subprocess.STDOUT,
                           pass_fds=(output,))
            os.fsync(output)
        finally:
            os.close(output)
        self.guard()

    @contextmanager
    def owner(self):
        self.guard()
        fd = self.run.open_file('acquisition.lock', os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd = fd
            yield
        finally:
            self.lock_fd = None
            os.close(fd)

    def prepare_destination(self, dry_run=False):
        self.guard()
        try:
            value = os.stat(DEST.name, dir_fd=self.models.fd, follow_symlinks=False)
        except FileNotFoundError:
            value = None
        if value is not None and (not stat.S_ISDIR(value.st_mode)
                or value.st_dev != os.fstat(self.models.fd).st_dev
                or value.st_uid != os.geteuid() or value.st_mode & 0o022):
            raise IntegrityError('foreign or redirected model destination')
        if value is None and not dry_run:
            os.mkdir(DEST.name, 0o700, dir_fd=self.models.fd)
            os.fsync(self.models.fd)
        if value is not None or not dry_run:
            self.dest = self.anchor(DEST, os.fstat(self.models.fd).st_dev)
            marker = self.evidence.entry('destination-owner.json')
            expected = dict(manifest_sha256=MANIFEST_SHA256, destination=str(DEST),
                            device=os.fstat(self.dest.fd).st_dev, inode=os.fstat(self.dest.fd).st_ino)
            if marker:
                fd = self.evidence.open_file('destination-owner.json', os.O_RDONLY)
                with os.fdopen(fd) as stream:
                    if json.load(stream) != expected:
                        raise IntegrityError('destination ownership binding mismatch')
            elif os.listdir(self.dest.fd):
                raise IntegrityError('existing nonempty destination lacks task ownership proof')
            if marker is None and not dry_run:
                self.atomic_json('destination-owner.json', expected)
        allowed = {row['path'] + suffix for row in self.artifacts for suffix in ('', '.partial')}
        if self.dest and set(os.listdir(self.dest.fd)) - allowed:
            raise IntegrityError('unexpected foreign destination entry')
        remaining = 0
        for artifact in self.artifacts:
            final = self.dest.entry(artifact['path']) if self.dest else None
            partial = self.dest.entry(artifact['path'] + '.partial') if self.dest else None
            if final is not None and partial is not None:
                raise IntegrityError('ambiguous final plus partial')
            present = (final or partial).st_size if final or partial else 0
            if present > artifact['size_bytes'] or (final and present != artifact['size_bytes']):
                raise IntegrityError('oversize partial or incomplete final')
            remaining += artifact['size_bytes'] - present
            self.state['files'][artifact['path']] = dict(status='PENDING', bytes_present=present,
                                                        initial_bytes=present, verified=False)
        free = os.fstatvfs(self.models.fd)
        free_bytes = free.f_bavail * free.f_frsize
        if free_bytes < remaining + RESERVE + self.args.workers * CHUNK:
            raise IntegrityError('insufficient capacity for remaining artifacts and 20 GiB reserve')
        self.state['capacity'] = dict(model_free_bytes=free_bytes, remaining_bytes=remaining,
            reserve_bytes=RESERVE, write_buffer_bytes=self.args.workers * CHUNK)
        return self.state['capacity']

    def transfer(self, artifact, partial):
        size = artifact['size_bytes']
        row = self.state['files'][artifact['path']]
        # Exactly empty artifact is an ordinary safely-created file and is still
        # read/hash verified below. No HTTP request, especially no invalid Range.
        if size == 0:
            self.guard()
            fd = self.dest.open_file(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            os.fsync(fd)
            os.close(fd)
            return
        for attempt in range(12):
            self.cancelled()
            self.guard()
            prior = self.dest.entry(partial)
            offset = prior.st_size if prior else 0
            if offset == size:
                return
            if offset > size:
                raise IntegrityError('oversize partial')
            url = f'https://huggingface.co/{REPO_ID}/resolve/{REV}/{urllib.parse.quote(artifact["path"])}'
            headers = {'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
                    validate_response(response, offset, size)
                    self.guard()
                    flags = os.O_WRONLY | os.O_APPEND
                    if prior is None:
                        flags |= os.O_CREAT | os.O_EXCL
                    fd = self.dest.open_file(partial, flags)
                    try:
                        value = os.fstat(fd)
                        if value.st_size != offset or (prior and identity(prior) != identity(value)):
                            raise IntegrityError('partial identity/offset changed before resume')
                        with self.mutex:
                            row.update(status='DOWNLOADING', request_offset=offset,
                                response_status=response.status,
                                content_range=response.headers.get('Content-Range'), attempt=attempt + 1)
                            self.status(True)
                        while True:
                            self.cancelled()
                            block = response.read(min(CHUNK, size - offset + 1))
                            if not block:
                                break
                            if offset + len(block) > size:
                                raise IntegrityError('HTTP body exceeds expected size')
                            self.guard()
                            self.cancelled()
                            visible = self.dest.entry(partial)
                            current = os.fstat(fd)
                            if (visible is None or identity(current) != identity(visible)
                                    or current.st_size != offset or current.st_nlink != 1):
                                raise IntegrityError('partial changed during transfer')
                            written = os.write(fd, block)
                            offset += written
                            with self.mutex:
                                self.transferred += written
                                row['bytes_present'] = offset
                                self.status()
                            if written != len(block):
                                raise OSError('short artifact write')
                    finally:
                        os.fsync(fd)
                        os.close(fd)
                if offset != size:
                    raise OSError('incomplete HTTP body')
                return
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # Never include exception strings, URLs, headers, or body text.
                with self.mutex:
                    row['last_transfer_error_type'] = type(exc).__name__
                    self.status(True)
                if attempt == 11:
                    raise RuntimeError('bounded download retry limit') from None
                if self.cancel.wait(min(2**attempt, 30)):
                    raise Cancelled('acquisition cancelled')

    def verify_artifact(self, artifact, name):
        self.guard()
        fd = self.dest.open_file(name, os.O_RDONLY)
        sha256 = hashlib.sha256()
        git = hashlib.sha1() if 'git_blob_sha1' in artifact else None
        if git is not None:
            git.update(f'blob {artifact["size_bytes"]}\0'.encode())
        try:
            before = file_proof(os.fstat(fd))
            if before['size_bytes'] != artifact['size_bytes']:
                raise IntegrityError('artifact size mismatch')
            while True:
                self.cancelled()
                block = os.read(fd, CHUNK)
                if not block:
                    break
                self.guard()
                sha256.update(block)
                if git is not None:
                    git.update(block)
            computed = sha256.hexdigest()
            if computed != artifact['sha256']:
                raise IntegrityError('computed SHA256 mismatch; artifact preserved')
            if git is not None and git.hexdigest() != artifact['git_blob_sha1']:
                raise IntegrityError('computed Git payload identity mismatch; artifact preserved')
            after = self.dest.entry(name)
            if after is None or before != file_proof(os.fstat(fd)) or before != file_proof(after):
                raise IntegrityError('artifact changed during hash verification')
            os.fsync(fd)
            return computed, git.hexdigest() if git is not None else None, before
        finally:
            os.close(fd)

    def one(self, artifact):
        name = artifact['path']
        partial = name + '.partial'
        row = self.state['files'][name]
        self.cancelled()
        if self.dest.entry(name) is None:
            prior = self.dest.entry(partial)
            if prior is None or prior.st_size != artifact['size_bytes']:
                self.transfer(artifact, partial)
            target = partial
        else:
            target = name
        with self.mutex:
            row['status'] = 'HASHING'
            self.status(True)
        computed, git, proof = self.verify_artifact(artifact, target)
        if target == partial:
            self.cancelled()
            self.guard()
            if self.dest.entry(name) is not None or file_proof(self.dest.entry(partial)) != proof:
                raise IntegrityError('artifact changed before atomic promotion')
            # Destination directory is task-private and the process holds its
            # sole task lease. Rename preserves inode and never truncates partials.
            os.rename(partial, name, src_dir_fd=self.dest.fd, dst_dir_fd=self.dest.fd)
            os.fsync(self.dest.fd)
            new = self.dest.entry(name)
            if (new.st_dev, new.st_ino, new.st_size, new.st_mtime_ns) != (
                    proof['device'], proof['inode'], proof['size_bytes'], proof['mtime_ns']):
                raise IntegrityError('promoted artifact identity mismatch')
            proof = file_proof(new)
        with self.mutex:
            row.update(status='VERIFIED', verified=True, computed_sha256=computed,
                       bytes_present=artifact['size_bytes'], file_stat=proof)
            if git is not None:
                row['computed_git_blob_sha1'] = git
            self.status(True)

    def pinned_metadata(self):
        """Retry only transient transport failures; identity mismatches fail immediately."""
        url = f'https://huggingface.co/api/models/{REPO_ID}/revision/{REV}?blobs=true'
        for attempt in range(4):
            self.cancelled()
            self.guard()
            self.state.update(status='VERIFYING_PINNED_METADATA', metadata_attempt=attempt + 1)
            self.status(True)
            try:
                with urllib.request.urlopen(url, timeout=45) as response:
                    if response.status != 200:
                        raise IntegrityError('unexpected metadata HTTP status')
                    payload = response.read(2 * 1024**2 + 1)
                    if len(payload) > 2 * 1024**2:
                        raise IntegrityError('oversized pinned metadata response')
                metadata = json.loads(payload)
                compare_metadata(self.artifacts, metadata)
                return metadata
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self.state['metadata_transfer_error_type'] = type(exc).__name__
                self.status(True)
                if attempt == 3:
                    raise RuntimeError('bounded pinned metadata retry limit') from None
                if self.cancel.wait(2**attempt):
                    raise Cancelled('acquisition cancelled')

    def acquire(self):
        if self.args.dry_run:
            capacity = self.prepare_destination(dry_run=True)
            print(json.dumps(dict(status='DRY_RUN_PASS', capacity=capacity,
                manifest_sha256=MANIFEST_SHA256, artifact_count=81, total_bytes=TOTAL,
                destination=str(DEST), run_dir=str(RUN)), sort_keys=True))
            return
        with self.owner():
            try:
                self.prepare_destination()
                self.state['status'] = 'GUARDED'
                self.status(True)
                self.common_guards('before-' + str(os.getpid()))
                metadata = self.pinned_metadata()
                # Record only public immutable identity fields, never response URLs.
                self.atomic_json('hf-pinned-metadata.json', dict(id=REPO_ID, sha=REV,
                    siblings=[{key: row[key] for key in ('rfilename', 'size', 'blobId', 'lfs') if key in row}
                              for row in metadata['siblings']]))
                self.state['status'] = 'DOWNLOADING'
                self.status(True)
                errors = []
                def worker(artifact):
                    try:
                        self.one(artifact)
                    except BaseException as exc:
                        self.cancel.set()
                        with self.mutex:
                            self.state['files'][artifact['path']].update(status='FAILED', error_type=type(exc).__name__)
                        raise
                with ThreadPoolExecutor(max_workers=self.args.workers, thread_name_prefix='q38a') as pool:
                    futures = [pool.submit(worker, artifact) for artifact in self.artifacts]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except BaseException as exc:
                            errors.append(exc)
                            self.cancel.set()
                if errors:
                    raise next((exc for exc in errors if not isinstance(exc, Cancelled)), errors[0])
                self.cancelled()
                self.guard()
                if set(os.listdir(self.dest.fd)) != {row['path'] for row in self.artifacts}:
                    raise IntegrityError('completed tree artifact set mismatch')
                records = []
                for artifact in self.artifacts:
                    row = self.state['files'][artifact['path']]
                    if not row.get('verified') or file_proof(self.dest.entry(artifact['path'])) != row['file_stat']:
                        raise IntegrityError('verified file metadata changed before completion')
                    records.append(dict(path=artifact['path'], size_bytes=artifact['size_bytes'],
                        computed_sha256=row['computed_sha256'], file_stat=row['file_stat']))
                self.common_guards('after-' + str(os.getpid()))
                for record in records:
                    present = self.dest.entry(record['path'])
                    if present is None or file_proof(present) != record['file_stat']:
                        raise IntegrityError('verified file changed during final common guards')
                self.state.update(status='COMPLETE_COMPUTED_SHA256', artifacts=records,
                                  completed=stamp(), seal='NOT_SEALED')
                self.status(True)
                self.atomic_json('acquisition-complete.json', self.state)
            except BaseException as exc:
                self.cancel.set()
                self.state.update(status='CANCELLED' if isinstance(exc, Cancelled) else 'STOP',
                                  error_type=type(exc).__name__)
                try:
                    self.status(True, failure=True)
                except Exception:
                    print('STOP: final status unavailable; prior evidence may be stale', file=sys.stderr)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=SOURCE / 'reports/q38s-acquisition-manifest.json')
    parser.add_argument('--manifest-sha256', default=MANIFEST_SHA256)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--dry-run', action='store_true', help='read-only guards, manifest, destination, and capacity check')
    args = parser.parse_args()
    job = None
    try:
        job = Acquisition(args)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda signum, frame: job.cancel.set())
        job.acquire()
        return 0
    except Exception as exc:
        print('STOP acquisition: ' + type(exc).__name__, file=sys.stderr)
        return 1
    finally:
        if job:
            job.close()


if __name__ == '__main__':
    sys.exit(main())
