#!/usr/bin/env python3
"""C1 four-tree helper. CLI is dry-run only; an approved runner owns apply gates.

apply_reviewed(root, reviewed, gate) requires the exact fresh reviewed tree
snapshot. gate(snapshot) must recheck canonical lease/idle ownership, installed
storage/root guards, UUIDs, acquisition/process/container non-use and approved
metadata/reference retirement, and return True. The caller retains ownership
through deletion and performs retained-backend/guard/catalog checks afterward.
This helper never stops a model, retires references, or removes a container.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

ALLOWLIST = {
    '/data/models/minimax-m3-mxfp8': '/data',
    '/data/models/qwen3-30b-a3b-instruct-2507': '/data',
    '/data/models/qwen3-0.6b-smoke': '/data',
    '/data/models-large/qwen3-coder-next-fp8': '/data/models-large',
}
OWNER_UID = 0
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class Refused(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Refused(reason)


def metadata(info):
    return {key: getattr(info, 'st_' + key) for key in
            ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size',
             'mtime_ns', 'ctime_ns', 'blocks')}


def protected_directory(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, OWNER_UID)
            and not info.st_mode & 0o022, 'unprotected_directory_ancestor')


def read_mounts():
    def decode(value):
        return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)
    rows = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        parts = line.split()
        split = parts.index('-')
        rows.append({'id': parts[0], 'parent': parts[1], 'device': parts[2],
                     'fsroot': decode(parts[3]), 'path': decode(parts[4]),
                     'fstype': parts[split + 1], 'source': decode(parts[split + 2])})
    return rows


def mount_identity(root):
    rows = read_mounts()
    require(not any(r['path'] == root or r['path'].startswith(root + '/')
                    for r in rows), 'target_or_nested_mount')
    candidates = [r for r in rows if root.startswith(r['path'].rstrip('/') + '/')]
    require(bool(candidates), 'mount_visibility_missing')
    deepest = max(len(r['path']) for r in candidates)
    selected = [r for r in candidates if len(r['path']) == deepest]
    require(len(selected) == 1, 'mount_identity_ambiguous')
    row = selected[0]
    require(row['path'] == ALLOWLIST[root] and row['fstype'] == 'ext4'
            and row['fsroot'] == '/', 'unexpected_mount')
    return row


@contextmanager
def opened_parent(root):
    require(type(root) is str and root in ALLOWLIST, 'target_not_allowlisted')
    require(os.geteuid() == OWNER_UID, 'privileged_visibility_required')
    require(shutil.rmtree.avoids_symlink_attacks, 'fd_safe_rmtree_unavailable')
    descriptors, edges = [], []
    try:
        fd = os.open('/', DIR_FLAGS)
        descriptors.append(fd)
        protected_directory(os.fstat(fd))
        for component in Path(root).parts[1:-1]:
            child = os.open(component, DIR_FLAGS, dir_fd=fd)
            descriptors.append(child)
            info = os.fstat(child)
            protected_directory(info)
            edges.append((fd, component, child, (info.st_dev, info.st_ino)))
            fd = child

        def recheck():
            for parent, name, child, identity in edges:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                opened = os.fstat(child)
                protected_directory(named)
                protected_directory(opened)
                require((named.st_dev, named.st_ino) == identity
                        == (opened.st_dev, opened.st_ino), 'ancestor_replaced')
        recheck()
        yield fd, Path(root).name, recheck
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def snapshot(parent, name, root):
    mount = mount_identity(root)
    root_info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    require(stat.S_ISDIR(root_info.st_mode), 'target_not_directory')
    seen, counts, digest = set(), {'directories': 0, 'files': 0,
                                  'allocated_bytes': 0, 'apparent_file_bytes': 0}, hashlib.sha256()

    def visit(directory, entry, relative):
        info = os.stat(entry, dir_fd=directory, follow_symlinks=False)
        require(info.st_dev == root_info.st_dev, 'descendant_device_changed')
        identity = (info.st_dev, info.st_ino)
        require(identity not in seen, 'duplicate_inode')
        seen.add(identity)
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),
                'link_or_special_entry')
        if stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1, 'hardlinked_file')
            counts['files'] += 1
            counts['apparent_file_bytes'] += info.st_size
        else:
            counts['directories'] += 1
        counts['allocated_bytes'] += info.st_blocks * 512
        digest.update(json.dumps([relative, metadata(info)], sort_keys=True).encode() + b'\n')
        if stat.S_ISDIR(info.st_mode):
            child = os.open(entry, DIR_FLAGS, dir_fd=directory)
            try:
                require(metadata(os.fstat(child)) == metadata(info), 'directory_open_drift')
                for sub in sorted(os.listdir(child)):
                    visit(child, sub, relative + '/' + sub)
                require(metadata(os.fstat(child)) == metadata(info), 'directory_scan_drift')
            finally:
                os.close(child)
        require(metadata(os.stat(entry, dir_fd=directory, follow_symlinks=False))
                == metadata(info), 'entry_scan_drift')

    visit(parent, name, '.')
    require(mount_identity(root) == mount, 'mount_scan_drift')
    require(metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
            == metadata(root_info), 'root_scan_drift')
    return {'root': root, 'root_identity': metadata(root_info), 'mount': mount,
            'tree_metadata_sha256': digest.hexdigest(), **counts}


def dry_run(root):
    with opened_parent(root) as (parent, name, recheck):
        result = snapshot(parent, name, root)
        recheck()
        return result


def apply_reviewed(root, reviewed, gate):
    require(callable(gate), 'approved_gate_required')
    with opened_parent(root) as (parent, name, recheck):
        before = snapshot(parent, name, root)
        require(before == reviewed, 'reviewed_snapshot_drift')
        require(gate(before) is True, 'current_use_or_ownership_gate_failed')
        # Gate may take time; repeat the complete snapshot immediately before rm.
        recheck()
        require(snapshot(parent, name, root) == reviewed, 'preapply_snapshot_drift')
        recheck()
        require(mount_identity(root) == reviewed['mount'], 'preapply_mount_drift')
        require(metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                == reviewed['root_identity'], 'preapply_root_drift')
        # Exceptions propagate: a mid-tree failure is partial, never success.
        shutil.rmtree(name, dir_fd=parent)
        os.fsync(parent)
        recheck()
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return {'root': root, 'absence_verified': True,
                    'removed_inventory_allocated_bytes': reviewed['allocated_bytes'],
                    'filesystem_free_delta': 'measure_separately_in_runner'}
        raise Refused('target_present_after_delete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, choices=tuple(ALLOWLIST))
    parser.add_argument('--dry-run', action='store_true', required=True,
                        help='tree identity/allocation only; no non-use clearance or deletion')
    args = parser.parse_args()
    try:
        result = dry_run(args.root)
    except (Refused, OSError, ValueError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, Refused) else 'inspection_failed'}))
        return 1
    print(json.dumps({'status': 'TREE_DRY_RUN_ONLY', 'non_use_clearance': False,
                      'snapshot': result}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
