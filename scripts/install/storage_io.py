"""Descriptor-anchored I/O for registered installer storage.

The caller supplies the existing trusted storage verifier and holds the shared
installer/lifecycle lease for its entire transaction. This module adds no lease.
Every path mutation uses held directory descriptors, so a detached mount cannot
redirect a write into the underlying root filesystem. GuardedFile bounds writes
to 1 MiB and checks both the verifier and descriptor ancestry around each chunk.
Subprocesses using fileno() must be monitored by their caller with check(); the
descriptor itself remains anchored even if a detach races that monitor.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid


MAX_CHUNK = 1024 * 1024
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class StorageIOError(RuntimeError):
    """Sanitized storage failure suitable for installer stage reporting."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _parts(relative):
    value = os.fspath(relative)
    if (not isinstance(value, str) or not value or value.startswith("/")
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or "\x00" in value):
        raise StorageIOError("unsafe_storage_relative_path")
    return value.split("/")


def _identity(info):
    return info.st_dev, info.st_ino


def _protected(info, uid, *, directory=False, ancestor=False, private=False):
    owners = {0, uid} if ancestor else {uid}
    if info.st_uid not in owners or info.st_mode & (0o077 if private else 0o022):
        raise StorageIOError("unprotected_storage_owner_or_mode")
    if directory:
        if not stat.S_ISDIR(info.st_mode) or info.st_nlink < 1:
            raise StorageIOError("invalid_storage_directory")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise StorageIOError("invalid_storage_file_or_hardlink")


def _registration_identity(snapshot):
    try:
        value = {"schema_version": snapshot["schema_version"], "roots": snapshot["roots"],
                 **{key: {field: snapshot[key][field] for field in ("path", "mount", "uuid", "fstype")}
                    for key in ("data", "models")}}
        if value["schema_version"] != 1 or not isinstance(value["roots"], dict):
            raise ValueError()
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError):
        raise StorageIOError("invalid_storage_guard_snapshot") from None


def _live_roles(snapshot):
    roles = snapshot.get("verified_roles", ("data", "models"))
    if (not isinstance(roles, (list, tuple)) or not roles
            or any(role not in {"data", "models"} for role in roles)):
        raise StorageIOError("invalid_storage_guard_roles")
    return tuple(role for role in ("data", "models") if role in roles)


def _path_role(snapshot, path):
    # Distinct model subtrees cannot be reclassified by a nested service root.
    model = snapshot["models"]["path"]
    if model != snapshot["data"]["path"] and (path == model or path.startswith(model + "/")):
        return "models"
    # More-specific declared service roots win when models share the data root.
    candidates = [(snapshot[role]["path"], role) for role in ("data", "models")]
    candidates += [(root, "models" if key == "models" else "data")
                   for key, root in snapshot["roots"].items()]
    matches = [(len(root), role) for root, role in candidates
               if path == root or path.startswith(root + "/")]
    if not matches:
        raise StorageIOError("storage_anchor_outside_registered_roots")
    return max(matches)[1]


def _absolute_path(path):
    value = os.fspath(path)
    if (not isinstance(value, str) or not value.startswith("/")
            or "\x00" in value or str(Path(value)) != value
            or ".." in Path(value).parts):
        raise StorageIOError("unsafe_storage_anchor_path")
    return value


