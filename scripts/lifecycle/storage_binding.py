"""Read-only lifecycle binding to the installer's protected storage registry.

All topology checks belong to install.storage.Storage. This adapter never adopts
storage and never obtains roots from the environment or a deployment profile.
Path validation is a preflight, not a substitute for I1b's anchored writer.
mounted_guard wraps I1b MountedStorageGuard and preserves captured registration
identity for each snapshot supplied to the separately owned AnchoredRoot writer.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from functools import wraps
import inspect
import json
import os
from pathlib import Path
import re
import stat
import sys

from install.storage import Storage, StorageError


class BindingError(StorageError):
    """Safe failure of a registry-bound lifecycle operation."""


def _binding_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except BindingError:
            raise
        except (StorageError, OSError, KeyError, TypeError, ValueError):
            raise BindingError("registered_storage_verification_failed") from None
    return wrapped


def stable_identity(registry):
    """Match I1 schema1 identity; observed source/device/parents are excluded."""
    try:
        return copy.deepcopy({
            "schema_version": registry["schema_version"], "roots": registry["roots"],
            **{role: {key: registry[role][key] for key in ("path", "mount", "uuid", "fstype")}
               for role in ("data", "models")},
        })
    except (KeyError, TypeError):
        raise BindingError("invalid_storage_identity") from None


def _mounted_call(function, *args, **kwargs):
    """Normalize only shared guard calls, never an exception from the caller."""
    try:
        return function(*args, **kwargs)
    except BindingError:
        raise
    except Exception:
        raise BindingError("mounted_storage_guard_failed") from None


@contextmanager
def _entered_storage_context(context):
    """Close constructor-owned I1b descriptors even if entry verification fails.

    All I/O and descriptors still belong to the shared context. Its __exit__
    closes exactly once; a failed __enter__ otherwise receives no Python cleanup.
    """
    try:
        entered = context.__enter__()
    except BaseException:
        context.__exit__(*sys.exc_info())
        raise
    try:
        yield entered
    except BaseException:
        if not context.__exit__(*sys.exc_info()):
            raise
    else:
        context.__exit__(None, None, None)


class _BoundMountedGuard:
    def __init__(self, mounted, identity):
        if not callable(mounted) or not callable(getattr(mounted, "verify_full", None)):
            raise BindingError("i1b_mounted_storage_guard_required")
        self._mounted, self._identity = mounted, copy.deepcopy(identity)

    def _snapshot(self, value):
        if not isinstance(value, dict) or stable_identity(value) != self._identity:
            raise BindingError("mounted_storage_identity_changed")
        return copy.deepcopy(value)

    def __call__(self):
        return self._snapshot(_mounted_call(self._mounted))

    def check_path(self, path):
        """Retain the writer's actual-path capability and this binding's checks."""
        checker = getattr(self._mounted, "check_path", None)
        if not callable(checker):
            raise BindingError("mounted_storage_path_guard_required")
        return self._snapshot(_mounted_call(checker, path))

    def verify_full(self):
        result = _mounted_call(self._mounted.verify_full)
        # The frozen API does not require verify_full to return a value. If it
        # does return a snapshot, that snapshot must match too. The subsequent
        # descriptor-backed call checks the held registration/mount identities.
        if result is not None:
            self._snapshot(result)
        return self()


class RegisteredStorageBinding:
    """An immutable identity plus the shared, live registry verifier.

    system_root is an explicit in-process fixture seam inherited from Storage;
    the lifecycle CLI never accepts a root override. The public storage handle
    is for I1b storage_io only; verification still compares the captured identity.
    """

    def __init__(self, storage, registry):
        self.storage = storage
        self._registry = copy.deepcopy(registry)
        self._identity = stable_identity(registry)

    @classmethod
    @_binding_errors
    def read_registered(cls, runner, *, system_root=Path("/")):
        """Read protected identity for offline metadata; no mount observation.

        This is never start/write authorization. Those paths call verify or
        validate_path before accessing registered artifacts or mutating state.
        """
        reader = Storage({}, runner, system_root=system_root)
        registry = reader.read_registration()
        if registry is None:
            raise BindingError("storage_registration_required")
        config = {
            "data_dir": registry["data"]["path"], "data_uuid": registry["data"]["uuid"],
            "model_dir": registry["models"]["path"], "model_uuid": registry["models"]["uuid"],
            "storage_mode": registry.get("storage_mode", "existing"),
        }
        storage = Storage(config, runner, system_root=system_root)
        if registry["data"]["path"] != registry["data"]["mount"] or registry["roots"] != storage._roots():
            raise BindingError("invalid_registered_root_layout")
        for role in ("data", "models"):
            value = registry[role]
            if (value["path"] != value["mount"] and not value["path"].startswith(value["mount"] + "/")):
                raise BindingError("registered_namespace_outside_mount")
        data, models = registry["data"], registry["models"]
        if ((data["mount"] == models["mount"]) != (data["uuid"] == models["uuid"])
                or data["mount"] == models["mount"] and data["fstype"] != models["fstype"]):
            raise BindingError("ambiguous_registered_mount_alias")
        return cls(storage, registry)

    @classmethod
    @_binding_errors
    def load(cls, runner, *, system_root=Path("/"), roles=("data", "models")):
        binding = cls.read_registered(runner, system_root=system_root)
        binding.verify(roles=roles)
        return binding

    @property
    def registry(self):
        return copy.deepcopy(self._registry)

    @property
    def identity(self):
        return copy.deepcopy(self._identity)

    @_binding_errors
    def verify(self, roles=("data", "models")):
        """Recheck protected registration and relevant actual mounts.

        I1's provisional verifier has no role selection. Until I1c supplies it,
        data-only calls conservatively verify both roles. This may prevent state
        persistence when models are absent; callers must preserve volatile stop
        recovery and report state_persisted:false. It is never a safety bypass.
        """
        if isinstance(roles, str) or not roles or not set(roles) <= {"data", "models"}:
            raise BindingError("invalid_storage_roles")
        registry = self.storage.read_registration()
        if registry is None or stable_identity(registry) != self._identity:
            raise BindingError("storage_registration_changed_or_missing")
        verifier = self.storage.verify
        if "roles" in inspect.signature(verifier).parameters:
            return verifier(registration=self._registry, roles=tuple(sorted(set(roles))))
        return verifier(registration=self._registry)

    @contextmanager
    def mounted_guard(self, storage_io, roles=("data", "models")):
        """Wrap the real I1b mounted guard for an anchored-write transaction.

        ``with binding.mounted_guard(storage_io) as guard:`` yields a callable
        snapshot guard for ``storage_io.AnchoredRoot(binding.path('services'), guard)``.
        Full topology/capacity checks run before and after the body; each fast
        snapshot must retain this binding's captured stable identity. The real
        shared context owns all registry/mountinfo descriptors and their close.

        Reviewed I1W forwards roles to Storage and requires explicit attestation
        for reduced roles. Until I1c publishes that Storage API, the actual
        data-only guard fails closed. Older full-role fixture constructors are
        retained as an interface seam, never data-only integration evidence.
        """
        if isinstance(roles, str) or not roles or not set(roles) <= {"data", "models"}:
            raise BindingError("invalid_storage_roles")
        factory = getattr(storage_io, "MountedStorageGuard", None)
        if not callable(factory):
            raise BindingError("i1b_mounted_storage_guard_required")
        options = {}
        if "roles" in inspect.signature(factory).parameters:
            options["roles"] = tuple(sorted(set(roles)))
        context = _mounted_call(factory, self.storage, **options)
        if not all(callable(getattr(context, name, None)) for name in ("__enter__", "__exit__")):
            raise BindingError("i1b_mounted_storage_guard_required")
        try:
            mounted = _mounted_call(context.__enter__)
        except BaseException:
            # I1b opens registry descriptors in its constructor. If a mount
            # changes before __enter__, Python does not call __exit__ for us.
            _mounted_call(context.__exit__, *sys.exc_info())
            raise
        try:
            guard = _BoundMountedGuard(mounted, self._identity)
            guard.verify_full()
            try:
                yield guard
            finally:
                guard.verify_full()
        finally:
            _mounted_call(context.__exit__, *sys.exc_info())

    def role_mount(self, role):
        if role == "models":
            return "models"
        if role == "data" or role in self._registry["roots"]:
            return "data"
        raise BindingError("unknown_storage_role")

    def path(self, role, suffix=""):
        """Construct one host path from an allowed role and normalized suffix."""
        self.role_mount(role)
        root = (self._registry[role]["path"] if role in {"data", "models"}
                else self._registry["roots"][role])
        if not isinstance(suffix, str):
            raise BindingError("invalid_storage_suffix")
        if suffix and (not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", suffix)
                       or any(part in {".", ".."} for part in suffix.split("/"))):
            raise BindingError("invalid_storage_suffix")
        return root + ("/" + suffix if suffix else "")

    @_binding_errors
    def validate_path(self, role, path):
        """Validate one source or write target; do not create or read its bytes.

        A missing target is checked at its nearest existing ancestor. This
        catches hidden mounts below registered roots, including paths whose
        immediate parent has not been created. The anchored writer must retain
        a directory FD and recheck at commit to close a detach/write race.
        """
        path = str(path)
        root = self.path(role)
        if path == root:
            suffix = ""
        elif path.startswith(root + "/"):
            suffix = path[len(root) + 1:]
        else:
            raise BindingError("path_outside_storage_role")
        if self.path(role, suffix) != path:
            raise BindingError("invalid_storage_path")
        mount_role = self.role_mount(role)
        self.verify(roles=(mount_role,))
        local = self.storage._no_symlink(path, protected=True)
        ancestor = local
        while not ancestor.exists():
            ancestor = ancestor.parent
        absolute = "/" + str(ancestor.relative_to(self.storage.system_root))
        observed = self.storage._mount(absolute)
        expected = self._registry[mount_role]
        if any(observed.get(key) != expected[field] for key, field in
               (("target", "mount"), ("uuid", "uuid"), ("fstype", "fstype"))):
            raise BindingError("path_crosses_unregistered_mount")
        return local

    def read_json(self, role, path, *, maximum=1024 * 1024):
        """Read a bounded private protected instance/state JSON, never a key."""
        local = self.validate_path(role, path)
        descriptor = None
        try:
            descriptor = os.open(local, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(descriptor)
            named = local.stat(follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.storage.owner
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > maximum
                    or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                raise BindingError("unsafe_storage_json")
            with os.fdopen(descriptor, "r") as stream:
                descriptor = None
                text = stream.read(maximum + 1)
                after = os.fstat(stream.fileno())
                named = local.stat(follow_symlinks=False)
                signature = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                          item.st_mtime_ns, item.st_ctime_ns)
                if signature(info) != signature(after) or signature(after) != signature(named):
                    raise BindingError("storage_json_changed_during_read")
            if len(text) > maximum:
                raise BindingError("storage_json_too_large")
            value = json.loads(text)
            if not isinstance(value, dict):
                raise BindingError("invalid_storage_json")
            self.validate_path(role, path)
            return value
        except (OSError, UnicodeError, ValueError, TypeError):
            raise BindingError("invalid_or_missing_storage_json") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
