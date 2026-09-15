#!/usr/bin/env python3
"""Outer ownership guardian for synthetic packages on approved disposable Ubuntu.

This module never installs packages. Production commands are hidden by two exact
read-only bind mounts while the outer process supervises disposable test children.
The caller must provide exact-identity scope cleanup; unresolved ownership leaves
the harmless mounts in place for VM teardown instead of exposing real apt again.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from validation.i2p.run import capability, validate_context


TARGETS = (Path('/usr/bin/apt-get'), Path('/usr/bin/dpkg'))
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
CONTEXT_KEYS = ('GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT', 'GITHUB_REPOSITORY',
                'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
                'I2P_DISPOSABLE_ACK', 'RUNNER_TEMP')
LOCKS = ('/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock',
         '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock')
# Only populated when exact scope cleanup is unknown. Keep descriptors alive and
# bindings harmless until the disposable VM is discarded. Never unlock a lease.
_PRESERVED = []


class GuardianError(RuntimeError):
    """Only constant, sanitized codes may be supplied."""
    def __init__(self, code):
        self.code = code if isinstance(code, str) and re.fullmatch(r'[a-z0-9_]{1,100}', code) else 'guardian_failure'
        super().__init__(self.code)


def _command(argv):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=15, env=ENV, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise GuardianError('guardian_command_failed') from None
    if result.returncode or len(result.stdout) > 65536 or len(result.stderr) > 65536:
        raise GuardianError('guardian_command_failed')
    return result.stdout.decode('utf-8', errors='strict')


def _json(path, value):
    path = Path(path)
    content = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    temporary = path.with_name(path.name + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)


def _private(path, *, directory=False):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise GuardianError('guardian_unsafe_path')
    for item in (path, *path.parents):
        info = item.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise GuardianError('guardian_unsafe_path')
        if item != path or directory:
            if not stat.S_ISDIR(info.st_mode):
                raise GuardianError('guardian_unsafe_path')
        elif not stat.S_ISREG(info.st_mode):
            raise GuardianError('guardian_unsafe_path')
    return path


def _snapshot_fd(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024 * 1024:
        raise GuardianError('guardian_unsafe_file')
    digest = hashlib.sha256()
    position = 0
    while position < info.st_size:
        block = os.pread(fd, min(1024 * 1024, info.st_size - position), position)
        if not block:
            raise GuardianError('guardian_file_changed')
        digest.update(block)
        position += len(block)
    after = os.fstat(fd)
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size',
              'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(info, field) != getattr(after, field) for field in fields):
        raise GuardianError('guardian_file_changed')
    return {**{field[3:]: getattr(info, field) for field in fields},
            'sha256': digest.hexdigest()}


def _open_original(path, *, writable=False):
    _private(path)
    flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC
    flags |= getattr(os, 'O_NOATIME', 0)
    fd = os.open(path, flags)
    try:
        snapshot = _snapshot_fd(fd)
        live = path.lstat()
        if (live.st_dev, live.st_ino) != (snapshot['dev'], snapshot['ino']):
            raise GuardianError('guardian_file_changed')
    except BaseException:
        os.close(fd)
        raise
    return fd, snapshot


def _mounts(text=None):
    if text is None:
        text = Path('/proc/self/mountinfo').read_text()
    rows = []
    for line in text.splitlines():
        left, separator, right = line.partition(' - ')
        values = left.split()
        if not separator or len(values) < 6 or len(right.split()) < 3:
            raise GuardianError('guardian_mountinfo_invalid')
        decode = lambda value: re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)
        rows.append({'mount_id': int(values[0]), 'parent_id': int(values[1]),
                     'device': values[2], 'root': decode(values[3]),
                     'target': decode(values[4]), 'options': sorted(values[5].split(',')),
                     'filesystem': right.split()[0]})
    return rows


def _target_mount(target):
    matches = [row for row in _mounts() if row['target'] == str(target)]
    if len(matches) > 1:
        raise GuardianError('guardian_stacked_mount_refused')
    return matches[0] if matches else None


def _assert_binding(row, *, readonly=True):
    current = _target_mount(Path(row['target']))
    info = Path(row['target']).lstat()
    if (current != row['mount'] or (info.st_dev, info.st_ino) !=
            (row['source']['dev'], row['source']['ino']) or
            (readonly and 'ro' not in current['options'])):
        raise GuardianError('guardian_binding_identity_changed')


def _no_package_activity(originals):
    identities = {(row['original']['dev'], row['original']['ino']) for row in originals}
    names = {'apt', 'apt-get', 'aptitude', 'dpkg', 'dpkg-deb', 'dpkg-preconfigure',
             'unattended-upgr', 'unattended-upgrade', 'apt.systemd.dai', 'packagekitd'}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            executable = (entry / 'exe').stat()
            comm = (entry / 'comm').read_text().strip()
        except FileNotFoundError:
            continue
        except (PermissionError, OSError):
            raise GuardianError('guardian_process_inventory_unknown') from None
        if (executable.st_dev, executable.st_ino) in identities or comm in names:
            raise GuardianError('guardian_package_activity_present')
    for unit in ('apt-daily.service', 'apt-daily-upgrade.service',
                 'unattended-upgrades.service', 'packagekit.service'):
        output = _command(['/usr/bin/systemctl', 'show', unit,
                           '--property=ActiveState', '--value'])
        if output.strip() not in {'inactive', 'failed', ''}:
            raise GuardianError('guardian_package_service_active')


def _guard(workdir):
    context = {key: os.environ.get(key, '') for key in CONTEXT_KEYS}
    validate_context(context)
    # Reuse the reviewed real runner/capability guard, without primitive reruns.
    capabilities = capability(Path(context['RUNNER_TEMP']))
    # cgroup.kill exists only in non-root cgroups (kernel cgroup-v2 docs).
    # Inspect an existing system manager subtree; never create/signal it. Actual
    # owned-cgroup kill semantics are exercised later through the shipped scope.
    if not any((Path('/sys/fs/cgroup') / name / 'cgroup.kill').is_file()
               for name in ('system.slice', 'user.slice', 'init.scope')):
        raise GuardianError('guardian_requires_cgroup_kill')
    capabilities['cgroup_kill_available'] = True
    workdir = _private(workdir, directory=True)
    namespace = workdir if workdir.parent == Path('/run') else workdir.parent
    if (namespace.parent != Path('/run') or
            not re.fullmatch(r'i2r-[0-9a-f]{32}', namespace.name) or
            (workdir != namespace and workdir.name != 'fixture')):
        raise GuardianError('guardian_requires_fresh_run_namespace')
    if stat.S_IMODE(workdir.stat().st_mode) != 0o700:
        raise GuardianError('guardian_requires_private_workdir')
    return capabilities


FAKE_PROGRAM = r'''#!/usr/bin/python3
"""Root-owned synthetic package fixture: no package mutation implementation."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

