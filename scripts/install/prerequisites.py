"""Pinned Ubuntu prerequisites. Mutations run only behind the caller's storage guard.

The caller owns the installer/lifecycle lock. No command output is included in errors.
check_* methods are read-only. Driver checkpoints are facts, never success markers.
"""
import json
import os
from pathlib import Path
import re
import stat
import tempfile


GIB = 1024 ** 3
POLICY_SENTINEL = b"#!/bin/sh\n# local-ai installer temporary package service inhibitor\nexit 101\n"


class PrerequisiteError(RuntimeError):
    def __init__(self, message, code="prerequisite_validation_failed", public_details=None):
        self.code = code
        self.public_details = public_details or {}
        super().__init__(message)


class RebootRequired(PrerequisiteError):
    exit_code = 75

    def __init__(self, checkpoint):
        self.checkpoint = checkpoint
        self.target_kernel = checkpoint.get("target_kernel")
        super().__init__(checkpoint["message"], code="reboot_required",
                         public_details={"target_kernel": self.target_kernel})


def protected_path(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022 or (not directory and info.st_nlink != 1):
        raise PrerequisiteError("Unsafe prerequisite path ownership/type/mode: " + str(path))


def atomic_bytes(path, content, mode=0o600):
    protected_path(path.parent, directory=True)
    if path.exists() or path.is_symlink():
        protected_path(path)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    tmp = Path(name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def assert_package_admission(data_dir, storage_guard, *, policy_path=None):
    """Read-only canonical-admission gate; acquires no lease and restores nothing.

    L1/I1b call this AFTER acquiring their canonical lifecycle lease and BEFORE
    any ordinary mutation. Lock availability never proves package quiescence.
    Every pending marker/gate blocks admission, even if its service is terminal.
    An explicitly selected recovery operation instead calls recover_policy under
    that lease, then retries this check. No installer config/lockfile is needed.
    """
    storage_guard()
    data = Path(data_dir)
    if not data.is_absolute() or data == Path("/") or data.resolve() != data:
        raise PrerequisiteError("Package admission requires canonical verified data storage")
    protected_path(data, directory=True)
    state = data
    for part in ("services", "installer"):
        state = state / part
        if not state.exists() and not state.is_symlink():
            break
        protected_path(state, directory=True)
    pending = any(path.exists() or path.is_symlink() for path in (
        data / "services/installer/package-service-policy.json",
        data / "services/installer/package-execution-gate.json"))
    policy = Path(policy_path or "/usr/sbin/policy-rc.d")
    if policy.parent.resolve() != policy.parent:
        raise PrerequisiteError("Unsafe service policy parent", code="existing_policy_changed")
    protected_path(policy.parent, directory=True)
    if policy.exists() or policy.is_symlink():
        protected_path(policy)
        if policy.stat().st_size > 65536:
            raise PrerequisiteError("Service policy is unexpectedly large")
        pending = pending or policy.read_bytes() == POLICY_SENTINEL
    storage_guard()
    if pending:
        raise PrerequisiteError(
            "Pending package transaction blocks mutation admission even when the lifecycle "
            "lease is available. Run explicit package recovery under the same canonical lease; "
            "retain inhibitor and marker until exact quiescence is verified.",
            code="package_transaction_recovery_required")


class Prerequisites:
    def __init__(self, config, runner, storage_guard, lock_path=None, *, policy_path=None):
        self.config, self.runner, self.guard = config, runner, storage_guard
        self.data = Path(config["data_dir"])
        if not self.data.is_absolute() or self.data == Path("/"):
            raise PrerequisiteError("Prerequisites require an absolute dedicated data path")
        self.lock = json.loads(Path(lock_path or Path(__file__).with_name("versions.lock.json")).read_text())
        if self.lock.get("schema_version") != 1:
            raise PrerequisiteError("Unsupported package lock schema")
        self.state = self.data / "services/installer"
        self.checkpoint_path = self.state / "driver-checkpoint.json"
        self.policy_path = Path(policy_path or "/usr/sbin/policy-rc.d")
        self.apt_root = self.data / "cache/installer-apt"

    def _run(self, argv, timeout=60, env=None):
        try:
            return self.runner.run(argv, timeout=timeout, env=env).strip()
        except Exception:
            raise PrerequisiteError("Command failed: " + Path(argv[0]).name + "; inspect protected installer diagnostics") from None

    def _maybe(self, argv):
        try:
            return self._run(argv)
        except PrerequisiteError:
            return ""

    def _root_free(self):
        try:
            return int(self._run(["df", "-B1", "--output=avail", "/"]).splitlines()[-1])
        except ValueError:
            raise PrerequisiteError("Cannot determine root free space") from None

    def _guard(self, package_bytes=0):
        self.guard()
        minimum = max(4 * GIB, int(self.config.get("root_min_free_bytes", 4 * GIB)))
        budget = int(self.config.get("root_package_budget_bytes", 2 * GIB))
        if package_bytes > budget or self._root_free() < minimum + package_bytes:
            raise PrerequisiteError("Root package budget/free-space gate failed; data storage cannot substitute for OS package space",
                                    code="insufficient_root_package_budget")

    def _assert_root(self):
        if self._run(["id", "-u"]) != "0":
            raise PrerequisiteError("Server package setup requires root or sudo")

    def _installed(self, pins):
        for name, version in pins.items():
            actual = self._maybe(["dpkg-query", "-W", "-f=${Status}\t${Version}", name])
            if actual != "install ok installed\t" + version:
                return False
        return True

    def check_base(self):
        if ((self.state / "package-service-policy.json").exists()
                or (self.state / "package-service-policy.json").is_symlink()):
            return False
        return self._installed(self.lock["requested"]["base"])

    def _ensure_directory(self, path):
        if self.data.resolve() != self.data or not path.is_relative_to(self.data):
            raise PrerequisiteError("Prerequisite path must stay within canonical data storage")
        # Validate each ancestor before descending or creating anything under it.
        protected_path(self.data, directory=True)
        current = self.data
        for part in path.relative_to(self.data).parts:
            current = current / part
            self._guard()
            if not current.exists() and not current.is_symlink():
                current.mkdir(mode=0o700)
            protected_path(current, directory=True)

    def _validate_state_path(self, path):
        if self.data.resolve() != self.data or not path.is_relative_to(self.data):
            raise PrerequisiteError("State must stay within canonical data storage")
        protected_path(self.data, directory=True)
        current = self.data
        for part in path.parent.relative_to(self.data).parts:
            current = current / part
            protected_path(current, directory=True)
        protected_path(path)

    def _write_json(self, path, obj):
        self._ensure_directory(path.parent)
        self._guard()
        atomic_bytes(path, (json.dumps(obj, sort_keys=True) + "\n").encode())

    def _paths(self):
        self._guard()
        for path in [self.apt_root / "archives/partial", self.apt_root / "lists/partial",
                     self.apt_root / "tmp", self.apt_root / "sourceparts", self.data / "logs/installer", self.state]:
            self._ensure_directory(path)
        if any((self.apt_root / "sourceparts").iterdir()):
            raise PrerequisiteError("Installer sourceparts must be empty; refusing additional package sources")
        # Only this installer uses these sources. Host sources and unattended upgrades are preserved.
        sources = self.apt_root / "ubuntu.sources"
        snapshot = self.lock["ubuntu_snapshot"]
        content = ("Types: deb\nURIs: https://snapshot.ubuntu.com/ubuntu/" + snapshot + "/\n"
                   "Suites: noble noble-updates noble-security\nComponents: main restricted universe multiverse\n"
                   "Architectures: amd64\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
                   "Check-Valid-Until: no\n")
        self._guard()
        atomic_bytes(sources, content.encode())

    def _apt_options(self):
        values = {
            "Dir::Etc::sourcelist": self.apt_root / "ubuntu.sources",
            "Dir::Etc::sourceparts": self.apt_root / "sourceparts",
            "Dir::State::lists": self.apt_root / "lists",
            "Dir::Cache": self.apt_root,
            "Dir::Cache::archives": self.apt_root / "archives",
            "Dir::Log": self.data / "logs/installer",
            "Dir::Log::Terminal": self.data / "logs/installer/apt-term.log",
            "Dir::Log::History": self.data / "logs/installer/apt-history.log",
            "DPkg::Options::": "--log=" + str(self.data / "logs/installer/dpkg.log"),
            "DPkg::Lock::Timeout": "0",
            "APT::Get::List-Cleanup": "false",
            "Acquire::Retries": "3",
            "Acquire::https::Timeout": "30",
            "APT::Update::Error-Mode": "any",
        }
        return [part for key, value in values.items() for part in ("-o", key + "=" + str(value))]

    def _apt(self, args, timeout=600):
        env = {"DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "l", "LC_ALL": "C",
               "TMPDIR": str(self.apt_root / "tmp"), "TMP": str(self.apt_root / "tmp"),
               "TEMP": str(self.apt_root / "tmp")}
        self._guard()
        argv = ["apt-get", *self._apt_options(), *args]
        if "--no-download" in args:
            result = self.package_transaction(argv, timeout=timeout, env=env)
        else:
            result = self._run(argv, timeout=timeout, env=env)
        self._guard()
        return result

    def _available(self, name, version):
        try:
            raw = self._run(["apt-cache", *self._apt_options(), "show", name + "=" + version])
        except PrerequisiteError:
            raise PrerequisiteError("Locked package unavailable: " + name + "=" + version,
                                    code="locked_package_unavailable", public_details={"package": name, "version": version}) from None
        fields = dict(line.split(": ", 1) for line in raw.split("\n\n")[0].splitlines()
                      if ": " in line and not line.startswith(" "))
        record = self.lock["packages"].get(name)
        if not record or any(fields.get(k) != str(v) for k, v in {
            "Version": version, "SHA256": record["sha256"], "Size": record["size_bytes"]}.items()):
            raise PrerequisiteError("Locked package unavailable or metadata changed: " + name + "=" + version,
                                    code="locked_package_unavailable", public_details={"package": name, "version": version})

    def _policy_current(self):
        if self.policy_path.parent.resolve() != self.policy_path.parent:
            raise PrerequisiteError("Unsafe service policy parent", code="existing_policy_changed")
        protected_path(self.policy_path.parent, directory=True)
        if self.policy_path.exists() or self.policy_path.is_symlink():
            protected_path(self.policy_path)
            if self.policy_path.stat().st_size > 65536:
                raise PrerequisiteError("Service policy is unexpectedly large")
            return self.policy_path.read_bytes()
        return None

    @staticmethod
    def _ownership_error(code="package_ownership_unknown"):
        return PrerequisiteError(
            "Package recovery is blocked: retain the inhibitor and lifecycle ownership. "
            "Inspect the exact recorded unit, invocation and cgroup in package-service-policy.json; "
            "resolve ownership/quiescence before retrying under the canonical lease. "
            "Do not delete the marker, restore policy, or signal a stored PID.", code=code)

    def _saved_policy(self, marker):
        self._validate_state_path(marker)
        try:
            if marker.stat().st_size > 256 * 1024:
                raise ValueError()
            saved = json.loads(marker.read_text())
            if not isinstance(saved, dict):
                raise ValueError()
            if (saved.get("schema_version") != 2 or type(saved["existed"]) is not bool
                    or type(saved["mode"]) is not int or not 0 <= saved["mode"] <= 0o7777
                    or saved["mode"] & 0o022 or not isinstance(saved["transaction"], dict)
                    or saved["phase"] not in {"preparing", "owned"}):
                raise ValueError()
            original = bytes.fromhex(saved["original_hex"])
            if len(original) > 65536 or (not saved["existed"] and original):
                raise ValueError()
            return saved, original if saved["existed"] else None
        except (KeyError, ValueError, TypeError, OSError):
            # Legacy markers have no trustworthy ownership: never auto-upgrade.
            raise self._ownership_error() from None

    def recover_policy(self):
        """Reconcile under the caller's canonical lifecycle lease before admission.

        Exact retained transaction identity AND recursive quiescence are required.
        A legacy/incomplete marker, missing unit, reboot, inspect error or reused
        identity retains the inhibitor and marker. No stale PID is ever signaled.
        """
        self.guard()
        marker = self.state / "package-service-policy.json"
        if not marker.exists() and not marker.is_symlink():
            if self._policy_current() == POLICY_SENTINEL:
                raise self._ownership_error("package_ownership_marker_missing")
            return {"changed": False}
        self._assert_root()
        saved, original = self._saved_policy(marker)
        if saved["phase"] != "owned":
            raise self._ownership_error("package_ownership_incomplete")
        try:
            status = self.runner.inspect_package(saved["transaction"])
            if not isinstance(status, dict) or status.get("state") not in {"live", "quiescent"}:
                raise ValueError()
        except Exception:
            raise self._ownership_error() from None
        if status.get("state") != "quiescent":
            raise self._ownership_error("package_scope_live_recovery_required")
        current = self._policy_current()
        if current not in (POLICY_SENTINEL, original):
            raise PrerequisiteError("Package service policy changed outside installer", code="existing_policy_changed")
        # Quiescence is not a package-success marker. Interrupted dpkg state is
        # an explicit repair checkpoint, never an unpinned automatic configure.
        if self._run(["dpkg", "--audit"]):
            raise PrerequisiteError(
                "Owned package scope is quiescent but dpkg audit requires repair; retain the "
                "transaction record and inhibitor. Review a pinned repair under package ownership before retry.",
                code="package_database_repair_required")
        self.guard()
        if original is None:
            if current is not None:
                self.policy_path.unlink()
        else:
            # Also repairs a crash after bytes were restored but before mode or
            # marker retirement. Preserve all original permission bits exactly.
            atomic_bytes(self.policy_path, original, mode=saved["mode"])
        policy_fd = os.open(self.policy_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(policy_fd)
        finally:
            os.close(policy_fd)
        self.guard()
        # Gate retirement precedes marker retirement. No new process may be
        # launched from this gate; the exact retained invocation is terminal.
        gate = self.state / "package-execution-gate.json"
        if gate.exists() or gate.is_symlink():
            self._validate_state_path(gate)
            gate.unlink()
        marker.unlink()
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(state_fd)
        finally:
            os.close(state_fd)
        return {"changed": True, "package_database_audited": True}

    def package_transaction(self, argv, *, timeout=120, env=None):
        """Public package mutation boundary, shared by prerequisite/container stages.

        Constructor config supplies the verified data/state root; storage_guard
        is rechecked before writes. Runner must borrow the caller's canonical
        lifecycle lease. argv must be the caller's already-reviewed/pinned apt-get
        plan with explicit data-backed cache/log options. This boundary owns the
        ONE policy marker/inhibitor and manager identity, including recovery.
        Successful return proves scope exit and a clean dpkg audit; the caller
        must still verify its package/version postconditions before stage success.
        """
        self.recover_policy()
        assert_package_admission(self.data, self.guard, policy_path=self.policy_path)
        self._guard()
        try:
            identity = self.runner.package_identity()
        except Exception as exc:
            raise self._ownership_error(getattr(exc, "code", "package_borrowed_lifecycle_lease_required")) from None
        marker = self.state / "package-service-policy.json"
        gate = self.state / "package-execution-gate.json"
        if gate.exists() or gate.is_symlink():
            raise self._ownership_error("package_execution_gate_orphaned")
        current = self._policy_current()
        saved = {"schema_version": 2, "existed": current is not None,
                 "original_hex": (current or b"").hex(),
                 "mode": stat.S_IMODE(self.policy_path.stat().st_mode) if current is not None else 0o755,
                 "transaction": identity, "phase": "preparing"}
        # Both previous policy and allocated unique unit identity precede start.
        self._write_json(marker, saved)
        self._guard()
        atomic_bytes(self.policy_path, POLICY_SENTINEL, mode=0o755)
        try:
            saved["transaction"] = self.runner.prepare_package(identity, gate_path=gate, timeout=timeout)
            saved["phase"] = "owned"
            self._write_json(marker, saved)
            self.runner.hold_package_lease(saved["transaction"])
            self._guard()
            return self.runner.run_package(saved["transaction"], argv, gate_path=gate,
                                           timeout=timeout, env=env)
        except Exception as exc:
            raise PrerequisiteError(
                "Owned package command failed; check transaction recovery and dpkg audit before retry.",
                code=getattr(exc, "code", "package_command_failed")) from None
        finally:
            # No unconditional restore: recovery revalidates persisted ownership,
            # recursive liveness and the existing policy on EVERY exit path.
            self.recover_policy()

    def _package_install(self, argv, timeout=120, env=None):
        """Compatibility alias; new stages should use package_transaction."""
        return self.package_transaction(argv, timeout=timeout, env=env)

    def _install(self, group):
        self._assert_root()
        self._paths()
        requested = self.lock["requested"][group]
        self._apt(["update"])
        for name, version in requested.items():
            self._available(name, version)
        pins = [name + "=" + version for name, version in requested.items()]
        simulation = self._apt(["-s", "--no-install-recommends", "--no-remove", "install", *pins])
        if re.search(r"^(Remv|Purg) ", simulation, re.M) or "DOWNGRADED" in simulation:
            raise PrerequisiteError("Package plan removes or downgrades existing packages", code="package_plan_downgrade")
        changes = {}
        for line in simulation.splitlines():
            if not line.startswith("Inst "):
                continue
            match = re.match(r"Inst (\S+)(?: \[[^\]]+\])? \((\S+)", line)
            if not match:
                raise PrerequisiteError("Unrecognized package simulation output")
            name, version = match.groups()
            name = name.removesuffix(":amd64")
            if name not in self.lock["groups"][group] or self.lock["packages"][name]["version"] != version:
                raise PrerequisiteError("Unpinned dependency would be installed: " + name, code="unpinned_dependency",
                                        public_details={"package": name, "version": version})
            self._available(name, version)
            changes[name] = version
        install_bytes = sum(self.lock["packages"][n]["installed_bytes"] for n in changes)
        # dpkg Installed-Size excludes generated initramfs and maintainer-script
        # output. Reserve a bounded allowance in addition to package payloads.
        generated_allowance = (GIB if group == "driver" else GIB // 4) if changes else 0
        root_bound = install_bytes + generated_allowance
        download_bytes = sum(self.lock["packages"][n]["size_bytes"] for n in changes)
        self._guard(root_bound)
        available = int(self._run(["df", "-B1", "--output=avail", str(self.data)]).splitlines()[-1])
        if available < download_bytes + GIB:
            raise PrerequisiteError("Insufficient verified data capacity for pinned package archives")
        all_pins = dict(requested, **changes)
        args = ["--yes", "--no-install-recommends", "--no-remove", "install",
                *[n + "=" + v for n, v in sorted(all_pins.items())]]
        self._apt(["--download-only", *args], timeout=3600)
        self._guard(root_bound)
        self._apt(["--no-download", *args], timeout=3600)
        if not self._installed(all_pins):
            raise PrerequisiteError("Package postcondition failed")
        self._guard()
        return {"changed_packages": changes, "download_bytes": download_bytes,
                "root_package_payload_bytes": install_bytes, "root_generated_allowance_bytes": generated_allowance,
                "root_package_reserved_bytes": root_bound, "ubuntu_snapshot": self.lock["ubuntu_snapshot"]}

    def apply_base(self):
        self._guard()
        self.recover_policy()
        if self.check_base():
            return {"changed": False}
        return {"changed": True, **self._install("base")}

    def _driver_facts(self):
        rows = self._maybe(["nvidia-smi", "--query-gpu=driver_version,pci.bus_id", "--format=csv,noheader,nounits"])
        module = self._maybe(["cat", "/sys/module/nvidia/version"])
        installed = self._maybe(["modinfo", "-F", "version", "nvidia"])
        parsed = [tuple(item.strip() for item in row.split(",")) for row in rows.splitlines() if row.strip()]
        if not parsed or any(len(row) != 2 or row[0] != module for row in parsed) or installed != module:
            return None
        expected = int(self.config.get("expected_gpu_count", 2))
        if len(parsed) != expected or len({row[1] for row in parsed}) != expected:
            return None
        version = tuple(int(item) for item in module.split(".")) if re.fullmatch(r"\d+\.\d+\.\d+", module) else ()
        minimum = tuple(int(item) for item in self.lock["compatibility"]["compatible_driver_minimum"].split("."))
        if version < minimum:
            return None
        return {"module_version": module, "gpu_count": expected, "gpu_pci_bus_ids": [row[1] for row in parsed]}

    def check_driver(self):
        self.guard()
        if ((self.state / "package-service-policy.json").exists()
                or (self.state / "package-service-policy.json").is_symlink()):
            return False
        if self.checkpoint_path.exists():
            self._validate_state_path(self.checkpoint_path)
            checkpoint = json.loads(self.checkpoint_path.read_text())
            if checkpoint.get("boot_id") == self._run(["cat", "/proc/sys/kernel/random/boot_id"]):
                return False
        return self._driver_facts() is not None

    def apply_driver(self):
        self._guard()
        self.recover_policy()
        if self.check_driver():
            return {"changed": False, "driver": self._driver_facts(), "gpu_container_gate": "PENDING runtime stage"}
        boot_id = self._run(["cat", "/proc/sys/kernel/random/boot_id"])
        if self.checkpoint_path.exists():
            protected_path(self.checkpoint_path)
            checkpoint = json.loads(self.checkpoint_path.read_text())
            if checkpoint["boot_id"] == boot_id:
                raise RebootRequired(checkpoint)
            raise PrerequisiteError("Driver remains invalid after reboot: verify firmware/module signing, selected kernel, GPU presence and module/userspace agreement",
                                    code="post_reboot_driver_invalid", public_details={"target_kernel": checkpoint["target_kernel"]})
        secure_boot = self._maybe(["mokutil", "--sb-state"])
        if not any(value in secure_boot for value in ("SecureBoot enabled", "SecureBoot disabled", "EFI variables are not supported")):
            raise PrerequisiteError("Cannot determine Secure Boot state before driver installation", code="secure_boot_state_unavailable")
        previous = self._maybe(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n", "*nvidia*", "linux-image-*"])
        self._paths()
        self._write_json(self.state / "driver-rollback-inventory.json", {"schema_version": 1,
                    "packages_before": previous, "kernel_before": self._run(["uname", "-r"]),
                    "note": "Previous kernel/packages preserved; no purge, autoremove or automatic reboot"})
        evidence = self._install("driver")
        checkpoint = {"schema_version": 1, "reboot_required": True, "boot_id": boot_id,
                      "secure_boot_enabled": "SecureBoot enabled" in secure_boot,
                      "target_kernel": self.lock["compatibility"]["driver_kernel"],
                      "package_evidence": evidence,
                      "message": "Driver packages installed. Reboot into kernel " + self.lock["compatibility"]["driver_kernel"] +
                                 ", then run ./install.sh resume --through driver --yes. No automatic reboot was performed."}
        self._write_json(self.checkpoint_path, checkpoint)
        self._guard()
        raise RebootRequired(checkpoint)
