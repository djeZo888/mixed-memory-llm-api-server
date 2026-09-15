"""Pinned container/toolkit stages; caller retains the installer/lifecycle lease.

No lifecycle/profile ownership or model activation lives here. All mutations use
Runner's writable command boundary. system_root/uid are test injection seams.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import tomllib
import urllib.request
import uuid

from .core import InstallError, Pending, Runner, digest
from .prerequisites import Prerequisites, PrerequisiteError, atomic_bytes, protected_path
from .storage_io import AnchoredRoot

UNITS = ("docker.service", "docker.socket", "containerd.service", "nvidia-cdi-refresh.path", "nvidia-cdi-refresh.service")
NVIDIA_RUNTIME = {"path": "nvidia-container-runtime", "args": []}
GIB = 1024 ** 3


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


class ContainerPackages(Prerequisites):
    """Reuse the I1 exact dependency solver, cache placement and service policy."""
    def __init__(self, config, runner, guard, *, lock, system_root=Path("/"), uid=0):
        super().__init__(config, runner, guard, policy_path=system_root / "usr/sbin/policy-rc.d")
        self.lock, self.uid, self._anchor = lock, uid, None

    def _ensure_directory(self, path):
        if not path.is_relative_to(self.data):
            raise InstallError("package_path_outside_data")
        with AnchoredRoot(str(self.data), self.guard, uid=self.uid) as root:
            root.mkdir(str(path.relative_to(self.data)))

    def _write_json(self, path, obj):
        with AnchoredRoot(str(self.data), self.guard, uid=self.uid) as root:
            relative = str(path.relative_to(self.data))
            root.mkdir(str(path.parent.relative_to(self.data)))
            root.atomic_json(relative, obj)

    def _atomic(self, path, content):
        root = self._anchor
        relative = str(path.relative_to(self.data))
        temporary = str(path.parent.relative_to(self.data) / (".container-" + uuid.uuid4().hex))
        with root.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY) as stream:
            stream.write(content)
            stream.fsync()
        root.replace(temporary, relative)

    def _apt_options(self):
        if self._anchor is None:
            raise InstallError("package_storage_anchor_required")
        prefix = self._anchor.proc_path()
        return [value.replace(str(self.data), prefix) for value in super()._apt_options()] + ["-o", "APT::Sandbox::User=root"]

    def _run(self, argv, timeout=60, env=None):
        if self._anchor is not None and env is not None:
            prefix = self._anchor.proc_path()
            env = {key: value.replace(str(self.data), prefix) for key, value in env.items()}
        return super()._run(argv, timeout=timeout, env=env)

    def require_package_api(self):
        required = ("package_identity", "prepare_package", "hold_package_lease", "run_package", "inspect_package")
        if any(not callable(getattr(self.runner, name, None)) for name in required):
            raise Pending("i1r_package_lease_integration_required")

    def _install(self, group):
        self.require_package_api()
        with AnchoredRoot(str(self.data), self.guard, uid=self.uid) as root:
            self._anchor = root
            try:
                return super()._install(group)
            finally:
                self._anchor = None

    def _paths(self):
        if self._anchor is None:
            raise InstallError("package_storage_anchor_required")
        self._guard()
        for path in [self.apt_root / "archives/partial", self.apt_root / "lists/partial",
                     self.apt_root / "tmp", self.apt_root / "sourceparts", self.data / "logs/installer", self.state]:
            self._ensure_directory(path)
        with self._anchor.directory(str((self.apt_root / "sourceparts").relative_to(self.data))) as sourceparts:
            if os.listdir(sourceparts.fileno()):
                raise InstallError("unexpected_package_sourceparts")
        snapshot = self.lock["ubuntu_snapshot"]
        sources = ("Types: deb\nURIs: https://snapshot.ubuntu.com/ubuntu/" + snapshot + "/\n"
                   "Suites: noble noble-updates noble-security\nComponents: main restricted universe multiverse\n"
                   "Architectures: amd64\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
                   "Check-Valid-Until: no\n")
        keys = self.apt_root / "keys"
        self._ensure_directory(keys)
        for name, record in self.lock["container_repositories"].items():
            target = keys / (name + ".asc")
            self._guard()
            relative = str(target.relative_to(self.data))
            if self._anchor.stat(relative, missing_ok=True) is not None:
                with self._anchor.open(relative) as stream:
                    content = stream.read(record["key_size_bytes"] + 1)
            else:
                # Key payload is bounded; there is no credential or argv input.
                try:
                    with urllib.request.urlopen(record["key_url"], timeout=30) as response:
                        if response.status != 200 or not response.url.startswith("https://"):
                            raise ValueError()
                        content = response.read(record["key_size_bytes"] + 1)
                except Exception:
                    raise PrerequisiteError("Pinned repository key unavailable", code="repository_key_unavailable") from None
            if (len(content) != record["key_size_bytes"] or
                    hashlib.sha256(content).hexdigest() != record["key_sha256"]):
                raise PrerequisiteError("Pinned repository key identity changed", code="repository_key_changed")
            self._guard()
            self._atomic(target, content)
            if name == "docker":
                sources += ("\nTypes: deb\nURIs: https://download.docker.com/linux/ubuntu\n"
                            "Suites: noble\nComponents: stable\nArchitectures: amd64\n")
            elif name == "nvidia":
                sources += ("\nTypes: deb\nURIs: https://nvidia.github.io/libnvidia-container/stable/deb/amd64/\n"
                            "Suites: /\nArchitectures: amd64\n")
            else:
                raise InstallError("unknown_container_repository")
            sources += "Signed-By: " + self._anchor.proc_path(relative) + "\n"
        self._guard()
        self._atomic(self.apt_root / "ubuntu.sources", sources.encode())


class ContainerStage:
    def __init__(self, config, runner, guard, *, prereqs=None, system_root=Path("/"), uid=0, lock=None):
        self.config, self.runner, self.guard = config, runner, guard
        self.system_root, self.uid = Path(system_root).resolve(), uid
        self.lock = lock or json.loads(Path(__file__).with_name("versions.lock.json").read_text())
        self.data = Path(config["data_dir"])
        self.state = self.data / "services/installer"
        self.prereqs = prereqs or ContainerPackages(config, runner, guard, lock=self.lock, system_root=self.system_root, uid=uid)
        self.mask_marker = self.state / "container-service-masks.json"
        self.gpu_record = self.state / "gpu-container-gate.json"

    def _system(self, path):
        return self.system_root / path.lstrip("/")

    def _run(self, argv, timeout=60):
        try:
            return self.runner.run(argv, timeout=timeout).strip()
        except Exception:
            raise InstallError("container_command_failed") from None

    def _maybe(self, argv):
        try:
            return self._run(argv)
        except InstallError:
            return ""

    def _roots(self):
        registration = self.guard()
        if not isinstance(registration, dict) or not isinstance(registration.get("roots"), dict):
            raise InstallError("container_storage_registration_required")
        roots = registration["roots"]
        expected = {"docker": self.data / "docker", "containerd": self.data / "containerd",
                    "state": self.state, "logs": self.data / "logs", "build": self.data / "build"}
        if any(roots.get(name) != str(path) for name, path in expected.items()):
            raise InstallError("container_registered_roots_mismatch")
        return roots

    def _safe(self, path, *, create=False):
        """Tiny OS configuration files only; payload/state writes use storage I/O."""
        path = Path(path)
        boundary = self.data if path.is_relative_to(self.data) else self.system_root
        current = boundary
        protected_path(current, directory=True)
        for part in path.parent.relative_to(boundary).parts:
            current /= part
            if create and not current.exists():
                current.mkdir(mode=0o755)
            if current.exists() or current.is_symlink():
                protected_path(current, directory=True)
        if path.exists() or path.is_symlink():
            protected_path(path)

    def _read(self, path):
        self._safe(path)
        if not path.exists():
            return None
        if path.stat().st_size > 1024 * 1024:
            raise InstallError("container_config_too_large")
        return path.read_bytes()

    def _write_system(self, path, content):
        self.guard()
        self._safe(path, create=True)
        if self._read(path) != content:
            if path.name == "50-local-ai-storage.conf" and path.exists():
                raise InstallError("container_storage_dropin_conflict")
            atomic_bytes(path, content, mode=0o644)

    def _state_read(self, path):
        with AnchoredRoot(str(self.data), self.guard, uid=self.uid) as root:
            relative = str(path.relative_to(self.data))
            return root.read_json(relative) if root.stat(relative, missing_ok=True) is not None else None

    def _state_write(self, path, value):
        with AnchoredRoot(str(self.data), self.guard, uid=self.uid) as root:
            root.mkdir(str(path.parent.relative_to(self.data)))
            root.atomic_json(str(path.relative_to(self.data)), value)

    def _state_unlink(self, path):
        with AnchoredRoot(str(self.data), self.guard, uid=self.uid) as root:
            root.unlink(str(path.relative_to(self.data)), missing_ok=True)

    def _active(self, unit):
        result = self._maybe(["systemctl", "is-active", unit])
        if result in {"activating", "deactivating", "reloading"}:
            raise InstallError("container_service_transition_in_progress")
        return result == "active"

    def _docker_info(self):
        raw = self._maybe(["docker", "info", "--format", "{{json .}}"])
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except ValueError:
            return None

    def _configs(self):
        roots = self._roots()
        docker_path = self._system("/etc/docker/daemon.json")
        containerd_path = self._system("/etc/containerd/config.toml")
        docker_bytes, containerd_bytes = self._read(docker_path), self._read(containerd_path)
        try:
            docker = json.loads(docker_bytes) if docker_bytes is not None else {}
            containerd = tomllib.loads(containerd_bytes.decode()) if containerd_bytes is not None else {}
            if not isinstance(docker, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise InstallError("invalid_container_configuration") from None
        for existing, expected in ((docker.get("data-root"), roots["docker"]),
                                   (containerd.get("root"), roots["containerd"])):
            if existing is not None and existing != expected:
                raise InstallError("container_service_root_mismatch")
        if containerd.get("version", 3) not in {2, 3}:
            raise InstallError("containerd_config_version_requires_review")
        if containerd.get("grpc", {}).get("tcp_address"):
            raise InstallError("containerd_api_exposure_requires_review")
        if containerd.get("imports"):
            raise InstallError("containerd_imports_require_review")
        if docker.get("hosts") and docker["hosts"] != ["unix:///var/run/docker.sock"]:
            raise InstallError("docker_api_exposure_requires_review")
        runtimes = docker.get("runtimes", {})
        if not isinstance(runtimes, dict) or ("nvidia" in runtimes and runtimes["nvidia"] not in (NVIDIA_RUNTIME, {"path": "/usr/bin/nvidia-container-runtime", "args": []})):
            raise InstallError("nvidia_runtime_configuration_conflict")
        # Existing root payload must never be hidden by changing a config file.
        for relative in ("/var/lib/docker", "/var/lib/containerd"):
            old = self._system(relative)
            self._safe(old / ".check")
            if old.exists() and any(old.iterdir()):
                raise InstallError("existing_container_root_payload_requires_migration")
        required = dict(docker)
        required["data-root"] = roots["docker"]
        required["runtimes"] = dict(runtimes)
        required["runtimes"].setdefault("nvidia", NVIDIA_RUNTIME)
        required.setdefault("log-driver", "local")
        if required["log-driver"] not in {"local", "json-file", "none"}:
            raise InstallError("docker_logging_policy_requires_review")
        required.setdefault("log-opts", {} if required["log-driver"] == "none" else {"max-size": "10m", "max-file": "3"})
        if not isinstance(required["log-opts"], dict):
            raise InstallError("invalid_docker_logging_policy")
        if required["log-driver"] != "none":
            options = required["log-opts"]
            if not re.fullmatch(r"[1-9][0-9]*(?:[kKmMgG])?", str(options.get("max-size", ""))) or not re.fullmatch(r"[1-9][0-9]*", str(options.get("max-file", ""))):
                raise InstallError("unbounded_docker_logging_requires_review")
        text = containerd_bytes.decode() if containerd_bytes is not None else "version = 3\n"
        if "root" not in containerd:
            text = "root = " + json.dumps(roots["containerd"]) + "\n" + text
        if containerd.get("state", "/run/containerd") != "/run/containerd":
            raise InstallError("containerd_state_path_requires_review")
        return ((docker_path, docker_bytes, _json_bytes(required)),
                (containerd_path, containerd_bytes, text.encode()))

    def _dropin(self):
        # A private bind retains the verified filesystem after a lazy detach;
        # BindsTo also tears the service down on an ordinary mount-unit loss.
        # Unit-name escaping follows systemd.unit(5), including escaped hyphens.
        path = str(self.data).strip("/")
        escaped = "".join("-" if c == "/" else c if c.isascii() and (c.isalnum() or c in "_ .") and c != " " else "\\x" + format(ord(c), "02x") for c in path)
        mount_unit = (escaped or "-") + ".mount"
        return ("[Unit]\nRequiresMountsFor=" + str(self.data) + "\nBindsTo=" + mount_unit +
                "\nAfter=" + mount_unit + "\n[Service]\nPrivateMounts=yes\nBindPaths=" + str(self.data) +
                "\nEnvironment=DOCKER_TMPDIR=" + str(self.data / "cache/docker-tmp") +
                "\nEnvironment=TMPDIR=" + str(self.data / "cache/container-tmp") +
                "\nStandardOutput=null\nStandardError=null\n").encode()

    def _service_contract(self):
        for unit in ("docker.service", "containerd.service"):
            command = self._maybe(["systemctl", "show", unit, "--property=ExecStart", "--value"])
            # Vendor systemd flags are expected; any path override needs explicit
            # review because it can take precedence over the checked files.
            if not command and self._active(unit):
                raise InstallError("container_service_command_unverified")
            if re.search(r"(?:^|[\s;])(?:--(?:data-root|root|config(?:-file)?|state|address)(?:=|\s|$)|-[gcrsa](?:\S*|$))", command) or "tcp://" in command:
                raise InstallError("container_service_override_requires_review")
        info = self._docker_info()
        if info and info.get("DockerRootDir") != str(self.data / "docker"):
            raise InstallError("container_service_root_mismatch")
        return info

    def check(self):
        self._roots()
        if self.mask_marker.exists() or (self.state / "package-service-policy.json").exists():
            return False
        configs = self._configs()
        info = self._service_contract()
        if not self.prereqs._installed({**self.lock["requested"]["docker"], **self.lock["requested"]["toolkit"]}):
            return False
        # Semantically compatible daemon JSON is preserved byte-for-byte.
        if configs[0][1] is None or json.loads(configs[0][1]) != json.loads(configs[0][2]) or configs[1][1] != configs[1][2]:
            return False
        for unit in ("docker.service", "containerd.service"):
            if self._read(self._system("/etc/systemd/system/" + unit + ".d/50-local-ai-storage.conf")) != self._dropin():
                return False
            if not self._active(unit):
                return False
            environment = self._maybe(["systemctl", "show", unit, "--property=Environment", "--value"])
            bindings = self._maybe(["systemctl", "show", unit, "--property=BindPaths", "--value"])
            private = self._maybe(["systemctl", "show", unit, "--property=PrivateMounts", "--value"])
            required_env = {"DOCKER_TMPDIR=" + str(self.data / "cache/docker-tmp"), "TMPDIR=" + str(self.data / "cache/container-tmp")}
            if private != "yes" or not required_env.issubset(set(shlex.split(environment))) or str(self.data) not in {item.split(":", 1)[0] for item in bindings.split()}:
                return False
        if not (info and "nvidia" in info.get("Runtimes", {})):
            return False
        try:
            actual = self._run(["containerd", "--config", str(self._system("/etc/containerd/config.toml")), "config", "dump"])
            return tomllib.loads(actual).get("root") == str(self.data / "containerd")
        except (ValueError, InstallError):
            return False

    def recover_masks(self):
        saved = self._state_read(self.mask_marker)
        if not saved:
            return
        if saved.get("schema_version") != 1 or any(unit not in UNITS for unit in saved.get("created", [])):
            raise InstallError("invalid_container_mask_checkpoint")
        for unit in saved["created"]:
            path = self._system("/run/systemd/system/" + unit)
            if path.is_symlink() and os.readlink(path) == "/dev/null":
                path.unlink()
            elif path.exists() or path.is_symlink():
                raise InstallError("container_service_mask_changed")
        self._run(["systemctl", "daemon-reload"])
        self.guard()
        self._state_unlink(self.mask_marker)

    @contextmanager
    def _inhibit(self):
        created = []
        for unit in UNITS:
            path = self._system("/run/systemd/system/" + unit)
            self._safe(path.parent / ".check", create=True)
            if path.exists() or path.is_symlink():
                if not path.is_symlink() or os.readlink(path) != "/dev/null":
                    raise InstallError("existing_runtime_unit_override_requires_review")
            else:
                created.append(unit)
        self._state_write(self.mask_marker, {"schema_version": 1, "created": created})
        try:
            for unit in created:
                os.symlink("/dev/null", self._system("/run/systemd/system/" + unit))
            self._run(["systemctl", "daemon-reload"])
            yield
        finally:
            # I1R must establish exact transaction quiescence before either
            # inhibitor is restored. Unknown ownership leaves masks in place.
            self.prereqs.recover_policy()
            for unit in created:
                path = self._system("/run/systemd/system/" + unit)
                if path.is_symlink() and os.readlink(path) == "/dev/null":
                    path.unlink()
                elif path.exists() or path.is_symlink():
                    raise InstallError("container_service_mask_changed")
            self._run(["systemctl", "daemon-reload"])
            self.guard()
            self._state_unlink(self.mask_marker)

    def apply(self):
        self._roots()
        self.prereqs._assert_root()
        if any(not self.prereqs._installed(self.lock["requested"][group]) for group in ("docker", "toolkit")):
            self.prereqs.require_package_api()
        self.prereqs.recover_policy()
        self.recover_masks()
        if self.check():
            return {"changed": False, "packages": {**self.lock["requested"]["docker"], **self.lock["requested"]["toolkit"]}}
        configs = self._configs()
        self._service_contract()
        if any(self._active(unit) for unit in UNITS):
            raise InstallError("active_container_service_requires_coordinated_change")
        for root in (self.data / "docker", self.data / "containerd", self.data / "cache/docker-tmp", self.data / "cache/container-tmp"):
            self.prereqs._ensure_directory(root)
        evidence = {}
        with self._inhibit():
            # Files are in place BEFORE dpkg (including first package start).
            for path, old, new in configs:
                if old is not None:
                    backup = self.state / ("container-config-before-" + hashlib.sha256(str(path).encode()).hexdigest() + ".json")
                    saved = self._state_read(backup)
                    if saved is None:
                        self._state_write(backup, {"path": str(path), "sha256": hashlib.sha256(old).hexdigest(), "content_hex": old.hex()})
                    else:
                        try:
                            if saved["path"] != str(path) or hashlib.sha256(bytes.fromhex(saved["content_hex"])).hexdigest() != saved["sha256"]:
                                raise ValueError()
                        except (KeyError, ValueError, TypeError):
                            raise InstallError("container_original_backup_changed") from None
                if old is None or (path.suffix == ".json" and json.loads(old) != json.loads(new)) or (path.suffix != ".json" and old != new):
                    self._write_system(path, new)
            for unit in ("docker.service", "containerd.service"):
                self._write_system(self._system("/etc/systemd/system/" + unit + ".d/50-local-ai-storage.conf"), self._dropin())
            for group in ("docker", "toolkit"):
                if not self.prereqs._installed(self.lock["requested"][group]):
                    evidence[group] = self.prereqs._install(group)
            self._run(["dockerd", "--validate", "--config-file", str(self._system("/etc/docker/daemon.json"))])
            actual = self._run(["containerd", "--config", str(self._system("/etc/containerd/config.toml")), "config", "dump"])
            try:
                if tomllib.loads(actual).get("root") != str(self.data / "containerd"):
                    raise ValueError()
            except ValueError:
                raise InstallError("containerd_effective_root_mismatch") from None
            self.guard()
        self._service_contract()
        self.guard()
        self._run(["systemctl", "start", "containerd.service", "docker.service"], timeout=120)
        self.guard()
        if not self.check():
            raise InstallError("container_postcondition_failed")
        result = {"changed": True, "packages": evidence, "storage_roots": self._roots(),
                  "gpu_gate": "NOT_RUN", "service_effects": "containerd/docker started; no model activated"}
        self._state_write(self.state / "container-evidence.json", result)
        return result

    def _gpu_identity(self):
        raw = self._run(["nvidia-smi", "--query-gpu=driver_version,pci.bus_id", "--format=csv,noheader,nounits"])
        rows = sorted(tuple(x.strip().lower() for x in row.split(",")) for row in raw.splitlines() if row.strip())
        if len(rows) != self.config.get("expected_gpu_count", 2) or any(len(row) != 2 for row in rows) or len({row[1] for row in rows}) != len(rows):
            raise InstallError("gpu_container_host_identity_invalid")
        image = self.lock["gpu_container_gate"]["image"]
        if not re.fullmatch(r"[A-Za-z0-9_./:-]+@sha256:[0-9a-f]{64}", image):
            raise InstallError("gpu_container_image_not_pinned")
        raw = self._maybe(["docker", "image", "inspect", image, "--format", "{{json .}}"])
        try:
            inspect = json.loads(raw)
            repo_digest = image.split(":", 1)[0] + "@" + image.split("@", 1)[1]
            artifact = self.lock["gpu_container_gate"]["registry_artifact"]
            known_ids = {artifact.get(key) for key in ("config_digest", "platform_manifest_digest", "index_digest")}
            known_ids.discard(None)
            if (inspect.get("Architecture") != "amd64" or inspect.get("Os") != "linux" or
                    repo_digest not in inspect.get("RepoDigests", []) or inspect.get("Id") not in known_ids):
                raise ValueError()
        except (ValueError, AttributeError):
            raise InstallError("gpu_container_image_identity_mismatch") from None
        return {"image": image, "image_id": inspect["Id"], "host_gpus": [list(row) for row in rows],
                "boot_id": self._run(["cat", "/proc/sys/kernel/random/boot_id"]),
                "lock_identity": digest(self.lock), "config_identity": digest(self.config)}

    def _evidence_class(self):
        return "ACTUAL_GPU_COMMAND" if type(self.runner) is Runner else "SYNTHETIC_FIXTURE"

    def check_gpu(self):
        if not self.check():
            return False
        saved = self._state_read(self.gpu_record)
        if not saved:
            return False
        try:
            return saved.get("identity") == self._gpu_identity() and saved.get("result") == "PASS" and saved.get("evidence_class") == self._evidence_class()
        except InstallError:
            return False

    def apply_gpu(self):
        if not self.check():
            raise InstallError("gpu_container_engine_not_verified")
        if self.check_gpu():
            return {"changed": False, **self._state_read(self.gpu_record)}
        image = self.lock["gpu_container_gate"]["image"]
        self.guard()
        if not self._maybe(["docker", "image", "inspect", image, "--format", "{{json .}}"]):
            record = self.lock["gpu_container_gate"]
            needed = record["registry_artifact"]["compressed_artifact_bytes"] + record["capacity_reserve_bytes"]
            available = int(self._run(["df", "-B1", "--output=avail", str(self.data)]).splitlines()[-1])
            if available < needed:
                raise InstallError("gpu_container_capacity_insufficient")
            self._run(["docker", "pull", "--platform", "linux/amd64", image], timeout=3600)
        self.guard()
        identity = self._gpu_identity()
        command = ["docker", "run", "--rm", "--pull", "never", "--network", "none", "--read-only", "--gpus", "all", image,
                   "nvidia-smi", "--query-gpu=driver_version,pci.bus_id", "--format=csv,noheader,nounits"]
        output = self._run(command, timeout=120)
        self.guard()
        rows = sorted([x.strip().lower() for x in row.split(",")] for row in output.splitlines() if row.strip())
        if rows != identity["host_gpus"] or self._gpu_identity() != identity:
            raise InstallError("gpu_container_identity_or_execution_failed")
        result = {"schema_version": 1, "identity": identity, "result": "PASS", "evidence_class": self._evidence_class(),
                  "command": command, "output_sha256": hashlib.sha256(output.encode()).hexdigest()}
        self._state_write(self.gpu_record, result)
        return {"changed": True, **result}