ROOT = Path(__ROOT__)
TOOL = __TOOL__

def private(path, directory=False):
    path = Path(path)
    if not path.is_absolute() or not path.is_relative_to(ROOT):
        raise ValueError('fixture_path_refused')
    for part in (path, *path.parents):
        info = part.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError('fixture_path_refused')
        if part != path or directory:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError('fixture_path_refused')
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError('fixture_path_refused')
        if part == ROOT:
            break
    return path

def read_json(path):
    private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_size > 4096:
            raise ValueError('fixture_control_too_large')
        return json.loads(os.read(fd, 4097))
    finally:
        os.close(fd)

def apt_mode(args):
    args = list(args)
    path_options = {'Dir::Etc::sourcelist', 'Dir::Etc::sourceparts', 'Dir::State::lists',
                    'Dir::Cache', 'Dir::Cache::archives', 'Dir::Log', 'Dir::Log::Terminal',
                    'Dir::Log::History'}
    fixed = {'DPkg::Lock::Timeout':'0', 'APT::Get::List-Cleanup':'false',
             'Acquire::Retries':'3', 'Acquire::https::Timeout':'30',
             'APT::Update::Error-Mode':'any', 'APT::Sandbox::User':'root'}
    while args and args[0] == '-o':
        if len(args) < 2 or '=' not in args[1]:
            raise ValueError('fixture_argv_refused')
        key, value = args[1].split('=', 1)
        if key in path_options:
            valid = value.startswith('/') and '\0' not in value
        elif key == 'DPkg::Options::':
            valid = value.startswith('--log=/') and '\0' not in value
        else:
            valid = key in fixed and value == fixed[key]
        if not valid:
            raise ValueError('fixture_argv_refused')
        del args[:2]
    if args == ['update']:
        return 'preparation'
    for prefix in (['-s', '--no-install-recommends', '--no-remove', 'install'],
                   ['--download-only', '--yes', '--no-install-recommends', '--no-remove', 'install']):
        if args == prefix + ['i2r-fixture=1.0']:
            return 'preparation'
    allowed_flags = {'--no-download', '--yes', '--no-install-recommends', '--no-remove'}
    while args and args[0] in allowed_flags:
        args.pop(0)
    if len(args) != 2 or args[0] != 'install':
        raise ValueError('fixture_argv_refused')
    modes = {'i2r-success=1':'success', 'i2r-fail=1':'fail',
             'i2r-descendant=1':'descendant', 'i2r-wait=1':'sleep'}
    if args[1] not in modes:
        raise ValueError('fixture_argv_refused')
    return modes[args[1]]

