#!/usr/bin/env python3
"""Fixed ai-vm Q38 seal probe: metadata/proof reads only; no payload byte reads.

Run only via Worker1 SSH as root, with the exact VM-GUARDS.json commands run by
the parent before/after the bounded phase. This probe independently verifies
their protected bytes; it does not run their report-writing behavior.

No installer, API, Docker, keys, lifecycle state, model writes, or new lock.
``with validate() as proof:`` retains acquisition lock and payload O_PATH FDs;
``proof.check()`` rechecks immediately around a caller's separately authorized,
canonical-lease/registered-anchored publication. The probe itself writes nothing.

Verification: python3 -B reports/l2vm-q38-check.py --help; compile(source, path,
'exec') on worker; exact Linux read-only run and review emitted safe JSON.
"""
import argparse
import contextlib
import datetime
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

MODEL = '/data/models-large/qwen38-27b-fp8'
EVIDENCE = '/data/models-large/.q38a-evidence-20260915'
RUN = '/data/build/q38a-20260915'
MANIFEST = '/data/services/q38a-20260915/repo/reports/q38s-acquisition-manifest.json'
MANIFEST_SHA = '726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2'
SEAL_SHA = 'a9b1ee9c80ca7030b79387b64f63d494159d0db7966f6510737e20c568584cfe'
COMPLETE_SHA = '970b026bbb8a4d500f1aee146c3ffaf51f64ca7d0eb3c3a24237e6a51c35f8c5'
RECEIPT_SHA = '2020e3d4b19a3d4a7221dfbf37a4f558ed98dcbd73e302b716ab95fb04e17dce'
REVISION = '017b9c7af6b5689d5dd426a76e0bc077eb5ca20a'
REPO_ID = 'Qwen/Qwen3.8-27B-FP8'
COUNT, TOTAL = 81, 30890049597
MOUNTS = {'/data': '8daf56f1-5649-4163-9d87-919c2d271875',
          '/data/models-large': 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'}
GUARD_ROOT = '/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915/scripts/common/'
GUARDS = {'require-data-mounted.sh': '5bd86b1e3f84fe5ca76922ca896289edb723b09bc03b99044b7d1ec320215c4f',
          'root-disk-guard.sh': '2f798c28d905fd819b00c550c0fd3cd7ebdac95ebb32f38876bce952dcbaf813'}
META_FIELDS = ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns', 'uid', 'gid', 'nlink', 'mode')
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Stop(RuntimeError):
    """Only static safe failure codes may be attached."""


def require(value, code):
    if not value:
        raise Stop(code)


def metadata(value):
    return {key: getattr(value, 'st_' + key) for key in META_FIELDS}


def same(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def command(*args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            check=True, timeout=30, text=True)
    require(len(result.stdout) <= 8 * 1024**2, 'command_output_too_large')
    return result.stdout


class Directory:
    """Retain every no-follow ancestor descriptor and recheck named identity."""
    def __init__(self, path, *, acquisition=False):
        self.path, self.chain, self.acquisition = Path(path), [], acquisition
        require(self.path.is_absolute() and '..' not in self.path.parts, 'unsafe_fixed_directory')
        try:
            fd = os.open('/', DIR_FLAGS)
            self.chain.append(('/', None, fd, metadata(os.fstat(fd))))
            current = Path('/')
            for name in self.path.parts[1:]:
                current /= name
                fd = os.open(name, DIR_FLAGS, dir_fd=fd)
                self.chain.append((str(current), name, fd, metadata(os.fstat(fd))))
            self.fd = fd
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        parent = None
        for path, name, fd, before in self.chain:
            info = os.fstat(fd)
            require(stat.S_ISDIR(info.st_mode), 'directory_type_changed')
            require((info.st_dev, info.st_ino) == (before['dev'], before['ino']), 'directory_identity_changed')
            if self.acquisition and path == '/data/build':
                require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) in
                        {(1000, 1001, 0o2775), (0, 1001, 0o2755)}, 'build_metadata_drift')
            elif self.acquisition and path == RUN:
                require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) ==
                        (1000, 1001, 0o2700), 'acquisition_owner_metadata_drift')
            else:
                require(info.st_uid == 0 and not info.st_mode & 0o022, 'unprotected_directory')
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                require(stat.S_ISDIR(named.st_mode) and
                        (named.st_dev, named.st_ino) == (info.st_dev, info.st_ino), 'directory_path_changed')
            parent = fd

    def file_stat(self, name, fd):
        self.check()
        value, named = os.fstat(fd), os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and
                same(metadata(value), metadata(named)), 'file_identity_changed')
        require(value.st_dev == os.fstat(self.fd).st_dev, 'file_crosses_mount')
        return value

    def open(self, name, *, metadata_only=False, lock=False):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name not in {'.', '..'}, 'unsafe_fixed_file')
        self.check()
        flags = (os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC if metadata_only else READ_FLAGS)
        if lock:
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        fd = os.open(name, flags, dir_fd=self.fd)
        try:
            self.file_stat(name, fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        for _path, _name, fd, _before in reversed(self.chain):
            os.close(fd)
        self.chain.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def protected_bytes(path, expected_sha, *, private=False, maximum=2 * 1024**2):
    path = Path(path)
    with Directory(path.parent) as parent:
        fd = parent.open(path.name)
        try:
            before = metadata(parent.file_stat(path.name, fd))
            require(before['uid'] == 0 and not before['mode'] & 0o022 and
                    (not private or stat.S_IMODE(before['mode']) == 0o600), 'unprotected_proof_file')
            require(0 < before['size'] <= maximum, 'proof_file_size_invalid')
            chunks, remaining = [], before['size'] + 1
            while remaining:
                block = os.read(fd, min(remaining, 1024**2))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            raw = b''.join(chunks)
            require(len(raw) == before['size'] and metadata(parent.file_stat(path.name, fd)) == before,
                    'proof_changed_during_read')
            require(hashlib.sha256(raw).hexdigest() == expected_sha, 'protected_proof_hash_mismatch')
            return raw, before
        finally:
            os.close(fd)


def mount_snapshot():
    require(shutil.disk_usage('/').free >= 4 * 1024**3, 'root_free_below_4_gib')
    with open('/proc/self/mountinfo', encoding='utf-8') as stream:
        raw = stream.read(4 * 1024**2 + 1)
    require(len(raw) <= 4 * 1024**2, 'mountinfo_too_large')
    entries = [line.split() for line in raw.splitlines()]
    rows = json.loads(command('findmnt', '--json', '--list', '-o',
                              'TARGET,SOURCE,UUID,FSTYPE,OPTIONS,FSROOT,MAJ:MIN'))['filesystems']
    block_rows = []
    def flatten(items):
        for item in items:
            block_rows.append(item)
            flatten(item.get('children', []))
    flatten(json.loads(command('lsblk', '--json', '--paths', '-o',
                              'NAME,TYPE,UUID,PKNAME,MAJ:MIN'))['blockdevices'])
    selected = {}
    for path, uuid in MOUNTS.items():
        matches = [row for row in rows if row.get('uuid') == uuid]
        require(len(matches) == 1, 'uuid_mount_alias')
        row = matches[0]
        require(row.get('target') == path and row.get('fstype') == 'ext4' and row.get('fsroot') == '/'
                and 'rw' in row.get('options', '').split(','), 'exact_whole_volume_mount_required')
        devices = {(item['name'], item.get('maj:min')) for item in block_rows if item.get('uuid') == uuid}
        require(len(devices) == 1 and next(iter(devices))[1] == row.get('maj:min'), 'uuid_device_alias')
        mounted = [entry for entry in entries if len(entry) > 9 and entry[2] == row['maj:min']]
        require(len(mounted) == 1 and mounted[0][3:5] == ['/', path], 'whole_volume_mount_alias')
        dev = os.stat(path).st_dev
        require(row['maj:min'] == str(os.major(dev)) + ':' + str(os.minor(dev)), 'mount_device_changed')
        selected[path] = mounted[0]
    require(len({os.stat(p).st_dev for p in ['/', *MOUNTS]}) == 3, 'storage_devices_not_distinct')
    for path in (MODEL, EVIDENCE, RUN, MANIFEST, GUARD_ROOT):
        covering = [entry for entry in entries if len(entry) > 9 and
                    (path == entry[4] or path.startswith(entry[4].rstrip('/') + '/'))]
        actual = max(covering, key=lambda entry: len(entry[4]))
        role = '/data/models-large' if path.startswith('/data/models-large/') else '/data'
        require(actual == selected[role], 'task_path_crosses_unregistered_mount')
        require(not any(entry[4].startswith(path.rstrip('/') + '/') for entry in entries
                        if len(entry) > 9), 'unexpected_task_submount')
    return selected


def inactive():
    raw = command('systemctl', 'show', 'q38a-weights-20260915-r2.service',
                  '--property=ActiveState', '--property=SubState', '--property=MainPID')
    value = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    require(value == {'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0'},
            'acquisition_unit_not_quiescent')


def open_writers(targets):
    """Bounded metadata-only /proc scan adapted from reviewed Q38A checker."""
    deadline = time.monotonic() + 30
    writers = mappings = unreadable = processes = descriptors = 0
    map_targets = {(os.major(dev), os.minor(dev), ino) for dev, ino in targets}
    for process in Path('/proc').iterdir():
        require(time.monotonic() < deadline, 'proc_scan_time_bound')
        if not process.name.isdigit():
            continue
        processes += 1
        require(processes <= 100000, 'proc_scan_process_bound')
        try:
            files = list((process / 'fd').iterdir())
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            unreadable += 1
            continue
        for descriptor in files:
            descriptors += 1
            require(descriptors <= 2000000 and time.monotonic() < deadline, 'proc_scan_descriptor_bound')
            try:
                value = descriptor.stat()
                if (value.st_dev, value.st_ino) not in targets:
                    continue
                with (process / 'fdinfo' / descriptor.name).open() as stream:
                    info = stream.read(65537)
                require(len(info) <= 65536, 'proc_fdinfo_too_large')
                flags = int(next(line.split()[1] for line in info.splitlines() if line.startswith('flags:')), 8)
                after = descriptor.stat()
                if (after.st_dev, after.st_ino) != (value.st_dev, value.st_ino):
                    continue
                if flags & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR):
                    writers += 1
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError:
                unreadable += 1
        try:
            size = 0
            with (process / 'maps').open() as stream:
                for line in stream:
                    size += len(line)
                    require(size <= 16 * 1024**2 and time.monotonic() < deadline, 'proc_maps_scan_bound')
                    fields = line.split(maxsplit=5)
                    if len(fields) < 5 or 'w' not in fields[1] or not fields[1].endswith('s'):
                        continue
                    major, minor = (int(part, 16) for part in fields[3].split(':'))
                    if (major, minor, int(fields[4])) in map_targets:
                        mappings += 1
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            unreadable += 1
    require(not writers and not mappings and not unreadable, 'payload_writer_or_unreadable_proc_entry')
    return {'writable_descriptors': writers, 'shared_writable_mappings': mappings,
            'unreadable_entries': unreadable, 'processes_observed': processes}


