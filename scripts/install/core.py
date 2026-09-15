"""Protected state, command boundary and verified resumable stage execution."""
from __future__ import annotations

import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import uuid


class InstallError(Exception):
    exit_code = 1

    def __init__(self, code):
        # Error messages are codes, never subprocess output, credentials or argv.
        self.code = code if re.fullmatch(r"[a-z0-9_]{1,100}", str(code)) else "operation_failed"
        super().__init__(self.code)


class Pending(InstallError):
    exit_code = 78


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def private_path(path, *, uid=0, directory=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise InstallError("unsafe_path")
    for parent in reversed((path, *path.parents)):
        if not parent.exists() and not parent.is_symlink():
            continue
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid not in {0, uid} or info.st_mode & 0o022:
            raise InstallError("untrusted_path_owner_or_permissions")
    info = path.lstat()
    if info.st_uid != uid:
        raise InstallError("untrusted_path_owner_or_permissions")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise InstallError("not_a_directory")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
        raise InstallError("unprotected_state_file")


def atomic_json(path, value, *, uid=0):
    path = Path(path)
    private_path(path.parent, uid=uid, directory=True)
    if path.exists() or path.is_symlink():
        private_path(path, uid=uid)
    fd, temporary = tempfile.mkstemp(prefix=".installer-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_private_json(path, *, uid=0):
    private_path(path, uid=uid)
    try:
        if Path(path).stat().st_size > 1024 * 1024:
            raise InstallError("state_too_large")
        value = json.loads(Path(path).read_text())
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise InstallError("invalid_state_json") from None


@contextlib.contextmanager
def exclusive(path, *, uid=0):
    """Fixed lifecycle lock; caller must hold through all installer actions."""
    path = Path(path)
    existing = path.parent
    while not existing.exists() and not existing.is_symlink():
        existing = existing.parent
    private_path(existing, uid=uid, directory=True)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_path(path.parent, uid=uid, directory=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        private_path(path, uid=uid)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("installer_or_lifecycle_owner_active") from None
        yield fd
    finally:
        os.close(fd)


class Runner:
    """No shell expansion or inherited cloud credentials; outputs never relayed."""
    def __init__(self, writable=False):
        self.writable = writable

    @staticmethod
    def _readonly(argv):
        # Allow complete known discovery shapes, not executable basenames or a
        # single benign flag mixed with unrelated mutating options. Add new
        # observations here only with command-boundary tests.
        args = list(argv)
        if args in [
            ["id", "-u"],
            ["uname", "-r"],
            ["cat", "/sys/module/nvidia/version"],
            ["cat", "/proc/sys/kernel/random/boot_id"],
            ["dpkg", "--print-architecture"],
            ["getent", "ahosts", "snapshot.ubuntu.com"],
            ["ss", "-H", "-ltn"],
            ["mokutil", "--sb-state"],
            ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            ["nvidia-smi", "--query-gpu=driver_version,pci.bus_id", "--format=csv,noheader,nounits"],
            ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n", "*nvidia*", "linux-image-*"],
            ["modinfo", "-F", "version", "nvidia"],
            ["lsblk", "--json", "--bytes", "--paths", "--output", "NAME,PATH,TYPE,PKNAME,MOUNTPOINTS,FSTYPE,UUID,SIZE,WWN,SERIAL,RO,MAJ:MIN"],
        ]:
            return True
        if (len(args) == 6 and args[:5] == ["findmnt", "--json", "--output",
                "TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN", "--target"]):
            return args[5].startswith("/")
        if (len(args) == 4 and args[:3] == ["dpkg-query", "-W", "-f=${Status}\t${Version}"]):
            return bool(re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::(?:amd64|all))?", args[3]))
        if len(args) == 4 and args[:3] in (["df", "--output=avail", "--block-size=1"], ["df", "-B1", "--output=avail"]):
            return args[3].startswith("/")
        if (len(args) == 6 and args[:5] == ["wipefs", "--no-act", "--json", "--output", "DEVICE,OFFSET,TYPE,UUID,LABEL"]):
            return bool(re.fullmatch(r"/dev/[A-Za-z0-9_./-]+", args[5]))
        return False

    def run(self, argv, *, timeout=120, env=None):
        if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) for a in argv):
            raise InstallError("invalid_command")
        if not self.writable and (env or not self._readonly(argv)):
            raise InstallError("read_only_command_boundary")
        clean = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        if env:
            clean.update(env)
        try:
            result = subprocess.run(argv, env=clean, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise InstallError("command_unavailable_or_timeout") from None
        if result.returncode:
            raise InstallError("command_failed")
        return result.stdout


class State:
    def __init__(self, path, config, lock_hash, input_hash, guard, *, uid=0):
        self.path, self.guard, self.uid = Path(path), guard, uid
        self.identity = {"schema_version": 1, "config_hash": digest(config),
                         "lock_hash": lock_hash, "input_hash": input_hash}
        self.guard()
        if self.path.exists() or self.path.is_symlink():
            self.value = read_private_json(self.path, uid=uid)
            if any(self.value.get(k) != v for k, v in self.identity.items()):
                raise InstallError("state_config_lock_or_source_changed")
            self._validate_records()
        else:
            self.value = {**self.identity, "installation_id": str(uuid.uuid4()), "stages": {}}

    def _validate_records(self):
        records, installation = self.value.get("stages"), self.value.get("installation_id")
        try:
            if not isinstance(installation, str) or str(uuid.UUID(installation)) != installation:
                raise ValueError()
            if not isinstance(records, dict):
                raise ValueError()
            for name, record in records.items():
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or not isinstance(record, dict):
                    raise ValueError()
                if any(record.get(k) != v for k, v in self.identity.items()) or record.get("installation_id") != installation:
                    raise ValueError()
                if record.get("status") not in {"running", "complete", "failed", "reboot_required"}:
                    raise ValueError()
                if type(record.get("attempt")) is not int or record["attempt"] < 0:
                    raise ValueError()
                for field in ("started", "finished"):
                    if field in record:
                        datetime.datetime.fromisoformat(record[field])
                if record["status"] == "running" and "started" not in record:
                    raise ValueError()
                if record["status"] != "running" and "finished" not in record:
                    raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise InstallError("invalid_stage_state") from None

    def save(self):
        # A missing mount must not cause even error/status files on the root disk.
        self.guard()
        atomic_json(self.path, self.value, uid=self.uid)

    def run(self, stages, *, verify_only=False):
        results = []
        for name, check, action in stages:
            self.guard()
            record = self.value["stages"].get(name, {})
            try:
                valid = bool(check())
                # Run fresh verification even after a recorded PASS; no-op performs no writes.
                if valid and record.get("status") == "complete":
                    results.append({"stage": name, "status": "verified_noop"})
                    continue
                if verify_only:
                    results.append({"stage": name, "status": "verified" if valid else "pending"})
                    continue
                if not valid:
                    self.value["stages"][name] = {**self.identity, "installation_id": self.value["installation_id"],
                        "status": "running", "started": now(), "attempt": record.get("attempt", 0) + 1}
                    self.save()
                    action()
                    self.guard()
                    if not check():
                        raise InstallError("stage_postcondition_failed")
                self.value["stages"][name] = {**self.identity, "installation_id": self.value["installation_id"],
                    "status": "complete", "started": self.value["stages"].get(name, {}).get("started", now()),
                    "finished": now(), "attempt": self.value["stages"].get(name, {}).get("attempt", 0)}
                self.save()
                results.append({"stage": name, "status": "complete"})
            except Exception as exc:
                if not verify_only:
                    code = exc.code if isinstance(exc, InstallError) else "stage_failed"
                    checkpoint = getattr(exc, "checkpoint", None)
                    self.value["stages"][name] = {**self.identity, "installation_id": self.value["installation_id"],
                        "status": "reboot_required" if getattr(exc, "exit_code", 1) == 75 else "failed",
                        "failure": code, "started": self.value["stages"].get(name, {}).get("started", now()),
                        "finished": now(), "attempt": record.get("attempt", 0) + 1}
                    # Only allow explicitly nonsecret machine checkpoint fields.
                    if isinstance(checkpoint, dict):
                        safe = {}
                        if isinstance(checkpoint.get("boot_id"), str) and re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", checkpoint["boot_id"]):
                            safe["boot_id"] = checkpoint["boot_id"]
                        if isinstance(checkpoint.get("reason"), str) and re.fullmatch(r"[a-z0-9_]{1,100}", checkpoint["reason"]):
                            safe["reason"] = checkpoint["reason"]
                        if isinstance(checkpoint.get("required_driver"), str) and re.fullmatch(r"[0-9]{1,4}(\.[0-9]{1,5}){1,3}", checkpoint["required_driver"]):
                            safe["required_driver"] = checkpoint["required_driver"]
                        if type(checkpoint.get("secure_boot")) is bool:
                            safe["secure_boot"] = checkpoint["secure_boot"]
                        self.value["stages"][name]["checkpoint"] = safe
                    try:
                        self.save()
                    except Exception:
                        pass  # mount lost: previous durable record is stale; never fallback
                raise
        return results