def control(value, selected):
    if not isinstance(value, dict) or set(value) - {'mode', 'duration'}:
        raise ValueError('fixture_control_refused')
    mode = value.get('mode', selected)
    duration = value.get('duration', 0.3)
    if mode != selected or isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError('fixture_control_refused')
    if not math.isfinite(duration) or not 0 <= duration <= 12:
        raise ValueError('fixture_control_refused')
    return mode, duration

def event(directory, stage):
    raw = Path('/proc/self/stat').read_text().split(') ', 1)[1].split()
    cgroup = Path('/proc/self/cgroup').read_text().strip()
    if len(cgroup) > 4096 or not cgroup.startswith('0::/'):
        raise ValueError('fixture_cgroup_refused')
    value = {'stage':stage, 'pid':os.getpid(), 'start_ticks':int(raw[19]),
             'ppid':os.getppid(), 'cgroup':cgroup}
    path = directory / 'events.jsonl'
    if path.exists() or path.is_symlink():
        private(path)
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_size > 128 * 1024:
            raise ValueError('fixture_events_too_large')
        os.write(fd, (json.dumps(value, sort_keys=True) + '\n').encode())
    finally:
        os.close(fd)

def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('fixture_disposable_root_required')
    args = sys.argv[1:]
    if TOOL == 'dpkg':
        if args == ['--audit']:
            value = read_json(ROOT / 'audit-state.json')
            if not isinstance(value, dict) or set(value) != {'dirty'} or type(value['dirty']) is not bool:
                raise ValueError('fixture_audit_control_refused')
            if value['dirty']:
                print('i2r-fixture synthetic dirty audit')
            return 0
        if args == ['--print-architecture']:
            print('amd64')
            return 0
        if args == ['--version']:
            print('I2R synthetic dpkg fixture version 1')
            return 0
        raise ValueError('fixture_readonly_dpkg_only')
    mode = apt_mode(args)
    directory = private(Path(os.environ['TMPDIR']).resolve(strict=True), directory=True)
    if mode == 'preparation':
        event(directory, 'preparation')
        print('I2R_FAKE_APT_PREPARATION_OK')
        return 0
    mode, duration = control(read_json(directory / 'control.json'), mode)
    event(directory, 'main_started')
    if mode == 'descendant':
        child = os.fork()
        if child:
            event(directory, 'main_exit')
            return 0
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        event(directory, 'descendant_started')
        time.sleep(duration)
        event(directory, 'descendant_exit')
        os._exit(0)
    if mode == 'sleep':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(duration)
    event(directory, 'main_exit')
    return 23 if mode == 'fail' else 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        print('I2R_FAKE_COMMAND_REFUSED', file=sys.stderr)
        raise SystemExit(97)