class Proof:
    def __init__(self, stack):
        require(os.geteuid() == 0 and sys.platform.startswith('linux') and hasattr(os, 'O_PATH'),
                'linux_root_required')
        self.mounts = mount_snapshot()
        self.guard_metadata = {}
        for name, digest in GUARDS.items():
            _raw, info = protected_bytes(GUARD_ROOT + name, digest)
            self.guard_metadata[name] = info
        manifest_raw, self.manifest_metadata = protected_bytes(MANIFEST, MANIFEST_SHA)
        self.manifest = json.loads(manifest_raw)
        self.evidence_directory = stack.enter_context(Directory(EVIDENCE))
        require(stat.S_IMODE(os.fstat(self.evidence_directory.fd).st_mode) == 0o700,
                'evidence_directory_not_private')
        self.evidence_metadata = metadata(os.fstat(self.evidence_directory.fd))
        self.seal_raw, self.seal_metadata = protected_bytes(EVIDENCE + '/sealed-evidence.json', SEAL_SHA, private=True)
        self.complete_raw, self.complete_metadata = protected_bytes(EVIDENCE + '/acquisition-complete.json', COMPLETE_SHA, private=True)
        self.seal, complete = json.loads(self.seal_raw), json.loads(self.complete_raw)
        header = {'schema_version': 1, 'status': 'COMPLETE_ROOT_REHASHED_AND_SEALED',
                  'model_id': 'qwen38-27b-fp8', 'repo_id': REPO_ID, 'revision': REVISION,
                  'destination': MODEL, 'manifest_sha256': MANIFEST_SHA,
                  'acquisition_complete_sha256': COMPLETE_SHA, 'artifact_count': COUNT, 'verified_bytes': TOTAL}
        require(all(same(self.seal.get(key), value) for key, value in header.items()), 'sealed_identity_mismatch')
        require(same(self.seal['expected_manifest'], self.manifest), 'sealed_expected_manifest_mismatch')
        expected = self.manifest['artifacts']
        names = [row['path'] for row in expected]
        require(len(names) == len(set(names)) == COUNT and sum(row['size_bytes'] for row in expected) == TOTAL,
                'pinned_manifest_count_mismatch')
        require('.gitattributes' in names and any(row['path'] == 'safetensors-md5sum.txt' and
                type(row['size_bytes']) is int and row['size_bytes'] == 0 for row in expected), 'required_artifact_missing')
        self.rows = {row['path']: row for row in self.seal['artifacts']}
        acquired = {row['path']: row for row in complete['artifacts']}
        require(len(self.seal['artifacts']) == len(complete['artifacts']) == COUNT and
                set(self.rows) == set(acquired) == set(names), 'proof_membership_mismatch')
        for row in expected:
            name = row['path']
            require(type(row['size_bytes']) is int and row['size_bytes'] >= 0 and
                    re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name not in {'.', '..'}, 'invalid_artifact_tuple')
            for proof in (self.rows[name], acquired[name]):
                require(same(proof['size_bytes'], row['size_bytes']) and proof['computed_sha256'] == row['sha256'],
                        'computed_artifact_tuple_mismatch')
        self.run = stack.enter_context(Directory(RUN, acquisition=True))
        self.lock_fd = self.run.open('acquisition.lock', lock=True)
        stack.callback(os.close, self.lock_fd)
        self.lock_metadata = metadata(self.run.file_stat('acquisition.lock', self.lock_fd))
        require((self.lock_metadata['uid'], self.lock_metadata['gid'], stat.S_IMODE(self.lock_metadata['mode']))
                == (1000, 1001, 0o600), 'acquisition_lock_owner_drift')
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('acquisition_lock_busy') from None
        inactive()
        self.model = stack.enter_context(Directory(MODEL))
        self.payloads = {}
        for name in names:
            fd = self.model.open(name, metadata_only=True)
            self.payloads[name] = fd
            stack.callback(os.close, fd)
        self.receipt = {'schema_version': 1, 'complete': True, 'repo_id': REPO_ID, 'revision': REVISION,
                        'model_root': MODEL, 'manifest_sha256': MANIFEST_SHA, 'artifact_count': COUNT,
                        'total_bytes': TOTAL, 'artifacts': [{'path': name, 'size_bytes': self.rows[name]['size_bytes'],
                        'sha256': self.rows[name]['computed_sha256'], 'verified': True} for name in sorted(names)]}
        raw = (json.dumps(self.receipt, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
        require(hashlib.sha256(raw).hexdigest() == RECEIPT_SHA, 'proposed_receipt_hash_mismatch')
        self.instance_addition = {'qwen38-27b-fp8': {'verified': True, 'revision': REVISION,
            'manifest_sha256': MANIFEST_SHA,
            'completion_manifest': '/data/services/llm-manager/acquisition/qwen38-27b-fp8.complete.json',
            'evidence': EVIDENCE + '/sealed-evidence.json'}}
        self.check()

    def check(self):
        require(mount_snapshot() == self.mounts, 'mount_identity_changed_during_proof')
        inactive()
        require(metadata(self.run.file_stat('acquisition.lock', self.lock_fd)) == self.lock_metadata,
                'acquisition_lock_replaced')
        self.evidence_directory.check()
        require(metadata(os.fstat(self.evidence_directory.fd)) == self.evidence_metadata, 'evidence_directory_changed')
        for path, digest, expected, private in (
            (MANIFEST, MANIFEST_SHA, self.manifest_metadata, False),
            (EVIDENCE + '/sealed-evidence.json', SEAL_SHA, self.seal_metadata, True),
            (EVIDENCE + '/acquisition-complete.json', COMPLETE_SHA, self.complete_metadata, True)):
            _raw, current = protected_bytes(path, digest, private=private)
            require(current == expected, 'protected_proof_identity_changed')
        for name, digest in GUARDS.items():
            _raw, current = protected_bytes(GUARD_ROOT + name, digest)
            require(current == self.guard_metadata[name], 'canonical_guard_identity_changed')
        self._check_payload_stats()
        targets = {(os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in self.payloads.values()}
        require(len(targets) == COUNT, 'payload_inode_alias')
        self.proc = open_writers(targets)
        self._check_payload_stats()
        require(mount_snapshot() == self.mounts, 'mount_identity_changed_after_proof')
        return self.summary()

    def _check_payload_stats(self):
        self.model.check()
        current = metadata(os.fstat(self.model.fd))
        require(current == self.seal['directory']['after'] and current['uid'] == current['gid'] == 0
                and stat.S_IMODE(current['mode']) == 0o555, 'sealed_directory_stat_drift')
        require(set(os.listdir(self.model.fd)) == set(self.payloads), 'sealed_tree_membership_drift')
        for name, fd in self.payloads.items():
            current = metadata(self.model.file_stat(name, fd))
            require(current == self.rows[name]['sealed_stat'] and current['uid'] == current['gid'] == 0
                    and stat.S_IMODE(current['mode']) == 0o444 and current['nlink'] == 1,
                    'sealed_payload_stat_drift')

    def summary(self):
        return {'status': 'PASS_PROTECTED_SEAL_CURRENT',
                'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'artifact_count': COUNT, 'verified_bytes_attested': TOTAL,
                'payload_bytes_read': 0, 'current_stat_matches': COUNT,
                'seal_sha256': SEAL_SHA, 'acquisition_complete_sha256': COMPLETE_SHA,
                'manifest_sha256': MANIFEST_SHA, 'proposed_receipt_sha256': RECEIPT_SHA,
                'canonical_guard_source_hashes': 'PASS', 'acquisition_lock': 'HELD_EXISTING_EXCLUSIVE',
                'acquisition_unit': 'inactive/dead/MainPID0', 'open_writers': self.proc,
                'root_free_bytes': shutil.disk_usage('/').free,
                'receipt_publication': 'NOT_PERFORMED_BY_THIS_PROBE',
                'authentication': 'NOT_ATTESTED', 'runtime': 'NOT_ATTESTED', 'readiness': 'NOT_ATTESTED'}


@contextlib.contextmanager
def validate():
    """Retain proof handles for a separately authorized publication transaction."""
    with contextlib.ExitStack() as stack:
        proof = Proof(stack)
        yield proof
        proof.check()


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = None
    try:
        with validate() as proof:
            result = proof.summary()
        result['acquisition_lock'] = 'HELD_THROUGH_FINAL_CHECK_THEN_RELEASED'
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, Stop) else type(error).__name__
        print(json.dumps({'status': 'STOP', 'code': code, 'payload_bytes_read': 0,
                          'receipt_publication': 'NOT_PERFORMED_BY_THIS_PROBE'}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