class MountedStorageGuard:
    """Fast continuous guard after one full trusted Storage.guard() check.

    Keeps the fixed registration file and its protected ancestry open, compares
    its exact bytes, and reads Linux mountinfo on *every* call. Every managed
    root must still resolve to its captured exact mount ID/device/entry.
    check_path() additionally validates every component of an operation path;
    unrelated descendant mounts are allowed. There
    is no timer, cached success interval, shell command or environment override.
    Call verify_full() at stage boundaries for capacity and block-topology QA.

    mountinfo_reader is an explicit in-process fixture seam; production omits
    it and uses only /proc/self/mountinfo in the installer's mount namespace.
    """

    def __init__(self, storage, *, roles=("data", "models"), mountinfo_reader=None):
        self.roles = _live_roles({"verified_roles": roles})
        self.storage = storage
        self.uid = storage.owner
        self._read_mountinfo = mountinfo_reader or self._linux_mountinfo
        self._snapshot = copy.deepcopy(self._full_snapshot())
        self._registration = _registration_identity(self._snapshot)
        self._lineage, self._fd, self._closed = [], None, False
        self._lock = threading.RLock()
        # Storage.system_root is already an explicit in-process fixture seam.
        # The installed path remains fixed, with no argv or env override.
        path = Path(storage.system_root) / "etc/local-ai-server/storage.json"
        try:
            fd = os.open("/", _DIR_FLAGS)
            self._lineage.append((None, fd, _identity(os.fstat(fd))))
            for name in path.parts[1:-1]:
                fd = os.open(name, _DIR_FLAGS, dir_fd=fd)
                self._lineage.append((name, fd, _identity(os.fstat(fd))))
            self._name, self._parent = path.name, fd
            self._fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
            self._file_identity = _identity(os.fstat(self._fd))
            self._check_registry_path()
            self._registry_bytes = self._registry_content()
            if _registration_identity(json.loads(self._registry_bytes)) != self._registration:
                raise StorageIOError("registered_storage_identity_changed")
            entries = self._mounts()
            self._expected_mounts = self._required_mounts(entries)
            self._expected_role_mounts = self._role_mounts(entries)
            self()
        except BaseException:
            self.close()
            raise

    def _full_snapshot(self):
        snapshot = (self.storage.guard() if self.roles == ("data", "models")
                    else self.storage.guard(roles=self.roles))
        if _live_roles(snapshot) != self.roles:
            raise StorageIOError("storage_guard_roles_changed")
        return snapshot

    @staticmethod
    def _linux_mountinfo():
        try:
            with open("/proc/self/mountinfo", "rb") as stream:
                value = stream.read(8 * MAX_CHUNK + 1)
            if len(value) > 8 * MAX_CHUNK:
                raise StorageIOError("storage_mountinfo_too_large")
            return value.decode("utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            raise StorageIOError("storage_mountinfo_unavailable") from None

    @staticmethod
    def _decode_mount_path(value):
        # The kernel escapes these four characters in mountinfo path fields.
        decoded = re.sub(r"\\(040|011|012|134)", lambda match: chr(int(match[1], 8)), value)
        if not decoded.startswith("/"):
            raise StorageIOError("invalid_storage_mountinfo")
        return decoded

    def _mounts(self):
        try:
            lines = self._read_mountinfo().splitlines()
            entries = []
            for line in lines:
                fields = line.split()
                split = fields.index("-", 6)
                if len(fields) != split + 4 or not fields[0].isdigit() or not fields[1].isdigit():
                    raise ValueError()
                if not re.fullmatch(r"[0-9]+:[0-9]+", fields[2]):
                    raise ValueError()
                entries.append({"mount": self._decode_mount_path(fields[4]), "device": fields[2],
                                "fstype": fields[split + 1], "entry": tuple(fields)})
            if not entries:
                raise ValueError()
            return entries
        except (AttributeError, ValueError, IndexError):
            raise StorageIOError("invalid_storage_mountinfo") from None

    def _required_mounts(self, entries):
        result = {}
        paths = set(self._snapshot["roots"].values()) | {self._snapshot[key]["path"] for key in ("data", "models")}
        for path in sorted(paths):
            role = _path_role(self._snapshot, path)
            if role not in self.roles:
                continue
            expected = self._snapshot[role]
            result[path] = self._mount_entry(entries, path, expected)
        return result

    @staticmethod
    def _mount_entry(entries, path, expected):
        candidates = [entry for entry in entries
                      if entry["mount"] == "/" or path == entry["mount"] or path.startswith(entry["mount"] + "/")]
        if not candidates:
            raise StorageIOError("registered_storage_mount_lost")
        length = max(len(entry["mount"]) for entry in candidates)
        matches = [entry for entry in candidates if len(entry["mount"]) == length]
        if len(matches) != 1:
            raise StorageIOError("registered_storage_mount_ambiguous")
        current = matches[0]
        if any(current[field] != expected[field] for field in ("mount", "device", "fstype")):
            raise StorageIOError("registered_storage_mount_changed")
        return current["entry"]

    def _role_mounts(self, entries):
        return {role: self._mount_entry(entries, self._snapshot[role]["mount"], self._snapshot[role])
                for role in self.roles}

    def _check_registry_path(self):
        if self._closed:
            raise StorageIOError("storage_guard_closed")
        parent = None
        for name, fd, identity in self._lineage:
            info = os.fstat(fd)
            _protected(info, self.uid, directory=True, ancestor=True)
            if _identity(info) != identity:
                raise StorageIOError("registered_storage_path_changed")
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if _identity(named) != identity or not stat.S_ISDIR(named.st_mode):
                    raise StorageIOError("registered_storage_path_changed")
            parent = fd
        parent_info = os.fstat(self._parent)
        _protected(parent_info, self.uid, directory=True, private=True)
        info = os.fstat(self._fd)
        _protected(info, self.uid, private=True)
        named = os.stat(self._name, dir_fd=self._parent, follow_symlinks=False)
        if _identity(info) != self._file_identity or _identity(named) != self._file_identity or not stat.S_ISREG(named.st_mode):
            raise StorageIOError("registered_storage_file_changed")

    def _registry_content(self):
        self._check_registry_path()
        info = os.fstat(self._fd)
        if info.st_size > 16384:
            raise StorageIOError("registered_storage_file_too_large")
        result = os.pread(self._fd, 16385, 0)
        if len(result) > 16384 or len(result) != info.st_size:
            raise StorageIOError("registered_storage_file_changed")
        self._check_registry_path()
        return result

    def _checked_mounts(self):
        if self._registry_content() != self._registry_bytes:
            raise StorageIOError("registered_storage_bytes_changed")
        entries = self._mounts()
        if (self._required_mounts(entries) != self._expected_mounts
                or self._role_mounts(entries) != self._expected_role_mounts):
            raise StorageIOError("registered_storage_mount_identity_changed")
        return entries

    def __call__(self):
        with self._lock:
            self._checked_mounts()
            return self._writer_snapshot()

    def _writer_snapshot(self):
        # A wrapper must forward check_path; copying this dict must not silently
        # turn a mounted guard into the legacy no-argument verifier contract.
        return {**copy.deepcopy(self._snapshot), "path_validation_required": True}

    def check_path(self, path):
        """Validate each component, including an absent final operation name.

        Check intermediate components even when a deeper registered mount row
        still exists: a new ancestor bind can hide that deeper mount. Only
        captured registered mounts may be crossed, never an arbitrary bind
        with the same st_dev. The caller also checks its held FD ancestry.
        """
        path = _absolute_path(path)
        with self._lock:
            entries = self._checked_mounts()
            if _path_role(self._snapshot, path) not in self.roles:
                raise StorageIOError("storage_role_not_verified")
            for component in [*reversed(Path(path).parents), Path(path)]:
                current = str(component)
                roles = [role for role in self.roles
                         if current == self._snapshot[role]["mount"]
                         or current.startswith(self._snapshot[role]["mount"].rstrip("/") + "/")]
                if not roles:
                    if any(current == self._snapshot[key]["mount"]
                           or current.startswith(self._snapshot[key]["mount"].rstrip("/") + "/")
                           for key in ("data", "models")):
                        raise StorageIOError("storage_role_not_verified")
                    continue  # Outside the registered mounts; FD ancestry is still checked.
                role = max(roles, key=lambda key: len(self._snapshot[key]["mount"]))
                observed = self._mount_entry(entries, current, self._snapshot[role])
                if observed != self._expected_role_mounts[role]:
                    raise StorageIOError("registered_storage_mount_identity_changed")
            return self._writer_snapshot()

    def verify_full(self):
        with self._lock:
            self()
            snapshot = self._full_snapshot()
            if _registration_identity(snapshot) != self._registration:
                raise StorageIOError("registered_storage_identity_changed")
            if any(snapshot[key]["device"] != self._snapshot[key]["device"] for key in self.roles):
                raise StorageIOError("registered_storage_mount_changed")
            self._snapshot = copy.deepcopy(snapshot)
            return self()

    guard = __call__

    def close(self):
        if not self._closed:
            self._closed = True
            if self._fd is not None:
                os.close(self._fd)
            for _name, fd, _identity_value in reversed(self._lineage):
                os.close(fd)
            self._lineage.clear()

    def __enter__(self):
        self()
        return self

    def __exit__(self, *_exc):
        self.close()


class AnchoredRoot:
    """Existing protected root/descendant from a trusted registration snapshot.

    All API paths except the constructor path are normalized relative paths.
    uid is an explicit in-process fixture seam; production callers use uid=0.
    Keep this context alive for every GuardedFile and passed subprocess FD.
    """

    def __init__(self, path, guard, *, uid=0):
        self.path = Path(_absolute_path(path))
        self.uid, self._verifier = uid, guard
        # Preserve capability when callers pass the existing bound guard alias.
        provider = getattr(guard, "__self__", guard)
        self._path_verifier = getattr(provider, "check_path", None)
        self._lineage, self._closed = [], False
        self._lock = threading.RLock()
        if not self.path.is_absolute() or str(self.path) != os.fspath(path) or ".." in self.path.parts:
            raise StorageIOError("unsafe_storage_anchor_path")
        snapshot = guard()
        if snapshot.get("path_validation_required") and not callable(self._path_verifier):
            raise StorageIOError("storage_path_verifier_required")
        self._registration = _registration_identity(snapshot)
        self._roles = _live_roles(snapshot)
        authorized = [root for root in [*snapshot["roots"].values(), snapshot["data"]["path"], snapshot["models"]["path"]]
                      if str(self.path) == root or str(self.path).startswith(root + "/")]
        if not authorized:
            raise StorageIOError("storage_anchor_outside_registered_roots")
        self._role = _path_role(snapshot, str(self.path))
        if self._role not in self._roles:
            raise StorageIOError("storage_role_not_verified")
        try:
            fd = os.open("/", _DIR_FLAGS)
            info = os.fstat(fd)
            self._lineage.append((None, fd, _identity(info)))
            _protected(info, uid, directory=True, ancestor=True)
            for part in self.path.parts[1:]:
                fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
                info = os.fstat(fd)
                self._lineage.append((part, fd, _identity(info)))
                _protected(info, uid, directory=True, ancestor=True)
            self._fd = fd
            _protected(os.fstat(fd), uid, directory=True)
            self._device = os.fstat(fd).st_dev
            self.check()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *_exc):
        self.close()

    def close(self):
        if not self._closed:
            self._closed = True
            for _name, fd, _id in reversed(self._lineage):
                os.close(fd)
            self._lineage.clear()

    def _check_chain(self, chain, *, anchored=True):
        parent = self._fd if anchored else None
        for name, fd, identity in chain:
            info = os.fstat(fd)
            _protected(info, self.uid, directory=True, ancestor=not anchored)
            if _identity(info) != identity or (anchored and info.st_dev != self._device):
                raise StorageIOError("storage_directory_identity_changed")
            if parent is not None:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if _identity(named) != identity or not stat.S_ISDIR(named.st_mode):
                    raise StorageIOError("storage_directory_detached_or_replaced")
            parent = fd

    def check(self, relative=""):
        """Recheck the actual operation path and all held anchor identities."""
        if self._closed:
            raise StorageIOError("storage_anchor_closed")
        parts = _parts(relative) if relative else []
        path = str(self.path.joinpath(*parts))
        snapshot = self._path_verifier(path) if self._path_verifier is not None else self._verifier()
        if snapshot.get("path_validation_required") and not callable(self._path_verifier):
            raise StorageIOError("storage_path_verifier_required")
        if _live_roles(snapshot) != self._roles:
            raise StorageIOError("storage_guard_roles_changed")
        if _registration_identity(snapshot) != self._registration:
            raise StorageIOError("registered_storage_identity_changed")
        if _path_role(snapshot, path) not in self._roles:
            raise StorageIOError("storage_role_not_verified")
        try:
            major, minor = (int(value) for value in snapshot[self._role]["device"].split(":"))
            expected_device = os.makedev(major, minor)
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            raise StorageIOError("invalid_registered_storage_device") from None
        if os.fstat(self._fd).st_dev != expected_device or expected_device != self._device:
            raise StorageIOError("storage_anchor_device_mismatch")
        self._check_chain(self._lineage, anchored=False)
        _protected(os.fstat(self._fd), self.uid, directory=True)
        return snapshot

    guard = check

    def _authorize(self, parts):
        return self.check("/".join(parts))

    def fileno(self):
        self.check()
        return self._fd

    def proc_path(self, relative=""):
        """Linux subprocess path through the live parent installer's held FD.

        Keep this root open until the child exits, and check it while the child
        runs. The caller may alternatively use pass_fds and /proc/self/fd/N.
        """
        self._authorize(_parts(relative) if relative else [])
        suffix = "/" + "/".join(_parts(relative)) if relative else ""
        return f"/proc/{os.getpid()}/fd/{self.fileno()}" + suffix

    def directory(self, relative):
        parts = _parts(relative)
        self._authorize(parts)
        self.check()
        return AnchoredRoot(str(self.path.joinpath(*parts)), self._verifier, uid=self.uid)

    def _parents(self, parts, *, create=False, mode=0o700):
        chain, parent = [], self._fd
        try:
            for part in parts:
                self._authorize(parts)
                self._check_chain(chain)
                if create:
                    try:
                        os.mkdir(part, mode, dir_fd=parent)
                        os.fsync(parent)
                    except FileExistsError:
                        pass
                fd = os.open(part, _DIR_FLAGS, dir_fd=parent)
                info = os.fstat(fd)
                chain.append((part, fd, _identity(info)))
                _protected(info, self.uid, directory=True)
                if info.st_dev != self._device:
                    raise StorageIOError("storage_directory_crosses_filesystem")
                parent = fd
            self._authorize(parts)
            self._check_chain(chain)
            return parent, chain
        except BaseException:
            for _name, fd, _id in reversed(chain):
                os.close(fd)
            raise

    @staticmethod
    def _close_chain(chain):
        for _name, fd, _id in reversed(chain):
            os.close(fd)

    def mkdir(self, relative, *, mode=0o700, parents=True):
        parts = _parts(relative)
        self._authorize(parts)
        if mode & ~0o777 or mode & 0o022:
            raise StorageIOError("unsafe_storage_create_mode")
        self.check()
        parent, chain = self._parents(parts[:-1], create=parents, mode=mode)
        try:
            self._authorize(parts)
            self._check_chain(chain)
            try:
                os.mkdir(parts[-1], mode, dir_fd=parent)
            except FileExistsError:
                pass
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            _protected(info, self.uid, directory=True)
            if info.st_dev != self._device:
                raise StorageIOError("storage_directory_crosses_filesystem")
            os.fsync(parent)
            self._authorize(parts)
            self._check_chain(chain)
        finally:
            self._close_chain(chain)

    def open(self, relative, flags=os.O_RDONLY, mode=0o600):
        parts = _parts(relative)
        self._authorize(parts)
        allowed = (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL
                   | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        if flags & ~allowed or mode & ~0o777 or mode & 0o022:
            raise StorageIOError("unsafe_storage_open_flags_or_mode")
        self.check()
        parent, chain = self._parents(parts[:-1])
        fd = None
        try:
            self._authorize(parts)
            self._check_chain(chain)
            # Delay truncation until regular-file, hardlink, owner/device and
            # descriptor checks have passed. NONBLOCK prevents FIFO-open hangs.
            fd = os.open(parts[-1], (flags & ~os.O_TRUNC) | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                         mode, dir_fd=parent)
            result = GuardedFile(self, parts[-1], fd, parent, chain)
            result.check()
            if flags & os.O_TRUNC:
                result.truncate(0)
            return result
        except BaseException:
            if fd is not None:
                os.close(fd)
            self._close_chain(chain)
            raise

    def stat(self, relative, *, missing_ok=False):
        parts = _parts(relative)
        self._authorize(parts)
        self.check()
        try:
            parent, chain = self._parents(parts[:-1])
        except FileNotFoundError:
            if missing_ok:
                self._authorize(parts)
                return None
            raise
        try:
            try:
                info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                if missing_ok:
                    self._authorize(parts)
                    self._check_chain(chain)
                    return None
                raise
            _protected(info, self.uid, directory=stat.S_ISDIR(info.st_mode))
            if info.st_dev != self._device:
                raise StorageIOError("storage_file_crosses_filesystem")
            self._authorize(parts)
            self._check_chain(chain)
            return info
        finally:
            self._close_chain(chain)

    def read_json(self, relative, *, max_bytes=MAX_CHUNK):
        with self.open(relative) as stream:
            info = stream.stat()
            _protected(info, self.uid, private=True)
            if info.st_size > max_bytes:
                raise StorageIOError("storage_json_too_large")
            chunks, remaining = [], max_bytes + 1
            while remaining:
                chunk = stream.read(min(MAX_CHUNK, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if not remaining:
                raise StorageIOError("storage_json_too_large")
        try:
            value = json.loads(b"".join(chunks))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeDecodeError):
            raise StorageIOError("invalid_storage_json") from None

    def atomic_json(self, relative, value):
        """Write+fsync+rename+directory-fsync; caller owns the shared lease.

        Interrupted temporary files are never treated as completion. On lost
        storage they remain on that anchored filesystem; cleanup cannot fall
        through to another filesystem.
        """
        parts = _parts(relative)
        self._authorize(parts)
        if not isinstance(value, dict):
            raise StorageIOError("invalid_storage_json")
        encoded = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        if len(encoded) > MAX_CHUNK:
            raise StorageIOError("storage_json_too_large")
        temporary = "/".join(parts[:-1] + [".installer-" + uuid.uuid4().hex])
        with self._lock:
            existing = self.stat(relative, missing_ok=True)
            if existing is not None:
                _protected(existing, self.uid, private=True)
            try:
                with self.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as stream:
                    stream.write(encoded)
                    stream.fsync()
                self.replace(temporary, relative)
            finally:
                with contextlib.suppress(Exception):
                    self.unlink(temporary, missing_ok=True)

    def replace(self, source, destination):
        """Atomically promote a validated regular file within this root."""
        destination_parts = _parts(destination)
        self._authorize(destination_parts)
        with self._lock, self.open(source) as stream:
            destination_parent, chain = self._parents(destination_parts[:-1])
            try:
                self.stat(destination, missing_ok=True)
                stream.fsync()
                self._authorize(destination_parts)
                stream.check()
                self._check_chain(chain)
                os.replace(stream.name, destination_parts[-1], src_dir_fd=stream.parent,
                           dst_dir_fd=destination_parent)
                os.fsync(destination_parent)
                if stream.parent != destination_parent:
                    os.fsync(stream.parent)
                self._authorize(destination_parts)
                self.check(source)
                self._check_chain(stream._chain)
                self._check_chain(chain)
                promoted = os.stat(destination_parts[-1], dir_fd=destination_parent, follow_symlinks=False)
                if _identity(promoted) != stream.identity:
                    raise StorageIOError("storage_promotion_identity_changed")
                _protected(promoted, self.uid)
            finally:
                self._close_chain(chain)

    def unlink(self, relative, *, missing_ok=False):
        parts = _parts(relative)
        self._authorize(parts)
        self.check()
        parent, chain = self._parents(parts[:-1])
        try:
            info = self.stat(relative, missing_ok=missing_ok)
            if info is None:
                return
            _protected(info, self.uid)
            self._authorize(parts)
            self._check_chain(chain)
            os.unlink(parts[-1], dir_fd=parent)
            os.fsync(parent)
            self._authorize(parts)
            self._check_chain(chain)
        finally:
            self._close_chain(chain)


class GuardedFile:
    """Unbuffered file whose reads, writes and fsyncs validate its held path."""

    def __init__(self, root, name, fd, parent, chain):
        self.root, self.name, self._fd, self.parent, self._chain = root, name, fd, parent, chain
        self._relative = "/".join([item[0] for item in chain] + [name])
        self.identity = _identity(os.fstat(fd))
        self._closed = False

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *_exc):
        self.close()

    def check(self):
        if self._closed:
            raise StorageIOError("storage_file_closed")
        self.root.check(self._relative)
        self.root._check_chain(self._chain)
        info = os.fstat(self._fd)
        _protected(info, self.root.uid)
        named = os.stat(self.name, dir_fd=self.parent, follow_symlinks=False)
        if (info.st_dev != self.root._device or _identity(info) != self.identity
                or _identity(named) != self.identity or not stat.S_ISREG(named.st_mode)):
            raise StorageIOError("storage_file_detached_or_replaced")
        return info

    def fileno(self):
        self.check()
        return self._fd

    def stat(self):
        return self.check()

    def read(self, size=MAX_CHUNK):
        if not isinstance(size, int) or size < 0 or size > MAX_CHUNK:
            raise StorageIOError("storage_read_must_be_bounded")
        self.check()
        result = os.read(self._fd, size)
        self.check()
        return result

    def write(self, data):
        view, written = memoryview(data), 0
        while written < len(view):
            self.check()
            count = os.write(self._fd, view[written:written + MAX_CHUNK])
            if count <= 0:
                raise StorageIOError("storage_write_no_progress")
            written += count
            self.check()
        return written

    def seek(self, offset, whence=os.SEEK_SET):
        self.check()
        return os.lseek(self._fd, offset, whence)

    def truncate(self, size=0):
        self.check()
        os.ftruncate(self._fd, size)
        self.check()

    def fsync(self):
        self.check()
        os.fsync(self._fd)
        self.check()

    def close(self):
        if not self._closed:
            self._closed = True
            os.close(self._fd)
            self.root._close_chain(self._chain)