'''


def _fake_program(workdir, tool):
    if tool not in {'apt-get', 'dpkg'}:
        raise GuardianError('guardian_unknown_fake_tool')
    return FAKE_PROGRAM.replace('__ROOT__', repr(str(workdir))).replace('__TOOL__', repr(tool))


def assert_active_bindings(workdir):
    """Read-only precondition for integration helpers before invoking apt/dpkg."""
    validate_context({key: os.environ.get(key, '') for key in CONTEXT_KEYS})
    path = _private(Path(workdir) / 'fake-packages/bindings.json')
    if path.stat().st_size > 65536:
        raise GuardianError('guardian_bindings_evidence_invalid')
    value = json.loads(path.read_text())
    if value.get('state') != 'active' or [row['target'] for row in value['bindings']] != list(map(str, TARGETS)):
        raise GuardianError('guardian_bindings_not_active')
    for row in value['bindings']:
        _assert_binding(row)
    return True


@contextmanager
def fake_packages(workdir, *, cleanup):
    """Bind harmless package fixtures; outer parent survives test-child SIGKILL.

    cleanup() must return {'status':'PASS', ...} after proving every exact owned
    scope quiescent. This callback runs before unmount on normal and error exits.
    Unknown ownership preserves fake bindings and refuses restoration.
    """
    if not callable(cleanup):
        raise GuardianError('guardian_exact_cleanup_required')
    workdir = Path(workdir)
    capabilities = _guard(workdir)  # Before any creation, lock, or mount.
    fixture = workdir / 'fake-packages'
    fixture.mkdir(mode=0o700)  # Exclusive: stale fixture/mount state is refused.
    evidence_path = fixture / 'bindings.json'
    evidence = {'schema_version': 1, 'status': 'FAIL', 'state': 'preparing', 'capability': capabilities,
                'bindings': [], 'locks': [], 'cleanup': {'status': 'NOT_TESTED'},
                'proof_class': 'actual_systemd_synthetic_package'}
    originals, lock_fds, source_fds = [], [], []
    yielded = False
    saved_handlers = {}
    preserved = False
    try:
        for target in TARGETS:
            if _target_mount(target) is not None:
                raise GuardianError('guardian_preexisting_target_mount')
            fd, snapshot = _open_original(target)
            originals.append({'fd': fd, 'target': str(target), 'original': snapshot})
        _no_package_activity(originals)
        for name in LOCKS:
            path = Path(name)
            if not path.exists() and not path.is_symlink():
                if name in LOCKS[:2]:
                    raise GuardianError('guardian_required_package_lock_missing')
                evidence['locks'].append({'path': name, 'status': 'absent_not_created'})
                continue
            fd, snapshot = _open_original(path, writable=True)
            lock_fds.append((fd, snapshot, name))
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise GuardianError('guardian_package_database_busy') from None
            evidence['locks'].append({'path': name, 'status': 'held_without_write', 'original': snapshot})
        _no_package_activity(originals)
        _json(workdir / 'audit-state.json', {'dirty': False})
        for original in originals:
            target = Path(original['target'])
            source = fixture / target.name
            fd = os.open(source, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o500)
            try:
                os.write(fd, _fake_program(workdir, target.name).encode())
                os.fsync(fd)
            finally:
                os.close(fd)
            source_fd, source_snapshot = _open_original(source)
            source_fds.append(source_fd)
            if _target_mount(target) is not None or _snapshot_fd(original['fd']) != original['original']:
                raise GuardianError('guardian_original_changed_before_bind')
            try:
                _command(['/usr/bin/mount', '--bind', str(source), str(target)])
            finally:
                # A failed mount command may still have attached a mount. Adopt
                # it for cleanup only after proving the exact fresh source inode.
                mounted = _target_mount(target)
                if mounted is not None:
                    info = target.lstat()
                    if (info.st_dev, info.st_ino) != (source_snapshot['dev'], source_snapshot['ino']):
                        raise GuardianError('guardian_binding_identity_changed')
                    row = {'target': str(target), 'original': original['original'],
                           'source': source_snapshot, 'mount': mounted}
                    evidence['bindings'].append(row)
            _command(['/usr/bin/mount', '-o', 'remount,bind,ro', str(target)])
            if mounted is None:
                raise GuardianError('guardian_mount_not_attached')
            row['mount'] = _target_mount(target)
            _assert_binding(row)
        evidence['state'] = 'active'
        _json(evidence_path, evidence)
        # The outer guardian is not a deliberate SIGKILL target. Its bounded
        # SIGTERM/INT/deadline exits pass through exact scope cleanup first.
        def interrupted(signum, frame):
            raise GuardianError('guardian_interrupted_or_deadline')
        if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
            raise GuardianError('guardian_existing_alarm_refused')
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
            saved_handlers[number] = signal.signal(number, interrupted)
        signal.setitimer(signal.ITIMER_REAL, 600)
        yielded = True
        yield {'fixture_root': str(workdir), 'audit_path': str(workdir / 'audit-state.json'),
               'bindings_path': str(evidence_path), 'evidence': evidence}
    finally:
        if saved_handlers:
            signal.setitimer(signal.ITIMER_REAL, 0)
            # Do not interrupt teardown halfway through restoring two bindings.
            for number in saved_handlers:
                signal.signal(number, signal.SIG_IGN)
        try:
            if yielded:
                try:
                    result = cleanup()
                except BaseException:
                    result = {'status': 'FAIL', 'code': 'guardian_scope_cleanup_failed'}
                evidence['cleanup'] = result
                if not isinstance(result, dict) or result.get('status') != 'PASS':
                    preserved = True
                    raise GuardianError('guardian_scope_cleanup_unknown_bindings_preserved')
            for row in reversed(evidence['bindings']):
                _assert_binding(row, readonly=False)
                _command(['/usr/bin/umount', '--', row['target']])
                if _target_mount(Path(row['target'])) is not None:
                    raise GuardianError('guardian_unmount_not_complete')
            for row in originals:
                if _snapshot_fd(row['fd']) != row['original']:
                    raise GuardianError('guardian_underlying_original_changed')
                restored_fd, restored = _open_original(Path(row['target']))
                os.close(restored_fd)
                if restored != row['original']:
                    raise GuardianError('guardian_original_not_restored')
                row['restored'] = True
            for fd, snapshot, name in lock_fds:
                if _snapshot_fd(fd) != snapshot:
                    raise GuardianError('guardian_package_lock_file_changed')
            evidence['state'] = 'restored'
            evidence['originals_restored'] = all(row.get('restored') for row in originals)
            evidence['status'] = 'PASS'
            if not yielded:
                evidence['cleanup'] = {'status': 'PASS', 'code': 'no_test_children_started'}
        except BaseException:
            preserved = True
            evidence['state'] = 'cleanup_blocked_bindings_or_evidence_preserved'
            raise
        finally:
            if preserved:
                _PRESERVED.extend([row['fd'] for row in originals] + source_fds + [row[0] for row in lock_fds])
            else:
                for fd in [row['fd'] for row in originals] + source_fds + [row[0] for row in lock_fds]:
                    os.close(fd)  # Close-only; no LOCK_UN anywhere.
            _json(evidence_path, evidence)
            for number, handler in saved_handlers.items():
                signal.signal(number, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='show exact safety plan without mutation')
    args = parser.parse_args()
    if not args.dry_run:
        parser.error('guardian is called only by the bounded I2R outer orchestrator; use --dry-run')
    print(json.dumps({'targets': list(map(str, TARGETS)), 'binding': 'read-only',
                      'host': 'I2P-guarded ephemeral GitHub-hosted Ubuntu24.04 only',
                      'cleanup': 'exact scope quiescence, exact own mount IDs, retained original metadata/hash',
                      'real_package_mutation': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
