"""Render the single lifecycle boot owner from registered host paths.

I1b installs/enables the returned unit after protected snapshot installation.
This module performs read-only validation and never installs or starts a service.
Escaping follows systemd.unit(5), String Escaping for Inclusion in Unit Names:
https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .storage_binding import BindingError, _binding_errors


RECOVERY_ROOT = "/usr/local/lib/local-ai-server"
RECOVERY_FILES = (
    "scripts/llmctl", "scripts/lifecycle/__init__.py", "scripts/lifecycle/manager.py",
    "scripts/lifecycle/runtime_io.py", "scripts/lifecycle/qwen_next.py",
    "scripts/lifecycle/storage_binding.py", "scripts/common/lifecycle_lease.py",
    "scripts/install/__init__.py", "scripts/install/storage.py", "scripts/install/storage_io.py",
    "scripts/install/prerequisites.py",
)


@_binding_errors
def mount_unit_name(path):
    """Return the exact systemd mount unit for a normalized simple path."""
    # Registered paths use this shared validator; whitespace, %, $, backslash,
    # commas and traversal cannot enter a unit or an Exec argument.
    from install.storage import Storage
    Storage._path(path)
    raw = path[1:]
    name = "".join("-" if char == "/" else
                   char if char.isascii() and (char.isalnum() or char in "_:.")
                   and not (index == 0 and char == ".") else
                   "\\x" + format(ord(char), "02x")
                   for index, char in enumerate(raw)) + ".mount"
    if len(name) > 255:
        raise BindingError("mount_unit_name_too_long")
    return name


def _protected_tree(binding, local, source_root=None):
    if not local.is_dir():
        raise BindingError("installed_source_directory_required")
    owner = binding.storage.owner
    # Imports/configs must be part of the protected installed snapshot. A
    # protected parent cannot authorize a writable or symlinked child module.
    for current, directories, files in os.walk(local, followlinks=False):
        for entry in [Path(current), *(Path(current) / name for name in directories + files)]:
            if source_root is not None:
                logical = str(Path(source_root) / entry.relative_to(local))
                binding.validate_path("services", logical)
            info = entry.lstat()
            if (info.st_uid != owner or info.st_mode & 0o022
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    or stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                raise BindingError("installed_source_is_not_protected")
    for required in RECOVERY_FILES:
        if not (local / required).is_file():
            raise BindingError("installed_source_snapshot_incomplete")


def _read_source_bytes(path, owner):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        named = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022
                or info.st_nlink != 1 or info.st_size > 1024 * 1024
                or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
            raise BindingError("unsafe_recovery_source_file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            value = stream.read(1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
            named = path.stat(follow_symlinks=False)
        signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if len(value) > 1024 * 1024 or signature(info) != signature(after) or signature(after) != signature(named):
            raise BindingError("recovery_source_changed_during_read")
        return value
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validate_recovery_snapshot(binding, source_root):
    source = binding.validate_path("services", source_root)
    _protected_tree(binding, source, source_root)
    recovery = binding.storage._no_symlink(RECOVERY_ROOT, protected=True)
    _protected_tree(binding, recovery)
    required = set(RECOVERY_FILES)
    actual = {str(path.relative_to(recovery)) for path in recovery.rglob("*") if path.is_file()}
    if actual != required:
        raise BindingError("recovery_snapshot_file_set_mismatch")
    for relative in sorted(required):
        if (_read_source_bytes(source / relative, binding.storage.owner)
                != _read_source_bytes(recovery / relative, binding.storage.owner)):
            raise BindingError("recovery_snapshot_source_mismatch")


@_binding_errors
def render_boot_unit(binding, source_root, instance_path):
    """Validate the installed snapshot/instance and return systemd unit text.

    source_root and instance_path are explicit registered-services paths. The
    protected instance must bind storage_identity to this exact registration.
    One-filesystem registrations emit one mount dependency, even when models
    occupy a descendant namespace. Nested/sibling filesystems emit both mounts.
    No command here changes boot intent or claims actual Linux boot validation.
    """
    source_root, instance_path = str(source_root), str(instance_path)
    binding.verify()
    if instance_path != binding.path("services", "llm-manager/deployment-instance.json"):
        raise BindingError("boot_instance_path_mismatch")
    _validate_recovery_snapshot(binding, source_root)
    instance = binding.read_json("services", instance_path)
    if instance.get("storage_identity") != binding.identity:
        raise BindingError("instance_storage_identity_mismatch")
    mounts = sorted({binding.registry[role]["mount"] for role in ("data", "models")})
    units = " ".join(mount_unit_name(path) for path in mounts)
    # The fixed interpreter runs in isolated/no-bytecode mode. scripts/llmctl
    # explicitly adds its own protected source directory to sys.path.
    command = "/usr/bin/python3 -I -B " + source_root + "/scripts/llmctl"
    stop_command = "/usr/bin/python3 -I -B " + RECOVERY_ROOT + "/scripts/llmctl"
    binding.verify()
    return "\n".join([
        "# Generated by lifecycle.boot_unit.render_boot_unit; I1b owns installation.",
        "# One boot intent replayer. Docker restart policy remains no.",
        "[Unit]", "Description=Restore explicitly desired llmctl deployment",
        "Requires=docker.service", "After=docker.service systemd-tmpfiles-setup.service",
        "RequiresMountsFor=" + " ".join(mounts), "BindsTo=" + units, "After=" + units,
        *("ConditionPathIsMountPoint=" + path for path in mounts),
        "", "[Service]", "Type=oneshot", "RemainAfterExit=yes",
        "WorkingDirectory=/",
        "ExecStart=" + command + " boot-start --yes --instance " + instance_path,
        "ExecStop=" + stop_command + " boot-stop --yes --instance " + instance_path,
        "TimeoutStartSec=3h", "TimeoutStopSec=5min", "UMask=0077",
        "StandardOutput=null", "StandardError=null", "",
        "[Install]", "WantedBy=multi-user.target", "",
    ])
