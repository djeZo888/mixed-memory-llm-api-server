"""One borrowable lifecycle lock for the installer, manager and future callers.

Import this module as ``common.lifecycle_lease`` with ``scripts`` on sys.path.
Only ``acquire_lease`` mints capabilities; a borrowed capability is validated
without reopening or reacquiring its lock. Descriptors are deliberately private.

``system_root`` and ``trusted_uid`` are explicit, in-process worker fixture
seams. Production uses the defaults, never command-line or environment roots.
The fixture root is the trust boundary; production walks from ``/`` itself.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import errno
import fcntl
import os
from pathlib import Path
import re
import stat


class LeaseError(Exception):
    """A safe diagnostic code, without paths, command output or credentials."""

    def __init__(self, code):
        self.code = code if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,100}", code) else "lease_failed"
        super().__init__(self.code)


class LeaseBusy(LeaseError):
    """Atomic nonblocking acquisition found the canonical lock already held."""

    def __init__(self):
        super().__init__("lifecycle_busy")


class LifecycleLease:
    """An active, same-process capability owned by its acquisition context.

    Callers may only pass the object onward or call ``validate()``. There is no
    public descriptor, release method or arbitrary-FD construction interface.
    """

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        raise LeaseError("lease_must_be_acquired")

    def validate(self) -> None:
        record = _active.get(self) if type(self) is LifecycleLease else None
        if record is None:
            raise LeaseError("lease_not_active")
        if record.pid != os.getpid():
            raise LeaseError("lease_wrong_process")
        try:
            info = os.fstat(record.fd)
        except OSError:
            raise LeaseError("lease_descriptor_closed") from None
        _check_file(info, record.trusted_uid)
        if _identity(info) != record.identity:
            raise LeaseError("lease_descriptor_changed")
        _check_canonical(record.root, record.trusted_uid, record.identity)


@dataclass(frozen=True)
class _Record:
    fd: int
    root: Path
    trusted_uid: int
    pid: int
    identity: tuple[int, int]


# Object identity in this private registry supplies mint provenance. Merely
# possessing a trusted inode or an arbitrary open descriptor supplies no lease.
_active: dict[LifecycleLease, _Record] = {}
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _identity(info):
    return info.st_dev, info.st_ino


def _root_args(system_root, trusted_uid):
    try:
        root = Path(system_root)
    except (TypeError, ValueError):
        raise LeaseError("unsafe_lease_root") from None
    if not root.is_absolute() or ".." in root.parts or type(trusted_uid) is not int or trusted_uid < 0:
        raise LeaseError("unsafe_lease_root")
    return root


def _check_directory(info, trusted_uid):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, trusted_uid}
            or info.st_mode & 0o022):
        raise LeaseError("untrusted_lock_directory")


def _check_file(info, trusted_uid):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != trusted_uid
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
        raise LeaseError("untrusted_lock_file")


@contextlib.contextmanager
def _lock_directory(root, trusted_uid, *, create):
    """Walk fixed components using trusted directory FDs, never mkdir parents."""
    descriptors = []
    try:
        fd = os.open(root, _DIRECTORY_FLAGS)
        descriptors.append(fd)
        _check_directory(os.fstat(fd), trusted_uid)
        for component in ("run", "llmctl"):
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            descriptors.append(child)
            info = os.fstat(child)
            _check_directory(info, trusted_uid)
            if component == "llmctl" and (info.st_uid != trusted_uid or stat.S_IMODE(info.st_mode) != 0o700):
                raise LeaseError("untrusted_lock_directory")
            named = os.stat(component, dir_fd=fd, follow_symlinks=False)
            if _identity(named) != _identity(info) or not stat.S_ISDIR(named.st_mode):
                raise LeaseError("lock_path_changed")
            fd = child
        yield fd
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _check_canonical(root, trusted_uid, identity):
    try:
        with _lock_directory(root, trusted_uid, create=False) as directory:
            info = os.stat("lifecycle.lock", dir_fd=directory, follow_symlinks=False)
            _check_file(info, trusted_uid)
            if _identity(info) != identity:
                raise LeaseError("lock_path_changed")
    except OSError:
        raise LeaseError("lock_path_changed") from None


def _close_owned(record):
    """Close only: an inherited watcher must retain the same locked description."""
    if record.pid != os.getpid():
        return
    try:
        info = os.fstat(record.fd)
    except OSError:
        return
    if _identity(info) != record.identity:
        return
    try:
        os.close(record.fd)
    except OSError:
        raise LeaseError("lease_release_failed") from None


@contextlib.contextmanager
def acquire_lease(*, blocking=True, system_root=Path("/"), trusted_uid=0):
    """Acquire the canonical exclusive lock, then yield a validated lease.

    Nonblocking contention raises LeaseBusy. The context closes its descriptor
    on success or error; it never unlocks an inherited watcher's description.
    Pass its lease to nested lifecycle operations instead of acquiring again.
    """
    root = _root_args(system_root, trusted_uid)
    if type(blocking) is not bool:
        raise LeaseError("invalid_lease_blocking_mode")
    fd = None
    record = None
    lease = None
    try:
        try:
            with _lock_directory(root, trusted_uid, create=True) as directory:
                fd = os.open("lifecycle.lock", os.O_CREAT | os.O_RDWR | _FILE_FLAGS,
                             0o600, dir_fd=directory)
                info = os.fstat(fd)
                _check_file(info, trusted_uid)
                record = _Record(fd, root, trusted_uid, os.getpid(), _identity(info))
                _check_canonical(root, trusted_uid, record.identity)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except OSError as exc:
                if not blocking and exc.errno in {errno.EAGAIN, errno.EACCES}:
                    raise LeaseBusy() from None
                raise
            _check_canonical(root, trusted_uid, record.identity)
            lease = object.__new__(LifecycleLease)
            _active[lease] = record
            lease.validate()
        except OSError:
            raise LeaseError("lease_acquisition_failed") from None
        yield lease
    finally:
        if lease is not None:
            _active.pop(lease, None)
        if record is not None:
            _close_owned(record)
        elif fd is not None:
            os.close(fd)


def transition_in_progress(*, system_root=Path("/"), trusted_uid=0) -> bool:
    """Observe the same canonical lock without creating paths or waiting.

    The result is a momentary observation, not authorization for any mutation.
    Missing lock returns false; unsafe existing directories/files fail closed.
    """
    root = _root_args(system_root, trusted_uid)
    fd = None
    locked = False
    try:
        try:
            with _lock_directory(root, trusted_uid, create=False) as directory:
                fd = os.open("lifecycle.lock", os.O_RDONLY | _FILE_FLAGS, dir_fd=directory)
                info = os.fstat(fd)
                _check_file(info, trusted_uid)
                identity = _identity(info)
                _check_canonical(root, trusted_uid, identity)
        except FileNotFoundError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            if exc.errno not in {errno.EAGAIN, errno.EACCES}:
                raise
        _check_canonical(root, trusted_uid, identity)
        return not locked
    except OSError:
        raise LeaseError("lease_observation_failed") from None
    finally:
        if fd is not None:
            os.close(fd)


def _validate_borrowed_lease(lease, *, system_root=Path("/"), trusted_uid=0):
    """Validate mint provenance and the borrowing Manager's expected lock scope."""
    root = _root_args(system_root, trusted_uid)
    if type(lease) is not LifecycleLease:
        raise LeaseError("invalid_borrowed_lease")
    lease.validate()
    record = _active[lease]
    if record.root != root or record.trusted_uid != trusted_uid:
        raise LeaseError("borrowed_lease_scope_mismatch")


def _export_package_watcher_fd(lease) -> int:
    """Transfer a same-description duplicate for I1R's subprocess pass_fds only.

    The caller owns this duplicate and MUST close it after watcher handoff or
    failure. It must never LOCK_UN. The private lease descriptor is not exported;
    closing/reusing the export cannot invalidate or counterfeit the active lease.
    Exported descriptors do not authorize Manager borrowing or mint a lease.
    """
    if type(lease) is not LifecycleLease:
        raise LeaseError("invalid_borrowed_lease")
    lease.validate()
    try:
        return os.dup(_active[lease].fd)
    except OSError:
        raise LeaseError("package_lease_export_failed") from None


def _after_fork_child():
    # flock ownership follows the open-file description across fork. Closing a
    # child's duplicate (never LOCK_UN) prevents it prolonging the parent's lock.
    for record in _active.values():
        try:
            if _identity(os.fstat(record.fd)) == record.identity:
                os.close(record.fd)
        except OSError:
            pass
    _active.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)
