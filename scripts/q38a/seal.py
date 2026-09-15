#!/usr/bin/env python3
"""Root-only Q38A payload seal; never publish lifecycle state or activate a model."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

REPO_ID = 'Qwen/Qwen3.8-27B-FP8'
REVISION = '017b9c7af6b5689d5dd426a76e0bc077eb5ca20a'
MANIFEST_SHA256 = '726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2'
TOTAL = 30890049597
COUNT = 81
RUN = Path('/data/build/q38a-20260915')
DEST = Path('/data/models-large/qwen38-27b-fp8')
EVIDENCE = Path('/data/models-large/.q38a-evidence-20260915')
UNIT = 'q38a-weights-20260915-r2.service'
DATA_UUID = '8daf56f1-5649-4163-9d87-919c2d271875'
MODEL_UUID = 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
CHUNK = 8 * 1024**2
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class SealError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise SealError(code)


def metadata(info):
    return {name: getattr(info, 'st_' + name) for name in
            ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns', 'uid', 'gid', 'nlink', 'mode')}


def acquisition_metadata(info):
    return dict(device=info.st_dev, inode=info.st_ino, size_bytes=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns,
                uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), nlink=info.st_nlink)


def identity(info):
    return info.st_dev, info.st_ino


def regular(info):
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'nonregular_or_hardlinked_file')


class Directory:
    """Retain and verify every ancestor FD; never follow a renamed path on write."""
    def __init__(self, path, guard=lambda: None):
        self.path, self.guard, self.chain = Path(path), guard, []
        require(self.path.is_absolute() and '..' not in self.path.parts, 'unsafe_directory_path')
        try:
            fd = os.open('/', DIR_FLAGS)
            self.chain.append((None, fd, identity(os.fstat(fd))))
            for component in self.path.parts[1:]:
                fd = os.open(component, DIR_FLAGS, dir_fd=fd)
                self.chain.append((component, fd, identity(os.fstat(fd))))
            self.fd = fd
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        self.guard()
        parent = None
        for name, fd, expected in self.chain:
            info = os.fstat(fd)
            require(stat.S_ISDIR(info.st_mode) and identity(info) == expected, 'directory_descriptor_changed')
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                require(stat.S_ISDIR(named.st_mode) and identity(named) == expected, 'directory_path_changed')
            parent = fd

    def close(self):
        for _name, fd, _expected in reversed(self.chain):
            os.close(fd)
        self.chain = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def open(self, name, flags=FILE_FLAGS, mode=0o600):
        require(isinstance(name, str) and name not in ('', '.', '..') and '/' not in name,
                'unsafe_relative_name')
        self.check()
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     mode, dir_fd=self.fd)
        try:
            self.file_check(name, fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def file_check(self, name, fd):
        self.check()
        info = os.fstat(fd)
        named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        regular(info)
        require(stat.S_ISREG(named.st_mode) and identity(info) == identity(named), 'file_path_changed')
        require(info.st_dev == os.fstat(self.fd).st_dev, 'file_crosses_mount')
        return info


def read_json(path, maximum=2 * 1024**2):
    path = Path(path)
    with Directory(path.parent) as parent:
        fd = parent.open(path.name)
        try:
            before = metadata(os.fstat(fd))
            require(before['size'] <= maximum, 'json_too_large')
            raw = os.read(fd, maximum + 1)
            require(len(raw) == before['size'] and metadata(parent.file_check(path.name, fd)) == before,
                    'json_changed_during_read')
            return json.loads(raw), raw
        finally:
            os.close(fd)


def validate_manifest(value, raw, expected_sha256=MANIFEST_SHA256):
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, 'manifest_sha256_mismatch')
    require(value.get('repo_id') == REPO_ID and value.get('revision') == REVISION,
            'manifest_identity_mismatch')
    rows = value.get('artifacts')
    require(isinstance(rows, list) and len(rows) == COUNT and value.get('artifact_count') == COUNT
            and value.get('total_bytes') == TOTAL, 'manifest_totals_mismatch')
    names = []
    for row in rows:
        name = row['path']
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', name)
                and name not in ('', '.', '..') and '/' not in name
                and not name.endswith('.partial'), 'unsafe_manifest_path')
        require(type(row['size_bytes']) is int and row['size_bytes'] >= 0
                and isinstance(row['sha256'], str) and len(row['sha256']) == 64
                and all(c in '0123456789abcdef' for c in row['sha256']), 'invalid_manifest_artifact')
        names.append(name)
    require(len(set(names)) == COUNT and sum(row['size_bytes'] for row in rows) == TOTAL,
            'manifest_artifacts_mismatch')
    return rows


class MountGuard:
    """Task-fixed UUIDs plus mount-ID continuity; no registry adoption or overrides."""
    def __init__(self):
        self.expected = {}
        for path, uuid in (('/data', DATA_UUID), ('/data/models-large', MODEL_UUID)):
            with Directory(path):
                pass
            response = subprocess.run(['findmnt', '--json', '-M', path, '-o', 'TARGET,UUID,FSTYPE,OPTIONS'],
                                      capture_output=True, text=True, check=True)
            rows = json.loads(response.stdout)['filesystems']
            require(len(rows) == 1 and rows[0].get('target') == path and rows[0].get('uuid') == uuid
                    and rows[0].get('fstype') == 'ext4' and 'rw' in rows[0].get('options', '').split(','),
                    'exact_mount_uuid_required')
            self.expected[path] = self.mount_entry(path)
        devices = [os.stat(path).st_dev for path in ('/', '/data', '/data/models-large')]
        require(len(set(devices)) == 3, 'storage_devices_must_be_distinct')
        self()

    @staticmethod
    def mount_entries():
        with open('/proc/self/mountinfo', 'r', encoding='utf-8') as stream:
            raw = stream.read(4 * 1024**2 + 1)
        require(len(raw) <= 4 * 1024**2, 'mountinfo_too_large')
        return [tuple(line.split()) for line in raw.splitlines()]

    @classmethod
    def mount_entry(cls, path):
        matches = [row for row in cls.mount_entries() if len(row) > 6 and row[4] == path]
        require(len(matches) == 1, 'missing_or_ambiguous_mount')
        return matches[0]

    def __call__(self):
        require(shutil.disk_usage('/').free >= 4 * 1024**3, 'root_free_below_4_gib')
        for path, expected in self.expected.items():
            require(self.mount_entry(path) == expected, 'mount_identity_changed')
        entries = self.mount_entries()
        for row in entries:
            require(len(row) > 6, 'invalid_mountinfo')
            for path in (str(DEST), str(EVIDENCE), str(RUN)):
                require(row[4] != path and not row[4].startswith(path + '/'), 'unexpected_task_mount')
        for path in (DEST, EVIDENCE, RUN, RUN / 'evidence'):
            for part in [*reversed(path.parents), path]:
                if not str(part).startswith('/data/') and str(part) != '/data':
                    continue
                role = '/data/models-large' if (str(part) == '/data/models-large'
                         or str(part).startswith('/data/models-large/')) else '/data'
                matches = [row for row in entries if str(part) == row[4]
                           or str(part).startswith(row[4].rstrip('/') + '/')]
                longest = max(len(row[4]) for row in matches)
                covering = [row for row in matches if len(row[4]) == longest]
                require(covering == [self.expected[role]], 'task_path_crosses_unexpected_mount')


def hash_file(parent, name, fd):
    before = metadata(parent.file_check(name, fd))
    sha256, git_sha1 = hashlib.sha256(), hashlib.sha1()
    git_sha1.update(b'blob ' + str(before['size']).encode() + b'\0')
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        parent.check()
        chunk = os.read(fd, CHUNK)
        if not chunk:
            break
        sha256.update(chunk)
        git_sha1.update(chunk)
    require(metadata(parent.file_check(name, fd)) == before, 'artifact_changed_during_hash')
    return sha256.hexdigest(), git_sha1.hexdigest(), before


def atomic_evidence(directory, value, *, trusted_uid=0):
    """Only task-private root evidence, never the lifecycle acquisition directory."""
    target, temporary = 'sealed-evidence.json', '.sealed-evidence.pending'
    directory.check()
    require(os.fstat(directory.fd).st_uid == trusted_uid and stat.S_IMODE(os.fstat(directory.fd).st_mode) == 0o700,
            'unprotected_evidence_directory')
    try:
        os.stat(target, dir_fd=directory.fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise SealError('sealed_evidence_already_exists')
    fd = directory.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
        written = 0
        while written < len(raw):
            directory.file_check(temporary, fd)
            written += os.write(fd, raw[written:written + CHUNK])
        os.fsync(fd)
        directory.file_check(temporary, fd)
        require(os.fstat(fd).st_uid == trusted_uid and stat.S_IMODE(os.fstat(fd).st_mode) == 0o600,
                'unprotected_evidence_file')
        os.rename(temporary, target, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
        os.fsync(directory.fd)
        directory.file_check(target, fd)
    finally:
        os.close(fd)
    return hashlib.sha256(raw).hexdigest()


def validate_completion(complete, artifacts):
    expected = {'schema_version': 1, 'status': 'COMPLETE_COMPUTED_SHA256',
                'selection': 'qwen38-27b-fp8', 'repo_id': REPO_ID, 'revision': REVISION,
                'destination': str(DEST), 'manifest_sha256': MANIFEST_SHA256,
                'artifact_count': COUNT, 'total_bytes': TOTAL, 'verified_bytes': TOTAL}
    require(all(complete.get(key) == value and type(complete.get(key)) is type(value)
                for key, value in expected.items()), 'acquisition_completion_identity_mismatch')
    rows = complete.get('artifacts')
    require(isinstance(rows, list) and len(rows) == COUNT, 'acquisition_completion_count_mismatch')
    by_name = {row['path']: row for row in rows}
    require(len(by_name) == COUNT and set(by_name) == {row['path'] for row in artifacts},
            'acquisition_completion_paths_mismatch')
    for artifact in artifacts:
        row = by_name[artifact['path']]
        require(row.get('size_bytes') == artifact['size_bytes']
                and row.get('computed_sha256') == artifact['sha256']
                and isinstance(row.get('file_stat'), dict), 'acquisition_completion_hash_mismatch')
    return by_name


def require_inactive_unit():
    result = subprocess.run(['systemctl', 'show', UNIT, '--property=ActiveState',
                             '--property=SubState', '--property=MainPID'],
                            capture_output=True, text=True, check=True)
    value = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require(value == {'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0'},
            'acquisition_unit_must_be_inactive')


@contextlib.contextmanager
def acquisition_lock(run, guard):
    with Directory(run, guard) as directory:
        fd = directory.open('acquisition.lock', os.O_RDWR)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SealError('acquisition_lock_busy') from None
            directory.file_check('acquisition.lock', fd)
            yield lambda: directory.file_check('acquisition.lock', fd)
        finally:
            os.close(fd)


def verify_tree(parent, artifacts, completed_rows, *, rehash, check_lock):
    """Keep all payload FDs open through sealing and proof publication."""
    expected_names = {row['path'] for row in artifacts}
    require(set(os.listdir(parent.fd)) == expected_names, 'unexpected_missing_or_partial_payload')
    opened, proofs = {}, []
    try:
        for artifact in artifacts:
            check_lock()
            name = artifact['path']
            fd = parent.open(name)
            opened[name] = fd
            before = parent.file_check(name, fd)
            require(before.st_size == artifact['size_bytes'], 'payload_size_mismatch')
            require(acquisition_metadata(before) == completed_rows[name]['file_stat'],
                    'payload_metadata_changed_since_acquisition')
            proof = dict(path=name, size_bytes=before.st_size, pre_seal=metadata(before))
            if rehash:
                computed, git_sha1, baseline = hash_file(parent, name, fd)
                require(computed == artifact['sha256'], 'root_payload_sha256_mismatch')
                if 'git_blob_sha1' in artifact:
                    require(git_sha1 == artifact['git_blob_sha1'], 'root_git_payload_sha1_mismatch')
                if 'lfs_sha256' in artifact:
                    require(computed == artifact['lfs_sha256'], 'root_lfs_payload_sha256_mismatch')
                proof.update(computed_sha256=computed, pre_seal=baseline)
                if 'git_blob_sha1' in artifact:
                    proof['computed_git_blob_sha1'] = git_sha1
                if 'lfs_pointer_git_blob_sha1' in artifact:
                    proof['lfs_pointer_git_blob_sha1'] = artifact['lfs_pointer_git_blob_sha1']
            proofs.append(proof)
        require(len({identity(os.fstat(fd)) for fd in opened.values()}) == len(artifacts),
                'payload_inode_alias')
        require(set(os.listdir(parent.fd)) == expected_names, 'payload_set_changed')
        return opened, proofs
    except BaseException:
        for fd in opened.values():
            os.close(fd)
        raise


def seal_tree(parent, opened, proofs, *, check_lock, trusted_uid=0):
    """The uid seam is in-process test-only; production always uses root."""
    before_directory = metadata(os.fstat(parent.fd))
    for proof in proofs:
        name, before = proof['path'], proof['pre_seal']
        fd = opened[name]
        check_lock()
        require(metadata(parent.file_check(name, fd)) == before, 'payload_changed_before_seal')
        os.fchown(fd, trusted_uid, 0 if trusted_uid == 0 else os.getgid())
        os.fchmod(fd, 0o444)
        os.fsync(fd)
        after = metadata(parent.file_check(name, fd))
        require(all(after[key] == before[key] for key in ('dev', 'ino', 'size', 'mtime_ns', 'nlink')),
                'payload_identity_changed_during_seal')
        require(after['uid'] == trusted_uid and stat.S_IMODE(after['mode']) == 0o444,
                'payload_seal_failed')
        proof['sealed_stat'] = after
    require(set(os.listdir(parent.fd)) == set(opened), 'payload_set_changed_before_directory_seal')
    check_lock()
    parent.check()
    os.fchown(parent.fd, trusted_uid, 0 if trusted_uid == 0 else os.getgid())
    os.fchmod(parent.fd, 0o555)
    os.fsync(parent.fd)
    parent.check()
    after_directory = metadata(os.fstat(parent.fd))
    require(after_directory['uid'] == trusted_uid and stat.S_IMODE(after_directory['mode']) == 0o555,
            'payload_directory_seal_failed')
    require(all(after_directory[key] == before_directory[key] for key in ('dev', 'ino', 'mtime_ns')),
            'payload_directory_changed_during_seal')
    for proof in proofs:
        require(metadata(parent.file_check(proof['path'], opened[proof['path']])) == proof['sealed_stat'],
                'sealed_payload_changed')
    return dict(before=before_directory, after=after_directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Operator prerequisite: acquisition unit inactive and no writable open payload descriptors. '
        'Dry-run validates guards, lock, completion and file metadata; apply rereads every payload byte. '
        'The source must be root-owned and protected before invoking as root. '
        'No lifecycle receipt, registry, deployment instance, service or runtime is changed.'))
    parser.add_argument('--dry-run', action='store_true', help='Read-only seal readiness; no hash/seal/evidence write')
    args = parser.parse_args(argv)
    require(os.geteuid() == 0, 'root_required')
    guard = MountGuard()
    manifest_path = Path(__file__).resolve().parents[2] / 'reports/q38s-acquisition-manifest.json'
    manifest, manifest_raw = read_json(manifest_path)
    artifacts = validate_manifest(manifest, manifest_raw)
    with acquisition_lock(RUN, guard) as check_lock:
        require_inactive_unit()
        complete, complete_raw = read_json(RUN / 'evidence/acquisition-complete.json')
        completed_rows = validate_completion(complete, artifacts)
        marker, _marker_raw = read_json(RUN / 'evidence/destination-owner.json')
        with Directory(DEST.parent, guard) as model_mount, Directory(DEST, guard) as model:
            mount_stat = os.fstat(model_mount.fd)
            require(mount_stat.st_uid == 0 and not (mount_stat.st_mode & 0o022),
                    'model_parent_must_be_protected')
            require(marker == dict(manifest_sha256=MANIFEST_SHA256, destination=str(DEST),
                                   device=os.fstat(model.fd).st_dev, inode=os.fstat(model.fd).st_ino),
                    'task_destination_marker_mismatch')
            try:
                existing_evidence = os.stat(EVIDENCE.name, dir_fd=model_mount.fd, follow_symlinks=False)
            except FileNotFoundError:
                existing_evidence = None
            if existing_evidence is not None:
                require(stat.S_ISDIR(existing_evidence.st_mode) and existing_evidence.st_uid == 0
                        and stat.S_IMODE(existing_evidence.st_mode) == 0o700,
                        'unprotected_existing_evidence_directory')
                with Directory(EVIDENCE, guard) as existing:
                    require(not set(os.listdir(existing.fd)) & {'sealed-evidence.json', '.sealed-evidence.pending'},
                            'existing_seal_evidence_requires_review')
            opened, proofs = verify_tree(model, artifacts, completed_rows,
                                         rehash=not args.dry_run, check_lock=check_lock)
            try:
                if args.dry_run:
                    print(json.dumps(dict(status='PASS_SEAL_DRY_RUN', artifact_count=COUNT,
                        total_bytes=TOTAL, hashes='NOT_REREAD_DRY_RUN', destination=str(DEST),
                        evidence_path=str(EVIDENCE / 'sealed-evidence.json'))))
                    return 0
                directory_proof = seal_tree(model, opened, proofs, check_lock=check_lock)
                check_lock()
                model_mount.check()
                try:
                    os.mkdir(EVIDENCE.name, 0o700, dir_fd=model_mount.fd)
                    os.fsync(model_mount.fd)
                    created_evidence = True
                except FileExistsError:
                    created_evidence = False
                with Directory(EVIDENCE, guard) as evidence:
                    if created_evidence:
                        require(os.fstat(evidence.fd).st_uid == 0, 'unexpected_evidence_owner')
                        # The protected model mount is setgid; normalize only this newly-created task directory.
                        os.fchmod(evidence.fd, 0o700)
                        os.fsync(evidence.fd)
                    result = dict(schema_version=1, status='COMPLETE_ROOT_REHASHED_AND_SEALED',
                        model_id='qwen38-27b-fp8', repo_id=REPO_ID, revision=REVISION,
                        destination=str(DEST), manifest_sha256=MANIFEST_SHA256,
                        acquisition_complete_sha256=hashlib.sha256(complete_raw).hexdigest(),
                        storage={'data': {'path': '/data', 'uuid': DATA_UUID, 'mountinfo': guard.expected['/data']},
                                 'models': {'path': '/data/models-large', 'uuid': MODEL_UUID,
                                            'mountinfo': guard.expected['/data/models-large']},
                                 'root_free_bytes': shutil.disk_usage('/').free},
                        artifact_count=COUNT, verified_bytes=TOTAL, artifacts=proofs,
                        directory=directory_proof, sealed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        lifecycle_receipt='NOT_PUBLISHED_LIVE_DEPLOY_HANDOFF_REQUIRED',
                        inference='NOT_TESTED', authentication='NOT_TESTED', tool_calls='NOT_TESTED',
                        expected_manifest=manifest)
                    proof_hash = atomic_evidence(evidence, result)
                check_lock()
                require_inactive_unit()
                model.check()
                guard()
                print(json.dumps(dict(status=result['status'], artifact_count=COUNT,
                    verified_bytes=TOTAL, evidence_path=str(EVIDENCE / 'sealed-evidence.json'),
                    evidence_sha256=proof_hash, lifecycle_receipt=result['lifecycle_receipt'])))
            finally:
                for fd in opened.values():
                    os.close(fd)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (SealError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('STOP: ' + (str(error) if isinstance(error, SealError) else type(error).__name__), file=sys.stderr)
        raise SystemExit(1)
