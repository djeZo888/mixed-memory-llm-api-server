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
import select
import signal
import stat
import subprocess
import tempfile
import time
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
    def __init__(self, writable=False, *, package_lease_fd=None, package_scope=None):
        self.writable = writable
        self.package_lease_fd = package_lease_fd
        self.package_scope = package_scope or SystemdPackageScope()
        self._package_watchers = []
        self._package_lease_identities = set()

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
            ["dpkg", "--audit"],
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

    @staticmethod
    def _package_preparation(argv):
        """Allow only the existing non-dpkg apt preparation command shapes.

        Parse options before the subcommand; a package named 'update', a flag
        embedded in an option value, or a later mode override cannot bypass the
        owned mutation boundary.
        """
        if argv[0] != "apt-get":
            return False
        args = list(argv[1:])
        path_options = {"Dir::Etc::sourcelist", "Dir::Etc::sourceparts", "Dir::State::lists",
                        "Dir::Cache", "Dir::Cache::archives", "Dir::Log", "Dir::Log::Terminal",
                        "Dir::Log::History"}
        fixed_options = {"DPkg::Lock::Timeout": "0", "APT::Get::List-Cleanup": "false",
                         "Acquire::Retries": "3", "Acquire::https::Timeout": "30",
                         "APT::Update::Error-Mode": "any"}
        while args and args[0] == "-o":
            if len(args) < 2 or "=" not in args[1]:
                return False
            key, value = args[1].split("=", 1)
            if key in path_options:
                valid = value.startswith("/") and "\0" not in value
            elif key == "DPkg::Options::":
                valid = value.startswith("--log=/") and "\0" not in value
            else:
                valid = key in fixed_options and value == fixed_options[key]
            if not valid:
                return False
            del args[:2]
        if args == ["update"]:
            return True
        for prefix in (["-s", "--no-install-recommends", "--no-remove", "install"],
                       ["--download-only", "--yes", "--no-install-recommends", "--no-remove", "install"]):
            if args[:len(prefix)] == prefix and len(args) > len(prefix):
                return all(re.fullmatch(r"[a-z0-9][a-z0-9+.-]*=[A-Za-z0-9.+:~_-]+", pin)
                           for pin in args[len(prefix):])
        return False

    def run(self, argv, *, timeout=120, env=None):
        if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) for a in argv):
            raise InstallError("invalid_command")
        if not self.writable and (env or not self._readonly(argv)):
            raise InstallError("read_only_command_boundary")
        if (Path(argv[0]).name in {"apt", "apt-get", "dpkg"} and not self._readonly(argv)
                and not self._package_preparation(argv)):
            raise InstallError("owned_package_transaction_required")
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


    def _validate_package_lease(self):
        """Caller lends its canonical, already-held, close-only lifecycle lease.

        No lock is acquired here. In particular this is not an alternative to
        the global admission/recovery contract owned by the lifecycle caller.
        """
        if not self.writable or self.package_lease_fd is None:
            raise InstallError("package_borrowed_lifecycle_lease_required")
        try:
            if type(self.package_lease_fd) is not int or self.package_lease_fd < 3:
                raise ValueError()
            info = os.fstat(self.package_lease_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError()
        except (OSError, ValueError, TypeError):
            raise InstallError("package_borrowed_lifecycle_lease_invalid") from None

    def package_identity(self):
        self._validate_package_lease()
        return self.package_scope.new_identity()

    def prepare_package(self, identity, *, gate_path, timeout):
        self._validate_package_lease()
        return self.package_scope.prepare(identity, gate_path=Path(gate_path), timeout=timeout)

    def inspect_package(self, identity):
        return self.package_scope.inspect(identity)

    def hold_package_lease(self, identity):
        """Detach a keeper outside the package cgroup before opening its gate.

        fork duplicates the SAME flock open-file description. The keeper never
        acquires a lock, signals a PID, or calls LOCK_UN. Unknown manager state
        deliberately retains the lease; operators must resolve ownership first.
        """
        self._validate_package_lease()
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            initialized = False
            try:
                os.close(read_fd)
                os.setsid()
                for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
                    signal.signal(sig, signal.SIG_IGN)
                # Avoid keeping CLI pipes, files, or unrelated leases alive.
                import resource
                limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
                if limit == resource.RLIM_INFINITY:
                    limit = 1048576
                keep = sorted({self.package_lease_fd, write_fd})
                start = 3
                for fd in keep:
                    if fd >= start:
                        os.closerange(start, fd)
                        start = fd + 1
                os.closerange(start, int(limit))
                null = os.open(os.devnull, os.O_RDWR)
                for fd in (0, 1, 2):
                    os.dup2(null, fd)
                if null > 2 and null not in keep:
                    os.close(null)
                initialized = True
                try:
                    os.write(write_fd, b"R")
                except BrokenPipeError:
                    pass  # CLI crashed during handshake; still monitor to quiescence.
                os.close(write_fd)
            except BaseException:
                if not initialized:
                    # No READY could have been sent: no package gate can open.
                    os._exit(1)
            while True:
                try:
                    if self.inspect_package(identity)["state"] == "quiescent":
                        os._exit(0)  # close-only lease release
                except BaseException:
                    pass  # Unknown is never proof of quiescence, even on interruption.
                try:
                    time.sleep(0.1)
                except BaseException:
                    pass
        os.close(write_fd)
        self._package_watchers.append(pid)  # waitpid only; never durable identity
        try:
            if not select.select([read_fd], [], [], 5)[0] or os.read(read_fd, 1) != b"R":
                raise InstallError("package_lease_keeper_unavailable")
            self._package_lease_identities.add(digest(identity))
        finally:
            os.close(read_fd)

    def run_package(self, identity, argv, *, gate_path, timeout=120, env=None):
        """Open a persisted gate; only the manager owns the package process tree."""
        self._validate_package_lease()
        if digest(identity) not in self._package_lease_identities:
            raise InstallError("package_lease_keeper_required")
        try:
            self.package_scope.execute(identity, argv, gate_path=Path(gate_path), env=env)
            deadline = time.monotonic() + timeout + 15
            while True:
                try:
                    status = self.inspect_package(identity)
                except InstallError as exc:
                    if exc.code != "package_scope_state_changing_retry" or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
                    continue
                if status["state"] == "quiescent":
                    if not status["successful"]:
                        raise InstallError("package_command_failed_or_timeout")
                    return ""
                if time.monotonic() >= deadline:
                    raise InstallError("package_scope_still_live_recovery_required")
                time.sleep(0.1)
        except BaseException:
            # The manager also enforces RuntimeMaxSec after a hard CLI crash.
            # abort only uses a pinned, identity-validated cgroup FD, never a PID
            # or a unit-name signal. Unknown leaves inhibitor + keeper intact.
            try:
                self.package_scope.abort(identity)
            except Exception:
                pass
            raise
        finally:
            for pid in self._package_watchers[:]:
                if os.waitpid(pid, os.WNOHANG)[0]:
                    self._package_watchers.remove(pid)


class SystemdPackageScope:
    """Ubuntu 24.04/systemd 255 + unified cgroup v2 package ownership.

    A retained transient service is prepared with a waiting Python executable.
    It cannot exec apt until the caller durably records the manager's exact
    invocation and starts the borrowed-lease keeper. No --collect/stop/reset is
    used: losing retained identity is a recovery error, never an empty scope.
    """
    PROPERTIES = ("Id", "Description", "LoadState", "ActiveState", "SubState",
                  "InvocationID", "ControlGroup", "MainPID", "ExecMainPID", "ExecMainCode",
                  "ExecMainStatus", "Result", "Type", "ExitType", "RemainAfterExit",
                  "KillMode", "SendSIGKILL", "Restart", "CollectMode")
    SETTINGS = {"Type": "exec", "ExitType": "cgroup", "RemainAfterExit": "yes",
                "KillMode": "control-group", "SendSIGKILL": "yes", "Restart": "no",
                "CollectMode": "inactive"}

    @staticmethod
    def _boot_id():
        try:
            value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            if str(uuid.UUID(value)) != value:
                raise ValueError()
            return value
        except (OSError, ValueError):
            raise InstallError("package_systemd_boot_identity_unavailable") from None

    @staticmethod
    def _command(argv):
        try:
            result = subprocess.run(argv, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                    "LANG": "C", "LC_ALL": "C"}, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    timeout=10, check=False)
            if result.returncode:
                raise ValueError()
            return result.stdout
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise InstallError("package_scope_inspection_or_manager_failed") from None

    def new_identity(self):
        token = uuid.uuid4().hex
        return {"kind": "systemd-cgroup-v2", "token": token,
                "unit": "local-ai-package-" + token + ".service", "boot_id": self._boot_id()}

    def _validate(self, identity, prepared=True):
        try:
            token = identity["token"]
            if (identity["kind"] != "systemd-cgroup-v2" or not re.fullmatch(r"[0-9a-f]{32}", token)
                    or identity["unit"] != "local-ai-package-" + token + ".service"
                    or identity["boot_id"] != self._boot_id()):
                raise ValueError()
            if prepared and (not re.fullmatch(r"[0-9a-f]{32}", identity["invocation_id"])
                    or identity["cgroup"] != "/system.slice/" + identity["unit"]
                    or type(identity["cgroup_inode"]) is not int or identity["cgroup_inode"] <= 0):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise InstallError("package_scope_identity_missing_or_stale") from None

    def _show(self, identity):
        self._validate(identity, prepared=False)
        raw = self._command(["/usr/bin/systemctl", "show", "--no-pager", "--all",
                             "--property=" + ",".join(self.PROPERTIES), "--", identity["unit"]])
        try:
            rows = [row.split("=", 1) for row in raw.splitlines()]
            values = dict(rows)
            if len(values) != len(rows) or set(values) != set(self.PROPERTIES):
                raise ValueError()
            if (values["Id"] != identity["unit"] or values["LoadState"] != "loaded"
                    or values["Description"] != "local-ai package " + identity["token"]
                    or any(values[k] != v for k, v in self.SETTINGS.items())
                    or not re.fullmatch(r"[0-9a-f]{32}", values["InvocationID"])
                    or (identity.get("invocation_id") and values["InvocationID"] != identity["invocation_id"])):
                raise ValueError()
            return values
        except (ValueError, KeyError):
            raise InstallError("package_scope_identity_missing_or_stale") from None

    def _cgroup(self, identity):
        """A pinned directory cannot be retargeted to a newly reused cgroup."""
        self._validate(identity)
        path = Path("/sys/fs/cgroup") / identity["cgroup"].lstrip("/")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError:
            raise InstallError("package_cgroup_state_unknown") from None
        try:
            if os.fstat(fd).st_ino != identity["cgroup_inode"]:
                raise InstallError("package_cgroup_identity_changed")
            return fd
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _populated(fd):
        try:
            event_fd = os.open("cgroup.events", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(event_fd) as stream:
                rows = [line.split() for line in stream]
                fields = dict(rows)
            if len(rows) != len(fields) or fields.get("populated") not in {"0", "1"}:
                raise ValueError()
            return fields["populated"] == "1"
        except (OSError, ValueError):
            raise InstallError("package_cgroup_state_unknown") from None

    def prepare(self, identity, *, gate_path, timeout):
        self._validate(identity, prepared=False)
        if type(timeout) not in {int, float} or not 0 < timeout <= 86400:
            raise InstallError("package_timeout_invalid")
        private_path(gate_path.parent, directory=True)
        if gate_path.exists() or gate_path.is_symlink():
            raise InstallError("package_execution_gate_already_exists")
        # Unified v2 and cgroup.kill are required; no process-group fallback.
        if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
            raise InstallError("package_unified_cgroup_v2_required")
        properties = {**self.SETTINGS, "RuntimeMaxSec": str(timeout),
                      "TimeoutStartSec": "15", "TimeoutStopSec": "5",
                      "StandardOutput": "null", "StandardError": "null",
                      "UMask": "0077", "Delegate": "no"}
        self._command(["/usr/bin/systemd-run", "--quiet", "--unit=" + identity["unit"],
                       "--description=local-ai package " + identity["token"],
                       *["--property=" + k + "=" + v for k, v in properties.items()],
                       "--", "/usr/bin/python3", "-I", str(Path(__file__).resolve()),
                       "--package-worker", str(gate_path)])
        values = self._show(identity)
        if values["ActiveState"] != "active" or values["SubState"] != "running":
            raise InstallError("package_scope_not_ready")
        path = "/system.slice/" + identity["unit"]
        if values["ControlGroup"] != path:
            raise InstallError("package_scope_identity_missing_or_stale")
        try:
            fd = os.open("/sys/fs/cgroup" + path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                inode = os.fstat(fd).st_ino
                kill_fd = os.open("cgroup.kill", os.O_WRONLY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(kill_fd)  # feature check only; no write
            finally:
                os.close(fd)
        except OSError:
            raise InstallError("package_cgroup_state_unknown") from None
        prepared = {**identity, "invocation_id": values["InvocationID"],
                    "cgroup": path, "cgroup_inode": inode}
        if self.inspect(prepared)["state"] != "live":
            raise InstallError("package_scope_not_ready")
        return prepared

    def inspect(self, identity):
        self._validate(identity)
        values = self._show(identity)
        if values["ControlGroup"] not in {identity["cgroup"], ""}:
            raise InstallError("package_scope_identity_missing_or_stale")
        fd = self._cgroup(identity)
        try:
            populated = self._populated(fd) if fd is not None else False
            # Revalidate the manager after observing the pinned kernel object.
            after = self._show(identity)
            if any(after[k] != values[k] for k in ("ActiveState", "SubState", "ControlGroup", "MainPID")):
                raise InstallError("package_scope_state_changing_retry")
            if populated:
                return {"state": "live", "successful": False}
            terminal = (values["ActiveState"], values["SubState"]) in {
                ("active", "exited"), ("failed", "failed")}
            if not terminal or values["MainPID"] != "0":
                raise InstallError("package_cgroup_state_unknown")
            # Missing kernel cgroup is acceptable ONLY with this exact retained
            # terminal invocation: systemd removes empty cgroups. Missing UNIT
            # identity, a reboot, or a reused inode never supplies this proof.
            return {"state": "quiescent", "successful": values["Result"] == "success"
                    and values["ExecMainCode"] == "1" and values["ExecMainStatus"] == "0"}
        finally:
            if fd is not None:
                os.close(fd)

    def execute(self, identity, argv, *, gate_path, env=None):
        if gate_path.exists() or gate_path.is_symlink():
            raise InstallError("package_execution_gate_already_exists")
        if self.inspect(identity)["state"] != "live":
            raise InstallError("package_scope_not_ready")
        if (not isinstance(argv, (list, tuple)) or not argv or argv[0] != "apt-get"
                or any(not isinstance(a, str) or "\0" in a for a in argv)):
            raise InstallError("invalid_package_command")
        clean = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        allowed = {"DEBIAN_FRONTEND", "NEEDRESTART_MODE", "LC_ALL", "TMPDIR", "TMP", "TEMP"}
        if env:
            if set(env) - allowed or any(not isinstance(v, str) or "\0" in v for v in env.values()):
                raise InstallError("invalid_package_environment")
            clean.update(env)
        atomic_json(gate_path, {"identity": identity, "argv": list(argv), "env": clean})

    def abort(self, identity):
        """Terminate only the validated kernel object, not a reusable unit/PID."""
        status = self.inspect(identity)
        if status["state"] == "quiescent":
            return
        fd = self._cgroup(identity)
        if fd is None:
            raise InstallError("package_cgroup_state_unknown")
        try:
            kill_fd = os.open("cgroup.kill", os.O_WRONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                self._show(identity)  # immutable invocation check before write
                os.write(kill_fd, b"1")
            finally:
                os.close(kill_fd)
        except OSError:
            raise InstallError("package_cgroup_state_unknown") from None
        finally:
            os.close(fd)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.inspect(identity)["state"] == "quiescent":
                return
            time.sleep(0.1)
        raise InstallError("package_scope_still_live_recovery_required")


def _package_worker(gate_path):
    """Manager-owned pre-exec gate. No apt process exists before durable identity."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if gate_path.exists():
            gate = read_private_json(gate_path)
            scope = SystemdPackageScope()
            identity = gate["identity"]
            scope._validate(identity)
            if os.environ.get("INVOCATION_ID") != identity["invocation_id"]:
                raise InstallError("package_scope_identity_missing_or_stale")
            # All executable/environment data is installer-created protected state.
            argv, env = gate["argv"], gate["env"]
            if not argv or argv[0] != "apt-get":
                raise InstallError("invalid_package_command")
            os.execve("/usr/bin/apt-get", argv, env)
        time.sleep(0.05)
    raise InstallError("package_execution_gate_timeout")


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


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--package-worker":
        try:
            _package_worker(Path(sys.argv[2]))
        except BaseException:
            sys.exit(1)  # never emit command, policy, or environment data
    else:
        sys.exit(2)
